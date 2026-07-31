# -*- coding: utf-8 -*-
"""Motor del Sugerido de Compras por rotación de ventas (Fase B, REQ-C01→C03).

Separado de la pantalla a propósito: el wizard de hoy y la pantalla definitiva
de mañana (form u OWL) consumen los mismos métodos. Todo se calcula POR LOTES
(_read_group / lecturas masivas) — el POC hacía una búsqueda por producto y no
aguantaba el catálogo real.

Convención de unidades: TODO se presenta en la UNIDAD DE COMPRA del producto
(REQ-C03), como en la pantalla de ADG. Los costos van SIN ITBIS (así los
guarda la base y así los presenta el sugerido del cliente).
"""
from dateutil.relativedelta import relativedelta

from odoo import _, fields, models
from odoo.exceptions import UserError


class SugeridoMotor(models.AbstractModel):
    _name = 'surtidora.sugerido.motor'
    _description = 'Motor de cálculo del sugerido de compras'

    def calcular(self, suplidor, company, fecha_desde, fecha_hasta, dias_abastecer):
        """Filas del sugerido para un suplidor. Devuelve una lista de dicts
        (una por producto) con todas las cifras en la unidad de compra."""
        productos = self._productos_del_suplidor(suplidor, company)
        if not productos:
            raise UserError(_(
                'El suplidor %s no tiene productos asociados '
                '(pestaña Compras del producto).', suplidor.display_name))
        dias_periodo = max((fecha_hasta - fecha_desde).days, 1)

        ventas = self._total_por_producto_en_base(
            'sale.order.line', productos, company,
            [('order_id.state', '=', 'sale'),
             ('order_id.date_order', '>=', fecha_desde),
             ('order_id.date_order', '<=', fecha_hasta)],
            'product_uom_qty', 'product_uom_id')
        pendientes = self._oc_pendiente_por_producto(productos, company)
        ultimas = self._ultima_compra_por_producto(productos, suplidor, company)
        refs = self._referencias_suplidor(productos, suplidor)

        filas = []
        for producto in productos.with_company(company):
            base = producto.uom_id
            uom_compra = producto.surtidora_uom_compra_id or base
            factor = uom_compra._compute_quantity(1.0, base, round=False) or 1.0

            salidas_base = ventas.get(producto.id, 0.0)
            ventas_dia = salidas_base / dias_periodo / factor
            existencia = producto.qty_available / factor
            pendiente = pendientes.get(producto.id, 0.0) / factor
            necesaria = ventas_dia * dias_abastecer
            ultima = ultimas.get(producto.id, {})

            filas.append({
                'product_id': producto.id,
                'uom_compra_id': uom_compra.id,
                'ref_suplidor': refs.get(producto.product_tmpl_id.id, ''),
                'fecha_ultima_compra': ultima.get('fecha'),
                'cantidad_ultima_compra': ultima.get('cantidad', 0.0) / factor,
                'existencia_actual': existencia,
                'salidas_periodo': salidas_base / factor,
                'ventas_dia': ventas_dia,
                'ordenes_pendientes': pendiente,
                'cant_necesaria': necesaria,
                'cant_sugerida': necesaria - existencia - pendiente,
                'costo_uom_compra': producto.standard_price * factor,
            })
        return filas

    # ------------------------------------------------------------------
    # Agregados por lote
    # ------------------------------------------------------------------
    def _productos_del_suplidor(self, suplidor, company):
        """Productos comprables del suplidor en la compañía (REQ-C01)."""
        return self.env['product.product'].search([
            ('seller_ids.partner_id', '=', suplidor.id),
            ('purchase_ok', '=', True),
            ('company_id', 'in', [False, company.id]),
        ])

    def _total_por_producto_en_base(self, modelo, productos, company, domain_extra,
                                    campo_qty, campo_uom):
        """Suma de cantidades por producto CONVERTIDA A UNIDAD BASE.

        Las líneas pueden venir en cualquier empaque (una venta de '1 Caja de
        18' guarda qty=1 en esa UdM) — se agrupa por (producto, UdM) y se
        convierte cada subtotal. Sumar la columna directo estaría mal."""
        grupos = self.env[modelo]._read_group(
            [('product_id', 'in', productos.ids),
             ('company_id', '=', company.id)] + domain_extra,
            ['product_id', campo_uom], [f'{campo_qty}:sum'])
        totales = {}
        for producto, uom, subtotal in grupos:
            base = producto.uom_id
            cantidad = uom._compute_quantity(subtotal, base, round=False) \
                if uom and uom != base else subtotal
            totales[producto.id] = totales.get(producto.id, 0.0) + cantidad
        return totales

    def _oc_pendiente_por_producto(self, productos, company):
        """Cantidad ordenada y aún no recibida, en unidad base (REQ-C02)."""
        grupos = self.env['purchase.order.line']._read_group(
            [('product_id', 'in', productos.ids),
             ('company_id', '=', company.id),
             ('order_id.state', 'in', ('purchase', 'done'))],
            ['product_id', 'product_uom_id'],
            ['product_qty:sum', 'qty_received:sum'])
        pendientes = {}
        for producto, uom, ordenada, recibida in grupos:
            base = producto.uom_id
            resto = max((ordenada or 0.0) - (recibida or 0.0), 0.0)
            if uom and uom != base:
                resto = uom._compute_quantity(resto, base, round=False)
            pendientes[producto.id] = pendientes.get(producto.id, 0.0) + resto
        return pendientes

    def _ultima_compra_por_producto(self, productos, suplidor, company):
        """Fecha y cantidad (en base) de la última compra a ESTE suplidor."""
        lineas = self.env['purchase.order.line'].search_read(
            [('product_id', 'in', productos.ids),
             ('company_id', '=', company.id),
             ('partner_id', '=', suplidor.id),
             ('order_id.state', 'in', ('purchase', 'done'))],
            ['product_id', 'product_uom_id', 'product_qty', 'date_planned'],
            order='date_planned desc')
        ultimas = {}
        uoms = self.env['uom.uom']
        for linea in lineas:
            pid = linea['product_id'][0]
            if pid in ultimas:
                continue
            producto = self.env['product.product'].browse(pid)
            cantidad = linea['product_qty']
            uom = uoms.browse(linea['product_uom_id'][0]) if linea['product_uom_id'] else False
            if uom and uom != producto.uom_id:
                cantidad = uom._compute_quantity(cantidad, producto.uom_id, round=False)
            ultimas[pid] = {'fecha': linea['date_planned'], 'cantidad': cantidad}
        return ultimas

    def _referencias_suplidor(self, productos, suplidor):
        """Referencia del suplidor por plantilla (REQ-C04 — va al grid y a la OC)."""
        infos = self.env['product.supplierinfo'].search_read(
            [('partner_id', '=', suplidor.id),
             ('product_tmpl_id', 'in', productos.product_tmpl_id.ids)],
            ['product_tmpl_id', 'product_code'])
        return {i['product_tmpl_id'][0]: i['product_code'] or '' for i in infos}

    # ------------------------------------------------------------------
    # Detalle del producto seleccionado (iteración 2 — REQ-C05/C06)
    # ------------------------------------------------------------------
    MESES = ('Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun',
             'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic')

    def detalle_producto(self, producto, company, dias_abastecer):
        """Panel "Información del producto seleccionado" de la captura 14."""
        producto = producto.with_company(company)
        ultima = self._ultimas_compras(producto, company, limite=1)
        ultima = ultima[0] if ultima else {}
        hoy = fields.Date.context_today(self)
        dias_desde = (hoy - ultima['fecha'].date()).days if ultima.get('fecha') else 0
        return {
            'ultimo_costo_base': ultima.get('costo_base', 0.0),
            'costo_promedio': producto.standard_price,
            'dias_desde_compra': dias_desde,
            'existencia_actual': producto.qty_available,
            'dev_ventas': self._devoluciones(producto, company, de_ventas=True),
            'dev_compras': self._devoluciones(producto, company, de_ventas=False),
        }

    def matriz_mensual(self, producto, company, meses=12):
        """Matriz mensual comprado vs vendido, en unidad base (REQ-C05).

        El argumento de Adelso contra pedidos inflados: "usted vende mucho de
        esto" → "mentira, una caja mensual"."""
        hoy = fields.Date.context_today(self)
        inicio = hoy.replace(day=1) - relativedelta(months=meses - 1)

        vendidas = self._lineas_con_fecha(
            'sale.order.line', producto, company,
            [('order_id.state', '=', 'sale'), ('order_id.date_order', '>=', inicio)],
            'product_uom_qty', 'product_uom_id')
        compradas = self._lineas_con_fecha(
            'purchase.order.line', producto, company,
            [('order_id.state', 'in', ('purchase', 'done')), ('date_planned', '>=', inicio)],
            'product_qty', 'product_uom_id')

        filas = []
        cursor = inicio
        for _i in range(meses):
            clave = (cursor.year, cursor.month)
            filas.append({
                'mes': f'{self.MESES[cursor.month - 1]} {cursor.year}',
                'comprado': compradas.get(clave, 0.0),
                'vendido': vendidas.get(clave, 0.0),
            })
            cursor += relativedelta(months=1)
        return filas

    def _lineas_con_fecha(self, modelo, producto, company, domain_extra,
                          campo_qty, campo_uom):
        """Cantidades por (año, mes) en unidad base, para UN producto."""
        campos = [campo_qty, campo_uom]
        con_fecha_propia = modelo == 'purchase.order.line'
        campos.append('date_planned' if con_fecha_propia else 'order_id')
        lineas = self.env[modelo].search_read(
            [('product_id', '=', producto.id),
             ('company_id', '=', company.id)] + domain_extra, campos)
        fechas_orden = {}
        if not con_fecha_propia:
            ordenes = {l['order_id'][0] for l in lineas if l['order_id']}
            fechas_orden = {o['id']: o['date_order'] for o in self.env['sale.order'].search_read(
                [('id', 'in', list(ordenes))], ['date_order'])}
        uoms = self.env['uom.uom']
        base = producto.uom_id
        totales = {}
        for linea in lineas:
            fecha = linea['date_planned'] if con_fecha_propia \
                else fechas_orden.get(linea['order_id'][0])
            if not fecha:
                continue
            cantidad = linea[campo_qty]
            uom = uoms.browse(linea[campo_uom][0]) if linea[campo_uom] else False
            if uom and uom != base:
                cantidad = uom._compute_quantity(cantidad, base, round=False)
            clave = (fecha.year, fecha.month)
            totales[clave] = totales.get(clave, 0.0) + cantidad
        return totales

    def _ultimas_compras(self, producto, company, limite=10):
        """Últimas compras SIN filtrar suplidor (REQ-C06 — el caso Trululú:
        un producto con 7 distribuidores, se ve a quién y a cuánto se compró)."""
        lineas = self.env['purchase.order.line'].search_read(
            [('product_id', '=', producto.id),
             ('company_id', '=', company.id),
             ('order_id.state', 'in', ('purchase', 'done'))],
            ['date_planned', 'product_qty', 'product_uom_id', 'price_unit',
             'partner_id', 'order_id'],
            order='date_planned desc', limit=limite)
        base = producto.uom_id
        uoms = self.env['uom.uom']
        filas = []
        for linea in lineas:
            uom = uoms.browse(linea['product_uom_id'][0]) if linea['product_uom_id'] else base
            factor = uom._compute_quantity(1.0, base, round=False) or 1.0
            filas.append({
                'fecha': linea['date_planned'],
                'cantidad': linea['product_qty'],
                'unidad': uom.name,
                'costo': linea['price_unit'],
                'costo_base': linea['price_unit'] / factor if factor else linea['price_unit'],
                'suplidor': linea['partner_id'][1] if linea['partner_id'] else '',
                'orden': linea['order_id'][1] if linea['order_id'] else '',
            })
        return filas

    def _oc_pendientes_producto(self, producto, company):
        """Panel "Órdenes de Compra Pendientes" del producto (captura 14)."""
        lineas = self.env['purchase.order.line'].search_read(
            [('product_id', '=', producto.id),
             ('company_id', '=', company.id),
             ('order_id.state', 'in', ('purchase', 'done'))],
            ['order_id', 'date_planned', 'partner_id', 'product_qty',
             'qty_received', 'product_uom_id'],
            order='date_planned desc', limit=20)
        filas = []
        for linea in lineas:
            pendiente = max(linea['product_qty'] - linea['qty_received'], 0.0)
            if not pendiente:
                continue
            filas.append({
                'orden': linea['order_id'][1] if linea['order_id'] else '',
                'fecha': linea['date_planned'],
                'suplidor': linea['partner_id'][1] if linea['partner_id'] else '',
                'ordenada': linea['product_qty'],
                'pendiente': pendiente,
                'unidad': linea['product_uom_id'][1] if linea['product_uom_id'] else '',
            })
        return filas

    def _devoluciones(self, producto, company, de_ventas):
        """Devoluciones acumuladas (movimientos de retorno hechos), en base."""
        usage = 'customer' if de_ventas else 'supplier'
        grupos = self.env['stock.move']._read_group(
            [('product_id', '=', producto.id),
             ('company_id', '=', company.id),
             ('state', '=', 'done'),
             ('origin_returned_move_id', '!=', False),
             ('location_id.usage' if de_ventas else 'location_dest_id.usage', '=', usage)],
            [], ['quantity:sum'])
        return grupos[0][0] or 0.0 if grupos else 0.0

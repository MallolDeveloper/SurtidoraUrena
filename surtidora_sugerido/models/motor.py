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
from odoo import _, models
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

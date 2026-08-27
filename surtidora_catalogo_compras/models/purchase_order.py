# -*- coding: utf-8 -*-
"""Lo que hace falta saber de un producto ANTES de pedirlo, en su tarjeta.

Odoo enseña el precio de la tarifa: lo que el suplidor pide hoy. Este módulo
añade lo que se mira para decidir si ese precio es bueno y si vale la pena
pedirlo:

    · cuándo y a cuánto se le compró por última vez A ESE suplidor
    · cuánto de esa última compra se ha vendido, y en cuántos días
    · quién se lo llevó por última vez, y cuándo
    · qué otros suplidores lo han vendido, y a cuánto
    · el costo de la ficha, PERO solo si no coincide con la tarifa

El catálogo pide los datos de las tarjetas visibles en UNA sola llamada a
`_get_product_catalog_order_line_info`, que recibe el lote completo. Por eso
todo aquí se resuelve en dos consultas por página, no una por tarjeta.

Y se engancha AHÍ, no en `_get_product_catalog_order_data`, aunque ese último
parezca el sitio natural. Odoo arma la respuesta por DOS caminos según el
producto ya esté o no en la orden:

    ya en la orden  ->  purchase.order.line._get_product_catalog_lines_data()
    todavía no      ->  purchase.order._get_product_catalog_order_data()

Colgarse del segundo deja sin dato justo las tarjetas que el comprador ya
tocó — que son las que está mirando. `_get_product_catalog_order_line_info`
es donde los dos caminos vuelven a juntarse.
"""
from odoo import _, fields, models
from odoo.tools.misc import format_amount, format_date

# Estados en los que una orden ya es una compra de verdad. Un borrador no es
# una compra: el precio todavía se está negociando y nadie pagó nada.
_ESTADOS_COMPRADOS = ('purchase', 'done')

# Cuántos suplidores alternativos caben en la tarjeta sin volverla ilegible.
# No es un límite de datos sino de espacio: el histórico completo ya se ve en
# la ficha del producto.
_OTROS_SUPLIDORES_MAX = 2

# Cómo se llama al cliente de una venta de mostrador sin nombre. No es un dato
# que falte: es que se vendió al público.
_MOSTRADOR = 'Mostrador'


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    def _get_product_catalog_order_line_info(self, product_ids, child_field=False, **kwargs):
        datos = super()._get_product_catalog_order_line_info(
            product_ids, child_field=child_field, **kwargs)
        productos = self.env['product.product'].browse(product_ids).exists()
        for producto_id, extra in self._surtidora_datos_de_compra(productos, datos).items():
            if producto_id in datos:
                datos[producto_id].update(extra)
        return datos

    # ------------------------------------------------------------------
    # Orquestación
    # ------------------------------------------------------------------
    def _surtidora_datos_de_compra(self, products, datos_nativos):
        """{product_id: {...}} con todo lo que este módulo añade a la tarjeta."""
        # En una orden nueva todavía no hay suplidor, y sin suplidor esto no
        # significa nada: la gracia es "cuánto le pagué A ÉL".
        if len(self) != 1 or not self.partner_id or not products:
            return {}

        lineas = self._surtidora_lineas_compradas(products)
        ordenes = self._surtidora_ordenes_de(lineas) if lineas else {}
        ultimas = self._surtidora_ultima_por_suplidor(lineas, ordenes)
        unidades = self._surtidora_unidad_de_la_tarjeta(products, datos_nativos)
        ventas = self._surtidora_ventas(products)

        resultado = {}
        for producto in products:
            nombre_unidad, unidades_base = unidades[producto.id]
            propias = ultimas.get(producto.id, {})
            del_producto = ventas.get(producto.id) or {}
            ficha = {}
            ficha.update(self._surtidora_ultima_compra(
                producto, propias, unidades_base, nombre_unidad))
            ficha.update(self._surtidora_rotacion(
                producto, propias, del_producto.get('movimientos') or []))
            ficha.update(self._surtidora_otros_suplidores(
                producto, propias, unidades_base))
            ficha.update(self._surtidora_costo_discrepante(
                producto, unidades_base, nombre_unidad,
                datos_nativos.get(producto.id) or {}))
            ficha.update(del_producto.get('ultima') or {})
            if ficha:
                resultado[producto.id] = ficha
        return resultado

    # ------------------------------------------------------------------
    # Los tres datos
    # ------------------------------------------------------------------
    def _surtidora_ultima_compra(self, producto, por_suplidor, unidades_base, nombre_unidad):
        """Última compra a ESTE suplidor. Si nunca se le compró, nada.

        Un 0.00 se leería como "se lo compré hoy gratis", así que se omite.
        """
        propia = por_suplidor.get(self.partner_id.id)
        if not propia:
            return {}
        orden, linea = propia
        return {
            'surtidoraUltimaFecha': format_date(self.env, orden['date_approve']),
            'surtidoraUltimoPrecio': format_amount(
                self.env,
                self._surtidora_precio_neto(orden, linea, producto.uom_id, unidades_base),
                self.currency_id),
            'surtidoraUltimaUnidad': nombre_unidad,
        }

    def _surtidora_otros_suplidores(self, producto, por_suplidor, unidades_base):
        """Quién más le ha vendido este producto, y a cuánto.

        Es la munición para negociar: "este mismo me lo dio otro más barato".
        Se excluye el suplidor de la orden, que ya sale como última compra, y
        se ordena por fecha para que arriba quede el precio más reciente —
        no el más barato, que puede ser de hace tres años.
        """
        otros = [
            (orden, linea, partner_id)
            for partner_id, (orden, linea) in por_suplidor.items()
            if partner_id != self.partner_id.id
        ]
        if not otros:
            return {}
        otros.sort(key=lambda x: x[0]['date_approve'], reverse=True)
        return {
            'surtidoraOtrosSuplidores': [{
                'suplidor': linea['partner_id'][1] if linea['partner_id'] else '',
                'fecha': format_date(self.env, orden['date_approve']),
                'precio': format_amount(
                    self.env,
                    self._surtidora_precio_neto(orden, linea, producto.uom_id, unidades_base),
                    self.currency_id),
            } for orden, linea, _pid in otros[:_OTROS_SUPLIDORES_MAX]],
        }

    def _surtidora_costo_discrepante(self, producto, unidades_base, nombre_unidad, datos_producto):
        """El costo de la ficha, SOLO si no coincide con la tarifa.

        Enseñarlo siempre sería repetir el número de arriba: el ETL cargó
        costo y tarifa de la misma columna de ADG, así que coinciden al
        centavo en 3,737 de 3,755 tarifas, y con costeo estándar Odoo no lo
        actualiza nunca por su cuenta.

        Cuando NO coinciden casi siempre es un dato malo —una unidad base
        equivocada deja el costo en 4.16 contra una tarifa de 228.57— y eso sí
        hay que verlo antes de firmar la compra. Por eso aparece como aviso y
        no como columna fija.

        La comparación va con `compare_amounts` en vez de un umbral inventado:
        el criterio es "¿son cantidades de dinero distintas?", y a precisión de
        moneda no hay ni un falso positivo por redondeo (medido: 3,737 exactos).

        Se ENSEÑA el costo tal como está registrado en la ficha —129.92 por
        Paquete— y no convertido a la unidad de la tarjeta —1,818.88 por Caja
        de 14—: el comprador tiene que poder reconocer el número que ve en el
        producto. La conversión se añade al lado solo cuando la unidad de la
        tarjeta es otra, para que la comparación contra la tarifa no exija
        multiplicar de cabeza.
        """
        costo_en_ficha = producto.standard_price
        costo_en_tarjeta = costo_en_ficha * unidades_base
        tarifa = datos_producto.get('price')
        if not costo_en_ficha or tarifa is None:
            return {}
        if not self.currency_id.compare_amounts(costo_en_tarjeta, tarifa):
            return {}

        aviso = {
            'surtidoraCosto': format_amount(self.env, costo_en_ficha, self.currency_id),
            'surtidoraCostoUnidad': producto.uom_id.display_name,
        }
        if abs(unidades_base - 1.0) > 1e-9:
            aviso['surtidoraCostoEquivale'] = format_amount(
                self.env, costo_en_tarjeta, self.currency_id)
            aviso['surtidoraCostoEquivaleUnidad'] = nombre_unidad
        return aviso

    def _surtidora_rotacion(self, producto, por_suplidor, movimientos):
        """Qué pasó con la ÚLTIMA compra, en porcentaje.

        Es el dato que se mira con el vendedor del suplidor delante, cuando
        aparece con mercancía que nadie pidió: no basta con saber qué hay en
        almacén, hay que saber si lo anterior se movió o sigue ahí parado.

        Tres lecturas, y la tercera es la que importa:

            se vendió todo    -> la última compra se agotó, y en cuántos días
            se vendió parte   -> qué porcentaje
            no se vendió NADA -> aviso: lo de la vez pasada sigue completo

        Va en PORCENTAJE y no en cantidades a propósito. Una compra vieja
        hecha en paquetes, leída en la unidad de la tarjeta —cajas—, daba
        números como «13.43», que ni son lo que nadie compró ni dicen de qué
        son sin mirar la línea de arriba. La proporción, en cambio, no depende
        de la unidad: por eso aquí se cuenta todo en unidad base y no hace
        falta convertir nada.
        """
        propia = por_suplidor.get(self.partner_id.id)
        if not propia:
            return {}
        orden, linea = propia

        # La compra del día no dice nada todavía: sin días transcurridos no
        # hay rotación que medir.
        comprado = fields.Datetime.context_timestamp(self, orden['date_approve'])
        dias = (fields.Date.context_today(self) - comprado.date()).days
        if dias <= 0:
            return {}

        comprada = linea['product_qty'] * self._surtidora_unidades_base_de(
            linea, producto.uom_id)
        if comprada <= 0:
            return {}
        vendida = sum(q for f, q in movimientos if f >= orden['date_approve'])

        if vendida <= 0:
            texto = _('Sin vender nada de la última compra · %s días') % dias
        elif vendida >= comprada:
            texto = _('Última compra agotada en %s días') % dias
        else:
            porcentaje = 100.0 * vendida / comprada
            if porcentaje < 1:
                # redondear a 0% diría «no se vendió nada», que es otra cosa
                texto = _('Vendido menos del 1%% de la última compra · %(dias)s días',
                          dias=dias)
            else:
                texto = _('Vendido %(pct)s%% de la última compra · %(dias)s días',
                          pct=int(porcentaje), dias=dias)
        return {
            'surtidoraRotacion': texto,
            'surtidoraRotacionParada': vendida <= 0,
        }

    def _surtidora_ventas(self, products):
        """{product_id: {'ultima': {...}, 'movimientos': [(fecha, qty_base)]}}.

        De una sola lectura salen las dos cosas que la tarjeta necesita: quién
        se lo llevó por última vez, y cuánto se ha vendido desde la última
        compra. Separarlas costaría el doble de consultas para leer lo mismo.

        Mira las DOS puertas de salida, porque en Surtidora se vende por las
        dos y quedarse con una sola daría una fecha vieja y una cuenta corta:
        el mostrador (POS) no genera `sale.order`, y el crédito no pasa por el
        POS. Las cantidades se acumulan en UNIDAD BASE; la conversión a la
        unidad de la tarjeta la hace quien las use.

        Va con `sudo()` a propósito. Los permisos de lectura son:

            sale.order.line -> Ventas, Contabilidad, Inventario, Portal
            pos.order.line  -> SOLO «Punto de venta / Usuario»

        Un comprador no tiene el de POS, así que sin `sudo()` esto no sería un
        dato que falta: sería un AccessError que tumba el catálogo entero. La
        contrapartida es que el nombre del cliente queda a la vista de quien
        pueda abrir el catálogo de compras — es una decisión, no un descuido.

        No se muestra el PRECIO de venta a propósito: lleva ITBIS dentro y va
        en otra unidad que el resto de la tarjeta, y mezclar bases es lo que ya
        costó dos correcciones.
        """
        datos = {}

        def anotar(product_id, fecha, cliente, cantidad_base):
            ficha = datos.setdefault(product_id, {'ultima': None, 'movimientos': []})
            ficha['movimientos'].append((fecha, cantidad_base))
            if not ficha['ultima'] or ficha['ultima'][0] < fecha:
                ficha['ultima'] = (fecha, cliente)

        bases = {p.id: p.uom_id for p in products}

        lineas = self.env['sale.order.line'].sudo().search_read(
            [('product_id', 'in', products.ids),
             ('company_id', '=', self.company_id.id),
             ('order_id.state', 'in', ('sale', 'done')),
             ('product_uom_qty', '>', 0)],
            ['product_id', 'order_id', 'product_uom_qty', 'product_uom_id'])
        if lineas:
            ordenes = {
                o['id']: o for o in self.env['sale.order'].sudo().search_read(
                    [('id', 'in', list({l['order_id'][0] for l in lineas}))],
                    ['date_order', 'partner_id'])
            }
            for linea in lineas:
                orden = ordenes.get(linea['order_id'][0])
                if not orden:
                    continue
                producto_id = linea['product_id'][0]
                anotar(producto_id, orden['date_order'],
                       orden['partner_id'][1] if orden['partner_id'] else '',
                       linea['product_uom_qty'] * self._surtidora_unidades_base_de(
                           linea, bases.get(producto_id)))

        if 'pos.order.line' in self.env:
            # en el POS la cantidad YA viene en la unidad base del producto
            lineas = self.env['pos.order.line'].sudo().search_read(
                [('product_id', 'in', products.ids),
                 ('company_id', '=', self.company_id.id),
                 ('order_id.state', 'in', ('paid', 'done', 'invoiced')),
                 ('qty', '>', 0)],
                ['product_id', 'order_id', 'qty'])
            if lineas:
                ordenes = {
                    o['id']: o for o in self.env['pos.order'].sudo().search_read(
                        [('id', 'in', list({l['order_id'][0] for l in lineas}))],
                        ['date_order', 'partner_id'])
                }
                for linea in lineas:
                    orden = ordenes.get(linea['order_id'][0])
                    if not orden:
                        continue
                    # una venta de mostrador sin cliente no es un dato que
                    # falta: es que se vendió al público
                    anotar(linea['product_id'][0], orden['date_order'],
                           orden['partner_id'][1] if orden['partner_id'] else _MOSTRADOR,
                           linea['qty'])

        for ficha in datos.values():
            if ficha['ultima'] and ficha['ultima'][1]:
                fecha, cliente = ficha['ultima']
                ficha['ultima'] = {
                    'surtidoraUltimaVentaFecha': format_date(self.env, fecha),
                    'surtidoraUltimoCliente': cliente,
                }
            else:
                ficha['ultima'] = None
        return datos

    # ------------------------------------------------------------------
    # Lectura por lotes
    # ------------------------------------------------------------------
    def _surtidora_lineas_compradas(self, products):
        """Líneas de compra de estos productos, de CUALQUIER suplidor.

        Sin filtrar por suplidor a propósito: de la misma lectura salen la
        última compra a este y la de los demás. `company_id` está almacenado
        en la línea, así que el filtro no cuesta un join extra.

        Trae TODO el histórico de los productos de la página, no una ventana de
        meses: recortarlo escondería la última compra de un producto que se
        pide una vez al año, que es justo el que hay que mirar antes de
        negociar. El volumen queda acotado por la paginación del catálogo —
        son las tarjetas visibles, no el catálogo entero.
        """
        return self.env['purchase.order.line'].search_read(
            [('product_id', 'in', products.ids),
             ('company_id', '=', self.company_id.id),
             ('order_id.state', 'in', _ESTADOS_COMPRADOS),
             # una cantidad negativa es una devolución al suplidor; devolver
             # no es comprar y su precio no sirve para negociar
             ('product_qty', '>', 0)],
            ['product_id', 'partner_id', 'product_uom_id', 'product_qty',
             'price_subtotal', 'order_id'])

    def _surtidora_ordenes_de(self, lineas):
        """Fecha y moneda de las órdenes del lote.

        Va en consulta aparte a propósito: en la línea, `date_approve` es un
        related SIN almacenar, así que no se puede ordenar por él en SQL ni
        confiar en el orden de los ids (una orden vieja se puede confirmar hoy).
        """
        ids = list({linea['order_id'][0] for linea in lineas})
        return {
            orden['id']: orden
            for orden in self.env['purchase.order'].search_read(
                [('id', 'in', ids)], ['date_approve', 'currency_id'])
        }

    def _surtidora_ultima_por_suplidor(self, lineas, ordenes):
        """{product_id: {partner_id: (orden, linea)}} con la compra más
        reciente de cada par producto+suplidor.

        El desempate por `id` NO es cosmético. Con dos compras del mismo día
        —BOKA15 tiene dos, una a 133.00 la funda y otra que sale a 112.72—
        comparar solo por fecha deja ganar a la que el ORM devuelva primero, y
        la tarjeta enseña un precio u otro según el orden de la consulta.

        Y va a ser el caso normal, no la excepción: el histórico que traiga el
        ETL de ADG casi seguro llegue con la fecha a las 00:00:00, así que
        todas las compras de un mismo día empatarían. A igualdad de fecha gana
        la línea de id mayor, que es la que se creó después.
        """
        ultimas = {}
        for linea in lineas:
            orden = ordenes.get(linea['order_id'][0])
            # date_approve puede venir vacío en órdenes migradas: sin fecha no
            # hay forma de saber cuál fue la última, así que la línea se cae.
            if not orden or not orden['date_approve'] or not linea['partner_id']:
                continue
            del_producto = ultimas.setdefault(linea['product_id'][0], {})
            previa = del_producto.get(linea['partner_id'][0])
            if previa and self._surtidora_orden_de_reciente(*previa) >= \
                    self._surtidora_orden_de_reciente(orden, linea):
                continue
            del_producto[linea['partner_id'][0]] = (orden, linea)
        return ultimas

    @staticmethod
    def _surtidora_orden_de_reciente(orden, linea):
        """Con qué criterio se decide cuál compra es "la última"."""
        return (orden['date_approve'], linea['id'])

    # ------------------------------------------------------------------
    # Conversiones
    # ------------------------------------------------------------------
    def _surtidora_unidad_de_la_tarjeta(self, products, datos_nativos):
        """{product_id: (nombre de la unidad, cuántas unidades base vale)}.

        En qué unidad está expresado el precio que la tarjeta YA enseña. No es
        siempre la misma, y de ahí salía un desfase: Odoo toma el precio de la
        LÍNEA cuando el producto ya está en la orden —y entonces va en la
        unidad de esa línea— y el de la TARIFA cuando todavía no está. Con más
        de una línea del mismo producto vuelve a la tarifa, así que solo la
        línea única manda.

        El nombre se toma de la línea y no de `uomDisplayName` a propósito:
        Odoo solo corrige esa etiqueta si la unidad de la línea difiere de la
        unidad base del producto (`purchase_order_line.py`), así que una línea
        en la unidad base contra una tarifa en cajas se queda con la etiqueta
        del suplidor, que no es la del precio que muestra.
        """
        por_producto = {}
        for linea in self.order_line:
            if linea.product_id:
                por_producto.setdefault(linea.product_id.id, []).append(linea)

        unidades = {}
        for producto in products:
            propias = por_producto.get(producto.id) or []
            if len(propias) == 1:
                uom = propias[0].product_uom_id
                unidades[producto.id] = (
                    uom.display_name,
                    uom._compute_quantity(1.0, producto.uom_id, round=False) or 1.0)
            else:
                datos = datos_nativos.get(producto.id) or {}
                unidades[producto.id] = (
                    datos.get('uomDisplayName') or producto.uom_id.display_name,
                    datos.get('uomFactor') or 1.0)
        return unidades

    def _surtidora_precio_neto(self, orden, linea, base, unidades_base):
        """Lo que se pagó por UNA de las unidades que muestra la tarjeta, SIN ITBIS.

        Dos decisiones, y las dos son para que los números de la tarjeta se
        puedan comparar de un vistazo:

        1. NETO. Justo encima va el precio de la tarifa, que también es neto.
           Mostrar uno con impuesto y otro sin él hace que un precio que no se
           movió parezca una subida del 18%. Se parte de `price_subtotal` —la
           base imponible, ya con el descuento aplicado— y no de `price_unit`,
           así el número no depende de si el impuesto está configurado como
           incluido o excluido.
        2. MISMA UNIDAD que ese precio (ver `_surtidora_unidad_de_la_tarjeta`).
           Poner 135.59 por paquete al lado de 1,084.72 por caja sería invitar
           a un error de negociación.
        """
        precio = linea['price_subtotal'] / linea['product_qty']
        precio = precio / self._surtidora_unidades_base_de(linea, base) * unidades_base

        moneda = self.env['res.currency'].browse(orden['currency_id'][0]) \
            if orden.get('currency_id') else self.currency_id
        if moneda and moneda != self.currency_id:
            precio = moneda._convert(
                precio, self.currency_id, self.company_id, orden['date_approve'].date())
        return precio

    def _surtidora_unidades_base_de(self, linea, base):
        """Cuántas unidades base vale UNA unidad de la línea.

        Lo usan el precio y la rotación: la línea puede venir en cajas y la
        tarjeta hablar en paquetes, o al revés. Nunca devuelve 0 — una
        división por cero aquí saldría en pantalla como un precio absurdo.
        """
        uom = self.env['uom.uom'].browse(
            linea['product_uom_id'][0]) if linea.get('product_uom_id') else base
        if not uom or not base:
            return 1.0
        return uom._compute_quantity(1.0, base, round=False) or 1.0

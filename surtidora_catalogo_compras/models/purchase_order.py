# -*- coding: utf-8 -*-
"""La última compra a ESE suplidor, en la tarjeta del catálogo.

El catálogo pide los datos de las tarjetas visibles en UNA sola llamada a
`_get_product_catalog_order_data`, que recibe el lote completo de productos.
Por eso todo aquí se resuelve en dos consultas por página, no una por tarjeta.
"""
from odoo import models
from odoo.tools.misc import format_amount, format_date

# Estados en los que una orden ya es una compra de verdad. Un borrador no es
# una compra: el precio todavía se está negociando y nadie pagó nada.
_ESTADOS_COMPRADOS = ('purchase', 'done')


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    def _get_product_catalog_order_data(self, products, **kwargs):
        datos = super()._get_product_catalog_order_data(products, **kwargs)
        for product_id, ultima in self._surtidora_ultima_compra(products, datos).items():
            if product_id in datos:
                datos[product_id].update(ultima)
        return datos

    # ------------------------------------------------------------------
    def _surtidora_ultima_compra(self, products, datos_nativos):
        """{product_id: {surtidoraUltimaFecha, surtidoraUltimoPrecio}}.

        `datos_nativos` es lo que ya devolvió Odoo: de ahí sale `uomFactor`,
        para no calcular la unidad por nuestra cuenta y acabar discrepando
        con el precio que la propia tarjeta enseña al lado.
        """
        # En una orden nueva todavía no hay suplidor, y sin suplidor esto no
        # significa nada: la gracia es "cuánto le pagué A ÉL".
        if len(self) != 1 or not self.partner_id or not products:
            return {}

        lineas = self._surtidora_lineas_compradas(products)
        if not lineas:
            return {}
        ordenes = self._surtidora_ordenes_de(lineas)

        ultimas = {}
        for linea in lineas:
            orden = ordenes.get(linea['order_id'][0])
            # date_approve puede venir vacío en órdenes migradas: sin fecha no
            # hay forma de saber cuál fue la última, así que la línea se cae.
            if not orden or not orden['date_approve']:
                continue
            producto_id = linea['product_id'][0]
            previa = ultimas.get(producto_id)
            if previa and previa[0]['date_approve'] >= orden['date_approve']:
                continue
            ultimas[producto_id] = (orden, linea)

        bases = {p.id: p.uom_id for p in products}
        return {
            producto_id: {
                'surtidoraUltimaFecha': format_date(self.env, orden['date_approve']),
                'surtidoraUltimoPrecio': format_amount(
                    self.env,
                    self._surtidora_precio_en_unidad_de_tarjeta(
                        orden, linea, bases.get(producto_id),
                        (datos_nativos.get(producto_id) or {}).get('uomFactor') or 1.0),
                    self.currency_id),
            }
            for producto_id, (orden, linea) in ultimas.items()
        }

    def _surtidora_lineas_compradas(self, products):
        """Líneas de compra a este suplidor. `partner_id` y `company_id` están
        almacenados en la línea, así que el filtro no cuesta un join extra.

        Trae TODO el histórico de los productos de la página, no una ventana de
        meses: recortarlo escondería la última compra de un producto que se
        pide una vez al año, que es justo el que hay que mirar antes de
        negociar. El volumen queda acotado por la paginación del catálogo —
        son las tarjetas visibles, no el catálogo entero.
        """
        return self.env['purchase.order.line'].search_read(
            [('product_id', 'in', products.ids),
             ('partner_id', '=', self.partner_id.id),
             ('company_id', '=', self.company_id.id),
             ('order_id.state', 'in', _ESTADOS_COMPRADOS),
             # una cantidad negativa es una devolución al suplidor; devolver
             # no es comprar y su precio no sirve para negociar
             ('product_qty', '>', 0)],
            ['product_id', 'product_uom_id', 'product_qty', 'price_total', 'order_id'])

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

    def _surtidora_precio_en_unidad_de_tarjeta(self, orden, linea, base, uom_factor):
        """Lo que se pagó por una unidad de las que muestra la tarjeta, CON ITBIS.

        Dos conversiones, y las dos han mordido antes en este proyecto:

        1. IMPUESTO. Se parte de `price_total`, que ya trae impuestos y
           descuentos aplicados. Usar `price_unit` obligaría a saber si el
           impuesto está configurado como incluido — y en esta base lo está por
           herencia de la compañía, no por el propio impuesto, que dice que no.
        2. UNIDAD. La tarjeta enseña el precio por la unidad de la TARIFA
           (una caja), y la compra pudo hacerse en paquetes sueltos. Poner
           135.59 al lado de 1,084.72 sería invitar a un error de negociación.
        """
        precio = linea['price_total'] / linea['product_qty']

        uom_linea = self.env['uom.uom'].browse(
            linea['product_uom_id'][0]) if linea['product_uom_id'] else base
        if uom_linea and base:
            unidades_base = uom_linea._compute_quantity(1.0, base, round=False)
            if unidades_base:
                precio = precio / unidades_base * uom_factor

        moneda = self.env['res.currency'].browse(orden['currency_id'][0]) \
            if orden.get('currency_id') else self.currency_id
        if moneda and moneda != self.currency_id:
            precio = moneda._convert(
                precio, self.currency_id, self.company_id, orden['date_approve'].date())
        return precio

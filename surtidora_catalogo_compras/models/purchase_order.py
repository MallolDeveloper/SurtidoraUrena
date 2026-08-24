# -*- coding: utf-8 -*-
"""La última compra a ESE suplidor, en la tarjeta del catálogo.

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
from odoo import models
from odoo.tools.misc import format_amount, format_date

# Estados en los que una orden ya es una compra de verdad. Un borrador no es
# una compra: el precio todavía se está negociando y nadie pagó nada.
_ESTADOS_COMPRADOS = ('purchase', 'done')


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    def _get_product_catalog_order_line_info(self, product_ids, child_field=False, **kwargs):
        datos = super()._get_product_catalog_order_line_info(
            product_ids, child_field=child_field, **kwargs)
        productos = self.env['product.product'].browse(product_ids).exists()
        for producto_id, ultima in self._surtidora_ultima_compra(productos, datos).items():
            if producto_id in datos:
                datos[producto_id].update(ultima)
        return datos

    # ------------------------------------------------------------------
    def _surtidora_ultima_compra(self, products, datos_nativos):
        """{product_id: {surtidoraUltimaFecha, surtidoraUltimoPrecio, surtidoraUltimaUnidad}}."""
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

        unidades = self._surtidora_unidad_de_la_tarjeta(products, datos_nativos)
        bases = {p.id: p.uom_id for p in products}
        resultado = {}
        for producto_id, (orden, linea) in ultimas.items():
            nombre_unidad, unidades_base = unidades[producto_id]
            resultado[producto_id] = {
                'surtidoraUltimaFecha': format_date(self.env, orden['date_approve']),
                'surtidoraUltimoPrecio': format_amount(
                    self.env,
                    self._surtidora_precio_neto(
                        orden, linea, bases.get(producto_id), unidades_base),
                    self.currency_id),
                'surtidoraUltimaUnidad': nombre_unidad,
            }
        return resultado

    def _surtidora_unidad_de_la_tarjeta(self, products, datos_nativos):
        """{product_id: (nombre de la unidad, cuántas unidades base vale)}.

        En qué unidad está expresado el precio que la tarjeta YA enseña. No es
        siempre la misma, y de ahí salía el desfase: Odoo toma el precio de la
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
            ['product_id', 'product_uom_id', 'product_qty', 'price_subtotal', 'order_id'])

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

    def _surtidora_precio_neto(self, orden, linea, base, unidades_base):
        """Lo que se pagó por UNA de las unidades que muestra la tarjeta, SIN ITBIS.

        Dos decisiones, y las dos son para que los dos números de la tarjeta se
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

        uom_linea = self.env['uom.uom'].browse(
            linea['product_uom_id'][0]) if linea['product_uom_id'] else base
        if uom_linea and base:
            en_base = uom_linea._compute_quantity(1.0, base, round=False)
            if en_base:
                precio = precio / en_base * unidades_base

        moneda = self.env['res.currency'].browse(orden['currency_id'][0]) \
            if orden.get('currency_id') else self.currency_id
        if moneda and moneda != self.currency_id:
            precio = moneda._convert(
                precio, self.currency_id, self.company_id, orden['date_approve'].date())
        return precio

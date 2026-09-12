# -*- coding: utf-8 -*-
"""Rastro de todo cambio de precio de lista, venga de donde venga.

En ADG la pestaña «Hist. Precios» guarda cada cambio de precio con antes,
después, fecha, hora y usuario — y se usa: 5,215 cambios reales en 12 meses,
casi todos de Mariano desde «Liquidación de Precios por Unidad» (medido en
`inv_historico_precios`, 12-sep-2026).

En Odoo, lo que se COBRA es la regla de lista (`product.pricelist.item`), y
ese modelo no lleva chatter ni tracking: un precio cambiado desde la vista
nativa de listas de precios, por importación o por RPC no dejaba huella.
Solo la dejaba el asistente «Precios y margen», que escribe su propia
bitácora. Este archivo cierra el hueco donde de verdad se cierra —en la
regla— para que cualquier vía deje el mismo rastro en el chatter del
producto, que es donde ya está la historia del asistente."""
from markupsafe import Markup, escape

from odoo import _, api, models

# El asistente escribe su bitácora completa (con el TOTAL del empaque y la
# ficha sincronizada), así que se le pide callar al rastro por regla para no
# anotar el mismo cambio dos veces.
CTX_SIN_RASTRO = 'surtidora_sin_rastro_precio'


class ProductPricelistItem(models.Model):
    _inherit = 'product.pricelist.item'

    # ------------------------------------------------------------------
    # Ganchos del ORM
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        reglas = super().create(vals_list)
        if not self.env.context.get(CTX_SIN_RASTRO):
            for regla in reglas:
                regla._surtidora_anotar(
                    _('regla nueva: %s', regla._surtidora_precio_texto()))
        return reglas

    def write(self, vals):
        if self.env.context.get(CTX_SIN_RASTRO) or not self._surtidora_toca_precio(vals):
            return super().write(vals)
        antes = {regla.id: regla._surtidora_precio_texto() for regla in self}
        resultado = super().write(vals)
        for regla in self:
            ahora = regla._surtidora_precio_texto()
            if ahora != antes[regla.id]:
                regla._surtidora_anotar(
                    _('%(antes)s → %(ahora)s', antes=antes[regla.id], ahora=ahora))
        return resultado

    def unlink(self):
        if not self.env.context.get(CTX_SIN_RASTRO):
            for regla in self:
                regla._surtidora_anotar(
                    _('regla eliminada: %s', regla._surtidora_precio_texto()))
        return super().unlink()

    # ------------------------------------------------------------------
    # Piezas
    # ------------------------------------------------------------------
    @api.model
    def _surtidora_toca_precio(self, vals):
        """Solo interesa lo que cambia el precio que se cobra; renombrar la
        lista o mover fechas de vigencia no es un cambio de precio."""
        return bool({'fixed_price', 'percent_price', 'price_discount',
                     'price_surcharge', 'price_markup', 'compute_price',
                     'base', 'min_quantity'} & set(vals))

    def _surtidora_precio_texto(self):
        """El precio de la regla como se lee en el mostrador."""
        self.ensure_one()
        if self.compute_price == 'fixed':
            precio = '%.2f' % self.fixed_price
        elif self.compute_price == 'percentage':
            precio = _('%.2f %% de descuento', self.percent_price)
        else:
            precio = _('fórmula sobre %s', dict(
                self._fields['base']._description_selection(self.env)
            ).get(self.base, self.base))
        if self.min_quantity and self.min_quantity != 1.0:
            precio = _('%(precio)s desde %(cantidad)g', precio=precio,
                       cantidad=self.min_quantity)
        return precio

    def _surtidora_anotar(self, detalle):
        """Una línea en el chatter del producto de la regla. Las reglas
        globales o por categoría no tienen un producto donde anotar; esas
        quedan fuera (son 0 en el catálogo migrado)."""
        self.ensure_one()
        tmpl = self.product_tmpl_id or self.product_id.product_tmpl_id
        if not tmpl:
            return
        titulo = _('Cambio de precio de lista por %s:', self.env.user.name)
        linea = _('%(lista)s: %(detalle)s',
                  lista=self.pricelist_id.display_name, detalle=detalle)
        # sudo: escribir en el chatter del producto exige el grupo
        # «Products / Create», que un Gerente de Ventas no tiene — sin esto
        # cambiar un precio desde la lista revienta con AccessError.
        tmpl.sudo().message_post(
            body=Markup('<br/>').join([escape(titulo), escape(linea)]))

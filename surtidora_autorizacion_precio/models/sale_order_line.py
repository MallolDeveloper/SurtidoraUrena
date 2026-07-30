# -*- coding: utf-8 -*-
from odoo import fields, models


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    autorizacion_id = fields.Many2one(
        'surtidora.autorizacion.precio', string='Autorización de precio',
        copy=False, readonly=True)

    # ------------------------------------------------------------------
    # Reglas de precio (núcleo reutilizable por cualquier pantalla de venta)
    # ------------------------------------------------------------------
    def _precio_de_lista(self):
        """Precio que la lista del pedido asigna a esta línea (misma mecánica
        validada en la mini-data: regla base + regla por cantidad/empaque)."""
        self.ensure_one()
        order = self.order_id
        if not order.pricelist_id or not self.product_id:
            return self.price_unit
        return order.pricelist_id._get_product_price(
            self.product_id, self.product_uom_qty or 1.0,
            currency=order.currency_id, uom=self.product_uom_id,
            date=order.date_order,
        )

    def _costo_en_uom(self):
        """Costo del producto expresado en la unidad de la línea (para comparar
        contra el precio de venta — RB-08)."""
        self.ensure_one()
        factor = self.product_uom_id._compute_quantity(
            1.0, self.product_id.uom_id, round=False)
        return self.product_id.standard_price * factor

    def _es_bajo_costo(self):
        """RB-08: ¿el precio de la línea está por debajo del costo?"""
        self.ensure_one()
        if not self.product_id or self.display_type:
            return False
        return self.currency_id.compare_amounts(
            self.price_unit, self._costo_en_uom()) < 0

    def _requiere_autorizacion(self):
        """RB-01: ¿el precio está por debajo de la lista (menos la tolerancia)
        y sin una autorización vigente que lo cubra?"""
        self.ensure_one()
        if not self.product_id or self.display_type:
            return False
        tolerancia = self.company_id.surtidora_tolerancia_precio_pct or 0.0
        piso = self._precio_de_lista() * (1 - tolerancia / 100.0)
        if self.currency_id.compare_amounts(self.price_unit, piso) >= 0:
            return False
        if self.autorizacion_id and self.autorizacion_id.sigue_vigente_para(self):
            return False
        return True

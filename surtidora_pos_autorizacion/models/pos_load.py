# -*- coding: utf-8 -*-
"""El POS necesita el costo del producto para marcar EN ROJO al instante la
línea bajo costo (sin ir al servidor por cada tecla). *args para ser inmunes
a cambios de firma entre builds de Odoo 19 (mismo patrón de pos_empaques)."""
from odoo import api, models


class ProductProduct(models.Model):
    _inherit = 'product.product'

    @api.model
    def _load_pos_data_fields(self, *args, **kwargs):
        fields = super()._load_pos_data_fields(*args, **kwargs)
        return list(set(fields) | {'standard_price'})

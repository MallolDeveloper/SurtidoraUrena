# -*- coding: utf-8 -*-
"""Campos extra que el POS necesita para la venta por empaque.

El POS estándar ya carga product.uom (barcode por empaque) y uom.uom, pero sin
el factor de conversión ni la lista de empaques del producto. Se usan *args para
ser inmunes a cambios de firma entre builds de Odoo 19."""
from odoo import api, models


class UomUom(models.Model):
    _inherit = 'uom.uom'

    @api.model
    def _load_pos_data_fields(self, *args, **kwargs):
        fields = super()._load_pos_data_fields(*args, **kwargs)
        return list(set(fields) | {'relative_factor', 'relative_uom_id'})


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    @api.model
    def _load_pos_data_fields(self, *args, **kwargs):
        fields = super()._load_pos_data_fields(*args, **kwargs)
        return list(set(fields) | {'uom_ids'})

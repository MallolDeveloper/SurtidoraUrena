# -*- coding: utf-8 -*-
"""Campos extra que el POS necesita para la venta por empaque.

El POS estándar ya carga product.uom (barcode por empaque) y uom.uom, pero sin
el factor de conversión ni la lista de empaques del producto. Se usan *args para
ser inmunes a cambios de firma entre builds de Odoo 19."""
from odoo import api, fields, models


class UomUom(models.Model):
    _inherit = 'uom.uom'

    @api.model
    def _load_pos_data_fields(self, *args, **kwargs):
        fields = super()._load_pos_data_fields(*args, **kwargs)
        return list(set(fields) | {'relative_factor', 'relative_uom_id'})


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    surtidora_caja_fraccionable = fields.Boolean(
        string='La caja se fracciona (¼/½/¾)',
        help='RB-09: en el POS la CAJA de este producto puede venderse en fracciones '
             '(¼, ½, ¾) a precio de caja. Solo se ofrecen fracciones que den unidades '
             'base enteras (caja de 24 → 6/12/18). La unidad base NUNCA se fracciona.')

    @api.model
    def _load_pos_data_fields(self, *args, **kwargs):
        fields = super()._load_pos_data_fields(*args, **kwargs)
        return list(set(fields) | {'uom_ids', 'surtidora_caja_fraccionable'})

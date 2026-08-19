# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    surtidora_margen_unidad_pct = fields.Float(
        related='company_id.surtidora_margen_unidad_pct', readonly=False,
        string='Margen sugerido en la unidad (%)')
    surtidora_descuento_empaque_pct = fields.Float(
        related='company_id.surtidora_descuento_empaque_pct', readonly=False,
        string='Descuento por empaque (%)')
    surtidora_lista_precio_ficha = fields.Many2one(
        related='company_id.surtidora_lista_precio_ficha', readonly=False,
        string='Lista que fija el Precio de venta')

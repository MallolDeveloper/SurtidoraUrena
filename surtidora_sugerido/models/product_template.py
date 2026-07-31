# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    surtidora_uom_compra_id = fields.Many2one(
        'uom.uom', string='Unidad de compra (sugerido)',
        help='REQ-C03: la "definida de compra" de ADG — el sugerido analiza y '
             'ordena en esta unidad (caja/fardo). Vacía = unidad base.')

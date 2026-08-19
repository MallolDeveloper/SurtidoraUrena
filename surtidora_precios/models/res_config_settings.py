# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    surtidora_lista_precio_ficha = fields.Many2one(
        related='company_id.surtidora_lista_precio_ficha', readonly=False,
        string='Lista que fija el Precio de venta')

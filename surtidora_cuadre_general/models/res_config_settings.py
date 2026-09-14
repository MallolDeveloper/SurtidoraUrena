# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    surtidora_registrar_deposito = fields.Boolean(
        related='company_id.surtidora_registrar_deposito', readonly=False)
    surtidora_diario_deposito_id = fields.Many2one(
        related='company_id.surtidora_diario_deposito_id', readonly=False)
    surtidora_fondo_caja = fields.Monetary(
        related='company_id.surtidora_fondo_caja', readonly=False)

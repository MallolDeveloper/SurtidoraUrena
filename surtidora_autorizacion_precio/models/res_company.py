# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    surtidora_tolerancia_precio_pct = fields.Float(
        string='Tolerancia de precio (%)', default=0.0,
        help='Margen de rebaja permitido sin autorización, como % del precio de '
             'lista. 0 = cualquier rebaja exige autorización (RB-01).')
    surtidora_permitir_bajo_costo = fields.Boolean(
        string='Permitir vender bajo costo', default=False,
        help='APAGADO por regla de negocio: la venta bajo costo está bloqueada '
             'para todos los usuarios sin excepción (RB-08). Solo un '
             'administrador puede cambiar este parámetro.')

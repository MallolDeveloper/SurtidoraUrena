# -*- coding: utf-8 -*-
from odoo import fields, models


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    surtidora_es_temporal = fields.Boolean(
        string='OC temporal', copy=False,
        help='REQ-C07: orden "guardada temporal" desde el sugerido (en '
             'negociación con el vendedor) — aún no es compromiso firme.')

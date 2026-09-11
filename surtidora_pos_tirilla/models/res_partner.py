# -*- coding: utf-8 -*-
from odoo import api, models


class ResPartner(models.Model):
    """El código del cliente llega al POS.

    La tirilla de ADG identifica al cliente por su código antes que por el
    nombre («Cliente: 009891 CHARINA BATISTA PARRA»), y es el código el que
    el cliente conoce y el que aparece en su estado de cuenta. El POS carga
    una lista explícita de campos de res.partner, y `ref` no está en ella."""
    _inherit = 'res.partner'

    @api.model
    def _load_pos_data_fields(self, *args, **kwargs):
        campos = super()._load_pos_data_fields(*args, **kwargs)
        return list(set(campos) | {'ref'})

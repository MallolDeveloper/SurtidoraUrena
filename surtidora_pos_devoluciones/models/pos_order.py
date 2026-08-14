# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PosOrder(models.Model):
    _inherit = 'pos.order'

    surtidora_motivo_dev_id = fields.Many2one(
        'surtidora.motivo.devolucion', string='Motivo de devolución',
        copy=False, index='btree_not_null', ondelete='restrict',
        help='REQ-V18: motivo con el que se registró la devolución '
             '(obligatorio, como en ADG). Lo asigna la cajera desde el POS. '
             'ondelete=restrict: un motivo ya usado se ARCHIVA, no se borra '
             '(borrarlo dejaría las devoluciones históricas sin motivo).')

    @api.model
    def _load_pos_data_fields(self, *args, **kwargs):
        """pos.order hoy carga TODOS sus campos (lista vacía = todos); si el
        core algún día la acota, el motivo debe seguir viajando al POS."""
        campos = super()._load_pos_data_fields(*args, **kwargs)
        if campos:
            campos = list(set(campos) | {'surtidora_motivo_dev_id'})
        return campos

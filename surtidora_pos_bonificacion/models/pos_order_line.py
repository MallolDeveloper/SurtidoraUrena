# -*- coding: utf-8 -*-
"""Qué línea es una bonificación y qué premio la generó (REQ-V09/V10).

Las unidades gratis entran como una línea normal del producto (así las
descuenta el inventario y así las ve el premio del núcleo, que las pone a
cero con su línea de descuento). Este campo es la marca que las distingue
de las pagadas: el POS la usa para no mezclarlas con las pagadas y para
retirarlas si la venta ya no alcanza la cantidad; el backend, para saber
qué se regaló y por cuál programa."""
from odoo import api, fields, models


class PosOrderLine(models.Model):
    _inherit = 'pos.order.line'

    surtidora_premio_id = fields.Many2one(
        'loyalty.reward', string='Bonificación (premio)', index=True,
        ondelete='set null',
        help='Premio «Compra X Obtén Y» que metió estas unidades gratis en la '
             'venta. Vacío en las unidades que el cliente pagó.')

    @api.model
    def _load_pos_data_fields(self, *args, **kwargs):
        campos = super()._load_pos_data_fields(*args, **kwargs)
        # lista vacía = el POS carga todos los campos; solo se agrega si el
        # core acota la lista en algún build (mismo criterio que
        # surtidora_pos_empaques.surtidora_uom_venta_id)
        if campos:
            campos = list(set(campos) | {'surtidora_premio_id'})
        return campos

# -*- coding: utf-8 -*-
"""La unidad EN QUE SE VENDIÓ la línea (REQ-V16).

La línea siempre guarda la cantidad en unidad base (18 paquetes), porque es
lo que descuenta el inventario y lo que espera la tarifa. Pero el cliente
compró "1 caja", y así lo dice el recibo de ADG. Este campo recuerda esa
elección para poder presentarla; NO cambia ni la cantidad ni el precio."""
from odoo import api, fields, models


class PosOrderLine(models.Model):
    _inherit = 'pos.order.line'

    surtidora_uom_venta_id = fields.Many2one(
        'uom.uom', string='Unidad de venta (empaque)', ondelete='restrict',
        help='Empaque que eligió la cajera. La cantidad de la línea sigue '
             'en unidad base; esto solo sirve para presentarla como "1 Caja".')

    @api.model
    def _load_pos_data_fields(self, *args, **kwargs):
        campos = super()._load_pos_data_fields(*args, **kwargs)
        # lista vacía = el POS carga todos los campos; solo se agrega si el
        # core acota la lista en algún build
        if campos:
            campos = list(set(campos) | {'surtidora_uom_venta_id'})
        return campos

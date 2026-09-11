# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PosConfig(models.Model):
    """El almacén que despacha, para la tirilla.

    La factura de ADG lo imprime («Almacén: 1 - PRINCIPAL») y el despachador
    lo usa para saber de dónde sacar la mercancía. El POS no carga
    stock.warehouse, así que el nombre viaja resuelto desde el servidor como
    related del tipo de operación de la caja."""
    _inherit = 'pos.config'

    surtidora_almacen = fields.Char(
        related='picking_type_id.warehouse_id.name', string='Almacén (tirilla)')

    @api.model
    def _load_pos_data_fields(self, *args, **kwargs):
        """pos.config hoy carga TODOS sus campos (lista vacía = todos); si el
        core algún día la acota, el almacén debe seguir viajando al POS."""
        campos = super()._load_pos_data_fields(*args, **kwargs)
        if campos:
            campos = list(set(campos) | {'surtidora_almacen'})
        return campos

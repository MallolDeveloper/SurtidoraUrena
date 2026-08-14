# -*- coding: utf-8 -*-
from odoo import fields, models


class PosOrder(models.Model):
    """Los datos del pie de la tirilla viajan DENTRO de la orden.

    Al reimprimir desde el POS, el cliente web pisa session_id/config_id de
    las órdenes recargadas con la sesión ACTUAL del terminal (y res.users de
    otros cajeros ni se carga) — el pie mentiría en toda reimpresión. Estos
    related se resuelven en el SERVIDOR y llegan con el registro de la
    orden, así que la tirilla reimpresa dice la caja, el cajero y el cuadre
    VERDADEROS de aquella venta (revisión adversaria 14-ago)."""
    _inherit = 'pos.order'

    surtidora_caja = fields.Char(
        related='session_id.config_id.name', string='Caja (tirilla)')
    surtidora_cajero = fields.Char(
        related='user_id.name', string='Cajero (tirilla)')
    surtidora_cuadre = fields.Char(
        related='session_id.name', string='Cuadre (tirilla)')

# -*- coding: utf-8 -*-
from odoo import api, fields, models


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

    # Regla del cliente (11-sep-2026, en Surtidora): «si la orden la crea el
    # vendedor se atribuye a él; si no, al cajero». El vendedor de ruta hace
    # PEDIDOS (RB-11: nunca factura); la cajera los carga en el POS y cobra.
    # Por eso el vendedor es el comercial del pedido de origen (pos_sale deja
    # ese rastro en cada línea), y sin pedido detrás, la venta es de quien
    # la digitó en el mostrador. Calculado aquí y no en el navegador para que
    # la reimpresión de otra sesión diga el vendedor VERDADERO de aquella
    # venta, igual que caja, cajero y cuadre.
    surtidora_vendedor = fields.Char(
        compute='_compute_surtidora_vendedor', string='Vendedor (tirilla)')

    @api.depends('lines.sale_order_origin_id.user_id', 'user_id')
    def _compute_surtidora_vendedor(self):
        for orden in self:
            pedido = orden.lines.mapped('sale_order_origin_id')[:1]
            quien = pedido.user_id if pedido and pedido.user_id else orden.user_id
            orden.surtidora_vendedor = quien.name or ''

# -*- coding: utf-8 -*-
"""No sale del almacén lo que la caja confirmó sin autorización (P19).

pos_sale confirma la cotización ENTERA al cobrarla en caja, aunque la caja
cobre solo una parte. Lo que no pasó por la caja queda con su entrega viva
(WH/OUT), y si iba por debajo de la lista o del costo sin autorización, esa
entrega no se valida hasta que se autorice o se corrija (ver sale_order.py).

Se frena en button_validate, que es el botón del almacén (y el de la app de
código de barras): la caja no lo usa, arma y cierra su propia entrega por
otro camino, así que un cobro en caja nunca cae aquí.
"""
from odoo import _, models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def button_validate(self):
        # Solo salidas al cliente con algo por entregar: una devolución que
        # entra no es vender, y un movimiento en cero no entrega nada.
        movimientos = self.move_ids.filtered(
            lambda mov: mov.picking_code == 'outgoing'
            and mov.state not in ('done', 'cancel')
            and not mov.product_uom.is_zero(mov.product_uom_qty))
        # sudo: el almacenista no necesita permisos de ventas para que se
        # revise la línea de venta de lo que va a entregar
        movimientos.sudo().sale_line_id.filtered(
            'surtidora_confirmada_sin_autorizar',
        )._surtidora_frenar_retenidas(_('entregar'))
        return super().button_validate()

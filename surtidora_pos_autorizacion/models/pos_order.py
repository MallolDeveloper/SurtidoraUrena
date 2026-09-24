# -*- coding: utf-8 -*-
"""Atar la autorización a la venta que de verdad se cobró.

La fila de auditoría se escribe cuando el supervisor teclea su PIN, que es
ANTES de cobrar: en ese momento la venta todavía no existe en el servidor.
Si después se cancela o se abandona, la bitácora se queda con una excepción
de una venta que nunca ocurrió, y nadie que la lea puede distinguirla de
una real. En la base había dos así: el pedido 261-1-000009, cancelado, y
un TEST-RPC que ni existe.

Cuando la venta baja del mostrador se enlaza por su referencia, y a partir
de ahí `estado_venta` dice sola si aquello se cobró o no.
"""
from odoo import api, models


class PosOrder(models.Model):
    _inherit = 'pos.order'

    @api.model_create_multi
    def create(self, lista_valores):
        ordenes = super().create(lista_valores)
        ordenes._surtidora_enlazar_autorizaciones()
        return ordenes

    def action_pos_order_paid(self):
        """También al cobrarla: si la venta subió en borrador antes de que el
        supervisor pusiera el PIN, el enlace de create no alcanzó sus filas.
        Va antes de marcarla pagada porque pos_sale puede confirmar la
        cotización dentro de ese mismo paso (pago en línea).

        Después de cobrada ya no se enlaza nada (point_of_sale ignora la
        venta que vuelve a subir ya pagada): una fila escrita más tarde con
        la referencia de esta venta no la cubre. La cotización cobrada en
        caja se ampara solo por este enlace (P19)."""
        self._surtidora_enlazar_autorizaciones()
        return super().action_pos_order_paid()

    def _surtidora_enlazar_autorizaciones(self):
        Auditoria = self.env['surtidora.autorizacion.precio'].sudo()
        for orden in self:
            referencias = [r for r in (orden.pos_reference, orden.name) if r]
            if not referencias:
                continue
            filas = Auditoria.search([
                ('origen', '=', 'pos'),
                ('pos_order_id', '=', False),
                ('order_ref', 'in', referencias),
            ])
            if filas:
                filas.pos_order_id = orden.id

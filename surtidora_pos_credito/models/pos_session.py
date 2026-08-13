# -*- coding: utf-8 -*-
"""Conciliación automática de los bonos al cerrar la sesión.

Sin esto, el apunte deudor que genera cada pago con bono queda suelto y la
nota de crédito sigue "abierta": el mismo bono podría gastarse otra vez al
día siguiente (hallazgo de la revisión adversaria del 13-ago). La política
12.4 del levantamiento lo dice explícito: "el bono se aplica como crédito
pendiente (conciliación NC ↔ factura)"."""
from odoo import models


class PosSession(models.Model):
    _inherit = 'pos.session'

    def _validate_session(self, *args, **kwargs):
        res = super()._validate_session(*args, **kwargs)
        self._surtidora_conciliar_bonos()
        return res

    def _surtidora_conciliar_bonos(self):
        """Cada pago con bono de esta sesión generó (por split) un apunte
        DEUDOR en la CxC del cliente. Se concilia FIFO contra sus créditos
        abiertos (NC / pagos a cuenta, los más viejos primero)."""
        for sesion in self:
            move = sesion.sudo().move_id
            if not move:
                continue
            pagos = sesion.sudo().order_ids.mapped('payment_ids').filtered(
                lambda p: p.payment_method_id.surtidora_es_bono and p.amount > 0)
            for pago in pagos:
                comercial = pago.pos_order_id.partner_id.commercial_partner_id
                debito = move.line_ids.filtered(
                    lambda l: l.partner_id == comercial
                    and l.account_id.account_type == 'asset_receivable'
                    and not l.reconciled
                    and l.amount_residual > 0
                    and abs(l.balance - pago.amount) < 0.01)[:1]
                if not debito:
                    continue  # el apunte no es identificable: lo concilia CxC
                creditos = self.env['account.move.line'].sudo().search([
                    ('partner_id', '=', comercial.id),
                    ('account_id', '=', debito.account_id.id),
                    ('parent_state', '=', 'posted'),
                    ('amount_residual', '<', 0.0),
                ], order='date, id')
                if creditos:
                    (debito + creditos).reconcile()

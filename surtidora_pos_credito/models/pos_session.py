# -*- coding: utf-8 -*-
"""Conciliación automática de los bonos al cerrar la sesión.

Sin esto, el apunte deudor que genera cada pago con bono queda suelto y la
nota de crédito sigue "abierta": el mismo bono podría gastarse otra vez al
día siguiente (hallazgo de la revisión adversaria del 13-ago). La política
12.4 del levantamiento lo dice explícito: "el bono se aplica como crédito
pendiente (conciliación NC ↔ factura)".

Dos caminos, según dónde deja Odoo la deuda del bono:
- Orden SIN factura: el cierre crea (por split) un apunte deudor del
  cliente en el asiento de la sesión → se concilia contra sus créditos.
- Orden FACTURADA: el cierre no crea ese apunte; la parte pagada con bono
  queda abierta en la factura → se concilia la factura contra sus créditos.
"""
from odoo import Command, _, fields, models
from odoo.tools import float_compare


class PosSession(models.Model):
    _inherit = 'pos.session'

    def _validate_session(self, *args, **kwargs):
        res = super()._validate_session(*args, **kwargs)
        self._surtidora_conciliar_bonos()
        return res

    def _surtidora_conciliar_bonos(self):
        """REQ-V18: aplica los bonos de la sesión recién cerrada.

        Solo si la sesión quedó cerrada: si el asiento de cierre no cuadra,
        Odoo revierte la transacción y devuelve el asistente — la sesión
        sigue abierta y conciliar ahí gastaría el bono dos veces (el candado
        lo sigue contando como usado)."""
        for sesion in self.sudo():
            if sesion.state != 'closed':
                continue
            sesion._surtidora_conciliar_bonos_sesion()
            sesion._surtidora_conciliar_bonos_facturas()

    def _surtidora_pagos_bono(self):
        return self.order_ids.payment_ids.filtered(
            lambda p: p.payment_method_id.surtidora_es_bono)

    def _surtidora_conciliar_bonos_sesion(self):
        """Órdenes SIN factura: cada pago con bono generó (por split) un
        apunte DEUDOR en la CxC del cliente dentro del asiento de la sesión.
        Se concilia FIFO contra sus créditos abiertos (NC / pagos a cuenta,
        los más viejos primero).

        Las órdenes facturadas no tienen ese apunte: buscarlo por cliente y
        monto podía agarrar la venta a Crédito (no facturada) del mismo
        cliente por el mismo monto y saldarla con su NC."""
        move = self.move_id
        if not move:
            return
        pagos = self._surtidora_pagos_bono().filtered(
            lambda p: p.amount > 0 and not p.pos_order_id.account_move)
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

    def _surtidora_conciliar_bonos_facturas(self):
        """Órdenes FACTURADAS pagadas con bono: la factura quedó abierta por
        la parte del bono y la NC del cliente también. Se aplica el bono
        contra sus créditos abiertos (los más viejos primero), sin pasar del
        tope de _bono_por_conciliar ni de lo que el cliente tiene a favor.

        - El bono cubre todo lo abierto de la factura (bono + efectivo o
          tarjeta): se concilia la factura con los créditos, igual que el
          botón estándar «Agregar» de los créditos pendientes.
        - El bono cubre solo una parte (bono + Crédito): reconcile() no
          admite tope, así que un asiento puente mueve exactamente el bono
          y el resto de la factura sigue siendo deuda.
        - Devoluciones facturadas: su RINV ya es el bono; no hay nada que
          aplicar (_bono_por_conciliar solo devuelve ventas)."""
        credito = self.env['surtidora.pos.credito'].sudo()
        rounding = self.company_id.currency_id.rounding
        for pendiente in credito._bono_por_conciliar(self._surtidora_pagos_bono()):
            creditos = self._surtidora_creditos_abiertos(pendiente['factura'],
                                                        pendiente['lineas'])
            monto = self.company_id.currency_id.round(
                min(pendiente['tope'], -sum(creditos.mapped('amount_residual'))))
            if float_compare(monto, 0.0, precision_rounding=rounding) <= 0:
                continue  # sin saldo a favor: esa parte queda como deuda
            abierto = sum(pendiente['lineas'].mapped('amount_residual'))
            if float_compare(monto, abierto, precision_rounding=rounding) == 0:
                (pendiente['lineas'] + creditos).with_company(
                    pendiente['factura'].company_id).reconcile()
            else:
                self._surtidora_puente_bono(pendiente, monto, creditos)

    def _surtidora_creditos_abiertos(self, factura, lineas):
        """Saldo a favor del cliente que el bono puede consumir: NC / pagos a
        cuenta sin conciliar de la MISMA entidad comercial, cuenta por
        cobrar y compañía que la factura. Mismo criterio que
        verificar_bono (partner = entidad comercial); nunca otro cliente."""
        return self.env['account.move.line'].sudo().search([
            ('partner_id', '=', factura.commercial_partner_id.id),
            ('account_id', '=', lineas[:1].account_id.id),
            ('company_id', '=', factura.company_id.id),
            ('parent_state', '=', 'posted'),
            ('reconciled', '=', False),
            ('amount_residual', '<', 0.0),
        ], order='date_maturity, date, id')

    def _surtidora_puente_bono(self, pendiente, monto, creditos):
        """Aplica `monto` de bono a la factura cuando el bono no la cubre
        entera: un asiento en el diario del POS (el mismo que usa Odoo para
        los «Invoice payment») con dos líneas en la CxC del cliente por
        `monto` — el haber salda la factura y el debe consume sus créditos.

        El puente queda en pos.payment.account_move_id (campo nativo): se ve
        desde los asientos de la sesión, la factura muestra «Bono / Nota de
        Crédito» como forma de pago y marca el bono como ya aplicado."""
        factura, lineas = pendiente['factura'], pendiente['lineas']
        base = {
            'account_id': lineas[:1].account_id.id,
            'partner_id': factura.commercial_partner_id.id,
            'name': _('Bono aplicado a %(factura)s', factura=factura.name),
        }
        puente = self.env['account.move'].sudo().with_company(factura.company_id).create({
            'move_type': 'entry',
            'journal_id': self.config_id.journal_id.id,
            'date': fields.Date.context_today(self),
            'ref': _('Bono / Nota de Crédito de %(orden)s (%(factura)s)',
                     orden=pendiente['orden'].name, factura=factura.name),
            'line_ids': [Command.create({**base, 'balance': -monto}),
                         Command.create({**base, 'balance': monto})],
        })
        puente._post()
        haber = puente.line_ids.filtered(lambda l: l.balance < 0)
        (haber + lineas).with_company(factura.company_id).reconcile()
        ((puente.line_ids - haber) + creditos).with_company(factura.company_id).reconcile()
        pendiente['pagos'].write({'account_move_id': puente.id})

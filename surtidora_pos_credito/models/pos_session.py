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

Y ANTES de los bonos, la devolución de un fiado (DC-5): el Crédito negativo
rebaja la deuda del cliente en vez de quedar como saldo a favor que se
gasta como bono (_surtidora_aplicar_devoluciones).
"""
from odoo import Command, _, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare


class PosSession(models.Model):
    _inherit = 'pos.session'

    def _validate_session(self, *args, **kwargs):
        res = super()._validate_session(*args, **kwargs)
        self._surtidora_conciliar_bonos()
        return res

    def _surtidora_conciliar_bonos(self):
        """REQ-V18: aplica los bonos de la sesión recién cerrada, y DC-5:
        las devoluciones a la cuenta del cliente.

        Solo si la sesión quedó cerrada: si el asiento de cierre no cuadra,
        Odoo revierte la transacción y devuelve el asistente — la sesión
        sigue abierta y conciliar ahí gastaría el bono dos veces (el candado
        lo sigue contando como usado).

        Las devoluciones van PRIMERO: si el bono corriera antes, podía
        consumir el crédito de la devolución de un fiado (FIFO) y dejar
        abierto un bono legítimo que se gastaría otra vez. Van otra vez al
        final por la parte a Crédito de una factura pagada con bono +
        Crédito, que solo queda libre cuando el bono ya se aplicó."""
        for sesion in self.sudo():
            if sesion.state != 'closed':
                continue
            sesion._surtidora_aplicar_devoluciones()
            sesion._surtidora_conciliar_bonos_sesion()
            sesion._surtidora_conciliar_bonos_facturas()
            sesion._surtidora_aplicar_devoluciones()

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

    # ------------------------------------------------------------------
    # DC-5: la devolución de un fiado rebaja la deuda
    # ------------------------------------------------------------------
    def _surtidora_aplicar_devoluciones(self):
        """Concilia el crédito de cada devolución a cuenta (Crédito
        negativo) contra las deudas abiertas del MISMO cliente: primero la
        de la venta devuelta, después las demás, las que vencen primero.

        Sirve con y sin factura: el crédito es la RINV o el apunte del
        cliente en el asiento de este cierre (_apuntes_por_pago). Aplica
        las devoluciones de esta caja y las de otras cajas ya cerradas cuya
        venta fiada es de esta sesión (su deuda recién entra a
        contabilidad). Si la venta devuelta sigue en OTRA caja abierta, se
        deja para el cierre de esa caja, que la aplica primero contra ella.
        Si el cliente no debe nada, el crédito queda como saldo a favor
        legítimo.

        Idempotente: solo trabaja lo que sigue abierto
        (_devoluciones_por_aplicar), así que un segundo cierre o un
        reintento no concilia dos veces. Si una conciliación falla, el
        cierre NO se cae: queda la nota en la sesión para CxC."""
        credito = self.env['surtidora.pos.credito'].sudo().with_company(self.company_id)
        pagos = self._surtidora_pagos_devolucion()
        if not pagos:
            return
        reservadas = self._surtidora_deudas_reservadas(pagos)
        for pendiente in credito._devoluciones_por_aplicar(pagos):
            primero, en_otra_caja = credito._deuda_de_venta(
                pendiente['orden'].refunded_order_id)
            if en_otra_caja:
                continue
            try:
                with self.env.cr.savepoint():
                    self._surtidora_aplicar_devolucion(
                        pendiente,
                        self._surtidora_deudas_a_rebajar(pendiente, primero) - reservadas)
            except UserError as error:
                self.message_post(body=_(
                    'La devolución %(orden)s no se pudo aplicar a la deuda del '
                    'cliente: %(error)s. Conciliarla a mano en CxC.',
                    orden=pendiente['orden'].name, error=error))

    def _surtidora_pagos_devolucion(self):
        """Pagos de devolución a cuenta que toca este cierre: los de sus
        órdenes y los de las devoluciones de sus ventas fiadas."""
        credito = self.env['surtidora.pos.credito']
        pagos = self.order_ids.payment_ids
        ventas = pagos.filtered(lambda p: credito._es_fiado(p) and p.amount > 0).pos_order_id
        return (pagos.filtered(credito._es_devolucion_a_cuenta)
                | credito._devoluciones_de_ventas(ventas))

    def _surtidora_deudas_reservadas(self, pagos):
        """Deudas que un bono va a pagar: las facturas con bono de esta
        caja o de otra abierta (_deudas_reservadas_bono) y los apuntes de
        los bonos sin factura de este cierre, que concilia
        _surtidora_conciliar_bonos_sesion. Si la devolución las pagara, el
        bono no encontraría qué pagar y quedaría para gastarse otra vez."""
        credito = self.env['surtidora.pos.credito'].sudo().with_company(self.company_id)
        bonos = self._surtidora_pagos_bono()
        for comercial in pagos.partner_id.commercial_partner_id:
            bonos |= credito._pagos_bono_facturados(comercial)
        sin_factura = bonos.filtered(lambda p: p.session_id == self and p.amount > 0
                                     and not p.pos_order_id.account_move)
        return credito._deudas_reservadas_bono(bonos).union(
            *credito._apuntes_por_pago(sin_factura).values())

    def _surtidora_deudas_a_rebajar(self, pendiente, primero):
        """Deudas del cliente del crédito, en su misma CxC y compañía:
        `primero` (la de la venta devuelta) y después FIFO (vencimiento)."""
        credito = self.env['surtidora.pos.credito'].sudo()
        apunte = pendiente['creditos'][:1]
        fifo = self.env['account.move.line'].sudo().search(
            credito._dominio_deudas(apunte.partner_id, apunte.company_id)
            + [('account_id', '=', apunte.account_id.id)],
            order='date_maturity, date, id')
        return (primero & fifo) | fifo

    def _surtidora_aplicar_devolucion(self, pendiente, deudas):
        """Concilia el crédito con las deudas, una por una y en orden
        (reconcile() de un lote las reordena por fecha).

        RINV mixta (Crédito + Bono): reconcile() no admite tope y se
        comería el bono, así que un asiento puente aplica exactamente la
        parte de la cuenta que encuentra deuda (_surtidora_puente_devolucion)
        y la marca como aplicada."""
        if not deudas:
            return
        moneda = self.company_id.currency_id
        creditos, tope = pendiente['creditos'], pendiente['tope']
        if moneda.compare_amounts(-sum(creditos.mapped('amount_residual')), tope) > 0:
            creditos = self._surtidora_puente_devolucion(
                pendiente, moneda.round(min(tope, sum(deudas.mapped('amount_residual')))))
        for deuda in deudas:
            abiertos = creditos.filtered(lambda l: not l.reconciled)
            if not abiertos:
                break
            (abiertos + deuda).with_company(self.company_id).reconcile()

    def _surtidora_puente_devolucion(self, pendiente, monto):
        """Asiento puente en el diario del POS (como el del bono): el debe
        consume `monto` de la RINV y el haber, que devuelve, rebaja la
        deuda. Queda en pos.payment.account_move_id: la devolución ya se
        aplicó y el resto de la RINV sigue siendo el bono del cliente."""
        creditos = pendiente['creditos']
        documento = creditos[:1].move_id
        base = {
            'account_id': creditos[:1].account_id.id,
            'partner_id': creditos[:1].partner_id.id,
            'name': _('Devolución a cuenta de %(orden)s', orden=pendiente['orden'].name),
        }
        puente = self.env['account.move'].sudo().with_company(self.company_id).create({
            'move_type': 'entry',
            'journal_id': self.config_id.journal_id.id,
            'date': fields.Date.context_today(self),
            'ref': _('Devolución a cuenta de %(orden)s (%(documento)s)',
                     orden=pendiente['orden'].name, documento=documento.name),
            'line_ids': [Command.create({**base, 'balance': monto}),
                         Command.create({**base, 'balance': -monto})],
        })
        puente._post()
        debe = puente.line_ids.filtered(lambda l: l.balance > 0)
        (debe + creditos).with_company(self.company_id).reconcile()
        pendiente['pagos'].write({'account_move_id': puente.id})
        return puente.line_ids - debe

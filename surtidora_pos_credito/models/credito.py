# -*- coding: utf-8 -*-
"""Candado de crédito del mostrador: el servidor decide con datos frescos
(el balance del cliente cambia con cada factura); el POS solo pinta el
veredicto. Mismo principio motor/pantalla del resto de módulos Surtidora."""
from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import AccessError
from odoo.tools import float_compare


class PosPaymentMethod(models.Model):
    _inherit = 'pos.payment.method'

    surtidora_es_bono = fields.Boolean(
        string='Es bono / nota de crédito',
        help='REQ-V18: este método APLICA el saldo a favor del cliente '
             '(notas de crédito abiertas) en vez de crear deuda nueva.')

    @api.model
    def _load_pos_data_fields(self, *args, **kwargs):
        campos = super()._load_pos_data_fields(*args, **kwargs)
        return list(set(campos) | {'surtidora_es_bono'})


class PosCredito(models.AbstractModel):
    _name = 'surtidora.pos.credito'
    _description = 'Verificación de crédito para ventas del POS'

    @api.model
    def verificar(self, partner_id, monto):
        """¿Puede este cliente llevarse `monto` a crédito?

        Devuelve un veredicto con datos crudos (el POS arma el mensaje):
        - permitido: bool
        - motivo: '' | 'sin_cliente' | 'sin_credito' | 'excede'
        - limite / balance / disponible: números en moneda de la compañía
        - cliente: nombre para el mensaje

        Reglas (réplica de la condición crédito de ADG):
        - Sin cliente no hay crédito.
        - El "Límite de crédito" activado en la ficha ES la autorización:
          cliente sin límite = cliente de contado.
        - Balance pendiente + esta venta no puede pasar el límite.
        """
        # El sudo de abajo no debe quedar expuesto a cualquier autenticado.
        if not self.env.user.has_group('point_of_sale.group_pos_user'):
            raise AccessError(_('Solo usuarios del punto de venta.'))
        if not partner_id:
            return self._veredicto(False, 'sin_cliente')
        # sudo puntual: la cajera no tiene acceso contable, pero el candado
        # necesita leer el balance por cobrar del cliente.
        cliente = self.sudo().env['res.partner'].browse(int(partner_id))
        # el crédito vive en la entidad comercial (matriz), no en el contacto
        comercial = cliente.commercial_partner_id
        if not comercial.use_partner_credit_limit or comercial.credit_limit <= 0:
            return self._veredicto(False, 'sin_credito', cliente=cliente)
        # comercial.credit solo ve asientos contabilizados. El crédito fiado
        # HOY (pay_later) en una orden SIN factura no toca contabilidad hasta
        # el cierre de sesión: sin este término el cliente podría exceder su
        # límite comprando varias veces el mismo día (revisión adversaria
        # 13-ago). En una orden FACTURADA la deuda ya es la factura abierta
        # y ya está en comercial.credit: _credito_en_sesion no la repite.
        balance = comercial.credit + self._credito_en_sesion(comercial)
        disponible = comercial.credit_limit - balance
        rounding = self.env.company.currency_id.rounding
        if float_compare(monto, disponible, precision_rounding=rounding) > 0:
            return self._veredicto(False, 'excede', cliente=cliente,
                                   balance=balance, disponible=disponible)
        return self._veredicto(True, '', cliente=cliente,
                               balance=balance, disponible=disponible)

    def _dominio_sesion_abierta(self, comercial):
        """Pagos POS del cliente (entidad comercial) en sesiones aún no
        cerradas de la compañía activa: lo que la contabilidad del cierre
        todavía no registró."""
        return [
            ('pos_order_id.partner_id.commercial_partner_id', '=', comercial.id),
            ('pos_order_id.session_id.state', '!=', 'closed'),
            ('pos_order_id.company_id', '=', self.env.company.id),
        ]

    @api.model
    def _dominio_sin_factura(self):
        """La orden aún NO tiene factura publicada.

        Con factura publicada, Odoo deja abierta la factura (o la RINV) por
        la parte pagada con métodos pay_later (pos_payment.py salta esos
        pagos al crear los «Invoice payment») y el cierre ya no crea su
        apunte por cobrar (pos_session.py, `not order_is_invoiced`). Esa
        deuda o saldo a favor YA está en la CxC del cliente: sumarlo otra
        vez desde el POS lo contaba doble mientras la sesión seguía abierta.
        """
        return ['|', ('pos_order_id.account_move', '=', False),
                ('pos_order_id.account_move.state', '!=', 'posted')]

    def _credito_en_sesion(self, comercial):
        """Pagos "cuenta cliente" de sesiones POS aún abiertas: deuda real
        que la contabilidad todavía no registró. Los BONOS se excluyen:
        aplican saldo a favor existente, no crean deuda. Las órdenes con
        factura publicada también: su deuda ya es la factura abierta."""
        pagos = self.sudo().env['pos.payment'].search(
            self._dominio_sesion_abierta(comercial)
            + self._dominio_sin_factura()
            + self._dominio_fiado())
        return sum(pagos.mapped('amount'))

    # ------------------------------------------------------------------
    # Bono / Nota de Crédito como forma de pago (REQ-V18, política 12.4)
    # ------------------------------------------------------------------
    @api.model
    def verificar_bono(self, partner_id, monto):
        """¿El cliente tiene saldo a favor suficiente para pagar `monto`
        con bono? Saldo a favor = notas de crédito / pagos a cuenta sin
        conciliar (residuales NEGATIVOS en su CxC) menos los bonos ya
        usados en sesiones POS abiertas y menos lo que el cierre va a
        aplicar a la deuda desde una devolución a Crédito (DC-5,
        _plan_devoluciones)."""
        if not self.env.user.has_group('point_of_sale.group_pos_user'):
            raise AccessError(_('Solo usuarios del punto de venta.'))
        if not partner_id:
            return {'permitido': False, 'motivo': 'sin_cliente',
                    'disponible': 0.0, 'cliente': ''}
        cliente = self.sudo().env['res.partner'].browse(int(partner_id))
        comercial = cliente.commercial_partner_id
        if float(monto) <= 0:
            # DEVOLUCIÓN: el bono se EMITE (la política 12.4 dice que la
            # devolución es la que crea el bono) — no exige saldo previo
            return {'permitido': True, 'motivo': '',
                    'cliente': cliente.display_name,
                    'a_favor': 0.0, 'usados': 0.0, 'disponible': 0.0}
        lineas = self.sudo().env['account.move.line'].search([
            ('partner_id', '=', comercial.id),
            ('account_id.account_type', '=', 'asset_receivable'),
            ('parent_state', '=', 'posted'),
            ('amount_residual', '<', 0.0),
            ('company_id', '=', self.env.company.id),
        ])
        a_favor = -sum(lineas.mapped('amount_residual'))
        usados = self._bonos_usados(comercial)
        # DC-5: la devolución de un fiado rebaja la deuda, no es bono. En
        # sudo como el resto: la cajera no lee contabilidad.
        a_cuenta = -self.sudo()._plan_devoluciones(comercial)['a_favor']
        moneda = self.env.company.currency_id
        # redondeado: 160.10 − 160.10 armados por sumas distintas no debe
        # dejar un «disponible» de 1e-14 que el POS convierta en línea de 0
        disponible = moneda.round(a_favor - usados - a_cuenta)
        rounding = moneda.rounding
        permitido = (disponible > 0 and
                     float_compare(monto, disponible,
                                   precision_rounding=rounding) <= 0)
        return {
            'permitido': permitido,
            'motivo': '' if permitido else ('sin_bono' if disponible <= 0 else 'excede'),
            'cliente': cliente.display_name,
            'a_favor': a_favor,
            'usados': usados,
            'a_cuenta': a_cuenta,
            'disponible': max(disponible, 0.0),
        }

    def _bonos_usados(self, comercial):
        """Bono aplicado en sesiones abiertas que la CxC todavía NO refleja
        (REQ-V18). Se resta del saldo a favor para que el disponible sea el
        mismo con la sesión abierta que después del cierre:

        - Orden SIN factura (venta o devolución): nada llega a contabilidad
          hasta el cierre → cuenta con su signo (+ consume, − emite).
        - VENTA facturada: la NC sigue abierta hasta el cierre
          (pos.session._surtidora_conciliar_bonos) → cuenta lo que el cierre
          va a aplicar (el tope de _bono_por_conciliar).
        - DEVOLUCIÓN facturada: la RINV ya ES el bono (residual negativo, ya
          sumado en el saldo a favor) → no cuenta; contarla lo duplicaba.
        """
        pagos = self.sudo().env['pos.payment'].search(
            self._dominio_sesion_abierta(comercial)
            + self._dominio_sin_factura()
            + [('payment_method_id.surtidora_es_bono', '=', True)])
        pendientes = self._bono_por_conciliar(self._pagos_bono_facturados(comercial))
        return sum(pagos.mapped('amount')) + sum(p['tope'] for p in pendientes)

    def _pagos_bono_facturados(self, comercial):
        """Pagos con bono de órdenes con factura publicada del cliente en
        sesiones abiertas (los que el cierre concilia contra la factura)."""
        return self.sudo().env['pos.payment'].search(
            self._dominio_sesion_abierta(comercial)
            + [('payment_method_id.surtidora_es_bono', '=', True),
               ('pos_order_id.account_move.state', '=', 'posted')])

    @api.model
    def _bono_por_conciliar(self, pagos):
        """Por cada VENTA facturada pagada (en todo o en parte) con bono:
        su factura, las líneas por cobrar aún abiertas, los pagos con bono y
        el monto que el bono debe saldar al cierre.

        tope = min(Σ bono de la orden, residual abierto de la factura): la
        factura nunca se salda de más (p. ej. si alguien ya la concilió a
        mano). Una orden cuyo bono ya tiene asiento (account_move_id) ya
        fue aplicada: no está pendiente (idempotencia del cierre).

        Única fuente para el cierre de sesión, el candado del bono y el
        panel del cliente. Montos en moneda de la compañía (Surtidora opera
        en una sola moneda), igual que verificar_bono."""
        pendientes = []
        pagos = pagos.filtered(lambda p: p.payment_method_id.surtidora_es_bono
                               and p.pos_order_id.account_move.state == 'posted')
        for orden, pagos_orden in pagos.grouped('pos_order_id').items():
            if pagos_orden.account_move_id:
                continue
            factura = orden.account_move
            lineas = factura.line_ids.filtered(
                lambda l: l.account_id.account_type == 'asset_receivable'
                and not l.reconciled and l.amount_residual > 0)
            tope = min(sum(pagos_orden.mapped('amount')),
                       sum(lineas.mapped('amount_residual')))
            if float_compare(tope, 0.0,
                             precision_rounding=factura.company_currency_id.rounding) > 0:
                pendientes.append({'orden': orden, 'factura': factura,
                                   'lineas': lineas, 'pagos': pagos_orden,
                                   'tope': tope})
        return pendientes

    # ------------------------------------------------------------------
    # Devolución a la cuenta del cliente (DC-5)
    # ------------------------------------------------------------------
    # Un fiado no se devuelve en efectivo (surtidora_pos_devoluciones): va a
    # la cuenta del cliente con Crédito NEGATIVO. Eso deja un crédito en su
    # CxC (la RINV, o un apunte del cierre si no hay factura) que Odoo NO
    # concilia contra la venta fiada: el cliente seguía debiendo el total y
    # verificar_bono contaba ese crédito como saldo a favor. El mismo dinero
    # servía dos veces: liberaba cupo (el candado usa el balance neto) y se
    # gastaba como bono. Ahora el cierre lo aplica a la deuda
    # (pos.session._surtidora_aplicar_devoluciones) y, mientras la caja
    # sigue abierta, el bono y el panel ya lo descuentan.
    @api.model
    def _dominio_fiado(self):
        """Pagos «cuenta cliente»: pay_later (sin diario) que NO son bono.
        El mismo criterio que _credito_en_sesion."""
        return [('payment_method_id.journal_id', '=', False),
                ('payment_method_id.surtidora_es_bono', '=', False)]

    @api.model
    def _es_fiado(self, pago):
        metodo = pago.payment_method_id
        return metodo.type == 'pay_later' and not metodo.surtidora_es_bono

    @api.model
    def _es_devolucion_a_cuenta(self, pago):
        """Crédito NEGATIVO: lo devuelto (o abonado) va a la cuenta del
        cliente. Primero rebaja lo que debe; solo lo que sobra, si ya no
        debe nada, queda como saldo a favor que puede gastar como bono."""
        return self._es_fiado(pago) and pago.amount < 0

    @api.model
    def _dominio_deudas(self, socio, compania):
        """Deudas abiertas del cliente (entidad comercial) en su CxC."""
        return [
            ('partner_id', '=', socio.id),
            ('account_id.account_type', '=', 'asset_receivable'),
            ('company_id', '=', compania.id),
            ('parent_state', '=', 'posted'),
            ('reconciled', '=', False),
            ('amount_residual', '>', 0.0),
        ]

    @api.model
    def _apuntes_por_pago(self, pagos):
        """{pago: apuntes por cobrar donde quedó} para pagos pay_later.

        - Orden FACTURADA: su factura o su RINV. Odoo no crea apunte para
          esos pagos al cerrar (pos_session.py, `not order_is_invoiced`).
        - Orden SIN factura con la sesión cerrada: el apunte que el cierre
          creó para ESE pago (_asignar_apuntes_sesion).
        - Sesión abierta sin factura: ninguno todavía."""
        vacio = self.env['account.move.line']
        apuntes = {}
        for pago in pagos:
            factura = pago.pos_order_id.account_move
            apuntes[pago] = factura.line_ids.filtered(
                lambda l: l.account_id.account_type == 'asset_receivable'
            ) if factura.state == 'posted' else vacio
        sin_factura = pagos.filtered(lambda p: not apuntes[p]
                                     and p.session_id.state == 'closed'
                                     and p.session_id.move_id)
        for sesion in sin_factura.session_id:
            asignados = self._asignar_apuntes_sesion(sesion)
            for pago in sin_factura.filtered(lambda p: p.session_id == sesion):
                apuntes[pago] = asignados.get(pago, vacio)
        return apuntes

    @api.model
    def _asignar_apuntes_sesion(self, sesion):
        """{pago: apunte} del asiento de cierre para los pagos pay_later
        split de órdenes SIN factura de la sesión.

        El core crea UN apunte por pago (split_transactions,
        _create_pay_later_receivable_lines) con el cliente contable, su CxC
        y el monto del pago, pero no guarda el enlace. Se reconoce por
        cliente y monto, repartiendo entre TODOS los pagos de la sesión
        para que dos iguales no tomen el mismo apunte. Primero por el
        nombre, que el core arma «<sesión> - <método>» (una devolución a
        Crédito y otra a Bono por lo mismo); si el idioma del cierre fue
        otro, por monto."""
        moneda = sesion.currency_id
        pagos = sesion.order_ids.filtered(lambda o: not o.account_move).payment_ids.filtered(
            lambda p: p.payment_method_id.type == 'pay_later'
            and p.payment_method_id.split_transactions
            and not moneda.is_zero(p.amount))
        libres = sesion.move_id.line_ids.filtered(
            lambda l: l.partner_id and l.account_id.account_type == 'asset_receivable')
        asignados = {}
        for por_nombre in (True, False):
            for pago in pagos.filtered(lambda p: p not in asignados):
                socio = pago.partner_id.commercial_partner_id
                apunte = libres.filtered(
                    lambda l: l.partner_id == socio
                    and moneda.is_zero(l.balance - pago.amount)
                    and (not por_nombre
                         or (l.name or '').endswith(pago.payment_method_id.name)))[:1]
                if apunte:
                    asignados[pago] = apunte
                    libres -= apunte
        return asignados

    @api.model
    def _devoluciones_de_ventas(self, ventas):
        """Pagos de devolución a cuenta de las órdenes que devolvieron
        algo de estas ventas."""
        devoluciones = ventas.lines.refund_orderline_ids.order_id
        return devoluciones.payment_ids.filtered(self._es_devolucion_a_cuenta)

    @api.model
    def _devoluciones_por_aplicar(self, pagos):
        """Por cada orden con devolución a cuenta YA contabilizada y aún
        abierta: sus apuntes acreedores, sus pagos y cuánto aplicar (tope).

        tope = min(Σ Crédito negativo, lo abierto de sus apuntes): en una
        RINV mixta (Crédito + Bono) solo la parte de la cuenta rebaja
        deuda; la del bono sigue siendo saldo a favor. Una orden cuyo pago
        ya tiene asiento puente (account_move_id) ya se aplicó
        (idempotencia del cierre).

        Única fuente para el cierre de sesión y para el plan que usan el
        candado del bono y el panel."""
        pendientes = []
        pagos = pagos.filtered(self._es_devolucion_a_cuenta)
        apuntes = self._apuntes_por_pago(pagos)
        rounding = self.env.company.currency_id.rounding
        for orden, pagos_orden in pagos.grouped('pos_order_id').items():
            if pagos_orden.account_move_id:
                continue
            creditos = self.env['account.move.line'].union(
                *(apuntes[p] for p in pagos_orden)).filtered(
                lambda l: not l.reconciled and l.amount_residual < 0)
            tope = min(-sum(pagos_orden.mapped('amount')),
                       -sum(creditos.mapped('amount_residual')))
            if float_compare(tope, 0.0, precision_rounding=rounding) > 0:
                pendientes.append({'orden': orden, 'pagos': pagos_orden,
                                   'creditos': creditos, 'tope': tope})
        return pendientes

    @api.model
    def _deuda_de_venta(self, venta):
        """Lo que la venta devuelta dejó a deber con Crédito: (apuntes aún
        abiertos, ¿sigue sin contabilizar?). Sin contabilizar = su caja
        sigue abierta y no se facturó: la deuda llega con ese cierre."""
        apuntes = self.env['account.move.line']
        pagos = venta.payment_ids.filtered(lambda p: self._es_fiado(p) and p.amount > 0)
        if not pagos:
            return apuntes, False
        apuntes = apuntes.union(*self._apuntes_por_pago(pagos).values())
        if not apuntes:
            return apuntes, venta.session_id.state != 'closed'
        return apuntes.filtered(lambda l: not l.reconciled and l.amount_residual > 0), False

    @api.model
    def _deudas_reservadas_bono(self, pagos_bono):
        """Facturas que un bono va a pagar al cerrar su caja
        (_bono_por_conciliar). La devolución no las toca: si las pagara, el
        bono no encontraría qué pagar y el saldo a favor quedaría para
        gastarse otra vez."""
        return self.env['account.move.line'].union(
            *(p['lineas'] for p in self._bono_por_conciliar(pagos_bono)))

    def _devoluciones_pendientes(self, comercial):
        """Devoluciones a cuenta del cliente que algún cierre todavía va a
        aplicar: las de cajas abiertas, y las ya cerradas cuya venta fiada
        sigue en una caja abierta (se aplican al cerrar esa caja)."""
        Pago = self.sudo().env['pos.payment']
        fiado = self._dominio_sesion_abierta(comercial) + self._dominio_fiado()
        abiertas = Pago.search(fiado + [('amount', '<', 0)])
        ventas = Pago.search(fiado + [('amount', '>', 0)]).pos_order_id
        cerradas = self._devoluciones_de_ventas(ventas).filtered(
            lambda p: p.partner_id.commercial_partner_id == comercial)
        return abiertas | cerradas

    def _deudas_disponibles(self, comercial):
        """{deuda: lo que admite}, en el orden en que el cierre las rebaja
        (FIFO: las que vencen primero, primero):
        - apuntes por cobrar abiertos, menos los reservados por un bono;
        - lo fiado HOY en órdenes sin factura de cajas abiertas (la orden
          es la clave): todavía no está en contabilidad, pero su cierre
          creará la deuda contra la que se aplicará la devolución."""
        env = self.sudo().env
        reservadas = self._deudas_reservadas_bono(self._pagos_bono_facturados(comercial))
        lineas = env['account.move.line'].search(
            self._dominio_deudas(comercial, self.env.company),
            order='date_maturity, date, id') - reservadas
        disponibles = {linea: linea.amount_residual for linea in lineas}
        fiado = env['pos.payment'].search(
            self._dominio_sesion_abierta(comercial) + self._dominio_sin_factura()
            + self._dominio_fiado() + [('amount', '>', 0)])
        for venta, pagos in fiado.grouped('pos_order_id').items():
            disponibles[venta] = sum(pagos.mapped('amount'))
        return disponibles

    def _plan_devoluciones(self, comercial):
        """Lo que los cierres pendientes harán con las devoluciones a
        cuenta del cliente, para que el bono y el panel digan HOY lo mismo
        que después del cierre (igual que _bonos_usados con los bonos).

        Simula pos.session._surtidora_aplicar_devoluciones: cada devolución
        rebaja primero la deuda de la venta devuelta y después las demás
        (FIFO). Lo que no encuentra deuda es saldo a favor legítimo.

        Devuelve el ajuste de cada cifra del panel:
        - a_favor: saldo a favor que va a la deuda (negativo), o el sobrante
          de una devolución aún sin contabilizar (positivo);
        - en_sesion: el mismo ajuste sobre lo fiado en cajas abiertas;
        - deudas: {apunte: monto} que se le rebaja a cada deuda."""
        plan = {'a_favor': 0.0, 'en_sesion': 0.0, 'deudas': defaultdict(float)}
        pagos = self._devoluciones_pendientes(comercial)
        if not pagos:
            return plan
        contabilizadas = {p['orden']: p['tope']
                          for p in self._devoluciones_por_aplicar(pagos)}
        disponibles = self._deudas_disponibles(comercial)
        rounding = self.env.company.currency_id.rounding
        for devolucion, pagos_dev in sorted(pagos.grouped('pos_order_id').items(),
                                            key=lambda par: par[0].id):
            contabilizada = devolucion in contabilizadas
            if contabilizada:
                resto = contabilizadas[devolucion]
            elif devolucion.session_id.state != 'closed' \
                    and devolucion.account_move.state != 'posted':
                resto = -sum(pagos_dev.mapped('amount'))
            else:
                continue  # ya se aplicó al cerrar su caja
            for deuda in self._deudas_en_orden(devolucion, disponibles):
                toma = min(resto, disponibles[deuda])
                if float_compare(toma, 0.0, precision_rounding=rounding) <= 0:
                    continue
                disponibles[deuda] -= toma
                resto -= toma
                if deuda._name == 'pos.order':
                    plan['en_sesion'] -= toma      # fiado de hoy que se rebaja
                else:
                    plan['deudas'][deuda] += toma
                if contabilizada:
                    plan['a_favor'] -= toma        # deja de ser saldo a favor
                else:
                    plan['en_sesion'] += toma      # sale de lo pendiente de hoy
                if float_compare(resto, 0.0, precision_rounding=rounding) <= 0:
                    break
            if not contabilizada and float_compare(resto, 0.0, precision_rounding=rounding) > 0:
                # sin deuda que rebajar: al cerrar queda como saldo a favor
                plan['a_favor'] += resto
                plan['en_sesion'] += resto
        return plan

    def _deudas_en_orden(self, devolucion, disponibles):
        """Primero la deuda de la venta devuelta, después las demás."""
        apuntes, sin_contabilizar = self._deuda_de_venta(devolucion.refunded_order_id)
        primero = list(apuntes) + ([devolucion.refunded_order_id] if sin_contabilizar else [])
        primero = [d for d in primero if d in disponibles]
        return primero + [d for d in disponibles if d not in primero]

    def _veredicto(self, permitido, motivo, cliente=None, balance=0.0,
                   disponible=0.0):
        comercial = cliente.commercial_partner_id if cliente else None
        return {
            'permitido': permitido,
            'motivo': motivo,
            'cliente': cliente.display_name if cliente else '',
            'limite': comercial.credit_limit if comercial else 0.0,
            'balance': balance,
            'disponible': max(disponible, 0.0),
        }

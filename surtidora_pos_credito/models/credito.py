# -*- coding: utf-8 -*-
"""Candado de crédito del mostrador: el servidor decide con datos frescos
(el balance del cliente cambia con cada factura); el POS solo pinta el
veredicto. Mismo principio motor/pantalla del resto de módulos Surtidora."""
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
            + [('payment_method_id.journal_id', '=', False),
               ('payment_method_id.surtidora_es_bono', '=', False)])
        return sum(pagos.mapped('amount'))

    # ------------------------------------------------------------------
    # Bono / Nota de Crédito como forma de pago (REQ-V18, política 12.4)
    # ------------------------------------------------------------------
    @api.model
    def verificar_bono(self, partner_id, monto):
        """¿El cliente tiene saldo a favor suficiente para pagar `monto`
        con bono? Saldo a favor = notas de crédito / pagos a cuenta sin
        conciliar (residuales NEGATIVOS en su CxC) menos los bonos ya
        usados en sesiones POS abiertas."""
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
        disponible = a_favor - usados
        rounding = self.env.company.currency_id.rounding
        permitido = (disponible > 0 and
                     float_compare(monto, disponible,
                                   precision_rounding=rounding) <= 0)
        return {
            'permitido': permitido,
            'motivo': '' if permitido else ('sin_bono' if disponible <= 0 else 'excede'),
            'cliente': cliente.display_name,
            'a_favor': a_favor,
            'usados': usados,
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

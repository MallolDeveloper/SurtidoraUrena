# -*- coding: utf-8 -*-
"""Candado de crédito del mostrador: el servidor decide con datos frescos
(el balance del cliente cambia con cada factura); el POS solo pinta el
veredicto. Mismo principio motor/pantalla del resto de módulos Surtidora."""
from odoo import _, api, models
from odoo.exceptions import AccessError
from odoo.tools import float_compare


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
        # comercial.credit solo ve asientos contabilizados; el crédito fiado
        # HOY (pay_later) no toca contabilidad hasta el cierre de sesión.
        # Sin este término el cliente podría exceder su límite comprando
        # varias veces el mismo día (revisión adversaria 13-ago).
        balance = comercial.credit + self._credito_en_sesion(comercial)
        disponible = comercial.credit_limit - balance
        rounding = self.env.company.currency_id.rounding
        if float_compare(monto, disponible, precision_rounding=rounding) > 0:
            return self._veredicto(False, 'excede', cliente=cliente,
                                   balance=balance, disponible=disponible)
        return self._veredicto(True, '', cliente=cliente,
                               balance=balance, disponible=disponible)

    def _credito_en_sesion(self, comercial):
        """Pagos "cuenta cliente" de sesiones POS aún abiertas: deuda real
        que la contabilidad todavía no registró."""
        pagos = self.sudo().env['pos.payment'].search([
            ('payment_method_id.type', '=', 'pay_later'),
            ('pos_order_id.partner_id.commercial_partner_id', '=', comercial.id),
            ('pos_order_id.session_id.state', '!=', 'closed'),
            ('pos_order_id.company_id', '=', self.env.company.id),
        ])
        return sum(pagos.mapped('amount'))

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

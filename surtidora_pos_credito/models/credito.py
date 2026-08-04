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
        balance = comercial.credit
        disponible = comercial.credit_limit - balance
        rounding = self.env.company.currency_id.rounding
        if float_compare(monto, disponible, precision_rounding=rounding) > 0:
            return self._veredicto(False, 'excede', cliente=cliente,
                                   balance=balance, disponible=disponible)
        return self._veredicto(True, '', cliente=cliente,
                               balance=balance, disponible=disponible)

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

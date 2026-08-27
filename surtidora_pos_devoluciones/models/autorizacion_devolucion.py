# -*- coding: utf-8 -*-
"""La clave del supervisor para devolver EFECTIVO en el mostrador.

Solo se pide cuando sale dinero de la gaveta. Un bono o una nota de crédito
no mueven efectivo, así que pasan como antes: quien devuelve no se lleva nada
que haya que reponer al cuadrar.

El PIN se valida AQUÍ —el hash nunca viaja al navegador— reutilizando el
mismo verificador que autoriza las rebajas de precio.
"""
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError


class AutorizacionDevolucion(models.Model):
    _name = 'surtidora.autorizacion.devolucion'
    _description = 'Autorización de devolución en efectivo'
    _order = 'create_date desc'
    _rec_name = 'order_ref'

    order_ref = fields.Char(
        string='Referencia de la venta', required=True, index=True,
        help='Referencia que el mostrador dio a la devolución. Se enlaza con '
             'la orden real cuando esta baja al servidor.')
    pos_order_id = fields.Many2one(
        'pos.order', string='Devolución', ondelete='set null', index='btree_not_null',
        help='Se rellena cuando la devolución llega del mostrador. Vacío '
             'significa que se autorizó y después no se cobró.')
    autorizador_id = fields.Many2one(
        'res.users', string='Autorizó', required=True, ondelete='restrict')
    cajero_id = fields.Many2one(
        'res.users', string='Lo pidió', required=True, ondelete='restrict')
    monto = fields.Monetary(string='Efectivo devuelto', required=True)
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda s: s.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    consumida = fields.Boolean(
        string='Usada', default=False, copy=False,
        help='Una autorización sirve para UNA devolución. Sin esto, el mismo '
             'permiso valdría para devolver dos veces.')


class PosDevolucion(models.AbstractModel):
    _name = 'surtidora.pos.devolucion'
    _description = 'Autorización de devolución en efectivo desde el POS'

    @api.model
    def autorizar_efectivo(self, pin, order_ref, monto, refunded_order_id=False,
                           session_id=False):
        """Valida el PIN y deja la autorización lista para la devolución.

        Devuelve {ok, autorizador} o {ok: False, mensaje} explicando POR QUÉ.
        El mensaje importa: si el cajero no sabe si falló la clave, el monto o
        la caja, va a volver a intentarlo hasta que alguien se canse.

        Aquí se repiten las mismas comprobaciones que hace la compuerta del
        servidor al validar. No es duplicar por gusto: sin esto el cajero se
        entera del problema DESPUÉS de teclear la clave del supervisor y con
        el cliente delante.
        """
        self._verificar_pos_user()
        monto = abs(float(monto or 0.0))
        if not pin or not monto:
            return {'ok': False}

        # La sesión la manda el mostrador: buscarla por usuario sería adivinar
        # —un cajero puede tener más de una abierta— y de esa suposición
        # dependen dos de las cuatro reglas.
        original = self.env['pos.order'].browse(
            int(refunded_order_id)).exists() if refunded_order_id else None
        sesion = self.env['pos.session'].browse(
            int(session_id)).exists() if session_id else self.env['pos.session']
        problema = self.env['pos.order']._surtidora_problema_devolucion(
            original, monto, sesion)
        if problema:
            return {'ok': False, 'mensaje': problema}

        try:
            autorizador = self.env['res.users']._surtidora_verificar_pin(str(pin))
        except UserError as bloqueo:
            # demasiados intentos: el cajero tiene que saber POR QUÉ no entra
            return {'ok': False, 'mensaje': str(bloqueo)}
        if not autorizador:
            return {'ok': False}

        self.env['surtidora.autorizacion.devolucion'].sudo().create({
            'order_ref': order_ref or '',
            'autorizador_id': autorizador.id,
            'cajero_id': self.env.uid,
            'monto': monto,
            'company_id': self.env.company.id,
        })
        return {'ok': True, 'autorizador': autorizador.name}

    @api.model
    def _verificar_pos_user(self):
        if not self.env.user.has_group('point_of_sale.group_pos_user'):
            raise AccessError(_('Solo el personal del mostrador puede pedir '
                                'una autorización de devolución.'))

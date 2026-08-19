# -*- coding: utf-8 -*-
"""El PIN del supervisor: el secreto con el que se aprueban las rebajas.

Todo lo que se cuida aquí existe por una sola razón: que la bitácora de
autorizaciones diga la VERDAD sobre quién aprobó cada rebaja. Un PIN
compartido, adivinable o imposible de revocar no es un problema de
seguridad abstracto — es una bitácora que señala a la persona equivocada.
"""
from datetime import timedelta

from markupsafe import Markup
from passlib.context import CryptContext

from odoo import _, fields, models
from odoo.exceptions import UserError, ValidationError

# mismo esquema de hash que usa Odoo para contraseñas
_pin_crypt = CryptContext(schemes=['pbkdf2_sha512'])

_PIN_MINIMO = 4        # dígitos
_INTENTOS_MAX = 5      # fallos seguidos antes de cerrar la puerta
_BLOQUEO_MINUTOS = 5   # cuánto se queda cerrada


class ResUsers(models.Model):
    _inherit = 'res.users'

    surtidora_pin_hash = fields.Char(groups='base.group_system', copy=False)
    surtidora_pin = fields.Char(
        string='PIN de autorización de precios',
        compute='_compute_surtidora_pin', inverse='_inverse_surtidora_pin',
        help='PIN secreto del supervisor (REQ-V27). Se guarda cifrado; al '
             'teclearlo en la estación del vendedor aprueba rebajas de precio.\n\n'
             'Solo números y al menos %s dígitos, porque en la caja se teclea '
             'con el teclado numérico. No puede repetir el de otro autorizador: '
             'si dos personas comparten PIN, la bitácora no puede decir quién '
             'autorizó. Para retirarlo, borre el contenido del campo y '
             'guarde.' % _PIN_MINIMO)
    # contadores del ANTIFRAUDE, sobre el usuario que PIDE la autorización
    # (el cajero), no sobre el supervisor. Sin vista: son de uso interno.
    surtidora_pin_intentos = fields.Integer(default=0, copy=False)
    surtidora_pin_bloqueado_hasta = fields.Datetime(copy=False)

    # ------------------------------------------------------------------
    # Poner, cambiar y RETIRAR el PIN
    # ------------------------------------------------------------------
    def _compute_surtidora_pin(self):
        for user in self:
            user.surtidora_pin = '****' if user.sudo().surtidora_pin_hash else False

    def _inverse_surtidora_pin(self):
        for user in self:
            valor = (user.surtidora_pin or '').strip()
            if valor == '****':
                continue  # nadie lo tocó: es lo que muestra el compute
            if not valor:
                # RETIRAR. Antes, vaciar el campo no hacía nada y el PIN
                # anterior seguía vigente para siempre: a un supervisor que
                # se iba de la empresa no había forma de quitárselo.
                user.sudo().write({
                    'surtidora_pin_hash': False,
                    'surtidora_pin_intentos': 0,
                    'surtidora_pin_bloqueado_hasta': False,
                })
                user._surtidora_anotar_cambio(_('PIN de autorización RETIRADO'))
                continue
            user._surtidora_validar_pin(valor)
            user.sudo().write({
                'surtidora_pin_hash': _pin_crypt.hash(valor),
                'surtidora_pin_intentos': 0,
                'surtidora_pin_bloqueado_hasta': False,
            })
            user._surtidora_anotar_cambio(_('PIN de autorización cambiado'))

    def _surtidora_validar_pin(self, valor):
        """Las tres condiciones que hacen que el PIN sirva para auditar."""
        self.ensure_one()
        if not valor.isdigit():
            raise ValidationError(_(
                'El PIN solo puede llevar números: en la caja se teclea con el '
                'teclado numérico y una letra no se podría escribir.'))
        if len(valor) < _PIN_MINIMO:
            raise ValidationError(_(
                'El PIN debe tener al menos %s dígitos.') % _PIN_MINIMO)
        if len(set(valor)) == 1:
            raise ValidationError(_(
                'Un PIN con todos los dígitos iguales se adivina al primer '
                'intento. Elija otro.'))
        # UNICIDAD. Sin esto, si dos supervisores eligen el mismo PIN, el
        # sistema atribuye la rebaja al primero de la lista y nadie se entera:
        # la bitácora señalaría a quien no autorizó nada.
        for otro in self.sudo().search([('id', '!=', self.id)]):
            if otro.surtidora_pin_hash and _pin_crypt.verify(
                    valor, otro.surtidora_pin_hash):
                raise ValidationError(_(
                    'Ese PIN ya lo usa otro autorizador. Elija uno distinto: '
                    'si dos personas comparten PIN, la bitácora no puede decir '
                    'quién autorizó la rebaja.'))

    def _surtidora_anotar_cambio(self, texto):
        """Quién tocó el PIN y cuándo, en el historial del usuario. Cambiar un
        PIN es tan auditable como usarlo."""
        self.ensure_one()
        self.sudo().message_post(body=Markup('<p>%s</p>') % _(
            '%(que)s por %(quien)s.', que=texto, quien=self.env.user.name))

    # ------------------------------------------------------------------
    # Usarlo
    # ------------------------------------------------------------------
    def _surtidora_verificar_pin(self, pin):
        """Devuelve el usuario autorizador (grupo Autorizador de Precios) cuyo
        PIN coincide, o un recordset vacío si nadie coincide.

        Lanza UserError si quien lo pide está bloqueado por intentos fallidos.
        """
        solicitante = self.env.user
        ahora = fields.Datetime.now()
        hasta = solicitante.sudo().surtidora_pin_bloqueado_hasta
        if hasta and hasta > ahora:
            minutos = int((hasta - ahora).total_seconds() // 60) + 1
            raise UserError(_(
                'Demasiados intentos con un PIN incorrecto. Vuelva a '
                'intentarlo en %s minuto(s).') % minutos)
        autorizadores = self.env.ref(
            'surtidora_autorizacion_precio.group_autorizador_precio').sudo().user_ids
        for user in autorizadores:
            if user.surtidora_pin_hash and _pin_crypt.verify(
                    pin.strip(), user.surtidora_pin_hash):
                self._surtidora_contar_intento(solicitante, acierto=True)
                return user
        self._surtidora_contar_intento(solicitante, acierto=False)
        return self.env['res.users']

    def _surtidora_contar_intento(self, solicitante, acierto):
        """Cuenta los intentos del usuario que PIDE la autorización.

        Va con cursor propio a propósito: cuando el PIN no vale, el backend
        lanza UserError y el rollback se llevaría por delante el contador —
        el mismo motivo por el que el asistente borra su PIN así. Sin esto,
        probar los 10,000 PIN de cuatro dígitos no cuesta nada.

        El bloqueo es por SOLICITANTE, no por supervisor: así un cajero
        insistente no deja fuera de juego a toda la tienda.
        """
        with self.pool.cursor() as cr:
            if acierto:
                cr.execute(
                    'UPDATE res_users SET surtidora_pin_intentos = 0, '
                    'surtidora_pin_bloqueado_hasta = NULL WHERE id = %s',
                    (solicitante.id,))
                return
            cr.execute(
                'UPDATE res_users SET surtidora_pin_intentos = '
                'COALESCE(surtidora_pin_intentos, 0) + 1 WHERE id = %s '
                'RETURNING surtidora_pin_intentos', (solicitante.id,))
            fila = cr.fetchone()
            if fila and fila[0] >= _INTENTOS_MAX:
                cr.execute(
                    'UPDATE res_users SET surtidora_pin_intentos = 0, '
                    'surtidora_pin_bloqueado_hasta = %s WHERE id = %s',
                    (fields.Datetime.now() + timedelta(minutes=_BLOQUEO_MINUTOS),
                     solicitante.id))

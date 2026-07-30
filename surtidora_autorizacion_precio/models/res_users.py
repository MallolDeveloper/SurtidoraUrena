# -*- coding: utf-8 -*-
from passlib.context import CryptContext

from odoo import fields, models

# mismo esquema de hash que usa Odoo para contraseñas
_pin_crypt = CryptContext(schemes=['pbkdf2_sha512'])


class ResUsers(models.Model):
    _inherit = 'res.users'

    surtidora_pin_hash = fields.Char(groups='base.group_system', copy=False)
    surtidora_pin = fields.Char(
        string='PIN de autorización de precios',
        compute='_compute_surtidora_pin', inverse='_inverse_surtidora_pin',
        help='PIN secreto del supervisor (REQ-V27). Se guarda cifrado; '
             'al teclearlo en la estación del vendedor aprueba rebajas de precio.')

    def _compute_surtidora_pin(self):
        for user in self:
            user.surtidora_pin = '****' if user.sudo().surtidora_pin_hash else False

    def _inverse_surtidora_pin(self):
        for user in self:
            if user.surtidora_pin and user.surtidora_pin != '****':
                user.sudo().surtidora_pin_hash = _pin_crypt.hash(user.surtidora_pin.strip())

    def _surtidora_verificar_pin(self, pin):
        """Devuelve el usuario autorizador (grupo Autorizador de Precios de esta
        compañía) cuyo PIN coincide, o un recordset vacío si nadie coincide."""
        autorizadores = self.env.ref(
            'surtidora_autorizacion_precio.group_autorizador_precio').sudo().user_ids
        for user in autorizadores:
            if user.surtidora_pin_hash and _pin_crypt.verify(pin.strip(), user.surtidora_pin_hash):
                return user
        return self.env['res.users']

# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    # Decisión del cliente (14-sep-2026): arrancan solo con la hoja impresa
    # y contabilidad marca el depósito al conciliar; cuando le agarren
    # confianza, encienden esto y la supervisora lo registra con un botón.
    surtidora_registrar_deposito = fields.Boolean(
        string='La supervisora registra el depósito',
        help='Con esto encendido, la hoja de depósito trae el botón '
             '«Registrar depósito», que mueve el efectivo a depositar del '
             'diario de caja al diario del banco. El monto sale del arqueo; '
             'no se teclea.')
    surtidora_diario_deposito_id = fields.Many2one(
        'account.journal', string='Banco donde se deposita',
        domain="[('type', '=', 'bank'), ('company_id', '=', id)]")
    surtidora_fondo_caja = fields.Monetary(
        string='Fondo que se deja en cada caja', default=2000.0,
        currency_field='currency_id',
        help='Lo que la supervisora deja en la gaveta al cerrar (RD$2,000 en '
             'todas las cajas, medido en ADG). La hoja de depósito lo resta '
             'del efectivo contado por cada caja cerrada, y la caja lo propone '
             'al abrir el turno siguiente. En cero, la caja propone lo contado '
             'en el cierre anterior, como Odoo de fábrica.')

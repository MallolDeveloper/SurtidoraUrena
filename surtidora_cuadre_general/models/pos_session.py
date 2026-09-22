# -*- coding: utf-8 -*-
from odoo import models


class PosSession(models.Model):
    _inherit = 'pos.session'

    def action_pos_session_open(self):
        """Al abrir, la caja propone el fondo que la supervisora deja en la
        gaveta (Ajustes → Punto de venta), no lo que se contó al cerrar.

        Odoo propone lo contado en el cierre anterior. En Surtidora ese monto
        incluye lo que la supervisora se lleva al banco, así que cada mañana la
        cajera abría con RD$2,000 contra una propuesta de, por ejemplo,
        RD$12,576.70, y el turno anotaba esa «diferencia» todos los días. Solo
        cambia lo que se propone: si la gaveta tiene otra cosa, la cajera
        teclea lo que cuenta y Odoo anota la diferencia como siempre.

        No se toca un turno de rescate ni una caja sin control de efectivo, y
        con el fondo en cero en Ajustes queda lo de fábrica."""
        por_abrir = self.filtered(lambda s: s.state == 'opening_control')
        resultado = super().action_pos_session_open()
        for sesion in por_abrir:
            fondo = sesion.company_id.surtidora_fondo_caja
            if fondo and sesion.config_id.cash_control and not sesion.rescue:
                sesion.cash_register_balance_start = fondo
        return resultado

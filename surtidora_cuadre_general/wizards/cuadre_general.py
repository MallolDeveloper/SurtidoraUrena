# -*- coding: utf-8 -*-
"""Asistente «Cuadre general»: fecha (y caja opcional) → PDF con el cuadre
de todas las cajas y la hoja de depósito; y el botón de registrar el
depósito si está encendido en Ajustes."""
from odoo import _, api, fields, models


class CuadreGeneral(models.TransientModel):
    _name = 'surtidora.cuadre.general'
    _description = 'Cuadre general de cajas'

    fecha = fields.Date(string='Día', required=True, default=fields.Date.context_today)
    config_id = fields.Many2one('pos.config', string='Caja',
                                help='Vacío = todas las cajas del día.')
    resumen = fields.Html(compute='_compute_resumen', sanitize=False)
    puede_registrar = fields.Boolean(compute='_compute_resumen')
    a_depositar = fields.Monetary(compute='_compute_resumen', currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', default=lambda s: s.env.company.currency_id)

    @api.depends('fecha', 'config_id')
    def _compute_resumen(self):
        motor = self.env['surtidora.cuadre.general.motor']
        for wizard in self:
            if not wizard.fecha:
                wizard.resumen, wizard.puede_registrar, wizard.a_depositar = '', False, 0.0
                continue
            d = motor.datos(wizard.fecha, wizard.config_id or None)
            moneda = wizard.currency_id
            if not d['sesiones']:
                wizard.resumen = _('<p class="text-muted">No hay cajas cerradas ese día.</p>')
                wizard.puede_registrar, wizard.a_depositar = False, 0.0
                continue
            filas = ''.join(
                f"<tr><td>{c['caja']}</td><td class='text-end'>{c['turnos']}</td>"
                f"<td class='text-end'>{moneda.format(c['contado'])}</td>"
                f"<td class='text-end'>{moneda.format(c['diferencia'])}</td></tr>"
                for c in d['cajas'])
            aviso = (_('<p class="text-warning mb-1">⚠ Alguna caja cerró sin conteo por '
                       'denominación: la hoja de depósito sale incompleta.</p>')
                     if d['arqueo_incompleto'] else '')
            wizard.resumen = (
                f"{aviso}<table class='table table-sm mb-2'><thead><tr><th>Caja</th>"
                f"<th class='text-end'>Turnos</th><th class='text-end'>Contado</th>"
                f"<th class='text-end'>Diferencia</th></tr></thead><tbody>{filas}</tbody></table>"
                f"<p class='mb-0'><b>{_('Efectivo a depositar')}:</b> {moneda.format(d['a_depositar'])}"
                f" &nbsp;·&nbsp; <b>{_('Según facturas')}:</b> {moneda.format(d['segun_facturas'])}"
                f" &nbsp;·&nbsp; <b>{_('Sobrante / faltante')}:</b> {moneda.format(d['sobrante'])}</p>")
            wizard.puede_registrar = d['puede_registrar'] and d['a_depositar'] > 0
            wizard.a_depositar = d['a_depositar']

    def action_imprimir(self):
        self.ensure_one()
        return self.env.ref('surtidora_cuadre_general.action_reporte_cuadre_general') \
            .report_action(self)

    def action_registrar_deposito(self):
        self.ensure_one()
        asiento = self.env['surtidora.cuadre.general.motor'].registrar_deposito(
            self.fecha, self.a_depositar, self.config_id or None)
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': asiento.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def surtidora_datos(self):
        """Para la plantilla QWeb (no invoca métodos con guion bajo)."""
        self.ensure_one()
        return self.env['surtidora.cuadre.general.motor'].datos(
            self.fecha, self.config_id or None)

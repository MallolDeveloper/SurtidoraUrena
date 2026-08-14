# -*- coding: utf-8 -*-
"""Asistente que autoriza el ajuste: motivo del catálogo + clave del
supervisor. Es el único que puede emitir el vale que la compuerta exige."""
import uuid

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_is_zero

from ..models.ajuste import CTX_VALE

_GRUPO_AUTORIZADOR = 'surtidora_autorizacion_precio.group_autorizador_precio'
_MAX_LINEAS_RESUMEN = 25


class AjusteAutorizacion(models.TransientModel):
    _name = 'surtidora.ajuste.autorizacion'
    _description = 'Autorización de ajuste de inventario'

    quant_ids = fields.Many2many('stock.quant', string='Líneas a ajustar')
    motivo_id = fields.Many2one('surtidora.motivo.ajuste', string='Motivo',
                                required=True)
    nota = fields.Char(string='Nota', help='Detalle libre para la bitácora.')
    pin = fields.Char(string='Clave del supervisor', required=True)
    resumen = fields.Text(string='Resumen', readonly=True,
                          compute='_compute_resumen')

    @api.depends('quant_ids')
    def _compute_resumen(self):
        """Qué se va a ajustar, a la vista antes de teclear la clave.

        Altas y bajas van SEPARADAS: netearlas escondía la magnitud real
        (500 de faltante contra 500 de sobrante no es «cero movimiento»)."""
        for wizard in self:
            lineas, altas, bajas = [], 0.0, 0.0
            quants = wizard.quant_ids
            for quant in quants:
                compania = quant.company_id or self.env.company
                diferencia = quant.inventory_quantity - quant.quantity
                valor = diferencia * quant.product_id.with_company(
                    compania).standard_price
                if diferencia >= 0:
                    altas += valor
                else:
                    bajas += valor
                if len(lineas) < _MAX_LINEAS_RESUMEN:
                    lineas.append('%s: %+.2f %s (%s → %s)' % (
                        quant.product_id.display_name, diferencia,
                        quant.product_uom_id.name or '',
                        self._num(quant.quantity),
                        self._num(quant.inventory_quantity)))
            if len(quants) > _MAX_LINEAS_RESUMEN:
                lineas.append(_('… y %s líneas más.')
                              % (len(quants) - _MAX_LINEAS_RESUMEN))
            if quants:
                moneda = (quants[:1].company_id or self.env.company).currency_id
                lineas.append('')
                lineas.append(_('%(n)s línea(s). Sobrantes: %(s)s %(a)s · '
                                'Faltantes: %(s)s %(b)s',
                                n=len(quants), s=moneda.symbol,
                                a=self._num(altas), b=self._num(abs(bajas))))
            wizard.resumen = '\n'.join(lineas) or _('Sin líneas por ajustar.')

    @staticmethod
    def _num(valor):
        return '{:,.2f}'.format(valor or 0.0)

    def action_confirmar(self):
        self.ensure_one()
        pin = (self.pin or '').strip()
        # el PIN se borra ANTES que nada: el asistente lo guarda en su tabla
        # para poder enviarlo, y quien lo puede leer después es justo el
        # encargado al que se está controlando
        self.sudo().write({'pin': False})

        quants = self.quant_ids.filtered(lambda q: not float_is_zero(
            q.inventory_quantity - q.quantity,
            precision_rounding=q.product_uom_id.rounding or 0.01))
        if not quants:
            raise UserError(_('Ya no hay diferencias por ajustar.'))

        autorizador = self.env['res.users']._surtidora_verificar_pin(pin)
        if not autorizador or not autorizador.has_group(_GRUPO_AUTORIZADOR):
            # mismo mensaje en ambos casos: no se le dice a quien prueba
            # claves si acertó el usuario pero le falta el permiso
            raise UserError(_('Clave de supervisor incorrecta o sin permiso '
                              'para autorizar ajustes.'))

        # la foto se toma ANTES de aplicar: al aplicar, el conteo se limpia
        filas = quants.surtidora_datos_ajuste()
        for fila in filas:
            fila.update({
                'motivo_id': self.motivo_id.id,
                'motivo_texto': self.motivo_id.name,
                'nota': self.nota or '',
                'solicitante_id': self.env.user.id,
                'autorizador_id': autorizador.id,
            })

        vale = self.env['surtidora.ajuste.vale'].sudo().create({
            'token': uuid.uuid4().hex,
            'user_id': self.env.uid,
            'autorizador_id': autorizador.id,
            'quant_ids': [(6, 0, quants.ids)],
        })
        try:
            resultado = quants.with_context(
                **{CTX_VALE: vale.token}).action_apply_inventory()
        finally:
            # el vale vale para UNA aplicación, salga bien o mal
            vale.sudo().usado = True
        # la bitácora se escribe DESPUÉS de que el ajuste ocurrió: si algo
        # revienta antes, no queda un registro de un ajuste que no pasó
        self.env['surtidora.ajuste.bitacora'].sudo().create(filas)
        return resultado

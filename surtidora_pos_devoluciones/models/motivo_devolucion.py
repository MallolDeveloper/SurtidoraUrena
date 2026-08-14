# -*- coding: utf-8 -*-
from odoo import api, fields, models


class MotivoDevolucion(models.Model):
    """Catálogo de motivos de devolución (REQ-V18).

    Réplica del sis_tipos_devoluciones de ADG, donde el tipo es OBLIGATORIO
    al registrar la devolución (inv_tipodev_oblig=True). Los precargados son
    los reales del cliente, ordenados por frecuencia de uso; editables y
    archivables por el encargado del POS."""
    _name = 'surtidora.motivo.devolucion'
    _inherit = ['pos.load.mixin']
    _description = 'Motivo de devolución'
    _order = 'sequence, id'

    name = fields.Char(string='Motivo', required=True)
    nota = fields.Char(
        string='Nota',
        help='Aclaración para la cajera de cuándo aplica este motivo.')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    # v19: _sql_constraints ya no existe (el registry lo ignora con warning)
    _nombre_unico = models.Constraint('unique(name)', 'Ese motivo ya existe.')

    # *args/**kwargs: blindaje ante cambios de firma del mixin entre builds
    @api.model
    def _load_pos_data_domain(self, *args, **kwargs):
        return [('active', '=', True)]

    @api.model
    def _load_pos_data_fields(self, *args, **kwargs):
        # nota: segunda línea del popup (guía de la cajera); active: el POS
        # refresca el catálogo incluyendo archivados para depurar su caché
        return ['id', 'name', 'sequence', 'nota', 'active']

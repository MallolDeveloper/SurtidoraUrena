# -*- coding: utf-8 -*-
from odoo import fields, models


class MotivoDescuento(models.Model):
    """Catálogo de motivos de descuento/autorización (reunión 7-ago, punto 6).

    En vez de un texto libre, el motivo se ELIGE de esta lista — así después
    se puede analizar cuáles motivos generan más descuentos (propuesta de
    Carlos aprobada por Adelso). El listado definitivo lo entrega Surtidora;
    los precargados son editables/archivables."""
    _name = 'surtidora.motivo.descuento'
    _description = 'Motivo de descuento / autorización de precio'
    _order = 'sequence, name'

    name = fields.Char(string='Motivo', required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('nombre_unico', 'unique(name)', 'Ese motivo ya existe.'),
    ]

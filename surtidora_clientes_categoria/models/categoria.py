# -*- coding: utf-8 -*-
"""Categoría del cliente como etiqueta buscable (REQ-V28).

En ADG el catálogo de categorías está VACÍO: la única fuente es el
paréntesis dentro del nombre ("RICARDO ESPINAL (CHUCHERO)"). Ese
workaround es justo lo que el requerimiento pide eliminar.

Odoo ya trae etiquetas de contacto buscables y filtrables; lo que falta es
(a) el vocabulario real del cliente y (b) sacar la categoría del nombre y
convertirla en etiqueta. Esto último es delicado —toca el nombre de 900
clientes— así que va con vista previa obligatoria.

Las variantes se declaran en datos, no en código: la lista es de Adelso y
va a cambiar."""
from odoo import fields, models


class ResPartnerCategory(models.Model):
    _inherit = 'res.partner.category'

    surtidora_variantes = fields.Char(
        string='Variantes en el nombre',
        help='Textos que, encontrados entre paréntesis en el nombre del '
             'cliente, significan esta categoría. Separados por coma y sin '
             'importar tildes ni mayúsculas. Ej.: CHUCHERO, CHUCHERA, '
             'CHUCHERIA')

    def _surtidora_variantes_lista(self):
        """Variantes normalizadas de esta categoría (incluye su nombre)."""
        self.ensure_one()
        crudas = (self.surtidora_variantes or '').split(',')
        variantes = {normalizar(v) for v in crudas if v.strip()}
        variantes.add(normalizar(self.name))
        return {v for v in variantes if v}


def normalizar(texto):
    """Sin tildes, sin espacios de sobra y en mayúsculas: así se comparan
    'Cafetería' y 'CAFETERIA'."""
    if not texto:
        return ''
    reemplazos = str.maketrans('ÁÉÍÓÚÜÑáéíóúüñ', 'AEIOUUNAEIOUUN')
    return ' '.join(texto.translate(reemplazos).upper().split())

# -*- coding: utf-8 -*-
"""Saca la categoría del nombre y la convierte en etiqueta (REQ-V28).

Conservador por diseño: solo toca lo que reconoce. Los 645 textos distintos
entre paréntesis mezclan categorías reales con nombres de dueños
("COLMADO X (JUAN CARLOS)") y apodos; lo que no está en la lista se deja
intacto en el nombre."""
import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..models.categoria import normalizar

_PARENTESIS = re.compile(r'\(([^()]*)\)')


class ExtraerCategoria(models.TransientModel):
    _name = 'surtidora.extraer.categoria'
    _description = 'Extraer categoría del nombre del cliente'

    aplicar_nombre = fields.Boolean(
        string='Quitar el texto del nombre', default=True,
        help='Además de poner la etiqueta, limpia el paréntesis del nombre. '
             'Sin esto, la categoría queda duplicada en los dos sitios.')
    solo_sin_etiqueta = fields.Boolean(
        string='Solo clientes sin etiqueta', default=True,
        help='No vuelve a tocar los que ya fueron clasificados.')
    vista_previa = fields.Text(string='Vista previa', readonly=True)
    revisado = fields.Boolean(string='Vista previa generada', default=False)

    # ------------------------------------------------------------------
    def _candidatos(self):
        """(partner, categoría, nombre limpio) de lo que SÍ se reconoce."""
        categorias = self.env['res.partner.category'].search([])
        indice = {}
        for categoria in categorias:
            for variante in categoria._surtidora_variantes_lista():
                indice.setdefault(variante, categoria)
        if not indice:
            return []
        dominio = [('name', 'like', '(')]
        if self.solo_sin_etiqueta:
            dominio.append(('category_id', '=', False))
        filas = []
        for partner in self.env['res.partner'].search(dominio):
            nombre = partner.name or ''
            encontradas, limpio = [], nombre
            for bruto in _PARENTESIS.findall(nombre):
                categoria = indice.get(normalizar(bruto))
                if categoria:
                    encontradas.append(categoria)
                    limpio = limpio.replace('(%s)' % bruto, '', 1)
            if encontradas:
                limpio = ' '.join(limpio.split()).strip(' -,')
                filas.append((partner, encontradas, limpio or nombre))
        return filas

    def action_vista_previa(self):
        self.ensure_one()
        filas = self._candidatos()
        if not filas:
            raise UserError(_(
                'No hay clientes por clasificar. Revise que las categorías '
                'tengan sus variantes escritas.'))
        conteo = {}
        muestras = []
        for partner, categorias, limpio in filas:
            for categoria in categorias:
                conteo[categoria.name] = conteo.get(categoria.name, 0) + 1
            if len(muestras) < 15:
                muestras.append('%s  →  %s  [%s]' % (
                    partner.name, limpio if self.aplicar_nombre else partner.name,
                    ', '.join(c.name for c in categorias)))
        lineas = [_('Se van a etiquetar %s clientes:') % len(filas), '']
        lineas += ['   %s: %s' % (n, c) for n, c in sorted(
            conteo.items(), key=lambda x: -x[1])]
        lineas += ['', _('Ejemplos:'), '']
        lineas += ['   ' + m for m in muestras]
        if len(filas) > 15:
            lineas.append('   ' + _('… y %s más.') % (len(filas) - 15))
        self.vista_previa = '\n'.join(lineas)
        self.revisado = True
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_aplicar(self):
        """Solo después de la vista previa: el nombre de 900 clientes no se
        toca a ciegas."""
        self.ensure_one()
        if not self.revisado:
            raise UserError(_('Genere primero la vista previa.'))
        filas = self._candidatos()
        if not filas:
            raise UserError(_('Ya no hay nada por clasificar.'))
        for partner, categorias, limpio in filas:
            vals = {'category_id': [(4, c.id) for c in categorias]}
            if self.aplicar_nombre and limpio != partner.name:
                vals['name'] = limpio
            partner.write(vals)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Clientes clasificados'),
                'message': _('%s clientes quedaron etiquetados.') % len(filas),
                'type': 'success',
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }

# -*- coding: utf-8 -*-
"""La escalera de precios de la casa, lista por lista.

Un solo margen para todas las listas no refleja cómo se vende aquí. Medido
sobre los 544 productos del catálogo que SÍ tienen escalera:

    Precio 1 (Mayor)     margen 23.3%   descuento por empaque 0.0%
    Precio 2             margen 45.8%   descuento por empaque 9.4%
    Precio 3             margen 46.2%   descuento por empaque 9.2%
    Precio 4 (Detalle)   margen 46.8%   descuento por empaque 9.2%

La lógica del negocio se lee sola en esos números: **Mayor YA es el precio
de volumen** —margen ajustado, y la caja no da descuento adicional porque
no hace falta—, mientras que las otras tres llevan casi el doble de margen
en la unidad suelta y sí premian llevarse el empaque completo.

Estos números NO se clavan en el código: se calculan desde el propio
catálogo con el botón «Calcular desde el catálogo» y después se ajustan a
mano. Son política de precios, y la política la pone la casa.
"""
import statistics

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class MargenLista(models.Model):
    _name = 'surtidora.margen.lista'
    _description = 'Margen sugerido por lista de precios'
    _order = 'pricelist_id'

    company_id = fields.Many2one(
        'res.company', required=True, index=True,
        default=lambda self: self.env.company)
    pricelist_id = fields.Many2one(
        'product.pricelist', string='Lista', required=True, ondelete='cascade')
    margen_pct = fields.Float(
        string='Margen en la unidad (%)',
        help='Sobre el costo CON ITBIS, para la unidad base del producto.')
    descuento_empaque_pct = fields.Float(
        string='Descuento por empaque (%)',
        help='Cuánto más barata sale la unidad al llevar el empaque completo, '
             'en ESTA lista. En Mayor suele ser 0: ese precio ya es el de '
             'volumen.')

    _sql_constraints = []  # v19: se declara con models.Constraint

    _unica_por_lista = models.Constraint(
        'UNIQUE(company_id, pricelist_id)',
        'Ya hay un margen sugerido para esa lista en esta compañía.')

    # ------------------------------------------------------------------
    @api.model
    def calcular_desde_catalogo(self):
        """Rellena la tabla con lo que el catálogo ya hace.

        Se miran SOLO los productos que tienen escalera —precios distintos
        entre listas—, que son los que están fijados con criterio. Los que
        tienen las cuatro listas iguales vienen así de la carga de ADG y
        promediarlos aplanaría justo lo que se quiere reproducir.
        """
        motor = self.env['surtidora.precios.motor']
        margenes, descuentos = motor.medir_escalera_del_catalogo()
        if not margenes:
            raise UserError(_(
                'No hay suficientes productos con precios distintos entre '
                'listas como para deducir una escalera. Teclee los márgenes '
                'a mano.'))
        for lista in self.env['product.pricelist'].browse(list(margenes)):
            fila = self.search([('company_id', '=', self.env.company.id),
                                ('pricelist_id', '=', lista.id)], limit=1)
            valores = {
                'margen_pct': round(margenes[lista.id], 1),
                'descuento_empaque_pct': round(descuentos.get(lista.id, 0.0), 1),
            }
            if fila:
                fila.write(valores)
            else:
                self.create(dict(valores, company_id=self.env.company.id,
                                 pricelist_id=lista.id))
        return True

    @api.model
    def para_lista(self, lista_id):
        """(margen, descuento) de una lista. Si no está en la tabla, cae a los
        valores generales de la compañía."""
        fila = self.search([('company_id', '=', self.env.company.id),
                            ('pricelist_id', '=', lista_id)], limit=1)
        if fila:
            return fila.margen_pct, fila.descuento_empaque_pct
        empresa = self.env.company
        return (empresa.surtidora_margen_unidad_pct,
                empresa.surtidora_descuento_empaque_pct)

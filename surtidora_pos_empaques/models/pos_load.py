# -*- coding: utf-8 -*-
"""Campos extra que el POS necesita para la venta por empaque.

El POS estándar ya carga product.uom (barcode por empaque) y uom.uom, pero sin
el factor de conversión ni la lista de empaques del producto. Se usan *args para
ser inmunes a cambios de firma entre builds de Odoo 19."""
from odoo import _, api, fields, models


class UomUom(models.Model):
    _inherit = 'uom.uom'

    @api.model
    def _load_pos_data_fields(self, *args, **kwargs):
        fields = super()._load_pos_data_fields(*args, **kwargs)
        return list(set(fields) | {'relative_factor', 'relative_uom_id'})


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    surtidora_caja_fraccionable = fields.Boolean(
        string='La caja se fracciona (¼/½/¾)',
        help='RB-09: en el POS la CAJA de este producto puede venderse en fracciones '
             '(¼, ½, ¾) a precio de caja. Solo se ofrecen fracciones que den unidades '
             'base enteras (caja de 24 → 6/12/18). La unidad base NUNCA se fracciona.')

    # Una casilla que no puede hacer nada y no lo dice es una trampa: el
    # usuario la marca, va al mostrador y no entiende por qué no pasa nada.
    # Pasó de verdad — un producto con la unidad base puesta en «Caja de 7»
    # y sin empaques: no hay nada que fraccionar, y nadie avisaba.
    surtidora_aviso_fraccion = fields.Char(
        compute='_compute_surtidora_aviso_fraccion')

    @api.depends('surtidora_caja_fraccionable', 'uom_ids', 'uom_id')
    def _compute_surtidora_aviso_fraccion(self):
        for producto in self:
            producto.surtidora_aviso_fraccion = (
                producto._surtidora_motivo_sin_fraccion()
                if producto.surtidora_caja_fraccionable else '')

    def _surtidora_motivo_sin_fraccion(self):
        """Por qué el mostrador no va a ofrecer fracciones, si es que no va."""
        self.ensure_one()
        base = self.uom_id
        empaques = [(u, u._compute_quantity(1.0, base, round=False))
                    for u in self.uom_ids] if base else []
        empaques = [(u, f) for u, f in empaques if f > 1]
        if not empaques:
            return _(
                'Este producto no tiene ningún empaque que fraccionar: su '
                'unidad base ya es «%s». Para vender media caja, la unidad '
                'base tiene que ser lo que se vende SUELTO (el paquete) y la '
                'caja un empaque aparte, en el campo Unidades.') % base.name
        divisibles = [u.name for u, f in empaques
                      if any(float(f * x).is_integer() for x in (0.25, 0.5, 0.75))]
        if not divisibles:
            nombres = ', '.join('%s (x%g)' % (u.name, f) for u, f in empaques)
            return _(
                'Ninguna fracción da unidades enteras en %s, así que el '
                'mostrador no ofrecerá ninguna. El fraccionamiento necesita un '
                'empaque divisible: una caja de 24 sí (¼=6, ½=12, ¾=18); una '
                'de 7 no, porque ni la mitad ni el cuarto son enteros.'
            ) % nombres
        return ''

    @api.model
    def _load_pos_data_fields(self, *args, **kwargs):
        fields = super()._load_pos_data_fields(*args, **kwargs)
        return list(set(fields) | {'uom_ids', 'surtidora_caja_fraccionable'})

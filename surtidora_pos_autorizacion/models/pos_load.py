# -*- coding: utf-8 -*-
"""Lo que el mostrador necesita tener a mano para decidir sin ir al servidor:
el COSTO del producto (para pintar en rojo la línea bajo costo al instante,
sin una llamada por cada tecla) y la TOLERANCIA de la compañía (para saber
cuánto se puede rebajar del precio de lista sin pedir PIN).

*args para ser inmunes a cambios de firma entre builds de Odoo 19 (mismo
patrón de pos_empaques)."""
from odoo import api, models


class ProductProduct(models.Model):
    _inherit = 'product.product'

    @api.model
    def _load_pos_data_fields(self, *args, **kwargs):
        fields = super()._load_pos_data_fields(*args, **kwargs)
        return list(set(fields) | {'standard_price'})


class ResCompany(models.Model):
    _inherit = 'res.company'

    @api.model
    def _load_pos_data_fields(self, *args, **kwargs):
        fields = super()._load_pos_data_fields(*args, **kwargs)
        return list(set(fields) | {'surtidora_tolerancia_precio_pct',
                                   'surtidora_permitir_bajo_costo'})

# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    surtidora_lista_precio_ficha = fields.Many2one(
        'product.pricelist', string='Lista que fija el Precio de venta',
        domain="[('company_id', 'in', [False, id])]",
        help='En Odoo lo que se cobra es el precio de la LISTA, no el campo '
             '«Precio de venta» de la ficha del producto: ese campo solo se '
             'usa cuando el producto no tiene regla en la lista activa. Para '
             'que la ficha no muestre un número que nadie cobra, al mantener '
             'precios se pone al día con la unidad base de esta lista.\n\n'
             'En la carga desde ADG el Precio de venta quedó igualado a '
             'Precio 4 (Detalle): de 558 productos con precios distintos por '
             'lista, coincide con Detalle en los 558 y con Mayor solo en 12.\n\n'
             'Vacío = no se toca el Precio de venta de la ficha.')

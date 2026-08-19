# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    # Cómo se sugiere un precio partiendo solo del costo. Los valores por
    # defecto NO son inventados: son las medianas del propio catálogo de
    # Surtidora (30,749 reglas de precio medidas el 19-ago-2026), así que un
    # producto nuevo sale coherente con los que ya se venden.
    surtidora_margen_unidad_pct = fields.Float(
        string='Margen sugerido en la unidad (%)', default=25.0,
        help='Margen sobre el costo CON ITBIS con el que se propone el precio '
             'de la unidad base. La mediana del catálogo es 24.6%; el cuartil '
             'bajo 16.8% y el alto 39.7%, así que es un punto de partida, no '
             'una ley: cada producto se ajusta después.')
    surtidora_descuento_empaque_pct = fields.Float(
        string='Descuento por empaque (%)', default=7.0,
        help='Cuánto más barata sale la unidad al llevar el empaque completo. '
             'Así es como se fijan los precios aquí: el 96% de los empaques '
             'del catálogo está puesto como un descuento sobre el precio '
             'unitario, no con un margen propio. La mediana es 6.9%.')
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

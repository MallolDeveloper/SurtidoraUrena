# -*- coding: utf-8 -*-
{
    'name': 'Surtidora - Último costo de compra',
    'summary': 'El «Último Costo» y su fecha en la ficha del producto, como en '
               'Costos y Precios de ADG: lo que se pagó la última vez, no el promedio.',
    'description': """
En ADG la ficha del producto muestra dos costos: el PROMEDIO (que Odoo tiene
como `standard_price`) y el ÚLTIMO, con la fecha de la última compra. Es el
costo neto por unidad base de la última línea de compra (`item_netcos`):
verificado con GAG004, 36.7335 el 28-ago-2026, Molinos Modernos.

No es un adorno. Medido en la base de ADG sobre los 2,868 productos con
venta en los últimos 12 meses: en 770 el último costo difiere del promedio
más de un 5 %, y en 702 de esos el último está POR ENCIMA. Con el promedio
como único termómetro, el margen se ve más sano de lo que deja la próxima
compra — justo donde Adelso decide el precio.

Odoo no lo tiene: `standard_price` es el promedio (o el estándar), y el
precio de la última orden vive repartido en las líneas de compra. Este
módulo:

- guarda `surtidora_ultimo_costo` y `surtidora_ultimo_costo_fecha` en la
  ficha, junto al costo, con quién se lo vendió;
- los alimenta al VALIDAR LA RECEPCIÓN (no al confirmar la orden: lo que
  cuenta es lo que entró), con el mismo costo que Odoo usa para valorar la
  entrada — `_get_stock_move_price_unit`: neto de ITBIS, con el descuento,
  por unidad base y a la tasa de la fecha si la compra fue en dólares;
- deja un método de carga (`surtidora_cargar_ultimo_costo`) para traer el
  dato de ADG el día del corte, sin pasar por la recepción.

Las devoluciones a suplidor y los ajustes de inventario NO lo tocan: solo
las entradas que vienen de una línea de compra.
    """,
    'version': '19.0.1.0.0',
    'category': 'Inventory/Purchase',
    'author': 'Mallol Consulting - Smerlin Ramos',
    'license': 'OPL-1',
    'depends': ['purchase_stock'],
    'data': [
        'views/product_template_views.xml',
    ],
    'installable': True,
    'application': False,
}

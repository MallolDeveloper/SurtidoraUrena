# -*- coding: utf-8 -*-
{
    'name': 'Surtidora - Alta Ágil de Productos',
    'summary': 'REQ-P06: dar de alta un producto completo en UNA pantalla — '
               'identidad, costo, precios por nivel y empaques con sus '
               'códigos de barras.',
    'description': """
"Llegan referencias cada semana" y hoy cada alta obliga a recorrer varias
pantallas: la ficha del producto, la pestaña de empaques, una regla de
precio por cada lista y por cada empaque (8 reglas para un producto con una
caja), la ficha del proveedor y la regla de reorden.

Esta pantalla lo hace todo de una sola vez, con la disposición del maestro
de productos de ADG (capturas 05/06/07):

- Identidad: referencia interna, nombre, categoría, proveedor y su código.
- Código de barras: el que trae el producto o uno interno generado
  (EAN-13 válido, se reutiliza el generador de surtidora_etiquetas).
- Costo SIN ITBIS y precios CON ITBIS (la dualidad de ADG).
- Precios por nivel con el % de margen en vivo: se teclea el precio y el
  margen se recalcula, o se pide un margen objetivo y la pantalla sugiere
  el precio redondeado a múltiplo de 5 (el 98% de los precios reales lo son).
- Empaques: unidad y factor (1 caja = 18 paquetes), su código de barras y
  el precio de la caja completa por cada nivel.
- Reorden mínimo/máximo, unidad de compra y la casilla de fraccionable.

El motor valida en el servidor (RB-08: ningún precio por debajo del costo)
y crea todo en una sola transacción: si algo falla, no queda un producto a
medio armar.
    """,
    'version': '19.0.1.0.0',
    'category': 'Inventory/Inventory',
    'author': 'Mallol Consulting - Smerlin Ramos',
    'license': 'OPL-1',
    # surtidora_etiquetas: generador de códigos internos EAN-13.
    # pos_empaques / sugerido: la casilla de fraccionable y la unidad de
    # compra son suyas — sin ellos la pantalla las omite en silencio.
    'depends': [
        'product', 'stock', 'purchase', 'account',
        'surtidora_etiquetas', 'surtidora_pos_empaques', 'surtidora_sugerido',
    ],
    'data': [
        'views/pantalla_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'surtidora_producto_alta/static/src/**/*',
        ],
    },
    'installable': True,
    'application': False,
}

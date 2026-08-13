# -*- coding: utf-8 -*-
{
    'name': 'Surtidora - Mantenimiento de Precios',
    'summary': 'Una pantalla para mantener los precios por lista y por empaque '
               'con el % de margen como termómetro — como Costos y Precios de ADG.',
    'description': """
Hallazgo de la auditoría (verificado contra la base de ADG): el PRECIO es el
maestro y el margen es el termómetro — Adelso fija el precio comercial redondo
mirando el % de beneficio, que varía por unidad y por lista. ADG no recalcula
precios al cambiar el costo: el repricing es manual, apoyado en ese %.

Esta pantalla replica ese flujo en una sola vista:
- Buscar el producto (código, nombre o barcode) con lista instantánea.
- Grid por LISTA (Precio 1-4) y por UNIDAD (base + empaques): costo con ITBIS,
  precio editable (el total del empaque, como lo dice el cliente: "la caja a
  880") y el % de margen recalculado EN VIVO mientras se teclea.
- Piso visual: margen < 5% en ámbar ("me salgo de mi punto de equilibrio"),
  bajo costo en rojo — y el guardado bloquea precios bajo costo (RB-08).
- Guardar escribe las MISMAS reglas de lista migradas (base min_qty=0 +
  empaque min_qty=factor) y deja rastro en el chatter del producto.

Fórmula (deducida de 3,000 precios reales de ADG):
    precio = costo sin ITBIS × factor × (1 + ITBIS) × (1 + margen)
    """,
    'version': '19.0.1.0.0',
    'category': 'Sales/Sales',
    'author': 'Mallol Consulting - Smerlin Ramos',
    'license': 'OPL-1',
    'depends': ['product', 'sale_management'],
    'data': [
        'views/pantalla_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'surtidora_precios/static/src/**/*',
        ],
    },
    'installable': True,
    'application': False,
}

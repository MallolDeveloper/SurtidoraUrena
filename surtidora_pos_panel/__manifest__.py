# -*- coding: utf-8 -*-
{
    'name': 'Surtidora - Panel de Mostrador (POS)',
    'summary': 'Todo en una pantalla: último precio al cliente, existencia por '
               'almacén y precios por empaque, siempre visibles en el POS.',
    'description': """
Criterio del cliente (jul-2026): todo se debe ver en UNA sola pantalla.

Panel lateral fijo en la pantalla de productos del POS que se actualiza al
tocar/escanear un producto:
- Últimas ventas de ESE producto a ESE cliente — fecha, cantidad y precio
  (REQ-V06 / RB-06: el anti-"a mí me lo pusiste a menos"). Incluye ventas
  de POS y de facturación backend.
- Precios por unidad/empaque con su equivalente (REQ-V03).
- Existencia disponible por almacén (REQ-V04).

Los datos los arma el servidor en una sola llamada; el panel solo pinta.
    """,
    'version': '19.0.1.0.0',
    'category': 'Sales/Point of Sale',
    'author': 'Mallol Consulting - Smerlin Ramos',
    'license': 'OPL-1',
    'depends': ['point_of_sale'],
    'assets': {
        'point_of_sale._assets_pos': [
            'surtidora_pos_panel/static/src/**/*',
        ],
    },
    'installable': True,
    'application': False,
}

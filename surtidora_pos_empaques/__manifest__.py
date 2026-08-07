# -*- coding: utf-8 -*-
{
    'name': 'Surtidora - Venta por Empaque en POS',
    'summary': 'Vender por caja/docena/fardo en el POS: selector de unidad al agregar '
               'el producto y escaneo del código de barras del empaque.',
    'description': """
El desarrollo clave de la arquitectura híbrida (POS para contado, 45% de las
líneas se venden en empaques — dato real de la operación):

- Al tocar un producto con empaques, el POS pregunta la unidad mostrando el
  precio de cada una (Paquete 55.00 / Caja de 18 — 880.00) — REQ-V05/V24.
- Escanear el código de barras del EMPAQUE agrega la cantidad del factor con
  su precio correcto (el POS estándar lo agregaba como 1 unidad base) — REQ-P02.
- El precio del empaque sale de las listas de precios (regla por cantidad) ya
  migradas — sin lógica de precios duplicada.

Notas: la línea queda expresada en unidad base (18 Paquete a 48.89 = 880), que
es como el POS de Odoo modela internamente; el ticket cuadra al centavo.
    """,
    'version': '19.0.1.2.0',
    'category': 'Sales/Point of Sale',
    'author': 'Mallol Consulting - Smerlin Ramos',
    'license': 'OPL-1',
    'depends': ['point_of_sale'],
    'data': [
        'views/product_template_views.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'surtidora_pos_empaques/static/src/**/*',
        ],
    },
    'installable': True,
    'application': False,
}

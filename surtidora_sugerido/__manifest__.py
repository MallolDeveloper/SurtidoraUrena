# -*- coding: utf-8 -*-
{
    'name': 'Surtidora - Sugerido de Compras',
    'summary': 'Sugerido por rotación de ventas en unidad de compra — '
               'evolución del POC de Mallol contra la pantalla real de ADG.',
    'description': """
Fase B (REQ-C01→C04, C07). Iteración 1 — el motor:
- Cálculo POR LOTES (aguanta el catálogo completo; el POC era por producto).
- Todo en la UNIDAD DE COMPRA del producto (caja/fardo) — REQ-C03.
- Conversión correcta de ventas en empaques (una venta de "1 caja" no es 1 und).
- Rango de fechas de análisis + días a abastecer, como la pantalla de ADG.
- Referencia del suplidor en el grid y en la OC — REQ-C04.
- OC temporal (borrador marcado) vs firme (confirmada) — REQ-C07.
- Botones "Ordenar lo sugerido" / "Quitar cantidades" (botonera de ADG).
- Costos SIN ITBIS (como los presenta el sugerido del cliente).
- Multi-company desde el día 1.

Iteración 2: paneles de contexto (histórico mensual compras vs ventas,
última compra multi-suplidor, info del producto). Iteración 3: impresión
en 2 copias (vendedor/almacén).
    """,
    'version': '19.0.1.0.0',
    'category': 'Inventory/Purchase',
    'author': 'Mallol Consulting - Smerlin Ramos',
    'license': 'OPL-1',
    'depends': ['purchase', 'sale_management', 'stock'],
    'data': [
        'security/ir.model.access.csv',
        'wizards/sugerido_views.xml',
        'views/purchase_order_views.xml',
        'views/product_template_views.xml',
    ],
    'installable': True,
    'application': True,
}

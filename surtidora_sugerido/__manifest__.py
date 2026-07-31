# -*- coding: utf-8 -*-
{
    'name': 'Surtidora - Sugerido de Compras',
    'summary': 'Sugerido por rotación de ventas en unidad de compra — evolución '
               'del POC de Mallol contra la pantalla real de ADG (Fase B).',
    'description': """
Iteración 1 (REQ-C01→C04, C07):
- Motor de cálculo POR LOTES separado de la pantalla (aguanta el catálogo real;
  el POC hacía una consulta por producto).
- Todo en la UNIDAD DE COMPRA del producto (REQ-C03) — como la pantalla de ADG.
- Rango de fechas de análisis (no "días de historial").
- Columnas del as-is: últ. compra, salidas del período, ref. del suplidor.
- OC temporal (borrador marcado, negociación abierta) vs firme (confirmada).
- Costos SIN ITBIS (dualidad de ADG) y multi-company desde el día 1.

Iteración 2: paneles de contexto (histórico mensual compras vs ventas,
multi-suplidor). Iteración 3: impresión en 2 copias.
    """,
    'version': '19.0.2.0.1',
    'category': 'Inventory/Purchase',
    'author': 'Mallol Consulting - Smerlin Ramos',
    'license': 'OPL-1',
    'depends': ['purchase', 'sale_management', 'stock'],
    'data': [
        'security/ir.model.access.csv',
        'views/product_template_views.xml',
        'views/purchase_order_views.xml',
        'wizards/sugerido_views.xml',
        'wizards/detalle_views.xml',
    ],
    'installable': True,
    'application': True,
}

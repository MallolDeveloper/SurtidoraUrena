# -*- coding: utf-8 -*-
{
    'name': 'Surtidora - Spike Pantalla de Negociación (Backend)',
    'summary': 'SPIKE Fase C (variante backend): botón de negociación en la línea de venta '
               'con precios por empaque, existencia por almacén e historial del cliente.',
    'description': """
Prototipo desechable para la decisión POS vs backend (Levantamiento §3.3).
Replica los elementos de la "pantalla de negociación" de ADGSystems:
- Precios por empaque (paquete Y caja simultáneos, con equivalente por unidad base) — REQ-V03
- Existencia por almacén — REQ-V04
- Últimas 2 compras del cliente para el producto — REQ-V06 / RB-06
No es la pantalla definitiva (esa se construye tras la decisión del spike).
    """,
    'version': '19.0.1.0.0',
    'category': 'Sales',
    'author': 'Mallol Consulting - Smerlin Ramos',
    'license': 'OPL-1',
    'depends': ['sale_management', 'stock'],
    'data': [
        'security/ir.model.access.csv',
        'views/negociacion_wizard_views.xml',
        'views/sale_order_views.xml',
    ],
    'installable': True,
    'application': False,
}

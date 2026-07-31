# Copyright 2026 Mallol Consulting
# License LGPL-3
{
    "name": "Mallol Sugerido de Compras",
    "summary": "Sugerido de compras por rotación de ventas (días de cobertura)",
    "description": """
POC: replica el 'Sugerido de Compras por rotación de ventas' de sistemas
legacy. Calcula por producto la velocidad de venta (ventas/día), la cantidad
necesaria para X días de abastecimiento, descuenta existencia y órdenes de
compra pendientes, y sugiere la cantidad a ordenar. Genera la Orden de Compra.
""",
    "category": "Inventory/Purchase",
    "version": "19.0.1.0.1",
    "author": "Mallol Consulting",
    "website": "https://mallolconsulting.com",
    "license": "LGPL-3",
    "depends": ["purchase", "sale_management", "stock"],
    "data": [
        "security/ir.model.access.csv",
        "views/sugerido_views.xml",
    ],
    "post_init_hook": "post_init_hook",
    "application": True,
    "installable": True,
}

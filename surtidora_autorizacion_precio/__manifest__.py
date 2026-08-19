# -*- coding: utf-8 -*-
{
    'name': 'Surtidora - Autorización de Precios',
    'summary': 'Cambio de precio con clave de supervisor (PIN) y bloqueo de venta '
               'bajo costo, con registro de auditoría.',
    'description': """
Control de precios en ventas (Levantamiento Surtidora Ureña):
- RB-01 / REQ-V07: vender por debajo del precio de lista exige autorización de un
  supervisor, que la aprueba con su PIN en la estación del vendedor.
- RB-08 / REQ-V08: la venta por debajo del costo queda bloqueada para TODOS los
  usuarios sin excepción (desactivable solo por parámetro de compañía).
- REQ-V27: doble autorización con PIN oculto (petición histórica del cliente).
- Auditoría: cada autorización queda registrada (quién, qué, cuánto, cuándo).

El núcleo (reglas + PIN + auditoría) es independiente de la pantalla de venta:
la pantalla definitiva de la Fase C lo reutiliza tal cual.
    """,
    'version': '19.0.5.0.0',
    'category': 'Sales',
    'author': 'Mallol Consulting - Smerlin Ramos',
    'license': 'OPL-1',
    'depends': ['sale_management'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/motivos_data.xml',
        'views/autorizacion_views.xml',
        'views/sale_order_views.xml',
        'views/res_company_views.xml',
        'views/res_users_views.xml',
        'wizards/autorizar_precio_views.xml',
    ],
    'installable': True,
    'application': False,
}

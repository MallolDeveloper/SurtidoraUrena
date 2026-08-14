# -*- coding: utf-8 -*-
{
    'name': 'Surtidora - Ajustes de Inventario con Motivo',
    'summary': 'REQ-I04: ningún ajuste de existencia sin motivo del catálogo '
               'y clave de supervisor, con bitácora a prueba de borrado.',
    'description': """
Un ajuste cambia la existencia sin comprar ni vender: es la puerta por
donde se puede sacar mercancía del sistema sin dejar rastro. Hoy en ADG el
ajuste NO pide motivo — el campo de concepto viene vacío en 295 de los
últimos 300 ajustes registrados.

Este módulo aplica al inventario el mismo control que ya existe para los
precios:

- Motivo obligatorio de un catálogo (no texto libre), para poder analizar
  después qué está causando las diferencias.
- Clave de un supervisor autorizado, con el resumen de lo que se va a
  ajustar A LA VISTA antes de teclearla: qué producto, cuánto sube o baja
  y cuánto vale esa diferencia al costo.
- Bitácora con quién ajustó, quién autorizó, la cantidad de antes y la de
  después. Sin permiso de edición ni de borrado para nadie.

La compuerta está en el punto por donde pasan las dos vías de la pantalla
de inventario físico: el botón «Aplicar» de cada línea y «Aplicar todo».

Reutiliza el PIN y el grupo de supervisores de surtidora_autorizacion_precio.
    """,
    'version': '19.0.1.0.0',
    'category': 'Inventory/Inventory',
    'author': 'Mallol Consulting - Smerlin Ramos',
    'license': 'OPL-1',
    'depends': ['stock', 'account', 'surtidora_autorizacion_precio'],
    'data': [
        'security/ir.model.access.csv',
        'security/ir_rule.xml',
        'data/motivos_ajuste_data.xml',
        'views/ajuste_views.xml',
    ],
    'installable': True,
    'application': False,
}

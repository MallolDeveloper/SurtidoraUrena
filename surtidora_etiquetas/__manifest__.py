# -*- coding: utf-8 -*-
{
    'name': 'Surtidora - Códigos Internos y Etiquetas',
    'summary': 'Genera código de barras interno (EAN-13 válido) para productos sin '
               'código y las etiquetas por producto y por empaque con precio.',
    'description': """
REQ-P04 / REQ-I08 del levantamiento:

- Productos que llegan sin código de barras (sacos, cajas genéricas) reciben
  un código interno: EAN-13 válido con prefijo 20 (rango de uso interno GS1),
  generado por secuencia con dígito verificador correcto.
- Asistente "Imprimir etiquetas": una etiqueta por unidad — la base Y cada
  empaque — con su código de barras y su precio según la lista elegida
  (formato 57x32mm, rollo Zebra típico; el ZPL exacto se ajustará cuando la
  sesión de inventario confirme el modelo de impresora).
    """,
    'version': '19.0.1.0.0',
    'category': 'Inventory',
    'author': 'Mallol Consulting - Smerlin Ramos',
    'license': 'OPL-1',
    'depends': ['product'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_sequence.xml',
        'report/etiquetas_report.xml',
        'views/product_template_views.xml',
        'wizards/etiquetas_wizard_views.xml',
    ],
    'installable': True,
    'application': False,
}

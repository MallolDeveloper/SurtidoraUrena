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

LA SIMBOLOGÍA SALE DEL CÓDIGO, NO AL REVÉS
------------------------------------------
El catálogo no es todo EAN-13. De 3,704 códigos en ficha:

    2,910  EAN-13 válido (355 internos nuestros, prefijo 20)
      706  UPC-A de 12 dígitos — el estándar americano
       24  EAN-8 (22 de ellos válidos: cigarrillos, cervezas)
       21  ITF-14, código de embalaje
       43  dígito verificador malo o largo inválido

Por eso el reporte pide `barcode_type=auto` y deja que Odoo elija por el
largo: 13 -> EAN-13, 8 -> EAN-8, el resto -> Code128, que encoda el número
literal. Si el dígito verificador no cuadra, Odoo también cae a Code128 solo.

**NO cambiar `auto` por `UPCA` para los de 12 dígitos.** Parece lo correcto y
no lo es: Odoo convierte UPCA a EAN-13 ANTEPONIENDO UN CERO, así que
imprimiría 0028661704211 — trece dígitos que no están en ninguna ficha y que
al escanear no encuentran nada. Comprobado comparando las imágenes byte a
byte contra las de Code128.
    """,
    'version': '19.0.1.1.0',
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

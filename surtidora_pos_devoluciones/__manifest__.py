# -*- coding: utf-8 -*-
{
    'name': 'Surtidora - Devoluciones con motivo en el POS',
    'summary': 'REQ-V18: toda devolución del mostrador registra su motivo '
               '(catálogo real de ADG) y lo imprime en el recibo.',
    'description': """
En ADG el tipo de devolución es OBLIGATORIO (cia_setup.inv_tipodev_oblig=True)
y se elige de un catálogo. Este módulo replica ese control en el POS:

- Catálogo "Motivos de devolución" precargado con los motivos reales de ADG
  (sis_tipos_devoluciones), ordenados por frecuencia de uso real de los
  últimos 12 meses (~7 devoluciones/día). Los 7 motivos "Fulana se equivocó
  al digitar" de ADG colapsan en UN "Error de digitación": en Odoo la orden
  ya registra quién la digitó.
- Al tocar "Reembolsar" en el POS se pide el motivo; la compuerta final al
  validar la orden vuelve a exigirlo si falta (popup cancelado, F5 a mitad,
  línea negativa tecleada a mano — la "devolución sin factura" de ADG — o
  preset de devolución). Sin motivo no hay devolución, igual que en ADG.
- El motivo viaja con la orden (sync nativo), queda visible en el backend
  (formulario, filtros "Devoluciones" / "Devoluciones sin motivo" y agrupado
  por motivo) y se imprime en el recibo. Solo el encargado corrige un motivo
  equivocado; el botón "Return Products" del backend queda para encargados
  (no pasa por el candado del POS).

El pago de la devolución ya lo cubre surtidora_pos_credito: el método
"Bono / Nota de Crédito" emite el bono nominativo (política 12.4).

NO se rutea mercancía al almacén de Dañados automáticamente: en ADG el
almacén de la devolución va en blanco y dañados/vencidos son ~12 casos al
año — eso se resuelve con un traspaso interno manual.
    """,
    'version': '19.0.2.0.1',
    'category': 'Sales/Point of Sale',
    'author': 'Mallol Consulting - Smerlin Ramos',
    'license': 'OPL-1',
    'depends': ['point_of_sale'],
    'data': [
        'security/ir.model.access.csv',
        'data/motivos_devolucion_data.xml',
        'views/motivo_devolucion_views.xml',
        'views/pos_order_views.xml',
        'views/autorizacion_devolucion_views.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'surtidora_pos_devoluciones/static/src/**/*',
        ],
    },
    'installable': True,
    'application': False,
}

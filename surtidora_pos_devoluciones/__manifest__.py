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

La devolución en EFECTIVO tiene tope: lo que la venta dejó en efectivo, NETO
del vuelto (recibido − vuelto), menos lo ya devuelto. Odoo 19 guarda el
vuelto como un pago negativo en efectivo (`is_change`); contarlo como
devolución, o ignorarlo en lo pagado, dejaba devolver el billete entero
—y con pago mixto, en efectivo lo que se cobró con tarjeta.

El pago de la devolución ya lo cubre surtidora_pos_credito: el método
"Bono / Nota de Crédito" emite el bono nominativo (política 12.4).

- El botón "Reembolsar" del core se planta EN SILENCIO cuando no se tecleó
  cantidad en ninguna línea (`if (!order || !this.getHasItemsToRefund())
  return;`), y solo se autocompleta si la venta tiene un artículo de una
  unidad — así que el fallo se siente aleatorio. Ahora avisa qué falta, y
  distingue "teclee la cantidad" de "esta venta ya se devolvió completa",
  que manda a la cajera a sitios opuestos.

Devolución sin factura FACTURADA (cliente empresa, que Odoo 19 factura
solo, y toda venta cuando entre el módulo fiscal): Odoo decide el documento
solo por "is_refund", que marcan el botón "Reembolsar" y la devolución del
backend. La línea
negativa tecleada a mano salía como FACTURA de total positivo que le cobraba
al cliente lo devuelto (−100 en efectivo = el cliente quedaba debiendo 200).
Ahora una orden con total negativo sale como NOTA DE CRÉDITO (RINV), con las
mismas líneas: pagada en efectivo queda conciliada, pagada con bono queda
como saldo a favor. La mixta con total ≥ 0 sigue siendo factura. No
cambian el inventario, el margen ni los reportes del POS; en contabilidad
la devolución aparece como nota de crédito, que es lo correcto.
Con l10n_do_accounting la nota de crédito exigirá el NCF modificado: lo
pondrá el futuro surtidora_pos_fiscal con el NCF de ADG de la venta de
origen. Por eso l10n_do_accounting NO debe activarse en producción antes
de surtidora_pos_fiscal: sin el NCF modificado, estas devoluciones no
sincronizan. Las mixtas (factura o nota con líneas negativas) también
quedan como caso de ese módulo. En el asistente «Facturar» del backend,
facturar una devolución sin factura aparte de las ventas.

NO se rutea mercancía al almacén de Dañados automáticamente: en ADG el
almacén de la devolución va en blanco y dañados/vencidos son ~12 casos al
año — eso se resuelve con un traspaso interno manual.
    """,
    'version': '19.0.2.2.4',
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

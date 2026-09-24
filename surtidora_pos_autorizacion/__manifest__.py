# -*- coding: utf-8 -*-
{
    'name': 'Surtidora - Bajo Costo en el POS',
    'summary': 'Bloqueo de venta por debajo del costo en el mostrador, con '
               'excepción autorizada (motivo + PIN + doble confirmación).',
    'description': """
Punto 5 de la reunión con el cliente (7-ago-2026):

- La línea vendida por debajo del costo se marca EN ROJO al instante, mientras
  el cajero teclea (el aviso destacado que pidió Adelso).
- Al COBRAR, la venta queda bloqueada con un aviso rojo. La vía de excepción
  —mercancía próxima a vencer que hoy rematan a mitad de precio en vez de
  botarla— exige: motivo del catálogo + PIN de supervisor + doble
  confirmación ("¿está seguro?"), y queda auditada con origen Mostrador.
- El PIN se valida en el SERVIDOR (nunca viaja el hash al navegador) y la
  auditoría reutiliza surtidora.autorizacion.precio — la misma bitácora que
  las cotizaciones del backend.

La comparación es precio tecleado vs costo del producto (sin ITBIS), la misma
regla RB-08 ya validada en el backend.

- RB-01: al COBRAR, las líneas por debajo del precio de lista (menos la
  tolerancia de la compañía) piden motivo del catálogo + PIN de supervisor,
  sin doble confirmación, y quedan en la misma bitácora.
- Una fracción de empaque (¼/½/¾, RB-09 de surtidora_pos_empaques) se
  compara contra la tarifa del empaque completo, que es su precio legítimo.

- Cotización cobrada en caja (pos_sale, P19): la autorización de la caja
  cubre la línea de la cotización que se cobró con ella, y el candado de
  precios ya no tumba la venta en la confirmación que pos_sale hace al
  guardar el cobro (otro error ahí, como los permisos de la cajera sobre la
  orden de venta, sí la tumba: ver models/sale_order.py). Lo que
  quede sin cubrir (también lo que nunca pasó por la caja, porque pos_sale
  confirma la cotización entera) queda marcado, con una nota en la orden, y
  no se entrega ni se factura desde oficina hasta que se autorice o se
  corrija.
    """,
    'version': '19.0.2.1.0',
    'category': 'Sales/Point of Sale',
    'author': 'Mallol Consulting - Smerlin Ramos',
    'license': 'OPL-1',
    # pos_sale: la cotización cobrada en caja (P19). Ya estaba instalado por
    # surtidora_pos_tirilla, que también depende de él. sale_stock: el freno
    # de la entrega mira la línea de venta del movimiento (instalado en Dev).
    'depends': ['point_of_sale', 'pos_sale', 'sale_stock',
                'surtidora_autorizacion_precio'],
    'assets': {
        'point_of_sale._assets_pos': [
            'surtidora_pos_autorizacion/static/src/**/*',
        ],
    },
    'installable': True,
    'application': False,
}

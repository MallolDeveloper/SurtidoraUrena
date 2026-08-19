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
    """,
    'version': '19.0.1.4.0',
    'category': 'Sales/Point of Sale',
    'author': 'Mallol Consulting - Smerlin Ramos',
    'license': 'OPL-1',
    'depends': ['point_of_sale', 'surtidora_autorizacion_precio'],
    'assets': {
        'point_of_sale._assets_pos': [
            'surtidora_pos_autorizacion/static/src/**/*',
        ],
    },
    'installable': True,
    'application': False,
}

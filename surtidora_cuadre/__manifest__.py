# -*- coding: utf-8 -*-
{
    'name': 'Surtidora - Cuadre de Caja',
    'summary': 'REQ-V17: la hoja de cuadre imprimible del cierre de caja — '
               'declarado vs calculado por método, arqueo por denominación '
               'y diferencia, como el cuadre de ADG.',
    'description': """
El cuadre de ADG compara lo DECLARADO por la cajera contra lo CALCULADO por
el sistema (patrón cuad_X / cuad_Xc de inv_cuadres) con arqueo por
denominación. Datos reales de 12 meses: ~5.4 cuadres/día en 6 cajas y 1,470
cuadres con diferencia (promedio RD$594) — la diferencia visible es el
control central.

Este módulo lo replica sobre la sesión del POS:

- Reporte PDF "Cuadre de Caja" (botón en la sesión y menú Imprimir):
  cabecera con caja/cajero/apertura/cierre, resumen por forma de pago,
  detalle del efectivo (fondo + ventas − devoluciones en efectivo +
  entradas − salidas = esperado vs contado, DIFERENCIA destacada), arqueo
  por denominación, devoluciones (por motivo si el módulo de devoluciones
  está instalado, y por forma de pago), entradas y salidas de caja, y
  líneas de firma Entregado/Revisado.
- La devolución en EFECTIVO lleva su propia línea. Antes se restaba dentro
  de «Ventas en efectivo» (`amount:sum` cancela los pagos negativos), así
  que el total salía correcto pero la salida no se veía: la cajera la leía
  en el bloque de Devoluciones y la restaba otra vez a ojo. Ese bloque
  además mezclaba efectivo con bonos —que no tocan la gaveta—, por lo que
  no cuadraba contra nada; ahora se desglosa por forma de pago y la fila de
  efectivo da exactamente la misma cifra que el bloque del efectivo.
- El conteo por denominación del popup de cierre se PERSISTE estructurado
  (campo JSON en la sesión): el POS nativo solo lo dejaba como texto en las
  notas de cierre, imposible de tabular en un reporte.

El motor arma todos los datos (surtidora_datos_cuadre); la plantilla solo
pinta — mismo estándar motor/pantalla del resto de módulos Surtidora.
    """,
    'version': '19.0.1.1.0',
    'category': 'Sales/Point of Sale',
    'author': 'Mallol Consulting - Smerlin Ramos',
    'license': 'OPL-1',
    'depends': ['point_of_sale'],
    'data': [
        'report/cuadre_report.xml',
        'views/pos_session_views.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'surtidora_cuadre/static/src/**/*',
        ],
    },
    'installable': True,
    'application': False,
}

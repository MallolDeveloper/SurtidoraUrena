# -*- coding: utf-8 -*-
{
    'name': 'Surtidora - Tirilla del mostrador',
    'summary': 'REQ-V16: el recibo del POS con formato de tirilla dominicana '
               '— encabezado fiscal y pie Caja | Cajero | Cuadre No.',
    'description': """
La factura del mostrador es una tirilla térmica de 80mm (EPSON TM-T88IV),
no una hoja. Este módulo ajusta el recibo nativo del POS al formato que el
cliente conoce (captura 20 de ADG):

- Encabezado fiscal ARRIBA: razón social, RNC, dirección y teléfono (el
  recibo nativo los ponía al pie; la tirilla dominicana lleva el RNC en la
  cabeza). El pie ADG "Caja / Cajero / Cuadre No." REEMPLAZA ese bloque
  nativo — sin duplicados y el pie queda al final, como en la captura 20.
- "Devuelta" en vez de "Cambio" (así se dice en el mostrador).
- Debajo de cada línea, SOLO el TIPO de empaque —CAJA, PAQUETE, DOCENA,
  UNIDAD— a tamaño de línea, sin el precio por empaque y sin el "de 60
  (Paquete)". La tirilla la lee el despachador y lo que tiene que ver de un
  vistazo es qué empaque va; cuántos trae ya lo dice el nombre del producto
  (11-sep-2026, con la tirilla impresa al lado de la de ADG). Cada tipo lleva
  su estilo como código visual: *CAJA en negrita con asterisco, DOCENA en
  cursiva, PAQUETE y el resto en letra normal (tirilla.scss). Qué empaque rotular lo decide
  surtidora_pos_empaques.
- El "Atendido por" se retira de las ventas (el cajero va al pie), pero se
  CONSERVA en el comprobante de entrada/salida de efectivo — era su única
  mención del responsable.
- Los datos del pie viajan DENTRO de la orden (campos related resueltos en
  servidor): la reimpresión de una venta de otra sesión u otra caja imprime
  el cuadre/caja/cajero VERDADEROS de aquella venta — el cliente web pisa
  session_id/config_id de las órdenes recargadas con los actuales.
- Al confirmar la apertura de caja se refresca el nombre real de la sesión
  (el servidor lo asigna en ese momento; sin el refresh, todas las tirillas
  del día dirían "Cuadre No.: /" hasta un F5).

Los datos de la compañía se cargan en la ficha (RNC 130728526 tomado de la
base real de ADG). El NCF/e-CF en la tirilla queda para la sesión fiscal —
depende del proveedor de e-CF, aún sin identificar.

La conexión física con la impresora (ePOS/IoT Box) es configuración del
puesto en sitio, no de este módulo.
    """,
    'version': '19.0.1.2.1',
    'category': 'Sales/Point of Sale',
    'author': 'Mallol Consulting - Smerlin Ramos',
    'license': 'OPL-1',
    # surtidora_pos_empaques va antes: su parche decide en qué empaque se
    # presenta la línea, y el de aquí lo lee (unidad_linea.js).
    'depends': ['point_of_sale', 'surtidora_pos_empaques'],
    'assets': {
        'point_of_sale._assets_pos': [
            'surtidora_pos_tirilla/static/src/**/*',
        ],
    },
    'installable': True,
    'application': False,
}

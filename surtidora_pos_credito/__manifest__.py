# -*- coding: utf-8 -*-
{
    'name': 'Surtidora - Crédito en el POS',
    'summary': 'Venta a crédito desde el mostrador (cuenta del cliente) con '
               'candado de límite de crédito — como la condición crédito de ADG.',
    'description': """
En ADG contado y crédito salían de la MISMA pantalla de facturación. Este
módulo lo replica en el POS ("una sola pantalla"):

- Método de pago "Crédito (Cuenta Cliente)" — el monto no entra a caja: queda
  cargado a la cuenta por cobrar del cliente (pay_later nativo de Odoo).
- Candado de crédito (el servidor decide, el POS solo pinta el mensaje):
  * Sin cliente seleccionado → no hay crédito.
  * Cliente sin límite de crédito autorizado → bloqueado (en ADG solo ~440
    clientes tienen crédito; aquí el límite en la ficha ES la autorización).
  * Balance pendiente + esta venta > límite → bloqueado, mostrando el
    disponible real.
- Doble verificación: al tocar el método de pago (aviso temprano) y al validar
  la orden (compuerta final — evita colar el crédito editando montos).

La instalación agrega el método a las cajas existentes y activa la opción
de límite de crédito por cliente en la compañía.

El mayoreo con negociación formal (cotización + botón de negociación) sigue
por el backend de Ventas.
    """,
    'version': '19.0.1.0.1',
    'category': 'Sales/Point of Sale',
    'author': 'Mallol Consulting - Smerlin Ramos',
    'license': 'OPL-1',
    'depends': ['point_of_sale'],
    'data': [
        'data/payment_method_data.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'surtidora_pos_credito/static/src/**/*',
        ],
    },
    'post_init_hook': 'configurar_credito_pos',
    'installable': True,
    'application': False,
}

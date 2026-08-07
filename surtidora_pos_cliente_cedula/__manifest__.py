# -*- coding: utf-8 -*-
{
    'name': 'Surtidora - Cliente por Cédula/Tarjeta en POS',
    'summary': 'Escanear la cédula (o tarjeta de lealtad) del cliente en el POS '
               'lo identifica y lo asigna a la orden.',
    'description': """
REQ-V29 del levantamiento: en ADGSystems la cajera pasa el código de barras del
reverso de la cédula (o la tarjeta emitida) por el lente y el sistema identifica
al cliente preferencial. Réplica en Odoo:

- El código se guarda en la ficha del cliente (campo "Código de barras",
  visible junto a las etiquetas).
- En el POS, cualquier código escaneado que NO sea un producto se busca como
  cliente (primero local, luego en el servidor) y se asigna a la orden.
- Es la puerta de entrada de los surti-puntos: con el cliente asignado, el
  programa de lealtad acumula automáticamente.

Sin reglas de nomenclatura frágiles: funciona con cédula, tarjeta o cualquier
código que se registre al cliente.
    """,
    'version': '19.0.1.1.0',
    'category': 'Sales/Point of Sale',
    'author': 'Mallol Consulting - Smerlin Ramos',
    'license': 'OPL-1',
    'depends': ['point_of_sale'],
    'data': [
        'views/res_partner_views.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'surtidora_pos_cliente_cedula/static/src/**/*',
        ],
    },
    'installable': True,
    'application': False,
}

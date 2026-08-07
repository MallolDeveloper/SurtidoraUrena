# -*- coding: utf-8 -*-
{
    'name': 'Surtidora - Vista de lista en el POS',
    'summary': 'Los productos en lista con su precio, como en ADG, en vez de '
               'mosaico de fotos que el catálogo no tiene.',
    'description': """
El catálogo de Surtidora casi no tiene fotos: el mosaico del POS muestra
cuadros grises con el nombre recortado y sin precio.

Este módulo agrega un botón para alternar entre mosaico y LISTA:
- Una fila por producto, a lo ancho de la pantalla.
- Referencia interna + nombre completo (sin recortar) + PRECIO a la derecha.
- Sin la foto de relleno, que en este catálogo no aporta nada.

La elección se recuerda por equipo (queda guardada en el navegador de esa
estación), así cada puesto trabaja como prefiera.
    """,
    'version': '19.0.1.1.0',
    'category': 'Sales/Point of Sale',
    'author': 'Mallol Consulting - Smerlin Ramos',
    'license': 'OPL-1',
    'depends': ['point_of_sale'],
    'assets': {
        'point_of_sale._assets_pos': [
            'surtidora_pos_lista/static/src/**/*',
        ],
    },
    'installable': True,
    'application': False,
}

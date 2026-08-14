# -*- coding: utf-8 -*-
{
    'name': 'Surtidora - Categoría de cliente como etiqueta',
    'summary': 'REQ-V28: la categoría deja de vivir entre paréntesis dentro '
               'del nombre y pasa a ser una etiqueta buscable.',
    'description': """
En ADG el catálogo de categorías de cliente está VACÍO: la única forma de
saber que alguien es chuchero o colmadero es el paréntesis dentro de su
nombre ("RICARDO ESPINAL (CHUCHERO)"). Ese apaño es justo lo que el
requerimiento pide eliminar.

Odoo ya trae etiquetas de contacto buscables y filtrables. Lo que faltaba
es el vocabulario real del cliente y una forma segura de migrar el dato:

- Las 10 categorías reales, medidas en la base de ADG, cada una con las
  variantes con que aparecen escritas (CHUCHERO, CHUCHERA, CHUCHERIA…).
  Las variantes se editan desde la ficha de la etiqueta: la lista es del
  cliente y va a cambiar.
- Un asistente que recorre los clientes, reconoce la categoría dentro del
  paréntesis, la pone como etiqueta y limpia el nombre — con VISTA PREVIA
  obligatoria antes de tocar nada.

Conservador a propósito: de los 645 textos distintos que hay entre
paréntesis, la mayoría son nombres de dueños y apodos ("COLMADO X (JUAN
CARLOS)"). Solo se toca lo que coincide con una categoría conocida; el
resto se deja intacto. Con las 10 categorías actuales quedan clasificados
unos 900 clientes.
    """,
    'version': '19.0.1.0.0',
    'category': 'Sales/Sales',
    'author': 'Mallol Consulting - Smerlin Ramos',
    'license': 'OPL-1',
    'depends': ['sale', 'sales_team'],
    'data': [
        'security/ir.model.access.csv',
        'data/categorias_data.xml',
        'views/categoria_views.xml',
    ],
    'installable': True,
    'application': False,
}

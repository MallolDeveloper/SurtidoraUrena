# -*- coding: utf-8 -*-
{
    'name': 'Surtidora - Mantenimiento de Precios',
    'summary': 'Botón en la ficha del producto para fijar precios por lista y '
               'por empaque con el % de margen — como Costos y Precios de ADG.',
    'description': """
Hallazgo de la auditoría (verificado contra la base de ADG): el PRECIO es el
maestro y el margen es el termómetro — Adelso fija el precio comercial redondo
mirando el % de beneficio, que varía por unidad y por lista. ADG no recalcula
precios al cambiar el costo: el repricing es manual, apoyado en ese %.

Odoo no tiene campo de margen en ningún sitio, y guarda el precio del empaque
POR UNIDAD BASE (la caja de 18 a 880 se almacena como 48.8889). Este módulo
cubre solo esos dos huecos, SIN reemplazar nada del estándar: agrega un botón
"Precios y margen" a la ficha nativa del producto, que abre un asistente con:

- una fila por LISTA (Precio 1-4) y por UNIDAD (base + empaques), con el costo
  con ITBIS, el precio actual y el % de margen;
- "Sugerir precios": del margen objetivo al precio redondeado a múltiplos
  (el 98% de los precios de la casa son múltiplos de 5), nunca bajo costo;
- el precio se teclea como TOTAL del empaque ("la caja a 880") y el servidor
  hace la división;
- al aplicar escribe las MISMAS reglas de lista migradas (base min_qty=0 +
  empaque min_qty=factor), bloquea el precio bajo costo (RB-08) y deja rastro
  en el chatter del producto.

Fórmula (deducida de 3,000 precios reales de ADG):
    precio = costo sin ITBIS × factor × (1 + ITBIS) × (1 + margen)
    """,
    'version': '19.0.4.0.1',
    'category': 'Sales/Sales',
    'author': 'Mallol Consulting - Smerlin Ramos',
    'license': 'OPL-1',
    'depends': ['product', 'sale_management'],
    'data': [
        'security/ir.model.access.csv',
        'views/res_config_settings_views.xml',
        'views/precio_sugerido_views.xml',
    ],
    'installable': True,
    'application': False,
}

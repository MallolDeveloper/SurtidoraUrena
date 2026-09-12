# -*- coding: utf-8 -*-
{
    'name': 'Surtidora - Bonificación automática en el POS',
    'summary': 'REQ-V09/V10: «compra N, lleva M gratis» entra solo al llegar a '
               'la cantidad, como en ADG, sin pasar por el botón Recompensa.',
    'description': """
En ADG la bonificación es una línea que el sistema inserta sola cuando la
venta alcanza la cantidad de la regla (inv_bonificacion_prod: 25 vigentes,
~5 al día, casi todas «compra N unidades de X, lleva M de Y gratis»).

Odoo trae la misma regla en Descuentos y lealtad («Compra X Obtén Y»), pero
el POS solo pone gratis un producto que YA está en la orden. Con la caja de
18 Saltinas en pantalla el Dekreme no aparece: la cajera tiene que
agregarlo, o pedirlo por ⋮ → Recompensa. Verificado en SurtidoraDev el
11-sep-2026, en pantalla y en el código del bundle desplegado
(`_computeUnclaimedFreeProductQty`: `Math.min(available, freeQty)`).

Este módulo hace lo que haría la cajera, en el acto:

- Cuando las unidades PAGADAS llegan a la cantidad de la regla, agrega a la
  orden las unidades del premio, marcadas como bonificación
  (`surtidora_premio_id`); el núcleo las pone gratis por su vía normal.
- Si la cajera baja la cantidad, las bonificadas que sobran se retiran
  solas. Si borra la línea bonificada, renuncia al premio para esa orden
  (igual que borrar la línea de premio del núcleo); «Restablecer programas»
  lo devuelve.
- Las unidades bonificadas no se mezclan con las pagadas del mismo producto:
  quedan en su propia línea, y así llegan al backend y al recibo.

Solo toca la bonificación clásica: programa «Compra X Obtén Y», automático,
un solo premio de un solo producto, reglas por unidad. Descuentos, cupones,
puntos y premios por etiqueta siguen en manos del núcleo tal cual.

Semántica (la de ADG): lo que la cajera teclea es lo que el cliente PAGA;
las gratis van encima. En un 3x2, teclear 2 trae la tercera; teclear 3
trae una cuarta.

Fuera, a propósito: el tope obligatorio de RB-14. El tope nativo
(limit_usage/max_usage) cuenta órdenes y el de ADG cuenta unidades
regaladas; se decide con el cliente antes de exigirlo.
    """,
    'version': '19.0.1.0.2',
    'category': 'Sales/Point of Sale',
    'author': 'Mallol Consulting - Smerlin Ramos',
    'license': 'OPL-1',
    'depends': ['point_of_sale', 'pos_loyalty'],
    'data': [],
    'assets': {
        'point_of_sale._assets_pos': [
            'surtidora_pos_bonificacion/static/src/**/*',
        ],
    },
    'installable': True,
    'application': False,
}

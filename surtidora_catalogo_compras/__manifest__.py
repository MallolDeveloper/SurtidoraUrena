# -*- coding: utf-8 -*-
{
    'name': 'Surtidora - Última compra en el catálogo',
    'summary': 'La tarjeta del catálogo de compras dice cuándo se le compró por '
               'última vez a ese suplidor y a qué precio.',
    'description': """
Odoo enseña en cada tarjeta el precio de la TARIFA: lo que el suplidor dice
que cuesta hoy. Lo que no enseña —y es lo que se mira para negociar— es lo que
se pagó la última vez. No hay campo nativo para eso: `product.product` no tiene
ni fecha ni precio de última compra.

Este módulo lo añade a la tarjeta, justo debajo del precio:

    Últ. compra 12/08/2026 · RD$ 1,084.72

Reglas que lo hacen fiable:

- Es la última compra a ESE suplidor, no a cualquiera — es con quien se negocia.
- El precio va CON ITBIS y se toma de `price_total / product_qty`, que ya lleva
  impuestos y descuentos y NO depende de cómo esté configurado el impuesto.
- Se convierte a la MISMA unidad que muestra la tarjeta (reutilizando el
  `uomFactor` que calcula el propio Odoo), o el número de al lado sería
  incomparable: la tarifa en cajas contra un precio en paquetes.
- Si nunca se le compró, no se muestra nada. Un 0.00 se lee como "se lo compré
  hoy gratis".

No toca el sugerido nativo, ni `purchase`, ni `purchase_stock`, ni el catálogo
de ventas. Solo lee y presenta.
    """,
    'version': '19.0.1.1.0',
    'category': 'Inventory/Purchase',
    'author': 'Mallol Consulting - Smerlin Ramos',
    'license': 'OPL-1',
    'depends': ['purchase_stock'],
    'assets': {
        'web.assets_backend': [
            'surtidora_catalogo_compras/static/src/**/*',
        ],
    },
    'installable': True,
    'application': False,
}

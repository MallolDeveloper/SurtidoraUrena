# -*- coding: utf-8 -*-
{
    'name': 'Surtidora - Última compra en el catálogo',
    'summary': 'La tarjeta del catálogo de compras dice cuándo se le compró por '
               'última vez a ese suplidor y a qué precio.',
    'description': """
Odoo enseña en cada tarjeta el precio de la TARIFA: lo que el suplidor dice
que cuesta hoy. Este módulo añade las tres cosas que se miran para saber si
ese precio es bueno:

1. LA ÚLTIMA COMPRA A ESE SUPLIDOR — fecha y precio. No hay campo nativo para
   esto: `product.product` no tiene ni fecha ni precio de última compra.

       Últ. compra 31/07/2026 · RD$ 1,764.00 / Caja de 14 (Paquete)

2. QUÉ OTROS SUPLIDORES LO HAN VENDIDO, y a cuánto. La munición para
   negociar: "este mismo me lo dio otro más barato". Se ordena por fecha, no
   por precio: el más barato puede ser de hace tres años.

3. EL COSTO DE LA FICHA, pero SOLO cuando no coincide con la tarifa. El ETL
   cargó costo y tarifa de la misma columna de ADG, así que coinciden al
   centavo en 3,737 de 3,755 tarifas; enseñarlo siempre sería repetir el
   número de arriba. Cuando NO coinciden casi siempre es un dato malo (una
   unidad base equivocada deja el costo en 4.16 contra una tarifa de 228.57),
   y eso sí hay que verlo antes de firmar la compra.

Reglas que lo hacen fiable:

- Todo NETO, igual que el precio de la tarifa que va justo encima. Mezclar
  bases hace que un precio que no se movió parezca una subida del 18%.
- Todo en la MISMA unidad que ese precio, que no siempre es la de la tarifa:
  con una sola línea del producto en la orden, Odoo muestra el precio de la
  LÍNEA, en la unidad de la línea.
- Solo órdenes confirmadas, y sin cantidades negativas: devolver no es
  comprar.
- Si no hay dato, no se muestra nada. Un 0.00 se lee como "se lo compré hoy
  gratis".

No toca el sugerido nativo, ni `purchase`, ni `purchase_stock`, ni el catálogo
de ventas. Solo lee y presenta.
    """,
    'version': '19.0.3.0.0',
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

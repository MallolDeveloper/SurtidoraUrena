# -*- coding: utf-8 -*-
{
    'name': 'Surtidora - Sugerido en la unidad del suplidor',
    'summary': 'El botón "Agregar todos" del sugerido escribía la cantidad en '
               'unidad base mientras la tarjeta la rotulaba en cajas.',
    'description': """
QUÉ PASABA
----------
En el catálogo de compras, la misma pantalla tiene dos formas de meter un
producto en la orden, y no hacían lo mismo:

    botón «+»          ->  5 Caja de 20  a RD$ 946.20   (100 paquetes)
    «Agregar todos»    ->  85 Paquete    a RD$  47.31   ( 85 paquetes)

El «+» corre en el navegador y divide entre el factor del empaque; «Agregar
todos» llama al servidor, que escribía la cantidad tal cual, en la unidad base
del producto.

El dinero de la orden salía BIEN —85 paquetes cuestan lo que cuestan 85
paquetes—. Lo que salía mal es lo que lee una persona: la tarjeta rotula la
unidad de la TARIFA, así que la pantalla decía «85 · Caja de 20» encima de una
línea de 85 paquetes. Un factor de 20 entre el rótulo y la línea.

Medido sobre una orden real de 83 líneas: 80 rotuladas con una unidad distinta
a la que llevaban, por RD$ 690,501.99.

DE DÓNDE VIENE
--------------
No es un defecto nuestro: es un fallo que Odoo YA corrigió y que este servidor
todavía no tiene.

    build desplegado    19.0+e-20260305   (5 de marzo de 2026)
    corrección oficial  193f5282          (6 de agosto de 2026)
    «[FIX] purchase_stock: respect product uom for catalog suggestion»

LO QUE HACE, EN DOS PASOS SEPARADOS A PROPÓSITO
-----------------------------------------------
1. LA UNIDAD — es la corrección oficial, con sus mismas expresiones. No cambia
   cuánto se compra: 85 paquetes y 4.25 cajas de 20 son la misma mercancía por
   el mismo dinero (RD$ 4,021.35 antes y después). Cambia en qué unidad está
   escrita, que es la que la tarjeta ya venía rotulando.

2. EL EMPAQUE ENTERO — esto ya no es de Odoo, es decisión de Surtidora. A un
   suplidor no se le piden 4.25 cajas. Sin este paso, 75 de aquellas 83 líneas
   quedarían en fracciones de caja y la orden no se podría enviar. Con él, el
   sugerido termina donde termina el botón «+» de la misma pantalla: 5 cajas.

   TIENE PRECIO Y HAY QUE SABERLO: sobre esas 83 líneas son RD$ 62,876.76 más
   (9.1%). No es gasto de más sino grano de compra —la caja es lo mínimo que
   el suplidor vende, y lo que sobra queda en almacén y rebaja el sugerido del
   mes que viene—, pero se decide mirando el número, no de gratis.

   Y NO SE PUEDE HACER CONFIGURANDO. En Odoo 19 el redondeo dejó de ser por
   unidad: `uom.uom.rounding` es un campo CALCULADO que devuelve el decimal de
   «Product Unit» para todas por igual (`uom_uom.py::_compute_rounding`). Por
   eso las 354 unidades de la base leen 0.01. Bajarlo a entero volvería
   indivisible también la libra de avena. De ahí que este paso sea código.

   Sale en un método propio, `_surtidora_a_empaque_entero`: quitarlo es borrar
   una línea, y queda el paso 1 solo.

SE DESACTIVA SOLO
-----------------
La corrección solo entra en las líneas que son EXACTAMENTE lo que deja el
nativo sin corregir. En un servidor ya actualizado la línea llega en la unidad
del suplidor, la huella no coincide y no se toca nada. Entonces este módulo se
desinstala sin deshacer ni un dato — salvo que se quiera conservar el paso 2,
que Odoo sigue sin hacer.
    """,
    'version': '19.0.1.0.0',
    'category': 'Inventory/Purchase',
    'author': 'Mallol Consulting - Smerlin Ramos',
    'license': 'OPL-1',
    'depends': ['purchase_stock'],
    'installable': True,
    'application': False,
}

# -*- coding: utf-8 -*-
"""El sugerido nativo, escribiendo en la unidad en la que se compra.

«Agregar todos» dejaba la cantidad en la unidad BASE del producto —85
paquetes— mientras la tarjeta la rotulaba con la unidad de la TARIFA —«Caja
de 20»—. El dinero salía bien; lo que salía mal era lo que lee una persona,
con un factor de 20 entre el rótulo y la línea.

Es un fallo que Odoo ya corrigió aguas arriba (193f5282, 6-ago-2026) y que
este servidor todavía no tiene (build 19.0+e-20260305).

Se hacen DOS cosas, y solo la primera es de Odoo:

    1. LA UNIDAD — las mismas dos expresiones del parche oficial:

           unidad   = tarifa del suplidor, o la base si no le compra a él
           cantidad = producto.uom_id._compute_quantity(suggested_qty, unidad)

       Esto no cambia cuánto se compra: 85 paquetes y 4.25 cajas de 20 son la
       misma mercancía por el mismo dinero.

    2. EL EMPAQUE ENTERO — decisión de Surtidora, no de Odoo. Sí cambia cuánto
       se compra, hacia arriba, y por eso vive en un método aparte con su
       precio medido: ver `_surtidora_a_empaque_entero`.

SE CORRIGE DESPUÉS, NO SE REESCRIBE EL MÉTODO. `action_purchase_order_suggest`
son cuarenta líneas que arman secciones, colapsan líneas repetidas y guardan
los parámetros en el suplidor; copiarlas para cambiar dos sería quedarse con
una copia vieja del día que Odoo toque cualquiera de las otras treinta y ocho.
Envolver el método y arreglar su salida deja el resto intacto.

Y ESO LO VUELVE AUTO-DESACTIVABLE. La corrección solo entra en las líneas que
son EXACTAMENTE lo que deja el nativo sin corregir. En un servidor ya
actualizado la línea llega en la unidad del suplidor, la huella no coincide y
no se toca nada: el módulo se puede desinstalar sin deshacer ni un dato.
"""
from odoo import models
from odoo.tools import float_compare, float_round


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    def action_purchase_order_suggest(self):
        cambio = super().action_purchase_order_suggest()
        self._surtidora_reexpresar_en_unidad_de_compra()
        return cambio

    def _surtidora_reexpresar_en_unidad_de_compra(self):
        """Pasa a la unidad de la tarifa las líneas que el sugerido dejó en base.

        La conversión sola no cambiaría cuánto se compra —85 paquetes son 4.25
        cajas de 20, la misma mercancía por el mismo dinero—; el redondeo a caja
        entera que viene después sí, y está medido en
        `_surtidora_a_empaque_entero`. Lo que en todo caso queda arreglado es el
        desfase que se veía en pantalla: la unidad de la línea pasa a ser la que
        la tarjeta ya venía rotulando.

        El precio se recalcula solo. `price_unit` es un `compute` almacenado que
        depende de `product_uom_id` y `product_qty` (`purchase_order_line.py`),
        así que al escribir los dos Odoo relee la tarifa: 47.31 por paquete pasa
        a 946.20 por caja y el subtotal no se mueve.
        """
        for linea in self.order_line:
            producto = linea.product_id
            unidad = self._surtidora_unidad_de_compra(producto)
            if unidad == producto.uom_id:
                continue
            if not self._surtidora_es_salida_del_nativo(linea, producto):
                continue
            linea.write({
                'product_uom_id': unidad.id,
                'product_qty': self._surtidora_a_empaque_entero(producto, unidad),
            })

    def _surtidora_a_empaque_entero(self, producto, unidad):
        """El sugerido en la unidad de compra, redondeado a empaque entero.

        La conversión es la del parche oficial. El redondeo NO: es decisión de
        Surtidora, y es la que hace que la orden se pueda enviar —a un suplidor
        no se le piden 4.25 cajas— y que este botón termine donde termina el
        «+» de la misma pantalla, que ya redondeaba hacia arriba.

        Hacia ARRIBA y no al más cercano: la caja es el grano mínimo de compra,
        así que quedarse corto es no cubrir la demanda que el propio sugerido
        acaba de calcular. Lo que sobra queda en almacén y rebaja el sugerido
        del mes siguiente.

        Se redondea sobre la unidad de compra ya convertida, no sobre la base:
        `precision_rounding=1.0` aquí significa «una caja», no «un paquete».

        No se puede conseguir configurando. En Odoo 19 `uom.uom.rounding` es un
        campo calculado que devuelve el decimal de «Product Unit» para todas
        las unidades por igual, así que no hay forma de declarar que la caja es
        indivisible y la libra no.
        """
        cantidad = producto.uom_id._compute_quantity(producto.suggested_qty, unidad)
        return float_round(cantidad, precision_rounding=1.0, rounding_method='UP')

    def _surtidora_unidad_de_compra(self, producto):
        """La unidad de la tarifa de ESTE suplidor; si no le compra, la base.

        Misma expresión que el parche oficial, incluido el `[:1]`: con más de
        una tarifa del mismo suplidor manda la primera, que es la de menor
        secuencia.
        """
        tarifa = producto.seller_ids.filtered(
            lambda vendedor: vendedor.partner_id == self.partner_id)[:1]
        return tarifa.product_uom_id or producto.uom_id

    def _surtidora_es_salida_del_nativo(self, linea, producto):
        """¿Esta línea es tal cual la dejó el sugerido sin corregir?

        Es la huella del fallo: unidad base del producto y cantidad igual al
        sugerido, sin convertir. Sirve para dos cosas a la vez —acotar la
        corrección a las líneas que el sugerido acaba de escribir, sin tocar lo
        que el comprador puso a mano, y no hacer nada en un servidor donde el
        nativo ya convierte.

        Se compara con `float_compare` y no con `==` porque son flotantes: la
        cantidad viaja por el ORM y un `85.0 == 85.00000000000001` fallaría en
        silencio, dejando la línea sin corregir sin decir por qué.
        """
        if not producto or not producto.suggested_qty:
            return False
        return (
            linea.product_uom_id == producto.uom_id
            and float_compare(linea.product_qty, producto.suggested_qty,
                              precision_rounding=producto.uom_id.rounding) == 0
        )

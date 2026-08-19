# -*- coding: utf-8 -*-
from odoo import fields, models


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    autorizacion_id = fields.Many2one(
        'surtidora.autorizacion.precio', string='Autorización de precio',
        copy=False, readonly=True)

    # ------------------------------------------------------------------
    # Reglas de precio (núcleo reutilizable por cualquier pantalla de venta)
    # ------------------------------------------------------------------
    # DOS BASES DISTINTAS, Y NO SE PUEDEN MEZCLAR
    # ------------------------------------------------------------------
    # El ITBIS de Surtidora está configurado como *incluido en el precio*
    # (price_include). Eso parte los números en dos mundos:
    #
    #   · CON ITBIS  → el precio de lista (100.00) y price_unit.
    #   · SIN ITBIS  → el costo del producto (standard_price = 76.27).
    #
    # Comparar el precio contra el costo sin convertir regalaba una franja
    # entera del 18%: un artículo de costo 76.27 (piso real 90.00 con ITBIS)
    # se podía vender a 76.28 sin que saltara ningún bloqueo.
    #
    # Y `price_unit` tampoco es lo que paga el cliente: el descuento vive en
    # otra columna. Una línea de 100.00 con 99% de descuento se cobraba a 1.00
    # y pasaba el confirmar sin pedir autorización ni bloquear por bajo costo
    # (comprobado contra la base de pruebas).
    #
    # Odoo ya publica los dos valores por unidad y con el descuento aplicado,
    # así que no hay que calcular nada a mano:
    #   price_reduce_taxinc  → con ITBIS   → se compara con el PRECIO DE LISTA
    #   price_reduce_taxexcl → sin ITBIS   → se compara con el COSTO
    def _precio_de_lista(self):
        """Precio que la lista del pedido asigna a esta línea (misma mecánica
        validada en la mini-data: regla base + regla por cantidad/empaque).
        Viene CON ITBIS, igual que price_reduce_taxinc."""
        self.ensure_one()
        order = self.order_id
        if not order.pricelist_id or not self.product_id:
            return self.price_unit
        return order.pricelist_id._get_product_price(
            self.product_id, self.product_uom_qty or 1.0,
            currency=order.currency_id, uom=self.product_uom_id,
            date=order.date_order,
        )

    def _costo_en_uom(self):
        """Costo del producto expresado en la unidad de la línea, SIN ITBIS
        (para comparar contra price_reduce_taxexcl — RB-08)."""
        self.ensure_one()
        factor = self.product_uom_id._compute_quantity(
            1.0, self.product_id.uom_id, round=False)
        return self.product_id.standard_price * factor

    def _es_bajo_costo(self):
        """RB-08: ¿lo que el cliente paga por unidad, sin ITBIS, está por
        debajo del costo?"""
        self.ensure_one()
        if not self.product_id or self.display_type:
            return False
        # price_reduce_taxexcl es price_subtotal/cantidad: con cantidad 0 da
        # 0.00 y marcaría bajo costo una línea que no vende nada
        if not self.product_uom_qty:
            return False
        return self.currency_id.compare_amounts(
            self.price_reduce_taxexcl, self._costo_en_uom()) < 0

    def _requiere_autorizacion(self):
        """RB-01: ¿lo que el cliente paga está por debajo de la lista (menos la
        tolerancia) y sin una autorización vigente que lo cubra?"""
        self.ensure_one()
        if not self.product_id or self.display_type:
            return False
        if not self.product_uom_qty:
            return False
        tolerancia = self.company_id.surtidora_tolerancia_precio_pct or 0.0
        piso = self._precio_de_lista() * (1 - tolerancia / 100.0)
        if self.currency_id.compare_amounts(self.price_reduce_taxinc, piso) >= 0:
            return False
        if self.autorizacion_id and self.autorizacion_id.sigue_vigente_para(self):
            return False
        return True

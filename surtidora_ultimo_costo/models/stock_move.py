# -*- coding: utf-8 -*-
"""La recepción alimenta el último costo, igual que en ADG.

Se engancha al VALIDAR la entrada, no al confirmar la orden: en ADG el
`prod_cosultimo` se mueve con la compra registrada (lo que entró), y una
orden confirmada que nunca llega no debe cambiar el costo de nada."""
from odoo import models


class StockMove(models.Model):
    _inherit = 'stock.move'

    def _action_done(self, cancel_backorder=False):
        movimientos = super()._action_done(cancel_backorder=cancel_backorder)
        movimientos._surtidora_alimentar_ultimo_costo()
        return movimientos

    def _surtidora_es_entrada_de_compra(self):
        """Entra a un almacén propio y viene de una línea de compra. Las
        devoluciones a suplidor salen de interno, así que quedan fuera; los
        ajustes y traspasos no traen línea de compra."""
        self.ensure_one()
        return (self.state == 'done'
                and bool(self.purchase_line_id)
                and self.location_dest_id.usage == 'internal'
                and self.location_id.usage != 'internal')

    def _surtidora_alimentar_ultimo_costo(self):
        """Por cada producto recibido, el costo de la línea de compra de la
        entrada MÁS RECIENTE del lote."""
        entradas = self.filtered(lambda m: m._surtidora_es_entrada_de_compra())
        por_producto = {}
        for mov in sorted(entradas, key=lambda m: (m.date, m.id)):
            por_producto[mov.product_id.product_tmpl_id] = mov
        for plantilla, mov in por_producto.items():
            linea = mov.purchase_line_id
            # el MISMO costo con el que Odoo valora la entrada: neto de ITBIS,
            # con el descuento, por unidad base, a la tasa de la fecha del
            # movimiento si la compra fue en otra moneda
            costo = linea.with_context(conversion_date=mov.date)._get_stock_move_price_unit()
            plantilla._surtidora_registrar_ultimo_costo(
                costo, mov.date.date() if mov.date else False, linea.order_id.partner_id)

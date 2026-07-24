# -*- coding: utf-8 -*-
from odoo import _, models


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def action_abrir_negociacion(self):
        self.ensure_one()
        if not self.product_id:
            return False
        wizard = self.env['surtidora.negociacion.wizard'].create(
            self._negociacion_wizard_vals()
        )
        return {
            'type': 'ir.actions.act_window',
            'name': _('Negociación — %s', self.product_id.display_name),
            'res_model': 'surtidora.negociacion.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def _negociacion_wizard_vals(self):
        self.ensure_one()
        product = self.product_id
        order = self.order_id
        return {
            'line_id': self.id,
            'precio_ids': [(0, 0, vals) for vals in self._negociacion_precios(product, order)],
            'stock_ids': [(0, 0, vals) for vals in self._negociacion_stock(product)],
            'historial_ids': [(0, 0, vals) for vals in self._negociacion_historial(product, order)],
        }

    def _negociacion_precios(self, product, order):
        """Precio por cada empaque del producto según la lista del pedido (REQ-V03)."""
        pricelist = order.pricelist_id
        base_uom = product.uom_id
        rows = []
        for uom in (base_uom | product.uom_ids):
            factor = uom._compute_quantity(1.0, base_uom, round=False)
            if pricelist:
                precio = pricelist._get_product_price(
                    product, 1.0, currency=order.currency_id,
                    uom=uom, date=order.date_order,
                )
            else:
                precio = product.list_price * factor
            rows.append({
                'uom_id': uom.id,
                'factor': factor,
                'precio': precio,
                'equivalente_base': precio / factor if factor else 0.0,
                'currency_id': order.currency_id.id,
                'es_actual': uom == self.product_uom_id,
            })
        return rows

    def _negociacion_stock(self, product):
        """Existencia disponible por almacén (REQ-V04)."""
        rows = []
        for wh in self.env['stock.warehouse'].search([]):
            grupos = self.env['stock.quant']._read_group(
                [('product_id', '=', product.id),
                 ('location_id', 'child_of', wh.view_location_id.id)],
                [], ['quantity:sum', 'reserved_quantity:sum'],
            )
            cantidad, reservada = grupos[0] if grupos else (0.0, 0.0)
            rows.append({
                'warehouse_id': wh.id,
                'existencia': cantidad or 0.0,
                'reservada': reservada or 0.0,
                'disponible': (cantidad or 0.0) - (reservada or 0.0),
                'uom_id': product.uom_id.id,
            })
        return rows

    def _negociacion_historial(self, product, order):
        """Últimas 2 compras del cliente para este producto (REQ-V06 / RB-06)."""
        lineas = self.search([
            ('order_partner_id', 'child_of', order.partner_id.commercial_partner_id.id),
            ('product_id', '=', product.id),
            ('state', '=', 'sale'),
            ('id', '!=', self.id),
        ], order='create_date desc', limit=2)
        return [{
            'fecha': l.order_id.date_order,
            'orden': l.order_id.name,
            'cantidad': l.product_uom_qty,
            'uom_id': l.product_uom_id.id,
            'precio': l.price_unit,
            'currency_id': l.currency_id.id,
        } for l in lineas]

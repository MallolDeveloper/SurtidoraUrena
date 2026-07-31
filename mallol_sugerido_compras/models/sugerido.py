# Copyright 2026 Mallol Consulting
# License LGPL-3
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SugeridoCompras(models.TransientModel):
    _name = "mallol.sugerido.compras"
    _description = "Sugerido de Compras por Rotación de Ventas"

    supplier_id = fields.Many2one(
        "res.partner",
        string="Suplidor",
        required=True,
        domain=[("supplier_rank", ">", 0)],
    )
    dias_abastecer = fields.Integer("Días a Abastecer", default=30, required=True)
    dias_historial = fields.Integer(
        "Días de Historial (ventas)", default=30, required=True
    )
    line_ids = fields.One2many(
        "mallol.sugerido.compras.line", "wizard_id", string="Sugerido"
    )

    def action_calcular(self):
        self.ensure_one()
        if self.dias_historial <= 0 or self.dias_abastecer <= 0:
            raise UserError(_("Los días deben ser mayores a cero."))
        self.line_ids.unlink()
        date_from = fields.Datetime.now() - timedelta(days=self.dias_historial)

        products = self.env["product.product"].search(
            [("seller_ids.partner_id", "=", self.supplier_id.id)]
        )
        Sol = self.env["sale.order.line"]
        Pol = self.env["purchase.order.line"]
        vals = []
        for p in products:
            # Ventas por día = vendido en el período / días del período
            sols = Sol.search(
                [
                    ("product_id", "=", p.id),
                    ("order_id.state", "=", "sale"),
                    ("order_id.date_order", ">=", date_from),
                ]
            )
            vendido = sum(sols.mapped("product_uom_qty"))
            ventas_dia = vendido / self.dias_historial

            # Órdenes de compra pendientes de recibir
            pols = Pol.search(
                [
                    ("product_id", "=", p.id),
                    ("order_id.state", "in", ("purchase", "done")),
                ]
            )
            pendiente = sum(max(l.product_qty - l.qty_received, 0.0) for l in pols)

            existencia = p.qty_available
            sugerida = (ventas_dia * self.dias_abastecer) - existencia - pendiente
            vals.append(
                (
                    0,
                    0,
                    {
                        "product_id": p.id,
                        "existencia_actual": existencia,
                        "ventas_dia": ventas_dia,
                        "ordenes_pendientes": pendiente,
                        "cantidad_ordenar": max(0.0, round(sugerida)),
                    },
                )
            )
        self.line_ids = vals
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_generar_oc(self):
        self.ensure_one()
        a_ordenar = self.line_ids.filtered(lambda l: l.cantidad_ordenar > 0)
        if not a_ordenar:
            raise UserError(
                _("No hay nada que ordenar (ninguna línea con Cantidad Ordenar > 0).")
            )
        po = self.env["purchase.order"].create(
            {
                "partner_id": self.supplier_id.id,
                "order_line": [
                    (
                        0,
                        0,
                        {
                            "product_id": l.product_id.id,
                            "name": l.product_id.display_name,
                            "product_qty": l.cantidad_ordenar,
                            "product_uom_id": l.product_id.uom_id.id,
                            "price_unit": l.product_id.standard_price,
                            "date_planned": fields.Datetime.now(),
                        },
                    )
                    for l in a_ordenar
                ],
            }
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("Orden de Compra Generada"),
            "res_model": "purchase.order",
            "res_id": po.id,
            "view_mode": "form",
            "target": "current",
        }


class SugeridoComprasLine(models.TransientModel):
    _name = "mallol.sugerido.compras.line"
    _description = "Línea de Sugerido de Compras"
    _order = "cant_sugerida desc"

    wizard_id = fields.Many2one(
        "mallol.sugerido.compras", required=True, ondelete="cascade"
    )
    product_id = fields.Many2one("product.product", string="Producto", required=True)
    default_code = fields.Char(related="product_id.default_code", string="Referencia")
    uom_name = fields.Char(related="product_id.uom_id.name", string="Unidad")
    existencia_actual = fields.Float("Existencia Actual", digits="Product Unit")
    ventas_dia = fields.Float("Ventas x Día", digits=(16, 4))
    ordenes_pendientes = fields.Float("Ord. Pend.", digits="Product Unit")
    cant_necesaria = fields.Float(
        "Cant. Necesaria", compute="_compute_sugerido", store=True,
        digits="Product Unit"
    )
    cant_sugerida = fields.Float(
        "Cant. Sugerida", compute="_compute_sugerido", store=True,
        digits="Product Unit"
    )
    cantidad_ordenar = fields.Float("Cantidad Ordenar", digits="Product Unit")

    @api.depends(
        "ventas_dia",
        "existencia_actual",
        "ordenes_pendientes",
        "wizard_id.dias_abastecer",
    )
    def _compute_sugerido(self):
        for l in self:
            l.cant_necesaria = l.ventas_dia * l.wizard_id.dias_abastecer
            l.cant_sugerida = (
                l.cant_necesaria - l.existencia_actual - l.ordenes_pendientes
            )

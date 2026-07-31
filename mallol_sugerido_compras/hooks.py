# Copyright 2026 Mallol Consulting
# License LGPL-3
from datetime import timedelta

from odoo import fields

SUP_NAME = "WILLY CHIC DOMINICANA, S.R.L."

# (referencia, descripción, costo, existencia, vendido_30d, oc_pendiente)
PRODUCTOS = [
    ("GACN02", "GALLETAS CREMICA KOKO 24/12-AZUL-GDE", 862.56, 267, 258, 30),
    ("GACQ02", "GALLETAS CREMICA QUESO 12/12", 400.0, 11, 172, 67),
    ("GATG12", "GALLETAS TRIO GRANDE 10/12 CREMICA TRIO 6", 350.0, 112, 111, 0),
    ("FRFR30", "FRUTZA XL FRESA JELLY 24/30", 500.0, 24, 40, 0),
    ("JOJF12", "JOJO JELLY FRESITA 12/150 TARRO", 300.0, 5, 23, 0),
    ("GATC24", "GALLETA CREMICA TWINNIES CHOC VANILLA 24/12", 420.0, 0, 23, 0),
    ("YUPI60", "YUMI PIZZA 12/60 8.GR", 250.0, 7, 16, 0),
    ("WIIC10", "WILLY ICE POP 15/10 HELADITO .850ML", 180.0, 42, 15, 0),
]


def post_init_hook(env):
    if env["res.partner"].search_count([("name", "=", SUP_NAME)]):
        return

    supplier = env["res.partner"].create(
        {"name": SUP_NAME, "company_type": "company", "supplier_rank": 1}
    )
    wh = env["stock.warehouse"].search([], limit=1)
    location = wh.lot_stock_id

    Product = env["product.product"]
    so_lines, po_lines = [], []
    for code, name, costo, stock, v30, pend in PRODUCTOS:
        prod = Product.create(
            {
                "name": name,
                "default_code": code,
                "type": "consu",
                "is_storable": True,
                "standard_price": costo,
                "list_price": round(costo * 1.3, 2),
                "purchase_ok": True,
                "sale_ok": True,
                "seller_ids": [(0, 0, {"partner_id": supplier.id, "price": costo})],
            }
        )
        if stock:
            env["stock.quant"]._update_available_quantity(prod, location, stock)
        if v30:
            so_lines.append(
                (
                    0,
                    0,
                    {
                        "product_id": prod.id,
                        "name": name,
                        "product_uom_qty": v30,
                        "price_unit": round(costo * 1.3, 2),
                    },
                )
            )
        if pend:
            po_lines.append(
                (
                    0,
                    0,
                    {
                        "product_id": prod.id,
                        "name": name,
                        "product_qty": pend,
                        "product_uom_id": prod.uom_id.id,
                        "price_unit": costo,
                        "date_planned": fields.Datetime.now(),
                    },
                )
            )

    # Venta confirmada, fechada hace 15 días -> alimenta "ventas por día"
    if so_lines:
        cliente = env["res.partner"].create(
            {"name": "Cliente Demo Distribución", "customer_rank": 1}
        )
        so = env["sale.order"].create(
            {"partner_id": cliente.id, "order_line": so_lines}
        )
        so.action_confirm()
        so.write({"date_order": fields.Datetime.now() - timedelta(days=15)})

    # Orden de compra confirmada y pendiente de recibir -> "Ord. Pend."
    if po_lines:
        po = env["purchase.order"].create(
            {"partner_id": supplier.id, "order_line": po_lines}
        )
        po.button_confirm()

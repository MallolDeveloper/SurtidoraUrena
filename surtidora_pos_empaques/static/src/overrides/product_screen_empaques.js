import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { SelectionPopup } from "@point_of_sale/app/components/popups/selection_popup/selection_popup";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";

/**
 * Venta por empaque y fraccionamiento en el POS (Surtidora Ureña).
 *
 * 1. Al tocar un producto con empaques se pregunta la unidad, con el precio
 *    de cada una (REQ-V05/V24). El precio del empaque lo resuelve la regla
 *    por cantidad de la lista de precios (18 x 48.89 = 880).
 * 2. RB-09 / REQ-V23: si el producto tiene "la caja se fracciona", se ofrecen
 *    ¼, ½ y ¾ del empaque A PRECIO DE CAJA (½ caja de 18 = 9 und a 440, no a
 *    precio suelto). Solo fracciones que den unidades base enteras. La línea
 *    lleva precio manual (price_type) para que no se recalcule a precio suelto.
 * 3. Escanear el barcode del empaque agrega el factor completo (REQ-P02).
 */
const FRACCIONES = [
    { f: 0.25, txt: "¼" },
    { f: 0.5, txt: "½" },
    { f: 0.75, txt: "¾" },
];

patch(ProductScreen.prototype, {
    /** Empaques del producto: UdM adicionales con factor > 1. */
    _empaquesDe(productTemplate) {
        return (productTemplate.uom_ids || []).filter(
            (uom) => uom.relative_factor && uom.relative_factor > 1
        );
    },

    /** Opciones del popup. Cada item = { qty, price? } (price = manual, tarifa caja).
     *
     * Cada empaque lleva su ARGUMENTO DE VENTA en la segunda línea: a cuánto
     * sale la unidad suelta comprando ese empaque y cuánto se ahorra. Es la
     * conversación real del mostrador ("el paquete está en 45, pero en caja
     * de 24 te sale a 41"), así que va donde se elige la unidad. */
    _opcionesEmpaque(productTemplate) {
        const order = this.pos.getOrder();
        const pricelist = order && order.pricelist_id;
        const fmt = (valor) => this.env.utils.formatCurrency(valor);
        const nombreBase = productTemplate.uom_id?.name || _t("Unidad");
        const precioBase = productTemplate.getPrice(pricelist, 1, 0);
        const opciones = [
            {
                id: 0,
                label: `${nombreBase} — ${fmt(precioBase)}`,
                item: { qty: 1 },
                isSelected: true,
            },
        ];
        let id = 0;
        for (const uom of this._empaquesDe(productTemplate)) {
            const factor = uom.relative_factor;
            const tarifaCaja = productTemplate.getPrice(pricelist, factor, 0);
            opciones.push({
                id: ++id,
                label: `${uom.name} (${factor} ${nombreBase}) — ${fmt(tarifaCaja * factor)}`,
                description: this._argumentoEmpaque(precioBase, tarifaCaja, nombreBase),
                item: { qty: factor },
            });
            if (productTemplate.surtidora_caja_fraccionable) {
                for (const { f, txt } of FRACCIONES) {
                    const qty = factor * f;
                    if (!Number.isInteger(qty)) {
                        continue; // solo fracciones que den unidades enteras
                    }
                    opciones.push({
                        id: ++id,
                        label: `${txt} ${uom.name} (${qty} ${
                            productTemplate.uom_id?.name || _t("und")
                        }) — ${fmt(tarifaCaja * qty)}`,
                        item: { qty, price: tarifaCaja },
                    });
                }
            }
        }
        return opciones;
    },

    /** "41.00 por Paquete · ahorra 4.00 en cada uno" — el gancho de la venta.
     * Si el empaque no trae descuento, solo se informa el equivalente. */
    _argumentoEmpaque(precioBase, tarifaCaja, nombreBase) {
        const fmt = (valor) => this.env.utils.formatCurrency(valor);
        const equivalente = `${fmt(tarifaCaja)} ${_t("por")} ${nombreBase}`;
        const ahorro = precioBase - tarifaCaja;
        if (ahorro <= 0) {
            return equivalente;
        }
        return `${equivalente} · ${_t("ahorra")} ${fmt(ahorro)} ${_t("en cada uno")}`;
    },

    async _elegirEmpaque(productTemplate) {
        return await makeAwaitable(this.dialog, SelectionPopup, {
            title: _t("Unidad de venta — %s", productTemplate.display_name),
            list: this._opcionesEmpaque(productTemplate),
        });
    },

    async addProductToOrder(product) {
        if (this._empaquesDe(product).length) {
            const seleccion = await this._elegirEmpaque(product);
            if (!seleccion) {
                return; // canceló el popup
            }
            if (seleccion.qty > 1 || seleccion.price !== undefined) {
                const vals = { product_tmpl_id: product, qty: seleccion.qty };
                if (seleccion.price !== undefined) {
                    vals.price_unit = seleccion.price;
                    vals.price_type = "manual"; // tarifa caja: no recalcular a precio suelto
                }
                await this.pos.addLineToCurrentOrder(vals, {});
                this.showOptionalProductPopupIfNeeded(product);
                return;
            }
        }
        return super.addProductToOrder(...arguments);
    },

    async _barcodeProductAction(code) {
        const empaque = this.pos.models["product.uom"].getBy("barcode", code.base_code);
        const factor = empaque && empaque.uom_id && empaque.uom_id.relative_factor;
        if (empaque && empaque.product_id && factor > 1) {
            await this.pos.addLineToCurrentOrder(
                {
                    product_id: empaque.product_id,
                    product_tmpl_id: empaque.product_id.product_tmpl_id,
                    qty: factor,
                },
                { code },
                empaque.product_id.needToConfigure()
            );
            this.numberBuffer.reset();
            return;
        }
        return super._barcodeProductAction(...arguments);
    },
});

import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { SelectionPopup } from "@point_of_sale/app/components/popups/selection_popup/selection_popup";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";

/**
 * Venta por empaque en el POS (Surtidora Ureña).
 *
 * 1. Al tocar un producto con empaques, se pregunta la unidad mostrando el
 *    precio de cada una; elegir "Caja de 18" agrega 18 unidades base, cuyo
 *    precio lo resuelve la regla por cantidad de la lista de precios (la
 *    mecánica validada: 18 x 48.89 = 880).
 * 2. Escanear el barcode del empaque (product.uom) agrega la cantidad del
 *    factor; el POS estándar lo agregaba como 1 unidad base (precio errado).
 */
patch(ProductScreen.prototype, {
    /** Empaques del producto: UdM adicionales con factor > 1. */
    _empaquesDe(productTemplate) {
        return (productTemplate.uom_ids || []).filter(
            (uom) => uom.relative_factor && uom.relative_factor > 1
        );
    },

    /** Popup de unidad. Devuelve la cantidad en unidad base, o undefined si cancela. */
    async _elegirEmpaque(productTemplate) {
        const order = this.pos.getOrder();
        const pricelist = order && order.pricelist_id;
        const fmt = (valor) => this.env.utils.formatCurrency(valor);
        const precioBase = productTemplate.getPrice(pricelist, 1, 0);
        const opciones = [
            {
                id: 0,
                label: `${productTemplate.uom_id?.name || _t("Unidad")} — ${fmt(precioBase)}`,
                item: 1,
                isSelected: true,
            },
        ];
        for (const uom of this._empaquesDe(productTemplate)) {
            const factor = uom.relative_factor;
            const precioEmpaque = productTemplate.getPrice(pricelist, factor, 0) * factor;
            opciones.push({
                id: uom.id,
                label: `${uom.name} — ${fmt(precioEmpaque)}`,
                item: factor,
            });
        }
        return await makeAwaitable(this.dialog, SelectionPopup, {
            title: _t("Unidad de venta — %s", productTemplate.display_name),
            list: opciones,
        });
    },

    async addProductToOrder(product) {
        if (this._empaquesDe(product).length) {
            const cantidad = await this._elegirEmpaque(product);
            if (!cantidad) {
                return; // canceló el popup
            }
            if (cantidad > 1) {
                await this.pos.addLineToCurrentOrder({ product_tmpl_id: product, qty: cantidad }, {});
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

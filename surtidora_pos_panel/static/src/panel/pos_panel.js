import { useState } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";

/**
 * Panel de contexto del mostrador (criterio "todo en una sola pantalla").
 *
 * Al tocar o escanear un producto, el panel lateral se actualiza con:
 * últimas ventas de ese producto a ese cliente (RB-06), precios por
 * empaque (REQ-V03) y existencia por almacén (REQ-V04). El servidor arma
 * todo en una llamada (surtidora.pos.panel.info_panel).
 */
patch(ProductScreen.prototype, {
    setup() {
        super.setup(...arguments);
        this.surtiOrm = useService("orm");
        this.surtiPanel = useState({ datos: null, cargando: false });
    },

    async _surtiActualizarPanel(producto) {
        if (!producto) {
            return;
        }
        const variante = producto.product_variant_ids
            ? producto.product_variant_ids[0]
            : producto;
        if (!variante) {
            return;
        }
        const orden = this.pos.getOrder();
        this.surtiPanel.cargando = true;
        try {
            this.surtiPanel.datos = await this.surtiOrm.call(
                "surtidora.pos.panel",
                "info_panel",
                [
                    variante.id,
                    orden?.getPartner()?.id || false,
                    orden?.pricelist_id?.id || false,
                ]
            );
        } catch {
            this.surtiPanel.datos = null;
        } finally {
            this.surtiPanel.cargando = false;
        }
    },

    async addProductToOrder(product) {
        const resultado = await super.addProductToOrder(...arguments);
        this._surtiActualizarPanel(product);
        return resultado;
    },

    async _barcodeProductAction(code) {
        const resultado = await super._barcodeProductAction(...arguments);
        const empaque = this.pos.models["product.uom"].getBy("barcode", code.base_code);
        const producto =
            (empaque && empaque.product_id) ||
            this.pos.models["product.product"].getBy("barcode", code.base_code);
        if (producto) {
            this._surtiActualizarPanel(producto.product_tmpl_id || producto);
        }
        return resultado;
    },

    surtiN(valor, decimales = 2) {
        return (valor || 0).toLocaleString("es-DO", {
            minimumFractionDigits: decimales,
            maximumFractionDigits: decimales,
        });
    },
});

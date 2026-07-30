import { patch } from "@web/core/utils/patch";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";

/**
 * Identificación del cliente por cédula/tarjeta en el POS (REQ-V29).
 *
 * Si el código escaneado no corresponde a ningún producto (ni base ni
 * empaque), se busca como cliente por su código de barras — primero en los
 * datos cargados y luego en el servidor (reutilizando _getPartnerByBarcode
 * del POS estándar) — y se asigna a la orden. Si tampoco es cliente, sigue
 * el flujo estándar (que muestra el aviso de código desconocido).
 */
patch(ProductScreen.prototype, {
    async _barcodeProductAction(code) {
        const esProductoLocal =
            this.pos.models["product.product"].getBy("barcode", code.base_code) ||
            this.pos.models["product.uom"].getBy("barcode", code.base_code);
        if (!esProductoLocal) {
            const cliente = await this._getPartnerByBarcode({ code: code.base_code });
            if (cliente) {
                if (this.currentOrder.get_partner() !== cliente) {
                    this.currentOrder.set_partner(cliente);
                }
                this.numberBuffer.reset();
                return;
            }
        }
        return super._barcodeProductAction(...arguments);
    },
});

import { patch } from "@web/core/utils/patch";
import { onMounted } from "@odoo/owl";
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
    setup() {
        super.setup(...arguments);
        // El cliente se pide al abrir la cuenta; si el turno todavía espera
        // el conteo de apertura, se pide al confirmarlo (cliente_tras_apertura.js).
        onMounted(() => this.pos.surtiPedirCliente());
    },

    async addProductToOrder(product) {
        const orden = this.pos.getOrder();
        if (orden && !orden.getPartner()) {
            const cliente = await this.pos.selectPartner();
            if (!cliente) {
                this.notification.add(
                    "Elija el cliente antes de agregar productos.",
                    { type: "warning" }
                );
                return;
            }
        }
        return super.addProductToOrder(...arguments);
    },

    async _barcodeProductAction(code) {
        const esProductoLocal =
            this.pos.models["product.product"].getBy("barcode", code.base_code) ||
            this.pos.models["product.uom"].getBy("barcode", code.base_code);
        if (!esProductoLocal) {
            const cliente = await this._getPartnerByBarcode({ code: code.base_code });
            if (cliente) {
                // Vía oficial del store (v19 renombró set_partner→setPartner;
                // además así se disparan los efectos colgados del cambio de
                // cliente, como la carga del balance CxC del panel).
                if (this.currentOrder.getPartner() !== cliente) {
                    this.pos.setPartnerToCurrentOrder(cliente);
                }
                this.numberBuffer.reset();
                return;
            }
        }
        return super._barcodeProductAction(...arguments);
    },
});

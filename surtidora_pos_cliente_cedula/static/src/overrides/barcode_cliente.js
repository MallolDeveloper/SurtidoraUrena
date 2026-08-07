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
        onMounted(() => this._surtiPedirCliente());
    },

    /**
     * EL CLIENTE VA PRIMERO: al abrir una cuenta nueva se pide antes de
     * nada, porque de él dependen la lista de precios, el crédito y el
     * historial del panel. Elegirlo después obliga a recalcular lo ya
     * tecleado — y ahí es donde se cotiza mal.
     *
     * Solo se pregunta una vez por orden: si la cajera cierra el diálogo
     * (venta sin identificar), no la perseguimos; el guard de abajo vuelve
     * a pedirlo cuando intente agregar el primer producto.
     */
    async _surtiPedirCliente() {
        const orden = this.pos.getOrder();
        if (!orden || orden.getPartner() || orden.uiState.surtiClientePedido) {
            return;
        }
        if (orden.lines?.length) {
            return; // cuenta ya empezada: no interrumpir a media venta
        }
        orden.uiState.surtiClientePedido = true;
        await this.pos.selectPartner();
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

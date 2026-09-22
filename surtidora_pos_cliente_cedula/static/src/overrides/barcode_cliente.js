import { patch } from "@web/core/utils/patch";
import { onMounted } from "@odoo/owl";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";

/**
 * Identificación del cliente por cédula/tarjeta en el POS (REQ-V29).
 *
 * Orden de búsqueda de un código escaneado:
 *   1. producto o empaque precargado en la caja;
 *   2. producto en el servidor (con surtidora_pos_empaques instalado, también
 *      por el código de sus empaques/códigos extra: product.uom);
 *   3. cliente por su código de barras — primero en los datos cargados y
 *      luego en el servidor (_getPartnerByBarcode del POS estándar) — y se
 *      asigna a la orden;
 *   4. flujo estándar (aviso de código desconocido).
 * Antes el cliente se buscaba ANTES que el producto no precargado: un viaje
 * de más al servidor por cada producto que no estaba en la caja.
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
        // _getProductByBarcode ya mira lo local y, si hace falta, el servidor;
        // la capa que lo llame después en este mismo escaneo no repite viaje
        // (surtidora_pos_empaques lo recuerda por escaneo).
        const producto = await this._getProductByBarcode(code);
        if (!producto && (await this._surtiAsignarClientePorCodigo(code))) {
            this.numberBuffer.reset();
            return;
        }
        return super._barcodeProductAction(...arguments);
    },

    /** Asigna a la orden el cliente dueño del código. ¿Lo encontró? */
    async _surtiAsignarClientePorCodigo(code) {
        const cliente = await this._getPartnerByBarcode({ code: code.base_code });
        if (!cliente) {
            return false;
        }
        // Vía oficial del store (v19 renombró set_partner→setPartner;
        // además así se disparan los efectos colgados del cambio de
        // cliente, como la carga del balance CxC del panel).
        if (this.currentOrder.getPartner() !== cliente) {
            this.pos.setPartnerToCurrentOrder(cliente);
        }
        return true;
    },
});

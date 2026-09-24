import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { OpeningControlPopup } from "@point_of_sale/app/components/popups/opening_control_popup/opening_control_popup";

/**
 * EL CONTEO VA ANTES QUE EL CLIENTE.
 *
 * Al montarse la pantalla de venta, Odoo abre la ventana de apertura
 * (ProductScreen → pos.openOpeningControl) y enseguida nosotros pedíamos el
 * cliente: el diálogo del cliente quedaba ENCIMA y la cajera veía primero
 * «Elija un cliente» y después el conteo del fondo (visto en CAJA 05,
 * 22-sep-2026). Ahora, mientras el turno espera apertura, no se pide el
 * cliente; se pide en cuanto la cajera confirma el conteo.
 */

/**
 * Cuentas a las que ya se les pidió el cliente desde que se cargó la caja
 * (por uuid).
 *
 * Va en memoria y NO en order.uiState, a propósito: Odoo 19 guarda el
 * uiState de cada orden en el IndexedDB del navegador y lo restaura al
 * recargar (related_models/index.js: serializeForIndexedDB y setupRecord),
 * y una cuenta en borrador sin cobrar sobrevive al cierre del turno
 * (data_service_options.js solo purga las finalizadas y sincronizadas).
 * La cuenta vacía que queda al final del día, a la que ya se le había
 * pedido el cliente, amanecía como la primera del turno siguiente con la
 * marca puesta: al confirmar el conteo no se pedía nada y la ventana
 * salía recién con «Nueva orden» (CAJA 05, 24-sep-2026).
 */
const cuentasConClientePedido = new Set();

patch(PosStore.prototype, {
    /**
     * EL CLIENTE VA PRIMERO en la venta: al abrir una cuenta nueva se pide
     * antes de nada, porque de él dependen la lista de precios, el crédito
     * y el historial del panel. Elegirlo después obliga a recalcular lo ya
     * tecleado, y ahí es donde se cotiza mal.
     *
     * Solo se pregunta una vez por cuenta mientras la caja esté cargada: si
     * la cajera cierra el diálogo (venta sin identificar), no la
     * perseguimos; el guard de addProductToOrder vuelve a pedirlo con el
     * primer producto. Al recargar la caja o empezar un turno, una cuenta
     * vacía y sin cliente se vuelve a preguntar una vez.
     */
    async surtiPedirCliente() {
        if (this.shouldShowOpeningControl()) {
            return; // primero el conteo: se pide al confirmar la apertura
        }
        const orden = this.getOrder();
        if (!orden || orden.getPartner() || cuentasConClientePedido.has(orden.uuid)) {
            return;
        }
        if (orden.lines?.length) {
            return; // cuenta ya empezada: no interrumpir a media venta
        }
        cuentasConClientePedido.add(orden.uuid);
        await this.selectPartner();
    },
});

patch(OpeningControlPopup.prototype, {
    async confirm() {
        // El confirm del core deja la sesión en "opened" y cierra su ventana
        // antes de volver; si el servidor falla, lanza el error y no se
        // llega aquí; si la sesión fue borrada, recarga y queda sin abrir.
        await super.confirm(...arguments);
        if (this.pos.session.state === "opened") {
            // Sin await: el diálogo de apertura ya se cerró y no hay que
            // retener su botón mientras la cajera elige al cliente.
            this.pos.surtiPedirCliente();
        }
    },
});

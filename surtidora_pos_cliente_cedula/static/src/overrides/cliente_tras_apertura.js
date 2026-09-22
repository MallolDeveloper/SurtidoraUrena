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
patch(PosStore.prototype, {
    /**
     * EL CLIENTE VA PRIMERO en la venta: al abrir una cuenta nueva se pide
     * antes de nada, porque de él dependen la lista de precios, el crédito
     * y el historial del panel. Elegirlo después obliga a recalcular lo ya
     * tecleado, y ahí es donde se cotiza mal.
     *
     * Solo se pregunta una vez por orden: si la cajera cierra el diálogo
     * (venta sin identificar), no la perseguimos; el guard de
     * addProductToOrder vuelve a pedirlo con el primer producto.
     */
    async surtiPedirCliente() {
        if (this.shouldShowOpeningControl()) {
            return; // primero el conteo: se pide al confirmar la apertura
        }
        const orden = this.getOrder();
        if (!orden || orden.getPartner() || orden.uiState.surtiClientePedido) {
            return;
        }
        if (orden.lines?.length) {
            return; // cuenta ya empezada: no interrumpir a media venta
        }
        orden.uiState.surtiClientePedido = true;
        await this.selectPartner();
    },
});

patch(OpeningControlPopup.prototype, {
    async confirm() {
        await super.confirm(...arguments);
        if (this.pos.session.state === "opened") {
            // Sin await: el diálogo de apertura ya se cerró y no hay que
            // retener su botón mientras la cajera elige al cliente.
            this.pos.surtiPedirCliente();
        }
    },
});

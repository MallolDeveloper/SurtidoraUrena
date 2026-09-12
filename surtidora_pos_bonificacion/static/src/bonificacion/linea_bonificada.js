import { patch } from "@web/core/utils/patch";
import { PosOrderline } from "@point_of_sale/app/models/pos_order_line";
// En Odoo 19 el numpad (`updateSelectedOrderline` / `_setValue`) vive en
// OrderSummary, no en ProductScreen: ahí es donde pos_loyalty engancha lo
// suyo y ahí hay que engancharse. Parchar ProductScreen no se ejecuta nunca.
import { OrderSummary } from "@point_of_sale/app/screens/product_screen/order_summary/order_summary";

/**
 * La línea bonificada es una línea aparte y se comporta como el premio.
 *
 * - No se mezcla con las unidades pagadas del mismo producto: si el núcleo
 *   la fusionara, la marca `surtidora_premio_id` quedaría sobre una línea
 *   mitad pagada, mitad gratis, y ya no se sabría qué retirar cuando la
 *   venta baja de la cantidad.
 * - Borrarla a mano es renunciar al premio en esta orden, exactamente lo
 *   que hace el núcleo cuando se borra su línea de premio
 *   (`disabledRewards`): si no, el ajuste la volvería a meter al instante.
 *   «Restablecer programas» la devuelve, como al premio.
 */
patch(PosOrderline.prototype, {
    canBeMergedWith(otra) {
        if (this.surtidora_premio_id || otra.surtidora_premio_id) {
            return false;
        }
        return super.canBeMergedWith(...arguments);
    },
});

patch(OrderSummary.prototype, {
    /**
     * ⌫ sobre la línea bonificada. El núcleo, con ⌫, primero pone la
     * cantidad en cero ("") y con el segundo ⌫ borra ("remove"). Para la
     * bonificada las dos cosas significan lo mismo: la cajera no la quiere.
     * Se retira de una vez y se apaga el premio, que si no el ajuste la
     * volvería a meter (una línea en cero cuenta como cero puestas).
     */
    _setValue(val) {
        const linea = this.currentOrder?.getSelectedOrderline();
        const quitar = ["", "remove"].includes(val) && this.pos.numpadMode === "quantity";
        if (quitar && linea?.surtidora_premio_id) {
            this.currentOrder.uiState.disabledRewards.add(linea.surtidora_premio_id.id);
            this.currentOrder.removeOrderline(linea);
            this.numberBuffer.reset();
            // el núcleo retira su línea de premio y el ajuste, las demás bonificadas
            this.pos.updateRewards();
            return;
        }
        return super._setValue(...arguments);
    },
});

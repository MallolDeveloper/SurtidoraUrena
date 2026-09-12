import { patch } from "@web/core/utils/patch";
import { PosOrderline } from "@point_of_sale/app/models/pos_order_line";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";

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

patch(ProductScreen.prototype, {
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

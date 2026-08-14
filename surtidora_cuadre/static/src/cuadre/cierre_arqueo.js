import { patch } from "@web/core/utils/patch";
import { ClosePosPopup } from "@point_of_sale/app/components/popups/closing_popup/closing_popup";

/**
 * El conteo por denominación del popup de cierre (moneyDetails) muere en el
 * cliente: el core solo manda un texto en las notas. Se persiste
 * ESTRUCTURADO en la sesión ANTES de cerrarla, para que la hoja de cuadre
 * lo tabule (REQ-V17, arqueo estilo ADG).
 */
patch(ClosePosPopup.prototype, {
    async closeSession() {
        // SIEMPRE se manda (aunque sea vacío): si un intento de cierre
        // falló con desglose y en el segundo la cajera teclea el total a
        // mano, el POS anula moneyDetails — sin este borrado la hoja
        // imprimiría el arqueo viejo contradiciendo el efectivo contado.
        try {
            await this.pos.data.call("pos.session", "surtidora_guardar_arqueo", [
                this.pos.session.id,
                this.moneyDetails || {},
            ]);
        } catch {
            // sin red o error: el cuadre sale sin el desglose (RB-07),
            // el total contado igual queda en la sesión
        }
        return await super.closeSession(...arguments);
    },
});

import { patch } from "@web/core/utils/patch";
import { OpeningControlPopup } from "@point_of_sale/app/components/popups/opening_control_popup/opening_control_popup";

/**
 * Al confirmar el conteo de apertura, el SERVIDOR le asigna el nombre real
 * a la sesión (antes es "/"), pero el registro local del POS se queda con
 * el "/" — toda tirilla del día imprimiría "Cuadre No.: /" hasta un F5
 * (revisión adversaria 14-ago). El read con campos limitados sí actualiza
 * el registro local en el data service.
 */
patch(OpeningControlPopup.prototype, {
    async confirm() {
        await super.confirm(...arguments);
        try {
            await this.pos.data.read("pos.session", [this.pos.session.id], ["name"]);
        } catch {
            // sin red: queda el nombre cacheado; se corrige al recargar (RB-07)
        }
    },
});

import { patch } from "@web/core/utils/patch";
import { onWillStart } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { PartnerList } from "@point_of_sale/app/screens/partner_list/partner_list";

/**
 * RB-15: los cajeros NO crean ni modifican clientes (solo CxC y
 * supervisores) — el origen de los duplicados actuales.
 *
 * Hallazgos de la revisión adversaria (13-ago) aplicados:
 * - El guard vive en PosStore.editPartner, el punto por el que pasan TODAS
 *   las vías (la lista de clientes es solo un envoltorio; selectPreset lo
 *   llama directo).
 * - Un fallo de red al consultar el permiso NO se cachea: se niega ese
 *   intento y se reintenta en el próximo (antes un parpadeo de red dejaba
 *   al supervisor bloqueado toda la sesión).
 * - Si la caja usa empleados (pos_hr), además del permiso del usuario se
 *   exige que el CAJERO en turno sea gerente — el usuario HTTP puede ser
 *   otro que el humano frente a la caja.
 */
patch(PosStore.prototype, {
    async surtiPuedeGestionarClientes() {
        if (this.surtiGestionClientes === undefined) {
            try {
                this.surtiGestionClientes = await this.data.call(
                    "surtidora.pos.clientes", "puede_gestionar", []);
            } catch {
                return false; // negar SIN cachear: el próximo intento reintenta
            }
        }
        if (this.config.module_pos_hr && this.cashier?._role !== "manager") {
            return false;
        }
        return this.surtiGestionClientes;
    },

    async editPartner(partner = false) {
        if (!(await this.surtiPuedeGestionarClientes())) {
            this.notification.add(
                _t("Los clientes se crean y modifican desde CxC o por un supervisor."),
                { type: "warning" });
            return false;
        }
        return await super.editPartner(...arguments);
    },
});

patch(PartnerList.prototype, {
    setup() {
        super.setup(...arguments);
        // precarga el flag para que el template decida los botones "Crear"
        onWillStart(() => this.pos.surtiPuedeGestionarClientes());
    },
});

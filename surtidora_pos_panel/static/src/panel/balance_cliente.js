import { patch } from "@web/core/utils/patch";
import { useEffect } from "@odoo/owl";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";

/**
 * REQ-V02: al elegir el cliente, el panel muestra su CxC fresca.
 *
 * El disparador es un EFECTO sobre el cliente de la orden ACTIVA (no un
 * parche del setter): así cubre todas las vías por las que un cliente
 * llega a la pantalla — selector, escaneo de cédula, cotización liquidada
 * (pos_sale asigna el partner directo), cambio de ticket y recarga del
 * navegador. Hallazgos de la revisión adversaria del 13-ago.
 */
patch(PosStore.prototype, {
    async surtiCargarBalance(partner) {
        if (!partner) {
            this.surtiBalance = null;
            return;
        }
        // token de secuencia: solo la petición MÁS RECIENTE puede escribir
        // (una respuesta o un fallo rezagados no pisan nada)
        const req = (this._surtiBalReq = (this._surtiBalReq || 0) + 1);
        let balance = null;
        try {
            balance = await this.data.call(
                "surtidora.pos.panel", "balance_cliente", [partner.id]);
        } catch {
            balance = null;
        }
        if (req !== this._surtiBalReq) {
            return; // llegó tarde: ya hay otra petición en curso
        }
        if (this.getOrder()?.getPartner()?.id === partner.id) {
            this.surtiBalance = balance;
        }
    },
});

patch(ProductScreen.prototype, {
    setup() {
        super.setup(...arguments);
        // El efecto observa el cliente de la orden activa: cualquier vía
        // que lo cambie (o cambiar de orden) refresca el balance.
        useEffect(
            (partnerId) => {
                const partner = this.pos.getOrder()?.getPartner();
                if (!partnerId) {
                    this.pos.surtiBalance = null;
                } else if (this.pos.surtiBalance?.partner_id !== partnerId) {
                    this.pos.surtiCargarBalance(partner);
                }
            },
            () => [this.pos.getOrder()?.getPartner()?.id]
        );
    },
});

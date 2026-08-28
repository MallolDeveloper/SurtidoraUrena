import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { TicketScreen } from "@point_of_sale/app/screens/ticket_screen/ticket_screen";

/**
 * «Reembolsar» sin cantidades no hace NADA, y no lo dice.
 *
 * En el core la salida es muda:
 *
 *     if (!order || !this.getHasItemsToRefund()) {
 *         return;                          // <- sin aviso de ningún tipo
 *     }
 *
 * La cajera toca el botón, no pasa nada, lo vuelve a tocar, y termina
 * llamando al supervisor. Con ~7 devoluciones al día en 4 cajas, eso es
 * ruido diario por un mensaje que falta. La única excepción del core es la
 * venta de UN artículo de UNA unidad, que se autocompleta sola — por eso el
 * fallo se siente aleatorio: a veces el botón responde y a veces no.
 *
 * Este parche NO cambia el flujo. Solo le pone voz al caso en el que el
 * core ya se iba a plantar; si hay cantidades tecleadas, no se entera nadie.
 */
patch(TicketScreen.prototype, {
    setup() {
        super.setup(...arguments);
        // pos_loyalty monta este mismo servicio en su parche; asignarlo dos
        // veces es inocuo, y así el aviso no depende de que ese esté puesto
        this.notification = useService("notification");
    },

    async onDoRefund() {
        const orden = this.getSelectedOrder();
        // Mismo predicado que usa el core para plantarse, así que el aviso
        // sale exactamente cuando no iba a pasar nada — ni antes ni después.
        // Incluye ya la venta de un solo artículo: `getHasItemsToRefund`
        // devuelve true para esa antes de que se rellene la cantidad.
        if (orden && !this.getHasItemsToRefund()) {
            this.notification.add(this._surtiAvisoSinCantidades(orden), {
                type: "warning",
            });
            return;
        }
        return await super.onDoRefund(...arguments);
    },

    /**
     * Los dos motivos se explican distinto a propósito: mandar a «teclear la
     * cantidad» sobre una venta ya devuelta completa la deja intentándolo en
     * bucle, que es justo la llamada al supervisor que se quiere evitar.
     */
    _surtiAvisoSinCantidades(orden) {
        return this._surtiQuedaAlgoPorDevolver(orden)
            ? _t(
                  "Indique cuánto devolver de cada artículo: toque la línea " +
                      "y teclee la cantidad."
              )
            : _t("Esta venta ya se devolvió completa: no queda nada por devolver.");
    },

    _surtiQuedaAlgoPorDevolver(orden) {
        return (orden.lines || []).some((linea) => {
            // `refundedQty` ya viene en positivo y descuenta las
            // devoluciones canceladas (getter del core en pos.order.line)
            const restante = linea.getQuantity() - linea.refundedQty;
            return restante > 0 && !this.pos.isProductQtyZero(restante);
        });
    },
});

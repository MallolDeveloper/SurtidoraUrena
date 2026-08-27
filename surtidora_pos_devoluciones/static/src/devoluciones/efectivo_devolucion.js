import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import OrderPaymentValidation from "@point_of_sale/app/utils/order_payment_validation";
import { NumberPopup } from "@point_of_sale/app/components/popups/number_popup/number_popup";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { esDevolucion } from "@surtidora_pos_devoluciones/devoluciones/motivo_devolucion";

/**
 * Devolver EFECTIVO necesita la clave de un supervisor.
 *
 * Solo cuando sale dinero de la gaveta: un bono, una nota de crédito o una
 * venta a crédito todavía sin pagar no mueven efectivo, así que pasan como
 * antes. La regla se dispara por `is_cash_count` del método de pago y no por
 * su nombre — quien renombre "Efectivo" no debe poder apagar el control sin
 * darse cuenta.
 *
 * Esta pantalla es la comodidad; el control de verdad está en el servidor
 * (pos_order.py), que vuelve a comprobarlo todo cuando la orden baja. Pedir
 * la clave solo aquí no sería un control: el navegador se salta con tres
 * llamadas, que es exactamente lo que ya pasó con el candado de precios.
 */
function efectivoQueSale(orden) {
    return (orden.payment_ids || []).reduce((total, pago) => {
        const importe = pago.amount || 0;
        return importe < 0 && pago.payment_method_id?.is_cash_count
            ? total - importe
            : total;
    }, 0);
}

function ventaOriginal(orden) {
    for (const linea of orden.lines || []) {
        const original = linea.refunded_orderline_id?.order_id;
        if (original) {
            return original;
        }
    }
    return null;
}

patch(OrderPaymentValidation.prototype, {
    async isOrderValid(isForceValidate) {
        // El motivo se pide antes (lo hace el otro parche): si falta, ni
        // siquiera llegamos a molestar al supervisor.
        if (!(await super.isOrderValid(isForceValidate))) {
            return false;
        }
        return await this._surtiAutorizarEfectivo();
    },

    async _surtiAutorizarEfectivo() {
        const orden = this.order;
        if (!esDevolucion(orden)) {
            return true;
        }
        const efectivo = efectivoQueSale(orden);
        if (!efectivo) {
            return true;
        }

        const dialog = this.pos.dialog;
        // El monto va en el título: NumberPopup no tiene subtítulo, y
        // formatCurrency vive en el env de un componente — esto no lo es.
        const pin = await makeAwaitable(dialog, NumberPopup, {
            title: _t("Clave del supervisor para devolver efectivo"),
            formatDisplayedValue: (v) => "•".repeat(String(v).length),
        });
        if (!pin) {
            return false;
        }

        let resultado;
        try {
            resultado = await this.pos.data.call(
                "surtidora.pos.devolucion",
                "autorizar_efectivo",
                [
                    String(pin),
                    orden.pos_reference || orden.name || "",
                    efectivo,
                    ventaOriginal(orden)?.id || false,
                    this.pos.session?.id || false,
                ]
            );
        } catch {
            // Sin servidor no se puede verificar la clave, y una devolución
            // en efectivo sin verificar es dinero que sale sin control. Aquí
            // NO aplica el fail-open de RB-07: eso protege la venta, no la
            // salida de caja.
            dialog.add(AlertDialog, {
                title: _t("No se pudo verificar la clave"),
                body: _t(
                    "Sin conexión con el servidor no se puede autorizar una " +
                        "devolución en efectivo. Inténtelo de nuevo o entregue " +
                        "un bono."
                ),
            });
            return false;
        }

        if (!resultado?.ok) {
            dialog.add(AlertDialog, {
                title: _t("Devolución no autorizada"),
                body:
                    resultado?.mensaje ||
                    _t("Esa clave no corresponde a un supervisor autorizado."),
            });
            return false;
        }
        return true;
    },
});

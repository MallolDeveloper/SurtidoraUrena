import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import OrderPaymentValidation from "@point_of_sale/app/utils/order_payment_validation";

/**
 * Bono / Nota de Crédito como forma de pago (REQ-V18, política 12.4).
 *
 * El bono es NOMINATIVO (cada bono de ADG lleva su cliente) y se aplica
 * como crédito en la compra nueva — pago mixto: cubre hasta su saldo y la
 * diferencia va en efectivo/tarjeta. El saldo lo decide el SERVIDOR.
 *
 * Reglas de la revisión adversaria (13-ago):
 * - En DEVOLUCIONES (monto negativo) el bono se EMITE, no se consume: no
 *   se exige saldo previo — es el caso que origina el bono.
 * - El tope descuenta los bonos ya aplicados en ESTA orden.
 * - El bono nunca da cambio: el total en bonos no puede exceder la venta.
 */

function montoBonoDe(orden) {
    return orden.payment_ids
        .filter((p) => p.payment_method_id.surtidora_es_bono)
        .reduce((s, p) => s + p.amount, 0);
}

async function veredictoBono(pos, partnerId, monto) {
    try {
        return await pos.data.call("surtidora.pos.credito", "verificar_bono", [
            partnerId || false,
            monto,
        ]);
    } catch {
        return { permitido: false, motivo: "sin_conexion", disponible: 0 };
    }
}

function mensajeBono(veredicto) {
    const cuerpos = {
        sin_cliente: _t("Seleccione el cliente: el bono es nominativo."),
        sin_bono: _t("%s no tiene bonos ni saldo a favor disponibles."),
        sin_conexion: _t("No se pudo consultar el saldo de bonos. Intente de nuevo."),
    };
    let body = cuerpos[veredicto.motivo] || _t("Bono no disponible.");
    if (veredicto.motivo === "sin_bono") {
        body = body.replace("%s", veredicto.cliente);
    }
    return { title: _t("Bono / Nota de Crédito"), body };
}

patch(PaymentScreen.prototype, {
    /** Al tocar el método Bono: validar saldo y TOPAR la línea al restante. */
    async addNewPaymentLine(paymentMethod) {
        if (!paymentMethod.surtidora_es_bono) {
            return await super.addNewPaymentLine(...arguments);
        }
        const orden = this.currentOrder;
        const cliente = orden.getPartner();
        if (!cliente) {
            this.dialog.add(AlertDialog, mensajeBono({ motivo: "sin_cliente" }));
            return false;
        }
        const monto = orden.getDefaultAmountDueToPayIn(paymentMethod);
        if (monto <= 0) {
            // DEVOLUCIÓN: el bono se emite (queda como saldo a favor al
            // cerrar sesión); no requiere saldo previo
            return await super.addNewPaymentLine(...arguments);
        }
        const v = await veredictoBono(this.pos, cliente.id, monto);
        // el disponible real descuenta lo ya aplicado en ESTA orden
        const disponible = Math.max(0, (v.disponible || 0) - montoBonoDe(orden));
        if (!v.permitido && v.motivo !== "excede") {
            this.dialog.add(AlertDialog, mensajeBono(v));
            return false;
        }
        if (disponible <= 0) {
            this.dialog.add(AlertDialog, {
                title: _t("Bono / Nota de Crédito"),
                body: _t("Ya aplicó todo el saldo disponible de %s en esta venta.",
                    cliente.name),
            });
            return false;
        }
        const creada = await super.addNewPaymentLine(...arguments);
        if (creada && disponible < monto) {
            // pago mixto: el bono cubre hasta su saldo; el resto, otra forma
            const linea = orden.payment_ids.at(-1);
            linea.setAmount(disponible);
            this.numberBuffer.set(disponible.toString()); // buffer en sintonía
            this.notification.add(
                _t("Bono disponible: %s — el resto se cobra con otra forma de pago.",
                    this.env.utils.formatCurrency(disponible)),
                { type: "info" });
        }
        return creada;
    },
});

patch(OrderPaymentValidation.prototype, {
    /** Compuerta final: bonos ≤ saldo fresco Y ≤ total de la venta (el
     * bono nunca se convierte en cambio en efectivo). Los negativos
     * (emisión por devolución) pasan. */
    async isOrderValid(isForceValidate) {
        const montoBono = montoBonoDe(this.order);
        if (montoBono > 0) {
            const fmt = this.pos.env.utils.formatCurrency;
            const total = this.order.priceIncl;
            if (montoBono > total + 0.005) {
                this.pos.dialog.add(AlertDialog, {
                    title: _t("Bono / Nota de Crédito"),
                    body: _t("El bono aplicado (%s) excede el total de la venta (%s): " +
                        "el bono no da cambio en efectivo.", fmt(montoBono), fmt(total)),
                });
                return false;
            }
            const v = await veredictoBono(
                this.pos, this.order.getPartner()?.id, montoBono);
            if (!v.permitido) {
                this.pos.dialog.add(AlertDialog, v.motivo === "excede"
                    ? {
                        title: _t("Bono insuficiente"),
                        body: _t("El bono aplicado (%s) excede el saldo disponible (%s). Ajuste el monto.",
                            fmt(montoBono), fmt(v.disponible)),
                    }
                    : mensajeBono(v));
                return false;
            }
        }
        return await super.isOrderValid(...arguments);
    },
});

import { patch } from "@web/core/utils/patch";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import OrderPaymentValidation from "@point_of_sale/app/utils/order_payment_validation";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";

/**
 * Candado de crédito del mostrador (la condición "crédito" de ADG en el POS).
 *
 * El veredicto lo da el servidor (surtidora.pos.credito.verificar) con el
 * balance fresco del cliente; aquí solo se pregunta en dos momentos:
 * 1. Al tocar el método "Crédito" — aviso temprano, antes de crear la línea.
 * 2. Al validar la orden — compuerta final (evita colar el crédito editando
 *    montos después del primer chequeo).
 * Si el servidor no responde, el crédito se niega (nunca fiar a ciegas).
 */

async function veredictoCredito(pos, partnerId, monto) {
    try {
        return await pos.data.call("surtidora.pos.credito", "verificar", [
            partnerId || false,
            monto,
        ]);
    } catch {
        return { permitido: false, motivo: "sin_conexion" };
    }
}

function mensajeCredito(veredicto, formatear) {
    const cuerpos = {
        sin_cliente: _t("Seleccione el cliente antes de vender a crédito."),
        sin_credito: _t(
            "%s no está autorizado a comprar a crédito.\n" +
                "La autorización es el 'Límite de crédito' en la ficha del cliente."
        ),
        excede: _t(
            "%s no tiene crédito suficiente.\n" +
                "Límite: %s · Balance pendiente: %s · Disponible: %s"
        ),
        sin_conexion: _t(
            "No se pudo verificar el crédito con el servidor. Intente de nuevo."
        ),
    };
    let body = cuerpos[veredicto.motivo] || _t("Venta a crédito no permitida.");
    if (veredicto.motivo === "sin_credito") {
        body = body.replace("%s", veredicto.cliente);
    } else if (veredicto.motivo === "excede") {
        body = body
            .replace("%s", veredicto.cliente)
            .replace("%s", formatear(veredicto.limite))
            .replace("%s", formatear(veredicto.balance))
            .replace("%s", formatear(veredicto.disponible));
    }
    return { title: _t("Crédito no disponible"), body };
}

function montoCreditoDe(orden) {
    return orden.payment_ids
        .filter((pago) => pago.payment_method_id.type === "pay_later")
        .reduce((suma, pago) => suma + pago.amount, 0);
}

patch(PaymentScreen.prototype, {
    /** Aviso temprano: no dejar ni crear la línea de crédito si no procede. */
    async addNewPaymentLine(paymentMethod) {
        if (paymentMethod.type === "pay_later") {
            const orden = this.currentOrder;
            const monto = orden.getDefaultAmountDueToPayIn(paymentMethod);
            const veredicto = await veredictoCredito(
                this.pos,
                orden.getPartner()?.id,
                monto
            );
            if (!veredicto.permitido) {
                this.dialog.add(
                    AlertDialog,
                    mensajeCredito(veredicto, this.env.utils.formatCurrency)
                );
                return false;
            }
        }
        return await super.addNewPaymentLine(paymentMethod);
    },
});

patch(OrderPaymentValidation.prototype, {
    /** Compuerta final: re-verificar el total en líneas de crédito. */
    async isOrderValid(isForceValidate) {
        const montoCredito = montoCreditoDe(this.order);
        if (montoCredito > 0) {
            const veredicto = await veredictoCredito(
                this.pos,
                this.order.getPartner()?.id,
                montoCredito
            );
            if (!veredicto.permitido) {
                this.pos.dialog.add(
                    AlertDialog,
                    mensajeCredito(veredicto, this.pos.env.utils.formatCurrency)
                );
                return false;
            }
        }
        return await super.isOrderValid(isForceValidate);
    },
});

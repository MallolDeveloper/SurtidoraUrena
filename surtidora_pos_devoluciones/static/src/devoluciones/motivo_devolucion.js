import { patch } from "@web/core/utils/patch";
import { TicketScreen } from "@point_of_sale/app/screens/ticket_screen/ticket_screen";
import OrderPaymentValidation from "@point_of_sale/app/utils/order_payment_validation";
import { SelectionPopup } from "@point_of_sale/app/components/popups/selection_popup/selection_popup";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";

/**
 * Devoluciones con motivo obligatorio (REQ-V18 — en ADG el tipo de
 * devolución es obligatorio: inv_tipodev_oblig=True).
 *
 * Dos momentos, mismo principio que los demás candados Surtidora:
 * 1. Al tocar "Reembolsar" (aviso natural: la devolución arranca declarando
 *    su motivo, como en ADG).
 * 2. Al validar la orden — compuerta final: cubre el popup cancelado, el
 *    F5 a mitad de devolución, la línea negativa tecleada a mano (la
 *    "devolución sin factura" de ADG) y los presets de devolución.
 *
 * El motivo queda en la orden (campo real, sincroniza solo) y se imprime
 * en el recibo. Catálogo vacío o sin red NO frena el mostrador (RB-07),
 * pero avisa en pantalla para que la degradación sea visible.
 */

// Exportada: el candado de la devolución en EFECTIVO usa exactamente el
// mismo criterio. Duplicarlo sería garantizar que un día divergen.
export function esDevolucion(orden) {
    // Reembolso formal, preset de devolución, o línea negativa manual.
    // Las líneas negativas de pos_sale (anticipos/liquidación de
    // cotización) NO son devolución: llevan referencia a la venta origen.
    return (
        orden.isRefund ||
        orden.preset_id?.is_return === true ||
        (orden.lines || []).some(
            (linea) =>
                linea.refunded_orderline_id ||
                (linea.qty < 0 &&
                    !linea.sale_order_line_id &&
                    !linea.sale_order_origin_id)
        )
    );
}

function motivosDisponibles(pos) {
    const modelo = pos.models["surtidora.motivo.devolucion"];
    return (modelo ? modelo.getAll() : [])
        .filter((motivo) => motivo.active !== false)
        .sort((a, b) => a.sequence - b.sequence || a.id - b.id);
}

async function refrescarCatalogo(pos) {
    // Trae el catálogo fresco en cada devolución (~7/día, costo nulo):
    // cubre el terminal cuya sesión abierta quedó cacheada sin el catálogo
    // (instalación con sesión abierta + F5) y depura del caché los motivos
    // archivados (la carga incremental del POS nunca los purga). El domain
    // explícito sobre active trae TAMBIÉN los archivados, para que el
    // registro cacheado se actualice a active=False y el filtro lo saque.
    try {
        await pos.data.searchRead(
            "surtidora.motivo.devolucion",
            ["|", ["active", "=", true], ["active", "=", false]],
            ["id", "name", "sequence", "nota", "active"]
        );
    } catch {
        // sin red: se usa lo cacheado (RB-07)
    }
}

async function pedirMotivoDevolucion(pos, dialog) {
    await refrescarCatalogo(pos);
    const motivos = motivosDisponibles(pos);
    if (!motivos.length) {
        // fail-open deliberado (RB-07: el mostrador no se detiene), pero
        // VISIBLE: sin este aviso, un catálogo vaciado apagaría el control
        // en silencio hasta que alguien audite el backend
        pos.notification?.add(
            _t(
                "No hay catálogo de motivos: la devolución saldrá SIN motivo. " +
                    "Avise al encargado."
            ),
            { type: "warning" }
        );
        return null;
    }
    return await makeAwaitable(dialog, SelectionPopup, {
        title: _t("Motivo de la devolución"),
        list: motivos.map((motivo) => ({
            id: motivo.id,
            label: motivo.name,
            description: motivo.nota || undefined,
            item: motivo,
            isSelected: false,
        })),
    });
}

patch(TicketScreen.prototype, {
    /** La devolución arranca declarando su motivo (flujo ADG). */
    async addAdditionalRefundInfo(order, destinationOrder) {
        // una orden vacía reciclada puede traer el motivo de una devolución
        // abortada — nunca heredarlo: sin selección, la compuerta final
        // vuelve a exigirlo
        destinationOrder.surtidora_motivo_dev_id = false;
        const motivo = await pedirMotivoDevolucion(this.pos, this.dialog);
        if (motivo) {
            destinationOrder.surtidora_motivo_dev_id = motivo;
        }
        return await super.addAdditionalRefundInfo(order, destinationOrder);
    },
});

patch(OrderPaymentValidation.prototype, {
    /** Compuerta final: sin motivo no hay devolución. */
    async isOrderValid(isForceValidate) {
        if (esDevolucion(this.order) && !this.order.surtidora_motivo_dev_id) {
            const motivo = await pedirMotivoDevolucion(this.pos, this.pos.dialog);
            if (motivo) {
                this.order.surtidora_motivo_dev_id = motivo;
            } else if (motivosDisponibles(this.pos).length) {
                this.pos.dialog.add(AlertDialog, {
                    title: _t("Devolución sin motivo"),
                    body: _t(
                        "Toda devolución debe registrar su motivo. " +
                            "Seleccione el motivo para poder continuar."
                    ),
                });
                return false;
            }
        }
        return await super.isOrderValid(isForceValidate);
    },
});

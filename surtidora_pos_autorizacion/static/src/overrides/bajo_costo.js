import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { PosOrderline } from "@point_of_sale/app/models/pos_order_line";
import OrderPaymentValidation from "@point_of_sale/app/utils/order_payment_validation";
import { SelectionPopup } from "@point_of_sale/app/components/popups/selection_popup/selection_popup";
import { NumberPopup } from "@point_of_sale/app/components/popups/number_popup/number_popup";
import { ask, makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";

/**
 * Bloqueo de venta BAJO COSTO en el mostrador (punto 5, reunión 7-ago).
 *
 * Dos tiempos, porque el numpad aplica el precio tecla a tecla (escribir
 * "150" pasa por 1 y 15 — un diálogo por tecla sería insufrible):
 *
 * 1. MIENTRAS TECLEA: la línea se pinta de rojo al instante (getter
 *    reactivo surtiBajoCosto + template de la línea). El aviso destacado.
 * 2. AL COBRAR: compuerta dura. La excepción (mercancía por vencer que se
 *    remata en vez de botarla) exige motivo del catálogo + PIN de
 *    supervisor + doble confirmación, y queda auditada. El PIN se valida
 *    en el servidor; sin conexión no hay excepción.
 *
 * La comparación es la misma regla RB-08 del backend, y va SIN ITBIS en los
 * dos lados. Esto no es un detalle: el ITBIS de Surtidora está configurado
 * como incluido en el precio, así que `price_unit` LLEVA el 18% mientras que
 * `standard_price` no lo lleva. Compararlos de frente regalaba una franja
 * entera del 18% — un artículo de costo 76.27 (piso real 90.00 con ITBIS) se
 * podía cobrar a 76.28 sin que la línea se pintara de rojo ni se pidiera PIN.
 * El propio Odoo hace esta resta antes de mostrar el margen en "Info del
 * producto": priceWithoutTax = tax_details.total_excluded.
 */

patch(PosOrderline.prototype, {
    /** Costo del producto en unidad base (0 = sin costo configurado). */
    get surtiCosto() {
        return this.product_id?.standard_price || 0;
    },

    /** Precio por unidad en la MISMA base que el costo: con el descuento
     * aplicado y SIN impuestos. Odoo ya lo calcula por línea. */
    get surtiPrecioEfectivo() {
        try {
            const unitario = this.unitPrices;
            if (unitario && typeof unitario.total_excluded === "number") {
                return unitario.total_excluded;
            }
        } catch {
            // la línea todavía no entró en el cálculo de impuestos del pedido
        }
        // Respaldo: se descuenta a mano la tasa de los impuestos que van
        // INCLUIDOS en el precio (los que se cobran aparte no inflan price_unit).
        const incluidos = (this.tax_ids || []).filter(
            (t) => t.price_include && t.amount_type === "percent");
        const tasa = incluidos.reduce((suma, t) => suma + (t.amount || 0), 0);
        const bruto = this.price_unit * (1 - (this.getDiscount() || 0) / 100);
        return bruto / (1 + tasa / 100);
    },

    /** El mismo precio efectivo pero CON impuestos. Es la base en la que el
     * backend graba `surtidora.autorizacion.precio` (price_reduce_taxinc) y
     * en la que viene el precio de tarifa; mezclarlas hacía que una misma
     * rebaja se viera 13 puntos mayor si venía del mostrador. */
    get surtiPrecioEfectivoConItbis() {
        try {
            const unitario = this.unitPrices;
            if (unitario && typeof unitario.total_included === "number") {
                return unitario.total_included;
            }
        } catch {
            // la línea todavía no entró en el cálculo de impuestos del pedido
        }
        return this.price_unit * (1 - (this.getDiscount() || 0) / 100);
    },

    /** ¿La línea está por debajo del costo? (pinta el rojo del template)
     *
     * La línea del producto combo es una CABECERA: Odoo la deja en 0.00 y
     * reparte el dinero en las hijas, que sí llevan producto y costo reales
     * y sí se revisan una por una. Medirla contra el costo bloquearía TODA
     * venta de combo en cuanto alguien le ponga costo al combo — algo muy
     * natural de hacer. `combo_line_ids` es como el propio Odoo distingue
     * la cabecera. */
    get surtiBajoCosto() {
        if (this.combo_line_ids?.length) {
            return false;
        }
        const costo = this.surtiCosto;
        return costo > 0 && this.surtiPrecioEfectivo < costo - 0.005;
    },
});

patch(OrderPaymentValidation.prototype, {
    async isOrderValid(isForceValidate) {
        const pendientes = this._surtiLineasBajoCosto();
        if (pendientes.length && !(await this._surtiExcepcionBajoCosto(pendientes))) {
            return false;
        }
        return await super.isOrderValid(...arguments);
    },

    /** Líneas bajo costo SIN autorización vigente (si el precio bajó más
     * después de autorizar, se re-autoriza — misma regla del backend). */
    _surtiLineasBajoCosto() {
        const ok = this.order.uiState.surtiBajoCostoOk || {};
        return this.order.lines.filter(
            (linea) =>
                linea.surtiBajoCosto &&
                !(ok[linea.uuid] !== undefined &&
                    linea.surtiPrecioEfectivo >= ok[linea.uuid] - 0.005)
        );
    },

    /** Flujo completo de la excepción. Devuelve true si quedó autorizada. */
    async _surtiExcepcionBajoCosto(lineas) {
        const dialog = this.pos.dialog;
        const fmt = (v) => this.pos.env.utils.formatCurrency(v);
        const detalle = lineas
            .map((l) => `• ${l.product_id.display_name}: ${fmt(l.surtiPrecioEfectivo)} ` +
                `${_t("sin ITBIS (costo")} ${fmt(l.surtiCosto)})`)
            .join("\n");

        // 1. Aviso rojo con la puerta a la excepción
        const abrir = await ask(dialog, {
            title: _t("⛔ VENTA BAJO COSTO"),
            body: _t("Bloqueada: hay productos por debajo del costo.\n\n%s\n\n" +
                "¿Autorizar una excepción? (requiere motivo y PIN de supervisor)", detalle),
            confirmLabel: _t("Autorizar excepción..."),
            cancelLabel: _t("Corregir la venta"),
        });
        if (!abrir) {
            return false;
        }

        // 2. Motivo del catálogo (punto 6: se elige, no se escribe)
        let motivos;
        try {
            motivos = await this.pos.data.call("surtidora.pos.autorizacion", "motivos", []);
        } catch {
            motivos = [];
        }
        if (!motivos.length) {
            dialog.add(AlertDialog, {
                title: _t("Sin conexión o sin motivos"),
                body: _t("No se pudo cargar el catálogo de motivos. La excepción " +
                    "bajo costo no puede autorizarse sin conexión."),
            });
            return false;
        }
        const motivo = await makeAwaitable(dialog, SelectionPopup, {
            title: _t("Motivo de la excepción"),
            list: motivos.map((m) => ({ id: m.id, label: m.nombre, item: m })),
        });
        if (!motivo) {
            return false;
        }

        // 3. PIN del supervisor (enmascarado; se valida en el servidor)
        const pin = await makeAwaitable(dialog, NumberPopup, {
            title: _t("PIN del supervisor"),
            formatDisplayedValue: (v) => "•".repeat(String(v).length),
        });
        if (!pin) {
            return false;
        }

        // 4. Doble confirmación — el "¿estás seguro?" que pidió Adelso
        const seguro = await ask(dialog, {
            title: _t("¿Está seguro?"),
            body: _t('Se venderá BAJO COSTO por "%s". Quedará registrado ' +
                "a nombre del supervisor que autoriza.", motivo.nombre),
            confirmLabel: _t("Sí, autorizar"),
            cancelLabel: _t("No"),
        });
        if (!seguro) {
            return false;
        }

        // 5. Validación del PIN + auditoría, en una sola llamada
        let resultado;
        try {
            resultado = await this.pos.data.call(
                "surtidora.pos.autorizacion", "autorizar_bajo_costo", [
                    String(pin),
                    motivo.id,
                    "",
                    this.order.pos_reference || this.order.name || "",
                    this.order.getPartner()?.id || false,
                    lineas.map((l) => ({
                        product_id: l.product_id.id,
                        precio: l.surtiPrecioEfectivoConItbis,
                        precio_lista: this._surtiPrecioLista(l),
                        cantidad: l.qty,
                    })),
                ]);
        } catch {
            resultado = { ok: false };
        }
        if (!resultado.ok) {
            dialog.add(AlertDialog, {
                title: resultado.mensaje ? _t("Autorización bloqueada") : _t("PIN incorrecto"),
                body: resultado.mensaje ||
                    _t("El PIN no corresponde a ningún autorizador de precios."),
            });
            return false;
        }

        const ok = this.order.uiState.surtiBajoCostoOk || {};
        for (const linea of lineas) {
            ok[linea.uuid] = linea.surtiPrecioEfectivo;
        }
        this.order.uiState.surtiBajoCostoOk = ok;
        this.pos.notification.add(
            _t("Excepción bajo costo autorizada por %s", resultado.autorizador),
            { type: "success" });
        return true;
    },

    _surtiPrecioLista(linea) {
        try {
            const tmpl = linea.product_id.product_tmpl_id;
            return tmpl.getPrice(this.order.pricelist_id, 1, 0);
        } catch {
            return 0;
        }
    },
});

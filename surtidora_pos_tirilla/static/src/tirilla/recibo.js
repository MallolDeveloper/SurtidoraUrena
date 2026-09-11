import { patch } from "@web/core/utils/patch";
import { ReceiptHeader } from "@point_of_sale/app/screens/receipt_screen/receipt/receipt_header/receipt_header";
import { OrderReceipt } from "@point_of_sale/app/screens/receipt_screen/receipt/order_receipt";

/**
 * Lo que la tirilla de ADG trae y el recibo nativo no (11-sep-2026, con
 * las dos impresas al lado): el título que dice CÓMO se vendió, el número
 * de la venta grande y en código de barras, y el conteo de renglones.
 *
 * Aquí solo se calculan los valores; dónde y cómo se pintan está en
 * tirilla.xml y tirilla.scss.
 */

/** Ancho del código de barras en píxeles CSS: el recibo se imprime a 266
 * px de ancho (point_of_sale/receipt_screen.scss), y el código va con
 * margen a cada lado para que el lector lo tome de una. */
const ANCHO_CODIGO_BARRAS = 220;
const ALTO_CODIGO_BARRAS = 44;

patch(ReceiptHeader.prototype, {
    /**
     * Crédito = se pagó (al menos en parte) con un método que difiere el
     * cobro y NO es bono. Es la misma regla con la que surtidora_pos_credito
     * mide el crédito consumido en la sesión: `pay_later` sin
     * `surtidora_es_bono`. Si ese módulo no está, el bono no se distingue y
     * cualquier pago diferido cuenta como crédito — se degrada, no se rompe.
     */
    get surtidoraEsCredito() {
        return (this.order.payment_ids || []).some(
            (pago) =>
                pago.amount > 0 &&
                pago.payment_method_id?.type === "pay_later" &&
                !pago.payment_method_id?.surtidora_es_bono
        );
    },

    get surtidoraTitulo() {
        return this.surtidoraEsCredito ? "FACTURA A CRÉDITO" : "FACTURA A CONTADO";
    },

    /**
     * El número de la venta como Code128, para escanear el recibo en una
     * devolución en vez de teclearlo. Se usa el generador de códigos del
     * propio servidor, el mismo de las etiquetas de producto; el POS está
     * en línea y `printWeb` espera a que las imágenes carguen antes de
     * imprimir. Code128 y no EAN: la referencia lleva guiones
     * («265-1-000003») y Code128 la encoda tal cual.
     */
    get surtidoraCodigoBarras() {
        const referencia = this.order.pos_reference;
        if (!referencia) {
            return "";
        }
        return (
            `/report/barcode/?barcode_type=Code128&value=${encodeURIComponent(referencia)}` +
            `&width=${ANCHO_CODIGO_BARRAS * 2}&height=${ALTO_CODIGO_BARRAS * 2}&humanreadable=0`
        );
    },
});

patch(OrderReceipt.prototype, {
    /** Renglones vendidos, como el «ITEMS: 16» de ADG: líneas, no unidades.
     * Un combo cuenta una vez (por su padre), no por cada componente. */
    get surtidoraItems() {
        return (this.order.lines || []).filter((linea) => linea.qty && !linea.combo_parent_id)
            .length;
    },
});

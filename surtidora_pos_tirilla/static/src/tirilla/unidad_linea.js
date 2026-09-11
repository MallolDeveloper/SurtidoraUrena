import { patch } from "@web/core/utils/patch";
import { Orderline } from "@point_of_sale/app/components/orderline/orderline";

/**
 * Debajo de cada línea de la tirilla va SOLO el tipo de empaque.
 *
 * La tirilla la lee el despachador, y lo que tiene que ver de un vistazo es
 * si son cajas, paquetes, docenas o unidades sueltas — no a cuánto sale el
 * paquete ni cuántos trae. El renglón nativo mezclaba las tres cosas
 * ("RD$ 1,140.00 / Paquete de 60 (Unidad)"). Pedido del cliente el
 * 11-sep-2026, con la tirilla impresa al lado de la de ADG, y afinado el
 * mismo día: «CAJA» a secas, sin el "de 60 (Paquete)".
 *
 * QUÉ SE ESCRIBE. La primera palabra del nombre de la unidad: «Caja de 60
 * (Paquete)» → CAJA, «Fardo de 2 (Paquete)» → FARDO, «Docena» → DOCENA. En
 * esta base la primera palabra es siempre el tipo (medido: Caja, Paquete,
 * Unidad, Fardo, Docena, Pote, Tarro, Libra, Saco, Cajita, Gruesa…), así
 * que no hace falta un catálogo aparte. Cuántos trae ya lo dice el nombre
 * del producto («ALKA SELTZER 36/60»).
 *
 * CÓMO SE VE cada tipo lo decide el CSS (tirilla.scss), no este archivo:
 * aquí solo se emite una clase por tipo — surti-unidad-caja,
 * surti-unidad-paquete, surti-unidad-docena… — y el estilo (negrita para
 * paquete, negrita cursiva para docena, normal para el resto) vive donde
 * viven los estilos. Resaltar un tipo nuevo es una línea de CSS.
 *
 * QUÉ UNIDAD SE ROTULA lo decide surtidora_pos_empaques: si presentó la
 * línea como "1 Caja de 60", aquí dice CAJA; si la dejó en unidad base
 * (fracción de empaque sin precio fijado), dice la base. Esa decisión llega
 * en `vals.surtidoraEmpaque` y no se recalcula aquí — por eso el módulo
 * depende de empaques, para que su parche corra antes.
 *
 * Solo en el recibo. Carrito y reembolsos conservan el renglón nativo.
 */

/** «Caja de 60 (Paquete)» → «Caja». */
function tipoDeEmpaque(nombreUnidad) {
    return (nombreUnidad || "").trim().split(/\s+/)[0] || "";
}

/** «Cajón» → «cajon», «Libra(S)» → «libra-s»: apto para nombre de clase. */
function claseDe(tipo) {
    const sinAcentos = tipo.normalize("NFD").replace(/[\u0300-\u036f]/g, "");
    return sinAcentos.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

patch(Orderline.prototype, {
    get lineScreenValues() {
        const vals = super.lineScreenValues;
        if (this.props.mode !== "receipt" || !this.line?.order_id) {
            return vals;
        }
        const tipo = tipoDeEmpaque(
            vals.surtidoraEmpaque || this.line.product_id?.uom_id?.name
        );
        vals.surtidoraUnidad = tipo;
        vals.surtidoraUnidadClase = tipo ? `surti-unidad-${claseDe(tipo)}` : "";
        // sin el renglón de precio: el empaque va solo
        vals.displayPriceUnit = false;
        return vals;
    },
});

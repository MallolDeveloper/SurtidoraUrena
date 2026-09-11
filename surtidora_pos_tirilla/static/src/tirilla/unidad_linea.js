import { patch } from "@web/core/utils/patch";
import { Orderline } from "@point_of_sale/app/components/orderline/orderline";

/**
 * Debajo de cada línea de la tirilla va SOLO el empaque, en negrita.
 *
 * La tirilla la lee el despachador, y lo que tiene que ver de un vistazo es
 * si son cajas, paquetes o unidades sueltas — no a cuánto sale el paquete.
 * El renglón nativo mezclaba las dos cosas ("RD$ 1,140.00 / Paquete de 60")
 * y el precio, que no le sirve a quien despacha, le quitaba peso a lo que sí.
 * Pedido del cliente el 11-sep-2026, viendo la tirilla impresa al lado de
 * la de ADG.
 *
 * QUÉ UNIDAD SE ROTULA. La misma que ya decide surtidora_pos_empaques: si
 * presentó la línea como "1 Caja de 8", aquí dice «Caja de 8»; si la dejó en
 * unidad base (fracción de empaque sin precio fijado), dice la unidad base.
 * Esa decisión llega en `vals.surtidoraEmpaque`; no se recalcula aquí para
 * no tener dos reglas que un día se contradigan. Por eso el módulo depende
 * de surtidora_pos_empaques: el parche de allá tiene que correr antes.
 *
 * Solo en el recibo. El carrito y la pantalla de reembolsos siguen con su
 * renglón nativo: ahí el precio unitario sí le importa a la cajera.
 */
patch(Orderline.prototype, {
    get lineScreenValues() {
        const vals = super.lineScreenValues;
        if (this.props.mode !== "receipt" || !this.line?.order_id) {
            return vals;
        }
        vals.surtidoraUnidad =
            vals.surtidoraEmpaque || this.line.product_id?.uom_id?.name || "";
        // sin el renglón de precio: el empaque va solo y en negrita
        vals.displayPriceUnit = false;
        return vals;
    },
});

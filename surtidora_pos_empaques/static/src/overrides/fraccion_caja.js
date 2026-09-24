import { patch } from "@web/core/utils/patch";
import { PosOrderline } from "@point_of_sale/app/models/pos_order_line";

/**
 * Fracciones de empaque (RB-09 / REQ-V23): una sola lista y una sola regla
 * para quien las OFRECE (el selector de unidad) y quien revisa su PRECIO
 * (RB-01). La tirilla (orderline_empaque.js) decide aparte cómo ROTULAR la
 * línea («0.50 Caja»); ese criterio es de presentación, no de precio, y no
 * se mezcla con este.
 *
 * El selector de unidad ofrece ¼, ½ y ¾ del empaque A PRECIO DE EMPAQUE
 * (½ caja de 18 = 9 paquetes a 43.89, no a los 47.00 del suelto). Pero la
 * línea queda en unidad base —9 paquetes—, y para cualquiera que la mire
 * después es indistinguible de 9 paquetes sueltos rebajados. RB-01 (bajo
 * lista, en surtidora_pos_autorizacion) le preguntaba a la tarifa con 9, la
 * regla por cantidad (mín. 18) no aplicaba, comparaba contra el suelto y
 * pedía PIN en TODA venta de fracción, por una rebaja que nadie hizo.
 *
 * Por eso la regla de qué es una fracción legítima vive aquí, junto al
 * selector que la crea, y se publica en la línea (`surtidoraFactorFraccion`)
 * para que la regla de precios la lea sin recalcularla: dos copias de la
 * lista de fracciones terminarían diciendo cosas distintas.
 */
export const FRACCIONES = [
    { f: 0.25, txt: "¼" },
    { f: 0.5, txt: "½" },
    { f: 0.75, txt: "¾" },
];

/** Fracciones que se ofrecen para un empaque de `factor` unidades base.
 * Solo las que dan unidades ENTERAS: caja de 24 → 6/12/18; caja de 18 →
 * solo ½ = 9 (medio paquete no existe en el anaquel). */
export function fraccionesDeEmpaque(factor) {
    return FRACCIONES.map(({ f, txt }) => ({ f, txt, qty: factor * f })).filter(({ qty }) =>
        Number.isInteger(qty)
    );
}

/** Factor del empaque si la línea es una fracción legítima; 0 si no.
 *
 * Legítima = las tres cosas a la vez:
 * - el producto está marcado «La caja se fracciona»;
 * - la línea recuerda el empaque en que se vendió (`surtidora_uom_venta_id`).
 *   Lo ponen el selector (al elegir un empaque o una fracción) y el escaneo
 *   del código del empaque; la línea suelta no lo lleva;
 * - la cantidad es exactamente una de las fracciones que ese empaque ofrece.
 *
 * Una caja (del selector o escaneada) a la que la cajera le cambia la
 * cantidad a mano JUSTO a una fracción (18 → 9) también pasa. Se acepta
 * así porque equivale a elegir «½ caja» en el selector (RB-09): no abre
 * ningún precio que el selector no dé ya. Cualquier otra cantidad (7, 4.5,
 * 73) no pasa y la tarifa se consulta con esa cantidad, como cualquier línea.
 *
 * Una línea SUELTA de 9 paquetes (tocada como «Paquete», escaneada con el
 * código del paquete o con la cantidad tecleada) no lleva empaque y no
 * pasa: sigue siendo suelta. */
export function factorDeFraccion(linea) {
    const factor = linea.surtidora_uom_venta_id?.relative_factor;
    if (!factor || factor <= 1) {
        return 0;
    }
    if (!linea.product_id?.product_tmpl_id?.surtidora_caja_fraccionable) {
        return 0;
    }
    const esFraccion = fraccionesDeEmpaque(factor).some(
        ({ qty }) => Math.abs(linea.qty - qty) < 0.0001
    );
    return esFraccion ? factor : 0;
}

patch(PosOrderline.prototype, {
    /** Factor del empaque del que esta línea es fracción (18 en ½ caja de
     * 18), o 0 si no es una fracción. Lo lee RB-01 para cotizar la línea
     * como el empaque completo. */
    get surtidoraFactorFraccion() {
        return factorDeFraccion(this);
    },
});

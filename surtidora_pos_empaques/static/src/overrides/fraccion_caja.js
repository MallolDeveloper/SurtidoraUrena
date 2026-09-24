import { patch } from "@web/core/utils/patch";
import { PosOrderline } from "@point_of_sale/app/models/pos_order_line";

/**
 * Fracciones de empaque (RB-09 / REQ-V23): UNA sola verdad para quien las
 * ofrece y para quien las revisa.
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
 * Legítima = las tres cosas que solo el selector junta:
 * - el producto está marcado «La caja se fracciona»;
 * - la línea recuerda el empaque en que se vendió (`surtidora_uom_venta_id`,
 *   que solo ponen el selector y el escaneo del empaque);
 * - la cantidad es exactamente una de las fracciones que ese empaque ofrece.
 *
 * Una línea SUELTA de 9 paquetes (tocada como «Paquete», escaneada o con la
 * cantidad tecleada) no lleva empaque y no pasa: sigue siendo suelta. */
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

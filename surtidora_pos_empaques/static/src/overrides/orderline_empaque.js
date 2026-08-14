import { patch } from "@web/core/utils/patch";
import { Orderline } from "@point_of_sale/app/components/orderline/orderline";
import { formatCurrency } from "@web/core/currency";

/**
 * La línea del RECIBO se presenta en el empaque que se vendió (REQ-V16).
 *
 * Internamente la línea guarda 18 paquetes a 48.89 — así lo necesitan el
 * inventario y la tarifa —, pero el cliente compró "1 caja a 880.00" y así
 * lo dice la factura de ADG (captura 20: unidad CAJA, cantidad 1.00).
 *
 * SOLO EL RECIBO (revisión adversaria 14-ago). El mismo componente pinta
 * el carrito y la pantalla de reembolsos, y ahí todo lo demás sigue en
 * unidad base: el numpad, el contador de artículos y la cantidad a
 * devolver. Presentar "1" donde la cajera teclea 18 hacía que devolver
 * una caja devolviera un solo paquete — plata mal devuelta.
 */

/** Cuántos empaques representa la línea, o null si no se puede presentar
 * así con honestidad. */
function empaquesDe(linea) {
    const uom = linea.surtidora_uom_venta_id;
    const factor = uom?.relative_factor;
    if (!factor || factor <= 1) {
        return null;
    }
    const cantidad = linea.qty / factor;
    // Cajas COMPLETAS siempre; fracciones solo si el precio quedó fijado
    // por el popup (price_type "manual"). Si la cajera cambió la cantidad
    // a mano, el núcleo REPRECIA la línea a precio suelto: multiplicar ese
    // precio por el factor publicaría un precio de caja que no existe en
    // ninguna lista, así que ahí se dice la verdad en unidades base.
    const entera = Math.abs(cantidad - Math.round(cantidad)) < 0.0001;
    if (!entera && linea.price_type !== "manual") {
        return null;
    }
    return { cantidad, uom, factor };
}

patch(Orderline.prototype, {
    get lineScreenValues() {
        const vals = super.lineScreenValues;
        // fuera del recibo NO se toca nada (ver cabecera)
        if (this.props.mode !== "receipt" || this.props.basic_receipt) {
            return vals;
        }
        const linea = this.line;
        if (!linea?.order_id) {
            return vals;
        }
        const empaque = empaquesDe(linea);
        if (!empaque) {
            return vals;
        }
        // cantidad: "1" o "0.50" (media caja) — el núcleo parte la cifra en
        // entero y decimales para pintar los decimales más chicos
        const absoluto = Math.abs(empaque.cantidad);
        const entero = Math.trunc(empaque.cantidad);
        const decimales = Math.round((absoluto - Math.trunc(absoluto)) * 100);
        vals.unitPart = String(entero === 0 && empaque.cantidad < 0 ? "-0" : entero);
        vals.decimalPart = decimales ? `.${String(decimales).padStart(2, "0")}` : "";
        // precio del empaque completo, con el descuento de la línea aplicado
        // para que nunca contradiga el total que imprime el propio núcleo
        const efectivo = linea.price_unit * (1 - (linea.discount || 0) / 100);
        vals.displayPriceUnit = `${formatCurrency(
            efectivo * empaque.factor,
            linea.currency.id
        )} / ${empaque.uom.name}`;
        return vals;
    },
});

import { patch } from "@web/core/utils/patch";
import { PosOrderline } from "@point_of_sale/app/models/pos_order_line";

/**
 * Dos líneas del mismo producto se juntan solo si se vendieron en la MISMA
 * unidad de venta (REQ-V05/V24).
 *
 * La línea guarda la cantidad en unidad base (18 paquetes) y, aparte, en qué
 * empaque se vendió (`surtidora_uom_venta_id`: «Caja de 18»; vacío = la
 * unidad suelta, sea escaneada o elegida en el popup). El núcleo decide si
 * junta mirando producto, precio y tipo de precio, pero no ese dato: con
 * «Agrupar en el punto de venta» encendido en la unidad base, «1 caja» y
 * «1 paquete suelto» del mismo producto se fundirían en 19 paquetes
 * rotulados como caja en la tirilla.
 *
 * Con esto, escanear dos veces el mismo producto da UNA línea con cantidad 2
 * (como ADG: solo el 4.1 % de sus facturas repite producto y unidad, medido
 * ago-sep 2026), y la caja y el suelto quedan en líneas separadas.
 */
patch(PosOrderline.prototype, {
    canBeMergedWith(otra) {
        if (unidadDeVenta(this) !== unidadDeVenta(otra)) {
            return false;
        }
        return super.canBeMergedWith(...arguments);
    },
});

function unidadDeVenta(linea) {
    return linea.surtidora_uom_venta_id?.id || false;
}

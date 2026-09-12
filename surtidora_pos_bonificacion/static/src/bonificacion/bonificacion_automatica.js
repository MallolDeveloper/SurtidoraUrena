import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/services/pos_store";

/**
 * La bonificación entra SOLA al llegar a la cantidad, como en ADG
 * (REQ-V09/V10).
 *
 * En ADG «compra N, lleva M gratis» es una línea que el sistema inserta al
 * alcanzar la cantidad de la regla. El pos_loyalty de Odoo tiene la misma
 * regla («Compra X Obtén Y») pero solo pone gratis un producto que YA está
 * en la orden:
 *
 *     return Math.min(available, freeQty) - claimed;   // _computeUnclaimedFreeProductQty
 *
 * Con la caja de 18 Saltinas en pantalla el Dekreme no aparece hasta que la
 * cajera lo agrega, o lo pide por ⋮ → Recompensa. Verificado en SurtidoraDev
 * el 11-sep-2026, en pantalla y en el bundle desplegado.
 *
 * Este parche hace lo que haría la cajera, en el acto: cuando las unidades
 * PAGADAS alcanzan la cantidad de la regla, agrega a la orden las unidades
 * del premio marcadas con `surtidora_premio_id`, y el núcleo las pone
 * gratis por su vía normal (el `addLineToCurrentOrder` de pos_loyalty
 * aplica el premio al producto que entra). Si la cajera baja la cantidad,
 * las bonificadas que sobran se retiran solas.
 *
 * Solo toca la bonificación clásica: programa «Compra X Obtén Y»,
 * automático, un solo premio de un solo producto, reglas por unidad. Todo lo
 * demás (descuentos, cupones, puntos, premios por etiqueta) sigue en manos
 * del núcleo tal cual.
 *
 * Semántica (la de ADG): lo que la cajera teclea es lo que el cliente PAGA;
 * las gratis van encima. En un 3x2, teclear 2 trae la tercera y teclear 3
 * trae una cuarta. El núcleo, solo, habría hecho gratis una de las 3.
 *
 * Se engancha en `updateRewards`, que es por donde pasa cualquier cambio de
 * la orden que pueda mover un premio (agregar línea, numpad, escaneo,
 * cliente, lista de precios, restablecer programas).
 */
patch(PosStore.prototype, {
    updateRewards() {
        const resultado = super.updateRewards(...arguments);
        // el núcleo a secas, para volver a casar sus premios tras un ajuste
        // sin pasar otra vez por este parche
        const nucleo = () => super.updateRewards();
        this._surtiBonificarAutomatico(nucleo);
        return resultado;
    },

    /**
     * Una pasada a la vez. Si llega otro cambio mientras se está ajustando
     * (la cajera sigue tecleando, o la propia línea que se agrega dispara
     * otro `updateRewards`), se repite UNA pasada al terminar; converge
     * porque una pasada sin cambios no dispara nada.
     */
    async _surtiBonificarAutomatico(nucleo) {
        if (this._surtiBonificando) {
            this._surtiRepetirBonificacion = true;
            return;
        }
        this._surtiBonificando = true;
        try {
            let vueltas = 0;
            do {
                this._surtiRepetirBonificacion = false;
                await this._surtiUnaPasadaDeBonificacion(nucleo);
            } while (this._surtiRepetirBonificacion && ++vueltas < 5);
        } finally {
            this._surtiBonificando = false;
        }
    },

    async _surtiUnaPasadaDeBonificacion(nucleo) {
        const orden = this.getOrder();
        if (!this._surtiOrdenBonificable(orden)) {
            return;
        }
        // puntos al día antes de decidir (misma espera que hace el núcleo)
        await this.orderUpdateLoyaltyPrograms();
        let cambio = false;
        for (const bono of this._surtiBonificacionesActivas(orden)) {
            cambio = (await this._surtiAjustarBonificacion(orden, bono)) || cambio;
        }
        if (cambio) {
            nucleo();
        }
    },

    _surtiOrdenBonificable(orden) {
        return (
            Boolean(orden) &&
            !orden.finalized &&
            this.models["loyalty.program"].length > 0 &&
            // devoluciones y líneas negativas: ahí no se regala nada
            !orden.lines.some((linea) => linea.getQuantity() < 0)
        );
    },

    /**
     * Programas «compra N, lleva M gratis» que hay que mirar en esta orden:
     * los que están dando puntos ahora mismo, y además los que ya metieron
     * unidades gratis aunque ya no den puntos. Cuando la venta baja de la
     * cantidad, el núcleo saca al programa de `couponPointChanges` y borra su
     * línea de premio; si no se mira también por las líneas bonificadas, la
     * unidad regalada se queda en la orden convertida en pagada.
     */
    _surtiBonificacionesActivas(orden) {
        const bonos = new Map();
        for (const cambio of Object.values(orden.uiState.couponPointChanges)) {
            const programa = this.models["loyalty.program"].get(cambio.program_id);
            const premio = programa && this._surtiPremioDeBonificacion(programa);
            if (premio) {
                bonos.set(programa.id, { programa, premio, coupon_id: cambio.coupon_id });
            }
        }
        for (const linea of orden.lines) {
            const premio = linea.surtidora_premio_id;
            const programa = premio?.program_id;
            if (programa && !bonos.has(programa.id)) {
                // sin cupón vivo: no le corresponden unidades gratis
                bonos.set(programa.id, { programa, premio, coupon_id: null });
            }
        }
        return [...bonos.values()];
    },

    /** El único premio del programa si es una bonificación clásica; si no, null. */
    _surtiPremioDeBonificacion(programa) {
        const esBonificacion =
            programa.program_type === "buy_x_get_y" &&
            programa.trigger === "auto" &&
            programa.applies_on === "current" &&
            !programa.is_nominative &&
            programa.reward_ids.length === 1 &&
            programa.rule_ids.every((regla) => regla.reward_point_mode === "unit");
        if (!esBonificacion) {
            return null;
        }
        const premio = programa.reward_ids[0];
        const unProducto =
            premio.reward_type === "product" && !premio.multi_product && premio.reward_product_id;
        return unProducto ? premio : null;
    },

    /** Deja en la orden exactamente las unidades gratis que corresponden. */
    async _surtiAjustarBonificacion(orden, { programa, premio, coupon_id }) {
        const lineasBono = this._surtiLineasBonificadas(orden, premio);
        const puestas = lineasBono.reduce((suma, linea) => suma + linea.getQuantity(), 0);
        // la cajera borró la bonificación a mano: renunció al premio en esta orden
        const debidas = orden.uiState.disabledRewards.has(premio.id)
            ? 0
            : this._surtiUnidadesDebidas(orden, programa, premio, coupon_id, puestas);
        if (debidas > puestas) {
            return await this._surtiAgregarBonificadas(premio, debidas - puestas);
        }
        if (debidas < puestas) {
            this._surtiRetirarBonificadas(orden, lineasBono, puestas - debidas);
            return true;
        }
        return false;
    },

    _surtiLineasBonificadas(orden, premio) {
        return orden.lines.filter((linea) => linea.surtidora_premio_id?.id === premio.id);
    },

    /**
     * Cuántas unidades gratis corresponden a lo que el cliente PAGA.
     *
     * Puntos ganados = puntos vivos + los ya gastados en premios de este
     * cupón. A eso se le quitan los puntos que generan las propias unidades
     * bonificadas cuando el premio es el mismo producto de la regla (3x2):
     * esas no se pagan, así que no bonifican. Con premio de otro producto
     * (Saltinas → Dekreme) la resta da cero porque el Dekreme no puntúa.
     */
    _surtiUnidadesDebidas(orden, programa, premio, coupon_id, puestas) {
        if (!coupon_id) {
            return 0;
        }
        const gastados = orden.lines
            .filter((linea) => linea.is_reward_line && linea.coupon_id?.id === coupon_id)
            .reduce((suma, linea) => suma + (linea.points_cost || 0), 0);
        const ganados = orden._getRealCouponPoints(coupon_id) + gastados;
        const pagados =
            ganados - puestas * this._surtiPuntosPorUnidad(programa, premio.reward_product_id);
        const requeridos = premio.required_points;
        if (!requeridos || pagados < requeridos) {
            return 0;
        }
        return Math.floor(pagados / requeridos) * (premio.reward_product_qty || 1);
    },

    /** Cuántos puntos da UNA unidad del producto bajo las reglas del programa. */
    _surtiPuntosPorUnidad(programa, producto) {
        return programa.rule_ids
            .filter((regla) => regla.any_product || regla.validProductIds?.has(producto.id))
            .reduce((suma, regla) => suma + (regla.reward_point_amount || 0), 0);
    },

    /**
     * Mismos `vals` que usa el botón Recompensa del núcleo, más la marca.
     * `configure=false`: nada de popups; el precio es el de la lista y el
     * premio del núcleo lo deja en cero.
     */
    async _surtiAgregarBonificadas(premio, cuantas) {
        const producto = premio.reward_product_id;
        const linea = await this.addLineToCurrentOrder(
            {
                product_id: producto,
                product_tmpl_id: producto.product_tmpl_id,
                qty: cuantas,
                surtidora_premio_id: premio,
            },
            {},
            false
        );
        return Boolean(linea);
    },

    /** Retira las que sobran, empezando por la última que se agregó. */
    _surtiRetirarBonificadas(orden, lineasBono, sobran) {
        for (const linea of [...lineasBono].reverse()) {
            if (sobran <= 0) {
                break;
            }
            const cantidad = linea.getQuantity();
            if (cantidad <= sobran) {
                orden.removeOrderline(linea);
                sobran -= cantidad;
            } else {
                linea.setQuantity(cantidad - sobran);
                sobran = 0;
            }
        }
    },
});

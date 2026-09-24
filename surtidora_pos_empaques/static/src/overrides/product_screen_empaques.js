import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { SelectionPopup } from "@point_of_sale/app/components/popups/selection_popup/selection_popup";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { fraccionesDeEmpaque } from "@surtidora_pos_empaques/overrides/fraccion_caja";

/**
 * Venta por empaque y fraccionamiento en el POS (Surtidora Ureña).
 *
 * 1. Al tocar un producto con empaques se pregunta la unidad, con el precio
 *    de cada una (REQ-V05/V24). El precio del empaque lo resuelve la regla
 *    por cantidad de la lista de precios (18 x 48.89 = 880).
 * 2. RB-09 / REQ-V23: si el producto tiene "la caja se fracciona", se ofrecen
 *    ¼, ½ y ¾ del empaque A PRECIO DE CAJA (½ caja de 18 = 9 und a 440, no a
 *    precio suelto). Solo fracciones que den unidades base enteras. La línea
 *    lleva precio manual (price_type) para que no se recalcule a precio suelto.
 * 3. Escanear el barcode del empaque agrega el factor completo (REQ-P02).
 * 4. Un código que vive en product.uom (empaque o código extra de la unidad
 *    base) de un producto NO precargado se encuentra en el servidor: la caja
 *    precarga como mucho `limited_product_count` productos y el POS estándar
 *    solo busca afuera por product.product.barcode («código desconocido»).
 */
/**
 * Búsqueda en el servidor de CADA escaneo, por el objeto del código.
 *
 * Un mismo escaneo pasa por varias capas que preguntan «¿qué producto es?»
 * (este módulo, surtidora_pos_cliente_cedula, pos_barcodelookup y el POS
 * estándar). Sin esto, un código que no es producto (una cédula) iba al
 * servidor una vez por capa. El lector arma un objeto nuevo por escaneo, así
 * que la clave caduca sola con el escaneo y el siguiente vuelve a preguntar
 * (por si el producto se creó entre medio).
 */
const busquedasEnServidor = new WeakMap();

patch(ProductScreen.prototype, {
    /** Empaques del producto: UdM adicionales con factor > 1. */
    _empaquesDe(productTemplate) {
        return (productTemplate.uom_ids || []).filter(
            (uom) => uom.relative_factor && uom.relative_factor > 1
        );
    },

    /** Opciones del popup. Cada item = { qty, price? } (price = manual, tarifa caja).
     *
     * Cada empaque lleva su ARGUMENTO DE VENTA en la segunda línea: a cuánto
     * sale la unidad suelta comprando ese empaque y cuánto se ahorra. Es la
     * conversación real del mostrador ("el paquete está en 45, pero en caja
     * de 24 te sale a 41"), así que va donde se elige la unidad. */
    _opcionesEmpaque(productTemplate) {
        const order = this.pos.getOrder();
        const pricelist = order && order.pricelist_id;
        const fmt = (valor) => this.env.utils.formatCurrency(valor);
        const nombreBase = productTemplate.uom_id?.name || _t("Unidad");
        const precioBase = productTemplate.getPrice(pricelist, 1, 0);
        const opciones = [
            {
                id: 0,
                label: `${nombreBase} — ${fmt(precioBase)}`,
                item: { qty: 1 },
                isSelected: true,
            },
        ];
        let id = 0;
        for (const uom of this._empaquesDe(productTemplate)) {
            const factor = uom.relative_factor;
            const tarifaCaja = productTemplate.getPrice(pricelist, factor, 0);
            opciones.push({
                id: ++id,
                label: `${uom.name} (${factor} ${nombreBase}) — ${fmt(tarifaCaja * factor)}`,
                surti: this._argumentoEmpaque(precioBase, tarifaCaja, nombreBase, factor),
                // `uom`: para presentar la línea como "1 Caja" (REQ-V16)
                item: { qty: factor, uom },
            });
            if (productTemplate.surtidora_caja_fraccionable) {
                // las mismas fracciones que RB-01 reconoce como legítimas
                // (fraccion_caja.js): solo las que dan unidades enteras
                for (const { txt, qty } of fraccionesDeEmpaque(factor)) {
                    opciones.push({
                        id: ++id,
                        label: `${txt} ${uom.name} (${qty} ${
                            productTemplate.uom_id?.name || _t("und")
                        }) — ${fmt(tarifaCaja * qty)}`,
                        item: { qty, price: tarifaCaja, uom },
                    });
                }
            }
        }
        return opciones;
    },

    /**
     * El guion de venta del empaque, en piezas para que la pantalla resalte
     * lo que importa (reunión 7-ago):
     * - el precio por unidad comprando el empaque, en negrita (punto 2);
     * - cuánto ahorra por unidad Y en la caja completa (punto 3).
     * Si el empaque no trae descuento solo se informa el equivalente: no se
     * inventa un ahorro que no existe.
     */
    _argumentoEmpaque(precioBase, tarifaCaja, nombreBase, factor) {
        const fmt = (valor) => this.env.utils.formatCurrency(valor);
        const argumento = { equivalente: fmt(tarifaCaja), unidad: nombreBase };
        const ahorroUnidad = precioBase - tarifaCaja;
        if (ahorroUnidad > 0) {
            argumento.ahorroUnidad = fmt(ahorroUnidad);
            argumento.ahorroTotal = fmt(ahorroUnidad * factor);
        }
        return argumento;
    },

    async _elegirEmpaque(productTemplate) {
        return await makeAwaitable(this.dialog, SelectionPopup, {
            title: _t("Unidad de venta — %s", productTemplate.display_name),
            list: this._opcionesEmpaque(productTemplate),
        });
    },

    async addProductToOrder(product) {
        if (this._empaquesDe(product).length) {
            const seleccion = await this._elegirEmpaque(product);
            if (!seleccion) {
                return; // canceló el popup
            }
            if (seleccion.qty > 1 || seleccion.price !== undefined) {
                const vals = { product_tmpl_id: product, qty: seleccion.qty };
                if (seleccion.price !== undefined) {
                    vals.price_unit = seleccion.price;
                    vals.price_type = "manual"; // tarifa caja: no recalcular a precio suelto
                }
                if (seleccion.uom) {
                    // recuerda el empaque para presentarlo en el recibo (REQ-V16)
                    vals.surtidora_uom_venta_id = seleccion.uom;
                }
                await this.pos.addLineToCurrentOrder(vals, {});
                this.showOptionalProductPopupIfNeeded(product);
                return;
            }
        }
        return super.addProductToOrder(...arguments);
    },

    /** Producto de un código entre lo precargado: el suyo o el de su empaque. */
    _surtiProductoLocalPorCodigo(barcode) {
        const producto = this.pos.models["product.product"].getBy("barcode", barcode);
        if (producto) {
            return producto;
        }
        const empaque = this.pos.models["product.uom"].getBy("barcode", barcode);
        return empaque && empaque.product_id;
    },

    /**
     * El dominio del POS estándar más los códigos de product.uom (empaques y
     * códigos extra de la unidad base, hasta 38 por producto en Surtidora).
     * El servidor (load_product_from_pos) ya devuelve las product.uom cuyo
     * barcode está en el dominio: con esto el empaque llega a la caja junto
     * con el producto, sus precios y sus demás empaques.
     */
    _surtiDominioPorCodigo(barcode) {
        return [
            "|",
            ["product_variant_ids.barcode", "in", [barcode]],
            ["product_variant_ids.product_uom_ids.barcode", "in", [barcode]],
        ];
    },

    /** Trae del servidor el producto del código y lo resuelve ya cargado. */
    async _surtiCargarProductoPorCodigo(barcode) {
        await this.pos.loadNewProducts(this._surtiDominioPorCodigo(barcode));
        // Se resuelve por el código y no con el primer producto devuelto:
        // una plantilla con variantes trae todas y el código es de una sola.
        return this._surtiProductoLocalPorCodigo(barcode);
    },

    /**
     * Lo precargado sigue por el camino estándar (sin viaje al servidor). Lo
     * que no, se busca UNA vez por escaneo con el dominio ampliado; como ese
     * dominio contiene al estándar, si aquí no aparece tampoco aparecería
     * allá, y por eso no se vuelve a preguntar con super.
     */
    async _getProductByBarcode(code) {
        if (!code?.base_code || this._surtiProductoLocalPorCodigo(code.base_code)) {
            return super._getProductByBarcode(...arguments);
        }
        // La cédula/tarjeta de un cliente que la caja ya tiene cargado no es
        // un producto: sin esto cada escaneo del cliente frecuente iría al
        // servidor a buscar un producto y, sin red, dejaría de asignarse
        // (antes se asignaba sin ningún viaje). surtidora_pos_cliente_cedula
        // lo asigna después, desde lo local.
        if (this.pos.models["res.partner"].getBy("barcode", code.code || code.base_code)) {
            return undefined;
        }
        if (!busquedasEnServidor.has(code)) {
            busquedasEnServidor.set(code, this._surtiCargarProductoPorCodigo(code.base_code));
        }
        return busquedasEnServidor.get(code);
    },

    /**
     * Primero se asegura el producto (lo trae del servidor si no estaba
     * precargado) y solo entonces se mira si el código es de un empaque: el
     * empaque de un producto no precargado tampoco estaba en la caja. Un
     * código extra de la unidad base (factor 1) sigue al estándar: 1 unidad.
     */
    async _barcodeProductAction(code) {
        await this._getProductByBarcode(code);
        const empaque = this.pos.models["product.uom"].getBy("barcode", code.base_code);
        if (empaque && empaque.product_id && !empaque.uom_id) {
            // La unidad del empaque se creó con la caja abierta: la caja carga
            // las unidades solo al abrir y no la conoce. Cobrar 1 unidad en
            // silencio sería peor que avisar.
            this.notification.add(
                "Este empaque es nuevo y la caja todavía no lo conoce: recargue la caja (F5) y vuelva a escanear.",
                { type: "danger" }
            );
            this.numberBuffer.reset();
            return;
        }
        const factor = empaque && empaque.uom_id && empaque.uom_id.relative_factor;
        if (empaque && empaque.product_id && factor > 1) {
            await this.pos.addLineToCurrentOrder(
                {
                    product_id: empaque.product_id,
                    product_tmpl_id: empaque.product_id.product_tmpl_id,
                    qty: factor,
                    // el escaneo del empaque también se presenta como "1 Caja"
                    surtidora_uom_venta_id: empaque.uom_id,
                },
                { code },
                empaque.product_id.needToConfigure()
            );
            this.numberBuffer.reset();
            return;
        }
        return super._barcodeProductAction(...arguments);
    },
});

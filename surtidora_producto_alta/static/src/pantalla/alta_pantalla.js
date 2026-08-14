import { Component, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

/**
 * Alta ágil de productos (REQ-P06) — la disposición del maestro de ADG
 * (capturas 05/06/07) en una sola pantalla.
 *
 * El PRECIO es el maestro (98% de los precios reales son múltiplos de 5):
 * se teclea el precio y el margen se pinta como termómetro; el botón de
 * sugerir hace el camino inverso desde un margen objetivo y redondea a 5.
 * El servidor valida y escribe todo en una transacción.
 *
 * Correcciones de la revisión adversaria (14-ago) marcadas con «RA:».
 */
export class AltaPantalla extends Component {
    static template = "surtidora_producto_alta.Pantalla";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            cargando: true,
            error: null,
            guardando: false,
            config: null,
            form: this.formVacio(),
            sugerencias: [],
            campoActivo: null,
            resaltado: 0,
            creado: null,
        });
        this._buscaSeq = 0;
        this._debounce = null;
        this.cargar();
    }

    formVacio(previo) {
        return {
            referencia: "",
            nombre: "",
            barcode: "",
            categoria_id: previo?.categoria_id ?? null,
            categoria_nombre: previo?.categoria_nombre ?? "",
            proveedor_id: previo?.proveedor_id ?? null,
            proveedor_nombre: previo?.proveedor_nombre ?? "",
            ref_proveedor: "",
            uom_id: previo?.uom_id ?? null,
            uom_nombre: previo?.uom_nombre ?? "",
            impuesto_id: previo?.impuesto_id ?? null,
            costo: "",
            costo_por: "base", // "base" | uom_id del empaque (RA)
            fraccionable: false,
            uom_compra_id: null, // RA: explícito, ya no se adivina
            reorden_min: "",
            reorden_max: "",
            empaques: [],
            precios: {},
            margen_objetivo: previo?.margen_objetivo ?? "",
        };
    }

    async cargar() {
        try {
            const config = await this.orm.call("surtidora.producto.alta", "datos_iniciales", []);
            this.state.config = config;
            this.state.form.impuesto_id = config.impuesto?.id ?? null;
            this.state.form.margen_objetivo = String(config.margen_sugerido.detalle);
            this.state.error = null;
        } catch (error) {
            // RA: antes la pantalla quedaba en blanco y muda
            this.state.error =
                error.data?.message || _t("No se pudo cargar la pantalla.");
        } finally {
            this.state.cargando = false;
        }
    }

    // ------------------------------------------------------------------
    // Typeahead (comparte lista, pero cada campo pinta solo la suya)
    // ------------------------------------------------------------------
    lanzarBusqueda(metodo, args, campo) {
        this.state.campoActivo = campo;
        this.state.resaltado = 0;
        clearTimeout(this._debounce);
        const seq = ++this._buscaSeq;
        this._debounce = setTimeout(async () => {
            try {
                const filas = await this.orm.call("surtidora.producto.alta", metodo, args);
                if (seq === this._buscaSeq) {
                    this.state.sugerencias = filas;
                }
            } catch {
                if (seq === this._buscaSeq) {
                    this.state.sugerencias = [];
                }
            }
        }, 250);
    }

    buscar(campo, modelo, ev) {
        const texto = ev.target.value;
        this.state.form[campo + "_nombre"] = texto;
        this.state.form[campo + "_id"] = null;
        this.lanzarBusqueda("buscar", [modelo, texto], campo);
    }

    buscarBase(ev) {
        const texto = ev.target.value;
        this.state.form.uom_nombre = texto;
        this.state.form.uom_id = null;
        this.lanzarBusqueda("buscar_uom_base", [texto], "uom");
    }

    buscarUom(indice, ev) {
        const texto = ev.target.value;
        const empaque = this.state.form.empaques[indice];
        empaque.uom_nombre = texto;
        empaque.uom_id = null;
        empaque.factor = 0;
        this.lanzarBusqueda("buscar_uom", [texto, this.state.form.uom_id], `emp${indice}`);
    }

    elegir(campo, fila) {
        this.state.form[campo + "_id"] = fila.id;
        this.state.form[campo + "_nombre"] = fila.nombre;
        this.cerrarYa();
    }

    elegirUom(indice, fila) {
        const empaque = this.state.form.empaques[indice];
        empaque.uom_id = fila.id;
        empaque.uom_nombre = fila.nombre;
        empaque.factor = fila.factor || 0;
        if (!this.state.form.uom_compra_id) {
            this.state.form.uom_compra_id = fila.id; // sugerencia, editable
        }
        this.cerrarYa();
    }

    /** RA: teclado — flechas, Enter y Escape (antes solo mouse). */
    teclas(ev, alElegir) {
        if (!this.state.sugerencias.length) {
            return;
        }
        if (ev.key === "ArrowDown") {
            ev.preventDefault();
            this.state.resaltado = (this.state.resaltado + 1) % this.state.sugerencias.length;
        } else if (ev.key === "ArrowUp") {
            ev.preventDefault();
            this.state.resaltado =
                (this.state.resaltado - 1 + this.state.sugerencias.length) %
                this.state.sugerencias.length;
        } else if (ev.key === "Enter") {
            ev.preventDefault();
            alElegir(this.state.sugerencias[this.state.resaltado]);
        } else if (ev.key === "Escape") {
            this.cerrarYa();
        }
    }

    cerrarYa() {
        clearTimeout(this._debounce);
        this._buscaSeq++; // invalida respuestas en vuelo
        this.state.sugerencias = [];
        this.state.campoActivo = null;
        this.state.resaltado = 0;
    }

    cerrarSugerencias() {
        setTimeout(() => {
            if (this.state.sugerencias.length) {
                this.state.sugerencias = [];
                this.state.campoActivo = null;
            }
        }, 200);
    }

    // ------------------------------------------------------------------
    // Altas al vuelo (RA: sin esto el alta se trababa)
    // ------------------------------------------------------------------
    async crearRegistro(campo, modelo) {
        const nombre = this.state.form[campo + "_nombre"];
        try {
            const fila = await this.orm.call("surtidora.producto.alta", "crear_registro", [
                modelo,
                nombre,
            ]);
            this.elegir(campo, fila);
            this.notification.add(_t("%s creado.", fila.nombre), { type: "success" });
        } catch (error) {
            this.notification.add(error.data?.message || _t("No se pudo crear."), {
                type: "danger",
            });
        }
    }

    async crearUnidad(indice) {
        const empaque = this.state.form.empaques[indice];
        const factor = this.num(empaque.factor_nuevo);
        if (!this.state.form.uom_id) {
            this.notification.add(_t("Elija primero la unidad base."), { type: "warning" });
            return;
        }
        if (factor <= 1) {
            this.notification.add(_t("Escriba cuántas unidades base trae el empaque."), {
                type: "warning",
            });
            return;
        }
        try {
            const fila = await this.orm.call("surtidora.producto.alta", "crear_uom", [
                empaque.uom_nombre,
                factor,
                this.state.form.uom_id,
            ]);
            this.elegirUom(indice, fila);
            empaque.factor_nuevo = "";
            this.notification.add(_t("Unidad %s creada.", fila.nombre), { type: "success" });
        } catch (error) {
            this.notification.add(error.data?.message || _t("No se pudo crear la unidad."), {
                type: "danger",
            });
        }
    }

    // ------------------------------------------------------------------
    // Empaques
    // ------------------------------------------------------------------
    agregarEmpaque() {
        this.state.form.empaques.push({
            uom_id: null,
            uom_nombre: "",
            factor: 0,
            factor_nuevo: "",
            barcode: "",
            _key: `emp${Date.now()}${this.state.form.empaques.length}`,
        });
    }

    quitarEmpaque(indice) {
        const empaque = this.state.form.empaques[indice];
        if (empaque?.uom_id) {
            for (const lista of this.state.config.listas) {
                delete this.state.form.precios[`${lista.id}:${empaque.uom_id}`];
            }
            if (this.state.form.uom_compra_id === empaque.uom_id) {
                this.state.form.uom_compra_id = null;
            }
        }
        this.state.form.empaques.splice(indice, 1);
    }

    get empaquesValidos() {
        return this.state.form.empaques.filter((e) => e.uom_id);
    }

    // ------------------------------------------------------------------
    // Precios y margen
    // ------------------------------------------------------------------
    get tasa() {
        const imp = this.state.config?.impuesto;
        return this.state.form.impuesto_id && imp ? imp.tasa / 100 : 0;
    }

    /** RA: el costo se puede teclear por caja (así llega la factura del
     * proveedor) y se convierte a unidad base. */
    get costoBase() {
        const costo = this.num(this.state.form.costo);
        const por = this.state.form.costo_por;
        if (por === "base") {
            return costo;
        }
        const empaque = this.empaquesValidos.find((e) => String(e.uom_id) === String(por));
        return empaque?.factor ? costo / empaque.factor : costo;
    }

    get costoConItbis() {
        return this.costoBase * (1 + this.tasa);
    }

    clave(lista, empaque) {
        return `${lista.id}:${empaque ? empaque.uom_id : "base"}`;
    }

    precio(lista, empaque) {
        return this.state.form.precios[this.clave(lista, empaque)] ?? "";
    }

    escribirPrecio(lista, empaque, ev) {
        const valor = ev.target.value;
        const clave = this.clave(lista, empaque);
        if (valor === "") {
            delete this.state.form.precios[clave];
        } else {
            this.state.form.precios[clave] = valor;
        }
    }

    margen(lista, empaque) {
        const costo = this.costoConItbis * (empaque ? empaque.factor || 0 : 1);
        const precio = this.num(this.precio(lista, empaque));
        if (!costo || !precio) {
            return null;
        }
        return ((precio - costo) / costo) * 100;
    }

    claseMargen(lista, empaque) {
        const margen = this.margen(lista, empaque);
        if (margen === null) {
            return "";
        }
        if (margen < 0) {
            return "text-danger fw-bolder";
        }
        return margen < 5 ? "text-warning fw-bolder" : "text-success";
    }

    get hayPreciosTecleados() {
        return Object.keys(this.state.form.precios).length > 0;
    }

    /** Del margen objetivo al precio, redondeado a múltiplo de 5.
     * RA: cada lista recibe SU margen (la mayorista vende más barato que
     * la de detalle) y la caja menos margen que la unidad. */
    sugerirPrecios() {
        const objetivo = this.num(this.state.form.margen_objetivo);
        const costo = this.costoConItbis;
        if (!costo) {
            this.notification.add(_t("Primero escriba el costo."), { type: "warning" });
            return;
        }
        if (this.hayPreciosTecleados && !window.confirm(
            _t("Se reemplazarán los precios ya escritos. ¿Continuar?"))) {
            return;
        }
        const redondear5 = (valor) => Math.max(5, Math.round(valor / 5) * 5);
        const listas = this.state.config.listas;
        const mayorista = this.state.config.margen_sugerido.mayorista;
        const bajaCaja = objetivo - this.state.config.margen_sugerido.caja;
        listas.forEach((lista, indice) => {
            // la primera lista es la mayorista (P1) y la última el detalle
            const esMayorista = indice < listas.length / 2;
            const margen = esMayorista ? Math.min(objetivo, mayorista) : objetivo;
            const base = Math.max(redondear5(costo * (1 + margen / 100)), Math.ceil(costo));
            this.state.form.precios[this.clave(lista, null)] = String(base);
            for (const empaque of this.empaquesValidos) {
                const margenCaja = Math.max(0, esMayorista ? Math.min(margen, bajaCaja) : bajaCaja);
                const costoCaja = costo * empaque.factor;
                // nunca por debajo del costo: RB-08 lo rechazaría
                const total = Math.max(
                    redondear5(costoCaja * (1 + margenCaja / 100)),
                    Math.ceil(costoCaja)
                );
                this.state.form.precios[this.clave(lista, empaque)] = String(total);
            }
        });
    }

    // ------------------------------------------------------------------
    // Acciones
    // ------------------------------------------------------------------
    async generarCodigo(destino) {
        const actual = destino === null ? this.state.form.barcode
                                        : this.state.form.empaques[destino].barcode;
        if (actual && !window.confirm(_t("Ya hay un código escrito. ¿Reemplazarlo?"))) {
            return;
        }
        try {
            const codigo = await this.orm.call(
                "surtidora.producto.alta", "codigo_barras_interno", []);
            if (destino === null) {
                this.state.form.barcode = codigo;
            } else {
                this.state.form.empaques[destino].barcode = codigo;
            }
        } catch (error) {
            this.notification.add(error.data?.message || _t("No se pudo generar el código."), {
                type: "danger",
            });
        }
    }

    async crear() {
        if (this.state.guardando) {
            return;
        }
        this.state.guardando = true;
        try {
            const form = this.state.form;
            const resumen = await this.orm.call("surtidora.producto.alta", "crear", [
                {
                    referencia: form.referencia,
                    nombre: form.nombre,
                    barcode: form.barcode,
                    categoria_id: form.categoria_id,
                    proveedor_id: form.proveedor_id,
                    ref_proveedor: form.ref_proveedor,
                    uom_id: form.uom_id,
                    impuesto_id: form.impuesto_id,
                    costo: this.costoBase, // siempre por unidad base
                    fraccionable: form.fraccionable,
                    uom_compra_id: form.uom_compra_id,
                    reorden_min: form.reorden_min,
                    reorden_max: form.reorden_max,
                    almacen_id: this.state.config.almacen?.id || null,
                    // se mandan TODOS: el servidor avisa del que quedó sin unidad
                    empaques: form.empaques.map((e) => ({
                        uom_id: e.uom_id,
                        barcode: e.barcode,
                    })),
                    precios: form.precios,
                },
            ]);
            this.state.creado = resumen;
            // RA: se conserva el contexto del lote (proveedor, categoría,
            // unidad base) — llegan 10 referencias del mismo suplidor
            this.state.form = this.formVacio(this.state.form);
        } catch (error) {
            this.notification.add(error.data?.message || _t("No se pudo crear el producto."), {
                type: "danger",
                sticky: true, // RA: el aviso ya no se desvanece
            });
        } finally {
            this.state.guardando = false;
        }
    }

    num(valor) {
        const numero = parseFloat(valor);
        return isNaN(numero) ? 0 : numero;
    }

    n(valor, dec = 2) {
        return (valor ?? 0).toLocaleString("es-DO", {
            minimumFractionDigits: dec,
            maximumFractionDigits: dec,
        });
    }
}

registry.category("actions").add("surtidora_producto_alta.pantalla", AltaPantalla);

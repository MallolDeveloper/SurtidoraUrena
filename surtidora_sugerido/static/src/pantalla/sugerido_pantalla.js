import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

/**
 * Pantalla única del Sugerido de Compras (captura 14 de ADG).
 *
 * Todo a la vista a la vez — sin popups: filtros arriba, panel del producto
 * seleccionado + matriz mensual siempre visibles, grid central (clic en la
 * fila actualiza los paneles), últimas compras y OC pendientes abajo.
 * Los números vienen del mismo motor que el wizard (surtidora.sugerido.motor).
 */
export class SugeridoPantalla extends Component {
    static template = "surtidora_sugerido.Pantalla";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        const hoy = new Date();
        const haceUnAno = new Date(hoy.getTime() - 365 * 24 * 3600 * 1000);
        this.state = useState({
            suplidores: [],
            filtroSuplidor: "",
            listaAbierta: false,
            resaltado: 0,
            suplidorId: 0,
            desde: haceUnAno.toISOString().slice(0, 10),
            hasta: hoy.toISOString().slice(0, 10),
            dias: 30,
            buscarProducto: "",
            filas: [],
            cargando: false,
            creandoOC: false,
            seleccionId: 0,
            detalle: null,
            cargandoDetalle: false,
            orden: { campo: "cant_sugerida", dir: -1 },
        });
        this.cacheDetalle = {};
        // El suplidor con el que se CALCULÓ — la OC se crea a este, no al
        // valor vivo del select (evita OC confirmada al suplidor equivocado).
        this.suplidorCalculado = 0;
        onWillStart(async () => {
            this.state.suplidores = await this.orm.searchRead(
                "res.partner",
                [["supplier_rank", ">", 0]],
                ["display_name"],
                { order: "name" }
            );
        });
    }

    // ------------------------------------------------------------------
    // Datos
    // ------------------------------------------------------------------
    get suplidoresFiltrados() {
        const filtro = this.state.filtroSuplidor.toLowerCase();
        const lista = filtro
            ? this.state.suplidores.filter((s) => s.display_name.toLowerCase().includes(filtro))
            : this.state.suplidores;
        return lista.slice(0, 80);
    }

    get filasOrdenadas() {
        const { campo, dir } = this.state.orden;
        return [...this.state.filas].sort((a, b) => {
            const va = a[campo] ?? "";
            const vb = b[campo] ?? "";
            if (va === vb) return 0;
            return (va > vb ? 1 : -1) * dir;
        });
    }

    /**
     * Filas que se ven en la tabla: el buscador filtra por referencia,
     * nombre o referencia del suplidor.
     *
     * Los botones de la botonera trabajan sobre ESTAS filas, no sobre todo
     * el cálculo: si el comprador filtró "galleta", "Ordenar lo sugerido"
     * ordena galletas y la OC lleva galletas — lo que ve es lo que hace.
     */
    get filasVisibles() {
        const texto = this.state.buscarProducto.trim().toLowerCase();
        if (!texto) {
            return this.filasOrdenadas;
        }
        return this.filasOrdenadas.filter((f) =>
            `${f.referencia || ""} ${f.producto || ""} ${f.ref_suplidor || ""}`
                .toLowerCase()
                .includes(texto)
        );
    }

    get seleccion() {
        return this.state.filas.find((f) => f.product_id === this.state.seleccionId) || null;
    }

    /**
     * El histórico de 12 meses se parte en dos tablas de 6 puestas lado a
     * lado: así el comprador ve el año completo de una sola mirada, sin
     * desplazarse (pedido de Adelso en la revisión del 7-ago).
     */
    get matrizPartida() {
        const meses = this.state.detalle?.matriz || [];
        const mitad = Math.ceil(meses.length / 2);
        return [meses.slice(0, mitad), meses.slice(mitad)];
    }

    async calcular() {
        if (!this.state.suplidorId) {
            this.notification.add("Elija un suplidor primero.", { type: "warning" });
            return;
        }
        this.state.cargando = true;
        this.state.detalle = null;
        this.state.seleccionId = 0;
        this.cacheDetalle = {};
        try {
            this.state.filas = await this.orm.call(
                "surtidora.sugerido.motor",
                "sugerido_json",
                [this.state.suplidorId, this.state.desde, this.state.hasta, this.state.dias]
            );
            this.suplidorCalculado = this.state.suplidorId;
            if (this.state.filas.length) {
                await this.seleccionar(this.filasOrdenadas[0]);
            }
        } finally {
            this.state.cargando = false;
        }
    }

    async seleccionar(fila) {
        const pid = fila.product_id;
        this.state.seleccionId = pid;
        if (!this.cacheDetalle[pid]) {
            this.state.cargandoDetalle = true;
            try {
                this.cacheDetalle[pid] = await this.orm.call(
                    "surtidora.sugerido.motor",
                    "detalle_json",
                    [pid, this.state.dias]
                );
            } finally {
                if (this.state.seleccionId === pid) {
                    this.state.cargandoDetalle = false;
                }
            }
        }
        if (this.state.seleccionId !== pid) {
            return; // el usuario ya cambió de fila: no pisar su detalle
        }
        this.state.detalle = this.cacheDetalle[pid];
    }

    // ------------------------------------------------------------------
    // Combobox de suplidor (typeahead: la lista se ve MIENTRAS se escribe)
    // ------------------------------------------------------------------
    escribirSuplidor(ev) {
        this.state.filtroSuplidor = ev.target.value;
        this.state.listaAbierta = true;
        this.state.resaltado = 0;
        // el texto ya no corresponde a un suplidor elegido
        this.state.suplidorId = 0;
    }

    abrirLista() {
        this.state.listaAbierta = true;
        this.state.resaltado = 0;
    }

    cerrarLista() {
        this.state.listaAbierta = false;
    }

    elegirSuplidor(suplidor) {
        const esOtro = this.suplidorCalculado && suplidor.id !== this.suplidorCalculado;
        this.state.suplidorId = suplidor.id;
        this.state.filtroSuplidor = suplidor.display_name;
        this.cerrarLista();
        if (esOtro) {
            this._invalidarCalculo();
        }
    }

    tecladoSuplidor(ev) {
        const lista = this.suplidoresFiltrados;
        if (ev.key === "ArrowDown") {
            ev.preventDefault();
            this.state.listaAbierta = true;
            this.state.resaltado = Math.min(this.state.resaltado + 1, lista.length - 1);
        } else if (ev.key === "ArrowUp") {
            ev.preventDefault();
            this.state.resaltado = Math.max(this.state.resaltado - 1, 0);
        } else if (ev.key === "Enter" && this.state.listaAbierta && lista.length) {
            ev.preventDefault();
            this.elegirSuplidor(lista[this.state.resaltado] || lista[0]);
        } else if (ev.key === "Escape") {
            this.cerrarLista();
        }
    }

    _invalidarCalculo() {
        // las filas en pantalla eran de otro suplidor: fuera
        this.state.filas = [];
        this.state.detalle = null;
        this.state.seleccionId = 0;
        this.suplidorCalculado = 0;
    }

    // ------------------------------------------------------------------
    // Acciones de la botonera (las de ADG)
    // ------------------------------------------------------------------
    ordenarLoSugerido() {
        for (const fila of this.filasVisibles) {
            fila.cantidad_ordenar = Math.max(0, Math.ceil(fila.cant_sugerida));
        }
    }

    quitarCantidades() {
        for (const fila of this.filasVisibles) {
            fila.cantidad_ordenar = 0;
        }
    }

    /**
     * Abre la ficha del producto en un diálogo para corregir el costo (u
     * otra cosa) sin salir del sugerido, y al cerrar refresca el costo de
     * esa fila. No recalcula todo: eso borraría lo ya tecleado.
     */
    abrirProducto(fila) {
        this.action.doAction(
            {
                type: "ir.actions.act_window",
                res_model: "product.product",
                res_id: fila.product_id,
                views: [[false, "form"]],
                target: "new",
            },
            { onClose: () => this._refrescarCosto(fila) }
        );
    }

    async _refrescarCosto(fila) {
        const datos = await this.orm.call("surtidora.sugerido.motor", "costo_json", [
            fila.product_id,
        ]);
        fila.costo_uom_compra = datos.costo_uom_compra;
    }

    async crearOC(firme) {
        if (this.state.creandoOC) {
            return; // guard anti doble clic: una OC, no dos
        }
        if (!this.suplidorCalculado) {
            this.notification.add("Calcule el sugerido antes de generar la orden.", { type: "warning" });
            return;
        }
        const lineas = this.filasVisibles
            .filter((f) => f.cantidad_ordenar > 0)
            .map((f) => ({
                product_id: f.product_id,
                uom_id: f.uom_compra_id,
                cantidad: f.cantidad_ordenar,
                precio: f.costo_uom_compra,
                descripcion: f.ref_suplidor
                    ? `${f.producto}\nRef. suplidor: ${f.ref_suplidor}`
                    : f.producto,
            }));
        if (!lineas.length) {
            this.notification.add('Ninguna línea tiene "Cantidad a ordenar".', { type: "warning" });
            return;
        }
        this.state.creandoOC = true;
        try {
            const resultado = await this.orm.call(
                "surtidora.sugerido.motor",
                "crear_oc_json",
                [this.suplidorCalculado, lineas, firme]
            );
            this.notification.add(
                `Orden ${resultado.name} ${firme ? "confirmada" : "guardada temporal"}.`,
                { type: "success" }
            );
            this.action.doAction({
                type: "ir.actions.act_window",
                res_model: "purchase.order",
                res_id: resultado.order_id,
                views: [[false, "form"]],
                target: "current",
            });
        } finally {
            this.state.creandoOC = false;
        }
    }

    ordenarPor(campo) {
        const orden = this.state.orden;
        if (orden.campo === campo) {
            orden.dir = -orden.dir;
        } else {
            orden.campo = campo;
            orden.dir = -1;
        }
    }

    // ------------------------------------------------------------------
    // Formato
    // ------------------------------------------------------------------
    n(valor, decimales = 2) {
        return (valor || 0).toLocaleString("es-DO", {
            minimumFractionDigits: decimales,
            maximumFractionDigits: decimales,
        });
    }

    fecha(texto) {
        return texto ? texto.slice(0, 10) : "—";
    }

    actualizarCantidad(fila, ev) {
        const valor = parseFloat(ev.target.value);
        fila.cantidad_ordenar = isNaN(valor) || valor < 0 ? 0 : valor;
    }

    /** Costo negociado para ESTA orden. No toca el costo del producto: para
     * cambiarlo de forma permanente está el botón de la ficha. */
    actualizarCosto(fila, ev) {
        const valor = parseFloat(ev.target.value);
        fila.costo_uom_compra = isNaN(valor) || valor < 0 ? 0 : valor;
    }
}

registry.category("actions").add("surtidora_sugerido.pantalla", SugeridoPantalla);

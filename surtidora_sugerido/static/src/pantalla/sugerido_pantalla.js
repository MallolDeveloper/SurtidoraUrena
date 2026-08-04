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
            suplidorId: 0,
            desde: haceUnAno.toISOString().slice(0, 10),
            hasta: hoy.toISOString().slice(0, 10),
            dias: 30,
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
                { order: "display_name" }
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

    get seleccion() {
        return this.state.filas.find((f) => f.product_id === this.state.seleccionId) || null;
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

    cambioSuplidor() {
        // cambiar el suplidor invalida lo calculado (las filas eran de otro)
        this.state.filas = [];
        this.state.detalle = null;
        this.state.seleccionId = 0;
        this.suplidorCalculado = 0;
    }

    // ------------------------------------------------------------------
    // Acciones de la botonera (las de ADG)
    // ------------------------------------------------------------------
    ordenarLoSugerido() {
        for (const fila of this.state.filas) {
            fila.cantidad_ordenar = Math.max(0, Math.ceil(fila.cant_sugerida));
        }
    }

    quitarCantidades() {
        for (const fila of this.state.filas) {
            fila.cantidad_ordenar = 0;
        }
    }

    async crearOC(firme) {
        if (this.state.creandoOC) {
            return; // guard anti doble clic: una OC, no dos
        }
        if (!this.suplidorCalculado) {
            this.notification.add("Calcule el sugerido antes de generar la orden.", { type: "warning" });
            return;
        }
        const lineas = this.state.filas
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
}

registry.category("actions").add("surtidora_sugerido.pantalla", SugeridoPantalla);

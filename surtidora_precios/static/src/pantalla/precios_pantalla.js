import { Component, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";

/**
 * Mantenimiento de Precios (réplica del flujo "Costos y Precios" de ADG).
 *
 * El precio es el MAESTRO: se teclea el total del empaque ("la caja a 880")
 * y el % de margen se recalcula en vivo como termómetro. El motor del
 * servidor arma los datos y escribe las reglas; aquí solo se pinta.
 *
 * Guardas de la revisión adversaria (13-ago): token de vigencia en carga y
 * búsqueda, debounce del typeahead, campo vacío = descartar la edición,
 * y confirmación antes de botar cambios sin guardar.
 */
export class PreciosPantalla extends Component {
    static template = "surtidora_precios.Pantalla";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.dialog = useService("dialog");
        this.state = useState({
            buscar: "",
            resultados: [],
            listaAbierta: false,
            resaltado: 0,
            data: null,
            cargando: false,
            guardando: false,
            edits: {}, // clave lista:uom -> precio_total tecleado
        });
        this._buscaSeq = 0; // token: solo la búsqueda más reciente pinta
        this._cargaSeq = 0; // token: solo la carga más reciente pinta
        this._debounce = null;
    }

    // ------------------------------------------------------------------
    // Typeahead de producto (con debounce y token de vigencia)
    // ------------------------------------------------------------------
    escribir(ev) {
        this.state.buscar = ev.target.value;
        this.state.resaltado = 0;
        clearTimeout(this._debounce);
        const texto = this.state.buscar.trim();
        if (texto.length < 2) {
            this.state.resultados = [];
            this.state.listaAbierta = false;
            return;
        }
        const seq = ++this._buscaSeq;
        this._debounce = setTimeout(async () => {
            const res = await this.orm.call(
                "surtidora.precios.motor", "buscar_json", [texto]);
            // una respuesta vieja, o una lista que el usuario ya cerró
            // (Escape/blur/elección), no reabre nada
            if (seq === this._buscaSeq) {
                this.state.resultados = res;
                this.state.listaAbierta = res.length > 0;
            }
        }, 250);
    }

    teclado(ev) {
        const lista = this.state.resultados;
        if (ev.key === "ArrowDown") {
            ev.preventDefault();
            this.state.listaAbierta = true;
            this.state.resaltado = Math.min(this.state.resaltado + 1, lista.length - 1);
        } else if (ev.key === "ArrowUp") {
            ev.preventDefault();
            this.state.resaltado = Math.max(this.state.resaltado - 1, 0);
        } else if (ev.key === "Enter" && this.state.listaAbierta && lista.length) {
            ev.preventDefault();
            this.elegir(lista[this.state.resaltado] || lista[0]);
        } else if (ev.key === "Escape") {
            this.cerrarLista();
        }
    }

    cerrarLista() {
        this._buscaSeq++; // invalida cualquier respuesta en vuelo
        this.state.listaAbierta = false;
    }

    elegir(producto) {
        this.cerrarLista();
        if (this.hayCambios) {
            this.dialog.add(ConfirmationDialog, {
                title: _t("Cambios sin guardar"),
                body: _t("Hay precios editados sin guardar. ¿Descartarlos y cambiar de producto?"),
                confirmLabel: _t("Descartar y cambiar"),
                cancelLabel: _t("Quedarme"),
                confirm: () => this._elegir(producto),
                cancel: () => {},
            });
            return;
        }
        this._elegir(producto);
    }

    async _elegir(producto) {
        this.state.buscar = `${producto.ref} — ${producto.nombre}`;
        await this.cargar(producto.id);
    }

    async cargar(templateId) {
        const seq = ++this._cargaSeq;
        this.state.cargando = true;
        try {
            const data = await this.orm.call(
                "surtidora.precios.motor", "producto_json", [templateId]);
            if (seq === this._cargaSeq) {
                this.state.data = data;
                this.state.edits = {};
            }
        } finally {
            if (seq === this._cargaSeq) {
                this.state.cargando = false;
            }
        }
    }

    // ------------------------------------------------------------------
    // Edición y margen en vivo
    // ------------------------------------------------------------------
    clave(fila) {
        return `${fila.lista_id}:${fila.uom_id}`;
    }

    precioDe(fila) {
        const editado = this.state.edits[this.clave(fila)];
        return editado === undefined ? fila.precio_total : editado;
    }

    editar(fila, ev) {
        const valor = parseFloat(ev.target.value);
        if (isNaN(valor) || valor <= 0) {
            // campo vacío o basura = descartar ESTA edición, no volverla 0
            delete this.state.edits[this.clave(fila)];
        } else {
            this.state.edits[this.clave(fila)] = valor;
        }
    }

    /** % de margen sobre el costo con ITBIS — el termómetro de Adelso. */
    margenDe(fila) {
        const precio = this.precioDe(fila);
        if (!fila.costo_total_itbis || !precio) {
            return null;
        }
        return (precio / fila.costo_total_itbis - 1) * 100;
    }

    /** rojo = bajo costo (RB-08) · ámbar = bajo el piso del 5% · verde = sano */
    claseMargen(fila) {
        const m = this.margenDe(fila);
        if (m === null) {
            return "";
        }
        if (m < 0) {
            return "surti-margen-rojo";
        }
        return m < 5 ? "surti-margen-ambar" : "surti-margen-ok";
    }

    _difiere(fila) {
        const e = this.state.edits[this.clave(fila)];
        return e !== undefined && Math.abs(e - fila.precio_total) > 0.005;
    }

    get hayCambios() {
        return (this.state.data?.filas || []).some((f) => this._difiere(f));
    }

    get listasAgrupadas() {
        const grupos = [];
        for (const fila of this.state.data?.filas || []) {
            let g = grupos.find((x) => x.lista_id === fila.lista_id);
            if (!g) {
                g = { lista_id: fila.lista_id, lista: fila.lista, filas: [] };
                grupos.push(g);
            }
            g.filas.push(fila);
        }
        return grupos;
    }

    async guardar() {
        if (this.state.guardando || !this.hayCambios) {
            return;
        }
        const d = this.state.data;
        const cambios = d.filas.filter((f) => this._difiere(f)).map((f) => ({
            lista_id: f.lista_id,
            lista: f.lista,
            uom_id: f.uom_id,
            precio_total: this.precioDe(f),
        }));
        this.state.guardando = true;
        try {
            const r = await this.orm.call(
                "surtidora.precios.motor", "guardar_json", [d.template_id, cambios]);
            this.notification.add(
                _t("%s precio(s) actualizados.", r.cambios), { type: "success" });
            for (const aviso of r.avisos || []) {
                this.notification.add(aviso, { type: "warning", sticky: true });
            }
            await this.cargar(d.template_id);
        } finally {
            this.state.guardando = false;
        }
    }

    n(valor, dec = 2) {
        return (valor ?? 0).toLocaleString("es-DO", {
            minimumFractionDigits: dec,
            maximumFractionDigits: dec,
        });
    }
}

registry.category("actions").add("surtidora_precios.pantalla", PreciosPantalla);

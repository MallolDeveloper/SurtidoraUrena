import { patch } from "@web/core/utils/patch";
import { TicketScreen } from "@point_of_sale/app/screens/ticket_screen/ticket_screen";
import { useBarcodeReader } from "@point_of_sale/app/hooks/barcode_reader_hook";

/**
 * En la pantalla de tickets, escanear el recibo ENCUENTRA la venta.
 *
 * La tirilla lleva su número de venta en Code128 justamente para esto
 * (surtidora_pos_tirilla): que en una devolución la cajera escanee el papel
 * en vez de teclear «265-1-000003». Pero el POS no sabía qué hacer con ese
 * escaneo aquí: el servicio de códigos reparte cada lectura por TIPO a los
 * callbacks que registra la pantalla montada, y la pantalla de tickets no
 * registra ninguno. La referencia caía en la regla genérica de producto y
 * salía «código desconocido» (11-sep-2026, probado con el lector en mano).
 *
 * Con este parche la pantalla registra el tipo `product` —el que produce la
 * regla genérica de la nomenclatura para cualquier código que no sea de
 * balanza, descuento, cliente o lote— y lo trata como lo que es aquí: un
 * número de recibo. No hay conflicto con la pantalla de productos: sus
 * callbacks se dan de baja al desmontarse, y estos se dan de alta solo
 * mientras la pantalla de tickets está en pantalla.
 *
 * Busca en las ventas SINCRONIZADAS (filtro «Pagadas»/servidor), porque la
 * venta a devolver puede ser de otro día u otra caja, y usa el mismo campo
 * «Número de recibo» del buscador nativo, así que la lista y el desplegable
 * quedan como si la cajera lo hubiera tecleado. Si aparece exactamente esa
 * venta, la selecciona; si no, deja la lista filtrada y a la vista.
 */
/**
 * Lo que escribe el lector, llevado a la forma guardada «265-1-000003».
 *
 * Un lector en modo teclado emula un teclado AMERICANO y Windows le aplica
 * la distribución activa: en la latinoamericana la tecla que en US es «-»
 * escribe «'», así que el mismo código de barras llega como 265'1'000003 y
 * la búsqueda literal no encuentra nada (11-sep-2026, con el lector en
 * mano: «No orders found» con la tirilla recién impresa). Los dígitos son
 * iguales en todas las distribuciones; el separador no. Por eso cualquier
 * tramo que no sea dígito se lee como el guion de la referencia.
 */
function referenciaDe(texto) {
    return String(texto || "")
        .trim()
        .replace(/[^0-9]+/g, "-")
        .replace(/^-+|-+$/g, "");
}

/** «265-1-000003» y «265'1'000003» son la misma venta. */
function mismaReferencia(a, b) {
    return referenciaDe(a) === referenciaDe(b);
}

patch(TicketScreen.prototype, {
    setup() {
        super.setup(...arguments);
        // `useBarcodeReader` liga el callback a este componente y lo registra
        // solo mientras la pantalla está montada
        useBarcodeReader({ product: this._surtidoraBuscarRecibo });
    },

    async _surtidoraBuscarRecibo(codigo) {
        const referencia = referenciaDe(codigo.base_code || codigo.code);
        if (!referencia) {
            return;
        }
        // la venta puede no estar en memoria: buscar en las del servidor
        this.state.filter = "SYNCED";
        await this.onSearch({ fieldName: "RECEIPT_NUMBER", searchTerm: referencia });
        // exacta, no difusa: es la referencia del papel, no lo que alguien
        // recuerda a medias
        const venta = this.pos.models["pos.order"].find((orden) =>
            mismaReferencia(orden.pos_reference, referencia)
        );
        if (venta) {
            this.onClickOrder(venta);
        }
    },
});

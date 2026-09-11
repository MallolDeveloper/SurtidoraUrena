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
patch(TicketScreen.prototype, {
    setup() {
        super.setup(...arguments);
        // `useBarcodeReader` liga el callback a este componente y lo registra
        // solo mientras la pantalla está montada
        useBarcodeReader({ product: this._surtidoraBuscarRecibo });
    },

    async _surtidoraBuscarRecibo(codigo) {
        const referencia = String(codigo.base_code || codigo.code || "").trim();
        if (!referencia) {
            return;
        }
        // la venta puede no estar en memoria: buscar en las del servidor
        this.state.filter = "SYNCED";
        await this.onSearch({ fieldName: "RECEIPT_NUMBER", searchTerm: referencia });
        // exacta, no difusa: es la referencia del papel, no lo que alguien
        // recuerda a medias
        const venta = this.pos.models["pos.order"].find(
            (orden) => orden.pos_reference === referencia
        );
        if (venta) {
            this.onClickOrder(venta);
        }
    },
});

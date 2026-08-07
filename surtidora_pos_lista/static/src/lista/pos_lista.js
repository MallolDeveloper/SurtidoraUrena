import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { ProductCard } from "@point_of_sale/app/components/product_card/product_card";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";

/**
 * Vista de LISTA para el catálogo del POS (Surtidora Ureña).
 *
 * El catálogo casi no tiene fotos, así que el mosaico gasta la pantalla en
 * cuadros grises y recorta el nombre. En lista cabe la referencia, el nombre
 * completo y el precio — que es lo que el cajero necesita para negociar.
 *
 * La preferencia se guarda por estación (navegador), no en la base: cada
 * puesto trabaja como quiera sin pisar la configuración de los demás.
 */
const CLAVE = "surtidora_pos_vista_lista";

patch(PosStore.prototype, {
    async setup() {
        await super.setup(...arguments);
        // Se inicializa aquí para que OWL la siga desde el primer render.
        this.surtiVistaLista = localStorage.getItem(CLAVE) === "1";
    },

    /** Clase que recibe cada tarjeta: la nuestra en lista, la de Odoo si no. */
    get productViewMode() {
        if (this.surtiVistaLista) {
            return "surti-fila";
        }
        return super.productViewMode;
    },

    surtiAlternarVista() {
        this.surtiVistaLista = !this.surtiVistaLista;
        localStorage.setItem(CLAVE, this.surtiVistaLista ? "1" : "0");
    },
});

patch(ProductCard.prototype, {
    setup() {
        super.setup(...arguments);
        this.pos = usePos();
    },

    /** Precio de una unidad base con la tarifa del cliente en curso. */
    get surtiPrecio() {
        const producto = this.props.product;
        if (!producto?.getPrice) {
            return "";
        }
        const pricelist = this.pos.getOrder()?.pricelist_id;
        return this.env.utils.formatCurrency(producto.getPrice(pricelist, 1, 0));
    },

    get surtiReferencia() {
        return this.props.product?.default_code || "";
    },
});

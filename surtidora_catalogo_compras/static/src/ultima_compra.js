/** @odoo-module **/
// La tarjeta del catálogo pasa TODO `productCatalogData` como props del
// componente de la línea (t-props="productCatalogData"). Los dos datos nuevos
// que manda el servidor hay que declararlos o OWL rechaza el render.
//
// Se declaran en las clases MÁS DERIVADAS, no en la base: cada subclase copia
// `props` con un spread en el cuerpo de la clase, y eso ya corrió cuando este
// archivo se carga. Parchar la base a estas alturas no llegaría a las hijas.
import { ProductCatalogPurchaseOrderLine } from "@purchase/product_catalog/purchase_order_line/purchase_order_line";
import { ProductCatalogPurchaseSuggestOrderLine } from "@purchase_stock/product_catalog/record/purchase_order_line";

const PROPS_ULTIMA_COMPRA = {
    surtidoraUltimaFecha: { type: String, optional: true },
    surtidoraUltimoPrecio: { type: String, optional: true },
    surtidoraUltimaUnidad: { type: String, optional: true },
};

for (const Componente of [
    ProductCatalogPurchaseOrderLine,
    ProductCatalogPurchaseSuggestOrderLine,
]) {
    Componente.props = { ...Componente.props, ...PROPS_ULTIMA_COMPRA };
}

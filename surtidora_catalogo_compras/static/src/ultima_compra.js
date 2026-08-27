/** @odoo-module **/
// La tarjeta del catálogo pasa TODO `productCatalogData` como props del
// componente de la línea (t-props="productCatalogData"). Los datos nuevos que
// manda el servidor hay que declararlos o OWL rechaza el render.
//
// Se declaran en las clases MÁS DERIVADAS, no en la base: cada subclase copia
// `props` con un spread en el cuerpo de la clase, y eso ya corrió cuando este
// archivo se carga. Parchar la base a estas alturas no llegaría a las hijas.
import { ProductCatalogPurchaseOrderLine } from "@purchase/product_catalog/purchase_order_line/purchase_order_line";
import { ProductCatalogPurchaseSuggestOrderLine } from "@purchase_stock/product_catalog/record/purchase_order_line";

const PROPS_SURTIDORA = {
    // última compra a ESTE suplidor
    surtidoraUltimaFecha: { type: String, optional: true },
    surtidoraUltimoPrecio: { type: String, optional: true },
    surtidoraUltimaUnidad: { type: String, optional: true },
    // qué otros suplidores lo han vendido: [{suplidor, fecha, precio}]
    surtidoraOtrosSuplidores: { type: Array, optional: true },
    // el costo de la ficha, solo cuando NO coincide con la tarifa
    surtidoraCosto: { type: String, optional: true },
    surtidoraCostoUnidad: { type: String, optional: true },
    surtidoraCostoEquivale: { type: String, optional: true },
    surtidoraCostoEquivaleUnidad: { type: String, optional: true },
    // cuánto de la última compra se ha vendido, y en cuántos días
    surtidoraRotacion: { type: String, optional: true },
    surtidoraRotacionParada: { type: Boolean, optional: true },
    // quién se lo llevó por última vez
    surtidoraUltimaVentaFecha: { type: String, optional: true },
    surtidoraUltimoCliente: { type: String, optional: true },
};

for (const Componente of [
    ProductCatalogPurchaseOrderLine,
    ProductCatalogPurchaseSuggestOrderLine,
]) {
    Componente.props = { ...Componente.props, ...PROPS_SURTIDORA };
}

# -*- coding: utf-8 -*-
from odoo import api, fields, models


class EtiquetasWizard(models.TransientModel):
    """Imprime etiquetas por producto Y por empaque (REQ-P04 / REQ-I08).

    Cada unidad sale con su código de barras y su precio según la lista
    elegida — misma mecánica de precios de la venta (regla por cantidad)."""
    _name = 'surtidora.etiquetas.wizard'
    _description = 'Imprimir etiquetas de productos y empaques'

    pricelist_id = fields.Many2one(
        'product.pricelist', string='Lista de precios', required=True,
        default=lambda self: self.env['product.pricelist'].search([], limit=1),
        help='Los precios de las etiquetas salen de esta lista (base y empaques).')
    product_ids = fields.Many2many(
        'product.template', string='Productos', required=True,
        default=lambda self: self.env.context.get('active_ids', []))
    incluir_empaques = fields.Boolean(string='Incluir empaques', default=True)

    def action_imprimir(self):
        self.ensure_one()
        return self.env.ref('surtidora_etiquetas.action_report_etiquetas').report_action(self)

    def _etiquetas(self):
        """Datos de cada etiqueta: [{producto, unidad, barcode, precio}, ...]"""
        self.ensure_one()
        etiquetas = []
        for producto in self.product_ids:
            etiquetas.append({
                'nombre': producto.display_name,
                'referencia': producto.default_code or '',
                'unidad': producto.uom_id.name,
                'barcode': producto.barcode or '',
                'precio': self.pricelist_id._get_product_price(
                    producto.product_variant_id, 1.0, uom=producto.uom_id),
            })
            if not self.incluir_empaques:
                continue
            for uom in producto.uom_ids:
                factor = uom._compute_quantity(1.0, producto.uom_id, round=False)
                empaque = self.env['product.uom'].search([
                    ('product_id', '=', producto.product_variant_id.id),
                    ('uom_id', '=', uom.id)], limit=1)
                etiquetas.append({
                    'nombre': producto.display_name,
                    'referencia': producto.default_code or '',
                    'unidad': uom.name,
                    'barcode': empaque.barcode or '',
                    'precio': self.pricelist_id._get_product_price(
                        producto.product_variant_id, factor,
                        uom=producto.uom_id) * factor,
                })
        return etiquetas


class ReportEtiquetas(models.AbstractModel):
    _name = 'report.surtidora_etiquetas.report_etiquetas'
    _description = 'Reporte de etiquetas por producto y empaque'

    @api.model
    def _get_report_values(self, docids, data=None):
        wizard = self.env['surtidora.etiquetas.wizard'].browse(docids)
        return {
            'doc_ids': docids,
            'doc_model': 'surtidora.etiquetas.wizard',
            'docs': wizard,
            'etiquetas': wizard._etiquetas(),
        }

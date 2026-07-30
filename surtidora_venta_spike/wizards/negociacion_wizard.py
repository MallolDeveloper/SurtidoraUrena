# -*- coding: utf-8 -*-
from odoo import fields, models


class NegociacionWizard(models.TransientModel):
    _name = 'surtidora.negociacion.wizard'
    _description = 'Spike: pantalla de negociación de la línea de venta'

    line_id = fields.Many2one('sale.order.line', required=True, ondelete='cascade')
    product_id = fields.Many2one(related='line_id.product_id')
    partner_id = fields.Many2one(related='line_id.order_partner_id')
    precio_ids = fields.One2many('surtidora.negociacion.precio', 'wizard_id', string='Precios por empaque')
    stock_ids = fields.One2many('surtidora.negociacion.stock', 'wizard_id', string='Existencia por almacén')
    historial_ids = fields.One2many('surtidora.negociacion.historial', 'wizard_id', string='Últimas compras del cliente')


class NegociacionPrecio(models.TransientModel):
    _name = 'surtidora.negociacion.precio'
    _description = 'Spike negociación: precio por empaque'
    _order = 'factor'

    wizard_id = fields.Many2one('surtidora.negociacion.wizard', required=True, ondelete='cascade')
    uom_id = fields.Many2one('uom.uom', string='Unidad', readonly=True)
    factor = fields.Float(string='Factor', digits=(12, 4), readonly=True)
    precio = fields.Monetary(string='Precio', currency_field='currency_id', readonly=True)
    equivalente_base = fields.Monetary(
        string='Equivale por unidad base', currency_field='currency_id', readonly=True,
        help='Lo que sale la unidad base comprando en este empaque — el argumento '
             'de venta sugestiva ("llévese la caja y le sale a menos el paquete").')
    currency_id = fields.Many2one('res.currency', readonly=True)
    es_actual = fields.Boolean(string='Actual', readonly=True)

    def action_usar(self):
        """Aplica este empaque a la línea; Odoo recalcula el precio por la lista."""
        self.ensure_one()
        self.wizard_id.line_id.product_uom_id = self.uom_id
        return {'type': 'ir.actions.act_window_close'}


class NegociacionStock(models.TransientModel):
    _name = 'surtidora.negociacion.stock'
    _description = 'Spike negociación: existencia por almacén'

    wizard_id = fields.Many2one('surtidora.negociacion.wizard', required=True, ondelete='cascade')
    warehouse_id = fields.Many2one('stock.warehouse', string='Almacén', readonly=True)
    existencia = fields.Float(readonly=True)
    reservada = fields.Float(readonly=True)
    disponible = fields.Float(readonly=True)
    uom_id = fields.Many2one('uom.uom', string='Unidad', readonly=True)


class NegociacionHistorial(models.TransientModel):
    _name = 'surtidora.negociacion.historial'
    _description = 'Spike negociación: últimas compras del cliente'
    _order = 'fecha desc'

    wizard_id = fields.Many2one('surtidora.negociacion.wizard', required=True, ondelete='cascade')
    fecha = fields.Datetime(readonly=True)
    orden = fields.Char(string='Orden', readonly=True)
    cantidad = fields.Float(readonly=True)
    uom_id = fields.Many2one('uom.uom', string='Unidad', readonly=True)
    precio = fields.Monetary(string='Precio pagado', currency_field='currency_id', readonly=True)
    currency_id = fields.Many2one('res.currency', readonly=True)

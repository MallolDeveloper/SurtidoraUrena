# -*- coding: utf-8 -*-
from odoo import fields, models


class AutorizacionPrecio(models.Model):
    """Registro de auditoría: cada precio autorizado queda aquí (quién, qué, cuánto).

    Es el corazón reutilizable del módulo: cualquier pantalla de venta
    (backend, POS o la definitiva de Fase C) crea y consulta estos registros.
    """
    _name = 'surtidora.autorizacion.precio'
    _description = 'Autorización de precio en venta'
    _order = 'create_date desc'

    company_id = fields.Many2one(
        'res.company', required=True, index=True,
        default=lambda self: self.env.company)
    line_id = fields.Many2one('sale.order.line', string='Línea de venta', ondelete='set null')
    order_ref = fields.Char(string='Orden', help='Referencia de la orden al momento de autorizar.')
    product_id = fields.Many2one('product.product', string='Producto', required=True)
    uom_id = fields.Many2one('uom.uom', string='Unidad', required=True)
    cantidad = fields.Float(string='Cantidad')
    precio_lista = fields.Monetary(string='Precio de lista', currency_field='currency_id')
    precio_autorizado = fields.Monetary(string='Precio autorizado', currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', required=True)
    solicitante_id = fields.Many2one(
        'res.users', string='Solicitado por', required=True,
        help='Usuario de la sesión donde se pidió la autorización (el cajero/vendedor).')
    autorizador_id = fields.Many2one(
        'res.users', string='Autorizado por', required=True,
        help='Supervisor cuyo PIN validó la autorización (RB-01).')
    partner_id = fields.Many2one('res.partner', string='Cliente')
    motivo_id = fields.Many2one(
        'surtidora.motivo.descuento', string='Motivo', ondelete='restrict',
        help='Del catálogo de motivos (punto 6, reunión 7-ago): permite '
             'analizar qué motivos generan más descuentos.')
    nota = fields.Char(string='Nota')
    origen = fields.Selection(
        [('backend', 'Cotización'), ('pos', 'Mostrador (POS)')],
        default='backend', string='Origen')

    def sigue_vigente_para(self, line):
        """La autorización cubre la línea solo si producto, unidad y precio siguen
        siendo los autorizados (si el precio vuelve a bajar, se re-autoriza)."""
        self.ensure_one()
        return (
            self.product_id == line.product_id
            and self.uom_id == line.product_uom_id
            and line.currency_id.compare_amounts(line.price_unit, self.precio_autorizado) >= 0
        )

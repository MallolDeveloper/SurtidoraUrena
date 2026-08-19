# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    requiere_autorizacion_precio = fields.Boolean(
        compute='_compute_requiere_autorizacion_precio',
        help='Hay líneas con precio bajo lista pendientes de autorizar.')

    @api.depends('order_line.price_unit', 'order_line.discount',
                 'order_line.product_uom_qty', 'order_line.product_uom_id',
                 'order_line.autorizacion_id')
    def _compute_requiere_autorizacion_precio(self):
        for order in self:
            order.requiere_autorizacion_precio = bool(order._lineas_pendientes())

    def _lineas_pendientes(self):
        """Líneas vendidas bajo lista y aún sin autorización vigente (RB-01)."""
        self.ensure_one()
        return self.order_line.filtered(lambda l: l._requiere_autorizacion())

    def _lineas_bajo_costo(self):
        """Líneas vendidas bajo costo — bloqueo duro para todos (RB-08)."""
        self.ensure_one()
        if self.company_id.surtidora_permitir_bajo_costo:
            return self.order_line.browse()
        return self.order_line.filtered(lambda l: l._es_bajo_costo())

    def action_confirm(self):
        """Candado al confirmar: primero el bloqueo duro (RB-08), luego las
        autorizaciones pendientes (RB-01)."""
        for order in self:
            bajo_costo = order._lineas_bajo_costo()
            if bajo_costo:
                raise UserError(_(
                    'Venta BAJO COSTO bloqueada (regla de la empresa, sin '
                    'excepciones):\n%s',
                    '\n'.join('  • %s: precio %.2f sin ITBIS < costo %.2f' % (
                        l.product_id.display_name, l.price_reduce_taxexcl, l._costo_en_uom())
                        for l in bajo_costo)))
            pendientes = order._lineas_pendientes()
            if pendientes:
                raise UserError(_(
                    'Hay precios por debajo de la lista sin autorizar:\n%s\n\n'
                    'Use el botón "Autorizar precios" — un supervisor debe '
                    'aprobar con su PIN.',
                    '\n'.join('  • %s: %.2f (lista: %.2f)' % (
                        l.product_id.display_name, l.price_reduce_taxinc, l._precio_de_lista())
                        for l in pendientes)))
        return super().action_confirm()

    def action_abrir_autorizacion_precios(self):
        """Abre el wizard donde el supervisor aprueba con su PIN (REQ-V07/V27)."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Autorizar precios'),
            'res_model': 'surtidora.autorizar.precio.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_order_id': self.id},
        }

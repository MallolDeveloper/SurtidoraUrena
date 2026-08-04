# -*- coding: utf-8 -*-
"""Servidor del panel de mostrador: arma en UNA llamada todo lo que el panel
muestra. La pantalla solo pinta (mismo principio del motor del sugerido)."""
from datetime import datetime

from odoo import _, api, models
from odoo.exceptions import AccessError


class PosPanel(models.AbstractModel):
    _name = 'surtidora.pos.panel'
    _description = 'Datos del panel de contexto del mostrador'

    @api.model
    def info_panel(self, product_id, partner_id=False, pricelist_id=False):
        """Precios por empaque, existencia por almacén y últimas ventas del
        producto a ese cliente (REQ-V03/V04/V06, RB-06)."""
        # Solo usuarios del POS pueden consultar el panel (el sudo de
        # abajo NO debe quedar expuesto a cualquier usuario autenticado).
        if not self.env.user.has_group('point_of_sale.group_pos_user'):
            raise AccessError(_('Solo usuarios del punto de venta.'))
        # sudo puntual: la cajera necesita ver historial/existencias aunque su
        # usuario no tenga acceso a ventas backend — el panel devuelve SOLO los
        # campos que el negocio quiere en mostrador (así opera ADG).
        env = self.sudo().env
        producto = env['product.product'].browse(int(product_id))
        cliente = env['res.partner'].browse(int(partner_id)) if partner_id else None
        pricelist = env['product.pricelist'].browse(int(pricelist_id)) \
            if pricelist_id else env['product.pricelist']
        return {
            'producto': producto.display_name,
            'precios': self._precios_por_unidad(producto, pricelist),
            'almacenes': self._existencia_por_almacen(producto),
            'historial': self._historial_cliente(producto, cliente) if cliente else [],
            'cliente': cliente.display_name if cliente else '',
        }

    def _precios_por_unidad(self, producto, pricelist):
        """Precio de la unidad base y de cada empaque, con el equivalente por
        base — el argumento de venta sugestiva (REQ-V03)."""
        base = producto.uom_id
        filas = []
        for uom in (base | producto.uom_ids):
            factor = uom._compute_quantity(1.0, base, round=False) or 1.0
            if pricelist:
                precio = pricelist._get_product_price(producto, 1.0, uom=uom)
            else:
                precio = producto.list_price * factor
            filas.append({
                'unidad': uom.name,
                'precio': precio,
                'equivalente': precio / factor if factor else precio,
            })
        return filas

    def _existencia_por_almacen(self, producto):
        """Disponible por almacén (REQ-V04)."""
        filas = []
        for almacen in producto.env['stock.warehouse'].search([]):
            grupos = producto.env['stock.quant']._read_group(
                [('product_id', '=', producto.id),
                 ('location_id', 'child_of', almacen.view_location_id.id)],
                [], ['quantity:sum', 'reserved_quantity:sum'])
            cantidad, reservada = grupos[0] if grupos else (0.0, 0.0)
            filas.append({
                'almacen': almacen.name,
                'disponible': (cantidad or 0.0) - (reservada or 0.0),
            })
        return filas

    def _historial_cliente(self, producto, cliente, limite=3):
        """Últimas ventas de ESE producto a ESE cliente, mezclando mostrador
        (POS) y facturación backend (REQ-V06 / RB-06)."""
        comercial = cliente.commercial_partner_id
        env = producto.env  # ya viene con sudo desde info_panel
        ventas = []

        lineas_pos = env['pos.order.line'].search_read(
            [('product_id', '=', producto.id),
             ('order_id.partner_id', 'child_of', comercial.id),
             ('order_id.state', 'in', ('paid', 'done', 'invoiced'))],
            ['qty', 'price_unit', 'order_id'], order='id desc', limit=limite * 2)
        if lineas_pos:
            fechas = {o['id']: o['date_order'] for o in env['pos.order'].search_read(
                [('id', 'in', [l['order_id'][0] for l in lineas_pos])], ['date_order'])}
            for linea in lineas_pos:
                ventas.append({
                    'fecha': fechas.get(linea['order_id'][0]),
                    'cantidad': linea['qty'],
                    'unidad': producto.uom_id.name,
                    'precio': linea['price_unit'],
                    'origen': 'POS',
                })

        lineas_venta = env['sale.order.line'].search_read(
            [('product_id', '=', producto.id),
             ('order_partner_id', 'child_of', comercial.id),
             ('state', '=', 'sale')],
            ['product_uom_qty', 'price_unit', 'product_uom_id', 'order_id'],
            order='id desc', limit=limite * 2)
        if lineas_venta:
            fechas = {o['id']: o['date_order'] for o in env['sale.order'].search_read(
                [('id', 'in', [l['order_id'][0] for l in lineas_venta])], ['date_order'])}
            for linea in lineas_venta:
                ventas.append({
                    'fecha': fechas.get(linea['order_id'][0]),
                    'cantidad': linea['product_uom_qty'],
                    'unidad': linea['product_uom_id'][1] if linea['product_uom_id'] else '',
                    'precio': linea['price_unit'],
                    'origen': 'Factura',
                })

        ventas.sort(key=lambda v: v['fecha'] or datetime.min, reverse=True)
        for venta in ventas:
            venta['fecha'] = venta['fecha'].strftime('%d/%m/%Y') if venta['fecha'] else ''
        return ventas[:limite]

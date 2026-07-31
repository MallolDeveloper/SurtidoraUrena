# -*- coding: utf-8 -*-
from odoo import fields, models


class SugeridoDetalle(models.TransientModel):
    """Popup "Información del producto seleccionado" (captura 14, REQ-C05/C06).

    Se crea ya poblado desde la línea del sugerido (patrón del wizard de
    negociación: el servidor arma los datos, la vista solo los muestra)."""
    _name = 'surtidora.sugerido.detalle'
    _description = 'Detalle del producto en el sugerido'

    product_id = fields.Many2one('product.product', string='Producto', readonly=True)
    uom_base_name = fields.Char(string='Unidad base', readonly=True)
    ultimo_costo_base = fields.Float(string='Último costo (base)', readonly=True, digits='Product Price')
    costo_promedio = fields.Float(
        string='Costo promedio', readonly=True, digits='Product Price',
        help='Costo promedio ponderado de Odoo (sin ITBIS).')
    dias_desde_compra = fields.Integer(string='Días desde la últ. compra', readonly=True)
    existencia_actual = fields.Float(string='Existencia (base)', readonly=True, digits=(16, 2))
    dev_ventas = fields.Float(string='Dev. de ventas', readonly=True, digits=(16, 2))
    dev_compras = fields.Float(string='Dev. de compras', readonly=True, digits=(16, 2))
    mes_ids = fields.One2many('surtidora.sugerido.detalle.mes', 'wizard_id',
                              string='Compras vs ventas por mes')
    compra_ids = fields.One2many('surtidora.sugerido.detalle.compra', 'wizard_id',
                                 string='Últimas compras')
    oc_ids = fields.One2many('surtidora.sugerido.detalle.oc', 'wizard_id',
                             string='OC pendientes')


class SugeridoDetalleMes(models.TransientModel):
    _name = 'surtidora.sugerido.detalle.mes'
    _description = 'Matriz mensual comprado vs vendido'

    wizard_id = fields.Many2one('surtidora.sugerido.detalle', required=True, ondelete='cascade')
    mes = fields.Char(string='Mes', readonly=True)
    comprado = fields.Float(string='Comprado', readonly=True, digits=(16, 2))
    vendido = fields.Float(string='Vendido', readonly=True, digits=(16, 2))


class SugeridoDetalleCompra(models.TransientModel):
    _name = 'surtidora.sugerido.detalle.compra'
    _description = 'Últimas compras del producto (multi-suplidor)'

    wizard_id = fields.Many2one('surtidora.sugerido.detalle', required=True, ondelete='cascade')
    fecha = fields.Datetime(string='Fecha', readonly=True)
    cantidad = fields.Float(string='Cantidad', readonly=True, digits=(16, 2))
    unidad = fields.Char(string='Unidad', readonly=True)
    costo = fields.Float(string='Costo', readonly=True, digits='Product Price')
    suplidor = fields.Char(string='Suplidor', readonly=True)
    orden = fields.Char(string='Orden', readonly=True)


class SugeridoDetalleOC(models.TransientModel):
    _name = 'surtidora.sugerido.detalle.oc'
    _description = 'OC pendientes del producto'

    wizard_id = fields.Many2one('surtidora.sugerido.detalle', required=True, ondelete='cascade')
    orden = fields.Char(string='Orden', readonly=True)
    fecha = fields.Datetime(string='Fecha', readonly=True)
    suplidor = fields.Char(string='Suplidor', readonly=True)
    ordenada = fields.Float(string='Ordenada', readonly=True, digits=(16, 2))
    pendiente = fields.Float(string='Pendiente', readonly=True, digits=(16, 2))
    unidad = fields.Char(string='Unidad', readonly=True)

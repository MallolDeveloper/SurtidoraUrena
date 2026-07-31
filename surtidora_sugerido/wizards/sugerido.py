# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class Sugerido(models.TransientModel):
    """Pantalla del Sugerido de Compras (Fase B, iteración 1).

    La pantalla es un cascarón: los números los pone surtidora.sugerido.motor.
    Iteración 2 agrega los paneles de contexto (histórico mensual, multi-
    suplidor); iteración 3 la impresión en 2 copias."""
    _name = 'surtidora.sugerido'
    _description = 'Sugerido de compras por rotación de ventas'

    company_id = fields.Many2one(
        'res.company', string='Compañía', required=True,
        default=lambda self: self.env.company)
    suplidor_id = fields.Many2one(
        'res.partner', string='Suplidor', required=True,
        domain=[('supplier_rank', '>', 0)])
    fecha_desde = fields.Date(
        string='Analizar ventas desde', required=True,
        default=lambda self: fields.Date.context_today(self) - timedelta(days=365))
    fecha_hasta = fields.Date(
        string='Hasta', required=True,
        default=fields.Date.context_today)
    dias_abastecer = fields.Integer(string='Días a abastecer', default=30, required=True)
    line_ids = fields.One2many('surtidora.sugerido.line', 'wizard_id', string='Sugerido')

    @api.constrains('fecha_desde', 'fecha_hasta', 'dias_abastecer')
    def _check_parametros(self):
        for wizard in self:
            if wizard.fecha_desde >= wizard.fecha_hasta:
                raise UserError(_('El rango de fechas está invertido.'))
            if wizard.dias_abastecer <= 0:
                raise UserError(_('Los días a abastecer deben ser mayores a cero.'))

    def action_calcular(self):
        self.ensure_one()
        filas = self.env['surtidora.sugerido.motor'].calcular(
            self.suplidor_id, self.company_id,
            fields.Datetime.to_datetime(self.fecha_desde),
            fields.Datetime.to_datetime(self.fecha_hasta) + timedelta(days=1),
            self.dias_abastecer)
        self.line_ids.unlink()
        self.line_ids = [(0, 0, fila) for fila in filas]
        return self._reabrir()

    def action_ordenar_lo_sugerido(self):
        """Botón "Ordenar lo sugerido" de ADG: copia la sugerencia a la
        columna editable, redondeada hacia arriba a unidades enteras."""
        self.ensure_one()
        for linea in self.line_ids:
            linea.cantidad_ordenar = max(0, -(-linea.cant_sugerida // 1))
        return self._reabrir()

    def action_quitar_cantidades(self):
        self.ensure_one()
        self.line_ids.write({'cantidad_ordenar': 0})
        return self._reabrir()

    def action_oc_temporal(self):
        """REQ-C07: OC en borrador marcada temporal (negociación en curso)."""
        return self._crear_oc(firme=False)

    def action_oc_firme(self):
        """REQ-C07: OC confirmada — compromiso con el suplidor."""
        return self._crear_oc(firme=True)

    def _crear_oc(self, firme):
        self.ensure_one()
        a_ordenar = self.line_ids.filtered(lambda l: l.cantidad_ordenar > 0)
        if not a_ordenar:
            raise UserError(_('Ninguna línea tiene "Cantidad a ordenar".'))
        orden = self.env['purchase.order'].with_company(self.company_id).create({
            'partner_id': self.suplidor_id.id,
            'company_id': self.company_id.id,
            'surtidora_es_temporal': not firme,
            'order_line': [(0, 0, {
                'product_id': linea.product_id.id,
                'name': self._descripcion_oc(linea),
                'product_qty': linea.cantidad_ordenar,
                'product_uom_id': linea.uom_compra_id.id,
                'price_unit': linea.costo_uom_compra,
                'date_planned': fields.Datetime.now(),
            }) for linea in a_ordenar],
        })
        if firme:
            orden.button_confirm()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Orden de compra %s', _('firme') if firme else _('temporal')),
            'res_model': 'purchase.order',
            'res_id': orden.id,
            'view_mode': 'form',
        }

    def _descripcion_oc(self, linea):
        """La OC lleva la referencia del suplidor (REQ-C04) para que el
        vendedor reconozca sus propios códigos en la impresión."""
        partes = [linea.product_id.display_name]
        if linea.ref_suplidor:
            partes.append(_('Ref. suplidor: %s', linea.ref_suplidor))
        return '\n'.join(partes)

    def _reabrir(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }


class SugeridoLine(models.TransientModel):
    _name = 'surtidora.sugerido.line'
    _description = 'Línea del sugerido de compras'
    _order = 'cant_sugerida desc'

    wizard_id = fields.Many2one('surtidora.sugerido', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Producto', required=True)
    referencia = fields.Char(related='product_id.default_code', string='Referencia')
    uom_compra_id = fields.Many2one('uom.uom', string='Unidad de compra', readonly=True)
    ref_suplidor = fields.Char(string='Ref. suplidor', readonly=True)
    fecha_ultima_compra = fields.Datetime(string='Últ. compra', readonly=True)
    cantidad_ultima_compra = fields.Float(string='Cant. últ. compra', readonly=True, digits=(16, 2))
    existencia_actual = fields.Float(string='Existencia', readonly=True, digits=(16, 2))
    salidas_periodo = fields.Float(string='Salidas del período', readonly=True, digits=(16, 2))
    ventas_dia = fields.Float(string='Ventas × día', readonly=True, digits=(16, 4))
    ordenes_pendientes = fields.Float(string='OC pendientes', readonly=True, digits=(16, 2))
    cant_necesaria = fields.Float(string='Cant. necesaria', readonly=True, digits=(16, 2))
    cant_sugerida = fields.Float(string='Cant. sugerida', readonly=True, digits=(16, 2))
    cantidad_ordenar = fields.Float(string='Cantidad a ordenar', digits=(16, 2))
    costo_uom_compra = fields.Float(
        string='Costo (sin ITBIS)', readonly=True, digits='Product Price',
        help='Costo en la unidad de compra. SIN ITBIS — como lo presenta el '
             'sugerido del sistema actual.')

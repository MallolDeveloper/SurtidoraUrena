# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AutorizarPrecioWizard(models.TransientModel):
    """El supervisor teclea su PIN en la estación del vendedor y aprueba
    las rebajas pendientes de la orden (RB-01, REQ-V07, REQ-V27)."""
    _name = 'surtidora.autorizar.precio.wizard'
    _description = 'Autorizar precios con PIN de supervisor'

    order_id = fields.Many2one('sale.order', required=True, ondelete='cascade')
    linea_ids = fields.One2many('surtidora.autorizar.precio.linea', 'wizard_id')
    # NO required a nivel de campo: hay que poder vaciarlo. Lo exige la
    # vista, y el código valida que venga.
    pin = fields.Char(string='PIN del supervisor')
    motivo_id = fields.Many2one(
        'surtidora.motivo.descuento', string='Motivo', required=True)
    nota = fields.Char(string='Nota (opcional)')

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        order = self.env['sale.order'].browse(vals.get('order_id'))
        if order:
            vals['linea_ids'] = [(0, 0, {
                'line_id': line.id,
                'precio_lista': line._precio_de_lista(),
                'bajo_costo': line._es_bajo_costo(),
            }) for line in order._lineas_pendientes()]
        return vals

    def _borrar_pin(self):
        """Borra el PIN en una transacción APARTE.

        El asistente guarda el PIN en su tabla para poder enviarlo, y quien
        puede leerlo después es justo el vendedor al que se controla (los
        registros del asistente pertenecen a quien los crea). Borrarlo con
        un write normal no sirve: si después se rechaza el PIN, el rollback
        lo devuelve a su sitio. Por eso va con cursor propio, que confirma
        solo (probado: sin esto el PIN quedaba guardado)."""
        if not self.id:
            return
        with self.pool.cursor() as cr:
            cr.execute('UPDATE surtidora_autorizar_precio_wizard '
                       'SET pin = NULL WHERE id = %s', (self.id,))

    def action_autorizar(self):
        self.ensure_one()
        pin = (self.pin or '').strip()
        self._borrar_pin()
        if not pin:
            raise UserError(_('Teclee el PIN del supervisor.'))
        autorizador = self.env['res.users']._surtidora_verificar_pin(pin)
        if not autorizador:
            raise UserError(_('PIN incorrecto o el usuario no es autorizador de precios.'))

        for wl in self.linea_ids:
            line = wl.line_id
            if line._es_bajo_costo():
                # RB-08: ni el PIN autoriza bajo costo
                raise UserError(_(
                    '%s está BAJO COSTO — bloqueado para todos, el PIN no aplica (RB-08).',
                    line.product_id.display_name))
            line.autorizacion_id = self.env['surtidora.autorizacion.precio'].sudo().create({
                'company_id': line.company_id.id,
                'line_id': line.id,
                'order_ref': line.order_id.name,
                'product_id': line.product_id.id,
                'uom_id': line.product_uom_id.id,
                'cantidad': line.product_uom_qty,
                'precio_lista': wl.precio_lista,
                'precio_autorizado': line.price_unit,
                'currency_id': line.currency_id.id,
                'solicitante_id': self.env.user.id,
                'autorizador_id': autorizador.id,
                'partner_id': line.order_partner_id.id,
                'motivo_id': self.motivo_id.id,
                'nota': self.nota,
            })
        return {'type': 'ir.actions.act_window_close'}


class AutorizarPrecioLinea(models.TransientModel):
    _name = 'surtidora.autorizar.precio.linea'
    _description = 'Línea pendiente de autorización'

    wizard_id = fields.Many2one('surtidora.autorizar.precio.wizard', required=True, ondelete='cascade')
    line_id = fields.Many2one('sale.order.line', required=True, ondelete='cascade')
    product_id = fields.Many2one(related='line_id.product_id', string='Producto')
    uom_id = fields.Many2one(related='line_id.product_uom_id', string='Unidad')
    cantidad = fields.Float(related='line_id.product_uom_qty', string='Cantidad')
    precio_lista = fields.Monetary(currency_field='currency_id', string='Precio de lista', readonly=True)
    # price_unit es Float (no Monetary) en sale.order.line — el related debe coincidir
    precio_propuesto = fields.Float(
        related='line_id.price_unit', string='Precio propuesto', digits='Product Price')
    currency_id = fields.Many2one(related='line_id.currency_id')
    bajo_costo = fields.Boolean(string='¡Bajo costo!', readonly=True)

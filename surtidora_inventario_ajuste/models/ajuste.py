# -*- coding: utf-8 -*-
"""Ajustes de inventario con motivo y autorización (REQ-I04).

Un ajuste cambia la existencia sin comprar ni vender: es la puerta por la
que se puede sacar mercancía del sistema sin dejar rastro. En ADG el ajuste
no pide motivo — viene VACÍO en 295 de los últimos 300.

DÓNDE ESTÁ LA COMPUERTA (revisión adversaria 14-ago): en la creación del
`stock.move` de inventario, NO en el botón. El botón es una de varias vías
—«Aplicar», «Aplicar todo», el campo de aplicación automática, o un simple
write por RPC— y todas terminan creando ese movimiento. Además la compuerta
falla CERRADA: sin vale de autorización no hay ajuste, punto.

EL VALE es un permiso de un solo uso emitido por el asistente después de
validar la clave del supervisor. No alcanza con poner una bandera en el
contexto (eso lo puede hacer cualquiera por RPC): el vale es un registro
que solo el asistente puede crear."""
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import float_is_zero

CTX_VALE = 'surtidora_ajuste_vale'


class MotivoAjuste(models.Model):
    _name = 'surtidora.motivo.ajuste'
    _description = 'Motivo de ajuste de inventario'
    _order = 'sequence, id'

    name = fields.Char(string='Motivo', required=True)
    nota = fields.Char(string='Nota', help='Cuándo aplica este motivo.')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _nombre_unico = models.Constraint('unique(name)', 'Ese motivo ya existe.')


class AjusteVale(models.Model):
    """Permiso de un solo uso para aplicar un ajuste.

    Nadie tiene permiso de creación sobre este modelo: solo lo crea el
    asistente (con sudo) tras validar la clave del supervisor. Por eso
    sirve de credencial — a diferencia de una bandera de contexto, que
    cualquiera puede inventarse desde afuera."""
    _name = 'surtidora.ajuste.vale'
    _description = 'Vale de autorización de ajuste'

    token = fields.Char(required=True, index=True, copy=False)
    usado = fields.Boolean(default=False)
    user_id = fields.Many2one('res.users', required=True, ondelete='restrict')
    autorizador_id = fields.Many2one('res.users', required=True, ondelete='restrict')
    quant_ids = fields.Many2many('stock.quant')

    @api.model
    def _validar(self, token):
        """Vale vigente para ESTE usuario, sin usar. Devuelve el vale o
        vacío. No se marca usado aquí: un mismo permiso cubre todos los
        movimientos de UNA aplicación."""
        if not token:
            return self.browse()
        limite = fields.Datetime.subtract(fields.Datetime.now(), minutes=15)
        return self.sudo().search([
            ('token', '=', token),
            ('usado', '=', False),
            ('user_id', '=', self.env.uid),
            ('create_date', '>=', limite),
        ], limit=1)


class AjusteBitacora(models.Model):
    """Quién ajustó qué, cuánto y por qué. Sin edición ni borrado para
    nadie — tampoco para el administrador: la ACL se refuerza en el
    modelo, porque una bitácora que el auditado puede alterar no es
    bitácora."""
    _name = 'surtidora.ajuste.bitacora'
    _description = 'Bitácora de ajustes de inventario'
    _order = 'create_date desc, id desc'
    _rec_name = 'product_id'

    company_id = fields.Many2one(
        'res.company', required=True, default=lambda s: s.env.company)
    product_id = fields.Many2one('product.product', string='Producto',
                                 required=True, ondelete='restrict')
    location_id = fields.Many2one('stock.location', string='Ubicación',
                                  ondelete='restrict')
    uom_id = fields.Many2one('uom.uom', string='Unidad', ondelete='restrict')
    cantidad_sistema = fields.Float(string='Cantidad en sistema')
    cantidad_contada = fields.Float(string='Cantidad contada')
    diferencia = fields.Float(string='Diferencia')
    valor_diferencia = fields.Monetary(
        string='Valor de la diferencia', currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', required=True)
    motivo_id = fields.Many2one('surtidora.motivo.ajuste', string='Motivo',
                                required=True, ondelete='restrict')
    motivo_texto = fields.Char(
        string='Motivo (como se registró)',
        help='Copia del nombre del motivo al momento del ajuste: si luego '
             'se renombra el catálogo, la historia no cambia.')
    nota = fields.Char(string='Nota')
    solicitante_id = fields.Many2one('res.users', string='Ajustó',
                                     required=True, ondelete='restrict')
    autorizador_id = fields.Many2one('res.users', string='Autorizó',
                                     required=True, ondelete='restrict')

    def write(self, vals):
        raise AccessError(_('La bitácora de ajustes no se puede modificar.'))

    def unlink(self):
        raise AccessError(_('La bitácora de ajustes no se puede borrar.'))


class StockMove(models.Model):
    _inherit = 'stock.move'

    @api.model_create_multi
    def create(self, vals_list):
        """LA COMPUERTA. Todo ajuste de inventario —venga del botón de la
        línea, de «Aplicar todo», del campo de aplicación automática o de
        un write por RPC— termina creando un movimiento con is_inventory.
        Sin vale de autorización vigente, no se crea."""
        if any(vals.get('is_inventory') for vals in vals_list):
            vale = self.env['surtidora.ajuste.vale']._validar(
                self.env.context.get(CTX_VALE))
            if not vale:
                raise UserError(_(
                    'Los ajustes de inventario necesitan un motivo y la '
                    'clave de un supervisor.\n\n'
                    'Use el botón «Aplicar» de la pantalla de inventario '
                    'físico: ahí se pide la autorización.'))
        return super().create(vals_list)


class StockQuant(models.Model):
    _inherit = 'stock.quant'

    def action_apply_inventory(self):
        """Abre el asistente de autorización. La compuerta de verdad está
        en `stock.move.create`; esto solo es el camino cómodo para la
        cajera/encargado (si alguien llegara por otra vía, el movimiento
        se rechaza igual)."""
        if self.env.context.get(CTX_VALE):
            return super().action_apply_inventory()
        pendientes = self.filtered(lambda q: not float_is_zero(
            q.inventory_quantity - q.quantity,
            precision_rounding=q.product_uom_id.rounding or 0.01))
        if not pendientes:
            # falla CERRADA: nunca aplicar por el camino de escape
            raise UserError(_('No hay diferencias por ajustar en estas líneas.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Autorizar ajuste de inventario'),
            'res_model': 'surtidora.ajuste.autorizacion',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_quant_ids': [(6, 0, pendientes.ids)]},
        }

    def surtidora_datos_ajuste(self):
        """Foto de cada línea ANTES de aplicar. La diferencia se recalcula
        aquí (el campo almacenado puede haber quedado viejo si la
        existencia se movió después del conteo) y el costo se lee con la
        compañía del quant, que es la que valora ese inventario."""
        filas = []
        for quant in self:
            compania = quant.company_id or self.env.company
            diferencia = quant.inventory_quantity - quant.quantity
            costo = quant.product_id.with_company(compania).standard_price
            filas.append({
                'product_id': quant.product_id.id,
                'location_id': quant.location_id.id,
                'uom_id': quant.product_uom_id.id,
                'cantidad_sistema': quant.quantity,
                'cantidad_contada': quant.inventory_quantity,
                'diferencia': diferencia,
                'valor_diferencia': diferencia * costo,
                'currency_id': compania.currency_id.id,
                'company_id': compania.id,
            })
        return filas

# -*- coding: utf-8 -*-
from odoo import _, fields, models
from odoo.exceptions import UserError


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
    # El costo del MOMENTO. Sin esto la excepción de bajo costo no se puede
    # medir después: standard_price cambia con cada compra, y dentro de seis
    # meses nadie puede saber si aquella venta fue un 5% o un 40% bajo costo.
    costo = fields.Monetary(
        string='Costo al autorizar', currency_field='currency_id',
        help='Costo del producto en el instante de autorizar, sin ITBIS. Se '
             'calcula en el servidor: es lo que permite medir después cuánto '
             'se dejó de ganar.')
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
    # Copia del NOMBRE del motivo, no solo el enlace: el catálogo es editable
    # y renombrar «Vencimiento próximo» a «Promoción» reescribiría en silencio
    # la razón de todas las rebajas pasadas. Mismo patrón que la bitácora de
    # ajustes de inventario.
    motivo_texto = fields.Char(string='Motivo (al autorizar)', readonly=True)
    nota = fields.Char(string='Nota')
    origen = fields.Selection(
        [('backend', 'Cotización'), ('pos', 'Mostrador (POS)')],
        default='backend', string='Origen')

    # ------------------------------------------------------------------
    # Una bitácora no se edita: es la prueba de quién autorizó qué
    # ------------------------------------------------------------------
    # El create=false/edit=false/delete=false de la vista es solo pantalla; el
    # ACL daba escritura al Gerente de Ventas, que suele ser el jefe de quien
    # pide las rebajas. Con exportar, cambiar el autorizador y reimportar,
    # la bitácora quedaba alterada sin dejar huella.
    def write(self, valores):
        if not self.env.su:
            raise UserError(_(
                'La bitácora de autorizaciones no se modifica: es la prueba de '
                'quién autorizó qué. Si un registro está mal, deje constancia '
                'en la nota de una autorización nueva.'))
        return super().write(valores)

    def unlink(self):
        if not self.env.su:
            raise UserError(_('La bitácora de autorizaciones no se borra.'))
        return super().unlink()

    def sigue_vigente_para(self, line):
        """La autorización cubre la línea solo si producto, unidad y precio siguen
        siendo los autorizados (si el precio vuelve a bajar, se re-autoriza).

        Se compara con price_reduce_taxinc —lo que el cliente paga por unidad,
        con el descuento ya aplicado— y no con price_unit: si no, bastaba con
        autorizar 90.00 y luego escribir 99% en la columna de descuento para
        cobrar 0.90 amparado en la misma autorización."""
        self.ensure_one()
        return (
            self.product_id == line.product_id
            and self.uom_id == line.product_uom_id
            and line.currency_id.compare_amounts(
                line.price_reduce_taxinc, self.precio_autorizado) >= 0
            # y que no hayan SUBIDO la cantidad: el supervisor firmó una
            # rebaja de N unidades, no de las que se le ocurran después
            and line.product_uom_qty <= self.cantidad
        )

# -*- coding: utf-8 -*-
"""El «Último Costo» de la ficha de ADG (bloque Costos y Precios).

Es el costo neto por unidad base de la última compra que ENTRÓ, con su
fecha y su suplidor. `standard_price` sigue siendo el promedio: los dos
conviven, como en ADG, y se comparan de un vistazo."""
from odoo import _, api, fields, models
from odoo.exceptions import AccessError


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    surtidora_ultimo_costo = fields.Float(
        string='Último costo', digits='Product Price',
        help='Lo que se pagó por UNA unidad base en la última recepción de '
             'compra: neto de ITBIS, con el descuento, en pesos. El «Costo» '
             'de al lado es el promedio; este es el de la última vez.')
    surtidora_ultimo_costo_fecha = fields.Date(string='Fecha última compra')
    surtidora_ultimo_costo_partner_id = fields.Many2one(
        'res.partner', string='Último suplidor', ondelete='set null')
    # Cuánto se aleja el último del promedio, en %, para verlo en la ficha
    # sin hacer la cuenta: positivo = la última compra salió más cara.
    surtidora_ultimo_costo_desvio = fields.Float(
        string='Último vs promedio %', digits=(16, 1),
        compute='_compute_surtidora_ultimo_costo_desvio')

    @api.depends('surtidora_ultimo_costo', 'standard_price')
    def _compute_surtidora_ultimo_costo_desvio(self):
        for producto in self:
            promedio = producto.standard_price
            ultimo = producto.surtidora_ultimo_costo
            producto.surtidora_ultimo_costo_desvio = (
                (ultimo - promedio) / promedio * 100 if promedio and ultimo else 0.0)

    def _surtidora_registrar_ultimo_costo(self, costo, fecha, partner):
        """Un solo sitio escribe los tres campos, venga de la recepción o de
        la carga. Se pisa siempre: es «el último», no «el mayor». Con sudo
        porque escribir en la ficha exige «Products / Create», que quien
        valida una recepción no siempre tiene."""
        self.sudo().write({
            'surtidora_ultimo_costo': costo,
            'surtidora_ultimo_costo_fecha': fecha,
            'surtidora_ultimo_costo_partner_id': partner.id if partner else False,
        })

    @api.model
    def surtidora_cargar_ultimo_costo(self, filas):
        """Carga masiva desde ADG el día del corte.

        `filas`: lista de {'ref': default_code, 'costo': float, 'fecha':
        'YYYY-MM-DD', 'suplidor': ref del partner o False}. Devuelve cuántas
        se aplicaron y las referencias que no se encontraron. Solo Compras /
        Administrador puede llamarlo: es una escritura masiva sobre el maestro."""
        if not self.env.user.has_group('purchase.group_purchase_manager'):
            raise AccessError(_('Solo Compras / Administrador puede cargar el último costo.'))
        refs = [f['ref'] for f in filas if f.get('ref')]
        productos = {p.default_code: p for p in self.search(
            [('default_code', 'in', refs)])}
        socios = {}
        codigos = {f['suplidor'] for f in filas if f.get('suplidor')}
        if codigos:
            # solo suplidores: en ADG clientes y suplidores se numeran en
            # secuencias que chocan; los clientes migraron con prefijo CLI-
            # y los suplidores con el código pelado, pero se acota igual
            socios = {s.ref: s for s in self.env['res.partner'].search(
                [('ref', 'in', list(codigos)), ('supplier_rank', '>', 0)])}
        aplicadas, sin_producto = 0, []
        for fila in filas:
            producto = productos.get(fila.get('ref'))
            if not producto:
                sin_producto.append(fila.get('ref'))
                continue
            producto._surtidora_registrar_ultimo_costo(
                float(fila['costo']), fila.get('fecha') or False,
                socios.get(fila.get('suplidor')))
            aplicadas += 1
        return {'aplicadas': aplicadas, 'sin_producto': sin_producto}

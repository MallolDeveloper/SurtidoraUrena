# -*- coding: utf-8 -*-
"""Precios y margen desde la ficha NATIVA del producto (REQ §3.4).

No reemplaza nada de Odoo: es un botón en el formulario estándar que abre
esta ventana. Cubre los dos huecos que el estándar deja al fijar precios:

1. El margen no se ve en ninguna parte — Odoo no tiene campo de margen.
2. El precio del empaque se guarda POR UNIDAD BASE: para poner la caja en
   880 hay que teclear 48.8889. Aquí se teclea 880 y la división la hace
   el servidor.

Toda la lógica de lectura y escritura vive en `surtidora.precios.motor`,
que ya estaba construido y revisado; esto solo lo presenta.

El margen se calcula como lo entiende el negocio: sobre el costo CON
ITBIS, igual que el `benef` de ADGSystems, para que los números que vea
Adelso coincidan con los que conoce."""
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class PrecioSugerido(models.TransientModel):
    _name = 'surtidora.precio.sugerido'
    _description = 'Precios y margen del producto'

    product_tmpl_id = fields.Many2one('product.template', string='Producto',
                                      required=True, readonly=True)
    costo_base = fields.Float(string='Costo sin ITBIS', readonly=True,
                              digits='Product Price')
    itbis_pct = fields.Float(string='ITBIS %', readonly=True)
    margen_objetivo = fields.Float(
        string='Margen objetivo %', default=15.0,
        help='Sobre el costo con ITBIS, igual que en el sistema actual.')
    redondeo = fields.Float(
        string='Redondear a múltiplos de', default=5.0,
        help='El 98% de los precios de la casa son múltiplos de 5.')
    linea_ids = fields.One2many('surtidora.precio.sugerido.linea', 'wizard_id')
    aviso = fields.Text(readonly=True)

    # ------------------------------------------------------------------
    @api.model
    def default_get(self, campos):
        valores = super().default_get(campos)
        tmpl_id = self.env.context.get('active_id')
        if not tmpl_id or self.env.context.get('active_model') != 'product.template':
            raise UserError(_('Abra esta ventana desde la ficha de un producto.'))
        datos = self.env['surtidora.precios.motor'].producto_json(tmpl_id)
        valores.update({
            'product_tmpl_id': datos['template_id'],
            'costo_base': datos['costo_base'],
            'itbis_pct': datos['itbis_pct'],
            'linea_ids': [(0, 0, {
                'lista_id': f['lista_id'],
                'uom_id': f['uom_id'],
                'factor': f['factor'],
                'costo_total': f['costo_total_itbis'],
                'precio_actual': f['precio_total'],
                'precio_nuevo': f['precio_total'],
            }) for f in datos['filas']],
        })
        avisos = []
        if not datos['costo_base']:
            avisos.append(_('El producto no tiene costo: sin costo no hay '
                            'margen que calcular ni piso que respetar.'))
        if datos['reglas_extra']:
            avisos.append(_(
                'Este producto tiene %s regla(s) de precio que esta ventana '
                'NO toca (variantes, promociones con fecha o cantidades '
                'fraccionadas). Se editan desde la lista de precios.')
                % datos['reglas_extra'])
        valores['aviso'] = '\n'.join(avisos)
        return valores

    # ------------------------------------------------------------------
    def action_sugerir(self):
        """Del margen objetivo al precio, redondeado. Nunca por debajo del
        costo: RB-08 lo rechazaría al aplicar."""
        self.ensure_one()
        paso = self.redondeo if self.redondeo > 0 else 0.01
        for linea in self.linea_ids:
            if not linea.costo_total:
                continue
            bruto = linea.costo_total * (1 + self.margen_objetivo / 100.0)
            sugerido = round(bruto / paso) * paso
            # el redondeo hacia abajo no puede meterlo bajo costo
            while sugerido < linea.costo_total:
                sugerido += paso
            linea.precio_nuevo = sugerido
        return self._reabrir()

    def action_aplicar(self):
        """Escribe solo las filas que cambiaron, por el motor (que valida
        RB-08, recalcula el factor en servidor y deja la bitácora)."""
        self.ensure_one()
        cambios = [{
            'lista_id': l.lista_id.id,
            'lista': l.lista_id.name,
            'uom_id': l.uom_id.id,
            'precio_total': l.precio_nuevo,
        } for l in self.linea_ids
            if l.precio_nuevo and abs(l.precio_nuevo - l.precio_actual) >= 0.01]
        if not cambios:
            raise UserError(_('No hay ningún precio modificado.'))
        resultado = self.env['surtidora.precios.motor'].guardar_json(
            self.product_tmpl_id.id, cambios)
        mensaje = _('%s precio(s) actualizados.') % resultado['cambios']
        if resultado.get('avisos'):
            mensaje += '\n' + '\n'.join(resultado['avisos'])
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'title': _('Precios actualizados'), 'message': mensaje,
                       'type': 'success', 'sticky': bool(resultado.get('avisos')),
                       'next': {'type': 'ir.actions.act_window_close'}},
        }

    def _reabrir(self):
        return {'type': 'ir.actions.act_window', 'res_model': self._name,
                'res_id': self.id, 'view_mode': 'form', 'target': 'new',
                'context': self.env.context}


class PrecioSugeridoLinea(models.TransientModel):
    _name = 'surtidora.precio.sugerido.linea'
    _description = 'Precio por lista y unidad'
    _order = 'lista_id, factor'

    wizard_id = fields.Many2one('surtidora.precio.sugerido', ondelete='cascade')
    lista_id = fields.Many2one('product.pricelist', string='Lista', readonly=True)
    uom_id = fields.Many2one('uom.uom', string='Unidad', readonly=True)
    factor = fields.Float(readonly=True, digits=(16, 4))
    costo_total = fields.Float(string='Costo c/ITBIS', readonly=True,
                               digits='Product Price')
    precio_actual = fields.Float(string='Precio actual', readonly=True,
                                 digits='Product Price')
    precio_nuevo = fields.Float(string='Precio nuevo', digits='Product Price',
                                help='Total del empaque completo, como se '
                                     'habla en el mostrador: "la caja a 880".')
    margen_actual = fields.Float(string='Margen actual %',
                                 compute='_compute_margenes')
    margen_nuevo = fields.Float(string='Margen nuevo %',
                                compute='_compute_margenes')

    @api.depends('precio_actual', 'precio_nuevo', 'costo_total')
    def _compute_margenes(self):
        for linea in self:
            costo = linea.costo_total
            linea.margen_actual = ((linea.precio_actual - costo) / costo * 100
                                   if costo else 0.0)
            linea.margen_nuevo = ((linea.precio_nuevo - costo) / costo * 100
                                  if costo else 0.0)

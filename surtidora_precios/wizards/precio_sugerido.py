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
Adelso coincidan con los que conoce.

DISEÑO — por qué el servidor no le cree al navegador
====================================================
El cliente web NO devuelve los campos de solo lectura al guardar, y el
botón «Sugerir precios» guarda el formulario. Las filas llegaban entonces
sin lista, sin unidad y sin costo, y la ventana quedaba en ceros.

Por eso aquí la línea GUARDA lo mínimo —la lista, la unidad y el precio
tecleado— y todo lo demás lo CALCULA el servidor desde el producto. Y por
si el navegador tampoco devuelve la lista y la unidad, `create` las repone
por orden de fila. No queda nada que el cliente pueda perder."""
import math

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class PrecioSugerido(models.TransientModel):
    _name = 'surtidora.precio.sugerido'
    _description = 'Precios y margen del producto'

    product_tmpl_id = fields.Many2one('product.template', string='Producto',
                                      required=True)
    costo_base = fields.Float(string='Costo sin ITBIS', compute='_compute_cabecera',
                              digits='Product Price')
    itbis_pct = fields.Float(string='ITBIS %', compute='_compute_cabecera')
    aviso = fields.Text(compute='_compute_cabecera')
    margen_objetivo = fields.Float(
        string='Margen objetivo %', default=15.0,
        help='Sobre el costo con ITBIS, igual que en el sistema actual.')
    redondeo = fields.Float(
        string='Redondear a múltiplos de', default=5.0,
        help='El 98% de los precios de la casa son múltiplos de 5.')
    linea_ids = fields.One2many('surtidora.precio.sugerido.linea', 'wizard_id')

    @api.depends('product_tmpl_id')
    def _compute_cabecera(self):
        motor = self.env['surtidora.precios.motor']
        for wizard in self:
            if not wizard.product_tmpl_id:
                wizard.costo_base = wizard.itbis_pct = 0.0
                wizard.aviso = ''
                continue
            datos = motor.producto_json(wizard.product_tmpl_id.id)
            wizard.costo_base = datos['costo_base']
            wizard.itbis_pct = datos['itbis_pct']
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
            wizard.aviso = '\n'.join(avisos)

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
            # solo lo mínimo; el resto lo recalcula el servidor
            'linea_ids': [(0, 0, {
                'lista_id': f['lista_id'],
                'uom_id': f['uom_id'],
                'precio_nuevo': f['precio_total'],
            }) for f in datos['filas']],
        })
        return valores

    @api.model_create_multi
    def create(self, lista_valores):
        wizards = super().create(lista_valores)
        wizards._reponer_lineas()
        return wizards

    def _reponer_lineas(self):
        """Si el navegador devolvió las filas sin lista ni unidad, se reponen
        desde el producto. El orden de creación de las líneas es el mismo que
        el de `producto_json`, así que la fila n corresponde a la fila n."""
        motor = self.env['surtidora.precios.motor']
        for wizard in self:
            lineas = wizard.linea_ids.sorted('id')
            if not lineas or all(l.lista_id and l.uom_id for l in lineas):
                continue
            filas = motor.producto_json(wizard.product_tmpl_id.id)['filas']
            if len(filas) != len(lineas):
                raise UserError(_(
                    'Los precios del producto cambiaron mientras la ventana '
                    'estaba abierta. Ciérrela y vuelva a abrirla.'))
            for linea, fila in zip(lineas, filas):
                linea.write({'lista_id': fila['lista_id'],
                             'uom_id': fila['uom_id']})

    # ------------------------------------------------------------------
    def action_sugerir(self):
        """Del margen objetivo al precio, redondeado. Nunca por debajo del
        costo: RB-08 lo rechazaría al aplicar."""
        self.ensure_one()
        # sin costo no hay margen que aplicar: antes el botón se quedaba
        # callado y parecía averiado (típico en los combos, que no lo llevan)
        if not any(l.costo_total for l in self.linea_ids):
            raise UserError(_(
                'El producto no tiene costo, así que no hay margen que '
                'calcular. Ponga el costo en la pestaña «Compra» del producto '
                'y vuelva a intentarlo; mientras tanto puede teclear los '
                'precios a mano.'))
        paso = self.redondeo if self.redondeo > 0 else 0.01
        for linea in self.linea_ids:
            if not linea.costo_total:
                continue
            bruto = linea.costo_total * (1 + self.margen_objetivo / 100.0)
            sugerido = round(bruto / paso) * paso
            if sugerido < linea.costo_total:
                # el redondeo hacia abajo no puede meterlo bajo costo. Se sube
                # al múltiplo justo por encima del costo de una vez: subir de
                # paso en paso podía dar millones de vueltas con un margen
                # objetivo negativo y un redondeo fino.
                sugerido = math.ceil(linea.costo_total / paso) * paso
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
            if l.lista_id and l.uom_id and l.precio_nuevo
            and abs(l.precio_nuevo - l.precio_actual) >= 0.01]
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
    """Solo se guardan la lista, la unidad y el precio tecleado. Factor,
    costo y precio actual se CALCULAN desde el producto en cada lectura:
    son justamente los campos que el navegador no devolvía y que dejaban la
    fila en ceros."""
    _name = 'surtidora.precio.sugerido.linea'
    _description = 'Precio por lista y unidad'
    _order = 'id'  # mismo orden que `producto_json`; ver `_reponer_lineas`

    wizard_id = fields.Many2one('surtidora.precio.sugerido', ondelete='cascade')
    lista_id = fields.Many2one('product.pricelist', string='Lista')
    uom_id = fields.Many2one('uom.uom', string='Unidad')
    precio_nuevo = fields.Float(string='Precio nuevo', digits='Product Price',
                                help='Total del empaque completo, como se '
                                     'habla en el mostrador: "la caja a 880".')

    factor = fields.Float(compute='_compute_desde_producto', digits=(16, 4))
    costo_total = fields.Float(string='Costo c/ITBIS', digits='Product Price',
                               compute='_compute_desde_producto')
    precio_actual = fields.Float(string='Precio actual', digits='Product Price',
                                 compute='_compute_desde_producto')
    margen_actual = fields.Float(string='Margen actual %',
                                 compute='_compute_desde_producto')
    margen_nuevo = fields.Float(string='Margen nuevo %',
                                compute='_compute_margen_nuevo')

    @api.depends('wizard_id.product_tmpl_id', 'lista_id', 'uom_id')
    def _compute_desde_producto(self):
        motor = self.env['surtidora.precios.motor']
        cache = {}
        for linea in self:
            tmpl = linea.wizard_id.product_tmpl_id
            fila = None
            if tmpl and linea.lista_id and linea.uom_id:
                if tmpl.id not in cache:
                    cache[tmpl.id] = {(f['lista_id'], f['uom_id']): f
                                      for f in motor.producto_json(tmpl.id)['filas']}
                fila = cache[tmpl.id].get((linea.lista_id.id, linea.uom_id.id))
            linea.factor = fila['factor'] if fila else 0.0
            linea.costo_total = fila['costo_total_itbis'] if fila else 0.0
            linea.precio_actual = fila['precio_total'] if fila else 0.0
            linea.margen_actual = (
                (linea.precio_actual - linea.costo_total) / linea.costo_total * 100
                if linea.costo_total else 0.0)

    @api.depends('precio_nuevo', 'costo_total')
    def _compute_margen_nuevo(self):
        for linea in self:
            linea.margen_nuevo = (
                (linea.precio_nuevo - linea.costo_total) / linea.costo_total * 100
                if linea.costo_total else 0.0)

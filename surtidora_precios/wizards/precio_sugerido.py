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
    modo = fields.Selection(
        [('casa', 'Como vende la casa (cada lista con lo suyo)'),
         ('uniforme', 'Un solo margen para las cuatro listas')],
        string='Cómo sugerir', default='casa', required=True,
        help='«Como vende la casa» usa la escalera medida en el propio '
             'catálogo: Mayor con margen ajustado y sin descuento de empaque '
             '—ya es el precio de volumen—, y las otras tres con más margen '
             'en la unidad y descuento al llevar el empaque completo.')
    margen_objetivo = fields.Float(
        string='Margen de la unidad %',
        default=lambda self: self.env.company.surtidora_margen_unidad_pct,
        help='Sobre el costo con ITBIS, igual que en el sistema actual. Se '
             'aplica a la UNIDAD BASE; los empaques salen de ella.')
    descuento_empaque = fields.Float(
        string='Descuento por empaque %',
        default=lambda self: self.env.company.surtidora_descuento_empaque_pct,
        help='Cuánto más barata sale la unidad al llevar el empaque completo. '
             'Así se fijan los precios aquí: el 96% de los empaques del '
             'catálogo está puesto como un descuento sobre el precio unitario, '
             'no con un margen propio.')
    redondeo = fields.Float(
        string='Redondear a múltiplos de', default=5.0,
        help='El 98% de los precios de la casa son múltiplos de 5.')
    linea_ids = fields.One2many('surtidora.precio.sugerido.linea', 'wizard_id')
    # Declarar un empaque desde aquí. La ventana solo puede mostrar las
    # unidades que el producto YA tiene, así que en un producto nuevo no
    # había ninguna fila donde poner el precio del paquete: había que salir
    # a la ficha, crear la unidad de medida y volver. Se declara aquí, que
    # es donde uno está pensando en «la unidad a 5 y el paquete de 25 a 100».
    empaque_nombre = fields.Char(string='Empaque', default='Paquete')
    empaque_vista_previa = fields.Char(compute='_compute_empaque_vista_previa')
    empaque_cantidad = fields.Float(
        string='Trae cuántas unidades', digits=(16, 2),
        help='Cuántas unidades base entran en el empaque. Un paquete de 25 '
             'unidades: 25.')

    @api.depends('product_tmpl_id', 'empaque_nombre', 'empaque_cantidad')
    def _compute_empaque_vista_previa(self):
        """Qué se va a crear exactamente, ANTES de crearlo.

        Sin esto se puede armar un disparate sin enterarse: pasó de verdad con
        un producto cuya unidad base era «Caja de 36 (Paquete)». Al pedir un
        empaque «Paquete» de 36 se creó «Paquete de 36 (Caja de 36)», que son
        36 CAJAS — 1,296 paquetes. El código hizo lo que se le pidió; nadie
        avisó de lo que eso significaba."""
        for wizard in self:
            base = wizard.product_tmpl_id.uom_id
            partes = []
            if base and base.relative_factor and base.relative_factor > 1:
                partes.append(_(
                    '⚠ La unidad base de este producto YA es un empaque: «%(base)s» '
                    'son %(factor)g × %(padre)s. La unidad base debe ser lo que se '
                    'vende SUELTO. Lo que agregue aquí colgará de esa caja, no del '
                    'artículo suelto.',
                    base=base.name, factor=base.relative_factor,
                    padre=base.relative_uom_id.name or ''))
            if base and wizard.empaque_cantidad > 1:
                partes.append(_(
                    'Se creará «%(nombre)s», que son %(cantidad)g × %(base)s.',
                    nombre='%s de %g (%s)' % (
                        (wizard.empaque_nombre or 'Paquete').strip(),
                        wizard.empaque_cantidad, base.name),
                    cantidad=wizard.empaque_cantidad, base=base.name))
            wizard.empaque_vista_previa = '\n'.join(partes)

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
            # el campo «Precio de venta» de la ficha no es lo que se cobra:
            # si va por su cuenta, la ficha enseña un número que nadie cobra
            if datos['lista_ficha'] and not datos['precio_ficha_lista']:
                # sin NINGUNA regla, la tabla sale en 0.00 pero el producto sí
                # se vende: la caja cae al precio de la ficha. Callarlo hacía
                # creer que el producto no tiene precio.
                if datos['precio_ficha']:
                    avisos.append(_(
                        'Este producto no tiene ninguna regla de precio, así '
                        'que la tabla sale en 0.00: hoy el mostrador cobra los '
                        '%(ficha).2f del «Precio de venta» de la ficha, igual '
                        'en las cuatro listas. Si fija precios aquí, pasarán a '
                        'mandar ellos y la ficha los seguirá.',
                        ficha=datos['precio_ficha']))
                else:
                    avisos.append(_(
                        'Este producto no tiene precio en ninguna parte: ni '
                        'reglas de lista ni «Precio de venta» en la ficha. '
                        'Tal como está, el mostrador no puede venderlo.'))
            elif datos['lista_ficha'] and abs(
                    datos['precio_ficha'] - datos['precio_ficha_lista']) >= 0.01:
                avisos.append(_(
                    'El «Precio de venta» de la ficha dice %(ficha).2f pero '
                    '%(lista)s cobra %(real).2f, y lo que se cobra es la lista. '
                    'Al aplicar se pondrá al día la ficha.',
                    ficha=datos['precio_ficha'], lista=datos['lista_ficha'],
                    real=datos['precio_ficha_lista']))
            base = wizard.product_tmpl_id.uom_id
            if base.relative_factor and base.relative_factor > 1:
                avisos.append(_(
                    'La unidad base de este producto es «%(base)s», que ya es un '
                    'empaque de %(factor)g × %(padre)s. Todos los precios de abajo '
                    'se entienden POR ESA CAJA, no por el artículo suelto. Si no '
                    'era la intención, corrija la unidad de medida en la ficha '
                    'antes de fijar precios.',
                    base=base.name, factor=base.relative_factor,
                    padre=base.relative_uom_id.name or ''))
            if datos.get('fraccionadas'):
                avisos.append(_(
                    'Este producto tiene %s regla(s) de precio por cantidades '
                    'menores que una unidad. Odoo aplica siempre la de cantidad '
                    'MAYOR, así que esas mandan sobre la fila base: el «precio '
                    'actual» de aquí no es el que cobra el mostrador. Revíselas '
                    'en la lista de precios antes de tocar nada.')
                    % datos['fraccionadas'])
            escalera = wizard._describir_escalera(datos['filas'])
            if escalera:
                avisos.append(_(
                    'Este producto NO cobra lo mismo en todas las listas: %s. '
                    '«Sugerir precios» aplica un solo margen y las igualaría; '
                    'ajuste el margen de cada fila si quiere conservar la '
                    'diferencia.') % escalera)
            if datos['reglas_extra']:
                avisos.append(_(
                    'Este producto tiene %s regla(s) de precio que esta ventana '
                    'NO toca (variantes o promociones con fecha). Se '
                    'editan desde la lista de precios.')
                    % datos['reglas_extra'])
            wizard.aviso = '\n'.join(avisos)

    @staticmethod
    def _describir_escalera(filas):
        """Si una misma unidad se cobra distinto según la lista, lo describe
        («Paquete: de 4.31 a 6.58»). Devuelve '' si todas van iguales.

        Es el 14% del catálogo: la lista de Mayor suele ir por debajo de las
        demás, y aplanarla de un clic sería perder el precio de mayorista."""
        por_unidad = {}
        for f in filas:
            if f['precio_total']:
                por_unidad.setdefault(f['unidad'], set()).add(round(f['precio_total'], 2))
        partes = ['%s: de %.2f a %.2f' % (unidad, min(precios), max(precios))
                  for unidad, precios in por_unidad.items() if len(precios) > 1]
        return '; '.join(partes)

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
                # el margen ya no se calcula solo: lo pone quien fija el precio
                'margen_nuevo': ((f['precio_total'] - f['costo_total_itbis'])
                                 / f['costo_total_itbis'] * 100)
                if f['costo_total_itbis'] else 0.0,
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
                # con la lista repuesta ya hay costo: el margen puede decir algo
                linea.margen_nuevo = linea._margen_de(linea.precio_nuevo)

    # ------------------------------------------------------------------
    # Del margen al precio: UNA sola definición, la usan el botón de sugerir
    # y la columna de margen editable de cada fila.
    # ------------------------------------------------------------------
    def _paso_redondeo(self):
        self.ensure_one()
        return self.redondeo if self.redondeo > 0 else 0.01

    @staticmethod
    def _redondear(bruto, costo, paso):
        """Al múltiplo pedido, nunca por debajo del costo."""
        precio = round(bruto / paso) * paso
        if precio < costo:
            # el redondeo hacia abajo no puede meterlo bajo costo. Se sube al
            # múltiplo justo por encima de una vez: subir de paso en paso
            # daba millones de vueltas con un margen objetivo negativo.
            precio = math.ceil(costo / paso) * paso
        return precio

    @classmethod
    def precio_desde_margen(cls, costo, margen_pct, paso):
        """Precio redondeado al múltiplo pedido, nunca por debajo del costo."""
        if not costo:
            return 0.0
        return cls._redondear(costo * (1 + margen_pct / 100.0), costo, paso)

    def action_sugerir(self):
        """Del COSTO al precio de venta, en todas las filas y de una vez.

        Se hace en dos pasadas porque así se fijan los precios aquí, medido
        sobre las 30,749 reglas del catálogo: el 96% de los empaques está
        puesto como un DESCUENTO sobre el precio unitario, no con un margen
        propio. Es decir, la casa no piensa «qué margen le pongo a la caja»,
        piensa «la caja sale un 7% más barata por unidad».

        1. La unidad base de cada lista sale del margen sobre el costo.
        2. Cada empaque sale de esa unidad: precio × factor − descuento.

        Ninguno queda bajo costo, que RB-08 lo rechazaría al aplicar."""
        self.ensure_one()
        # sin costo no hay margen que aplicar: antes el botón se quedaba
        # callado y parecía averiado (típico en los combos, que no lo llevan)
        if not any(l.costo_total for l in self.linea_ids):
            raise UserError(_(
                'El producto no tiene costo, así que no hay margen que '
                'calcular. Ponga el costo en la pestaña «Compra» del producto '
                'y vuelva a intentarlo; mientras tanto puede teclear los '
                'precios a mano.'))
        paso = self._paso_redondeo()
        Escalera = self.env['surtidora.margen.lista']
        # 1ª pasada: la unidad base de cada lista, por margen sobre el costo
        unidad_por_lista, ajuste_por_lista = {}, {}
        for linea in self.linea_ids:
            if linea.factor > 1 or not linea.costo_total:
                continue
            margen, descuento = self._ajuste_de(Escalera, linea.lista_id.id)
            ajuste_por_lista[linea.lista_id.id] = descuento
            linea.precio_nuevo = self.precio_desde_margen(
                linea.costo_total, margen, paso)
            linea.margen_nuevo = linea._margen_de(linea.precio_nuevo)
            unidad_por_lista[linea.lista_id.id] = linea.precio_nuevo
        # 2ª pasada: cada empaque, a partir de SU unidad y de la misma lista
        for linea in self.linea_ids:
            if linea.factor <= 1 or not linea.costo_total:
                continue
            unidad = unidad_por_lista.get(linea.lista_id.id)
            if unidad:
                descuento = ajuste_por_lista.get(linea.lista_id.id, 0.0)
                bruto = unidad * linea.factor * (1 - descuento / 100.0)
            else:
                # sin unidad base en esa lista no hay de dónde colgarlo:
                # se cae al margen, que siempre da un número razonable
                margen, _d = self._ajuste_de(Escalera, linea.lista_id.id)
                bruto = linea.costo_total * (1 + margen / 100.0)
            linea.precio_nuevo = self._redondear(bruto, linea.costo_total, paso)
            linea.margen_nuevo = linea._margen_de(linea.precio_nuevo)
        return self._reabrir()

    def _ajuste_de(self, Escalera, lista_id):
        """El (margen, descuento) que toca a esa lista según el modo elegido."""
        self.ensure_one()
        if self.modo == 'uniforme':
            return self.margen_objetivo, self.descuento_empaque
        return Escalera.para_lista(lista_id)

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
        # no se corta aquí aunque no haya precios tocados: puede que lo único
        # desfasado sea el «Precio de venta» de la ficha, y ponerlo al día es
        # trabajo válido. El motor cuenta ese ajuste como un cambio más.
        resultado = self.env['surtidora.precios.motor'].guardar_json(
            self.product_tmpl_id.id, cambios)
        if not resultado['cambios']:
            raise UserError(_('No hay ningún precio modificado.'))
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

    def action_agregar_empaque(self):
        """Le da al producto un empaque nuevo y vuelve con sus filas puestas.

        Reutiliza la unidad de medida si ya existe una igual — hay 321 en el
        sistema y 187 las comparten varios productos, así que lo normal es
        reusar, no crear."""
        self.ensure_one()
        cantidad = self.empaque_cantidad or 0.0
        if cantidad <= 1:
            raise UserError(_(
                'Diga cuántas unidades trae el empaque; tiene que ser más de '
                'una. Un paquete de 25 unidades: 25.'))
        tmpl = self.product_tmpl_id
        base = tmpl.uom_id
        nombre = '%s de %g (%s)' % (
            (self.empaque_nombre or 'Paquete').strip(), cantidad, base.name)
        Uom = self.env['uom.uom'].sudo()   # crear unidades pide «Products / Create»
        uom = Uom.search([('relative_uom_id', '=', base.id),
                          ('relative_factor', '=', cantidad),
                          ('name', '=', nombre)], limit=1)
        if not uom:
            uom = Uom.create({'name': nombre, 'relative_uom_id': base.id,
                              'relative_factor': cantidad})
        if uom in tmpl.uom_ids:
            raise UserError(_('El producto ya tiene el empaque «%s».') % nombre)
        # sudo: escribir en product.template pide «Products / Create», que un
        # Gerente de Ventas no tiene — _verificar_grupo ya dijo quién entra
        tmpl.sudo().uom_ids = [(4, uom.id)]
        return {'type': 'ir.actions.act_window', 'res_model': self._name,
                'view_mode': 'form', 'target': 'new',
                'context': dict(self.env.context,
                                active_id=tmpl.id,
                                active_model='product.template')}

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
    # OJO: campo LLANO, no computado con inverse. Con inverse, el ORM
    # escribía primero `precio_nuevo` y DESPUÉS corría el inverse, que volvía
    # a pasar el precio por el redondeo: teclear 3,883 guardaba 3,885, y un
    # precio bajo costo se subía solo sin que RB-08 llegara a avisar. En el
    # primer guardado pasaba lo contrario — el inverse corría antes de que
    # `_reponer_lineas` pusiera la lista, así que el margen tecleado se perdía
    # en silencio. Con dos onchange el cliente resuelve las dos direcciones y
    # lo que queda en pantalla es exactamente lo que se guarda.
    margen_nuevo = fields.Float(
        string='Margen nuevo %',
        help='Se puede teclear: escriba el margen y el precio se calcula solo, '
             'redondeado; o escriba el precio y aquí verá el margen que deja. '
             'Sirve para dar a Mayor un margen distinto que a Detalle.')

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
            # sin precio todavía el margen no es -100%: es que no hay precio.
            # Enseñar -100.00 en un producto nuevo se lee como si algo
            # estuviera roto, y solo dice que la fila está vacía.
            linea.margen_actual = (
                (linea.precio_actual - linea.costo_total) / linea.costo_total * 100
                if linea.costo_total and linea.precio_actual else 0.0)

    def _margen_de(self, precio):
        self.ensure_one()
        return ((precio - self.costo_total) / self.costo_total * 100
                if self.costo_total else 0.0)

    @api.onchange('precio_nuevo')
    def _onchange_precio_nuevo(self):
        """Se teclea el precio: el margen es el termómetro que lo acompaña."""
        for linea in self:
            linea.margen_nuevo = linea._margen_de(linea.precio_nuevo)

    @api.onchange('margen_nuevo')
    def _onchange_margen_nuevo(self):
        """Se teclea el margen: manda el precio, redondeado. El que queda no
        es el tecleado —20% sobre 90.00 con múltiplos de 5 da 110.00, o sea
        22.2%— y la columna lo muestra: el precio es el maestro y el margen el
        termómetro, igual que en ADG."""
        for linea in self:
            if not linea.costo_total or not linea.wizard_id:
                continue
            linea.precio_nuevo = linea.wizard_id.precio_desde_margen(
                linea.costo_total, linea.margen_nuevo,
                linea.wizard_id._paso_redondeo())
            linea.margen_nuevo = linea._margen_de(linea.precio_nuevo)

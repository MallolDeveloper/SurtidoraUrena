# -*- coding: utf-8 -*-
"""Cobrar en caja una cotización sin perder la venta (P19).

Al cobrar en la caja una cotización («Cotización/orden» → «Cerrar la
orden»), pos_sale confirma la orden de venta DENTRO de la misma
sincronización que guarda la venta de la caja (pos_sale, pos_order.py,
sync_from_ui: `sale_order.action_confirm()`, sin savepoint). Si el candado
de precios (RB-01 / RB-08) lanza un error ahí, se deshace todo y la venta
cobrada no llega al servidor.

No es teórico: en Dev, el 8-ago, la caja «Mostrador Surtidora (spike)»
cobró 45.00 de la S00044 con la excepción bajo costo autorizada con PIN; la
sincronización cayó con «Venta BAJO COSTO bloqueada», la venta no subió y
terminó cancelada al cerrar la caja con el pago dentro.

Tres piezas:

1. La autorización que la caja pidió con motivo + PIN cubre la línea de la
   cotización que se cobró con ella, con los mismos límites que una de
   oficina: no cubre un precio más bajo que el autorizado, ni más cantidad
   que la autorizada, ni más de lo que la caja cobró de esa línea.
2. Si aun así queda una línea sin cubrir, la confirmación que dispara ESE
   cobro no se frena, porque el dinero ya entró: la línea queda marcada y
   la orden lleva una nota interna que dice qué pasó por la caja y qué no.
3. Lo marcado no se entrega ni se factura desde oficina mientras siga sin
   cubrir. Hace falta porque pos_sale confirma la cotización ENTERA aunque
   la caja cobre solo una parte (una línea borrada, menos cantidad, un
   anticipo): sin este freno, lo que nunca pasó por la caja quedaba
   confirmado, con su entrega viva, sin ningún control. Se libera cuando un
   supervisor la autoriza con «Autorizar precios» (RB-01), cuando se corrige
   el precio o cuando se quita la cantidad que no pasó por la caja; lo que va
   BAJO COSTO no admite PIN en oficina (RB-08).

Confirmar desde oficina no cambia: pasa por el candado de siempre.
"""
from markupsafe import Markup, escape

from odoo import _, fields, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _validar_precios_al_confirmar(self):
        """El candado sigue igual para todos, salvo para la confirmación que
        dispara el cobro en caja que se está guardando (P19): ahí no se frena
        la venta, se retiene lo que quede sin cubrir."""
        if self._surtidora_cobrada_ahora_en_caja():
            return self._surtidora_retener_lo_no_cubierto()
        return super()._validar_precios_al_confirmar()

    def _surtidora_retener_lo_no_cubierto(self):
        """Marca las líneas que el candado habría frenado y deja la nota. La
        marca es la que después frena la entrega y la factura desde oficina.
        sudo: quien confirma aquí es la cajera, y la marca es del sistema."""
        self.ensure_one()
        sin_cubrir = self._lineas_bajo_costo() | self._lineas_pendientes()
        if not sin_cubrir:
            return
        sin_cubrir.sudo().surtidora_confirmada_sin_autorizar = True
        self._surtidora_dejar_constancia_de_caja(sin_cubrir)

    def _create_invoices(self, grouped=False, final=False, date=None):
        """P19: lo que la caja confirmó sin autorización no se factura desde
        oficina mientras siga sin cubrir. Solo cuenta lo que de verdad se iba
        a facturar: lo que la caja ya cobró pos_sale lo da por facturado."""
        self.order_line.filtered(
            lambda linea: linea.surtidora_confirmada_sin_autorizar
            and linea.product_uom_id.compare(linea.qty_to_invoice, 0) > 0,
        )._surtidora_frenar_retenidas(_('facturar'))
        return super()._create_invoices(grouped=grouped, final=final, date=date)

    def _surtidora_cobrada_ahora_en_caja(self):
        """¿Esta confirmación la dispara el cobro en caja que se está guardando?

        Se mira en los datos y no en el contexto: el contexto lo manda
        cualquiera por RPC, y con una bandera así se confirmaría desde oficina
        saltándose el candado. Una venta de caja cobrada y escrita en ESTA
        misma transacción solo existe mientras la caja guarda el cobro:
        pos_sale confirma justo después de marcarla pagada. Una orden cobrada
        en caja otro día, devuelta a borrador y confirmada desde oficina, pasa
        por el candado normal."""
        self.ensure_one()
        ahora = self.env.cr.now()
        return any(
            venta.state not in ('draft', 'cancel') and venta.write_date == ahora
            for venta in self.sudo().pos_order_line_ids.order_id)

    def _surtidora_dejar_constancia_de_caja(self, lineas):
        """Nota interna con las líneas que el candado habría frenado.

        Va con sudo porque quien confirma aquí es la cajera, y publicar en la
        orden exige escribir sobre ella. Como nota interna, para que no le
        llegue un correo al cliente, que suele seguir sus cotizaciones."""
        self.ensure_one()
        ventas = self.sudo().pos_order_line_ids.order_id
        titulo = _(
            'Cobrada en caja (%s). La orden se confirmó para no perder el '
            'cobro, pero estas líneas van por debajo de la lista o del costo '
            'sin una autorización que las cubra. Mientras sigan así no se '
            'pueden entregar ni facturar desde oficina: un supervisor las '
            'autoriza con «Autorizar precios», o se corrige el precio, o se '
            'quita la cantidad que no pasó por la caja.',
            ', '.join(v.pos_reference or v.name for v in ventas))
        detalle = ['• ' + linea._surtidora_renglon_de_constancia() for linea in lineas]
        self.sudo().message_post(
            body=Markup('<br/>').join([escape(titulo)] + [escape(d) for d in detalle]),
            subtype_xmlid='mail.mt_note')


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    surtidora_confirmada_sin_autorizar = fields.Boolean(
        string='Confirmada en caja sin autorizar', copy=False, readonly=True,
        help='La caja confirmó la orden al cobrarla y esta línea iba por debajo '
             'de la lista o del costo sin una autorización que la cubriera. '
             'Mientras siga sin cubrir no se entrega ni se factura desde '
             'oficina (P19).')

    def _requiere_autorizacion(self):
        """RB-01: la rebaja que la caja autorizó con motivo + PIN cubre la
        línea de la cotización que se cobró con ella. Una excepción bajo
        costo también la cubre: la caja la atiende por el camino estricto y
        no pregunta dos veces (bajo_costo.js, isOrderValid)."""
        return (super()._requiere_autorizacion()
                and not self._surtidora_amparada_por_caja(('rb01', 'rb08')))

    def _bajo_costo_bloqueado(self):
        """RB-08: la excepción bajo costo que la caja autorizó (motivo + PIN +
        doble confirmación) cubre la línea de la cotización que se cobró con
        ella. Es la misma política que una venta normal de caja; en oficina
        el PIN sigue sin aplicar."""
        return (super()._bajo_costo_bloqueado()
                and not self._surtidora_amparada_por_caja(('rb08',)))

    # ------------------------------------------------------------------
    # Lo que la caja confirmó sin autorización (P19)
    # ------------------------------------------------------------------
    def _surtidora_retenida(self):
        """¿Línea que la caja confirmó sin autorización y que sigue sin
        cubrir? Se mide en vivo: en cuanto se autoriza o se corrige, suelta."""
        self.ensure_one()
        return bool(self.surtidora_confirmada_sin_autorizar) and (
            self._bajo_costo_bloqueado() or self._requiere_autorizacion())

    def _surtidora_frenar_retenidas(self, accion):
        """Frena `accion` (entregar, facturar) si alguna de estas líneas sigue
        retenida. Quien llama ya dejó solo las que tienen algo pendiente."""
        retenidas = self.filtered(lambda linea: linea._surtidora_retenida())
        if not retenidas:
            return
        raise UserError(_(
            'No se puede %(accion)s: la caja confirmó la orden al cobrarla, '
            'pero estas líneas van por debajo de la lista o del costo sin una '
            'autorización que las cubra:\n%(lineas)s\n\n'
            'Un supervisor debe autorizarlas con «Autorizar precios», o hay que '
            'corregir el precio o quitar la cantidad que no pasó por la caja. '
            'Lo que va BAJO COSTO no admite PIN en oficina (RB-08).',
            accion=accion,
            lineas='\n'.join(
                '  • %s: %s' % (linea.order_id.name, linea._surtidora_renglon_de_constancia())
                for linea in retenidas)))

    def _surtidora_renglon_de_constancia(self):
        """Un renglón de la nota: precio contra lista, si va bajo costo y
        cuánto de la línea pasó de verdad por la caja, que es lo que el
        supervisor necesita para decidir."""
        self.ensure_one()
        cobrado = self._convert_qty(self, self._surtidora_cobrado_en_caja(), 'p2s')
        if self.product_uom_id.compare(cobrado, self.product_uom_qty) >= 0:
            caja = _('cobrada en caja')
        elif self.product_uom_id.compare(cobrado, 0) > 0:
            caja = _('la caja cobró %(cobrado).2f de %(total).2f %(unidad)s; el '
                     'resto NO pasó por la caja',
                     cobrado=cobrado, total=self.product_uom_qty,
                     unidad=self.product_uom_id.name)
        else:
            caja = _('NO pasó por la caja')
        bajo_costo = (_(' — BAJO COSTO: el PIN no aplica en oficina; se corrige '
                        'el precio o se quita la cantidad')
                      if self._bajo_costo_bloqueado() else '')
        return _('%(producto)s: %(precio).2f (lista: %(lista).2f), %(caja)s%(costo)s',
                 producto=self.product_id.display_name,
                 precio=self._cobrado_por_unidad(),
                 lista=self._precio_de_lista(),
                 caja=caja, costo=bajo_costo)

    # ------------------------------------------------------------------
    # La autorización de la caja, medida contra la línea de la cotización
    # ------------------------------------------------------------------
    def _surtidora_amparada_por_caja(self, tipos):
        """¿Alguna autorización de la caja de esos tipos cubre la línea tal
        como está ahora?

        La bitácora de la caja va en la unidad base del producto, por unidad
        y con ITBIS, y la caja pasa la cotización a unidad base al cobrarla
        (pos_sale, read_converted). La línea se lleva a esa misma base antes
        de comparar. Los límites son los de sigue_vigente_para: no cubre un
        precio más bajo que el autorizado ni más cantidad que la autorizada.
        Y la cantidad tiene además el tope de lo que la caja cobró de ESTA
        línea: la misma venta puede llevar otra línea del mismo producto
        rebajada con PIN, y esa fila no autoriza estirar la cotización."""
        self.ensure_one()
        filas = self._surtidora_autorizaciones_de_caja(tipos)
        if not filas:
            return False
        unidad = self.product_id.uom_id
        precio = self.product_uom_id._compute_price(self._cobrado_por_unidad(), unidad)
        cubren = filas.filtered(
            lambda fila: self.currency_id.compare_amounts(
                precio, fila.precio_autorizado) >= 0)
        if not cubren:
            return False
        cantidad = self.product_uom_id._compute_quantity(
            self.product_uom_qty, unidad, round=False)
        tope = min(sum(cubren.mapped('cantidad')), self._surtidora_cobrado_en_caja())
        return unidad.compare(cantidad, tope) <= 0

    def _surtidora_lineas_de_caja(self):
        """Líneas de caja que liquidaron esta línea en una venta cobrada (ni
        borrador ni cancelada). sudo: el enlace es solo para usuarios del
        punto de venta."""
        self.ensure_one()
        return self.sudo().pos_order_line_ids.filtered(
            lambda linea_caja: linea_caja.order_id.state not in ('draft', 'cancel'))

    def _surtidora_cobrado_en_caja(self):
        """Cantidad de esta línea que cobró la caja, en la unidad base del
        producto: la de la caja y la de la bitácora."""
        self.ensure_one()
        return sum(self._surtidora_lineas_de_caja().mapped('qty'))

    def _surtidora_autorizaciones_de_caja(self, tipos):
        """Filas de la bitácora que la caja escribió al cobrar esta línea.

        Solo por la venta enlazada. La referencia no sirve de llave: la manda
        el navegador, y una fila escrita DESPUÉS del cobro con la referencia
        de esa venta quedaría cubriéndola. El enlace se hace al crear la venta
        y al cobrarla (pos_order.py), así que una fila pedida con la venta
        todavía en borrador también llega."""
        self.ensure_one()
        ventas = self._surtidora_lineas_de_caja().order_id
        if not ventas:
            return self.env['surtidora.autorizacion.precio']
        return self.env['surtidora.autorizacion.precio'].sudo().search([
            ('origen', '=', 'pos'),
            ('tipo', 'in', list(tipos)),
            ('product_id', '=', self.product_id.id),
            ('uom_id', '=', self.product_id.uom_id.id),
            ('pos_order_id', 'in', ventas.ids),
        ])

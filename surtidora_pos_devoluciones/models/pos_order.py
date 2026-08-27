# -*- coding: utf-8 -*-
"""Las compuertas de la devolución, en el SERVIDOR.

El motivo y la clave del supervisor se piden en el mostrador, pero pedirlos
solo ahí no es un control: el navegador se puede saltar con tres llamadas al
servidor, que es exactamente lo que ya pasó con el candado de precios. Aquí
se vuelve a comprobar todo cuando la orden baja, que es el único momento en
que el dato es real.

Las reglas de la devolución en EFECTIVO, tal como las fijó el cliente:

    · el efectivo devuelto no puede pasar de lo que se pagó en efectivo
    · tiene que ser la MISMA caja que facturó, y del MISMO día
    · si la gaveta no tiene efectivo suficiente, se bloquea
    · la autoriza un supervisor con su clave, y queda en bitácora

Un bono, una nota de crédito o una venta a crédito todavía sin pagar no
mueven dinero de la gaveta: pasan sin clave.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class PosOrder(models.Model):
    _inherit = 'pos.order'

    surtidora_motivo_dev_id = fields.Many2one(
        'surtidora.motivo.devolucion', string='Motivo de devolución',
        copy=False, index='btree_not_null', ondelete='restrict',
        help='REQ-V18: motivo con el que se registró la devolución '
             '(obligatorio, como en ADG). Lo asigna la cajera desde el POS. '
             'ondelete=restrict: un motivo ya usado se ARCHIVA, no se borra '
             '(borrarlo dejaría las devoluciones históricas sin motivo).')

    @api.model
    def _load_pos_data_fields(self, *args, **kwargs):
        """pos.order hoy carga TODOS sus campos (lista vacía = todos); si el
        core algún día la acota, el motivo debe seguir viajando al POS."""
        campos = super()._load_pos_data_fields(*args, **kwargs)
        if campos:
            campos = list(set(campos) | {'surtidora_motivo_dev_id'})
        return campos

    # ------------------------------------------------------------------
    # La compuerta
    # ------------------------------------------------------------------
    @api.model
    def sync_from_ui(self, orders):
        for orden in orders:
            self._surtidora_revisar_devolucion(orden)
        return super().sync_from_ui(orders)

    @api.model
    def _surtidora_revisar_devolucion(self, orden):
        """Compuerta del servidor sobre el diccionario que manda el mostrador."""
        if not self._surtidora_es_devolucion(orden):
            return

        if not orden.get('surtidora_motivo_dev_id'):
            raise UserError(_(
                'Toda devolución tiene que llevar un motivo. Elíjalo en la '
                'pantalla antes de cobrar.'))

        efectivo = self._surtidora_efectivo_de(orden)
        if not efectivo:
            # bono, nota de crédito o venta a crédito sin pagar: no sale
            # dinero de la gaveta, así que no hay nada que autorizar
            return

        # `_get_refunded_orders` es del core y ya garantiza que sea UNA sola
        originales = self._get_refunded_orders(orden)
        sesion = self.env['pos.session'].browse(orden.get('session_id')).exists()
        problema = self._surtidora_problema_devolucion(
            originales[:1] or None, efectivo, sesion)
        if problema:
            raise UserError(problema)

        if not self._surtidora_autorizacion_para(orden, efectivo):
            raise UserError(_(
                'Devolver %(monto)s en efectivo necesita la clave de un '
                'supervisor. Pídala en la pantalla de pago.',
                monto=self.env.company.currency_id.round(efectivo)))

    # ------------------------------------------------------------------
    # Las cuatro reglas
    # ------------------------------------------------------------------
    @api.model
    def _surtidora_problema_devolucion(self, original, efectivo, sesion):
        """Devuelve el texto del problema, o None si la devolución puede ir.

        Se llama DOS veces —al pedir la clave y al validar— para que el
        cajero se entere del impedimento antes de molestar al supervisor.
        """
        if sesion and not self._surtidora_hay_efectivo(sesion, efectivo):
            return _('La caja no tiene %(monto)s en efectivo. Esta devolución '
                     'no se puede pagar en efectivo.',
                     monto=self.env.company.currency_id.round(efectivo))
        if not original:
            # Devolución sin factura: no hay contra qué comprobar la caja, el
            # día ni lo que se pagó. Se deja pasar bajo la responsabilidad del
            # supervisor, que para eso teclea su clave.
            return None
        # Sin sesión no se puede saber en qué caja estamos. Solo pasa al pedir
        # la clave, y la compuerta del servidor —que sí la conoce— lo vuelve a
        # comprobar antes de guardar nada.
        if sesion and original.config_id != sesion.config_id:
            return _('Esta venta se facturó en «%(caja)s». La devolución en '
                     'efectivo tiene que hacerse en esa misma caja.',
                     caja=original.config_id.display_name)
        hoy = fields.Date.context_today(self)
        dia = fields.Datetime.context_timestamp(self, original.date_order).date()
        if dia != hoy:
            return _('Solo se devuelve en efectivo una venta del día. Esta es '
                     'del %(dia)s: la nota de crédito la tramita contabilidad.',
                     dia=dia)
        disponible = self._surtidora_efectivo_devolvible(original)
        if efectivo > disponible + 0.001:
            return _('De esta venta solo se pagaron %(pagado)s en efectivo, y '
                     'ya se devolvieron %(devuelto)s. El resto lo tramita '
                     'contabilidad.',
                     pagado=self.env.company.currency_id.round(
                         self._surtidora_pagado_en_efectivo(original)),
                     devuelto=self.env.company.currency_id.round(
                         self._surtidora_pagado_en_efectivo(original) - disponible))
        return None

    @api.model
    def _surtidora_efectivo_devolvible(self, original):
        """Lo que se pagó en efectivo, menos lo ya devuelto así.

        Sin restar lo ya devuelto, dos devoluciones de media factura sacarían
        de la gaveta más efectivo del que entró por esa venta.
        """
        # Por dominio, no filtrando en memoria: filtrar obligaría a traerse
        # TODAS las órdenes del sistema para quedarse con dos.
        hijas = self.search([
            ('lines.refunded_orderline_id', 'in', original.lines.ids),
            ('id', '!=', original.id),
        ])
        devuelto = -sum(
            pago.amount for pago in hijas.payment_ids
            if pago.payment_method_id.is_cash_count and pago.amount < 0)
        return self._surtidora_pagado_en_efectivo(original) - devuelto

    @api.model
    def _surtidora_pagado_en_efectivo(self, original):
        return sum(p.amount for p in original.payment_ids
                   if p.payment_method_id.is_cash_count and p.amount > 0)

    @api.model
    def _surtidora_hay_efectivo(self, sesion, efectivo):
        """¿La gaveta aguanta esta salida?

        Se mide contra el saldo TEÓRICO de la sesión (apertura + movimientos),
        que es lo que el sistema cree que hay. El conteo real solo existe al
        cerrar, y para entonces el cliente ya se fue.
        """
        if not sesion or not sesion.config_id.cash_control:
            return True
        return sesion.cash_register_balance_end >= efectivo

    # ------------------------------------------------------------------
    # Lectura del diccionario que manda el mostrador
    # ------------------------------------------------------------------
    @api.model
    def _surtidora_es_devolucion(self, orden):
        """Las tres formas de devolver: el reembolso formal, el preset de
        devolución y la línea negativa tecleada a mano (la «devolución sin
        factura» de ADG). Es el mismo criterio que usa la pantalla."""
        for linea in orden.get('lines') or []:
            if len(linea) < 3 or linea[0] not in (0, 1):
                continue
            valores = linea[2]
            if valores.get('refunded_orderline_id'):
                return True
            if (valores.get('qty') or 0) < 0 and not valores.get('sale_order_line_id') \
                    and not valores.get('sale_order_origin_id'):
                return True
        return False

    @api.model
    def _surtidora_efectivo_de(self, orden):
        """Cuánto EFECTIVO sale de la gaveta con esta devolución.

        Se mira `is_cash_count` del método, no su nombre: quien renombre
        «Efectivo» no debe poder saltarse el control sin querer.
        """
        metodos = {}
        total = 0.0
        for pago in orden.get('payment_ids') or []:
            if len(pago) < 3 or pago[0] not in (0, 1):
                continue
            valores = pago[2]
            importe = valores.get('amount') or 0.0
            if importe >= 0:
                continue
            metodo_id = valores.get('payment_method_id')
            if metodo_id not in metodos:
                metodos[metodo_id] = self.env['pos.payment.method'].browse(
                    metodo_id).exists().is_cash_count
            if metodos[metodo_id]:
                total += -importe
        return total

    @api.model
    def _surtidora_autorizacion_para(self, orden, efectivo):
        """Busca una autorización viva que cubra este monto y la consume."""
        referencias = [r for r in (orden.get('pos_reference'), orden.get('name')) if r]
        if not referencias:
            return False
        Autorizacion = self.env['surtidora.autorizacion.devolucion'].sudo()
        fila = Autorizacion.search([
            ('consumida', '=', False),
            ('order_ref', 'in', referencias),
            ('monto', '>=', efectivo - 0.001),
        ], limit=1)
        if not fila:
            return False
        fila.consumida = True
        return fila

    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, lista_valores):
        ordenes = super().create(lista_valores)
        ordenes._surtidora_enlazar_autorizacion_dev()
        return ordenes

    def _surtidora_enlazar_autorizacion_dev(self):
        """Ata la autorización a la devolución que de verdad se cobró.

        La fila se escribe cuando el supervisor teclea la clave, que es ANTES
        de cobrar: en ese momento la orden todavía no existe. Sin este enlace
        la bitácora no distingue una devolución real de una que se autorizó y
        después se abandonó.
        """
        Autorizacion = self.env['surtidora.autorizacion.devolucion'].sudo()
        for orden in self:
            referencias = [r for r in (orden.pos_reference, orden.name) if r]
            if not referencias:
                continue
            filas = Autorizacion.search([
                ('pos_order_id', '=', False),
                ('order_ref', 'in', referencias),
            ])
            if filas:
                filas.pos_order_id = orden.id

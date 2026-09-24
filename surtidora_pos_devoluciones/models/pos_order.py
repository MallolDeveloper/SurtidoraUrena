# -*- coding: utf-8 -*-
"""Las compuertas de la devolución, en el SERVIDOR.

El motivo y la clave del supervisor se piden en el mostrador, pero pedirlos
solo ahí no es un control: el navegador se puede saltar con tres llamadas al
servidor, que es exactamente lo que ya pasó con el candado de precios. Aquí
se vuelve a comprobar todo cuando la orden baja, que es el único momento en
que el dato es real.

Las reglas de la devolución en EFECTIVO, tal como las fijó el cliente:

    · el efectivo devuelto no puede pasar de lo que se pagó en efectivo
      (NETO: lo recibido menos el vuelto)
    · tiene que ser la MISMA caja que facturó, y del MISMO día
    · si la gaveta no tiene efectivo suficiente, se bloquea
    · la autoriza un supervisor con su clave, y queda en bitácora

Un bono, una nota de crédito o una venta a crédito todavía sin pagar no
mueven dinero de la gaveta: pasan sin clave.

Y si la orden se FACTURA (cliente empresa hoy; toda venta con el módulo
fiscal), una devolución sin factura sale como nota de crédito, no como
factura que le cobra al cliente: ver «La factura».
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
        if not original.date_order:
            # Sin fecha no se puede afirmar que sea del día, y aquí sale
            # dinero: se bloquea. `context_timestamp` con vacío no devuelve
            # None, revienta con un assert — y un assert en la caja es una
            # pantalla de error en la cara del cliente, no un aviso.
            return _('Esta venta no tiene fecha registrada, así que no se '
                     'puede confirmar que sea del día. La devolución la '
                     'tramita contabilidad.')
        hoy = fields.Date.context_today(self)
        dia = fields.Datetime.context_timestamp(self, original.date_order).date()
        if dia != hoy:
            return _('Solo se devuelve en efectivo una venta del día. Esta es '
                     'del %(dia)s: la nota de crédito la tramita contabilidad.',
                     dia=dia)
        disponible = self._surtidora_efectivo_devolvible(original)
        if efectivo > disponible + 0.001:
            return _('De esta venta solo quedaron %(pagado)s en efectivo (lo '
                     'pagado menos el vuelto), y ya se devolvieron '
                     '%(devuelto)s. El resto lo tramita contabilidad.',
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
        # el vuelto de una hija (un cambio que salió con saldo a pagar) no
        # es efectivo devuelto de ESTA venta
        devuelto = -sum(
            pago.amount for pago in hijas.payment_ids
            if pago.payment_method_id.is_cash_count
            and self._surtidora_es_devolucion_de_efectivo(
                pago.amount, pago.is_change))
        return self._surtidora_pagado_en_efectivo(original) - devuelto

    @api.model
    def _surtidora_pagado_en_efectivo(self, original):
        """El efectivo NETO que la venta dejó en la gaveta: recibido − vuelto.

        En Odoo 19 el vuelto es un pago negativo en efectivo (`is_change`,
        «devolver»). Sumando solo los positivos el tope era el BILLETE que
        entregó el cliente, no lo que se quedó en la caja: la orden 47 de Dev
        (+200 y −20 de vuelto) admitía devolver 200 en efectivo por una venta
        de 180. Y con pago mixto era peor: 500 con tarjeta + un billete de
        1,000 (vuelto 500) dejaba devolver en efectivo la venta ENTERA,
        convirtiendo en efectivo lo que se cobró con tarjeta.

        Nunca negativo: una venta que no dejó efectivo no tiene efectivo que
        devolver.
        """
        neto = sum(
            p.amount for p in original.payment_ids
            if p.payment_method_id.is_cash_count
            and not self._surtidora_es_devolucion_de_efectivo(
                p.amount, p.is_change))
        return max(neto, 0.0)

    @api.model
    def _surtidora_es_devolucion_de_efectivo(self, importe, es_vuelto):
        """¿Este pago en efectivo es una DEVOLUCIÓN, o parte de una venta?

        El vuelto no es una devolución. Odoo 19 lo guarda con el signo
        CONTRARIO al pago al que pertenece: negativo en una venta (el cliente
        dio 200 por 180) y positivo en una devolución pagada de más. Así que
        el signo decide, leído al revés si es vuelto. Es el mismo criterio
        que el cuadre de caja (surtidora_cuadre) y que la pantalla
        (efectivo_devolucion.js): si divergen, el tope y el cuadre no
        amarran.
        """
        return (importe < 0) != bool(es_vuelto)

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

        El vuelto no cuenta como salida. En el primer envío ni siquiera viene
        como línea (el core lo crea después, desde `amount_return`), pero una
        orden que se reenvía ya lo trae como pago `is_change`: sin este
        criterio, un cambio con saldo a pagar pediría clave por su vuelto.
        """
        metodos = {}
        total = 0.0
        for pago in orden.get('payment_ids') or []:
            if len(pago) < 3 or pago[0] not in (0, 1):
                continue
            valores = pago[2]
            importe = valores.get('amount') or 0.0
            if not self._surtidora_es_devolucion_de_efectivo(
                    importe, valores.get('is_change')):
                continue
            metodo_id = valores.get('payment_method_id')
            if metodo_id not in metodos:
                metodos[metodo_id] = self.env['pos.payment.method'].browse(
                    metodo_id).exists().is_cash_count
            if metodos[metodo_id]:
                total += -importe
        return max(total - self._surtidora_vuelto_que_regresa(orden), 0.0)

    @api.model
    def _surtidora_vuelto_que_regresa(self, orden):
        """En una devolución pagada de MÁS (se teclean −200 por −180), Odoo 19
        manda la diferencia en `amount_return` con signo POSITIVO y la asienta
        después como pago `is_change` en efectivo: esos 20 vuelven a la
        gaveta, no salen. En una venta `amount_return` es negativo (el vuelto
        que se entrega) y aquí no cuenta. Si la orden ya trae el vuelto como
        línea (reenvío), el bucle de arriba ya lo descontó."""
        ya_en_lineas = any(len(p) >= 3 and p[2].get('is_change')
                           for p in orden.get('payment_ids') or [])
        return 0.0 if ya_en_lineas else max(orden.get('amount_return') or 0.0, 0.0)

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
    # La factura
    # ------------------------------------------------------------------
    def _prepare_invoice_vals(self):
        """Una devolución sin factura FACTURADA sale como nota de crédito.

        El core elige el documento solo por `is_refund` (pos_order.py:869), y
        `is_refund` lo marcan el botón «Reembolsar» del POS y la devolución
        del backend («Return Products»). La
        línea negativa tecleada a mano (la «devolución sin factura» de ADG)
        llega con is_refund=False, así que el core arma una FACTURA. Como ya
        volteó las cantidades porque el total es negativo (:1846-1862), esa
        factura sale POSITIVA: se publica sin error y le COBRA al cliente lo
        que se le devolvía (−1 BOKA15 en efectivo: INV de 100 + el débito del
        pago de −100 = el cliente queda debiendo 200). Con todas las ventas
        facturadas (NCF), esto pasaría en cada devolución sin factura.

        Solo cambia el tipo de documento, y va DESPUÉS de super() a propósito.
        Las líneas ya se calcularon para out_invoice sin is_refund
        (qty_sign=+1, :208), el mismo signo que el core usa para un reembolso
        nativo en out_refund: la nota sale con cantidades y total positivos,
        igual que RINV/2026/00006 (orden 53). Pedir out_refund ANTES haría
        que :210 volteara otra vez las cantidades y la nota saldría negativa.

        No se marca is_refund: el core guarda los subtotales de un reembolso
        nativo con otro signo, y voltearlo solo en el servidor cambia el
        margen (orden 31: 27.97 → 197.47) y el reporte de ventas.

        Fiscal: con l10n_do_accounting la nota de crédito exige el NCF
        modificado (account_move.py:789-791). Lo pondrá el futuro
        surtidora_pos_fiscal con el NCF de ADG de la venta de origen, y tiene
        que depender de este módulo (y de l10n_do_pos si algún día se usa:
        lee move_type después de su super(), pos_order.py:349, y por debajo
        de este vería out_invoice).
        """
        valores = super()._prepare_invoice_vals()
        if valores.get('move_type') == 'out_invoice' \
                and self._surtidora_es_nota_de_credito():
            valores['move_type'] = 'out_refund'
        return valores

    def _surtidora_es_nota_de_credito(self):
        """¿El core ya volteó las cantidades de TODAS estas órdenes?

        Es el mismo predicado del core (`amount_total < 0.0`,
        pos_order.py:1846): el documento se voltea exactamente cuando se
        voltearon las líneas. Una mixta con total ≥ 0 sigue siendo factura
        (con su línea negativa); con total < 0, nota de crédito.

        `all()` y no la suma: en un lote con signos mezclados cada orden
        viene volteada por su cuenta y ningún tipo de documento cuadra, así
        que se deja lo nativo. La caja factura de a una orden, pero el
        asistente «Facturar» del backend (pos.make.invoice, consolidado por
        defecto) puede juntar varias: una devolución sin factura mezclada
        con ventas en ese lote sale mal, así que se facturan por separado.
        """
        return bool(self) and all(orden.amount_total < 0.0 for orden in self)

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

        Solo se ata la CONSUMIDA. Una autorización sirve para una devolución:
        si la cajera pide la clave, abandona y la vuelve a pedir, quedan dos
        filas y solo la segunda se cobró. Atándolas todas, la abandonada
        aparecía como cobrada —tapando justo el filtro «Autorizadas sin
        cobrar», que existe para cazar eso— y la columna de monto, que va
        sumada en la lista, contaba el dinero dos veces.
        """
        Autorizacion = self.env['surtidora.autorizacion.devolucion'].sudo()
        for orden in self:
            referencias = [r for r in (orden.pos_reference, orden.name) if r]
            if not referencias:
                continue
            # `_surtidora_autorizacion_para` ya la marcó consumida durante el
            # sync, justo antes de este create, así que aquí hay exactamente
            # una. Sin `limit`: si algún día hubiera dos, que se vea en la
            # bitácora en vez de quedar una silenciosamente fuera.
            filas = Autorizacion.search([
                ('pos_order_id', '=', False),
                ('consumida', '=', True),
                ('order_ref', 'in', referencias),
            ])
            if filas:
                filas.pos_order_id = orden.id

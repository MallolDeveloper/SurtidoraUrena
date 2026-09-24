# -*- coding: utf-8 -*-
"""DC-5: lo que se fió vuelve a la cuenta del cliente.

La regla «un fiado no se devuelve en efectivo» (surtidora_pos_devoluciones)
solo mide el efectivo. Por las otras puertas el fiado seguía saliendo:
devuelto con «Bono / Nota de Crédito», el cliente gastaba el bono enseguida
mientras la factura fiada seguía abierta por el total. El mismo dinero
servía dos veces (liberaba cupo y se gastaba), que es justo DC-5. Devuelto
con tarjeta o transferencia, quedaba registrado que se le devolvía dinero a
quien nunca pagó.

La puerta correcta es «Crédito (Cuenta Cliente)» negativo: el cierre lo
aplica a la deuda (pos.session._surtidora_aplicar_devoluciones) y, si el
cliente ya no debe nada, queda como saldo a favor que sí puede gastar como
bono. El candado de crédito deja pasar siempre un monto negativo
(surtidora.pos.credito.verificar), así que esa puerta nunca está cerrada.
"""
from odoo import _, api, models
from odoo.exceptions import UserError
from odoo.tools import float_compare
from odoo.tools.misc import format_amount


class PosOrder(models.Model):
    _inherit = 'pos.order'

    def _process_saved_order(self, draft):
        """La compuerta corre al cobrar, sobre la orden YA guardada.

        No sobre el diccionario que manda el mostrador: el POS 19 no reenvía
        las líneas ni los pagos que ya subieron y no cambiaron
        (related_models/serialization.js). Una devolución que subió antes en
        borrador (por ejemplo, al sincronizar la venta del siguiente cliente)
        llega al cobrarla con `lines: []` y `payment_ids: []`; revisando el
        diccionario no se encontraba la venta devuelta y el bono pasaba.

        Aquí la orden ya tiene todas sus líneas y todos sus pagos, incluido
        el vuelto que el core acaba de asentar como línea `is_change`
        (_process_payment_lines corre justo antes). Un UserError deshace
        toda la sincronización, igual que antes: la caja devuelve la orden a
        borrador."""
        if not draft and self.state != 'cancel':
            self._surtidora_revisar_devolucion_fiado()
        return super()._process_saved_order(draft)

    def _surtidora_revisar_devolucion_fiado(self):
        """En la devolución de una venta fiada, lo que sale POR FUERA de la
        cuenta del cliente (efectivo, tarjeta, transferencia o bono) no pasa
        de lo que esa venta se cobró sin fiar, menos lo ya devuelto así. Es
        la misma forma que la regla del efectivo: cada peso vuelve por donde
        entró. Solo para ventas con fiado: la devolución de una venta de
        contado no cambia."""
        self.ensure_one()
        venta = self.lines.refunded_orderline_id.order_id[:1]
        credito = self.env['surtidora.pos.credito']
        fiado = venta.payment_ids.filtered(lambda p: credito._es_fiado(p) and p.amount > 0)
        if not fiado:
            return
        moneda = venta.currency_id
        tope = self._surtidora_devolvible_fuera_de_cuenta(venta)
        # lo que esta devolución entrega por fuera de la cuenta: todo pago que
        # no es fiado, con su signo, vuelto incluido (positivo en una
        # devolución pagada de más, porque esos pesos regresan)
        fuera = -self._surtidora_cobrado_sin_fiar(self)
        if float_compare(fuera, tope, precision_rounding=moneda.rounding) > 0:
            raise UserError(_(
                'La venta %(venta)s se fió: %(fiado)s quedaron a la cuenta del '
                'cliente. Lo devuelto vuelve a esa cuenta con «%(metodo)s», que '
                'primero rebaja lo que debe; si ya no debe nada, le queda como '
                'saldo a favor. Por fuera de la cuenta (efectivo, tarjeta, '
                'transferencia o bono) solo se pueden devolver %(tope)s: lo que '
                'esa venta se cobró sin fiar, menos lo ya devuelto así.',
                venta=venta.pos_reference or venta.name,
                fiado=format_amount(self.env, sum(fiado.mapped('amount')), moneda),
                metodo=fiado[:1].payment_method_id.name,
                tope=format_amount(self.env, tope, moneda)))

    def _surtidora_devolvible_fuera_de_cuenta(self, venta):
        """Lo que la venta se cobró sin fiar (neto del vuelto) menos lo que
        sus otras devoluciones ya entregaron por fuera de la cuenta.

        Sin restar lo ya devuelto, dos devoluciones de media venta a bono
        sacarían más de lo que entró sin fiar. La orden que se está
        revisando no cuenta como «otra»."""
        self.ensure_one()
        dominio = [('lines.refunded_orderline_id', 'in', venta.lines.ids),
                   ('state', 'not in', ('draft', 'cancel')),
                   ('id', '!=', self.id)]
        devuelto = sum(max(-self._surtidora_cobrado_sin_fiar(hija), 0.0)
                       for hija in self.search(dominio))
        return max(self._surtidora_cobrado_sin_fiar(venta) - devuelto, 0.0)

    @api.model
    def _surtidora_cobrado_sin_fiar(self, orden):
        """Suma de los pagos de la orden que no son fiado (el vuelto, que es
        un pago en efectivo, incluido con su signo)."""
        credito = self.env['surtidora.pos.credito']
        return sum(p.amount for p in orden.payment_ids if not credito._es_fiado(p))

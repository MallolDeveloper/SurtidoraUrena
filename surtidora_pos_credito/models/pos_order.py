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


class PosOrder(models.Model):
    _inherit = 'pos.order'

    @api.model
    def sync_from_ui(self, orders):
        for orden in orders:
            self._surtidora_revisar_devolucion_fiado(orden)
        return super().sync_from_ui(orders)

    @api.model
    def _surtidora_revisar_devolucion_fiado(self, orden):
        """Compuerta del servidor sobre el diccionario que manda el mostrador.

        En la devolución de una venta fiada, lo que sale POR FUERA de la
        cuenta del cliente (efectivo, tarjeta, transferencia o bono) no pasa
        de lo que esa venta se cobró sin fiar, menos lo ya devuelto así. Es
        la misma forma que la regla del efectivo: cada peso vuelve por donde
        entró. Solo para ventas con fiado: la devolución de una venta de
        contado no cambia."""
        if orden.get('state') == 'draft':
            return  # se revisa cuando se cobra
        venta = self._get_refunded_orders(orden)[:1]
        credito = self.env['surtidora.pos.credito']
        fiado = venta.payment_ids.filtered(lambda p: credito._es_fiado(p) and p.amount > 0)
        if not fiado:
            return
        moneda = venta.currency_id
        tope = self._surtidora_devolvible_fuera_de_cuenta(venta, orden)
        if float_compare(self._surtidora_fuera_de_cuenta(orden), tope,
                         precision_rounding=moneda.rounding) > 0:
            raise UserError(_(
                'La venta %(venta)s se fió: %(fiado)s quedaron a la cuenta del '
                'cliente. Lo devuelto vuelve a esa cuenta con «%(metodo)s», que '
                'primero rebaja lo que debe; si ya no debe nada, le queda como '
                'saldo a favor. Por fuera de la cuenta (efectivo, tarjeta, '
                'transferencia o bono) solo se pueden devolver %(tope)s: lo que '
                'esa venta se cobró sin fiar, menos lo ya devuelto así.',
                venta=venta.pos_reference or venta.name,
                fiado=moneda.round(sum(fiado.mapped('amount'))),
                metodo=fiado[:1].payment_method_id.name,
                tope=moneda.round(tope)))

    @api.model
    def _surtidora_fuera_de_cuenta(self, orden):
        """Lo que esta devolución entrega por fuera de la cuenta del cliente:
        todo pago que no es fiado, con su signo, más el vuelto.

        El vuelto lo asienta el core después, desde `amount_return` y con
        ese mismo signo (pos_order.py, _process_payment_lines): positivo en
        una devolución pagada de más, porque esos pesos regresan. Si la
        orden se reenvía ya lo trae como línea `is_change` y no se cuenta
        dos veces."""
        credito = self.env['surtidora.pos.credito']
        neto, trae_vuelto = 0.0, False
        for linea in orden.get('payment_ids') or []:
            if len(linea) < 3 or linea[0] not in (0, 1):
                continue
            valores = linea[2]
            trae_vuelto = trae_vuelto or bool(valores.get('is_change'))
            metodo = self.env['pos.payment.method'].browse(
                valores.get('payment_method_id')).exists()
            if metodo and not credito._es_metodo_fiado(metodo):
                neto += valores.get('amount') or 0.0
        if not trae_vuelto:
            neto += orden.get('amount_return') or 0.0
        return -neto

    @api.model
    def _surtidora_devolvible_fuera_de_cuenta(self, venta, orden):
        """Lo que la venta se cobró sin fiar (neto del vuelto) menos lo que
        sus otras devoluciones ya entregaron por fuera de la cuenta.

        Sin restar lo ya devuelto, dos devoluciones de media venta a bono
        sacarían más de lo que entró sin fiar. La orden que se está
        revisando no cuenta como «otra» si se reenvía (mismo uuid)."""
        dominio = [('lines.refunded_orderline_id', 'in', venta.lines.ids),
                   ('state', 'not in', ('draft', 'cancel'))]
        if orden.get('uuid'):
            dominio.append(('uuid', '!=', orden['uuid']))
        devuelto = sum(max(-self._surtidora_cobrado_sin_fiar(hija), 0.0)
                       for hija in self.search(dominio))
        return max(self._surtidora_cobrado_sin_fiar(venta) - devuelto, 0.0)

    @api.model
    def _surtidora_cobrado_sin_fiar(self, orden):
        """Suma de los pagos de la orden que no son fiado (el vuelto, que es
        un pago en efectivo, incluido con su signo)."""
        credito = self.env['surtidora.pos.credito']
        return sum(p.amount for p in orden.payment_ids if not credito._es_fiado(p))

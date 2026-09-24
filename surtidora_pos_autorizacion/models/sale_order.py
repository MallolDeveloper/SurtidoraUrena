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

Dos piezas, y ninguna abre una puerta desde oficina:

1. La autorización que la caja pidió con motivo + PIN cubre la línea de la
   cotización que se cobró con ella, con los mismos límites que una de
   oficina: no cubre un precio más bajo ni más cantidad que la autorizada.
2. Si aun así queda una línea sin cubrir (la caja midió contra otra lista o
   con otro costo que oficina), la confirmación que dispara ESE cobro no se
   frena: el dinero ya entró. Queda una nota en la orden y la línea sigue
   marcada «Autorizar precios» para que un supervisor la revise.
"""
from markupsafe import Markup, escape

from odoo import _, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _validar_precios_al_confirmar(self):
        """El candado sigue igual para todos, salvo para la confirmación que
        dispara el cobro en caja que se está guardando (P19)."""
        if self._surtidora_cobrada_ahora_en_caja():
            self._surtidora_dejar_constancia_de_caja()
            return
        return super()._validar_precios_al_confirmar()

    def _lineas_bajo_costo(self):
        """RB-08: la excepción bajo costo que la caja autorizó (motivo + PIN +
        doble confirmación) cubre la línea de la cotización que se cobró con
        ella. En oficina RB-08 sigue sin excepciones: allí no hay forma de
        crear una fila de caja."""
        return super()._lineas_bajo_costo().filtered(
            lambda linea: not linea._surtidora_amparada_por_caja(('rb08',)))

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

    def _surtidora_dejar_constancia_de_caja(self):
        """Nota interna con las líneas que el candado habría frenado.

        Va con sudo porque quien confirma aquí es la cajera, y publicar en la
        orden exige escribir sobre ella. Como nota interna, para que no le
        llegue un correo al cliente, que suele seguir sus cotizaciones."""
        self.ensure_one()
        bajo_costo = self._lineas_bajo_costo()
        lineas = bajo_costo | self._lineas_pendientes()
        if not lineas:
            return
        ventas = self.sudo().pos_order_line_ids.order_id
        titulo = _(
            'Cobrada en caja (%s). La orden se confirmó sin frenar el cobro, '
            'pero estas líneas van por debajo de la lista o del costo sin una '
            'autorización que las cubra; un supervisor debe revisarlas:',
            ', '.join(v.pos_reference or v.name for v in ventas))
        detalle = [
            _('• %(producto)s: %(precio).2f (lista: %(lista).2f)%(costo)s',
              producto=linea.product_id.display_name,
              precio=linea._cobrado_por_unidad(),
              lista=linea._precio_de_lista(),
              costo=_(' — BAJO COSTO') if linea in bajo_costo else '')
            for linea in lineas]
        self.sudo().message_post(
            body=Markup('<br/>').join([escape(titulo)] + [escape(d) for d in detalle]),
            subtype_xmlid='mail.mt_note')


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def _requiere_autorizacion(self):
        """RB-01: la rebaja que la caja autorizó con motivo + PIN cubre la
        línea de la cotización que se cobró con ella. Una excepción bajo
        costo también la cubre: la caja la atiende por el camino estricto y
        no pregunta dos veces (bajo_costo.js, isOrderValid)."""
        return (super()._requiere_autorizacion()
                and not self._surtidora_amparada_por_caja(('rb01', 'rb08')))

    def _surtidora_amparada_por_caja(self, tipos):
        """¿Alguna autorización de la caja de esos tipos cubre la línea tal
        como está ahora?

        La bitácora de la caja va en la unidad base del producto, por unidad
        y con ITBIS, y la caja pasa la cotización a unidad base al cobrarla
        (pos_sale, read_converted). La línea se lleva a esa misma base antes
        de comparar. Los límites son los de sigue_vigente_para: no cubre un
        precio más bajo que el autorizado ni más cantidad que la autorizada,
        así que después de confirmar nadie la estira desde oficina."""
        self.ensure_one()
        filas = self._surtidora_autorizaciones_de_caja(tipos)
        if not filas:
            return False
        unidad = self.product_id.uom_id
        precio = self.product_uom_id._compute_price(self._cobrado_por_unidad(), unidad)
        cantidad = self.product_uom_id._compute_quantity(
            self.product_uom_qty, unidad, round=False)
        cubren = filas.filtered(
            lambda fila: self.currency_id.compare_amounts(
                precio, fila.precio_autorizado) >= 0)
        return bool(cubren) and unidad.compare(
            cantidad, sum(cubren.mapped('cantidad'))) <= 0

    def _surtidora_autorizaciones_de_caja(self, tipos):
        """Filas de la bitácora que la caja escribió al cobrar esta línea.

        Se buscan por la venta enlazada y, por si la venta se guardó en
        borrador antes de pedir el PIN (entonces el enlace de create no la
        alcanzó), también por su referencia. Solo pos_reference: el name de
        una venta sin cobrar es «/» y casaría con cualquiera."""
        self.ensure_one()
        Auditoria = self.env['surtidora.autorizacion.precio'].sudo()
        ventas = self.sudo().pos_order_line_ids.order_id.filtered(
            lambda venta: venta.state not in ('draft', 'cancel'))
        if not ventas:
            return Auditoria
        referencias = [r for r in ventas.mapped('pos_reference') if r]
        return Auditoria.search([
            ('origen', '=', 'pos'),
            ('tipo', 'in', list(tipos)),
            ('product_id', '=', self.product_id.id),
            ('uom_id', '=', self.product_id.uom_id.id),
            '|', ('pos_order_id', 'in', ventas.ids),
            '&', ('pos_order_id', '=', False), ('order_ref', 'in', referencias),
        ])

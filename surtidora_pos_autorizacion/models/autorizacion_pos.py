# -*- coding: utf-8 -*-
"""Servidor de la excepción bajo costo del mostrador.

El PIN se valida AQUÍ (el hash nunca viaja al navegador) y la auditoría
reutiliza surtidora.autorizacion.precio, la misma bitácora del backend."""
from odoo import _, api, models
from odoo.exceptions import AccessError, UserError


class PosAutorizacion(models.AbstractModel):
    _name = 'surtidora.pos.autorizacion'
    _description = 'Autorización de venta bajo costo desde el POS'

    @api.model
    def motivos(self):
        """Catálogo de motivos activos para el diálogo de excepción."""
        self._verificar_pos_user()
        return [{'id': m.id, 'nombre': m.name}
                for m in self.env['surtidora.motivo.descuento'].search([])]

    @api.model
    def autorizar_bajo_costo(self, pin, motivo_id, nota, order_ref,
                             partner_id, lineas, tipo='rb08'):
        """Valida el PIN del supervisor y registra UNA auditoría por línea.

        lineas: [{product_id, precio, precio_lista, cantidad}]
        tipo:   'rb08' venta bajo costo | 'rb01' rebaja bajo el precio de lista.
                Va al final y con valor por defecto para que un navegador que
                todavía tenga el JS viejo siga funcionando.
        Devuelve {ok, autorizador} o {ok: False} si el PIN no corresponde.
        """
        self._verificar_pos_user()
        if not pin or not lineas:
            return {'ok': False}
        try:
            autorizador = self.env['res.users']._surtidora_verificar_pin(str(pin))
        except UserError as bloqueo:
            # demasiados intentos: el cajero tiene que saber POR QUÉ no entra,
            # o lo va a seguir intentando creyendo que se equivocó de tecla
            return {'ok': False, 'mensaje': str(bloqueo)}
        if not autorizador:
            return {'ok': False}
        # El motivo se valida contra el catálogo: el navegador manda un id y
        # nada garantizaba que existiera ni que fuera de este catálogo.
        motivo = self.env['surtidora.motivo.descuento'].browse(
            int(motivo_id) if motivo_id else 0).exists()
        if not motivo:
            return {'ok': False, 'mensaje': _('El motivo elegido ya no existe.')}
        Auditoria = self.env['surtidora.autorizacion.precio'].sudo()
        productos = self.env['product.product'].browse(
            [int(l['product_id']) for l in lineas]).exists()
        por_id = {p.id: p for p in productos}
        for linea in lineas:
            producto = por_id.get(int(linea['product_id']))
            if not producto:
                continue
            Auditoria.create({
                'company_id': self.env.company.id,
                'order_ref': order_ref or '',
                'product_id': producto.id,
                'uom_id': producto.uom_id.id,
                'cantidad': linea.get('cantidad', 0.0),
                'precio_lista': linea.get('precio_lista', 0.0),
                'precio_autorizado': linea['precio'],
                # el COSTO lo pone el servidor, no el navegador: es el número
                # con el que después se mide la gravedad de la excepción, y
                # standard_price cambia con cada compra
                'costo': producto.with_company(self.env.company).standard_price,
                'currency_id': self.env.company.currency_id.id,
                'solicitante_id': self.env.user.id,
                'autorizador_id': autorizador.id,
                'partner_id': int(partner_id) if partner_id else False,
                'motivo_id': motivo.id,
                'motivo_texto': motivo.name or '',
                'nota': nota or '',
                'origen': 'pos',
                'tipo': 'rb01' if tipo == 'rb01' else 'rb08',
            })
        return {'ok': True, 'autorizador': autorizador.name}

    def _verificar_pos_user(self):
        if not self.env.user.has_group('point_of_sale.group_pos_user'):
            raise AccessError(_('Solo usuarios del punto de venta.'))

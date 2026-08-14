# -*- coding: utf-8 -*-
"""Cuadre de caja (REQ-V17): el arqueo por denominación del cierre se
persiste ESTRUCTURADO (el popup nativo solo lo deja como texto en las notas)
y un motor arma todos los datos del reporte — la plantilla solo pinta
(motor/pantalla, estándar Surtidora)."""
import math

from odoo import _, api, fields, models
from odoo.exceptions import AccessError

# Órdenes que el core considera "capturadas" para el efectivo esperado.
# Sin este filtro el resumen sumaría pagos de órdenes en borrador o
# canceladas y no cuadraría contra el esperado del propio Odoo.
ESTADOS_CAPTURADOS = ('paid', 'done')


class PosSession(models.Model):
    _inherit = 'pos.session'

    surtidora_arqueo_json = fields.Json(
        string='Arqueo por denominación (cierre)', copy=False,
        help='{valor_billete: cantidad} contado por la cajera en el popup '
             'de cierre. Lo envía el POS (patch de ClosePosPopup).')

    # ------------------------------------------------------------------
    # Persistencia del conteo (lo llama el JS del cierre)
    # ------------------------------------------------------------------
    def surtidora_guardar_arqueo(self, detalle):
        """Guarda el conteo por denominación ANTES de cerrar la sesión.

        Un dict vacío BORRA el arqueo: si la cajera teclea el total a mano
        el POS anula su desglose, y sin este borrado quedaría el conteo de
        un intento anterior contradiciendo el efectivo contado."""
        if not self.env.user.has_group('point_of_sale.group_pos_user'):
            raise AccessError(_('Solo usuarios del punto de venta.'))
        if not isinstance(detalle, dict):
            detalle = {}  # el método es invocable por RPC: nunca confiar
        limpio = {}
        for valor, cantidad in detalle.items():
            try:
                # isfinite: float() acepta 'nan' e 'inf', y esos valores
                # revientan el redondeo monetario al imprimir el cuadre
                if not math.isfinite(float(valor)):
                    continue
                cantidad = int(cantidad or 0)
            except (TypeError, ValueError):
                continue  # basura del input: se ignora esa denominación
            # se conservan las cantidades NEGATIVAS (el popup las admite si
            # se teclea el signo): botarlas dejaría el total del arqueo por
            # encima del efectivo contado, justo la incoherencia a evitar
            if cantidad:
                limpio[str(valor)] = cantidad
        # sudo puntual: la cajera cierra la caja pero no siempre tiene
        # write sobre pos.session por RPC
        for sesion in self.sudo():
            if sesion.state != 'closed':
                sesion.surtidora_arqueo_json = limpio
        return True

    # ------------------------------------------------------------------
    # Motor del reporte
    # ------------------------------------------------------------------
    def surtidora_datos_cuadre(self):
        """Todos los datos de la hoja de cuadre en un solo dict.

        Réplica del cuadre de ADG (inv_cuadres): declarado vs calculado por
        método, arqueo por denominación, entradas/salidas y diferencia.

        Público porque QWeb no invoca métodos con guion bajo; por eso lleva
        su propio control de acceso — sin él, cualquier usuario autenticado
        podría leer por RPC el efectivo de cualquier caja (el sudo de abajo
        salta las reglas normales)."""
        self.ensure_one()
        if not (self.env.user.has_group('point_of_sale.group_pos_user')
                or self.env.user.has_group('account.group_account_readonly')):
            raise AccessError(_('No tiene acceso al cuadre de caja.'))
        # y solo cajas de una compañía habilitada para el usuario (el sudo
        # de abajo se salta las reglas multi-compañía)
        if self.company_id and self.company_id not in self.env.companies:
            raise AccessError(_('Esa caja es de otra compañía.'))
        # sudo puntual de LECTURA: el encargado que imprime no siempre tiene
        # permisos contables (los movimientos de caja viven en contabilidad)
        sesion = self.sudo()

        ordenes = sesion.order_ids.filtered(
            lambda o: o.state in ESTADOS_CAPTURADOS)

        # pagos calculados por método (solo de órdenes capturadas, igual
        # que el efectivo esperado que calcula Odoo)
        grupos = sesion.env['pos.payment']._read_group(
            [('session_id', '=', sesion.id),
             ('pos_order_id.state', 'in', ESTADOS_CAPTURADOS)],
            ['payment_method_id'], ['amount:sum'])
        metodos = []
        ventas_efectivo = 0.0
        for metodo, monto in grupos:
            metodos.append({'nombre': metodo.name, 'monto': monto})
            if metodo.is_cash_count:
                ventas_efectivo += monto

        # devoluciones (por motivo si el módulo de devoluciones está)
        devoluciones = ordenes.filtered(lambda o: o.amount_total < 0)
        devol_por_motivo = []
        if 'surtidora_motivo_dev_id' in ordenes._fields:
            por_motivo = {}
            for orden in devoluciones:
                clave = orden.surtidora_motivo_dev_id.name or _('(sin motivo)')
                acumulado = por_motivo.setdefault(clave, [0, 0.0])
                acumulado[0] += 1
                acumulado[1] += orden.amount_total
            devol_por_motivo = [
                {'motivo': motivo, 'cantidad': datos[0], 'monto': datos[1]}
                for motivo, datos in sorted(por_motivo.items())]

        # quién cobró de verdad: la sesión la puede operar más de un cajero
        # y user_id solo dice quién la ABRIÓ (firma engañosa en la hoja)
        cajeros = {}
        for orden in ordenes:
            nombre = orden.user_id.name or ''
            fila = cajeros.setdefault(nombre, [0, 0.0])
            fila[0] += 1
            fila[1] += orden.amount_total
        cajeros = [{'nombre': nombre, 'ordenes': datos[0], 'monto': datos[1]}
                   for nombre, datos in sorted(cajeros.items())]

        movimientos = self._surtidora_movimientos_caja(sesion)

        # arqueo por denominación
        arqueo = []
        total_arqueo = 0.0
        for valor, cantidad in (sesion.surtidora_arqueo_json or {}).items():
            subtotal = float(valor) * cantidad
            total_arqueo += subtotal
            arqueo.append({'denominacion': float(valor),
                           'cantidad': cantidad, 'subtotal': subtotal})
        arqueo.sort(key=lambda fila: -fila['denominacion'])

        moneda = sesion.currency_id
        return {
            'caja': sesion.config_id.name,
            'cuadre': sesion.name,
            'abrio': sesion.user_id.name,
            'cajeros': cajeros,
            'apertura': sesion.start_at,
            'cierre': sesion.stop_at,
            'cerrada': sesion.state == 'closed',
            # `closing_control` = ya contaron el efectivo pero el cierre no
            # terminó: ahí el contado y la diferencia SÍ valen (es cuando
            # más se necesitan, para investigar el cierre que falló)
            'contado_hecho': sesion.state in ('closed', 'closing_control'),
            'fondo': sesion.cash_register_balance_start,
            'ventas_efectivo': ventas_efectivo,
            'entradas': sum(m['monto'] for m in movimientos if m['monto'] > 0),
            'salidas': -sum(m['monto'] for m in movimientos if m['monto'] < 0),
            'esperado': sesion.cash_register_balance_end,
            'contado': sesion.cash_register_balance_end_real,
            'diferencia': sesion.cash_register_difference,
            'cuadrado': moneda.is_zero(sesion.cash_register_difference),
            'faltante': sesion.cash_register_difference < 0,
            'metodos': metodos,
            'total_ventas': sum(ordenes.mapped('amount_total')),
            'num_ordenes': len(ordenes),
            'num_devoluciones': len(devoluciones),
            'monto_devoluciones': sum(devoluciones.mapped('amount_total')),
            'devol_por_motivo': devol_por_motivo,
            'movimientos': movimientos,
            'arqueo': arqueo,
            'total_arqueo': total_arqueo,
            # el arqueo pudo quedar de un intento de cierre anterior (solo
            # tiene sentido comparar cuando el efectivo ya se contó)
            'arqueo_descuadrado': bool(arqueo)
            and sesion.state in ('closed', 'closing_control')
            and not moneda.is_zero(
                total_arqueo - sesion.cash_register_balance_end_real),
        }

    @api.model
    def _surtidora_movimientos_caja(self, sesion):
        """Entradas y salidas MANUALES de efectivo.

        El cierre también crea líneas de extracto con `pos_session_id` (la
        combinada de ventas y la de diferencia), así que se filtra por el
        patrón que usa `try_cash_in_out` — verificado contra el servidor:
        `<sesión>-<Tipo>-<motivo>`, mientras las del cierre llevan el nombre
        de la sesión pelado. Filtrar por lo que SÍ es manual (y no por
        excluir lo conocido) evita que una línea nueva del core se cuele."""
        lineas = sesion.env['account.bank.statement.line'].search(
            [('pos_session_id', '=', sesion.id),
             ('payment_ref', '=like', (sesion.name or '') + '-%')],
            order='create_date')
        movimientos = []
        for linea in lineas:
            # "Caja/00011-Entrada-Pago mensajero" → "Entrada · Pago mensajero"
            concepto = (linea.payment_ref or '')[len(sesion.name or '') + 1:]
            partes = concepto.split('-', 1)
            movimientos.append({
                'concepto': ' · '.join(p for p in partes if p) or concepto,
                'monto': linea.amount,
            })
        return movimientos

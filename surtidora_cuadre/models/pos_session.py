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
        metodos = [{'nombre': metodo.name, 'monto': monto}
                   for metodo, monto in grupos]

        # El efectivo ENTRA por ventas y SALE por devoluciones. Sumar los dos
        # con un solo `amount:sum` los cancela EN SILENCIO: el total salía
        # correcto, pero rotulado «Ventas en efectivo», y la salida no
        # figuraba en ninguna línea del bloque. La cajera solo la veía abajo,
        # en Devoluciones, y la restaba otra vez a ojo — descuadre inventado.
        ventas_efectivo, devoluciones_efectivo = \
            self._surtidora_efectivo_por_signo(sesion)

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

        # Lo devuelto, por forma de pago. Es lo que amarra la línea de
        # «Devoluciones en efectivo» de arriba con este bloque, y lo que deja
        # ver que un bono o una nota de crédito NO tocaron la gaveta: sin
        # esto, el total mezcla dinero con papel y no cuadra contra nada.
        # Se calcula sobre los pagos NEGATIVOS —no sobre las órdenes de total
        # negativo— para que la parte en efectivo dé exactamente la misma
        # cifra que el bloque del efectivo, incluso si una orden mezcla
        # devolución y venta nueva.
        grupos_devol = sesion.env['pos.payment']._read_group(
            [('session_id', '=', sesion.id),
             ('pos_order_id.state', 'in', ESTADOS_CAPTURADOS),
             ('amount', '<', 0)],
            ['payment_method_id'], ['amount:sum'])
        devol_por_metodo = [
            {'nombre': metodo.name, 'monto': monto,
             'de_caja': metodo.is_cash_count}
            for metodo, monto in grupos_devol]

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
            'devoluciones_efectivo': devoluciones_efectivo,
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
            'devol_por_metodo': devol_por_metodo,
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
    def _surtidora_efectivo_por_signo(self, sesion):
        """Lo que ENTRÓ y lo que SALIÓ de la gaveta, ya separados.

        Un pago negativo en el POS es dinero que sale: no hay otra forma de
        registrar una devolución en efectivo. El vuelto no cuenta aquí —
        viaja en `amount_return`, no como línea de pago.

        La salida se devuelve CON su signo (negativa, o cero), igual que los
        montos de `devol_por_metodo` con los que tiene que amarrar. Así la
        plantilla la imprime tal cual: negarla ahí daría `-0.0` en todos los
        cuadres sin devoluciones, y la hoja saldría con un «-0.00».
        """
        base = [('session_id', '=', sesion.id),
                ('pos_order_id.state', 'in', ESTADOS_CAPTURADOS),
                ('payment_method_id.is_cash_count', '=', True)]

        def sumar(signo):
            # groupby vacío: una sola fila con el total, o ninguna si no hay
            # pagos de ese signo (y `amount:sum` puede venir en None)
            grupos = sesion.env['pos.payment']._read_group(
                base + [('amount', signo, 0)], [], ['amount:sum'])
            return (grupos[0][0] if grupos else 0.0) or 0.0

        return sumar('>'), sumar('<')

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

# -*- coding: utf-8 -*-
"""Motor del cuadre general y de la hoja de depósito (REQ-V17).

No recalcula nada: pide a cada sesión su `surtidora_datos_cuadre()` (el
cuadre por caja de `surtidora_cuadre`, ya verificado contra el efectivo
esperado de Odoo) y lo CONSOLIDA. Una caja con dos turnos (lo normal en
Surtidora: 07:00-13:00 y 13:30-17:00) sale como una fila que suma sus dos
sesiones, igual que el CUADRE GENERAL de ADG.

Motor/pantalla, estándar Surtidora: la plantilla QWeb solo pinta."""
import collections
import datetime

import pytz

from odoo import _, api, models
from odoo.exceptions import AccessError, UserError


class CuadreGeneralMotor(models.AbstractModel):
    _name = 'surtidora.cuadre.general.motor'
    _description = 'Motor del cuadre general de cajas'

    # ------------------------------------------------------------------
    # Sesiones del día
    # ------------------------------------------------------------------
    @api.model
    def sesiones_del_dia(self, fecha, config=None):
        """Sesiones CERRADAS cuyo cierre cae en `fecha` (hora local del
        usuario). Se toma el cierre y no la apertura porque la caja de
        crédito de Mariano abre a las 17:48 del día anterior y cierra al
        mediodía siguiente (visto en ADG): pertenece al día en que se
        cuenta el dinero."""
        self._verificar_acceso()
        desde, hasta = self._rango_utc(fecha)
        dominio = [('state', '=', 'closed'),
                   ('stop_at', '>=', desde), ('stop_at', '<', hasta),
                   ('company_id', 'in', self.env.companies.ids)]
        if config:
            dominio.append(('config_id', '=', config.id))
        return self.env['pos.session'].search(dominio, order='config_id, stop_at')

    def _rango_utc(self, fecha):
        """[00:00, 24:00) del día en la zona del usuario, expresado en UTC,
        que es como Odoo guarda `stop_at`."""
        zona = pytz.timezone(self.env.user.tz or 'UTC')
        inicio = zona.localize(datetime.datetime.combine(fecha, datetime.time.min))
        inicio_utc = inicio.astimezone(pytz.utc).replace(tzinfo=None)
        return inicio_utc, inicio_utc + datetime.timedelta(days=1)

    @api.model
    def _verificar_acceso(self):
        if not (self.env.user.has_group('point_of_sale.group_pos_manager')
                or self.env.user.has_group('account.group_account_readonly')):
            raise AccessError(_('Solo el encargado del punto de venta o '
                                'contabilidad pueden ver el cuadre general.'))

    # ------------------------------------------------------------------
    # Consolidación
    # ------------------------------------------------------------------
    @api.model
    def datos(self, fecha, config=None):
        """Todo lo que pintan las dos hojas, en un dict."""
        sesiones = self.sesiones_del_dia(fecha, config)
        detalles = [(s, s.surtidora_datos_cuadre()) for s in sesiones]
        empresa = self.env.company
        fondo = empresa.surtidora_fondo_caja

        cajas = self._por_caja(detalles)
        metodos = self._por_metodo(detalles)
        arqueo, total_arqueo = self._arqueo_sumado(detalles)
        cajeros = self._cajeros(detalles)

        total_contado = sum(c['contado'] for c in cajas)
        total_devol = sum(c['devoluciones'] for c in cajas)
        total_entradas = sum(c['entradas'] for c in cajas)
        total_egresos = sum(c['egresos'] for c in cajas)
        total_diferencia = sum(c['diferencia'] for c in cajas)
        efectivo_contado = sum(d['contado'] for _s, d in detalles)
        fondos_dejados = fondo * len(sesiones)
        a_depositar = efectivo_contado - fondos_dejados

        # «Según facturas»: lo que las ventas dicen que debió entrar por
        # todos los medios. La hoja de depósito lo compara contra lo que
        # de verdad se cuenta + tarjetas + egresos.
        # «Según facturas» = lo COBRADO hoy por todos los medios que son
        # dinero (efectivo, tarjetas, transferencia). El crédito y los bonos
        # quedan fuera de las dos columnas: no entran a la gaveta ni al banco.
        segun_facturas = sum(m['monto'] for m in metodos if not m['diferido'])
        contado_total = a_depositar + sum(
            m['monto'] for m in metodos
            if not m['de_caja'] and not m['diferido']) + total_egresos
        return {
            'fecha': fecha,
            'caja_filtro': config.name if config else _('(TODAS)'),
            'sesiones': len(sesiones),
            'cajas': cajas,
            'tot_contado': total_contado,
            'tot_devoluciones': total_devol,
            'tot_entradas': total_entradas,
            'tot_egresos': total_egresos,
            'tot_balance': total_contado - total_devol + total_entradas - total_egresos,
            'tot_diferencia': total_diferencia,
            'metodos': metodos,
            'cajeros': cajeros,
            'arqueo': arqueo,
            'total_arqueo': total_arqueo,
            'efectivo_contado': efectivo_contado,
            'fondo_por_caja': fondo,
            'fondos_dejados': fondos_dejados,
            'a_depositar': a_depositar,
            'segun_facturas': segun_facturas,
            'contado_total': contado_total,
            'sobrante': contado_total - segun_facturas,
            'arqueo_incompleto': any(
                not d['arqueo'] for _s, d in detalles) and bool(detalles),
            'puede_registrar': empresa.surtidora_registrar_deposito
            and bool(empresa.surtidora_diario_deposito_id),
            'banco': empresa.surtidora_diario_deposito_id.name or '',
        }

    def _por_caja(self, detalles):
        """Una fila por caja, sumando sus sesiones (turnos) del día."""
        filas = collections.OrderedDict()
        for sesion, d in detalles:
            fila = filas.setdefault(sesion.config_id.id, {
                'caja': sesion.config_id.name, 'turnos': 0, 'sesiones': [],
                'contado': 0.0, 'devoluciones': 0.0, 'entradas': 0.0,
                'egresos': 0.0, 'diferencia': 0.0, 'cajeros': set()})
            fila['turnos'] += 1
            fila['sesiones'].append(sesion.name)
            # Como en el CUADRE GENERAL de ADG: «Contado» es lo vendido
            # (positivo, sin restar devoluciones), «Devoluciones» va en su
            # columna, y el Balance las resta. `monto_devoluciones` viene
            # NEGATIVO del motor por sesión (órdenes de total < 0).
            fila['contado'] += d['total_ventas'] - d['monto_devoluciones']
            fila['devoluciones'] += -d['monto_devoluciones']
            fila['entradas'] += d['entradas']
            fila['egresos'] += d['salidas']
            fila['diferencia'] += d['diferencia']
            fila['cajeros'].update(c['nombre'] for c in d['cajeros'])
        for fila in filas.values():
            fila['balance'] = (fila['contado'] - fila['devoluciones']
                               + fila['entradas'] - fila['egresos'])
            fila['cajeros'] = ', '.join(sorted(fila['cajeros']))
            fila['sesiones'] = ', '.join(fila['sesiones'])
        return list(filas.values())

    def _por_metodo(self, detalles):
        """Detalle de ingresos por forma de pago, sumado. `de_caja` marca el
        efectivo (lo que se cuenta en la gaveta); el resto son tarjetas,
        transferencias, bonos… cada uno en su fila, tal como estén
        configurados los métodos de pago."""
        acumulado = collections.OrderedDict()
        metodos = self.env['pos.payment.method'].search(
            [('company_id', 'in', [False, self.env.company.id])])
        de_caja = {m.name: m.is_cash_count for m in metodos}
        # pay_later = crédito en cuenta y bonos: NO es dinero que entre hoy.
        # ADG lo saca del «total en efectivo»; aquí se muestra pero no
        # cuenta para el depósito ni para «según facturas» cobradas.
        diferido = {m.name: m.type == 'pay_later' for m in metodos}
        for _s, d in detalles:
            for m in d['metodos']:
                acumulado[m['nombre']] = acumulado.get(m['nombre'], 0.0) + m['monto']
        return [{'nombre': nombre, 'monto': monto,
                 'de_caja': de_caja.get(nombre, False),
                 'diferido': diferido.get(nombre, False)}
                for nombre, monto in acumulado.items()]

    def _arqueo_sumado(self, detalles):
        """El conteo por denominación de todas las sesiones, sumado: es lo
        que la supervisora lleva al banco, y lo que hoy teclea en Excel."""
        por_valor = collections.Counter()
        for _s, d in detalles:
            for fila in d['arqueo']:
                por_valor[fila['denominacion']] += fila['cantidad']
        arqueo = [{'denominacion': v, 'cantidad': c, 'subtotal': v * c}
                  for v, c in sorted(por_valor.items(), reverse=True)]
        return arqueo, sum(f['subtotal'] for f in arqueo)

    def _cajeros(self, detalles):
        acumulado = {}
        for _s, d in detalles:
            for c in d['cajeros']:
                fila = acumulado.setdefault(c['nombre'], [0, 0.0])
                fila[0] += c['ordenes']
                fila[1] += c['monto']
        return [{'nombre': n, 'ordenes': v[0], 'monto': v[1]}
                for n, v in sorted(acumulado.items())]

    # ------------------------------------------------------------------
    # Registrar el depósito (opcional)
    # ------------------------------------------------------------------
    @api.model
    def registrar_deposito(self, fecha, monto, config=None):
        """Mueve el efectivo a depositar del diario de caja al diario del
        banco. En Odoo 19 la transferencia entre diarios es un asiento en el
        diario del BANCO: débito a la cuenta del banco, crédito a la cuenta
        de la caja. Así el extracto del banco lo casa solo al conciliar.
        Idempotente por día y caja: no se registra dos veces."""
        self._verificar_acceso()
        empresa = self.env.company
        if not empresa.surtidora_registrar_deposito:
            raise UserError(_('El registro del depósito está apagado en Ajustes.'))
        banco = empresa.surtidora_diario_deposito_id
        if not banco:
            raise UserError(_('Falta el banco donde se deposita (Ajustes → Punto de venta).'))
        if monto <= 0:
            raise UserError(_('No hay efectivo a depositar.'))
        caja = self._diario_de_caja(config)
        referencia = _('Depósito %(banco)s del %(fecha)s%(caja)s',
                       banco=banco.name, fecha=fecha.strftime('%d-%m-%Y'),
                       caja=(' · ' + config.name) if config else '')
        Move = self.env['account.move']
        existente = Move.search([('journal_id', '=', banco.id), ('date', '=', fecha),
                                 ('ref', '=', referencia), ('state', '!=', 'cancel')], limit=1)
        if existente:
            raise UserError(_('Ya hay un depósito registrado ese día: %s', existente.name))
        asiento = Move.create({
            'journal_id': banco.id,
            'date': fecha,
            'ref': referencia,
            'line_ids': [
                (0, 0, {'account_id': banco.default_account_id.id,
                        'name': referencia, 'debit': monto, 'credit': 0.0}),
                (0, 0, {'account_id': caja.default_account_id.id,
                        'name': referencia, 'debit': 0.0, 'credit': monto}),
            ],
        })
        asiento.action_post()
        return asiento

    def _diario_de_caja(self, config):
        """El diario de efectivo de la caja (o de la primera con efectivo)."""
        metodos = self.env['pos.payment.method'].search(
            [('is_cash_count', '=', True), ('journal_id', '!=', False)])
        if config:
            metodos = metodos.filtered(lambda m: m in config.payment_method_ids)
        if not metodos or not metodos[0].journal_id.default_account_id:
            raise UserError(_('No hay método de pago en efectivo con diario y cuenta.'))
        return metodos[0].journal_id

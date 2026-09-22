# -*- coding: utf-8 -*-
{
    'name': 'Surtidora - Cuadre general y hoja de depósito',
    'summary': 'REQ-V17: el cuadre de TODAS las cajas del día y la hoja de '
               'depósito al banco, como las hace hoy la supervisora en ADG y Excel.',
    'description': """
Cómo cierra la caja Surtidora de verdad (medido en inv_cuadres, 12 meses):
la cajera abre su caja y NO la cierra — cierra una supervisora (YPENA en
el 93 % de los cierres), que cuenta el efectivo, deja el fondo fijo de
RD$2,000 y hace dos hojas: el CUADRE GENERAL de ADG (todas las cajas del
día, sumando los dos turnos de cada una) y una hoja de depósito en Excel
(conteo por denominación de todo el efectivo, menos fondos, más tarjetas
y egresos, contra las ventas según facturas — y el sobrante o faltante).

`surtidora_cuadre` ya hace el cuadre POR SESIÓN. Este módulo lo reúne:

- Asistente «Cuadre general» (menú Punto de venta → Informes): fecha y,
  opcionalmente, una caja. Toma las sesiones CERRADAS ese día y llama al
  motor de cada una — no recalcula nada por su cuenta.
- PDF con dos hojas: (1) CUADRE GENERAL: fila por caja (contado, devoluciones,
  entradas, egresos, balance, diferencia del arqueo), totales, detalle por
  forma de pago, cajeros del día; (2) HOJA DE DEPÓSITO: arqueo por
  denominación SUMADO de todas las sesiones, menos los fondos dejados en
  las cajas, = efectivo a depositar; tarjetas por tipo; egresos; ventas
  según facturas; diferencia. Firmas Recibido conforme / Quien entrega.
- «Registrar depósito» (opcional, Ajustes → Punto de venta): crea la
  transferencia del diario de caja al diario del banco por el efectivo a
  depositar, con el monto que sale del arqueo — la supervisora confirma,
  no teclea. Apagado, la hoja solo se imprime y contabilidad marca el
  depósito al conciliar el extracto (decisión del cliente, 14-sep-2026).
  El botón solo aparece a quien puede contabilizar («Contabilidad /
  Facturación»): ver el cuadre no basta para mover dinero.
- Al abrir un turno, la caja propone el fondo configurado (RD$2,000) en
  vez de lo contado en el cierre anterior, que incluía lo que se llevó al
  banco: así la cajera no ve una «diferencia» cada mañana.

Los métodos de pago separados (Transferencia, Tarjeta del Gobierno,
Cardnet) y el bono de tarjeta preferencial como medio de pago son
CONFIGURACIÓN de pos.payment.method, no código: aquí solo salen en su fila.
    """,
    'version': '19.0.1.1.0',
    'category': 'Sales/Point of Sale',
    'author': 'Mallol Consulting - Smerlin Ramos',
    'license': 'OPL-1',
    'depends': ['surtidora_cuadre', 'account'],
    'data': [
        'security/ir.model.access.csv',
        'report/cuadre_general_report.xml',
        'wizards/cuadre_general_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'installable': True,
    'application': False,
}

# -*- coding: utf-8 -*-
{
    'name': 'Surtidora - Crédito en el POS',
    'summary': 'Venta a crédito desde el mostrador (cuenta del cliente) con '
               'candado de límite de crédito — como la condición crédito de ADG.',
    'description': """
En ADG contado y crédito salían de la MISMA pantalla de facturación. Este
módulo lo replica en el POS ("una sola pantalla"):

- Método de pago "Crédito (Cuenta Cliente)" — el monto no entra a caja: queda
  cargado a la cuenta por cobrar del cliente (pay_later nativo de Odoo).
- Candado de crédito (el servidor decide, el POS solo pinta el mensaje):
  * Sin cliente seleccionado → no hay crédito.
  * Cliente sin límite de crédito autorizado → bloqueado (en ADG solo ~440
    clientes tienen crédito; aquí el límite en la ficha ES la autorización).
  * Balance pendiente + esta venta > límite → bloqueado, mostrando el
    disponible real.
- Doble verificación: al tocar el método de pago (aviso temprano) y al validar
  la orden (compuerta final — evita colar el crédito editando montos).
- Método "Bono / Nota de Crédito" (REQ-V18, política 12.4): aplica el saldo a
  favor del cliente (NC / pagos a cuenta abiertos) como forma de pago; la
  devolución lo emite. Al cerrar la sesión se concilia contra esas NC, las
  más viejas primero, para que el mismo bono no se gaste dos veces.

Órdenes FACTURADAS (con el módulo fiscal toda venta llevará NCF): Odoo deja
la factura (o la RINV) abierta por la parte pagada con Crédito o Bono y el
cierre ya no crea el apunte por cobrar. Por eso:
- el candado y el bono no vuelven a sumar lo que ya está en la factura;
- la devolución facturada con bono ya ES su RINV (no se cuenta dos veces);
- al cierre, la factura pagada con bono se concilia contra las NC del
  cliente (misma entidad comercial y compañía). Si el bono cubre solo una
  parte (bono + Crédito), un asiento puente en el diario del POS mueve
  exactamente el bono y el resto sigue como deuda del cliente.

Devolución de un fiado (DC-5): lo que se fió vuelve a la cuenta del
cliente con Crédito negativo. Ese crédito (la RINV, o el apunte del cierre
si no hay factura) REBAJA LA DEUDA, no es bono:
- Crédito negativo siempre se permite, aunque el cliente no tenga límite
  activo: no crea deuda;
- en la devolución de una venta fiada, lo que sale por fuera de la cuenta
  (efectivo, tarjeta, transferencia o bono) no pasa de lo que esa venta se
  cobró sin fiar, menos lo ya devuelto así (compuerta del servidor al
  sincronizar la orden, models/pos_order.py). La devolución de una venta
  de contado no cambia;
- al cerrar la sesión se concilia contra las deudas abiertas del mismo
  cliente y de la MISMA cuenta por cobrar: primero la de la venta devuelta,
  después FIFO por vencimiento (antes de conciliar los bonos, y otra vez
  después por lo que un bono deja abierto en su factura). Si la venta
  devuelta sigue en otra caja abierta, se aplica al cerrar esa caja.
  Idempotente. Si falla, la caja cierra igual y contabilidad recibe una
  actividad «Por hacer»;
- con la caja abierta, el candado del bono y el panel ya descuentan lo que
  el cierre va a aplicar: el disponible es el mismo antes y después;
- si el cliente no debe nada, queda como saldo a favor legítimo;
- en una RINV mixta (Crédito + Bono) un asiento puente separa la parte de
  la cuenta, que rebaja deuda; la del bono sigue siendo bono.
Las notas de crédito de apertura (RAPCXC) no se tocan.

La instalación agrega el método a las cajas existentes y activa la opción
de límite de crédito por cliente en la compañía.

El mayoreo con negociación formal (cotización + botón de negociación) sigue
por el backend de Ventas.
    """,
    'version': '19.0.1.2.0',
    'category': 'Sales/Point of Sale',
    'author': 'Mallol Consulting - Smerlin Ramos',
    'license': 'OPL-1',
    'depends': ['point_of_sale'],
    'data': [
        'data/payment_method_data.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'surtidora_pos_credito/static/src/**/*',
        ],
    },
    'post_init_hook': 'configurar_credito_pos',
    'installable': True,
    'application': False,
}

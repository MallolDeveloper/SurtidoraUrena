# Surtidora — Panel de Mostrador (POS)

Criterio del cliente (jul-2026): **todo se debe ver en una sola pantalla**.
Este módulo agrega la tercera columna del mostrador: el contexto que en ADG
está siempre a la vista, sin popups.

## Qué muestra (se actualiza al tocar/escanear un producto)

| Sección | Contenido | REQ |
|---|---|---|
| Precios por unidad | Base y cada empaque con su equivalente por unidad ("la caja te deja el paquete a 48.89") | REQ-V03 |
| Existencia por almacén | Disponible en Principal / #2 Chino / Dañados; negativos en rojo | REQ-V04 |
| **Últimas ventas a este cliente** | Fecha, cantidad y precio de las últimas 3 ventas de ESE producto a ESE cliente — mezcla mostrador (POS) y facturación backend | REQ-V06 / RB-06 |

Si no hay cliente en la orden, el panel lo dice y pide seleccionarlo — la
sección de historial es el anti-"a mí me lo pusiste a menos".

## Balance del cliente (REQ-V02)

Al seleccionar el cliente, `balance_cliente` devuelve vencido / por vencer /
a favor / fiado en sesión / límite. Reglas con órdenes **facturadas** (toda
venta llevará NCF con el módulo fiscal):

- Lo fiado a Crédito en una orden facturada ya es su factura abierta: no se
  suma otra vez como "en sesión". Con `surtidora_pos_credito` instalado la
  cifra sale del mismo método que usa el candado (`_credito_en_sesion`).
- Venta facturada pagada con bono, con la sesión abierta: la parte del bono
  se descuenta de la factura (el cierre la concilia contra la NC) y del
  saldo a favor — no aparece como deuda y como bono usado a la vez.
- Devolución facturada con bono: su RINV ya es el saldo a favor; no se
  vuelve a sumar.
- Devolución de un fiado a Crédito (DC-5): el cierre la aplica a la deuda
  de su misma cuenta por cobrar (primero la venta devuelta, después FIFO;
  los cheques devueltos de apertura van en otra cuenta y no se tocan). Con
  la caja abierta el panel ya la pinta así (`_plan_devoluciones` del módulo
  de crédito): baja la deuda o lo fiado hoy, no sube el saldo a favor. Si
  el cliente no debe nada en esa cuenta, sí es saldo a favor.

## Diseño

- `models/pos_panel.py`: el servidor arma TODO en una llamada
  (`surtidora.pos.panel.info_panel`). `sudo` puntual y comentado: la cajera
  necesita el historial aunque su usuario no lea ventas backend; solo se
  devuelven los campos que el negocio quiere en mostrador.
- `static/src/panel/`: patch de `ProductScreen` (estado propio + refresco en
  `addProductToOrder` y `_barcodeProductAction`) y `t-inherit` del template
  vivo del POS (tercera columna tras el `rightpane`). Oculto en pantallas
  pequeñas.
- Convive con `surtidora_pos_empaques` (las cadenas de `super` se encadenan).

## Prueba post-merge

1. Instalar → recargar el POS
2. Asignar cliente FAUSTO RODRIGUEZ → tocar GALLETAS GUARINA SALADA
3. El panel derecho muestra: Paquete 55 / Caja de 18 — 880, existencia por
   almacén, y las últimas ventas de la Guarina a Fausto con su precio

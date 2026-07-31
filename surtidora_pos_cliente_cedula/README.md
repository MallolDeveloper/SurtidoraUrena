# Surtidora — Cliente por Cédula/Tarjeta en POS

REQ-V29: la cajera pasa la cédula (código de barras del reverso) o la tarjeta
de lealtad por el lente y el cliente queda identificado en la orden — la
puerta de entrada de los surti-puntos.

## Cómo funciona

1. **Captura**: en la ficha del cliente aparece el campo "Código cédula/tarjeta
   (POS)" (junto a las etiquetas). Se escanea o digita una vez, ahí queda.
2. **En el POS**: cualquier código escaneado que no sea producto se busca como
   cliente (primero en datos cargados, luego en el servidor) y se asigna a la
   orden. Con el cliente asignado, la lealtad acumula automáticamente.
3. Si tampoco es cliente → aviso estándar de código desconocido.

## Decisión de diseño

Sin reglas de nomenclatura por prefijo/longitud (frágiles con códigos internos
Zebra y formatos de cédula): la regla es simple — "no es producto → ¿es
cliente?". Funciona con cédula, tarjeta o cualquier código registrado.

## Prueba post-merge

1. `sudo surtidora-update surtidora_pos_cliente_cedula` (instalar desde Apps la primera vez)
2. FAUSTO RODRIGUEZ ya tiene código de prueba: `40212345678`
3. En el POS, teclear rápido `40212345678` + Enter (o escanear) → el cliente
   queda asignado a la orden sin abrir la lista

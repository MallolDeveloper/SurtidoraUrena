# surtidora_pos_bonificacion

**REQ-V09/V10** — la bonificación «compra N, lleva M gratis» entra sola en el POS al llegar a la cantidad, como en ADG.

Pendiente aparte (RB-14, «toda bonificación con tope obligatorio»): el tope nativo (`limit_usage`/`max_usage`) cuenta órdenes, ADG cuenta unidades regaladas; se decide con el cliente antes de exigirlo.

## Por qué existe

Odoo trae la regla en *Punto de venta → Productos → Descuentos y lealtad → Compra X Obtén Y*, pero su POS solo pone gratis un producto que **ya está en la orden** (`Math.min(available, freeQty)` en `_computeUnclaimedFreeProductQty`). Con la caja de 18 Saltinas en pantalla, el Dekreme no aparece: la cajera tiene que agregarlo o pedirlo por ⋮ → Recompensa. Verificado en SurtidoraDev el 11-sep-2026 en pantalla y en el bundle desplegado.

## Qué hace

- Al alcanzar las unidades **pagadas** la cantidad de la regla, agrega las unidades del premio marcadas con `surtidora_premio_id`; el núcleo las pone gratis por su vía normal.
- Si la venta baja de la cantidad, retira las bonificadas que sobran.
- Borrar la línea bonificada = renunciar al premio en esa orden (`disabledRewards`, igual que borrar la línea de premio del núcleo). *Restablecer programas* lo devuelve.
- Las bonificadas no se fusionan con las pagadas: van en su propia línea, y así llegan al backend (`pos.order.line.surtidora_premio_id`).

## Alcance

Solo la bonificación clásica: programa *Compra X Obtén Y*, automático, un solo premio de un solo producto, reglas por unidad. Descuentos por %, cupones, puntos y premios por etiqueta quedan en manos del núcleo.

## Semántica

La de ADG: lo que la cajera teclea es lo que el cliente paga; las gratis van encima. En un 3x2, teclear 2 trae la tercera; teclear 3 trae una cuarta.

## Cómo probar en el mostrador

1. Programa «Bonificación: 1 Caja Saltinas 18/12 = 1 Dekreme GRATIS» (existe en Dev). Vender 1 caja de Saltinas → aparece «1 DEKREME» y su línea de premio a −130.00; total sin cambio.
2. Programa «PRUEBA · 3x2 GALLETAS DE PRUEBAS»: tocar el producto 2 veces → entra una tercera línea gratis. Bajar una de las pagadas a 0 → la gratis se va.
3. Borrar la línea bonificada con ⌫ → no vuelve; ⋮ → *Restablecer programas* → vuelve.

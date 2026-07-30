# Surtidora — Venta por Empaque en POS

El desarrollo clave de la arquitectura híbrida (POS = mostrador contado). En la
operación real el **45% de las líneas** se vende en empaques (docena/caja/fardo).

## Qué hace

| Flujo | Antes (POS estándar) | Con este módulo |
|---|---|---|
| Tocar un producto con empaques | Agrega 1 unidad base | Popup: "Paquete — 55.00" / "Caja de 18 — 880.00" con el precio real de cada unidad |
| Escanear barcode del empaque | Agregaba 1 unidad base (precio errado) o "desconocido" | Agrega el factor completo (18) → total 880 |
| Precio | — | Lo resuelve la regla por cantidad de la lista de precios (sin lógica duplicada) |

La línea queda en unidad base (18 Paquete × 48.89 = 880.00) — así modela el POS
de Odoo internamente; el ticket cuadra al centavo.

## Fraccionamiento (v1.1 — RB-09 / REQ-V23)

Si el producto tiene activo **"La caja se fracciona (¼/½/¾)"** (ficha del
producto), el popup ofrece además las fracciones del empaque **a precio de
caja**: ½ caja de 18 = 9 und a 440.00 (tarifa caja 48.89), no a precio suelto.

- Solo se ofrecen fracciones que den unidades base ENTERAS (caja de 24 →
  6/12/18; caja de 18 → solo ½=9). Decisión de coherencia física, validar
  con el cliente.
- La línea lleva `price_type = manual` para que el POS no recalcule la
  fracción a precio suelto.
- La unidad base NUNCA se fracciona (RB-09).

## Diseño

- `models/pos_load.py`: agrega `relative_factor`/`relative_uom_id` (uom.uom) y
  `uom_ids` (product.template) a la data que el POS carga. Con `*args` para
  tolerar cambios de firma entre builds.
- `static/src/overrides/product_screen_empaques.js`: patch de `ProductScreen`
  (popup de unidad + corrección del escaneo de empaque).

## Prueba post-merge

1. `sudo surtidora-update surtidora_pos_empaques`
2. POS → tocar GALLETAS GUARINA SALADA → popup con Paquete 55 / Caja de 18 880
3. Elegir caja → línea de 18 paquetes, total 880
4. Escanear un barcode de empaque real (los migrados del ensayo #1) → mismo efecto

# Surtidora — Sugerido de Compras (Fase B)

LA pantalla de Adelso (Levantamiento §4.1, captura 14) — evolución del POC
`mallol_sugerido_compras` contra la espec real. **Iteración 1 de 3.**

## Qué trae esta iteración (el motor)

| Mejora vs POC | Detalle | REQ |
|---|---|---|
| Cálculo por lotes | `_read_group` agrupado; el POC buscaba por producto (N+1) y no aguantaba los 3,877 | C01 |
| Unidad de compra | Análisis, grid y OC en la unidad de compra del producto (campo nuevo en la ficha, mapea a la "definida de compra" de ADG) | C03 |
| Conversión de empaques | Las ventas en "Caja de 18" se convierten a base antes de sumar — sumar la columna directo estaría mal | C02 |
| Rango de fechas | Desde–hasta como ADG (default: último año), no "días de historial" | C01 |
| Ref. del suplidor | En el grid y en la descripción de la OC | C04 |
| OC temporal vs firme | Borrador marcado `surtidora_es_temporal` (con filtro en Compras) vs confirmada | C07 |
| Botonera ADG | "Ordenar lo sugerido" (redondeo hacia arriba) / "Quitar cantidades" | as-is |
| Costos sin ITBIS | Como los presenta el sugerido del cliente (aviso en pantalla, igual que ADG) | as-is |
| Multi-company | Compañía en el wizard, dominios y OC | Nota POC |

**Diseño**: `surtidora.sugerido.motor` (AbstractModel) calcula; el wizard solo
pinta. La pantalla definitiva (form u OWL, iteración 2-3) consume el mismo motor.

## Iteraciones siguientes

2. Paneles de contexto: histórico mensual compras vs ventas, última compra
   multi-suplidor, info del producto seleccionado (REQ-C05/C06). Existencia
   anterior/final a la última compra (requiere stock histórico por fecha).
3. Impresión de OC en 2 copias (vendedor/almacén, REQ-C08) + lo que salga de
   la sesión de Compras (estacionalidad, mín/máx, frecuencia de visita).

## Nota de datos

El ambiente dev aún no tiene historial de ventas migrado (la migración va al
final del proyecto): probar con las ventas demo del POC + ventas propias.
Cuando el historial real se migre, la pantalla nace con 12 años de rotación.

# Surtidora — Sugerido de Compras (Fase B)

Evolución del POC `mallol_sugerido_compras` contra la pantalla real de ADG
(Levantamiento §4.1 + captura 14). **La pantalla de Adelso.**

## Iteración 1 (este módulo)

| Qué | Detalle | REQ |
|---|---|---|
| Motor por lotes | `surtidora.sugerido.motor` separado de la UI; agregados con `_read_group` (el POC hacía una consulta por producto — no aguantaba 3,877) | C01 |
| Unidad de compra | Campo "Unidad de compra (sugerido)" en el producto; TODO el análisis y la OC salen en esa unidad (caja/fardo) | C03 |
| Conversión correcta de ventas | Las líneas vendidas en empaques (1 Caja de 18) se convierten a base antes de sumar — sumar la columna directo estaría mal | C02 |
| Columnas del as-is | Últ. compra (fecha+cantidad), existencia, salidas del período, OC pendientes, ventas×día, necesaria, sugerida, a ordenar (editable) | C02 |
| Ref. del suplidor | En el grid y en la descripción de la OC | C04 |
| OC temporal vs firme | "Guardar OC temporal" (borrador marcado + filtro en Compras) / "Generar OC firme" (confirmada) | C07 |
| Botonera ADG | "Ordenar lo sugerido" (copia redondeando hacia arriba) / "Quitar cantidades" | as-is |
| Rango de fechas | Desde–hasta (default 1 año), no "días de historial" | as-is |
| Costos sin ITBIS | Como los presenta el sugerido de ADG (nota en pantalla) | dualidad |
| Multi-company | Compañía en el wizard; dominios y OC por compañía | estándar |

## Pendiente (iteraciones 2-3)

- Paneles de contexto: histórico mensual compras vs ventas, última compra
  multi-suplidor, días abastecido, devoluciones (REQ-C05/C06)
- Impresión de la OC en 2 copias vendedor/almacén (REQ-C08)
- Existencia anterior/final a la última compra (diseño de stock histórico)
- Lo que salga de la sesión de Compras: estacionalidad, mín/máx (preguntas 8-9)

## Nota de datos

El dev aún no tiene historial de ventas migrado (la migración va al final del
proyecto) — probar con los datos demo del POC (Willy Chic) o ventas propias.
El campo `surtidora_uom_compra_id` se puede poblar desde la data real de ADG
(`unid_defectocompra`, ya extraída) cuando se decida.

## Prueba post-merge

1. Instalar desde Apps
2. Poner "Unidad de compra (sugerido)" = Caja de 18 en GALLETAS GUARINA SALADA
3. Compras → Sugerido (Surtidora) → suplidor WILLY CHIC → Calcular
4. Verificar cifras en CAJAS, "Ordenar lo sugerido", y generar una OC temporal
   → aparece con su etiqueta y filtro en Compras

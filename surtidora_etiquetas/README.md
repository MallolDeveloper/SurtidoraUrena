# Surtidora — Códigos Internos y Etiquetas

REQ-P04 (código interno + etiquetas Zebra) y REQ-I08 (etiqueta por producto Y
por empaque).

## Qué hace

**1. Generar código interno** — acción "Generar código interno (sin código)"
en la lista o ficha de productos: asigna un **EAN-13 válido con prefijo 20**
(rango GS1 de uso interno) por secuencia, con dígito verificador correcto y
chequeo anti-colisión contra códigos existentes (productos Y empaques). Solo
actúa sobre productos SIN código — nunca pisa uno real.

**2. Imprimir etiquetas** — acción "Imprimir etiquetas (base + empaques)":
asistente con lista de precios como parámetro; genera PDF de etiquetas
**57×32mm (una por página, estilo rollo)** con nombre, referencia, unidad,
precio y código de barras — una etiqueta por la unidad base y **una por cada
empaque** con su propio barcode y su precio real (misma mecánica de la venta:
caja a 880, no base×factor).

## Pendiente para afinar (sesión de inventario)

- Marca/modelo de la Zebra y el formato actual de etiqueta (⬜ del
  levantamiento) → ajustar el paperformat o pasar a ZPL nativo.
- Los verificadores de pasillo (REQ-V15) muestran precio caja+paquete — misma
  fuente de datos de este módulo.

## Prueba post-merge

1. Instalar desde Apps
2. Productos → seleccionar varios sin barcode → acción "Generar código interno"
3. Seleccionar GALLETAS GUARINA SALADA → "Imprimir etiquetas (base + empaques)"
   → PDF: etiqueta Paquete a 55 con su EAN + etiqueta Caja de 18 a 880

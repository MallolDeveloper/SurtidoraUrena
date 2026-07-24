# Surtidora — Spike Pantalla de Negociación (Backend)

**SPIKE de la Fase C** (Levantamiento §3.3) — prototipo de la variante *backend* para la
decisión POS vs pantalla custom. **No es la pantalla definitiva.**

## Qué hace

Agrega un botón 🤝 en cada línea de la orden de venta que abre la "pantalla de
negociación" (réplica del concepto de ADGSystems):

| Pestaña | Contenido | REQ |
|---|---|---|
| Precios por empaque | Paquete Y caja simultáneos con el equivalente por unidad base + botón "Usar" | REQ-V03 |
| Existencia por almacén | Existencia / reservada / disponible por almacén | REQ-V04 |
| Últimas compras del cliente | Fecha, cantidad, unidad y precio de las últimas 2 compras del producto | REQ-V06 / RB-06 |

## Qué medir en el spike

- Clics/tiempo para: agregar producto → ver precios → cambiar a caja → seguir.
- Comparar contra el flujo de ADG (el estándar del cliente).

## Instalación

`sudo surtidora-update surtidora_venta_spike` tras el merge (o instalar desde Apps).

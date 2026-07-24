# Surtidora — Autorización de Precios

Control de precios en ventas con clave de supervisor y auditoría.

## Reglas implementadas

| Regla | Comportamiento |
|---|---|
| **RB-01 / REQ-V07** | Precio por debajo de la lista → la orden no confirma sin autorización. El supervisor teclea su **PIN en la estación del vendedor** (botón "Autorizar precios"). |
| **RB-08 / REQ-V08** | Precio por debajo del **costo** → bloqueado para TODOS, el PIN **no** aplica. Solo un administrador puede apagar la regla (parámetro de compañía). |
| **REQ-V27** | El PIN es secreto y se guarda cifrado (pbkdf2, igual que las contraseñas de Odoo) — la "doble autorización" pedida históricamente por el cliente. |
| Auditoría | Cada aprobación queda en **Ventas → Autorizaciones de precio**: quién pidió, quién autorizó, producto, lista vs autorizado, cliente, fecha. |

## Configuración

1. **Ajustes → Usuarios**: asignar el grupo **"Autorizador de Precios"** a los supervisores (Adelso, Mariano, Hipólito) y definirles su **PIN** (pestaña "Autorización de precios" del usuario, visible solo para administradores).
2. **Compañía → pestaña "Autorización de precios"**: tolerancia % (default 0 = toda rebaja requiere PIN) y el candado de bajo costo (default bloqueado).

## Flujo del cajero

1. Baja el precio en una línea → al confirmar, Odoo se lo bloquea y aparece el botón amarillo **"Autorizar precios"**.
2. Llama al supervisor → el supervisor teclea su PIN ahí mismo → autorizado y auditado.
3. Si el precio vuelve a bajar después de autorizado, exige autorización de nuevo.

## Diseño (reutilización)

El núcleo — reglas (`_requiere_autorizacion`, `_es_bajo_costo`), verificación de PIN
(`res.users._surtidora_verificar_pin`) y auditoría (`surtidora.autorizacion.precio`) —
no depende de la pantalla: la pantalla de venta definitiva (Fase C, backend o POS)
lo consume tal cual. Solo el wizard es específico del backend.

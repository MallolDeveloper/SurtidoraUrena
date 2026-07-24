# SurtidoraUrena — Módulos Odoo 19

Módulos custom del proyecto Surtidora Ureña (Mallol Consulting). La raíz del repo es el addons path: cada carpeta de primer nivel es un módulo Odoo (prefijo `surtidora_`).

## Flujo de trabajo

- Rama `main` = desarrollo estable. **Nada entra directo**: todo cambio va en rama `feat/...` → Pull Request → revisión (Carlos + auditoría) → merge.
- Al hacer merge a `main`, GitHub Actions despliega automático al ambiente de desarrollo (VPS Mallol, `http://178.156.249.105:8091`, DB `SurtidoraDev`): pull + actualización de los módulos cambiados + restart.
- Rama `production` (futura) = servidor on-premise del cliente, deploy con aprobación manual.

## Ambientes

| Ambiente | Dónde | Deploy |
|---|---|---|
| Desarrollo | VPS Mallol :8091 | Automático al merge en `main` |
| Producción | Servidor on-premise del cliente | Runner self-hosted + aprobación (por montar) |

## Estándares

Ver `Paquete de Arranque Dev` (folder del proyecto): version bump en cada cambio, multi-company, nada hardcoded, no tocar `l10n_do_*`, configurar antes que construir.

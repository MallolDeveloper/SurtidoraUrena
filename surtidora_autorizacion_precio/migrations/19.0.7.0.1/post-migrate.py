# -*- coding: utf-8 -*-
"""Poner al día las filas que ya existían cuando se añadieron `tipo`,
`pos_order_id` y `estado_venta`.

Dos cosas que el valor por defecto no puede acertar:

1. Hasta esta versión el mostrador SOLO hacía excepciones de bajo costo
   (RB-01 no existía allí). Dejarlas con el `rb01` por defecto etiquetaría
   como «rebaja aprobada» lo que en realidad fue vender bajo costo — justo
   al revés de lo que un auditor necesita ver.
2. El enlace con la venta del mostrador se hace al sincronizar, así que las
   filas viejas se quedarían sin él y todas dirían «SIN VENTA», incluidas
   las que sí se cobraron.

El costo del momento NO se puede reconstruir: `standard_price` ya cambió.
Las filas viejas se quedan con 0.00, que es la verdad — no se sabe.
"""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    filas = env['surtidora.autorizacion.precio'].search([('origen', '=', 'pos')])
    if filas:
        filas.write({'tipo': 'rb08'})

    cr.execute("SELECT to_regclass('pos_order')")
    if not cr.fetchone()[0]:
        return
    for fila in filas:
        if fila.pos_order_id or not fila.order_ref:
            continue
        orden = env['pos.order'].search(
            ['|', ('pos_reference', '=', fila.order_ref),
             ('name', '=', fila.order_ref)], limit=1)
        if orden:
            fila.pos_order_id = orden.id
    # estado_venta es calculado y almacenado: ya se calculó al instalar el
    # campo, así que hay que rehacerlo con los enlaces nuevos
    env.add_to_compute(
        env['surtidora.autorizacion.precio']._fields['estado_venta'],
        env['surtidora.autorizacion.precio'].search([]))

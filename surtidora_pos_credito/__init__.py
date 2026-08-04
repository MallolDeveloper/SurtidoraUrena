# -*- coding: utf-8 -*-
from . import models


def configurar_credito_pos(env):
    """Deja el crédito usable sin configuración manual (idempotente):

    - Agrega el método "Crédito (Cuenta Cliente)" a todas las cajas existentes.
    - Activa el límite de crédito por cliente en las compañías, para que el
      campo "Límite de crédito" aparezca en la ficha del cliente — ese campo
      es la autorización que el candado verifica.
    """
    metodo = env.ref('surtidora_pos_credito.metodo_pago_credito')
    for config in env['pos.config'].search([]):
        if metodo not in config.payment_method_ids:
            config.payment_method_ids = [(4, metodo.id)]
    env['res.company'].search([]).filtered(
        lambda c: not c.account_use_credit_limit
    ).account_use_credit_limit = True

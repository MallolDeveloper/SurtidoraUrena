# -*- coding: utf-8 -*-
"""RB-15: los cajeros NO crean ni modifican clientes — eso es de CxC y
supervisores. El origen de los clientes duplicados de hoy es justamente que
las cajeras crean códigos nuevos a clientes viejos."""
from odoo import _, api, models
from odoo.exceptions import AccessError


class PosClientes(models.AbstractModel):
    _name = 'surtidora.pos.clientes'
    _description = 'Permisos de gestión de clientes desde el POS'

    @api.model
    def puede_gestionar(self):
        """¿El usuario de esta sesión puede crear/editar clientes en el POS?

        RB-15: solo supervisores (gerentes del punto de venta). El cajero
        busca y elige, pero las altas y cambios viven en CxC/backend."""
        if not self.env.user.has_group('point_of_sale.group_pos_user'):
            raise AccessError(_('Solo usuarios del punto de venta.'))
        return self.env.user.has_group('point_of_sale.group_pos_manager')

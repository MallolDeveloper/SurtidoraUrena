# -*- coding: utf-8 -*-
from odoo import api, models


class PosSession(models.Model):
    _inherit = 'pos.session'

    @api.model
    def _load_pos_data_models(self, *args, **kwargs):
        """Registra el catálogo de motivos entre los modelos que el POS carga
        al abrir sesión (misma vía por la que pos_loyalty/pos_sale suman los
        suyos). Sin esto, el many2one de la orden no 'conecta' en el
        framework relacional del POS y la asignación se ignora en silencio."""
        modelos = super()._load_pos_data_models(*args, **kwargs)
        return modelos + ['surtidora.motivo.devolucion']

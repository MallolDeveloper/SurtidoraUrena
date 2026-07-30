# -*- coding: utf-8 -*-
from odoo import _, models
from odoo.exceptions import UserError


def _digito_verificador_ean13(doce_digitos):
    """Dígito verificador EAN-13 estándar para una cadena de 12 dígitos."""
    pares = sum(int(d) for d in doce_digitos[1::2])
    impares = sum(int(d) for d in doce_digitos[0::2])
    return str((10 - (impares + pares * 3) % 10) % 10)


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    def action_generar_codigo_interno(self):
        """REQ-P04: asigna un EAN-13 interno (prefijo 20, rango GS1 de uso
        interno) a los productos seleccionados que NO tengan código de barras.
        Con dígito verificador válido: cualquier lector lo acepta."""
        secuencia = self.env['ir.sequence']
        generados = 0
        for producto in self.filtered(lambda p: not p.barcode):
            barcode = self._siguiente_codigo_interno(secuencia)
            producto.barcode = barcode
            generados += 1
        if not generados:
            raise UserError(_(
                'Los productos seleccionados ya tienen código de barras — '
                'el código interno es solo para los que llegan sin código.'))
        return True

    def _siguiente_codigo_interno(self, secuencia, intentos=10):
        """Siguiente EAN-13 interno libre (evita colisiones con códigos ya usados)."""
        for _intento in range(intentos):
            base = '20' + secuencia.next_by_code('surtidora.barcode.interno')
            barcode = base + _digito_verificador_ean13(base)
            en_producto = self.env['product.template'].search_count([('barcode', '=', barcode)])
            en_empaque = self.env['product.uom'].search_count([('barcode', '=', barcode)])
            if not en_producto and not en_empaque:
                return barcode
        raise UserError(_('No se pudo generar un código interno libre — revisar la secuencia.'))

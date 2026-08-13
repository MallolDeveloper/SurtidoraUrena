# -*- coding: utf-8 -*-
"""Motor del mantenimiento de precios: los datos los arma el servidor, la
pantalla solo pinta y recalcula el margen en vivo (mismo principio
motor/pantalla del sugerido).

Reglas de negocio ancladas en la auditoría rev.3:
- El PRECIO es el maestro; el % de margen es indicador derivado.
- precio = costo sin ITBIS × factor × (1 + ITBIS) × (1 + margen).
- Piso comercial 5% ("punto de equilibrio" de Adelso) — visual, no bloquea.
- RB-08: no se FIJA un precio de lista bajo costo — salvo que la fila ya
  esté bajo costo (dato migrado de ADG: 323 reglas en 67 productos) y el
  cambio MEJORE la brecha; empeorarla sigue bloqueado."""
from markupsafe import Markup, escape

from odoo import _, api, models
from odoo.exceptions import AccessError, UserError

_GRUPO = 'sales_team.group_sale_manager'
_TOL = 0.001  # tolerancia para comparar min_quantity (float) con el factor


class PreciosMotor(models.AbstractModel):
    _name = 'surtidora.precios.motor'
    _description = 'Motor del mantenimiento de precios por lista y empaque'

    # ------------------------------------------------------------------
    # Fachadas JSON de la pantalla
    # ------------------------------------------------------------------
    @api.model
    def buscar_json(self, texto):
        """Productos por código, nombre o barcode (para el typeahead)."""
        self._verificar_grupo()
        if not texto or len(texto.strip()) < 2:
            return []
        texto = texto.strip()
        productos = self.env['product.template'].search(
            ['&', ('sale_ok', '=', True),
             '|', '|', ('default_code', 'ilike', texto),
             ('name', 'ilike', texto), ('barcode', 'ilike', texto)],
            limit=30, order='default_code')
        return [{'id': p.id, 'ref': p.default_code or '', 'nombre': p.name}
                for p in productos]

    @api.model
    def producto_json(self, template_id):
        """Todo lo que la pantalla necesita del producto, en una llamada."""
        self._verificar_grupo()
        tmpl = self.env['product.template'].browse(int(template_id))
        tmpl = tmpl.with_company(self.env.company)
        itbis = self._tasa_itbis(tmpl)
        unidades = self._unidades(tmpl)
        reglas, extras = self._reglas_por_clave(tmpl)
        filas = []
        for lista in self._listas():
            for u in unidades:
                regla = reglas.get(self._clave(lista.id, u['factor']))
                costo_total = tmpl.standard_price * u['factor'] * (1 + itbis)
                filas.append({
                    'lista_id': lista.id,
                    'lista': lista.name,
                    'uom_id': u['uom_id'],
                    'unidad': u['nombre'],
                    'factor': u['factor'],
                    'regla_id': regla and regla.id or False,
                    # lo que el negocio dice: "la caja a 880" (total del
                    # empaque), redondeado — 48.8889×18 da 880.0002 en float
                    'precio_total': round(regla.fixed_price * u['factor'], 2) if regla else 0.0,
                    'costo_total_itbis': costo_total,
                })
        return {
            'template_id': tmpl.id,
            'ref': tmpl.default_code or '',
            'nombre': tmpl.name,
            'costo_base': tmpl.standard_price,
            'itbis_pct': itbis * 100,
            'unidades': unidades,
            'filas': filas,
            # reglas que esta pantalla NO edita (variantes, promos con fecha,
            # cantidades fraccionadas): se avisan, no se ocultan
            'reglas_extra': extras,
        }

    @api.model
    def guardar_json(self, template_id, cambios):
        """Escribe/crea las reglas de lista. cambios: [{lista_id, uom_id,
        precio_total}] — precio_total es el TOTAL del empaque. El factor y
        la validez de la lista se recalculan AQUÍ (no se confía en el
        navegador)."""
        self._verificar_grupo()
        tmpl = self.env['product.template'].browse(int(template_id))
        tmpl = tmpl.with_company(self.env.company)
        itbis = self._tasa_itbis(tmpl)
        reglas, _extras = self._reglas_por_clave(tmpl)
        listas_ok = {l.id for l in self._listas()}
        Item = self.env['product.pricelist.item']
        bitacora, avisos = [], []
        for c in cambios:
            lista_id = int(c['lista_id'])
            if lista_id not in listas_ok:
                raise UserError(_('Lista de precios inválida.'))
            factor, unidad = self._factor_de_uom(tmpl, int(c['uom_id']))
            total = float(c['precio_total'])
            if total <= 0:
                raise UserError(_('El precio de %s debe ser mayor que cero.', unidad))
            regla = reglas.get(self._clave(lista_id, factor))
            anterior = round(regla.fixed_price * factor, 2) if regla else None
            costo_total = tmpl.standard_price * factor * (1 + itbis)
            if costo_total > 0 and total < costo_total:
                # RB-08 con válvula para data migrada: si la fila YA estaba
                # bajo costo, se permite MEJORAR la brecha; empeorar no.
                if anterior is None or anterior >= costo_total or total < anterior:
                    raise UserError(_(
                        '%(unidad)s quedaría BAJO COSTO (precio %(precio).2f vs '
                        'costo con ITBIS %(costo).2f). RB-08: no se fija un precio '
                        'de lista por debajo del costo.',
                        unidad=unidad, precio=total, costo=costo_total))
                avisos.append(_(
                    '%(unidad)s sigue bajo costo (%(precio).2f vs %(costo).2f), '
                    'pero el cambio reduce la brecha.',
                    unidad=unidad, precio=total, costo=costo_total))
            unitario = total / factor
            if regla:
                regla.fixed_price = unitario
            else:
                Item.create({
                    'pricelist_id': lista_id,
                    'product_tmpl_id': tmpl.id,
                    'applied_on': '1_product',
                    'compute_price': 'fixed',
                    'min_quantity': 0.0 if factor == 1.0 else factor,
                    'fixed_price': unitario,
                })
            bitacora.append(_(
                '%(lista)s · %(unidad)s: %(antes)s → %(ahora).2f',
                lista=c.get('lista', lista_id), unidad=unidad,
                antes=('%.2f' % anterior) if anterior is not None else _('(nuevo)'),
                ahora=total))
        if bitacora:
            titulo = _('Mantenimiento de precios por %s:', self.env.user.name)
            cuerpo = Markup('<br/>').join(
                [escape(titulo)] + [escape(l) for l in bitacora])
            tmpl.message_post(body=cuerpo)
        return {'ok': True, 'cambios': len(bitacora), 'avisos': avisos}

    # ------------------------------------------------------------------
    # Piezas
    # ------------------------------------------------------------------
    def _verificar_grupo(self):
        if not self.env.user.has_group(_GRUPO):
            raise AccessError(_('Solo gerentes de ventas mantienen precios.'))

    def _listas(self):
        """Listas operativas: las que tienen reglas fijas por producto
        (excluye la "Default" vacía que Odoo crea sola)."""
        listas = self.env['product.pricelist'].search(
            [('company_id', 'in', [False, self.env.company.id])], order='id')
        grupos = self.env['product.pricelist.item']._read_group(
            [('pricelist_id', 'in', listas.ids), ('compute_price', '=', 'fixed')],
            ['pricelist_id'], ['__count'])
        con_reglas = {g[0].id for g in grupos}
        return listas.filtered(lambda l: l.id in con_reglas) or listas

    def _tasa_itbis(self, tmpl):
        """Tasa de impuesto de venta (0.18 o 0.0 si exento) — los costos de
        Surtidora van SIN ITBIS y los precios CON ITBIS (dualidad de ADG)."""
        impuestos = tmpl.taxes_id.filtered(
            lambda t: t.company_id == self.env.company and t.amount_type == 'percent')
        return sum(impuestos.mapped('amount')) / 100.0

    def _unidades(self, tmpl):
        base = tmpl.uom_id
        unidades = [{'uom_id': base.id, 'nombre': base.name, 'factor': 1.0}]
        for uom in tmpl.uom_ids:
            factor = uom._compute_quantity(1.0, base, round=False) or 1.0
            if factor > 1:
                unidades.append({'uom_id': uom.id, 'nombre': uom.name, 'factor': factor})
        return unidades

    def _factor_de_uom(self, tmpl, uom_id):
        """Factor REAL de la unidad, recalculado en servidor. La unidad debe
        ser la base o un empaque del producto."""
        for u in self._unidades(tmpl):
            if u['uom_id'] == uom_id:
                return u['factor'], u['nombre']
        raise UserError(_('La unidad no pertenece al producto.'))

    def _reglas_por_clave(self, tmpl):
        """Reglas fijas del producto que ESTA pantalla mantiene, indexadas
        por (lista, factor):
        - base: min_quantity 0 o 1 (si hay ambas gana la 1, como el motor de
          precios de Odoo: min_quantity desc, luego id desc);
        - empaque: min_quantity == factor exacto.
        Variantes, promos con fecha y cantidades fraccionadas NO se tocan:
        se devuelven como conteo para avisar en pantalla."""
        reglas = self.env['product.pricelist.item'].search([
            ('product_tmpl_id', '=', tmpl.id),
            ('compute_price', '=', 'fixed'),
            ('applied_on', '=', '1_product'),
            ('product_id', '=', False),
            ('date_start', '=', False),
            ('date_end', '=', False),
        ])
        factores = [u['factor'] for u in self._unidades(tmpl)]
        indice, extras = {}, 0
        for r in sorted(reglas, key=lambda r: (r.min_quantity, r.id)):
            mq = r.min_quantity
            if mq < _TOL or abs(mq - 1.0) < _TOL:
                # base: el sort asegura que la ganadora del motor de Odoo
                # (min_quantity mayor, luego id mayor) quede de última y pise
                indice[self._clave(r.pricelist_id.id, 1.0)] = r
                continue
            # la clave se arma con el FACTOR de la unidad (no con el
            # min_quantity de la regla): es lo que la pantalla busca
            factor = next((f for f in factores
                           if f > 1 and abs(mq - f) < _TOL), None)
            if factor is not None:
                indice[self._clave(r.pricelist_id.id, factor)] = r
            else:
                extras += 1  # fraccionadas u otros min_qty: no se editan aquí
        extras += self.env['product.pricelist.item'].search_count([
            ('product_tmpl_id', '=', tmpl.id),
            '|', '|', '|', ('compute_price', '!=', 'fixed'),
            ('applied_on', '!=', '1_product'),
            ('product_id', '!=', False),
            '|', ('date_start', '!=', False), ('date_end', '!=', False),
        ])
        return indice, extras

    @staticmethod
    def _clave(lista_id, factor):
        return f'{lista_id}:{round(float(factor), 3)}'

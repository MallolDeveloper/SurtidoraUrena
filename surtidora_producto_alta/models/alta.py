# -*- coding: utf-8 -*-
"""Alta ágil de productos (REQ-P06).

El servidor decide y escribe; la pantalla solo pinta y recoge (mismo
principio motor/pantalla del sugerido y de mantenimiento de precios).
Todo el alta ocurre en UNA transacción: o queda el producto completo con
sus empaques, precios y proveedor, o no queda nada.

Correcciones de la revisión adversaria (14-ago) marcadas con «RA:»."""
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

_GRUPO = 'stock.group_stock_manager'
_TOL = 0.001


class ProductoAlta(models.AbstractModel):
    _name = 'surtidora.producto.alta'
    _description = 'Alta ágil de productos'

    # ------------------------------------------------------------------
    # Datos para armar la pantalla
    # ------------------------------------------------------------------
    @api.model
    def datos_iniciales(self):
        """Todo lo que la pantalla necesita para pintarse."""
        self._verificar_grupo()
        compania = self.env.company
        impuesto = self.env['account.tax'].search([
            ('type_tax_use', '=', 'sale'),
            ('amount_type', '=', 'percent'),
            ('company_id', '=', compania.id),
        ], order='amount desc', limit=1)
        almacen = self.env['stock.warehouse'].search(
            [('company_id', '=', compania.id)], order='sequence, id', limit=1)
        listas = self._listas()
        return {
            # RA: la lista de referencia (la primera) define el list_price
            # del producto, para que ninguna tarifa sin regla venda a 0
            'listas': [{'id': l.id, 'nombre': l.name,
                        'moneda': l.currency_id.name} for l in listas],
            'impuesto': {'id': impuesto.id, 'nombre': impuesto.name,
                         'tasa': impuesto.amount} if impuesto else None,
            'almacen': {'id': almacen.id, 'nombre': almacen.name} if almacen else None,
            'moneda': compania.currency_id.symbol,
            # referencia del levantamiento (§3.4): el paquete se vende con
            # más margen que la caja, y el mayorista con menos que el detalle
            'margen_sugerido': {'detalle': 15.0, 'mayorista': 9.0, 'caja': 7.0},
        }

    @api.model
    def buscar(self, modelo, texto, limite=10):
        """Typeahead de proveedor y categoría."""
        self._verificar_grupo()
        permitidos = {
            'res.partner': [('supplier_rank', '>', 0)],
            'product.category': [],
        }
        if modelo not in permitidos:
            raise UserError(_('Búsqueda no permitida.'))
        dominio = list(permitidos[modelo])
        if texto:
            dominio.append(('name', 'ilike', texto))
        registros = self.env[modelo].search(dominio, limit=limite, order='name')
        return [{'id': r.id, 'nombre': r.display_name} for r in registros]

    @api.model
    def buscar_uom(self, texto, base_id=False, limite=20):
        """Unidades candidatas a empaque de ESTA base.

        RA: antes se devolvía `relative_factor` (el factor contra el padre
        inmediato) y la pantalla mentía en cadenas de dos niveles
        (Unidad→Paquete→Caja). Ahora el factor viene RESUELTO contra la
        unidad base, y solo se ofrecen unidades convertibles a ella."""
        self._verificar_grupo()
        dominio = [('name', 'ilike', texto)] if texto else []
        base = self.env['uom.uom'].browse(int(base_id or 0))
        registros = self.env['uom.uom'].search(dominio, limit=100, order='name')
        filas = []
        for uom in registros:
            factor = 0.0
            if base.exists() and uom != base:
                factor = self._factor_contra_base(uom, base)
                if factor <= 1 + _TOL:
                    continue  # no sirve de empaque de esta base
            filas.append({
                'id': uom.id,
                'nombre': uom.display_name,
                'factor': factor,
                # ayuda a distinguir las UdM duplicadas de la migración
                'relativa': uom.relative_uom_id.display_name or '',
            })
            if len(filas) >= limite:
                break
        return filas

    @api.model
    def buscar_uom_base(self, texto, limite=15):
        """Unidades para la BASE del producto (sin filtro de convertibilidad)."""
        self._verificar_grupo()
        dominio = [('name', 'ilike', texto)] if texto else []
        registros = self.env['uom.uom'].search(dominio, limit=limite, order='name')
        return [{'id': u.id, 'nombre': u.display_name, 'factor': 0.0,
                 'relativa': u.relative_uom_id.display_name or ''}
                for u in registros]

    @api.model
    def crear_uom(self, nombre, factor, base_id):
        """Crea la unidad de empaque que falta (RA: sin esto el alta se
        traba — ADG tiene 175 factores distintos y cada semana llegan
        referencias con empaques nuevos)."""
        self._verificar_grupo()
        nombre = (nombre or '').strip()
        factor = self._num(factor)
        base = self.env['uom.uom'].browse(int(base_id or 0))
        if not nombre:
            raise UserError(_('La unidad necesita un nombre.'))
        if factor <= 1:
            raise UserError(_('El empaque debe contener más de una unidad base.'))
        if not base.exists():
            raise UserError(_('Elija primero la unidad base del producto.'))
        if self.env['uom.uom'].search_count([('name', '=ilike', nombre)]):
            raise UserError(_('Ya existe una unidad llamada "%s".') % nombre)
        uom = self.env['uom.uom'].sudo().create({
            'name': nombre,
            'relative_factor': factor,
            'relative_uom_id': base.id,
        })
        return {'id': uom.id, 'nombre': uom.display_name, 'factor': factor,
                'relativa': base.display_name}

    @api.model
    def crear_registro(self, modelo, nombre):
        """Alta rápida de proveedor o categoría sin salir de la pantalla."""
        self._verificar_grupo()
        nombre = (nombre or '').strip()
        if not nombre:
            raise UserError(_('Escriba el nombre primero.'))
        if modelo == 'res.partner':
            registro = self.env['res.partner'].sudo().create(
                {'name': nombre, 'supplier_rank': 1, 'company_type': 'company'})
        elif modelo == 'product.category':
            registro = self.env['product.category'].sudo().create({'name': nombre})
        else:
            raise UserError(_('No se puede crear ese registro aquí.'))
        return {'id': registro.id, 'nombre': registro.display_name}

    @api.model
    def codigo_barras_interno(self):
        """EAN-13 interno libre (reutiliza el generador de etiquetas)."""
        self._verificar_grupo()
        return self.env['product.template'].sudo()._siguiente_codigo_interno(
            self.env['ir.sequence'].sudo())

    # ------------------------------------------------------------------
    # Alta
    # ------------------------------------------------------------------
    @api.model
    def crear(self, datos):
        """Crea el producto completo. Devuelve un resumen para la pantalla.

        RA: valida TODO y reporta los problemas JUNTOS — antes llegaban de
        uno en uno y el encargado corregía y reintentaba cinco veces."""
        self._verificar_grupo()
        datos = datos or {}
        errores = []

        nombre = (datos.get('nombre') or '').strip()
        if not nombre:
            errores.append(_('Falta el nombre del producto.'))
        costo = self._num(datos.get('costo'))
        if costo <= 0:
            # RA: costo 0 desactivaba RB-08 por completo
            errores.append(_('Falta el costo (debe ser mayor que cero).'))

        uom_base = self.env['uom.uom'].browse(int(datos.get('uom_id') or 0))
        if not uom_base.exists():
            errores.append(_('Falta la unidad base del producto.'))

        empaques = []
        if uom_base.exists():
            empaques = self._validar_empaques(datos.get('empaques') or [],
                                              uom_base, errores)
        listas = self._listas()
        precios = self._validar_precios(datos.get('precios') or {}, listas,
                                        empaques, costo, datos, errores)
        self._validar_codigos(datos, empaques, errores)
        self._validar_reorden(datos, errores)
        if errores:
            raise UserError('\n• '.join([_('Revise antes de crear:')] + errores))

        # --- escritura (una sola transacción) --------------------------
        # sudo puntual: el encargado de inventario no tiene permisos de
        # ventas ni de compras, pero el alta debe dejar tarifas y ficha de
        # proveedor completas (RA: sin esto el alta reventaba por ACL)
        env = self.sudo().env
        plantilla = env['product.template'].create(
            self._vals_producto(datos, nombre, uom_base, costo, empaques,
                                listas, precios))
        variante = plantilla.product_variant_id

        self._crear_codigos_empaque(env, variante, empaques)
        self._crear_reglas_precio(env, plantilla, listas, precios, empaques)
        self._crear_proveedor(env, plantilla, datos)
        self._crear_reorden(env, variante, datos)

        return {
            'id': plantilla.id,
            'nombre': plantilla.display_name,
            'referencia': plantilla.default_code or '',
            'codigo_barras': variante.barcode or '',
            'empaques': len(empaques),
            'reglas': len(listas) * (1 + len(empaques)),
        }

    # ------------------------------------------------------------------
    # Validación
    # ------------------------------------------------------------------
    def _factor_contra_base(self, uom, base):
        """Cuántas unidades base entran en `uom`. 0 si no son convertibles
        (RA: unidades de otra cadena daban un factor sin sentido)."""
        try:
            return uom._compute_quantity(1.0, base, round=False)
        except Exception:
            return 0.0

    def _validar_empaques(self, crudos, uom_base, errores):
        empaques, vistos, por_factor = [], set(), {}
        for crudo in crudos:
            uom_id = int(crudo.get('uom_id') or 0)
            if not uom_id:
                # RA: antes se descartaba en silencio y el alta se declaraba
                # exitosa sin ese empaque
                errores.append(_('Hay un empaque sin unidad seleccionada.'))
                continue
            uom = self.env['uom.uom'].browse(uom_id)
            if not uom.exists():
                errores.append(_('Un empaque apunta a una unidad que ya no existe.'))
                continue
            if uom == uom_base:
                errores.append(_('El empaque no puede ser la unidad base.'))
                continue
            if uom.id in vistos:
                errores.append(_('El empaque "%s" está repetido.') % uom.display_name)
                continue
            vistos.add(uom.id)
            factor = self._factor_contra_base(uom, uom_base)
            if factor <= 1 + _TOL:
                errores.append(_(
                    'El empaque "%(emp)s" no equivale a más de una unidad '
                    '"%(base)s" (¿pertenece a otra familia de unidades?).',
                    emp=uom.display_name, base=uom_base.display_name))
                continue
            # RA: las tarifas guardan el precio por CANTIDAD (min_quantity =
            # factor): dos empaques del mismo tamaño no se pueden distinguir
            clave = round(factor, 3)
            if clave in por_factor:
                errores.append(_(
                    'Los empaques "%(a)s" y "%(b)s" equivalen ambos a %(f)s '
                    'unidades base: la tarifa no puede darles precios '
                    'distintos. Deje uno solo.',
                    a=por_factor[clave], b=uom.display_name, f=clave))
                continue
            por_factor[clave] = uom.display_name
            empaques.append({'uom': uom, 'factor': factor,
                             'barcode': (crudo.get('barcode') or '').strip()})
        return empaques

    def _validar_precios(self, crudos, listas, empaques, costo, datos, errores):
        """Precios por lista y por unidad. RB-08: nada por debajo del costo.

        En pantalla se teclea el TOTAL del empaque ("la caja a 880"); aquí
        se guarda el precio por unidad base que espera la tarifa."""
        costo_con_itbis = costo * (1 + self._tasa(datos))
        precios = {}
        for lista in listas:
            base = self._num(crudos.get('%s:base' % lista.id))
            if base <= 0:
                errores.append(_('Falta el precio de la unidad en "%s".') % lista.name)
            else:
                self._exigir_sobre_costo(base, costo_con_itbis, lista.name,
                                         _('unidad'), errores)
                precios[self._clave(lista.id, 1.0)] = base
            for empaque in empaques:
                total = self._num(crudos.get('%s:%s' % (lista.id, empaque['uom'].id)))
                if total <= 0:
                    errores.append(_(
                        'Falta el precio de "%(emp)s" en "%(lista)s".',
                        emp=empaque['uom'].display_name, lista=lista.name))
                    continue
                unitario = total / empaque['factor']
                self._exigir_sobre_costo(unitario, costo_con_itbis, lista.name,
                                         empaque['uom'].display_name, errores)
                precios[self._clave(lista.id, empaque['factor'])] = unitario
        return precios

    def _exigir_sobre_costo(self, precio, costo_con_itbis, lista, unidad, errores):
        """RB-08: la venta bajo costo está bloqueada para TODOS."""
        if costo_con_itbis and precio < costo_con_itbis - _TOL:
            errores.append(_(
                '"%(unidad)s" en "%(lista)s" queda por debajo del costo '
                '(regla RB-08).', unidad=unidad, lista=lista))

    def _validar_codigos(self, datos, empaques, errores):
        """Códigos únicos entre productos, empaques y el propio formulario.

        RA: `active_test=False` — un código en uso por un producto ARCHIVADO
        no aparecía aquí y reventaba después con un error crudo de Postgres."""
        env = self.env(context=dict(self.env.context, active_test=False))
        codigos = []
        principal = (datos.get('barcode') or '').strip()
        if principal:
            codigos.append((principal, _('el producto')))
        for empaque in empaques:
            if empaque['barcode']:
                codigos.append((empaque['barcode'], empaque['uom'].display_name))
        vistos = set()
        for codigo, donde in codigos:
            if codigo in vistos:
                errores.append(_(
                    'El código de barras %s está repetido en el formulario.') % codigo)
                continue
            vistos.add(codigo)
            if env['product.product'].sudo().search_count([('barcode', '=', codigo)]):
                errores.append(_(
                    'El código %(cod)s (%(donde)s) ya lo usa otro producto.',
                    cod=codigo, donde=donde))
            elif env['product.uom'].sudo().search_count([('barcode', '=', codigo)]):
                errores.append(_(
                    'El código %(cod)s (%(donde)s) ya lo usa otro empaque.',
                    cod=codigo, donde=donde))
        referencia = (datos.get('referencia') or '').strip()
        # RA: la referencia también vive en las variantes
        if referencia and env['product.product'].sudo().search_count(
                [('default_code', '=', referencia)]):
            errores.append(_('La referencia interna "%s" ya existe.') % referencia)

    def _validar_reorden(self, datos, errores):
        minimo = self._num(datos.get('reorden_min'))
        maximo = self._num(datos.get('reorden_max'))
        # RA: solo mínimo es válido (Odoo lo acepta); solo se rechaza el
        # máximo MENOR que el mínimo cuando ambos vienen
        if maximo and maximo < minimo:
            errores.append(_('El reorden máximo no puede ser menor que el mínimo.'))

    # ------------------------------------------------------------------
    # Escritura
    # ------------------------------------------------------------------
    def _vals_producto(self, datos, nombre, uom_base, costo, empaques,
                       listas, precios):
        # RA: list_price 0 hacía que cualquier tarifa SIN regla vendiera a
        # cero; se usa el precio base de la primera lista como referencia
        referencia_precio = precios.get(self._clave(listas[0].id, 1.0), 0.0) if listas else 0.0
        vals = {
            'name': nombre,
            'is_storable': True,
            'uom_id': uom_base.id,
            'standard_price': costo,  # SIN ITBIS (dualidad de ADG)
            'list_price': referencia_precio,
            'uom_ids': [(6, 0, [e['uom'].id for e in empaques])],
        }
        if datos.get('referencia'):
            vals['default_code'] = datos['referencia'].strip()
        if datos.get('categoria_id'):
            vals['categ_id'] = int(datos['categoria_id'])
        if datos.get('barcode'):
            vals['barcode'] = datos['barcode'].strip()
        impuesto_id = datos.get('impuesto_id')
        # exento: sin impuestos NI en venta NI en compra (RA: el exento
        # quedaba con ITBIS de compra y descuadraba el costeo)
        vals['taxes_id'] = [(6, 0, [int(impuesto_id)] if impuesto_id else [])]
        vals['supplier_taxes_id'] = [(6, 0, self._impuestos_compra(impuesto_id))]
        # el mostrador es el POS: sin esto el producto no aparece en caja
        if 'available_in_pos' in self.env['product.template']._fields:
            vals['available_in_pos'] = True
        campos = self.env['product.template']._fields
        if 'surtidora_caja_fraccionable' in campos:
            vals['surtidora_caja_fraccionable'] = bool(datos.get('fraccionable'))
        if 'surtidora_uom_compra_id' in campos and datos.get('uom_compra_id'):
            vals['surtidora_uom_compra_id'] = int(datos['uom_compra_id'])
        return vals

    def _impuestos_compra(self, impuesto_venta_id):
        """El equivalente de compra del impuesto de venta elegido."""
        if not impuesto_venta_id:
            return []
        venta = self.env['account.tax'].browse(int(impuesto_venta_id))
        compra = self.env['account.tax'].search([
            ('type_tax_use', '=', 'purchase'),
            ('amount_type', '=', 'percent'),
            ('amount', '=', venta.amount),
            ('company_id', '=', self.env.company.id),
        ], limit=1)
        return compra.ids

    def _crear_codigos_empaque(self, env, variante, empaques):
        """Un product.uom por empaque CON código (el barcode es obligatorio
        en ese modelo: sin código no se crea el registro, el empaque igual
        queda disponible por `uom_ids`)."""
        filas = [{
            'product_id': variante.id,
            'uom_id': empaque['uom'].id,
            'barcode': empaque['barcode'],
        } for empaque in empaques if empaque['barcode']]
        if filas:
            env['product.uom'].create(filas)

    def _crear_reglas_precio(self, env, plantilla, listas, precios, empaques):
        """Una regla fija por lista y por unidad: la base con min_quantity 0
        y cada empaque con min_quantity = su factor (mecánica validada en el
        ensayo de migración)."""
        filas = []
        for lista in listas:
            filas.append(self._vals_regla(
                lista, plantilla, 0.0, precios[self._clave(lista.id, 1.0)]))
            for empaque in empaques:
                filas.append(self._vals_regla(
                    lista, plantilla, empaque['factor'],
                    precios[self._clave(lista.id, empaque['factor'])]))
        env['product.pricelist.item'].create(filas)

    def _vals_regla(self, lista, plantilla, min_qty, precio):
        return {
            'pricelist_id': lista.id,
            'applied_on': '1_product',
            'product_tmpl_id': plantilla.id,
            'compute_price': 'fixed',
            'fixed_price': round(precio, 4),
            'min_quantity': min_qty,
        }

    def _crear_proveedor(self, env, plantilla, datos):
        if not datos.get('proveedor_id'):
            return
        vals = {
            'partner_id': int(datos['proveedor_id']),
            'product_tmpl_id': plantilla.id,
            'price': self._num(datos.get('costo')),
        }
        # el código del proveedor solo si lo capturaron: rellenarlo con el
        # interno fue el bug del punto 7 (3,743 fichas con basura)
        if datos.get('ref_proveedor'):
            vals['product_code'] = datos['ref_proveedor'].strip()
        env['product.supplierinfo'].create(vals)

    def _crear_reorden(self, env, variante, datos):
        minimo = self._num(datos.get('reorden_min'))
        maximo = self._num(datos.get('reorden_max'))
        if minimo <= 0 and maximo <= 0:
            return
        almacen = env['stock.warehouse'].browse(int(datos.get('almacen_id') or 0))
        if not almacen.exists():
            almacen = env['stock.warehouse'].search(
                [('company_id', '=', self.env.company.id)], order='sequence, id', limit=1)
        if not almacen:
            return  # sin almacén no hay regla de reorden, pero el alta vale
        env['stock.warehouse.orderpoint'].create({
            'product_id': variante.id,
            'warehouse_id': almacen.id,
            'location_id': almacen.lot_stock_id.id,
            'product_min_qty': minimo,
            'product_max_qty': max(maximo, minimo),
        })

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------
    def _verificar_grupo(self):
        if not self.env.user.has_group(_GRUPO):
            raise AccessError(_('Solo el encargado de inventario da de alta productos.'))

    def _listas(self):
        """Listas operativas de la compañía, en la MONEDA de la compañía
        (RA: una tarifa en otra moneda pediría precios que no cuadran)."""
        listas = self.env['product.pricelist'].search([
            ('company_id', 'in', [False, self.env.company.id]),
            ('currency_id', '=', self.env.company.currency_id.id),
        ], order='id')
        grupos = self.env['product.pricelist.item']._read_group(
            [('pricelist_id', 'in', listas.ids), ('compute_price', '=', 'fixed')],
            ['pricelist_id'], ['__count'])
        con_reglas = {g[0].id for g in grupos}
        return listas.filtered(lambda l: l.id in con_reglas) or listas

    def _tasa(self, datos):
        if not datos.get('impuesto_id'):
            return 0.0
        impuesto = self.env['account.tax'].browse(int(datos['impuesto_id']))
        return (impuesto.amount / 100.0) if impuesto.exists() else 0.0

    @staticmethod
    def _num(valor):
        try:
            return float(valor or 0)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _clave(lista_id, factor):
        return '%s:%s' % (lista_id, round(float(factor), 3))

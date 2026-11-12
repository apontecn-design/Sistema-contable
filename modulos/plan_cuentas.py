# CONTEM: componente extraído del app.py original; ejecución secuencial compartida.
PLAN_BASE = [
    ("1", "ACTIVOS", "Activo", "Activo", None, 1),
    ("1.1", "Activo Corriente", "Activo", "Activo", "1", 2),
    ("1.1.01", "Caja", "Activo", "Activo", "1.1", 3),
    ("1.1.02", "Bancos", "Activo", "Activo", "1.1", 3),
    ("1.1.03", "Cuentas por cobrar", "Activo", "Activo", "1.1", 3),
    ("1.1.03.01", "Clientes", "Activo", "Activo", "1.1.03", 4),
    ("1.1.03.02", "IVA Crédito Fiscal", "Activo", "Activo", "1.1.03", 4),
    ("1.1.04", "Inventarios", "Activo", "Activo", "1.1", 3),
    ("1.2", "Activo No Corriente", "Activo", "Activo", "1", 2),
    ("1.2.01", "Propiedades, Planta y Equipos", "Activo", "Activo", "1.2", 3),
    ("1.2.01.01", "Activo Fijo", "Activo", "Activo", "1.2.01", 4),
    ("2", "PASIVOS", "Pasivo", "Pasivo", None, 1),
    ("2.1", "Pasivo Corriente", "Pasivo", "Pasivo", "2", 2),
    ("2.1.01", "Cuentas por pagar", "Pasivo", "Pasivo", "2.1", 3),
    ("2.1.01.01", "Proveedores", "Pasivo", "Pasivo", "2.1.01", 4),
    ("2.1.01.02", "IVA Débito Fiscal", "Pasivo", "Pasivo", "2.1.01", 4),
    ("2.1.01.03", "IVA por pagar", "Pasivo", "Pasivo", "2.1.01", 4),
    # Obligaciones laborales del plan histórico de producción (altas no destructivas).
    ("2.1.02", "Obligaciones laborales y previsionales", "Pasivo", "Pasivo", "2.1", 3),
    ("2.1.02.01", "Remuneraciones por pagar", "Pasivo", "Pasivo", "2.1.02", 4),
    ("2.1.02.02", "Cotizaciones previsionales por pagar", "Pasivo", "Pasivo", "2.1.02", 4),
    ("2.1.02.03", "Retenciones de Trabajadores por pagar", "Pasivo", "Pasivo", "2.1.02", 4),
    ("2.1.02.04", "Otras obligaciones laborales", "Pasivo", "Pasivo", "2.1.02", 4),
    ("2.1.02.05", "Impuesto Único de trabajadores por pagar", "Pasivo", "Pasivo", "2.1.02", 4),
    ("3", "PATRIMONIO", "Patrimonio", "Patrimonio", None, 1),
    ("3.1", "Capital", "Patrimonio", "Patrimonio", "3", 2),
    ("3.1.01", "Capital", "Patrimonio", "Patrimonio", "3.1", 3),
    ("4", "INGRESOS", "Nominal", "Ingresos", None, 1),
    ("4.1", "Ingresos Operacionales", "Nominal", "Ingresos", "4", 2),
    ("4.1.01", "Ventas", "Nominal", "Ingresos", "4.1", 3),
    ("4.1.02", "Servicios", "Nominal", "Ingresos", "4.1", 3),
    ("4.1.03", "Otros Ingresos", "Nominal", "Ingresos", "4.1", 3),
    ("4.1.04", "Ventas exentas", "Nominal", "Ingresos", "4.1", 3),
    ("5", "COSTOS", "Nominal", "Gastos", None, 1),
    ("5.1", "Costos de Venta", "Nominal", "Gastos", "5", 2),
    ("5.1.01", "Costo de Ventas", "Nominal", "Gastos", "5.1", 3),
    ("5.2", "GASTOS", "Nominal", "Gastos", None, 1),
    ("5.2.01", "Gastos Generales", "Nominal", "Gastos", "5.2", 3),
    ("5.2.02", "IVA No Recuperable", "Nominal", "Gastos", "5.2", 3),
    ("5.2.03", "IVA Uso Común", "Nominal", "Gastos", "5.2", 3),
    ("6", "RESULTADOS", "Nominal", "Gastos", None, 1),
    ("1.1.09", "Cuentas por cobrar relacionadas", "Activo", "Activo", "1.1", 3),
    ("1.1.09.01", "Cuentas por cobrar partes relacionadas nacionales", "Activo", "Activo", "1.1.09", 4),
    ("1.1.09.02", "Cuentas por cobrar partes relacionadas extranjeras", "Activo", "Activo", "1.1.09", 4),
    ("1.2.01.02", "Terrenos", "Activo", "Activo", "1.2.01", 4),
    ("1.2.01.03", "Construcciones y bodegas", "Activo", "Activo", "1.2.01", 4),
    ("1.2.01.04", "Vehículos", "Activo", "Activo", "1.2.01", 4),
    ("1.2.01.05", "Equipos y otros activos fijos", "Activo", "Activo", "1.2.01", 4),
    ("1.2.02", "Depreciación acumulada", "Activo", "Activo", "1.2", 3),
    ("1.2.02.01", "Depreciación acumulada construcciones", "Activo", "Activo", "1.2.02", 4),
    ("1.2.02.02", "Depreciación acumulada vehículos", "Activo", "Activo", "1.2.02", 4),
    ("1.2.02.03", "Depreciación acumulada equipos", "Activo", "Activo", "1.2.02", 4),
    ("2.1.04", "Cuentas por pagar relacionadas", "Pasivo", "Pasivo", "2.1", 3),
    ("2.1.04.01", "Cuentas por pagar partes relacionadas nacionales", "Pasivo", "Pasivo", "2.1.04", 4),
    ("2.1.04.02", "Cuentas por pagar partes relacionadas extranjeras", "Pasivo", "Pasivo", "2.1.04", 4),
    ("3.2", "Resultados acumulados", "Patrimonio", "Patrimonio", "3", 2),
    ("3.2.01", "Resultados acumulados", "Patrimonio", "Patrimonio", "3.2", 3),
    ("3.3", "Resultado del ejercicio", "Patrimonio", "Patrimonio", "3", 2),
    ("3.3.01", "Resultado del ejercicio", "Patrimonio", "Patrimonio", "3.3", 3),
    ("5.2.01.14", "Comisiones y gastos bancarios", "Nominal", "Gastos", "5.2.01", 4),
    ("5.2.01.15", "Patentes y permisos", "Nominal", "Gastos", "5.2.01", 4),
    ("5.2.01.16", "Depreciaciones", "Nominal", "Gastos", "5.2.01", 4),
    ("6.1", "Gastos Administrativos", "Nominal", "Gastos", "6", 2),
]


def instalar_plan_base(conn):
    for fila in PLAN_BASE:
        conn.execute("""
            INSERT OR IGNORE INTO plan_cuentas
            (codigo, nombre, categoria, tipo, padre_codigo, nivel)
            VALUES (?, ?, ?, ?, ?, ?)
        """, fila)

    conn.commit()


def reorganizar_plan_2026_seguro(conn):
    """Amplía/ordena el plan sin borrar ni renumerar cuentas con historia."""
    # Asegura todas las cuentas nuevas del PLAN_BASE.
    instalar_plan_base(conn)
    # No renombrar cuentas existentes: la denominación histórica y las
    # personalizaciones del usuario son la fuente de verdad.
    # Las cuentas ausentes se agregan de forma aditiva mediante instalar_plan_base.
    # Cuenta transitoria separada de Gastos de personal.
    conn.execute("""
        INSERT OR IGNORE INTO plan_cuentas
        (codigo, nombre, categoria, tipo, padre_codigo, nivel)
        VALUES ('1.1.03.03', 'IVA de uso común por determinar',
                'Activo', 'Activo', '1.1.03', 4)
    """)
    # Migrar únicamente la asignación antigua y errónea; conservar roles personalizados.
    conn.execute("""
        UPDATE config_cuentas SET codigo='1.1.03.03'
        WHERE rol='iva_uso_comun' AND codigo='5.2.03'
    """)
    conn.commit()


def sgci_guardar_cuenta(conn, codigo, nombre, categoria, tipo, padre_codigo, nivel, *, crear=False):
    accion = 'crear' if crear else 'editar'
    sgci_autorizar_operacion(conn, 'contabilidad', accion, 'Plan de Cuentas')
    codigo, nombre = str(codigo or '').strip(), str(nombre or '').strip()
    padre_codigo = str(padre_codigo or '').strip() or None
    if not codigo or not nombre:
        raise ValueError('Debe indicar código y nombre de cuenta.')
    if categoria not in ('Activo','Pasivo','Patrimonio','Nominal') or tipo not in ('Activo','Pasivo','Patrimonio','Ingresos','Gastos'):
        raise ValueError('Categoría o tipo de cuenta inválido.')
    if isinstance(nivel,bool) or str(nivel) not in tuple(str(n) for n in range(1,11)):
        raise ValueError('El nivel debe ser un entero entre 1 y 10.')
    if conn.in_transaction:
        raise RuntimeError('Guarda o revierte la operación pendiente antes de modificar el plan.')
    with conn:
        conn.execute('BEGIN IMMEDIATE')
        sgci_autorizar_operacion(conn, 'contabilidad', accion, 'Plan de Cuentas')
        if not crear and not conn.execute('SELECT 1 FROM plan_cuentas WHERE codigo=?',(codigo,)).fetchone():
            raise ValueError('Cuenta no encontrada.')
        ancestro,visitados = padre_codigo,set()
        while ancestro:
            if ancestro == codigo or ancestro in visitados:
                raise ValueError('La cuenta padre generaría una jerarquía circular.')
            visitados.add(ancestro)
            fila=conn.execute('SELECT padre_codigo FROM plan_cuentas WHERE codigo=?',(ancestro,)).fetchone()
            if fila is None:
                raise ValueError('La cuenta padre no existe en el plan.')
            ancestro=fila[0]
        if crear:
            conn.execute('INSERT INTO plan_cuentas(codigo,nombre,categoria,tipo,padre_codigo,nivel) VALUES(?,?,?,?,?,?)',
                         (codigo,nombre,categoria,tipo,padre_codigo,int(nivel)))
        else:
            conn.execute('UPDATE plan_cuentas SET nombre=?,categoria=?,tipo=?,padre_codigo=?,nivel=? WHERE codigo=?',
                         (nombre,categoria,tipo,padre_codigo,int(nivel),codigo))
        conn.execute('INSERT INTO auditoria(fecha_hora,usuario,accion,detalle) VALUES(?,?,?,?)',
            (datetime.now().isoformat(timespec='seconds'),sgci_identidad_actual(),
             'CREAR CUENTA' if crear else 'EDITAR CUENTA',codigo))
    return codigo


def sgci_exportar_plan(conn):
    sgci_autorizar_operacion(conn, 'contabilidad', 'ver', 'Plan de Cuentas')
    sgci_autorizar_operacion(conn, 'contabilidad', 'exportar', 'Plan de Cuentas')
    df=pd.read_sql_query('SELECT codigo AS Código,nombre AS Cuenta,categoria AS Categoría,tipo AS Tipo,padre_codigo AS Padre,nivel AS Nivel FROM plan_cuentas ORDER BY codigo',conn)
    return pdf_desde_dataframe('Plan de Cuentas','CONTEM - Sistema Contable y Empresarial',df)


class Plan:

    def __init__(self, conn):

        self.df = pd.read_sql_query(
            """
            SELECT
                codigo,
                nombre,
                categoria,
                tipo,
                padre_codigo,
                nivel
            FROM plan_cuentas
            ORDER BY codigo
            """,
            conn
        )

        if self.df.empty:
            self.todos = {}
            self.hojas = {}
            self.por_nombre = {}
            return

        self.df["codigo"] = self.df["codigo"].astype(str)

        padres = set(
            self.df["padre_codigo"]
            .dropna()
            .astype(str)
        )

        self.df["imputable"] = ~self.df["codigo"].isin(padres)

        self.todos = dict(
            zip(
                self.df["codigo"],
                self.df["nombre"]
            )
        )

        hojas = self.df[
            self.df["imputable"]
        ]

        self.hojas = dict(
            zip(
                hojas["codigo"],
                hojas["nombre"]
            )
        )

        self.por_nombre = {
            str(nombre).strip().lower(): codigo
            for codigo, nombre in self.hojas.items()
        }

    def resolver(self, texto):

        if texto is None:
            return None

        t = str(texto).strip()

        if not t:
            return None

        if t in self.hojas:
            return t, self.hojas[t]

        if " - " in t:

            codigo = t.split(
                " - ",
                1
            )[0].strip()

            if codigo in self.hojas:
                return codigo, self.hojas[codigo]

        codigo = self.por_nombre.get(
            t.lower()
        )

        if codigo:
            return codigo, self.hojas[codigo]

        return None


def cuentas_imputables(conn):

    plan = Plan(conn)

    df = plan.df[
        plan.df["imputable"]
    ].copy()

    df["etiqueta"] = (
        df["codigo"]
        + " - "
        + df["nombre"]
    )

    return df.reset_index(drop=True)


# ============================================================
# ROLES
# ============================================================

def cargar_roles(conn):

    plan = Plan(conn)

    guardados = dict(
        conn.execute(
            """
            SELECT rol, codigo
            FROM config_cuentas
            """
        ).fetchall()
    )

    resultado = {}

    for rol, (_, defecto) in ROLES.items():

        codigo = guardados.get(
            rol,
            defecto
        )

        if codigo in plan.todos:
            resultado[rol] = (
                codigo,
                plan.todos[codigo]
            )
        else:
            resultado[rol] = None

    return resultado


def guardar_rol(conn, rol, codigo):
    sgci_autorizar_operacion(conn,'administracion','editar','Matriz Contable')

    if rol == "iva_uso_comun" and (
        codigo == "5.2.03" or str(codigo).startswith("5.2.03.")
    ):
        raise ValueError("El IVA de uso común no puede asignarse a Gastos de personal.")

    conn.execute(
        """
        INSERT OR REPLACE INTO config_cuentas
        (rol, codigo)
        VALUES (?, ?)
        """,
        (rol, codigo)
    )

    conn.commit()


# ============================================================
# RCV (Normalizador Adaptado a Compras y Ventas del SII)
# ============================================================

def normalizar_rcv(df, tipo):
    compras = tipo == "compras"
    cols_lower = {c.lower(): c for c in df.columns}

    def buscar_col(*posibles):
        for p in posibles:
            if p.lower() in cols_lower:
                return cols_lower[p.lower()]
        return None

    resultado = pd.DataFrame()

    if compras:
        rut_col = buscar_col("RUT Proveedor", "Rut Proveedor", "RUT", "Rut")
        tipo_doc_col = buscar_col("Tipo Doc", "Tipo", "Tipo Documento")
        folio_col = buscar_col("Folio", "Nro", "Nro.", "Número")
        fecha_doc_col = buscar_col("Fecha Docto", "Fecha Emision", "Fecha Emisión", "Fecha")
        fecha_rec_col = buscar_col("Fecha Recepcion", "Fecha Recepción")
        razon_col = buscar_col("Razon Social", "Razón Social", "Proveedor")
        exento_col = buscar_col("Monto Exento", "Exento")
        neto_col = buscar_col("Monto Neto", "Neto")
        iva_col = buscar_col("Monto IVA Recuperable", "IVA", "I.V.A.")
        total_col = buscar_col("Monto Total", "Total")
        
        iva_nr_col = buscar_col("Monto Iva No Recuperable", "Monto IVA No Recuperable")
        neto_af_col = buscar_col("Monto Neto Activo Fijo")
        iva_af_col = buscar_col("IVA Activo Fijo")
        iva_uc_col = buscar_col("IVA uso Comun", "IVA uso Común")
        
        ref_tipo_col = buscar_col("Tipo Docto. Referencia", "Tipo Doc Referencia")
        ref_folio_col = buscar_col("Folio Docto. Referencia", "Folio Referencia")

        if not tipo_doc_col or not folio_col:
            cols = df.columns
            resultado["tipo_doc"] = pd.to_numeric(df.iloc[:, 1], errors="coerce")
            resultado["folio"] = df.iloc[:, 5].fillna("").astype(str).str.strip()
            resultado["fecha_doc"] = serie_fecha(df.iloc[:, 6])
            resultado["fecha_recepcion"] = serie_fecha(df.iloc[:, 7])
            resultado["rut"] = df.iloc[:, 3].fillna("").astype(str).apply(normalizar_rut)
            resultado["razon_social"] = df.iloc[:, 4].fillna("").astype(str).str.strip()
            resultado["exento"] = serie_numero(df.iloc[:, 9]) if len(cols) > 9 else 0.0
            resultado["neto"] = serie_numero(df.iloc[:, 10]) if len(cols) > 10 else 0.0
            resultado["iva"] = serie_numero(df.iloc[:, 11]) if len(cols) > 11 else 0.0
            resultado["iva_no_rec"] = serie_numero(df.iloc[:, 12]) if len(cols) > 12 else 0.0
            resultado["neto_af"] = serie_numero(df.iloc[:, 15]) if len(cols) > 15 else 0.0
            resultado["iva_af"] = serie_numero(df.iloc[:, 16]) if len(cols) > 16 else 0.0
            resultado["iva_uso_comun"] = serie_numero(df.iloc[:, 17]) if len(cols) > 17 else 0.0
            resultado["total"] = serie_numero(df.iloc[:, 14]) if len(cols) > 14 else 0.0
            resultado["ref_type"] = None
            resultado["ref_folio"] = ""
        else:
            resultado["tipo_doc"] = pd.to_numeric(df[tipo_doc_col], errors="coerce")
            resultado["folio"] = df[folio_col].fillna("").astype(str).str.strip()
            resultado["fecha_doc"] = serie_fecha(df[fecha_doc_col])
            resultado["fecha_recepcion"] = serie_fecha(df[fecha_rec_col]) if fecha_rec_col else None
            resultado["rut"] = df[rut_col].fillna("").astype(str).apply(normalizar_rut)
            resultado["razon_social"] = df[razon_col].fillna("").astype(str).str.strip() if razon_col else ""
            resultado["exento"] = serie_numero(df[exento_col]) if exento_col else 0.0
            resultado["neto"] = serie_numero(df[neto_col]) if neto_col else 0.0
            resultado["iva"] = serie_numero(df[iva_col]) if iva_col else 0.0
            resultado["iva_no_rec"] = serie_numero(df[iva_nr_col]) if iva_nr_col else 0.0
            resultado["neto_af"] = serie_numero(df[neto_af_col]) if neto_af_col else 0.0
            resultado["iva_af"] = serie_numero(df[iva_af_col]) if iva_af_col else 0.0
            resultado["iva_uso_comun"] = serie_numero(df[iva_uc_col]) if iva_uc_col else 0.0
            resultado["total"] = serie_numero(df[total_col]) if total_col else 0.0
            resultado["ref_type"] = pd.to_numeric(df[ref_tipo_col], errors="coerce") if ref_tipo_col else None
            resultado["ref_folio"] = df[ref_folio_col].fillna("").astype(str).str.strip() if ref_folio_col else ""

    else:
        rut_col = buscar_col("Rut cliente", "RUT Cliente", "Rut Cliente", "RUT", "Rut")
        tipo_doc_col = buscar_col("Tipo Doc", "Tipo", "Tipo Documento")
        folio_col = buscar_col("Folio", "Nro", "Nro.", "Número")
        fecha_doc_col = buscar_col("Fecha Docto", "Fecha Emision", "Fecha Emisión", "Fecha")
        fecha_rec_col = buscar_col("Fecha Recepcion", "Fecha Recepción")
        razon_col = buscar_col("Razon Social", "Razón Social", "Cliente")
        exento_col = buscar_col("Monto Exento", "Exento")
        neto_col = buscar_col("Monto Neto", "Neto")
        iva_col = buscar_col("Monto IVA", "IVA", "I.V.A.")
        total_col = buscar_col("Monto total", "Monto Total", "Total")
        ref_tipo_col = buscar_col("Tipo Docto. Referencia", "Tipo Doc Referencia")
        ref_folio_col = buscar_col("Folio Docto. Referencia", "Folio Referencia")

        resultado["tipo_doc"] = pd.to_numeric(df[tipo_doc_col], errors="coerce") if tipo_doc_col else pd.to_numeric(df.iloc[:, 1], errors="coerce")
        resultado["folio"] = df[folio_col].fillna("").astype(str).str.strip() if folio_col else df.iloc[:, 5].fillna("").astype(str).str.strip()
        resultado["fecha_doc"] = serie_fecha(df[fecha_doc_col]) if fecha_doc_col else serie_fecha(df.iloc[:, 6])
        resultado["fecha_recepcion"] = serie_fecha(df[fecha_rec_col]) if fecha_rec_col else None
        resultado["rut"] = df[rut_col].fillna("").astype(str).apply(normalizar_rut) if rut_col else df.iloc[:, 3].fillna("").astype(str).apply(normalizar_rut)
        resultado["razon_social"] = df[razon_col].fillna("").astype(str).str.strip() if razon_col else df.iloc[:, 4].fillna("").astype(str).str.strip()
        resultado["exento"] = serie_numero(df[exento_col]) if exento_col else 0.0
        resultado["neto"] = serie_numero(df[neto_col]) if neto_col else 0.0
        resultado["iva"] = serie_numero(df[iva_col]) if iva_col else 0.0
        resultado["iva_no_rec"] = 0.0
        resultado["neto_af"] = 0.0
        resultado["iva_af"] = 0.0
        resultado["iva_uso_comun"] = 0.0
        resultado["total"] = serie_numero(df[total_col]) if total_col else 0.0
        resultado["ref_type"] = pd.to_numeric(df[ref_tipo_col], errors="coerce") if ref_tipo_col else None
        resultado["ref_folio"] = df[ref_folio_col].fillna("").astype(str).str.strip() if ref_folio_col else ""

    resultado = resultado[resultado["tipo_doc"].notna()].copy()
    resultado["tipo_doc"] = resultado["tipo_doc"].astype(int)

    if resultado.empty:
        raise ValueError("No se encontraron documentos válidos.")

    return resultado.reset_index(drop=True)


    with pestañas[3]:
        st.subheader("Editar cuenta existente")
        st.caption("Permite corregir nombre, clasificación, cuenta padre y nivel sin cambiar el código contable ni los movimientos históricos.")

        cuentas_editar = pd.read_sql_query(
            """SELECT codigo,nombre,categoria,tipo,padre_codigo,nivel
               FROM plan_cuentas ORDER BY codigo""", conn
        )

        if cuentas_editar.empty:
            st.info("No hay cuentas disponibles para editar.")
        else:
            etiquetas_editar = [f"{r.codigo} - {r.nombre}" for r in cuentas_editar.itertuples()]
            cuenta_sel = st.selectbox("Cuenta a editar", etiquetas_editar, key="editar_plan_cuenta")
            codigo_sel = cuenta_sel.split(" - ", 1)[0]
            fila = cuentas_editar.loc[cuentas_editar["codigo"] == codigo_sel].iloc[0]

            # La cuenta seleccionada no puede ser su propio padre ni tener como padre una cuenta hija.
            codigos_descendientes = set()
            frontera = {codigo_sel}
            while frontera:
                hijos = set(cuentas_editar.loc[cuentas_editar["padre_codigo"].isin(frontera), "codigo"].astype(str))
                hijos -= codigos_descendientes
                if not hijos:
                    break
                codigos_descendientes.update(hijos)
                frontera = hijos

            padres_validos = cuentas_editar[
                ~cuentas_editar["codigo"].astype(str).isin({codigo_sel} | codigos_descendientes)
            ].copy()
            opciones_padre = ["— Sin cuenta padre —"] + [
                f"{r.codigo} - {r.nombre}" for r in padres_validos.itertuples()
            ]

            padre_actual = str(fila["padre_codigo"]) if pd.notna(fila["padre_codigo"]) else ""
            indice_padre = 0
            if padre_actual:
                for i, etiqueta in enumerate(opciones_padre):
                    if etiqueta.startswith(padre_actual + " - "):
                        indice_padre = i
                        break

            categorias = ["Activo", "Pasivo", "Patrimonio", "Nominal"]
            tipos = ["Activo", "Pasivo", "Patrimonio", "Ingresos", "Gastos"]
            categoria_actual = str(fila["categoria"]) if pd.notna(fila["categoria"]) else "Activo"
            tipo_actual = str(fila["tipo"]) if pd.notna(fila["tipo"]) else "Activo"

            with st.form("editar_cuenta_existente"):
                st.text_input("Código", value=codigo_sel, disabled=True, help="El código se mantiene bloqueado para proteger los movimientos históricos.")
                nombre_edit = st.text_input("Nombre", value=str(fila["nombre"] or ""))
                categoria_edit = st.selectbox(
                    "Categoría", categorias,
                    index=categorias.index(categoria_actual) if categoria_actual in categorias else 0
                )
                tipo_edit = st.selectbox(
                    "Tipo", tipos,
                    index=tipos.index(tipo_actual) if tipo_actual in tipos else 0
                )
                padre_edit = st.selectbox("Cuenta padre", opciones_padre, index=indice_padre)
                nivel_edit = st.number_input(
                    "Nivel", min_value=1, max_value=10, value=int(fila["nivel"] or 1), step=1
                )
                confirmar_edit = st.checkbox("Confirmo que deseo actualizar la estructura de esta cuenta.")

                if st.form_submit_button("Guardar cambios", type="primary", disabled=not confirmar_edit):
                    try:
                        nuevo_padre = None if padre_edit.startswith("—") else padre_edit.split(" - ", 1)[0]
                        if nuevo_padre:
                            padre_row = cuentas_editar.loc[cuentas_editar["codigo"] == nuevo_padre]
                            if padre_row.empty:
                                raise ValueError("La cuenta padre seleccionada no existe.")
                            nivel_padre = int(padre_row.iloc[0]["nivel"] or 0)
                            if int(nivel_edit) <= nivel_padre:
                                raise ValueError(f"El nivel de la cuenta debe ser mayor que el nivel de su padre ({nivel_padre}).")

                        conn.execute(
                            """UPDATE plan_cuentas
                               SET nombre=?, categoria=?, tipo=?, padre_codigo=?, nivel=?
                               WHERE codigo=?""",
                            (nombre_edit.strip(), categoria_edit, tipo_edit, nuevo_padre, int(nivel_edit), codigo_sel)
                        )
                        conn.commit()
                        registrar_auditoria(
                            conn, "EDITAR PLAN DE CUENTAS",
                            f"Cuenta {codigo_sel}: padre {padre_actual or 'SIN PADRE'} -> {nuevo_padre or 'SIN PADRE'}, nivel {int(fila['nivel'] or 1)} -> {int(nivel_edit)}"
                        )
                        sgci_exito(f"Cuenta {codigo_sel} actualizada correctamente.")
                        st.rerun()
                    except Exception as e:
                        conn.rollback()
                        st.error(f"No se pudo actualizar la cuenta: {e}")


# ============================================================
# REGLAS CONTABLES
# ============================================================


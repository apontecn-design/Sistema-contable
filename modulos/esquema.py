# CONTEM: componente extraído del app.py original; ejecución secuencial compartida.
def tabla_existe(conn, tabla):
    return conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type='table'
        AND name=?
        """,
        (tabla,)
    ).fetchone() is not None


def columnas_tabla(conn, tabla):
    if not tabla_existe(conn, tabla):
        return []

    return [
        fila[1]
        for fila in conn.execute(
            f"PRAGMA table_info({tabla})"
        ).fetchall()
    ]


def agregar_columna(conn, tabla, columna_nombre, tipo):
    if columna_nombre not in columnas_tabla(conn, tabla):
        conn.execute(
            f"""
            ALTER TABLE {tabla}
            ADD COLUMN {columna_nombre} {tipo}
            """
        )


def crear_esquema(conn):

    conn.execute("""
        CREATE TABLE IF NOT EXISTS empresa (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rut TEXT,
            razon_social TEXT,
            giro TEXT,
            direccion TEXT,
            comuna TEXT,
            ciudad TEXT,
            fecha_creacion TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS plan_cuentas (
            codigo TEXT PRIMARY KEY,
            nombre TEXT NOT NULL,
            categoria TEXT,
            tipo TEXT,
            padre_codigo TEXT,
            nivel INTEGER DEFAULT 1
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rut TEXT UNIQUE,
            nombre TEXT,
            razon_social TEXT,
            email TEXT,
            telefono TEXT,
            direccion TEXT,
            comuna TEXT,
            ciudad TEXT,
            cuenta_defecto TEXT,
            activo INTEGER DEFAULT 1,
            fecha_creacion TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS proveedores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rut TEXT UNIQUE,
            nombre TEXT,
            razon_social TEXT,
            email TEXT,
            telefono TEXT,
            direccion TEXT,
            comuna TEXT,
            ciudad TEXT,
            cuenta_defecto TEXT,
            centro_costo TEXT,
            activo INTEGER DEFAULT 1,
            fecha_creacion TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS compras (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            proveedor_id INTEGER,
            cuenta_gasto TEXT,
            centro_costo TEXT,
            monto_neto REAL DEFAULT 0,
            iva REAL DEFAULT 0,
            monto_total REAL DEFAULT 0,
            glosa TEXT,
            tipo_doc INTEGER,
            folio TEXT,
            lote_id TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS ventas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            cliente_id INTEGER,
            cuenta_ingreso TEXT,
            monto_neto REAL DEFAULT 0,
            iva REAL DEFAULT 0,
            monto_total REAL DEFAULT 0,
            glosa TEXT,
            tipo_doc INTEGER,
            folio TEXT,
            lote_id TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS libro_diario (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            cuenta TEXT,
            debe REAL DEFAULT 0,
            haber REAL DEFAULT 0,
            glosa TEXT,
            centro_costo TEXT,
            codigo_cuenta TEXT,
            asiento_id INTEGER,
            lote_id TEXT,
            origen TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS pagos_clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            cliente_id INTEGER,
            monto REAL DEFAULT 0,
            medio_pago TEXT,
            cuenta_banco TEXT,
            glosa TEXT,
            lote_id TEXT
        )
    """)

    # Trazabilidad de anticipos de clientes: separa lo recibido de lo ya aplicado a CxC.
    agregar_columna(conn, "pagos_clientes", "monto_recibido", "REAL DEFAULT 0")
    agregar_columna(conn, "pagos_clientes", "cuenta_anticipo", "TEXT")
    agregar_columna(conn, "pagos_clientes", "cartola_id", "INTEGER")
    agregar_columna(conn, "pagos_clientes", "asiento_origen_id", "INTEGER")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS pagos_proveedores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            proveedor_id INTEGER,
            monto REAL DEFAULT 0,
            medio_pago TEXT,
            cuenta_banco TEXT,
            glosa TEXT,
            lote_id TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS aplicaciones_clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pago_id INTEGER,
            venta_id INTEGER,
            monto REAL DEFAULT 0
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS aplicaciones_proveedores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pago_id INTEGER,
            compra_id INTEGER,
            monto REAL DEFAULT 0
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS reglas_contables (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo TEXT NOT NULL,
            rut TEXT,
            patron TEXT,
            tipo_doc INTEGER,
            codigo_cuenta TEXT NOT NULL,
            prioridad INTEGER DEFAULT 100,
            activa INTEGER DEFAULT 1,
            descripcion TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS config_cuentas (
            rol TEXT PRIMARY KEY,
            codigo TEXT
        )
    """)

    for rol, (_, codigo) in ROLES.items():
        conn.execute(
            """
            INSERT OR IGNORE INTO config_cuentas
            (rol, codigo)
            VALUES (?, ?)
            """,
            (rol, codigo)
        )


    conn.execute("""
        CREATE TABLE IF NOT EXISTS bancos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            numero_cuenta TEXT,
            tipo TEXT,
            moneda TEXT DEFAULT 'CLP',
            cuenta_contable TEXT,
            saldo_inicial REAL DEFAULT 0,
            activo INTEGER DEFAULT 1
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS cartola_bancaria (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            banco_id INTEGER,
            fecha TEXT,
            descripcion TEXT,
            referencia TEXT,
            cargo REAL DEFAULT 0,
            abono REAL DEFAULT 0,
            saldo REAL,
            conciliado INTEGER DEFAULT 0,
            observacion TEXT,
            lote_id TEXT,
            UNIQUE(banco_id, fecha, descripcion, cargo, abono, referencia)
        )
    """)

    # Obligaciones/operaciones manuales para conciliación bancaria
    conn.execute("""
        CREATE TABLE IF NOT EXISTS obligaciones_manuales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            tipo TEXT DEFAULT 'PAGO',
            descripcion TEXT NOT NULL,
            referencia TEXT,
            monto REAL DEFAULT 0,
            codigo_cuenta TEXT,
            conciliado INTEGER DEFAULT 0,
            fecha_conciliacion TEXT,
            cartola_id INTEGER,
            asiento_id INTEGER
        )
    """)

    # Nuevos campos de trazabilidad para movimientos bancarios.
    agregar_columna(conn, "cartola_bancaria", "origen", "TEXT DEFAULT 'CARTOLA'")
    agregar_columna(conn, "cartola_bancaria", "asiento_id", "INTEGER")
    agregar_columna(conn, "cartola_bancaria", "match_tipo", "TEXT")
    agregar_columna(conn, "cartola_bancaria", "match_id", "INTEGER")
    agregar_columna(conn, "cartola_bancaria", "match_confianza", "REAL")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS periodos_contables (
            periodo TEXT PRIMARY KEY,
            estado TEXT DEFAULT 'ABIERTO',
            fecha_cierre TEXT,
            observacion TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS auditoria (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha_hora TEXT,
            usuario TEXT,
            accion TEXT,
            detalle TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS activos_fijos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT UNIQUE,
            descripcion TEXT,
            fecha_compra TEXT,
            valor REAL DEFAULT 0,
            vida_util_meses INTEGER DEFAULT 1,
            valor_residual REAL DEFAULT 0,
            cuenta_activo TEXT,
            cuenta_depreciacion TEXT,
            cuenta_gasto TEXT,
            activo INTEGER DEFAULT 1
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS inventario (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT UNIQUE,
            descripcion TEXT,
            unidad TEXT,
            stock REAL DEFAULT 0,
            costo_unitario REAL DEFAULT 0,
            cuenta_inventario TEXT,
            cuenta_costo_venta TEXT,
            activo INTEGER DEFAULT 1
        )
    """)

    # ========================================================
    # MÓDULO NÓMINA - tablas independientes del núcleo contable
    # ========================================================
    conn.execute("""
        CREATE TABLE IF NOT EXISTS nomina_trabajadores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rut TEXT UNIQUE NOT NULL,
            nombre TEXT NOT NULL,
            fecha_ingreso TEXT,
            cargo TEXT,
            tipo_contrato TEXT DEFAULT 'Indefinido',
            sueldo_base REAL DEFAULT 0,
            gratificacion_tipo TEXT DEFAULT 'Monto mensual',
            gratificacion_valor REAL DEFAULT 0,
            afp TEXT DEFAULT 'Uno',
            salud_tipo TEXT DEFAULT 'Fonasa',
            isapre TEXT,
            salud_modalidad TEXT DEFAULT '7% legal',
            salud_valor REAL DEFAULT 7,
            afc INTEGER DEFAULT 1,
            anticipo_quincenal INTEGER DEFAULT 1,
            anticipo_porcentaje REAL DEFAULT 50,
            banco TEXT,
            tipo_cuenta TEXT,
            numero_cuenta TEXT,
            activo INTEGER DEFAULT 1,
            fecha_creacion TEXT
        )
    """)

    # Recursos Humanos: extensiones independientes; no alteran asientos ni liquidaciones.
    conn.execute("""CREATE TABLE IF NOT EXISTS rrhh_documentos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        trabajador_id INTEGER NOT NULL,
        tipo TEXT NOT NULL,
        nombre_archivo TEXT NOT NULL,
        fecha_documento TEXT,
        observacion TEXT,
        contenido BLOB NOT NULL,
        sha256 TEXT NOT NULL,
        creado_en TEXT NOT NULL,
        activo INTEGER NOT NULL DEFAULT 1,
        FOREIGN KEY(trabajador_id) REFERENCES nomina_trabajadores(id)
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS rrhh_vacaciones_movimientos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        trabajador_id INTEGER NOT NULL,
        fecha TEXT NOT NULL,
        tipo TEXT NOT NULL CHECK(tipo IN ('ASIGNACION','DESCUENTO','AJUSTE')),
        dias REAL NOT NULL CHECK(dias > 0),
        observacion TEXT,
        creado_en TEXT NOT NULL,
        FOREIGN KEY(trabajador_id) REFERENCES nomina_trabajadores(id)
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS rrhh_vacaciones_solicitudes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        trabajador_id INTEGER NOT NULL,
        fecha_solicitud TEXT NOT NULL,
        desde TEXT NOT NULL,
        hasta TEXT NOT NULL,
        dias_solicitados REAL NOT NULL CHECK(dias_solicitados > 0),
        estado TEXT NOT NULL DEFAULT 'PENDIENTE',
        observacion TEXT,
        revisado_por TEXT,
        fecha_revision TEXT,
        observacion_revision TEXT,
        creado_en TEXT NOT NULL,
        FOREIGN KEY(trabajador_id) REFERENCES nomina_trabajadores(id)
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_rrhh_doc_trab ON rrhh_documentos(trabajador_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_rrhh_vac_trab ON rrhh_vacaciones_movimientos(trabajador_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_rrhh_sol_trab ON rrhh_vacaciones_solicitudes(trabajador_id)")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS nomina_parametros_afp (
            afp TEXT PRIMARY KEY,
            comision REAL NOT NULL,
            vigente_desde TEXT,
            activo INTEGER DEFAULT 1
        )
    """)
    for _afp, _comision in {
        'Capital':1.44, 'Cuprum':1.44, 'Habitat':1.27, 'Modelo':0.58,
        'PlanVital':1.16, 'Provida':1.45, 'Uno':0.46
    }.items():
        conn.execute("INSERT OR IGNORE INTO nomina_parametros_afp(afp,comision,vigente_desde) VALUES(?,?,?)", (_afp,_comision,'2025-10-01'))

    conn.execute("""
        CREATE TABLE IF NOT EXISTS nomina_historial_condiciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trabajador_id INTEGER NOT NULL,
            vigente_desde TEXT NOT NULL,
            sueldo_base REAL DEFAULT 0,
            gratificacion_tipo TEXT,
            gratificacion_valor REAL DEFAULT 0,
            afp TEXT,
            salud_tipo TEXT,
            isapre TEXT,
            salud_modalidad TEXT,
            salud_valor REAL DEFAULT 0,
            observacion TEXT,
            fecha_registro TEXT,
            UNIQUE(trabajador_id, vigente_desde)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS nomina_parametros_mensuales (
            periodo TEXT PRIMARY KEY,
            valor_uf REAL DEFAULT 0,
            observacion TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS nomina_periodos (
            periodo TEXT PRIMARY KEY,
            estado TEXT DEFAULT 'BORRADOR',
            fecha_cierre TEXT,
            asiento_id INTEGER,
            observacion TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS nomina_anticipos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trabajador_id INTEGER NOT NULL,
            periodo TEXT NOT NULL,
            fecha TEXT,
            monto REAL DEFAULT 0,
            observacion TEXT,
            asiento_id INTEGER,
            contabilizado INTEGER DEFAULT 0
        )
    """)
    # Anulación lógica: conserva el registro y evita descontarlo de nómina.
    agregar_columna(conn, "nomina_anticipos", "anulado", "INTEGER DEFAULT 0")
    agregar_columna(conn, "nomina_anticipos", "asiento_reverso_id", "INTEGER")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS nomina_prestamos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trabajador_id INTEGER NOT NULL,
            fecha TEXT,
            monto_original REAL DEFAULT 0,
            numero_cuotas INTEGER DEFAULT 1,
            cuota REAL DEFAULT 0,
            primera_cuota TEXT,
            saldo REAL DEFAULT 0,
            estado TEXT DEFAULT 'VIGENTE',
            observacion TEXT,
            asiento_id INTEGER,
            contabilizado INTEGER DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS nomina_prestamo_cuotas_programadas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prestamo_id INTEGER NOT NULL,
            fecha TEXT NOT NULL,
            monto REAL NOT NULL,
            UNIQUE(prestamo_id,fecha)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS nomina_liquidaciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            periodo TEXT NOT NULL,
            trabajador_id INTEGER NOT NULL,
            dias_trabajados REAL DEFAULT 30,
            sueldo_base REAL DEFAULT 0,
            sueldo_periodo REAL DEFAULT 0,
            gratificacion REAL DEFAULT 0,
            horas_extras REAL DEFAULT 0,
            bonos_imponibles REAL DEFAULT 0,
            otros_imponibles REAL DEFAULT 0,
            asignacion_no_imponible REAL DEFAULT 0,
            otros_no_imponibles REAL DEFAULT 0,
            total_imponible REAL DEFAULT 0,
            total_no_imponible REAL DEFAULT 0,
            total_haberes REAL DEFAULT 0,
            afp_nombre TEXT,
            afp_comision REAL DEFAULT 0,
            afp_descuento REAL DEFAULT 0,
            salud_tipo TEXT,
            salud_modalidad TEXT,
            salud_valor REAL DEFAULT 0,
            salud_descuento REAL DEFAULT 0,
            afc_descuento REAL DEFAULT 0,
            impuesto_unico REAL DEFAULT 0,
            prestamo_descuento REAL DEFAULT 0,
            otros_descuentos REAL DEFAULT 0,
            total_descuentos REAL DEFAULT 0,
            liquido_periodo REAL DEFAULT 0,
            anticipo REAL DEFAULT 0,
            saldo_pagar REAL DEFAULT 0,
            estado TEXT DEFAULT 'BORRADOR',
            observacion TEXT,
            UNIQUE(periodo, trabajador_id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS nomina_cuotas_prestamo (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prestamo_id INTEGER NOT NULL,
            liquidacion_id INTEGER,
            periodo TEXT NOT NULL,
            monto REAL DEFAULT 0,
            aplicado INTEGER DEFAULT 0,
            UNIQUE(prestamo_id, periodo)
        )
    """)

    for _col, _tipo in [("uf_valor","REAL DEFAULT 0"),("salud_plan_pesos","REAL DEFAULT 0"),("bono_no_imponible","REAL DEFAULT 0")]:
        agregar_columna(conn, "nomina_liquidaciones", _col, _tipo)

    migraciones = {
        "clientes": [
            ("razon_social", "TEXT"),
            ("email", "TEXT"),
            ("telefono", "TEXT"),
            ("direccion", "TEXT"),
            ("comuna", "TEXT"),
            ("ciudad", "TEXT"),
            ("cuenta_defecto", "TEXT"),
            ("activo", "INTEGER DEFAULT 1"),
            ("fecha_creacion", "TEXT"),
        ],
        "proveedores": [
            ("razon_social", "TEXT"),
            ("email", "TEXT"),
            ("telefono", "TEXT"),
            ("comuna", "TEXT"),
            ("ciudad", "TEXT"),
            ("cuenta_defecto", "TEXT"),
            ("centro_costo", "TEXT"),
            ("activo", "INTEGER DEFAULT 1"),
            ("fecha_creacion", "TEXT"),
        ],
        "compras": [
            ("tipo_doc", "INTEGER"),
            ("folio", "TEXT"),
            ("lote_id", "TEXT"),
        ],
        "ventas": [
            ("tipo_doc", "INTEGER"),
            ("folio", "TEXT"),
            ("lote_id", "TEXT"),
        ],
        "libro_diario": [
            ("codigo_cuenta", "TEXT"),
            ("asiento_id", "INTEGER"),
            ("lote_id", "TEXT"),
            ("origen", "TEXT"),
        ],
    }

    for tabla, cols in migraciones.items():
        for nombre, tipo in cols:
            agregar_columna(
                conn,
                tabla,
                nombre,
                tipo
            )

    # Trazabilidad y protección contra archivos duplicados.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS importaciones_archivos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            modulo TEXT NOT NULL,
            nombre_archivo TEXT NOT NULL,
            archivo_hash TEXT NOT NULL,
            lote_id TEXT,
            fecha_hora TEXT NOT NULL,
            registros_leidos INTEGER DEFAULT 0,
            registros_nuevos INTEGER DEFAULT 0,
            registros_duplicados INTEGER DEFAULT 0,
            UNIQUE(modulo, archivo_hash)
        )
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_compras_proveedor
        ON compras(proveedor_id)
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_compras_fecha
        ON compras(fecha)
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_ventas_cliente
        ON ventas(cliente_id)
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_ventas_fecha
        ON ventas(fecha)
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_diario_fecha
        ON libro_diario(fecha)
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_diario_codigo
        ON libro_diario(codigo_cuenta)
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_diario_asiento
        ON libro_diario(asiento_id)
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_reglas_rut
        ON reglas_contables(rut)
    """)

    try:
        conn.execute("DROP INDEX IF EXISTS ux_ventas_doc")
        conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS
            ux_ventas_doc
            ON ventas(cliente_id, tipo_doc, folio)
            WHERE cliente_id IS NOT NULL AND tipo_doc IS NOT NULL AND folio IS NOT NULL
        """)
    except Exception:
        pass

    try:
        conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS
            ux_compras_doc
            ON compras(proveedor_id, tipo_doc, folio)
            WHERE tipo_doc IS NOT NULL
            AND folio IS NOT NULL
        """)
    except Exception:
        pass

    conn.commit()


# ============================================================
# PLAN DE CUENTAS
# ============================================================


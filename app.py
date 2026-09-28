import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime

st.set_page_config(page_title="Sistema Contable Web", page_icon="💼", layout="wide")

DB_FILE = "sistema_contable.db"

def get_connection():
    return sqlite3.connect(DB_FILE)

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # 1. Tablas Operativas Básicas
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS proveedores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        rut TEXT,
        nombre TEXT
    )""")
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS compras (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fecha TEXT,
        proveedor_id INTEGER,
        cuenta_gasto TEXT,
        monto_neto REAL,
        iva REAL,
        monto_total REAL,
        glosa TEXT
    )""")
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pagos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fecha TEXT,
        proveedor_id INTEGER,
        monto REAL
    )""")
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS clientes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        rut TEXT,
        nombre TEXT
    )""")
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ventas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fecha TEXT,
        cliente_id INTEGER,
        cuenta_ingreso TEXT,
        monto_neto REAL,
        iva REAL,
        monto_total REAL,
        glosa TEXT
    )""")
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS cobros (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fecha TEXT,
        cliente_id INTEGER,
        monto REAL
    )""")
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS libro_diario (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fecha TEXT,
        cuenta TEXT,
        debe REAL,
        haber REAL,
        glosa TEXT
    )""")
    
    # 2. Recreación/Migración Segura de Plan de Cuentas
    cursor.execute("PRAGMA table_info(plan_cuentas)")
    columnas_pc = [info[1] for info in cursor.fetchall()]
    
    # Si la tabla plan_cuentas no existe o tiene la estructura antigua, la actualizamos
    if not columnas_pc or "categoria" not in columnas_pc:
        cursor.execute("DROP TABLE IF EXISTS plan_cuentas")
        cursor.execute("""
        CREATE TABLE plan_cuentas (
            codigo TEXT PRIMARY KEY,
            nombre TEXT,
            categoria TEXT, -- 'Real' o 'Nominal'
            tipo TEXT,      -- 'Activo', 'Pasivo', 'Patrimonio', 'Ingresos', 'Gastos'
            padre_codigo TEXT,
            nivel INTEGER   -- 1: Clase, 2: Cuenta Principal, 3: Subcuenta
        )""")
        
        cat_inicial = [
            # CUENTAS REALES (BALANCE GENERAL)
            ("1", "ACTIVO", "Real", "Activo", None, 1),
            ("1.1", "Activo Corriente", "Real", "Activo", "1", 2),
            ("1.1.01", "Efectivo y Equivalentes", "Real", "Activo", "1.1", 2),
            ("1.1.01.01", "Banco", "Real", "Activo", "1.1.01", 3),
            ("1.1.01.02", "Caja General", "Real", "Activo", "1.1.01", 3),
            ("1.1.02", "Cuentas y Documentos por Cobrar", "Real", "Activo", "1.1", 2),
            ("1.1.02.01", "Cuentas por Cobrar Clientes", "Real", "Activo", "1.1.02", 3),
            ("1.1.02.02", "IVA Crédito Fiscal", "Real", "Activo", "1.1.02", 3),
            ("1.2", "Activo No Corriente", "Real", "Activo", "1", 2),
            ("1.2.01", "Propiedad, Planta y Equipo", "Real", "Activo", "1.2", 2),
            ("1.2.01.01", "Equipos de Computación", "Real", "Activo", "1.2.01", 3),
            ("1.2.01.02", "Muebles y Enseres", "Real", "Activo", "1.2.01", 3),
            
            ("2", "PASIVO", "Real", "Pasivo", None, 1),
            ("2.1", "Pasivo Corriente", "Real", "Pasivo", "2", 2),
            ("2.1.01", "Cuentas por Pagar Comerciales", "Real", "Pasivo", "2.1", 2),
            ("2.1.01.01", "Cuentas por Pagar Proveedores", "Real", "Pasivo", "2.1.01", 3),
            ("2.1.01.02", "IVA Débito Fiscal", "Real", "Pasivo", "2.1.01", 3),
            ("2.1.01.03", "Retenciones e Impuestos por Pagar", "Real", "Pasivo", "2.1.01", 3),
            
            ("3", "PATRIMONIO", "Real", "Patrimonio", None, 1),
            ("3.1", "Patrimonio Neto", "Real", "Patrimonio", "3", 2),
            ("3.1.01", "Capital Social", "Real", "Patrimonio", "3.1", 3),
            ("3.1.02", "Resultados Acumulados", "Real", "Patrimonio", "3.1", 3),
            
            # CUENTAS NOMINALES (ESTADO DE RESULTADOS)
            ("4", "INGRESOS", "Nominal", "Ingresos", None, 1),
            ("4.1", "Ingresos Operacionales", "Nominal", "Ingresos", "4", 2),
            ("4.1.01", "Ingresos por Ventas", "Nominal", "Ingresos", "4.1", 3),
            ("4.1.02", "Ingresos por Servicios", "Nominal", "Ingresos", "4.1", 3),
            ("4.2", "Ingresos No Operacionales", "Nominal", "Ingresos", "4", 2),
            ("4.2.01", "Otros Ingresos", "Nominal", "Ingresos", "4.2", 3),
            
            ("5", "GASTOS Y COSTOS", "Nominal", "Gastos", None, 1),
            ("5.1", "Costos de Operación / Ventas", "Nominal", "Gastos", "5", 2),
            ("5.1.01", "Costo de Ventas", "Nominal", "Gastos", "5.1", 3),
            ("5.2", "Gastos Operacionales", "Nominal", "Gastos", "5", 2),
            ("5.2.01", "Gastos Generales", "Nominal", "Gastos", "5.2", 3),
            ("5.2.02", "Gastos de Arriendo", "Nominal", "Gastos", "5.2", 3),
            ("5.2.03", "Gastos de Servicios Básicos", "Nominal", "Gastos", "5.2", 3),
            ("5.2.04", "Remuneraciones y Sueldos", "Nominal", "Gastos", "5.2", 3),
            ("5.2.05", "Gastos de Publicidad y Marketing", "Nominal", "Gastos", "5.2", 3)
        ]
        cursor.executemany("""
            INSERT INTO plan_cuentas (codigo, nombre, categoria, tipo, padre_codigo, nivel) 
            VALUES (?, ?, ?, ?, ?, ?)
        """, cat_inicial)

    # 3. Verificación de columnas en Compras y Ventas
    def agregar_columna_si_no_existe(tabla, columna, tipo_dato):
        cursor.execute(f"PRAGMA table_info({tabla})")
        columnas = [info[1] for info in cursor.fetchall()]
        if columna not in columnas:
            cursor.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {tipo_dato}")

    agregar_columna_si_no_existe("compras", "cuenta_gasto", "TEXT")
    agregar_columna_si_no_existe("compras", "monto_neto", "REAL")
    agregar_columna_si_no_existe("compras", "iva", "REAL")
    agregar_columna_si_no_existe("compras", "monto_total", "REAL")

    agregar_columna_si_no_existe("ventas", "cuenta_ingreso", "TEXT")
    agregar_columna_si_no_existe("ventas", "monto_neto", "REAL")
    agregar_columna_si_no_existe("ventas", "iva", "REAL")
    agregar_columna_si_no_existe("ventas", "monto_total", "REAL")

    conn.commit()
    conn.close()

init_db()

st.sidebar.title("📌 Menú Principal")
opcion = st.sidebar.radio(
    "Selecciona un Módulo:",
    [
        "Inicio / Resumen",
        "📋 Plan de Cuentas",
        "✏️ Registrar Asiento Manual",
        "Registrar Compra Proveedor",
        "Registrar Pago Proveedor",
        "Registrar Venta Cliente",
        "Registrar Cobro Cliente",
        "Cartola Bancaria y Saldos",
        "Libro Diario (Contabilidad)",
        "📊 Reportes Financieros"
    ]
)

conn = get_connection()

def obtener_subcuentas(tipo_filtro=None):
    if tipo_filtro:
        query = "SELECT nombre FROM plan_cuentas WHERE nivel = 3 AND tipo = ? ORDER BY codigo"
        df = pd.read_sql_query(query, conn, params=(tipo_filtro,))
    else:
        query = "SELECT nombre FROM plan_cuentas WHERE nivel = 3 ORDER BY codigo"
        df = pd.read_sql_query(query, conn)
    return df['nombre'].tolist() if not df.empty else []


if opcion == "Inicio / Resumen":
    st.title("💼 Sistema Contable Web")
    st.subheader("Bienvenido a tu Sistema Contable Integrado")
    st.info("Utiliza el menú lateral para acceder al Plan de Cuentas, Asientos Manuales, Compras, Ventas, Banco, Libro Diario y Reportes.")

elif opcion == "📋 Plan de Cuentas":
    st.header("📋 Plan de Cuentas (Cuentas Reales y Nominales)")
    
    tab_reales, tab_nominales, tab_crear = st.tabs([
        "🏛️ Cuentas Reales (Balance)", 
        "📈 Cuentas Nominales (Resultados)", 
        "➕ Crear Nueva Cuenta / Subcuenta"
    ])
    
    with tab_reales:
        st.subheader("Cuentas Reales (Activo, Pasivo, Patrimonio)")
        df_reales = pd.read_sql_query("""
            SELECT codigo as 'Código', nombre as 'Nombre de Cuenta / Subcuenta', 
                   tipo as 'Tipo', nivel as 'Nivel'
            FROM plan_cuentas 
            WHERE categoria = 'Real' 
            ORDER BY codigo
        """, conn)
        
        df_reales['Nombre de Cuenta / Subcuenta'] = df_reales.apply(
            lambda r: ("  " * (r['Nivel'] - 1) + "• " if r['Nivel'] > 1 else "") + r['Nombre de Cuenta / Subcuenta'], axis=1
        )
        st.dataframe(df_reales[['Código', 'Nombre de Cuenta / Subcuenta', 'Tipo']], use_container_width=True)

    with tab_nominales:
        st.subheader("Cuentas Nominales (Ingresos, Gastos y Costos)")
        df_nom = pd.read_sql_query("""
            SELECT codigo as 'Código', nombre as 'Nombre de Cuenta / Subcuenta', 
                   tipo as 'Tipo', nivel as 'Nivel'
            FROM plan_cuentas 
            WHERE categoria = 'Nominal' 
            ORDER BY codigo
        """, conn)
        
        df_nom['Nombre de Cuenta / Subcuenta'] = df_nom.apply(
            lambda r: ("  " * (r['Nivel'] - 1) + "• " if r['Nivel'] > 1 else "") + r['Nombre de Cuenta / Subcuenta'], axis=1
        )
        st.dataframe(df_nom[['Código', 'Nombre de Cuenta / Subcuenta', 'Tipo']], use_container_width=True)

    with tab_crear:
        st.subheader("Añadir Nueva Cuenta o Subcuenta al Catálogo")
        
        df_padres = pd.read_sql_query("SELECT codigo, nombre, categoria, tipo, nivel FROM plan_cuentas WHERE nivel < 3 ORDER BY codigo", conn)
        
        with st.form("form_nueva_subcuenta"):
            col1, col2 = st.columns(2)
            with col1:
                padre_sel = st.selectbox(
                    "Selecciona Cuenta Padre / Principal", 
                    options=df_padres['codigo'] + " - " + df_padres['nombre']
                )
                cod_padre = padre_sel.split(" - ")[0]
                row_padre = df_padres[df_padres['codigo'] == cod_padre].iloc[0]
                
                nuevo_codigo = st.text_input("Código para Nueva Subcuenta (Ej: 5.2.06)", value=f"{cod_padre}.")
                nombre_cuenta = st.text_input("Nombre de la Cuenta / Subcuenta")
                
            with col2:
                categoria = st.text_input("Categoría", value=row_padre['categoria'], disabled=True)
                tipo_cuenta = st.text_input("Tipo de Cuenta", value=row_padre['tipo'], disabled=True)
                nivel_cuenta = row_padre['nivel'] + 1
                st.caption(f"Se registrará como Nivel {nivel_cuenta} ({categoria})")
                
            btn_guardar_cta = st.form_submit_button("💾 Guardar Nueva Cuenta")
            
            if btn_guardar_cta:
                if nuevo_codigo and nombre_cuenta:
                    try:
                        cursor = conn.cursor()
                        cursor.execute("""
                            INSERT INTO plan_cuentas (codigo, nombre, categoria, tipo, padre_codigo, nivel)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (nuevo_codigo, nombre_cuenta, row_padre['categoria'], row_padre['tipo'], cod_padre, nivel_cuenta))
                        conn.commit()
                        st.success(f"¡Cuenta '{nombre_cuenta}' ({nuevo_codigo}) creada con éxito!")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("El código ingresado ya existe. Usa un código único.")
                else:
                    st.error("Por favor completa el código y el nombre.")

elif opcion == "✏️ Registrar Asiento Manual":
    st.header("✏️ Registrar Asiento Contable Manual (Partida Doble)")
    st.caption("Registra ajustes o transacciones seleccionando cuentas o subcuentas del Plan de Cuentas.")
    
    lista_cuentas = obtener_subcuentas()
    
    fecha_m = st.date_input("Fecha del Asiento", datetime.now())
    glosa_m = st.text_input("Glosa / Explicación del Asiento", "Ajuste contable manual")
    
    st.markdown("---")
    st.subheader("Movimientos del Asiento")
    
    col_a, col_b = st.columns(2)
    
    with col_a:
        st.markdown("### 🔹 Línea 1 (Debe)")
        cuenta_debe = st.selectbox("Subcuenta al Debe", lista_cuentas, key="c_debe")
        monto_debe = st.number_input("Monto Debe ($)", min_value=0.0, step=100.0, key="m_debe")
        
    with col_b:
        st.markdown("### 🔸 Línea 2 (Haber)")
        cuenta_haber = st.selectbox("Subcuenta al Haber", lista_cuentas, key="c_haber")
        monto_haber = st.number_input("Monto Haber ($)", min_value=0.0, step=100.0, key="m_haber")
        
    st.markdown("---")
    
    diferencia = abs(monto_debe - monto_haber)
    if monto_debe > 0 and monto_haber > 0:
        if monto_debe == monto_haber:
            st.success("✅ Asiento cuadrado (Debe = Haber)")
        else:
            st.error(f"❌ Asiento descuadrado por ${diferencia:,.0f}")
            
    if st.button("Guardar Asiento Manual"):
        if monto_debe <= 0 or monto_haber <= 0:
            st.error("Los montos deben ser mayores a $0.")
        elif monto_debe != monto_haber:
            st.error("No se puede guardar un asiento descuadrado. El Debe debe ser igual al Haber.")
        else:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?, ?, ?, 0, ?)",
                           (str(fecha_m), cuenta_debe, monto_debe, glosa_m))
            cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?, ?, 0, ?, ?)",
                           (str(fecha_m), cuenta_haber, monto_haber, glosa_m))
            conn.commit()
            st.success("¡Asiento manual guardado correctamente en el Libro Diario!")

elif opcion == "Registrar Compra Proveedor":
    st.header("🛒 Registrar Compra (Desglose Neto + IVA)")
    
    cuentas_gastos = obtener_subcuentas("Gastos")
    if not cuentas_gastos:
        cuentas_gastos = ["Gastos Generales"]

    col_input1, col_input2 = st.columns(2)
    with col_input1:
        fecha = st.date_input("Fecha de Compra", datetime.now())
        rut_prov = st.text_input("RUT Proveedor")
        nombre_prov = st.text_input("Nombre Proveedor")
        cuenta_gasto_sel = st.selectbox("Imputar a Subcuenta de Gasto:", cuentas_gastos)
        glosa = st.text_input("Glosa / Detalle")
    
    with col_input2:
        monto_neto = st.number_input("Monto Neto (Base $)", min_value=0.0, step=100.0)
        iva = round(monto_neto * 0.19, 2)
        monto_total = round(monto_neto + iva, 2)
        
        st.metric("IVA Crédito Fiscal (19%)", f"${iva:,.0f}")
        st.metric("Monto Total ($)", f"${monto_total:,.0f}")
    
    if st.button("Guardar Compra"):
        if rut_prov and monto_neto > 0:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM proveedores WHERE rut = ?", (rut_prov,))
            res = cursor.fetchone()
            prov_id = res[0] if res else cursor.execute("INSERT INTO proveedores (rut, nombre) VALUES (?, ?)", (rut_prov, nombre_prov)).lastrowid
            
            cursor.execute("""
                INSERT INTO compras (fecha, proveedor_id, cuenta_gasto, monto_neto, iva, monto_total, glosa) 
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (str(fecha), prov_id, cuenta_gasto_sel, monto_neto, iva, monto_total, glosa))
            
            cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?, ?, ?, 0, ?)", (str(fecha), cuenta_gasto_sel, monto_neto, f"Compra {nombre_prov}"))
            cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?, 'IVA Crédito Fiscal', ?, 0, ?)", (str(fecha), iva, f"IVA Compra {nombre_prov}"))
            cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?, 'Cuentas por Pagar Proveedores', 0, ?, ?)", (str(fecha), monto_total, f"Compra {nombre_prov}"))
            
            conn.commit()
            st.success(f"¡Compra registrada con éxito e imputada a '{cuenta_gasto_sel}'! Total: ${monto_total:,.0f}")
        else:
            st.error("Por favor ingresa el RUT del proveedor y un monto neto válido.")

elif opcion == "Registrar Pago Proveedor":
    st.header("💸 Registrar Pago a Proveedor")
    
    try:
        df_prov = pd.read_sql_query("SELECT id, nombre FROM proveedores", conn)
    except Exception:
        df_prov = pd.DataFrame(columns=['id', 'nombre'])
        
    if not df_prov.empty:
        prov_sel = st.selectbox("Selecciona Proveedor", df_prov['nombre'])
        prov_id = df_prov[df_prov['nombre'] == prov_sel]['id'].values[0]
        fecha_pago = st.date_input("Fecha Pago", datetime.now())
        monto_pago = st.number_input("Monto Pagado ($)", min_value=0.0, step=100.0)
        if st.button("Registrar Pago"):
            if monto_pago > 0:
                cursor = conn.cursor()
                cursor.execute("INSERT INTO pagos (fecha, proveedor_id, monto) VALUES (?, ?, ?)", (str(fecha_pago), prov_id, monto_pago))
                cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?, 'Cuentas por Pagar Proveedores', ?, 0, ?)", (str(fecha_pago), monto_pago, f"Pago a {prov_sel}"))
                cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?, 'Banco', 0, ?, ?)", (str(fecha_pago), monto_pago, f"Pago a {prov_sel}"))
                conn.commit()
                st.success("¡Pago registrado!")
    else:
        st.warning("No hay proveedores registrados previamente. Registra primero una compra.")

elif opcion == "Registrar Venta Cliente":
    st.header("📈 Registrar Venta (Desglose Neto + IVA)")
    
    cuentas_ingresos = obtener_subcuentas("Ingresos")
    if not cuentas_ingresos:
        cuentas_ingresos = ["Ingresos por Ventas"]

    col_v1, col_v2 = st.columns(2)
    with col_v1:
        fecha_v = st.date_input("Fecha de Venta", datetime.now())
        rut_cli = st.text_input("RUT Cliente")
        nombre_cli = st.text_input("Nombre Cliente")
        cuenta_ingreso_sel = st.selectbox("Imputar a Subcuenta de Ingreso:", cuentas_ingresos)
        glosa_v = st.text_input("Glosa / Detalle")
    
    with col_v2:
        monto_neto_v = st.number_input("Monto Neto Venta (Base $)", min_value=0.0, step=100.0)
        iva_v = round(monto_neto_v * 0.19, 2)
        monto_total_v = round(monto_neto_v + iva_v, 2)
        
        st.metric("IVA Débito Fiscal (19%)", f"${iva_v:,.0f}")
        st.metric("Monto Total Venta ($)", f"${monto_total_v:,.0f}")
        
    if st.button("Guardar Venta"):
        if rut_cli and monto_neto_v > 0:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM clientes WHERE rut = ?", (rut_cli,))
            res = cursor.fetchone()
            cli_id = res[0] if res else cursor.execute("INSERT INTO clientes (rut, nombre) VALUES (?, ?)", (rut_cli, nombre_cli)).lastrowid
            
            cursor.execute("""
                INSERT INTO ventas (fecha, cliente_id, cuenta_ingreso, monto_neto, iva, monto_total, glosa) 
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (str(fecha_v), cli_id, cuenta_ingreso_sel, monto_neto_v, iva_v, monto_total_v, glosa_v))
            
            cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?, 'Cuentas por Cobrar Clientes', ?, 0, ?)", (str(fecha_v), monto_total_v, f"Venta a {nombre_cli}"))
            cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?, ?, 0, ?, ?)", (str(fecha_v), cuenta_ingreso_sel, monto_neto_v, f"Venta a {nombre_cli}"))
            cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?, 'IVA Débito Fiscal', 0, ?, ?)", (str(fecha_v), iva_v, f"IVA Venta {nombre_cli}"))
            
            conn.commit()
            st.success(f"¡Venta registrada con éxito e imputada a '{cuenta_ingreso_sel}'! Total: ${monto_total_v:,.0f}")
        else:
            st.error("Por favor ingresa el RUT del cliente y un monto neto válido.")

elif opcion == "Registrar Cobro Cliente":
    st.header("💰 Registrar Cobro de Cliente")
    
    try:
        df_cli = pd.read_sql_query("SELECT id, nombre FROM clientes", conn)
    except Exception:
        df_cli = pd.DataFrame(columns=['id', 'nombre'])
        
    if not df_cli.empty:
        cli_sel = st.selectbox("Selecciona Cliente", df_cli['nombre'])
        cli_id = df_cli[df_cli['nombre'] == cli_sel]['id'].values[0]
        fecha_cobro = st.date_input("Fecha Cobro", datetime.now())
        monto_cobro = st.number_input("Monto Cobrado ($)", min_value=0.0, step=100.0)
        if st.button("Registrar Cobro"):
            if monto_cobro > 0:
                cursor = conn.cursor()
                cursor.execute("INSERT INTO cobros (fecha, cliente_id, monto) VALUES (?, ?, ?)", (str(fecha_cobro), cli_id, monto_cobro))
                cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?, 'Banco', ?, 0, ?)", (str(fecha_cobro), monto_cobro, f"Cobro a {cli_sel}"))
                cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?, 'Cuentas por Cobrar Clientes', 0, ?, ?)", (str(fecha_cobro), monto_cobro, f"Cobro a {cli_sel}"))
                conn.commit()
                st.success("¡Cobro abonado al Banco!")
    else:
        st.warning("No hay clientes registrados previamente. Registra primero una venta.")

elif opcion == "Cartola Bancaria y Saldos":
    st.header("🏦 Cartola Bancaria y Flujo de Caja")
    df_ingresos = pd.read_sql_query("SELECT SUM(monto) as total FROM cobros", conn)
    df_egresos = pd.read_sql_query("SELECT SUM(monto) as total FROM pagos", conn)
    
    total_ing = df_ingresos['total'].iloc[0] or 0.0
    total_egr = df_egresos['total'].iloc[0] or 0.0
    saldo_banco = total_ing - total_egr
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Ingresos (Cobros)", f"${total_ing:,.0f}")
    col2.metric("Total Egresos (Pagos)", f"${total_egr:,.0f}")
    col3.metric("Saldo Disponible Banco", f"${saldo_banco:,.0f}")

elif opcion == "Libro Diario (Contabilidad)":
    st.header("📖 Libro Diario Contable")
    df_ld = pd.read_sql_query("SELECT * FROM libro_diario ORDER BY id DESC", conn)
    if not df_ld.empty:
        st.dataframe(df_ld, use_container_width=True)
        total_debe = df_ld['debe'].sum()
        total_haber = df_ld['haber'].sum()
        c1, c2 = st.columns(2)
        c1.metric("Total Debe", f"${total_debe:,.0f}")
        c2.metric("Total Haber", f"${total_haber:,.0f}")
    else:
        st.info("Aún no hay asientos registrados en el Libro Diario.")

elif opcion == "📊 Reportes Financieros":
    st.header("📊 Reportes y Balances Financieros")
    
    tab1, tab2, tab3 = st.tabs(["Estado de Resultados", "Balance de Comprobación", "Exportar y Respaldos"])
    
    with tab1:
        st.subheader("Estado de Resultados (Cuentas Nominales)")
        df_v = pd.read_sql_query("SELECT SUM(monto_neto) as total FROM ventas", conn)
        df_c = pd.read_sql_query("SELECT SUM(monto_neto) as total FROM compras", conn)
        
        tot_ventas = df_v['total'].iloc[0] or 0.0
        tot_compras = df_c['total'].iloc[0] or 0.0
        resultado = tot_ventas - tot_compras
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Ingresos Netos Totales", f"${tot_ventas:,.0f}")
        c2.metric("Costos/Gastos Netos Totales", f"${tot_compras:,.0f}")
        c3.metric("Resultado Neto del Ejercicio", f"${resultado:,.0f}", delta=f"${resultado:,.0f}")
        
    with tab2:
        st.subheader("Balance de Comprobación de Sumas y Saldos")
        df_bal = pd.read_sql_query("""
            SELECT l.cuenta as 'Subcuenta', p.tipo as 'Tipo de Cuenta', 
                   SUM(l.debe) as Total_Debe, SUM(l.haber) as Total_Haber,
                   (SUM(l.debe) - SUM(l.haber)) as Saldo_Neto
            FROM libro_diario l
            LEFT JOIN plan_cuentas p ON l.cuenta = p.nombre
            GROUP BY l.cuenta
        """, conn)
        if not df_bal.empty:
            st.dataframe(df_bal, use_container_width=True)
        else:
            st.info("No hay datos contables suficientes para generar el balance.")

    with tab3:
        st.subheader("Descargar Respaldos")
        
        col_r1, col_r2 = st.columns(2)
        
        with col_r1:
            st.markdown("### 💾 Respaldo Completo (.db)")
            st.caption("Descarga la base de datos completa para subir a tu Google Drive.")
            try:
                with open(DB_FILE, "rb") as fp:
                    db_bytes = fp.read()
                fecha_hoy = datetime.now().strftime("%Y-%m-%d")
                st.download_button(
                    label="💾 Descargar Base de Datos Completa (.db)",
                    data=db_bytes,
                    file_name=f"sistema_contable_{fecha_hoy}.db",
                    mime="application/x-sqlite3"
                )
            except Exception:
                st.error("Aún no se ha generado el archivo de base de datos.")

        with col_r2:
            st.markdown("### 📥 Exportar Libro Diario (.csv)")
            st.caption("Descarga el Libro Diario en formato CSV / Excel.")
            df_exp = pd.read_sql_query("SELECT * FROM libro_diario", conn)
            if not df_exp.empty:
                csv = df_exp.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 Descargar Libro Diario (.csv)",
                    data=csv,
                    file_name="libro_diario.csv",
                    mime="text/csv"
                )
            else:
                st.info("No hay registros para exportar.")

conn.close()

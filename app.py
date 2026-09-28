import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime

st.set_page_config(page_title="Sistema Contable Web", page_icon="💼", layout="wide")

def get_connection():
    return sqlite3.connect("sistema_contable.db")

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Tablas existentes
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS proveedores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        rut TEXT UNIQUE,
        nombre TEXT
    )""")
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS compras (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fecha TEXT,
        proveedor_id INTEGER,
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
        rut TEXT UNIQUE,
        nombre TEXT
    )""")
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ventas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fecha TEXT,
        cliente_id INTEGER,
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
    
    # Tabla Plan de Cuentas
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS plan_cuentas (
        codigo TEXT PRIMARY KEY,
        nombre TEXT,
        tipo TEXT
    )""")
    
    # Poblar Plan de Cuentas por defecto si está vacío
    cursor.execute("SELECT COUNT(*) FROM plan_cuentas")
    if cursor.fetchone()[0] == 0:
        cuentas_defecto = [
            ("1101", "Banco", "Activo"),
            ("1102", "Caja", "Activo"),
            ("1103", "Cuentas por Cobrar", "Activo"),
            ("1104", "IVA Crédito Fiscal", "Activo"),
            ("2101", "Cuentas por Pagar", "Pasivo"),
            ("2102", "IVA Débito Fiscal", "Pasivo"),
            ("3101", "Capital Social", "Patrimonio"),
            ("4101", "Ingresos por Ventas", "Ingresos"),
            ("5101", "Gastos Generales", "Gastos"),
            ("5102", "Gastos de Arriendo", "Gastos"),
            ("5103", "Gastos de Servicios Básicos", "Gastos"),
            ("5104", "Remuneraciones", "Gastos")
        ]
        cursor.executemany("INSERT INTO plan_cuentas (codigo, nombre, tipo) VALUES (?, ?, ?)", cuentas_defecto)

    try:
        cursor.execute("ALTER TABLE compras ADD COLUMN monto_neto REAL")
        cursor.execute("ALTER TABLE compras ADD COLUMN iva REAL")
        cursor.execute("ALTER TABLE compras ADD COLUMN monto_total REAL")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE ventas ADD COLUMN monto_neto REAL")
        cursor.execute("ALTER TABLE ventas ADD COLUMN iva REAL")
        cursor.execute("ALTER TABLE ventas ADD COLUMN monto_total REAL")
    except sqlite3.OperationalError:
        pass

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

if opcion == "Inicio / Resumen":
    st.title("💼 Sistema Contable Web")
    st.subheader("Bienvenido a tu Sistema Contable Integrado")
    st.info("Utiliza el menú lateral para acceder al Plan de Cuentas, Asientos Manuales, Compras, Ventas, Banco, Libro Diario y Reportes.")

elif opcion == "📋 Plan de Cuentas":
    st.header("📋 Plan de Cuentas Contable")
    
    tab_ver, tab_crear = st.tabs(["Ver Plan de Cuentas", "Añadir Nueva Cuenta"])
    
    with tab_ver:
        df_pc = pd.read_sql_query("SELECT codigo as 'Código', nombre as 'Nombre Cuenta', tipo as 'Tipo de Cuenta' FROM plan_cuentas ORDER BY codigo", conn)
        st.dataframe(df_pc, use_container_width=True)
        
    with tab_crear:
        st.subheader("Agregar Cuenta Personalizada")
        with st.form("form_nueva_cuenta"):
            cod = st.text_input("Código de Cuenta (Ej: 5105)")
            nom = st.text_input("Nombre de Cuenta (Ej: Gastos de Publicidad)")
            tip = st.selectbox("Tipo de Cuenta", ["Activo", "Pasivo", "Patrimonio", "Ingresos", "Gastos"])
            btn_nc = st.form_submit_button("Guardar Cuenta")
            
            if btn_nc:
                if cod and nom:
                    try:
                        c = conn.cursor()
                        c.execute("INSERT INTO plan_cuentas (codigo, nombre, tipo) VALUES (?, ?, ?)", (cod, nom, tip))
                        conn.commit()
                        st.success(f"¡Cuenta '{nom}' creada exitosamente!")
                    except sqlite3.IntegrityError:
                        st.error("El código de cuenta ya existe.")
                else:
                    st.error("Por favor completa el código y el nombre.")

elif opcion == "✏️ Registrar Asiento Manual":
    st.header("✏️ Registrar Asiento Contable Manual (Partida Doble)")
    st.caption("Registra ajustes manuales o transacciones especiales asegurando que la suma del Debe sea igual al Haber.")
    
    df_cuentas = pd.read_sql_query("SELECT nombre FROM plan_cuentas ORDER BY nombre", conn)
    lista_cuentas = df_cuentas['nombre'].tolist() if not df_cuentas.empty else ["Banco", "Caja", "Gastos Generales", "Capital Social"]
    
    fecha_m = st.date_input("Fecha del Asiento", datetime.now())
    glosa_m = st.text_input("Glosa / Explicación del Asiento", "Ajuste contable manual")
    
    st.markdown("---")
    st.subheader("Movimientos del Asiento")
    
    col_a, col_b = st.columns(2)
    
    with col_a:
        st.markdown("### 🔹 Línea 1 (Debe)")
        cuenta_debe = st.selectbox("Cuenta al Debe", lista_cuentas, key="c_debe")
        monto_debe = st.number_input("Monto Debe ($)", min_value=0.0, step=100.0, key="m_debe")
        
    with col_b:
        st.markdown("### 🔸 Línea 2 (Haber)")
        cuenta_haber = st.selectbox("Cuenta al Haber", lista_cuentas, key="c_haber")
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
    
    col_input1, col_input2 = st.columns(2)
    with col_input1:
        fecha = st.date_input("Fecha de Compra", datetime.now())
        rut_prov = st.text_input("RUT Proveedor")
        nombre_prov = st.text_input("Nombre Proveedor")
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
                INSERT INTO compras (fecha, proveedor_id, monto_neto, iva, monto_total, glosa) 
                VALUES (?, ?, ?, ?, ?, ?)
            """, (str(fecha), prov_id, monto_neto, iva, monto_total, glosa))
            
            cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?, 'Gastos Generales', ?, 0, ?)", (str(fecha), monto_neto, f"Compra {nombre_prov}"))
            cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?, 'IVA Crédito Fiscal', ?, 0, ?)", (str(fecha), iva, f"IVA Compra {nombre_prov}"))
            cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?, 'Cuentas por Pagar', 0, ?, ?)", (str(fecha), monto_total, f"Compra {nombre_prov}"))
            
            conn.commit()
            st.success(f"¡Compra registrada con éxito! Total: ${monto_total:,.0f}")
        else:
            st.error("Por favor ingresa el RUT del proveedor y un monto neto válido.")

elif opcion == "Registrar Pago Proveedor":
    st.header("💸 Registrar Pago a Proveedor")
    df_prov = pd.read_sql_query("SELECT id, nombre FROM proveedores", conn)
    if not df_prov.empty:
        prov_sel = st.selectbox("Selecciona Proveedor", df_prov['nombre'])
        prov_id = df_prov[df_prov['nombre'] == prov_sel]['id'].values[0]
        fecha_pago = st.date_input("Fecha Pago", datetime.now())
        monto_pago = st.number_input("Monto Pagado ($)", min_value=0.0, step=100.0)
        if st.button("Registrar Pago"):
            if monto_pago > 0:
                cursor = conn.cursor()
                cursor.execute("INSERT INTO pagos (fecha, proveedor_id, monto) VALUES (?, ?, ?)", (str(fecha_pago), prov_id, monto_pago))
                cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?, 'Cuentas por Pagar', ?, 0, ?)", (str(fecha_pago), monto_pago, f"Pago a {prov_sel}"))
                cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?, 'Banco', 0, ?, ?)", (str(fecha_pago), monto_pago, f"Pago a {prov_sel}"))
                conn.commit()
                st.success("¡Pago registrado!")
    else:
        st.warning("No hay proveedores registrados previamente.")

elif opcion == "Registrar Venta Cliente":
    st.header("📈 Registrar Venta (Desglose Neto + IVA)")
    
    col_v1, col_v2 = st.columns(2)
    with col_v1:
        fecha_v = st.date_input("Fecha de Venta", datetime.now())
        rut_cli = st.text_input("RUT Cliente")
        nombre_cli = st.text_input("Nombre Cliente")
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
                INSERT INTO ventas (fecha, cliente_id, monto_neto, iva, monto_total, glosa) 
                VALUES (?, ?, ?, ?, ?, ?)
            """, (str(fecha_v), cli_id, monto_neto_v, iva_v, monto_total_v, glosa_v))
            
            cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?, 'Cuentas por Cobrar', ?, 0, ?)", (str(fecha_v), monto_total_v, f"Venta a {nombre_cli}"))
            cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?, 'Ingresos por Ventas', 0, ?, ?)", (str(fecha_v), monto_neto_v, f"Venta a {nombre_cli}"))
            cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?, 'IVA Débito Fiscal', 0, ?, ?)", (str(fecha_v), iva_v, f"IVA Venta {nombre_cli}"))
            
            conn.commit()
            st.success(f"¡Venta registrada con éxito! Total: ${monto_total_v:,.0f}")
        else:
            st.error("Por favor ingresa el RUT del cliente y un monto neto válido.")

elif opcion == "Registrar Cobro Cliente":
    st.header("💰 Registrar Cobro de Cliente")
    df_cli = pd.read_sql_query("SELECT id, nombre FROM clientes", conn)
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
                cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?, 'Cuentas por Cobrar', 0, ?, ?)", (str(fecha_cobro), monto_cobro, f"Cobro a {cli_sel}"))
                conn.commit()
                st.success("¡Cobro abonado al Banco!")
    else:
        st.warning("No hay clientes registrados previamente.")

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
    
    tab1, tab2, tab3 = st.tabs(["Estado de Resultados", "Balance de Comprobación", "Exportar Datos"])
    
    with tab1:
        st.subheader("Estado de Resultados Simplificado")
        df_v = pd.read_sql_query("SELECT SUM(monto_neto) as total FROM ventas", conn)
        df_c = pd.read_sql_query("SELECT SUM(monto_neto) as total FROM compras", conn)
        
        tot_ventas = df_v['total'].iloc[0] or 0.0
        tot_compras = df_c['total'].iloc[0] or 0.0
        resultado = tot_ventas - tot_compras
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Ingresos Netos (Ventas)", f"${tot_ventas:,.0f}")
        c2.metric("Costos/Gastos Netos (Compras)", f"${tot_compras:,.0f}")
        c3.metric("Resultado Neto (Utilidad/Pérdida)", f"${resultado:,.0f}", delta=f"${resultado:,.0f}")
        
    with tab2:
        st.subheader("Balance de Comprobación de Sumas y Saldos")
        df_bal = pd.read_sql_query("""
            SELECT cuenta, SUM(debe) as Total_Debe, SUM(haber) as Total_Haber,
                   (SUM(debe) - SUM(haber)) as Saldo
            FROM libro_diario
            GROUP BY cuenta
        """, conn)
        if not df_bal.empty:
            st.dataframe(df_bal, use_container_width=True)
        else:
            st.info("No hay datos contables suficientes para generar el balance.")

    with tab3:
        st.subheader("Descargar Libro Diario en CSV")
        df_exp = pd.read_sql_query("SELECT * FROM libro_diario", conn)
        if not df_exp.empty:
            csv = df_exp.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Descargar Libro Diario (.csv)", data=csv, file_name="libro_diario.csv", mime="text/csv")
        else:
            st.info("No hay registros para exportar.")

conn.close()

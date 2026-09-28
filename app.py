import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime

# Configuración de página
st.set_page_config(page_title="Sistema Contable Web", page_icon="💼", layout="wide")

# Conexión con base de datos SQLite
def get_connection():
    return sqlite3.connect("sistema_contable.db")

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    # Tablas existentes
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
        monto REAL,
        glosa TEXT
    )""")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pagos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fecha TEXT,
        proveedor_id INTEGER,
        monto REAL
    )""")
    # Módulo de Clientes / Ventas
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
        monto REAL,
        glosa TEXT
    )""")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS cobros (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fecha TEXT,
        cliente_id INTEGER,
        monto REAL
    )""")
    # Libro Diario (Asientos Contables)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS libro_diario (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fecha TEXT,
        cuenta TEXT,
        debe REAL,
        haber REAL,
        glosa TEXT
    )""")
    conn.commit()
    conn.close()

init_db()

# Menú lateral interactivo
st.sidebar.title("📌 Menú Principal")
opcion = st.sidebar.radio(
    "Selecciona un Módulo:",
    [
        "Inicio / Resumen",
        "Registrar Compra Proveedor",
        "Registrar Pago Proveedor",
        "Registrar Venta Cliente",
        "Registrar Cobro Cliente",
        "Cartola Bancaria y Saldos",
        "Libro Diario (Contabilidad)"
    ]
)

conn = get_connection()

if opcion == "Inicio / Resumen":
    st.title("💼 Sistema Contable Web")
    st.subheader("Bienvenido a tu Sistema Contable Integrado")
    st.info("Utiliza el menú lateral para acceder a Compras, Ventas, Clientes, Proveedores, Banco y Libro Diario.")

elif opcion == "Registrar Compra Proveedor":
    st.header("🛒 Registrar Compra (Proveedores)")
    with st.form("form_compra"):
        fecha = st.date_input("Fecha de Compra", datetime.now())
        rut_prov = st.text_input("RUT Proveedor")
        nombre_prov = st.text_input("Nombre Proveedor")
        monto = st.number_input("Monto Total ($)", min_value=0.0, step=100.0)
        glosa = st.text_input("Glosa / Detalle")
        btn = st.form_submit_button("Guardar Compra")
        
        if btn and rut_prov and monto > 0:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM proveedores WHERE rut = ?", (rut_prov,))
            res = cursor.fetchone()
            if res:
                prov_id = res[0]
            else:
                cursor.execute("INSERT INTO proveedores (rut, nombre) VALUES (?, ?)", (rut_prov, nombre_prov))
                prov_id = cursor.lastrowid
            
            cursor.execute("INSERT INTO compras (fecha, proveedor_id, monto, glosa) VALUES (?, ?, ?, ?)",
                           (str(fecha), prov_id, monto, glosa))
            # Asiento Contable Automático (Gasto / Cuentas por Pagar)
            cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?, 'Gastos Generales', ?, 0, ?)",
                           (str(fecha), monto, f"Compra {nombre_prov}"))
            cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?, 'Cuentas por Pagar', 0, ?, ?)",
                           (str(fecha), monto, f"Compra {nombre_prov}"))
            conn.commit()
            st.success("¡Compra registrada y asiento contable generado correctamente!")

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
                cursor.execute("INSERT INTO pagos (fecha, proveedor_id, monto) VALUES (?, ?, ?)",
                               (str(fecha_pago), prov_id, monto_pago))
                # Asiento Contable (Cuentas por Pagar / Banco)
                cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?, 'Cuentas por Pagar', ?, 0, ?)",
                               (str(fecha_pago), monto_pago, f"Pago a {prov_sel}"))
                cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?, 'Banco', 0, ?, ?)",
                               (str(fecha_pago), monto_pago, f"Pago a {prov_sel}"))
                conn.commit()
                st.success("¡Pago registrado!")
    else:
        st.warning("No hay proveedores registrados.")

elif opcion == "Registrar Venta Cliente":
    st.header("📈 Registrar Venta (Clientes)")
    with st.form("form_venta"):
        fecha_v = st.date_input("Fecha de Venta", datetime.now())
        rut_cli = st.text_input("RUT Cliente")
        nombre_cli = st.text_input("Nombre Cliente")
        monto_v = st.number_input("Monto Venta ($)", min_value=0.0, step=100.0)
        glosa_v = st.text_input("Glosa / Detalle")
        btn_v = st.form_submit_button("Guardar Venta")
        
        if btn_v and rut_cli and monto_v > 0:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM clientes WHERE rut = ?", (rut_cli,))
            res = cursor.fetchone()
            if res:
                cli_id = res[0]
            else:
                cursor.execute("INSERT INTO clientes (rut, nombre) VALUES (?, ?)", (rut_cli, nombre_cli))
                cli_id = cursor.lastrowid
            
            cursor.execute("INSERT INTO ventas (fecha, cliente_id, monto, glosa) VALUES (?, ?, ?, ?)",
                           (str(fecha_v), cli_id, monto_v, glosa_v))
            # Asiento Contable Automático (Cuentas por Cobrar / Ventas)
            cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?, 'Cuentas por Cobrar', ?, 0, ?)",
                           (str(fecha_v), monto_v, f"Venta a {nombre_cli}"))
            cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?, 'Ingresos por Ventas', 0, ?, ?)",
                           (str(fecha_v), monto_v, f"Venta a {nombre_cli}"))
            conn.commit()
            st.success("¡Venta registrada e ingresada al Libro Diario!")

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
                cursor.execute("INSERT INTO cobros (fecha, cliente_id, monto) VALUES (?, ?, ?)",
                               (str(fecha_cobro), cli_id, monto_cobro))
                # Asiento Contable (Banco / Cuentas por Cobrar)
                cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?, 'Banco', ?, 0, ?)",
                               (str(fecha_cobro), monto_cobro, f"Cobro a {cli_sel}"))
                cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?, 'Cuentas por Cobrar', 0, ?, ?)",
                               (str(fecha_cobro), monto_cobro, f"Cobro a {cli_sel}"))
                conn.commit()
                st.success("¡Cobro abonado al Banco!")
    else:
        st.warning("No hay clientes registrados.")

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
    st.header("📖 Libro Diario Contable (Asientos de Partida Doble)")
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

conn.close()

import streamlit as st
import pandas as pd
import sqlite3
import io
from datetime import datetime

st.set_page_config(page_title="Sistema Contable Web Chilenos", page_icon="🇨🇱", layout="wide")

DB_FILE = "sistema_contable.db"

def get_connection():
    return sqlite3.connect(DB_FILE)

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Creación de tablas base
    tablas = [
        """CREATE TABLE IF NOT EXISTS proveedores (id INTEGER PRIMARY KEY AUTOINCREMENT, rut TEXT UNIQUE, nombre TEXT, cuenta_defecto TEXT, centro_costo TEXT)""",
        """CREATE TABLE IF NOT EXISTS compras (id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, proveedor_id INTEGER, cuenta_gasto TEXT, centro_costo TEXT, monto_neto REAL, iva REAL, monto_total REAL, glosa TEXT)""",
        """CREATE TABLE IF NOT EXISTS pagos (id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, proveedor_id INTEGER, monto REAL)""",
        """CREATE TABLE IF NOT EXISTS clientes (id INTEGER PRIMARY KEY AUTOINCREMENT, rut TEXT UNIQUE, nombre TEXT)""",
        """CREATE TABLE IF NOT EXISTS ventas (id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, cliente_id INTEGER, cuenta_ingreso TEXT, monto_neto REAL, iva REAL, monto_total REAL, glosa TEXT)""",
        """CREATE TABLE IF NOT EXISTS cobros (id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, cliente_id INTEGER, monto REAL)""",
        """CREATE TABLE IF NOT EXISTS bancos_movimientos (id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, tipo TEXT, monto REAL, glosa TEXT)""",
        """CREATE TABLE IF NOT EXISTS libro_diario (id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, cuenta TEXT, debe REAL, haber REAL, glosa TEXT, centro_costo TEXT)"""
    ]
    for tabla in tablas:
        cursor.execute(tabla)
        
    cursor.execute("PRAGMA table_info(plan_cuentas)")
    columnas_pc = [info[1] for info in cursor.fetchall()]
    
    if not columnas_pc or "categoria" not in columnas_pc:
        cursor.execute("DROP TABLE IF EXISTS plan_cuentas")
        cursor.execute("""
        CREATE TABLE plan_cuentas (
            codigo TEXT PRIMARY KEY,
            nombre TEXT,
            categoria TEXT,
            tipo TEXT,
            padre_codigo TEXT,
            nivel INTEGER
        )""")
        
        cat_inicial = [
            ("1", "ACTIVO", "Real", "Activo", None, 1),
            ("1.1", "Activo Corriente", "Real", "Activo", "1", 2),
            ("1.1.01", "Efectivo y Equivalentes al Efectivo", "Real", "Activo", "1.1", 3),
            ("1.1.01.01", "Banco", "Real", "Activo", "1.1.01", 3),
            ("1.1.01.02", "Caja General", "Real", "Activo", "1.1.01", 3),
            ("1.1.03", "Cuentas Comerciales y Otras Cuentas por Cobrar", "Real", "Activo", "1.1", 2),
            ("1.1.03.01", "Cuentas por Cobrar Clientes", "Real", "Activo", "1.1.03", 3),
            ("1.1.03.02", "IVA Crédito Fiscal", "Real", "Activo", "1.1.03", 3),
            ("1.2", "Activo No Corriente", "Real", "Activo", "1", 2),
            ("1.2.01", "Propiedades, Planta y Equipo", "Real", "Activo", "1.2", 2),
            ("2", "PASIVO", "Real", "Pasivo", None, 1),
            ("2.1", "Pasivo Corriente", "Real", "Pasivo", "2", 2),
            ("2.1.01", "Cuentas Comerciales y Otras Cuentas por Pagar", "Real", "Pasivo", "2.1", 2),
            ("2.1.01.01", "Cuentas por Pagar Proveedores", "Real", "Pasivo", "2.1.01", 3),
            ("2.1.01.02", "IVA Débito Fiscal", "Real", "Pasivo", "2.1.01", 3),
            ("3", "PATRIMONIO", "Real", "Patrimonio", None, 1),
            ("3.1", "Patrimonio Neto", "Real", "Patrimonio", "3", 2),
            ("3.1.01", "Capital Social", "Real", "Patrimonio", "3.1", 3),
            ("3.1.02", "Resultados Acumulados", "Real", "Patrimonio", "3.1", 3),
            ("4", "INGRESOS", "Nominal", "Ingresos", None, 1),
            ("4.1", "Ingresos de Actividades Ordinarias", "Nominal", "Ingresos", "4", 2),
            ("4.1.01", "Ingresos por Ventas", "Nominal", "Ingresos", "4.1", 3),
            ("5", "COSTOS Y GASTOS", "Nominal", "Gastos", None, 1),
            ("5.1", "Costo de Ventas", "Nominal", "Gastos", "5", 2),
            ("5.1.01", "Costo de Ventas", "Nominal", "Gastos", "5.1", 3),
            ("5.2", "Gastos de Administración y Ventas", "Nominal", "Gastos", "5", 2),
            ("5.2.01", "Gastos Generales", "Nominal", "Gastos", "5.2", 3)
        ]
        cursor.executemany("INSERT INTO plan_cuentas VALUES (?, ?, ?, ?, ?, ?)", cat_inicial)

    conn.commit()
    conn.close()

init_db()

st.sidebar.title("📌 Menú Principal")
opcion = st.sidebar.radio(
    "Selecciona un Módulo:",
    [
        "Inicio / Resumen",
        "🏢 Módulo de Proveedores",
        "📈 Módulo de Clientes",
        "📥 Carga Masiva / Importar",
        "📋 Plan de Cuentas",
        "✏️ Registrar Asiento Manual",
        "🏦 Bancos y Cartola",
        "📖 Libro Diario (Contabilidad)",
        "📊 Reportes Financieros (Norma Chile)"
    ]
)

conn = get_connection()
LISTA_CENTROS_COSTO = ["General / Ninguno", "Administración", "Ventas", "Operaciones / Producción", "TI y Tecnología", "Marketing"]

def obtener_subcuentas(tipo_filtro=None):
    if tipo_filtro:
        query = "SELECT nombre FROM plan_cuentas WHERE nivel = 3 AND tipo = ? ORDER BY codigo"
        df = pd.read_sql_query(query, conn, params=(tipo_filtro,))
    else:
        query = "SELECT nombre FROM plan_cuentas WHERE nivel = 3 ORDER BY codigo"
        df = pd.read_sql_query(query, conn)
    return df['nombre'].tolist() if not df.empty else []

if opcion == "Inicio / Resumen":
    st.title("💼 Sistema Contable Web - Estándar Chileno")
    st.subheader("Control Contable, SII y Normas CMF / IFRS")
    st.info("Utiliza el menú lateral para gestionar proveedores, clientes, cargas masivas y reportes financieros.")

elif opcion == "🏢 Módulo de Proveedores":
    st.header("🏢 Módulo de Proveedores y Cuentas por Pagar")
    
    tab_reg, tab_pago, tab_rep = st.tabs(["🛒 Factura de Compra", "💸 Pago a Proveedor", "📋 Estado de Cuenta"])
    
    with tab_reg:
        st.subheader("Registrar Compra Manual")
        c1, c2 = st.columns(2)
        with c1:
            f_c = st.date_input("Fecha", datetime.now())
            r_p = st.text_input("RUT Proveedor")
            n_p = st.text_input("Razón Social")
            cta_g = st.selectbox("Gasto", obtener_subcuentas("Gastos") or ["Gastos Generales"])
            cc_p = st.selectbox("Centro de Costo", LISTA_CENTROS_COSTO)
            g_c = st.text_input("Detalle")
        with c2:
            neto_c = st.number_input("Monto Neto ($)", min_value=0.0, step=100.0)
            iva_c = round(neto_c * 0.19, 2)
            tot_c = round(neto_c + iva_c, 2)
            st.metric("IVA (19%)", f"${iva_c:,.0f}")
            st.metric("Total", f"${tot_c:,.0f}")
            
        if st.button("Guardar Compra"):
            if r_p and neto_c > 0:
                cursor = conn.cursor()
                cursor.execute("SELECT id FROM proveedores WHERE rut = ?", (r_p,))
                res = cursor.fetchone()
                p_id = res[0] if res else cursor.execute("INSERT INTO proveedores (rut, nombre) VALUES (?, ?)", (r_p, n_p)).lastrowid
                
                cursor.execute("INSERT INTO compras (fecha, proveedor_id, cuenta_gasto, centro_costo, monto_neto, iva, monto_total, glosa) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (str(f_c), p_id, cta_g, cc_p, neto_c, iva_c, tot_c, g_c))
                cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa, centro_costo) VALUES (?, ?, ?, 0, ?, ?)", (str(f_c), cta_g, neto_c, f"Compra {n_p}", cc_p))
                cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa, centro_costo) VALUES (?, 'IVA Crédito Fiscal', ?, 0, ?, ?)", (str(f_c), iva_c, f"IVA Compra {n_p}", cc_p))
                cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa, centro_costo) VALUES (?, 'Cuentas por Pagar Proveedores', 0, ?, ?, ?)", (str(f_c), tot_c, f"Compra {n_p}", cc_p))
                conn.commit()
                st.success("¡Compra registrada!")

    with tab_pago:
        st.subheader("Registrar Pago")
        df_prov = pd.read_sql_query("SELECT id, rut, nombre FROM proveedores", conn)
        if not df_prov.empty:
            p_sel = st.selectbox("Proveedor", df_prov['rut'] + " - " + df_prov['nombre'])
            pid = df_prov[df_prov['rut'] == p_sel.split(" - ")[0]]['id'].values[0]
            f_pag = st.date_input("Fecha Pago", datetime.now(), key="fp")
            m_pag = st.number_input("Monto ($)", min_value=0.0, step=100.0)
            if st.button("Registrar Pago"):
                if m_pag > 0:
                    cursor = conn.cursor()
                    cursor.execute("INSERT INTO pagos (fecha, proveedor_id, monto) VALUES (?, ?, ?)", (str(f_pag), pid, m_pag))
                    cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?, 'Cuentas por Pagar Proveedores', ?, 0, ?)", (str(f_pag), m_pag, f"Pago a {p_sel}"))
                    cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?, 'Banco', 0, ?, ?)", (str(f_pag), m_pag, f"Pago a {p_sel}"))
                    conn.commit()
                    st.success("¡Pago registrado!")

    with tab_rep:
        st.subheader("📑 Estado de Cuenta del Proveedor (Cartola)")
        st.caption("Muestra el historial cronológico de compras (Cargos) y pagos (Abonos) para calcular la deuda viva.")
        if 'df_prov' in locals() and not df_prov.empty:
            prov_rep = st.selectbox("Seleccionar Proveedor", df_prov['rut'] + " - " + df_prov['nombre'], key="rep_p")
            p_id_rep = df_prov[df_prov['rut'] == prov_rep.split(" - ")[0]]['id'].values[0]
            
            c_f1, c_f2 = st.columns(2)
            with c_f1: f_ini = st.date_input("Desde", datetime(2026, 1, 1), key="fi_p")
            with c_f2: f_fin = st.date_input("Hasta", datetime.now(), key="ff_p")
            
            # Extraer Compras (Aumentan deuda)
            df_c = pd.read_sql_query("SELECT fecha, 'Factura Compra' as Documento, glosa as Detalle, monto_total as Cargo, 0 as Abono FROM compras WHERE proveedor_id = ? AND fecha BETWEEN ? AND ?", conn, params=(p_id_rep, str(f_ini), str(f_fin)))
            # Extraer Pagos (Disminuyen deuda)
            df_p = pd.read_sql_query("SELECT fecha, 'Pago Emitido' as Documento, 'Abono a deuda' as Detalle, 0 as Cargo, monto as Abono FROM pagos WHERE proveedor_id = ? AND fecha BETWEEN ? AND ?", conn, params=(p_id_rep, str(f_ini), str(f_fin)))
            
            df_estado = pd.concat([df_c, df_p]).sort_values(by='fecha').reset_index(drop=True)
            
            if not df_estado.empty:
                df_estado['Saldo Deuda ($)'] = df_estado['Cargo'].cumsum() - df_estado['Abono'].cumsum()
                st.dataframe(df_estado, use_container_width=True)
                
                saldo_final = df_estado['Saldo Deuda ($)'].iloc[-1]
                st.metric(f"Saldo Pendiente por Pagar a {prov_rep.split(' - ')[1]}", f"${saldo_final:,.0f}")
                
                csv = df_estado.to_csv(index=False).encode('utf-8')
                st.download_button("📥 Descargar Estado de Cuenta (.csv)", data=csv, file_name=f"estado_cuenta_prov_{prov_rep.split(' - ')[0]}.csv", mime="text/csv")
            else:
                st.info("No hay movimientos en este rango de fechas.")

elif opcion == "📈 Módulo de Clientes":
    st.header("📈 Módulo de Clientes y Cuentas por Cobrar")
    
    tab_reg_v, tab_cobro, tab_rep_v = st.tabs(["📈 Factura de Venta", "💰 Recibir Cobro", "📋 Estado de Cuenta"])
    
    with tab_reg_v:
        st.subheader("Registrar Venta Manual")
        c1, c2 = st.columns(2)
        with c1:
            f_v = st.date_input("Fecha", datetime.now(), key="fv")
            r_cl = st.text_input("RUT Cliente")
            n_cl = st.text_input("Razón Social")
            cta_i = st.selectbox("Ingreso", obtener_subcuentas("Ingresos") or ["Ingresos por Ventas"])
            g_v = st.text_input("Detalle")
        with c2:
            neto_v = st.number_input("Monto Neto ($)", min_value=0.0, step=100.0)
            iva_v = round(neto_v * 0.19, 2)
            tot_v = round(neto_v + iva_v, 2)
            st.metric("IVA (19%)", f"${iva_v:,.0f}")
            st.metric("Total", f"${tot_v:,.0f}")
            
        if st.button("Guardar Venta"):
            if r_cl and neto_v > 0:
                cursor = conn.cursor()
                cursor.execute("SELECT id FROM clientes WHERE rut = ?", (r_cl,))
                res = cursor.fetchone()
                cid = res[0] if res else cursor.execute("INSERT INTO clientes (rut, nombre) VALUES (?, ?)", (r_cl, n_cl)).lastrowid
                
                cursor.execute("INSERT INTO ventas (fecha, cliente_id, cuenta_ingreso, monto_neto, iva, monto_total, glosa) VALUES (?, ?, ?, ?, ?, ?, ?)", (str(f_v), cid, cta_i, neto_v, iva_v, tot_v, g_v))
                cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?, 'Cuentas por Cobrar Clientes', ?, 0, ?)", (str(f_v), tot_v, f"Venta {n_cl}"))
                cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?, ?, 0, ?, ?)", (str(f_v), cta_i, neto_v, f"Venta {n_cl}"))
                cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?, 'IVA Débito Fiscal', 0, ?, ?)", (str(f_v), iva_v, f"IVA Venta {n_cl}"))
                conn.commit()
                st.success("¡Venta registrada!")

    with tab_cobro:
        st.subheader("Registrar Cobro")
        df_cli = pd.read_sql_query("SELECT id, rut, nombre FROM clientes", conn)
        if not df_cli.empty:
            c_sel = st.selectbox("Cliente", df_cli['rut'] + " - " + df_cli['nombre'])
            cid = df_cli[df_cli['rut'] == c_sel.split(" - ")[0]]['id'].values[0]
            f_cob = st.date_input("Fecha Cobro", datetime.now(), key="fc_c")
            m_cob = st.number_input("Monto ($)", min_value=0.0, step=100.0, key="mc")
            if st.button("Registrar Cobro"):
                if m_cob > 0:
                    cursor = conn.cursor()
                    cursor.execute("INSERT INTO cobros (fecha, cliente_id, monto) VALUES (?, ?, ?)", (str(f_cob), cid, m_cob))
                    cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?, 'Banco', ?, 0, ?)", (str(f_cob), m_cob, f"Cobro a {c_sel}"))
                    cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?, 'Cuentas por Cobrar Clientes', 0, ?, ?)", (str(f_cob), m_cob, f"Cobro a {c_sel}"))
                    conn.commit()
                    st.success("¡Cobro registrado!")

    with tab_rep_v:
        st.subheader("📑 Estado de Cuenta del Cliente (Cartola)")
        st.caption("Muestra el historial cronológico de facturas emitidas (Cargos) y cobros recibidos (Abonos) para calcular lo que nos deben.")
        if 'df_cli' in locals() and not df_cli.empty:
            cli_rep = st.selectbox("Seleccionar Cliente", df_cli['rut'] + " - " + df_cli['nombre'], key="rep_c")
            c_id_rep = df_cli[df_cli['rut'] == cli_rep.split(" - ")[0]]['id'].values[0]
            
            c_f1, c_f2 = st.columns(2)
            with c_f1: f_ini_c = st.date_input("Desde", datetime(2026, 1, 1), key="fi_c")
            with c_f2: f_fin_c = st.date_input("Hasta", datetime.now(), key="ff_c")
            
            # Extraer Ventas (Aumentan deuda del cliente a nosotros)
            df_v = pd.read_sql_query("SELECT fecha, 'Factura Venta' as Documento, glosa as Detalle, monto_total as Cargo, 0 as Abono FROM ventas WHERE cliente_id = ? AND fecha BETWEEN ? AND ?", conn, params=(c_id_rep, str(f_ini_c), str(f_fin_c)))
            # Extraer Cobros (Disminuyen deuda del cliente a nosotros)
            df_cb = pd.read_sql_query("SELECT fecha, 'Cobro Recibido' as Documento, 'Abono a deuda' as Detalle, 0 as Cargo, monto as Abono FROM cobros WHERE cliente_id = ? AND fecha BETWEEN ? AND ?", conn, params=(c_id_rep, str(f_ini_c), str(f_fin_c)))
            
            df_estado_c = pd.concat([df_v, df_cb]).sort_values(by='fecha').reset_index(drop=True)
            
            if not df_estado_c.empty:
                df_estado_c['Saldo por Cobrar ($)'] = df_estado_c['Cargo'].cumsum() - df_estado_c['Abono'].cumsum()
                st.dataframe(df_estado_c, use_container_width=True)
                
                saldo_final_c = df_estado_c['Saldo por Cobrar ($)'].iloc[-1]
                st.metric(f"Saldo Pendiente por Cobrar a {cli_rep.split(' - ')[1]}", f"${saldo_final_c:,.0f}")
                
                csv_c = df_estado_c.to_csv(index=False).encode('utf-8')
                st.download_button("📥 Descargar Estado de Cuenta (.csv)", data=csv_c, file_name=f"estado_cuenta_cli_{cli_rep.split(' - ')[0]}.csv", mime="text/csv")
            else:
                st.info("No hay movimientos en este rango de fechas.")

# ... (El resto de los módulos de la aplicación [Bancos, Libro Diario, Reportes, etc.] permanecen exactamente igual que en la versión anterior).

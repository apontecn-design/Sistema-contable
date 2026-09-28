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
            ("1.2.01.01", "Equipos de Computación", "Real", "Activo", "1.2.01", 3),
            ("1.2.01.02", "Muebles y Enseres", "Real", "Activo", "1.2.01", 3),
            
            ("2", "PASIVO", "Real", "Pasivo", None, 1),
            ("2.1", "Pasivo Corriente", "Real", "Pasivo", "2", 2),
            ("2.1.01", "Cuentas Comerciales y Otras Cuentas por Pagar", "Real", "Pasivo", "2.1", 2),
            ("2.1.01.01", "Cuentas por Pagar Proveedores", "Real", "Pasivo", "2.1.01", 3),
            ("2.1.01.02", "IVA Débito Fiscal", "Real", "Pasivo", "2.1.01", 3),
            ("2.1.01.03", "Retenciones e Impuestos por Pagar", "Real", "Pasivo", "2.1.01", 3),
            
            ("3", "PATRIMONIO", "Real", "Patrimonio", None, 1),
            ("3.1", "Patrimonio Neto", "Real", "Patrimonio", "3", 2),
            ("3.1.01", "Capital Social", "Real", "Patrimonio", "3.1", 3),
            ("3.1.02", "Resultados Acumulados", "Real", "Patrimonio", "3.1", 3),
            
            ("4", "INGRESOS", "Nominal", "Ingresos", None, 1),
            ("4.1", "Ingresos de Actividades Ordinarias", "Nominal", "Ingresos", "4", 2),
            ("4.1.01", "Ingresos por Ventas", "Nominal", "Ingresos", "4.1", 3),
            ("4.1.02", "Ingresos por Servicios", "Nominal", "Ingresos", "4.1", 3),
            
            ("5", "COSTOS Y GASTOS", "Nominal", "Gastos", None, 1),
            ("5.1", "Costo de Ventas", "Nominal", "Gastos", "5", 2),
            ("5.1.01", "Costo de Ventas", "Nominal", "Gastos", "5.1", 3),
            ("5.2", "Gastos de Administración y Ventas", "Nominal", "Gastos", "5", 2),
            ("5.2.01", "Gastos Generales", "Nominal", "Gastos", "5.2", 3),
            ("5.2.02", "Gastos de Arriendo", "Nominal", "Gastos", "5.2", 3),
            ("5.2.03", "Gastos de Servicios Básicos", "Nominal", "Gastos", "5.2", 3),
            ("5.2.04", "Remuneraciones y Honorarios", "Nominal", "Gastos", "5.2", 3)
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

def leer_csv_sii(uploaded_file):
    bytes_data = uploaded_file.getvalue()
    for enc in ['utf-8', 'latin1', 'cp1252', 'iso-8859-1']:
        for sep in [';', ',', '\t']:
            try:
                df = pd.read_csv(io.BytesIO(bytes_data), encoding=enc, sep=sep)
                if len(df.columns) > 1:
                    df.columns = [str(col).strip() for col in df.columns]
                    return df
            except Exception:
                continue
    return None

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
            f_c = st.date_input("Fecha", datetime.now(), key="fc_p")
            r_p = st.text_input("RUT Proveedor", key="rp_p")
            n_p = st.text_input("Razón Social", key="np_p")
            cta_g = st.selectbox("Gasto", obtener_subcuentas("Gastos") or ["Gastos Generales"], key="ctap_p")
            cc_p = st.selectbox("Centro de Costo", LISTA_CENTROS_COSTO, key="cc_p")
            g_c = st.text_input("Detalle", key="gp_p")
        with c2:
            neto_c = st.number_input("Monto Neto ($)", min_value=0.0, step=100.0, key="netop_p")
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
            p_sel = st.selectbox("Proveedor", df_prov['rut'] + " - " + df_prov['nombre'], key="psel_p")
            pid = df_prov[df_prov['rut'] == p_sel.split(" - ")[0]]['id'].values[0]
            f_pag = st.date_input("Fecha Pago", datetime.now(), key="fp_p")
            m_pag = st.number_input("Monto ($)", min_value=0.0, step=100.0, key="mp_p")
            if st.button("Registrar Pago"):
                if m_pag > 0:
                    cursor = conn.cursor()
                    cursor.execute("INSERT INTO pagos (fecha, proveedor_id, monto) VALUES (?, ?, ?)", (str(f_pag), pid, m_pag))
                    cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?, 'Cuentas por Pagar Proveedores', ?, 0, ?)", (str(f_pag), m_pag, f"Pago a {p_sel}"))
                    cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?, 'Banco', 0, ?, ?)", (str(f_pag), m_pag, f"Pago a {p_sel}"))
                    conn.commit()
                    st.success("¡Pago registrado!")
        else:
            st.info("No hay proveedores registrados.")

    with tab_rep:
        st.subheader("📑 Estado de Cuenta del Proveedor (Cartola)")
        st.caption("Muestra el historial cronológico de compras (Cargos) y pagos (Abonos) para calcular la deuda viva.")
        df_prov_rep = pd.read_sql_query("SELECT id, rut, nombre FROM proveedores", conn)
        if not df_prov_rep.empty:
            prov_rep = st.selectbox("Seleccionar Proveedor", df_prov_rep['rut'] + " - " + df_prov_rep['nombre'], key="rep_p")
            p_id_rep = df_prov_rep[df_prov_rep['rut'] == prov_rep.split(" - ")[0]]['id'].values[0]
            
            c_f1, c_f2 = st.columns(2)
            with c_f1: f_ini = st.date_input("Desde", datetime(2026, 1, 1), key="fi_p")
            with c_f2: f_fin = st.date_input("Hasta", datetime.now(), key="ff_p")
            
            df_c = pd.read_sql_query("SELECT fecha, 'Factura Compra' as Documento, glosa as Detalle, monto_total as Cargo, 0 as Abono FROM compras WHERE proveedor_id = ? AND fecha BETWEEN ? AND ?", conn, params=(p_id_rep, str(f_ini), str(f_fin)))
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
        else:
            st.info("No hay proveedores registrados.")

elif opcion == "📈 Módulo de Clientes":
    st.header("📈 Módulo de Clientes y Cuentas por Cobrar")
    
    tab_reg_v, tab_cobro, tab_rep_v = st.tabs(["📈 Factura de Venta", "💰 Recibir Cobro", "📋 Estado de Cuenta"])
    
    with tab_reg_v:
        st.subheader("Registrar Venta Manual")
        c1, c2 = st.columns(2)
        with c1:
            f_v = st.date_input("Fecha", datetime.now(), key="fv_c")
            r_cl = st.text_input("RUT Cliente", key="rc_c")
            n_cl = st.text_input("Razón Social", key="nc_c")
            cta_i = st.selectbox("Ingreso", obtener_subcuentas("Ingresos") or ["Ingresos por Ventas"], key="ctai_c")
            g_v = st.text_input("Detalle", key="gv_c")
        with c2:
            neto_v = st.number_input("Monto Neto ($)", min_value=0.0, step=100.0, key="netov_c")
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
            c_sel = st.selectbox("Cliente", df_cli['rut'] + " - " + df_cli['nombre'], key="csel_c")
            cid = df_cli[df_cli['rut'] == c_sel.split(" - ")[0]]['id'].values[0]
            f_cob = st.date_input("Fecha Cobro", datetime.now(), key="fc_c")
            m_cob = st.number_input("Monto ($)", min_value=0.0, step=100.0, key="mc_c")
            if st.button("Registrar Cobro"):
                if m_cob > 0:
                    cursor = conn.cursor()
                    cursor.execute("INSERT INTO cobros (fecha, cliente_id, monto) VALUES (?, ?, ?)", (str(f_cob), cid, m_cob))
                    cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?, 'Banco', ?, 0, ?)", (str(f_cob), m_cob, f"Cobro a {c_sel}"))
                    cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa) VALUES (?, 'Cuentas por Cobrar Clientes', 0, ?, ?)", (str(f_cob), m_cob, f"Cobro a {c_sel}"))
                    conn.commit()
                    st.success("¡Cobro registrado!")
        else:
            st.info("No hay clientes registrados.")

    with tab_rep_v:
        st.subheader("📑 Estado de Cuenta del Cliente (Cartola)")
        st.caption("Muestra el historial cronológico de facturas emitidas (Cargos) y cobros recibidos (Abonos) para calcular lo que nos deben.")
        df_cli_rep = pd.read_sql_query("SELECT id, rut, nombre FROM clientes", conn)
        if not df_cli_rep.empty:
            cli_rep = st.selectbox("Seleccionar Cliente", df_cli_rep['rut'] + " - " + df_cli_rep['nombre'], key="rep_c")
            c_id_rep = df_cli_rep[df_cli_rep['rut'] == cli_rep.split(" - ")[0]]['id'].values[0]
            
            c_f1, c_f2 = st.columns(2)
            with c_f1: f_ini_c = st.date_input("Desde", datetime(2026, 1, 1), key="fi_c")
            with c_f2: f_fin_c = st.date_input("Hasta", datetime.now(), key="ff_c")
            
            df_v = pd.read_sql_query("SELECT fecha, 'Factura Venta' as Documento, glosa as Detalle, monto_total as Cargo, 0 as Abono FROM ventas WHERE cliente_id = ? AND fecha BETWEEN ? AND ?", conn, params=(c_id_rep, str(f_ini_c), str(f_fin_c)))
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
        else:
            st.info("No hay clientes registrados.")

elif opcion == "📥 Carga Masiva / Importar":
    st.header("📥 Carga Masiva e Importación de Archivos")
    
    tab_sii, tab_saldos, tab_asientos = st.tabs([
        "📄 RCV del SII", 
        "📊 Matriz Saldos Iniciales / Asientos Masivos", 
        "📖 Asientos Manuales / Históricos"
    ])
    
    with tab_sii:
        st.subheader("Importar Resumen / Detalle RCV del SII")
        tipo_rcv = st.selectbox("Tipo de Registro:", ["Ventas (Clientes)", "Compras (Proveedores)"])
        file_rcv = st.file_uploader("Selecciona el archivo CSV del SII", type=["csv", "txt"])
        if file_rcv is not None:
            df_sii = leer_csv_sii(file_rcv)
            if df_sii is not None:
                st.success(f"¡Archivo leído con éxito! {len(df_sii)} registros encontrados.")
                st.dataframe(df_sii.head(5), use_container_width=True)

    with tab_saldos:
        st.subheader("Carga Masiva de Saldos Iniciales o Asientos en Excel/CSV")
        st.caption("Sube un archivo estructurado con las columnas obligatorias: fecha, cuenta, debe, haber, glosa")
        
        plantilla_saldos = pd.DataFrame([
            {"fecha": "2026-01-02", "cuenta": "Banco", "debe": 5000000, "haber": 0, "glosa": "Saldo inicial Banco"},
            {"fecha": "2026-01-02", "cuenta": "Capital Social", "debe": 0, "haber": 5000000, "glosa": "Aporte inicial capital"}
        ])
        csv_matriz = plantilla_saldos.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Descargar Matriz Modelo para Carga Masiva (.csv)", data=csv_matriz, file_name="matriz_saldos_iniciales.csv", mime="text/csv")
        
        file_matriz = st.file_uploader("Sube tu matriz completada (.csv)", type=["csv"], key="matriz_up")
        if file_matriz is not None:
            df_matriz = pd.read_csv(file_matriz)
            st.dataframe(df_matriz, use_container_width=True)
            t_debe = df_matriz['debe'].sum()
            t_haber = df_matriz['haber'].sum()
            
            c1, c2 = st.columns(2)
            c1.metric("Total Debe", f"${t_debe:,.0f}")
            c2.metric("Total Haber", f"${t_haber:,.0f}")
            
            if abs(t_debe - t_haber) < 0.01:
                st.success("✅ La matriz está perfectamente cuadrada (Debe = Haber)")
                if st.button("🚀 Importar Masivamente al Libro Diario"):
                    cursor = conn.cursor()
                    for _, r in df_matriz.iterrows():
                        cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa, centro_costo) VALUES (?, ?, ?, ?, ?, 'General / Ninguno')",
                                       (str(r['fecha']), str(r['cuenta']), float(r['debe']), float(r['haber']), str(r['glosa'])))
                    conn.commit()
                    st.success("¡Saldos iniciales y asientos importados exitosamente!")
            else:
                st.error("❌ La matriz está descuadrada. El Debe debe igualar al Haber.")

    with tab_asientos:
        st.subheader("Carga de Lotes de Asientos Manuales")
        file_as = st.file_uploader("Subir Archivo Asientos", type=["csv"], key="as_up")
        if file_as is not None:
            df_a = pd.read_csv(file_as)
            st.dataframe(df_a, use_container_width=True)

elif opcion == "📋 Plan de Cuentas":
    st.header("📋 Plan de Cuentas (Normativa Chilena)")
    df_pc = pd.read_sql_query("SELECT codigo as 'Código', nombre as 'Nombre', categoria as 'Categoría', tipo as 'Tipo' FROM plan_cuentas ORDER BY codigo", conn)
    st.dataframe(df_pc, use_container_width=True)

elif opcion == "✏️ Registrar Asiento Manual":
    st.header("✏️ Registrar Asiento Contable Manual (Partida Doble)")
    lista_cuentas = obtener_subcuentas()
    
    fecha_m = st.date_input("Fecha", datetime.now())
    glosa_m = st.text_input("Glosa del Asiento", "Asiento manual")
    cc_m = st.selectbox("Centro de Costo", LISTA_CENTROS_COSTO)
    
    c1, c2 = st.columns(2)
    with c1:
        cuenta_debe = st.selectbox("Cuenta al Debe", lista_cuentas, key="d")
        monto_debe = st.number_input("Monto Debe ($)", min_value=0.0, step=100.0, key="md")
    with c2:
        cuenta_haber = st.selectbox("Cuenta al Haber", lista_cuentas, key="h")
        monto_haber = st.number_input("Monto Haber ($)", min_value=0.0, step=100.0, key="mh")
        
    st.markdown("---")
    st.subheader("👁️ Vista Previa del Asiento Contable")
    if monto_debe > 0 or monto_haber > 0:
        df_preview = pd.DataFrame([
            {"Fecha": str(fecha_m), "Cuenta / Subcuenta": cuenta_debe, "Debe ($)": monto_debe, "Haber ($)": 0.0, "Glosa": glosa_m, "Centro Costo": cc_m},
            {"Fecha": str(fecha_m), "Cuenta / Subcuenta": cuenta_haber, "Debe ($)": 0.0, "Haber ($)": monto_haber, "Glosa": glosa_m, "Centro Costo": cc_m}
        ])
        st.dataframe(df_preview, use_container_width=True)
        
        if monto_debe == monto_haber:
            st.success("✅ Asiento cuadrado y listo para registrar.")
        else:
            st.error(f"❌ Descuadrado por ${abs(monto_debe - monto_haber):,.0f}")

    if st.button("Registrar y Guardar Asiento"):
        if monto_debe > 0 and monto_debe == monto_haber:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa, centro_costo) VALUES (?, ?, ?, 0, ?, ?)", (str(fecha_m), cuenta_debe, monto_debe, glosa_m, cc_m))
            cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa, centro_costo) VALUES (?, ?, 0, ?, ?, ?)", (str(fecha_m), cuenta_haber, monto_haber, glosa_m, cc_m))
            conn.commit()
            st.success("¡Asiento guardado correctamente en el Libro Diario!")
        else:
            st.error("Verifica que los montos sean iguales y mayores a cero.")

elif opcion == "🏦 Bancos y Cartola":
    st.header("🏦 Gestión de Bancos y Movimientos Manuales")
    
    with st.form("form_banco_manual"):
        st.subheader("Registrar Movimiento Bancario Manual")
        fb = st.date_input("Fecha", datetime.now())
        tipo_mov = st.selectbox("Tipo de Movimiento", ["Débito (Egreso / Comisión / Retiro)", "Crédito (Depósito / Abono)"])
        monto_b = st.number_input("Monto ($)", min_value=0.0, step=100.0)
        glosa_b = st.text_input("Glosa / Detalle")
        btn_mb = st.form_submit_button("Registrar en Banco y Libro Diario")
        if btn_mb:
            if monto_b > 0:
                cursor = conn.cursor()
                cursor.execute("INSERT INTO bancos_movimientos (fecha, tipo, monto, glosa) VALUES (?, ?, ?, ?)", (str(fb), tipo_mov, monto_b, glosa_b))
                if "Débito" in tipo_mov:
                    cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa, centro_costo) VALUES (?, 'Gastos Generales', ?, 0, ?, 'General / Ninguno')", (str(fb), monto_b, glosa_b))
                    cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa, centro_costo) VALUES (?, 'Banco', 0, ?, ?, 'General / Ninguno')", (str(fb), monto_b, glosa_b))
                else:
                    cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa, centro_costo) VALUES (?, 'Banco', ?, 0, ?, 'General / Ninguno')", (str(fb), monto_b, glosa_b))
                    cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa, centro_costo) VALUES (?, 'Otros Ingresos', 0, ?, ?, 'General / Ninguno')", (str(fb), monto_b, glosa_b))
                conn.commit()
                st.success("¡Movimiento bancario registrado e integrado al Libro Diario!")

    st.markdown("---")
    st.subheader("Historial de Movimientos Bancarios")
    df_bm = pd.read_sql_query("SELECT * FROM bancos_movimientos ORDER BY id DESC", conn)
    if not df_bm.empty:
        st.dataframe(df_bm, use_container_width=True)

elif opcion == "📖 Libro Diario (Contabilidad)":
    st.header("📖 Libro Diario Contable y Filtros por Cuenta")
    
    lista_cuentas = obtener_subcuentas()
    cuenta_filtro = st.selectbox("Filtrar Libro Diario por Cuenta o Subcuenta específica:", ["Todas las cuentas"] + lista_cuentas)
    
    if cuenta_filtro == "Todas las cuentas":
        df_ld = pd.read_sql_query("SELECT * FROM libro_diario ORDER BY id DESC", conn)
    else:
        df_ld = pd.read_sql_query("SELECT * FROM libro_diario WHERE cuenta = ? ORDER BY id DESC", conn, params=(cuenta_filtro,))
        
    if not df_ld.empty:
        st.dataframe(df_ld, use_container_width=True)
        t_d = df_ld['debe'].sum()
        t_h = df_ld['haber'].sum()
        c1, c2 = st.columns(2)
        c1.metric("Total Debe Filtrado", f"${t_d:,.0f}")
        c2.metric("Total Haber Filtrado", f"${t_h:,.0f}")
    else:
        st.info("No hay registros para la cuenta seleccionada.")

elif opcion == "📊 Reportes Financieros (Norma Chile)":
    st.header("📊 Reportes y Balances Financieros (CMF / IFRS)")
    
    tab_er, tab_esf, tab_bc = st.tabs(["Estado de Resultados", "Estado de Situación Financiera", "Balance de Comprobación"])
    
    with tab_er:
        st.subheader("Estado de Resultados Integral (Por Función)")
        df_er_data = pd.read_sql_query("""
            SELECT l.cuenta, p.tipo, SUM(l.haber) - SUM(l.debe) as saldo_ingreso, SUM(l.debe) - SUM(l.haber) as saldo_gasto
            FROM libro_diario l
            LEFT JOIN plan_cuentas p ON l.cuenta = p.nombre
            WHERE p.categoria = 'Nominal'
            GROUP BY l.cuenta, p.tipo
        """, conn)
        
        ingresos, costos, gastos = 0.0, 0.0, 0.0
        for _, row in df_er_data.iterrows():
            if row['tipo'] == 'Ingresos': ingresos += row['saldo_ingreso']
            elif 'Costo' in row['cuenta']: costos += row['saldo_gasto']
            else: gastos += row['saldo_gasto']
            
        margen = ingresos - costos
        resultado = margen - gastos
        st.markdown(f"* **(+) Ingresos Ordinarios:** ${ingresos:,.0f}")
        st.markdown(f"* **(-) Costo de Ventas:** ${costos:,.0f}")
        st.markdown(f"### = Margen Bruto: ${margen:,.0f}")
        st.markdown(f"* **(-) Gastos Operacionales:** ${gastos:,.0f}")
        st.markdown(f"### 🇨🇱 Resultado del Ejercicio: ${resultado:,.0f}")

    with tab_esf:
        st.subheader("Estado de Situación Financiera (Balance General Clasificado)")
        df_esf_data = pd.read_sql_query("""
            SELECT l.cuenta, p.tipo, SUM(l.debe) - SUM(l.haber) as deudor, SUM(l.haber) - SUM(l.debe) as acreedor
            FROM libro_diario l
            LEFT JOIN plan_cuentas p ON l.cuenta = p.nombre
            WHERE p.categoria = 'Real'
            GROUP BY l.cuenta, p.tipo
        """, conn)
        
        act_corr, act_nocorr, pas_corr, pat = 0.0, 0.0, 0.0, 0.0
        for _, row in df_esf_data.iterrows():
            s = row['deudor'] if row['deudor'] > 0 else 0.0
            if row['tipo'] == 'Activo':
                if 'Propiedades' in row['cuenta']: act_nocorr += s
                else: act_corr += s
            elif row['tipo'] == 'Pasivo': pas_corr += row['acreedor']
            elif row['tipo'] == 'Patrimonio': pat += row['acreedor']
            
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("#### 🏛️ ACTIVOS")
            st.text(f"Activo Corriente: ${act_corr:,.0f}")
            st.text(f"Activo No Corriente: ${act_nocorr:,.0f}")
            st.markdown(f"**Total Activos:** ${act_corr + act_nocorr:,.0f}")
        with c2:
            st.markdown("#### 📉 PASIVOS Y PATRIMONIO")
            st.text(f"Pasivo Corriente: ${pas_corr:,.0f}")
            st.text(f"Patrimonio Neto: ${pat:,.0f}")
            st.markdown(f"**Total Pasivo + Patrimonio:** ${pas_corr + pat:,.0f}")

    with tab_bc:
        st.subheader("Balance de Comprobación y Saldos (Sumas y Saldos)")
        df_bc = pd.read_sql_query("""
            SELECT l.cuenta as 'Subcuenta', p.tipo as 'Tipo', 
                   SUM(l.debe) as Total_Debe, SUM(l.haber) as Total_Haber,
                   CASE WHEN SUM(l.debe) > SUM(l.haber) THEN SUM(l.debe) - SUM(l.haber) ELSE 0 END as Saldo_Deudor,
                   CASE WHEN SUM(l.haber) > SUM(l.debe) THEN SUM(l.haber) - SUM(l.debe) ELSE 0 END as Saldo_Acreedor
            FROM libro_diario l
            LEFT JOIN plan_cuentas p ON l.cuenta = p.nombre
            GROUP BY l.cuenta
        """, conn)
        if not df_bc.empty:
            st.dataframe(df_bc, use_container_width=True)
            st.metric("Total Sumas Debe", f"${df_bc['Total_Debe'].sum():,.0f}")
            st.metric("Total Sumas Haber", f"${df_bc['Total_Haber'].sum():,.0f}")

conn.close()

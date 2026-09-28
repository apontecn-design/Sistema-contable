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
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS proveedores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        rut TEXT UNIQUE,
        nombre TEXT,
        cuenta_defecto TEXT,
        centro_costo TEXT
    )""")
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS compras (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fecha TEXT,
        proveedor_id INTEGER,
        cuenta_gasto TEXT,
        centro_costo TEXT,
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
        glosa TEXT,
        centro_costo TEXT
    )""")
    
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
            # BALANCE CLASIFICADO CHILE (ACTIVOS)
            ("1", "ACTIVO", "Real", "Activo", None, 1),
            ("1.1", "Activo Corriente", "Real", "Activo", "1", 2),
            ("1.1.01", "Efectivo y Equivalentes al Efectivo", "Real", "Activo", "1.1", 3),
            ("1.1.01.01", "Banco", "Real", "Activo", "1.1.01", 3),
            ("1.1.01.02", "Caja General", "Real", "Activo", "1.1.01", 3),
            ("1.1.02", "Otros Activos Financieros Corrientes", "Real", "Activo", "1.1", 2),
            ("1.1.03", "Cuentas Comerciales y Otras Cuentas por Cobrar", "Real", "Activo", "1.1", 2),
            ("1.1.03.01", "Cuentas por Cobrar Clientes", "Real", "Activo", "1.1.03", 3),
            ("1.1.03.02", "IVA Crédito Fiscal", "Real", "Activo", "1.1.03", 3),
            ("1.2", "Activo No Corriente", "Real", "Activo", "1", 2),
            ("1.2.01", "Propiedades, Planta y Equipo", "Real", "Activo", "1.2", 2),
            ("1.2.01.01", "Equipos de Computación", "Real", "Activo", "1.2.01", 3),
            ("1.2.01.02", "Muebles y Enseres", "Real", "Activo", "1.2.01", 3),
            
            # BALANCE CLASIFICADO CHILE (PASIVOS Y PATRIMONIO)
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
            
            # ESTADO DE RESULTADOS CLASIFICADO CHILE (FUNCIÓN)
            ("4", "INGRESOS", "Nominal", "Ingresos", None, 1),
            ("4.1", "Ingresos de Actividades Ordinarias", "Nominal", "Ingresos", "4", 2),
            ("4.1.01", "Ingresos por Ventas", "Nominal", "Ingresos", "4.1", 3),
            ("4.1.02", "Ingresos por Servicios", "Nominal", "Ingresos", "4.1", 3),
            ("4.2", "Otros Ingresos, por Función", "Nominal", "Ingresos", "4", 2),
            ("4.2.01", "Otros Ingresos", "Nominal", "Ingresos", "4.2", 3),
            
            ("5", "COSTOS Y GASTOS", "Nominal", "Gastos", None, 1),
            ("5.1", "Costo de Ventas", "Nominal", "Gastos", "5", 2),
            ("5.1.01", "Costo de Ventas", "Nominal", "Gastos", "5.1", 3),
            ("5.2", "Gastos de Administración y Ventas", "Nominal", "Gastos", "5", 2),
            ("5.2.01", "Gastos Generales", "Nominal", "Gastos", "5.2", 3),
            ("5.2.02", "Gastos de Arriendo", "Nominal", "Gastos", "5.2", 3),
            ("5.2.03", "Gastos de Servicios Básicos", "Nominal", "Gastos", "5.2", 3),
            ("5.2.04", "Remuneraciones y Honorarios", "Nominal", "Gastos", "5.2", 3),
            ("5.2.05", "Gastos de Publicidad y Marketing", "Nominal", "Gastos", "5.2", 3)
        ]
        cursor.executemany("""
            INSERT INTO plan_cuentas (codigo, nombre, categoria, tipo, padre_codigo, nivel) 
            VALUES (?, ?, ?, ?, ?, ?)
        """, cat_inicial)

    conn.commit()
    conn.close()

init_db()

st.sidebar.title("📌 Menú Principal")
opcion = st.sidebar.radio(
    "Selecciona un Módulo:",
    [
        "Inicio / Resumen",
        "📥 Carga Masiva / Importar",
        "🏢 Maestro de Proveedores y Reglas",
        "📋 Plan de Cuentas",
        "✏️ Registrar Asiento Manual",
        "Registrar Compra Proveedor",
        "Registrar Pago Proveedor",
        "Registrar Venta Cliente",
        "Registrar Cobro Cliente",
        "Cartola Bancaria y Saldos",
        "Libro Diario (Contabilidad)",
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
    st.info("Utiliza el menú lateral para administrar tu maestro de proveedores, realizar cargas masivas y emitir reportes financieros ajustados a la normativa chilena.")

elif opcion == "🏢 Maestro de Proveedores y Reglas":
    st.header("🏢 Maestro de Proveedores y Reglas de Imputación")
    st.caption("Configura la cuenta de gasto y centro de costo predeterminado para la automatización de tus compras.")
    
    cuentas_gastos = obtener_subcuentas("Gastos") or ["Gastos Generales"]
    
    # Formulario para registrar proveedor manual si la lista está vacía
    with st.expander("➕ Registrar Nuevo Proveedor Manualmente", expanded=False):
        with st.form("form_nuevo_prov"):
            r_rut = st.text_input("RUT Proveedor (Ej: 76123456-K)")
            r_nom = st.text_input("Razón Social / Nombre")
            r_cta = st.selectbox("Cuenta de Gasto Habitual", cuentas_gastos)
            r_cc = st.selectbox("Centro de Costo", LISTA_CENTROS_COSTO)
            btn_add_p = st.form_submit_button("Guardar Proveedor en Maestro")
            if btn_add_p:
                if r_rut and r_nom:
                    try:
                        cursor = conn.cursor()
                        cursor.execute("INSERT INTO proveedores (rut, nombre, cuenta_defecto, centro_costo) VALUES (?, ?, ?, ?)", 
                                       (r_rut.strip(), r_nom.strip(), r_cta, r_cc))
                        conn.commit()
                        st.success("¡Proveedor registrado con éxito!")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("El RUT ingresado ya existe en la base de datos.")
                else:
                    st.error("Ingresa el RUT y el nombre del proveedor.")

    df_prov = pd.read_sql_query("SELECT id, rut, nombre, cuenta_defecto, centro_costo FROM proveedores ORDER BY nombre", conn)
    
    st.subheader("📋 Lista de Proveedores Registrados y Reglas")
    if not df_prov.empty:
        st.dataframe(df_prov[['rut', 'nombre', 'cuenta_defecto', 'centro_costo']], use_container_width=True)
        
        st.markdown("---")
        st.subheader("✏️ Modificar Regla de Imputación Existente")
        
        prov_seleccionado = st.selectbox("Selecciona Proveedor:", options=df_prov['rut'] + " - " + df_prov['nombre'])
        rut_sel = prov_seleccionado.split(" - ")[0]
        row_p = df_prov[df_prov['rut'] == rut_sel].iloc[0]
        
        with st.form("form_regla_prov"):
            col_r1, col_r2 = st.columns(2)
            with col_r1:
                cta_def = st.selectbox(
                    "Cuenta de Gasto Habitual:", 
                    options=cuentas_gastos, 
                    index=cuentas_gastos.index(row_p['cuenta_defecto']) if row_p['cuenta_defecto'] in cuentas_gastos else 0
                )
            with col_r2:
                cc_def = st.selectbox(
                    "Centro de Costo Asociado:", 
                    options=LISTA_CENTROS_COSTO,
                    index=LISTA_CENTROS_COSTO.index(row_p['centro_costo']) if row_p['centro_costo'] in LISTA_CENTROS_COSTO else 0
                )
                
            btn_guardar_regla = st.form_submit_button("💾 Actualizar Regla")
            if btn_guardar_regla:
                cursor = conn.cursor()
                cursor.execute("UPDATE proveedores SET cuenta_defecto = ?, centro_costo = ? WHERE rut = ?", (cta_def, cc_def, rut_sel))
                conn.commit()
                st.success(f"¡Regla actualizada para {row_p['nombre']}!")
                st.rerun()
    else:
        st.warning("No hay proveedores registrados aún. Utiliza el formulario superior para agregar el primero o importa un archivo del SII.")

elif opcion == "📥 Carga Masiva / Importar":
    st.header("📥 Carga Masiva e Importación de Archivos")
    
    tab_sii, tab_entidades, tab_asientos = st.tabs([
        "📄 RCV del SII (Compras / Ventas)", 
        "👥 Clientes y Proveedores", 
        "📖 Asientos Manuales / Históricos"
    ])
    
    with tab_sii:
        st.subheader("Importar Resumen / Detalle RCV del SII")
        col_tipo, col_cuenta, col_cc = st.columns(3)
        with col_tipo:
            tipo_rcv = st.selectbox("Tipo de Registro:", ["Ventas (Clientes)", "Compras (Proveedores)"])
        with col_cuenta:
            if "Ventas" in tipo_rcv:
                cuentas_opt = obtener_subcuentas("Ingresos") or ["Ingresos por Ventas"]
                label_cta = "Subcuenta de Ingreso (Por defecto):"
            else:
                cuentas_opt = obtener_subcuentas("Gastos") or ["Gastos Generales"]
                label_cta = "Subcuenta de Gasto (Comodín si no hay regla):"
            cta_imputar_defecto = st.selectbox(label_cta, cuentas_opt)
        with col_cc:
            cc_defecto = st.selectbox("Centro de Costo (Por defecto):", LISTA_CENTROS_COSTO)

        file_rcv = st.file_uploader("Selecciona el archivo CSV del SII", type=["csv", "txt"])
        
        if file_rcv is not None:
            df_sii = leer_csv_sii(file_rcv)
            if df_sii is not None:
                st.success(f"¡Archivo leído con éxito! Se encontraron {len(df_sii)} registros.")
                st.dataframe(df_sii.head(10), use_container_width=True)
                
                col_rut = next((c for c in df_sii.columns if 'RUT' in c.upper() or 'RUT' in c), None)
                col_nombre = next((c for c in df_sii.columns if 'RAZON' in c.upper() or 'NOMBRE' in c.upper()), None)
                col_fecha = next((c for c in df_sii.columns if 'FECHA' in c.upper()), None)
                col_neto = next((c for c in df_sii.columns if 'NETO' in c.upper()), None)
                col_iva = next((c for c in df_sii.columns if 'IVA' in c.upper() and 'NO' not in c.upper()), None)
                col_total = next((c for c in df_sii.columns if 'TOTAL' in c.upper()), None)
                
                if not col_rut or not col_neto:
                    st.error("No se detectaron automáticamente las columnas principales (RUT, Neto).")
                else:
                    if st.button("🚀 Procesar e Importar Masivamente"):
                        cursor = conn.cursor()
                        registros_procesados = 0
                        
                        for _, row in df_sii.iterrows():
                            rut_val = str(row[col_rut]).strip() if pd.notna(row[col_rut]) else "S/RUT"
                            nombre_val = str(row[col_nombre]).strip() if col_nombre and pd.notna(row[col_nombre]) else f"Entidad {rut_val}"
                            
                            fecha_str = str(datetime.now().strftime("%Y-%m-%d"))
                            if col_fecha and pd.notna(row[col_fecha]):
                                try:
                                    fecha_parsed = pd.to_datetime(row[col_fecha], dayfirst=True)
                                    fecha_str = fecha_parsed.strftime("%Y-%m-%d")
                                except Exception:
                                    pass
                                    
                            def parse_monto(val):
                                if pd.isna(val): return 0.0
                                val_str = str(val).replace(".", "").replace(",", ".").replace("$", "").strip()
                                try: return float(val_str)
                                except: return 0.0

                            m_neto = parse_monto(row[col_neto])
                            m_iva = parse_monto(row[col_iva]) if col_iva else round(m_neto * 0.19, 2)
                            m_total = parse_monto(row[col_total]) if col_total else round(m_neto + m_iva, 2)
                            
                            if m_neto <= 0 and m_total <= 0:
                                continue

                            if "Ventas" in tipo_rcv:
                                cursor.execute("SELECT id FROM clientes WHERE rut = ?", (rut_val,))
                                res_cli = cursor.fetchone()
                                if res_cli:
                                    cli_id = res_cli[0]
                                else:
                                    try:
                                        cursor.execute("INSERT INTO clientes (rut, nombre) VALUES (?, ?)", (rut_val, nombre_val))
                                        cli_id = cursor.lastrowid
                                    except Exception:
                                        cursor.execute("SELECT id FROM clientes WHERE rut = ?", (rut_val,))
                                        res_r = cursor.fetchone()
                                        cli_id = res_r[0] if res_r else 1
                                
                                cursor.execute("""
                                    INSERT INTO ventas (fecha, cliente_id, cuenta_ingreso, monto_neto, iva, monto_total, glosa)
                                    VALUES (?, ?, ?, ?, ?, ?, ?)
                                """, (fecha_str, cli_id, cta_imputar_defecto, m_neto, m_iva, m_total, f"Carga Masiva SII - {nombre_val}"))
                                
                                cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa, centro_costo) VALUES (?, 'Cuentas por Cobrar Clientes', ?, 0, ?, ?)", (fecha_str, m_total, f"Venta {nombre_val}", cc_defecto))
                                cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa, centro_costo) VALUES (?, ?, 0, ?, ?, ?)", (fecha_str, cta_imputar_defecto, m_neto, f"Venta {nombre_val}", cc_defecto))
                                cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa, centro_costo) VALUES (?, 'IVA Débito Fiscal', 0, ?, ?, ?)", (fecha_str, m_iva, f"IVA Venta {nombre_val}", cc_defecto))

                            else:
                                cursor.execute("SELECT id, cuenta_defecto, centro_costo FROM proveedores WHERE rut = ?", (rut_val,))
                                res_prov = cursor.fetchone()
                                
                                cta_final_gasto = cta_imputar_defecto
                                cc_final = cc_defecto
                                
                                if res_prov:
                                    prov_id = res_prov[0]
                                    if res_prov[1]: cta_final_gasto = res_prov[1]
                                    if res_prov[2]: cc_final = res_prov[2]
                                else:
                                    try:
                                        cursor.execute("INSERT INTO proveedores (rut, nombre, cuenta_defecto, centro_costo) VALUES (?, ?, ?, ?)", (rut_val, nombre_val, cta_imputar_defecto, cc_defecto))
                                        prov_id = cursor.lastrowid
                                    except Exception:
                                        cursor.execute("SELECT id, cuenta_defecto, centro_costo FROM proveedores WHERE rut = ?", (rut_val,))
                                        res_r = cursor.fetchone()
                                        prov_id = res_r[0] if res_r else 1
                                        if res_r and res_r[1]: cta_final_gasto = res_r[1]
                                        if res_r and res_r[2]: cc_final = res_r[2]
                                
                                cursor.execute("""
                                    INSERT INTO compras (fecha, proveedor_id, cuenta_gasto, centro_costo, monto_neto, iva, monto_total, glosa)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                                """, (fecha_str, prov_id, cta_final_gasto, cc_final, m_neto, m_iva, m_total, f"Carga Masiva SII - {nombre_val}"))
                                
                                cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa, centro_costo) VALUES (?, ?, ?, 0, ?, ?)", (fecha_str, cta_final_gasto, m_neto, f"Compra {nombre_val}", cc_final))
                                cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa, centro_costo) VALUES (?, 'IVA Crédito Fiscal', ?, 0, ?, ?)", (fecha_str, m_iva, f"IVA Compra {nombre_val}", cc_final))
                                cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa, centro_costo) VALUES (?, 'Cuentas por Pagar Proveedores', 0, ?, ?, ?)", (fecha_str, m_total, f"Compra {nombre_val}", cc_final))

                            registros_procesados += 1
                        
                        conn.commit()
                        st.balloons()
                        st.success(f"¡Importación completada! Se contabilizaron {registros_procesados} documentos.")
            else:
                st.error("No se pudo interpretar el archivo CSV.")

    with tab_entidades:
        st.subheader("Carga Masiva de Clientes / Proveedores")
        tipo_entidad = st.radio("Selecciona tipo de entidad:", ["Clientes", "Proveedores"], horizontal=True)
        file_ent = st.file_uploader("Subir Archivo de Entidades (.csv)", type=["csv"])
        if file_ent is not None:
            df_e = pd.read_csv(file_ent)
            st.dataframe(df_e.head(), use_container_width=True)
            if st.button("Guardar Entidades Masivamente"):
                cursor = conn.cursor()
                tabla_target = "clientes" if tipo_entidad == "Clientes" else "proveedores"
                guardados = 0
                for _, r in df_e.iterrows():
                    try:
                        cursor.execute(f"INSERT INTO {tabla_target} (rut, nombre, cuenta_defecto, centro_costo) VALUES (?, ?, 'Gastos Generales', 'General / Ninguno')", (str(r['rut']).strip(), str(r['nombre']).strip()))
                        guardados += 1
                    except sqlite3.IntegrityError:
                        pass
                conn.commit()
                st.success(f"¡Se registraron {guardados} {tipo_entidad} con éxito!")

    with tab_asientos:
        st.subheader("Carga Masiva de Asientos Contables Manuales")
        file_as = st.file_uploader("Subir Archivo de Asientos Manuales (.csv)", type=["csv"])
        if file_as is not None:
            df_a = pd.read_csv(file_as)
            st.dataframe(df_a, use_container_width=True)
            if st.button("Guardar Asientos Masivos en Libro Diario"):
                cursor = conn.cursor()
                for _, r in df_a.iterrows():
                    cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa, centro_costo) VALUES (?, ?, ?, ?, ?, 'General / Ninguno')", 
                                   (str(r['fecha']), str(r['cuenta']), float(r['debe']), float(r['haber']), str(r['glosa'])))
                conn.commit()
                st.success("¡Asientos agregados correctamente!")

elif opcion == "📋 Plan de Cuentas":
    st.header("📋 Plan de Cuentas (Normativa Chilena)")
    df_pc = pd.read_sql_query("SELECT codigo as 'Código', nombre as 'Nombre', categoria as 'Categoría', tipo as 'Tipo', nivel as 'Nivel' FROM plan_cuentas ORDER BY codigo", conn)
    st.dataframe(df_pc, use_container_width=True)

elif opcion == "✏️ Registrar Asiento Manual":
    st.header("✏️ Registrar Asiento Contable Manual")
    lista_cuentas = obtener_subcuentas()
    fecha_m = st.date_input("Fecha", datetime.now())
    glosa_m = st.text_input("Glosa", "Asiento manual")
    cc_m = st.selectbox("Centro de Costo", LISTA_CENTROS_COSTO)
    
    c1, c2 = st.columns(2)
    with c1:
        cta_debe = st.selectbox("Cuenta Debe", lista_cuentas, key="d")
        m_debe = st.number_input("Monto Debe ($)", min_value=0.0, step=100.0)
    with c2:
        cta_haber = st.selectbox("Cuenta Haber", lista_cuentas, key="h")
        m_haber = st.number_input("Monto Haber ($)", min_value=0.0, step=100.0)
        
    if st.button("Guardar Asiento"):
        if m_debe > 0 and m_debe == m_haber:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa, centro_costo) VALUES (?, ?, ?, 0, ?, ?)", (str(fecha_m), cta_debe, m_debe, glosa_m, cc_m))
            cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa, centro_costo) VALUES (?, ?, 0, ?, ?, ?)", (str(fecha_m), cta_haber, m_haber, glosa_m, cc_m))
            conn.commit()
            st.success("¡Asiento guardado!")
        else:
            st.error("Los montos deben ser iguales (Partida Doble).")

elif opcion == "Registrar Compra Proveedor":
    st.header("🛒 Registrar Compra")
    cuentas_gastos = obtener_subcuentas("Gastos") or ["Gastos Generales"]
    c1, c2 = st.columns(2)
    with c1:
        f_c = st.date_input("Fecha", datetime.now())
        r_p = st.text_input("RUT Proveedor")
        n_p = st.text_input("Nombre Proveedor")
        cta_g = st.selectbox("Gasto", cuentas_gastos)
        cc_p = st.selectbox("Centro Costo", LISTA_CENTROS_COSTO)
        g_c = st.text_input("Glosa")
    with c2:
        neto_c = st.number_input("Neto ($)", min_value=0.0, step=100.0)
        iva_c = round(neto_c * 0.19, 2)
        tot_c = round(neto_c + iva_c, 2)
        st.metric("IVA (19%)", f"${iva_c:,.0f}")
        st.metric("Total", f"${tot_c:,.0f}")
        
    if st.button("Guardar Compra"):
        if r_p and neto_c > 0:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM proveedores WHERE rut = ?", (r_p,))
            res = cursor.fetchone()
            p_id = res[0] if res else cursor.execute("INSERT INTO proveedores (rut, nombre, cuenta_defecto, centro_costo) VALUES (?, ?, ?, ?)", (r_p, n_p, cta_g, cc_p)).lastrowid
            
            cursor.execute("INSERT INTO compras (fecha, proveedor_id, cuenta_gasto, centro_costo, monto_neto, iva, monto_total, glosa) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (str(f_c), p_id, cta_g, cc_p, neto_c, iva_c, tot_c, g_c))
            cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa, centro_costo) VALUES (?, ?, ?, 0, ?, ?)", (str(f_c), cta_g, neto_c, f"Compra {n_p}", cc_p))
            cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa, centro_costo) VALUES (?, 'IVA Crédito Fiscal', ?, 0, ?, ?)", (str(f_c), iva_c, f"IVA Compra {n_p}", cc_p))
            cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa, centro_costo) VALUES (?, 'Cuentas Comerciales y Otras Cuentas por Pagar', 0, ?, ?, ?)", (str(f_c), tot_c, f"Compra {n_p}", cc_p))
            conn.commit()
            st.success("¡Compra registrada!")

elif opcion == "Registrar Pago Proveedor":
    st.header("💸 Registrar Pago a Proveedor")
    df_prov = pd.read_sql_query("SELECT id, nombre FROM proveedores", conn)
    if not df_prov.empty:
        p_sel = st.selectbox("Proveedor", df_prov['nombre'])
        pid = df_prov[df_prov['nombre'] == p_sel]['id'].values[0]
        f_pag = st.date_input("Fecha Pago", datetime.now())
        m_pag = st.number_input("Monto Pago ($)", min_value=0.0, step=100.0)
        if st.button("Registrar Pago"):
            if m_pag > 0:
                cursor = conn.cursor()
                cursor.execute("INSERT INTO pagos (fecha, proveedor_id, monto) VALUES (?, ?, ?)", (str(f_pag), pid, m_pag))
                cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa, centro_costo) VALUES (?, 'Cuentas Comerciales y Otras Cuentas por Pagar', ?, 0, ?, 'General / Ninguno')", (str(f_pag), m_pag, f"Pago a {p_sel}"))
                cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa, centro_costo) VALUES (?, 'Banco', 0, ?, ?, 'General / Ninguno')", (str(f_pag), m_pag, f"Pago a {p_sel}"))
                conn.commit()
                st.success("¡Pago registrado!")

elif opcion == "Registrar Venta Cliente":
    st.header("📈 Registrar Venta")
    cuentas_ingresos = obtener_subcuentas("Ingresos") or ["Ingresos por Ventas"]
    c1, c2 = st.columns(2)
    with c1:
        f_v = st.date_input("Fecha Venta", datetime.now())
        r_cl = st.text_input("RUT Cliente")
        n_cl = st.text_input("Nombre Cliente")
        cta_i = st.selectbox("Ingreso", cuentas_ingresos)
        g_v = st.text_input("Glosa Venta")
    with c2:
        neto_v = st.number_input("Neto Venta ($)", min_value=0.0, step=100.0)
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
            cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa, centro_costo) VALUES (?, 'Cuentas Comerciales y Otras Cuentas por Cobrar', ?, 0, ?, 'General / Ninguno')", (str(f_v), tot_v, f"Venta {n_cl}"))
            cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa, centro_costo) VALUES (?, ?, 0, ?, ?, 'General / Ninguno')", (str(f_v), cta_i, neto_v, f"Venta {n_cl}"))
            cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa, centro_costo) VALUES (?, 'IVA Débito Fiscal', 0, ?, ?, 'General / Ninguno')", (str(f_v), iva_v, f"IVA Venta {n_cl}"))
            conn.commit()
            st.success("¡Venta registrada!")

elif opcion == "Registrar Cobro Cliente":
    st.header("💰 Registrar Cobro a Cliente")
    df_cli = pd.read_sql_query("SELECT id, nombre FROM clientes", conn)
    if not df_cli.empty:
        c_sel = st.selectbox("Cliente", df_cli['nombre'])
        cid = df_cli[df_cli['nombre'] == c_sel]['id'].values[0]
        f_cob = st.date_input("Fecha Cobro", datetime.now())
        m_cob = st.number_input("Monto Cobrado ($)", min_value=0.0, step=100.0)
        if st.button("Registrar Cobro"):
            if m_cob > 0:
                cursor = conn.cursor()
                cursor.execute("INSERT INTO cobros (fecha, cliente_id, monto) VALUES (?, ?, ?)", (str(f_cob), cid, m_cob))
                cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa, centro_costo) VALUES (?, 'Banco', ?, 0, ?, 'General / Ninguno')", (str(f_cob), m_cob, f"Cobro a {c_sel}"))
                cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa, centro_costo) VALUES (?, 'Cuentas Comerciales y Otras Cuentas por Cobrar', 0, ?, ?, 'General / Ninguno')", (str(f_cob), m_cob, f"Cobro a {c_sel}"))
                conn.commit()
                st.success("¡Cobro registrado!")

elif opcion == "Cartola Bancaria y Saldos":
    st.header("🏦 Cartola Bancaria y Flujo de Caja")
    df_ing = pd.read_sql_query("SELECT SUM(monto) as total FROM cobros", conn)
    df_egr = pd.read_sql_query("SELECT SUM(monto) as total FROM pagos", conn)
    t_ing = df_ing['total'].iloc[0] or 0.0
    t_egr = df_egr['total'].iloc[0] or 0.0
    st.metric("Saldo Disponible en Banco", f"${t_ing - t_egr:,.0f}")

elif opcion == "Libro Diario (Contabilidad)":
    st.header("📖 Libro Diario Contable")
    df_ld = pd.read_sql_query("SELECT * FROM libro_diario ORDER BY id DESC", conn)
    if not df_ld.empty:
        st.dataframe(df_ld, use_container_width=True)

elif opcion == "📊 Reportes Financieros (Norma Chile)":
    st.header("📊 Reportes Financieros bajo Normativa Chilena (CMF / IFRS)")
    
    tab_er, tab_esf, tab_resp = st.tabs(["Estado de Resultados por Función", "Estado de Situación Financiera", "Exportar Datos"])
    
    with tab_er:
        st.subheader("Estado de Resultados Integral (Por Función)")
        st.caption("Clasificación formal según prácticas contables en Chile.")
        
        # Obtener sumas de libro diario para cuentas nominales
        df_er_data = pd.read_sql_query("""
            SELECT l.cuenta, p.tipo, SUM(l.haber) - SUM(l.debe) as saldo_ingreso, SUM(l.debe) - SUM(l.haber) as saldo_gasto
            FROM libro_diario l
            LEFT JOIN plan_cuentas p ON l.cuenta = p.nombre
            WHERE p.categoria = 'Nominal'
            GROUP BY l.cuenta, p.tipo
        """, conn)
        
        ingresos_totales = 0.0
        costo_ventas = 0.0
        gastos_operacionales = 0.0
        
        for _, row in df_er_data.iterrows():
            cuenta = row['cuenta']
            tipo = row['tipo']
            if tipo == 'Ingresos':
                ingresos_totales += row['saldo_ingreso']
            elif 'Costo' in cuenta:
                costo_ventas += row['saldo_gasto']
            else:
                gastos_operacionales += row['saldo_gasto']
                
        margen_bruto = ingresos_totales - costo_ventas
        resultado_operacional = margen_bruto - gastos_operacionales
        
        st.markdown(f"* **(+) Ingresos de Actividades Ordinarias:** ${ingresos_totales:,.0f}")
        st.markdown(f"* **(-) Costo de Ventas:** ${costo_ventas:,.0f}")
        st.markdown(f"### = Margen Bruto: ${margen_bruto:,.0f}")
        st.markdown(f"* **(-) Gastos de Administración y Ventas:** ${gastos_operacionales:,.0f}")
        st.markdown(f"### 🇨🇱 Resultado del Ejercicio (Utilidad / Pérdida): ${resultado_operacional:,.0f}")

    with tab_esf:
        st.subheader("Estado de Situación Financiera (Balance General Clasificado)")
        st.caption("Presentación de Activos, Pasivos y Patrimonio según exigencias chilenas.")
        
        df_esf_data = pd.read_sql_query("""
            SELECT l.cuenta, p.tipo, SUM(l.debe) - SUM(l.haber) as saldo_deudor, SUM(l.haber) - SUM(l.debe) as saldo_acreedor
            FROM libro_diario l
            LEFT JOIN plan_cuentas p ON l.cuenta = p.nombre
            WHERE p.categoria = 'Real'
            GROUP BY l.cuenta, p.tipo
        """, conn)
        
        total_activo_corriente = 0.0
        total_activo_nocorriente = 0.0
        total_pasivo_corriente = 0.0
        total_patrimonio = 0.0
        
        for _, row in df_esf_data.iterrows():
            cuenta = row['cuenta']
            tipo = row['tipo']
            saldo = row['saldo_deudor'] if row['saldo_deudor'] > 0 else 0.0
            
            if tipo == 'Activo':
                if 'Propiedades' in cuenta or 'Equipo' in cuenta or 'No Corriente' in cuenta:
                    total_activo_nocorriente += saldo
                else:
                    total_activo_corriente += saldo
            elif tipo == 'Pasivo':
                total_pasivo_corriente += row['saldo_acreedor']
            elif tipo == 'Patrimonio':
                total_patrimonio += row['saldo_acreedor']
                
        total_activos = total_activo_corriente + total_activo_nocorriente
        total_pasivo_patrimonio = total_pasivo_corriente + total_patrimonio
        
        col_b1, col_b2 = st.columns(2)
        with col_b1:
            st.markdown("#### 🏛️ ACTIVOS")
            st.text(f"Activo Corriente: ${total_activo_corriente:,.0f}")
            st.text(f"Activo No Corriente: ${total_activo_nocorriente:,.0f}")
            st.markdown(f"**Total Activos:** ${total_activos:,.0f}")
            
        with col_b2:
            st.markdown("#### 📉 PASIVOS Y PATRIMONIO")
            st.text(f"Pasivo Corriente: ${total_pasivo_corriente:,.0f}")
            st.text(f"Patrimonio Neto: ${total_patrimonio:,.0f}")
            st.markdown(f"**Total Pasivo + Patrimonio:** ${total_pasivo_patrimonio:,.0f}")

    with tab_resp:
        st.subheader("Exportar Base de Datos")
        try:
            with open(DB_FILE, "rb") as fp:
                db_bytes = fp.read()
            st.download_button("💾 Descargar Base de Datos Completa (.db)", data=db_bytes, file_name="sistema_contable_chile.db", mime="application/x-sqlite3")
        except Exception:
            st.error("Base de datos no disponible.")

conn.close()

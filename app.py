import streamlit as st
import pandas as pd
import sqlite3
import io
from datetime import datetime

st.set_page_config(page_title="Sistema Contable Web", page_icon="💼", layout="wide")

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
    
    def asegurar_columna(tabla, columna, tipo):
        cursor.execute(f"PRAGMA table_info({tabla})")
        cols = [info[1] for info in cursor.fetchall()]
        if cols and columna not in cols:
            try:
                cursor.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {tipo}")
            except Exception:
                pass

    asegurar_columna("proveedores", "cuenta_defecto", "TEXT")
    asegurar_columna("proveedores", "centro_costo", "TEXT")
    asegurar_columna("compras", "cuenta_gasto", "TEXT")
    asegurar_columna("compras", "centro_costo", "TEXT")
    asegurar_columna("compras", "monto_neto", "REAL")
    asegurar_columna("compras", "iva", "REAL")
    asegurar_columna("compras", "monto_total", "REAL")
    asegurar_columna("ventas", "cuenta_ingreso", "TEXT")
    asegurar_columna("ventas", "monto_neto", "REAL")
    asegurar_columna("ventas", "iva", "REAL")
    asegurar_columna("ventas", "monto_total", "REAL")
    asegurar_columna("libro_diario", "centro_costo", "TEXT")

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
        "📊 Reportes Financieros"
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
    st.title("💼 Sistema Contable Web")
    st.subheader("Bienvenido a tu Sistema Contable Integrado")
    st.info("Utiliza el menú lateral para acceder al Módulo de Carga Masiva, Maestro de Proveedores, Plan de Cuentas, Asientos Manuales, Compras, Ventas, Banco, Libro Diario y Reportes.")

elif opcion == "🏢 Maestro de Proveedores y Reglas":
    st.header("🏢 Maestro de Proveedores y Reglas de Imputación")
    st.caption("Configura qué cuenta contable de gasto y centro de costo se asignará automáticamente a cada proveedor cuando cargues facturas masivas del SII.")
    
    cuentas_gastos = obtener_subcuentas("Gastos") or ["Gastos Generales"]
    
    # Lectura protegida con reintento automático si faltan columnas en la BD antigua
    try:
        df_prov = pd.read_sql_query("SELECT id, rut, nombre, cuenta_defecto, centro_costo FROM proveedores ORDER BY nombre", conn)
    except Exception:
        c_temp = conn.cursor()
        try: c_temp.execute("ALTER TABLE proveedores ADD COLUMN cuenta_defecto TEXT")
        except: pass
        try: c_temp.execute("ALTER TABLE proveedores ADD COLUMN centro_costo TEXT")
        except: pass
        conn.commit()
        df_prov = pd.read_sql_query("SELECT id, rut, nombre, cuenta_defecto, centro_costo FROM proveedores ORDER BY nombre", conn)
    
    st.subheader("📋 Lista de Proveedores Registrados")
    if not df_prov.empty:
        st.dataframe(df_prov[['rut', 'nombre', 'cuenta_defecto', 'centro_costo']], use_container_width=True)
        
        st.markdown("---")
        st.subheader("✏️ Asignar / Modificar Regla de Imputación")
        
        prov_seleccionado = st.selectbox("Selecciona Proveedor para Configurar:", options=df_prov['rut'] + " - " + df_prov['nombre'])
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
                
            btn_guardar_regla = st.form_submit_button("💾 Guardar Regla de Imputación")
            if btn_guardar_regla:
                cursor = conn.cursor()
                cursor.execute("UPDATE proveedores SET cuenta_defecto = ?, centro_costo = ? WHERE rut = ?", (cta_def, cc_def, rut_sel))
                conn.commit()
                st.success(f"¡Regla guardada con éxito para {row_p['nombre']}! Carga masiva usará: '{cta_def}' y '{cc_def}'.")
                st.rerun()
    else:
        st.info("Aún no tienes proveedores registrados. Puedes registrarlos manualmente o importar compras del SII para alimentarlos automáticamente.")

elif opcion == "📥 Carga Masiva / Importar":
    st.header("📥 Carga Masiva e Importación de Archivos")
    
    tab_sii, tab_entidades, tab_asientos = st.tabs([
        "📄 RCV del SII (Compras / Ventas)", 
        "👥 Clientes y Proveedores", 
        "📖 Asientos Manuales / Históricos"
    ])
    
    with tab_sii:
        st.subheader("Importar Resumen / Detalle RCV del SII")
        st.caption("Adjunta directamente el archivo CSV descargado desde el Registro de Compras y Ventas del SII.")
        
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
                    st.error("No se detectaron automáticamente las columnas principales (RUT, Neto). Por favor revisa el formato del archivo.")
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
                                try:
                                    cursor.execute("SELECT id, cuenta_defecto, centro_costo FROM proveedores WHERE rut = ?", (rut_val,))
                                    res_prov = cursor.fetchone()
                                except Exception:
                                    cursor.execute("ALTER TABLE proveedores ADD COLUMN cuenta_defecto TEXT")
                                    cursor.execute("ALTER TABLE proveedores ADD COLUMN centro_costo TEXT")
                                    conn.commit()
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
                        st.success(f"¡Importación completada! Se contabilizaron {registros_procesados} documentos respetando las reglas de imputación por RUT.")
            else:
                st.error("No se pudo interpretar la codificación del archivo CSV.")

    with tab_entidades:
        st.subheader("Carga Masiva de Clientes / Proveedores")
        st.caption("Sube un CSV con las columnas: `rut`, `nombre`")
        
        tipo_entidad = st.radio("Selecciona tipo de entidad:", ["Clientes", "Proveedores"], horizontal=True)
        
        plantilla_entidades = pd.DataFrame([{"rut": "12345678-9", "nombre": "Empresa Ejemplo SpA"}])
        csv_p_ent = plantilla_entidades.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Descargar Plantilla Modelo (.csv)", data=csv_p_ent, file_name="plantilla_entidades.csv", mime="text/csv")
        
        file_ent = st.file_uploader("Subir Archivo de Entidades", type=["csv"])
        if file_ent is not None:
            df_e = pd.read_csv(file_ent)
            st.dataframe(df_e.head(), use_container_width=True)
            if st.button("Guardar Entidades Masivamente"):
                cursor = conn.cursor()
                tabla_target = "clientes" if tipo_entidad == "Clientes" else "proveedores"
                guardados = 0
                for _, r in df_e.iterrows():
                    try:
                        cursor.execute(f"INSERT INTO {tabla_target} (rut, nombre) VALUES (?, ?)", (str(r['rut']).strip(), str(r['nombre']).strip()))
                        guardados += 1
                    except sqlite3.IntegrityError:
                        pass
                conn.commit()
                st.success(f"¡Se registraron {guardados} {tipo_entidad} con éxito!")

    with tab_asientos:
        st.subheader("Carga Masiva de Asientos Contables Manuales")
        st.caption("Sube un CSV con las columnas: `fecha`, `cuenta`, `debe`, `haber`, `glosa`")
        
        p_asientos = pd.DataFrame([
            {"fecha": "2026-09-01", "cuenta": "Banco", "debe": 100000, "haber": 0, "glosa": "Aporte Capital"},
            {"fecha": "2026-09-01", "cuenta": "Capital Social", "debe": 0, "haber": 100000, "glosa": "Aporte Capital"}
        ])
        csv_p_as = p_asientos.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Descargar Plantilla de Asientos (.csv)", data=csv_p_as, file_name="plantilla_asientos.csv", mime="text/csv")
        
        file_as = st.file_uploader("Subir Archivo de Asientos Manuales", type=["csv"])
        if file_as is not None:
            df_a = pd.read_csv(file_as)
            st.dataframe(df_a, use_container_width=True)
            tot_d = df_a['debe'].sum()
            tot_h = df_a['haber'].sum()
            
            c_d, c_h = st.columns(2)
            c_d.metric("Total Debe en Archivo", f"${tot_d:,.0f}")
            c_h.metric("Total Haber en Archivo", f"${tot_h:,.0f}")
            
            if abs(tot_d - tot_h) < 0.01:
                st.success("✅ El archivo está cuadrado (Debe = Haber)")
                if st.button("Guardar Asientos Masivos en Libro Diario"):
                    cursor = conn.cursor()
                    for _, r in df_a.iterrows():
                        cursor.execute("""
                            INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa)
                            VALUES (?, ?, ?, ?, ?)
                        """, (str(r['fecha']), str(r['cuenta']), float(r['debe']), float(r['haber']), str(r['glosa'])))
                    conn.commit()
                    st.success("¡Asientos históricos/masivos agregados correctamente al Libro Diario!")
            else:
                st.error("❌ El lote de asientos no está cuadrado. La suma total del Debe debe ser igual al Haber.")

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
    cc_m = st.selectbox("Centro de Costo", LISTA_CENTROS_COSTO)
    
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
            cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa, centro_costo) VALUES (?, ?, ?, 0, ?, ?)",
                           (str(fecha_m), cuenta_debe, monto_debe, glosa_m, cc_m))
            cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa, centro_costo) VALUES (?, ?, 0, ?, ?, ?)",
                           (str(fecha_m), cuenta_haber, monto_haber, glosa_m, cc_m))
            conn.commit()
            st.success("¡Asiento manual guardado correctamente en el Libro Diario!")

elif opcion == "Registrar Compra Proveedor":
    st.header("🛒 Registrar Compra (Desglose Neto + IVA)")
    
    cuentas_gastos = obtener_subcuentas("Gastos") or ["Gastos Generales"]

    col_input1, col_input2 = st.columns(2)
    with col_input1:
        fecha = st.date_input("Fecha de Compra", datetime.now())
        rut_prov = st.text_input("RUT Proveedor")
        nombre_prov = st.text_input("Nombre Proveedor")
        cuenta_gasto_sel = st.selectbox("Imputar a Subcuenta de Gasto:", cuentas_gastos)
        cc_sel = st.selectbox("Centro de Costo:", LISTA_CENTROS_COSTO)
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
            prov_id = res[0] if res else cursor.execute("INSERT INTO proveedores (rut, nombre, cuenta_defecto, centro_costo) VALUES (?, ?, ?, ?)", (rut_prov, nombre_prov, cuenta_gasto_sel, cc_sel)).lastrowid
            
            cursor.execute("""
                INSERT INTO compras (fecha, proveedor_id, cuenta_gasto, centro_costo, monto_neto, iva, monto_total, glosa) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (str(fecha), prov_id, cuenta_gasto_sel, cc_sel, monto_neto, iva, monto_total, glosa))
            
            cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa, centro_costo) VALUES (?, ?, ?, 0, ?, ?)", (str(fecha), cuenta_gasto_sel, monto_neto, f"Compra {nombre_prov}", cc_sel))
            cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa, centro_costo) VALUES (?, 'IVA Crédito Fiscal', ?, 0, ?, ?)", (str(fecha), iva, f"IVA Compra {nombre_prov}", cc_sel))
            cursor.execute("INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa, centro_costo) VALUES (?, 'Cuentas por Pagar Proveedores', 0, ?, ?, ?)", (str(fecha), monto_total, f"Compra {nombre_prov}", cc_sel))
            
            conn.commit()
            st.success(f"¡Compra registrada con éxito e imputada a '{cuenta_gasto_sel}' [{cc_sel}]! Total: ${monto_total:,.0f}")
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
        st.warning("No hay proveedores registrados previamente. Registra primero una compra o importa tus proveedores.")

elif opcion == "Registrar Venta Cliente":
    st.header("📈 Registrar Venta (Desglose Neto + IVA)")
    
    cuentas_ingresos = obtener_subcuentas("Ingresos") or ["Ingresos por Ventas"]

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
        st.warning("No hay clientes registrados previamente. Registra primero una venta o importa tus clientes.")

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

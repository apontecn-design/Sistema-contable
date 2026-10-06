# -*- coding: utf-8 -*-

"""
SGCI - Sistema de Gestión Contable Integral
Versión actualizada con:
- Corrección de multplicador de signo (-1) aplicado en resúmenes y montos para Notas de Crédito (Compras y Ventas)
- Tratamiento contable completo por Tipo de Documento SII
- Separación de Facturas Exentas de Ventas (Tipo 34 y 41 -> Cuenta Ventas Exentas)
- Protección de acceso mediante contraseña y respaldo de base de datos
"""

import io
import os
import re
import sqlite3
from datetime import datetime, date, timedelta
from hashlib import sha256
from decimal import Decimal, ROUND_HALF_UP

import pandas as pd
import streamlit as st


# ============================================================
# CONFIGURACIÓN Y SEGURIDAD (AUTENTICACIÓN)
# ============================================================

DATA_DIR = os.getenv("SGCI_DATA_DIR", ".")
os.makedirs(DATA_DIR, exist_ok=True)
DB_FILE = os.path.join(DATA_DIR, "sgci.db")

st.set_page_config(
    page_title="SGCI - Sistema Contable",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Identidad visual SGCI: verde sobrio, superficies claras y navegación compacta.
st.markdown("""
<style>
:root { --sgci-green:#176B55; --sgci-green-dark:#0F4F3F; --sgci-soft:#EAF5F0; --sgci-border:#DCE8E3; }
[data-testid="stAppViewContainer"] { background:#F7F9F8; }
[data-testid="stSidebar"] { background:#FFFFFF; border-right:1px solid var(--sgci-border); }
[data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 { color:var(--sgci-green-dark); }
[data-testid="stSidebar"] div[role="radiogroup"] label { padding:.18rem .35rem; border-radius:8px; }
[data-testid="stSidebar"] div[role="radiogroup"] label:hover { background:var(--sgci-soft); }
.stButton > button, .stDownloadButton > button { border-radius:8px; border:1px solid #BFD8CD; }
.stButton > button[kind="primary"] { background:var(--sgci-green)!important; border-color:var(--sgci-green)!important; color:white!important; }
.stButton > button[kind="primary"]:hover { background:var(--sgci-green-dark)!important; border-color:var(--sgci-green-dark)!important; }
[data-testid="stMetric"] { background:#FFFFFF; border:1px solid var(--sgci-border); padding:14px 16px; border-radius:10px; }
[data-baseweb="tab-list"] { gap:.35rem; }
button[data-baseweb="tab"] { border-radius:8px 8px 0 0; }
hr { border-color:var(--sgci-border)!important; }
</style>
""", unsafe_allow_html=True)

if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

if not st.session_state["authenticated"]:
    st.markdown("<br><br>", unsafe_allow_html=True)
    _, col2, _ = st.columns([1, 2, 1])
    with col2:
        st.title("🔐 Acceso Restringido - SGCI")
        st.info("Por seguridad, ingresa la contraseña para acceder al sistema contable.")
        pwd = st.text_input("Contraseña de acceso", type="password")
        if st.button("Ingresar al Sistema", type="primary", use_container_width=True):
            if pwd == "admin2026":
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("Contraseña incorrecta.")
    st.stop()


# ============================================================
# CONEXIÓN
# ============================================================

def conectar():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ============================================================
# FUNCIONES GENERALES
# ============================================================

def clp_round(valor):
    """Redondeo comercial al peso: 0,5 o más sube; menos de 0,5 baja."""
    try:
        return int(Decimal(str(valor or 0)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except Exception:
        return 0


def money(valor):
    try:
        return f"${clp_round(valor):,}".replace(",", ".")
    except Exception:
        return "$0"


def numero_clp(valor):
    try:
        return f"{clp_round(valor):,}".replace(",", ".")
    except Exception:
        return "0"


def formatear_montos_df(df):
    if df is None or getattr(df, "empty", True):
        return df
    out=df.copy()
    claves=("monto","total","saldo","debe","haber","cargo","abono","neto","iva","pagado","pendiente","precio","costo","sueldo","gratificacion","gratificación","imponible","haberes","descuentos","liquido","líquido","anticipo","cuota","prestamo","préstamo","impuesto","afp_descuento","salud_descuento","afc_descuento")
    for c in out.columns:
        nombre=str(c).lower()
        if any(k in nombre for k in claves) and pd.api.types.is_numeric_dtype(out[c]):
            out[c]=out[c].map(numero_clp)
    return out


def limpiar_texto(valor):
    if valor is None:
        return ""
    return str(valor).strip()


def normalizar_rut(rut):
    rut = limpiar_texto(rut).upper().replace(".", "").replace(" ", "")
    return rut


def validar_rut(rut):
    rut = normalizar_rut(rut)

    if not rut or "-" not in rut:
        return False

    cuerpo, dv = rut.rsplit("-", 1)

    if not cuerpo.isdigit() or len(dv) != 1:
        return False

    suma = 0
    multiplicador = 2

    for digito in reversed(cuerpo):
        suma += int(digito) * multiplicador
        multiplicador += 1
        if multiplicador > 7:
            multiplicador = 2

    resto = 11 - (suma % 11)

    if resto == 11:
        esperado = "0"
    elif resto == 10:
        esperado = "K"
    else:
        esperado = str(resto)

    return dv.upper() == esperado


def fecha_iso(valor):
    if valor is None:
        return None

    s = str(valor).strip()

    if not s:
        return None

    formatos = [
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%Y/%m/%d",
    ]

    for formato in formatos:
        try:
            return datetime.strptime(s[:10], formato).strftime("%Y-%m-%d")
        except Exception:
            pass

    try:
        d = pd.to_datetime(s, errors="coerce")
        if pd.isna(d):
            return None
        return d.strftime("%Y-%m-%d")
    except Exception:
        return None


def numero(valor):
    if valor is None:
        return 0.0

    s = str(valor).strip()

    if not s:
        return 0.0

    s = s.replace("$", "").replace(" ", "")

    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    else:
        if s.count(".") > 1:
            s = s.replace(".", "")
        else:
            pass

    try:
        return float(s)
    except Exception:
        return 0.0


def leer_csv(uploaded_file):
    datos = uploaded_file.getvalue()

    if not datos:
        raise ValueError("El archivo está vacío.")

    texto = None

    for enc in ("utf-8-sig", "latin1"):
        try:
            texto = datos.decode(enc)
            break
        except UnicodeDecodeError:
            continue

    if texto is None:
        raise ValueError("No fue posible leer el archivo.")

    lineas_limpias = [
        linea.rstrip(";")
        for linea in texto.splitlines()
    ]
    texto_limpio = "\n".join(lineas_limpias)

    primera = lineas_limpias[0] if lineas_limpias else ""

    separadores = [";", ",", "\t"]

    sep = max(
        separadores,
        key=lambda x: primera.count(x)
    )

    df = pd.read_csv(
        io.StringIO(texto_limpio),
        sep=sep,
        dtype=str,
        index_col=False
    )

    df.columns = [
        limpiar_texto(c)
        for c in df.columns
    ]

    return df.dropna(how="all")



def leer_archivo_tabular(uploaded_file):
    """Lee CSV o Excel, incluyendo planillas descargadas del SII."""
    nombre = getattr(uploaded_file, "name", "").lower()
    if nombre.endswith((".xlsx", ".xls")):
        datos = uploaded_file.getvalue()
        if not datos:
            raise ValueError("El archivo está vacío.")
        libro = pd.ExcelFile(io.BytesIO(datos))
        hojas = libro.sheet_names
        # El usuario puede escoger la hoja desde la interfaz; aquí se usa la primera.
        hoja = hojas[0]
        return pd.read_excel(io.BytesIO(datos), sheet_name=hoja, dtype=str)
    return leer_csv(uploaded_file)


def normalizar_columnas(df):
    df = df.copy()
    df.columns = [
        re.sub(r"\\s+", " ", limpiar_texto(c)).strip().lower()
        for c in df.columns
    ]
    return df


def leer_excel_con_hoja(uploaded_file, hoja=None):
    datos = uploaded_file.getvalue()
    if not datos:
        raise ValueError("El archivo está vacío.")
    libro = pd.ExcelFile(io.BytesIO(datos))
    if hoja is None:
        hoja = libro.sheet_names[0]
    return pd.read_excel(io.BytesIO(datos), sheet_name=hoja, dtype=str)

def serie_numero(serie):
    return serie.apply(numero)


def serie_fecha(serie):
    return serie.apply(fecha_iso)


# ============================================================
# TIPOS DE DOCUMENTOS SII (Criterios Oficiales)
# ============================================================

NOMBRES_DOC = {
    30: "Factura física / exenta no electrónica",
    32: "Factura de ventas/servicios exentos no electrónicos",
    33: "Factura electrónica",
    34: "Factura no afecta o exenta electrónica",
    39: "Boleta electrónica de ventas y servicios",
    41: "Boleta exenta electrónica",
    45: "Factura de compra",
    46: "Factura de compra electrónica",
    52: "Guía de despacho electrónica",
    55: "Nota de débito",
    56: "Nota de débito electrónica",
    60: "Nota de crédito",
    61: "Nota de crédito electrónica",
    801: "Orden de compra",
}

DOC_NOTA_CREDITO = {60, 61}
DOC_NOTA_DEBITO = {55, 56}

DOC_SOPORTADOS = {
    30,
    32,
    33,
    34,
    39,
    41,
    45,
    46,
    52,
    55,
    56,
    60,
    61,
}


def nombre_documento(tipo):
    try:
        tipo = int(tipo)
    except Exception:
        return str(tipo)

    return NOMBRES_DOC.get(
        tipo,
        f"Documento tipo {tipo}"
    )


# ============================================================
# ROLES CONTABLES
# ============================================================

ROLES = {
    "clientes": (
        "Clientes por cobrar",
        "1.1.03.01"
    ),
    "iva_credito": (
        "IVA Crédito Fiscal",
        "1.1.03.02"
    ),
    "proveedores": (
        "Proveedores por pagar",
        "2.1.01.01"
    ),
    "iva_debito": (
        "IVA Débito Fiscal",
        "2.1.01.02"
    ),
    "gasto_defecto": (
        "Gastos generales por defecto",
        "5.2.01"
    ),
    "ingreso_defecto": (
        "Ingresos por defecto (Ventas Afectas)",
        "4.1.01"
    ),
    "ingreso_exento": (
        "Ventas exentas",
        "4.1.04"
    ),
    "activo_fijo": (
        "Activo fijo",
        "1.2.01.01"
    ),
    "iva_no_recuperable": (
        "IVA no recuperable",
        "5.2.02"
    ),
    "iva_uso_comun": (
        "IVA de uso común",
        "5.2.03"
    ),
}


# ============================================================
# ESQUEMA Y MIGRACIONES
# ============================================================

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

    for _col, _tipo in [("uf_valor","REAL DEFAULT 0"),("salud_plan_pesos","REAL DEFAULT 0")]:
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
        conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS
            ux_ventas_doc
            ON ventas(tipo_doc, folio)
            WHERE tipo_doc IS NOT NULL
            AND folio IS NOT NULL
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
                        st.success(f"Cuenta {codigo_sel} actualizada correctamente.")
                        st.rerun()
                    except Exception as e:
                        conn.rollback()
                        st.error(f"No se pudo actualizar la cuenta: {e}")


# ============================================================
# REGLAS CONTABLES
# ============================================================

def buscar_regla(conn, tipo, rut, tipo_doc, razon_social=""):

    rut = normalizar_rut(rut)

    reglas = pd.read_sql_query(
        """
        SELECT *
        FROM reglas_contables
        WHERE tipo = ?
        AND activa = 1
        ORDER BY prioridad DESC, id DESC
        """,
        conn,
        params=(tipo,)
    )

    if reglas.empty:
        return None

    razon = limpiar_texto(
        razon_social
    ).lower()

    for _, regla in reglas.iterrows():

        regla_rut = normalizar_rut(
            regla["rut"]
        )

        regla_tipo_doc = regla["tipo_doc"]

        patron = limpiar_texto(
            regla["patron"]
        ).lower()

        if regla_rut and regla_rut != rut:
            continue

        if pd.notna(regla_tipo_doc):
            try:
                if int(regla_tipo_doc) != int(tipo_doc):
                    continue
            except Exception:
                continue

        if patron:
            if patron not in razon:
                continue

        return regla

    return None


def cuenta_habitual(conn, tipo, rut):

    tabla = (
        "proveedores"
        if tipo == "compras"
        else "clientes"
    )

    fila = conn.execute(
        f"""
        SELECT cuenta_defecto
        FROM {tabla}
        WHERE UPPER(TRIM(rut)) = ?
        """,
        (normalizar_rut(rut),)
    ).fetchone()

    if fila and fila["cuenta_defecto"]:
        return fila["cuenta_defecto"]

    return None


def preparar_documentos(conn, docs, tipo):

    compras = tipo == "compras"

    plan = Plan(conn)
    roles = cargar_roles(conn)

    if compras:
        rol_defecto = "gasto_defecto"
    else:
        rol_defecto = "ingreso_defecto"

    defecto = roles[rol_defecto]

    if defecto is None:
        raise ValueError(
            "La cuenta por defecto no está configurada."
        )

    existentes = set()

    if compras:

        filas = conn.execute(
            """
            SELECT
                p.rut,
                c.tipo_doc,
                c.folio
            FROM compras c
            JOIN proveedores p
                ON p.id = c.proveedor_id
            WHERE c.tipo_doc IS NOT NULL AND c.folio IS NOT NULL AND p.rut IS NOT NULL
            """
        ).fetchall()

        for fila in filas:
            try:
                existentes.add(
                    (
                        normalizar_rut(fila["rut"]),
                        int(fila["tipo_doc"]),
                        str(fila["folio"]).strip()
                    )
                )
            except Exception:
                pass

    else:

        filas = conn.execute(
            """
            SELECT tipo_doc, folio
            FROM ventas
            WHERE tipo_doc IS NOT NULL AND folio IS NOT NULL
            """
        ).fetchall()

        for fila in filas:
            try:
                existentes.add(
                    (
                        int(fila["tipo_doc"]),
                        str(fila["folio"]).strip()
                    )
                )
            except Exception:
                pass

    resultado = docs.copy()

    estados = []
    cuentas = []
    origenes = []
    signos = []
    observaciones = []

    vistos = set()

    for d in docs.itertuples():

        rut = normalizar_rut(d.rut)
        tipo_doc = int(d.tipo_doc)
        folio = str(d.folio).strip()

        clave = (
            (rut, tipo_doc, folio)
            if compras
            else
            (tipo_doc, folio)
        )

        obs = []

        if not validar_rut(rut):
            estado = "⚠️ RUT inválido"
            obs.append("Revisar RUT.")

        elif not d.fecha_doc:
            estado = "❌ Fecha inválida"

        elif tipo_doc not in DOC_SOPORTADOS:
            estado = "⚠️ Tipo no soportado"

        elif d.total == 0:
            estado = "⚠️ Monto cero"

        elif clave in existentes:
            estado = "🔁 Ya contabilizado"

        elif clave in vistos:
            estado = "🔁 Repetido en archivo"

        else:
            estado = "🟢 Nuevo"

        vistos.add(clave)

        # Criterio estricto de signo: Notas de crédito restan (-1), notas de débito y facturas suman (1)
        signo = (
            -1
            if tipo_doc in DOC_NOTA_CREDITO
            else 1
        )

        if compras:
            componentes = (
                d.exento
                + d.neto
                + d.iva
                + d.iva_no_rec
                + d.neto_af
                + d.iva_af
                + d.iva_uso_comun
            )
        else:
            componentes = (
                d.exento
                + d.neto
                + d.iva
            )

        diferencia = (
            d.total - componentes
        )

        if abs(diferencia) > 1:
            obs.append(
                f"Diferencia entre total y componentes: "
                f"{money(diferencia)}."
            )

        if d.exento > 0 and d.neto > 0:
            obs.append("Documento mixto: exento y afecto.")

        cuenta = None
        origen = None

        # Si es venta exenta (Código 34, 41 o 32), asignar por defecto la cuenta de ventas exentas
        if not compras and tipo_doc in {34, 41, 32}:
            exento_rol = roles.get("ingreso_exento")
            if exento_rol:
                cuenta = exento_rol[0]
                origen = f"Cuenta ventas exentas (Tipo {tipo_doc})"

        if not cuenta:
            regla = buscar_regla(
                conn,
                tipo,
                rut,
                tipo_doc,
                d.razon_social
            )

            if regla:
                cuenta = limpiar_texto(
                    regla["codigo_cuenta"]
                )
                origen = f"Regla #{int(regla['id'])}"

        if not cuenta and compras:
            habitual = cuenta_habitual(
                conn,
                tipo,
                rut
            )
            if habitual:
                cuenta = habitual
                origen = "Cuenta habitual"

        if not cuenta:
            cuenta = defecto[0]
            origen = "Cuenta por defecto"
            if estado == "🟢 Nuevo":
                estado = "🟡 Revisar cuenta"

        if cuenta not in plan.hojas:
            obs.append(
                "La cuenta sugerida no es imputable "
                "o no existe en el plan."
            )
            if estado.startswith("🟢"):
                estado = "🟡 Revisar cuenta"

        estados.append(estado)
        cuentas.append(cuenta)
        origenes.append(origen)
        signos.append(signo)
        observaciones.append(" ".join(obs))

    resultado["estado"] = estados
    resultado["cuenta_sugerida"] = cuentas
    resultado["cuenta_codigo"] = cuentas
    resultado["cuenta_origen"] = origenes
    resultado["signo"] = signos
    resultado["observaciones"] = observaciones

    return resultado


# ============================================================
# ASIENTOS (Con Blindaje Total y Cálculo Automático por Diferencia)
# ============================================================

def armar_asiento(doc, tipo, cuenta, roles):
    """
    Construye las líneas contables de un documento del RCV.

    REGLA FUNDAMENTAL:
    El tratamiento contable depende del TIPO DE DOCUMENTO,
    no del signo con que el SII entregue los montos.

    - Factura / Nota de Débito: efecto contable normal.
    - Nota de Crédito: revierte Debe y Haber.
    """

    # --------------------------------------------------------
    # FUNCIÓN AUXILIAR PARA OBTENER EL CÓDIGO DE UN ROL
    # --------------------------------------------------------
    #
    # cargar_roles() devuelve:
    #     (codigo, nombre)
    #
    # Esta función garantiza que al asiento siempre llegue
    # solamente el código contable.
    #

    def codigo_rol(nombre_rol, defecto=None):
        valor = roles.get(nombre_rol)

        if valor:
            if isinstance(valor, (tuple, list)):
                return valor[0]
            return valor

        if defecto is not None:
            if isinstance(defecto, (tuple, list)):
                return defecto[0]
            return defecto

        raise ValueError(
            f"No existe una cuenta configurada para el rol "
            f"'{nombre_rol}'."
        )

    # --------------------------------------------------------
    # 1. DATOS DEL DOCUMENTO
    # --------------------------------------------------------

    tipo_doc = int(getattr(doc, "tipo_doc", 0) or 0)

    # El tipo de documento determina el tratamiento.
    # Las NC revierten el asiento.
    es_nc = tipo_doc in DOC_NOTA_CREDITO

    # Usamos valores absolutos porque el signo del archivo SII
    # no determina por sí mismo el tratamiento contable.
    total = abs(float(getattr(doc, "total", 0) or 0))
    neto = abs(float(getattr(doc, "neto", 0) or 0))
    exento = abs(float(getattr(doc, "exento", 0) or 0))

    iva = abs(float(getattr(doc, "iva", 0) or 0))
    iva_no_rec = abs(float(getattr(doc, "iva_no_rec", 0) or 0))

    # Nombres reales utilizados por normalizar_rcv().
    neto_af = abs(float(getattr(doc, "neto_af", 0) or 0))
    iva_af = abs(float(getattr(doc, "iva_af", 0) or 0))
    iva_uso_comun = abs(
        float(getattr(doc, "iva_uso_comun", 0) or 0)
    )

    lineas_normales = []

    # --------------------------------------------------------
    # 2. COMPRAS
    # --------------------------------------------------------

    if tipo == "compras":

        cuenta_principal = cuenta

        # ----------------------------------------------------
        # BASE PRINCIPAL DE LA COMPRA
        # ----------------------------------------------------

        principal = neto + exento

        # Si el RCV no entrega base neta/exenta utilizable,
        # reconstruimos la base por diferencia.
        if principal <= 0.001 and neto_af <= 0.001:

            impuestos_separados = (
                iva
                + iva_no_rec
                + iva_uso_comun
                + iva_af
            )

            principal = max(
                total - impuestos_separados,
                0.0
            )

        # ----------------------------------------------------
        # DEBE: GASTO / COMPRA PRINCIPAL
        # ----------------------------------------------------

        if principal > 0.001:
            lineas_normales.append(
                (cuenta_principal, principal, 0.0)
            )

        # ----------------------------------------------------
        # ACTIVO FIJO
        # ----------------------------------------------------

        if neto_af > 0.001:
            codigo_activo_fijo = codigo_rol(
                "activo_fijo",
                cuenta_principal
            )

            lineas_normales.append(
                (codigo_activo_fijo, neto_af, 0.0)
            )

        # ----------------------------------------------------
        # IVA CRÉDITO FISCAL
        # ----------------------------------------------------
        #
        # Si el IVA de activo fijo está informado aparte,
        # evitamos duplicarlo dentro del IVA general.
        #

        iva_credito = max(iva - iva_af, 0.0)

        if iva_credito > 0.001:
            lineas_normales.append(
                (
                    codigo_rol("iva_credito"),
                    iva_credito,
                    0.0
                )
            )

        # ----------------------------------------------------
        # IVA DE ACTIVO FIJO
        # ----------------------------------------------------

        if iva_af > 0.001:
            lineas_normales.append(
                (
                    codigo_rol("iva_credito"),
                    iva_af,
                    0.0
                )
            )

        # ----------------------------------------------------
        # IVA NO RECUPERABLE
        # ----------------------------------------------------

        if iva_no_rec > 0.001:
            lineas_normales.append(
                (
                    codigo_rol(
                        "iva_no_recuperable",
                        cuenta_principal
                    ),
                    iva_no_rec,
                    0.0
                )
            )

        # ----------------------------------------------------
        # IVA DE USO COMÚN
        # ----------------------------------------------------

        if iva_uso_comun > 0.001:
            lineas_normales.append(
                (
                    codigo_rol(
                        "iva_uso_comun",
                        cuenta_principal
                    ),
                    iva_uso_comun,
                    0.0
                )
            )

        # ----------------------------------------------------
        # CUADRATURA AUTOMÁTICA
        # ----------------------------------------------------
        #
        # El Haber a Proveedores debe ser exactamente igual
        # al total del documento.
        #

        debe_actual = sum(
            x[1] for x in lineas_normales
        )

        diferencia = round(
            total - debe_actual,
            2
        )

        if abs(diferencia) > 0.01:

            encontrada = False

            # Primero intentamos absorber la diferencia
            # en la cuenta principal de compra/gasto.
            for i, (codigo, debe, haber) in enumerate(
                lineas_normales
            ):

                if (
                    codigo == cuenta_principal
                    and debe > 0
                ):

                    nuevo_debe = debe + diferencia

                    if nuevo_debe < -0.01:
                        raise ValueError(
                            f"Documento {doc.folio}: "
                            "la composición tributaria supera "
                            "el total del documento."
                        )

                    lineas_normales[i] = (
                        codigo,
                        max(nuevo_debe, 0.0),
                        haber
                    )

                    encontrada = True
                    break

            # Si no había línea principal y falta valor,
            # agregamos la diferencia a la cuenta seleccionada.
            if not encontrada and diferencia > 0.01:
                lineas_normales.append(
                    (
                        cuenta_principal,
                        diferencia,
                        0.0
                    )
                )

        # ----------------------------------------------------
        # HABER: PROVEEDORES
        # ----------------------------------------------------

        lineas_normales.append(
            (
                codigo_rol("proveedores"),
                0.0,
                total
            )
        )

    # --------------------------------------------------------
    # 3. VENTAS
    # --------------------------------------------------------

    elif tipo == "ventas":

        cuenta_ventas = cuenta

        # ----------------------------------------------------
        # DEBE: CLIENTES POR COBRAR
        # ----------------------------------------------------

        lineas_normales.append(
            (
                codigo_rol("clientes"),
                total,
                0.0
            )
        )

        # ----------------------------------------------------
        # HABER: IVA DÉBITO FISCAL
        # ----------------------------------------------------

        if iva > 0.001:
            lineas_normales.append(
                (
                    codigo_rol("iva_debito"),
                    0.0,
                    iva
                )
            )

        # ----------------------------------------------------
        # HABER: INGRESO POR VENTA
        # ----------------------------------------------------

        venta_base = round(
            total - iva,
            2
        )

        if venta_base > 0.001:
            lineas_normales.append(
                (
                    cuenta_ventas,
                    0.0,
                    venta_base
                )
            )

    else:
        raise ValueError(
            f"Tipo de operación no reconocido: {tipo}"
        )

    # --------------------------------------------------------
    # 4. NOTAS DE CRÉDITO
    # --------------------------------------------------------
    #
    # Las NC revierten el asiento normal.
    #
    # Ejemplo compra:
    #   Factura:
    #       Debe  Gasto / IVA
    #       Haber Proveedores
    #
    #   NC:
    #       Debe  Proveedores
    #       Haber Gasto / IVA
    #
    # Lo mismo aplica inversamente a las ventas.
    #

    if es_nc:
        lineas_normales = [
            (codigo, haber, debe)
            for codigo, debe, haber
            in lineas_normales
        ]

    # --------------------------------------------------------
    # 5. LIMPIEZA DE LÍNEAS
    # --------------------------------------------------------

    lineas = []

    for codigo, debe, haber in lineas_normales:

        # Blindaje adicional:
        # nunca permitimos que una tupla (codigo, nombre)
        # llegue al Libro Diario.
        if isinstance(codigo, (tuple, list)):
            codigo = codigo[0]

        if not codigo:
            raise ValueError(
                f"Documento {doc.folio}: "
                "se intentó contabilizar una cuenta vacía."
            )

        codigo = str(codigo).strip()

        debe = round(float(debe), 2)
        haber = round(float(haber), 2)

        if (
            abs(debe) <= 0.001
            and abs(haber) <= 0.001
        ):
            continue

        if debe < -0.001 or haber < -0.001:
            raise ValueError(
                f"Documento {doc.folio}: "
                "se generó un monto contable negativo."
            )

        lineas.append(
            (
                codigo,
                debe,
                haber
            )
        )

    # --------------------------------------------------------
    # 6. CONTROL CONTABLE FINAL
    # --------------------------------------------------------

    total_debe = round(
        sum(x[1] for x in lineas),
        2
    )

    total_haber = round(
        sum(x[2] for x in lineas),
        2
    )

    if abs(total_debe - total_haber) > 0.01:
        raise ValueError(
            f"Documento {doc.folio}: "
            f"asiento descuadrado. "
            f"Debe={total_debe}, "
            f"Haber={total_haber}"
        )

    return lineas


def siguiente_asiento(conn):

    fila = conn.execute(
        """
        SELECT COALESCE(
            MAX(asiento_id),
            0
        )
        FROM libro_diario
        """
    ).fetchone()

    return int(fila[0] or 0)


# ============================================================
# CONTABILIZACIÓN
# ============================================================

def obtener_entidad(
    conn,
    tabla,
    rut,
    razon_social
):

    rut = normalizar_rut(rut)

    fila = conn.execute(
        f"""
        SELECT id
        FROM {tabla}
        WHERE UPPER(TRIM(rut)) = ?
        """,
        (rut,)
    ).fetchone()

    if fila:
        conn.execute(
            f"""
            UPDATE {tabla}
            SET nombre = COALESCE(
                NULLIF(?, ''),
                nombre
            ),
            razon_social = COALESCE(
                NULLIF(?, ''),
                razon_social
            )
            WHERE id = ?
            """,
            (
                razon_social,
                razon_social,
                fila["id"]
            )
        )
        return fila["id"]

    ahora = datetime.now().isoformat(timespec="seconds")

    cur = conn.execute(
        f"""
        INSERT INTO {tabla}
        (
            rut,
            nombre,
            razon_social,
            activo,
            fecha_creacion
        )
        VALUES (?, ?, ?, 1, ?)
        """,
        (
            rut,
            razon_social,
            razon_social,
            ahora
        )
    )

    return cur.lastrowid


def contabilizar_rcv(
    conn,
    tipo,
    docs,
    fecha_modo="documento",
    recordar=True
):

    compras = tipo == "compras"

    plan = Plan(conn)
    roles = cargar_roles(conn)

    lote = (
        "RCV-COMPRAS-"
        if compras
        else "RCV-VENTAS-"
    ) + datetime.now().strftime("%Y%m%d-%H%M%S")

    cur = conn.cursor()
    asiento = siguiente_asiento(conn)

    documentos = 0
    total_debe = 0.0
    cuentas_recordadas = 0

    try:

        for d in docs.itertuples():

            if d.cuenta_codigo not in plan.hojas:
                raise ValueError(
                    f"La cuenta {d.cuenta_codigo} no es imputable."
                )

            tabla_entidad = (
                "proveedores"
                if compras
                else "clientes"
            )

            entidad_id = obtener_entidad(
                conn,
                tabla_entidad,
                d.rut,
                d.razon_social
            )

            fecha = (
                d.fecha_doc
                if fecha_modo == "documento"
                else (d.fecha_recepcion or d.fecha_doc)
            )

            glosa = (
                f"{nombre_documento(d.tipo_doc)} "
                f"N° {d.folio} - "
                f"{d.razon_social}"
            )

            lineas = armar_asiento(
                d,
                tipo,
                d.cuenta_codigo,
                roles
            )

            asiento += 1

            signo_val = int(d.signo)

            if compras:

                cuenta_nombre = plan.hojas[d.cuenta_codigo]
                centro = "General / Ninguno"

                fila_cc = conn.execute(
                    """
                    SELECT centro_costo
                    FROM proveedores
                    WHERE id = ?
                    """,
                    (entidad_id,)
                ).fetchone()

                if fila_cc and fila_cc["centro_costo"]:
                    centro = fila_cc["centro_costo"]

                cur.execute(
                    """
                    INSERT INTO compras
                    (
                        fecha,
                        proveedor_id,
                        cuenta_gasto,
                        centro_costo,
                        monto_neto,
                        iva,
                        monto_total,
                        glosa,
                        tipo_doc,
                        folio,
                        lote_id
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        fecha,
                        entidad_id,
                        cuenta_nombre,
                        centro,
                        (float(d.neto) + float(d.exento) + float(d.neto_af)) * signo_val,
                        (float(d.iva) + float(d.iva_af)) * signo_val,
                        float(d.total) * signo_val,
                        glosa,
                        int(d.tipo_doc),
                        str(d.folio),
                        lote
                    )
                )

            else:

                cuenta_nombre = plan.hojas[d.cuenta_codigo]

                cur.execute(
                    """
                    INSERT INTO ventas
                    (
                        fecha,
                        cliente_id,
                        cuenta_ingreso,
                        monto_neto,
                        iva,
                        monto_total,
                        glosa,
                        tipo_doc,
                        folio,
                        lote_id
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        fecha,
                        entidad_id,
                        cuenta_nombre,
                        (float(d.neto) + float(d.exento)) * signo_val,
                        float(d.iva) * signo_val,
                        float(d.total) * signo_val,
                        glosa,
                        int(d.tipo_doc),
                        str(d.folio),
                        lote
                    )
                )

            for codigo, debe, haber in lineas:

                cur.execute(
                    """
                    INSERT INTO libro_diario
                    (
                        fecha,
                        cuenta,
                        debe,
                        haber,
                        glosa,
                        centro_costo,
                        codigo_cuenta,
                        asiento_id,
                        lote_id,
                        origen
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        fecha,
                        plan.todos[codigo],
                        debe,
                        haber,
                        glosa,
                        "General / Ninguno",
                        codigo,
                        asiento,
                        lote,
                        (
                            "RCV Compras"
                            if compras
                            else "RCV Ventas"
                        )
                    )
                )

                total_debe += debe

            if recordar:
                if d.cuenta_codigo != d.cuenta_sugerida:
                    cur.execute(
                        f"""
                        UPDATE {tabla_entidad}
                        SET cuenta_defecto = ?
                        WHERE id = ?
                        """,
                        (
                            d.cuenta_codigo,
                            entidad_id
                        )
                    )
                    cuentas_recordadas += 1

            documentos += 1

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    return {
        "lote": lote,
        "documentos": documentos,
        "total_debe": total_debe,
        "cuentas_recordadas": cuentas_recordadas
    }


# ============================================================
# PAGOS
# ============================================================

def registrar_pago_cliente(
    conn,
    cliente_id,
    fecha,
    monto,
    medio_pago,
    cuenta_banco,
    glosa
):

    roles = cargar_roles(conn)
    plan = Plan(conn)

    if roles["clientes"] is None:
        raise ValueError("Cuenta de clientes no configurada.")

    if not cuenta_banco:
        raise ValueError("Debe seleccionar una cuenta bancaria.")

    if cuenta_banco not in plan.hojas:
        raise ValueError("La cuenta bancaria no es imputable.")

    lote = "PAGO-CLIENTE-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO pagos_clientes
        (
            fecha,
            cliente_id,
            monto,
            medio_pago,
            cuenta_banco,
            glosa,
            lote_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            fecha,
            cliente_id,
            monto,
            medio_pago,
            cuenta_banco,
            glosa,
            lote
        )
    )

    asiento = siguiente_asiento(conn) + 1
    nombre_banco = plan.hojas[cuenta_banco]

    nombre_cliente = conn.execute(
        """
        SELECT COALESCE(
            NULLIF(razon_social, ''),
            nombre
        )
        FROM clientes
        WHERE id = ?
        """,
        (cliente_id,)
    ).fetchone()[0]

    glosa_final = glosa or f"Pago cliente - {nombre_cliente}"

    cur.execute(
        """
        INSERT INTO libro_diario
        (
            fecha,
            cuenta,
            debe,
            haber,
            glosa,
            centro_costo,
            codigo_cuenta,
            asiento_id,
            lote_id,
            origen
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            fecha,
            nombre_banco,
            monto,
            0,
            glosa_final,
            "General / Ninguno",
            cuenta_banco,
            asiento,
            lote,
            "Pago de cliente"
        )
    )

    cur.execute(
        """
        INSERT INTO libro_diario
        (
            fecha,
            cuenta,
            debe,
            haber,
            glosa,
            centro_costo,
            codigo_cuenta,
            asiento_id,
            lote_id,
            origen
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            fecha,
            roles["clientes"][1],
            0,
            monto,
            glosa_final,
            "General / Ninguno",
            roles["clientes"][0],
            asiento,
            lote,
            "Pago de cliente"
        )
    )

    conn.commit()
    return lote


def registrar_pago_proveedor(
    conn,
    proveedor_id,
    fecha,
    monto,
    medio_pago,
    cuenta_banco,
    glosa
):

    roles = cargar_roles(conn)
    plan = Plan(conn)

    if roles["proveedores"] is None:
        raise ValueError("Cuenta de proveedores no configurada.")

    if cuenta_banco not in plan.hojas:
        raise ValueError("La cuenta bancaria no es imputable.")

    lote = "PAGO-PROVEEDOR-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO pagos_proveedores
        (
            fecha,
            proveedor_id,
            monto,
            medio_pago,
            cuenta_banco,
            glosa,
            lote_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            fecha,
            proveedor_id,
            monto,
            medio_pago,
            cuenta_banco,
            glosa,
            lote
        )
    )

    asiento = siguiente_asiento(conn) + 1
    nombre_banco = plan.hojas[cuenta_banco]

    nombre_proveedor = conn.execute(
        """
        SELECT COALESCE(
            NULLIF(razon_social, ''),
            nombre
        )
        FROM proveedores
        WHERE id = ?
        """,
        (proveedor_id,)
    ).fetchone()[0]

    glosa_final = glosa or f"Pago proveedor - {nombre_proveedor}"

    cur.execute(
        """
        INSERT INTO libro_diario
        (
            fecha,
            cuenta,
            debe,
            haber,
            glosa,
            centro_costo,
            codigo_cuenta,
            asiento_id,
            lote_id,
            origen
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            fecha,
            roles["proveedores"][1],
            monto,
            0,
            glosa_final,
            "General / Ninguno",
            roles["proveedores"][0],
            asiento,
            lote,
            "Pago a proveedor"
        )
    )

    cur.execute(
        """
        INSERT INTO libro_diario
        (
            fecha,
            cuenta,
            debe,
            haber,
            glosa,
            centro_costo,
            codigo_cuenta,
            asiento_id,
            lote_id,
            origen
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            fecha,
            nombre_banco,
            0,
            monto,
            glosa_final,
            "General / Ninguno",
            cuenta_banco,
            asiento,
            lote,
            "Pago a proveedor"
        )
    )

    conn.commit()
    return lote


# ============================================================
# ESTADOS DE CUENTA
# ============================================================

def estado_cuenta_cliente(
    conn,
    cliente_id,
    desde=None,
    hasta=None
):

    cliente = conn.execute(
        """
        SELECT *
        FROM clientes
        WHERE id = ?
        """,
        (cliente_id,)
    ).fetchone()

    if not cliente:
        return pd.DataFrame()

    params = [cliente_id]
    filtro = ""

    if desde:
        filtro += " AND v.fecha >= ? "
        params.append(desde)

    if hasta:
        filtro += " AND v.fecha <= ? "
        params.append(hasta)

    ventas = pd.read_sql_query(
        f"""
        SELECT
            v.fecha,
            v.tipo_doc,
            v.folio,
            v.glosa,
            v.monto_total AS cargo,
            0 AS abono
        FROM ventas v
        WHERE v.cliente_id = ?
        {filtro}
        ORDER BY v.fecha, v.id
        """,
        conn,
        params=params
    )

    params = [cliente_id]
    filtro = ""

    if desde:
        filtro += " AND p.fecha >= ? "
        params.append(desde)

    if hasta:
        filtro += " AND p.fecha <= ? "
        params.append(hasta)

    pagos = pd.read_sql_query(
        f"""
        SELECT
            p.fecha,
            NULL AS tipo_doc,
            NULL AS folio,
            COALESCE(
                p.glosa,
                'Pago recibido'
            ) AS glosa,
            0 AS cargo,
            p.monto AS abono
        FROM pagos_clientes p
        WHERE p.cliente_id = ?
        {filtro}
        ORDER BY p.fecha, p.id
        """,
        conn,
        params=params
    )

    df = pd.concat([ventas, pagos], ignore_index=True)

    if df.empty:
        return df

    df = df.sort_values(["fecha"]).reset_index(drop=True)
    df["cargo"] = pd.to_numeric(df["cargo"])
    df["abono"] = pd.to_numeric(df["abono"])
    df["saldo"] = (df["cargo"] - df["abono"]).cumsum()

    df["Documento"] = df.apply(
        lambda r: (
            f"{nombre_documento(r['tipo_doc'])} N° {r['folio']}"
            if pd.notna(r["tipo_doc"])
            else ""
        ),
        axis=1
    )

    return df


def estado_cuenta_proveedor(
    conn,
    proveedor_id,
    desde=None,
    hasta=None
):

    proveedor = conn.execute(
        """
        SELECT *
        FROM proveedores
        WHERE id = ?
        """,
        (proveedor_id,)
    ).fetchone()

    if not proveedor:
        return pd.DataFrame()

    params = [proveedor_id]
    filtro = ""

    if desde:
        filtro += " AND c.fecha >= ? "
        params.append(desde)

    if hasta:
        filtro += " AND c.fecha <= ? "
        params.append(hasta)

    compras = pd.read_sql_query(
        f"""
        SELECT
            c.fecha,
            c.tipo_doc,
            c.folio,
            c.glosa,
            c.monto_total AS cargo,
            0 AS abono
        FROM compras c
        WHERE c.proveedor_id = ?
        {filtro}
        ORDER BY c.fecha, c.id
        """,
        conn,
        params=params
    )

    params = [proveedor_id]
    filtro = ""

    if desde:
        filtro += " AND p.fecha >= ? "
        params.append(desde)

    if hasta:
        filtro += " AND p.fecha <= ? "
        params.append(hasta)

    pagos = pd.read_sql_query(
        f"""
        SELECT
            p.fecha,
            NULL AS tipo_doc,
            NULL AS folio,
            COALESCE(
                p.glosa,
                'Pago realizado'
            ) AS glosa,
            0 AS cargo,
            p.monto AS abono
        FROM pagos_proveedores p
        WHERE p.proveedor_id = ?
        {filtro}
        ORDER BY p.fecha, p.id
        """,
        conn,
        params=params
    )

    df = pd.concat([compras, pagos], ignore_index=True)

    if df.empty:
        return df

    df = df.sort_values(["fecha"]).reset_index(drop=True)
    df["cargo"] = pd.to_numeric(df["cargo"])
    df["abono"] = pd.to_numeric(df["abono"])
    df["saldo"] = (df["cargo"] - df["abono"]).cumsum()

    df["Documento"] = df.apply(
        lambda r: (
            f"{nombre_documento(r['tipo_doc'])} N° {r['folio']}"
            if pd.notna(r["tipo_doc"])
            else ""
        ),
        axis=1
    )

    return df


# ============================================================
# CONCILIACIÓN
# ============================================================

def conciliacion_clientes(conn):

    roles = cargar_roles(conn)
    if roles["clientes"] is None:
        return pd.DataFrame()

    codigo = roles["clientes"][0]

    saldo_contable = conn.execute(
        """
        SELECT
            COALESCE(SUM(debe), 0)
            -
            COALESCE(SUM(haber), 0)
        FROM libro_diario
        WHERE codigo_cuenta = ?
        """,
        (codigo,)
    ).fetchone()[0]

    clientes = pd.read_sql_query(
        """
        SELECT
            c.id,
            c.rut,
            COALESCE(
                NULLIF(c.razon_social, ''),
                c.nombre
            ) AS cliente,
            COALESCE(
                (
                    SELECT SUM(v.monto_total)
                    FROM ventas v
                    WHERE v.cliente_id = c.id
                ),
                0
            )
            -
            COALESCE(
                (
                    SELECT SUM(p.monto)
                    FROM pagos_clientes p
                    WHERE p.cliente_id = c.id
                ),
                0
            ) AS saldo_auxiliar
        FROM clientes c
        ORDER BY cliente
        """,
        conn
    )

    saldo_auxiliar = clientes["saldo_auxiliar"].sum() if not clientes.empty else 0

    return pd.DataFrame(
        [{
            "Cuenta contable": codigo,
            "Saldo contable": saldo_contable,
            "Saldo auxiliar": saldo_auxiliar,
            "Diferencia": saldo_contable - saldo_auxiliar,
        }]
    )


def conciliacion_proveedores(conn):

    roles = cargar_roles(conn)
    if roles["proveedores"] is None:
        return pd.DataFrame()

    codigo = roles["proveedores"][0]

    saldo_contable = conn.execute(
        """
        SELECT
            COALESCE(SUM(haber), 0)
            -
            COALESCE(SUM(debe), 0)
        FROM libro_diario
        WHERE codigo_cuenta = ?
        """,
        (codigo,)
    ).fetchone()[0]

    proveedores = pd.read_sql_query(
        """
        SELECT
            p.id,
            p.rut,
            COALESCE(
                NULLIF(p.razon_social, ''),
                p.nombre
            ) AS proveedor,
            COALESCE(
                (
                    SELECT SUM(c.monto_total)
                    FROM compras c
                    WHERE c.proveedor_id = p.id
                ),
                0
            )
            -
            COALESCE(
                (
                    SELECT SUM(pg.monto)
                    FROM pagos_proveedores pg
                    WHERE pg.proveedor_id = p.id
                ),
                0
            ) AS saldo_auxiliar
        FROM proveedores p
        ORDER BY proveedor
        """,
        conn
    )

    saldo_auxiliar = proveedores["saldo_auxiliar"].sum() if not proveedores.empty else 0

    return pd.DataFrame(
        [{
            "Cuenta contable": codigo,
            "Saldo contable": saldo_contable,
            "Saldo auxiliar": saldo_auxiliar,
            "Diferencia": saldo_contable - saldo_auxiliar,
        }]
    )


# ============================================================
# MAYOR Y BALANCE
# ============================================================

def obtener_mayor(
    conn,
    codigo,
    desde=None,
    hasta=None
):

    plan = Plan(conn)
    if codigo not in plan.todos:
        return pd.DataFrame()

    filtros = ["codigo_cuenta = ?"]
    params = [codigo]

    if desde:
        filtros.append("fecha >= ?")
        params.append(desde)

    if hasta:
        filtros.append("fecha <= ?")
        params.append(hasta)

    where = " AND ".join(filtros)

    df = pd.read_sql_query(
        f"""
        SELECT
            fecha AS Fecha,
            asiento_id AS Asiento,
            glosa AS Glosa,
            debe AS Debe,
            haber AS Haber,
            (debe - haber) AS Movimiento
        FROM libro_diario
        WHERE {where}
        ORDER BY fecha, id
        """,
        conn,
        params=params
    )

    if not df.empty:
        df["Saldo"] = df["Movimiento"].cumsum()

    return df


def balance_comprobacion(
    conn,
    desde=None,
    hasta=None
):

    filtros = []
    params = []

    if desde:
        filtros.append("d.fecha >= ?")
        params.append(desde)

    if hasta:
        filtros.append("d.fecha <= ?")
        params.append(hasta)

    where = ""
    if filtros:
        where = "WHERE " + " AND ".join(filtros)

    return pd.read_sql_query(
        f"""
        SELECT
            p.codigo AS Codigo,
            p.nombre AS Cuenta,
            p.tipo AS Tipo,
            COALESCE(SUM(d.debe), 0) AS Debe,
            COALESCE(SUM(d.haber), 0) AS Haber,
            COALESCE(SUM(d.debe), 0)
            -
            COALESCE(SUM(d.haber), 0)
            AS Saldo
        FROM plan_cuentas p
        LEFT JOIN libro_diario d
            ON d.codigo_cuenta = p.codigo
        {where}
        GROUP BY
            p.codigo,
            p.nombre,
            p.tipo
        HAVING
            ABS(Debe) > 0.001
            OR ABS(Haber) > 0.001
        ORDER BY p.codigo
        """,
        conn,
        params=params
    )


# ============================================================
# LOTES
# ============================================================

def listar_lotes(conn):

    return pd.read_sql_query(
        """
        SELECT
            lote_id AS Lote,
            origen AS Origen,
            MIN(fecha) AS Desde,
            MAX(fecha) AS Hasta,
            COUNT(DISTINCT asiento_id) AS Asientos,
            SUM(debe) AS Total_Debe,
            SUM(haber) AS Total_Haber
        FROM libro_diario
        WHERE lote_id IS NOT NULL
        GROUP BY
            lote_id,
            origen
        ORDER BY lote_id DESC
        """,
        conn
    )


def deshacer_lote(conn, lote):

    cur = conn.cursor()
    try:
        borrados = {}
        for tabla in (
            "libro_diario",
            "compras",
            "ventas",
            "pagos_clientes",
            "pagos_proveedores",
        ):
            resultado = cur.execute(
                f"""
                DELETE FROM {tabla}
                WHERE lote_id = ?
                """,
                (lote,)
            )
            borrados[tabla] = resultado.rowcount

        conn.commit()
        return borrados
    except Exception:
        conn.rollback()
        raise


# ============================================================
# REGLAS CONTABLES UI
# ============================================================

def guardar_regla(
    conn,
    tipo,
    rut,
    patron,
    tipo_doc,
    codigo,
    prioridad,
    descripcion
):

    conn.execute(
        """
        INSERT INTO reglas_contables
        (
            tipo,
            rut,
            patron,
            tipo_doc,
            codigo_cuenta,
            prioridad,
            activa,
            descripcion
        )
        VALUES (?, ?, ?, ?, ?, ?, 1, ?)
        """,
        (
            tipo,
            normalizar_rut(rut),
            patron,
            tipo_doc,
            codigo,
            prioridad,
            descripcion
        )
    )
    conn.commit()




# ============================================================
# RECLASIFICACIÓN CONTABLE DE COMPRAS YA CONTABILIZADAS
# ============================================================

def compras_para_reclasificar(conn):
    """Devuelve compras contabilizadas con la cuenta actualmente registrada."""
    return pd.read_sql_query(
        """
        SELECT
            c.id AS compra_id,
            c.fecha,
            p.rut,
            COALESCE(p.razon_social, p.nombre, '') AS proveedor,
            c.tipo_doc,
            c.folio,
            c.monto_neto,
            c.monto_total,
            c.cuenta_gasto,
            c.lote_id
        FROM compras c
        LEFT JOIN proveedores p ON p.id = c.proveedor_id
        ORDER BY c.fecha DESC, c.id DESC
        """,
        conn
    )


def codigo_cuenta_por_nombre(conn, nombre):
    fila = conn.execute(
        "SELECT codigo FROM plan_cuentas WHERE nombre = ? ORDER BY nivel DESC LIMIT 1",
        (limpiar_texto(nombre),)
    ).fetchone()
    return limpiar_texto(fila["codigo"]) if fila else None


def reclasificar_compras(conn, compra_ids, nueva_cuenta, recordar_proveedor=False):
    """Genera un asiento de reclasificación sin modificar IVA ni Proveedores."""
    ids = [int(x) for x in compra_ids]
    if not ids:
        raise ValueError("Selecciona al menos una compra.")

    plan = Plan(conn)
    if nueva_cuenta not in plan.hojas:
        raise ValueError("La nueva cuenta no existe o no es imputable.")

    placeholders = ",".join("?" for _ in ids)
    compras = conn.execute(
        f"""
        SELECT c.*, p.rut, COALESCE(p.razon_social,p.nombre,'') AS proveedor
        FROM compras c
        LEFT JOIN proveedores p ON p.id=c.proveedor_id
        WHERE c.id IN ({placeholders})
        ORDER BY c.fecha, c.id
        """,
        ids
    ).fetchall()

    if len(compras) != len(ids):
        raise ValueError("No fue posible localizar todas las compras seleccionadas.")

    asiento = siguiente_asiento(conn)
    lote = "RECLAS-COMPRAS-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    reclasificadas = 0
    omitidas = 0

    try:
        for c in compras:
            if periodo_cerrado(conn, c["fecha"]):
                raise ValueError(f"El período {str(c['fecha'])[:7]} está cerrado. Reabre el período antes de reclasificar.")

            cuenta_anterior = codigo_cuenta_por_nombre(conn, c["cuenta_gasto"])
            if not cuenta_anterior:
                raise ValueError(f"No pude identificar el código de la cuenta actual de la compra folio {c['folio']}.")
            if cuenta_anterior == nueva_cuenta:
                omitidas += 1
                continue

            # La base reclasificable debe salir del asiento REAL que generó el RCV,
            # no solamente de compras.monto_neto. Algunos RCV (por ejemplo ciertos
            # servicios) pueden venir con neto/exento en cero y armar_asiento()
            # reconstruye correctamente la base por diferencia contra el total.
            # En esos casos el Libro Diario sí contiene el monto contable correcto.
            fila_base = conn.execute(
                """
                SELECT
                    COALESCE(SUM(debe), 0) AS debe,
                    COALESCE(SUM(haber), 0) AS haber
                FROM libro_diario
                WHERE lote_id = ?
                  AND fecha = ?
                  AND glosa = ?
                  AND codigo_cuenta = ?
                  AND COALESCE(origen, '') NOT LIKE 'Reclasificación%'
                """,
                (c["lote_id"], c["fecha"], c["glosa"], cuenta_anterior)
            ).fetchone()

            debe_base = round(float(fila_base["debe"] or 0), 2) if fila_base else 0.0
            haber_base = round(float(fila_base["haber"] or 0), 2) if fila_base else 0.0
            monto = round(debe_base - haber_base, 2)

            # Respaldo para registros antiguos en los que la trazabilidad del lote
            # o la glosa no estuviera disponible. Solo se usa si el Diario no dio base.
            if abs(monto) <= 0.001:
                monto = round(float(c["monto_neto"] or 0), 2)

            if abs(monto) <= 0.001:
                raise ValueError(
                    f"La compra folio {c['folio']} no tiene base reclasificable "
                    "en el asiento original del Libro Diario."
                )

            asiento += 1
            glosa = (
                f"Reclasificación compra {nombre_documento(c['tipo_doc'])} N° {c['folio']} - "
                f"{c['proveedor']} | {cuenta_anterior} → {nueva_cuenta}"
            )

            # Facturas: Debe nueva / Haber anterior. NC: efecto inverso.
            if monto > 0:
                lineas = [(nueva_cuenta, abs(monto), 0.0), (cuenta_anterior, 0.0, abs(monto))]
            else:
                lineas = [(cuenta_anterior, abs(monto), 0.0), (nueva_cuenta, 0.0, abs(monto))]

            for codigo, debe, haber in lineas:
                conn.execute(
                    """
                    INSERT INTO libro_diario
                    (fecha, cuenta, debe, haber, glosa, centro_costo, codigo_cuenta, asiento_id, lote_id, origen)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (c["fecha"], plan.todos[codigo], debe, haber, glosa,
                     c["centro_costo"] or "General / Ninguno", codigo, asiento, lote, "Reclasificación RCV Compras")
                )

            conn.execute(
                "UPDATE compras SET cuenta_gasto=? WHERE id=?",
                (plan.todos[nueva_cuenta], c["id"])
            )

            if recordar_proveedor and c["proveedor_id"]:
                conn.execute(
                    "UPDATE proveedores SET cuenta_defecto=? WHERE id=?",
                    (nueva_cuenta, c["proveedor_id"])
                )

            reclasificadas += 1

        conn.execute(
            "INSERT INTO auditoria(fecha_hora, usuario, accion, detalle) VALUES (?,?,?,?)",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "admin", "RECLASIFICACIÓN RCV COMPRAS",
             f"Lote {lote}: {reclasificadas} compra(s) a {nueva_cuenta}; omitidas {omitidas}")
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return {"reclasificadas": reclasificadas, "omitidas": omitidas, "lote": lote}

# ============================================================
# CONTROL CONTABLE Y REPORTES
# ============================================================

def registrar_auditoria(conn, accion, detalle):
    conn.execute(
        "INSERT INTO auditoria(fecha_hora, usuario, accion, detalle) VALUES (?,?,?,?)",
        (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "admin", accion, detalle)
    )
    conn.commit()


def periodo_estado(conn, periodo):
    fila = conn.execute("SELECT estado FROM periodos_contables WHERE periodo=?", (periodo,)).fetchone()
    return fila[0] if fila else "ABIERTO"


def asegurar_periodo(conn, periodo):
    conn.execute("INSERT OR IGNORE INTO periodos_contables(periodo, estado) VALUES (?, 'ABIERTO')", (periodo,))
    conn.commit()


def periodo_cerrado(conn, fecha_texto):
    periodo = str(fecha_texto)[:7]
    return periodo_estado(conn, periodo) == "CERRADO"


def saldo_cuenta(conn, codigo, hasta=None):
    sql = "SELECT COALESCE(SUM(debe),0)-COALESCE(SUM(haber),0) FROM libro_diario WHERE codigo_cuenta=?"
    params=[codigo]
    if hasta:
        sql += " AND fecha <= ?"
        params.append(hasta)
    return float(conn.execute(sql, params).fetchone()[0] or 0)


def resumen_financiero(conn, hasta=None):
    where = ""
    params=[]
    if hasta:
        where=" WHERE fecha <= ?"
        params=[hasta]
    df = pd.read_sql_query(f"""
        SELECT p.codigo, p.nombre, p.tipo, p.categoria,
               COALESCE(SUM(l.debe),0) debe, COALESCE(SUM(l.haber),0) haber
        FROM plan_cuentas p
        LEFT JOIN libro_diario l ON l.codigo_cuenta=p.codigo {('AND l.fecha <= ?' if hasta else '')}
        GROUP BY p.codigo,p.nombre,p.tipo,p.categoria
        ORDER BY p.codigo
    """, conn, params=params)
    if df.empty:
        return df
    df["saldo"] = df["debe"] - df["haber"]
    return df


def estado_situacion(conn, hasta=None):
    df=resumen_financiero(conn,hasta)
    if df.empty: return df
    return df[df["tipo"].isin(["Activo","Pasivo","Patrimonio"])].copy()


def estado_resultados(conn, hasta=None, desde=None):
    sql="""
        SELECT p.codigo, p.nombre, p.tipo, p.categoria,
               COALESCE(SUM(l.debe),0) debe, COALESCE(SUM(l.haber),0) haber
        FROM plan_cuentas p
        LEFT JOIN libro_diario l ON l.codigo_cuenta=p.codigo
    """
    params=[]
    filtros=[]
    if desde:
        filtros.append("l.fecha >= ?"); params.append(desde)
    if hasta:
        filtros.append("l.fecha <= ?"); params.append(hasta)
    if filtros: sql += " WHERE " + " AND ".join(filtros)
    sql += " GROUP BY p.codigo,p.nombre,p.tipo,p.categoria ORDER BY p.codigo"
    df=pd.read_sql_query(sql,conn,params=params)
    if df.empty: return df
    df["saldo"] = df["haber"]-df["debe"]
    return df[df["tipo"].isin(["Ingresos","Gastos"])].copy()


def conciliacion_banco(conn, banco_id):
    banco=conn.execute("SELECT * FROM bancos WHERE id=?",(banco_id,)).fetchone()
    if not banco: return None
    movimientos=pd.read_sql_query("SELECT * FROM cartola_bancaria WHERE banco_id=? ORDER BY fecha,id",conn,params=[banco_id])
    saldo_cartola=float(movimientos["abono"].sum()-movimientos["cargo"].sum()+float(banco["saldo_inicial"] or 0)) if not movimientos.empty else float(banco["saldo_inicial"] or 0)
    saldo_contable=saldo_cuenta(conn,banco["cuenta_contable"]) if banco["cuenta_contable"] else 0
    return saldo_cartola,saldo_contable,saldo_cartola-saldo_contable,movimientos


def antiguedad_documentos(conn, tipo):
    hoy=date.today()
    if tipo=="clientes":
        df=pd.read_sql_query("""
            SELECT c.razon_social AS entidad, v.fecha, v.folio, v.monto_total AS monto,
                   COALESCE((SELECT SUM(p.monto) FROM pagos_clientes p WHERE p.cliente_id=v.cliente_id),0) pagos
            FROM ventas v JOIN clientes c ON c.id=v.cliente_id
            ORDER BY v.fecha
        """,conn)
    else:
        df=pd.read_sql_query("""
            SELECT p.razon_social AS entidad, c.fecha, c.folio, c.monto_total AS monto,
                   COALESCE((SELECT SUM(pg.monto) FROM pagos_proveedores pg WHERE pg.proveedor_id=c.proveedor_id),0) pagos
            FROM compras c JOIN proveedores p ON p.id=c.proveedor_id
            ORDER BY c.fecha
        """,conn)
    if df.empty: return df
    df["fecha"]=pd.to_datetime(df["fecha"],errors="coerce")
    df["saldo"]=df["monto"].abs()-df["pagos"].abs()
    df["dias"]=(pd.Timestamp(hoy)-df["fecha"]).dt.days.fillna(0).astype(int)
    df["tramo"]=pd.cut(df["dias"],[-1,30,60,90,10**9],labels=["0-30","31-60","61-90","+90"])
    return df[df["saldo"]>0.01]


def importar_cartola(conn, df, banco_id, origen="CARTOLA"):
    """Importa movimientos tabulares evitando duplicados."""
    df = normalizar_columnas(df)

    def col(*names):
        for n in names:
            if n.lower() in df.columns:
                return n.lower()
        return None

    fecha_c = col("fecha", "fecha movimiento", "fecha de movimiento", "date")
    desc_c = col("descripcion", "descripción", "detalle", "glosa", "movimiento")
    cargo_c = col("cargo", "cargos", "debito", "débito", "retiros", "egresos", "cheques y otros cargos")
    abono_c = col("abono", "abonos", "credito", "crédito", "depositos", "depósitos", "ingresos", "depositos y abonos", "depósitos y abonos")
    saldo_c = col("saldo", "saldo disponible", "balance", "saldo diario")
    ref_c = col("referencia", "nro documento", "nº de documento", "n° documento", "documento", "numero", "número")

    if not fecha_c or not desc_c:
        raise ValueError("No pude identificar Fecha y Descripción en la cartola.")

    lote = "BANCO-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    nuevos = 0
    repetidos = 0

    for _, r in df.iterrows():
        fecha = fecha_iso(r.get(fecha_c))
        desc = limpiar_texto(r.get(desc_c))
        ref = limpiar_texto(r.get(ref_c)) if ref_c else ""
        cargo = abs(numero(r.get(cargo_c))) if cargo_c else 0
        abono = abs(numero(r.get(abono_c))) if abono_c else 0
        saldo = numero(r.get(saldo_c)) if saldo_c and limpiar_texto(r.get(saldo_c)) else None

        if not fecha or not desc or (cargo <= 0 and abono <= 0):
            continue

        try:
            conn.execute(
                """INSERT INTO cartola_bancaria
                   (banco_id,fecha,descripcion,referencia,cargo,abono,saldo,lote_id,origen)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (banco_id, fecha, desc, ref, cargo, abono, saldo, lote, origen),
            )
            nuevos += 1
        except sqlite3.IntegrityError:
            repetidos += 1

    conn.commit()
    registrar_auditoria(conn, "IMPORTACIÓN CARTOLA", f"Banco {banco_id}: {nuevos} movimientos nuevos, {repetidos} repetidos")
    return nuevos, repetidos, lote


def leer_cartola_pdf(uploaded_file, password=""):
    """Extrae cartolas PDF de texto. Soporta PDF protegido con contraseña.

    Incluye reconocimiento específico del formato BCI observado y deja una
    estructura estándar: fecha, descripcion, referencia, cargo, abono, saldo.
    """
    datos = uploaded_file.getvalue()
    if not datos:
        raise ValueError("El PDF está vacío.")

    PdfReader = None
    try:
        from pypdf import PdfReader as _PdfReader
        PdfReader = _PdfReader
    except Exception:
        try:
            from PyPDF2 import PdfReader as _PdfReader
            PdfReader = _PdfReader
        except Exception:
            raise ValueError("Para leer PDF debes agregar 'pypdf' al archivo requirements.txt de Render/GitHub.")

    try:
        lector = PdfReader(io.BytesIO(datos))
        if getattr(lector, "is_encrypted", False):
            if not password:
                raise ValueError("La cartola está protegida. Ingresa la contraseña del PDF.")
            resultado = lector.decrypt(password)
            if not resultado:
                raise ValueError("La contraseña del PDF no es correcta.")
        texto = "\n".join((pagina.extract_text() or "") for pagina in lector.pages)
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"No fue posible leer el PDF: {e}")

    if not texto.strip():
        raise ValueError("El PDF no contiene texto extraíble. Si es una cartola escaneada, deberá cargarse manualmente o en CSV/Excel.")

    movimientos = []
    # BCI: fecha + sucursal + descripción + documento + cargo/abono + saldo.
    # En el formato observado, cada movimiento aparece en una sola línea.
    patron = re.compile(r"^(\d{2}-\d{2}-\d{4})\s+(.+?)\s+(\d+)\s+([\d\.]+)\s+([\d\.]+)\s*$")

    for linea in texto.splitlines():
        linea = re.sub(r"\s+", " ", linea.strip())
        m = patron.match(linea)
        if not m:
            continue
        fecha_txt, cuerpo, referencia, monto_txt, saldo_txt = m.groups()
        cuerpo_upper = cuerpo.upper()
        monto = numero(monto_txt)
        saldo = numero(saldo_txt)

        # Determinación por descripción para el formato BCI. Si el banco usa
        # términos de abono, se clasifica como abono; en caso contrario cargo.
        palabras_abono = ("ABONO", "DEPOSITO", "DEPÓSITO", "TRANSFERENCIA RECIBIDA", "PAGO RECIBIDO")
        es_abono = any(x in cuerpo_upper for x in palabras_abono)
        cargo = 0.0 if es_abono else abs(monto)
        abono = abs(monto) if es_abono else 0.0

        movimientos.append({
            "fecha": fecha_iso(fecha_txt),
            "descripcion": cuerpo,
            "referencia": referencia,
            "cargo": cargo,
            "abono": abono,
            "saldo": saldo,
        })

    if not movimientos:
        raise ValueError("Pude abrir el PDF, pero no reconocí movimientos bancarios. Puedes usar la carga manual o CSV/Excel.")

    return pd.DataFrame(movimientos)


def registrar_movimiento_manual(conn, banco_id, fecha, descripcion, referencia, cargo, abono, saldo=None):
    df = pd.DataFrame([{
        "fecha": fecha,
        "descripcion": descripcion,
        "referencia": referencia,
        "cargo": cargo,
        "abono": abono,
        "saldo": saldo,
    }])
    return importar_cartola(conn, df, banco_id, origen="MANUAL")


def crear_obligacion_manual(conn, fecha, tipo, descripcion, referencia, monto, codigo_cuenta):
    cur = conn.execute(
        """INSERT INTO obligaciones_manuales(fecha,tipo,descripcion,referencia,monto,codigo_cuenta)
           VALUES(?,?,?,?,?,?)""",
        (fecha_iso(fecha), tipo, limpiar_texto(descripcion), limpiar_texto(referencia), abs(float(monto)), codigo_cuenta),
    )
    conn.commit()
    registrar_auditoria(conn, "OBLIGACIÓN MANUAL", f"{tipo}: {descripcion} {money(monto)}")
    return cur.lastrowid


def candidatos_conciliacion(conn, movimiento_id):
    """Busca coincidencias por monto y agrega señales por fecha/referencia."""
    mov = conn.execute("SELECT * FROM cartola_bancaria WHERE id=?", (movimiento_id,)).fetchone()
    if not mov:
        return pd.DataFrame()

    es_cargo = float(mov["cargo"] or 0) > 0
    monto = abs(float(mov["cargo"] or mov["abono"] or 0))
    fecha_mov = pd.to_datetime(mov["fecha"], errors="coerce")
    ref_mov = limpiar_texto(mov["referencia"]).lower()
    candidatos = []

    def agregar(tipo, ident, fecha, descripcion, referencia, importe, cuenta, entidad_id=None):
        if abs(abs(float(importe or 0)) - monto) > 0.01:
            return
        puntos = 70.0  # monto exacto
        f = pd.to_datetime(fecha, errors="coerce")
        dias = None
        if pd.notna(fecha_mov) and pd.notna(f):
            dias = abs((fecha_mov - f).days)
            if dias <= 3:
                puntos += 20
            elif dias <= 15:
                puntos += 10
        ref = limpiar_texto(referencia).lower()
        if ref_mov and ref and ref_mov == ref:
            puntos += 10
        candidatos.append({
            "tipo": tipo,
            "id": int(ident),
            "fecha": fecha,
            "descripcion": descripcion,
            "referencia": referencia or "",
            "monto": monto,
            "cuenta": cuenta,
            "entidad_id": entidad_id,
            "confianza": min(puntos, 100.0),
            "dias": dias,
        })

    roles = cargar_roles(conn)
    if es_cargo:
        # Compras/proveedores aún no aplicadas completamente.
        filas = conn.execute("""
            SELECT c.id,c.fecha,c.folio,c.monto_total,c.proveedor_id,
                   COALESCE(p.razon_social,p.nombre,'Proveedor') entidad,
                   COALESCE((SELECT SUM(a.monto) FROM aplicaciones_proveedores a WHERE a.compra_id=c.id),0) aplicado
            FROM compras c LEFT JOIN proveedores p ON p.id=c.proveedor_id
        """).fetchall()
        cuenta = roles.get("proveedores")[0] if roles.get("proveedores") else None
        for r in filas:
            pendiente = max(abs(float(r["monto_total"] or 0)) - abs(float(r["aplicado"] or 0)), 0)
            agregar("PROVEEDOR", r["id"], r["fecha"], f"{r['entidad']} | Compra/Doc. {r['folio']}", r["folio"], pendiente, cuenta, r["proveedor_id"])
    else:
        filas = conn.execute("""
            SELECT v.id,v.fecha,v.folio,v.monto_total,v.cliente_id,
                   COALESCE(c.razon_social,c.nombre,'Cliente') entidad,
                   COALESCE((SELECT SUM(a.monto) FROM aplicaciones_clientes a WHERE a.venta_id=v.id),0) aplicado
            FROM ventas v LEFT JOIN clientes c ON c.id=v.cliente_id
        """).fetchall()
        cuenta = roles.get("clientes")[0] if roles.get("clientes") else None
        for r in filas:
            pendiente = max(abs(float(r["monto_total"] or 0)) - abs(float(r["aplicado"] or 0)), 0)
            agregar("CLIENTE", r["id"], r["fecha"], f"{r['entidad']} | Venta/Doc. {r['folio']}", r["folio"], pendiente, cuenta, r["cliente_id"])

    # Operaciones manuales: servicios, nómina, impuestos, arriendos, etc.
    tipo_manual = "PAGO" if es_cargo else "ABONO"
    filas = conn.execute("""
        SELECT * FROM obligaciones_manuales
        WHERE conciliado=0 AND tipo=?
    """, (tipo_manual,)).fetchall()
    for r in filas:
        agregar("MANUAL", r["id"], r["fecha"], r["descripcion"], r["referencia"], r["monto"], r["codigo_cuenta"], None)

    if not candidatos:
        return pd.DataFrame()
    return pd.DataFrame(candidatos).sort_values(["confianza", "fecha"], ascending=[False, False]).reset_index(drop=True)


def contabilizar_conciliacion_bancaria(conn, movimiento_id, candidato_tipo, candidato_id):
    """Confirma una coincidencia, genera el asiento bancario y deja trazabilidad."""
    mov = conn.execute("SELECT * FROM cartola_bancaria WHERE id=?", (movimiento_id,)).fetchone()
    if not mov:
        raise ValueError("Movimiento bancario no encontrado.")
    if int(mov["conciliado"] or 0) == 1:
        raise ValueError("Este movimiento ya está conciliado.")
    if periodo_cerrado(conn, mov["fecha"]):
        raise ValueError("El período contable de este movimiento está cerrado.")

    banco = conn.execute("SELECT * FROM bancos WHERE id=?", (mov["banco_id"],)).fetchone()
    if not banco or not banco["cuenta_contable"]:
        raise ValueError("La cuenta bancaria no tiene una cuenta contable configurada.")

    monto = abs(float(mov["cargo"] or mov["abono"] or 0))
    es_cargo = float(mov["cargo"] or 0) > 0
    if monto <= 0:
        raise ValueError("El movimiento no tiene monto para conciliar.")

    cuenta_contraparte = None
    descripcion = ""
    entidad_id = None
    documento_id = int(candidato_id)
    roles = cargar_roles(conn)

    if candidato_tipo == "PROVEEDOR":
        r = conn.execute("""SELECT c.*,COALESCE(p.razon_social,p.nombre,'Proveedor') entidad
                            FROM compras c LEFT JOIN proveedores p ON p.id=c.proveedor_id WHERE c.id=?""", (documento_id,)).fetchone()
        if not r:
            raise ValueError("Compra no encontrada.")
        cuenta_contraparte = roles.get("proveedores")[0] if roles.get("proveedores") else None
        descripcion = f"Pago proveedor {r['entidad']} Doc. {r['folio']}"
        entidad_id = r["proveedor_id"]
    elif candidato_tipo == "CLIENTE":
        r = conn.execute("""SELECT v.*,COALESCE(c.razon_social,c.nombre,'Cliente') entidad
                            FROM ventas v LEFT JOIN clientes c ON c.id=v.cliente_id WHERE v.id=?""", (documento_id,)).fetchone()
        if not r:
            raise ValueError("Venta no encontrada.")
        cuenta_contraparte = roles.get("clientes")[0] if roles.get("clientes") else None
        descripcion = f"Cobro cliente {r['entidad']} Doc. {r['folio']}"
        entidad_id = r["cliente_id"]
    elif candidato_tipo == "MANUAL":
        r = conn.execute("SELECT * FROM obligaciones_manuales WHERE id=? AND conciliado=0", (documento_id,)).fetchone()
        if not r:
            raise ValueError("La obligación manual no existe o ya fue conciliada.")
        cuenta_contraparte = r["codigo_cuenta"]
        descripcion = r["descripcion"]
    else:
        raise ValueError("Tipo de coincidencia no reconocido.")

    if not cuenta_contraparte:
        raise ValueError("La operación no tiene cuenta contable de contrapartida.")

    asiento_id = siguiente_asiento(conn) + 1
    lote = "CONC-BANCO-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    fecha = mov["fecha"]
    cuenta_banco = banco["cuenta_contable"]
    plan = Plan(conn)

    # Cargo bancario: Debe contrapartida / Haber Banco.
    # Abono bancario: Debe Banco / Haber contrapartida.
    lineas = [
        (cuenta_contraparte, monto, 0.0),
        (cuenta_banco, 0.0, monto),
    ] if es_cargo else [
        (cuenta_banco, monto, 0.0),
        (cuenta_contraparte, 0.0, monto),
    ]

    for codigo, debe, haber in lineas:
        nombre = plan.todos.get(codigo, codigo)
        conn.execute("""INSERT INTO libro_diario
            (fecha,cuenta,debe,haber,glosa,codigo_cuenta,asiento_id,lote_id,origen)
            VALUES(?,?,?,?,?,?,?,?,?)""",
            (fecha, nombre, debe, haber, descripcion, codigo, asiento_id, lote, "CONCILIACION_BANCARIA"))

    if candidato_tipo == "PROVEEDOR":
        cur = conn.execute("""INSERT INTO pagos_proveedores(fecha,proveedor_id,monto,medio_pago,cuenta_banco,glosa,lote_id)
                              VALUES(?,?,?,?,?,?,?)""", (fecha, entidad_id, monto, "Banco", cuenta_banco, descripcion, lote))
        conn.execute("INSERT INTO aplicaciones_proveedores(pago_id,compra_id,monto) VALUES(?,?,?)", (cur.lastrowid, documento_id, monto))
    elif candidato_tipo == "CLIENTE":
        cur = conn.execute("""INSERT INTO pagos_clientes(fecha,cliente_id,monto,medio_pago,cuenta_banco,glosa,lote_id)
                              VALUES(?,?,?,?,?,?,?)""", (fecha, entidad_id, monto, "Banco", cuenta_banco, descripcion, lote))
        conn.execute("INSERT INTO aplicaciones_clientes(pago_id,venta_id,monto) VALUES(?,?,?)", (cur.lastrowid, documento_id, monto))
    else:
        conn.execute("""UPDATE obligaciones_manuales
                        SET conciliado=1,fecha_conciliacion=?,cartola_id=?,asiento_id=? WHERE id=?""",
                     (datetime.now().isoformat(timespec="seconds"), movimiento_id, asiento_id, documento_id))

    confianza = 100.0
    conn.execute("""UPDATE cartola_bancaria
                    SET conciliado=1,observacion=?,asiento_id=?,match_tipo=?,match_id=?,match_confianza=?
                    WHERE id=?""",
                 (descripcion, asiento_id, candidato_tipo, documento_id, confianza, movimiento_id))
    conn.commit()
    registrar_auditoria(conn, "CONCILIACIÓN BANCARIA", f"Movimiento {movimiento_id} -> {candidato_tipo} {documento_id}, asiento {asiento_id}")
    return asiento_id


def contabilizar_imputacion_manual_bancaria(conn, movimiento_id, codigo_cuenta, descripcion=None):
    """Imputa directamente un movimiento bancario a una cuenta contable y lo deja conciliado.

    Cargo: Debe contrapartida / Haber Banco.
    Abono: Debe Banco / Haber contrapartida.
    """
    mov = conn.execute("SELECT * FROM cartola_bancaria WHERE id=?", (movimiento_id,)).fetchone()
    if not mov:
        raise ValueError("Movimiento bancario no encontrado.")
    if int(mov["conciliado"] or 0) == 1:
        raise ValueError("Este movimiento ya está conciliado.")
    if periodo_cerrado(conn, mov["fecha"]):
        raise ValueError("El período contable de este movimiento está cerrado.")

    banco = conn.execute("SELECT * FROM bancos WHERE id=?", (mov["banco_id"],)).fetchone()
    if not banco or not banco["cuenta_contable"]:
        raise ValueError("La cuenta bancaria no tiene una cuenta contable configurada.")

    plan = Plan(conn)
    if codigo_cuenta not in plan.todos:
        raise ValueError("La cuenta de contrapartida no existe en el plan de cuentas.")
    if codigo_cuenta == banco["cuenta_contable"]:
        raise ValueError("La contrapartida no puede ser la misma cuenta bancaria.")

    monto = abs(float(mov["cargo"] or mov["abono"] or 0))
    es_cargo = float(mov["cargo"] or 0) > 0
    if monto <= 0:
        raise ValueError("El movimiento no tiene monto para contabilizar.")

    glosa = limpiar_texto(descripcion) or limpiar_texto(mov["descripcion"]) or "Imputación manual bancaria"
    asiento_id = siguiente_asiento(conn) + 1
    lote = "CONC-MANUAL-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    fecha = mov["fecha"]
    cuenta_banco = banco["cuenta_contable"]

    lineas = [
        (codigo_cuenta, monto, 0.0),
        (cuenta_banco, 0.0, monto),
    ] if es_cargo else [
        (cuenta_banco, monto, 0.0),
        (codigo_cuenta, 0.0, monto),
    ]

    try:
        for codigo, debe, haber in lineas:
            nombre = plan.todos.get(codigo, codigo)
            conn.execute("""INSERT INTO libro_diario
                (fecha,cuenta,debe,haber,glosa,codigo_cuenta,asiento_id,lote_id,origen)
                VALUES(?,?,?,?,?,?,?,?,?)""",
                (fecha, nombre, debe, haber, glosa, codigo, asiento_id, lote, "CONCILIACION_BANCARIA_MANUAL"))

        conn.execute("""UPDATE cartola_bancaria
                        SET conciliado=1,observacion=?,asiento_id=?,match_tipo='IMPUTACION_MANUAL',
                            match_id=NULL,match_confianza=100
                        WHERE id=?""",
                     (glosa, asiento_id, movimiento_id))
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    registrar_auditoria(conn, "IMPUTACIÓN BANCARIA MANUAL",
                        f"Movimiento {movimiento_id} -> cuenta {codigo_cuenta}, asiento {asiento_id}")
    return asiento_id



def documentos_pendientes_proveedor(conn, proveedor_id):
    """Devuelve documentos de compra con saldo pendiente para un proveedor."""
    return pd.read_sql_query("""
        SELECT c.id, c.fecha, c.folio, c.tipo_doc, ABS(COALESCE(c.monto_total,0)) AS total,
               COALESCE((SELECT SUM(ABS(a.monto)) FROM aplicaciones_proveedores a WHERE a.compra_id=c.id),0) AS aplicado,
               MAX(ABS(COALESCE(c.monto_total,0)) - COALESCE((SELECT SUM(ABS(a.monto)) FROM aplicaciones_proveedores a WHERE a.compra_id=c.id),0),0) AS pendiente
        FROM compras c
        WHERE c.proveedor_id=?
          AND ABS(COALESCE(c.monto_total,0)) - COALESCE((SELECT SUM(ABS(a.monto)) FROM aplicaciones_proveedores a WHERE a.compra_id=c.id),0) > 0.01
        ORDER BY c.fecha, c.id
    """, conn, params=[int(proveedor_id)])


def contabilizar_pago_proveedor_desde_cartola(conn, movimiento_id, proveedor_id, compra_ids):
    """Contabiliza un cargo de cartola como pago a proveedor y aplica el monto a uno o varios documentos.

    Genera Debe Proveedores / Haber Banco y mantiene sincronizado el auxiliar del proveedor.
    Si el movimiento es menor al saldo de los documentos seleccionados, aplica parcialmente en orden.
    """
    mov = conn.execute("SELECT * FROM cartola_bancaria WHERE id=?", (int(movimiento_id),)).fetchone()
    if not mov:
        raise ValueError("Movimiento bancario no encontrado.")
    if int(mov["conciliado"] or 0) == 1:
        raise ValueError("Este movimiento ya está conciliado.")
    if float(mov["cargo"] or 0) <= 0:
        raise ValueError("El pago a proveedor debe corresponder a un cargo/salida de la cuenta bancaria.")
    if periodo_cerrado(conn, mov["fecha"]):
        raise ValueError("El período contable de este movimiento está cerrado.")

    banco = conn.execute("SELECT * FROM bancos WHERE id=?", (mov["banco_id"],)).fetchone()
    if not banco or not banco["cuenta_contable"]:
        raise ValueError("La cuenta bancaria no tiene una cuenta contable configurada.")

    roles = cargar_roles(conn)
    rol_prov = roles.get("proveedores")
    if not rol_prov:
        raise ValueError("La cuenta de Proveedores no está configurada.")
    cuenta_proveedores = rol_prov[0]
    cuenta_banco = banco["cuenta_contable"]
    if cuenta_banco == cuenta_proveedores:
        raise ValueError("La cuenta bancaria y la cuenta de Proveedores no pueden ser la misma.")

    proveedor = conn.execute("SELECT * FROM proveedores WHERE id=?", (int(proveedor_id),)).fetchone()
    if not proveedor:
        raise ValueError("Proveedor no encontrado.")
    compra_ids = [int(x) for x in compra_ids]
    if not compra_ids:
        raise ValueError("Selecciona al menos un documento pendiente del proveedor.")

    docs = documentos_pendientes_proveedor(conn, proveedor_id)
    docs = docs[docs["id"].isin(compra_ids)].copy()
    if docs.empty:
        raise ValueError("Los documentos seleccionados ya no tienen saldo pendiente.")

    monto = abs(float(mov["cargo"] or 0))
    disponible = float(docs["pendiente"].sum())
    if disponible + 0.01 < monto:
        raise ValueError(f"Los documentos seleccionados solo tienen {money(disponible)} pendientes y el cargo bancario es {money(monto)}.")

    nombre_prov = limpiar_texto(proveedor["razon_social"] or proveedor["nombre"] or "Proveedor")
    folios = ", ".join(str(x) for x in docs["folio"].tolist())
    glosa = f"Pago proveedor {nombre_prov} - Doc. {folios}"
    asiento_id = siguiente_asiento(conn) + 1
    lote = "CONC-PROV-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    plan = Plan(conn)

    try:
        for codigo, debe, haber in [(cuenta_proveedores, monto, 0.0), (cuenta_banco, 0.0, monto)]:
            conn.execute("""INSERT INTO libro_diario
                (fecha,cuenta,debe,haber,glosa,codigo_cuenta,asiento_id,lote_id,origen)
                VALUES(?,?,?,?,?,?,?,?,?)""",
                (mov["fecha"], plan.todos.get(codigo,codigo), debe, haber, glosa, codigo, asiento_id, lote, "CONCILIACION_PAGO_PROVEEDOR"))

        cur = conn.execute("""INSERT INTO pagos_proveedores(fecha,proveedor_id,monto,medio_pago,cuenta_banco,glosa,lote_id)
                              VALUES(?,?,?,?,?,?,?)""",
                           (mov["fecha"], int(proveedor_id), monto, "Banco", cuenta_banco, glosa, lote))
        pago_id = cur.lastrowid

        restante = monto
        aplicaciones = []
        for r in docs.itertuples(index=False):
            if restante <= 0.01:
                break
            aplicar = min(restante, float(r.pendiente))
            if aplicar > 0.01:
                conn.execute("INSERT INTO aplicaciones_proveedores(pago_id,compra_id,monto) VALUES(?,?,?)",
                             (pago_id, int(r.id), aplicar))
                aplicaciones.append((int(r.id), aplicar))
                restante -= aplicar
        if restante > 0.01:
            raise ValueError("No fue posible aplicar completamente el pago a los documentos seleccionados.")

        conn.execute("""UPDATE cartola_bancaria
                        SET conciliado=1,observacion=?,asiento_id=?,match_tipo='PROVEEDOR',match_id=?,match_confianza=100
                        WHERE id=?""",
                     (glosa, asiento_id, int(proveedor_id), int(movimiento_id)))
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    registrar_auditoria(conn, "PAGO PROVEEDOR DESDE CARTOLA",
                        f"Movimiento {movimiento_id} -> proveedor {proveedor_id}, asiento {asiento_id}")
    return asiento_id, aplicaciones


def contabilizar_pago_proveedor_sin_documento(conn, movimiento_id, proveedor_id):
    """Contabiliza un cargo bancario como pago a proveedor sin aplicarlo a una factura específica.

    Se usa para pagos de saldos anteriores o documentos que todavía no están cargados en SGCI.
    El pago queda en el auxiliar del proveedor y puede producir temporalmente un saldo deudor
    hasta que se incorporen los saldos iniciales/documentos históricos.
    """
    mov = conn.execute("SELECT * FROM cartola_bancaria WHERE id=?", (int(movimiento_id),)).fetchone()
    if not mov:
        raise ValueError("Movimiento bancario no encontrado.")
    if int(mov["conciliado"] or 0) == 1:
        raise ValueError("Este movimiento ya está conciliado.")
    if float(mov["cargo"] or 0) <= 0:
        raise ValueError("El pago a proveedor debe corresponder a un cargo/salida de la cuenta bancaria.")
    if periodo_cerrado(conn, mov["fecha"]):
        raise ValueError("El período contable de este movimiento está cerrado.")

    banco = conn.execute("SELECT * FROM bancos WHERE id=?", (mov["banco_id"],)).fetchone()
    if not banco or not banco["cuenta_contable"]:
        raise ValueError("La cuenta bancaria no tiene una cuenta contable configurada.")

    roles = cargar_roles(conn)
    rol_prov = roles.get("proveedores")
    if not rol_prov:
        raise ValueError("La cuenta de Proveedores no está configurada.")
    cuenta_proveedores = rol_prov[0]
    cuenta_banco = banco["cuenta_contable"]
    if cuenta_banco == cuenta_proveedores:
        raise ValueError("La cuenta bancaria y la cuenta de Proveedores no pueden ser la misma.")

    proveedor = conn.execute("SELECT * FROM proveedores WHERE id=?", (int(proveedor_id),)).fetchone()
    if not proveedor:
        raise ValueError("Proveedor no encontrado.")

    monto = abs(float(mov["cargo"] or 0))
    nombre_prov = limpiar_texto(proveedor["razon_social"] or proveedor["nombre"] or "Proveedor")
    glosa = f"Pago proveedor {nombre_prov} - saldo anterior / sin documento"
    asiento_id = siguiente_asiento(conn) + 1
    lote = "CONC-PROV-SD-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    plan = Plan(conn)

    try:
        for codigo, debe, haber in [(cuenta_proveedores, monto, 0.0), (cuenta_banco, 0.0, monto)]:
            conn.execute("""INSERT INTO libro_diario
                (fecha,cuenta,debe,haber,glosa,codigo_cuenta,asiento_id,lote_id,origen)
                VALUES(?,?,?,?,?,?,?,?,?)""",
                (mov["fecha"], plan.todos.get(codigo,codigo), debe, haber, glosa, codigo, asiento_id, lote, "CONCILIACION_PAGO_PROVEEDOR_SIN_DOCUMENTO"))

        conn.execute("""INSERT INTO pagos_proveedores(fecha,proveedor_id,monto,medio_pago,cuenta_banco,glosa,lote_id)
                        VALUES(?,?,?,?,?,?,?)""",
                     (mov["fecha"], int(proveedor_id), monto, "Banco", cuenta_banco, glosa, lote))

        conn.execute("""UPDATE cartola_bancaria
                        SET conciliado=1,observacion=?,asiento_id=?,match_tipo='PROVEEDOR_SIN_DOCUMENTO',
                            match_id=?,match_confianza=100
                        WHERE id=?""",
                     (glosa, asiento_id, int(proveedor_id), int(movimiento_id)))
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    registrar_auditoria(conn, "PAGO PROVEEDOR SIN DOCUMENTO",
                        f"Movimiento {movimiento_id} -> proveedor {proveedor_id}, asiento {asiento_id}")
    return asiento_id


def corregir_conciliacion_manual(conn, movimiento_id):
    """Revierte contablemente una imputación manual bancaria y reabre el movimiento para corregirlo."""
    mov = conn.execute("SELECT * FROM cartola_bancaria WHERE id=?", (int(movimiento_id),)).fetchone()
    if not mov or int(mov["conciliado"] or 0) != 1:
        raise ValueError("El movimiento no está conciliado.")
    if mov["match_tipo"] != "IMPUTACION_MANUAL" or not mov["asiento_id"]:
        raise ValueError("Solo se puede corregir desde aquí una imputación manual bancaria.")
    lineas = conn.execute("SELECT * FROM libro_diario WHERE asiento_id=? ORDER BY id", (mov["asiento_id"],)).fetchall()
    if not lineas:
        raise ValueError("No encontré el asiento original de la imputación.")
    if periodo_cerrado(conn, mov["fecha"]):
        raise ValueError("El período contable está cerrado; no se puede reabrir este movimiento.")

    nuevo_asiento = siguiente_asiento(conn) + 1
    lote = "REV-CONC-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    try:
        for l in lineas:
            conn.execute("""INSERT INTO libro_diario
                (fecha,cuenta,debe,haber,glosa,centro_costo,codigo_cuenta,asiento_id,lote_id,origen)
                VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (mov["fecha"], l["cuenta"], float(l["haber"] or 0), float(l["debe"] or 0),
                 f"Reverso corrección conciliación - {l['glosa']}", l["centro_costo"], l["codigo_cuenta"],
                 nuevo_asiento, lote, "REVERSO_CONCILIACION_BANCARIA"))
        conn.execute("""UPDATE cartola_bancaria SET conciliado=0,observacion=NULL,asiento_id=NULL,
                        match_tipo=NULL,match_id=NULL,match_confianza=NULL WHERE id=?""", (int(movimiento_id),))
        conn.commit()
    except Exception:
        conn.rollback(); raise
    registrar_auditoria(conn, "CORRECCIÓN CONCILIACIÓN", f"Movimiento {movimiento_id}; reverso asiento {nuevo_asiento}")
    return nuevo_asiento

# ============================================================
# NÓMINA - lógica y reportes
# ============================================================

def instalar_cuentas_nomina(conn):
    cuentas = [
        ('1.1.07','Anticipos y préstamos al personal','Activo','Activo','1.1',3),
        ('1.1.07.01','Anticipos de remuneraciones','Activo','Activo','1.1.07',4),
        ('1.1.07.02','Préstamos a trabajadores','Activo','Activo','1.1.07',4),
        ('2.1.02.05','Impuesto Único de trabajadores por pagar','Pasivo','Pasivo','2.1.02',4),
        ('5.2.03','Gastos de personal','Gastos','Gastos','5.2',3),
        ('5.2.03.01','Sueldos y remuneraciones','Gastos','Gastos','5.2.03',4),
        ('5.2.03.02','Gratificaciones','Gastos','Gastos','5.2.03',4),
        ('5.2.03.03','Asignaciones no imponibles','Gastos','Gastos','5.2.03',4),
        ('5.2.03.04','Otros gastos de personal','Gastos','Gastos','5.2.03',4),
    ]
    for c in cuentas:
        conn.execute("INSERT OR IGNORE INTO plan_cuentas(codigo,nombre,categoria,tipo,padre_codigo,nivel) VALUES(?,?,?,?,?,?)", c)
    conn.commit()


def nomina_pdf(titulo, subtitulo, columnas, filas, totales=None):
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import landscape, A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    except Exception as e:
        raise RuntimeError('ReportLab no está disponible para generar el PDF.') from e
    buf=io.BytesIO()
    doc=SimpleDocTemplate(buf,pagesize=landscape(A4),rightMargin=1*cm,leftMargin=1*cm,topMargin=1*cm,bottomMargin=1*cm)
    styles=getSampleStyleSheet(); story=[Paragraph(titulo,styles['Title']),Paragraph(subtitulo or '',styles['Normal']),Spacer(1,10)]
    data=[columnas]+[[str(x) for x in f] for f in filas]
    if totales: data.append([str(x) for x in totales])
    widths=[(landscape(A4)[0]-2*cm)/max(len(columnas),1)]*len(columnas)
    t=Table(data,colWidths=widths,repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#176B55')),('TEXTCOLOR',(0,0),(-1,0),colors.white),
        ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),7),('GRID',(0,0),(-1,-1),0.35,colors.HexColor('#DCE8E3')),
        ('VALIGN',(0,0),(-1,-1),'MIDDLE'),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#F3F7F5')]),
        ('BOTTOMPADDING',(0,0),(-1,0),7),('TOPPADDING',(0,0),(-1,0),7)
    ]))
    if totales: t.setStyle(TableStyle([('FONTNAME',(0,-1),(-1,-1),'Helvetica-Bold'),('BACKGROUND',(0,-1),(-1,-1),colors.HexColor('#EAF5F0'))]))
    story.append(t); doc.build(story); buf.seek(0); return buf.getvalue()


def nomina_asiento_linea(conn, fecha, codigo, debe, haber, glosa, asiento_id, origen='NOMINA'):
    if abs(float(debe or 0))+abs(float(haber or 0)) < .005: return
    nombre=Plan(conn).todos.get(codigo,codigo)
    conn.execute("INSERT INTO libro_diario(fecha,cuenta,debe,haber,glosa,codigo_cuenta,asiento_id,lote_id,origen) VALUES(?,?,?,?,?,?,?,?,?)",
                 (fecha,nombre,float(debe or 0),float(haber or 0),glosa,codigo,asiento_id,None,origen))


def nomina_registrar_pago_activo(conn, tabla, registro_id, fecha, monto, cuenta_activo, cuenta_banco, glosa):
    asiento=siguiente_asiento(conn)+1
    try:
        nomina_asiento_linea(conn,fecha,cuenta_activo,monto,0,glosa,asiento,'NOMINA_PAGO')
        nomina_asiento_linea(conn,fecha,cuenta_banco,0,monto,glosa,asiento,'NOMINA_PAGO')
        conn.execute(f"UPDATE {tabla} SET asiento_id=?, contabilizado=1 WHERE id=?",(asiento,registro_id))
        conn.commit(); return asiento
    except Exception:
        conn.rollback(); raise


def nomina_calcular(total_imponible, total_no_imponible, afp_comision, salud_tipo, salud_modalidad, salud_valor, uf_valor, afc_manual, impuesto, prestamo, otros_desc, anticipo, afp_manual=None, salud_manual=None):
    impon=max(float(total_imponible or 0),0); noimp=max(float(total_no_imponible or 0),0)
    afp = float(afp_manual) if afp_manual is not None else impon*(10+float(afp_comision or 0))/100
    legal_salud=impon*0.07
    if str(salud_tipo or 'Fonasa') == 'Fonasa': plan_pesos=legal_salud
    elif salud_modalidad == 'Plan en UF': plan_pesos=float(salud_valor or 0)*float(uf_valor or 0)
    elif salud_modalidad == 'Monto pactado en pesos': plan_pesos=float(salud_valor or 0)
    elif salud_modalidad == 'Porcentaje pactado': plan_pesos=impon*float(salud_valor or 7)/100
    else: plan_pesos=legal_salud
    salud_base=max(legal_salud,plan_pesos) if str(salud_tipo or '') == 'Isapre' else legal_salud
    salud=float(salud_manual) if salud_manual is not None else salud_base
    afc=float(afc_manual or 0); impuesto=float(impuesto or 0); prestamo=float(prestamo or 0); otros=float(otros_desc or 0); antic=float(anticipo or 0)
    afp=clp_round(afp); salud=clp_round(salud); afc=clp_round(afc); impuesto=clp_round(impuesto); prestamo=clp_round(prestamo); otros=clp_round(otros); antic=clp_round(antic)
    total_desc=afp+salud+afc+impuesto+prestamo+otros
    liquido=clp_round(impon+noimp-total_desc)
    return dict(afp=afp,salud=salud,salud_plan_pesos=clp_round(plan_pesos),total_desc=clp_round(total_desc),liquido=liquido,saldo=clp_round(liquido-antic))


def nomina_contabilizar_periodo(conn, periodo):
    liq=pd.read_sql_query("SELECT * FROM nomina_liquidaciones WHERE periodo=?",conn,params=(periodo,))
    if liq.empty: raise ValueError('No existen liquidaciones para el período.')
    if (liq['estado']=='CONTABILIZADO').all(): raise ValueError('Este período ya está contabilizado.')
    fecha=f"{periodo}-01"
    try:
        y,m=map(int,periodo.split('-')); fecha=(date(y+1,1,1)-timedelta(days=1) if m==12 else date(y,m+1,1)-timedelta(days=1)).isoformat()
    except Exception: fecha=date.today().isoformat()
    asiento=siguiente_asiento(conn)+1; glosa=f'Nómina {periodo}'
    sueldo=float(liq['sueldo_periodo'].sum()+liq['horas_extras'].sum()+liq['bonos_imponibles'].sum()+liq['otros_imponibles'].sum())
    grat=float(liq['gratificacion'].sum()); noimp=float(liq['total_no_imponible'].sum())
    afp=float(liq['afp_descuento'].sum()); salud=float(liq['salud_descuento'].sum()); afc=float(liq['afc_descuento'].sum())
    impuesto=float(liq['impuesto_unico'].sum()); otros=float(liq['otros_descuentos'].sum()); anticipos=float(liq['anticipo'].sum()); prestamos=float(liq['prestamo_descuento'].sum()); saldo=float(liq['saldo_pagar'].sum())
    try:
        nomina_asiento_linea(conn,fecha,'5.2.03.01',sueldo,0,glosa,asiento)
        nomina_asiento_linea(conn,fecha,'5.2.03.02',grat,0,glosa,asiento)
        nomina_asiento_linea(conn,fecha,'5.2.03.03',noimp,0,glosa,asiento)
        nomina_asiento_linea(conn,fecha,'2.1.02.02',0,afp+salud+afc,glosa,asiento)
        nomina_asiento_linea(conn,fecha,'2.1.02.05',0,impuesto,glosa,asiento)
        nomina_asiento_linea(conn,fecha,'2.1.02.03',0,otros,glosa,asiento)
        nomina_asiento_linea(conn,fecha,'1.1.07.01',0,anticipos,glosa,asiento)
        nomina_asiento_linea(conn,fecha,'1.1.07.02',0,prestamos,glosa,asiento)
        nomina_asiento_linea(conn,fecha,'2.1.02.01',0,saldo,glosa,asiento)
        debe=conn.execute('SELECT COALESCE(SUM(debe),0) FROM libro_diario WHERE asiento_id=?',(asiento,)).fetchone()[0]
        haber=conn.execute('SELECT COALESCE(SUM(haber),0) FROM libro_diario WHERE asiento_id=?',(asiento,)).fetchone()[0]
        if abs(debe-haber)>.5: raise ValueError(f'Asiento de nómina descuadrado: Debe {debe:,.0f} / Haber {haber:,.0f}. Revisa descuentos y anticipos.')
        conn.execute("UPDATE nomina_liquidaciones SET estado='CONTABILIZADO' WHERE periodo=?",(periodo,))
        conn.execute("INSERT OR IGNORE INTO nomina_periodos(periodo) VALUES(?)",(periodo,))
        conn.execute("UPDATE nomina_periodos SET estado='CONTABILIZADO',fecha_cierre=?,asiento_id=? WHERE periodo=?",(fecha,asiento,periodo))
        conn.commit(); return asiento
    except Exception:
        conn.rollback(); raise


# ============================================================
# INICIALIZACIÓN
# ============================================================

conn = conectar()

crear_esquema(conn)
instalar_plan_base(conn)
instalar_cuentas_nomina(conn)

roles_actuales = cargar_roles(conn)

if "config_cuentas" not in st.session_state:
    st.session_state["config_cuentas"] = roles_actuales


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.markdown("## SGCI")
st.sidebar.caption("Sistema de Gestión Contable Integral")
st.sidebar.markdown("---")

modulo_principal = st.sidebar.radio(
    "Navegación",
    ["🏠 Inicio", "🏦 Banco", "💰 Cuentas por Cobrar", "💳 Cuentas por Pagar", "👥 Nómina", "📚 Contabilidad", "⚙️ Administración"],
    label_visibility="collapsed",
    key="nav_modulo_principal"
)

nav_context = None
if modulo_principal == "🏠 Inicio":
    menu = "🏠 Inicio"
elif modulo_principal == "🏦 Banco":
    st.sidebar.caption("BANCO")
    st.sidebar.info("Cuentas bancarias · Cartolas · Movimientos · Conciliación bancaria")
    menu = "🏦 Bancos y Cartolas"
elif modulo_principal == "💰 Cuentas por Cobrar":
    st.sidebar.caption("CUENTAS POR COBRAR")
    sub = st.sidebar.radio("Sección", ["Clientes y estados de cuenta", "Pagos de clientes", "RCV Ventas", "Antigüedad de saldos", "Conciliación auxiliar"], key="nav_cxc")
    if sub == "Clientes y estados de cuenta": menu = "👥 Clientes"
    elif sub == "Pagos de clientes": menu = "💵 Pagos"; nav_context = "clientes"
    elif sub == "RCV Ventas": menu = "📤 RCV Ventas"
    elif sub == "Antigüedad de saldos": menu = "📌 Cuentas por Cobrar/Pagar"; nav_context = "clientes"
    else: menu = "📊 Conciliación"; nav_context = "clientes"
elif modulo_principal == "💳 Cuentas por Pagar":
    st.sidebar.caption("CUENTAS POR PAGAR")
    sub = st.sidebar.radio("Sección", ["Proveedores y estados de cuenta", "Pagos de proveedores", "RCV Compras", "Antigüedad de saldos", "Conciliación auxiliar"], key="nav_cxp")
    if sub == "Proveedores y estados de cuenta": menu = "🏢 Proveedores"
    elif sub == "Pagos de proveedores": menu = "💵 Pagos"; nav_context = "proveedores"
    elif sub == "RCV Compras": menu = "📥 RCV Compras"
    elif sub == "Antigüedad de saldos": menu = "📌 Cuentas por Cobrar/Pagar"; nav_context = "proveedores"
    else: menu = "📊 Conciliación"; nav_context = "proveedores"
elif modulo_principal == "👥 Nómina":
    st.sidebar.caption("NÓMINA")
    st.sidebar.info("Trabajadores · Anticipos · Préstamos · Liquidación · Reportes · Contabilización")
    menu = "👥 Nómina"
elif modulo_principal == "📚 Contabilidad":
    st.sidebar.caption("CONTABILIDAD")
    sub = st.sidebar.radio("Sección", ["Asientos y Saldos", "Plan de Cuentas", "Libro Diario", "Libro Mayor", "Balance de Comprobación", "Estados Financieros"], key="nav_conta")
    menu = {
        "Asientos y Saldos":"✍️ Asientos y Saldos", "Plan de Cuentas":"📋 Plan de Cuentas",
        "Libro Diario":"📒 Libro Diario", "Libro Mayor":"📚 Mayor",
        "Balance de Comprobación":"⚖️ Balance de Comprobación", "Estados Financieros":"📊 Estados Financieros"
    }[sub]
else:
    st.sidebar.caption("ADMINISTRACIÓN")
    sub = st.sidebar.radio("Sección", ["Cierre Mensual", "Reglas Contables", "Lotes", "Matriz Contable"], key="nav_admin")
    menu = {"Cierre Mensual":"🔒 Cierre Mensual", "Reglas Contables":"⚙️ Reglas Contables", "Lotes":"📦 Lotes", "Matriz Contable":"🧰 Matriz Contable"}[sub]

st.sidebar.divider()
st.sidebar.caption("Respaldo de Datos")
if os.path.exists(DB_FILE):
    with open(DB_FILE, "rb") as f:
        db_bytes = f.read()
    st.sidebar.download_button(
        label="💾 Descargar Respaldo BD",
        data=db_bytes,
        file_name=f"sgci_respaldo_{date.today().strftime('%Y%m%d')}.db",
        mime="application/octet-stream",
        help="Descarga una copia de seguridad exacta de tu base de datos local."
    )


if st.sidebar.button("🚪 Cerrar sesión"):
    st.session_state["authenticated"] = False
    st.rerun()



# ============================================================
# INICIO
# ============================================================

if menu == "🏠 Inicio":

    st.title("📊 SGCI")
    st.subheader("Sistema de Gestión Contable Integral")

    diario = pd.read_sql_query(
        """
        SELECT
            COALESCE(SUM(debe),0) AS debe,
            COALESCE(SUM(haber),0) AS haber,
            COUNT(*) AS movimientos
        FROM libro_diario
        """,
        conn
    ).iloc[0]

    clientes = conn.execute("SELECT COUNT(*) FROM clientes").fetchone()[0]
    proveedores = conn.execute("SELECT COUNT(*) FROM proveedores").fetchone()[0]

    facturas = conn.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM compras)
            +
            (SELECT COUNT(*) FROM ventas)
        """
    ).fetchone()[0]

    c1, c2, c3, c4 = st.columns(4)

    c1.metric("Movimientos", int(diario["movimientos"]))
    c2.metric("Clientes", clientes)
    c3.metric("Proveedores", proveedores)
    c4.metric("Documentos", facturas)

    st.divider()

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Control de cuadre")
        diferencia = float(diario["debe"]) - float(diario["haber"])

        if abs(diferencia) < 0.01:
            st.success("🟢 Libro Diario cuadrado")
        else:
            st.error(f"🔴 Diferencia: {money(diferencia)}")

        st.write(f"Debe: **{money(diario['debe'])}**")
        st.write(f"Haber: **{money(diario['haber'])}**")

    with col2:
        st.subheader("Estado del sistema")
        st.success("Base de datos conectada")
        st.write(f"Base: `{DB_FILE}`")
        st.write(f"Fecha: {date.today().strftime('%d/%m/%Y')}")

    st.divider()
    st.info(
        """
        Flujo recomendado:
        1. Cargar RCV.
        2. Revisar documentos.
        3. Confirmar cuentas contables.
        4. Contabilizar.
        5. Revisar auxiliares.
        6. Conciliar clientes/proveedores.
        7. Revisar Libro Diario y Balance.
        """
    )



# ============================================================
# MÓDULO NÓMINA
# ============================================================

elif menu == "👥 Nómina":
    st.title("👥 Nómina")
    st.caption("Gestión simple de remuneraciones: trabajadores, anticipos quincenales, préstamos, liquidaciones, reportes y contabilización.")
    tabs=st.tabs(["Trabajadores","Anticipos y préstamos","Liquidación mensual","Resumen y reportes","Parámetros","Contabilización"])

    with tabs[0]:
        st.subheader("Ficha del trabajador")
        trabajadores=pd.read_sql_query("SELECT * FROM nomina_trabajadores ORDER BY activo DESC,nombre",conn)
        if not trabajadores.empty:
            vista=trabajadores[['rut','nombre','cargo','fecha_ingreso','sueldo_base','afp','salud_tipo','banco','activo']].copy(); vista['sueldo_base']=vista['sueldo_base'].map(lambda x: money(x)); vista['activo']=vista['activo'].map({1:'Activo',0:'Inactivo'})
            st.dataframe(vista.rename(columns={'rut':'RUT','nombre':'Nombre','cargo':'Cargo','fecha_ingreso':'Ingreso','sueldo_base':'Sueldo base','afp':'AFP','salud_tipo':'Salud','banco':'Banco','activo':'Estado'}),use_container_width=True,hide_index=True)
        modo_trab=st.radio("Acción",["Nuevo trabajador","Editar trabajador"],horizontal=True,key='nom_modo_trab')
        edit_row=None
        if modo_trab=='Editar trabajador' and not trabajadores.empty:
            labels={f"{r.id} - {r.rut} - {r.nombre}":r for r in trabajadores.itertuples()}; sel=st.selectbox('Trabajador',list(labels)); edit_row=labels[sel]
        with st.form('nom_ficha_trab'):
            a,b,c=st.columns(3)
            rut=a.text_input('RUT',value=getattr(edit_row,'rut','') if edit_row else '')
            nombre=b.text_input('Nombre completo',value=getattr(edit_row,'nombre','') if edit_row else '')
            cargo=c.text_input('Cargo',value=getattr(edit_row,'cargo','') if edit_row else '')
            ingreso=a.date_input('Fecha de ingreso',value=pd.to_datetime(getattr(edit_row,'fecha_ingreso',date.today()) or date.today()).date())
            contrato=b.selectbox('Tipo de contrato',['Indefinido','Plazo fijo','Obra o faena','Otro'],index=['Indefinido','Plazo fijo','Obra o faena','Otro'].index(getattr(edit_row,'tipo_contrato','Indefinido') or 'Indefinido') if edit_row and (getattr(edit_row,'tipo_contrato','Indefinido') or 'Indefinido') in ['Indefinido','Plazo fijo','Obra o faena','Otro'] else 0)
            sueldo=c.number_input('Sueldo base mensual',min_value=0.0,value=float(getattr(edit_row,'sueldo_base',0) or 0),step=10000.0,format='%.0f')
            vigencia_cond=a.date_input('Condiciones vigentes desde',value=date.today(),help='Fecha desde la cual rigen sueldo, AFP y plan de salud. Los cambios quedan en historial.')
            grat_tipo=a.selectbox('Gratificación',['Monto mensual','Sin gratificación / manual'],index=0 if not edit_row or getattr(edit_row,'gratificacion_tipo','Monto mensual')=='Monto mensual' else 1)
            grat=b.number_input('Gratificación habitual',min_value=0.0,value=float(getattr(edit_row,'gratificacion_valor',0) or 0),step=1000.0,format='%.0f')
            afps=pd.read_sql_query("SELECT afp FROM nomina_parametros_afp WHERE activo=1 ORDER BY afp",conn)['afp'].tolist(); afp_actual=getattr(edit_row,'afp','Uno') if edit_row else 'Uno'; afp=c.selectbox('AFP',afps,index=afps.index(afp_actual) if afp_actual in afps else 0)
            salud_tipo=a.selectbox('Sistema de salud',['Fonasa','Isapre'],index=1 if edit_row and getattr(edit_row,'salud_tipo','Fonasa')=='Isapre' else 0)
            isapre=b.text_input('Isapre (si corresponde)',value=getattr(edit_row,'isapre','') or '' if edit_row else '')
            modalidades=['7% legal','Porcentaje pactado','Plan en UF','Monto pactado en pesos']; mod_actual=getattr(edit_row,'salud_modalidad','7% legal') if edit_row else '7% legal'; salud_modalidad=c.selectbox('Modalidad salud',modalidades,index=modalidades.index(mod_actual) if mod_actual in modalidades else 0)
            valor_def=float(getattr(edit_row,'salud_valor',7) or 7) if edit_row else 7.0; salud_valor=a.number_input('Porcentaje o monto pactado',min_value=0.0,value=valor_def,step=.01,help='7% legal: 7. Porcentaje: ej. 8,5. Plan en UF: ej. 4,25. Monto pactado: pesos.')
            afc=b.checkbox('Afecto a AFC',value=bool(getattr(edit_row,'afc',1)) if edit_row else True)
            anticipo=c.checkbox('Anticipo quincenal',value=bool(getattr(edit_row,'anticipo_quincenal',1)) if edit_row else True)
            ant_pct=a.number_input('% anticipo habitual',min_value=0.0,max_value=100.0,value=float(getattr(edit_row,'anticipo_porcentaje',50) or 50) if edit_row else 50.0)
            banco=b.text_input('Banco',value=getattr(edit_row,'banco','') or '' if edit_row else '')
            tipo_cta=c.selectbox('Tipo de cuenta',['Corriente','Vista','Ahorro','Otra'],index=0)
            nro=a.text_input('N° de cuenta',value=getattr(edit_row,'numero_cuenta','') or '' if edit_row else '')
            activo=b.checkbox('Trabajador activo',value=bool(getattr(edit_row,'activo',1)) if edit_row else True)
            guardar=st.form_submit_button('💾 Guardar ficha',type='primary')
            if guardar:
                if not rut.strip() or not nombre.strip(): st.error('RUT y nombre son obligatorios.')
                else:
                    vals=(rut.strip(),nombre.strip(),ingreso.isoformat(),cargo.strip(),contrato,clp_round(sueldo),grat_tipo,clp_round(grat),afp,salud_tipo,isapre.strip(),salud_modalidad,salud_valor,int(afc),int(anticipo),ant_pct,banco.strip(),tipo_cta,nro.strip(),int(activo),datetime.now().isoformat(timespec='seconds'))
                    if edit_row:
                        conn.execute("UPDATE nomina_trabajadores SET rut=?,nombre=?,fecha_ingreso=?,cargo=?,tipo_contrato=?,sueldo_base=?,gratificacion_tipo=?,gratificacion_valor=?,afp=?,salud_tipo=?,isapre=?,salud_modalidad=?,salud_valor=?,afc=?,anticipo_quincenal=?,anticipo_porcentaje=?,banco=?,tipo_cuenta=?,numero_cuenta=?,activo=?,fecha_creacion=? WHERE id=?",vals+(edit_row.id,))
                    else:
                        conn.execute("INSERT INTO nomina_trabajadores(rut,nombre,fecha_ingreso,cargo,tipo_contrato,sueldo_base,gratificacion_tipo,gratificacion_valor,afp,salud_tipo,isapre,salud_modalidad,salud_valor,afc,anticipo_quincenal,anticipo_porcentaje,banco,tipo_cuenta,numero_cuenta,activo,fecha_creacion) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",vals)
                    trabajador_id = edit_row.id if edit_row else conn.execute("SELECT id FROM nomina_trabajadores WHERE rut=?",(rut.strip(),)).fetchone()[0]
                    conn.execute("INSERT INTO nomina_historial_condiciones(trabajador_id,vigente_desde,sueldo_base,gratificacion_tipo,gratificacion_valor,afp,salud_tipo,isapre,salud_modalidad,salud_valor,observacion,fecha_registro) VALUES(?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(trabajador_id,vigente_desde) DO UPDATE SET sueldo_base=excluded.sueldo_base,gratificacion_tipo=excluded.gratificacion_tipo,gratificacion_valor=excluded.gratificacion_valor,afp=excluded.afp,salud_tipo=excluded.salud_tipo,isapre=excluded.isapre,salud_modalidad=excluded.salud_modalidad,salud_valor=excluded.salud_valor,fecha_registro=excluded.fecha_registro",(trabajador_id,vigencia_cond.isoformat(),clp_round(sueldo),grat_tipo,clp_round(grat),afp,salud_tipo,isapre.strip(),salud_modalidad,salud_valor,'Cambio desde ficha',datetime.now().isoformat(timespec='seconds')))
                    conn.commit(); st.success('Ficha y vigencia histórica guardadas.'); st.rerun()

        if edit_row:
            st.markdown('#### Historial de sueldo y condiciones previsionales')
            hc=pd.read_sql_query("SELECT vigente_desde,sueldo_base,afp,salud_tipo,isapre,salud_modalidad,salud_valor FROM nomina_historial_condiciones WHERE trabajador_id=? ORDER BY vigente_desde DESC",conn,params=(edit_row.id,))
            if not hc.empty:
                hc_show=hc.copy(); hc_show['sueldo_base']=hc_show['sueldo_base'].map(money)
                st.dataframe(hc_show,use_container_width=True,hide_index=True)
                pdf_ficha=nomina_pdf('Ficha e historial del trabajador',f'{edit_row.nombre} · RUT {edit_row.rut}',['Vigente desde','Sueldo','AFP','Salud','Isapre','Modalidad','Valor'],[[r.vigente_desde,money(r.sueldo_base),r.afp,r.salud_tipo,r.isapre or '',r.salud_modalidad,r.salud_valor] for r in hc.itertuples()])
                st.download_button('🖨️ PDF ficha / historial',pdf_ficha,f'ficha_{edit_row.rut}.pdf','application/pdf',key='pdf_ficha_nom')

    with tabs[1]:
        trab=pd.read_sql_query("SELECT id,rut,nombre,sueldo_base,anticipo_porcentaje FROM nomina_trabajadores WHERE activo=1 ORDER BY nombre",conn)
        if trab.empty: st.info('Primero crea trabajadores activos.')
        else:
            mapa={f"{r.rut} - {r.nombre}":r for r in trab.itertuples()}
            c1,c2=st.columns(2)
            with c1:
                st.markdown('#### Anticipo quincenal')
                quien=st.selectbox('Trabajador',list(mapa),key='ant_trab'); tr=mapa[quien]
                periodo=st.text_input('Período (AAAA-MM)',value=date.today().strftime('%Y-%m'),key='ant_per')
                sugerido=round(float(tr.sueldo_base or 0)*float(tr.anticipo_porcentaje or 50)/100)
                fecha_ant=st.date_input('Fecha del anticipo',date.today(),key='ant_fecha'); monto_ant=st.number_input('Monto',min_value=0.0,value=float(sugerido),step=10000.0,format='%.0f',key='ant_monto')
                obs_ant=st.text_input('Observación',key='ant_obs')
                if st.button('Registrar anticipo',key='ant_save'):
                    conn.execute("INSERT INTO nomina_anticipos(trabajador_id,periodo,fecha,monto,observacion) VALUES(?,?,?,?,?)",(tr.id,periodo,fecha_ant.isoformat(),monto_ant,obs_ant)); conn.commit(); st.success('Anticipo registrado.'); st.rerun()
            with c2:
                st.markdown('#### Préstamo al trabajador')
                quienp=st.selectbox('Trabajador',list(mapa),key='pre_trab'); tp=mapa[quienp]
                fecha_p=st.date_input('Fecha préstamo',date.today(),key='pre_fecha'); monto_p=st.number_input('Monto original',min_value=0.0,value=0.0,step=10000.0,format='%.0f',key='pre_monto'); cuotas=st.number_input('N° cuotas',min_value=1,max_value=120,value=1,key='pre_cuotas'); cuota=st.number_input('Cuota mensual',min_value=0.0,value=0.0,step=1000.0,format='%.0f',key='pre_cuota'); primera=st.text_input('Primera cuota (AAAA-MM)',value=date.today().strftime('%Y-%m'),key='pre_primera'); obs_p=st.text_input('Observación',key='pre_obs')
                if st.button('Registrar préstamo',key='pre_save'):
                    cuota_final=cuota or (monto_p/cuotas if cuotas else monto_p)
                    conn.execute("INSERT INTO nomina_prestamos(trabajador_id,fecha,monto_original,numero_cuotas,cuota,primera_cuota,saldo,observacion) VALUES(?,?,?,?,?,?,?,?)",(tp.id,fecha_p.isoformat(),monto_p,int(cuotas),cuota_final,primera,monto_p,obs_p)); conn.commit(); st.success('Préstamo registrado.'); st.rerun()
            st.divider(); st.markdown('#### Movimientos registrados')
            ants=pd.read_sql_query("SELECT a.id,t.nombre,a.periodo,a.fecha,a.monto,a.contabilizado,a.asiento_id FROM nomina_anticipos a JOIN nomina_trabajadores t ON t.id=a.trabajador_id ORDER BY a.id DESC",conn)
            pres=pd.read_sql_query("SELECT p.id,t.nombre,p.fecha,p.monto_original,p.numero_cuotas,p.cuota,p.saldo,p.estado,p.contabilizado,p.asiento_id FROM nomina_prestamos p JOIN nomina_trabajadores t ON t.id=p.trabajador_id ORDER BY p.id DESC",conn)
            st.dataframe(formatear_montos_df(ants),use_container_width=True,hide_index=True); st.dataframe(formatear_montos_df(pres),use_container_width=True,hide_index=True)
            if not ants.empty:
                pdf_ant=nomina_pdf('Anticipos de remuneraciones','SGCI',['ID','Trabajador','Período','Fecha','Monto','Contabilizado','Asiento'],[[r.id,r.nombre,r.periodo,r.fecha,money(r.monto),'Sí' if r.contabilizado else 'No',r.asiento_id or ''] for r in ants.itertuples()]); st.download_button('🖨️ PDF anticipos',pdf_ant,'anticipos_remuneraciones.pdf','application/pdf',key='pdf_anticipos')
            if not pres.empty:
                pdf_pre=nomina_pdf('Préstamos a trabajadores','SGCI',['ID','Trabajador','Fecha','Monto','Cuotas','Cuota','Saldo','Estado'],[[r.id,r.nombre,r.fecha,money(r.monto_original),r.numero_cuotas,money(r.cuota),money(r.saldo),r.estado] for r in pres.itertuples()]); st.download_button('🖨️ PDF préstamos',pdf_pre,'prestamos_trabajadores.pdf','application/pdf',key='pdf_prestamos')
            st.markdown('#### Contabilizar entrega de anticipo/préstamo')
            bancos=pd.read_sql_query("SELECT id,nombre,numero_cuenta,cuenta_contable FROM bancos WHERE activo=1 AND cuenta_contable IS NOT NULL",conn)
            pendientes=[]
            for r in ants[ants.contabilizado==0].itertuples(): pendientes.append((f"Anticipo #{r.id} · {r.nombre} · {money(r.monto)}",'nomina_anticipos',r.id,r.fecha,r.monto,'1.1.07.01'))
            for r in pres[pres.contabilizado==0].itertuples(): pendientes.append((f"Préstamo #{r.id} · {r.nombre} · {money(r.monto_original)}",'nomina_prestamos',r.id,r.fecha,r.monto_original,'1.1.07.02'))
            if pendientes and not bancos.empty:
                op=st.selectbox('Movimiento pendiente',[x[0] for x in pendientes]); mov=next(x for x in pendientes if x[0]==op)
                bm={f"{r.nombre} - {r.numero_cuenta} ({r.cuenta_contable})":r for r in bancos.itertuples()}; bl=st.selectbox('Banco utilizado',list(bm)); br=bm[bl]
                if st.button('Contabilizar salida bancaria',type='primary'):
                    asi=nomina_registrar_pago_activo(conn,mov[1],mov[2],mov[3],mov[4],mov[5],br.cuenta_contable,mov[0]); st.success(f'Asiento N° {asi} generado.'); st.rerun()
            elif pendientes: st.warning('Hay movimientos pendientes, pero no existe una cuenta bancaria activa vinculada contablemente.')

    with tabs[2]:
        st.subheader('Liquidación mensual')
        periodo=st.text_input('Período a liquidar (AAAA-MM)',value=date.today().strftime('%Y-%m'),key='liq_periodo')
        trab=pd.read_sql_query("SELECT * FROM nomina_trabajadores WHERE activo=1 ORDER BY nombre",conn)
        if trab.empty: st.info('No hay trabajadores activos.')
        else:
            labels={f"{r.rut} - {r.nombre}":r for r in trab.itertuples()}; lab=st.selectbox('Trabajador',list(labels),key='liq_trab'); tr=labels[lab]
            existente=conn.execute("SELECT * FROM nomina_liquidaciones WHERE periodo=? AND trabajador_id=?",(periodo,tr.id)).fetchone(); ex=dict(existente) if existente else {}
            fecha_periodo=f'{periodo}-01'
            hist_cond=conn.execute("SELECT * FROM nomina_historial_condiciones WHERE trabajador_id=? AND vigente_desde<=? ORDER BY vigente_desde DESC LIMIT 1",(tr.id,fecha_periodo)).fetchone()
            cond=dict(hist_cond) if hist_cond else dict(tr._asdict())
            st.caption('La liquidación toma automáticamente la última condición vigente al inicio del período y la congela históricamente.')
            c1,c2,c3=st.columns(3)
            dias=c1.number_input('Días trabajados',min_value=0.0,max_value=30.0,value=float(ex.get('dias_trabajados',30)),step=1.0)
            sueldo_base=c2.number_input('Sueldo base',min_value=0.0,value=float(ex.get('sueldo_base',cond.get('sueldo_base',tr.sueldo_base) or 0)),step=10000.0,format='%.0f')
            sueldo_periodo=c3.number_input('Sueldo del período',min_value=0.0,value=float(ex.get('sueldo_periodo',clp_round((cond.get('sueldo_base',tr.sueldo_base) or 0)*dias/30))),step=1000.0,format='%.0f')
            grat=c1.number_input('Gratificación',min_value=0.0,value=float(ex.get('gratificacion',cond.get('gratificacion_valor',tr.gratificacion_valor) or 0)),step=1000.0,format='%.0f')
            horas=c2.number_input('Horas extras ($)',min_value=0.0,value=float(ex.get('horas_extras',0)),step=1000.0,format='%.0f')
            bonos=c3.number_input('Bonos imponibles',min_value=0.0,value=float(ex.get('bonos_imponibles',0)),step=1000.0,format='%.0f')
            otros_imp=c1.number_input('Otros imponibles',min_value=0.0,value=float(ex.get('otros_imponibles',0)),step=1000.0,format='%.0f')
            noimp=c2.number_input('Asignación no imponible',min_value=0.0,value=float(ex.get('asignacion_no_imponible',0)),step=1000.0,format='%.0f')
            otros_noimp=c3.number_input('Otros no imponibles',min_value=0.0,value=float(ex.get('otros_no_imponibles',0)),step=1000.0,format='%.0f')
            total_imp=sueldo_periodo+grat+horas+bonos+otros_imp; total_noimp=noimp+otros_noimp
            afp_vig=cond.get('afp',tr.afp); com=conn.execute("SELECT comision FROM nomina_parametros_afp WHERE afp=?",(afp_vig,)).fetchone(); comision=float(com[0] if com else 0)
            st.markdown('##### Descuentos')
            d1,d2,d3=st.columns(3)
            afp_auto=clp_round(total_imp*(10+comision)/100); usar_afp_manual=d1.checkbox(f'AFP manual (auto {money(afp_auto)})',value=False); afp_manual=d1.number_input('AFP a descontar',min_value=0.0,value=float(ex.get('afp_descuento',afp_auto)),step=1000.0,format='%.0f',disabled=not usar_afp_manual)
            salud_tipo_vig=cond.get('salud_tipo',tr.salud_tipo) or 'Fonasa'; mod=cond.get('salud_modalidad',tr.salud_modalidad) or '7% legal'; sval=float(cond.get('salud_valor',tr.salud_valor) or 7); uf_row=conn.execute("SELECT valor_uf FROM nomina_parametros_mensuales WHERE periodo=?",(periodo,)).fetchone(); uf_valor=float(uf_row[0] if uf_row else ex.get('uf_valor',0) or 0); legal_salud=total_imp*0.07; plan_salud=(sval*uf_valor if mod=='Plan en UF' else (sval if mod=='Monto pactado en pesos' else total_imp*sval/100)); salud_auto=clp_round(legal_salud if salud_tipo_vig=='Fonasa' else max(legal_salud,plan_salud))
            usar_salud_manual=d2.checkbox(f'Salud manual (auto {money(salud_auto)})',value=False); salud_manual=d2.number_input('Salud a descontar',min_value=0.0,value=float(ex.get('salud_descuento',salud_auto)),step=1000.0,format='%.0f',disabled=not usar_salud_manual)
            if salud_tipo_vig=='Isapre' and mod=='Plan en UF': d2.caption(f'Plan: {sval:.2f} UF · equivalente {money(plan_salud)} · UF usada {uf_valor:,.2f}')
            afc=d3.number_input('AFC trabajador',min_value=0.0,value=float(ex.get('afc_descuento',0)),step=1000.0,format='%.0f',help='Editable para cuadrar con Previred.')
            impuesto=d1.number_input('Impuesto Único',min_value=0.0,value=float(ex.get('impuesto_unico',0)),step=1000.0,format='%.0f')
            prestamos=pd.read_sql_query("SELECT * FROM nomina_prestamos WHERE trabajador_id=? AND estado='VIGENTE' AND saldo>0 AND primera_cuota<=?",conn,params=(tr.id,periodo)); pre_sug=float(prestamos['cuota'].sum()) if not prestamos.empty else 0
            pre_desc=d2.number_input('Descuento préstamos',min_value=0.0,value=float(ex.get('prestamo_descuento',pre_sug)),step=1000.0,format='%.0f')
            otros_desc=d3.number_input('Otros descuentos',min_value=0.0,value=float(ex.get('otros_descuentos',0)),step=1000.0,format='%.0f')
            ant=conn.execute("SELECT COALESCE(SUM(monto),0) FROM nomina_anticipos WHERE trabajador_id=? AND periodo=?",(tr.id,periodo)).fetchone()[0] or 0
            calc=nomina_calcular(total_imp,total_noimp,comision,salud_tipo_vig,mod,sval,uf_valor,afc,impuesto,pre_desc,otros_desc,ant,afp_manual if usar_afp_manual else None,salud_manual if usar_salud_manual else None)
            a,b,c,d=st.columns(4); a.metric('Total imponible',money(total_imp)); b.metric('Total no imponible',money(total_noimp)); c.metric('Líquido período',money(calc['liquido'])); d.metric('Saldo fin de mes',money(calc['saldo']))
            st.info(f"AFP {afp_vig}: 10% + comisión {comision:.2f}% | Salud: {salud_tipo_vig} · {mod} | Anticipo registrado: {money(ant)}")
            obs=st.text_area('Observaciones',value=ex.get('observacion','') or '')
            if st.button('💾 Guardar / recalcular liquidación',type='primary'):
                vals=(periodo,tr.id,dias,sueldo_base,sueldo_periodo,grat,horas,bonos,otros_imp,noimp,otros_noimp,total_imp,total_noimp,total_imp+total_noimp,afp_vig,comision,calc['afp'],salud_tipo_vig,mod,sval,calc['salud'],afc,impuesto,pre_desc,otros_desc,calc['total_desc'],calc['liquido'],ant,calc['saldo'],uf_valor,calc['salud_plan_pesos'],'CALCULADO',obs)
                conn.execute("""INSERT INTO nomina_liquidaciones(periodo,trabajador_id,dias_trabajados,sueldo_base,sueldo_periodo,gratificacion,horas_extras,bonos_imponibles,otros_imponibles,asignacion_no_imponible,otros_no_imponibles,total_imponible,total_no_imponible,total_haberes,afp_nombre,afp_comision,afp_descuento,salud_tipo,salud_modalidad,salud_valor,salud_descuento,afc_descuento,impuesto_unico,prestamo_descuento,otros_descuentos,total_descuentos,liquido_periodo,anticipo,saldo_pagar,uf_valor,salud_plan_pesos,estado,observacion) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(periodo,trabajador_id) DO UPDATE SET dias_trabajados=excluded.dias_trabajados,sueldo_base=excluded.sueldo_base,sueldo_periodo=excluded.sueldo_periodo,gratificacion=excluded.gratificacion,horas_extras=excluded.horas_extras,bonos_imponibles=excluded.bonos_imponibles,otros_imponibles=excluded.otros_imponibles,asignacion_no_imponible=excluded.asignacion_no_imponible,otros_no_imponibles=excluded.otros_no_imponibles,total_imponible=excluded.total_imponible,total_no_imponible=excluded.total_no_imponible,total_haberes=excluded.total_haberes,afp_nombre=excluded.afp_nombre,afp_comision=excluded.afp_comision,afp_descuento=excluded.afp_descuento,salud_tipo=excluded.salud_tipo,salud_modalidad=excluded.salud_modalidad,salud_valor=excluded.salud_valor,salud_descuento=excluded.salud_descuento,afc_descuento=excluded.afc_descuento,impuesto_unico=excluded.impuesto_unico,prestamo_descuento=excluded.prestamo_descuento,otros_descuentos=excluded.otros_descuentos,total_descuentos=excluded.total_descuentos,liquido_periodo=excluded.liquido_periodo,anticipo=excluded.anticipo,saldo_pagar=excluded.saldo_pagar,uf_valor=excluded.uf_valor,salud_plan_pesos=excluded.salud_plan_pesos,estado=CASE WHEN nomina_liquidaciones.estado='CONTABILIZADO' THEN nomina_liquidaciones.estado ELSE 'CALCULADO' END,observacion=excluded.observacion""",vals)
                conn.execute("INSERT OR IGNORE INTO nomina_periodos(periodo) VALUES(?)",(periodo,)); conn.commit(); st.success('Liquidación guardada.'); st.rerun()

    with tabs[3]:
        st.subheader('Resumen de nómina y reportes')
        periodos=pd.read_sql_query("SELECT DISTINCT periodo FROM nomina_liquidaciones ORDER BY periodo DESC",conn)['periodo'].tolist()
        if not periodos: st.info('Aún no existen liquidaciones.')
        else:
            per=st.selectbox('Período',periodos,key='rep_per')
            df=pd.read_sql_query("""SELECT l.*,t.rut,t.nombre,t.cargo FROM nomina_liquidaciones l JOIN nomina_trabajadores t ON t.id=l.trabajador_id WHERE l.periodo=? ORDER BY t.nombre""",conn,params=(per,))
            cols=['rut','nombre','sueldo_periodo','gratificacion','total_imponible','total_no_imponible','afp_descuento','salud_descuento','afc_descuento','impuesto_unico','prestamo_descuento','anticipo','saldo_pagar']
            vista=df[cols].copy(); st.dataframe(formatear_montos_df(vista),use_container_width=True,hide_index=True)
            st.download_button('📥 Exportar resumen CSV',vista.to_csv(index=False,sep=';').encode('utf-8-sig'),f'nomina_{per}.csv','text/csv')
            headers=['RUT','Trabajador','Sueldo','Gratif.','Imponible','No impon.','AFP','Salud','AFC','Impuesto','Préstamo','Anticipo','Saldo final']
            filas=[]
            for r in vista.itertuples(index=False): filas.append([r[0],r[1]]+[money(x) for x in r[2:]])
            tot=['','TOTALES']+[money(vista[c].sum()) for c in cols[2:]]
            pdf=nomina_pdf(f'Resumen de Nómina - {per}','SGCI - Sistema de Gestión Contable Integral',headers,filas,tot)
            st.download_button('🖨️ PDF resumen de nómina',pdf,f'resumen_nomina_{per}.pdf','application/pdf')
            st.markdown('#### Liquidación individual imprimible')
            lm={f"{r.rut} - {r.nombre}":r for r in df.itertuples()}; ls=st.selectbox('Trabajador para reporte',list(lm),key='rep_trab'); rr=lm[ls]
            detalle=[['Sueldo período',money(rr.sueldo_periodo)],['Gratificación',money(rr.gratificacion)],['Horas extras',money(rr.horas_extras)],['Bonos imponibles',money(rr.bonos_imponibles)],['Total imponible',money(rr.total_imponible)],['Total no imponible',money(rr.total_no_imponible)],['AFP',money(rr.afp_descuento)],['Salud',money(rr.salud_descuento)],['Plan salud equivalente',money(getattr(rr,'salud_plan_pesos',0))],['UF utilizada',f"{float(getattr(rr,'uf_valor',0) or 0):,.2f}"],['AFC',money(rr.afc_descuento)],['Impuesto Único',money(rr.impuesto_unico)],['Préstamo',money(rr.prestamo_descuento)],['Otros descuentos',money(rr.otros_descuentos)],['Líquido período',money(rr.liquido_periodo)],['Anticipo quincenal',money(rr.anticipo)],['SALDO A PAGAR',money(rr.saldo_pagar)]]
            pdfi=nomina_pdf(f'Liquidación de Remuneraciones - {per}',f'{rr.nombre} · RUT {rr.rut} · {rr.cargo}', ['Concepto','Monto'],detalle)
            st.download_button('🖨️ PDF liquidación individual',pdfi,f'liquidacion_{rr.rut}_{per}.pdf','application/pdf')
            st.markdown('#### Historial del trabajador')
            hist=pd.read_sql_query("SELECT periodo,total_haberes,total_descuentos,liquido_periodo,anticipo,saldo_pagar,estado FROM nomina_liquidaciones WHERE trabajador_id=? ORDER BY periodo DESC",conn,params=(rr.trabajador_id,)); st.dataframe(formatear_montos_df(hist),use_container_width=True,hide_index=True)
            pdfh=nomina_pdf('Historial de Remuneraciones',f'{rr.nombre} · RUT {rr.rut}',['Período','Haberes','Descuentos','Líquido','Anticipo','Saldo final','Estado'],[[x.periodo,money(x.total_haberes),money(x.total_descuentos),money(x.liquido_periodo),money(x.anticipo),money(x.saldo_pagar),x.estado] for x in hist.itertuples()])
            st.download_button('🖨️ PDF historial trabajador',pdfh,f'historial_nomina_{rr.rut}.pdf','application/pdf')

    with tabs[4]:
        st.subheader('Parámetros previsionales')
        st.caption('Las comisiones AFP se guardan como parámetros editables para no depender de cambios en el código. Verifica vigencia antes de cerrar cada nómina.')
        afpdf=pd.read_sql_query("SELECT afp,comision,vigente_desde,activo FROM nomina_parametros_afp ORDER BY afp",conn); st.dataframe(afpdf,use_container_width=True,hide_index=True)
        amap={r.afp:r for r in afpdf.itertuples()}; aa=st.selectbox('AFP a modificar',list(amap)); ar=amap[aa]; nueva=st.number_input('Comisión %',min_value=0.0,max_value=10.0,value=float(ar.comision),step=.01); vig=st.text_input('Vigente desde',value=ar.vigente_desde or '')
        if st.button('Guardar parámetro AFP'):
            conn.execute("UPDATE nomina_parametros_afp SET comision=?,vigente_desde=? WHERE afp=?",(nueva,vig,aa)); conn.commit(); st.success('Parámetro actualizado.'); st.rerun()
        st.info('Salud: Fonasa usa 7% legal. Isapre admite 7%, porcentaje pactado, plan en UF o monto pactado en pesos; la liquidación conserva el valor UF utilizado y permite ajuste manual.')
        st.markdown('#### Valor UF por período')
        pu=st.text_input('Período UF (AAAA-MM)',value=date.today().strftime('%Y-%m'),key='uf_per'); vu=st.number_input('Valor UF del período',min_value=0.0,value=0.0,step=1.0,key='uf_val')
        if st.button('Guardar valor UF',key='uf_save'):
            conn.execute("INSERT INTO nomina_parametros_mensuales(periodo,valor_uf) VALUES(?,?) ON CONFLICT(periodo) DO UPDATE SET valor_uf=excluded.valor_uf",(pu,vu)); conn.commit(); st.success('UF guardada para el período.'); st.rerun()
        ufdf=pd.read_sql_query("SELECT periodo,valor_uf FROM nomina_parametros_mensuales ORDER BY periodo DESC",conn)
        if not ufdf.empty: st.dataframe(ufdf,use_container_width=True,hide_index=True)

    with tabs[5]:
        st.subheader('Contabilización de nómina')
        periodos=pd.read_sql_query("SELECT periodo,estado,fecha_cierre,asiento_id FROM nomina_periodos ORDER BY periodo DESC",conn)
        st.dataframe(periodos,use_container_width=True,hide_index=True)
        candidatos=pd.read_sql_query("SELECT DISTINCT periodo FROM nomina_liquidaciones WHERE estado<>'CONTABILIZADO' ORDER BY periodo DESC",conn)['periodo'].tolist()
        if candidatos:
            per=st.selectbox('Período a contabilizar',candidatos,key='cont_nom_per')
            df=pd.read_sql_query("SELECT COUNT(*) n,COALESCE(SUM(total_haberes),0) haberes,COALESCE(SUM(total_descuentos),0) descuentos,COALESCE(SUM(anticipo),0) anticipos,COALESCE(SUM(saldo_pagar),0) saldo FROM nomina_liquidaciones WHERE periodo=?",conn,params=(per,)).iloc[0]
            a,b,c,d=st.columns(4); a.metric('Trabajadores',int(df.n)); b.metric('Haberes',money(df.haberes)); c.metric('Anticipos',money(df.anticipos)); d.metric('Saldo fin de mes',money(df.saldo))
            st.warning('Al contabilizar, el período queda marcado como CONTABILIZADO. Revisa primero el resumen y las liquidaciones.')
            if st.button('🧾 Contabilizar nómina',type='primary'):
                try: asi=nomina_contabilizar_periodo(conn,per); registrar_auditoria(conn,'CONTABILIZAR NÓMINA',f'{per} asiento {asi}'); st.success(f'Nómina contabilizada en asiento N° {asi}.'); st.rerun()
                except Exception as e: st.error(str(e))
        else: st.info('No hay períodos pendientes de contabilización.')


# ESTADOS FINANCIEROS
# ============================================================

elif menu == "📊 Estados Financieros":
    st.title("📊 Estados Financieros")
    c1,c2,c3=st.columns(3)
    desde=c1.date_input("Desde", date(date.today().year,1,1), key="ef_desde")
    hasta=c2.date_input("Hasta", date.today(), key="ef_hasta")
    modo=c3.selectbox("Informe",["Estado de Resultados","Estado de Situación Financiera","Balance de Comprobación"])
    ds=desde.strftime("%Y-%m-%d"); hs=hasta.strftime("%Y-%m-%d")
    if modo=="Estado de Resultados":
        df=estado_resultados(conn,hs,ds)
        if df.empty: st.info("No hay movimientos para el período seleccionado.")
        else:
            ingresos=df[df.tipo=="Ingresos"]["saldo"].sum(); gastos=df[df.tipo=="Gastos"]["saldo"].sum(); resultado=ingresos-gastos
            a,b,c=st.columns(3); a.metric("Ingresos",money(ingresos)); b.metric("Gastos",money(gastos)); c.metric("Resultado",money(resultado))
            mostrar_ef=df[["codigo","nombre","saldo"]].rename(columns={"codigo":"Código","nombre":"Cuenta","saldo":"Saldo"})
            st.dataframe(mostrar_ef,use_container_width=True,hide_index=True)
            pdf_ef=nomina_pdf("Estado de Resultados",f"Desde {ds} hasta {hs}",["Código","Cuenta","Saldo"],[[r.Código,r.Cuenta,money(r.Saldo)] for r in mostrar_ef.itertuples(index=False)],["","RESULTADO",money(resultado)])
            st.download_button("🖨️ Imprimir / PDF Estado de Resultados",pdf_ef,f"estado_resultados_{hs}.pdf","application/pdf",key="pdf_er")
            st.success(f"Resultado del período: {money(resultado)}" if resultado>=0 else f"Resultado del período: {money(resultado)} (pérdida)")
    elif modo=="Estado de Situación Financiera":
        df=estado_situacion(conn,hs)
        if df.empty: st.info("No hay movimientos para la fecha seleccionada.")
        else:
            activos=df[df.tipo=="Activo"]["saldo"].sum(); pasivos=-df[df.tipo=="Pasivo"]["saldo"].sum(); patrimonio=-df[df.tipo=="Patrimonio"]["saldo"].sum()
            a,b,c=st.columns(3); a.metric("Activos",money(activos)); b.metric("Pasivos",money(pasivos)); c.metric("Patrimonio",money(patrimonio))
            mostrar_esf=df[["codigo","nombre","tipo","saldo"]].rename(columns={"codigo":"Código","nombre":"Cuenta","tipo":"Tipo","saldo":"Saldo"})
            st.dataframe(mostrar_esf,use_container_width=True,hide_index=True)
            pdf_esf=nomina_pdf("Estado de Situación Financiera",f"Al {hs}",["Código","Cuenta","Tipo","Saldo"],[[r.Código,r.Cuenta,r.Tipo,money(r.Saldo)] for r in mostrar_esf.itertuples(index=False)],["","TOTAL ACTIVO / P+P","",f"{money(activos)} / {money(pasivos+patrimonio)}"] )
            st.download_button("🖨️ Imprimir / PDF Estado de Situación",pdf_esf,f"estado_situacion_{hs}.pdf","application/pdf",key="pdf_esf")
            st.info(f"Control: Activo = {money(activos)} | Pasivo + Patrimonio = {money(pasivos+patrimonio)} | Diferencia = {money(activos-pasivos-patrimonio)}")
    else:
        df=resumen_financiero(conn,hs)
        if df.empty: st.info("No hay movimientos.")
        else:
            df["saldo_deudor"]=df["debe"]-df["haber"].clip(upper=df["debe"])
            df["saldo_acreedor"]=df["haber"]-df["debe"].clip(upper=df["haber"])
            mostrar_bc=df[["codigo","nombre","debe","haber","saldo"]].rename(columns={"codigo":"Código","nombre":"Cuenta","debe":"Debe","haber":"Haber","saldo":"Saldo"})
            st.dataframe(mostrar_bc,use_container_width=True,hide_index=True)
            pdf_bc=nomina_pdf("Balance de Comprobación",f"Al {hs}",["Código","Cuenta","Debe","Haber","Saldo"],[[r.Código,r.Cuenta,money(r.Debe),money(r.Haber),money(r.Saldo)] for r in mostrar_bc.itertuples(index=False)],["","TOTALES",money(df.debe.sum()),money(df.haber.sum()),money(df.saldo.sum())])
            st.download_button("🖨️ Imprimir / PDF Balance",pdf_bc,f"balance_comprobacion_{hs}.pdf","application/pdf",key="pdf_bc_ef")
            st.success("🟢 Balance cuadrado" if abs(df.debe.sum()-df.haber.sum())<0.01 else f"🔴 Diferencia: {money(df.debe.sum()-df.haber.sum())}")


# ============================================================
# BANCOS Y CARTOLAS
# ============================================================

elif menu == "🏦 Bancos y Cartolas":
    st.title("🏦 Banco")
    st.caption("Gestión bancaria, cartolas, movimientos y conciliación bancaria.")
    tabs = st.tabs(["Cuentas bancarias", "Cargar cartola", "Movimiento manual", "Conciliación", "Operaciones manuales", "Movimientos"])

    with tabs[0]:
        df = pd.read_sql_query("SELECT b.id AS ID,b.nombre AS Banco,b.numero_cuenta AS Cuenta,b.tipo AS Tipo,b.moneda AS Moneda,b.cuenta_contable AS Cuenta_Contable,b.saldo_inicial AS Saldo_Inicial FROM bancos b WHERE activo=1 ORDER BY nombre", conn)
        if not df.empty:
            st.dataframe(formatear_montos_df(df), use_container_width=True, hide_index=True)
        with st.form("nuevo_banco"):
            a,b,c = st.columns(3)
            nombre = a.text_input("Banco")
            numero_cuenta = b.text_input("N° cuenta")
            tipo = c.selectbox("Tipo", ["Cuenta corriente","Cuenta vista","Cuenta empresa","Otra"])
            cuentas = cuentas_imputables(conn)
            mapa = dict(zip(cuentas.etiqueta, cuentas.codigo))
            cuenta = c.selectbox("Cuenta contable bancaria", list(mapa.keys())) if mapa else ""
            saldo = st.number_input("Saldo inicial", value=0.0, step=1000.0,format='%.0f')
            if st.form_submit_button("Guardar cuenta bancaria"):
                conn.execute("INSERT INTO bancos(nombre,numero_cuenta,tipo,cuenta_contable,saldo_inicial) VALUES(?,?,?,?,?)", (nombre,numero_cuenta,tipo,mapa.get(cuenta),saldo))
                conn.commit(); registrar_auditoria(conn,"NUEVO BANCO",nombre); st.success("Cuenta bancaria creada.")

        st.divider()
        st.subheader("Vinculación contable de cuentas bancarias")
        st.caption("Cada cuenta bancaria debe apuntar a su cuenta del plan contable. Los cargos de cartola acreditarán esta cuenta; no Caja.")
        bancos_cfg = pd.read_sql_query("SELECT id,nombre,numero_cuenta,cuenta_contable FROM bancos WHERE activo=1 ORDER BY nombre", conn)
        if not bancos_cfg.empty and mapa:
            banco_cfg_label = st.selectbox("Cuenta bancaria a configurar", [f"{r.id} - {r.nombre} - {r.numero_cuenta}" for r in bancos_cfg.itertuples()], key="cfg_banco_sel")
            banco_cfg_id = int(banco_cfg_label.split(" - ")[0])
            actual = bancos_cfg.loc[bancos_cfg["id"]==banco_cfg_id,"cuenta_contable"].iloc[0]
            etiquetas = list(mapa.keys())
            idx_actual = next((i for i,e in enumerate(etiquetas) if mapa[e] == actual), 0)
            nueva_etiqueta = st.selectbox("Cuenta contable vinculada", etiquetas, index=idx_actual, key="cfg_banco_cuenta")
            if actual:
                st.info(f"Actualmente vinculada a: {actual} - {Plan(conn).todos.get(actual, actual)}")
            if st.button("💾 Guardar vinculación bancaria", key="guardar_cfg_banco"):
                conn.execute("UPDATE bancos SET cuenta_contable=? WHERE id=?", (mapa[nueva_etiqueta], banco_cfg_id))
                conn.commit(); registrar_auditoria(conn,"VINCULACIÓN BANCO",f"Banco {banco_cfg_id} -> {mapa[nueva_etiqueta]}")
                st.success("Vinculación actualizada. Los próximos asientos de esta cartola usarán esa cuenta bancaria.")
                st.rerun()

    with tabs[1]:
        bancos = pd.read_sql_query("SELECT id,nombre,numero_cuenta FROM bancos WHERE activo=1 ORDER BY nombre", conn)
        if bancos.empty:
            st.warning("Primero crea una cuenta bancaria.")
        else:
            banco_label = st.selectbox("Cuenta bancaria", [f"{r.id} - {r.nombre} - {r.numero_cuenta}" for r in bancos.itertuples()], key="carga_banco")
            banco_id = int(banco_label.split(" - ")[0])
            archivo = st.file_uploader("Cartola bancaria PDF, CSV o Excel", type=["pdf","csv","xlsx","xls"], key="cartola_file")
            password_pdf = st.text_input("Contraseña del PDF (solo si está protegido)", type="password", key="cartola_pwd")
            st.caption("La contraseña se usa únicamente para abrir el PDF durante esta carga; SGCI no la guarda.")

            if archivo:
                try:
                    if archivo.name.lower().endswith(".pdf"):
                        dfc = leer_cartola_pdf(archivo, password_pdf)
                    else:
                        dfc = leer_archivo_tabular(archivo)
                    st.write("Vista previa")
                    st.dataframe(dfc.head(50), use_container_width=True, hide_index=True)
                    if st.button("Importar cartola", type="primary"):
                        nuevos,repetidos,lote = importar_cartola(conn, dfc, banco_id, origen="PDF" if archivo.name.lower().endswith(".pdf") else "ARCHIVO")
                        st.success(f"Importados {nuevos} movimientos. Repetidos omitidos: {repetidos}.")
                        st.rerun()
                except Exception as e:
                    st.error(str(e))

            plantilla = pd.DataFrame([{"fecha":"2026-09-30","descripcion":"TRANSFERENCIA EJEMPLO","referencia":"12345","cargo":0,"abono":100000,"saldo":100000}])
            st.download_button("📥 Descargar plantilla de cartola", plantilla.to_csv(index=False,sep=";").encode("utf-8-sig"), "plantilla_cartola_bancaria.csv", "text/csv")

    with tabs[2]:
        bancos = pd.read_sql_query("SELECT id,nombre,numero_cuenta FROM bancos WHERE activo=1 ORDER BY nombre", conn)
        if bancos.empty:
            st.warning("Primero crea una cuenta bancaria.")
        else:
            with st.form("movimiento_bancario_manual"):
                label = st.selectbox("Cuenta bancaria", [f"{r.id} - {r.nombre} - {r.numero_cuenta}" for r in bancos.itertuples()])
                banco_id = int(label.split(" - ")[0])
                c1,c2 = st.columns(2)
                fecha_mov = c1.date_input("Fecha", date.today())
                naturaleza = c2.selectbox("Movimiento", ["Cargo / salida de dinero", "Abono / entrada de dinero"])
                descripcion = st.text_input("Descripción")
                referencia = st.text_input("Referencia / N° documento")
                monto = st.number_input("Monto", min_value=0.0, step=1000.0,format='%.0f')
                saldo = st.number_input("Saldo después del movimiento (opcional)", value=0.0, step=1000.0,format='%.0f')
                if st.form_submit_button("Guardar movimiento manual", type="primary"):
                    if not descripcion or monto <= 0:
                        st.error("Indica descripción y un monto mayor que cero.")
                    else:
                        cargo = monto if naturaleza.startswith("Cargo") else 0
                        abono = monto if naturaleza.startswith("Abono") else 0
                        nuevos,repetidos,_ = registrar_movimiento_manual(conn,banco_id,fecha_mov.strftime("%Y-%m-%d"),descripcion,referencia,cargo,abono,saldo)
                        if nuevos:
                            st.success("Movimiento guardado. Ya está disponible para conciliación.")
                        else:
                            st.warning("Ese movimiento ya existe y no se duplicó.")

    with tabs[3]:
        bancos = pd.read_sql_query("SELECT id,nombre,numero_cuenta FROM bancos WHERE activo=1 ORDER BY nombre", conn)
        if bancos.empty:
            st.info("No hay cuentas bancarias.")
        else:
            label = st.selectbox("Cuenta a conciliar", [f"{r.id} - {r.nombre} - {r.numero_cuenta}" for r in bancos.itertuples()], key="conc_banco")
            banco_id = int(label.split(" - ")[0])
            info = conciliacion_banco(conn,banco_id)
            if info:
                sc,ss,dif,movs = info
                a,b,c = st.columns(3); a.metric("Saldo cartola",money(sc)); b.metric("Saldo contable",money(ss)); c.metric("Diferencia",money(dif))
                st.success("🟢 Conciliación sin diferencia" if abs(dif)<0.01 else "🟡 Revisar diferencias")

            pendientes = pd.read_sql_query("""SELECT id,fecha,descripcion,referencia,cargo,abono,saldo,origen
                                                FROM cartola_bancaria WHERE banco_id=? AND conciliado=0
                                                ORDER BY fecha,id""", conn, params=[banco_id])
            if pendientes.empty:
                st.success("No hay movimientos pendientes de conciliación.")
            else:
                st.subheader("Movimientos pendientes")
                opciones_mov = []
                for r in pendientes.itertuples():
                    monto = r.cargo if float(r.cargo or 0)>0 else r.abono
                    clase = "Cargo" if float(r.cargo or 0)>0 else "Abono"
                    opciones_mov.append(f"{r.id} | {r.fecha} | {clase} {money(monto)} | {r.descripcion}")
                elegido = st.selectbox("Selecciona un movimiento", opciones_mov)
                movimiento_id = int(elegido.split(" | ",1)[0])
                cand = candidatos_conciliacion(conn,movimiento_id)
                if cand.empty:
                    st.warning("No encontré coincidencias exactas por monto. Puedes imputar este movimiento directamente a contabilidad aquí mismo.")
                else:
                    mostrar = cand[["confianza","tipo","fecha","descripcion","referencia","monto","cuenta"]].copy()
                    mostrar["confianza"] = mostrar["confianza"].apply(lambda x: f"{x:.0f}%")
                    st.dataframe(mostrar.rename(columns={"confianza":"Coincidencia","tipo":"Origen","fecha":"Fecha","descripcion":"Detalle","referencia":"Referencia","monto":"Monto","cuenta":"Cuenta"}), use_container_width=True, hide_index=True)
                    opciones_cand = [f"{i} | {r.tipo} | {r.descripcion} | {money(r.monto)} | {r.confianza:.0f}%" for i,r in cand.iterrows()]
                    sel = st.selectbox("Coincidencia propuesta", opciones_cand)
                    idx = int(sel.split(" | ",1)[0])
                    elegido_c = cand.iloc[idx]
                    st.info("SGCI propone por coincidencia de monto y suma puntos por cercanía de fecha/referencia. La contabilización solo ocurre cuando tú confirmas.")
                    if st.button("✅ Confirmar y contabilizar coincidencia", type="primary"):
                        try:
                            asiento = contabilizar_conciliacion_bancaria(conn,movimiento_id,elegido_c["tipo"],int(elegido_c["id"]))
                            st.success(f"Movimiento conciliado y contabilizado en el asiento {asiento}.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"No se pudo conciliar: {e}")

                mov_sel = pendientes.loc[pendientes["id"] == movimiento_id].iloc[0]
                if float(mov_sel["cargo"] or 0) > 0:
                    st.divider()
                    st.subheader("🏢 Pago a proveedor")
                    st.caption("Úsalo cuando el cargo bancario paga una factura ya contabilizada en RCV. SGCI rebaja Proveedores, acredita Banco y actualiza el auxiliar del proveedor y sus documentos.")
                    proveedores_pago = pd.read_sql_query("SELECT id,rut,COALESCE(NULLIF(razon_social,''),nombre) nombre FROM proveedores WHERE activo=1 ORDER BY nombre", conn)
                    if proveedores_pago.empty:
                        st.info("No hay proveedores registrados.")
                    else:
                        prov_labels = [f"{r.id} | {r.rut} | {r.nombre}" for r in proveedores_pago.itertuples()]
                        prov_label = st.selectbox("Proveedor", prov_labels, key=f"pago_prov_{movimiento_id}")
                        prov_id = int(prov_label.split(" | ",1)[0])
                        docs_pend = documentos_pendientes_proveedor(conn, prov_id)
                        modo_pago_prov = st.radio(
                            "Aplicación del pago",
                            ["Aplicar a documento(s) pendiente(s)", "Pago sin documento / saldo anterior"],
                            key=f"modo_pago_prov_{movimiento_id}",
                            horizontal=True
                        )

                        if modo_pago_prov == "Aplicar a documento(s) pendiente(s)":
                            if docs_pend.empty:
                                st.info("Este proveedor no tiene documentos con saldo pendiente. Si el pago corresponde a un período anterior, usa ‘Pago sin documento / saldo anterior’.")
                            else:
                                docs_show = docs_pend.copy()
                                for col in ["total","aplicado","pendiente"]:
                                    docs_show[col] = docs_show[col].apply(money)
                                st.dataframe(docs_show.rename(columns={"fecha":"Fecha","folio":"Folio","tipo_doc":"Tipo doc.","total":"Total","aplicado":"Pagado","pendiente":"Saldo pendiente"}), use_container_width=True, hide_index=True)
                                doc_map = {f"{int(r.id)} | {r.fecha} | Folio {r.folio} | pendiente {money(r.pendiente)}": int(r.id) for r in docs_pend.itertuples()}
                                docs_sel_labels = st.multiselect("Documento(s) que paga este movimiento", list(doc_map.keys()), key=f"docs_pago_{movimiento_id}")
                                docs_ids = [doc_map[x] for x in docs_sel_labels]
                                disponible = float(docs_pend[docs_pend["id"].isin(docs_ids)]["pendiente"].sum()) if docs_ids else 0.0
                                monto_mov = float(mov_sel["cargo"] or 0)
                                if docs_ids:
                                    st.info(f"Cargo bancario: {money(monto_mov)} | Saldo disponible en documentos seleccionados: {money(disponible)}")
                                    if disponible > monto_mov + 0.01:
                                        st.caption("El pago se aplicará en el orden de los documentos seleccionados; el último puede quedar parcialmente pagado.")
                                confirma_prov = st.checkbox("Confirmo que este movimiento corresponde al pago del proveedor y documentos seleccionados.", key=f"conf_pago_prov_{movimiento_id}")
                                if st.button("💳 Contabilizar pago a proveedor", type="primary", disabled=(not confirma_prov or not docs_ids), key=f"btn_pago_prov_{movimiento_id}"):
                                    try:
                                        asiento, aplicaciones = contabilizar_pago_proveedor_desde_cartola(conn, movimiento_id, prov_id, docs_ids)
                                        st.success(f"Pago contabilizado y conciliado en el asiento {asiento}. Auxiliar del proveedor actualizado.")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"No se pudo contabilizar el pago: {e}")
                        else:
                            monto_mov = float(mov_sel["cargo"] or 0)
                            st.info(f"Se registrará {money(monto_mov)} como pago de {prov_label.split(' | ',2)[-1]}, sin asociarlo a una factura. Quedará visible en el estado de cuenta del proveedor.")
                            st.caption("Esta opción es apropiada para saldos anteriores o documentos que aún no están cargados. Hasta incorporar el saldo inicial, el auxiliar puede mostrar temporalmente un saldo deudor.")
                            confirma_sin_doc = st.checkbox("Confirmo que el pago corresponde a este proveedor y no deseo asociarlo a un documento.", key=f"conf_pago_prov_sd_{movimiento_id}")
                            if st.button("💳 Contabilizar pago sin documento", type="primary", disabled=not confirma_sin_doc, key=f"btn_pago_prov_sd_{movimiento_id}"):
                                try:
                                    asiento = contabilizar_pago_proveedor_sin_documento(conn, movimiento_id, prov_id)
                                    st.success(f"Pago sin documento contabilizado y conciliado en el asiento {asiento}. Auxiliar del proveedor actualizado.")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"No se pudo contabilizar el pago: {e}")

                st.divider()
                st.subheader("Imputación manual del movimiento")
                st.caption("Úsala cuando no exista una coincidencia adecuada. Al confirmar, SGCI genera el asiento y marca el movimiento como conciliado. Si el gasto ya fue provisionado, selecciona la cuenta por pagar correspondiente; no vuelvas a seleccionar la cuenta de gasto.")
                cuentas_manual = cuentas_imputables(conn)
                if cuentas_manual.empty:
                    st.info("No hay cuentas imputables disponibles en el plan de cuentas.")
                else:
                    mapa_manual = dict(zip(cuentas_manual.etiqueta, cuentas_manual.codigo))
                    cuenta_manual = st.selectbox("Cuenta contable de contrapartida", list(mapa_manual.keys()), key=f"imputacion_cuenta_{movimiento_id}")
                    mov_sel = pendientes.loc[pendientes["id"] == movimiento_id].iloc[0]
                    glosa_base = limpiar_texto(mov_sel["descripcion"])
                    glosa_manual = st.text_input("Glosa del asiento", value=glosa_base, key=f"imputacion_glosa_{movimiento_id}")
                    monto_sel = float(mov_sel["cargo"] or 0) if float(mov_sel["cargo"] or 0) > 0 else float(mov_sel["abono"] or 0)
                    naturaleza_sel = "Cargo / salida" if float(mov_sel["cargo"] or 0) > 0 else "Abono / entrada"
                    st.info(f"Movimiento: {naturaleza_sel} por {money(monto_sel)}. SGCI usará automáticamente la cuenta bancaria como la otra línea del asiento.")
                    confirmar_manual = st.checkbox("Confirmo que revisé la cuenta contable y deseo contabilizar y conciliar este movimiento.", key=f"imputacion_confirma_{movimiento_id}")
                    if st.button("🧾 Contabilizar e imputar manualmente", type="primary", disabled=not confirmar_manual, key=f"imputacion_btn_{movimiento_id}"):
                        try:
                            asiento = contabilizar_imputacion_manual_bancaria(conn,movimiento_id,mapa_manual[cuenta_manual],glosa_manual)
                            st.success(f"Movimiento imputado, conciliado y contabilizado en el asiento {asiento}.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"No se pudo imputar el movimiento: {e}")

    with tabs[4]:
        st.subheader("Servicios, nómina y otros pagos/abonos")
        st.caption("Registra aquí operaciones que no provienen del RCV. Luego SGCI las buscará por coincidencia de monto contra la cartola.")
        cuentas = cuentas_imputables(conn)
        mapa = dict(zip(cuentas.etiqueta,cuentas.codigo))
        with st.form("nueva_operacion_manual"):
            c1,c2 = st.columns(2)
            fecha_op = c1.date_input("Fecha de la operación", date.today())
            tipo_op = c2.selectbox("Tipo", ["PAGO","ABONO"])
            descripcion_op = st.text_input("Descripción (ej.: Nómina septiembre, Internet, Arriendo)")
            referencia_op = st.text_input("Referencia (opcional)")
            monto_op = st.number_input("Monto de la operación", min_value=0.0, step=1000.0,format='%.0f')
            cuenta_op = st.selectbox("Cuenta contable de contrapartida", list(mapa.keys())) if mapa else ""
            if st.form_submit_button("Guardar operación"):
                if not descripcion_op or monto_op <= 0 or not cuenta_op:
                    st.error("Completa descripción, monto y cuenta contable.")
                else:
                    crear_obligacion_manual(conn,fecha_op.strftime("%Y-%m-%d"),tipo_op,descripcion_op,referencia_op,monto_op,mapa[cuenta_op])
                    st.success("Operación guardada. SGCI podrá encontrarla por coincidencia de monto.")
                    st.rerun()

        ops = pd.read_sql_query("""SELECT o.id,o.fecha,o.tipo,o.descripcion,o.referencia,o.monto,o.codigo_cuenta,
                                     CASE WHEN o.conciliado=1 THEN 'Conciliado' ELSE 'Pendiente' END estado
                                     FROM obligaciones_manuales o ORDER BY o.fecha DESC,o.id DESC""", conn)
        if not ops.empty:
            st.dataframe(ops, use_container_width=True, hide_index=True)

    with tabs[5]:
        bancos = pd.read_sql_query("SELECT id,nombre FROM bancos WHERE activo=1 ORDER BY nombre", conn)
        if not bancos.empty:
            label = st.selectbox("Cuenta", [f"{r.id} - {r.nombre}" for r in bancos.itertuples()], key="mov_banco")
            dfm = pd.read_sql_query("""SELECT fecha,descripcion,referencia,cargo,abono,saldo,
                                        CASE WHEN conciliado=1 THEN 'Sí' ELSE 'No' END conciliado,
                                        origen,match_tipo,match_id,asiento_id,observacion
                                        FROM cartola_bancaria WHERE banco_id=? ORDER BY fecha,id DESC""", conn, params=[int(label.split(" - ")[0])])
            st.dataframe(dfm, use_container_width=True, hide_index=True)

            corregibles = pd.read_sql_query("""SELECT id,fecha,descripcion,cargo,abono,asiento_id
                                               FROM cartola_bancaria
                                               WHERE banco_id=? AND conciliado=1 AND match_tipo='IMPUTACION_MANUAL'
                                               ORDER BY fecha,id DESC""", conn, params=[int(label.split(" - ")[0])])
            if not corregibles.empty:
                st.divider()
                st.subheader("Corregir imputación manual")
                st.caption("Si una imputación fue enviada a una cuenta equivocada, SGCI genera un asiento reverso y deja el movimiento pendiente para volver a conciliarlo. No elimina el asiento histórico.")
                corr_map = {}
                for r in corregibles.itertuples():
                    monto_corr = float(r.cargo or 0) if float(r.cargo or 0)>0 else float(r.abono or 0)
                    lab = f"{r.id} | {r.fecha} | {money(monto_corr)} | asiento {r.asiento_id} | {r.descripcion}"
                    corr_map[lab] = int(r.id)
                corr_label = st.selectbox("Movimiento a corregir", list(corr_map.keys()), key="corr_mov_banco")
                confirma_corr = st.checkbox("Confirmo que deseo revertir contablemente esta imputación y volver a dejar el movimiento pendiente.", key="corr_confirma")
                if st.button("↩️ Revertir y reabrir movimiento", disabled=not confirma_corr, key="corr_btn"):
                    try:
                        rev = corregir_conciliacion_manual(conn, corr_map[corr_label])
                        st.success(f"Imputación revertida mediante el asiento {rev}. El movimiento vuelve a estar pendiente de conciliación.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"No se pudo corregir la imputación: {e}")


# ============================================================
# CIERRE MENSUAL
# ============================================================

elif menu == "🔒 Cierre Mensual":
    st.title("🔒 Cierre Mensual")
    st.info("El cierre evita que se modifique accidentalmente un período ya revisado. Los ajustes posteriores deben registrarse en un período abierto.")
    periodos=pd.read_sql_query("SELECT periodo,estado,fecha_cierre,observacion FROM periodos_contables ORDER BY periodo DESC",conn)
    st.dataframe(periodos,use_container_width=True,hide_index=True)
    periodo=st.text_input("Período a revisar (AAAA-MM)",date.today().strftime("%Y-%m"))
    try:
        datetime.strptime(periodo,"%Y-%m")
        asegurar_periodo(conn,periodo)
        df=periodos.copy()
        desde=periodo+"-01"; ultimo=(pd.Period(periodo).end_time).strftime("%Y-%m-%d")
        diario=pd.read_sql_query("SELECT COALESCE(SUM(debe),0) debe,COALESCE(SUM(haber),0) haber FROM libro_diario WHERE fecha BETWEEN ? AND ?",conn,params=[desde,ultimo]).iloc[0]
        dif=float(diario.debe-diario.haber)
        c1,c2,c3=st.columns(3); c1.metric("Debe",money(diario.debe)); c2.metric("Haber",money(diario.haber)); c3.metric("Diferencia",money(dif))
        alertas=[]
        cc=conciliacion_clientes(conn); cp=conciliacion_proveedores(conn)
        if not cc.empty and abs(float(cc.iloc[0].Diferencia))>0.01: alertas.append("Diferencia en clientes")
        if not cp.empty and abs(float(cp.iloc[0].Diferencia))>0.01: alertas.append("Diferencia en proveedores")
        if abs(dif)>0.01: alertas.append("Libro diario descuadrado")
        st.subheader("Lista de comprobación")
        if alertas:
            for x in alertas: st.error("🔴 "+x)
        else: st.success("🟢 No se detectaron diferencias básicas. El período está listo para revisión final.")
        if periodo_estado(conn,periodo)=="ABIERTO":
            if st.button("🔒 CERRAR PERÍODO",type="primary"):
                if alertas: st.error("No se recomienda cerrar mientras existan alertas.")
                else:
                    conn.execute("UPDATE periodos_contables SET estado='CERRADO',fecha_cierre=? WHERE periodo=?",(datetime.now().strftime("%Y-%m-%d %H:%M:%S"),periodo)); conn.commit(); registrar_auditoria(conn,"CIERRE CONTABLE",periodo); st.success("Período cerrado."); st.rerun()
        else:
            st.success("🔒 Período cerrado")
            if st.button("Reabrir período"):
                conn.execute("UPDATE periodos_contables SET estado='ABIERTO',fecha_cierre=NULL WHERE periodo=?",(periodo,)); conn.commit(); registrar_auditoria(conn,"REAPERTURA CONTABLE",periodo); st.warning("Período reabierto."); st.rerun()
    except Exception as e: st.error(f"Período inválido: {e}")


# ============================================================
# CUENTAS POR COBRAR/PAGAR
# ============================================================

elif menu == "📌 Cuentas por Cobrar/Pagar":
    st.title("📌 Cuentas por Cobrar y por Pagar")
    t1,t2=st.tabs(["Clientes","Proveedores"])
    with t1:
        df=antiguedad_documentos(conn,"clientes")
        if df.empty: st.info("No hay saldos pendientes.")
        else:
            resumen=df.groupby("tramo",observed=False)["saldo"].sum().reindex(["0-30","31-60","61-90","+90"],fill_value=0).reset_index(); st.dataframe(resumen.rename(columns={"tramo":"Antigüedad","saldo":"Saldo"}),use_container_width=True,hide_index=True); st.dataframe(df[["entidad","fecha","folio","saldo","dias","tramo"]],use_container_width=True,hide_index=True)
    with t2:
        df=antiguedad_documentos(conn,"proveedores")
        if df.empty: st.info("No hay saldos pendientes.")
        else:
            resumen=df.groupby("tramo",observed=False)["saldo"].sum().reindex(["0-30","31-60","61-90","+90"],fill_value=0).reset_index(); st.dataframe(resumen.rename(columns={"tramo":"Antigüedad","saldo":"Saldo"}),use_container_width=True,hide_index=True); st.dataframe(df[["entidad","fecha","folio","saldo","dias","tramo"]],use_container_width=True,hide_index=True)

# ============================================================
# RCV COMPRAS
# ============================================================

elif menu == "📥 RCV Compras":

    st.title("📥 Registro de Compras - SII")

    pestañas_compras = st.tabs(["📂 Cargar Archivo CSV", "📥 Plantilla Descargable y Carga de Excel", "🔄 Reclasificar contabilizadas"])

    with pestañas_compras[0]:
        archivo = st.file_uploader(
            "Cargar RCV de Compras",
            type=["csv", "xlsx", "xls"],
            key="rcv_compras_file"
        )

        if archivo:
            try:
                df_original = leer_archivo_tabular(archivo)
                st.success(f"Archivo leído: {len(df_original):,} filas")

                df = normalizar_rcv(df_original, "compras")
                df = preparar_documentos(conn, df, "compras")

                st.session_state["rcv_compras"] = df
            except Exception as e:
                st.error(f"Error: {e}")

    with pestañas_compras[1]:
        st.info("Descarga la plantilla modelo, rellénala en tu Excel con tus compras y súbela aquí adjunta para procesarla de inmediato.")

        df_plantilla_modelo = pd.DataFrame([
            {
                "tipo_doc": 33,
                "folio": "147039",
                "fecha_doc": str(date.today()),
                "rut": "76123456-7",
                "razon_social": "PROVEEDOR EJEMPLO SPA",
                "exento": 0.0,
                "neto": 130125.0,
                "iva": 24724.0,
                "total": 154849.0
            }
        ])

        csv_plantilla = df_plantilla_modelo.to_csv(index=False, sep=";").encode("utf-8-sig")

        st.download_button(
            label="📥 Descargar Plantilla Modelo (CSV/Excel)",
            data=csv_plantilla,
            file_name="plantilla_rcv_compras.csv",
            mime="text/csv",
            type="secondary"
        )

        st.divider()

        archivo_subido = st.file_uploader(
            "Adjuntar Plantilla Rellenada",
            type=["csv"],
            key="archivo_plantilla_compras"
        )

        if archivo_subido:
            try:
                df_subido = leer_archivo_tabular(archivo_subido)
                df_prep = df_subido.copy()
                df_prep["fecha_doc"] = df_prep["fecha_doc"].apply(fecha_iso)
                df_prep["neto"] = df_prep["neto"].apply(numero)
                df_prep["iva"] = df_prep["iva"].apply(numero)
                df_prep["exento"] = df_prep["exento"].apply(numero)
                df_prep["total"] = df_prep["total"].apply(numero)
                df_prep["iva_no_rec"] = 0.0
                df_prep["neto_af"] = 0.0
                df_prep["iva_af"] = 0.0
                df_prep["iva_uso_comun"] = 0.0
                df_prep["fecha_recepcion"] = df_prep["fecha_doc"]
                df_prep["ref_type"] = None
                df_prep["ref_folio"] = ""

                df_procesado = preparar_documentos(conn, df_prep, "compras")
                st.session_state["rcv_compras"] = df_procesado
                st.success("¡Plantilla adjuntada y procesada con éxito! Revisa la bandeja de revisión abajo.")
            except Exception as e:
                st.error(f"Error procesando la plantilla adjunta: {e}")


    with pestañas_compras[2]:
        st.subheader("🔄 Reclasificar compras ya contabilizadas")
        st.caption("Genera un asiento de reclasificación. No modifica IVA Crédito Fiscal ni Proveedores y mantiene el documento original.")

        compras_reclas = compras_para_reclasificar(conn)
        if compras_reclas.empty:
            st.info("No hay compras contabilizadas para reclasificar.")
        else:
            filtro = st.text_input("Buscar por proveedor, RUT o folio", key="buscar_reclas_compra")
            vista = compras_reclas.copy()
            if filtro.strip():
                q = filtro.strip().lower()
                mascara = (
                    vista["proveedor"].fillna("").astype(str).str.lower().str.contains(q, regex=False)
                    | vista["rut"].fillna("").astype(str).str.lower().str.contains(q, regex=False)
                    | vista["folio"].fillna("").astype(str).str.lower().str.contains(q, regex=False)
                )
                vista = vista[mascara].copy()

            vista["Seleccionar"] = False
            vista["Neto"] = vista["monto_neto"].apply(money)
            vista["Total"] = vista["monto_total"].apply(money)
            editor = st.data_editor(
                vista[["Seleccionar", "compra_id", "fecha", "rut", "proveedor", "tipo_doc", "folio", "Neto", "Total", "cuenta_gasto"]].rename(columns={
                    "compra_id":"ID", "fecha":"Fecha", "rut":"RUT", "proveedor":"Proveedor", "tipo_doc":"Tipo", "folio":"Folio", "cuenta_gasto":"Cuenta actual"
                }),
                use_container_width=True,
                hide_index=True,
                disabled=["ID","Fecha","RUT","Proveedor","Tipo","Folio","Neto","Total","Cuenta actual"],
                key="editor_reclas_compras"
            )

            seleccionados = editor.loc[editor["Seleccionar"] == True, "ID"].astype(int).tolist()
            opciones_reclas = cuentas_imputables(conn)
            etiquetas_reclas = opciones_reclas["etiqueta"].tolist()
            nueva_etiqueta = st.selectbox("Nueva cuenta contable", etiquetas_reclas, key="nueva_cuenta_reclas")
            nueva_codigo = nueva_etiqueta.split(" - ", 1)[0]
            recordar = st.checkbox("Usar esta cuenta para futuras compras de estos proveedores", value=False, key="recordar_reclas")

            if seleccionados:
                st.info(f"{len(seleccionados)} compra(s) seleccionada(s). Se generará un asiento de reclasificación por cada documento.")
            confirmar = st.checkbox("Confirmo la reclasificación contable seleccionada", key="confirmar_reclas")
            if st.button("🔄 RECLASIFICAR COMPRAS", type="primary", disabled=(not seleccionados or not confirmar), key="btn_reclas_compras"):
                try:
                    r = reclasificar_compras(conn, seleccionados, nueva_codigo, recordar)
                    st.success(f"Reclasificación completada: {r['reclasificadas']} compra(s). Omitidas: {r['omitidas']}.")
                    st.rerun()
                except Exception as e:
                    st.error(f"No fue posible reclasificar: {e}")

    if "rcv_compras" in st.session_state and isinstance(st.session_state["rcv_compras"], pd.DataFrame):

        df = st.session_state["rcv_compras"].copy()

        st.divider()
        st.subheader("Resumen de importación")

        # Criterio corregido considerando el signo (-1 para NC)
        total = (df["total"] * df["signo"]).sum()
        neto = (df["neto"] * df["signo"]).sum()
        iva = (df["iva"] * df["signo"]).sum()

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Documentos", len(df))
        c2.metric("Neto", money(neto))
        c3.metric("IVA", money(iva))
        c4.metric("Total", money(total))

        st.divider()
        st.subheader("Bandeja de revisión")

        columnas = [
            "estado",
            "fecha_doc",
            "rut",
            "razon_social",
            "tipo_doc",
            "folio",
            "neto",
            "iva",
            "total",
            "cuenta_codigo",
            "cuenta_origen",
            "observaciones",
        ]

        mostrar = df[[c for c in columnas if c in df.columns]].copy()
        mostrar = mostrar.rename(
            columns={
                "estado": "Estado",
                "fecha_doc": "Fecha",
                "rut": "RUT",
                "razon_social": "Proveedor",
                "tipo_doc": "Tipo",
                "folio": "Folio",
                "neto": "Neto",
                "iva": "IVA",
                "total": "Total",
                "cuenta_codigo": "Cuenta",
                "cuenta_origen": "Origen cuenta",
                "observaciones": "Observaciones",
            }
        )

        st.dataframe(mostrar, use_container_width=True, hide_index=True)

        st.divider()
        st.subheader("Revisión y asignación de cuentas")

        opciones = cuentas_imputables(conn)
        etiquetas = opciones["etiqueta"].tolist()

        for i in range(len(df)):
            estado = df.loc[i, "estado"]
            if estado.startswith("🔁") or estado.startswith("❌") or estado.startswith("⚠️"):
                continue

            cuenta_actual = df.loc[i, "cuenta_codigo"]
            if cuenta_actual in opciones["codigo"].values:
                indice = opciones["codigo"].tolist().index(cuenta_actual)
            else:
                indice = 0

            nueva = st.selectbox(
                f"{df.loc[i, 'fecha_doc']} | {df.loc[i, 'razon_social']} | Doc. {df.loc[i, 'folio']}",
                etiquetas,
                index=indice,
                key=f"compra_cta_{i}"
            )

            codigo = nueva.split(" - ", 1)[0]
            df.loc[i, "cuenta_codigo"] = codigo

        st.session_state["rcv_compras"] = df

        validos = df[df["estado"].isin(["🟢 Nuevo", "🟡 Revisar cuenta"])].copy()

        st.divider()

        if not validos.empty:
            st.warning(f"{len(validos)} documento(s) listos para contabilizar.")

            if st.button("✅ CONTABILIZAR COMPRAS", type="primary"):
                try:
                    resultado = contabilizar_rcv(conn, "compras", validos)
                    st.success(f"Se contabilizaron {resultado['documentos']} documentos.")
                    del st.session_state["rcv_compras"]
                except Exception as e:
                    st.error(f"No se contabilizó el lote: {e}")


# ============================================================
# RCV VENTAS
# ============================================================

elif menu == "📤 RCV Ventas":

    st.title("📤 Registro de Ventas - SII")

    archivo = st.file_uploader(
        "Cargar RCV de Ventas",
        type=["csv"],
        key="rcv_ventas_file"
    )

    if archivo:
        try:
            df_original = leer_archivo_tabular(archivo)
            df = normalizar_rcv(df_original, "ventas")
            df = preparar_documentos(conn, df, "ventas")

            st.session_state["rcv_ventas"] = df
            st.success(f"{len(df):,} documentos encontrados.")
        except Exception as e:
            st.error(f"Error: {e}")

    if "rcv_ventas" in st.session_state and isinstance(st.session_state["rcv_ventas"], pd.DataFrame):

        df = st.session_state["rcv_ventas"].copy()

        # Criterio corregido considerando el signo (-1 para NC)
        total_v = (df["total"] * df["signo"]).sum()
        neto_v = (df["neto"] * df["signo"]).sum()
        iva_v = (df["iva"] * df["signo"]).sum()

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Documentos", len(df))
        c2.metric("Neto", money(neto_v))
        c3.metric("IVA", money(iva_v))
        c4.metric("Total", money(total_v))

        st.divider()
        st.subheader("Bandeja de revisión")

        mostrar = df[
            [
                "estado",
                "fecha_doc",
                "rut",
                "razon_social",
                "tipo_doc",
                "folio",
                "neto",
                "iva",
                "total",
                "cuenta_codigo",
                "cuenta_origen",
                "observaciones",
            ]
        ].rename(
            columns={
                "estado": "Estado",
                "fecha_doc": "Fecha",
                "rut": "RUT",
                "razon_social": "Cliente",
                "tipo_doc": "Tipo",
                "folio": "Folio",
                "neto": "Neto",
                "iva": "IVA",
                "total": "Total",
                "cuenta_codigo": "Cuenta",
                "cuenta_origen": "Origen cuenta",
                "observaciones": "Observaciones",
            }
        )

        st.dataframe(mostrar, use_container_width=True, hide_index=True)

        st.subheader("Asignación de cuentas de ingreso")

        opciones = cuentas_imputables(conn)
        etiquetas = opciones["etiqueta"].tolist()

        for i in range(len(df)):
            estado = df.loc[i, "estado"]
            if estado.startswith("🔁") or estado.startswith("❌") or estado.startswith("⚠️"):
                continue

            actual = df.loc[i, "cuenta_codigo"]
            if actual in opciones["codigo"].values:
                indice = opciones["codigo"].tolist().index(actual)
            else:
                indice = 0

            nueva = st.selectbox(
                f"{df.loc[i, 'fecha_doc']} | {df.loc[i, 'razon_social']} | Doc. {df.loc[i, 'folio']}",
                etiquetas,
                index=indice,
                key=f"venta_cta_{i}"
            )

            df.loc[i, "cuenta_codigo"] = nueva.split(" - ", 1)[0]

        st.session_state["rcv_ventas"] = df

        validos = df[df["estado"].isin(["🟢 Nuevo", "🟡 Revisar cuenta"])].copy()

        if not validos.empty:
            if st.button("✅ CONTABILIZAR VENTAS", type="primary"):
                try:
                    resultado = contabilizar_rcv(conn, "ventas", validos)
                    st.success(f"Se contabilizaron {resultado['documentos']} documentos.")
                    del st.session_state["rcv_ventas"]
                except Exception as e:
                    st.error(f"No se contabilizó el lote: {e}")


# ============================================================
# ASIENTOS MANUALES Y SALDOS INICIALES
# ============================================================

elif menu == "✍️ Asientos y Saldos":

    st.title("✍️ Asientos Manuales y Saldos Iniciales")
    st.info(
        """
        Sube una matriz en Excel (CSV) para registrar asientos manuales o cargar los saldos iniciales de tu plan de cuentas.
        Columnas requeridas: **fecha, codigo_cuenta, debe, haber, glosa** (Opcional: **asiento, centro_costo**).
        """
    )

    df_modelo_asiento = pd.DataFrame([
        {"fecha": "2026-01-01", "codigo_cuenta": "1.1.01", "debe": 500000.0, "haber": 0.0, "glosa": "Saldo inicial Caja", "asiento": 1, "centro_costo": "General / Ninguno"},
        {"fecha": "2026-01-01", "codigo_cuenta": "3.1.01", "debe": 0.0, "haber": 500000.0, "glosa": "Saldo inicial Capital", "asiento": 1, "centro_costo": "General / Ninguno"}
    ])
    csv_modelo_asiento = df_modelo_asiento.to_csv(index=False, sep=";").encode("utf-8-sig")

    st.download_button(
        label="📥 Descargar Plantilla de Asientos y Saldos",
        data=csv_modelo_asiento,
        file_name="plantilla_asientos_saldos.csv",
        mime="text/csv",
        type="secondary"
    )

    st.divider()

    tipo_carga = st.radio("Seleccione el origen del lote", ["Saldo inicial", "Asiento manual"])
    archivo_asiento = st.file_uploader("Adjuntar matriz rellenada", type=["csv"], key="subir_asientos")

    if archivo_asiento:
        try:
            df = leer_csv(archivo_asiento)
            df.columns = [str(c).strip().lower() for c in df.columns]

            obligatorias = ["fecha", "codigo_cuenta", "debe", "haber", "glosa"]
            faltantes = [c for c in obligatorias if c not in df.columns]

            if faltantes:
                st.error("Faltan columnas obligatorias: " + ", ".join(faltantes))
            else:
                plan = Plan(conn)
                resultado = pd.DataFrame()

                resultado["fecha"] = df["fecha"].apply(fecha_iso)
                resultado["cuenta_original"] = df["codigo_cuenta"].astype(str).str.strip()

                resuelto = resultado["cuenta_original"].apply(plan.resolver)
                resultado["codigo"] = resuelto.apply(lambda x: x[0] if x else None)
                resultado["cuenta"] = resuelto.apply(lambda x: x[1] if x else None)
                resultado["debe"] = df["debe"].apply(numero)
                resultado["haber"] = df["haber"].apply(numero)
                resultado["glosa"] = df["glosa"].fillna("").astype(str)

                resultado["centro_costo"] = df["centro_costo"].fillna("General / Ninguno") if "centro_costo" in df.columns else "General / Ninguno"
                resultado["asiento"] = pd.to_numeric(df["asiento"], errors="coerce") if "asiento" in df.columns else 1

                errores = []
                for i, fila in resultado.iterrows():
                    if not fila["fecha"]:
                        errores.append(f"Línea {i+2}: fecha inválida.")
                    if not fila["codigo"]:
                        errores.append(f"Línea {i+2}: cuenta '{fila['cuenta_original']}' no encontrada en el plan.")
                    if fila["debe"] > 0 and fila["haber"] > 0:
                        errores.append(f"Línea {i+2}: Debe y Haber simultáneos.")
                    if fila["debe"] == 0 and fila["haber"] == 0:
                        errores.append(f"Línea {i+2}: Debe y Haber están en cero.")

                for asiento_id, grupo in resultado.groupby("asiento"):
                    if abs(grupo["debe"].sum() - grupo["haber"].sum()) > 0.01:
                        errores.append(f"Asiento {asiento_id}: descuadrado (Debe={grupo['debe'].sum()}, Haber={grupo['haber'].sum()}).")

                if errores:
                    st.error("Se encontraron errores en la matriz:\n\n" + "\n".join(errores[:30]))
                else:
                    st.success("¡Matriz validada y cuadrada correctamente!")
                    st.dataframe(resultado, use_container_width=True, hide_index=True)

                    if st.button("✅ REGISTRAR EN LIBRO DIARIO", type="primary"):
                        prefix = "SALDO-INI-" if tipo_carga == "Saldo inicial" else "ASIENTOS-MAN-"
                        lote = prefix + datetime.now().strftime("%Y%m%d-%H%M%S")
                        cur = conn.cursor()
                        base = siguiente_asiento(conn)

                        mapa_asientos = {
                            n: i + 1
                            for i, n in enumerate(sorted(resultado["asiento"].unique()))
                        }

                        try:
                            for fila in resultado.itertuples():
                                asiento = base + mapa_asientos[fila.asiento]
                                cur.execute(
                                    """
                                    INSERT INTO libro_diario
                                    (
                                        fecha,
                                        cuenta,
                                        debe,
                                        haber,
                                        glosa,
                                        centro_costo,
                                        codigo_cuenta,
                                        asiento_id,
                                        lote_id,
                                        origen
                                    )
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                    """,
                                    (
                                        fila.fecha,
                                        fila.cuenta,
                                        fila.debe,
                                        fila.haber,
                                        fila.glosa,
                                        fila.centro_costo,
                                        fila.codigo,
                                        asiento,
                                        lote,
                                        tipo_carga
                                    )
                                )

                            conn.commit()
                            st.success(f"¡Registrado con éxito! Lote generado: {lote}")
                        except Exception as e:
                            conn.rollback()
                            st.error(f"Error al guardar: {e}")

        except Exception as e:
            st.error(f"Error leyendo el archivo: {e}")


# ============================================================
# CLIENTES
# ============================================================

elif menu == "👥 Clientes":

    st.title("👥 Clientes")

    pestañas = st.tabs(["Listado", "Estado de cuenta", "Nuevo cliente"])

    with pestañas[0]:
        df = pd.read_sql_query(
            """
            SELECT
                id,
                rut AS RUT,
                COALESCE(
                    NULLIF(razon_social, ''),
                    nombre
                ) AS Cliente,
                email AS Email,
                telefono AS Teléfono,
                cuenta_defecto AS Cuenta
            FROM clientes
            ORDER BY Cliente
            """,
            conn
        )
        st.dataframe(formatear_montos_df(df), use_container_width=True, hide_index=True)

    with pestañas[1]:
        clientes = conn.execute(
            """
            SELECT
                id,
                rut,
                COALESCE(
                    NULLIF(razon_social, ''),
                    nombre
                ) AS nombre
            FROM clientes
            ORDER BY nombre
            """
        ).fetchall()

        if clientes:
            opciones = {f"{x['rut']} - {x['nombre']}": x["id"] for x in clientes}
            seleccionado = st.selectbox("Cliente", list(opciones.keys()))
            cliente_id = opciones[seleccionado]

            df = estado_cuenta_cliente(conn, cliente_id)

            if df.empty:
                st.info("El cliente no tiene movimientos.")
            else:
                cargo = df["cargo"].sum()
                abono = df["abono"].sum()
                saldo = df.iloc[-1]["saldo"]

                c1, c2, c3 = st.columns(3)
                c1.metric("Facturado", money(cargo))
                c2.metric("Pagado", money(abono))
                c3.metric("Saldo", money(saldo))

                mostrar = df[
                    [
                        "fecha",
                        "Documento",
                        "glosa",
                        "cargo",
                        "abono",
                        "saldo",
                    ]
                ].rename(
                    columns={
                        "fecha": "Fecha",
                        "Documento": "Documento",
                        "glosa": "Glosa",
                        "cargo": "Cargo",
                        "abono": "Abono",
                        "saldo": "Saldo",
                    }
                )

                st.dataframe(mostrar, use_container_width=True, hide_index=True)
                filas_pdf=[[r.Fecha,r.Documento,r.Glosa,money(r.Cargo),money(r.Abono),money(r.Saldo)] for r in mostrar.itertuples(index=False)]
                pdf_ec=nomina_pdf("Estado de Cuenta de Cliente",seleccionado,["Fecha","Documento","Glosa","Cargo","Abono","Saldo"],filas_pdf,["","","TOTALES",money(cargo),money(abono),money(saldo)])
                st.download_button("🖨️ Imprimir / PDF estado de cuenta",pdf_ec,f"estado_cuenta_cliente_{cliente_id}.pdf","application/pdf",key=f"pdf_cliente_{cliente_id}")

    with pestañas[2]:
        with st.form("nuevo_cliente"):
            rut = st.text_input("RUT")
            nombre = st.text_input("Razón social")
            email = st.text_input("Email")
            telefono = st.text_input("Teléfono")

            if st.form_submit_button("Guardar cliente"):
                if not validar_rut(rut):
                    st.error("RUT inválido.")
                elif not nombre.strip():
                    st.error("Debe indicar razón social.")
                else:
                    try:
                        conn.execute(
                            """
                            INSERT INTO clientes
                            (
                                rut,
                                nombre,
                                razon_social,
                                email,
                                telefono,
                                activo,
                                fecha_creacion
                            )
                            VALUES (?, ?, ?, ?, ?, 1, ?)
                            """,
                            (
                                normalizar_rut(rut),
                                nombre,
                                nombre,
                                email,
                                telefono,
                                datetime.now().isoformat()
                            )
                        )
                        conn.commit()
                        st.success("Cliente creado.")
                    except Exception as e:
                        st.error(str(e))


# ============================================================
# PROVEEDORES
# ============================================================

elif menu == "🏢 Proveedores":

    st.title("🏢 Proveedores")

    pestañas = st.tabs(["Listado", "Estado de cuenta", "Nuevo proveedor"])

    with pestañas[0]:
        df = pd.read_sql_query(
            """
            SELECT
                id,
                rut AS RUT,
                COALESCE(
                    NULLIF(razon_social, ''),
                    nombre
                ) AS Proveedor,
                email AS Email,
                telefono AS Teléfono,
                cuenta_defecto AS Cuenta
            FROM proveedores
            ORDER BY Proveedor
            """,
            conn
        )
        st.dataframe(formatear_montos_df(df), use_container_width=True, hide_index=True)

    with pestañas[1]:
        proveedores = conn.execute(
            """
            SELECT
                id,
                rut,
                COALESCE(
                    NULLIF(razon_social, ''),
                    nombre
                ) AS nombre
            FROM proveedores
            ORDER BY nombre
            """
        ).fetchall()

        if proveedores:
            opciones = {f"{x['rut']} - {x['nombre']}": x["id"] for x in proveedores}
            seleccionado = st.selectbox("Proveedor", list(opciones.keys()))
            proveedor_id = opciones[seleccionado]

            df = estado_cuenta_proveedor(conn, proveedor_id)

            if df.empty:
                st.info("El proveedor no tiene movimientos.")
            else:
                cargo = df["cargo"].sum()
                abono = df["abono"].sum()
                saldo = df.iloc[-1]["saldo"]

                c1, c2, c3 = st.columns(3)
                c1.metric("Compras", money(cargo))
                c2.metric("Pagado", money(abono))
                c3.metric("Saldo", money(saldo))

                mostrar_prov=df[["fecha","Documento","glosa","cargo","abono","saldo"]].copy()
                st.dataframe(mostrar_prov,use_container_width=True,hide_index=True)
                filas_pdf=[[r.fecha,r.Documento,r.glosa,money(r.cargo),money(r.abono),money(r.saldo)] for r in mostrar_prov.itertuples(index=False)]
                pdf_ec=nomina_pdf("Estado de Cuenta de Proveedor",seleccionado,["Fecha","Documento","Glosa","Cargo","Abono","Saldo"],filas_pdf,["","","TOTALES",money(cargo),money(abono),money(saldo)])
                st.download_button("🖨️ Imprimir / PDF estado de cuenta",pdf_ec,f"estado_cuenta_proveedor_{proveedor_id}.pdf","application/pdf",key=f"pdf_proveedor_{proveedor_id}")

    with pestañas[2]:
        with st.form("nuevo_proveedor"):
            rut = st.text_input("RUT")
            nombre = st.text_input("Razón social")
            email = st.text_input("Email")
            telefono = st.text_input("Teléfono")

            if st.form_submit_button("Guardar proveedor"):
                if not validar_rut(rut):
                    st.error("RUT inválido.")
                elif not nombre.strip():
                    st.error("Debe indicar razón social.")
                else:
                    try:
                        conn.execute(
                            """
                            INSERT INTO proveedores
                            (
                                rut,
                                nombre,
                                razon_social,
                                email,
                                telefono,
                                activo,
                                fecha_creacion
                            )
                            VALUES (?, ?, ?, ?, ?, 1, ?)
                            """,
                            (
                                normalizar_rut(rut),
                                nombre,
                                nombre,
                                email,
                                telefono,
                                datetime.now().isoformat()
                            )
                        )
                        conn.commit()
                        st.success("Proveedor creado.")
                    except Exception as e:
                        st.error(str(e))


# ============================================================
# PAGOS
# ============================================================

elif menu == "💵 Pagos":

    st.title("💵 Pagos y cobranzas")

    pestañas = st.tabs(["Cobranza clientes", "Pago proveedores"])
    cuentas = cuentas_imputables(conn)
    cuentas_banco = cuentas[cuentas["codigo"].str.startswith("1.1.02")]

    with pestañas[0]:
        clientes = conn.execute(
            """
            SELECT id, rut,
            COALESCE(
                NULLIF(razon_social, ''),
                nombre
            ) AS nombre
            FROM clientes
            ORDER BY nombre
            """
        ).fetchall()

        if not clientes:
            st.info("No hay clientes registrados. Debe crear al menos un cliente para registrar cobranzas.")
        else:
            opciones = {f"{x['rut']} - {x['nombre']}": x["id"] for x in clientes}

            with st.form("pago_cliente"):
                seleccionado = st.selectbox("Cliente", list(opciones.keys()))
                fecha_pago = st.date_input("Fecha", date.today())
                monto_pago = st.number_input("Monto", min_value=0.0, step=1000.0,format='%.0f')
                medio = st.selectbox("Medio de pago", ["Transferencia", "Cheque", "Efectivo", "Tarjeta", "Otro"])

                if cuentas_banco.empty:
                    st.warning("No existen cuentas bajo 1.1.02.")
                    cuenta_banco = None
                else:
                    opciones_banco = dict(zip(cuentas_banco["etiqueta"], cuentas_banco["codigo"]))
                    cuenta_banco_label = st.selectbox("Cuenta bancaria", list(opciones_banco.keys()))
                    cuenta_banco = opciones_banco[cuenta_banco_label]

                glosa = st.text_input("Glosa")
                guardar = st.form_submit_button("Registrar cobranza")

                if guardar:
                    try:
                        lote = registrar_pago_cliente(
                            conn,
                            opciones[seleccionado],
                            fecha_pago.strftime("%Y-%m-%d"),
                            monto_pago,
                            medio,
                            cuenta_banco,
                            glosa
                        )
                        st.success(f"Pago registrado. Lote: {lote}")
                    except Exception as e:
                        st.error(str(e))

    with pestañas[1]:
        proveedores = conn.execute(
            """
            SELECT id, rut,
            COALESCE(
                NULLIF(razon_social, ''),
                nombre
            ) AS nombre
            FROM proveedores
            ORDER BY nombre
            """
        ).fetchall()

        if not proveedores:
            st.info("No hay proveedores registrados. Debe crear al menos un proveedor para registrar pagos.")
        else:
            opciones = {f"{x['rut']} - {x['nombre']}": x["id"] for x in proveedores}

            with st.form("pago_proveedor"):
                seleccionado = st.selectbox("Proveedor", list(opciones.keys()))
                fecha_pago = st.date_input("Fecha", date.today(), key="fecha_pago_proveedor")
                monto_pago = st.number_input("Monto", min_value=0.0, step=1000.0, key="monto_pago_proveedor")
                medio = st.selectbox("Medio de pago", ["Transferencia", "Cheque", "Efectivo", "Tarjeta", "Otro"], key="medio_proveedor")

                if cuentas_banco.empty:
                    st.warning("No existen cuentas bajo 1.1.02.")
                    cuenta_banco = None
                else:
                    opciones_banco = dict(zip(cuentas_banco["etiqueta"], cuentas_banco["codigo"]))
                    cuenta_label = st.selectbox("Cuenta bancaria", list(opciones_banco.keys()), key="cuenta_proveedor")
                    cuenta_banco = opciones_banco[cuenta_label]

                glosa = st.text_input("Glosa", key="glosa_proveedor")
                guardar_proveedor = st.form_submit_button("Registrar pago")

                if guardar_proveedor:
                    try:
                        lote = registrar_pago_proveedor(
                            conn,
                            opciones[seleccionado],
                            fecha_pago.strftime("%Y-%m-%d"),
                            monto_pago,
                            medio,
                            cuenta_banco,
                            glosa
                        )
                        st.success(f"Pago registrado. Lote: {lote}")
                    except Exception as e:
                        st.error(str(e))


# ============================================================
# LIBRO DIARIO
# ============================================================

elif menu == "📒 Libro Diario":

    st.title("📒 Libro Diario")

    df = pd.read_sql_query(
        """
        SELECT
            fecha AS Fecha,
            asiento_id AS Asiento,
            codigo_cuenta AS Código,
            cuenta AS Cuenta,
            debe AS Debe,
            haber AS Haber,
            glosa AS Glosa,
            origen AS Origen
        FROM libro_diario
        ORDER BY
            fecha DESC,
            asiento_id DESC,
            id DESC
        """,
        conn
    )

    st.dataframe(formatear_montos_df(df), use_container_width=True, hide_index=True)


# ============================================================
# MAYOR
# ============================================================

elif menu == "📚 Mayor":

    st.title("📚 Libro Mayor")

    cuentas = cuentas_imputables(conn)
    opciones = dict(zip(cuentas["etiqueta"], cuentas["codigo"]))

    seleccion = st.selectbox("Cuenta", list(opciones.keys()))
    codigo = opciones[seleccion]

    df = obtener_mayor(conn, codigo)

    if df.empty:
        st.info("La cuenta no tiene movimientos.")
    else:
        saldo = df.iloc[-1]["Saldo"]
        st.metric("Saldo", money(saldo))
        st.dataframe(formatear_montos_df(df), use_container_width=True, hide_index=True)


# ============================================================
# BALANCE DE COMPROBACIÓN
# ============================================================

elif menu == "⚖️ Balance de Comprobación":

    st.title("⚖ Balance de Comprobación")

    col1, col2 = st.columns(2)

    with col1:
        desde = st.date_input("Desde", date(date.today().year, 1, 1))

    with col2:
        hasta = st.date_input("Hasta", date.today())

    df = balance_comprobacion(
        conn,
        desde.strftime("%Y-%m-%d"),
        hasta.strftime("%Y-%m-%d")
    )

    if not df.empty:
        debe = df["Debe"].sum()
        haber = df["Haber"].sum()

        c1, c2, c3 = st.columns(3)
        c1.metric("Debe", money(debe))
        c2.metric("Haber", money(haber))
        c3.metric("Diferencia", money(debe - haber))

        if abs(debe - haber) < 0.01:
            st.success("🟢 Balance cuadrado.")
        else:
            st.error("🔴 Existe diferencia.")

        st.dataframe(formatear_montos_df(df), use_container_width=True, hide_index=True)


# ============================================================
# CONCILIACIÓN
# ============================================================

elif menu == "📊 Conciliación":

    st.title("📊 Conciliación de auxiliares")

    pestañas = st.tabs(["Clientes", "Proveedores"])

    with pestañas[0]:
        df = conciliacion_clientes(conn)
        if df.empty:
            st.warning("No se pudo determinar la cuenta de clientes.")
        else:
            st.dataframe(formatear_montos_df(df), use_container_width=True, hide_index=True)
            diferencia = df.iloc[0]["Diferencia"]
            if abs(diferencia) < 0.01:
                st.success("🟢 Auxiliar de clientes conciliado.")
            else:
                st.error(f"🔴 Diferencia: {money(diferencia)}")

    with pestañas[1]:
        df = conciliacion_proveedores(conn)
        if df.empty:
            st.warning("No se pudo determinar la cuenta de proveedores.")
        else:
            st.dataframe(formatear_montos_df(df), use_container_width=True, hide_index=True)
            diferencia = df.iloc[0]["Diferencia"]
            if abs(diferencia) < 0.01:
                st.success("🟢 Auxiliar de proveedores conciliado.")
            else:
                st.error(f"🔴 Diferencia: {money(diferencia)}")


# ============================================================
# PLAN DE CUENTAS
# ============================================================

elif menu == "📋 Plan de Cuentas":

    st.title("📋 Plan de Cuentas")

    pestañas = st.tabs(["Plan", "Cuentas de enlace", "Nueva cuenta", "Editar cuenta"])

    with pestañas[0]:
        df = pd.read_sql_query(
            """
            SELECT
                codigo AS Código,
                nombre AS Cuenta,
                categoria AS Categoría,
                tipo AS Tipo,
                padre_codigo AS Padre,
                nivel AS Nivel
            FROM plan_cuentas
            ORDER BY codigo
            """,
            conn
        )
        st.dataframe(formatear_montos_df(df), use_container_width=True, hide_index=True)

    with pestañas[1]:
        roles = cargar_roles(conn)

        for rol, (descripcion, defecto) in ROLES.items():
            actual = roles.get(rol)
            opciones = cuentas_imputables(conn)
            mapa = dict(zip(opciones["etiqueta"], opciones["codigo"]))

            codigo_actual = actual[0] if actual else defecto
            etiquetas = list(mapa.keys())
            seleccionado = None

            for etiqueta in etiquetas:
                if etiqueta.startswith(codigo_actual + " - "):
                    seleccionado = etiqueta
                    break

            if seleccionado is None:
                seleccionado = etiquetas[0]

            nuevo = st.selectbox(
                descripcion,
                etiquetas,
                index=etiquetas.index(seleccionado),
                key=f"rol_{rol}"
            )

            if st.button(f"Guardar {descripcion}", key=f"guardar_rol_{rol}"):
                guardar_rol(conn, rol, mapa[nuevo])
                st.success("Configuración guardada.")

    with pestañas[2]:
        with st.form("nueva_cuenta"):
            codigo = st.text_input("Código")
            nombre = st.text_input("Nombre")
            categoria = st.selectbox("Categoría", ["Activo", "Pasivo", "Patrimonio", "Nominal"])
            tipo = st.selectbox("Tipo", ["Activo", "Pasivo", "Patrimonio", "Ingresos", "Gastos"])
            padre = st.text_input("Código padre")
            nivel = st.number_input("Nivel", min_value=1, max_value=10, value=3)

            if st.form_submit_button("Crear cuenta"):
                try:
                    conn.execute(
                        """
                        INSERT INTO plan_cuentas
                        (
                            codigo,
                            nombre,
                            categoria,
                            tipo,
                            padre_codigo,
                            nivel
                        )
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            codigo.strip(),
                            nombre.strip(),
                            categoria,
                            tipo,
                            padre.strip() or None,
                            nivel
                        )
                    )
                    conn.commit()
                    st.success("Cuenta creada.")
                except Exception as e:
                    st.error(str(e))

    with pestañas[3]:
        st.subheader("Editar cuenta existente")
        st.caption("Permite corregir la estructura de una cuenta sin cambiar su código contable ni eliminar sus movimientos.")

        cuentas_editar = pd.read_sql_query(
            """
            SELECT codigo, nombre, categoria, tipo, padre_codigo, nivel
            FROM plan_cuentas
            ORDER BY codigo
            """,
            conn
        )

        if cuentas_editar.empty:
            st.info("No hay cuentas contables para editar.")
        else:
            etiquetas_editar = (cuentas_editar["codigo"] + " - " + cuentas_editar["nombre"]).tolist()
            seleccion_editar = st.selectbox(
                "Cuenta a editar",
                etiquetas_editar,
                key="editar_cuenta_seleccion"
            )
            codigo_editar = seleccion_editar.split(" - ", 1)[0]
            fila_editar = cuentas_editar.loc[cuentas_editar["codigo"] == codigo_editar].iloc[0]

            categorias = ["Activo", "Pasivo", "Patrimonio", "Nominal"]
            tipos = ["Activo", "Pasivo", "Patrimonio", "Ingresos", "Gastos"]

            padres_df = cuentas_editar.loc[cuentas_editar["codigo"] != codigo_editar, ["codigo", "nombre"]].copy()
            opciones_padre = ["Sin cuenta padre"] + (padres_df["codigo"] + " - " + padres_df["nombre"]).tolist()
            padre_actual = fila_editar["padre_codigo"]
            padre_actual = "" if pd.isna(padre_actual) else str(padre_actual).strip()
            indice_padre = 0
            if padre_actual:
                for i, etiqueta in enumerate(opciones_padre):
                    if etiqueta.startswith(padre_actual + " - "):
                        indice_padre = i
                        break

            with st.form("editar_cuenta_form"):
                st.text_input("Código", value=codigo_editar, disabled=True)
                nombre_editar = st.text_input("Nombre", value=str(fila_editar["nombre"] or ""))
                categoria_actual = str(fila_editar["categoria"] or "Activo")
                tipo_actual = str(fila_editar["tipo"] or "Activo")
                categoria_editar = st.selectbox(
                    "Categoría",
                    categorias,
                    index=categorias.index(categoria_actual) if categoria_actual in categorias else 0
                )
                tipo_editar = st.selectbox(
                    "Tipo",
                    tipos,
                    index=tipos.index(tipo_actual) if tipo_actual in tipos else 0
                )
                padre_editar = st.selectbox(
                    "Cuenta padre",
                    opciones_padre,
                    index=indice_padre
                )
                nivel_editar = st.number_input(
                    "Nivel",
                    min_value=1,
                    max_value=10,
                    value=int(fila_editar["nivel"] or 1),
                    step=1
                )

                guardar_edicion = st.form_submit_button("Guardar cambios", type="primary")

            if guardar_edicion:
                nuevo_padre = None if padre_editar == "Sin cuenta padre" else padre_editar.split(" - ", 1)[0]
                try:
                    if nuevo_padre == codigo_editar:
                        raise ValueError("Una cuenta no puede ser padre de sí misma.")

                    ancestro = nuevo_padre
                    visitados = set()
                    while ancestro:
                        if ancestro == codigo_editar:
                            raise ValueError("La cuenta padre seleccionada generaría una jerarquía circular.")
                        if ancestro in visitados:
                            break
                        visitados.add(ancestro)
                        row_padre = conn.execute(
                            "SELECT padre_codigo FROM plan_cuentas WHERE codigo = ?",
                            (ancestro,)
                        ).fetchone()
                        if not row_padre:
                            break
                        ancestro = row_padre[0]

                    conn.execute(
                        """
                        UPDATE plan_cuentas
                        SET nombre = ?, categoria = ?, tipo = ?, padre_codigo = ?, nivel = ?
                        WHERE codigo = ?
                        """,
                        (
                            nombre_editar.strip(),
                            categoria_editar,
                            tipo_editar,
                            nuevo_padre,
                            int(nivel_editar),
                            codigo_editar
                        )
                    )
                    conn.commit()
                    st.success(f"Cuenta {codigo_editar} actualizada correctamente.")
                    st.rerun()
                except Exception as e:
                    conn.rollback()
                    st.error(f"No se pudo actualizar la cuenta: {e}")


# ============================================================
# REGLAS CONTABLES
# ============================================================

elif menu == "⚙️ Reglas Contables":

    st.title("⚙️ Reglas de clasificación contable")
    st.info(
        """
        Las reglas tienen prioridad sobre la cuenta habitual del cliente/proveedor. 
        Esto permite que el SGCI aprenda la clasificación contable de cada empresa.
        """
    )

    cuentas = cuentas_imputables(conn)
    mapa_cuentas = dict(zip(cuentas["etiqueta"], cuentas["codigo"]))

    with st.form("nueva_regla"):
        tipo = st.selectbox("Tipo", ["compras", "ventas"])
        rut = st.text_input("RUT específico (opcional)")
        patron = st.text_input("Texto que debe contener la razón social (opcional)")
        tipo_doc = st.number_input("Tipo de documento (0 = cualquiera)", min_value=0, max_value=999, value=0)
        cuenta_label = st.selectbox("Cuenta contable", list(mapa_cuentas.keys()))
        prioridad = st.number_input("Prioridad", min_value=1, max_value=1000, value=100)
        descripcion = st.text_input("Descripción")

        if st.form_submit_button("Guardar regla"):
            guardar_regla(
                conn,
                tipo,
                rut,
                patron,
                None if tipo_doc == 0 else tipo_doc,
                mapa_cuentas[cuenta_label],
                prioridad,
                descripcion
            )
            st.success("Regla guardada.")

    st.divider()
    st.subheader("Reglas configuradas actualmente")

    reglas = pd.read_sql_query(
        """
        SELECT
            r.id AS ID,
            r.tipo AS Tipo,
            r.rut AS RUT,
            r.patron AS Patrón,
            r.tipo_doc AS Tipo_Doc,
            r.codigo_cuenta AS Cuenta,
            p.nombre AS Nombre_Cuenta,
            r.prioridad AS Prioridad,
            r.activa AS Activa,
            r.descripcion AS Descripción
        FROM reglas_contables r
        LEFT JOIN plan_cuentas p
            ON p.codigo = r.codigo_cuenta
        ORDER BY
            r.tipo,
            r.prioridad DESC
        """,
        conn
    )

    if reglas.empty:
        st.info("No hay reglas contables registradas todavía.")
    else:
        st.dataframe(reglas, use_container_width=True, hide_index=True)


# ============================================================
# LOTES
# ============================================================

elif menu == "📦 Lotes":

    st.title("📦 Lotes de contabilización")
    df = listar_lotes(conn)

    if df.empty:
        st.info("No existen lotes.")
    else:
        st.dataframe(formatear_montos_df(df), use_container_width=True, hide_index=True)
        st.divider()

        lote = st.selectbox("Seleccionar lote", df["Lote"].tolist())
        st.warning(
            "Deshacer un lote elimina los movimientos "
            "contables y documentos asociados a ese lote."
        )

        if st.button("🗑️ DESHACER LOTE", type="secondary"):
            try:
                resultado = deshacer_lote(conn, lote)
                st.success(f"Lote eliminado: {resultado}")
            except Exception as e:
                st.error(f"No fue posible eliminar el lote: {e}")


# ============================================================
# MATRIZ CONTABLE
# ============================================================

elif menu == "🧰 Matriz Contable":

    st.title("🧰 Importación de matriz contable")
    st.info(
        """
        Formato esperado:
        fecha | cuenta | debe | haber | glosa

        Opcionales:
        asiento | centro_costo
        """
    )

    archivo = st.file_uploader("Cargar matriz contable", type=["csv", "xlsx", "xls"], key="matriz")

    if archivo:
        try:
            df = leer_archivo_tabular(archivo)
            df.columns = [str(c).strip().lower() for c in df.columns]

            obligatorias = ["fecha", "cuenta", "debe", "haber", "glosa"]
            faltantes = [c for c in obligatorias if c not in df.columns]

            if faltantes:
                st.error("Faltan columnas: " + ", ".join(faltantes))
            else:
                plan = Plan(conn)
                resultado = pd.DataFrame()

                resultado["fecha"] = df["fecha"].apply(fecha_iso)
                resultado["cuenta_original"] = df["cuenta"].astype(str).str.strip()

                resuelto = resultado["cuenta_original"].apply(plan.resolver)

                resultado["codigo"] = resuelto.apply(lambda x: x[0] if x else None)
                resultado["cuenta"] = resuelto.apply(lambda x: x[1] if x else None)
                resultado["debe"] = df["debe"].apply(numero)
                resultado["haber"] = df["haber"].apply(numero)
                resultado["glosa"] = df["glosa"].fillna("").astype(str)

                if "centro_costo" in df.columns:
                    resultado["centro_costo"] = df["centro_costo"].fillna("General / Ninguno")
                else:
                    resultado["centro_costo"] = "General / Ninguno"

                if "asiento" in df.columns:
                    resultado["asiento"] = pd.to_numeric(df["asiento"], errors="coerce")
                else:
                    resultado["asiento"] = 1

                errores = []

                for i, fila in resultado.iterrows():
                    if not fila["fecha"]:
                        errores.append(f"Línea {i+2}: fecha inválida.")
                    if not fila["codigo"]:
                        errores.append(f"Línea {i+2}: cuenta '{fila['cuenta_original']}' no encontrada.")
                    if fila["debe"] > 0 and fila["haber"] > 0:
                        errores.append(f"Línea {i+2}: Debe y Haber simultáneos.")
                    if fila["debe"] == 0 and fila["haber"] == 0:
                        errores.append(f"Línea {i+2}: Debe y Haber están en cero.")

                for asiento_id, grupo in resultado.groupby("asiento"):
                    if abs(grupo["debe"].sum() - grupo["haber"].sum()) > 0.01:
                        errores.append(f"Asiento {asiento_id}: descuadrado.")

                if errores:
                    st.error("\n".join(errores[:30]))
                else:
                    st.success("Matriz validada correctamente.")
                    st.dataframe(resultado, use_container_width=True, hide_index=True)

                    if st.button("✅ IMPORTAR MATRIZ", type="primary"):
                        lote = "MATRIZ-" + datetime.now().strftime("%Y%m%d-%H%M%S")
                        cur = conn.cursor()
                        base = siguiente_asiento(conn)

                        mapa_asientos = {
                            n: i + 1
                            for i, n in enumerate(sorted(resultado["asiento"].unique()))
                        }

                        try:
                            for fila in resultado.itertuples():
                                asiento = base + mapa_asientos[fila.asiento]

                                cur.execute(
                                    """
                                    INSERT INTO libro_diario
                                    (
                                        fecha,
                                        cuenta,
                                        debe,
                                        haber,
                                        glosa,
                                        centro_costo,
                                        codigo_cuenta,
                                        asiento_id,
                                        lote_id,
                                        origen
                                    )
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                    """,
                                    (
                                        fila.fecha,
                                        fila.cuenta,
                                        fila.debe,
                                        fila.haber,
                                        fila.glosa,
                                        fila.centro_costo,
                                        fila.codigo,
                                        asiento,
                                        lote,
                                        "Matriz contable"
                                    )
                                )

                            conn.commit()
                            st.success(f"Matriz importada. Lote: {lote}")
                        except Exception as e:
                            conn.rollback()
                            st.error(f"Error: {e}")

        except Exception as e:
            st.error(f"Error leyendo matriz: {e}")


# ============================================================
# PIE
# ============================================================

st.sidebar.divider()
st.sidebar.caption("SGCI • Sistema de Gestión Contable Integral")
st.sidebar.caption("Motor contable + auxiliares + RCV + conciliación")

conn.close()

# CONTEM: componente extraído del app.py original; ejecución secuencial compartida.
def sgci_respaldo_consistente(conn):
    """Copia SQLite consistente, incluidos cambios confirmados todavía en WAL."""
    if not sgci_es_propietario():
        raise PermissionError('Solo el administrador principal puede descargar la base de datos.')
    if conn.in_transaction:
        raise RuntimeError('Guarda o revierte la operación pendiente antes de generar el respaldo.')
    import sqlite3 as _sqlite3
    from contextlib import closing as _cerrar
    from pathlib import Path as _Ruta
    from tempfile import TemporaryDirectory as _Temporal
    with _Temporal(prefix='contem_respaldo_') as carpeta:
        destino = _Ruta(carpeta)/'respaldo.db'
        with _cerrar(_sqlite3.connect(destino)) as copia:
            conn.backup(copia)
            # Un único archivo descargable, independiente de archivos WAL/SHM.
            copia.execute('PRAGMA journal_mode=DELETE')
            if copia.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('No se pudo verificar la integridad del respaldo.')
        return destino.read_bytes()


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


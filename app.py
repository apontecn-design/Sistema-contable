# -*- coding: utf-8 -*-
"""
contabilidad.py
Motor de contabilización del Sistema Contable.
 
Aquí vive la lógica que conecta las cargas masivas (RCV del SII y matrices de
asientos) con el Plan de Cuentas y el Libro Diario. No usa Streamlit, así que
se puede probar por separado.
"""
import io
import sqlite3
from datetime import datetime
 
import pandas as pd
 
# ---------------------------------------------------------------------------
# Cuentas de enlace: qué cuenta del plan usa cada función del sistema.
# (descripción, código por defecto). Se pueden cambiar desde Plan de Cuentas.
# ---------------------------------------------------------------------------
ROLES = {
    "clientes": ("Clientes por cobrar (contrapartida de las ventas)", "1.1.03.01"),
    "iva_credito": ("IVA Crédito Fiscal (compras)", "1.1.03.02"),
    "proveedores": ("Proveedores por pagar (contrapartida de las compras)", "2.1.01.01"),
    "iva_debito": ("IVA Débito Fiscal (ventas)", "2.1.01.02"),
    "gasto_defecto": ("Gasto por defecto (proveedor sin cuenta habitual)", "5.2.01"),
    "ingreso_defecto": ("Ingreso por defecto (cliente sin cuenta habitual)", "4.1.01"),
    "activo_fijo": ("Activo fijo (compras de activo fijo)", "1.2.01.01"),
}
 
NOMBRES_DOC = {
    30: "Factura",
    32: "Factura no afecta",
    33: "Factura electrónica",
    34: "Factura exenta electrónica",
    55: "Nota de débito",
    56: "Nota de débito electrónica",
    60: "Nota de crédito",
    61: "Nota de crédito electrónica",
}
DOC_NORMALES = {30, 32, 33, 34, 55, 56}
DOC_NOTA_CREDITO = {60, 61}
DOC_SOPORTADOS = DOC_NORMALES | DOC_NOTA_CREDITO
 
 
def nombre_doc(tipo):
    try:
        t = int(tipo)
    except (TypeError, ValueError):
        return str(tipo)
    return NOMBRES_DOC.get(t, f"Documento tipo {t}")
 
 
# ---------------------------------------------------------------------------
# Base de datos: columnas nuevas, tabla de enlaces, índices y trigger
# ---------------------------------------------------------------------------
def _agregar_columna(conn, tabla, columna, tipo):
    cols = [f[1] for f in conn.execute(f"PRAGMA table_info({tabla})")]
    if columna not in cols:
        conn.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {tipo}")
 
 
def migrar_db(conn):
    """Agrega lo necesario a la base existente sin borrar datos. Se puede llamar muchas veces."""
    for col, tipo in (("codigo_cuenta", "TEXT"), ("asiento_id", "INTEGER"),
                      ("lote_id", "TEXT"), ("origen", "TEXT")):
        _agregar_columna(conn, "libro_diario", col, tipo)
    for tabla in ("compras", "ventas"):
        for col, tipo in (("tipo_doc", "INTEGER"), ("folio", "TEXT"), ("lote_id", "TEXT")):
            _agregar_columna(conn, tabla, col, tipo)
    _agregar_columna(conn, "clientes", "cuenta_defecto", "TEXT")
 
    conn.execute("CREATE TABLE IF NOT EXISTS config_cuentas (rol TEXT PRIMARY KEY, codigo TEXT)")
    for rol, (_, codigo) in ROLES.items():
        conn.execute("INSERT OR IGNORE INTO config_cuentas (rol, codigo) VALUES (?, ?)", (rol, codigo))
 
    # La app (módulo Bancos) usa 'Otros Ingresos', que no existía en el plan.
    existe = conn.execute("SELECT 1 FROM plan_cuentas WHERE nombre = 'Otros Ingresos'").fetchone()
    padre = conn.execute("SELECT 1 FROM plan_cuentas WHERE codigo = '4.1'").fetchone()
    if not existe and padre:
        conn.execute("INSERT OR IGNORE INTO plan_cuentas (codigo, nombre, categoria, tipo, padre_codigo, nivel) "
                     "VALUES ('4.1.03', 'Otros Ingresos', 'Nominal', 'Ingresos', '4.1', 3)")
 
    # Un mismo documento no puede registrarse dos veces.
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_compras_doc ON compras (proveedor_id, tipo_doc, folio)")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_ventas_doc ON ventas (tipo_doc, folio)")
 
    # Todo asiento que se guarde solo con el nombre de la cuenta recibe su código automáticamente.
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS trg_libro_diario_codigo
        AFTER INSERT ON libro_diario
        WHEN NEW.codigo_cuenta IS NULL
        BEGIN
            UPDATE libro_diario SET codigo_cuenta = (
                SELECT codigo FROM plan_cuentas WHERE nombre = NEW.cuenta
                ORDER BY LENGTH(codigo) DESC, codigo LIMIT 1)
            WHERE id = NEW.id;
        END
    """)
    conn.execute("""
        UPDATE libro_diario SET codigo_cuenta = (
            SELECT p.codigo FROM plan_cuentas p WHERE p.nombre = libro_diario.cuenta
            ORDER BY LENGTH(p.codigo) DESC, p.codigo LIMIT 1)
        WHERE codigo_cuenta IS NULL
    """)
    conn.commit()
 
 
# ---------------------------------------------------------------------------
# Plan de cuentas
# ---------------------------------------------------------------------------
class Plan:
    """Lee el plan de cuentas. Una cuenta es imputable si no tiene cuentas hijas."""
 
    def __init__(self, conn):
        df = pd.read_sql_query(
            "SELECT codigo, nombre, categoria, tipo, padre_codigo, nivel FROM plan_cuentas ORDER BY codigo", conn)
        df["codigo"] = df["codigo"].astype(str)
        padres = set(df["padre_codigo"].dropna().astype(str))
        df["imputable"] = ~df["codigo"].isin(padres)
        self.df = df
        self.todos = dict(zip(df["codigo"], df["nombre"]))
        hojas = df[df["imputable"]]
        self.hojas = dict(zip(hojas["codigo"], hojas["nombre"]))
        self.por_nombre = {str(n).strip().lower(): c for c, n in self.hojas.items()}
 
    def resolver(self, texto):
        """Devuelve (codigo, nombre) de una cuenta imputable, o None. Acepta código, nombre o 'código - nombre'."""
        if texto is None or (isinstance(texto, float) and pd.isna(texto)):
            return None
        t = str(texto).strip()
        if not t:
            return None
        if t in self.hojas:
            return t, self.hojas[t]
        if " - " in t:
            c = t.split(" - ", 1)[0].strip()
            if c in self.hojas:
                return c, self.hojas[c]
        c = self.por_nombre.get(t.lower())
        if c:
            return c, self.hojas[c]
        return None
 
 
def cuentas_imputables(conn, tipo=None):
    df = Plan(conn).df
    df = df[df["imputable"]]
    if tipo:
        df = df[df["tipo"] == tipo]
    df = df.copy()
    df["etiqueta"] = df["codigo"] + " - " + df["nombre"]
    return df.reset_index(drop=True)
 
 
def cargar_roles(conn, plan=None):
    """{rol: (codigo, nombre)} — o None si el código configurado no existe en el plan."""
    plan = plan or Plan(conn)
    guardados = dict(conn.execute("SELECT rol, codigo FROM config_cuentas").fetchall())
    roles = {}
    for rol, (_, defecto) in ROLES.items():
        codigo = guardados.get(rol, defecto)
        roles[rol] = (codigo, plan.todos[codigo]) if codigo in plan.todos else None
    return roles
 
 
def guardar_rol(conn, rol, codigo):
    conn.execute("INSERT OR REPLACE INTO config_cuentas (rol, codigo) VALUES (?, ?)", (rol, codigo))
    conn.commit()
 
 
def movimientos_sin_cuenta(conn):
    """Movimientos del Libro Diario cuya cuenta no existe en el plan (no aparecen en los reportes)."""
    return pd.read_sql_query(
        "SELECT cuenta AS Cuenta, COUNT(*) AS Movimientos, SUM(debe) AS Debe, SUM(haber) AS Haber "
        "FROM libro_diario WHERE codigo_cuenta IS NULL GROUP BY cuenta", conn)
 
 
# ---------------------------------------------------------------------------
# Lectura de archivos
# ---------------------------------------------------------------------------
def leer_tabla_csv(datos):
    """Lee un CSV (separador ; , o tab; utf-8 o latin1).
    index_col=False evita que las columnas se corran cuando cada fila termina en ';' (como el RCV del SII)."""
    texto = None
    for enc in ("utf-8-sig", "latin1"):
        try:
            texto = datos.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if not texto or not texto.strip():
        raise ValueError("El archivo está vacío.")
    primera = texto.splitlines()[0]
    sep = max((";", ",", "\t"), key=primera.count)
    df = pd.read_csv(io.StringIO(texto), sep=sep, dtype=str, index_col=False)
    df.columns = [str(c).strip() for c in df.columns]
    return df.dropna(how="all")
 
 
def _col(df, *nombres):
    mapa = {str(c).strip().lower(): c for c in df.columns}
    for n in nombres:
        if n.lower() in mapa:
            return df[mapa[n.lower()]].fillna("").astype(str).str.strip()
    return pd.Series([""] * len(df), index=df.index)
 
 
def _num(serie):
    s = serie.fillna("").astype(str).str.strip()
    s = s.str.replace(r"\.(?=\d{3}(?:\D|$))", "", regex=True).str.replace(",", ".", regex=False)
    return pd.to_numeric(s, errors="coerce").fillna(0.0)
 
 
def _fecha_iso(serie):
    s = serie.fillna("").astype(str).str.strip().str.slice(0, 10)
    iso = pd.to_datetime(s, format="%Y-%m-%d", errors="coerce")
    dmy = pd.to_datetime(s, format="%d/%m/%Y", errors="coerce")
    return iso.fillna(dmy).dt.strftime("%Y-%m-%d")
 
 
def normalizar_rcv(df, tipo):
    """Deja el RCV (compras o ventas) con columnas estándar. tipo: 'compras' | 'ventas'."""
    compras = tipo == "compras"
    col_rut = "RUT Proveedor" if compras else "Rut cliente"
    otra = "Rut cliente" if compras else "RUT Proveedor"
    cols = [str(c).strip().lower() for c in df.columns]
    if col_rut.lower() not in cols:
        if otra.lower() in cols:
            raise ValueError(f"Este archivo parece ser de {'VENTAS' if compras else 'COMPRAS'}, "
                             f"pero elegiste {'Compras' if compras else 'Ventas'}. Cambia el tipo de registro.")
        raise ValueError(f"No encuentro la columna '{col_rut}'. ¿Es el detalle del RCV del SII?")
    for obligatoria in ("Tipo Doc", "Folio", "Fecha Docto", "Monto Total"):
        if obligatoria.lower() not in cols:
            raise ValueError(f"Falta la columna '{obligatoria}' en el archivo.")
 
    out = pd.DataFrame({
        "tipo_doc": pd.to_numeric(_col(df, "Tipo Doc"), errors="coerce"),
        "folio": _col(df, "Folio"),
        "fecha_doc": _fecha_iso(_col(df, "Fecha Docto")),
        "fecha_recepcion": _fecha_iso(_col(df, "Fecha Recepcion", "Fecha Recepción")),
        "rut": _col(df, col_rut).str.upper(),
        "razon_social": _col(df, "Razon Social", "Razón Social").str.replace(r"\s+", " ", regex=True),
        "exento": _num(_col(df, "Monto Exento")),
        "neto": _num(_col(df, "Monto Neto")),
        "iva": _num(_col(df, "Monto IVA Recuperable" if compras else "Monto IVA")),
        "iva_no_rec": _num(_col(df, "Monto Iva No Recuperable")) if compras else 0.0,
        "neto_af": _num(_col(df, "Monto Neto Activo Fijo")) if compras else 0.0,
        "iva_af": _num(_col(df, "IVA Activo Fijo")) if compras else 0.0,
        "iva_uso_comun": _num(_col(df, "IVA uso Comun", "IVA uso Común")) if compras else 0.0,
        "total": _num(_col(df, "Monto Total")),
        "ref_tipo": pd.to_numeric(_col(df, "Tipo Docto. Referencia"), errors="coerce"),
        "ref_folio": _col(df, "Folio Docto. Referencia"),
    })
    out = out[out["tipo_doc"].notna()].reset_index(drop=True)
    if out.empty:
        raise ValueError("No encontré documentos en el archivo.")
    out["tipo_doc"] = out["tipo_doc"].astype(int)
    return out
 
 
# ---------------------------------------------------------------------------
# Preparación: qué se puede contabilizar y con qué cuenta
# ---------------------------------------------------------------------------
def preparar_documentos(conn, docs, tipo):
    """Agrega estado, cuenta sugerida, signo (+1 / -1 en notas de crédito) y observaciones."""
    compras = tipo == "compras"
    plan = Plan(conn)
    roles = cargar_roles(conn, plan)
    requeridos = ("proveedores", "iva_credito", "gasto_defecto") if compras else ("clientes", "iva_debito", "ingreso_defecto")
    faltan = [ROLES[r][0] for r in requeridos if roles[r] is None]
    if faltan:
        raise ValueError("Estas cuentas de enlace apuntan a un código que no existe en tu plan de cuentas: "
                         + "; ".join(faltan) + ". Corrígelas en Plan de Cuentas → Cuentas de enlace.")
 
    defecto = roles["gasto_defecto" if compras else "ingreso_defecto"][0]
    tabla = "proveedores" if compras else "clientes"
    habitual = {}
    for rut, cta in conn.execute(
            f"SELECT rut, cuenta_defecto FROM {tabla} WHERE cuenta_defecto IS NOT NULL AND TRIM(cuenta_defecto) <> ''"):
        r = plan.resolver(cta)
        if r:
            habitual[str(rut).strip().upper()] = r[0]
 
    if compras:
        existentes = {(str(r).strip().upper(), int(t), str(f).strip()) for r, t, f in conn.execute(
            "SELECT p.rut, c.tipo_doc, c.folio FROM compras c JOIN proveedores p ON p.id = c.proveedor_id "
            "WHERE c.tipo_doc IS NOT NULL AND c.folio IS NOT NULL")}
    else:
        existentes = {(int(t), str(f).strip()) for t, f in conn.execute(
            "SELECT tipo_doc, folio FROM ventas WHERE tipo_doc IS NOT NULL AND folio IS NOT NULL")}
 
    estados, cuentas, origenes, signos, observ = [], [], [], [], []
    vistos = set()
    for d in docs.itertuples():
        clave = (d.rut, d.tipo_doc, d.folio) if compras else (d.tipo_doc, d.folio)
        obs = []
        if pd.isna(d.fecha_doc):
            estado = "❌ Fecha inválida"
        elif d.tipo_doc not in DOC_SOPORTADOS:
            estado = "⚠️ Tipo no soportado"
            obs.append(f"El tipo {d.tipo_doc} no se contabiliza automáticamente; regístralo con un asiento manual.")
        elif d.total == 0:
            estado = "⚠️ Monto cero"
        elif clave in existentes:
            estado = "🔁 Ya registrado"
        elif clave in vistos:
            estado = "🔁 Repetido en el archivo"
        else:
            estado = "✅ Nuevo"
        vistos.add(clave)
 
        signo = -1 if d.tipo_doc in DOC_NOTA_CREDITO else 1
        if compras:
            comp = d.exento + d.neto + d.iva + d.iva_no_rec + d.neto_af + d.iva_af + d.iva_uso_comun
        else:
            comp = d.exento + d.neto + d.iva
        dif = d.total - comp
        if abs(dif) > 1:
            obs.append(f"El total difiere de la suma de los montos en ${dif:,.0f}; se lleva a la cuenta principal.")
        if d.exento > 0 and d.neto > 0:
            obs.append("Documento mixto: parte exenta y parte afecta.")
        if compras and d.iva_uso_comun > 0:
            obs.append("IVA de uso común: se llevó al gasto; revisa la proporcionalidad.")
        if compras and d.iva_no_rec > 0:
            obs.append("IVA no recuperable: se suma al gasto.")
        if compras and d.neto_af > 0:
            obs.append("Incluye activo fijo.")
        if signo < 0:
            ref = f" (refiere a {nombre_doc(d.ref_tipo)} N° {d.ref_folio})" if d.ref_folio else ""
            obs.append("Nota de crédito: revierte el asiento" + ref + ".")
 
        if d.rut in habitual:
            cuenta, origen = habitual[d.rut], "Cuenta habitual"
        else:
            cuenta, origen = defecto, "Por defecto (revisar)"
        estados.append(estado); cuentas.append(cuenta); origenes.append(origen)
        signos.append(signo); observ.append(" ".join(obs))
 
    docs = docs.copy()
    docs["estado"] = estados
    docs["cuenta_sugerida"] = cuentas
    docs["cuenta_codigo"] = cuentas
    docs["cuenta_origen"] = origenes
    docs["signo"] = signos
    docs["obs"] = observ
    return docs
 
 
# ---------------------------------------------------------------------------
# Asientos
# ---------------------------------------------------------------------------
def armar_asiento(doc, tipo, cuenta, roles):
    """Devuelve [(codigo_cuenta, debe, haber), ...] de un documento. Cuadra siempre.
    Compras: gasto (todo lo que no es IVA con crédito ni activo fijo) + IVA crédito + activo fijo / Proveedores.
    Ventas: Clientes / Ingreso (total - IVA) + IVA débito. Las notas de crédito invierten el asiento."""
    total = float(doc.total)
    if tipo == "compras":
        iva = float(doc.iva) + float(doc.iva_af)
        neto_af = float(doc.neto_af)
        principal = total - iva - neto_af
        if principal < 0:
            raise ValueError(f"Documento {doc.folio}: los montos no son coherentes con el total.")
        if neto_af > 0 and roles["activo_fijo"] is None:
            raise ValueError("Hay activo fijo en el archivo, pero la cuenta de enlace 'Activo fijo' no existe en tu plan.")
        debe = [(cuenta, principal)]
        if neto_af > 0:
            debe.append((roles["activo_fijo"][0], neto_af))
        if iva > 0:
            debe.append((roles["iva_credito"][0], iva))
        haber = [(roles["proveedores"][0], total)]
    else:
        iva = float(doc.iva)
        principal = total - iva
        if principal < 0:
            raise ValueError(f"Documento {doc.folio}: los montos no son coherentes con el total.")
        debe = [(roles["clientes"][0], total)]
        haber = [(cuenta, principal)]
        if iva > 0:
            haber.append((roles["iva_debito"][0], iva))
    if doc.signo < 0:
        debe, haber = haber, debe
    lineas = [(c, round(m, 2), 0.0) for c, m in debe if m > 0] + [(c, 0.0, round(m, 2)) for c, m in haber if m > 0]
    if abs(sum(l[1] for l in lineas) - sum(l[2] for l in lineas)) > 0.01:
        raise ValueError(f"Documento {doc.folio}: el asiento no cuadra.")
    return lineas
 
 
def _siguiente_asiento(cur):
    return cur.execute("SELECT COALESCE(MAX(asiento_id), 0) FROM libro_diario").fetchone()[0]
 
 
def contabilizar(conn, tipo, docs, fecha_modo="documento", origen="", recordar=True):
    """Guarda los documentos (ya filtrados y con 'cuenta_codigo' definitiva) en compras/ventas y Libro Diario.
    Todo o nada: si algo falla no se guarda nada."""
    compras = tipo == "compras"
    plan = Plan(conn)
    roles = cargar_roles(conn, plan)
    lote = f"{'RCV-COMPRAS' if compras else 'RCV-VENTAS'}-{datetime.now():%Y%m%d-%H%M%S}"
    origen = origen or ("RCV Compras" if compras else "RCV Ventas")
    cur = conn.cursor()
    asiento = _siguiente_asiento(cur)
    n_docs = 0
    total_debe = 0.0
    recordadas = 0
    try:
        for d in docs.itertuples():
            if d.cuenta_codigo not in plan.hojas:
                raise ValueError(f"La cuenta '{d.cuenta_codigo}' del documento {d.folio} no es una cuenta imputable del plan.")
            nombre_cta = plan.hojas[d.cuenta_codigo]
            fecha = d.fecha_doc if fecha_modo == "documento" else (d.fecha_recepcion if isinstance(d.fecha_recepcion, str) else d.fecha_doc)
            glosa = f"{nombre_doc(d.tipo_doc)} N° {d.folio} - {d.razon_social}"
            lineas = armar_asiento(d, tipo, d.cuenta_codigo, roles)
 
            centro = "General / Ninguno"
            tabla = "proveedores" if compras else "clientes"
            fila = cur.execute(f"SELECT id FROM {tabla} WHERE UPPER(TRIM(rut)) = ?", (d.rut,)).fetchone()
            if fila:
                ent_id = fila[0]
            else:
                ent_id = cur.execute(f"INSERT INTO {tabla} (rut, nombre) VALUES (?, ?)", (d.rut, d.razon_social)).lastrowid
            if compras:
                cc = cur.execute("SELECT centro_costo FROM proveedores WHERE id = ?", (ent_id,)).fetchone()
                if cc and cc[0]:
                    centro = cc[0]
 
            s = int(d.signo)
            iva_doc = float(d.iva) + (float(d.iva_af) if compras else 0.0)
            if compras:
                cur.execute(
                    "INSERT INTO compras (fecha, proveedor_id, cuenta_gasto, centro_costo, monto_neto, iva, monto_total, glosa, tipo_doc, folio, lote_id) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (fecha, ent_id, nombre_cta, centro, s * (float(d.total) - iva_doc), s * iva_doc, s * float(d.total), glosa, int(d.tipo_doc), str(d.folio), lote))
            else:
                cur.execute(
                    "INSERT INTO ventas (fecha, cliente_id, cuenta_ingreso, monto_neto, iva, monto_total, glosa, tipo_doc, folio, lote_id) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (fecha, ent_id, nombre_cta, s * (float(d.total) - iva_doc), s * iva_doc, s * float(d.total), glosa, int(d.tipo_doc), str(d.folio), lote))
 
            asiento += 1
            for codigo, debe, haber in lineas:
                cur.execute(
                    "INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa, centro_costo, codigo_cuenta, asiento_id, lote_id, origen) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (fecha, plan.todos[codigo], float(debe), float(haber), glosa, centro, codigo, int(asiento), lote, origen))
                total_debe += debe
            n_docs += 1
 
            if recordar and d.cuenta_codigo != d.cuenta_sugerida:
                cur.execute(f"UPDATE {tabla} SET cuenta_defecto = ? WHERE id = ?", (d.cuenta_codigo, ent_id))
                recordadas += 1
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback()
        raise ValueError("Alguno de los documentos ya estaba registrado. No se guardó nada; vuelve a cargar el archivo.")
    except Exception:
        conn.rollback()
        raise
    return {"lote": lote, "documentos": n_docs, "total_debe": total_debe, "cuentas_recordadas": recordadas}
 
 
# ---------------------------------------------------------------------------
# Matrices de asientos (saldos iniciales, históricos)
# ---------------------------------------------------------------------------
def validar_asientos(conn, df):
    """Valida un archivo con columnas fecha, cuenta, debe, haber, glosa (opcionales: asiento, centro_costo).
    'cuenta' puede ser el código o el nombre. Devuelve (tabla resuelta, lista de errores)."""
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    faltan = [c for c in ("fecha", "cuenta", "debe", "haber", "glosa") if c not in df.columns]
    if faltan:
        return None, [f"Faltan columnas obligatorias: {', '.join(faltan)}."]
 
    plan = Plan(conn)
    errores = []
    out = pd.DataFrame(index=df.index)
    out["fecha"] = _fecha_iso(df["fecha"])
    out["cuenta_original"] = df["cuenta"].fillna("").astype(str).str.strip()
    resuelto = out["cuenta_original"].map(plan.resolver)
    out["codigo"] = resuelto.map(lambda r: r[0] if r else None)
    out["cuenta"] = resuelto.map(lambda r: r[1] if r else None)
    out["debe"] = _num(df["debe"])
    out["haber"] = _num(df["haber"])
    out["glosa"] = df["glosa"].fillna("").astype(str)
    out["centro_costo"] = (df["centro_costo"].fillna("General / Ninguno") if "centro_costo" in df.columns else "General / Ninguno")
    if "asiento" in df.columns:
        out["asiento"] = pd.to_numeric(df["asiento"], errors="coerce")
        if out["asiento"].isna().any():
            errores.append("La columna 'asiento' tiene filas vacías o con texto.")
    else:
        out["asiento"] = 1
 
    linea = lambda idx: ", ".join(str(i + 2) for i in idx[:10]) + ("…" if len(idx) > 10 else "")
    malas = list(out.index[out["fecha"].isna()])
    if malas:
        errores.append(f"Fecha inválida (usa AAAA-MM-DD o DD/MM/AAAA) en las líneas: {linea(malas)}.")
    for nombre in out.loc[out["codigo"].isna(), "cuenta_original"].unique():
        grupo = [c for c, n in plan.todos.items() if n.strip().lower() == nombre.lower() or c == nombre]
        if grupo:
            errores.append(f"'{nombre}' es una cuenta de grupo y no recibe movimientos; usa una subcuenta.")
        else:
            errores.append(f"La cuenta '{nombre}' no existe en el plan de cuentas.")
    malas = list(out.index[(out["debe"] < 0) | (out["haber"] < 0)])
    if malas:
        errores.append(f"Hay montos negativos en las líneas: {linea(malas)}.")
    malas = list(out.index[((out["debe"] > 0) & (out["haber"] > 0)) | ((out["debe"] == 0) & (out["haber"] == 0))])
    if malas:
        errores.append(f"Cada línea debe tener monto solo en Debe o solo en Haber (líneas: {linea(malas)}).")
    if not out["asiento"].isna().any():
        for n, g in out.groupby("asiento"):
            if abs(g["debe"].sum() - g["haber"].sum()) >= 0.01:
                errores.append(f"El asiento {int(n)} está descuadrado: Debe ${g['debe'].sum():,.0f} vs Haber ${g['haber'].sum():,.0f}.")
    return out, errores
 
 
def guardar_asientos(conn, tabla, origen):
    """Guarda una tabla ya validada. Rechaza un archivo que ya fue importado (mismo origen)."""
    if conn.execute("SELECT 1 FROM libro_diario WHERE origen = ? LIMIT 1", (origen,)).fetchone():
        raise ValueError("Este archivo ya fue importado antes. Si quieres cargarlo de nuevo, deshaz primero su lote.")
    lote = f"MATRIZ-{datetime.now():%Y%m%d-%H%M%S}"
    cur = conn.cursor()
    base = _siguiente_asiento(cur)
    orden = {n: i + 1 for i, n in enumerate(sorted(tabla["asiento"].unique()))}
    try:
        for r in tabla.itertuples():
            cur.execute(
                "INSERT INTO libro_diario (fecha, cuenta, debe, haber, glosa, centro_costo, codigo_cuenta, asiento_id, lote_id, origen) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (r.fecha, r.cuenta, float(r.debe), float(r.haber), r.glosa, r.centro_costo, r.codigo,
                 int(base + orden[r.asiento]), lote, origen))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return {"lote": lote, "lineas": len(tabla), "asientos": len(orden)}
 
 
# ---------------------------------------------------------------------------
# Lotes
# ---------------------------------------------------------------------------
def listar_lotes(conn):
    return pd.read_sql_query(
        "SELECT lote_id AS Lote, origen AS Origen, MIN(fecha) AS Desde, MAX(fecha) AS Hasta, "
        "COUNT(DISTINCT asiento_id) AS Asientos, SUM(debe) AS Total_Debe "
        "FROM libro_diario WHERE lote_id IS NOT NULL GROUP BY lote_id, origen ORDER BY lote_id DESC", conn)
 
 
def deshacer_lote(conn, lote_id):
    cur = conn.cursor()
    try:
        borrados = {}
        for tabla in ("libro_diario", "compras", "ventas"):
            borrados[tabla] = cur.execute(f"DELETE FROM {tabla} WHERE lote_id = ?", (lote_id,)).rowcount
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return borrados
 

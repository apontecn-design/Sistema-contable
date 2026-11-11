# CONTEM: componente extraído del app.py original; ejecución secuencial compartida.
import sqlite3
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



# Conciliación N:1: una línea del Libro Diario se utiliza como máximo una vez.
def sgci_crear_vinculos_bancarios(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS sgci_conciliacion_lineas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cartola_id INTEGER NOT NULL,
        diario_id INTEGER NOT NULL UNIQUE,
        monto REAL NOT NULL,
        creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(cartola_id) REFERENCES cartola_bancaria(id),
        FOREIGN KEY(diario_id) REFERENCES libro_diario(id)
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sgci_vinculos_cartola ON sgci_conciliacion_lineas(cartola_id)")
    conn.commit()


def sgci_lineas_bancarias_disponibles(conn, movimiento_id):
    sgci_crear_vinculos_bancarios(conn)
    mov=conn.execute("""SELECT cb.*,b.cuenta_contable FROM cartola_bancaria cb
        JOIN bancos b ON b.id=cb.banco_id WHERE cb.id=?""",(int(movimiento_id),)).fetchone()
    if not mov or int(mov['conciliado'] or 0):
        return pd.DataFrame()
    cuenta=str(mov['cuenta_contable'] or '').strip()
    if not cuenta:
        return pd.DataFrame()
    cargo=float(mov['cargo'] or 0)>0
    # Una salida de banco se acredita (Haber); un abono se debita (Debe).
    columna='haber' if cargo else 'debe'
    contraria='debe' if cargo else 'haber'
    return pd.read_sql_query(f"""SELECT ld.id,ld.fecha,ld.asiento_id,ld.glosa,ld.origen,
        ld.codigo_cuenta,ld.{columna} AS monto
        FROM libro_diario ld
        WHERE ld.codigo_cuenta=? AND ld.{columna}>0 AND COALESCE(ld.{contraria},0)=0
        AND NOT EXISTS(SELECT 1 FROM sgci_conciliacion_lineas x WHERE x.diario_id=ld.id)
        AND NOT EXISTS(SELECT 1 FROM cartola_bancaria cb
            WHERE cb.conciliado=1 AND cb.asiento_id=ld.asiento_id
            AND COALESCE(cb.match_tipo,'')<>'ASIENTOS_EXISTENTES')
        ORDER BY ld.fecha DESC,ld.id DESC LIMIT 1000""",conn,params=(cuenta,))


def sgci_conciliar_lineas_existentes(conn,movimiento_id,diario_ids):
    sgci_autorizar_operacion(conn, 'banco', 'conciliar', 'Conciliación bancaria')
    ids=[int(x) for x in diario_ids]
    if not ids or len(ids)!=len(set(ids)):
        raise ValueError('Selecciona líneas bancarias distintas.')
    sgci_crear_vinculos_bancarios(conn)
    try:
        conn.execute('BEGIN IMMEDIATE')
        mov=conn.execute("""SELECT cb.*,b.cuenta_contable FROM cartola_bancaria cb
            JOIN bancos b ON b.id=cb.banco_id WHERE cb.id=?""",(int(movimiento_id),)).fetchone()
        if not mov or int(mov['conciliado'] or 0):
            raise ValueError('El movimiento ya fue conciliado o no existe.')
        cuenta=str(mov['cuenta_contable'] or '').strip()
        if not cuenta:
            raise ValueError('La cuenta bancaria no tiene cuenta contable configurada.')
        cargo=float(mov['cargo'] or 0)>0
        objetivo=float(mov['cargo'] if cargo else mov['abono'] or 0)
        if objetivo<=0 or (float(mov['abono'] or 0)>0 and cargo):
            raise ValueError('El movimiento no tiene una naturaleza bancaria válida.')
        marks=','.join('?' for _ in ids)
        lineas=conn.execute(f'SELECT * FROM libro_diario WHERE id IN ({marks})',ids).fetchall()
        if len(lineas)!=len(ids):
            raise ValueError('Alguna línea contable ya no existe.')
        total=0
        for l in lineas:
            if str(l['codigo_cuenta'] or '')!=cuenta:
                raise ValueError('Una línea pertenece a otra cuenta bancaria.')
            monto=float(l['haber'] if cargo else l['debe'] or 0)
            opuesto=float(l['debe'] if cargo else l['haber'] or 0)
            if monto<=0 or opuesto!=0:
                raise ValueError('La naturaleza de una línea no coincide con la cartola.')
            if conn.execute('SELECT 1 FROM sgci_conciliacion_lineas WHERE diario_id=?',(l['id'],)).fetchone():
                raise ValueError('Una línea ya fue conciliada en otro movimiento.')
            if conn.execute("""SELECT 1 FROM cartola_bancaria
                WHERE conciliado=1 AND asiento_id=? AND COALESCE(match_tipo,'')<>'ASIENTOS_EXISTENTES'""",(l['asiento_id'],)).fetchone():
                raise ValueError('Un asiento ya está asociado a otra conciliación.')
            total+=monto
        if abs(total-objetivo)>0.005:
            raise ValueError(f'Las líneas suman {total:,.0f} y el movimiento {objetivo:,.0f}.')
        for l in lineas:
            monto=float(l['haber'] if cargo else l['debe'])
            conn.execute('INSERT INTO sgci_conciliacion_lineas(cartola_id,diario_id,monto) VALUES(?,?,?)',
                         (int(movimiento_id),int(l['id']),monto))
        asiento_referencia=int(lineas[0]['asiento_id']) if len({l['asiento_id'] for l in lineas})==1 else None
        cur=conn.execute("""UPDATE cartola_bancaria SET conciliado=1,
            match_tipo='ASIENTOS_EXISTENTES',match_id=NULL,match_confianza=100,
            asiento_id=?,observacion=? WHERE id=? AND conciliado=0""",
            (asiento_referencia,f'Conciliación sin asiento nuevo: {len(ids)} líneas del Libro Diario',int(movimiento_id)))
        if cur.rowcount!=1:
            raise ValueError('El movimiento cambió durante la operación.')
        conn.execute("""INSERT INTO auditoria(fecha_hora,usuario,accion,detalle)
            VALUES(CURRENT_TIMESTAMP,'SGCI','CONCILIACION ASIENTOS EXISTENTES',?)""",
            (f'Cartola {movimiento_id}; líneas {ids}; monto {objetivo:.0f}; sin asiento nuevo',))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return len(ids)

def sgci_grupo_cheque_protestado(conn, movimiento_id):
    """Identifica exclusivamente un cheque debitado, una devolución neutra y su reversa.

    No infiere pagos a proveedores ni altera el libro diario.
    """
    mov=conn.execute("SELECT * FROM cartola_bancaria WHERE id=?",(movimiento_id,)).fetchone()
    if not mov or int(mov['conciliado'] or 0):
        return None
    desc=str(mov['descripcion'] or '').upper()
    if 'DEV CHQ' not in desc or 'FIRMA DISCONFORM' not in desc:
        return None
    importe=float(mov['cargo'] or 0)
    if importe<=0 or abs(importe-float(mov['abono'] or 0))>0.005:
        return None
    filas=conn.execute("""SELECT * FROM cartola_bancaria
        WHERE banco_id=? AND fecha=? AND conciliado=0 AND id<>?
        ORDER BY id""",(mov['banco_id'],mov['fecha'],movimiento_id)).fetchall()
    cargos=[r for r in filas if 'CHEQUE COBRADO POR OTRO BANCO' in str(r['descripcion'] or '').upper()
            and abs(float(r['cargo'] or 0)-importe)<0.005 and abs(float(r['abono'] or 0))<0.005]
    reversas=[r for r in filas if 'REVERSA DE CARGO' in str(r['descripcion'] or '').upper()
              and abs(float(r['abono'] or 0)-importe)<0.005 and abs(float(r['cargo'] or 0))<0.005]
    # No seleccionar automáticamente si existen varias operaciones posibles.
    if len(cargos)!=1 or len(reversas)!=1:
        return None
    grupo=[cargos[0],mov,reversas[0]]
    if any(r['asiento_id'] is not None or r['match_tipo'] is not None or r['match_id'] is not None for r in grupo):
        return None
    ids=[int(r['id']) for r in grupo]
    if len(set(ids))!=3 or abs(sum(float(r['abono'] or 0)-float(r['cargo'] or 0) for r in grupo))>0.005:
        return None
    return grupo


def sgci_conciliar_cheque_protestado(conn, movimiento_id):
    """Cierra el grupo bancario de efecto neto cero sin asientos ni pagos."""
    sgci_autorizar_operacion(conn, 'banco', 'conciliar', 'Conciliación bancaria')
    try:
        conn.execute('BEGIN IMMEDIATE')
        grupo=sgci_grupo_cheque_protestado(conn,movimiento_id)
        if not grupo:
            raise ValueError('El grupo no es inequívoco o alguno de sus movimientos ya cambió.')
        ids=[int(r['id']) for r in grupo]
        # Verificar referencias externas antes de marcar movimientos.
        for tabla in ('obligaciones_manuales','pagos_clientes','sgci_conciliacion_lineas'):
            existe=conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(tabla,)).fetchone()
            if existe:
                n=conn.execute(f"SELECT COUNT(*) FROM {tabla} WHERE cartola_id IN (?,?,?)",ids).fetchone()[0]
                if n:
                    raise ValueError('Existen vínculos previos: operación no modificada.')
        detalle='Cheque protestado: débito, devolución de cargo y reversa; efecto neto $0. Sin pago ni asiento contable.'
        for r in grupo:
            cur=conn.execute("""UPDATE cartola_bancaria SET conciliado=1,
                match_tipo='CHEQUE_PROTESTADO',match_id=?,match_confianza=100,
                observacion=? WHERE id=? AND conciliado=0 AND asiento_id IS NULL AND match_tipo IS NULL""",
                (int(movimiento_id),detalle,int(r['id'])))
            if cur.rowcount!=1:
                raise ValueError('Un movimiento cambió; no se aplicaron modificaciones.')
        conn.execute("""INSERT INTO auditoria(fecha_hora,usuario,accion,detalle)
            VALUES(CURRENT_TIMESTAMP,'SGCI','CONCILIACION CHEQUE PROTESTADO',?)""",
            (f'Movimientos {ids}; devolución {movimiento_id}; sin asiento ni pago',))
        conn.commit()
        return ids
    except Exception:
        conn.rollback()
        raise


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


def hash_archivo(uploaded_file):
    """Huella SHA-256 del archivo subido."""
    return sha256(uploaded_file.getvalue()).hexdigest()

def importacion_archivo_existente(conn, modulo, archivo_hash):
    return conn.execute("SELECT * FROM importaciones_archivos WHERE modulo=? AND archivo_hash=? ORDER BY id DESC LIMIT 1", (modulo, archivo_hash)).fetchone()

def registrar_importacion_archivo(conn, modulo, nombre_archivo, archivo_hash, lote_id=None, leidos=0, nuevos=0, duplicados=0):
    conn.execute("""INSERT OR IGNORE INTO importaciones_archivos
        (modulo,nombre_archivo,archivo_hash,lote_id,fecha_hora,registros_leidos,registros_nuevos,registros_duplicados)
        VALUES(?,?,?,?,?,?,?,?)""",
        (modulo,nombre_archivo,archivo_hash,lote_id,datetime.now().strftime("%Y-%m-%d %H:%M:%S"),int(leidos or 0),int(nuevos or 0),int(duplicados or 0)))
    conn.commit()

def historial_archivos(conn, modulo, limite=50):
    return pd.read_sql_query("""SELECT nombre_archivo AS archivo, fecha_hora AS fecha_importacion, lote_id AS lote,
        registros_leidos AS leidos, registros_nuevos AS nuevos, registros_duplicados AS duplicados
        FROM importaciones_archivos WHERE modulo=? ORDER BY id DESC LIMIT ?""", conn, params=(modulo,int(limite)))


def resumen_rcv_historico(conn, tipo):
    """Resumen de documentos existentes; no reconstruye archivos ni altera asientos."""
    tabla = "compras" if tipo == "compras" else "ventas"
    return pd.read_sql_query(f"""
        SELECT substr(fecha,1,7) AS periodo,
               COUNT(*) AS documentos,
               COUNT(DISTINCT lote_id) AS lotes_identificados
        FROM {tabla}
        WHERE fecha IS NOT NULL AND length(fecha) >= 7
        GROUP BY substr(fecha,1,7)
        ORDER BY periodo DESC
    """, conn)


def mostrar_historial_rcv_completo(conn, tipo):
    """Muestra tanto importaciones auditadas como documentos anteriores al registro de archivos."""
    modulo = "RCV_COMPRAS" if tipo == "compras" else "RCV_VENTAS"
    historico = resumen_rcv_historico(conn, tipo)
    st.markdown("**Documentos registrados por período**")
    st.caption("Períodos según fecha del documento. Incluye registros antiguos, pero no permite recuperar el nombre ni la fecha de carga de archivos no registrados.")
    if historico.empty:
        st.caption("No hay documentos registrados para mostrar.")
    else:
        st.dataframe(historico.rename(columns={"periodo":"Período", "documentos":"Documentos registrados", "lotes_identificados":"Lotes identificados"}), use_container_width=True, hide_index=True)
    st.markdown("**Archivos importados con trazabilidad**")
    hist = historial_archivos(conn, modulo)
    if hist.empty:
        st.caption("No existen archivos registrados en el historial de importaciones.")
    else:
        st.dataframe(hist.rename(columns={"archivo":"Archivo", "fecha_importacion":"Fecha importación", "lote":"Lote", "leidos":"Leídos", "nuevos":"Nuevos", "duplicados":"Duplicados"}), use_container_width=True, hide_index=True)
    st.info("Control de duplicados: se comprueba RUT + tipo de documento + folio contra los documentos ya registrados y contra el archivo cargado. Solo los documentos nuevos y válidos pueden contabilizarse.")


def importar_cartola(conn, df, banco_id, origen="CARTOLA"):
    """Importa movimientos tabulares evitando duplicados."""
    sgci_autorizar_operacion(conn, 'banco', 'importar', 'Bancos y cartolas')
    return _importar_movimientos_cartola(conn, df, banco_id, origen)


def _importar_movimientos_cartola(conn, df, banco_id, origen):
    """Escritura compartida por las dos entradas autorizadas: importar y crear."""
    if not conn.execute('SELECT 1 FROM bancos WHERE id=? AND activo=1',(banco_id,)).fetchone():
        raise ValueError('Selecciona un banco activo.')
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

    lote = "BANCO-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    nuevos = 0
    repetidos = 0

    with conn:
        for _, r in df.iterrows():
            fecha = fecha_iso(r.get(fecha_c))
            desc = limpiar_texto(r.get(desc_c))
            ref = limpiar_texto(r.get(ref_c)) if ref_c else ""
            cargo = abs(numero(r.get(cargo_c))) if cargo_c else 0
            abono = abs(numero(r.get(abono_c))) if abono_c else 0
            saldo = numero(r.get(saldo_c)) if saldo_c and limpiar_texto(r.get(saldo_c)) else None
            if not ref and saldo is not None:
                ref = f"SGCI-SALDO-{int(round(saldo))}"
            if not fecha or not desc or (cargo <= 0 and abono <= 0):
                continue
            try:
                conn.execute('''INSERT INTO cartola_bancaria
                    (banco_id,fecha,descripcion,referencia,cargo,abono,saldo,lote_id,origen)
                    VALUES(?,?,?,?,?,?,?,?,?)''', (banco_id,fecha,desc,ref,cargo,abono,saldo,lote,origen))
                nuevos += 1
            except sqlite3.IntegrityError as exc:
                if exc.sqlite_errorname not in ('SQLITE_CONSTRAINT_UNIQUE','SQLITE_CONSTRAINT_PRIMARYKEY'):
                    raise
                repetidos += 1
        conn.execute('INSERT INTO auditoria(fecha_hora,usuario,accion,detalle) VALUES(?,?,?,?)',
            (datetime.now().isoformat(timespec='seconds'),sgci_identidad_actual(),'IMPORTACIÓN CARTOLA',
             f'Banco {banco_id}: {nuevos} movimientos nuevos, {repetidos} repetidos; lote {lote}'))
    return nuevos, repetidos, lote


def historial_importaciones_cartola(conn, banco_id):
    """Resume cada lote de cartola para permitir su administración segura."""
    return pd.read_sql_query("""
        SELECT
            lote_id AS lote,
            MIN(fecha) AS desde,
            MAX(fecha) AS hasta,
            COALESCE(MAX(origen),'') AS origen,
            COALESCE((SELECT ia.nombre_archivo FROM importaciones_archivos ia WHERE ia.modulo='CARTOLA' AND ia.lote_id=cartola_bancaria.lote_id ORDER BY ia.id DESC LIMIT 1),'') AS archivo,
            COUNT(*) AS movimientos,
            COALESCE(SUM(cargo),0) AS cargos,
            COALESCE(SUM(abono),0) AS abonos,
            COALESCE(SUM(CASE WHEN conciliado=1 THEN 1 ELSE 0 END),0) AS conciliados
        FROM cartola_bancaria
        WHERE banco_id=? AND lote_id IS NOT NULL AND TRIM(lote_id)<>''
        GROUP BY lote_id
        ORDER BY lote_id DESC
    """, conn, params=(banco_id,))


def eliminar_importacion_cartola(conn, banco_id, lote_id):
    """Elimina un lote solo si ninguno de sus movimientos fue conciliado."""
    sgci_autorizar_operacion(conn, 'banco', 'eliminar', 'Bancos y cartolas')
    info=conn.execute("""
        SELECT COUNT(*) total,
               COALESCE(SUM(CASE WHEN conciliado=1 THEN 1 ELSE 0 END),0) conciliados
        FROM cartola_bancaria
        WHERE banco_id=? AND lote_id=?
    """,(banco_id,lote_id)).fetchone()
    if not info or int(info[0] or 0)==0:
        raise ValueError("La importación seleccionada ya no contiene movimientos.")
    if int(info[1] or 0)>0:
        raise ValueError(
            f"No se puede eliminar esta importación porque contiene {int(info[1])} movimiento(s) conciliado(s). "
            "Primero deben reversarse desde Movimientos/Conciliación."
        )
    total=int(info[0])
    try:
        conn.execute("DELETE FROM cartola_bancaria WHERE banco_id=? AND lote_id=?",(banco_id,lote_id))
        conn.commit()
        registrar_auditoria(conn,"ELIMINAR IMPORTACIÓN CARTOLA",f"Banco {banco_id} · lote {lote_id} · {total} movimientos")
        return total
    except Exception:
        conn.rollback()
        raise


def numero_cartola_clp(valor):
    """Interpreta montos enteros CLP de cartolas chilenas.
    Ej.: 25.000 -> 25000; 2.028.758 -> 2028758; 754 -> 754.
    No se usa para UF, porcentajes ni RCV.
    """
    if valor is None:
        return 0.0
    s = str(valor).strip().replace("$", "").replace(" ", "")
    if not s:
        return 0.0
    negativo = s.startswith("-")
    s = s.lstrip("+-")
    # En cartolas CLP BCI el punto es separador de miles y no separador decimal.
    s = s.replace(".", "").replace(",", "")
    if not s.isdigit():
        return 0.0
    n = int(s)
    return float(-n if negativo else n)


def leer_cartola_pdf(uploaded_file, password=""):
    """Lee cartolas BCI separando referencia, cargos y abonos y verificando saldos."""
    datos = uploaded_file.getvalue()
    if not datos:
        raise ValueError("El PDF está vacío.")
    try:
        from pypdf import PdfReader
    except ImportError:
        from PyPDF2 import PdfReader
    try:
        lector = PdfReader(io.BytesIO(datos))
        if getattr(lector, "is_encrypted", False):
            if not password or not lector.decrypt(password):
                raise ValueError("Ingresa la contraseña correcta del PDF.")
        texto = "\n".join(p.extract_text() or "" for p in lector.pages)
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"No fue posible leer el PDF: {e}") from e

    # Separa estrictamente los importes CLP con puntos de miles de las
    # referencias (p. ej. 5297574, 5297569 o R).
    monto_re = r"\d{1,3}(?:\.\d{3})+"
    fila_re = re.compile(r"^(\d{2}-\d{2}-\d{4})\s+(.+?)\s+(" + monto_re + r")\s+(" + monto_re + r")\s*$")
    fila_doble_re = re.compile(r"^(\d{2}-\d{2}-\d{4})\s+(.+?)\s+(" + monto_re + r")\s+(" + monto_re + r")\s+(" + monto_re + r")\s*$")
    ref_re = re.compile(r"^(.*?)\s+(\d{4,}|R)$", re.I)
    palabras_abono = ("ABONO", "DEPOSITO", "DEPÓSITO", "TRANSFERENCIA RECIBIDA", "PAGO RECIBIDO", "TRANSFERENCIA DE", "TRANSFER DE", "DEPOSITO EN", "DEPÓSITO EN", "REVERSA DE CARGO")
    saldo_inicial_match = re.search(r"Saldo Anterior\s+(" + monto_re + r")", texto, re.I)
    saldo_anterior = numero_cartola_clp(saldo_inicial_match.group(1)) if saldo_inicial_match else None
    salida = []
    for linea in texto.splitlines():
        linea = re.sub(r"\s+", " ", linea.strip())
        doble = fila_doble_re.match(linea)
        simple = None if doble else fila_re.match(linea)
        if not doble and not simple:
            continue
        if doble:
            fecha, cuerpo, cargo_s, abono_s, saldo_s = doble.groups()
            cargo = numero_cartola_clp(cargo_s)
            abono = numero_cartola_clp(abono_s)
        else:
            fecha, cuerpo, importe_s, saldo_s = simple.groups()
            importe = numero_cartola_clp(importe_s)
            cargo = abono = 0.0
        saldo = numero_cartola_clp(saldo_s)
        # Referencia documental al final del texto, antes de los importes.
        # La referencia no puede confundirse con un monto monetario.
        referencia = ""
        mref = ref_re.match(cuerpo.strip())
        if mref:
            cuerpo, referencia = mref.group(1).strip(), mref.group(2)
        descripcion = cuerpo.strip()
        if simple:
            delta = None if saldo_anterior is None else round(saldo - saldo_anterior)
            if delta is not None and abs(abs(delta) - importe) <= 1:
                abono = importe if delta > 0 else 0.0
                cargo = importe if delta < 0 else 0.0
            elif any(pal in descripcion.upper() for pal in palabras_abono):
                abono = importe
            else:
                cargo = importe
        revision = "CARGO Y ABONO: REVISAR" if cargo and abono else ""
        if saldo_anterior is not None and abs((saldo_anterior - cargo + abono) - saldo) > 1:
            raise ValueError("La cartola no cuadra en el movimiento '" + descripcion + "'. No se importará: revisa la lectura del PDF.")
        salida.append({"fecha": fecha_iso(fecha), "descripcion": descripcion,
                       "referencia": referencia, "cargo": cargo, "abono": abono,
                       "saldo": saldo, "revision": revision})
        saldo_anterior = saldo
    if not salida:
        raise ValueError("No se reconocieron movimientos bancarios en el PDF.")
    return pd.DataFrame(salida)


def sgci_corregir_signo_cartola_pendiente(conn, movimiento_id, tipo_correcto):
    """Corrige únicamente un movimiento no conciliado, con auditoría y sin asientos."""
    sgci_autorizar_operacion(conn, 'banco', 'editar', 'Bancos y cartolas')
    mov = conn.execute("SELECT * FROM cartola_bancaria WHERE id=?", (int(movimiento_id),)).fetchone()
    if mov is None:
        raise ValueError("El movimiento ya no existe.")
    if int(mov["conciliado"] or 0) != 0 or mov["asiento_id"] is not None:
        raise ValueError("No es posible cambiar un movimiento conciliado o contabilizado.")
    cargo, abono = float(mov["cargo"] or 0), float(mov["abono"] or 0)
    if (cargo > 0) == (abono > 0):
        raise ValueError("El movimiento tiene un signo ambiguo y requiere revisión manual.")
    monto = cargo or abono
    if tipo_correcto not in ("Cargo", "Abono"):
        raise ValueError("Selecciona Cargo o Abono.")
    nuevo_cargo = monto if tipo_correcto == "Cargo" else 0.0
    nuevo_abono = monto if tipo_correcto == "Abono" else 0.0
    if cargo == nuevo_cargo and abono == nuevo_abono:
        raise ValueError("El movimiento ya tiene el signo seleccionado.")
    referencia_original = str(mov["referencia"] or "")
    referencia_nueva = referencia_original
    # Si otra transferencia real tiene exactamente el mismo importe y descripción,
    # la restricción UNIQUE no debe impedir corregir el signo de esta operación.
    # Usamos el saldo progresivo original para diferenciarla, sin tocar la otra fila.
    conflicto = conn.execute(
        """SELECT id FROM cartola_bancaria
           WHERE banco_id=? AND fecha=? AND descripcion=? AND cargo=? AND abono=?
             AND referencia=? AND id<>? LIMIT 1""",
        (mov["banco_id"], mov["fecha"], mov["descripcion"], nuevo_cargo,
         nuevo_abono, referencia_original, int(movimiento_id))
    ).fetchone()
    if conflicto:
        if mov["saldo"] is None:
            raise ValueError("Existe otro movimiento igual y falta el saldo bancario para distinguirlos. No se modificó nada.")
        referencia_nueva = f"SGCI-SALDO-{int(round(float(mov['saldo'])))}"
        existe_ref = conn.execute(
            """SELECT id FROM cartola_bancaria WHERE banco_id=? AND fecha=?
               AND descripcion=? AND cargo=? AND abono=? AND referencia=? AND id<>?""",
            (mov["banco_id"], mov["fecha"], mov["descripcion"], nuevo_cargo,
             nuevo_abono, referencia_nueva, int(movimiento_id))
        ).fetchone()
        if existe_ref:
            raise ValueError("Ya existe un movimiento con el mismo saldo y referencia interna. Revisa el PDF; no se modificó nada.")
    try:
        cur = conn.execute(
            """UPDATE cartola_bancaria SET cargo=?, abono=?, referencia=?
               WHERE id=? AND conciliado=0 AND asiento_id IS NULL""",
            (nuevo_cargo, nuevo_abono, referencia_nueva, int(movimiento_id))
        )
        if cur.rowcount != 1:
            raise ValueError("No se pudo modificar el movimiento.")
        registrar_auditoria(conn, "CORREGIR SIGNO CARTOLA",
                            f"Movimiento {movimiento_id} banco {mov['banco_id']} fecha {mov['fecha']}: "
                            f"cargo {cargo} abono {abono} -> cargo {nuevo_cargo} abono {nuevo_abono}; "
                            f"referencia {referencia_original!r} -> {referencia_nueva!r}")
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def registrar_movimiento_manual(conn, banco_id, fecha, descripcion, referencia, cargo, abono, saldo=None):
    sgci_autorizar_operacion(conn, 'banco', 'crear', 'Bancos y cartolas')
    df = pd.DataFrame([{
        "fecha": fecha,
        "descripcion": descripcion,
        "referencia": referencia,
        "cargo": cargo,
        "abono": abono,
        "saldo": saldo,
    }])
    return _importar_movimientos_cartola(conn, df, banco_id, origen="MANUAL")


def crear_obligacion_manual(conn, fecha, tipo, descripcion, referencia, monto, codigo_cuenta):
    sgci_autorizar_operacion(conn, 'banco', 'crear', 'Conciliación bancaria')
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
    sgci_autorizar_operacion(conn, 'banco', 'conciliar', 'Conciliación bancaria')
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
    sgci_autorizar_operacion(conn, 'banco', 'contabilizar', 'Conciliación bancaria')
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




def contabilizar_imputacion_multiple_bancaria(conn, movimiento_id, distribuciones, descripcion=None):
    sgci_autorizar_operacion(conn, 'banco', 'contabilizar', 'Conciliación bancaria')
    """Distribuye un único movimiento bancario entre varias cuentas y lo concilia en un solo asiento."""
    mov = conn.execute("SELECT * FROM cartola_bancaria WHERE id=?", (int(movimiento_id),)).fetchone()
    if not mov:
        raise ValueError("Movimiento bancario no encontrado.")
    if int(mov["conciliado"] or 0) == 1:
        raise ValueError("Este movimiento ya está conciliado.")
    if periodo_cerrado(conn, mov["fecha"]):
        raise ValueError("El período contable de este movimiento está cerrado.")
    banco = conn.execute("SELECT * FROM bancos WHERE id=?", (mov["banco_id"],)).fetchone()
    if not banco or not banco["cuenta_contable"]:
        raise ValueError("La cuenta bancaria no tiene una cuenta contable configurada.")

    monto = clp_round(abs(float(mov["cargo"] or mov["abono"] or 0)))
    es_cargo = float(mov["cargo"] or 0) > 0
    if monto <= 0:
        raise ValueError("El movimiento no tiene monto para contabilizar.")

    plan = Plan(conn)
    cuenta_banco = banco["cuenta_contable"]
    limpias = []
    for codigo, importe in distribuciones:
        importe = clp_round(float(importe or 0))
        if importe <= 0:
            continue
        if codigo not in plan.todos:
            raise ValueError(f"La cuenta {codigo} no existe en el plan de cuentas.")
        if codigo == cuenta_banco:
            raise ValueError("La cuenta bancaria no puede usarse como contrapartida.")
        limpias.append((codigo, importe))
    if len(limpias) < 2:
        raise ValueError("Ingresa al menos dos distribuciones con monto mayor que cero.")
    total = clp_round(sum(x[1] for x in limpias))
    if total != monto:
        raise ValueError(f"La distribución suma {money(total)} y debe sumar exactamente {money(monto)}.")

    glosa = limpiar_texto(descripcion) or limpiar_texto(mov["descripcion"]) or "Imputación bancaria distribuida"
    asiento_id = siguiente_asiento(conn) + 1
    lote = "CONC-MULTI-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    fecha = mov["fecha"]
    try:
        # Cargo/salida: varias cuentas al Debe y Banco al Haber.
        # Abono/entrada: Banco al Debe y varias cuentas al Haber.
        if es_cargo:
            lineas = [(c, imp, 0.0) for c, imp in limpias] + [(cuenta_banco, 0.0, monto)]
        else:
            lineas = [(cuenta_banco, monto, 0.0)] + [(c, 0.0, imp) for c, imp in limpias]
        for codigo, debe, haber in lineas:
            conn.execute("""INSERT INTO libro_diario
                (fecha,cuenta,debe,haber,glosa,codigo_cuenta,asiento_id,lote_id,origen)
                VALUES(?,?,?,?,?,?,?,?,?)""",
                (fecha, plan.todos.get(codigo, codigo), debe, haber, glosa, codigo, asiento_id, lote, "CONCILIACION_BANCARIA_MULTIPLE"))
        detalle = "; ".join(f"{c}: {money(imp)}" for c, imp in limpias)
        conn.execute("""UPDATE cartola_bancaria
                        SET conciliado=1,observacion=?,asiento_id=?,match_tipo='IMPUTACION_MULTIPLE',
                            match_id=NULL,match_confianza=100 WHERE id=?""",
                     (f"{glosa} | {detalle}", asiento_id, int(movimiento_id)))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    registrar_auditoria(conn, "IMPUTACIÓN BANCARIA MÚLTIPLE",
                        f"Movimiento {movimiento_id} distribuido en {len(limpias)} cuentas, asiento {asiento_id}")
    return asiento_id

def documentos_pendientes_cliente(conn, cliente_id):
    sgci_conc_esquema(conn)
    return pd.read_sql_query("""
        SELECT v.id,v.fecha,v.folio,v.tipo_doc,v.monto_total total,
               COALESCE((SELECT SUM(a.monto) FROM aplicaciones_clientes a WHERE a.venta_id=v.id),0) aplicado,
               MAX(ABS(v.monto_total)-COALESCE((SELECT SUM(a.monto) FROM aplicaciones_clientes a WHERE a.venta_id=v.id),0)
                   -COALESCE((SELECT SUM(x.monto) FROM sgci_compensaciones_documentos x WHERE x.modulo='VENTAS' AND x.documento_factura_id=v.id AND x.anulada=0),0),0) pendiente
        FROM ventas v
        WHERE v.cliente_id=? AND (v.tipo_doc IS NULL OR v.tipo_doc NOT IN (60,61,52))
          AND ABS(v.monto_total)-COALESCE((SELECT SUM(a.monto) FROM aplicaciones_clientes a WHERE a.venta_id=v.id),0)
             -COALESCE((SELECT SUM(x.monto) FROM sgci_compensaciones_documentos x WHERE x.modulo='VENTAS' AND x.documento_factura_id=v.id AND x.anulada=0),0) > 0.01
        ORDER BY v.fecha,v.id
    """, conn, params=(int(cliente_id),))


def sgci_saldos_apertura_clientes(conn):
    """Auxiliar histórico, sin crear nuevos asientos de apertura."""
    conn.execute("""CREATE TABLE IF NOT EXISTS sgci_apertura_clientes (
        cliente_id INTEGER PRIMARY KEY, monto INTEGER NOT NULL,
        observacion TEXT, fecha TEXT DEFAULT '2026-01-01')""")
    conn.execute("""CREATE TABLE IF NOT EXISTS sgci_aplicaciones_apertura_clientes (
        movimiento_id INTEGER PRIMARY KEY, cliente_id INTEGER NOT NULL,
        monto INTEGER NOT NULL, pago_id INTEGER, fecha TEXT NOT NULL)""")
    conn.commit()

def sgci_saldo_apertura_disponible(conn, cliente_id):
    sgci_saldos_apertura_clientes(conn)
    r=conn.execute("""SELECT COALESCE(a.monto,0)-COALESCE(
      (SELECT SUM(x.monto) FROM sgci_aplicaciones_apertura_clientes x
       WHERE x.cliente_id=a.cliente_id),0)
      FROM sgci_apertura_clientes a WHERE a.cliente_id=?""",(int(cliente_id),)).fetchone()
    return int(r[0]) if r else 0

def sgci_cobro_mixto(conn,movimiento_id,cliente_id,venta_ids,monto_apertura):
    """Un asiento Banco/Clientes; desglose auxiliar entre facturas y apertura."""
    sgci_autorizar_operacion(conn, 'banco', 'contabilizar', 'Conciliación bancaria')
    sgci_saldos_apertura_clientes(conn)
    mov=conn.execute("SELECT * FROM cartola_bancaria WHERE id=?",(int(movimiento_id),)).fetchone()
    if not mov or int(mov["conciliado"] or 0): raise ValueError("Movimiento inexistente o ya conciliado.")
    if periodo_cerrado(conn,mov["fecha"]): raise ValueError("Período cerrado.")
    monto=clp_round(float(mov["abono"] or 0))
    apertura=int(monto_apertura)
    if apertura<0 or apertura>sgci_saldo_apertura_disponible(conn,cliente_id):
        raise ValueError("La aplicación supera el saldo de apertura disponible.")
    docs=documentos_pendientes_cliente(conn,cliente_id)
    docs=docs[docs["id"].isin([int(x) for x in venta_ids])]
    total_docs=sum(clp_round(float(r.pendiente)) for r in docs.itertuples())
    if len(docs)!=len(set(venta_ids)): raise ValueError("Alguna factura ya no está pendiente.")
    if apertura+total_docs!=monto:
        raise ValueError(f"Debe distribuir exactamente {money(monto)} entre facturas y apertura.")
    if monto<=0: raise ValueError("Abono inválido.")
    banco=conn.execute("SELECT * FROM bancos WHERE id=?",(mov["banco_id"],)).fetchone()
    roles=cargar_roles(conn); cuenta_cli=roles.get("clientes")
    if not banco or not banco["cuenta_contable"] or not cuenta_cli:
        raise ValueError("Faltan cuentas contables de Banco o Clientes.")
    cliente=conn.execute("SELECT * FROM clientes WHERE id=?",(int(cliente_id),)).fetchone()
    if not cliente: raise ValueError("Cliente inexistente.")
    glosa=f"Cobro mixto cliente {cliente_id}; apertura {apertura}; facturas {', '.join(str(r.folio) for r in docs.itertuples())}"
    asiento=siguiente_asiento(conn)+1
    lote="CONC-CLI-MIX-"+datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    plan=Plan(conn)
    try:
        for codigo,debe,haber in [(banco["cuenta_contable"],monto,0),(cuenta_cli[0],0,monto)]:
            conn.execute("""INSERT INTO libro_diario(fecha,cuenta,debe,haber,glosa,codigo_cuenta,asiento_id,lote_id,origen)
                         VALUES(?,?,?,?,?,?,?,?,?)""",
                         (mov["fecha"],plan.todos.get(codigo,codigo),debe,haber,glosa,codigo,asiento,lote,"CONCILIACION_COBRO_CLIENTE"))
        cur=conn.execute("""INSERT INTO pagos_clientes(fecha,cliente_id,monto,medio_pago,cuenta_banco,glosa,lote_id,monto_recibido,cartola_id)
                        VALUES(?,?,?,?,?,?,?,?,?)""",
                        (mov["fecha"],int(cliente_id),monto,"Banco",banco["cuenta_contable"],glosa,lote,monto,int(movimiento_id)))
        for r in docs.itertuples():
            conn.execute("INSERT INTO aplicaciones_clientes(pago_id,venta_id,monto) VALUES(?,?,?)",
                         (cur.lastrowid,int(r.id),clp_round(float(r.pendiente))))
        if apertura:
            conn.execute("""INSERT INTO sgci_aplicaciones_apertura_clientes(movimiento_id,cliente_id,monto,pago_id,fecha)
                            VALUES(?,?,?,?,?)""",(int(movimiento_id),int(cliente_id),apertura,cur.lastrowid,mov["fecha"]))
        conn.execute("""UPDATE cartola_bancaria SET conciliado=1,observacion=?,asiento_id=?,
                        match_tipo='CLIENTE',match_id=?,match_confianza=100 WHERE id=?""",
                     (glosa,asiento,int(cliente_id),int(movimiento_id)))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return asiento

def contabilizar_cobro_cliente_desde_cartola(conn, movimiento_id, cliente_id, venta_ids,
                                               cuenta_diferencia=None, glosa_diferencia=""):
    sgci_autorizar_operacion(conn, 'banco', 'contabilizar', 'Conciliación bancaria')
    """Conciliación de abono: aplica a facturas del cliente y lleva cualquier exceso a otra cuenta."""
    mov=conn.execute("SELECT * FROM cartola_bancaria WHERE id=?",(int(movimiento_id),)).fetchone()
    if not mov: raise ValueError("Movimiento bancario no encontrado.")
    if int(mov["conciliado"] or 0)==1: raise ValueError("Este movimiento ya está conciliado.")
    if float(mov["abono"] or 0)<=0: raise ValueError("El cobro debe corresponder a un abono/entrada bancaria.")
    if periodo_cerrado(conn,mov["fecha"]): raise ValueError("El período contable está cerrado.")
    banco=conn.execute("SELECT * FROM bancos WHERE id=?",(mov["banco_id"],)).fetchone()
    if not banco or not banco["cuenta_contable"]: raise ValueError("La cuenta bancaria no tiene cuenta contable configurada.")
    roles=cargar_roles(conn); rol_cli=roles.get("clientes")
    if not rol_cli: raise ValueError("La cuenta Clientes no está configurada.")
    cliente=conn.execute("SELECT * FROM clientes WHERE id=?",(int(cliente_id),)).fetchone()
    if not cliente: raise ValueError("Cliente no encontrado.")
    venta_ids=[int(x) for x in venta_ids]
    if not venta_ids: raise ValueError("Selecciona al menos una factura.")
    docs=documentos_pendientes_cliente(conn,cliente_id)
    docs=docs[docs["id"].isin(venta_ids)].copy()
    if docs.empty: raise ValueError("Las facturas seleccionadas ya no tienen saldo pendiente.")

    monto_banco=clp_round(float(mov["abono"] or 0))
    saldo_docs=clp_round(float(docs["pendiente"].sum()))
    monto_cliente=min(monto_banco,saldo_docs)
    diferencia=clp_round(monto_banco-monto_cliente)
    if diferencia>0 and not cuenta_diferencia:
        raise ValueError(f"Existe un sobrante de {money(diferencia)}. Selecciona la cuenta donde deseas registrarlo.")
    if diferencia>0 and cuenta_diferencia in (banco["cuenta_contable"],rol_cli[0]):
        raise ValueError("La cuenta del sobrante debe ser distinta de Banco y Clientes.")

    nombre=limpiar_texto(cliente["razon_social"] or cliente["nombre"] or "Cliente")
    folios=", ".join(str(x) for x in docs["folio"].tolist())
    glosa=f"Cobro cliente {nombre} - Doc. {folios}"
    asiento=siguiente_asiento(conn)+1
    lote="CONC-CLI-"+datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    plan=Plan(conn)
    try:
        # Banco por el total efectivamente recibido
        conn.execute("""INSERT INTO libro_diario(fecha,cuenta,debe,haber,glosa,codigo_cuenta,asiento_id,lote_id,origen)
                        VALUES(?,?,?,?,?,?,?,?,?)""",
                     (mov["fecha"],plan.todos.get(banco["cuenta_contable"],banco["cuenta_contable"]),
                      monto_banco,0,glosa,banco["cuenta_contable"],asiento,lote,"CONCILIACION_COBRO_CLIENTE"))
        # Clientes solo por lo aplicado a documentos
        conn.execute("""INSERT INTO libro_diario(fecha,cuenta,debe,haber,glosa,codigo_cuenta,asiento_id,lote_id,origen)
                        VALUES(?,?,?,?,?,?,?,?,?)""",
                     (mov["fecha"],plan.todos.get(rol_cli[0],rol_cli[0]),0,monto_cliente,glosa,rol_cli[0],asiento,lote,"CONCILIACION_COBRO_CLIENTE"))
        # Sobrante: normalmente Anticipos recibidos de clientes (pasivo)
        if diferencia>0:
            gd=limpiar_texto(glosa_diferencia) or f"Anticipo/sobrante cliente {nombre}"
            conn.execute("""INSERT INTO libro_diario(fecha,cuenta,debe,haber,glosa,codigo_cuenta,asiento_id,lote_id,origen)
                            VALUES(?,?,?,?,?,?,?,?,?)""",
                         (mov["fecha"],plan.todos.get(cuenta_diferencia,cuenta_diferencia),0,diferencia,gd,
                          cuenta_diferencia,asiento,lote,"CONCILIACION_DIFERENCIA_CLIENTE"))
        cur=conn.execute("""INSERT INTO pagos_clientes(fecha,cliente_id,monto,medio_pago,cuenta_banco,glosa,lote_id)
                            VALUES(?,?,?,?,?,?,?)""",
                         (mov["fecha"],int(cliente_id),monto_cliente,"Banco",banco["cuenta_contable"],glosa,lote))
        restante=monto_cliente
        aplicaciones=[]
        for r in docs.itertuples(index=False):
            if restante<=0: break
            aplicar=min(restante,clp_round(float(r.pendiente)))
            if aplicar>0:
                conn.execute("INSERT INTO aplicaciones_clientes(pago_id,venta_id,monto) VALUES(?,?,?)",(cur.lastrowid,int(r.id),aplicar))
                aplicaciones.append((int(r.id),aplicar)); restante=clp_round(restante-aplicar)
        obs=glosa + (f" | Sobrante {money(diferencia)} -> {cuenta_diferencia}" if diferencia>0 else "")
        conn.execute("""UPDATE cartola_bancaria SET conciliado=1,observacion=?,asiento_id=?,match_tipo='CLIENTE',match_id=?,match_confianza=100 WHERE id=?""",
                     (obs,asiento,int(cliente_id),int(movimiento_id)))
        conn.commit()
    except Exception:
        conn.rollback(); raise
    registrar_auditoria(conn,"COBRO CLIENTE DESDE CARTOLA",
                        f"Movimiento {movimiento_id} -> cliente {cliente_id}, aplicado {monto_cliente}, sobrante {diferencia}, asiento {asiento}")
    return asiento,aplicaciones,diferencia


def contabilizar_cobro_cliente_sin_documento(conn,movimiento_id,cliente_id,cuenta_anticipo):
    sgci_autorizar_operacion(conn, 'banco', 'contabilizar', 'Conciliación bancaria')
    """Registra un abono sin factura como anticipo/saldo a favor del cliente y lo deja en su auxiliar."""
    mov=conn.execute("SELECT * FROM cartola_bancaria WHERE id=?",(int(movimiento_id),)).fetchone()
    if not mov: raise ValueError("Movimiento bancario no encontrado.")
    if int(mov["conciliado"] or 0)==1: raise ValueError("Este movimiento ya está conciliado.")
    monto=clp_round(float(mov["abono"] or 0))
    if monto<=0: raise ValueError("Debe ser un abono/entrada bancaria.")
    banco=conn.execute("SELECT * FROM bancos WHERE id=?",(mov["banco_id"],)).fetchone()
    if not banco or not banco["cuenta_contable"]: raise ValueError("La cuenta bancaria no tiene cuenta contable configurada.")
    cliente=conn.execute("SELECT * FROM clientes WHERE id=?",(int(cliente_id),)).fetchone()
    if not cliente: raise ValueError("Cliente no encontrado.")
    if not cuenta_anticipo: raise ValueError("Selecciona la cuenta de anticipo/saldo a favor.")
    nombre=limpiar_texto(cliente["razon_social"] or cliente["nombre"] or "Cliente")
    glosa=f"Anticipo / cobro sin documento cliente {nombre}"
    asiento=siguiente_asiento(conn)+1; lote="CONC-CLI-SD-"+datetime.now().strftime("%Y%m%d-%H%M%S-%f"); plan=Plan(conn)
    try:
        for codigo,debe,haber in [(banco["cuenta_contable"],monto,0),(cuenta_anticipo,0,monto)]:
            conn.execute("""INSERT INTO libro_diario(fecha,cuenta,debe,haber,glosa,codigo_cuenta,asiento_id,lote_id,origen)
                            VALUES(?,?,?,?,?,?,?,?,?)""",
                         (mov["fecha"],plan.todos.get(codigo,codigo),debe,haber,glosa,codigo,asiento,lote,"CONCILIACION_ANTICIPO_CLIENTE"))
        # El anticipo todavía NO rebaja Clientes/CxC. Guardamos por separado el efectivo recibido
        # para que quede disponible y pueda aplicarse posteriormente a facturas.
        conn.execute("""INSERT INTO pagos_clientes
                        (fecha,cliente_id,monto,medio_pago,cuenta_banco,glosa,lote_id,monto_recibido,cuenta_anticipo,cartola_id)
                        VALUES(?,?,?,?,?,?,?,?,?,?)""",
                     (mov["fecha"],int(cliente_id),0,"Banco",banco["cuenta_contable"],glosa,lote,
                      monto,cuenta_anticipo,int(movimiento_id)))
        conn.execute("""UPDATE cartola_bancaria SET conciliado=1,observacion=?,asiento_id=?,match_tipo='CLIENTE_ANTICIPO',match_id=?,match_confianza=100 WHERE id=?""",
                     (glosa,asiento,int(cliente_id),int(movimiento_id)))
        conn.commit()
    except Exception:
        conn.rollback(); raise
    registrar_auditoria(conn,"ANTICIPO CLIENTE DESDE CARTOLA",f"Movimiento {movimiento_id} -> cliente {cliente_id}, monto {monto}, asiento {asiento}")
    return asiento


def anticipos_contables_sin_asignar(conn):
    """Anticipos contabilizados que todavía no tienen cliente asociado en el auxiliar."""
    cuentas=conn.execute("""
        SELECT codigo,nombre FROM plan_cuentas
        WHERE LOWER(nombre) LIKE '%anticipo%cliente%'
        ORDER BY codigo
    """).fetchall()
    codigos=[x["codigo"] for x in cuentas]
    if not codigos:
        return pd.DataFrame()

    marks=",".join("?" for _ in codigos)
    sql=f"""
        SELECT ld.asiento_id,
               MIN(ld.fecha) AS fecha,
               MAX(CASE WHEN ld.codigo_cuenta IN ({marks}) THEN ld.codigo_cuenta END) AS cuenta_anticipo,
               SUM(CASE WHEN ld.codigo_cuenta IN ({marks}) THEN COALESCE(ld.haber,0)-COALESCE(ld.debe,0) ELSE 0 END) AS monto,
               MAX(CASE WHEN ld.codigo_cuenta IN ({marks}) THEN ld.glosa END) AS glosa
        FROM libro_diario ld
        WHERE ld.asiento_id IS NOT NULL
        GROUP BY ld.asiento_id
        HAVING SUM(CASE WHEN ld.codigo_cuenta IN ({marks}) THEN COALESCE(ld.haber,0)-COALESCE(ld.debe,0) ELSE 0 END)>0.01

           -- Excluir anticipos que ya fueron asignados por esta herramienta.
           AND NOT EXISTS (
               SELECT 1 FROM pagos_clientes p
               WHERE p.asiento_origen_id=ld.asiento_id
           )

           -- Excluir anticipos que ya nacieron correctamente asociados desde Banco,
           -- aunque no tengan asiento_origen_id (casos CLIENTE_ANTICIPO como 562 y 563).
           AND NOT EXISTS (
               SELECT 1
               FROM cartola_bancaria cb
               WHERE cb.asiento_id=ld.asiento_id
                 AND cb.conciliado=1
                 AND cb.match_tipo='CLIENTE_ANTICIPO'
                 AND cb.match_id IS NOT NULL
           )

           -- Respaldo adicional: excluir pagos del auxiliar que ya estén enlazados
           -- a la misma cartola/asiento.
           AND NOT EXISTS (
               SELECT 1
               FROM pagos_clientes p
               JOIN cartola_bancaria cb ON cb.id=p.cartola_id
               WHERE cb.asiento_id=ld.asiento_id
                 AND p.cliente_id IS NOT NULL
           )
        ORDER BY MIN(ld.fecha),ld.asiento_id
    """
    params=codigos+codigos+codigos+codigos
    return pd.read_sql_query(sql,conn,params=params)


def asignar_anticipo_contable_a_cliente(conn, asiento_id, cliente_id):
    sgci_autorizar_operacion(conn,'cxc','editar','Pagos de clientes')
    """Vincula a un cliente un anticipo ya contabilizado. No crea ni modifica asientos."""
    disponibles=anticipos_contables_sin_asignar(conn)
    fila=disponibles.loc[disponibles["asiento_id"]==int(asiento_id)]
    if fila.empty:
        raise ValueError("El asiento ya fue asignado o no corresponde a un anticipo disponible.")
    r=fila.iloc[0]
    cliente=conn.execute("SELECT * FROM clientes WHERE id=?",(int(cliente_id),)).fetchone()
    if not cliente:
        raise ValueError("Cliente no encontrado.")
    monto=clp_round(float(r["monto"] or 0))
    if monto<=0:
        raise ValueError("El asiento no tiene saldo de anticipo asignable.")

    # Intentar enlazar también la cartola original, sin modificarla.
    cartola=conn.execute("""
        SELECT id,banco_id FROM cartola_bancaria
        WHERE asiento_id=? AND COALESCE(abono,0)>0
        ORDER BY id LIMIT 1
    """,(int(asiento_id),)).fetchone()
    cartola_id=int(cartola["id"]) if cartola else None
    cuenta_banco=None
    if cartola:
        banco=conn.execute("SELECT cuenta_contable FROM bancos WHERE id=?",(cartola["banco_id"],)).fetchone()
        cuenta_banco=banco["cuenta_contable"] if banco else None

    nombre=limpiar_texto(cliente["razon_social"] or cliente["nombre"] or "Cliente")
    glosa=limpiar_texto(r["glosa"] or f"Anticipo existente asignado a {nombre}")
    try:
        conn.execute("""INSERT INTO pagos_clientes
            (fecha,cliente_id,monto,medio_pago,cuenta_banco,glosa,lote_id,
             monto_recibido,cuenta_anticipo,cartola_id,asiento_origen_id)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (r["fecha"],int(cliente_id),0,"Anticipo existente",cuenta_banco,glosa,
             f"ASIG-ANT-{int(asiento_id)}",monto,r["cuenta_anticipo"],cartola_id,int(asiento_id)))
        # Si encontramos la cartola, añadimos solo trazabilidad de cliente cuando no existía.
        if cartola_id:
            conn.execute("""
                UPDATE cartola_bancaria
                SET match_tipo=CASE WHEN COALESCE(match_tipo,'')='' THEN 'CLIENTE_ANTICIPO' ELSE match_tipo END,
                    match_id=CASE WHEN match_id IS NULL THEN ? ELSE match_id END
                WHERE id=?
            """,(int(cliente_id),cartola_id))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    registrar_auditoria(conn,"ASIGNAR ANTICIPO EXISTENTE",
                        f"Asiento {asiento_id} -> cliente {cliente_id}, monto {monto}, sin nuevo asiento")
    return monto


def recuperar_anticipos_historicos_cliente(conn, cliente_id):
    sgci_autorizar_operacion(conn,'cxc','editar','Pagos de clientes')
    """Recupera anticipos CLIENTE_ANTICIPO creados por versiones antiguas sin alterar sus asientos."""
    movimientos=conn.execute("""
        SELECT cb.*, b.cuenta_contable AS cuenta_banco
        FROM cartola_bancaria cb
        LEFT JOIN bancos b ON b.id=cb.banco_id
        WHERE cb.conciliado=1
          AND cb.match_tipo='CLIENTE_ANTICIPO'
          AND cb.match_id=?
          AND COALESCE(cb.abono,0)>0
        ORDER BY cb.fecha,cb.id
    """,(int(cliente_id),)).fetchall()
    creados=0
    for mov in movimientos:
        existe=conn.execute(
            "SELECT id FROM pagos_clientes WHERE cartola_id=?",
            (int(mov["id"]),)
        ).fetchone()
        if existe:
            continue

        # Las versiones antiguas dejaron una fila monto=0. La reutilizamos si puede identificarse.
        viejo=conn.execute("""
            SELECT id FROM pagos_clientes
            WHERE cliente_id=? AND fecha=? AND COALESCE(monto,0)=0
              AND (cartola_id IS NULL OR cartola_id=0)
            ORDER BY id DESC LIMIT 1
        """,(int(cliente_id),mov["fecha"])).fetchone()

        cuenta_ant=None
        if mov["asiento_id"]:
            fila=conn.execute("""
                SELECT codigo_cuenta FROM libro_diario
                WHERE asiento_id=? AND COALESCE(haber,0)>0
                  AND codigo_cuenta<>?
                ORDER BY haber DESC LIMIT 1
            """,(mov["asiento_id"],mov["cuenta_banco"])).fetchone()
            if fila:
                cuenta_ant=fila[0]

        if not cuenta_ant:
            fila=conn.execute("""
                SELECT codigo FROM plan_cuentas
                WHERE LOWER(nombre) LIKE '%anticipo%cliente%'
                ORDER BY codigo LIMIT 1
            """).fetchone()
            cuenta_ant=fila[0] if fila else None

        monto=clp_round(float(mov["abono"] or 0))
        glosa=mov["observacion"] or mov["descripcion"] or "Anticipo de cliente recuperado"
        if viejo:
            conn.execute("""
                UPDATE pagos_clientes
                SET monto_recibido=?, cuenta_anticipo=?, cartola_id=?,
                    glosa=COALESCE(NULLIF(glosa,''),?)
                WHERE id=?
            """,(monto,cuenta_ant,int(mov["id"]),glosa,int(viejo["id"])))
        else:
            conn.execute("""INSERT INTO pagos_clientes
                (fecha,cliente_id,monto,medio_pago,cuenta_banco,glosa,lote_id,monto_recibido,cuenta_anticipo,cartola_id)
                VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (mov["fecha"],int(cliente_id),0,"Banco",mov["cuenta_banco"],glosa,
                 f"RECUP-CARTOLA-{int(mov['id'])}",monto,cuenta_ant,int(mov["id"])))
        creados+=1
    if creados:
        conn.commit()
    return creados


# ============================================================
# SGCI: CONCILIACIÓN DOCUMENTAL Y SALDOS DE OTROS EJERCICIOS
# Estas operaciones NO crean asientos, ni modifican RCV.
# ============================================================


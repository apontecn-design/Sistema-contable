# CONTEM: componente extraído del app.py original; ejecución secuencial compartida.
from datetime import datetime
import hashlib
from pathlib import PurePath


def _tes_validar_adjunto(nombre, datos):
    nombre = str(nombre or '').replace('\\', '/').rsplit('/', 1)[-1]
    extension = PurePath(nombre).suffix.lower()
    firmas = {'.pdf': (b'%PDF-',), '.jpg': (b'\xff\xd8\xff',), '.jpeg': (b'\xff\xd8\xff',),
              '.png': (b'\x89PNG\r\n\x1a\n',), '.xlsx': (b'PK\x03\x04',),
              '.xls': (b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1',)}
    if extension not in firmas or not isinstance(datos, bytes) or not datos or len(datos) > 5*1024*1024:
        raise ValueError('Adjunta PDF, imagen o Excel válido de hasta 5 MB.')
    if not any(datos.startswith(firma) for firma in firmas[extension]):
        raise ValueError('El contenido del adjunto no corresponde al tipo de archivo.')
    return nombre, datos, hashlib.sha256(datos).hexdigest()


def tes_guardar_solicitud(conn, fecha, beneficiario, proveedor_id, concepto, fecha_limite,
                         observacion, detalles, adjunto=None):
    sgci_autorizar_operacion(conn, 'tesoreria', 'crear', 'Solicitudes de fondos')
    from datetime import date as _fecha
    fecha, fecha_limite = _fecha.fromisoformat(str(fecha)), _fecha.fromisoformat(str(fecha_limite))
    if fecha_limite < fecha or not str(beneficiario).strip() or not str(concepto).strip() or not detalles:
        raise ValueError('Revisa beneficiario, concepto, fechas y detalle de la solicitud.')
    lineas = []
    for d in detalles:
        monto = int(d['monto'])
        if monto <= 0 or monto != d['monto'] or not str(d['descripcion']).strip():
            raise ValueError('Cada línea necesita descripción y monto entero positivo en CLP.')
        compra_id = d.get('compra_id')
        if compra_id is not None:
            compra = conn.execute('SELECT proveedor_id FROM compras WHERE id=?', (compra_id,)).fetchone()
            if not compra or not proveedor_id or compra['proveedor_id'] != proveedor_id:
                raise ValueError('La factura no corresponde al proveedor de la solicitud.')
        lineas.append((str(d['tipo']), str(d.get('referencia') or ''), str(d['descripcion']).strip(),
                       monto, compra_id, d.get('tratamiento')))
    archivo = _tes_validar_adjunto(*adjunto) if adjunto else None
    with conn:
        cur = conn.execute('''INSERT INTO tes_solicitudes
            (fecha,beneficiario,proveedor_id,concepto,fecha_limite,moneda,estado,observacion,fecha_creacion)
            VALUES(?,?,?,?,?,'CLP','BORRADOR',?,?)''',
            (fecha.isoformat(),str(beneficiario).strip(),proveedor_id,str(concepto).strip(),
             fecha_limite.isoformat(),str(observacion).strip(),datetime.now().isoformat(timespec='seconds')))
        sid = cur.lastrowid
        conn.executemany('''INSERT INTO tes_solicitud_detalle
            (solicitud_id,tipo,referencia,descripcion,monto,compra_id,tratamiento) VALUES(?,?,?,?,?,?,?)''',
            [(sid,*d) for d in lineas])
        if archivo:
            conn.execute('INSERT INTO tes_adjuntos(solicitud_id,nombre,contenido,sha256,fecha) VALUES(?,?,?,?,?)',
                         (sid,*archivo,datetime.now().isoformat(timespec='seconds')))
        conn.execute('INSERT INTO tes_eventos(solicitud_id,fecha,accion,usuario) VALUES(?,?,?,?)',
                     (sid,datetime.now().isoformat(timespec='seconds'),'CREAR',sgci_identidad_actual()))
    return sid


def tes_cambiar_estado(conn, sid, nuevo):
    transiciones = {'ENVIADA': ('BORRADOR','crear','fecha_envio'),
                    'APROBADA': ('ENVIADA','aprobar','fecha_aprobacion'),
                    'RECHAZADA': ('ENVIADA','aprobar','fecha_rechazo')}
    if nuevo not in transiciones:
        raise ValueError('Transición de solicitud no permitida.')
    anterior, accion, campo = transiciones[nuevo]
    sgci_autorizar_operacion(conn, 'tesoreria', accion, 'Solicitudes de fondos')
    with conn:
        cur = conn.execute(f'UPDATE tes_solicitudes SET estado=?,{campo}=? WHERE id=? AND estado=?',
                           (nuevo,datetime.now().isoformat(timespec='seconds'),sid,anterior))
        if cur.rowcount != 1:
            raise ValueError('La solicitud cambió de estado o no existe. Actualiza la pantalla.')
        conn.execute('INSERT INTO tes_eventos(solicitud_id,fecha,accion,usuario) VALUES(?,?,?,?)',
                     (sid,datetime.now().isoformat(timespec='seconds'),nuevo,sgci_identidad_actual()))


def tes_guardar_clasificacion(conn, sid, seleccion):
    sgci_autorizar_operacion(conn, 'tesoreria', 'contabilizar', 'Confirmación de pagos')
    plan = Plan(conn).hojas
    if not seleccion or any(codigo not in plan for codigo in seleccion.values()):
        raise ValueError('Selecciona cuentas imputables para todas las líneas.')
    with conn:
        for did, codigo in seleccion.items():
            cur = conn.execute('''UPDATE tes_solicitud_detalle SET cuenta_contable=?
                WHERE id=? AND solicitud_id=? AND compra_id IS NULL AND EXISTS
                (SELECT 1 FROM tes_solicitudes WHERE id=? AND estado IN
                 ('BORRADOR','ENVIADA','APROBADA','PENDIENTE_CONTABILIZACION'))''', (codigo,did,sid,sid))
            if cur.rowcount != 1:
                raise ValueError('La línea no pertenece a una solicitud modificable.')


def tes_confirmar_pago(conn, sid, medio, fecha_pago, banco_id, banco_descripcion,
                       referencia, nombre, contenido, observaciones=''):
    sgci_autorizar_operacion(conn, 'tesoreria', 'confirmar', 'Confirmación de pagos')
    from datetime import date as _fecha
    _fecha.fromisoformat(str(fecha_pago))
    if medio not in ('TRANSFERENCIA','CHEQUE') or not str(referencia).strip():
        raise ValueError('Selecciona el medio y la referencia de pago.')
    nombre, contenido, _ = _tes_validar_adjunto(nombre,contenido)
    if PurePath(nombre).suffix.lower() not in ('.pdf','.png','.jpg','.jpeg'):
        raise ValueError('El comprobante de pago debe ser PDF o imagen.')
    with conn:
        cur = conn.execute("UPDATE tes_solicitudes SET estado='PENDIENTE_CONTABILIZACION' WHERE id=? AND estado='APROBADA'", (sid,))
        if cur.rowcount != 1:
            raise ValueError('La solicitud ya no está aprobada o el pago ya fue confirmado.')
        banco = conn.execute('SELECT cuenta_contable FROM bancos WHERE id=? AND activo=1',(banco_id,)).fetchone()
        if not banco or not banco['cuenta_contable']:
            raise ValueError('Selecciona un banco activo con cuenta contable.')
        faltan = conn.execute("SELECT COUNT(*) FROM tes_solicitud_detalle WHERE solicitud_id=? AND compra_id IS NULL AND COALESCE(cuenta_contable,'')=''",(sid,)).fetchone()[0]
        if faltan:
            raise ValueError('Guarda la cuenta contable de cada línea antes de confirmar.')
        conn.execute('''INSERT INTO tes_confirmaciones_pago
            (solicitud_id,medio,fecha_pago,banco_descripcion,referencia,nombre_comprobante,
             comprobante,observaciones,fecha_registro,banco_id)
            VALUES(?,?,?,?,?,?,?,?,?,?)''', (sid,medio,str(fecha_pago),str(banco_descripcion),
             str(referencia).strip(),nombre,contenido,str(observaciones),datetime.now().isoformat(timespec='seconds'),banco_id))
        conn.execute('INSERT INTO tes_eventos(solicitud_id,fecha,accion,usuario) VALUES(?,?,?,?)',
                     (sid,datetime.now().isoformat(timespec='seconds'),'CONFIRMAR',sgci_identidad_actual()))

def tes_crear_tablas(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS tes_solicitudes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fecha TEXT NOT NULL,
        beneficiario TEXT NOT NULL,
        proveedor_id INTEGER,
        concepto TEXT NOT NULL,
        fecha_limite TEXT,
        moneda TEXT NOT NULL DEFAULT 'CLP',
        estado TEXT NOT NULL DEFAULT 'BORRADOR',
        observacion TEXT,
        fecha_creacion TEXT NOT NULL,
        fecha_envio TEXT,
        fecha_aprobacion TEXT,
        fecha_rechazo TEXT,
        UNIQUE(id)
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS tes_solicitud_detalle (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        solicitud_id INTEGER NOT NULL REFERENCES tes_solicitudes(id),
        tipo TEXT NOT NULL,
        referencia TEXT,
        descripcion TEXT NOT NULL,
        monto INTEGER NOT NULL CHECK(monto > 0)
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS tes_confirmaciones_pago (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        solicitud_id INTEGER NOT NULL UNIQUE REFERENCES tes_solicitudes(id),
        medio TEXT NOT NULL CHECK(medio IN ('TRANSFERENCIA','CHEQUE')),
        fecha_pago TEXT NOT NULL,
        banco_descripcion TEXT NOT NULL,
        referencia TEXT NOT NULL,
        nombre_comprobante TEXT NOT NULL,
        comprobante BLOB NOT NULL,
        observaciones TEXT,
        fecha_registro TEXT NOT NULL,
        estado TEXT NOT NULL DEFAULT 'PENDIENTE_CONTABILIZACION',
        CHECK(length(comprobante) > 0)
    )""")
    # Extensión no destructiva para vincular solicitudes con compras contabilizadas.
    cols = {r[1] for r in conn.execute('PRAGMA table_info(tes_solicitud_detalle)').fetchall()}
    if 'compra_id' not in cols:
        conn.execute('ALTER TABLE tes_solicitud_detalle ADD COLUMN compra_id INTEGER')
    if 'tratamiento' not in cols:
        conn.execute('ALTER TABLE tes_solicitud_detalle ADD COLUMN tratamiento TEXT')
    for col, typ in [('banco_id','INTEGER'),('asiento_id','INTEGER'),('pago_proveedor_id','INTEGER'),('fecha_contabilizacion','TEXT'),('cuenta_contrapartida','TEXT'),('error_contabilizacion','TEXT')]:
        agregar_columna(conn, 'tes_confirmaciones_pago', col, typ)
    agregar_columna(conn, 'tes_solicitud_detalle', 'cuenta_contable', 'TEXT')
    agregar_columna(conn, 'tes_solicitudes', 'observacion_revision', 'TEXT')
    agregar_columna(conn, 'tes_solicitudes', 'fecha_revision', 'TEXT')
    conn.execute("""CREATE TABLE IF NOT EXISTS tes_eventos (
        id INTEGER PRIMARY KEY AUTOINCREMENT, solicitud_id INTEGER NOT NULL,
        fecha TEXT NOT NULL, accion TEXT NOT NULL, observacion TEXT,
        usuario TEXT)""")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_tes_asiento ON tes_confirmaciones_pago(asiento_id) WHERE asiento_id IS NOT NULL")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_tes_solicitudes_estado ON tes_solicitudes(estado)")
    conn.execute('''CREATE TABLE IF NOT EXISTS tes_adjuntos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        solicitud_id INTEGER NOT NULL REFERENCES tes_solicitudes(id),
        nombre TEXT NOT NULL, contenido BLOB NOT NULL, sha256 TEXT NOT NULL,
        fecha TEXT NOT NULL, UNIQUE(solicitud_id,sha256))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS tes_vinculos_obligacion (
        detalle_id INTEGER PRIMARY KEY,linea_origen_id INTEGER NOT NULL,huella TEXT NOT NULL,
        confirmado_por TEXT NOT NULL,fecha TEXT NOT NULL)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS tes_aplicaciones_obligacion (
        detalle_id INTEGER PRIMARY KEY,linea_origen_id INTEGER NOT NULL,monto INTEGER NOT NULL CHECK(monto>0),
        asiento_pago INTEGER NOT NULL)''')
    conn.commit()


def _tes_origen_obligacion(conn,linea_id):
    import json,math
    r=conn.execute('SELECT * FROM libro_diario WHERE id=?',(int(linea_id),)).fetchone()
    if not r or not r['asiento_id'] or not str(r['codigo_cuenta']).startswith('2.') or r['codigo_cuenta'] not in Plan(conn).hojas:
        raise ValueError('Selecciona una línea imputable de pasivo ya contabilizado.')
    monto=float(r['haber'] or 0)
    if not math.isfinite(monto) or monto<=0 or monto!=int(monto) or float(r['debe'] or 0)!=0:
        raise ValueError('El origen debe ser una obligación acreedora entera en CLP.')
    if str(r['origen'] or '').upper().startswith('REV') or r['origen']=='TESORERIA':
        raise ValueError('Un reverso o pago no puede ser el origen de una obligación.')
    origen_texto=str(r['origen'] or '').upper()
    if any(palabra in origen_texto for palabra in ('RCV','DTE','NOMINA','NÓMINA','CONCILIACION','CONCILIACIÓN')):
        raise ValueError('Este origen pertenece a un auxiliar; utiliza el flujo de documentos o nómina correspondiente.')
    if r['lote_id'] and conn.execute('SELECT 1 FROM compras WHERE lote_id=? LIMIT 1',(r['lote_id'],)).fetchone():
        raise ValueError('La obligación pertenece a una compra; utiliza el pago del documento.')
    asiento=[dict(x) for x in conn.execute('SELECT * FROM libro_diario WHERE asiento_id=? ORDER BY id',(r['asiento_id'],))]
    if any(not math.isfinite(float(x[c] or 0)) or float(x[c] or 0)<0 for x in asiento for c in ('debe','haber')) or abs(sum(float(x['debe'] or 0)-float(x['haber'] or 0) for x in asiento))>0.01:
        raise ValueError('El asiento de origen no está cuadrado.')
    huella=hashlib.sha256(json.dumps(asiento,sort_keys=True,allow_nan=False).encode('utf8')).hexdigest()
    aplicado=conn.execute('SELECT COALESCE(SUM(monto),0) FROM tes_aplicaciones_obligacion WHERE linea_origen_id=?',(r['id'],)).fetchone()[0]
    saldo_cuenta=conn.execute('SELECT COALESCE(SUM(haber-debe),0) FROM libro_diario WHERE codigo_cuenta=?',(r['codigo_cuenta'],)).fetchone()[0]
    return {'id':r['id'],'cuenta':r['codigo_cuenta'],'monto':int(monto),'disponible':min(int(monto)-int(aplicado),int(round(float(saldo_cuenta)))), 'huella':huella}


def tes_obligaciones_disponibles(conn):
    sgci_autorizar_operacion(conn,'tesoreria','ver','Confirmación de pagos')
    sgci_autorizar_operacion(conn,'contabilidad','ver','Libro Diario')
    filas=conn.execute("""SELECT id,fecha,asiento_id,codigo_cuenta,glosa FROM libro_diario
        WHERE codigo_cuenta LIKE '2.%' AND haber>0 AND COALESCE(debe,0)=0
        AND UPPER(COALESCE(origen,'')) NOT LIKE 'REV%' AND COALESCE(origen,'')<>'TESORERIA'
        ORDER BY fecha DESC,id DESC""").fetchall()
    datos=[]
    for r in filas:
        try:origen=_tes_origen_obligacion(conn,r['id'])
        except ValueError:continue
        if origen['disponible']>0:datos.append({**dict(r),'disponible':origen['disponible']})
    return pd.DataFrame(datos,columns=['id','fecha','asiento_id','codigo_cuenta','glosa','disponible'])


def tes_vincular_obligacion(conn,sid,detalle_id,linea_id,confirmacion):
    sgci_autorizar_operacion(conn,'tesoreria','contabilizar','Confirmación de pagos')
    sgci_autorizar_operacion(conn,'contabilidad','ver','Libro Diario')
    if confirmacion is not True:raise ValueError('Confirma que la obligación sigue pendiente y no fue pagada por otro medio.')
    if conn.in_transaction:raise RuntimeError('Finaliza la operación pendiente antes de vincular.')
    with conn:
        conn.execute('BEGIN IMMEDIATE')
        sgci_autorizar_operacion(conn,'tesoreria','contabilizar','Confirmación de pagos')
        sgci_autorizar_operacion(conn,'contabilidad','ver','Libro Diario')
        d=conn.execute('''SELECT d.* FROM tes_solicitud_detalle d JOIN tes_solicitudes s ON s.id=d.solicitud_id
            WHERE d.id=? AND d.solicitud_id=? AND s.estado IN ('BORRADOR','ENVIADA','APROBADA','PENDIENTE_CONTABILIZACION')''',(int(detalle_id),int(sid))).fetchone()
        if not d or d['compra_id'] is not None or d['tratamiento']!='Obligación ya contabilizada':
            raise ValueError('La línea no es una obligación modificable sin DTE.')
        origen=_tes_origen_obligacion(conn,linea_id)
        if int(d['monto'])>origen['disponible']:raise ValueError('La obligación de origen no tiene saldo suficiente.')
        conn.execute('''INSERT INTO tes_vinculos_obligacion(detalle_id,linea_origen_id,huella,confirmado_por,fecha)
            VALUES(?,?,?,?,?) ON CONFLICT(detalle_id) DO UPDATE SET linea_origen_id=excluded.linea_origen_id,
            huella=excluded.huella,confirmado_por=excluded.confirmado_por,fecha=excluded.fecha''',
            (d['id'],origen['id'],origen['huella'],sgci_identidad_actual(),datetime.now().isoformat(timespec='seconds')))
        conn.execute('UPDATE tes_solicitud_detalle SET cuenta_contable=? WHERE id=?',(origen['cuenta'],d['id']))
        conn.execute('INSERT INTO tes_eventos(solicitud_id,fecha,accion,usuario,observacion) VALUES(?,?,?,?,?)',
            (sid,datetime.now().isoformat(timespec='seconds'),'VINCULAR OBLIGACION',sgci_identidad_actual(),f"Línea {d['id']} -> diario {origen['id']}; obligación pendiente sin pago por otro medio confirmado"))


def tes_contabilizar_pago(conn, sid, banco_id, cuenta_sin_dte=None):
    sgci_autorizar_operacion(conn, 'tesoreria', 'contabilizar', 'Confirmación de pagos')
    """Contabilización atómica y única. No registra cartola ni conciliación."""
    if conn.in_transaction:raise RuntimeError('Finaliza la operación pendiente antes de contabilizar.')
    try:
        conn.execute('BEGIN IMMEDIATE')
        sgci_autorizar_operacion(conn,'tesoreria','contabilizar','Confirmación de pagos')
        sol=conn.execute('SELECT * FROM tes_solicitudes WHERE id=?',(sid,)).fetchone()
        pago=conn.execute('SELECT * FROM tes_confirmaciones_pago WHERE solicitud_id=?',(sid,)).fetchone()
        if not sol or not pago or sol['estado'] != 'PENDIENTE_CONTABILIZACION' or pago['asiento_id'] is not None:
            raise ValueError('Esta solicitud no está pendiente o ya fue contabilizada.')
        if periodo_cerrado(conn,pago['fecha_pago']):
            raise ValueError('El período contable de la fecha del pago está cerrado.')
        banco=conn.execute('SELECT * FROM bancos WHERE id=? AND activo=1',(int(banco_id),)).fetchone()
        if not banco or not banco['cuenta_contable']:
            raise ValueError('Selecciona un banco activo con cuenta contable configurada.')
        plan=Plan(conn).hojas
        cuenta_banco=str(banco['cuenta_contable']).strip()
        if cuenta_banco not in plan:
            raise ValueError('La cuenta contable del banco no es imputable o no existe.')
        detalles=conn.execute('SELECT * FROM tes_solicitud_detalle WHERE solicitud_id=?',(sid,)).fetchall()
        if not detalles:
            raise ValueError('La solicitud no tiene detalle.')
        movimientos=[]
        aplicaciones=[]
        obligaciones=[]
        for d in detalles:
            monto=int(d['monto'])
            if monto <= 0:
                raise ValueError('Monto inválido.')
            if d['compra_id'] is not None:
                compra=conn.execute('SELECT * FROM compras WHERE id=?',(int(d['compra_id']),)).fetchone()
                if not compra or not sol['proveedor_id'] or compra['proveedor_id'] != sol['proveedor_id']:
                    raise ValueError('La factura no pertenece al proveedor seleccionado.')
                if int(compra['tipo_doc'] or 0) in (60,61,52):
                    raise ValueError('Este tipo de documento requiere revisión antes del pago.')
                saldo=conn.execute('SELECT ABS(COALESCE(monto_total,0)) - COALESCE((SELECT SUM(ABS(monto)) FROM aplicaciones_proveedores WHERE compra_id=?),0) FROM compras WHERE id=?',(compra['id'],compra['id'])).fetchone()[0]
                reservado=sum(x[1] for x in aplicaciones if x[0]==compra['id'])
                if monto > round(saldo-reservado):
                    raise ValueError(f'El documento {compra["folio"]} no tiene saldo suficiente.')
                rol=cargar_roles(conn).get('proveedores')
                cuenta=rol[0] if rol else None
                aplicaciones.append((compra['id'],monto))
            else:
                tratamiento=str(d['tratamiento'] or '').strip()
                if not tratamiento:
                    raise ValueError('Indica el tratamiento contable del desembolso.')
                if tratamiento == 'Obligación ya contabilizada':
                    vinculo=conn.execute('SELECT * FROM tes_vinculos_obligacion WHERE detalle_id=?',(d['id'],)).fetchone()
                    if not vinculo:raise ValueError('Vincula el documento u obligación original antes de contabilizar para evitar duplicar el gasto.')
                    origen=_tes_origen_obligacion(conn,vinculo['linea_origen_id'])
                    if origen['huella']!=vinculo['huella']:raise ValueError('El asiento de origen cambió; vuelve a revisar y vincular la obligación.')
                    reservado=sum(x[2] for x in obligaciones if x[1]==origen['id'])
                    if monto>origen['disponible']-reservado:raise ValueError('La obligación de origen no tiene saldo suficiente.')
                    cuenta=origen['cuenta']
                    if d['cuenta_contable']!=cuenta:raise ValueError('La cuenta clasificada no coincide con la obligación de origen.')
                    obligaciones.append((d['id'],origen['id'],monto,cuenta))
                else:
                    cuenta=str(d['cuenta_contable'] or cuenta_sin_dte or pago['cuenta_contrapartida'] or '').strip()
                if not cuenta:
                    raise ValueError(f'Falta asignar la cuenta contable a la línea: {d["descripcion"]}.')
                if tratamiento == 'Pendiente de reconocimiento contable' and not cuenta.startswith(('4.','5.','6.','7.')):
                    raise ValueError('Para un gasto directo selecciona una cuenta de resultados apropiada.')
                if tratamiento == 'Anticipo a proveedor / beneficiario' and not cuenta.startswith('1.'):
                    raise ValueError('Un anticipo debe imputarse a una cuenta de activo.')
            if cuenta not in plan or cuenta == cuenta_banco:
                raise ValueError('La cuenta de contrapartida no es imputable o coincide con el banco.')
            movimientos.append((cuenta,monto))
        total=sum(m for _,m in movimientos)
        for cuenta in {o[3] for o in obligaciones}:
            saldo=conn.execute('SELECT COALESCE(SUM(haber-debe),0) FROM libro_diario WHERE codigo_cuenta=?',(cuenta,)).fetchone()[0]
            if sum(o[2] for o in obligaciones if o[3]==cuenta)>round(float(saldo)):
                raise ValueError('El pasivo no tiene saldo acreedor suficiente para este pago.')
        asiento=siguiente_asiento(conn)+1
        glosa=f'Tesorería SF-{sid:06d} · {sol["beneficiario"]} · {pago["referencia"]}'
        for cuenta,monto in movimientos:
            nomina_asiento_linea(conn,pago['fecha_pago'],cuenta,monto,0,glosa,asiento,'TESORERIA')
        nomina_asiento_linea(conn,pago['fecha_pago'],cuenta_banco,0,total,glosa,asiento,'TESORERIA')
        pago_proveedor_id=None
        if aplicaciones:
            if len(aplicaciones) != len(detalles):
                raise ValueError('No se admite mezclar DTE y otros conceptos en la misma solicitud.')
            cur=conn.execute('INSERT INTO pagos_proveedores(fecha,proveedor_id,monto,medio_pago,cuenta_banco,glosa,lote_id) VALUES(?,?,?,?,?,?,?)',
                (pago['fecha_pago'],sol['proveedor_id'],total,pago['medio'],cuenta_banco,glosa,f'TES-SF-{sid:06d}'))
            pago_proveedor_id=cur.lastrowid
            for compra_id,monto in aplicaciones:
                conn.execute('INSERT INTO aplicaciones_proveedores(pago_id,compra_id,monto) VALUES(?,?,?)',(pago_proveedor_id,compra_id,monto))
        cur=conn.execute("""UPDATE tes_confirmaciones_pago SET banco_id=?,asiento_id=?,pago_proveedor_id=? ,
            fecha_contabilizacion=?,estado='CONTABILIZADO',error_contabilizacion=NULL WHERE solicitud_id=? AND asiento_id IS NULL""",
            (int(banco_id),asiento,pago_proveedor_id,datetime.now().isoformat(timespec='seconds'),sid))
        if cur.rowcount != 1:
            raise ValueError('El pago ya fue contabilizado.')
        conn.execute("UPDATE tes_solicitudes SET estado='CONTABILIZADA' WHERE id=? AND estado='PENDIENTE_CONTABILIZACION'",(sid,))
        for did,linea,monto,cuenta in obligaciones:
            conn.execute('INSERT INTO tes_aplicaciones_obligacion(detalle_id,linea_origen_id,monto,asiento_pago) VALUES(?,?,?,?)',(did,linea,monto,asiento))
        conn.execute('INSERT INTO tes_eventos(solicitud_id,fecha,accion,usuario,observacion) VALUES(?,?,?,?,?)',
            (sid,datetime.now().isoformat(timespec='seconds'),'CONTABILIZAR',sgci_identidad_actual(),f'Asiento {asiento}; obligaciones vinculadas: {len(obligaciones)}'))
        conn.commit()
        return asiento
    except Exception:
        conn.rollback()
        raise


def tes_descargar_adjunto(conn, sid, adjunto_id):
    sgci_autorizar_operacion(conn, 'tesoreria', 'ver', 'Solicitudes de fondos')
    sgci_autorizar_operacion(conn, 'tesoreria', 'exportar', 'Solicitudes de fondos')
    fila = conn.execute('SELECT nombre,contenido FROM tes_adjuntos WHERE id=? AND solicitud_id=?',
                        (adjunto_id,sid)).fetchone()
    if not fila:
        raise ValueError('Adjunto no disponible para esta solicitud.')
    return fila['nombre'], bytes(fila['contenido'])


def pantalla_tesoreria(conn):
    sgci_autorizar_operacion(conn, 'tesoreria', 'ver', 'Solicitudes de fondos')
    st.title('💼 Tesorería · Solicitudes de fondos')
    st.caption('Gestión de solicitudes, confirmación de pagos y trazabilidad contable y bancaria.')
    tes_crear_tablas(conn)
    resumen_tes=pd.read_sql_query('SELECT estado,COUNT(*) AS cantidad FROM tes_solicitudes GROUP BY estado',conn)
    estados_tes=dict(zip(resumen_tes.estado,resumen_tes.cantidad)) if not resumen_tes.empty else {}
    c1,c2,c3,c4=st.columns(4)
    c1.metric('Borradores',estados_tes.get('BORRADOR',0))
    c2.metric('Enviadas / aprobadas',estados_tes.get('ENVIADA',0)+estados_tes.get('APROBADA',0))
    c3.metric('Pendientes de contabilizar',estados_tes.get('PENDIENTE_CONTABILIZACION',0))
    c4.metric('Contabilizadas',estados_tes.get('CONTABILIZADA',0))
    tab_nueva,tab_listado,tab_historial=st.tabs(['➕ Nueva solicitud','📋 Solicitudes registradas','🕘 Historial'])
    with tab_nueva:
        proveedores = pd.read_sql_query("SELECT id, rut, COALESCE(NULLIF(razon_social, ''), nombre) AS nombre FROM proveedores ORDER BY nombre", conn)
        opciones = {'Beneficiario externo / sin ficha de proveedor': None}
        for _, p in proveedores.iterrows():
            opciones[f"{p['nombre']} · {p['rut'] or 'Sin RUT'} · ID {int(p['id'])}"] = int(p['id'])
        # Fuera del formulario: permite refrescar las facturas al cambiar proveedor/tipo.
        opcion = st.selectbox('Proveedor / beneficiario registrado', list(opciones), key='tes2_proveedor')
        tipo = st.selectbox('Origen del documento', ['DTE contabilizado', 'Documento sin DTE', 'Anticipo', 'Otro'], key='tes2_tipo')
        pid_previo = opciones[opcion]
        compra_elegida = None
        doc_elegido = None
        tratamiento = None
        if tipo == 'DTE contabilizado':
            if pid_previo is None:
                st.warning('Selecciona un proveedor registrado para buscar facturas contabilizadas desde RCV.')
            else:
                docs = documentos_pendientes_proveedor(conn, pid_previo)
                # Las compras con saldo en el auxiliar se muestran por identificador interno.
                if docs.empty:
                    st.warning('Este proveedor no tiene facturas contabilizadas con saldo pendiente.')
                else:
                    opciones_docs = {f"ID {int(r.id)} · {r.fecha or 'Sin fecha'} · Tipo {r.tipo_doc} · Folio {r.folio or '—'} · Saldo {money(r.pendiente)}": int(r.id) for r in docs.itertuples(index=False)}
                    doc_label = st.selectbox('Factura contabilizada pendiente', list(opciones_docs), key='tes2_factura')
                    compra_elegida = opciones_docs[doc_label]
                    doc_elegido = docs.loc[docs.id == compra_elegida].iloc[0]
                    st.caption('Primera integración: una factura por solicitud. Posteriormente permitiremos varias facturas del mismo proveedor.')
        elif tipo in ('Documento sin DTE','Otro'):
            tratamiento = st.radio('Tratamiento contable del documento',
                ['Pendiente de reconocimiento contable', 'Obligación ya contabilizada'], key='tes2_tratamiento')
            st.caption('Si el gasto aún no se ha reconocido, elige pendiente de reconocimiento; si ya está contabilizado, debe identificarse la obligación de origen antes del pago.')
        elif tipo == 'Anticipo':
            tratamiento = 'Anticipo a proveedor / beneficiario'
            st.caption('El anticipo no se considera automáticamente gasto.')
        st.caption('Puedes incluir varias partidas en una misma transferencia. Para solicitudes sin DTE, agrega tantas filas como conceptos necesites.')
        partidas_nuevas = None
        if tipo != 'DTE contabilizado':
            if 'tes_partidas_nuevas' not in st.session_state:
                st.session_state['tes_partidas_nuevas'] = pd.DataFrame([
                    {'Descripción':'','Referencia':'','Monto CLP':0}])
            partidas_nuevas = st.data_editor(st.session_state['tes_partidas_nuevas'],
                num_rows='dynamic', hide_index=True, use_container_width=True,
                column_config={'Monto CLP':st.column_config.NumberColumn('Monto CLP',min_value=0,step=1)},
                key='tes_partidas_editor')
        with st.form('tes_nueva_solicitud', clear_on_submit=False):
            c1, c2 = st.columns(2)
            fecha = c1.date_input('Fecha de solicitud', value=date.today())
            fecha_limite = c2.date_input('Fecha límite de pago', value=date.today())
            beneficiario = st.text_input('Nombre del beneficiario (obligatorio si es externo)')
            concepto = st.text_input('Concepto de la solicitud')
            referencia = st.text_input('Número de factura, boleta o referencia (opcional)',
                value=str(doc_elegido['folio'] or '') if doc_elegido is not None else '')
            descripcion = st.text_input('Descripción del documento / desembolso')
            monto = st.number_input('Monto solicitado (CLP)', min_value=0, step=1,
                value=int(round(float(doc_elegido['pendiente']))) if doc_elegido is not None else 0)
            observacion = st.text_area('Observaciones', height=80)
            archivo_solicitud = st.file_uploader('Adjunto de la solicitud (PDF, imagen o Excel; máximo 5 MB)',
                type=['pdf','jpg','jpeg','png','xls','xlsx'], key='tes_adjunto_solicitud')
            guardar = st.form_submit_button('Guardar solicitud en borrador', type='primary')
        if guardar:
            sgci_exigir_permiso(conn, 'tesoreria', 'crear', 'Solicitudes de fondos')
            pid = opciones[opcion]
            if pid is not None:
                beneficiario = str(proveedores.loc[proveedores.id == pid, 'nombre'].iloc[0])
            beneficiario = beneficiario.strip()
            lineas_solicitud = []
            if partidas_nuevas is not None:
                for _, reg in partidas_nuevas.iterrows():
                    desc = str(reg.get('Descripción') or '').strip()
                    monto_fila = clp_round(reg.get('Monto CLP') or 0)
                    ref_fila = str(reg.get('Referencia') or '').strip()
                    if desc or monto_fila:
                        lineas_solicitud.append((desc,ref_fila,monto_fila))
            else:
                lineas_solicitud = [(descripcion.strip(),referencia.strip(),int(monto))]
            if not beneficiario or not concepto.strip() or not lineas_solicitud or any(not d or m <= 0 for d,r,m in lineas_solicitud):
                st.error('Completa beneficiario, concepto y cada línea con descripción y monto positivo.')
            elif tipo == 'DTE contabilizado' and (compra_elegida is None or int(monto) > int(round(float(doc_elegido['pendiente'])))):
                st.error('Selecciona una factura pendiente y no superes su saldo disponible.')
            elif fecha_limite < fecha:
                st.error('La fecha límite no puede ser anterior a la solicitud.')
            else:
                try:
                    sid = tes_guardar_solicitud(conn,fecha.isoformat(),beneficiario,pid,concepto,
                        fecha_limite.isoformat(),observacion,
                        [{'tipo':tipo,'referencia':r,'descripcion':d,'monto':m,
                          'compra_id':compra_elegida,'tratamiento':tratamiento} for d,r,m in lineas_solicitud],
                        (archivo_solicitud.name,archivo_solicitud.getvalue()) if archivo_solicitud else None)
                    st.session_state['tes_preferir_listado']=True
                    sgci_exito(f'Solicitud SF-{sid:06d} guardada como borrador. No se generó ningún asiento.')
                    st.session_state['tes_preferir_listado']=True
                    st.rerun()
                except Exception as e:
                    st.error(f'No se pudo guardar la solicitud: {e}')
    with tab_listado:
        solicitudes = pd.read_sql_query("""SELECT s.id, s.fecha, s.beneficiario, s.concepto, s.fecha_limite,
            s.estado, COALESCE(SUM(d.monto),0) AS total
            FROM tes_solicitudes s LEFT JOIN tes_solicitud_detalle d ON d.solicitud_id=s.id
            GROUP BY s.id ORDER BY s.id DESC""", conn)
        if solicitudes.empty:
            st.info('Todavía no hay solicitudes registradas.')
        else:
            filtro_estado=st.selectbox('Filtrar por estado',['Todos']+sorted(solicitudes.estado.unique().tolist()),key='tes_estado_filtro')
            solicitudes_visibles=solicitudes if filtro_estado=='Todos' else solicitudes[solicitudes.estado==filtro_estado]
            st.dataframe(solicitudes_visibles, hide_index=True, use_container_width=True)
            tes_boton_imprimir('Solicitudes '+filtro_estado,solicitudes_visibles,'solicitudes_'+filtro_estado.lower())
            pendientes_imp=solicitudes[solicitudes.estado=='PENDIENTE_CONTABILIZACION']
            tes_boton_imprimir('Pendientes de contabilización',pendientes_imp,'pendientes_contabilizacion')
            ids = solicitudes.id.astype(int).tolist()
            sid = st.selectbox('Selecciona una solicitud', ids, format_func=lambda n: f'SF-{n:06d}', key='tes_solicitud_actual')
            fila = conn.execute('SELECT * FROM tes_solicitudes WHERE id=?', (sid,)).fetchone()
            detalle = pd.read_sql_query('SELECT tipo, referencia, descripcion, monto, compra_id, tratamiento FROM tes_solicitud_detalle WHERE solicitud_id=?', conn, params=(sid,))
            st.write(f"**Beneficiario:** {fila['beneficiario']} · **Estado:** {fila['estado']}")
            # El tratamiento describe la naturaleza original del documento, no el estado actual del asiento.
            detalle_vista=detalle.copy()
            detalle_vista=detalle_vista.rename(columns={'tratamiento':'tratamiento declarado'})
            st.dataframe(detalle_vista, hide_index=True, use_container_width=True)
            tes_boton_imprimir(f'Detalle SF-{sid:06d}',detalle_vista,f'detalle_{sid}')
            st.metric('Total solicitado', money(detalle.monto.sum()))
            if sgci_puede_submodulo(conn,'tesoreria','Solicitudes de fondos','exportar'):
                for adj in conn.execute('SELECT id,nombre FROM tes_adjuntos WHERE solicitud_id=? ORDER BY id',(sid,)):
                    nombre_adjunto, contenido_adjunto = tes_descargar_adjunto(conn,sid,adj['id'])
                    st.download_button('Descargar adjunto: '+nombre_adjunto,contenido_adjunto,
                        file_name=nombre_adjunto,key=f'tes_adjunto_{adj["id"]}')
            if fila['estado'] in ('BORRADOR','ENVIADA','APROBADA','PENDIENTE_CONTABILIZACION'):
                st.markdown('#### Clasificación contable por línea')
                st.caption('Cada concepto se imputa a su propia cuenta. Una sola transferencia genera un asiento con varios débitos y un crédito bancario total.')
                detalles_db=conn.execute('SELECT id,descripcion,monto,compra_id,cuenta_contable,tratamiento FROM tes_solicitud_detalle WHERE solicitud_id=? ORDER BY id',(sid,)).fetchall()
                hojas_tes=cuentas_imputables(conn)
                cuentas_tes={f'{r.codigo} - {r.nombre}':r.codigo for r in hojas_tes.itertuples(index=False)}
                seleccion_tes={}
                for n,d in enumerate(detalles_db,1):
                    if d['compra_id'] is not None:
                        st.caption(f'Línea {n}: {d["descripcion"]} · {money(d["monto"])} · DTE vinculado: cuenta Proveedores automática')
                        continue
                    if d['tratamiento']=='Obligación ya contabilizada':
                        st.markdown(f'**Línea {n} · {d["descripcion"]} · {money(d["monto"])}**')
                        vinculo=conn.execute('SELECT linea_origen_id FROM tes_vinculos_obligacion WHERE detalle_id=?',(d['id'],)).fetchone()
                        if vinculo:st.caption(f'Obligación vinculada a línea del diario {vinculo[0]}. Se revalidará al pagar.')
                        if not sgci_puede_submodulo(conn,'contabilidad','Libro Diario','ver'):
                            st.info('La vinculación requiere autorización para consultar el Libro Diario.')
                            continue
                        origenes=tes_obligaciones_disponibles(conn)
                        opciones_origen={f"Línea {r.id} · Asiento {r.asiento_id} · {r.fecha} · {r.codigo_cuenta} · disponible {money(r.disponible)} · {str(r.glosa or '')[:90]}":int(r.id) for r in origenes.itertuples()}
                        origen_sel=st.selectbox('Obligación de origen',['Seleccionar obligación']+list(opciones_origen),key=f'tes_origen_{d["id"]}')
                        confirma_origen=st.checkbox('Confirmo que corresponde al beneficiario y que sigue pendiente, sin pagos por otro medio.',key=f'tes_origen_conf_{d["id"]}')
                        if st.button('Vincular obligación contabilizada',disabled=not(confirma_origen and origen_sel in opciones_origen),key=f'tes_origen_btn_{d["id"]}'):
                            try:
                                tes_vincular_obligacion(conn,sid,d['id'],opciones_origen[origen_sel],confirma_origen)
                                st.success('Origen vinculado. El pago debitará el pasivo sin volver a registrar el gasto.')
                                st.rerun()
                            except Exception as exc:st.error(f'No se realizaron cambios: {exc}')
                        continue
                    opciones_tes=['Seleccionar cuenta']+list(cuentas_tes)
                    previa=d['cuenta_contable'] or ''
                    indice=next((i for i,et in enumerate(opciones_tes) if cuentas_tes.get(et)==previa),0)
                    elegida=st.selectbox(f'Línea {n} · {d["descripcion"]} · {money(d["monto"])}',opciones_tes,index=indice,key=f'tes_linea_cta_{d["id"]}')
                    seleccion_tes[d['id']]=cuentas_tes.get(elegida)
                if seleccion_tes and st.button('💾 Guardar clasificación por línea',key=f'tes_guardar_cuentas_{sid}'):
                    sgci_exigir_permiso(conn,'tesoreria','contabilizar','Confirmación de pagos')
                    if fila['estado']=='CONTABILIZADA':
                        st.error('No se puede modificar un asiento contabilizado.')
                    else:
                        tes_guardar_clasificacion(conn,sid,seleccion_tes)
                        st.success('Clasificación contable guardada para todas las líneas.')
            if fila['estado'] == 'BORRADOR':
                if st.button('Marcar como enviada a Finanzas', key=f'tes_env_{sid}'):
                    sgci_exigir_permiso(conn, 'tesoreria', 'crear', 'Solicitudes de fondos')
                    tes_cambiar_estado(conn,sid,'ENVIADA')
                    st.session_state['tes_preferir_listado']=True
                    st.rerun()
            elif fila['estado'] == 'ENVIADA':
                st.caption('Registra únicamente decisiones efectivamente comunicadas por Finanzas.')
                c1, c2 = st.columns(2)
                if c1.button('Registrar aprobación externa', key=f'tes_ap_{sid}'):
                    sgci_exigir_permiso(conn, 'tesoreria', 'aprobar', 'Solicitudes de fondos')
                    tes_cambiar_estado(conn,sid,'APROBADA')
                    st.session_state['tes_preferir_listado']=True
                    st.rerun()
                if c2.button('Registrar rechazo externo', key=f'tes_re_{sid}'):
                    sgci_exigir_permiso(conn, 'tesoreria', 'aprobar', 'Solicitudes de fondos')
                    tes_cambiar_estado(conn,sid,'RECHAZADA')
                    st.session_state['tes_preferir_listado']=True
                    st.rerun()
            elif fila['estado'] == 'APROBADA':
                sin_dte_ap=detalle['compra_id'].isna().any()
                cuenta_ap=None
                faltan=conn.execute("SELECT COUNT(*) FROM tes_solicitud_detalle WHERE solicitud_id=? AND compra_id IS NULL AND COALESCE(cuenta_contable, '') = ''", (sid,)).fetchone()[0]
                if faltan:
                    st.warning(f'Hay {faltan} línea(s) sin cuenta contable. Guarda la clasificación antes de confirmar el pago.')
                st.info('Al guardar la confirmación, CONTEM intentará contabilizar automáticamente. La conciliación se realiza después.')
                with st.form(f'tes_pago_{sid}'):
                    medio = st.selectbox('Medio de pago', ['TRANSFERENCIA', 'CHEQUE'])
                    fecha_pago = st.date_input('Fecha de pago informada por Finanzas', value=date.today(), key=f'tes_fp_{sid}')
                    bancos_pago=conn.execute('SELECT id,nombre,numero_cuenta,cuenta_contable FROM bancos WHERE activo=1 ORDER BY nombre').fetchall()
                    opciones_banco={f"{b['nombre']} · {b['numero_cuenta'] or 'Sin número'} · {b['cuenta_contable'] or 'Sin cuenta contable'}":b['id'] for b in bancos_pago}
                    banco_etiqueta=st.selectbox('Banco de origen registrado', ['Seleccionar banco']+list(opciones_banco),key=f'tes_banco_id_{sid}')
                    banco_desc=st.text_input('Descripción adicional del banco (opcional)', key=f'tes_banco_{sid}')
                    referencia_pago = st.text_input('Referencia de transferencia o número de cheque', key=f'tes_ref_{sid}')
                    respaldo = st.file_uploader('Comprobante recibido (PDF, JPG o PNG; máximo 5 MB)', type=['pdf','jpg','jpeg','png'], key=f'tes_comp_{sid}')
                    observaciones_pago = st.text_area('Observaciones del pago', key=f'tes_obs_{sid}')
                    conformidad = st.checkbox('Confirmo que recibí evidencia del pago y que los datos son correctos.', key=f'tes_ok_{sid}')
                    registrar = st.form_submit_button('Confirmar transferencia y contabilizar', type='primary')
                if registrar:
                    sgci_exigir_permiso(conn, 'tesoreria', 'confirmar', 'Confirmación de pagos')
                    datos = respaldo.getvalue() if respaldo is not None else b''
                    if faltan:
                        st.error('Asigna y guarda una cuenta contable a cada línea antes de contabilizar.')
                    elif not conformidad:
                        st.error('Debes confirmar la revisión de los datos.')
                    elif banco_etiqueta == 'Seleccionar banco' or not referencia_pago.strip() or not datos:
                        st.error('Indica banco, referencia y adjunta un comprobante.')
                    elif len(datos) > 5 * 1024 * 1024:
                        st.error('El comprobante supera el máximo de 5 MB.')
                    else:
                        try:
                            tes_confirmar_pago(conn,sid,medio,fecha_pago.isoformat(),opciones_banco[banco_etiqueta],
                                banco_etiqueta,referencia_pago,respaldo.name,datos,observaciones_pago)
                            try:
                                asiento_auto=tes_contabilizar_pago(conn,sid,opciones_banco[banco_etiqueta],cuenta_ap)
                                sgci_exito(f'Pago confirmado y contabilizado automáticamente · Asiento {asiento_auto}.')
                            except Exception as error_auto:
                                with conn:
                                    conn.execute('UPDATE tes_confirmaciones_pago SET error_contabilizacion=? WHERE solicitud_id=?', (str(error_auto), sid))
                                sgci_exito('Comprobante registrado. Contabilización pendiente: '+str(error_auto))
                            st.session_state['tes_preferir_listado']=True
                            st.rerun()
                        except sqlite3.IntegrityError:
                            st.error('Ya existe una confirmación de pago para esta solicitud.')
                        except Exception as e:
                            st.error(f'No se pudo registrar el comprobante: {e}')
            elif fila['estado'] == 'PENDIENTE_CONTABILIZACION':
                pago = conn.execute('SELECT * FROM tes_confirmaciones_pago WHERE solicitud_id=?', (sid,)).fetchone()
                st.warning('Pago confirmado, pero el asiento aún no se ha generado. La cartola se conciliará después.')
                if pago and pago['error_contabilizacion']:
                    st.error('Motivo de la contabilización pendiente: ' + str(pago['error_contabilizacion']))
                for d in detalle.itertuples(index=False):
                    if pd.notna(d.compra_id):
                        st.info(f'DTE vinculado: compra interna ID {int(d.compra_id)}. Futuro asiento: Debe Proveedores / Haber Banco, previa verificación del saldo y del pago.')
                    elif d.tratamiento:
                        st.info(f'Tratamiento declarado: {d.tratamiento}. Se recuperará la cuenta ya seleccionada, si existe.')
                    else:
                        st.info('Solicitud anterior a Etapa 2B: tratamiento contable aún no clasificado. No se contabilizará automáticamente.')
                if pago:
                    st.write(f"**Medio:** {pago['medio']} · **Fecha:** {pago['fecha_pago']} · **Banco:** {pago['banco_descripcion']}")
                    st.write(f"**Referencia:** {pago['referencia']}")
                    tes_vista_comprobante(pago,sid)
                    bancos_disponibles=conn.execute('SELECT id,nombre,numero_cuenta,cuenta_contable FROM bancos WHERE activo=1 ORDER BY nombre').fetchall()
                    opciones_bancos={f"{b['nombre']} · {b['numero_cuenta'] or 'Sin número'} · {b['cuenta_contable'] or 'SIN CUENTA'}":int(b['id']) for b in bancos_disponibles}
                    predef_banco=next((i for i,k in enumerate(['Seleccionar banco']+list(opciones_bancos)) if opciones_bancos.get(k)==pago['banco_id']),0)
                    banco_sel=st.selectbox('Banco de origen para contabilizar', ['Seleccionar banco']+list(opciones_bancos),index=predef_banco,key=f'tes_cont_banco_{sid}')
                    cuenta_sin_dte=None
                    st.caption('Para corregir cuentas pendientes, utiliza los selectores por línea y guarda la clasificación.')
                    if st.button('Contabilizar pago confirmado',type='primary',key=f'tes_cont_{sid}'):
                        sgci_exigir_permiso(conn, 'tesoreria', 'contabilizar', 'Confirmación de pagos')
                        try:
                            if banco_sel=='Seleccionar banco':
                                raise ValueError('Selecciona el banco de origen.')
                            with conn:
                                conn.execute('UPDATE tes_confirmaciones_pago SET cuenta_contrapartida=? WHERE solicitud_id=? AND asiento_id IS NULL',(cuenta_sin_dte,sid))
                            asiento=tes_contabilizar_pago(conn,sid,opciones_bancos[banco_sel],cuenta_sin_dte)
                            sgci_exito(f'Pago SF-{sid:06d} contabilizado correctamente · Asiento {asiento}. Pendiente de conciliación bancaria.')
                            st.session_state['tes_preferir_listado']=True
                            st.rerun()
                        except Exception as exc:
                            with conn:
                                conn.execute('UPDATE tes_confirmaciones_pago SET error_contabilizacion=? WHERE solicitud_id=? AND asiento_id IS NULL',(str(exc),sid))
                            st.error(str(exc))
            elif fila['estado']=='CONTABILIZADA':
                pago=conn.execute('SELECT * FROM tes_confirmaciones_pago WHERE solicitud_id=?',(sid,)).fetchone()
                st.success(f"Pago contabilizado · Asiento {pago['asiento_id'] if pago else '—'}.")
                if pago:
                    tes_vista_comprobante(pago,sid)
                    conciliado=conn.execute("SELECT id FROM cartola_bancaria WHERE match_tipo='TESORERIA' AND match_id=? AND conciliado=1",(sid,)).fetchone()
                    st.info('Conciliada con cartola bancaria.' if conciliado else 'Pendiente de conciliación bancaria.')
                    asientos_tes=pd.read_sql_query('SELECT fecha,codigo_cuenta,cuenta,debe,haber,glosa FROM libro_diario WHERE asiento_id=? ORDER BY id',conn,params=(pago['asiento_id'],))
                    st.dataframe(asientos_tes,hide_index=True,use_container_width=True)
                    tes_boton_imprimir(f'Asiento {pago["asiento_id"]}',asientos_tes,f'asiento_{sid}')
    with tab_historial:
        st.subheader('Historial de solicitudes y pagos')
        historial=pd.read_sql_query("""SELECT s.id AS solicitud, s.fecha, s.beneficiario, s.concepto,
            s.estado, COALESCE(SUM(d.monto),0) AS monto, p.fecha_pago, p.referencia,
            p.asiento_id FROM tes_solicitudes s
            LEFT JOIN tes_solicitud_detalle d ON d.solicitud_id=s.id
            LEFT JOIN tes_confirmaciones_pago p ON p.solicitud_id=s.id
            GROUP BY s.id ORDER BY s.id DESC""",conn)
        if historial.empty:
            st.info('Aún no hay movimientos.')
        else:
            st.dataframe(formatear_montos_df(historial),hide_index=True,use_container_width=True)
            st.download_button('Descargar historial CSV',historial.to_csv(index=False).encode('utf-8-sig'),
                file_name='CONTEM_historial_tesoreria.csv',mime='text/csv')


# ============================================================
# SEGURIDAD - ROLES Y ACCESO POR MODULO (PILOTO CON CONTROLES EN OPERACIONES CRÍTICAS)
# ============================================================

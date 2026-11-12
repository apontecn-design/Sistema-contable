# CONTEM: componente extraído del app.py original; ejecución secuencial compartida.
def sgci_conc_esquema(conn):
    transaccion_previa = conn.in_transaction
    conn.execute("""CREATE TABLE IF NOT EXISTS sgci_compensaciones_documentos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        modulo TEXT NOT NULL CHECK(modulo IN ('VENTAS','COMPRAS')),
        tercero_id INTEGER NOT NULL,
        documento_credito_id INTEGER NOT NULL,
        documento_factura_id INTEGER NOT NULL,
        monto INTEGER NOT NULL CHECK(monto>0),
        fecha TEXT NOT NULL,
        observacion TEXT,
        usuario TEXT,
        anulada INTEGER NOT NULL DEFAULT 0,
        anulada_en TEXT,
        motivo_anulacion TEXT
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS sgci_saldos_ejercicios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        modulo TEXT NOT NULL CHECK(modulo IN ('VENTAS','COMPRAS')),
        tercero_id INTEGER NOT NULL,
        ejercicio INTEGER NOT NULL,
        referencia TEXT NOT NULL,
        monto INTEGER NOT NULL CHECK(monto>0),
        fecha TEXT NOT NULL,
        observacion TEXT,
        UNIQUE(modulo,tercero_id,ejercicio,referencia)
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS sgci_aplicaciones_ejercicios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        saldo_id INTEGER NOT NULL,
        pago_id INTEGER NOT NULL,
        monto INTEGER NOT NULL CHECK(monto>0),
        fecha TEXT NOT NULL,
        observacion TEXT,
        UNIQUE(saldo_id,pago_id)
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_sgci_comp_doc ON sgci_compensaciones_documentos(modulo,tercero_id,anulada)")
    if not transaccion_previa:
        conn.commit()


def sgci_autorizar_auxiliar(conn, modulo, accion='ver', pagos=False):
    """Validar el auxiliar antes de consultar datos o ejecutar migraciones."""
    if modulo not in ('VENTAS','COMPRAS'):
        raise ValueError('Módulo auxiliar inválido.')
    codigo = 'cxc' if modulo == 'VENTAS' else 'cxp'
    sub = ('Pagos de clientes' if modulo == 'VENTAS' else 'Pagos de proveedores') if pagos else (
        'Clientes y estados de cuenta' if modulo == 'VENTAS' else 'Proveedores y estados de cuenta')
    sgci_autorizar_operacion(conn,codigo,accion,sub)


def _sgci_monto_auxiliar(valor):
    from decimal import Decimal as _D, InvalidOperation as _Invalido
    try:
        monto = _D(str(valor))
        if not monto.is_finite() or monto <= 0 or monto != monto.to_integral_value():
            raise ValueError('El monto debe ser un entero positivo en CLP.')
    except (_Invalido,TypeError):
        raise ValueError('El monto debe ser un entero positivo en CLP.') from None
    return int(monto)


def _sgci_auditar_auxiliar(conn, accion, detalle):
    # Participa en la misma transacción: un error de auditoría revierte el cambio.
    conn.execute('INSERT INTO auditoria(fecha_hora,usuario,accion,detalle) VALUES(?,?,?,?)',
        (datetime.now().isoformat(timespec='seconds'),sgci_identidad_actual(),accion,detalle))


def _sgci_exigir_sin_transaccion(conn):
    if conn.in_transaction:
        raise RuntimeError('Guarda o revierte la operación pendiente antes de modificar el auxiliar.')

def sgci_nc_disponibles(conn, modulo, tercero_id):
    sgci_autorizar_auxiliar(conn,modulo)
    sgci_conc_esquema(conn)
    tabla, tercero = ('ventas','cliente_id') if modulo=='VENTAS' else ('compras','proveedor_id')
    return pd.read_sql_query(f"""SELECT d.id,d.fecha,d.tipo_doc,d.folio,ABS(d.monto_total) total,
       COALESCE((SELECT SUM(x.monto) FROM sgci_compensaciones_documentos x
          WHERE x.modulo=? AND x.documento_credito_id=d.id AND x.anulada=0),0) aplicado,
       MAX(0,ABS(d.monto_total)-COALESCE((SELECT SUM(x.monto) FROM sgci_compensaciones_documentos x
          WHERE x.modulo=? AND x.documento_credito_id=d.id AND x.anulada=0),0)) disponible
       FROM {tabla} d WHERE d.{tercero}=? AND d.tipo_doc IN (60,61)
       AND ABS(d.monto_total)>COALESCE((SELECT SUM(x.monto) FROM sgci_compensaciones_documentos x
          WHERE x.modulo=? AND x.documento_credito_id=d.id AND x.anulada=0),0)
       ORDER BY d.fecha,d.id""",conn,params=(modulo,modulo,int(tercero_id),modulo))

def sgci_facturas_compensables(conn, modulo, tercero_id):
    sgci_autorizar_auxiliar(conn,modulo)
    sgci_conc_esquema(conn)
    tabla, tercero, apps, docid = ('ventas','cliente_id','aplicaciones_clientes','venta_id') if modulo=='VENTAS' else ('compras','proveedor_id','aplicaciones_proveedores','compra_id')
    return pd.read_sql_query(f"""SELECT d.id,d.fecha,d.tipo_doc,d.folio,ABS(d.monto_total) total,
       COALESCE((SELECT SUM(ABS(a.monto)) FROM {apps} a WHERE a.{docid}=d.id),0) pagado,
       COALESCE((SELECT SUM(x.monto) FROM sgci_compensaciones_documentos x WHERE x.modulo=?
          AND x.documento_factura_id=d.id AND x.anulada=0),0) compensado,
       MAX(0,ABS(d.monto_total)-COALESCE((SELECT SUM(ABS(a.monto)) FROM {apps} a WHERE a.{docid}=d.id),0)
          -COALESCE((SELECT SUM(x.monto) FROM sgci_compensaciones_documentos x WHERE x.modulo=?
          AND x.documento_factura_id=d.id AND x.anulada=0),0)) pendiente
       FROM {tabla} d WHERE d.{tercero}=? AND (d.tipo_doc IS NULL OR d.tipo_doc NOT IN (60,61,52))
       AND ABS(d.monto_total)-COALESCE((SELECT SUM(ABS(a.monto)) FROM {apps} a WHERE a.{docid}=d.id),0)
          -COALESCE((SELECT SUM(x.monto) FROM sgci_compensaciones_documentos x WHERE x.modulo=?
          AND x.documento_factura_id=d.id AND x.anulada=0),0)>0
       ORDER BY d.fecha,d.id""",conn,params=(modulo,modulo,int(tercero_id),modulo))

def sgci_compensar_nc(conn,modulo,tercero_id,nc_id,factura_id,monto,observacion=''):
    sgci_autorizar_auxiliar(conn,modulo,'editar')
    _sgci_exigir_sin_transaccion(conn)
    sgci_conc_esquema(conn)
    monto=_sgci_monto_auxiliar(monto)
    if int(nc_id)==int(factura_id): raise ValueError('Los documentos deben ser diferentes.')
    with conn:
        conn.execute('BEGIN IMMEDIATE')
        nc=sgci_nc_disponibles(conn,modulo,tercero_id)
        fac=sgci_facturas_compensables(conn,modulo,tercero_id)
        nc=nc[nc.id==int(nc_id)];fac=fac[fac.id==int(factura_id)]
        if nc.empty or fac.empty: raise ValueError('Documento inexistente, de otro tercero o sin saldo.')
        if monto>int(nc.iloc[0].disponible) or monto>int(fac.iloc[0].pendiente):
            raise ValueError('La compensación supera el saldo de alguno de los documentos.')
        fecha=date.today().isoformat()
        if periodo_cerrado(conn,fecha): raise ValueError('El período actual está cerrado.')
        conn.execute("""INSERT INTO sgci_compensaciones_documentos
            (modulo,tercero_id,documento_credito_id,documento_factura_id,monto,fecha,observacion)
            VALUES(?,?,?,?,?,?,?)""",(modulo,int(tercero_id),int(nc_id),int(factura_id),monto,fecha,observacion.strip()))
        _sgci_auditar_auxiliar(conn,'COMPENSACION DOCUMENTAL',f'{modulo} tercero {tercero_id}: NC {nc_id} -> factura {factura_id} por {monto}')

def sgci_anular_compensacion(conn,identificador,motivo):
    permitidos = [modulo for modulo,codigo,sub in (
        ('VENTAS','cxc','Clientes y estados de cuenta'),('COMPRAS','cxp','Proveedores y estados de cuenta'))
        if sgci_puede_submodulo(conn,codigo,sub,'anular')]
    if not permitidos:
        raise PermissionError('No tienes autorización para revertir compensaciones.')
    _sgci_exigir_sin_transaccion(conn)
    sgci_conc_esquema(conn)
    if not motivo.strip(): raise ValueError('Indica el motivo de reversión.')
    with conn:
        conn.execute('BEGIN IMMEDIATE')
        marcas=','.join('?' for _ in permitidos)
        fila=conn.execute(f'SELECT * FROM sgci_compensaciones_documentos WHERE id=? AND anulada=0 AND modulo IN ({marcas})',
                          (int(identificador),*permitidos)).fetchone()
        if not fila: raise ValueError('Compensación inexistente o ya anulada.')
        sgci_autorizar_auxiliar(conn,fila['modulo'],'anular')
        if periodo_cerrado(conn,date.today().isoformat()): raise ValueError('Período actual cerrado.')
        conn.execute('UPDATE sgci_compensaciones_documentos SET anulada=1,anulada_en=?,motivo_anulacion=? WHERE id=?',
                     (datetime.now().isoformat(timespec='seconds'),motivo.strip(),int(identificador)))
        _sgci_auditar_auxiliar(conn,'REVERSO COMPENSACION',f'ID {identificador}: {motivo.strip()}')

def sgci_saldos_ejercicio_disponibles(conn,modulo,tercero_id):
    sgci_autorizar_auxiliar(conn,modulo)
    sgci_conc_esquema(conn)
    return pd.read_sql_query("""SELECT s.id,s.ejercicio,s.referencia,s.monto,
        COALESCE((SELECT SUM(a.monto) FROM sgci_aplicaciones_ejercicios a WHERE a.saldo_id=s.id),0) aplicado,
        s.monto-COALESCE((SELECT SUM(a.monto) FROM sgci_aplicaciones_ejercicios a WHERE a.saldo_id=s.id),0) disponible
        FROM sgci_saldos_ejercicios s WHERE s.modulo=? AND s.tercero_id=?
        AND s.monto>COALESCE((SELECT SUM(a.monto) FROM sgci_aplicaciones_ejercicios a WHERE a.saldo_id=s.id),0)
        ORDER BY s.ejercicio,s.id""",conn,params=(modulo,int(tercero_id)))

def sgci_registrar_saldo_ejercicio(conn,modulo,tercero_id,ejercicio,referencia,monto):
    sgci_autorizar_auxiliar(conn,modulo,'crear')
    _sgci_exigir_sin_transaccion(conn)
    sgci_conc_esquema(conn)
    monto=_sgci_monto_auxiliar(monto)
    if not referencia.strip():
        raise ValueError('Completa un ejercicio, referencia y monto válido.')
    if int(ejercicio)>=date.today().year: raise ValueError('El ejercicio debe ser anterior al actual.')
    # El asiento de apertura debe existir previamente: esta tabla no crea contabilidad.
    with conn:
        conn.execute('BEGIN IMMEDIATE')
        tabla = 'clientes' if modulo=='VENTAS' else 'proveedores'
        if not conn.execute(f'SELECT 1 FROM {tabla} WHERE id=?',(int(tercero_id),)).fetchone():
            raise ValueError('El tercero no existe en el auxiliar seleccionado.')
        conn.execute("""INSERT INTO sgci_saldos_ejercicios(modulo,tercero_id,ejercicio,referencia,monto,fecha)
                        VALUES(?,?,?,?,?,?)""",(modulo,int(tercero_id),int(ejercicio),referencia.strip(),int(monto),date.today().isoformat()))
        _sgci_auditar_auxiliar(conn,'SALDO EJERCICIO',f'{modulo} tercero {tercero_id}, {ejercicio}, {referencia}, {monto}')

def sgci_aplicar_pago_ejercicio(conn,modulo,tercero_id,saldo_id,pago_id,monto):
    sgci_autorizar_auxiliar(conn,modulo,'editar',pagos=True)
    _sgci_exigir_sin_transaccion(conn)
    sgci_conc_esquema(conn)
    monto=_sgci_monto_auxiliar(monto)
    with conn:
        conn.execute('BEGIN IMMEDIATE')
        saldo=sgci_saldos_ejercicio_disponibles(conn,modulo,tercero_id)
        saldo=saldo[saldo.id==int(saldo_id)]
        if saldo.empty or monto>int(saldo.iloc[0].disponible): raise ValueError('Saldo histórico insuficiente.')
        tabla='pagos_clientes' if modulo=='VENTAS' else 'pagos_proveedores'
        tercero='cliente_id' if modulo=='VENTAS' else 'proveedor_id'
        pago=conn.execute(f'SELECT * FROM {tabla} WHERE id=? AND {tercero}=?',(int(pago_id),int(tercero_id))).fetchone()
        if not pago: raise ValueError('Pago inexistente o de otro tercero.')
        if modulo=='VENTAS':
            if pago['cuenta_anticipo']: raise ValueError('Un anticipo contabilizado como pasivo requiere reclasificación contable; no se puede consumir aquí.')
            recibido=clp_round(pago['monto_recibido'] or pago['monto'] or 0)
            aplicado=conn.execute('SELECT COALESCE(SUM(monto),0) FROM aplicaciones_clientes WHERE pago_id=?',(int(pago_id),)).fetchone()[0]
            aplicado_apertura=conn.execute('SELECT COALESCE(SUM(monto),0) FROM sgci_aplicaciones_apertura_clientes WHERE pago_id=?',(int(pago_id),)).fetchone()[0] if tabla_existe(conn,'sgci_aplicaciones_apertura_clientes') else 0
        else:
            recibido=clp_round(pago['monto'] or 0)
            aplicado=conn.execute('SELECT COALESCE(SUM(ABS(monto)),0) FROM aplicaciones_proveedores WHERE pago_id=?',(int(pago_id),)).fetchone()[0]
            aplicado_apertura=0
        historico=conn.execute('SELECT COALESCE(SUM(a.monto),0) FROM sgci_aplicaciones_ejercicios a JOIN sgci_saldos_ejercicios s ON s.id=a.saldo_id WHERE a.pago_id=? AND s.modulo=?',(int(pago_id),modulo)).fetchone()[0]
        if monto>clp_round(recibido-aplicado-aplicado_apertura-historico):
            raise ValueError('El pago no tiene disponibilidad suficiente.')
        if periodo_cerrado(conn,date.today().isoformat()): raise ValueError('Período actual cerrado.')
        conn.execute('INSERT INTO sgci_aplicaciones_ejercicios(saldo_id,pago_id,monto,fecha) VALUES(?,?,?,?)',
                     (int(saldo_id),int(pago_id),monto,date.today().isoformat()))
        _sgci_auditar_auxiliar(conn,'APLICACION EJERCICIO',f'{modulo} saldo {saldo_id}, pago {pago_id}, {monto}')

def abonos_disponibles_cliente(conn, cliente_id):
    """Anticipos/cobros recibidos todavía disponibles para aplicar a facturas."""
    recuperar_anticipos_historicos_cliente(conn,cliente_id)
    sgci_saldos_apertura_clientes(conn)
    sgci_conc_esquema(conn)
    return pd.read_sql_query("""
        SELECT p.id,p.fecha,
               CASE WHEN COALESCE(p.monto_recibido,0)>0 THEN p.monto_recibido ELSE p.monto END AS monto,
               COALESCE(p.glosa,'Pago recibido') glosa,
               COALESCE((SELECT SUM(a.monto) FROM aplicaciones_clientes a WHERE a.pago_id=p.id),0) aplicado,
               MAX(
                 (CASE WHEN COALESCE(p.monto_recibido,0)>0 THEN p.monto_recibido ELSE p.monto END)
                 - COALESCE((SELECT SUM(a.monto) FROM aplicaciones_clientes a WHERE a.pago_id=p.id),0)
                 - COALESCE((SELECT SUM(x.monto) FROM sgci_aplicaciones_apertura_clientes x WHERE x.pago_id=p.id),0)
                 - COALESCE((SELECT SUM(x.monto) FROM sgci_aplicaciones_ejercicios x JOIN sgci_saldos_ejercicios h ON h.id=x.saldo_id WHERE x.pago_id=p.id AND h.modulo='VENTAS'),0),0
               ) disponible
        FROM pagos_clientes p
        WHERE p.cliente_id=?
          AND (CASE WHEN COALESCE(p.monto_recibido,0)>0 THEN p.monto_recibido ELSE p.monto END)
              - COALESCE((SELECT SUM(a.monto) FROM aplicaciones_clientes a WHERE a.pago_id=p.id),0)
              - COALESCE((SELECT SUM(x.monto) FROM sgci_aplicaciones_apertura_clientes x WHERE x.pago_id=p.id),0)
              - COALESCE((SELECT SUM(x.monto) FROM sgci_aplicaciones_ejercicios x JOIN sgci_saldos_ejercicios h ON h.id=x.saldo_id WHERE x.pago_id=p.id AND h.modulo='VENTAS'),0) > 0.01
        ORDER BY p.fecha,p.id
    """,conn,params=(int(cliente_id),))


def aplicar_abono_auxiliar_cliente(conn, cliente_id, pago_id, venta_ids):
    sgci_autorizar_operacion(conn,'cxc','editar','Pagos de clientes')
    """Aplica un saldo recibido a facturas. Si era anticipo, reclasifica Pasivo -> Clientes."""
    pago=conn.execute("SELECT * FROM pagos_clientes WHERE id=? AND cliente_id=?",
                      (int(pago_id),int(cliente_id))).fetchone()
    if not pago:
        raise ValueError("Abono no encontrado para este cliente.")

    total_recibido=clp_round(float(pago["monto_recibido"] or pago["monto"] or 0))
    aplicado_previo=conn.execute(
        "SELECT COALESCE(SUM(monto),0) FROM aplicaciones_clientes WHERE pago_id=?",
        (int(pago_id),)
    ).fetchone()[0]
    sgci_saldos_apertura_clientes(conn)
    sgci_conc_esquema(conn)
    apertura=conn.execute('SELECT COALESCE(SUM(monto),0) FROM sgci_aplicaciones_apertura_clientes WHERE pago_id=?',(int(pago_id),)).fetchone()[0]
    historico=conn.execute('SELECT COALESCE(SUM(a.monto),0) FROM sgci_aplicaciones_ejercicios a JOIN sgci_saldos_ejercicios s ON s.id=a.saldo_id WHERE a.pago_id=? AND s.modulo="VENTAS"',(int(pago_id),)).fetchone()[0]
    disponible=clp_round(total_recibido-float(aplicado_previo or 0)-float(apertura or 0)-float(historico or 0))
    if disponible<=0:
        raise ValueError("Este abono ya no tiene saldo disponible.")

    venta_ids=[int(x) for x in venta_ids]
    if not venta_ids:
        raise ValueError("Selecciona al menos una factura.")
    docs=documentos_pendientes_cliente(conn,cliente_id)
    docs=docs[docs["id"].isin(venta_ids)].copy()
    if docs.empty:
        raise ValueError("Las facturas seleccionadas ya no tienen saldo pendiente.")

    monto_aplicar=min(disponible,clp_round(float(docs["pendiente"].sum())))
    es_anticipo=bool(pago["cuenta_anticipo"]) and float(pago["monto_recibido"] or 0)>0
    asiento=None
    lote=None

    try:
        if es_anticipo and monto_aplicar>0:
            roles=cargar_roles(conn)
            rol_cli=roles.get("clientes")
            if not rol_cli:
                raise ValueError("La cuenta Clientes no está configurada.")
            cuenta_cli=rol_cli[0]
            cuenta_ant=pago["cuenta_anticipo"]
            if not cuenta_ant:
                raise ValueError("No se pudo identificar la cuenta contable del anticipo.")
            fecha_aplicacion=datetime.now().strftime("%Y-%m-%d")
            # La aplicación usa la fecha actual; si el período está cerrado, no se modifica el pasado.
            if periodo_cerrado(conn,fecha_aplicacion):
                raise ValueError("El período contable actual está cerrado.")
            asiento=siguiente_asiento(conn)+1
            lote="APL-ANT-CLI-"+datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            plan=Plan(conn)
            cliente=conn.execute("SELECT COALESCE(NULLIF(razon_social,''),nombre) nombre FROM clientes WHERE id=?",
                                 (int(cliente_id),)).fetchone()
            nombre=limpiar_texto(cliente["nombre"] if cliente else "Cliente")
            glosa=f"Aplicación anticipo cliente {nombre} a documentos"
            # Dr Anticipos recibidos de clientes / Cr Clientes
            conn.execute("""INSERT INTO libro_diario(fecha,cuenta,debe,haber,glosa,codigo_cuenta,asiento_id,lote_id,origen)
                            VALUES(?,?,?,?,?,?,?,?,?)""",
                         (fecha_aplicacion,plan.todos.get(cuenta_ant,cuenta_ant),monto_aplicar,0,
                          glosa,cuenta_ant,asiento,lote,"APLICACION_ANTICIPO_CLIENTE"))
            conn.execute("""INSERT INTO libro_diario(fecha,cuenta,debe,haber,glosa,codigo_cuenta,asiento_id,lote_id,origen)
                            VALUES(?,?,?,?,?,?,?,?,?)""",
                         (fecha_aplicacion,plan.todos.get(cuenta_cli,cuenta_cli),0,monto_aplicar,
                          glosa,cuenta_cli,asiento,lote,"APLICACION_ANTICIPO_CLIENTE"))

        restante=disponible
        aplicaciones=[]
        for r in docs.itertuples(index=False):
            if restante<=0:
                break
            monto=min(restante,clp_round(float(r.pendiente)))
            if monto>0:
                conn.execute("INSERT INTO aplicaciones_clientes(pago_id,venta_id,monto) VALUES(?,?,?)",
                             (int(pago_id),int(r.id),monto))
                aplicaciones.append((int(r.id),monto))
                restante=clp_round(restante-monto)

        # Solo lo efectivamente aplicado rebaja CxC en el auxiliar.
        if es_anticipo:
            conn.execute("UPDATE pagos_clientes SET monto=COALESCE(monto,0)+? WHERE id=?",
                         (sum(x[1] for x in aplicaciones),int(pago_id)))
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    registrar_auditoria(
        conn,"APLICACION AUXILIAR CLIENTE",
        f"Cliente {cliente_id}, pago {pago_id}, aplicado {sum(x[1] for x in aplicaciones)}, "
        f"saldo abono {restante}, asiento reclasificacion {asiento or 'no requerido'}"
    )
    return aplicaciones,restante


def documentos_pendientes_proveedor(conn, proveedor_id):
    """Devuelve documentos de compra con saldo pendiente para un proveedor."""
    sgci_conc_esquema(conn)
    return pd.read_sql_query("""
        SELECT c.id, c.fecha, c.folio, c.tipo_doc, ABS(COALESCE(c.monto_total,0)) AS total,
               COALESCE((SELECT SUM(ABS(a.monto)) FROM aplicaciones_proveedores a WHERE a.compra_id=c.id),0) AS aplicado,
               MAX(ABS(COALESCE(c.monto_total,0)) - COALESCE((SELECT SUM(ABS(a.monto)) FROM aplicaciones_proveedores a WHERE a.compra_id=c.id),0)
                  -COALESCE((SELECT SUM(x.monto) FROM sgci_compensaciones_documentos x WHERE x.modulo='COMPRAS' AND x.documento_factura_id=c.id AND x.anulada=0),0),0) AS pendiente
        FROM compras c
        WHERE c.proveedor_id=?
          AND (c.tipo_doc IS NULL OR c.tipo_doc NOT IN (60,61))
          AND ABS(COALESCE(c.monto_total,0)) - COALESCE((SELECT SUM(ABS(a.monto)) FROM aplicaciones_proveedores a WHERE a.compra_id=c.id),0)
              -COALESCE((SELECT SUM(x.monto) FROM sgci_compensaciones_documentos x WHERE x.modulo='COMPRAS' AND x.documento_factura_id=c.id AND x.anulada=0),0) > 0.01
        ORDER BY c.fecha, c.id
    """, conn, params=[int(proveedor_id)])


def pagos_disponibles_proveedor(conn, proveedor_id):
    """Pagos ya contabilizados al proveedor que todavía tienen saldo disponible para aplicar."""
    sgci_conc_esquema(conn)
    return pd.read_sql_query("""
        SELECT p.id,p.fecha,p.monto,
               COALESCE(p.glosa,'Pago a proveedor') glosa,
               COALESCE((SELECT SUM(ABS(a.monto)) FROM aplicaciones_proveedores a WHERE a.pago_id=p.id),0) aplicado,
               MAX(p.monto-COALESCE((SELECT SUM(ABS(a.monto)) FROM aplicaciones_proveedores a WHERE a.pago_id=p.id),0)
                   -COALESCE((SELECT SUM(a.monto) FROM sgci_aplicaciones_ejercicios a JOIN sgci_saldos_ejercicios s ON s.id=a.saldo_id WHERE s.modulo='COMPRAS' AND a.pago_id=p.id),0),0) disponible
        FROM pagos_proveedores p
        WHERE p.proveedor_id=?
          AND p.monto-COALESCE((SELECT SUM(ABS(a.monto)) FROM aplicaciones_proveedores a WHERE a.pago_id=p.id),0)
              -COALESCE((SELECT SUM(a.monto) FROM sgci_aplicaciones_ejercicios a JOIN sgci_saldos_ejercicios s ON s.id=a.saldo_id WHERE s.modulo='COMPRAS' AND a.pago_id=p.id),0) > 0.01
        ORDER BY p.fecha,p.id
    """,conn,params=(int(proveedor_id),))


def aplicar_pago_auxiliar_proveedor(conn, proveedor_id, pago_id, compra_ids):
    sgci_autorizar_operacion(conn,'cxp','editar','Pagos de proveedores')
    """Aplica saldo ya contabilizado de un pago a documentos del proveedor. No genera asiento."""
    pago=conn.execute(
        "SELECT * FROM pagos_proveedores WHERE id=? AND proveedor_id=?",
        (int(pago_id),int(proveedor_id))
    ).fetchone()
    if not pago:
        raise ValueError("Pago no encontrado para este proveedor.")

    aplicado=conn.execute(
        "SELECT COALESCE(SUM(ABS(monto)),0) FROM aplicaciones_proveedores WHERE pago_id=?",
        (int(pago_id),)
    ).fetchone()[0]
    disponible=clp_round(float(pago["monto"] or 0)-float(aplicado or 0))
    if disponible<=0:
        raise ValueError("Este pago ya no tiene saldo disponible.")

    compra_ids=[int(x) for x in compra_ids]
    if not compra_ids:
        raise ValueError("Selecciona al menos un documento.")

    docs=documentos_pendientes_proveedor(conn,proveedor_id)
    docs=docs[docs["id"].isin(compra_ids)].copy()
    if docs.empty:
        raise ValueError("Los documentos seleccionados ya no tienen saldo pendiente.")

    restante=disponible
    aplicaciones=[]
    try:
        for r in docs.itertuples(index=False):
            if restante<=0:
                break
            monto=min(restante,clp_round(float(r.pendiente)))
            if monto>0:
                conn.execute(
                    "INSERT INTO aplicaciones_proveedores(pago_id,compra_id,monto) VALUES(?,?,?)",
                    (int(pago_id),int(r.id),monto)
                )
                aplicaciones.append((int(r.id),monto))
                restante=clp_round(restante-monto)
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    registrar_auditoria(
        conn,"APLICACION AUXILIAR PROVEEDOR",
        f"Proveedor {proveedor_id}, pago {pago_id}, aplicado {sum(x[1] for x in aplicaciones)}, saldo pago {restante}"
    )
    return aplicaciones,restante


def sgci_crear_devoluciones_proveedor(conn):
    """Auxiliar para vincular reembolsos de proveedores con NC y factura sin duplicar el RCV."""
    conn.execute("""CREATE TABLE IF NOT EXISTS sgci_devoluciones_proveedor (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        movimiento_id INTEGER NOT NULL UNIQUE,
        proveedor_id INTEGER NOT NULL,
        nota_credito_id INTEGER NOT NULL,
        factura_id INTEGER NOT NULL,
        monto REAL NOT NULL CHECK(monto > 0),
        asiento_id INTEGER NOT NULL,
        lote_id TEXT NOT NULL,
        fecha TEXT NOT NULL,
        glosa TEXT NOT NULL
    )""")
    conn.commit()


def sgci_contabilizar_devolucion_proveedor(conn, movimiento_id, proveedor_id,
                                            nota_credito_id, factura_id, glosa=""):
    """Un asiento Banco Debe / Proveedores Haber y una línea en el auxiliar del proveedor.

    No genera una nueva compra ni altera el asiento de la nota de crédito.
    """
    sgci_autorizar_operacion(conn, 'banco', 'contabilizar', 'Conciliación bancaria')
    sgci_crear_devoluciones_proveedor(conn)
    mov = conn.execute("SELECT * FROM cartola_bancaria WHERE id=?", (int(movimiento_id),)).fetchone()
    if not mov or int(mov['conciliado'] or 0):
        raise ValueError('El movimiento bancario no existe o ya está conciliado.')
    monto = clp_round(float(mov['abono'] or 0))
    if monto <= 0 or float(mov['cargo'] or 0) > 0:
        raise ValueError('La devolución debe ser un abono bancario.')
    if periodo_cerrado(conn, mov['fecha']):
        raise ValueError('El período contable está cerrado.')
    banco = conn.execute('SELECT * FROM bancos WHERE id=?', (mov['banco_id'],)).fetchone()
    if not banco or not banco['cuenta_contable']:
        raise ValueError('La cuenta bancaria no tiene cuenta contable configurada.')
    proveedor = conn.execute('SELECT * FROM proveedores WHERE id=?', (int(proveedor_id),)).fetchone()
    if not proveedor:
        raise ValueError('Proveedor no encontrado.')
    nc = conn.execute('SELECT * FROM compras WHERE id=? AND proveedor_id=? AND tipo_doc IN (60,61)',
                      (int(nota_credito_id), int(proveedor_id))).fetchone()
    factura = conn.execute('SELECT * FROM compras WHERE id=? AND proveedor_id=? AND tipo_doc NOT IN (60,61)',
                           (int(factura_id), int(proveedor_id))).fetchone()
    if not nc or not factura or int(nc['id']) == int(factura['id']):
        raise ValueError('Selecciona una nota de crédito y una factura válidas del mismo proveedor.')
    roles = cargar_roles(conn)
    rol_prov = roles.get('proveedores')
    if not rol_prov:
        raise ValueError('La cuenta contable de Proveedores no está configurada.')
    codigo_prov, codigo_banco = rol_prov[0], banco['cuenta_contable']
    if codigo_prov == codigo_banco:
        raise ValueError('La cuenta de Banco no puede ser la misma que Proveedores.')
    # La diferencia NC - factura es la base del reembolso. No permitir aplicarla dos veces.
    disponible = clp_round(abs(float(nc['monto_total'] or 0)) - abs(float(factura['monto_total'] or 0)))
    aplicado = conn.execute("""SELECT COALESCE(SUM(monto),0) FROM sgci_devoluciones_proveedor
                              WHERE nota_credito_id=? AND factura_id=?""",
                           (int(nota_credito_id), int(factura_id))).fetchone()[0]
    restante = clp_round(disponible - float(aplicado or 0))
    if disponible <= 0 or monto > restante:
        raise ValueError(f'La diferencia disponible NC/factura es {money(max(0,restante))}; '
                         f'no alcanza para el abono de {money(monto)}. Revisa los documentos.')
    if conn.execute('SELECT 1 FROM sgci_devoluciones_proveedor WHERE movimiento_id=?',
                    (int(movimiento_id),)).fetchone():
        raise ValueError('Este abono ya tiene una devolución vinculada.')
    nombre = limpiar_texto(proveedor['razon_social'] or proveedor['nombre'] or 'Proveedor')
    detalle = limpiar_texto(glosa) or f'Devolución {nombre} - NC {nc["folio"]} / Factura {factura["folio"]}'
    asiento = siguiente_asiento(conn) + 1
    lote = 'DEV-PROV-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    plan = Plan(conn)
    try:
        conn.execute("""INSERT INTO libro_diario
            (fecha,cuenta,debe,haber,glosa,codigo_cuenta,asiento_id,lote_id,origen)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (mov['fecha'], plan.todos.get(codigo_banco,codigo_banco), monto, 0,
             detalle, codigo_banco, asiento, lote, 'DEVOLUCION_PROVEEDOR'))
        conn.execute("""INSERT INTO libro_diario
            (fecha,cuenta,debe,haber,glosa,codigo_cuenta,asiento_id,lote_id,origen)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (mov['fecha'], plan.todos.get(codigo_prov,codigo_prov), 0, monto,
             detalle, codigo_prov, asiento, lote, 'DEVOLUCION_PROVEEDOR'))
        conn.execute("""INSERT INTO sgci_devoluciones_proveedor
            (movimiento_id,proveedor_id,nota_credito_id,factura_id,monto,asiento_id,lote_id,fecha,glosa)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (int(movimiento_id),int(proveedor_id),int(nota_credito_id),int(factura_id),
             monto,asiento,lote,mov['fecha'],detalle))
        cur = conn.execute("""UPDATE cartola_bancaria
            SET conciliado=1,observacion=?,asiento_id=?,match_tipo='DEVOLUCION_PROVEEDOR',
                match_id=?,match_confianza=100 WHERE id=? AND conciliado=0""",
            (detalle,asiento,int(proveedor_id),int(movimiento_id)))
        if cur.rowcount != 1:
            raise ValueError('El movimiento dejó de estar pendiente; no se registró el asiento.')
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    registrar_auditoria(conn, 'DEVOLUCION PROVEEDOR',
                        f'Movimiento {movimiento_id}, proveedor {proveedor_id}, NC {nota_credito_id}, factura {factura_id}, asiento {asiento}')
    return asiento


def contabilizar_pago_proveedor_desde_cartola(conn, movimiento_id, proveedor_id, compra_ids,
                                                 cuenta_diferencia=None, glosa_diferencia=""):
    sgci_autorizar_operacion(conn, 'banco', 'contabilizar', 'Conciliación bancaria')
    """Contabiliza un cargo bancario como pago a proveedor.

    El monto aplicado al auxiliar del proveedor nunca supera el saldo de los documentos elegidos.
    Si el cargo bancario excede ese saldo, la diferencia puede imputarse a otra cuenta contable.
    Si el cargo es menor, se aplica parcialmente y el documento conserva saldo pendiente.
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

    monto_banco = clp_round(abs(float(mov["cargo"] or 0)))
    saldo_docs = clp_round(float(docs["pendiente"].sum()))
    monto_proveedor = min(monto_banco, saldo_docs)
    diferencia = clp_round(monto_banco - monto_proveedor)

    if diferencia > 0:
        if not cuenta_diferencia:
            raise ValueError(f"Existe una diferencia de {money(diferencia)}. Selecciona la cuenta contable donde deseas imputarla.")
        if cuenta_diferencia in (cuenta_banco, cuenta_proveedores):
            raise ValueError("La cuenta de diferencia debe ser distinta de Banco y Proveedores.")

    nombre_prov = limpiar_texto(proveedor["razon_social"] or proveedor["nombre"] or "Proveedor")
    folios = ", ".join(str(x) for x in docs["folio"].tolist())
    glosa = f"Pago proveedor {nombre_prov} - Doc. {folios}"
    asiento_id = siguiente_asiento(conn) + 1
    lote = "CONC-PROV-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    plan = Plan(conn)

    try:
        # Proveedores solo por lo efectivamente aplicado a sus documentos.
        conn.execute("""INSERT INTO libro_diario
            (fecha,cuenta,debe,haber,glosa,codigo_cuenta,asiento_id,lote_id,origen)
            VALUES(?,?,?,?,?,?,?,?,?)""",
            (mov["fecha"], plan.todos.get(cuenta_proveedores,cuenta_proveedores),
             monto_proveedor, 0.0, glosa, cuenta_proveedores, asiento_id, lote,
             "CONCILIACION_PAGO_PROVEEDOR"))

        # Exceso del cheque/pago: cuenta elegida por el usuario.
        if diferencia > 0:
            gd = limpiar_texto(glosa_diferencia) or f"Diferencia pago proveedor {nombre_prov}"
            conn.execute("""INSERT INTO libro_diario
                (fecha,cuenta,debe,haber,glosa,codigo_cuenta,asiento_id,lote_id,origen)
                VALUES(?,?,?,?,?,?,?,?,?)""",
                (mov["fecha"], plan.todos.get(cuenta_diferencia,cuenta_diferencia),
                 diferencia, 0.0, gd, cuenta_diferencia, asiento_id, lote,
                 "CONCILIACION_DIFERENCIA_PROVEEDOR"))

        # Banco siempre por el monto real de la cartola.
        conn.execute("""INSERT INTO libro_diario
            (fecha,cuenta,debe,haber,glosa,codigo_cuenta,asiento_id,lote_id,origen)
            VALUES(?,?,?,?,?,?,?,?,?)""",
            (mov["fecha"], plan.todos.get(cuenta_banco,cuenta_banco),
             0.0, monto_banco, glosa, cuenta_banco, asiento_id, lote,
             "CONCILIACION_PAGO_PROVEEDOR"))

        cur = conn.execute("""INSERT INTO pagos_proveedores(fecha,proveedor_id,monto,medio_pago,cuenta_banco,glosa,lote_id)
                              VALUES(?,?,?,?,?,?,?)""",
                           (mov["fecha"], int(proveedor_id), monto_proveedor, "Banco",
                            cuenta_banco, glosa, lote))
        pago_id = cur.lastrowid

        restante = monto_proveedor
        aplicaciones = []
        for r in docs.itertuples(index=False):
            if restante <= 0.01:
                break
            aplicar = min(restante, clp_round(float(r.pendiente)))
            if aplicar > 0:
                conn.execute("INSERT INTO aplicaciones_proveedores(pago_id,compra_id,monto) VALUES(?,?,?)",
                             (pago_id, int(r.id), aplicar))
                aplicaciones.append((int(r.id), aplicar))
                restante = clp_round(restante - aplicar)

        if restante > 0:
            raise ValueError("No fue posible aplicar completamente la porción correspondiente al proveedor.")

        observacion = glosa
        if diferencia > 0:
            observacion += f" | Diferencia {money(diferencia)} -> {cuenta_diferencia}"

        conn.execute("""UPDATE cartola_bancaria
                        SET conciliado=1,observacion=?,asiento_id=?,match_tipo='PROVEEDOR',match_id=?,match_confianza=100
                        WHERE id=?""",
                     (observacion, asiento_id, int(proveedor_id), int(movimiento_id)))
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    registrar_auditoria(conn, "PAGO PROVEEDOR DESDE CARTOLA",
                        f"Movimiento {movimiento_id} -> proveedor {proveedor_id}, aplicado {monto_proveedor}, diferencia {diferencia}, asiento {asiento_id}")
    return asiento_id, aplicaciones, diferencia


def contabilizar_pago_proveedor_sin_documento(conn, movimiento_id, proveedor_id):
    sgci_autorizar_operacion(conn, 'banco', 'contabilizar', 'Conciliación bancaria')
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


def revertir_abono_cliente_cartola(conn, movimiento_id):
    """Reversión conservadora y atómica de conciliación de cliente.

    Conserva el asiento original, crea reverso y elimina únicamente el registro
    auxiliar originado por esta conciliación. Nunca deshace aplicaciones posteriores.
    """
    sgci_autorizar_operacion(conn, 'banco', 'anular', 'Conciliación bancaria')
    mov = conn.execute('SELECT * FROM cartola_bancaria WHERE id=?', (int(movimiento_id),)).fetchone()
    if not mov or int(mov['conciliado'] or 0) != 1 or mov['match_tipo'] not in ('CLIENTE_ANTICIPO', 'CLIENTE'):
        raise ValueError('Selecciona un abono de cliente conciliado.')
    if float(mov['abono'] or 0) <= 0 or float(mov['cargo'] or 0) > 0:
        raise ValueError('El movimiento no es un abono bancario válido.')
    if not mov['asiento_id'] or periodo_cerrado(conn, mov['fecha']):
        raise ValueError('No existe asiento vinculado o el período original está cerrado.')
    lineas = conn.execute('SELECT * FROM libro_diario WHERE asiento_id=? ORDER BY id', (mov['asiento_id'],)).fetchall()
    if not lineas or abs(sum(float(l['debe'] or 0)-float(l['haber'] or 0) for l in lineas)) > 0.01:
        raise ValueError('El asiento original no existe o no está cuadrado.')
    lotes = {l['lote_id'] for l in lineas}
    if len(lotes) != 1 or not next(iter(lotes)):
        raise ValueError('El asiento original no tiene lote único; requiere revisión manual.')
    lote = next(iter(lotes))
    origenes = {l['origen'] for l in lineas}
    permitidos = {'CONCILIACION_ANTICIPO_CLIENTE', 'CONCILIACION_COBRO_CLIENTE',
                  'CONCILIACION_DIFERENCIA_CLIENTE'}
    if not origenes.issubset(permitidos):
        raise ValueError('El asiento contiene orígenes no compatibles con la reversión automática.')
    if conn.execute('SELECT 1 FROM cartola_bancaria WHERE asiento_id=? AND id<>?',
                    (mov['asiento_id'], int(movimiento_id))).fetchone():
        raise ValueError('El asiento pertenece a más de un movimiento bancario.')
    if conn.execute('SELECT 1 FROM libro_diario WHERE lote_id=? AND asiento_id<>?',
                    (lote, mov['asiento_id'])).fetchone():
        raise ValueError('El lote original aparece en otros asientos.')
    pagos = conn.execute('''SELECT * FROM pagos_clientes WHERE cartola_id=? OR lote_id=?
                          ORDER BY id''', (int(movimiento_id), lote)).fetchall()
    if len(pagos) != 1:
        raise ValueError('No se identificó un único abono del auxiliar; no se modificó nada.')
    pago = pagos[0]
    if pago['cliente_id'] is None or int(pago['cliente_id']) != int(mov['match_id'] or -1):
        raise ValueError('El cliente del auxiliar no coincide con la conciliación.')
    if pago['lote_id'] != lote:
        raise ValueError('El abono auxiliar no pertenece al lote contable original.')
    if pago['cartola_id'] is not None and int(pago['cartola_id']) != int(movimiento_id):
        raise ValueError('El abono está enlazado a otra cartola.')
    if conn.execute('SELECT 1 FROM aplicaciones_clientes WHERE pago_id=? LIMIT 1', (pago['id'],)).fetchone():
        raise ValueError('El abono ya tiene aplicaciones a facturas; reviértelas por su procedimiento específico.')
    if tabla_existe(conn, 'sgci_aplicaciones_apertura_clientes'):
        if conn.execute('SELECT 1 FROM sgci_aplicaciones_apertura_clientes WHERE pago_id=? OR movimiento_id=? LIMIT 1',
                        (pago['id'], int(movimiento_id))).fetchone():
            raise ValueError('El abono tiene aplicaciones a apertura; no puede revertirse automáticamente.')
    # No revertir cobros parcialmente aplicados ni con distribución documental.
    if mov['match_tipo'] == 'CLIENTE':
        raise ValueError('Los cobros aplicados a facturas requieren reversión documental; esta función solo revierte anticipos sin aplicar.')
    if origenes != {'CONCILIACION_ANTICIPO_CLIENTE'}:
        raise ValueError('El asiento no corresponde exclusivamente a un anticipo de cliente.')
    if abs(float(pago['monto_recibido'] or 0) - float(mov['abono'] or 0)) > 0.01:
        raise ValueError('El importe del auxiliar no coincide con el abono bancario.')
    if abs(float(pago['monto'] or 0)) > 0.01:
        raise ValueError('El anticipo ya tiene movimientos auxiliares; requiere revisión.')
    banco = conn.execute('SELECT cuenta_contable FROM bancos WHERE id=?', (mov['banco_id'],)).fetchone()
    if not banco or not banco['cuenta_contable']:
        raise ValueError('Banco sin cuenta contable configurada.')
    debe_banco = sum(float(l['debe'] or 0) for l in lineas if l['codigo_cuenta'] == banco['cuenta_contable'])
    if abs(debe_banco - float(mov['abono'] or 0)) > 0.01:
        raise ValueError('El asiento no coincide con el ingreso bancario.')
    # Transacción única: reverso + auxiliar + liberación de cartola + auditoría.
    try:
        conn.execute('BEGIN IMMEDIATE')
        nuevo = siguiente_asiento(conn) + 1
        rev_lote = 'REV-CLI-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        for l in lineas:
            conn.execute('''INSERT INTO libro_diario
                (fecha,cuenta,debe,haber,glosa,centro_costo,codigo_cuenta,asiento_id,lote_id,origen)
                VALUES(?,?,?,?,?,?,?,?,?,?)''',
                (mov['fecha'], l['cuenta'], float(l['haber'] or 0), float(l['debe'] or 0),
                 f"Reverso anticipo cliente, cartola {movimiento_id}, asiento {mov['asiento_id']} - {l['glosa'] or ''}",
                 l['centro_costo'], l['codigo_cuenta'], nuevo, rev_lote, 'REVERSO_CONCILIACION_CLIENTE'))
        eliminado = conn.execute('DELETE FROM pagos_clientes WHERE id=?', (pago['id'],))
        if eliminado.rowcount != 1:
            raise ValueError('No se pudo retirar el abono auxiliar.')
        actualizado = conn.execute('''UPDATE cartola_bancaria
            SET conciliado=0, observacion=NULL, asiento_id=NULL, match_tipo=NULL,
                match_id=NULL, match_confianza=NULL
            WHERE id=? AND conciliado=1 AND asiento_id=?''',
            (int(movimiento_id), mov['asiento_id']))
        if actualizado.rowcount != 1:
            raise ValueError('La cartola cambió durante la operación.')
        conn.execute('''INSERT INTO auditoria(fecha_hora,usuario,accion,detalle)
                        VALUES(?,?,?,?)''',
                     (datetime.now().isoformat(timespec='seconds'), 'SGCI',
                      'REVERSO ANTICIPO CLIENTE',
                      f"Cartola {movimiento_id}; abono auxiliar {pago['id']}; asiento original {mov['asiento_id']}; reverso {nuevo}"))
        conn.commit()
        return nuevo
    except Exception:
        conn.rollback()
        raise


def revertir_pago_proveedor_cartola(conn, movimiento_id):
    """Reversión atómica de pago bancario a proveedor, con comprobaciones de trazabilidad."""
    sgci_autorizar_operacion(conn, 'banco', 'anular', 'Conciliación bancaria')
    mov=conn.execute("SELECT * FROM cartola_bancaria WHERE id=?",(int(movimiento_id),)).fetchone()
    if not mov or int(mov['conciliado'] or 0)!=1 or mov['match_tipo'] not in ('PROVEEDOR','PROVEEDOR_SIN_DOCUMENTO'):
        raise ValueError('El movimiento no es un pago conciliado a proveedor.')
    if not mov['asiento_id'] or periodo_cerrado(conn,mov['fecha']):
        raise ValueError('No hay asiento vinculado o el período está cerrado.')
    lineas=conn.execute('SELECT * FROM libro_diario WHERE asiento_id=? ORDER BY id',(mov['asiento_id'],)).fetchall()
    if not lineas or abs(sum(float(l['debe'] or 0)-float(l['haber'] or 0) for l in lineas))>0.01:
        raise ValueError('El asiento original no existe o no está cuadrado.')
    lotes={l['lote_id'] for l in lineas}
    if len(lotes)!=1 or not next(iter(lotes)):
        raise ValueError('El asiento original no tiene un lote único.')
    lote=next(iter(lotes))
    origenes={l['origen'] for l in lineas}
    if not origenes.issubset({'CONCILIACION_BANCARIA','CONCILIACION_PAGO_PROVEEDOR','CONCILIACION_DIFERENCIA_PROVEEDOR','CONCILIACION_PAGO_PROVEEDOR_SIN_DOCUMENTO'}):
        raise ValueError('El asiento contiene orígenes que requieren revisión manual.')
    if conn.execute('SELECT 1 FROM cartola_bancaria WHERE asiento_id=? AND id<>?',(mov['asiento_id'],movimiento_id)).fetchone():
        raise ValueError('El asiento está vinculado a más de un movimiento.')
    pagos=conn.execute('SELECT * FROM pagos_proveedores WHERE lote_id=?',(lote,)).fetchall()
    if not pagos and mov['match_tipo']=='PROVEEDOR' and str(lote).startswith('CONC-BANCO-'):
        compra=conn.execute('SELECT proveedor_id FROM compras WHERE id=?',(mov['match_id'],)).fetchone()
        if not compra: raise ValueError('No se encontró el documento vinculado.')
        pagos=conn.execute("""SELECT DISTINCT p.* FROM pagos_proveedores p
            JOIN aplicaciones_proveedores a ON a.pago_id=p.id
            WHERE p.proveedor_id=? AND p.fecha=? AND a.compra_id=? AND ABS(p.monto-?)<0.01""",
            (compra['proveedor_id'],mov['fecha'],mov['match_id'],float(mov['cargo'] or 0))).fetchall()
    if len(pagos)!=1:
        raise ValueError('No se encontró un pago único asociado; no se realizó ningún cambio.')
    pago=pagos[0]
    if not str(lote).startswith('CONC-BANCO-') and int(pago['proveedor_id'])!=int(mov['match_id']):
        raise ValueError('El proveedor no coincide con la conciliación.')
    aplicaciones=conn.execute('SELECT * FROM aplicaciones_proveedores WHERE pago_id=?',(pago['id'],)).fetchall()
    aplicado=sum(abs(float(a['monto'] or 0)) for a in aplicaciones)
    if mov['match_tipo']=='PROVEEDOR' and (not aplicaciones or abs(aplicado-float(pago['monto'] or 0))>0.01):
        raise ValueError('Las aplicaciones del pago fueron modificadas; requiere revisión.')
    if mov['match_tipo']=='PROVEEDOR_SIN_DOCUMENTO' and aplicaciones:
        raise ValueError('Este pago sin documento ya fue aplicado; requiere revisión.')
    if str(lote).startswith('CONC-BANCO-'):
        if len(aplicaciones)!=1 or int(aplicaciones[0]['compra_id'])!=int(mov['match_id']):
            raise ValueError('El documento asociado no coincide; requiere revisión.')
    nuevo=siguiente_asiento(conn)+1
    rev_lote='REV-PROV-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    try:
        conn.execute('BEGIN IMMEDIATE')
        for l in lineas:
            conn.execute("""INSERT INTO libro_diario
                (fecha,cuenta,debe,haber,glosa,centro_costo,codigo_cuenta,asiento_id,lote_id,origen)
                VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (mov['fecha'],l['cuenta'],float(l['haber'] or 0),float(l['debe'] or 0),
                 'Reverso pago proveedor, cartola '+str(movimiento_id)+' - '+str(l['glosa'] or ''),
                 l['centro_costo'],l['codigo_cuenta'],nuevo,rev_lote,'REVERSO_CONCILIACION_PROVEEDOR'))
        conn.execute('DELETE FROM aplicaciones_proveedores WHERE pago_id=?',(pago['id'],))
        conn.execute('DELETE FROM pagos_proveedores WHERE id=?',(pago['id'],))
        cur=conn.execute("""UPDATE cartola_bancaria SET conciliado=0,observacion=NULL,asiento_id=NULL,
            match_tipo=NULL,match_id=NULL,match_confianza=NULL
            WHERE id=? AND conciliado=1 AND asiento_id=?""",(int(movimiento_id),mov['asiento_id']))
        if cur.rowcount!=1: raise ValueError('El movimiento cambió durante la operación.')
        conn.execute("""INSERT INTO auditoria(fecha_hora,usuario,accion,detalle) VALUES(?,?,?,?)""",
            (datetime.now().isoformat(timespec='seconds'),'SGCI','REVERSO PAGO PROVEEDOR',
             f"Cartola {movimiento_id}; pago {pago['id']}; asiento original {mov['asiento_id']}; reverso {nuevo}"))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return nuevo


def corregir_conciliacion_manual(conn, movimiento_id):
    """Revierte contablemente una imputación manual bancaria y reabre el movimiento para corregirlo."""
    sgci_autorizar_operacion(conn, 'banco', 'anular', 'Conciliación bancaria')
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
        ('2.1.02','Obligaciones laborales y previsionales','Pasivo','Pasivo','2.1',3),
        ('2.1.02.01','Remuneraciones por pagar','Pasivo','Pasivo','2.1.02',4),
        ('2.1.02.02','Cotizaciones previsionales por pagar','Pasivo','Pasivo','2.1.02',4),
        ('2.1.02.03','Retenciones de Trabajadores por pagar','Pasivo','Pasivo','2.1.02',4),
        ('2.1.02.04','Otras obligaciones laborales','Pasivo','Pasivo','2.1.02',4),
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
    """PDF tabular robusto: ajusta texto largo, anchos y orientación sin superponer celdas."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import landscape, A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_LEFT, TA_RIGHT
        from reportlab.lib.units import cm
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepInFrame
    except Exception as e:
        raise RuntimeError("ReportLab no está disponible para generar el PDF.") from e

    def esc(v):
        import html
        return html.escape("" if v is None else str(v)).replace("\n", "<br/>")

    n=max(len(columnas),1)
    page=A4
    usable=page[0]-2*cm
    # Peso por contenido: las columnas narrativas reciben más ancho que códigos/montos.
    pesos=[]
    for j,col in enumerate(columnas):
        muestras=[str(col)]+[str(f[j]) if j < len(f) else "" for f in filas[:80]]
        largo=max([len(x) for x in muestras] or [8])
        nombre=str(col).lower()
        if any(k in nombre for k in ("glosa","descripción","cuenta","trabajador","documento","nombre")):
            largo=max(largo,28)
        if any(k in nombre for k in ("debe","haber","saldo","cargo","abono","monto","total","imponible","descuento")):
            largo=min(max(largo,11),16)
        if any(k in nombre for k in ("descripción", "servicio", "glosa")):
            pesos.append(48)
        elif any(k in nombre for k in ("referencia",)):
            pesos.append(23)
        elif any(k in nombre for k in ("monto", "aplicado", "pendiente", "saldo")):
            pesos.append(16)
        elif nombre in ("días", "estado", "fecha", "vence", "factura"):
            pesos.append(11 if nombre != "días" else 7)
        else:
            pesos.append(min(max(largo,8),30))
    total_p=sum(pesos)
    widths=[usable*w/total_p for w in pesos]

    buf=io.BytesIO()
    doc=SimpleDocTemplate(buf,pagesize=page,rightMargin=1*cm,leftMargin=1*cm,topMargin=3.6*cm,bottomMargin=.8*cm)
    styles=getSampleStyleSheet()
    cell=ParagraphStyle("SGCICell",parent=styles["Normal"],fontName="Helvetica",fontSize=(5.2 if n>=9 else 6.2),leading=(6.6 if n>=9 else 8),wordWrap="CJK",alignment=TA_LEFT,spaceAfter=0,spaceBefore=0)
    head=ParagraphStyle("SGCIHead",parent=cell,fontName="Helvetica-Bold",textColor=colors.white,fontSize=(5.2 if n>=9 else 6.2),leading=(6.6 if n>=9 else 8))
    story=[Paragraph(esc(titulo),styles["Title"])]
    if subtitulo:
        story += [Paragraph(esc(subtitulo),styles["Normal"]),Spacer(1,8)]

    data=[[Paragraph(esc(x),head) for x in columnas]]
    for f in filas:
        data.append([Paragraph(esc(f[j] if j < len(f) else ""),cell) for j in range(n)])
    if totales:
        data.append([Paragraph(esc(totales[j] if j < len(totales) else ""),cell) for j in range(n)])

    t=Table(data,colWidths=widths,repeatRows=1,hAlign="LEFT")
    estilo=[
        ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#176B55")),
        ("TEXTCOLOR",(0,0),(-1,0),colors.white),
        ("GRID",(0,0),(-1,-1),0.30,colors.HexColor("#DCE8E3")),
        ("VALIGN",(0,0),(-1,-1),"TOP"),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#F3F7F5")]),
        ("LEFTPADDING",(0,0),(-1,-1),2),("RIGHTPADDING",(0,0),(-1,-1),2),
        ("TOPPADDING",(0,0),(-1,-1),3),("BOTTOMPADDING",(0,0),(-1,-1),3),
    ]
    if totales:
        estilo += [("FONTNAME",(0,-1),(-1,-1),"Helvetica-Bold"),
                   ("BACKGROUND",(0,-1),(-1,-1),colors.HexColor("#EAF5F0"))]
    t.setStyle(TableStyle(estilo))
    story.append(t)
    doc.build(story,onFirstPage=sgci_membrete_pdf,onLaterPages=sgci_membrete_pdf)
    buf.seek(0)
    return buf.getvalue()


def rrhh_pdf_liquidacion(conn, r):
    sgci_autorizar_operacion(conn,'nomina','ver','Liquidación mensual')
    sgci_autorizar_operacion(conn,'nomina','exportar','Liquidación mensual')
    ids = sgci_rrhh_ids_autorizados(conn,sgci_identidad_actual())
    if ids is not None and int(r.trabajador_id) not in ids:
        raise PermissionError('La liquidación está fuera del alcance autorizado.')
    """Formato de Asimex: solo presentación; no recalcula ni contabiliza."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepInFrame
    from reportlab.lib.units import cm
    from calendar import month_abbr
    from html import escape
    emp=conn.execute("SELECT razon_social,rut FROM empresa ORDER BY id LIMIT 1").fetchone()
    perfil_liq=sgci_perfil(conn)
    nombre_emp=str(perfil_liq.get('razon_social') or (emp['razon_social'] if emp else '') or 'Empresa')
    rut_emp=str(perfil_liq.get('rut') or (emp['rut'] if emp else '') or '')
    direccion_emp=', '.join(str(perfil_liq.get(c) or '') for c in ('direccion','comuna','ciudad') if perfil_liq.get(c))
    giro_emp=str(perfil_liq.get('giro') or '')
    trab=conn.execute("SELECT fecha_ingreso,tipo_contrato FROM nomina_trabajadores WHERE id=?",(r.trabajador_id,)).fetchone()
    contrato=trab['tipo_contrato'] if trab else ''
    ingreso=trab['fecha_ingreso'] if trab else ''
    try: ingreso=datetime.strptime(str(ingreso)[:10],'%Y-%m-%d').strftime('%d-%m-%Y')
    except (ValueError,TypeError): ingreso=str(ingreso or '')
    try:
        year,month=map(int,str(r.periodo).split('-')[:2])
        meses=['','ene','feb','mar','abr','may','jun','jul','ago','sep','oct','nov','dic']
        mes=f'{meses[month]}-{year%100:02d}'
        fecha_emision=f'{__import__("calendar").monthrange(year,month)[1]:02d}-{month:02d}-{year}'
    except (ValueError,IndexError): mes=str(r.periodo);fecha_emision=''
    style=ParagraphStyle('liquidacion_asimex',fontName='Helvetica',fontSize=8.4,leading=12)
    bold=ParagraphStyle('liquidacion_asimex_bold',parent=style,fontName='Helvetica-Bold')
    def P(x,b=False): return Paragraph(escape(str(x or '')),bold if b else style)
    def m(v): return money(v)
    def row(*xs): return [P(x) for x in xs]
    story=[]
    story.append(Table([[P('LIQUIDACIÓN DE REMUNERACIONES',True)]],colWidths=[17.1*cm],style=TableStyle([
        ('BOX',(0,0),(-1,-1),1,colors.black),('ALIGN',(0,0),(-1,-1),'CENTER'),('LEFTPADDING',(0,0),(-1,-1),10),('TOPPADDING',(0,0),(-1,-1),10),('BOTTOMPADDING',(0,0),(-1,-1),10)])))
    meta=[[P('SUCURSAL'),P(':'),P(''),P('MES'),P(':'),P(mes)],
          [P('EMPRESA'),P(':'),P(nombre_emp),P(''),P(''),P('')],
          [P('R.U.T.'),P(':'),P(rut_emp),P(''),P(''),P('')],
          [P('GIRO'),P(':'),P(giro_emp),P(''),P(''),P('')],
          [P('DIRECCIÓN'),P(':'),P(direccion_emp),P(''),P(''),P('')],
          [P('TRABAJADOR'),P(':'),P(r.nombre),P('CONTRATO'),P(':'),P(contrato)],
          [P('R.U.T.'),P(':'),P(r.rut),P('CENTRO DE COSTOS'),P(':'),P('')],
          [P('FECHA CONTRATO'),P(':'),P(ingreso),P(''),P(''),P('')],
          [P('CARGO'),P(':'),P(r.cargo),P(''),P(''),P('')],
          [P('DÍAS TRABAJADOS'),P(':'),P(r.dias_trabajados),P(''),P(''),P('')]]
    t=Table(meta,colWidths=[2.8*cm,.65*cm,6.0*cm,3.5*cm,.65*cm,3.5*cm],rowHeights=[None]*10)
    t.setStyle(TableStyle([('BOX',(0,0),(-1,-1),.8,colors.black),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),5),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]));story.append(t)
    def section(label,items):
        data=[[P(label,True),'','']]
        for name,detail,value in items:
            data.append([P(name),P(detail),P(m(value))])
        t=Table(data,colWidths=[6.4*cm,6.5*cm,4.2*cm])
        t.setStyle(TableStyle([('SPAN',(0,0),(-1,0)),('ALIGN',(0,0),(-1,0),'CENTER'),('LINEABOVE',(0,0),(-1,0),.8,colors.black),('LINEBELOW',(0,0),(-1,0),.8,colors.black),('ALIGN',(2,1),(2,-1),'RIGHT'),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('TOPPADDING',(0,0),(-1,0),10),('BOTTOMPADDING',(0,0),(-1,0),10),('TOPPADDING',(0,1),(-1,-1),5),('BOTTOMPADDING',(0,1),(-1,-1),5)]))
        story.append(t)
    hab=[('SUELDO BASE','',r.sueldo_periodo),('GRATIFICACIÓN','',r.gratificacion)]
    for label,field in [('HORAS EXTRAS','horas_extras'),('BONOS IMPONIBLES','bonos_imponibles'),('OTROS IMPONIBLES','otros_imponibles')]:
        if float(getattr(r,field,0) or 0): hab.append((label,'',getattr(r,field)))
    hab.append(('TOTAL IMPONIBLE','',r.total_imponible))
    for label,field in [('BONO NO IMPONIBLE','bono_no_imponible'),('VIÁTICOS Y MOVILIZACIÓN / ASIGNACIONES','asignacion_no_imponible'),('OTROS NO IMPONIBLES','otros_no_imponibles')]:
        if float(getattr(r,field,0) or 0): hab.append((label,'',getattr(r,field)))
    hab.extend([('TOTAL HABERES NO IMPONIBLES','',r.total_no_imponible),('TOTAL HABERES','',r.total_haberes)])
    section('HABERES',hab)
    afp_det=str(r.afp_nombre or '')
    if float(getattr(r,'afp_comision',0) or 0): afp_det+=f' · {10+float(r.afp_comision):.2f}%'
    salud_det=str(r.salud_tipo or '')
    if str(r.salud_tipo or '').lower()=='isapre' and getattr(r,'salud_modalidad',None): salud_det+=' · '+str(r.salud_modalidad)
    descuentos=[('A.F.P.',afp_det,r.afp_descuento),('SALUD',salud_det,r.salud_descuento),('AFC','',r.afc_descuento),('IMPTO. ÚNICO','',r.impuesto_unico)]
    if float(r.prestamo_descuento or 0): descuentos.append(('PRÉSTAMOS','',r.prestamo_descuento))
    if float(r.otros_descuentos or 0): descuentos.append(('OTROS DESCUENTOS','',r.otros_descuentos))
    descuentos.append(('TOTAL DESCUENTOS','',r.total_descuentos))
    section('DESCUENTOS',descuentos)
    story.append(Spacer(1,.6*cm))
    section('RESUMEN',[('ALCANCE LÍQUIDO','',r.liquido_periodo),('TOTAL ANTICIPOS','',r.anticipo),('TOTAL A PAGAR','',r.saldo_pagar)])
    story.append(Spacer(1,1.2*cm))
    story.append(Paragraph('Certifico que he recibido de '+escape(nombre_emp)+' el saldo indicado en la presente liquidación.',style))
    story.append(Spacer(1,.9*cm))
    story.append(Table([[P('FECHA EMISIÓN: '+fecha_emision),P('____________________________')],[P(''),P('RECIBÍ CONFORME')]],colWidths=[10*cm,7.1*cm],style=TableStyle([('ALIGN',(1,0),(1,-1),'CENTER')])) )
    out=io.BytesIO();doc=SimpleDocTemplate(out,pagesize=A4,leftMargin=1.95*cm,rightMargin=1.95*cm,topMargin=1.2*cm,bottomMargin=1.2*cm)
    # Ajuste proporcional del contenido para mantener la liquidación en una sola hoja A4.
    doc.build([KeepInFrame(16.85*cm, 25.0*cm, story, mode="shrink", hAlign="CENTER", vAlign="TOP")])
    return out.getvalue()


def pdf_desde_dataframe(titulo, subtitulo, df, columnas_monetarias=None, totales=None):
    """Convierte cualquier DataFrame del SGCI en reporte PDF imprimible."""
    if df is None or df.empty:
        return None
    columnas_monetarias=set(columnas_monetarias or [])
    filas=[]
    for _,r in df.iterrows():
        fila=[]
        for c in df.columns:
            v=r[c]
            if c in columnas_monetarias:
                v=money(v)
            elif pd.isna(v):
                v=""
            fila.append(v)
        filas.append(fila)
    return nomina_pdf(titulo,subtitulo,list(df.columns),filas,totales)


def nomina_asiento_linea(conn, fecha, codigo, debe, haber, glosa, asiento_id, origen='NOMINA'):
    if abs(float(debe or 0))+abs(float(haber or 0)) < .005: return
    nombre=Plan(conn).todos.get(codigo,codigo)
    conn.execute("INSERT INTO libro_diario(fecha,cuenta,debe,haber,glosa,codigo_cuenta,asiento_id,lote_id,origen) VALUES(?,?,?,?,?,?,?,?,?)",
                 (fecha,nombre,float(debe or 0),float(haber or 0),glosa,codigo,asiento_id,None,origen))


def nomina_registrar_pago_activo(conn, tabla, registro_id, fecha, monto, cuenta_activo, cuenta_banco, glosa):
    sgci_autorizar_operacion(conn, 'nomina', 'contabilizar', 'Contabilización')
    tipos = {'nomina_anticipos': ('monto', '1.1.07.01'),
             'nomina_prestamos': ('monto_original', '1.1.07.02')}
    if tabla not in tipos:
        raise ValueError('Tipo de movimiento de nómina inválido.')
    ids = sgci_rrhh_ids_autorizados(conn, sgci_identidad_actual())
    if ids is not None and not ids:
        raise PermissionError('No tienes trabajadores autorizados para esta operación.')
    _sgci_exigir_sin_transaccion(conn)
    with conn:
        conn.execute('BEGIN IMMEDIATE')
        parametros = [int(registro_id)]
        filtro = ''
        if ids is not None:
            filtro = ' AND trabajador_id IN (' + ','.join('?' for _ in ids) + ')'
            parametros.extend(sorted(ids))
        registro = conn.execute(f'SELECT * FROM {tabla} WHERE id=?' + filtro, parametros).fetchone()
        if registro is None:
            raise ValueError('Movimiento no disponible para esta operación.')
        if registro['contabilizado'] or registro['asiento_id']:
            raise ValueError('El movimiento ya está contabilizado.')
        if tabla == 'nomina_anticipos' and registro['anulado']:
            raise ValueError('El anticipo está anulado.')
        if tabla == 'nomina_prestamos' and registro['estado'] != 'VIGENTE':
            raise ValueError('El préstamo no está vigente.')
        campo_monto, cuenta_esperada = tipos[tabla]
        monto_guardado = _sgci_monto_auxiliar(registro[campo_monto])
        if str(fecha) != registro['fecha'] or _sgci_monto_auxiliar(monto) != monto_guardado:
            raise ValueError('El movimiento cambió. Actualiza la selección antes de contabilizar.')
        if cuenta_activo != cuenta_esperada:
            raise ValueError('La cuenta de anticipo o préstamo no corresponde al movimiento.')
        if periodo_cerrado(conn, registro['fecha']):
            raise ValueError('El período contable está cerrado.')
        banco = conn.execute('SELECT 1 FROM bancos WHERE activo=1 AND cuenta_contable=?',
                             (cuenta_banco,)).fetchone()
        if not banco or cuenta_banco not in Plan(conn).hojas:
            raise ValueError('La cuenta bancaria debe estar activa y ser imputable.')
        asiento=siguiente_asiento(conn)+1
        nomina_asiento_linea(conn,fecha,cuenta_activo,monto,0,glosa,asiento,'NOMINA_PAGO')
        nomina_asiento_linea(conn,fecha,cuenta_banco,0,monto,glosa,asiento,'NOMINA_PAGO')
        conn.execute(f"UPDATE {tabla} SET asiento_id=?, contabilizado=1 WHERE id=?",(asiento,registro_id))
        _sgci_auditar_auxiliar(conn, 'CONTABILIZAR ENTREGA NOMINA', f'{tabla}:{registro_id}; asiento:{asiento}')
    return asiento


def contabilizar_anticipo_nomina_desde_cartola(conn, movimiento_id, trabajador_id, periodo, observacion=""):
    sgci_autorizar_operacion(conn, 'banco', 'contabilizar', 'Conciliación bancaria')
    """Vincula un cargo real de cartola con un anticipo de nómina y lo contabiliza una sola vez."""
    ids = sgci_rrhh_ids_autorizados(conn, sgci_identidad_actual())
    if ids is not None and int(trabajador_id) not in ids:
        raise PermissionError('El trabajador está fuera de tu alcance de Recursos Humanos.')
    mov=conn.execute("SELECT * FROM cartola_bancaria WHERE id=?",(int(movimiento_id),)).fetchone()
    if not mov:
        raise ValueError("Movimiento bancario no encontrado.")
    if int(mov["conciliado"] or 0)==1:
        raise ValueError("Este movimiento ya está conciliado.")
    monto=clp_round(float(mov["cargo"] or 0))
    if monto<=0:
        raise ValueError("El anticipo de remuneración debe corresponder a un cargo/salida bancaria.")
    if periodo_cerrado(conn,mov["fecha"]):
        raise ValueError("El período contable de este movimiento está cerrado.")
    if not re.fullmatch(r"\d{4}-\d{2}",str(periodo or "")):
        raise ValueError("El período debe tener formato AAAA-MM.")

    tr=conn.execute("SELECT id,rut,nombre FROM nomina_trabajadores WHERE id=? AND activo=1",(int(trabajador_id),)).fetchone()
    if not tr:
        raise ValueError("Trabajador activo no encontrado.")
    banco=conn.execute("SELECT cuenta_contable FROM bancos WHERE id=?",(mov["banco_id"],)).fetchone()
    if not banco or not banco["cuenta_contable"]:
        raise ValueError("La cuenta bancaria no tiene cuenta contable vinculada.")

    # Evita duplicar el mismo anticipo si por error se vuelve a procesar el movimiento.
    marca=f"CARTOLA:{int(movimiento_id)}"
    dup=conn.execute("SELECT id FROM nomina_anticipos WHERE COALESCE(anulado,0)=0 AND observacion LIKE ?",(f"%{marca}%",)).fetchone()
    if dup:
        raise ValueError("Este movimiento de cartola ya fue vinculado previamente a un anticipo de nómina.")

    cuenta_activo="1.1.07.01"
    asiento=siguiente_asiento(conn)+1
    glosa=f"Anticipo remuneración {tr['nombre']} - {periodo}"
    obs=limpiar_texto(observacion) or glosa
    obs=f"{obs} | {marca}"
    try:
        nomina_asiento_linea(conn,mov["fecha"],cuenta_activo,monto,0,glosa,asiento,'NOMINA_ANTICIPO_CARTOLA')
        nomina_asiento_linea(conn,mov["fecha"],banco["cuenta_contable"],0,monto,glosa,asiento,'NOMINA_ANTICIPO_CARTOLA')
        cur=conn.execute("""INSERT INTO nomina_anticipos
            (trabajador_id,periodo,fecha,monto,observacion,asiento_id,contabilizado)
            VALUES(?,?,?,?,?,?,1)""",
            (int(trabajador_id),str(periodo),mov["fecha"],monto,obs,asiento))
        anticipo_id=cur.lastrowid
        conn.execute("""UPDATE cartola_bancaria
                        SET conciliado=1,observacion=?,asiento_id=?,match_tipo='NOMINA_ANTICIPO',match_id=?,match_confianza=100
                        WHERE id=?""",
                     (glosa,asiento,int(anticipo_id),int(movimiento_id)))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    registrar_auditoria(conn,"ANTICIPO NOMINA DESDE CARTOLA",
                        f"Movimiento {movimiento_id} -> trabajador {trabajador_id}, período {periodo}, monto {monto}, asiento {asiento}")
    return asiento, anticipo_id



def revertir_anticipo_nomina_cartola(conn, movimiento_id):
    # Revierte exclusivamente anticipos creados desde cartola.
    sgci_autorizar_operacion(conn, 'banco', 'anular', 'Conciliación bancaria')
    ids = sgci_rrhh_ids_autorizados(conn, sgci_identidad_actual())
    if ids is not None and not ids:
        raise PermissionError('No tienes trabajadores autorizados para esta operación.')
    mov = conn.execute("SELECT * FROM cartola_bancaria WHERE id=?", (int(movimiento_id),)).fetchone()
    if not mov or int(mov['conciliado'] or 0)!=1 or mov['match_tipo']!='NOMINA_ANTICIPO':
        raise ValueError('El movimiento no es un anticipo de nómina conciliado.')
    if not mov['asiento_id'] or not mov['match_id']:
        raise ValueError('Falta la vinculación contable del anticipo.')
    parametros = [mov['match_id']]
    filtro = ''
    if ids is not None:
        filtro = ' AND trabajador_id IN (' + ','.join('?' for _ in ids) + ')'
        parametros.extend(sorted(ids))
    ant = conn.execute('SELECT * FROM nomina_anticipos WHERE id=?' + filtro, parametros).fetchone()
    if not ant or int(ant['anulado'] or 0)!=0 or int(ant['contabilizado'] or 0)!=1:
        raise ValueError('El anticipo no existe, ya fue anulado o no está contabilizado.')
    if int(ant['asiento_id'] or 0)!=int(mov['asiento_id']):
        raise ValueError('El asiento del anticipo no coincide con la cartola.')
    if periodo_cerrado(conn,mov['fecha']):
        raise ValueError('El período contable está cerrado. Requiere revisión contable.')
    if conn.execute("SELECT 1 FROM nomina_liquidaciones WHERE trabajador_id=? AND periodo=? AND ABS(COALESCE(anticipo,0))>0.01", (ant['trabajador_id'],ant['periodo'])).fetchone():
        raise ValueError('Existe una liquidación con anticipo aplicado a este trabajador y período. Revisar antes de revertir.')
    if conn.execute("SELECT 1 FROM cartola_bancaria WHERE asiento_id=? AND id<>?", (mov['asiento_id'],movimiento_id)).fetchone():
        raise ValueError('El asiento está asociado a más de un movimiento bancario.')
    lineas=conn.execute('SELECT * FROM libro_diario WHERE asiento_id=? ORDER BY id', (mov['asiento_id'],)).fetchall()
    banco=conn.execute('SELECT cuenta_contable FROM bancos WHERE id=?', (mov['banco_id'],)).fetchone()
    monto=clp_round(mov['cargo'] or 0)
    if not banco or not banco['cuenta_contable'] or monto<=0 or len(lineas)!=2:
        raise ValueError('La estructura bancaria del anticipo requiere revisión manual.')
    if any(l['origen']!='NOMINA_ANTICIPO_CARTOLA' for l in lineas):
        raise ValueError('El asiento contiene líneas ajenas al anticipo de cartola.')
    debitos=sum(float(l['debe'] or 0) for l in lineas)
    creditos=sum(float(l['haber'] or 0) for l in lineas)
    if abs(debitos-creditos)>0.01 or abs(debitos-monto)>0.01:
        raise ValueError('El asiento original no coincide con el cargo bancario.')
    if not any(l['codigo_cuenta']=='1.1.07.01' and abs(float(l['debe'] or 0)-monto)<0.01 and abs(float(l['haber'] or 0))<0.01 for l in lineas):
        raise ValueError('No coincide el débito a anticipos del personal.')
    if not any(l['codigo_cuenta']==banco['cuenta_contable'] and abs(float(l['haber'] or 0)-monto)<0.01 and abs(float(l['debe'] or 0))<0.01 for l in lineas):
        raise ValueError('No coincide el crédito a la cuenta bancaria.')
    nuevo=siguiente_asiento(conn)+1
    lote='REV-NOMINA-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    try:
        conn.execute('BEGIN IMMEDIATE')
        for l in lineas:
            conn.execute('''INSERT INTO libro_diario
                (fecha,cuenta,debe,haber,glosa,centro_costo,codigo_cuenta,asiento_id,lote_id,origen)
                VALUES(?,?,?,?,?,?,?,?,?,?)''',
                (mov['fecha'],l['cuenta'],float(l['haber'] or 0),float(l['debe'] or 0),
                 'Reverso anticipo mal asignado, cartola '+str(movimiento_id)+' / asiento '+str(mov['asiento_id']),
                 l['centro_costo'],l['codigo_cuenta'],nuevo,lote,'REVERSO_NOMINA_ANTICIPO_CARTOLA'))
        actualizado=conn.execute('''UPDATE nomina_anticipos SET anulado=1, asiento_reverso_id=?,
            observacion=COALESCE(observacion,'') || ' | ANULADO POR REVERSO ' || ?
            WHERE id=? AND COALESCE(anulado,0)=0 AND asiento_id=?''',
            (nuevo,nuevo,ant['id'],mov['asiento_id']))
        if actualizado.rowcount!=1:
            raise ValueError('El anticipo cambió durante la operación.')
        actualizado=conn.execute('''UPDATE cartola_bancaria SET conciliado=0,observacion=NULL,
            asiento_id=NULL,match_tipo=NULL,match_id=NULL,match_confianza=NULL
            WHERE id=? AND conciliado=1 AND match_tipo='NOMINA_ANTICIPO' AND asiento_id=? AND match_id=?''',
            (int(movimiento_id),mov['asiento_id'],ant['id']))
        if actualizado.rowcount!=1:
            raise ValueError('La conciliación cambió durante la operación.')
        conn.execute('''INSERT INTO auditoria(fecha_hora,usuario,accion,detalle) VALUES(?,?,?,?)''',
            (datetime.now().isoformat(timespec='seconds'),sgci_identidad_actual(),
             'REVERSO ANTICIPO NOMINA',
             f"Cartola {movimiento_id}; anticipo {ant['id']}; asiento original {mov['asiento_id']}; reverso {nuevo}; monto {monto}"))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return nuevo


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


def nomina_vista_previa(conn, periodo):
    """Construye exactamente las partidas que usará la contabilización, sin escribir en BD."""
    liq=pd.read_sql_query("SELECT * FROM nomina_liquidaciones WHERE periodo=?",conn,params=(periodo,))
    if liq.empty: raise ValueError('No existen liquidaciones para el período.')
    if (liq['estado']=='CONTABILIZADO').any():
        raise ValueError('Hay liquidaciones contabilizadas en este período; se impide duplicar el asiento.')
    if not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])',str(periodo)):
        raise ValueError('Período inválido.')
    y,m=map(int,periodo.split('-'))
    fecha=(date(y+1,1,1)-timedelta(days=1) if m==12 else date(y,m+1,1)-timedelta(days=1)).isoformat()
    if periodo_cerrado(conn,fecha): raise ValueError('El período contable ya está cerrado.')
    tot=lambda c: sum(clp_round(v) for v in liq[c].fillna(0))
    # Los montos se suman por trabajador, evitando diferencias de redondeo.
    sueldo=sum(tot(c) for c in ['sueldo_periodo','horas_extras','bonos_imponibles','otros_imponibles'])
    valores=[
        ('5.2.03.01',sueldo,0),('5.2.03.02',tot('gratificacion'),0),
        ('5.2.03.03',tot('total_no_imponible'),0),
        ('2.1.02.02',0,tot('afp_descuento')+tot('salud_descuento')+tot('afc_descuento')),
        ('2.1.02.05',0,tot('impuesto_unico')),
        ('2.1.02.03',0,tot('otros_descuentos')),
        ('1.1.07.01',0,tot('anticipo')),
        ('1.1.07.02',0,tot('prestamo_descuento')),
        ('2.1.02.01',0,tot('saldo_pagar'))]
    plan=Plan(conn).todos
    faltantes=[cod for cod,d,h in valores if (d or h) and cod not in plan]
    if faltantes: raise ValueError('Faltan cuentas en el plan: '+', '.join(faltantes))
    filas=[{'Código':cod,'Cuenta':plan.get(cod,cod),'Debe':int(d),'Haber':int(h)} for cod,d,h in valores if d or h]
    debe=sum(f['Debe'] for f in filas); haber=sum(f['Haber'] for f in filas)
    return fecha,filas,debe,haber


def nomina_contabilizar_periodo(conn, periodo):
    """Contabilización atómica: evita duplicados y períodos parcialmente contabilizados."""
    sgci_autorizar_operacion(conn, 'nomina', 'contabilizar', 'Contabilización')
    if sgci_rrhh_ids_autorizados(conn,sgci_identidad_actual()) is not None:
        raise PermissionError('La contabilización general de nómina requiere autorización expresa para todos los trabajadores.')
    if conn.in_transaction:
        raise RuntimeError('Hay una transacción pendiente. Guarde o revierta antes de contabilizar Nómina.')
    try:
        # Bloquea otros escritores hasta registrar asiento y estados en una sola transacción.
        conn.execute('BEGIN IMMEDIATE')
        previo = conn.execute(
            "SELECT estado, asiento_id FROM nomina_periodos WHERE periodo=?", (periodo,)
        ).fetchone()
        if previo and (previo['estado'] == 'CONTABILIZADO' or previo['asiento_id'] is not None):
            raise ValueError('El período ya tiene un asiento registrado; no se permite duplicar.')
        fecha, filas, debe, haber = nomina_vista_previa(conn, periodo)
        if debe != haber or debe <= 0:
            raise ValueError(f'Asiento de nómina inválido: Debe {debe:,.0f} / Haber {haber:,.0f}.')
        asiento = siguiente_asiento(conn) + 1
        for fila in filas:
            nomina_asiento_linea(conn, fecha, fila['Código'], fila['Debe'],
                                fila['Haber'], f'Nómina {periodo}', asiento)
        actualizados = conn.execute(
            "UPDATE nomina_liquidaciones SET estado='CONTABILIZADO' "
            "WHERE periodo=? AND COALESCE(estado,'')<>'CONTABILIZADO'", (periodo,)
        ).rowcount
        if actualizados <= 0:
            raise ValueError('No hay liquidaciones pendientes; no se creó asiento.')
        conn.execute("INSERT OR IGNORE INTO nomina_periodos(periodo) VALUES(?)", (periodo,))
        conn.execute(
            "UPDATE nomina_periodos SET estado='CONTABILIZADO',fecha_cierre=?,asiento_id=? "
            "WHERE periodo=?", (fecha, asiento, periodo)
        )
        conn.commit()
        return asiento
    except Exception:
        conn.rollback()
        raise


# ============================================================
# FACTURACIÓN DTE: REPOSITORIO DOCUMENTAL (SIN CONTABILIZACIÓN)
# ============================================================


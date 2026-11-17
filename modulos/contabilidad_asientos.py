# CONTEM: componente extraído del app.py original; ejecución secuencial compartida.

def contem_guardar_asientos(conn, filas, origen='Asiento manual'):
    """Valida y registra el lote completo bajo una única reserva de escritura."""
    from datetime import date, datetime
    from decimal import Decimal
    from uuid import uuid4
    sgci_autorizar_operacion(conn,'contabilidad','contabilizar','Asientos y Saldos')
    if conn.in_transaction:
        raise ValueError('Hay una transacción pendiente; no se modificó.')
    if origen not in ('Asiento manual','Saldo inicial') or not filas:
        raise ValueError('Indica un tipo y líneas válidas para el asiento.')
    with conn:
        conn.execute('BEGIN IMMEDIATE')
        sgci_autorizar_operacion(conn,'contabilidad','contabilizar','Asientos y Saldos')
        plan=Plan(conn).hojas
        normalizadas=[];grupos={}
        for fila in filas:
            fecha=date.fromisoformat(str(fila['fecha'])).isoformat()
            codigo=str(fila['codigo']);grupo=str(fila.get('grupo',1))
            debe=Decimal(str(fila['debe']));haber=Decimal(str(fila['haber']))
            if (not debe.is_finite() or not haber.is_finite() or debe<0 or haber<0 or
                    debe!=debe.to_integral_value() or haber!=haber.to_integral_value() or
                    (debe>0)==(haber>0)):
                raise ValueError('Cada línea requiere un monto CLP entero positivo en un solo lado.')
            if codigo not in plan:
                raise ValueError('La cuenta ya no es imputable.')
            if periodo_cerrado(conn,fecha):
                raise ValueError('El período está cerrado.')
            glosa=str(fila.get('glosa') or '').strip()
            if not glosa:raise ValueError('La glosa es obligatoria.')
            datos=grupos.setdefault(grupo,[fecha,0,0])
            if datos[0]!=fecha:raise ValueError('Las líneas de un asiento deben tener la misma fecha.')
            datos[1]+=int(debe);datos[2]+=int(haber)
            cuenta=conn.execute('SELECT nombre FROM plan_cuentas WHERE codigo=?',(codigo,)).fetchone()[0]
            normalizadas.append((grupo,fecha,cuenta,int(debe),int(haber),glosa,
                str(fila.get('centro') or 'General / Ninguno'),codigo))
        if any(d!=h or d<=0 for _,d,h in grupos.values()):raise ValueError('El asiento no cuadra.')
        base=conn.execute('SELECT COALESCE(MAX(asiento_id),0) FROM libro_diario').fetchone()[0]
        mapa={g:int(base)+i+1 for i,g in enumerate(grupos)}
        lote=('SALDO-INI-' if origen=='Saldo inicial' else 'MANUAL-')+uuid4().hex
        conn.executemany('''INSERT INTO libro_diario
            (fecha,cuenta,debe,haber,glosa,centro_costo,codigo_cuenta,asiento_id,lote_id,origen)
            VALUES(?,?,?,?,?,?,?,?,?,?)''',[(fecha,cuenta,d,h,glosa,centro,codigo,mapa[g],lote,origen)
                for g,fecha,cuenta,d,h,glosa,centro,codigo in normalizadas])
        conn.execute('INSERT INTO auditoria(fecha_hora,usuario,accion,detalle) VALUES(?,?,?,?)',
            (datetime.now().isoformat(timespec='seconds'),sgci_identidad_actual(),'ASIENTOS MANUALES',lote))
    return {'lote':lote,'asientos':list(mapa.values())}


def contem_guardar_f29(conn,periodo,fecha,debito,credito):
    from datetime import date,datetime
    from decimal import Decimal
    sgci_autorizar_operacion(conn,'contabilidad','contabilizar','Asientos y Saldos')
    if conn.in_transaction:raise ValueError('Hay una transacción pendiente; no se modificó.')
    if date.fromisoformat(str(periodo)+'-01').strftime('%Y-%m')!=periodo:
        raise ValueError('Período inválido.')
    fecha=date.fromisoformat(str(fecha)).isoformat()
    d=Decimal(str(debito));c=Decimal(str(credito))
    if (not d.is_finite() or not c.is_finite() or d<=0 or c<0 or c>d or
            d!=d.to_integral_value() or c!=c.to_integral_value()):
        raise ValueError('Revisa los montos CLP de débito y crédito.')
    with conn:
        conn.execute('BEGIN IMMEDIATE')
        sgci_autorizar_operacion(conn,'contabilidad','contabilizar','Asientos y Saldos')
        if periodo_cerrado(conn,fecha) or periodo_cerrado(conn,periodo+'-01'):
            raise ValueError('El período está cerrado.')
        conn.execute('''CREATE TABLE IF NOT EXISTS compensaciones_iva_f29 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,periodo TEXT NOT NULL UNIQUE,
            fecha_contable TEXT NOT NULL,iva_debito REAL NOT NULL DEFAULT 0,
            iva_credito REAL NOT NULL DEFAULT 0,iva_por_pagar REAL NOT NULL DEFAULT 0,
            asiento_id INTEGER,creado_en TEXT DEFAULT CURRENT_TIMESTAMP)''')
        if conn.execute('SELECT 1 FROM compensaciones_iva_f29 WHERE periodo=?',(periodo,)).fetchone():
            raise ValueError('Ese período ya fue compensado.')
        lineas=[('2.1.01.02',int(d),0)]
        if c:lineas.append(('1.1.03.02',0,int(c)))
        if d-c:lineas.append(('2.1.01.03',0,int(d-c)))
        plan=Plan(conn).hojas
        if any(cod not in plan for cod,_,_ in lineas):raise ValueError('Cuenta IVA no imputable.')
        asiento=int(conn.execute('SELECT COALESCE(MAX(asiento_id),0)+1 FROM libro_diario').fetchone()[0])
        for cod,debe,haber in lineas:
            nombre=conn.execute('SELECT nombre FROM plan_cuentas WHERE codigo=?',(cod,)).fetchone()[0]
            conn.execute('''INSERT INTO libro_diario(fecha,cuenta,debe,haber,glosa,centro_costo,codigo_cuenta,asiento_id,lote_id,origen)
                VALUES(?,?,?,?,?,'General / Ninguno',?,?,?,'Compensación IVA F29')''',
                (fecha,nombre,debe,haber,'Compensación IVA F29 período '+periodo,cod,asiento,'F29-'+periodo))
        conn.execute('INSERT INTO compensaciones_iva_f29(periodo,fecha_contable,iva_debito,iva_credito,iva_por_pagar,asiento_id) VALUES(?,?,?,?,?,?)',
            (periodo,fecha,int(d),int(c),int(d-c),asiento))
        conn.execute('INSERT INTO auditoria(fecha_hora,usuario,accion,detalle) VALUES(?,?,?,?)',
            (datetime.now().isoformat(timespec='seconds'),sgci_identidad_actual(),'COMPENSACION IVA F29',periodo))
    return asiento

def contem_cambiar_cierre(conn,periodo,cerrar=True):
    from datetime import date,datetime
    import calendar
    sgci_autorizar_operacion(conn,'administracion','aprobar','Cierre Mensual')
    if conn.in_transaction:raise ValueError('Hay una transacción pendiente; no se modificó.')
    inicio=date.fromisoformat(str(periodo)+'-01')
    if inicio.strftime('%Y-%m')!=periodo:raise ValueError('Período inválido.')
    fin=inicio.replace(day=calendar.monthrange(inicio.year,inicio.month)[1]).isoformat()
    with conn:
        conn.execute('BEGIN IMMEDIATE')
        sgci_autorizar_operacion(conn,'administracion','aprobar','Cierre Mensual')
        estado=conn.execute('SELECT estado FROM periodos_contables WHERE periodo=?',(periodo,)).fetchone()
        actual=estado[0] if estado else 'ABIERTO'
        esperado='ABIERTO' if cerrar else 'CERRADO'
        if actual!=esperado:raise ValueError('El período cambió de estado; actualiza la pantalla.')
        if cerrar:
            diferencia=conn.execute('SELECT COALESCE(SUM(debe-haber),0) FROM libro_diario WHERE fecha BETWEEN ? AND ?',
                (inicio.isoformat(),fin)).fetchone()[0]
            if abs(diferencia)>0.01:raise ValueError('Libro diario descuadrado.')
            for consulta in (conciliacion_clientes,conciliacion_proveedores):
                df=consulta(conn)
                if not df.empty and abs(float(df.iloc[0]['Diferencia']))>0.01:
                    raise ValueError('Existen diferencias en auxiliares; revisa antes de cerrar.')
        conn.execute('''INSERT INTO periodos_contables(periodo,estado,fecha_cierre) VALUES(?,?,?)
            ON CONFLICT(periodo) DO UPDATE SET estado=excluded.estado,fecha_cierre=excluded.fecha_cierre''',
            (periodo,'CERRADO' if cerrar else 'ABIERTO',datetime.now().isoformat(timespec='seconds') if cerrar else None))
        conn.execute('INSERT INTO auditoria(fecha_hora,usuario,accion,detalle) VALUES(?,?,?,?)',
            (datetime.now().isoformat(timespec='seconds'),sgci_identidad_actual(),'CIERRE CONTABLE' if cerrar else 'REAPERTURA CONTABLE',periodo))


def obtener_entidad(
    conn,
    tabla,
    rut,
    razon_social
):
    if tabla not in ('proveedores', 'clientes'):
        raise ValueError('Entidad RCV no válida.')
    sgci_autorizar_operacion(
        conn, 'cxp' if tabla == 'proveedores' else 'cxc',
        'contabilizar', 'RCV Compras' if tabla == 'proveedores' else 'RCV Ventas')

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

    if tipo not in ('compras', 'ventas'):
        raise ValueError('Tipo de RCV no válido.')
    sgci_autorizar_operacion(conn, 'cxp' if tipo == 'compras' else 'cxc',
        'contabilizar', 'RCV Compras' if tipo == 'compras' else 'RCV Ventas')
    compras = tipo == "compras"

    plan = Plan(conn)
    roles = cargar_roles(conn)

    lote = (
        "RCV-COMPRAS-"
        if compras
        else "RCV-VENTAS-"
    ) + datetime.now().strftime("%Y%m%d-%H%M%S-%f")

    cur = conn.cursor()
    asiento = siguiente_asiento(conn)

    documentos = 0
    total_debe = 0.0
    cuentas_recordadas = 0

    try:

        for d in docs.itertuples():

            fecha = d.fecha_doc if fecha_modo == 'documento' else (d.fecha_recepcion or d.fecha_doc)
            if periodo_cerrado(conn,fecha):
                raise ValueError('El período del documento está cerrado; no se puede contabilizar el RCV.')

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
# RECUPERACIÓN DE DATOS TRIBUTARIOS DESDE RCV HISTÓRICO
# ============================================================


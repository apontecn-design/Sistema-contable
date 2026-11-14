# CONTEM: componente extraído del app.py original; ejecución secuencial compartida.

def panel_inicio_datos(conn, periodo):
    sgci_autorizar_operacion(conn,'inicio','ver','Panel principal')
    if not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])',str(periodo)):
        raise ValueError('Período inválido.')
    permisos={
        'finanzas':('contabilidad','Estados Financieros'),
        'bancos':('banco','Bancos y cartolas'),
        'conciliacion':('banco','Conciliación bancaria'),
        'diario':('contabilidad','Libro Diario'),
        'tesoreria':('tesoreria','Historial'),
        'proveedores':('cxp','Proveedores y estados de cuenta')}
    datos={clave:sgci_puede_submodulo(conn,modulo,sub,'ver') for clave,(modulo,sub) in permisos.items()}
    datos.update({clave:None for clave in ('ingresos','gastos','saldo_banco','pendientes_pago','pendientes_tes','pendientes_cartola','flujo','categorias','actividad','solicitudes','pendientes')})
    def autorizar(clave):
        modulo,sub=permisos[clave]
        sgci_autorizar_operacion(conn,modulo,'ver',sub)
    def valor(sql,parametros=()):return float(conn.execute(sql,parametros).fetchone()[0] or 0)
    if datos['finanzas']:
        autorizar('finanzas')
        datos['ingresos']=valor("SELECT COALESCE(SUM(haber-debe),0) FROM libro_diario WHERE substr(fecha,1,7)=? AND codigo_cuenta LIKE '4.%'",(periodo,))
        datos['gastos']=valor("SELECT COALESCE(SUM(debe-haber),0) FROM libro_diario WHERE substr(fecha,1,7)=? AND (codigo_cuenta LIKE '5.%' OR codigo_cuenta LIKE '6.%')",(periodo,))
        datos['flujo']=pd.read_sql_query("""SELECT substr(fecha,1,7) AS mes,
            SUM(CASE WHEN codigo_cuenta LIKE '4.%' THEN haber-debe ELSE 0 END) AS Ingresos,
            SUM(CASE WHEN codigo_cuenta LIKE '5.%' OR codigo_cuenta LIKE '6.%' THEN debe-haber ELSE 0 END) AS Egresos
            FROM libro_diario WHERE fecha IS NOT NULL GROUP BY substr(fecha,1,7) ORDER BY mes DESC LIMIT 6""",conn)
        datos['categorias']=pd.read_sql_query("""SELECT COALESCE(NULLIF(c.nombre,''),d.codigo_cuenta) AS Cuenta,
            SUM(d.debe-d.haber) AS Monto FROM libro_diario d LEFT JOIN plan_cuentas c ON c.codigo=d.codigo_cuenta
            WHERE substr(d.fecha,1,7)=? AND (d.codigo_cuenta LIKE '5.%' OR d.codigo_cuenta LIKE '6.%')
            GROUP BY d.codigo_cuenta HAVING ABS(SUM(d.debe-d.haber))>0 ORDER BY ABS(SUM(d.debe-d.haber)) DESC LIMIT 6""",conn,params=(periodo,))
    if datos['bancos']:
        autorizar('bancos')
        datos['saldo_banco']=valor('SELECT COALESCE(SUM(d.debe-d.haber),0) FROM libro_diario d WHERE d.codigo_cuenta IN (SELECT cuenta_contable FROM bancos WHERE activo=1)')
    if datos['conciliacion']:
        autorizar('conciliacion')
        datos['pendientes_cartola']=int(valor('SELECT COUNT(*) FROM cartola_bancaria WHERE conciliado=0'))
    if datos['diario']:
        autorizar('diario')
        datos['actividad']=pd.read_sql_query('SELECT fecha,cuenta,glosa,debe,haber FROM libro_diario ORDER BY id DESC LIMIT 7',conn)
    if datos['tesoreria']:
        autorizar('tesoreria')
        datos['pendientes_pago']=int(valor("SELECT COUNT(*) FROM tes_solicitudes WHERE estado='PENDIENTE_CONTABILIZACION'"))
        datos['pendientes_tes']=int(valor("SELECT COUNT(*) FROM tes_solicitudes WHERE estado IN ('BORRADOR','ENVIADA','APROBADA')"))
        datos['solicitudes']=pd.read_sql_query('''SELECT s.id,s.beneficiario,s.estado,COALESCE(SUM(d.monto),0) AS monto
            FROM tes_solicitudes s LEFT JOIN tes_solicitud_detalle d ON d.solicitud_id=s.id
            GROUP BY s.id ORDER BY s.id DESC LIMIT 7''',conn)
    if datos['proveedores']:
        autorizar('proveedores')
        pendientes=pd.read_sql_query('''SELECT p.nombre AS proveedor,c.folio,c.fecha,
            ROUND(ABS(COALESCE(c.monto_total,0))-COALESCE((SELECT SUM(ABS(a.monto)) FROM aplicaciones_proveedores a WHERE a.compra_id=c.id),0)) AS saldo
            FROM compras c LEFT JOIN proveedores p ON p.id=c.proveedor_id
            WHERE c.tipo_doc NOT IN (60,61,52) OR c.tipo_doc IS NULL ORDER BY c.fecha DESC LIMIT 100''',conn)
        datos['pendientes']=pendientes[pendientes.saldo>0].head(7) if not pendientes.empty else pendientes
    return datos

def balance_ocho_columnas(conn, desde=None, hasta=None):
    sgci_autorizar_operacion(conn, 'contabilidad', 'ver', 'Balance de Comprobación')
    from modulos.balance_ocho_columnas import generar_balance_ocho_columnas
    return generar_balance_ocho_columnas(conn, desde, hasta)


def exportar_balance_ocho(conn, desde=None, hasta=None, formato='pdf'):
    sgci_autorizar_operacion(conn, 'contabilidad', 'ver', 'Balance de Comprobación')
    sgci_autorizar_operacion(conn, 'contabilidad', 'exportar', 'Balance de Comprobación')
    from modulos.balance_ocho_columnas import generar_balance_ocho_columnas, balance_ocho_pdf, balance_ocho_excel
    informe = generar_balance_ocho_columnas(conn, desde, hasta)
    if formato == 'pdf':
        return balance_ocho_pdf(informe, desde, hasta, sgci_membrete_pdf)
    if formato == 'xlsx':
        return balance_ocho_excel(informe, desde, hasta)
    raise ValueError('Formato de balance no permitido.')


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
    sgci_autorizar_operacion(conn,'administracion','anular','Lotes')

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


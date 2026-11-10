# CONTEM: componente extraído del app.py original; ejecución secuencial compartida.
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


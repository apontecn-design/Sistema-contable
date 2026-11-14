# CONTEM: componente extraído del app.py original; ejecución secuencial compartida.
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
            CASE WHEN v.tipo_doc IN (60,61) THEN 0 ELSE ABS(COALESCE(v.monto_total,0)) END AS cargo,
            CASE WHEN v.tipo_doc IN (60,61) THEN ABS(COALESCE(v.monto_total,0)) ELSE 0 END AS abono
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
            CASE WHEN c.tipo_doc IN (60,61) THEN 0 ELSE ABS(COALESCE(c.monto_total,0)) END AS cargo,
            CASE WHEN c.tipo_doc IN (60,61) THEN ABS(COALESCE(c.monto_total,0)) ELSE 0 END AS abono
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

    sgci_crear_devoluciones_proveedor(conn)
    filtros_dev = ['d.proveedor_id=?']
    parametros_dev = [proveedor_id]
    if desde:
        filtros_dev.append('d.fecha >= ?')
        parametros_dev.append(desde)
    if hasta:
        filtros_dev.append('d.fecha <= ?')
        parametros_dev.append(hasta)
    devoluciones = pd.read_sql_query(f"""SELECT d.fecha, NULL AS tipo_doc, NULL AS folio,
        d.glosa, d.monto AS cargo, 0 AS abono
        FROM sgci_devoluciones_proveedor d
        WHERE {' AND '.join(filtros_dev)} ORDER BY d.fecha,d.id""",
        conn, params=parametros_dev)
    df = pd.concat([compras, pagos, devoluciones], ignore_index=True)

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


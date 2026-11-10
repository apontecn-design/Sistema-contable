# CONTEM: componente extraído del app.py original; ejecución secuencial compartida.
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
                    SELECT SUM(CASE WHEN c.tipo_doc IN (60,61)
                                    THEN -ABS(COALESCE(c.monto_total,0))
                                    ELSE ABS(COALESCE(c.monto_total,0)) END)
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


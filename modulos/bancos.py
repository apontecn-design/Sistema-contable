# CONTEM: componente extraído del app.py original; ejecución secuencial compartida.

def contem_guardar_banco(conn,nombre,numero,tipo,codigo,saldo=0):
    from datetime import datetime
    from decimal import Decimal
    sgci_autorizar_operacion(conn,'banco','crear','Bancos y cartolas')
    if conn.in_transaction:raise ValueError('Hay una transacción pendiente; no se modificó.')
    saldo=Decimal(str(saldo))
    if not str(nombre).strip() or not saldo.is_finite() or saldo!=saldo.to_integral_value():
        raise ValueError('Indica nombre y saldo CLP entero válido.')
    if tipo not in ('Cuenta corriente','Cuenta vista','Cuenta empresa','Otra'):raise ValueError('Tipo de cuenta inválido.')
    with conn:
        conn.execute('BEGIN IMMEDIATE')
        sgci_autorizar_operacion(conn,'banco','crear','Bancos y cartolas')
        if codigo not in Plan(conn).hojas:raise ValueError('Selecciona una cuenta imputable.')
        cur=conn.execute('INSERT INTO bancos(nombre,numero_cuenta,tipo,cuenta_contable,saldo_inicial) VALUES(?,?,?,?,?)',
            (str(nombre).strip(),str(numero).strip(),tipo,codigo,int(saldo)))
        bid=cur.lastrowid
        conn.execute('INSERT INTO auditoria(fecha_hora,usuario,accion,detalle) VALUES(?,?,?,?)',
            (datetime.now().isoformat(timespec='seconds'),sgci_identidad_actual(),'NUEVO BANCO',str(bid)))
    return bid


def contem_vincular_banco(conn,banco_id,codigo):
    from datetime import datetime
    sgci_autorizar_operacion(conn,'banco','editar','Bancos y cartolas')
    if conn.in_transaction:raise ValueError('Hay una transacción pendiente; no se modificó.')
    with conn:
        conn.execute('BEGIN IMMEDIATE')
        sgci_autorizar_operacion(conn,'banco','editar','Bancos y cartolas')
        if codigo not in Plan(conn).hojas:raise ValueError('Selecciona una cuenta imputable.')
        cur=conn.execute('UPDATE bancos SET cuenta_contable=? WHERE id=? AND activo=1',(codigo,banco_id))
        if cur.rowcount!=1:raise ValueError('Banco no disponible.')
        conn.execute('INSERT INTO auditoria(fecha_hora,usuario,accion,detalle) VALUES(?,?,?,?)',
            (datetime.now().isoformat(timespec='seconds'),sgci_identidad_actual(),'VINCULACION BANCO',f'{banco_id}: {codigo}'))
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


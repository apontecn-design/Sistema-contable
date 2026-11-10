# CONTEM: componente extraído del app.py original; ejecución secuencial compartida.
def asegurar_control_regularizacion_iva_compras(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS regularizacion_iva_compras (
            compra_id INTEGER PRIMARY KEY,
            asiento_regularizacion INTEGER NOT NULL,
            fecha_regularizacion TEXT NOT NULL,
            monto_iva REAL NOT NULL
        )
    """)
    conn.commit()


def compras_pendientes_regularizar_iva(conn):
    """
    Audita TODAS las compras históricas contabilizadas.

    Prioridad para determinar IVA:
    1) IVA guardado en compras.iva.
    2) Diferencia total - base guardada, cuando existe.
    3) Para documentos afectos antiguos cuya base quedó guardada por el bruto,
       reconstrucción 19/119 del total, marcada expresamente como RECONSTRUIDO.

    La detección NO depende de lote_id/glosa del asiento antiguo.
    """
    asegurar_control_regularizacion_iva_compras(conn)
    codigo_iva = ROLES["iva_credito"][1]
    # Compatibilidad con bases nuevas o históricas que aún no tienen esta
    # columna opcional del proceso de recuperación tributaria del RCV.
    columnas_compras = {fila[1] for fila in conn.execute('PRAGMA table_info(compras)').fetchall()}
    expr_recuperados = ('COALESCE(c.datos_tributarios_recuperados,0)'
                         if 'datos_tributarios_recuperados' in columnas_compras else '0')

    df = pd.read_sql_query(f"""
        SELECT
            c.id, c.fecha, c.tipo_doc, c.folio, c.glosa, c.lote_id,
            c.cuenta_gasto, COALESCE(c.monto_neto,0) AS monto_neto,
            COALESCE(c.iva,0) AS iva_registrado,
            COALESCE(c.monto_total,0) AS monto_total,
            {expr_recuperados} AS datos_tributarios_recuperados,
            p.rut,
            COALESCE(NULLIF(p.razon_social,''),p.nombre) AS proveedor
        FROM compras c
        LEFT JOIN proveedores p ON p.id=c.proveedor_id
        WHERE NOT EXISTS (
            SELECT 1 FROM regularizacion_iva_compras r
            WHERE r.compra_id=c.id
        )
        ORDER BY c.fecha,c.id
    """, conn)

    if df.empty:
        return df

    # Si el Mayor de IVA ya contiene una regularización identificable por compra,
    # no la volvemos a proponer aunque falte la tabla de control.
    ya_reg = set()
    filas = conn.execute("""
        SELECT glosa FROM libro_diario
        WHERE codigo_cuenta=?
          AND glosa LIKE 'Regularización IVA Crédito Fiscal RCV compra N° %'
    """, (codigo_iva,)).fetchall()
    for f in filas:
        ya_reg.add(str(f[0] or ""))

    afectos_reconstruibles = {33, 34, 46, 56, 61}
    candidatos = []
    for r in df.to_dict("records"):
        tipo = int(r.get("tipo_doc") or 0)
        total = abs(float(r.get("monto_total") or 0))
        base = abs(float(r.get("monto_neto") or 0))
        iva_guardado = abs(float(r.get("iva_registrado") or 0))

        glosa_control = f"Regularización IVA Crédito Fiscal RCV compra N° {r.get('folio')} - {r.get('proveedor')}"
        if any(g.startswith(glosa_control) for g in ya_reg):
            continue

        iva_calc = 0.0
        fuente = ""
        if int(r.get("datos_tributarios_recuperados") or 0) == 1:
            iva_calc = iva_guardado
            fuente = "RCV original SII"
            # Si el RCV original dice IVA recuperable cero, no inventamos 19/119.
            if iva_calc <= 0.01:
                continue
        elif iva_guardado > 0.01:
            iva_calc = iva_guardado
            fuente = "RCV registrado"
        elif total > 0.01 and base > 0.01 and (total - base) > 0.01:
            iva_calc = round(total - base, 0)
            fuente = "Total - base histórica"
        elif tipo in afectos_reconstruibles and total > 0.01:
            # Último recurso para históricos importados cuando el antiguo parser
            # guardó el bruto como base y perdió la columna IVA.
            iva_calc = round(total * 19 / 119, 0)
            fuente = "Reconstruido 19/119"

        if iva_calc <= 0.01:
            continue

        codigo_actual = codigo_cuenta_por_nombre(conn, r.get("cuenta_gasto"))
        if not codigo_actual:
            # Busca la última cuenta que recibió el débito en una reclasificación
            folio = str(r.get("folio") or "")
            fila = conn.execute("""
                SELECT codigo_cuenta
                FROM libro_diario
                WHERE glosa LIKE ?
                  AND debe > 0.01
                  AND codigo_cuenta NOT IN (?,?)
                ORDER BY asiento_id DESC,id DESC LIMIT 1
            """, (f"%N° {folio}%", ROLES["proveedores"][1], codigo_iva)).fetchone()
            codigo_actual = str(fila[0]) if fila else ""

        r["iva"] = iva_calc
        r["fuente_iva"] = fuente
        r["codigo_cuenta_actual"] = codigo_actual or ""
        candidatos.append(r)

    return pd.DataFrame(candidatos)

def regularizar_iva_historico_compras(conn):
    """
    Crea asientos de reclasificación auditables para compras históricas que
    quedaron sin IVA Crédito Fiscal.

    Factura/ND:
        Debe  IVA Crédito Fiscal
        Haber cuenta de gasto/activo original
    Nota de crédito:
        Debe  cuenta de gasto/activo original
        Haber IVA Crédito Fiscal

    No toca Proveedores, Banco ni el asiento RCV original.
    Es idempotente mediante regularizacion_iva_compras.
    """
    pendientes = compras_pendientes_regularizar_iva(conn)
    if pendientes.empty:
        return {"documentos": 0, "iva": 0.0, "lote": None}

    plan = Plan(conn)
    codigo_iva = ROLES["iva_credito"][1]
    if codigo_iva not in plan.todos:
        raise ValueError(f"No existe la cuenta {codigo_iva} - IVA Crédito Fiscal.")

    asiento = siguiente_asiento(conn)
    lote = "REG-IVA-RCV-C-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    total_iva = 0.0
    documentos = 0

    try:
        for r in pendientes.itertuples():
            monto = abs(float(r.iva or 0))
            if monto <= 0.01:
                continue

            codigo_contra = str(getattr(r, "codigo_cuenta_actual", "") or "")

            if not codigo_contra or codigo_contra not in plan.todos:
                raise ValueError(
                    f"No pude identificar la cuenta de gasto/activo actual de la compra "
                    f"{r.folio} ({r.proveedor})."
                )

            asiento += 1
            es_nc = int(r.tipo_doc or 0) in DOC_NOTA_CREDITO
            glosa_reg = f"Regularización IVA Crédito Fiscal RCV compra N° {r.folio} - {r.proveedor}"

            if es_nc:
                lineas = [
                    (codigo_contra, monto, 0.0),
                    (codigo_iva, 0.0, monto),
                ]
            else:
                lineas = [
                    (codigo_iva, monto, 0.0),
                    (codigo_contra, 0.0, monto),
                ]

            for codigo,debe,haber in lineas:
                conn.execute("""
                    INSERT INTO libro_diario
                    (fecha,cuenta,debe,haber,glosa,centro_costo,codigo_cuenta,
                     asiento_id,lote_id,origen)
                    VALUES (?,?,?,?,?,?,?,?,?,?)
                """, (
                    r.fecha, plan.todos[codigo], debe, haber, glosa_reg,
                    "General / Ninguno", codigo, asiento, lote,
                    "Regularización IVA RCV Compras"
                ))

            conn.execute("""
                INSERT INTO regularizacion_iva_compras
                (compra_id,asiento_regularizacion,fecha_regularizacion,monto_iva)
                VALUES (?,?,?,?)
            """, (
                int(r.id), asiento,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"), monto
            ))

            total_iva += (-monto if es_nc else monto)
            documentos += 1

        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return {"documentos": documentos, "iva": total_iva, "lote": lote}


# ============================================================
# PAGOS
# ============================================================

def registrar_pago_cliente(
    conn,
    cliente_id,
    fecha,
    monto,
    medio_pago,
    cuenta_banco,
    glosa
):
    sgci_autorizar_operacion(conn, 'cxc', 'crear')

    roles = cargar_roles(conn)
    plan = Plan(conn)

    if roles["clientes"] is None:
        raise ValueError("Cuenta de clientes no configurada.")

    if not cuenta_banco:
        raise ValueError("Debe seleccionar una cuenta bancaria.")

    if cuenta_banco not in plan.hojas:
        raise ValueError("La cuenta bancaria no es imputable.")

    lote = "PAGO-CLIENTE-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO pagos_clientes
        (
            fecha,
            cliente_id,
            monto,
            medio_pago,
            cuenta_banco,
            glosa,
            lote_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            fecha,
            cliente_id,
            monto,
            medio_pago,
            cuenta_banco,
            glosa,
            lote
        )
    )

    asiento = siguiente_asiento(conn) + 1
    nombre_banco = plan.hojas[cuenta_banco]

    nombre_cliente = conn.execute(
        """
        SELECT COALESCE(
            NULLIF(razon_social, ''),
            nombre
        )
        FROM clientes
        WHERE id = ?
        """,
        (cliente_id,)
    ).fetchone()[0]

    glosa_final = glosa or f"Pago cliente - {nombre_cliente}"

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
            nombre_banco,
            monto,
            0,
            glosa_final,
            "General / Ninguno",
            cuenta_banco,
            asiento,
            lote,
            "Pago de cliente"
        )
    )

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
            roles["clientes"][1],
            0,
            monto,
            glosa_final,
            "General / Ninguno",
            roles["clientes"][0],
            asiento,
            lote,
            "Pago de cliente"
        )
    )

    conn.commit()
    return lote


def registrar_pago_proveedor(
    conn,
    proveedor_id,
    fecha,
    monto,
    medio_pago,
    cuenta_banco,
    glosa
):
    sgci_autorizar_operacion(conn, 'cxp', 'crear')

    roles = cargar_roles(conn)
    plan = Plan(conn)

    if roles["proveedores"] is None:
        raise ValueError("Cuenta de proveedores no configurada.")

    if cuenta_banco not in plan.hojas:
        raise ValueError("La cuenta bancaria no es imputable.")

    lote = "PAGO-PROVEEDOR-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO pagos_proveedores
        (
            fecha,
            proveedor_id,
            monto,
            medio_pago,
            cuenta_banco,
            glosa,
            lote_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            fecha,
            proveedor_id,
            monto,
            medio_pago,
            cuenta_banco,
            glosa,
            lote
        )
    )

    asiento = siguiente_asiento(conn) + 1
    nombre_banco = plan.hojas[cuenta_banco]

    nombre_proveedor = conn.execute(
        """
        SELECT COALESCE(
            NULLIF(razon_social, ''),
            nombre
        )
        FROM proveedores
        WHERE id = ?
        """,
        (proveedor_id,)
    ).fetchone()[0]

    glosa_final = glosa or f"Pago proveedor - {nombre_proveedor}"

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
            roles["proveedores"][1],
            monto,
            0,
            glosa_final,
            "General / Ninguno",
            roles["proveedores"][0],
            asiento,
            lote,
            "Pago a proveedor"
        )
    )

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
            nombre_banco,
            0,
            monto,
            glosa_final,
            "General / Ninguno",
            cuenta_banco,
            asiento,
            lote,
            "Pago a proveedor"
        )
    )

    conn.commit()
    return lote


# ============================================================
# ESTADOS DE CUENTA
# ============================================================


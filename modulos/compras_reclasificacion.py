# CONTEM: componente extraído del app.py original; ejecución secuencial compartida.
def compras_para_reclasificar(conn):
    """Devuelve compras contabilizadas con la cuenta actualmente registrada."""
    return pd.read_sql_query(
        """
        SELECT
            c.id AS compra_id,
            c.fecha,
            p.rut,
            COALESCE(p.razon_social, p.nombre, '') AS proveedor,
            c.tipo_doc,
            c.folio,
            c.monto_neto,
            c.monto_total,
            c.cuenta_gasto,
            c.lote_id
        FROM compras c
        LEFT JOIN proveedores p ON p.id = c.proveedor_id
        ORDER BY c.fecha DESC, c.id DESC
        """,
        conn
    )


def codigo_cuenta_por_nombre(conn, nombre):
    fila = conn.execute(
        "SELECT codigo FROM plan_cuentas WHERE nombre = ? ORDER BY nivel DESC LIMIT 1",
        (limpiar_texto(nombre),)
    ).fetchone()
    return limpiar_texto(fila["codigo"]) if fila else None


def reclasificar_compras(conn, compra_ids, nueva_cuenta, recordar_proveedor=False):
    """Genera un asiento de reclasificación sin modificar IVA ni Proveedores."""
    ids = [int(x) for x in compra_ids]
    if not ids:
        raise ValueError("Selecciona al menos una compra.")

    plan = Plan(conn)
    if nueva_cuenta not in plan.hojas:
        raise ValueError("La nueva cuenta no existe o no es imputable.")

    placeholders = ",".join("?" for _ in ids)
    compras = conn.execute(
        f"""
        SELECT c.*, p.rut, COALESCE(p.razon_social,p.nombre,'') AS proveedor
        FROM compras c
        LEFT JOIN proveedores p ON p.id=c.proveedor_id
        WHERE c.id IN ({placeholders})
        ORDER BY c.fecha, c.id
        """,
        ids
    ).fetchall()

    if len(compras) != len(ids):
        raise ValueError("No fue posible localizar todas las compras seleccionadas.")

    asiento = siguiente_asiento(conn)
    lote = "RECLAS-COMPRAS-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    reclasificadas = 0
    omitidas = 0

    try:
        for c in compras:
            if periodo_cerrado(conn, c["fecha"]):
                raise ValueError(f"El período {str(c['fecha'])[:7]} está cerrado. Reabre el período antes de reclasificar.")

            cuenta_anterior = codigo_cuenta_por_nombre(conn, c["cuenta_gasto"])
            if not cuenta_anterior:
                raise ValueError(f"No pude identificar el código de la cuenta actual de la compra folio {c['folio']}.")
            if cuenta_anterior == nueva_cuenta:
                omitidas += 1
                continue

            # Para compras con IVA, reclasificamos la BASE y nunca el bruto.
            # compras.monto_neto queda alimentado por el RCV y evita trasladar el IVA
            # Crédito Fiscal a una cuenta de gasto.
            monto_guardado = round(float(c["monto_neto"] or 0), 2)

            # Respaldo para documentos exentos/legados sin base utilizable:
            # consultamos el asiento real.
            fila_base = conn.execute(
                """
                SELECT
                    COALESCE(SUM(debe), 0) AS debe,
                    COALESCE(SUM(haber), 0) AS haber
                FROM libro_diario
                WHERE lote_id = ?
                  AND fecha = ?
                  AND glosa = ?
                  AND codigo_cuenta = ?
                  AND COALESCE(origen, '') NOT LIKE 'Reclasificación%'
                """,
                (c["lote_id"], c["fecha"], c["glosa"], cuenta_anterior)
            ).fetchone()

            debe_base = round(float(fila_base["debe"] or 0), 2) if fila_base else 0.0
            haber_base = round(float(fila_base["haber"] or 0), 2) if fila_base else 0.0
            monto_diario = round(debe_base - haber_base, 2)

            # Si el RCV guardó una base neta, esa es la cantidad reclasificable.
            # Conservamos el signo de NC según el asiento original.
            if abs(monto_guardado) > 0.001:
                monto = monto_guardado
            else:
                monto = monto_diario

            if abs(monto) <= 0.001:
                raise ValueError(
                    f"La compra folio {c['folio']} no tiene base reclasificable "
                    "en el asiento original del Libro Diario."
                )

            asiento += 1
            glosa = (
                f"Reclasificación compra {nombre_documento(c['tipo_doc'])} N° {c['folio']} - "
                f"{c['proveedor']} | {cuenta_anterior} → {nueva_cuenta}"
            )

            # Facturas: Debe nueva / Haber anterior. NC: efecto inverso.
            if monto > 0:
                lineas = [(nueva_cuenta, abs(monto), 0.0), (cuenta_anterior, 0.0, abs(monto))]
            else:
                lineas = [(cuenta_anterior, abs(monto), 0.0), (nueva_cuenta, 0.0, abs(monto))]

            for codigo, debe, haber in lineas:
                conn.execute(
                    """
                    INSERT INTO libro_diario
                    (fecha, cuenta, debe, haber, glosa, centro_costo, codigo_cuenta, asiento_id, lote_id, origen)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (c["fecha"], plan.todos[codigo], debe, haber, glosa,
                     c["centro_costo"] or "General / Ninguno", codigo, asiento, lote, "Reclasificación RCV Compras")
                )

            conn.execute(
                "UPDATE compras SET cuenta_gasto=? WHERE id=?",
                (plan.todos[nueva_cuenta], c["id"])
            )

            if recordar_proveedor and c["proveedor_id"]:
                conn.execute(
                    "UPDATE proveedores SET cuenta_defecto=? WHERE id=?",
                    (nueva_cuenta, c["proveedor_id"])
                )

            reclasificadas += 1

        conn.execute(
            "INSERT INTO auditoria(fecha_hora, usuario, accion, detalle) VALUES (?,?,?,?)",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "admin", "RECLASIFICACIÓN RCV COMPRAS",
             f"Lote {lote}: {reclasificadas} compra(s) a {nueva_cuenta}; omitidas {omitidas}")
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return {"reclasificadas": reclasificadas, "omitidas": omitidas, "lote": lote}

# ============================================================
# CONTROL CONTABLE Y REPORTES
# ============================================================


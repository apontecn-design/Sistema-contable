# CONTEM: componente extraído del app.py original; ejecución secuencial compartida.
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


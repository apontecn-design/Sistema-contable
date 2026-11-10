# CONTEM: componente extraído del app.py original; ejecución secuencial compartida.
def guardar_regla(
    conn,
    tipo,
    rut,
    patron,
    tipo_doc,
    codigo,
    prioridad,
    descripcion
):

    conn.execute(
        """
        INSERT INTO reglas_contables
        (
            tipo,
            rut,
            patron,
            tipo_doc,
            codigo_cuenta,
            prioridad,
            activa,
            descripcion
        )
        VALUES (?, ?, ?, ?, ?, ?, 1, ?)
        """,
        (
            tipo,
            normalizar_rut(rut),
            patron,
            tipo_doc,
            codigo,
            prioridad,
            descripcion
        )
    )
    conn.commit()




# ============================================================
# RECLASIFICACIÓN CONTABLE DE COMPRAS YA CONTABILIZADAS
# ============================================================


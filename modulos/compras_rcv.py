# CONTEM: componente extraído del app.py original; ejecución secuencial compartida.
def cruzar_rcv_historico_compras(conn, df_rcv, devolver_no_encontrados=False):
    """
    Cruza un RCV original del SII contra compras existentes por
    RUT proveedor + tipo documento + folio. No crea documentos ni asientos.
    Si devolver_no_encontrados=True, devuelve también los documentos del RCV
    que no existen en SGCI.
    """
    if df_rcv is None or df_rcv.empty:
        vacio=pd.DataFrame()
        return (vacio,vacio) if devolver_no_encontrados else vacio

    existentes = pd.read_sql_query("""
        SELECT c.id AS compra_id, c.tipo_doc, CAST(c.folio AS TEXT) AS folio,
               c.monto_neto AS neto_actual, c.iva AS iva_actual,
               c.monto_total AS total_actual,
               p.rut, COALESCE(NULLIF(p.razon_social,''),p.nombre) AS proveedor
        FROM compras c
        JOIN proveedores p ON p.id=c.proveedor_id
    """, conn)

    def llave(rut,tipo,folio):
        return (
            normalizar_rut(rut),
            int(float(tipo or 0)),
            str(folio or "").strip().replace(".0","")
        )

    mapa={}
    for r in existentes.to_dict("records"):
        mapa[llave(r["rut"],r["tipo_doc"],r["folio"])]=r

    filas=[]
    faltantes=[]
    for r in df_rcv.to_dict("records"):
        k=llave(r.get("rut"),r.get("tipo_doc"),r.get("folio"))
        e=mapa.get(k)
        if not e:
            faltantes.append({
                "rut":k[0],
                "tipo_doc":k[1],
                "folio":k[2],
                "proveedor":r.get("proveedor") or r.get("razon_social") or "",
                "neto_rcv":float(r.get("neto") or 0),
                "exento_rcv":float(r.get("exento") or 0),
                "iva_rcv":float(r.get("iva") or 0),
                "iva_no_rec_rcv":float(r.get("iva_no_rec") or 0),
                "total_rcv":float(r.get("total") or 0),
            })
            continue
        filas.append({
            "compra_id":int(e["compra_id"]),
            "rut":k[0],
            "tipo_doc":k[1],
            "folio":k[2],
            "proveedor":e["proveedor"],
            "neto_rcv":float(r.get("neto") or 0),
            "exento_rcv":float(r.get("exento") or 0),
            "iva_rcv":float(r.get("iva") or 0),
            "iva_no_rec_rcv":float(r.get("iva_no_rec") or 0),
            "neto_af_rcv":float(r.get("neto_af") or 0),
            "iva_af_rcv":float(r.get("iva_af") or 0),
            "iva_uso_comun_rcv":float(r.get("iva_uso_comun") or 0),
            "total_rcv":float(r.get("total") or 0),
            "iva_actual":float(e["iva_actual"] or 0),
            "total_actual":float(e["total_actual"] or 0),
        })

    encontrados=pd.DataFrame(filas)
    no_encontrados=pd.DataFrame(faltantes)
    return (encontrados,no_encontrados) if devolver_no_encontrados else encontrados


def recuperar_datos_tributarios_rcv(conn, cruces):
    """
    Guarda en compras los datos tributarios EXACTOS del RCV original y los
    verifica con una conexión nueva al archivo SQLite después del COMMIT.
    No crea compras/asientos ni modifica proveedores, pagos o banco.
    """
    if cruces is None or cruces.empty:
        return {"actualizados":0,"verificados":0,"iva":0.0,"errores":[]}

    # Asegurar columnas de auditoría.
    agregar_columna(conn,"compras","monto_exento","REAL DEFAULT 0")
    agregar_columna(conn,"compras","iva_no_rec","REAL DEFAULT 0")
    agregar_columna(conn,"compras","neto_af","REAL DEFAULT 0")
    agregar_columna(conn,"compras","iva_af","REAL DEFAULT 0")
    agregar_columna(conn,"compras","iva_uso_comun","REAL DEFAULT 0")
    agregar_columna(conn,"compras","datos_tributarios_recuperados","INTEGER DEFAULT 0")
    conn.commit()

    preparados=[]
    for r in cruces.itertuples():
        compra_id=int(r.compra_id)
        # Se guardan exactamente los importes que vienen del RCV.
        neto=clp_round(r.neto_rcv)
        exento=clp_round(r.exento_rcv)
        iva=clp_round(r.iva_rcv)
        iva_no_rec=clp_round(r.iva_no_rec_rcv)
        neto_af=clp_round(r.neto_af_rcv)
        iva_af=clp_round(r.iva_af_rcv)
        iva_uso=clp_round(r.iva_uso_comun_rcv)
        total=clp_round(r.total_rcv)
        preparados.append((compra_id,neto,exento,iva,iva_no_rec,neto_af,iva_af,iva_uso,total))

    try:
        for compra_id,neto,exento,iva,iva_no_rec,neto_af,iva_af,iva_uso,total in preparados:
            cur=conn.execute("""
                UPDATE compras
                   SET monto_neto=?, iva=?, monto_total=?,
                       monto_exento=?, iva_no_rec=?, neto_af=?, iva_af=?,
                       iva_uso_comun=?, datos_tributarios_recuperados=1
                 WHERE id=?
            """,(neto,iva,total,exento,iva_no_rec,neto_af,iva_af,iva_uso,compra_id))
            if cur.rowcount != 1:
                raise ValueError(f"No se encontró la compra id {compra_id}.")
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    # Verificación independiente: cerramos cualquier duda sobre caché/estado de
    # la conexión usada por Streamlit y leemos de nuevo el archivo persistente.
    conn_check=sqlite3.connect(DB_FILE)
    try:
        verificados=0
        iva_verificado=0
        errores=[]
        for compra_id,neto,exento,iva,iva_no_rec,neto_af,iva_af,iva_uso,total in preparados:
            fila=conn_check.execute("""
                SELECT monto_neto,iva,monto_total,datos_tributarios_recuperados
                  FROM compras WHERE id=?
            """,(compra_id,)).fetchone()
            if fila is None:
                errores.append(f"Compra id {compra_id}: no existe después del COMMIT.")
                continue

            real_neto=clp_round(fila[0])
            real_iva=clp_round(fila[1])
            real_total=clp_round(fila[2])
            real_flag=int(fila[3] or 0)

            if (real_neto,real_iva,real_total,real_flag)==(neto,iva,total,1):
                verificados+=1
                iva_verificado+=abs(real_iva)
            else:
                errores.append(
                    f"Compra id {compra_id}: esperado neto {neto}, IVA {iva}, total {total}; "
                    f"guardado neto {real_neto}, IVA {real_iva}, total {real_total}, marca {real_flag}."
                )
    finally:
        conn_check.close()

    return {
        "actualizados":len(preparados),
        "verificados":verificados,
        "iva":iva_verificado,
        "errores":errores
    }


# ============================================================
# REGULARIZACIÓN HISTÓRICA IVA CRÉDITO - RCV COMPRAS
# ============================================================


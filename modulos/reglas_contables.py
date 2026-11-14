# CONTEM: componente extraído del app.py original; ejecución secuencial compartida.
def buscar_regla(conn, tipo, rut, tipo_doc, razon_social=""):

    rut = normalizar_rut(rut)

    reglas = pd.read_sql_query(
        """
        SELECT *
        FROM reglas_contables
        WHERE tipo = ?
        AND activa = 1
        ORDER BY prioridad DESC, id DESC
        """,
        conn,
        params=(tipo,)
    )

    if reglas.empty:
        return None

    razon = limpiar_texto(
        razon_social
    ).lower()

    for _, regla in reglas.iterrows():

        regla_rut = normalizar_rut(
            regla["rut"]
        )

        regla_tipo_doc = regla["tipo_doc"]

        patron = limpiar_texto(
            regla["patron"]
        ).lower()

        if regla_rut and regla_rut != rut:
            continue

        if pd.notna(regla_tipo_doc):
            try:
                if int(regla_tipo_doc) != int(tipo_doc):
                    continue
            except Exception:
                continue

        if patron:
            if patron not in razon:
                continue

        return regla

    return None


def cuenta_habitual(conn, tipo, rut):

    tabla = (
        "proveedores"
        if tipo == "compras"
        else "clientes"
    )

    fila = conn.execute(
        f"""
        SELECT cuenta_defecto
        FROM {tabla}
        WHERE UPPER(TRIM(rut)) = ?
        """,
        (normalizar_rut(rut),)
    ).fetchone()

    if fila and fila["cuenta_defecto"]:
        return fila["cuenta_defecto"]

    return None


def preparar_documentos(conn, docs, tipo):

    compras = tipo == "compras"

    plan = Plan(conn)
    roles = cargar_roles(conn)

    if compras:
        rol_defecto = "gasto_defecto"
    else:
        rol_defecto = "ingreso_defecto"

    defecto = roles[rol_defecto]

    if defecto is None:
        raise ValueError(
            "La cuenta por defecto no está configurada."
        )

    existentes = set()

    if compras:

        filas = conn.execute(
            """
            SELECT
                p.rut,
                c.tipo_doc,
                c.folio
            FROM compras c
            JOIN proveedores p
                ON p.id = c.proveedor_id
            WHERE c.tipo_doc IS NOT NULL AND c.folio IS NOT NULL AND p.rut IS NOT NULL
            """
        ).fetchall()

        for fila in filas:
            try:
                existentes.add(
                    (
                        normalizar_rut(fila["rut"]),
                        int(fila["tipo_doc"]),
                        str(fila["folio"]).strip()
                    )
                )
            except Exception:
                pass

    else:

        filas = conn.execute(
            """
            SELECT cl.rut, v.tipo_doc, v.folio
            FROM ventas v JOIN clientes cl ON cl.id=v.cliente_id
            WHERE v.tipo_doc IS NOT NULL AND v.folio IS NOT NULL AND cl.rut IS NOT NULL
            """
        ).fetchall()

        for fila in filas:
            try:
                existentes.add(
                    (
                        normalizar_rut(fila["rut"]),
                        int(fila["tipo_doc"]),
                        str(fila["folio"]).strip()
                    )
                )
            except Exception:
                pass

    resultado = docs.copy()

    estados = []
    cuentas = []
    origenes = []
    signos = []
    observaciones = []

    vistos = set()

    for d in docs.itertuples():

        rut = normalizar_rut(d.rut)
        tipo_doc = int(d.tipo_doc)
        folio = str(d.folio).strip()

        # Clave lógica anti-duplicado: RUT + tipo de documento + folio.
        clave = (rut, tipo_doc, folio)

        obs = []

        if not validar_rut(rut):
            estado = "⚠️ RUT inválido"
            obs.append("Revisar RUT.")

        elif not d.fecha_doc:
            estado = "❌ Fecha inválida"

        elif tipo_doc not in DOC_SOPORTADOS:
            estado = "⚠️ Tipo no soportado"

        elif d.total == 0:
            estado = "⚠️ Monto cero"

        elif clave in existentes:
            estado = "🔁 Ya contabilizado"

        elif clave in vistos:
            estado = "🔁 Repetido en archivo"

        else:
            estado = "🟢 Nuevo"

        vistos.add(clave)

        # Criterio estricto de signo: Notas de crédito restan (-1), notas de débito y facturas suman (1)
        signo = (
            -1
            if tipo_doc in DOC_NOTA_CREDITO
            else 1
        )

        if compras:
            componentes = (
                d.exento
                + d.neto
                + d.iva
                + d.iva_no_rec
                + d.neto_af
                + d.iva_af
                + d.iva_uso_comun
            )
        else:
            componentes = (
                d.exento
                + d.neto
                + d.iva
            )

        diferencia = (
            d.total - componentes
        )

        if abs(diferencia) > 1:
            obs.append(
                f"Diferencia entre total y componentes: "
                f"{money(diferencia)}."
            )

        if d.exento > 0 and d.neto > 0:
            obs.append("Documento mixto: exento y afecto.")

        cuenta = None
        origen = None

        # Si es venta exenta (Código 34, 41 o 32), asignar por defecto la cuenta de ventas exentas
        if not compras and tipo_doc in {34, 41, 32}:
            exento_rol = roles.get("ingreso_exento")
            if exento_rol:
                cuenta = exento_rol[0]
                origen = f"Cuenta ventas exentas (Tipo {tipo_doc})"

        if not cuenta:
            regla = buscar_regla(
                conn,
                tipo,
                rut,
                tipo_doc,
                d.razon_social
            )

            if regla:
                cuenta = limpiar_texto(
                    regla["codigo_cuenta"]
                )
                origen = f"Regla #{int(regla['id'])}"

        if not cuenta and compras:
            habitual = cuenta_habitual(
                conn,
                tipo,
                rut
            )
            if habitual:
                cuenta = habitual
                origen = "Cuenta habitual"

        if not cuenta:
            cuenta = defecto[0]
            origen = "Cuenta por defecto"
            if estado == "🟢 Nuevo":
                estado = "🟡 Revisar cuenta"

        if cuenta not in plan.hojas:
            obs.append(
                "La cuenta sugerida no es imputable "
                "o no existe en el plan."
            )
            if estado.startswith("🟢"):
                estado = "🟡 Revisar cuenta"

        estados.append(estado)
        cuentas.append(cuenta)
        origenes.append(origen)
        signos.append(signo)
        observaciones.append(" ".join(obs))

    resultado["estado"] = estados
    resultado["cuenta_sugerida"] = cuentas
    resultado["cuenta_codigo"] = cuentas
    resultado["cuenta_origen"] = origenes
    resultado["signo"] = signos
    resultado["observaciones"] = observaciones

    return resultado


# ============================================================
# ASIENTOS (Con Blindaje Total y Cálculo Automático por Diferencia)
# ============================================================

def armar_asiento(doc, tipo, cuenta, roles):
    """
    Construye las líneas contables de un documento del RCV.

    REGLA FUNDAMENTAL:
    El tratamiento contable depende del TIPO DE DOCUMENTO,
    no del signo con que el SII entregue los montos.

    - Factura / Nota de Débito: efecto contable normal.
    - Nota de Crédito: revierte Debe y Haber.
    """

    # --------------------------------------------------------
    # FUNCIÓN AUXILIAR PARA OBTENER EL CÓDIGO DE UN ROL
    # --------------------------------------------------------
    #
    # cargar_roles() devuelve:
    #     (codigo, nombre)
    #
    # Esta función garantiza que al asiento siempre llegue
    # solamente el código contable.
    #

    def codigo_rol(nombre_rol, defecto=None):
        valor = roles.get(nombre_rol)

        if valor:
            if isinstance(valor, (tuple, list)):
                return valor[0]
            return valor

        if defecto is not None:
            if isinstance(defecto, (tuple, list)):
                return defecto[0]
            return defecto

        raise ValueError(
            f"No existe una cuenta configurada para el rol "
            f"'{nombre_rol}'."
        )

    # --------------------------------------------------------
    # 1. DATOS DEL DOCUMENTO
    # --------------------------------------------------------

    tipo_doc = int(getattr(doc, "tipo_doc", 0) or 0)

    # El tipo de documento determina el tratamiento.
    # Las NC revierten el asiento.
    es_nc = tipo_doc in DOC_NOTA_CREDITO

    # Usamos valores absolutos porque el signo del archivo SII
    # no determina por sí mismo el tratamiento contable.
    total = abs(float(getattr(doc, "total", 0) or 0))
    neto = abs(float(getattr(doc, "neto", 0) or 0))
    exento = abs(float(getattr(doc, "exento", 0) or 0))

    iva = abs(float(getattr(doc, "iva", 0) or 0))
    iva_no_rec = abs(float(getattr(doc, "iva_no_rec", 0) or 0))

    # Nombres reales utilizados por normalizar_rcv().
    neto_af = abs(float(getattr(doc, "neto_af", 0) or 0))
    iva_af = abs(float(getattr(doc, "iva_af", 0) or 0))
    iva_uso_comun = abs(
        float(getattr(doc, "iva_uso_comun", 0) or 0)
    )

    lineas_normales = []

    # --------------------------------------------------------
    # 2. COMPRAS
    # --------------------------------------------------------

    if tipo == "compras":

        cuenta_principal = cuenta

        # ----------------------------------------------------
        # BASE PRINCIPAL DE LA COMPRA
        # ----------------------------------------------------

        principal = neto + exento

        # Si el RCV no entrega base neta/exenta utilizable,
        # reconstruimos la base por diferencia.
        if principal <= 0.001 and neto_af <= 0.001:

            impuestos_separados = (
                iva
                + iva_no_rec
                + iva_uso_comun
                + iva_af
            )

            principal = max(
                total - impuestos_separados,
                0.0
            )

        # ----------------------------------------------------
        # DEBE: GASTO / COMPRA PRINCIPAL
        # ----------------------------------------------------

        if principal > 0.001:
            lineas_normales.append(
                (cuenta_principal, principal, 0.0)
            )

        # ----------------------------------------------------
        # ACTIVO FIJO
        # ----------------------------------------------------

        if neto_af > 0.001:
            codigo_activo_fijo = codigo_rol(
                "activo_fijo",
                cuenta_principal
            )

            lineas_normales.append(
                (codigo_activo_fijo, neto_af, 0.0)
            )

        # ----------------------------------------------------
        # IVA CRÉDITO FISCAL
        # ----------------------------------------------------
        #
        # Si el IVA de activo fijo está informado aparte,
        # evitamos duplicarlo dentro del IVA general.
        #

        iva_credito = max(iva - iva_af, 0.0)

        if iva_credito > 0.001:
            lineas_normales.append(
                (
                    codigo_rol("iva_credito"),
                    iva_credito,
                    0.0
                )
            )

        # ----------------------------------------------------
        # IVA DE ACTIVO FIJO
        # ----------------------------------------------------

        if iva_af > 0.001:
            lineas_normales.append(
                (
                    codigo_rol("iva_credito"),
                    iva_af,
                    0.0
                )
            )

        # ----------------------------------------------------
        # IVA NO RECUPERABLE
        # ----------------------------------------------------

        if iva_no_rec > 0.001:
            lineas_normales.append(
                (
                    codigo_rol(
                        "iva_no_recuperable",
                        cuenta_principal
                    ),
                    iva_no_rec,
                    0.0
                )
            )

        # ----------------------------------------------------
        # IVA DE USO COMÚN
        # ----------------------------------------------------

        if iva_uso_comun > 0.001:
            cuenta_iva_uc = codigo_rol("iva_uso_comun", None)
            if not cuenta_iva_uc or cuenta_iva_uc == "5.2.03" or str(cuenta_iva_uc).startswith("5.2.03."):
                raise ValueError(
                    "Configuración inválida de IVA de uso común: revise la cuenta contable asignada."
                )
            lineas_normales.append((cuenta_iva_uc, iva_uso_comun, 0.0))

        # ----------------------------------------------------
        # CUADRATURA AUTOMÁTICA
        # ----------------------------------------------------
        #
        # El Haber a Proveedores debe ser exactamente igual
        # al total del documento.
        #

        debe_actual = sum(
            x[1] for x in lineas_normales
        )

        diferencia = round(
            total - debe_actual,
            2
        )

        if abs(diferencia) > 0.01:

            encontrada = False

            # Primero intentamos absorber la diferencia
            # en la cuenta principal de compra/gasto.
            for i, (codigo, debe, haber) in enumerate(
                lineas_normales
            ):

                if (
                    codigo == cuenta_principal
                    and debe > 0
                ):

                    nuevo_debe = debe + diferencia

                    if nuevo_debe < -0.01:
                        raise ValueError(
                            f"Documento {doc.folio}: "
                            "la composición tributaria supera "
                            "el total del documento."
                        )

                    lineas_normales[i] = (
                        codigo,
                        max(nuevo_debe, 0.0),
                        haber
                    )

                    encontrada = True
                    break

            # Si no había línea principal y falta valor,
            # agregamos la diferencia a la cuenta seleccionada.
            if not encontrada and diferencia > 0.01:
                lineas_normales.append(
                    (
                        cuenta_principal,
                        diferencia,
                        0.0
                    )
                )

        # ----------------------------------------------------
        # HABER: PROVEEDORES
        # ----------------------------------------------------

        lineas_normales.append(
            (
                codigo_rol("proveedores"),
                0.0,
                total
            )
        )

    # --------------------------------------------------------
    # 3. VENTAS
    # --------------------------------------------------------

    elif tipo == "ventas":

        cuenta_ventas = cuenta

        # ----------------------------------------------------
        # DEBE: CLIENTES POR COBRAR
        # ----------------------------------------------------

        lineas_normales.append(
            (
                codigo_rol("clientes"),
                total,
                0.0
            )
        )

        # ----------------------------------------------------
        # HABER: IVA DÉBITO FISCAL
        # ----------------------------------------------------

        if iva > 0.001:
            lineas_normales.append(
                (
                    codigo_rol("iva_debito"),
                    0.0,
                    iva
                )
            )

        # ----------------------------------------------------
        # HABER: INGRESO POR VENTA
        # ----------------------------------------------------

        venta_base = round(
            total - iva,
            2
        )

        if venta_base > 0.001:
            lineas_normales.append(
                (
                    cuenta_ventas,
                    0.0,
                    venta_base
                )
            )

    else:
        raise ValueError(
            f"Tipo de operación no reconocido: {tipo}"
        )

    # --------------------------------------------------------
    # 4. NOTAS DE CRÉDITO
    # --------------------------------------------------------
    #
    # Las NC revierten el asiento normal.
    #
    # Ejemplo compra:
    #   Factura:
    #       Debe  Gasto / IVA
    #       Haber Proveedores
    #
    #   NC:
    #       Debe  Proveedores
    #       Haber Gasto / IVA
    #
    # Lo mismo aplica inversamente a las ventas.
    #

    if es_nc:
        lineas_normales = [
            (codigo, haber, debe)
            for codigo, debe, haber
            in lineas_normales
        ]

    # --------------------------------------------------------
    # 5. LIMPIEZA DE LÍNEAS
    # --------------------------------------------------------

    lineas = []

    for codigo, debe, haber in lineas_normales:

        # Blindaje adicional:
        # nunca permitimos que una tupla (codigo, nombre)
        # llegue al Libro Diario.
        if isinstance(codigo, (tuple, list)):
            codigo = codigo[0]

        if not codigo:
            raise ValueError(
                f"Documento {doc.folio}: "
                "se intentó contabilizar una cuenta vacía."
            )

        codigo = str(codigo).strip()

        debe = round(float(debe), 2)
        haber = round(float(haber), 2)

        if (
            abs(debe) <= 0.001
            and abs(haber) <= 0.001
        ):
            continue

        if debe < -0.001 or haber < -0.001:
            raise ValueError(
                f"Documento {doc.folio}: "
                "se generó un monto contable negativo."
            )

        lineas.append(
            (
                codigo,
                debe,
                haber
            )
        )

    # --------------------------------------------------------
    # 6. CONTROL CONTABLE FINAL
    # --------------------------------------------------------

    total_debe = round(
        sum(x[1] for x in lineas),
        2
    )

    total_haber = round(
        sum(x[2] for x in lineas),
        2
    )

    if abs(total_debe - total_haber) > 0.01:
        raise ValueError(
            f"Documento {doc.folio}: "
            f"asiento descuadrado. "
            f"Debe={total_debe}, "
            f"Haber={total_haber}"
        )

    return lineas


def siguiente_asiento(conn):

    fila = conn.execute(
        """
        SELECT COALESCE(
            MAX(asiento_id),
            0
        )
        FROM libro_diario
        """
    ).fetchone()

    return int(fila[0] or 0)


# ============================================================
# CONTABILIZACIÓN
# ============================================================


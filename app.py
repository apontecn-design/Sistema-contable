import pandas as pd
import sqlite3
import streamlit as st

# Configuración de la página web
st.set_page_config(
    page_title="Sistema Contable Pyme", page_icon="📊", layout="wide"
)

# Conexión a la base de datos local
DB_PATH = "sistema_contable.db"


def inicializar_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS cuentas_contables (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo TEXT NOT NULL UNIQUE,
        nombre TEXT NOT NULL,
        tipo TEXT NOT NULL,
        naturaleza TEXT NOT NULL
    )""")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS asientos_contables (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        numero INTEGER NOT NULL UNIQUE,
        fecha TEXT NOT NULL,
        tipo_operacion TEXT NOT NULL,
        descripcion TEXT NOT NULL,
        periodo TEXT NOT NULL
    )""")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS detalle_asientos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        asiento_id INTEGER NOT NULL,
        cuenta_id INTEGER NOT NULL,
        debe REAL NOT NULL DEFAULT 0,
        haber REAL NOT NULL DEFAULT 0,
        FOREIGN KEY (asiento_id) REFERENCES asientos_contables(id),
        FOREIGN KEY (cuenta_id) REFERENCES cuentas_contables(id)
    )""")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS proveedores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo TEXT NOT NULL UNIQUE,
        razon_social TEXT NOT NULL,
        rut TEXT NOT NULL UNIQUE
    )""")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS facturas_compra (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        numero_factura TEXT NOT NULL,
        fecha TEXT NOT NULL,
        proveedor_id INTEGER NOT NULL,
        neto REAL NOT NULL,
        iva REAL NOT NULL,
        total REAL NOT NULL,
        asiento_id INTEGER
    )""")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pagos_proveedores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        factura_id INTEGER NOT NULL,
        fecha TEXT NOT NULL,
        monto REAL NOT NULL,
        medio_pago TEXT NOT NULL,
        asiento_id INTEGER
    )""")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS movimientos_banco (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fecha TEXT NOT NULL,
        tipo_movimiento TEXT NOT NULL,
        monto REAL NOT NULL,
        referencia TEXT
    )""")

    cuentas_basicas = [
        ("1.1.02", "Banco", "ACTIVO", "DEUDORA"),
        ("1.1.04", "IVA Crédito Fiscal", "ACTIVO", "DEUDORA"),
        ("2.1.01", "Proveedores", "PASIVO", "ACREEDORA"),
        ("5.1.01", "Costo de ventas / Gastos", "GASTO", "DEUDORA"),
    ]
    for cod, nom, tipo, nat in cuentas_basicas:
        cursor.execute(
            "INSERT OR IGNORE INTO cuentas_contables (codigo, nombre, tipo,"
            " naturaleza) VALUES (?, ?, ?, ?)",
            (cod, nom, tipo, nat),
        )

    cursor.execute(
        "INSERT OR IGNORE INTO proveedores (codigo, razon_social, rut) VALUES"
        " ('PROV01', 'PROVEEDOR EJEMPLO SpA', '77.111.222-3')"
    )

    conn.commit()
    conn.close()


inicializar_db()

# Menú de Navegación Lateral
st.sidebar.title("📌 Menú Principal")
opcion = st.sidebar.radio(
    "Selecciona un Módulo:",
    [
        "Inicio / Resumen",
        "Registrar Compra Proveedor",
        "Registrar Pago Proveedor",
        "Cartola Bancaria y Saldos",
    ],
)

st.title("💼 Sistema Contable Web")

if opcion == "Inicio / Resumen":
    st.subheader("Bienvenido a tu Sistema Contable Integrado")
    st.info(
        "Utiliza el menú lateral para registrar compras, pagos a proveedores y"
        " consultar la cartola de banco."
    )

elif opcion == "Registrar Compra Proveedor":
    st.subheader("🛒 Registro de Factura de Compra")
    with st.form("form_compra"):
        numero_factura = st.text_input("Número de Factura", "550")
        fecha = st.date_input("Fecha de Factura")
        neto = st.number_input("Monto Neto ($)", min_value=0.0, value=100000.0)
        iva = neto * 0.19
        total = neto + iva
        st.write(f"**IVA (19%):** ${iva:,.0f} | **Total:** ${total:,.0f}")

        submit = st.form_submit_button("Guardar Factura y Generar Asiento")

        if submit:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()

            cursor.execute(
                "SELECT IFNULL(MAX(numero), 0) + 1 FROM asientos_contables"
            )
            num_asiento = cursor.fetchone()[0]

            cursor.execute(
                """
                INSERT INTO asientos_contables (numero, fecha, tipo_operacion, descripcion, periodo)
                VALUES (?, ?, 'FACTURA DE COMPRA', ?, ?)
            """,
                (
                    num_asiento,
                    str(fecha),
                    f"Factura Compra N° {numero_factura}",
                    str(fecha)[:7],
                ),
            )
            asiento_id = cursor.lastrowid

            cursor.execute(
                "SELECT id FROM cuentas_contables WHERE codigo = '5.1.01'"
            )
            c_gasto = cursor.fetchone()[0]
            cursor.execute(
                "SELECT id FROM cuentas_contables WHERE codigo = '1.1.04'"
            )
            c_iva = cursor.fetchone()[0]
            cursor.execute(
                "SELECT id FROM cuentas_contables WHERE codigo = '2.1.01'"
            )
            c_prov = cursor.fetchone()[0]

            cursor.execute(
                "INSERT INTO detalle_asientos (asiento_id, cuenta_id, debe,"
                " haber) VALUES (?, ?, ?, 0)",
                (asiento_id, c_gasto, neto),
            )
            cursor.execute(
                "INSERT INTO detalle_asientos (asiento_id, cuenta_id, debe,"
                " haber) VALUES (?, ?, ?, 0)",
                (asiento_id, c_iva, iva),
            )
            cursor.execute(
                "INSERT INTO detalle_asientos (asiento_id, cuenta_id, debe,"
                " haber) VALUES (?, ?, 0, ?)",
                (asiento_id, c_prov, total),
            )

            cursor.execute(
                """
                INSERT INTO facturas_compra (numero_factura, fecha, proveedor_id, neto, iva, total, asiento_id)
                VALUES (?, ?, 1, ?, ?, ?, ?)
            """,
                (numero_factura, str(fecha), neto, iva, total, asiento_id),
            )

            conn.commit()
            conn.close()
            st.success(
                f"✅ Factura N° {numero_factura} guardada con éxito por"
                f" ${total:,.0f}. Asiento Contable #{num_asiento} creado."
            )

elif opcion == "Registrar Pago Proveedor":
    st.subheader("💳 Registro de Pago a Proveedor")
    with st.form("form_pago"):
        factura_id = st.number_input("ID de Factura", min_value=1, value=1)
        fecha_pago = st.date_input("Fecha de Pago")
        monto_pago = st.number_input(
            "Monto a Pagar ($)", min_value=0.0, value=50000.0
        )
        medio_pago = st.selectbox(
            "Medio de Pago", ["TRANSFERENCIA", "EFECTIVO", "CHEQUE"]
        )

        submit_pago = st.form_submit_button("Registrar Pago")

        if submit_pago:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()

            cursor.execute(
                "SELECT IFNULL(MAX(numero), 0) + 1 FROM asientos_contables"
            )
            num_asiento = cursor.fetchone()[0]

            cursor.execute(
                """
                INSERT INTO asientos_contables (numero, fecha, tipo_operacion, descripcion, periodo)
                VALUES (?, ?, 'PAGO PROVEEDOR', ?, ?)
            """,
                (
                    num_asiento,
                    str(fecha_pago),
                    f"Pago Factura ID {factura_id}",
                    str(fecha_pago)[:7],
                ),
            )
            asiento_id = cursor.lastrowid

            cursor.execute(
                "SELECT id FROM cuentas_contables WHERE codigo = '2.1.01'"
            )
            c_prov = cursor.fetchone()[0]
            cursor.execute(
                "SELECT id FROM cuentas_contables WHERE codigo = '1.1.02'"
            )
            c_banco = cursor.fetchone()[0]

            cursor.execute(
                "INSERT INTO detalle_asientos (asiento_id, cuenta_id, debe,"
                " haber) VALUES (?, ?, ?, 0)",
                (asiento_id, c_prov, monto_pago),
            )
            cursor.execute(
                "INSERT INTO detalle_asientos (asiento_id, cuenta_id, debe,"
                " haber) VALUES (?, ?, 0, ?)",
                (asiento_id, c_banco, monto_pago),
            )

            cursor.execute(
                """
                INSERT INTO pagos_proveedores (factura_id, fecha, monto, medio_pago, asiento_id)
                VALUES (?, ?, ?, ?, ?)
            """,
                (
                    factura_id,
                    str(fecha_pago),
                    monto_pago,
                    medio_pago,
                    asiento_id,
                ),
            )

            cursor.execute(
                """
                INSERT INTO movimientos_banco (fecha, tipo_movimiento, monto, referencia)
                VALUES (?, 'CARGO', ?, ?)
            """,
                (
                    str(fecha_pago),
                    monto_pago,
                    f"Pago Factura Compra ID {factura_id}",
                ),
            )

            conn.commit()
            conn.close()
            st.success(
                f"✅ Pago de ${monto_pago:,.0f} registrado exitosamente."
            )

elif opcion == "Cartola Bancaria y Saldos":
    st.subheader("📄 Estado de Cuenta y Cartola Bancaria")
    conn = sqlite3.connect(DB_PATH)

    st.write("### 🏢 Estado de Cuenta Proveedor")
    query_prov = """
        SELECT fecha AS Fecha, 'Factura ' || numero_factura AS Documento, total AS Cargo, 0 AS Abono 
        FROM facturas_compra
        UNION ALL
        SELECT p.fecha, 'Pago Factura ' || f.numero_factura, 0, p.monto 
        FROM pagos_proveedores p
        JOIN facturas_compra f ON p.factura_id = f.id
        ORDER BY Fecha ASC
    """
    df_prov = pd.read_sql_query(query_prov, conn)
    if not df_prov.empty:
        df_prov["Saldo"] = (df_prov["Cargo"] - df_prov["Abono"]).cumsum()
        st.dataframe(df_prov, use_container_width=True)

    st.write("### 🏦 Cartola Histórica de Banco")
    query_banco = """
        SELECT fecha AS Fecha, referencia AS Detalle, 
               CASE WHEN tipo_movimiento = 'ABONO' THEN monto ELSE 0 END AS Ingresos,
               CASE WHEN tipo_movimiento = 'CARGO' THEN monto ELSE 0 END AS Egresos
        FROM movimientos_banco
        ORDER BY Fecha ASC
    """
    df_banco = pd.read_sql_query(query_banco, conn)
    if not df_banco.empty:
        df_banco["Saldo"] = (
            df_banco["Ingresos"] - df_banco["Egresos"]
        ).cumsum()
        st.dataframe(df_banco, use_container_width=True)

    conn.close()

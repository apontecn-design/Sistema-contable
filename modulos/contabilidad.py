# CONTEM: componente extraído del app.py original; ejecución secuencial compartida.
ROLES = {
    "clientes": (
        "Clientes por cobrar",
        "1.1.03.01"
    ),
    "iva_credito": (
        "IVA Crédito Fiscal",
        "1.1.03.02"
    ),
    "proveedores": (
        "Proveedores por pagar",
        "2.1.01.01"
    ),
    "iva_debito": (
        "IVA Débito Fiscal",
        "2.1.01.02"
    ),
    "iva_por_pagar": (
        "IVA por pagar",
        "2.1.01.03"
    ),
    "gasto_defecto": (
        "Gastos generales por defecto",
        "5.2.01"
    ),
    "ingreso_defecto": (
        "Ingresos por defecto (Ventas Afectas)",
        "4.1.01"
    ),
    "ingreso_exento": (
        "Ventas exentas",
        "4.1.04"
    ),
    "activo_fijo": (
        "Activo fijo",
        "1.2.01.01"
    ),
    "iva_no_recuperable": (
        "IVA no recuperable",
        "5.2.02"
    ),
    "iva_uso_comun": (
        "IVA de uso común por determinar",
        "1.1.03.03"
    ),
}


# ============================================================
# ESQUEMA Y MIGRACIONES
# ============================================================


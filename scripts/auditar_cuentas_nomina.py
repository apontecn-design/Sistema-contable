"""Auditoría de compatibilidad de cuentas de Nómina sin escribir en la BD.

Uso: python scripts/auditar_cuentas_nomina.py /ruta/respaldo.db
Nunca ejecuta migraciones ni imprime datos personales.
"""
import argparse
import json
import sqlite3
from pathlib import Path

CUENTAS_NOMINA = {
    "2.1.02": "Obligaciones laborales y previsionales",
    "2.1.02.01": "Remuneraciones por pagar",
    "2.1.02.02": "Cotizaciones previsionales por pagar",
    "2.1.02.03": "Retenciones de Trabajadores por pagar",
    "2.1.02.04": "Otras obligaciones laborales",
    "2.1.02.05": "Impuesto Único de trabajadores por pagar",
}


def auditar(ruta):
    ruta = Path(ruta).resolve(strict=True)
    conn = sqlite3.connect(ruta.as_uri() + "?mode=ro", uri=True)
    try:
        integridad = conn.execute("PRAGMA integrity_check").fetchone()[0]
        tablas = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if "plan_cuentas" not in tablas:
            raise ValueError("No existe tabla plan_cuentas")
        columnas = {r[1] for r in conn.execute("PRAGMA table_info(plan_cuentas)")}
        if not {"codigo", "nombre", "padre_codigo"}.issubset(columnas):
            raise ValueError("Estructura de plan_cuentas incompatible")
        filas = {r[0]: (r[1], r[2]) for r in conn.execute(
            "SELECT codigo, nombre, padre_codigo FROM plan_cuentas")}
        faltantes = sorted(set(CUENTAS_NOMINA) - set(filas))
        padres_incorrectos = sorted(
            codigo for codigo in CUENTAS_NOMINA
            if codigo in filas and filas[codigo][1] !=
            ("2.1" if codigo == "2.1.02" else "2.1.02"))
        return {
            "integridad": integridad,
            "cuentas_plan": len(filas),
            "cuentas_nomina_presentes": len(CUENTAS_NOMINA) - len(faltantes),
            "faltantes": faltantes,
            "padres_incorrectos": padres_incorrectos,
            "compatible": integridad == "ok" and not faltantes and not padres_incorrectos,
        }
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("respaldo")
    args = parser.parse_args()
    print(json.dumps(auditar(args.respaldo), indent=2, ensure_ascii=False))

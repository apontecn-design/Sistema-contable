"""Auditoría de nómina de solo lectura. No modifica la base ni muestra datos personales."""
import argparse
import json
import sqlite3


def auditar_nomina(ruta):
    conn = sqlite3.connect("file:" + __import__("pathlib").Path(ruta).resolve(strict=True).as_posix() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        tablas = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        necesarias = {"nomina_periodos", "nomina_liquidaciones", "libro_diario"}
        if not necesarias <= tablas:
            return {"error": "Faltan tablas: " + ", ".join(sorted(necesarias - tablas))}
        periodos = conn.execute(
            "SELECT periodo, estado, asiento_id FROM nomina_periodos WHERE asiento_id IS NOT NULL ORDER BY periodo"
        ).fetchall()
        resultados = []
        for p in periodos:
            asiento = p["asiento_id"]
            lineas = conn.execute(
                "SELECT COUNT(*) n, COALESCE(SUM(debe),0) debe, COALESCE(SUM(haber),0) haber "
                "FROM libro_diario WHERE asiento_id=? AND origen='NOMINA'", (asiento,)
            ).fetchone()
            estados = conn.execute(
                "SELECT COUNT(*) n, SUM(CASE WHEN estado='CONTABILIZADO' THEN 1 ELSE 0 END) ok "
                "FROM nomina_liquidaciones WHERE periodo=?", (p["periodo"],)
            ).fetchone()
            otros = conn.execute(
                "SELECT COUNT(*) FROM nomina_periodos WHERE asiento_id=? AND periodo<>?", (asiento, p["periodo"])
            ).fetchone()[0]
            resultados.append({
                "periodo": p["periodo"], "asiento": asiento,
                "lineas": lineas["n"], "debe": round(lineas["debe"], 2),
                "haber": round(lineas["haber"], 2),
                "liquidaciones": estados["n"],
                "liquidaciones_contabilizadas": estados["ok"] or 0,
                "correcto": bool(lineas["n"] >= 2
                                and abs(lineas["debe"] - lineas["haber"]) < .01
                                and estados["n"] > 0 and estados["n"] == (estados["ok"] or 0)
                                and p["estado"] == "CONTABILIZADO" and otros == 0),
            })
        return {"periodos": resultados, "correcto": all(x["correcto"] for x in resultados)}
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("base_sqlite")
    args = parser.parse_args()
    print(json.dumps(auditar_nomina(args.base_sqlite), ensure_ascii=False, indent=2))

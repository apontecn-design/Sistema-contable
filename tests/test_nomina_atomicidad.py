"""Prueba aislada de atomicidad del asiento de Nómina, sin Streamlit ni producción."""
import ast
import sqlite3
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "modulos" / "conciliacion_documental.py"
TREE = ast.parse(SOURCE.read_text(encoding="utf-8"))
FUNCTION = next(n for n in TREE.body if isinstance(n, ast.FunctionDef)
                and n.name == "nomina_contabilizar_periodo")


def funcion_entorno(fallar=False):
    def vista(conn, periodo):
        return "2026-11-30", [
            {"Código": "5.2.03.01", "Debe": 1000, "Haber": 0},
            {"Código": "2.1.02.01", "Debe": 0, "Haber": 1000},
        ], 1000, 1000

    def linea(conn, fecha, codigo, debe, haber, glosa, asiento):
        if fallar and haber:
            raise RuntimeError("Fallo simulado al guardar la segunda línea")
        conn.execute("INSERT INTO libro_diario VALUES (?,?,?,?,?)",
                     (asiento, codigo, debe, haber, fecha))

    contexto = {
        "sgci_autorizar_operacion": lambda *a: None,
        "sgci_rrhh_ids_autorizados": lambda *a: None,
        "sgci_identidad_actual": lambda: 'administrador_prueba',
        "nomina_vista_previa": vista,
        "siguiente_asiento": lambda conn: 0,
        "nomina_asiento_linea": linea,
    }
    exec(compile(ast.Module(body=[FUNCTION], type_ignores=[]), str(SOURCE), "exec"),
         contexto)
    return contexto["nomina_contabilizar_periodo"]


def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE nomina_periodos (periodo TEXT PRIMARY KEY, estado TEXT,
            fecha_cierre TEXT, asiento_id INTEGER);
        CREATE TABLE nomina_liquidaciones (id INTEGER PRIMARY KEY, periodo TEXT,
            estado TEXT);
        CREATE TABLE libro_diario (asiento_id INTEGER, codigo_cuenta TEXT,
            debe INTEGER, haber INTEGER, fecha TEXT);
        INSERT INTO nomina_liquidaciones VALUES (1,'2026-11','PENDIENTE');
    """)
    return conn


class TestNominaAtomica(unittest.TestCase):
    def test_guarda_asiento_y_estado_y_rechaza_duplicado(self):
        with db() as conn:
            f = funcion_entorno()
            self.assertEqual(f(conn, "2026-11"), 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM libro_diario").fetchone()[0], 2)
            with self.assertRaises(ValueError):
                f(conn, "2026-11")
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM libro_diario").fetchone()[0], 2)

    def test_error_revierte_todas_las_lineas_y_estado(self):
        with db() as conn:
            with self.assertRaises(RuntimeError):
                funcion_entorno(fallar=True)(conn, "2026-11")
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM libro_diario").fetchone()[0], 0)
            self.assertEqual(conn.execute(
                "SELECT estado FROM nomina_liquidaciones WHERE id=1").fetchone()[0], "PENDIENTE")


if __name__ == "__main__":
    unittest.main()

"""Pruebas de la auditoría de cuentas de Nómina en modo lectura."""
import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "auditar_cuentas_nomina.py"
SPEC = importlib.util.spec_from_file_location("auditar_cuentas_nomina", SCRIPT)
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class TestAuditoriaCuentasNomina(unittest.TestCase):
    def test_detecta_faltantes_sin_alterar_respaldo(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / "respaldo.db"
            with sqlite3.connect(ruta) as db:
                db.execute("""CREATE TABLE plan_cuentas (
                    codigo TEXT PRIMARY KEY, nombre TEXT, padre_codigo TEXT)""")
                db.execute("INSERT INTO plan_cuentas VALUES ('2.1.02.05','Impuesto Único','2.1.02')")
            antes = ruta.read_bytes()
            resultado = MOD.auditar(ruta)
            self.assertFalse(resultado["compatible"])
            self.assertIn("2.1.02.01", resultado["faltantes"])
            self.assertEqual(ruta.read_bytes(), antes)

    def test_valida_jerarquia_completa(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / "respaldo.db"
            with sqlite3.connect(ruta) as db:
                db.execute("""CREATE TABLE plan_cuentas (
                    codigo TEXT PRIMARY KEY, nombre TEXT, padre_codigo TEXT)""")
                for codigo, nombre in MOD.CUENTAS_NOMINA.items():
                    padre = "2.1" if codigo == "2.1.02" else "2.1.02"
                    db.execute("INSERT INTO plan_cuentas VALUES (?,?,?)", (codigo, nombre, padre))
            self.assertTrue(MOD.auditar(ruta)["compatible"])


if __name__ == "__main__":
    unittest.main()

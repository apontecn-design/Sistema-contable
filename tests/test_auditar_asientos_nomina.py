import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path

RUTA = Path(__file__).resolve().parents[1] / "scripts" / "auditar_asientos_nomina.py"
spec = importlib.util.spec_from_file_location("auditoria_nomina", RUTA)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class TestAuditoriaNomina(unittest.TestCase):
    def test_asiento_cuadrado_y_desbalanceado_sin_escribir(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "nomina.db"
            conn = sqlite3.connect(ruta)
            conn.executescript("""
                CREATE TABLE nomina_periodos (periodo TEXT, estado TEXT, asiento_id INTEGER);
                CREATE TABLE nomina_liquidaciones (periodo TEXT, estado TEXT);
                CREATE TABLE libro_diario (asiento_id INTEGER, origen TEXT, debe REAL, haber REAL);
                INSERT INTO nomina_periodos VALUES ('2026-11','CONTABILIZADO',32);
                INSERT INTO nomina_liquidaciones VALUES ('2026-11','CONTABILIZADO');
                INSERT INTO libro_diario VALUES (32,'NOMINA',1200000,0);
                INSERT INTO libro_diario VALUES (32,'NOMINA',0,1200000);
            """)
            conn.commit()
            self.assertTrue(mod.auditar_nomina(ruta)["correcto"])
            conn.execute("UPDATE libro_diario SET haber=1100000 WHERE haber>0")
            conn.commit()
            self.assertFalse(mod.auditar_nomina(ruta)["correcto"])
            conn.close()


if __name__ == "__main__":
    unittest.main()

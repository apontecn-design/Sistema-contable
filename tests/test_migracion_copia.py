"""Ejecuta migración aditiva sobre una copia temporal y verifica invariantes."""
import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path

SCRIPT=Path(__file__).resolve().parents[1]/'scripts'/'validar_migracion_copia.py'
SPEC=importlib.util.spec_from_file_location('contem_migracion_copia',SCRIPT)
MOD=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class TestMigracionCopia(unittest.TestCase):
    def test_migracion_preserva_registros_y_diario(self):
        with tempfile.TemporaryDirectory() as temp:
            origen=Path(temp)/'respaldo.db'
            with sqlite3.connect(origen) as db:
                db.executescript("""
                    CREATE TABLE sgci_usuarios(
                        email TEXT PRIMARY KEY,rol TEXT,activo INTEGER,creado_en TEXT);
                    CREATE TABLE sgci_permisos(
                        email TEXT,modulo TEXT,accion TEXT,permitido INTEGER);
                    CREATE TABLE nomina_trabajadores(id INTEGER PRIMARY KEY);
                    CREATE TABLE libro_diario(id INTEGER PRIMARY KEY,debe REAL,haber REAL);
                    INSERT INTO sgci_usuarios VALUES
                        ('prueba@example.com','Ventas',1,'2026-01-01');
                    INSERT INTO sgci_permisos VALUES
                        ('prueba@example.com','cxc','ver',1);
                    INSERT INTO libro_diario VALUES(1,119,0),(2,0,119);
                """)
            antes=origen.read_bytes()
            resultado=MOD.validar(origen)
            self.assertTrue(resultado['aprobado'],resultado)
            self.assertTrue(resultado['totales_diario_preservados'])
            self.assertEqual(resultado['registros_antes'],
                             resultado['registros_despues'])
            self.assertEqual(origen.read_bytes(),antes)


if __name__=='__main__':
    unittest.main()

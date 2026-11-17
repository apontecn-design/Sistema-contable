from contextlib import closing
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
            with closing(sqlite3.connect(origen)) as db, db:
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


    def test_esquema_real_sin_usuarios_preserva_diario(self):
        # El respaldo de 2026-11-10 contiene sgci_usuarios y sgci_permisos
        # sin registros; reproducimos esa condición sin incluir datos privados.
        with tempfile.TemporaryDirectory() as temp:
            origen=Path(temp)/'copia_esquema.db'
            with closing(sqlite3.connect(origen)) as db, db:
                db.executescript("""
                    CREATE TABLE sgci_usuarios (
                        email TEXT PRIMARY KEY COLLATE NOCASE,
                        rol TEXT NOT NULL DEFAULT 'Personalizado',
                        activo INTEGER NOT NULL DEFAULT 1,
                        creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
                    CREATE TABLE sgci_permisos (
                        email TEXT NOT NULL COLLATE NOCASE,
                        modulo TEXT NOT NULL,
                        accion TEXT NOT NULL,
                        permitido INTEGER NOT NULL DEFAULT 0,
                        PRIMARY KEY(email,modulo,accion),
                        FOREIGN KEY(email) REFERENCES sgci_usuarios(email));
                    CREATE TABLE nomina_trabajadores(id INTEGER PRIMARY KEY);
                    CREATE TABLE libro_diario(id INTEGER PRIMARY KEY,debe REAL,haber REAL);
                    INSERT INTO libro_diario VALUES(1,2500,0),(2,0,2500);
                """)
            resultado=MOD.validar(origen)
            self.assertTrue(resultado['aprobado'],resultado)
            self.assertEqual(resultado['registros_despues']['sgci_usuarios'],0)
            self.assertTrue(resultado['totales_diario_preservados'])


if __name__=='__main__':
    unittest.main()

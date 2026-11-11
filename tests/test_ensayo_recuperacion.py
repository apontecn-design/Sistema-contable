from contextlib import closing
"""Ensayo de backup/restore sobre base sintética sin alterar origen."""
import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path

SCRIPT=Path(__file__).resolve().parents[1]/'scripts'/'ensayar_recuperacion.py'
SPEC=importlib.util.spec_from_file_location('contem_recuperacion',SCRIPT)
MOD=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class TestRecuperacion(unittest.TestCase):
    def test_respaldo_y_restauracion_conservan_origen(self):
        with tempfile.TemporaryDirectory() as carpeta:
            origen=Path(carpeta)/'original.db'
            with closing(sqlite3.connect(origen)) as db, db:
                db.executescript("""
                    PRAGMA foreign_keys=ON;
                    CREATE TABLE clientes(id INTEGER PRIMARY KEY,nombre TEXT);
                    CREATE TABLE ventas(id INTEGER PRIMARY KEY,cliente_id INTEGER
                        REFERENCES clientes(id),total REAL);
                    INSERT INTO clientes VALUES(1,'Cliente');
                    INSERT INTO ventas VALUES(10,1,119.0);
                """)
            antes=origen.read_bytes()
            resultado=MOD.ensayar(origen)
            self.assertTrue(resultado['aprobado'])
            self.assertEqual(resultado['integridad_restaurada'],'ok')
            self.assertEqual(origen.read_bytes(),antes)

    def test_no_crea_base_cuando_no_existe(self):
        with tempfile.TemporaryDirectory() as carpeta:
            origen=Path(carpeta)/'inexistente.db'
            with self.assertRaises(FileNotFoundError):
                MOD.ensayar(origen)
            self.assertFalse(origen.exists())


if __name__=='__main__':
    unittest.main()

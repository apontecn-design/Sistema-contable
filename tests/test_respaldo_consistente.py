from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from modulos import utilidades


class TestRespaldoConsistente(unittest.TestCase):
    def test_incluye_cambios_confirmados_en_wal(self):
        with tempfile.TemporaryDirectory() as carpeta:
            with closing(sqlite3.connect(Path(carpeta)/'origen.db')) as db:
                db.execute('PRAGMA journal_mode=WAL')
                db.execute('CREATE TABLE datos(id INTEGER)');db.commit()
                db.execute('INSERT INTO datos VALUES(123)');db.commit()
                with patch.dict(utilidades.sgci_respaldo_consistente.__globals__,{'sgci_es_propietario':lambda:True}):
                    respaldo=utilidades.sgci_respaldo_consistente(db)
                with closing(sqlite3.connect(':memory:')) as restaurada:
                    restaurada.deserialize(respaldo)
                    self.assertEqual(restaurada.execute('SELECT id FROM datos').fetchone()[0],123)
                    self.assertEqual(restaurada.execute('PRAGMA integrity_check').fetchone()[0],'ok')

    def test_empleado_no_puede_exportar_base(self):
        with closing(sqlite3.connect(':memory:')) as db:
            with patch.dict(utilidades.sgci_respaldo_consistente.__globals__,{'sgci_es_propietario':lambda:False}):
                with self.assertRaises(PermissionError):utilidades.sgci_respaldo_consistente(db)

    def test_no_incluye_operacion_sin_confirmar(self):
        with closing(sqlite3.connect(':memory:')) as db:
            db.execute('CREATE TABLE datos(id INTEGER)')
            db.execute('INSERT INTO datos VALUES(123)')
            with patch.dict(utilidades.sgci_respaldo_consistente.__globals__,{'sgci_es_propietario':lambda:True}):
                with self.assertRaises(RuntimeError):utilidades.sgci_respaldo_consistente(db)

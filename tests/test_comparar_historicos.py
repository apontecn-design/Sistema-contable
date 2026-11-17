"""Detecta cambios de contenido aun cuando los conteos de registros coinciden."""
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from scripts.comparar_historicos import comparar


class TestCompararHistoricos(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.a = Path(self.tmp.name) / 'origen.db'
        self.b = Path(self.tmp.name) / 'copia.db'
        for ruta in (self.a, self.b):
            with closing(sqlite3.connect(ruta)) as db, db:
                db.executescript("CREATE TABLE datos(id INTEGER, monto REAL, adjunto BLOB);"
                                 "INSERT INTO datos VALUES(1,119,X'0011'),(2,238,X'FF');")

    def modificar(self, sql):
        with closing(sqlite3.connect(self.b)) as db, db:
            db.executescript(sql)

    def test_iguales(self):
        self.assertTrue(comparar(self.a, self.b)['aprobado'])

    def test_mismo_conteo_distinto_valor(self):
        self.modificar('UPDATE datos SET monto=999 WHERE id=1')
        r = comparar(self.a, self.b)
        self.assertFalse(r['aprobado'])
        self.assertEqual(r['cambios'][0]['filas_antes'], r['cambios'][0]['filas_despues'])

    def test_adiciones_de_esquema_no_alteran_originales(self):
        self.modificar('ALTER TABLE datos ADD COLUMN nuevo TEXT; CREATE TABLE adicional(id INTEGER)')
        self.assertTrue(comparar(self.a, self.b)['aprobado'])

    def test_detecta_borrado(self):
        self.modificar('DELETE FROM datos WHERE id=1')
        self.assertFalse(comparar(self.a, self.b)['aprobado'])

    def test_detecta_tabla_ausente(self):
        self.modificar('DROP TABLE datos')
        self.assertFalse(comparar(self.a, self.b)['aprobado'])

    def test_detecta_columna_ausente(self):
        self.modificar('ALTER TABLE datos DROP COLUMN monto')
        self.assertFalse(comparar(self.a, self.b)['aprobado'])

    def test_no_crea_archivo_inexistente(self):
        ruta = Path(self.tmp.name) / 'no_existe.db'
        with self.assertRaises(sqlite3.OperationalError):
            comparar(self.a, ruta)
        self.assertFalse(ruta.exists())

    def test_no_modifica_archivos(self):
        antes = (self.a.read_bytes(), self.b.read_bytes())
        comparar(self.a, self.b)
        self.assertEqual(antes, (self.a.read_bytes(), self.b.read_bytes()))

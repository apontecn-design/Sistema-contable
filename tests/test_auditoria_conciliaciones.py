from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from scripts.auditar_sqlite import auditar


class TestAuditoriaConciliaciones(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.ruta=Path(self.tmp.name)/'copia.db'
        with closing(sqlite3.connect(self.ruta)) as db,db:
            db.executescript('''CREATE TABLE cartola_bancaria(id INTEGER,banco_id INTEGER,fecha TEXT,
              cargo REAL,abono REAL,conciliado INTEGER,asiento_id INTEGER,match_tipo TEXT,match_id INTEGER);
              CREATE TABLE sgci_conciliacion_lineas(cartola_id INTEGER,diario_id INTEGER,monto REAL);
              CREATE TABLE libro_diario(id INTEGER);
              INSERT INTO cartola_bancaria VALUES
              (1,1,'2026-01-01',100,0,1,NULL,'CHEQUE_PROTESTADO',2),
              (2,1,'2026-01-01',100,100,1,NULL,'CHEQUE_PROTESTADO',2),
              (3,1,'2026-01-01',0,100,1,NULL,'CHEQUE_PROTESTADO',2),
              (4,1,'2026-01-01',150,0,1,NULL,'ASIENTOS_EXISTENTES',NULL);
              INSERT INTO libro_diario VALUES(10),(20);
              INSERT INTO sgci_conciliacion_lineas VALUES(4,10,100),(4,20,50);''')

    def test_sin_asiento_directo_puede_tener_vinculos_validos(self):
        r=auditar(self.ruta)['hallazgos']
        self.assertEqual(r['cartolas_conciliadas_sin_asiento'],4)
        self.assertEqual(r['conciliaciones_existentes_sin_respaldo_cuadrado'],0)
        self.assertEqual(r['grupos_cheques_protestados_inconsistentes'],0)

    def test_detecta_vinculo_incompleto(self):
        with closing(sqlite3.connect(self.ruta)) as db,db:db.execute('DELETE FROM sgci_conciliacion_lineas WHERE diario_id=20')
        self.assertEqual(auditar(self.ruta)['hallazgos']['conciliaciones_existentes_sin_respaldo_cuadrado'],1)

    def test_detecta_grupo_protestado_incompleto(self):
        with closing(sqlite3.connect(self.ruta)) as db,db:db.execute('DELETE FROM cartola_bancaria WHERE id=3')
        self.assertEqual(auditar(self.ruta)['hallazgos']['grupos_cheques_protestados_inconsistentes'],1)

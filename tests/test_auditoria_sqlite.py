"""Contrato de auditoría de solo lectura sobre copia sintética de SQLite."""
import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path

SCRIPT=Path(__file__).resolve().parents[1]/'scripts'/'auditar_sqlite.py'
SPEC=importlib.util.spec_from_file_location('contem_auditoria',SCRIPT)
AUDIT=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


class TestAuditoriaSQLite(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.ruta=Path(self.tmp.name)/'copia.db'
        with sqlite3.connect(self.ruta) as db:
            db.executescript("""
                CREATE TABLE cartola_bancaria(
                    id INTEGER PRIMARY KEY,conciliado INTEGER,
                    asiento_id INTEGER,match_tipo TEXT,match_id INTEGER);
                INSERT INTO cartola_bancaria VALUES(1,1,NULL,'CHEQUE_PROTESTADO',10);
                INSERT INTO cartola_bancaria VALUES(2,1,NULL,'ASIENTOS_EXISTENTES',11);
                INSERT INTO cartola_bancaria VALUES(3,1,45,'TESORERIA',20);
                CREATE TABLE compras(id INTEGER PRIMARY KEY,monto_total REAL);
                CREATE TABLE pagos_proveedores(id INTEGER PRIMARY KEY,monto REAL);
                CREATE TABLE aplicaciones_proveedores(
                    id INTEGER PRIMARY KEY,pago_id INTEGER,compra_id INTEGER,monto REAL);
                INSERT INTO compras VALUES(1,100);
                INSERT INTO pagos_proveedores VALUES(1,70);
                INSERT INTO aplicaciones_proveedores VALUES(1,1,1,70);
            """)

    def tearDown(self):
        self.tmp.cleanup()

    def test_clasifica_cartolas_y_no_modifica_base(self):
        antes=self.ruta.read_bytes()
        r=AUDIT.auditar(self.ruta)
        self.assertEqual(r['integridad'],'ok')
        self.assertEqual(r['hallazgos']['cartolas_conciliadas_sin_asiento'],2)
        self.assertEqual(r['hallazgos']['cartolas_tesoreria_sin_asiento'],0)
        self.assertEqual(r['hallazgos']['cartolas_sin_asiento_por_tipo'],
                         {'CHEQUE_PROTESTADO':1,'ASIENTOS_EXISTENTES':1})
        self.assertEqual(r['hallazgos']['compras_sobrepagadas'],0)
        self.assertEqual(antes,self.ruta.read_bytes())

    def test_detecta_duplicados_tesoreria(self):
        with sqlite3.connect(self.ruta) as db:
            db.execute("""INSERT INTO cartola_bancaria VALUES
                (4,1,45,'TESORERIA',20)""")
        r=AUDIT.auditar(self.ruta)
        self.assertEqual(r['hallazgos']['cartolas_tesoreria_duplicadas'],1)

    def test_detecta_sobreaplicacion_proveedores(self):
        with sqlite3.connect(self.ruta) as db:
            db.execute('UPDATE aplicaciones_proveedores SET monto=90')
        r=AUDIT.auditar(self.ruta)
        self.assertEqual(r['hallazgos']['pagos_proveedores_sobreaplicados'],1)


if __name__=='__main__':
    unittest.main()

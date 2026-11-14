"""Pruebas de pagos parciales, saldos y reversión con auxiliares sintéticos.

No sustituyen las pruebas de servicios reales de registro/anulación.
"""
import sqlite3
import unittest


class TestAuxiliaresPagos(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:')
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript("""
            CREATE TABLE compras(id INTEGER PRIMARY KEY,monto_total REAL NOT NULL);
            CREATE TABLE ventas(id INTEGER PRIMARY KEY,monto_total REAL NOT NULL);
            CREATE TABLE pagos_proveedores(id INTEGER PRIMARY KEY,monto REAL NOT NULL);
            CREATE TABLE pagos_clientes(id INTEGER PRIMARY KEY,monto REAL NOT NULL);
            CREATE TABLE aplicaciones_proveedores(
                id INTEGER PRIMARY KEY,pago_id INTEGER REFERENCES pagos_proveedores(id),
                compra_id INTEGER REFERENCES compras(id),monto REAL NOT NULL CHECK(monto>0));
            CREATE TABLE aplicaciones_clientes(
                id INTEGER PRIMARY KEY,pago_id INTEGER REFERENCES pagos_clientes(id),
                venta_id INTEGER REFERENCES ventas(id),monto REAL NOT NULL CHECK(monto>0));
            INSERT INTO compras VALUES(1,100000);
            INSERT INTO ventas VALUES(1,80000);
            INSERT INTO pagos_proveedores VALUES(1,40000);
            INSERT INTO pagos_proveedores VALUES(2,20000);
            INSERT INTO pagos_clientes VALUES(1,30000);
            INSERT INTO aplicaciones_proveedores VALUES(1,1,1,40000);
            INSERT INTO aplicaciones_proveedores VALUES(2,2,1,20000);
            INSERT INTO aplicaciones_clientes VALUES(1,1,1,30000);
        """)
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def saldo(self,tabla,aplicaciones,columna):
        return self.db.execute(f"""SELECT d.monto_total-
            COALESCE((SELECT SUM(a.monto) FROM {aplicaciones} a
                      WHERE a.{columna}=d.id),0)
            FROM {tabla} d WHERE d.id=1""").fetchone()[0]

    def test_saldos_despues_de_pagos_parciales(self):
        self.assertEqual(self.saldo('compras','aplicaciones_proveedores','compra_id'),40000)
        self.assertEqual(self.saldo('ventas','aplicaciones_clientes','venta_id'),50000)

    def test_reversion_de_aplicacion_restaura_saldo(self):
        self.db.execute('DELETE FROM aplicaciones_proveedores WHERE id=2')
        self.db.commit()
        self.assertEqual(self.saldo('compras','aplicaciones_proveedores','compra_id'),60000)

    def test_rollback_restauracion_de_saldo(self):
        try:
            self.db.execute('BEGIN IMMEDIATE')
            self.db.execute('DELETE FROM aplicaciones_clientes WHERE id=1')
            raise RuntimeError('Falla simulada')
        except RuntimeError:
            self.db.rollback()
        self.assertEqual(self.saldo('ventas','aplicaciones_clientes','venta_id'),50000)

    def test_no_existen_referencias_huerfanas(self):
        self.assertEqual(self.db.execute('PRAGMA foreign_key_check').fetchall(),[])


if __name__=='__main__':
    unittest.main()

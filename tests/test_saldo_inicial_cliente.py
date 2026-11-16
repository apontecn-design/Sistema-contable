import sqlite3
import unittest
from unittest.mock import patch
from modulos import conciliacion_documental as servicio,contabilidad_reportes as reportes
from tests.soporte_flujos import preparar


class TestSaldoInicialCliente(unittest.TestCase):
    def setUp(self):
        self.db=preparar(self)
        reportes.sgci_saldos_apertura_clientes(self.db)
        self.db.execute("INSERT INTO clientes(id,rut,nombre) VALUES(1,'1-9','Cliente de prueba')")
        self.db.commit()

    def guardar(self,monto):servicio.guardar_saldo_inicial_cliente(self.db,1,monto)

    def test_crear_editar_y_cero_sin_asientos(self):
        diario=list(self.db.execute('SELECT * FROM libro_diario'))
        for monto in (100,200,0):
            self.guardar(monto)
            self.assertEqual(servicio.cliente_saldo_inicial(self.db,1),{'monto':monto,'aplicado':0,'disponible':monto})
        self.assertEqual(list(self.db.execute('SELECT * FROM libro_diario')),diario)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM auditoria WHERE accion='SALDO INICIAL CLIENTE'").fetchone()[0],3)

    def test_no_disminuye_por_debajo_de_aplicaciones(self):
        self.guardar(100)
        self.db.execute("INSERT INTO sgci_aplicaciones_apertura_clientes(movimiento_id,cliente_id,monto,fecha) VALUES(1,1,60,'2026-01-02')")
        self.db.commit();antes=list(self.db.iterdump())
        with self.assertRaises(ValueError):self.guardar(59)
        self.assertEqual(list(self.db.iterdump()),antes)
        self.guardar(60)
        self.assertEqual(servicio.cliente_saldo_inicial(self.db,1)['disponible'],0)

    def test_montos_invalidos_no_modifican_datos(self):
        antes=list(self.db.iterdump())
        for monto in (-1,1.5,'NaN','Infinity','abc',None,True,9223372036854775808):
            with self.subTest(monto=monto),self.assertRaises(ValueError):self.guardar(monto)
            self.assertEqual(list(self.db.iterdump()),antes)

    def test_cliente_inexistente_no_crea_saldo(self):
        with self.assertRaises(ValueError):servicio.guardar_saldo_inicial_cliente(self.db,999,100)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM sgci_apertura_clientes').fetchone()[0],0)

    def test_denegacion_precede_lecturas_y_escrituras(self):
        self.db.execute("INSERT INTO sgci_usuario_permisos_detalle VALUES('finanzas@example.com','cxc','Clientes y estados de cuenta','editar',0)")
        self.db.commit();consultas=[];self.db.set_trace_callback(consultas.append)
        with self.assertRaises(PermissionError):self.guardar(100)
        self.db.set_trace_callback(None)
        self.assertFalse(any('FROM clientes' in q or 'FROM sgci_apertura' in q or 'BEGIN IMMEDIATE' in q for q in consultas))

    def test_lectura_exige_permiso_de_pagos(self):
        self.db.execute("INSERT INTO sgci_usuario_permisos_detalle VALUES('finanzas@example.com','cxc','Pagos de clientes','ver',0)")
        self.db.commit()
        with self.assertRaises(PermissionError):servicio.cliente_saldo_inicial(self.db,1)

    def test_revocacion_tras_reserva_no_deja_cambios(self):
        original=servicio.sgci_autorizar_operacion
        def autorizar(conn,*args):
            original(conn,*args)
            if conn.in_transaction:raise PermissionError('Revocado')
        antes=list(self.db.iterdump())
        with patch.dict(vars(servicio),{'sgci_autorizar_operacion':autorizar}):
            with self.assertRaises(PermissionError):self.guardar(100)
        self.assertEqual(list(self.db.iterdump()),antes)

    def test_fallo_auditoria_revierte_saldo(self):
        self.db.execute("CREATE TRIGGER fallo BEFORE INSERT ON auditoria BEGIN SELECT RAISE(ABORT,'fallo'); END")
        self.db.commit();antes=list(self.db.iterdump())
        with self.assertRaises(sqlite3.IntegrityError):self.guardar(100)
        self.assertEqual(list(self.db.iterdump()),antes)

    def test_guardado_no_confirma_transaccion_ajena(self):
        self.db.execute("UPDATE clientes SET nombre='Pendiente' WHERE id=1")
        with self.assertRaises(RuntimeError):self.guardar(100)
        self.assertTrue(self.db.in_transaction)
        self.db.rollback()
        self.assertEqual(self.db.execute('SELECT nombre FROM clientes WHERE id=1').fetchone()[0],'Cliente de prueba')

    def test_lectura_e_inicializacion_preservan_transaccion(self):
        self.db.execute("UPDATE clientes SET nombre='Pendiente' WHERE id=1")
        antes=list(self.db.iterdump())
        reportes.sgci_saldos_apertura_clientes(self.db)
        servicio.cliente_saldo_inicial(self.db,1)
        self.assertTrue(self.db.in_transaction)
        self.assertEqual(list(self.db.iterdump()),antes)
        self.db.rollback()


if __name__=='__main__':unittest.main()

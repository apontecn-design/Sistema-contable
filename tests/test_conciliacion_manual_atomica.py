import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from modulos import contabilidad_reportes as servicio,conciliacion_documental as auxiliar
from tests.soporte_flujos import preparar


class TestConciliacionManualAtomica(unittest.TestCase):
    def setUp(self):
        self.db=preparar(self);auxiliar.sgci_conc_esquema(self.db)
        p=patch.dict(vars(servicio),{'sgci_conc_esquema':auxiliar.sgci_conc_esquema,'money':str,
            'documentos_pendientes_proveedor':auxiliar.documentos_pendientes_proveedor,
            '_sgci_exigir_sin_transaccion':auxiliar._sgci_exigir_sin_transaccion,'_sgci_auditar_auxiliar':auxiliar._sgci_auditar_auxiliar})
        p.start();self.addCleanup(p.stop)
        self.db.executescript("""
            INSERT INTO clientes(id,rut,nombre) VALUES(1,'1-9','Cliente prueba');
            INSERT INTO ventas(id,cliente_id,fecha,folio,tipo_doc,monto_total) VALUES(1,1,'2026-11-01','1',33,100);
            INSERT INTO compras(id,proveedor_id,fecha,folio,tipo_doc,monto_total) VALUES(1,1,'2026-11-01','1',33,100);
            INSERT INTO obligaciones_manuales(id,fecha,tipo,descripcion,monto,codigo_cuenta) VALUES(1,'2026-11-01','PAGO','Obligación sintética',100,'5.9.01');
            INSERT INTO plan_cuentas(codigo,nombre,tipo) VALUES('5.9.01','Gasto sintético A','Gastos'),('5.9.02','Gasto sintético B','Gastos');
            INSERT INTO cartola_bancaria(id,banco_id,fecha,descripcion,cargo,abono) VALUES(1,1,'2026-11-16','Cargo prueba',100,0),(2,1,'2026-11-16','Abono prueba',0,100);
        """)

    def sugerencia(self,db=None,mov=1,tipo='MANUAL'):
        return servicio.contabilizar_conciliacion_bancaria(db or self.db,mov,tipo,1)

    def manual(self,db=None,mov=1):
        return servicio.contabilizar_imputacion_manual_bancaria(db or self.db,mov,'5.9.01')

    def multiple(self,db=None,mov=1):
        return servicio.contabilizar_imputacion_multiple_bancaria(db or self.db,mov,[('5.9.01',40),('5.9.02',60)])

    def cuadrado(self,asiento,lineas=2):
        self.assertEqual(tuple(self.db.execute('SELECT SUM(debe),SUM(haber),COUNT(*) FROM libro_diario WHERE asiento_id=?',(asiento,)).fetchone()),(100,100,lineas))

    def test_sugerencia_manual_cuadra_y_vincula_obligacion(self):
        asiento=self.sugerencia();self.cuadrado(asiento)
        self.assertEqual(tuple(self.db.execute('SELECT conciliado,cartola_id,asiento_id FROM obligaciones_manuales WHERE id=1').fetchone()),(1,1,asiento))
        self.assertEqual(self.db.execute("SELECT usuario FROM auditoria WHERE accion='CONCILIACIÓN BANCARIA'").fetchone()[0],'finanzas@example.com')

    def test_sugerencia_cliente_aplica_saldo_exacto(self):
        asiento=self.sugerencia(mov=2,tipo='CLIENTE');self.cuadrado(asiento)
        self.assertEqual(self.db.execute('SELECT monto FROM aplicaciones_clientes').fetchone()[0],100)

    def test_sugerencia_proveedor_aplica_saldo_exacto(self):
        self.cuadrado(self.sugerencia(tipo='PROVEEDOR'))
        self.assertEqual(self.db.execute('SELECT monto FROM aplicaciones_proveedores').fetchone()[0],100)

    def test_imputacion_una_cuenta_cuadra_y_audita(self):
        self.cuadrado(self.manual())
        self.assertEqual(self.db.execute("SELECT usuario FROM auditoria WHERE accion='IMPUTACIÓN BANCARIA MANUAL'").fetchone()[0],'finanzas@example.com')

    def test_imputacion_multiple_cuadra_y_audita(self):
        self.cuadrado(self.multiple(),3)
        self.assertEqual(self.db.execute("SELECT usuario FROM auditoria WHERE accion='IMPUTACIÓN BANCARIA MÚLTIPLE'").fetchone()[0],'finanzas@example.com')

    def test_abonos_manuales_invierten_sentido_correctamente(self):
        self.cuadrado(self.manual(mov=2))
        self.assertEqual(self.db.execute("SELECT debe FROM libro_diario WHERE codigo_cuenta='1.1.02'").fetchone()[0],100)

    def test_fallo_auditoria_revierte_las_tres_rutas(self):
        self.db.execute("CREATE TRIGGER fallo BEFORE INSERT ON auditoria BEGIN SELECT RAISE(ABORT,'fallo'); END");self.db.commit()
        for op in (self.sugerencia,self.manual,self.multiple):
            antes=list(self.db.iterdump())
            with self.assertRaises(sqlite3.IntegrityError):op()
            self.assertEqual(list(self.db.iterdump()),antes)

    def test_transaccion_ajena_se_preserva(self):
        self.db.execute("UPDATE bancos SET nombre='Pendiente' WHERE id=1");antes=list(self.db.iterdump())
        for op in (self.sugerencia,self.manual,self.multiple):
            with self.assertRaises(RuntimeError):op()
            self.assertTrue(self.db.in_transaction);self.assertEqual(list(self.db.iterdump()),antes)
        self.db.rollback()

    def test_revocacion_bancaria_bajo_reserva(self):
        original=servicio.sgci_autorizar_operacion
        def autorizar(conn,*args):
            original(conn,*args)
            if conn.in_transaction:raise PermissionError('Revocado')
        for op in (self.sugerencia,self.manual,self.multiple):
            antes=list(self.db.iterdump())
            with patch.dict(vars(servicio),{'sgci_autorizar_operacion':autorizar}):
                with self.assertRaises(PermissionError):op()
            self.assertEqual(list(self.db.iterdump()),antes)

    def test_revocacion_auxiliar_bajo_reserva(self):
        original=servicio.sgci_autorizar_operacion
        for tipo,modulo,mov in [('CLIENTE','cxc',2),('PROVEEDOR','cxp',1)]:
            def autorizar(conn,mod,*args):
                original(conn,mod,*args)
                if conn.in_transaction and mod==modulo:raise PermissionError('Revocado')
            antes=list(self.db.iterdump())
            with patch.dict(vars(servicio),{'sgci_autorizar_operacion':autorizar}):
                with self.assertRaises(PermissionError):self.sugerencia(mov=mov,tipo=tipo)
            self.assertEqual(list(self.db.iterdump()),antes)

    def test_sugerencias_obsoletas_rechazan_saldo_distinto(self):
        self.db.execute('UPDATE ventas SET monto_total=80');self.db.execute('UPDATE compras SET monto_total=80');self.db.execute('UPDATE obligaciones_manuales SET monto=80');self.db.commit()
        for tipo,mov in [('CLIENTE',2),('PROVEEDOR',1),('MANUAL',1)]:
            antes=list(self.db.iterdump())
            with self.assertRaises(ValueError):self.sugerencia(mov=mov,tipo=tipo)
            self.assertEqual(list(self.db.iterdump()),antes)

    def test_sugerencias_rechazan_naturaleza_incorrecta(self):
        for tipo,mov in [('CLIENTE',1),('PROVEEDOR',2),('MANUAL',2)]:
            antes=list(self.db.iterdump())
            with self.assertRaises(ValueError):self.sugerencia(mov=mov,tipo=tipo)
            self.assertEqual(list(self.db.iterdump()),antes)

    def test_periodo_cerrado_bloquea_las_tres_rutas(self):
        self.db.execute("INSERT INTO periodos_contables(periodo,estado) VALUES('2026-11','CERRADO')");self.db.commit()
        for op in (self.sugerencia,self.manual,self.multiple):
            antes=list(self.db.iterdump())
            with self.assertRaises(ValueError):op()
            self.assertEqual(list(self.db.iterdump()),antes)

    def test_movimiento_ambiguo_o_invalido_no_se_contabiliza(self):
        for cargo,abono in [(100,10),(-100,0),(float('inf'),0)]:
            self.db.execute('UPDATE cartola_bancaria SET cargo=?,abono=? WHERE id=1',(cargo,abono));self.db.commit()
            for op in (self.sugerencia,self.manual,self.multiple):
                antes=list(self.db.iterdump())
                with self.assertRaises(ValueError):op()
                self.assertEqual(list(self.db.iterdump()),antes)

    def test_distribucion_inexacta_no_deja_asientos(self):
        antes=list(self.db.iterdump())
        with self.assertRaises(ValueError):servicio.contabilizar_imputacion_multiple_bancaria(self.db,1,[('5.9.01',40),('5.9.02',59)])
        self.assertEqual(list(self.db.iterdump()),antes)

    def test_obligacion_con_cuenta_inexistente_o_banco_se_rechaza(self):
        for codigo in ('NO-EXISTE','1.1.02'):
            self.db.execute('UPDATE obligaciones_manuales SET codigo_cuenta=?',(codigo,));self.db.commit()
            antes=list(self.db.iterdump())
            with self.assertRaises(ValueError):self.sugerencia()
            self.assertEqual(list(self.db.iterdump()),antes)

    def concurrentes(self,op):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta=Path(carpeta)/'conciliar.db'
            with closing(sqlite3.connect(ruta)) as db:self.db.backup(db)
            barrera=threading.Barrier(2)
            def ejecutar(i):
                with closing(sqlite3.connect(ruta,timeout=10)) as db:
                    db.row_factory=sqlite3.Row;barrera.wait(timeout=10)
                    try:return ('ok',op(db,i))
                    except ValueError:return ('rechazado',None)
            with ThreadPoolExecutor(max_workers=2) as pool:r=list(pool.map(ejecutar,range(2)))
            with closing(sqlite3.connect(ruta)) as db:
                c=[db.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in ('libro_diario','auditoria')]
            return r,c

    def test_dos_sesiones_no_duplican_sugerencia_manual(self):
        r,c=self.concurrentes(lambda db,i:self.sugerencia(db))
        self.assertCountEqual([x[0] for x in r],['ok','rechazado']);self.assertEqual(c,[2,1])

    def test_dos_sesiones_no_duplican_una_cuenta(self):
        r,c=self.concurrentes(lambda db,i:self.manual(db))
        self.assertCountEqual([x[0] for x in r],['ok','rechazado']);self.assertEqual(c,[2,1])

    def test_dos_sesiones_no_duplican_varias_cuentas(self):
        r,c=self.concurrentes(lambda db,i:self.multiple(db))
        self.assertCountEqual([x[0] for x in r],['ok','rechazado']);self.assertEqual(c,[3,1])

    def test_movimientos_distintos_no_sobreaplican_factura(self):
        self.db.execute("INSERT INTO cartola_bancaria(id,banco_id,fecha,descripcion,cargo,abono) VALUES(3,1,'2026-11-16','Otro abono',0,100)");self.db.commit()
        r,c=self.concurrentes(lambda db,i:self.sugerencia(db,2+i,'CLIENTE'))
        self.assertCountEqual([x[0] for x in r],['ok','rechazado']);self.assertEqual(c,[2,1])

    def test_movimientos_distintos_no_duplican_obligacion(self):
        self.db.execute("INSERT INTO cartola_bancaria(id,banco_id,fecha,descripcion,cargo,abono) VALUES(3,1,'2026-11-16','Otro cargo',100,0)");self.db.commit()
        r,c=self.concurrentes(lambda db,i:self.sugerencia(db,1 if i==0 else 3))
        self.assertCountEqual([x[0] for x in r],['ok','rechazado']);self.assertEqual(c,[2,1])

    def test_movimientos_validos_distintos_generan_asientos_distintos(self):
        r,c=self.concurrentes(lambda db,i:self.manual(db,i+1))
        self.assertEqual([x[0] for x in r],['ok','ok']);self.assertNotEqual(r[0][1],r[1][1]);self.assertEqual(c,[4,2])


if __name__=='__main__':unittest.main()

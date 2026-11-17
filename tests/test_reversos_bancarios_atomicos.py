import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from modulos import conciliacion_documental as servicio,contabilidad_reportes as banco
from tests.soporte_flujos import preparar


class TestReversosBancariosAtomicos(unittest.TestCase):
    def setUp(self):
        self.db=preparar(self);servicio.sgci_conc_esquema(self.db)
        p=patch.dict(vars(banco),{'sgci_conc_esquema':servicio.sgci_conc_esquema,'money':str,
            '_sgci_exigir_sin_transaccion':servicio._sgci_exigir_sin_transaccion,'_sgci_auditar_auxiliar':servicio._sgci_auditar_auxiliar})
        p.start();self.addCleanup(p.stop)
        p=patch.dict(vars(servicio),{'money':str});p.start();self.addCleanup(p.stop)
        self.db.executescript("""
            INSERT INTO clientes(id,rut,nombre) VALUES(1,'1-9','Cliente prueba');
            INSERT INTO compras(id,proveedor_id,fecha,folio,tipo_doc,monto_total) VALUES(1,1,'2026-11-01','1',33,100);
            INSERT INTO ventas(id,cliente_id,fecha,folio,tipo_doc,monto_total) VALUES(1,1,'2026-11-01','1',33,100);
            INSERT INTO plan_cuentas(codigo,nombre,tipo) VALUES('2.1.99','Anticipo sintético','Pasivo'),('5.9.01','Gasto sintético','Gastos');
            INSERT INTO cartola_bancaria(id,banco_id,fecha,descripcion,cargo,abono) VALUES(1,1,'2026-11-16','Anticipo',0,100),(2,1,'2026-11-16','Pago anterior',100,0),(3,1,'2026-11-16','Imputación',100,0),(4,1,'2026-11-16','Pago factura',100,0);
        """)
        self.asientos={1:banco.contabilizar_cobro_cliente_sin_documento(self.db,1,1,'2.1.99'),
            2:servicio.contabilizar_pago_proveedor_sin_documento(self.db,2,1),
            3:banco.contabilizar_imputacion_manual_bancaria(self.db,3,'5.9.01'),
            4:servicio.contabilizar_pago_proveedor_desde_cartola(self.db,4,1,[1])[0]}

    def revertir(self,mov,db=None):
        db=db or self.db
        if mov==1:return servicio.revertir_abono_cliente_cartola(db,mov)
        if mov in (2,4):return servicio.revertir_pago_proveedor_cartola(db,mov)
        return servicio.corregir_conciliacion_manual(db,mov)

    def test_los_cuatro_reversos_conservan_original_y_cuadran(self):
        for mov in (1,2,3,4):
            with self.subTest(mov=mov):
                original=list(self.db.execute('SELECT * FROM libro_diario WHERE asiento_id=?',(self.asientos[mov],)))
                reverso=self.revertir(mov)
                self.assertNotEqual(reverso,self.asientos[mov])
                self.assertEqual(list(self.db.execute('SELECT * FROM libro_diario WHERE asiento_id=?',(self.asientos[mov],))),original)
                self.assertEqual(tuple(self.db.execute('SELECT SUM(debe),SUM(haber) FROM libro_diario WHERE asiento_id=?',(reverso,)).fetchone()),(100,100))
                saldos=self.db.execute('SELECT codigo_cuenta,SUM(debe-haber) FROM libro_diario WHERE asiento_id IN (?,?) GROUP BY codigo_cuenta',(reverso,self.asientos[mov])).fetchall()
                self.assertTrue(all(abs(float(r[1]))<0.01 for r in saldos))
                self.assertEqual(tuple(self.db.execute('SELECT conciliado,asiento_id FROM cartola_bancaria WHERE id=?',(mov,)).fetchone()),(0,None))
                with self.assertRaises(ValueError):self.revertir(mov)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM pagos_clientes').fetchone()[0],0)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM pagos_proveedores').fetchone()[0],0)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM aplicaciones_proveedores').fetchone()[0],0)

    def test_auditoria_usa_identidad_efectiva(self):
        for mov in (1,2,3):self.revertir(mov)
        for accion in ('REVERSO ANTICIPO CLIENTE','REVERSO PAGO PROVEEDOR','CORRECCIÓN CONCILIACIÓN'):
            self.assertEqual(self.db.execute('SELECT usuario FROM auditoria WHERE accion=?',(accion,)).fetchone()[0],'finanzas@example.com')

    def test_fallo_auditoria_revierte_cuatro_rutas(self):
        self.db.execute("CREATE TRIGGER fallo BEFORE INSERT ON auditoria BEGIN SELECT RAISE(ABORT,'fallo'); END");self.db.commit()
        for mov in (1,2,3,4):
            antes=list(self.db.iterdump())
            with self.assertRaises(sqlite3.IntegrityError):self.revertir(mov)
            self.assertEqual(list(self.db.iterdump()),antes)

    def test_transaccion_ajena_se_preserva(self):
        self.db.execute("UPDATE bancos SET nombre='Pendiente' WHERE id=1");antes=list(self.db.iterdump())
        for mov in (1,2,3,4):
            with self.assertRaises(RuntimeError):self.revertir(mov)
            self.assertTrue(self.db.in_transaction);self.assertEqual(list(self.db.iterdump()),antes)
        self.db.rollback()

    def test_revocacion_bancaria_bajo_reserva(self):
        original=servicio.sgci_autorizar_operacion
        def autorizar(conn,*args):
            original(conn,*args)
            if conn.in_transaction:raise PermissionError('Revocado')
        for mov in (1,2,3,4):
            antes=list(self.db.iterdump())
            with patch.dict(vars(servicio),{'sgci_autorizar_operacion':autorizar}):
                with self.assertRaises(PermissionError):self.revertir(mov)
            self.assertEqual(list(self.db.iterdump()),antes)

    def test_revocacion_auxiliar_bajo_reserva(self):
        original=servicio.sgci_autorizar_operacion
        for mov,modulo in [(1,'cxc'),(2,'cxp'),(4,'cxp')]:
            def autorizar(conn,mod,*args):
                original(conn,mod,*args)
                if conn.in_transaction and mod==modulo:raise PermissionError('Revocado')
            antes=list(self.db.iterdump())
            with patch.dict(vars(servicio),{'sgci_autorizar_operacion':autorizar}):
                with self.assertRaises(PermissionError):self.revertir(mov)
            self.assertEqual(list(self.db.iterdump()),antes)

    def test_anticipo_aplicado_posteriormente_se_bloquea(self):
        pago=self.db.execute('SELECT id FROM pagos_clientes WHERE cartola_id=1').fetchone()[0]
        self.db.execute('INSERT INTO aplicaciones_clientes(pago_id,venta_id,monto) VALUES(?,1,40)',(pago,));self.db.commit()
        antes=list(self.db.iterdump())
        with self.assertRaises(ValueError):self.revertir(1)
        self.assertEqual(list(self.db.iterdump()),antes)

    def test_pago_sin_documento_aplicado_posteriormente_se_bloquea(self):
        lote=self.db.execute('SELECT lote_id FROM libro_diario WHERE asiento_id=?',(self.asientos[2],)).fetchone()[0]
        pago=self.db.execute('SELECT id FROM pagos_proveedores WHERE lote_id=?',(lote,)).fetchone()[0]
        self.db.execute('INSERT INTO aplicaciones_proveedores(pago_id,compra_id,monto) VALUES(?,1,40)',(pago,));self.db.commit()
        antes=list(self.db.iterdump())
        with self.assertRaises(ValueError):self.revertir(2)
        self.assertEqual(list(self.db.iterdump()),antes)

    def test_aplicacion_documental_alterada_se_bloquea(self):
        self.db.execute('UPDATE aplicaciones_proveedores SET monto=90');self.db.commit();antes=list(self.db.iterdump())
        with self.assertRaises(ValueError):self.revertir(4)
        self.assertEqual(list(self.db.iterdump()),antes)

    def test_asientos_con_importe_cambiado_no_se_revierten(self):
        for mov in (1,2,3,4):
            self.db.execute('UPDATE libro_diario SET debe=debe*2,haber=haber*2 WHERE asiento_id=?',(self.asientos[mov],));self.db.commit()
            antes=list(self.db.iterdump())
            with self.assertRaises(ValueError):self.revertir(mov)
            self.assertEqual(list(self.db.iterdump()),antes)

    def test_imputacion_con_origen_ajeno_no_se_revierte(self):
        self.db.execute("UPDATE libro_diario SET origen='AJENO' WHERE asiento_id=?",(self.asientos[3],));self.db.commit()
        antes=list(self.db.iterdump())
        with self.assertRaises(ValueError):self.revertir(3)
        self.assertEqual(list(self.db.iterdump()),antes)

    def test_asiento_compartido_por_cartolas_no_se_revierte(self):
        for mov in (1,2,3,4):
            self.db.execute("INSERT INTO cartola_bancaria(id,banco_id,fecha,descripcion,cargo,abono,asiento_id) VALUES(9,1,'2026-11-16','Compartido',1,0,?)",(self.asientos[mov],));self.db.commit()
            antes=list(self.db.iterdump())
            with self.assertRaises(ValueError):self.revertir(mov)
            self.assertEqual(list(self.db.iterdump()),antes)
            self.db.execute('DELETE FROM cartola_bancaria WHERE id=9');self.db.commit()

    def test_periodo_cerrado_bloquea_reversos(self):
        self.db.execute("INSERT INTO periodos_contables(periodo,estado) VALUES('2026-11','CERRADO')");self.db.commit()
        for mov in (1,2,3,4):
            antes=list(self.db.iterdump())
            with self.assertRaises(ValueError):self.revertir(mov)
            self.assertEqual(list(self.db.iterdump()),antes)

    def concurrentes(self,op):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta=Path(carpeta)/'reversos.db'
            with closing(sqlite3.connect(ruta)) as db:self.db.backup(db)
            barrera=threading.Barrier(2)
            def ejecutar(i):
                with closing(sqlite3.connect(ruta,timeout=10)) as db:
                    db.row_factory=sqlite3.Row;barrera.wait(timeout=10)
                    try:return ('ok',op(db,i))
                    except ValueError:return ('rechazado',None)
            with ThreadPoolExecutor(max_workers=2) as pool:r=list(pool.map(ejecutar,range(2)))
            with closing(sqlite3.connect(ruta)) as db:
                conteos=[db.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in ('libro_diario','auditoria')]
            return r,conteos

    def test_dos_sesiones_no_duplican_reverso_anticipo(self):
        r,c=self.concurrentes(lambda db,i:self.revertir(1,db))
        self.assertCountEqual([x[0] for x in r],['ok','rechazado']);self.assertEqual(c,[10,5])

    def test_dos_sesiones_no_duplican_reverso_proveedor(self):
        r,c=self.concurrentes(lambda db,i:self.revertir(2,db))
        self.assertCountEqual([x[0] for x in r],['ok','rechazado']);self.assertEqual(c,[10,5])

    def test_dos_sesiones_no_duplican_correccion_manual(self):
        r,c=self.concurrentes(lambda db,i:self.revertir(3,db))
        self.assertCountEqual([x[0] for x in r],['ok','rechazado']);self.assertEqual(c,[10,5])

    def test_dos_reversos_validos_generan_asientos_distintos(self):
        r,c=self.concurrentes(lambda db,i:self.revertir(i+1,db))
        self.assertEqual([x[0] for x in r],['ok','ok']);self.assertNotEqual(r[0][1],r[1][1]);self.assertEqual(c,[12,6])


if __name__=='__main__':unittest.main()

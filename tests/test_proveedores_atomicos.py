import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from modulos import conciliacion_documental as servicio
from tests.soporte_flujos import preparar


class TestProveedoresAtomicos(unittest.TestCase):
    def setUp(self):
        self.db=preparar(self);servicio.sgci_conc_esquema(self.db)
        servicio.sgci_crear_devoluciones_proveedor(self.db)
        p=patch.dict(vars(servicio),{'money':str});p.start();self.addCleanup(p.stop)
        self.db.executescript("""
            INSERT INTO compras(id,proveedor_id,fecha,folio,tipo_doc,monto_total) VALUES(1,1,'2026-11-01','1',33,100),(2,1,'2026-11-01','NC',61,-200),(3,2,'2026-11-01','3',33,50);
            INSERT INTO cartola_bancaria(id,banco_id,fecha,descripcion,cargo,abono) VALUES(1,1,'2026-11-16','Pago prueba',100,0),(2,1,'2026-11-16','Devolución prueba',0,100);
            INSERT INTO plan_cuentas(codigo,nombre,tipo) VALUES('1.1.99','Diferencia sintética','Activo');
        """)

    def pagar(self,db=None,mov=1,docs=None):
        return servicio.contabilizar_pago_proveedor_desde_cartola(db or self.db,mov,1,[1] if docs is None else docs)

    def sin_documento(self,db=None,mov=1):
        return servicio.contabilizar_pago_proveedor_sin_documento(db or self.db,mov,1)

    def devolver(self,db=None,mov=2):
        return servicio.sgci_contabilizar_devolucion_proveedor(db or self.db,mov,1,2,1)

    def cuadrado(self,asiento,monto):
        self.assertEqual(tuple(self.db.execute('SELECT SUM(debe),SUM(haber) FROM libro_diario WHERE asiento_id=?',(asiento,)).fetchone()),(monto,monto))

    def test_pago_cuadra_y_aplica_con_auditoria_real(self):
        asiento,aplicaciones,diferencia=self.pagar()
        self.cuadrado(asiento,100);self.assertEqual((aplicaciones,diferencia),([(1,100)],0))
        self.assertEqual(self.db.execute("SELECT usuario FROM auditoria WHERE accion='PAGO PROVEEDOR DESDE CARTOLA'").fetchone()[0],'finanzas@example.com')

    def test_pago_parcial_conserva_pendiente(self):
        self.db.execute('UPDATE cartola_bancaria SET cargo=40 WHERE id=1');self.db.commit()
        asiento,aplicaciones,_=self.pagar();self.cuadrado(asiento,40)
        self.assertEqual(aplicaciones,[(1,40)])
        self.assertEqual(servicio.documentos_pendientes_proveedor(self.db,1).pendiente.tolist(),[60])

    def test_diferencia_separa_auxiliar_y_otra_cuenta(self):
        self.db.execute('UPDATE cartola_bancaria SET cargo=120 WHERE id=1');self.db.commit()
        asiento,aplicaciones,diferencia=servicio.contabilizar_pago_proveedor_desde_cartola(self.db,1,1,[1],cuenta_diferencia='1.1.99')
        self.cuadrado(asiento,120);self.assertEqual((aplicaciones,diferencia),([(1,100)],20))
        self.assertEqual(self.db.execute('SELECT monto FROM pagos_proveedores').fetchone()[0],100)

    def test_pago_sin_documento_no_aplica_facturas(self):
        self.cuadrado(self.sin_documento(),100)
        self.assertEqual(self.db.execute('SELECT monto FROM pagos_proveedores').fetchone()[0],100)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM aplicaciones_proveedores').fetchone()[0],0)
        self.assertEqual(self.db.execute("SELECT usuario FROM auditoria WHERE accion='PAGO PROVEEDOR SIN DOCUMENTO'").fetchone()[0],'finanzas@example.com')

    def test_devolucion_no_duplica_compras_ni_iva(self):
        compras=list(self.db.execute('SELECT * FROM compras'))
        self.cuadrado(self.devolver(),100)
        self.assertEqual(list(self.db.execute('SELECT * FROM compras')),compras)
        self.assertEqual(self.db.execute('SELECT monto FROM sgci_devoluciones_proveedor').fetchone()[0],100)
        self.assertEqual(self.db.execute("SELECT usuario FROM auditoria WHERE accion='DEVOLUCION PROVEEDOR'").fetchone()[0],'finanzas@example.com')

    def test_seleccion_con_documento_ajeno_se_rechaza_completa(self):
        antes=list(self.db.iterdump())
        with self.assertRaises(ValueError):self.pagar(docs=[1,3])
        self.assertEqual(list(self.db.iterdump()),antes)

    def test_devolucion_documentos_ajenos_no_cambia_datos(self):
        antes=list(self.db.iterdump())
        with self.assertRaises(ValueError):servicio.sgci_contabilizar_devolucion_proveedor(self.db,2,1,2,3)
        self.assertEqual(list(self.db.iterdump()),antes)

    def test_fallo_auditoria_revierte_las_tres_rutas(self):
        self.db.execute("CREATE TRIGGER fallo BEFORE INSERT ON auditoria BEGIN SELECT RAISE(ABORT,'fallo'); END");self.db.commit()
        for op in (self.pagar,self.sin_documento,self.devolver):
            antes=list(self.db.iterdump())
            with self.assertRaises(sqlite3.IntegrityError):op()
            self.assertEqual(list(self.db.iterdump()),antes)

    def test_transaccion_ajena_se_preserva_en_las_tres_rutas(self):
        self.db.execute("UPDATE proveedores SET nombre='Pendiente' WHERE id=1");antes=list(self.db.iterdump())
        for op in (self.pagar,self.sin_documento,self.devolver):
            with self.assertRaises(RuntimeError):op()
            self.assertTrue(self.db.in_transaction);self.assertEqual(list(self.db.iterdump()),antes)
        self.db.rollback()

    def test_revalida_ambos_permisos_en_las_tres_rutas(self):
        original=servicio.sgci_autorizar_operacion
        for modulo in ('banco','cxp'):
            def autorizar(conn,mod,*args):
                original(conn,mod,*args)
                if conn.in_transaction and mod==modulo:raise PermissionError('Revocado')
            for op in (self.pagar,self.sin_documento,self.devolver):
                antes=list(self.db.iterdump())
                with patch.dict(vars(servicio),{'sgci_autorizar_operacion':autorizar}):
                    with self.assertRaises(PermissionError):op()
                self.assertEqual(list(self.db.iterdump()),antes)

    def test_periodo_cerrado_bloquea_las_tres_rutas(self):
        self.db.execute("INSERT INTO periodos_contables(periodo,estado) VALUES('2026-11','CERRADO')");self.db.commit()
        for op in (self.pagar,self.sin_documento,self.devolver):
            antes=list(self.db.iterdump())
            with self.assertRaises(ValueError):op()
            self.assertEqual(list(self.db.iterdump()),antes)

    def test_movimiento_ambiguo_bloquea_las_tres_rutas(self):
        self.db.execute('UPDATE cartola_bancaria SET abono=10 WHERE id=1')
        self.db.execute('UPDATE cartola_bancaria SET cargo=10 WHERE id=2');self.db.commit()
        for op in (self.pagar,self.sin_documento,self.devolver):
            antes=list(self.db.iterdump())
            with self.assertRaises(ValueError):op()
            self.assertEqual(list(self.db.iterdump()),antes)

    def test_inicializacion_no_confirma_transaccion_ajena(self):
        self.db.execute("UPDATE proveedores SET nombre='Pendiente' WHERE id=1")
        servicio.sgci_crear_devoluciones_proveedor(self.db)
        self.assertTrue(self.db.in_transaction);self.db.rollback()
        self.assertEqual(self.db.execute('SELECT nombre FROM proveedores WHERE id=1').fetchone()[0],'Proveedor de prueba')

    def concurrentes(self,op):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta=Path(carpeta)/'proveedores.db'
            with closing(sqlite3.connect(ruta)) as db:self.db.backup(db)
            barrera=threading.Barrier(2)
            def ejecutar(i):
                with closing(sqlite3.connect(ruta,timeout=10)) as db:
                    db.row_factory=sqlite3.Row;barrera.wait(timeout=10)
                    try:return ('ok',op(db,i))
                    except ValueError:return ('rechazado',None)
            with ThreadPoolExecutor(max_workers=2) as pool:resultados=list(pool.map(ejecutar,range(2)))
            with closing(sqlite3.connect(ruta)) as db:
                conteos=[db.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in ('pagos_proveedores','sgci_devoluciones_proveedor','libro_diario','auditoria')]
                aplicado=db.execute('SELECT COALESCE(SUM(monto),0) FROM aplicaciones_proveedores').fetchone()[0]
            return resultados,conteos,aplicado

    def test_dos_sesiones_no_duplican_pago(self):
        r,c,a=self.concurrentes(lambda db,i:self.pagar(db))
        self.assertCountEqual([x[0] for x in r],['ok','rechazado']);self.assertEqual((c,a),([1,0,2,1],100))

    def test_dos_sesiones_no_duplican_pago_sin_documento(self):
        r,c,a=self.concurrentes(lambda db,i:self.sin_documento(db))
        self.assertCountEqual([x[0] for x in r],['ok','rechazado']);self.assertEqual((c,a),([1,0,2,1],0))

    def test_dos_sesiones_no_duplican_devolucion(self):
        r,c,a=self.concurrentes(lambda db,i:self.devolver(db))
        self.assertCountEqual([x[0] for x in r],['ok','rechazado']);self.assertEqual((c,a),([0,1,2,1],0))

    def test_dos_pagos_no_sobreaplican_factura(self):
        self.db.execute("INSERT INTO cartola_bancaria(id,banco_id,fecha,descripcion,cargo,abono) VALUES(3,1,'2026-11-16','Otro pago',100,0)");self.db.commit()
        r,c,a=self.concurrentes(lambda db,i:self.pagar(db,1 if i==0 else 3))
        self.assertCountEqual([x[0] for x in r],['ok','rechazado']);self.assertEqual((c,a),([1,0,2,1],100))

    def test_dos_devoluciones_no_agotan_dos_veces_diferencia(self):
        self.db.execute('UPDATE cartola_bancaria SET abono=70 WHERE id=2')
        self.db.execute("INSERT INTO cartola_bancaria(id,banco_id,fecha,descripcion,cargo,abono) VALUES(3,1,'2026-11-16','Otra devolución',0,70)");self.db.commit()
        r,c,a=self.concurrentes(lambda db,i:self.devolver(db,2+i))
        self.assertCountEqual([x[0] for x in r],['ok','rechazado']);self.assertEqual(c,[0,1,2,1])

    def test_pagos_distintos_generan_asientos_distintos(self):
        self.db.execute("INSERT INTO cartola_bancaria(id,banco_id,fecha,descripcion,cargo,abono) VALUES(3,1,'2026-11-16','Otro pago',100,0)");self.db.commit()
        r,c,a=self.concurrentes(lambda db,i:self.sin_documento(db,1 if i==0 else 3))
        self.assertEqual([x[0] for x in r],['ok','ok']);self.assertNotEqual(r[0][1],r[1][1]);self.assertEqual(c,[2,0,4,2])


if __name__=='__main__':unittest.main()

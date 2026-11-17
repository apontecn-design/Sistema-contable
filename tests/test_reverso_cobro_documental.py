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


class TestReversoCobroDocumental(unittest.TestCase):
    def setUp(self):
        self.db=preparar(self);servicio.sgci_conc_esquema(self.db)
        banco.sgci_saldos_apertura_clientes(self.db);servicio.sgci_cobros_traza_esquema(self.db)
        p=patch.dict(vars(banco),{'sgci_conc_esquema':servicio.sgci_conc_esquema,'money':str,
            '_sgci_exigir_sin_transaccion':servicio._sgci_exigir_sin_transaccion,'_sgci_auditar_auxiliar':servicio._sgci_auditar_auxiliar})
        p.start();self.addCleanup(p.stop)
        self.db.executescript("""
            INSERT INTO clientes(id,rut,nombre) VALUES(1,'1-9','Cliente prueba');
            INSERT INTO ventas(id,cliente_id,fecha,folio,tipo_doc,monto_total) VALUES(1,1,'2026-11-01','1',33,60),(2,1,'2026-11-01','2',33,100),(3,1,'2026-11-01','3',33,100);
            INSERT INTO sgci_apertura_clientes(cliente_id,monto) VALUES(1,100);
            INSERT INTO cartola_bancaria(id,banco_id,fecha,descripcion,cargo,abono) VALUES(1,1,'2026-11-16','Mixto',0,100),(2,1,'2026-11-16','Factura',0,100),(3,1,'2026-11-16','Sugerencia',0,100);
        """)
        self.asientos={1:banco.sgci_cobro_mixto(self.db,1,1,[1],40),
            2:banco.contabilizar_cobro_cliente_desde_cartola(self.db,2,1,[2])[0],
            3:banco.contabilizar_conciliacion_bancaria(self.db,3,'CLIENTE',3)}

    def revertir(self,mov=1,db=None):return servicio.revertir_cobro_documental_cliente(db or self.db,mov)

    def pago(self,mov):return self.db.execute('SELECT pago_id FROM sgci_cobros_traza WHERE movimiento_id=? AND revertido=0',(mov,)).fetchone()[0]

    def test_los_tres_ciclos_conservan_originales_y_reabren_saldos(self):
        for mov in (1,2,3):
            original=list(self.db.execute('SELECT * FROM libro_diario WHERE asiento_id=?',(self.asientos[mov],)))
            reverso=self.revertir(mov)
            self.assertNotEqual(reverso,self.asientos[mov])
            self.assertEqual(list(self.db.execute('SELECT * FROM libro_diario WHERE asiento_id=?',(self.asientos[mov],))),original)
            self.assertEqual(tuple(self.db.execute('SELECT SUM(debe),SUM(haber) FROM libro_diario WHERE asiento_id=?',(reverso,)).fetchone()),(100,100))
            self.assertEqual(tuple(self.db.execute('SELECT conciliado,asiento_id FROM cartola_bancaria WHERE id=?',(mov,)).fetchone()),(0,None))
            with self.assertRaises(ValueError):self.revertir(mov)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM pagos_clientes').fetchone()[0],0)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM aplicaciones_clientes').fetchone()[0],0)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM sgci_aplicaciones_apertura_clientes').fetchone()[0],0)
        self.assertEqual(self.db.execute('SELECT SUM(revertido) FROM sgci_cobros_traza').fetchone()[0],3)
        self.assertEqual(banco.sgci_saldo_apertura_disponible(self.db,1),100)

    def test_cobro_puede_volver_a_contabilizarse_sin_perder_traza_anterior(self):
        self.revertir(1)
        nuevo=banco.sgci_cobro_mixto(self.db,1,1,[1],40)
        self.assertNotEqual(nuevo,self.asientos[1])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM sgci_cobros_traza WHERE movimiento_id=1').fetchone()[0],2)
        self.revertir(1)
        self.assertEqual(self.db.execute('SELECT SUM(revertido) FROM sgci_cobros_traza WHERE movimiento_id=1').fetchone()[0],2)

    def test_cobro_parcial_reabre_saldo_sin_borrar_factura(self):
        self.revertir(2)
        self.db.execute('UPDATE cartola_bancaria SET abono=40 WHERE id=2');self.db.commit()
        banco.contabilizar_cobro_cliente_desde_cartola(self.db,2,1,[2])
        self.revertir(2)
        self.assertEqual(self.db.execute('SELECT monto_total FROM ventas WHERE id=2').fetchone()[0],100)
        self.assertEqual(banco.documentos_pendientes_cliente(self.db,1).set_index('id').loc[2,'pendiente'],100)

    def test_cobro_con_sobrante_revierte_tambien_la_tercera_linea(self):
        self.revertir(2)
        self.db.execute("INSERT INTO plan_cuentas(codigo,nombre,tipo) VALUES('2.1.99','Sobrante sintético','Pasivo')")
        self.db.execute('UPDATE cartola_bancaria SET abono=120 WHERE id=2');self.db.commit()
        original=banco.contabilizar_cobro_cliente_desde_cartola(self.db,2,1,[2],cuenta_diferencia='2.1.99')[0]
        reverso=self.revertir(2)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM libro_diario WHERE asiento_id=?',(reverso,)).fetchone()[0],3)
        self.assertTrue(all(abs(float(r[0]))<0.01 for r in self.db.execute('SELECT SUM(debe-haber) FROM libro_diario WHERE asiento_id IN (?,?) GROUP BY codigo_cuenta',(original,reverso))))

    def test_cobro_solo_apertura_conserva_otras_aplicaciones(self):
        self.db.execute("INSERT INTO cartola_bancaria(id,banco_id,fecha,descripcion,cargo,abono) VALUES(4,1,'2026-11-16','Solo apertura',0,60)");self.db.commit()
        banco.sgci_cobro_mixto(self.db,4,1,[],60)
        self.revertir(4)
        self.assertEqual(banco.sgci_saldo_apertura_disponible(self.db,1),60)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM sgci_aplicaciones_apertura_clientes').fetchone()[0],1)

    def test_aplicacion_modificada_se_bloquea(self):
        self.db.execute('UPDATE aplicaciones_clientes SET monto=monto-1');self.db.commit()
        for mov in (1,2,3):
            antes=list(self.db.iterdump())
            with self.assertRaises(ValueError):self.revertir(mov)
            self.assertEqual(list(self.db.iterdump()),antes)

    def test_apertura_modificada_se_bloquea(self):
        self.db.execute('UPDATE sgci_aplicaciones_apertura_clientes SET monto=39');self.db.commit();antes=list(self.db.iterdump())
        with self.assertRaises(ValueError):self.revertir()
        self.assertEqual(list(self.db.iterdump()),antes)

    def test_documento_modificado_se_bloquea(self):
        self.db.execute('UPDATE ventas SET monto_total=monto_total+1');self.db.commit()
        for mov in (1,2,3):
            antes=list(self.db.iterdump())
            with self.assertRaises(ValueError):self.revertir(mov)
            self.assertEqual(list(self.db.iterdump()),antes)

    def test_auxiliar_modificado_se_bloquea(self):
        self.db.execute('UPDATE pagos_clientes SET monto=monto+1');self.db.commit()
        for mov in (1,2,3):
            antes=list(self.db.iterdump())
            with self.assertRaises(ValueError):self.revertir(mov)
            self.assertEqual(list(self.db.iterdump()),antes)

    def test_asiento_modificado_se_bloquea(self):
        self.db.execute("UPDATE libro_diario SET glosa='Cambio posterior'");self.db.commit()
        for mov in (1,2,3):
            antes=list(self.db.iterdump())
            with self.assertRaises(ValueError):self.revertir(mov)
            self.assertEqual(list(self.db.iterdump()),antes)

    def test_historico_sin_traza_no_se_adopta_automaticamente(self):
        self.db.execute('DELETE FROM sgci_cobros_traza');self.db.commit();antes=list(self.db.iterdump())
        with self.assertRaisesRegex(ValueError,'histórico'):self.revertir()
        self.assertEqual(list(self.db.iterdump()),antes)

    def test_lista_exige_ambos_permisos_de_lectura(self):
        self.assertEqual(set(servicio.cobros_documentales_reversibles(self.db,1).id),{1,2,3})
        for mod,sub in [('banco','Conciliación bancaria'),('cxc','Pagos de clientes')]:
            self.db.execute('INSERT INTO sgci_usuario_permisos_detalle VALUES(?,?,?,?,0)',('finanzas@example.com',mod,sub,'ver'));self.db.commit()
            with self.assertRaises(PermissionError):servicio.cobros_documentales_reversibles(self.db,1)
            self.db.execute('DELETE FROM sgci_usuario_permisos_detalle');self.db.commit()

    def test_transaccion_ajena_se_preserva(self):
        self.db.execute("UPDATE clientes SET nombre='Pendiente'");antes=list(self.db.iterdump())
        with self.assertRaises(RuntimeError):self.revertir()
        self.assertTrue(self.db.in_transaction);self.assertEqual(list(self.db.iterdump()),antes);self.db.rollback()

    def test_revocacion_bajo_reserva(self):
        original=servicio.sgci_autorizar_operacion
        for modulo in ('banco','cxc'):
            def autorizar(conn,mod,*args):
                original(conn,mod,*args)
                if conn.in_transaction and mod==modulo:raise PermissionError('Revocado')
            antes=list(self.db.iterdump())
            with patch.dict(vars(servicio),{'sgci_autorizar_operacion':autorizar}):
                with self.assertRaises(PermissionError):self.revertir()
            self.assertEqual(list(self.db.iterdump()),antes)

    def test_periodo_cerrado_bloquea(self):
        self.db.execute("INSERT INTO periodos_contables(periodo,estado) VALUES('2026-11','CERRADO')");self.db.commit();antes=list(self.db.iterdump())
        with self.assertRaises(ValueError):self.revertir()
        self.assertEqual(list(self.db.iterdump()),antes)

    def test_fallo_auditoria_revierte_todas_las_tablas(self):
        self.db.execute("CREATE TRIGGER fallo BEFORE INSERT ON auditoria BEGIN SELECT RAISE(ABORT,'fallo'); END");self.db.commit();antes=list(self.db.iterdump())
        with self.assertRaises(sqlite3.IntegrityError):self.revertir()
        self.assertEqual(list(self.db.iterdump()),antes)

    def test_no_retira_aplicaciones_de_otro_pago(self):
        pago_ajeno=self.pago(2)
        aplicaciones=list(self.db.execute('SELECT * FROM aplicaciones_clientes WHERE pago_id=?',(pago_ajeno,)))
        self.revertir(1)
        self.assertEqual(list(self.db.execute('SELECT * FROM aplicaciones_clientes WHERE pago_id=?',(pago_ajeno,))),aplicaciones)

    def test_fallo_traza_impide_confirmar_cobro(self):
        self.revertir(1)
        self.db.execute("CREATE TRIGGER fallo BEFORE INSERT ON sgci_cobros_traza BEGIN SELECT RAISE(ABORT,'fallo'); END");self.db.commit();antes=list(self.db.iterdump())
        with self.assertRaises(sqlite3.IntegrityError):banco.sgci_cobro_mixto(self.db,1,1,[1],40)
        self.assertEqual(list(self.db.iterdump()),antes)

    def concurrentes(self,op):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta=Path(carpeta)/'documental.db'
            with closing(sqlite3.connect(ruta)) as db:self.db.backup(db)
            barrera=threading.Barrier(2)
            def ejecutar(i):
                with closing(sqlite3.connect(ruta,timeout=10)) as db:
                    db.row_factory=sqlite3.Row;barrera.wait(timeout=10)
                    try:return ('ok',op(db,i))
                    except ValueError:return ('rechazado',None)
            with ThreadPoolExecutor(max_workers=2) as pool:r=list(pool.map(ejecutar,range(2)))
            with closing(sqlite3.connect(ruta)) as db:c=[db.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in ('libro_diario','pagos_clientes')]
            return r,c

    def test_dos_sesiones_no_duplican_reverso(self):
        r,c=self.concurrentes(lambda db,i:self.revertir(1,db))
        self.assertCountEqual([x[0] for x in r],['ok','rechazado']);self.assertEqual(c,[8,2])

    def test_reversos_distintos_generan_asientos_distintos(self):
        r,c=self.concurrentes(lambda db,i:self.revertir(i+1,db))
        self.assertEqual([x[0] for x in r],['ok','ok']);self.assertNotEqual(r[0][1],r[1][1]);self.assertEqual(c,[10,1])


if __name__=='__main__':unittest.main()

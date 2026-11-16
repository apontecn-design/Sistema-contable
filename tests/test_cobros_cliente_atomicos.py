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


class TestCobrosClienteAtomicos(unittest.TestCase):
    def setUp(self):
        self.db=preparar(self);auxiliar.sgci_conc_esquema(self.db)
        p=patch.dict(vars(servicio),{'sgci_conc_esquema':auxiliar.sgci_conc_esquema,'money':str,
            '_sgci_exigir_sin_transaccion':auxiliar._sgci_exigir_sin_transaccion,'_sgci_auditar_auxiliar':auxiliar._sgci_auditar_auxiliar})
        p.start();self.addCleanup(p.stop)
        self.db.executescript("""
            INSERT INTO clientes(id,rut,nombre) VALUES(1,'1-9','Cliente prueba'),(2,'2-7','Otro cliente');
            INSERT INTO ventas(id,cliente_id,fecha,folio,tipo_doc,monto_total) VALUES(1,1,'2026-11-01','1',33,100),(2,2,'2026-11-01','2',33,50);
            INSERT INTO cartola_bancaria(id,banco_id,fecha,descripcion,cargo,abono) VALUES(1,1,'2026-11-16','Cobro prueba',0,100);
            INSERT INTO plan_cuentas(codigo,nombre,tipo) VALUES('2.1.99','Anticipos sintéticos','Pasivo');
        """)

    def cobrar(self,db=None,mov=1,docs=None):
        return servicio.contabilizar_cobro_cliente_desde_cartola(db or self.db,mov,1,[1] if docs is None else docs)

    def anticipo(self,db=None,mov=1,cuenta='2.1.99'):
        return servicio.contabilizar_cobro_cliente_sin_documento(db or self.db,mov,1,cuenta)

    def test_cobro_cuadra_y_audita_identidad_real(self):
        asiento,aplicaciones,diferencia=self.cobrar()
        self.assertEqual(aplicaciones,[(1,100)]);self.assertEqual(diferencia,0)
        self.assertEqual(tuple(self.db.execute('SELECT SUM(debe),SUM(haber) FROM libro_diario WHERE asiento_id=?',(asiento,)).fetchone()),(100,100))
        self.assertEqual(self.db.execute("SELECT usuario FROM auditoria WHERE accion='COBRO CLIENTE DESDE CARTOLA'").fetchone()[0],'finanzas@example.com')

    def test_anticipo_conserva_efectivo_sin_aplicar_a_facturas(self):
        asiento=self.anticipo()
        self.assertEqual(tuple(self.db.execute('SELECT monto,monto_recibido,cuenta_anticipo,cartola_id FROM pagos_clientes').fetchone()),(0,100,'2.1.99',1))
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM aplicaciones_clientes').fetchone()[0],0)
        self.assertEqual(tuple(self.db.execute('SELECT SUM(debe),SUM(haber) FROM libro_diario WHERE asiento_id=?',(asiento,)).fetchone()),(100,100))
        self.assertEqual(self.db.execute("SELECT usuario FROM auditoria WHERE accion='ANTICIPO CLIENTE DESDE CARTOLA'").fetchone()[0],'finanzas@example.com')

    def test_cobro_parcial_conserva_saldo_pendiente(self):
        self.db.execute('UPDATE cartola_bancaria SET abono=40 WHERE id=1');self.db.commit()
        _,aplicaciones,_=self.cobrar()
        self.assertEqual(aplicaciones,[(1,40)])
        self.assertEqual(servicio.documentos_pendientes_cliente(self.db,1).pendiente.tolist(),[60])

    def test_sobrante_separa_facturas_y_otra_cuenta(self):
        self.db.execute('UPDATE cartola_bancaria SET abono=120 WHERE id=1');self.db.commit()
        asiento,aplicaciones,diferencia=servicio.contabilizar_cobro_cliente_desde_cartola(self.db,1,1,[1],cuenta_diferencia='2.1.99')
        self.assertEqual((aplicaciones,diferencia),([(1,100)],20))
        self.assertEqual(tuple(self.db.execute('SELECT SUM(debe),SUM(haber),COUNT(*) FROM libro_diario WHERE asiento_id=?',(asiento,)).fetchone()),(120,120,3))

    def test_factura_ajena_mezclada_no_se_ignora(self):
        antes=list(self.db.iterdump())
        with self.assertRaises(ValueError):self.cobrar(docs=[1,2])
        self.assertEqual(list(self.db.iterdump()),antes)

    def test_anticipo_rechaza_cuenta_inexistente_o_banco(self):
        for cuenta in ('INEXISTENTE','1.1.02'):
            antes=list(self.db.iterdump())
            with self.assertRaises(ValueError):self.anticipo(cuenta=cuenta)
            self.assertEqual(list(self.db.iterdump()),antes)

    def test_fallo_auditoria_revierte_ambas_rutas(self):
        self.db.execute("CREATE TRIGGER fallo BEFORE INSERT ON auditoria BEGIN SELECT RAISE(ABORT,'fallo'); END")
        self.db.commit()
        for operacion in (self.cobrar,self.anticipo):
            antes=list(self.db.iterdump())
            with self.assertRaises(sqlite3.IntegrityError):operacion()
            self.assertEqual(list(self.db.iterdump()),antes)

    def test_ambas_rutas_preservan_transaccion_ajena(self):
        self.db.execute("UPDATE clientes SET nombre='Pendiente' WHERE id=1")
        antes=list(self.db.iterdump())
        for operacion in (self.cobrar,self.anticipo):
            with self.assertRaises(RuntimeError):operacion()
            self.assertTrue(self.db.in_transaction);self.assertEqual(list(self.db.iterdump()),antes)
        self.db.rollback()

    def test_revocacion_dentro_de_reserva_bloquea_ambas_rutas(self):
        original=servicio.sgci_autorizar_operacion
        for modulo in ('banco','cxc'):
            def autorizar(conn,mod,*args):
                original(conn,mod,*args)
                if conn.in_transaction and mod==modulo:raise PermissionError('Revocado')
            for operacion in (self.cobrar,self.anticipo):
                antes=list(self.db.iterdump())
                with patch.dict(vars(servicio),{'sgci_autorizar_operacion':autorizar}):
                    with self.assertRaises(PermissionError):operacion()
                self.assertEqual(list(self.db.iterdump()),antes)

    def test_periodo_cerrado_bloquea_ambas_rutas(self):
        self.db.execute("INSERT INTO periodos_contables(periodo,estado) VALUES('2026-11','CERRADO')");self.db.commit()
        for operacion in (self.cobrar,self.anticipo):
            antes=list(self.db.iterdump())
            with self.assertRaises(ValueError):operacion()
            self.assertEqual(list(self.db.iterdump()),antes)

    def test_movimiento_con_cargo_y_abono_bloquea_ambas_rutas(self):
        self.db.execute('UPDATE cartola_bancaria SET cargo=10 WHERE id=1');self.db.commit()
        for operacion in (self.cobrar,self.anticipo):
            antes=list(self.db.iterdump())
            with self.assertRaises(ValueError):operacion()
            self.assertEqual(list(self.db.iterdump()),antes)

    def concurrentes(self,operacion):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta=Path(carpeta)/'cobros.db'
            with closing(sqlite3.connect(ruta)) as db:self.db.backup(db)
            barrera=threading.Barrier(2)
            def ejecutar(i):
                with closing(sqlite3.connect(ruta,timeout=10)) as db:
                    db.row_factory=sqlite3.Row;barrera.wait(timeout=10)
                    try:return ('ok',operacion(db,i))
                    except ValueError:return ('rechazado',None)
            with ThreadPoolExecutor(max_workers=2) as pool:resultados=list(pool.map(ejecutar,range(2)))
            with closing(sqlite3.connect(ruta)) as db:
                conteos=[db.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in ('pagos_clientes','libro_diario','auditoria')]
                aplicado=db.execute('SELECT COALESCE(SUM(monto),0) FROM aplicaciones_clientes').fetchone()[0]
            return resultados,conteos,aplicado

    def test_dos_sesiones_no_duplican_cobro(self):
        resultados,conteos,aplicado=self.concurrentes(lambda db,i:self.cobrar(db))
        self.assertCountEqual([x[0] for x in resultados],['ok','rechazado'])
        self.assertEqual(conteos,[1,2,1]);self.assertEqual(aplicado,100)

    def test_dos_sesiones_no_duplican_anticipo(self):
        resultados,conteos,aplicado=self.concurrentes(lambda db,i:self.anticipo(db))
        self.assertCountEqual([x[0] for x in resultados],['ok','rechazado'])
        self.assertEqual(conteos,[1,2,1]);self.assertEqual(aplicado,0)

    def test_dos_cobros_no_sobreaplican_misma_factura(self):
        self.db.execute("INSERT INTO cartola_bancaria(id,banco_id,fecha,descripcion,cargo,abono) VALUES(2,1,'2026-11-16','Otro cobro',0,100)");self.db.commit()
        resultados,conteos,aplicado=self.concurrentes(lambda db,i:self.cobrar(db,i+1))
        self.assertCountEqual([x[0] for x in resultados],['ok','rechazado'])
        self.assertEqual(conteos,[1,2,1]);self.assertEqual(aplicado,100)

    def test_anticipos_distintos_generan_asientos_distintos(self):
        self.db.execute("INSERT INTO cartola_bancaria(id,banco_id,fecha,descripcion,cargo,abono) VALUES(2,1,'2026-11-16','Otro anticipo',0,100)");self.db.commit()
        resultados,conteos,aplicado=self.concurrentes(lambda db,i:self.anticipo(db,i+1))
        self.assertEqual([x[0] for x in resultados],['ok','ok'])
        self.assertNotEqual(resultados[0][1],resultados[1][1]);self.assertEqual(conteos,[2,4,2]);self.assertEqual(aplicado,0)


if __name__=='__main__':unittest.main()

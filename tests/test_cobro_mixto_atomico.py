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


class TestCobroMixtoAtomico(unittest.TestCase):
    def setUp(self):
        self.db=preparar(self)
        auxiliar.sgci_conc_esquema(self.db)
        servicio.sgci_saldos_apertura_clientes(self.db)
        p=patch.dict(vars(servicio),{'sgci_conc_esquema':auxiliar.sgci_conc_esquema,'money':lambda x:str(x),
            '_sgci_exigir_sin_transaccion':auxiliar._sgci_exigir_sin_transaccion,'_sgci_auditar_auxiliar':auxiliar._sgci_auditar_auxiliar})
        p.start();self.addCleanup(p.stop)
        self.db.executescript("""
            INSERT INTO clientes(id,rut,nombre) VALUES(1,'1-9','Cliente prueba'),(2,'2-7','Otro cliente');
            INSERT INTO ventas(id,cliente_id,fecha,folio,tipo_doc,monto_total) VALUES(1,1,'2026-11-01','1',33,60),(2,2,'2026-11-01','2',33,60);
            INSERT INTO sgci_apertura_clientes(cliente_id,monto) VALUES(1,100);
            INSERT INTO cartola_bancaria(id,banco_id,fecha,descripcion,cargo,abono) VALUES(1,1,'2026-11-16','Cobro prueba',0,100);
        """)

    def cobrar(self,apertura=40,docs=None):
        return servicio.sgci_cobro_mixto(self.db,1,1,[1] if docs is None else docs,apertura)

    def test_cobro_mixto_cuadra_y_no_duplica_factura(self):
        asiento=self.cobrar()
        self.assertEqual(tuple(self.db.execute('SELECT SUM(debe),SUM(haber),COUNT(*) FROM libro_diario WHERE asiento_id=?',(asiento,)).fetchone()),(100,100,2))
        self.assertEqual(self.db.execute('SELECT monto FROM aplicaciones_clientes').fetchone()[0],60)
        self.assertEqual(self.db.execute('SELECT monto FROM sgci_aplicaciones_apertura_clientes').fetchone()[0],40)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM ventas').fetchone()[0],2)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM auditoria WHERE accion='COBRO MIXTO CLIENTE'").fetchone()[0],1)
        self.assertEqual(self.db.execute('SELECT conciliado FROM cartola_bancaria WHERE id=1').fetchone()[0],1)
        with self.assertRaises(ValueError):self.cobrar()
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM pagos_clientes').fetchone()[0],1)

    def test_fallo_auditoria_revierte_todas_las_tablas(self):
        self.db.execute("CREATE TRIGGER fallo BEFORE INSERT ON auditoria BEGIN SELECT RAISE(ABORT,'fallo'); END")
        self.db.commit();antes=list(self.db.iterdump())
        with self.assertRaises(sqlite3.IntegrityError):self.cobrar()
        self.assertEqual(list(self.db.iterdump()),antes)

    def test_no_confirma_ni_revierte_transaccion_ajena(self):
        self.db.execute("UPDATE clientes SET nombre='Pendiente' WHERE id=1")
        antes=list(self.db.iterdump())
        with self.assertRaises(RuntimeError):self.cobrar()
        self.assertEqual(list(self.db.iterdump()),antes)
        self.assertTrue(self.db.in_transaction)
        self.db.rollback()

    def test_revalida_ambos_permisos_dentro_de_reserva(self):
        original=servicio.sgci_autorizar_operacion
        for modulo in ('banco','cxc'):
            with self.subTest(modulo=modulo):
                def autorizar(conn,mod,*args):
                    original(conn,mod,*args)
                    if conn.in_transaction and mod==modulo:raise PermissionError('Revocado')
                antes=list(self.db.iterdump())
                with patch.dict(vars(servicio),{'sgci_autorizar_operacion':autorizar}):
                    with self.assertRaises(PermissionError):self.cobrar()
                self.assertEqual(list(self.db.iterdump()),antes)

    def test_apertura_invalida_no_trunca_importes(self):
        antes=list(self.db.iterdump())
        for monto in (-1,40.5,'NaN','Infinity',None,True,9223372036854775808):
            with self.subTest(monto=monto),self.assertRaises(ValueError):self.cobrar(monto)
            self.assertEqual(list(self.db.iterdump()),antes)

    def test_factura_ajena_no_se_aplica(self):
        antes=list(self.db.iterdump())
        with self.assertRaises(ValueError):self.cobrar(docs=[2])
        self.assertEqual(list(self.db.iterdump()),antes)

    def test_distribucion_inexacta_no_deja_cambios(self):
        antes=list(self.db.iterdump())
        with self.assertRaises(ValueError):self.cobrar(39)
        self.assertEqual(list(self.db.iterdump()),antes)

    def test_apertura_insuficiente_no_deja_cambios(self):
        antes=list(self.db.iterdump())
        with self.assertRaises(ValueError):self.cobrar(101,[])
        self.assertEqual(list(self.db.iterdump()),antes)

    def test_movimiento_con_cargo_y_abono_se_rechaza(self):
        self.db.execute('UPDATE cartola_bancaria SET cargo=10 WHERE id=1');self.db.commit()
        antes=list(self.db.iterdump())
        with self.assertRaises(ValueError):self.cobrar()
        self.assertEqual(list(self.db.iterdump()),antes)

    def concurrentes(self,operacion):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta=Path(carpeta)/'cobro.db'
            with closing(sqlite3.connect(ruta)) as db:self.db.backup(db)
            barrera=threading.Barrier(2)
            def ejecutar(i):
                with closing(sqlite3.connect(ruta,timeout=10)) as db:
                    db.row_factory=sqlite3.Row;barrera.wait(timeout=10)
                    try:return ('ok',operacion(db,i))
                    except ValueError:return ('rechazado',None)
            with ThreadPoolExecutor(max_workers=2) as pool:
                resultados=list(pool.map(ejecutar,range(2)))
            with closing(sqlite3.connect(ruta)) as db:
                conteos=[db.execute('SELECT COUNT(*) FROM '+tabla).fetchone()[0] for tabla in ('pagos_clientes','libro_diario','auditoria')]
                aplicado=db.execute('SELECT COALESCE(SUM(monto),0) FROM sgci_aplicaciones_apertura_clientes').fetchone()[0]
            return resultados,conteos,aplicado

    def test_dos_sesiones_no_duplican_mismo_cobro(self):
        resultados,conteos,aplicado=self.concurrentes(lambda db,i:servicio.sgci_cobro_mixto(db,1,1,[1],40))
        self.assertCountEqual([x[0] for x in resultados],['ok','rechazado'])
        self.assertEqual(conteos,[1,2,1]);self.assertEqual(aplicado,40)

    def test_dos_movimientos_no_sobreaplican_apertura_compartida(self):
        self.db.execute('UPDATE cartola_bancaria SET abono=70 WHERE id=1')
        self.db.execute("INSERT INTO cartola_bancaria(id,banco_id,fecha,descripcion,cargo,abono) VALUES(2,1,'2026-11-16','Segundo cobro',0,70)")
        self.db.commit()
        resultados,conteos,aplicado=self.concurrentes(lambda db,i:servicio.sgci_cobro_mixto(db,i+1,1,[],70))
        self.assertCountEqual([x[0] for x in resultados],['ok','rechazado'])
        self.assertEqual(conteos,[1,2,1]);self.assertEqual(aplicado,70)

    def test_movimientos_distintos_generan_asientos_distintos(self):
        self.db.execute('UPDATE sgci_apertura_clientes SET monto=200')
        self.db.execute("INSERT INTO cartola_bancaria(id,banco_id,fecha,descripcion,cargo,abono) VALUES(2,1,'2026-11-16','Segundo cobro',0,100)")
        self.db.commit()
        resultados,conteos,aplicado=self.concurrentes(lambda db,i:servicio.sgci_cobro_mixto(db,i+1,1,[],100))
        self.assertEqual([x[0] for x in resultados],['ok','ok'])
        self.assertNotEqual(resultados[0][1],resultados[1][1])
        self.assertEqual(conteos,[2,4,2]);self.assertEqual(aplicado,200)


if __name__=='__main__':unittest.main()

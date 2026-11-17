import sqlite3
import unittest
import pandas as pd
from modulos import contabilidad_reportes as bancos
from tests.soporte_flujos import preparar


class TestCartolasIntegracion(unittest.TestCase):
    def setUp(self):
        self.db=preparar(self)
        self.df=pd.DataFrame([{'fecha':'2026-11-11','descripcion':'Pago','cargo':100,'abono':0,'referencia':'REF1'},
                              {'fecha':'2026-11-11','descripcion':'Abono','cargo':0,'abono':300,'referencia':'REF2'}])

    def test_reimportacion_no_duplica_y_conserva_saldos(self):
        a=bancos.importar_cartola(self.db,self.df,1)
        b=bancos.importar_cartola(self.db,self.df,1)
        self.assertEqual(a[:2],(2,0));self.assertEqual(b[:2],(0,2))
        self.assertEqual(tuple(self.db.execute('SELECT SUM(cargo),SUM(abono) FROM cartola_bancaria').fetchone()),(100,300))
        self.assertEqual(self.db.execute('SELECT count(*) FROM libro_diario').fetchone()[0],0)

    def test_error_de_segunda_fila_revierte_todo_el_lote(self):
        self.db.execute("CREATE TRIGGER rechazar_abono BEFORE INSERT ON cartola_bancaria WHEN NEW.referencia='REF2' BEGIN SELECT RAISE(ABORT,'rechazo de prueba'); END")
        self.db.commit()
        with self.assertRaises(sqlite3.IntegrityError):bancos.importar_cartola(self.db,self.df,1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM cartola_bancaria').fetchone()[0],0)
        self.assertEqual(self.db.execute('SELECT count(*) FROM auditoria').fetchone()[0],0)

    def test_dos_movimientos_con_distinto_saldo_no_se_confunden(self):
        df=pd.DataFrame([{'fecha':'2026-11-11','descripcion':'Transferencia','cargo':100,'saldo':900},
                         {'fecha':'2026-11-11','descripcion':'Transferencia','cargo':100,'saldo':800}])
        self.assertEqual(bancos.importar_cartola(self.db,df,1)[:2],(2,0))

    def test_crear_manual_no_exige_importar_archivo(self):
        self.db.execute("DELETE FROM sgci_perfil_permisos WHERE accion='importar'");self.db.commit()
        r=bancos.registrar_movimiento_manual(self.db,1,'2026-11-11','Manual','MANUAL1',100,0)
        self.assertEqual(r[:2],(1,0))
        with self.assertRaises(PermissionError):bancos.importar_cartola(self.db,self.df,1)

    def test_banco_inexistente_no_deja_registros(self):
        with self.assertRaises(ValueError):bancos.importar_cartola(self.db,self.df,999)

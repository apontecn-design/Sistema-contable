"""Alcance laboral en creación y reversión bancaria, con servicios y SQLite reales."""
import unittest
import sqlite3
import tempfile
import threading
from pathlib import Path
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from modulos import conciliacion_documental as servicios, contabilidad_reportes, usuarios
from tests.soporte_flujos import preparar


class TestAnticiposCartolaAlcance(unittest.TestCase):
    def setUp(self):
        self.db=preparar(self)
        columnas={r[1] for r in self.db.execute('PRAGMA table_info(cartola_bancaria)')}
        for nombre,tipo in [('asiento_id','INTEGER'),('match_tipo','TEXT'),('match_id','INTEGER'),('match_confianza','INTEGER')]:
            if nombre not in columnas:self.db.execute(f'ALTER TABLE cartola_bancaria ADD COLUMN {nombre} {tipo}')
        self.db.execute("INSERT INTO nomina_trabajadores(id,rut,nombre,activo) VALUES(1,'1-9','Trabajador propio',1),(2,'2-7','Otro trabajador',1)")
        self.db.execute("INSERT INTO cartola_bancaria(id,banco_id,fecha,cargo,abono) VALUES(1,1,'2026-11-10',100,0)")
        self.db.execute("INSERT INTO sgci_usuario_trabajador(email,trabajador_id) VALUES('finanzas@example.com',1)")
        self.db.commit()
        p=patch.dict(vars(servicios),{
            'sgci_rrhh_ids_autorizados':usuarios.sgci_rrhh_ids_autorizados,
            'registrar_auditoria':contabilidad_reportes.registrar_auditoria})
        p.start();self.addCleanup(p.stop)

    def crear(self,trabajador=1):
        return servicios.contabilizar_anticipo_nomina_desde_cartola(self.db,1,trabajador,'2026-11')

    def test_selector_solo_activos_del_alcance_y_campos_necesarios(self):
        self.db.execute("INSERT INTO nomina_trabajadores(id,rut,nombre,activo) VALUES(3,'3-5','Inactivo',0)")
        self.db.execute("INSERT INTO sgci_rrhh_autorizados VALUES('finanzas@example.com',3)")
        self.db.execute("INSERT INTO sgci_alcance_rrhh VALUES('finanzas@example.com','autorizados')")
        antes=list(self.db.iterdump())
        filas=servicios.banco_trabajadores_anticipos(self.db)
        self.assertEqual(filas.id.tolist(),[1])
        self.assertEqual(list(filas.columns),['id','rut','nombre','sueldo_base','anticipo_porcentaje'])
        self.assertEqual(list(self.db.iterdump()),antes)

    def test_selector_alcance_todos_y_revocacion(self):
        self.db.execute("INSERT INTO sgci_alcance_rrhh VALUES('finanzas@example.com','todos')")
        self.assertEqual(set(servicios.banco_trabajadores_anticipos(self.db).id),{1,2})
        self.db.execute("UPDATE sgci_alcance_rrhh SET alcance='propios'")
        self.assertEqual(servicios.banco_trabajadores_anticipos(self.db).id.tolist(),[1])
        self.db.execute('DELETE FROM sgci_usuario_trabajador')
        self.assertTrue(servicios.banco_trabajadores_anticipos(self.db).empty)

    def test_selector_exige_ambos_permisos_antes_de_consultar_trabajadores(self):
        for modulo,sub in [('banco','Conciliación bancaria'),('nomina','Anticipos y préstamos')]:
            with self.subTest(modulo=modulo):
                self.db.execute('INSERT INTO sgci_usuario_permisos_detalle VALUES(?,?,?,?,0)',('finanzas@example.com',modulo,sub,'ver'))
                consultas=[];self.db.set_trace_callback(consultas.append)
                with self.assertRaises(PermissionError):servicios.banco_trabajadores_anticipos(self.db)
                self.db.set_trace_callback(None)
                self.assertFalse(any('FROM nomina_trabajadores' in q for q in consultas))
                self.db.execute('DELETE FROM sgci_usuario_permisos_detalle')

    def test_permiso_bancario_no_concede_creacion_laboral(self):
        self.db.execute("INSERT INTO sgci_usuario_permisos_detalle VALUES('finanzas@example.com','nomina','Anticipos y préstamos','crear',0)")
        self.db.commit();antes=list(self.db.iterdump())
        with self.assertRaises(PermissionError):self.crear()
        self.assertEqual(list(self.db.iterdump()),antes)

    def test_permiso_bancario_no_concede_anulacion_laboral(self):
        self.crear()
        self.db.execute("INSERT INTO sgci_usuario_permisos_detalle VALUES('finanzas@example.com','nomina','Anticipos y préstamos','anular',0)")
        self.db.commit();antes=list(self.db.iterdump())
        with self.assertRaises(PermissionError):servicios.revertir_anticipo_nomina_cartola(self.db,1)
        self.assertEqual(list(self.db.iterdump()),antes)

    def test_revocacion_laboral_al_entrar_en_transaccion_bloquea_creacion(self):
        self.comprobar_revocacion_transaccional('crear',lambda:self.crear())

    def test_revocacion_laboral_al_entrar_en_transaccion_bloquea_reverso(self):
        self.crear()
        self.comprobar_revocacion_transaccional('anular',lambda:servicios.revertir_anticipo_nomina_cartola(self.db,1))

    def comprobar_revocacion_transaccional(self,accion,operacion):
        antes=list(self.db.iterdump());llamadas=[]
        def autorizar(conn,modulo,act,sub=None):
            usuarios.sgci_autorizar_operacion(conn,modulo,act,sub)
            if modulo=='nomina' and act==accion:
                llamadas.append(conn.in_transaction)
                if conn.in_transaction:raise PermissionError('Permiso revocado')
        with patch.dict(vars(servicios),{'sgci_autorizar_operacion':autorizar}):
            with self.assertRaises(PermissionError):operacion()
        self.assertEqual(llamadas,[False,True])
        self.assertEqual(list(self.db.iterdump()),antes)
        self.assertFalse(self.db.in_transaction)

    def test_ciclo_propio_cuadra_y_reverso_conserva_original(self):
        original,anticipo=self.crear()
        reverso=servicios.revertir_anticipo_nomina_cartola(self.db,1)
        self.assertNotEqual(original,reverso)
        self.assertEqual(self.db.execute('SELECT count(*) FROM libro_diario').fetchone()[0],4)
        self.assertEqual(tuple(self.db.execute('SELECT SUM(debe),SUM(haber) FROM libro_diario').fetchone()),(200,200))
        self.assertEqual(self.db.execute('SELECT anulado FROM nomina_anticipos WHERE id=?',(anticipo,)).fetchone()[0],1)
        self.assertEqual(self.db.execute('SELECT conciliado FROM cartola_bancaria WHERE id=1').fetchone()[0],0)
        self.assertEqual(self.db.execute("SELECT usuario FROM auditoria WHERE accion='REVERSO ANTICIPO NOMINA'").fetchone()[0],'finanzas@example.com')
        with self.assertRaises(ValueError):servicios.revertir_anticipo_nomina_cartola(self.db,1)

    def test_crear_para_ajeno_no_lee_cartola_ni_escribe(self):
        consultas=[];self.db.set_trace_callback(consultas.append)
        with self.assertRaises(PermissionError):self.crear(2)
        self.db.set_trace_callback(None)
        self.assertFalse(any('cartola_bancaria' in sql for sql in consultas))
        self.assertEqual(self.db.execute('SELECT count(*) FROM nomina_anticipos').fetchone()[0],0)

    def test_revocar_alcance_bloquea_reversion_sin_cambios(self):
        self.crear()
        self.db.execute("UPDATE sgci_usuario_trabajador SET trabajador_id=2 WHERE email='finanzas@example.com'")
        self.db.commit()
        antes=list(self.db.iterdump())
        with self.assertRaises(ValueError):servicios.revertir_anticipo_nomina_cartola(self.db,1)
        self.assertEqual(list(self.db.iterdump()),antes)

    def test_alcance_autorizados_permite_otro_trabajador(self):
        self.db.execute("INSERT INTO sgci_alcance_rrhh(email,alcance) VALUES('finanzas@example.com','autorizados')")
        self.db.execute("INSERT INTO sgci_rrhh_autorizados(email,trabajador_id) VALUES('finanzas@example.com',2)")
        self.db.commit()
        self.crear(2)
        servicios.revertir_anticipo_nomina_cartola(self.db,1)

    def test_sin_vinculo_laboral_no_consulta_movimiento(self):
        self.db.execute('DELETE FROM sgci_usuario_trabajador');self.db.commit()
        consultas=[];self.db.set_trace_callback(consultas.append)
        with self.assertRaises(PermissionError):servicios.revertir_anticipo_nomina_cartola(self.db,1)
        self.db.set_trace_callback(None)
        self.assertFalse(any('cartola_bancaria' in sql for sql in consultas))

    def test_denegacion_bancaria_prevalece_sobre_alcance(self):
        self.db.execute("INSERT INTO sgci_usuario_permisos_detalle VALUES('finanzas@example.com','banco','Conciliación bancaria','contabilizar',0)")
        self.db.commit()
        with self.assertRaises(PermissionError):self.crear()
        self.assertEqual(self.db.execute('SELECT count(*) FROM nomina_anticipos').fetchone()[0],0)

    def fallo_auditoria(self):
        self.db.execute("CREATE TRIGGER fallo_auditoria BEFORE INSERT ON auditoria BEGIN SELECT RAISE(ABORT,'Fallo de prueba'); END")
        self.db.commit()

    def test_fallo_auditoria_revierte_anticipo_asiento_y_cartola(self):
        self.fallo_auditoria()
        antes=list(self.db.iterdump())
        with self.assertRaises(sqlite3.IntegrityError):self.crear()
        self.assertEqual(list(self.db.iterdump()),antes)

    def test_fallo_auditoria_revierte_reverso_completo(self):
        self.crear();self.fallo_auditoria()
        antes=list(self.db.iterdump())
        with self.assertRaises(sqlite3.IntegrityError):servicios.revertir_anticipo_nomina_cartola(self.db,1)
        self.assertEqual(list(self.db.iterdump()),antes)

    def test_creacion_no_confirma_transaccion_ajena(self):
        self.db.execute("UPDATE bancos SET nombre='Cambio pendiente' WHERE id=1")
        with self.assertRaises(RuntimeError):self.crear()
        self.assertTrue(self.db.in_transaction)
        self.db.rollback()
        self.assertNotEqual(self.db.execute('SELECT nombre FROM bancos WHERE id=1').fetchone()[0],'Cambio pendiente')

    def test_reverso_no_revierte_transaccion_ajena(self):
        self.crear()
        self.db.execute("UPDATE bancos SET nombre='Cambio pendiente' WHERE id=1")
        with self.assertRaises(RuntimeError):servicios.revertir_anticipo_nomina_cartola(self.db,1)
        self.assertTrue(self.db.in_transaction)
        self.db.rollback()
        self.assertEqual(self.db.execute('SELECT conciliado FROM cartola_bancaria WHERE id=1').fetchone()[0],1)

    def test_marca_cartola_10_no_bloquea_cartola_1(self):
        self.db.execute("INSERT INTO nomina_anticipos(trabajador_id,periodo,fecha,monto,observacion) VALUES(1,'2026-11','2026-11-10',100,'Previo | CARTOLA:10')")
        self.db.commit()
        self.crear()
        self.assertEqual(self.db.execute('SELECT count(*) FROM nomina_anticipos').fetchone()[0],2)

    def ejecutar_dos_sesiones(self,operacion):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta=Path(carpeta)/'concurrencia.db'
            with closing(sqlite3.connect(ruta)) as db:self.db.backup(db)
            barrera=threading.Barrier(2)
            def ejecutar(indice):
                with closing(sqlite3.connect(ruta,timeout=10)) as db:
                    db.row_factory=sqlite3.Row
                    barrera.wait(timeout=10)
                    try:return ('correcto',operacion(db,indice))
                    except ValueError:return ('rechazado',None)
            with ThreadPoolExecutor(max_workers=2) as ejecutor:
                futuros=[ejecutor.submit(ejecutar,i) for i in range(2)]
                resultados=[f.result(timeout=20) for f in futuros]
            with closing(sqlite3.connect(ruta)) as db:
                conteos={tabla:db.execute('SELECT count(*) FROM '+tabla).fetchone()[0]
                         for tabla in ('nomina_anticipos','libro_diario','auditoria')}
            return resultados,conteos

    def test_dos_sesiones_no_crean_dos_anticipos_del_mismo_movimiento(self):
        resultados,conteos=self.ejecutar_dos_sesiones(lambda db,i:
            servicios.contabilizar_anticipo_nomina_desde_cartola(db,1,1,'2026-11'))
        self.assertCountEqual([r[0] for r in resultados],['correcto','rechazado'])
        self.assertEqual(conteos,dict(nomina_anticipos=1,libro_diario=2,auditoria=1))

    def test_dos_movimientos_concurrentes_generan_asientos_distintos(self):
        self.db.execute("INSERT INTO cartola_bancaria(id,banco_id,fecha,cargo,abono) VALUES(2,1,'2026-11-11',100,0)")
        self.db.commit()
        resultados,conteos=self.ejecutar_dos_sesiones(lambda db,i:
            servicios.contabilizar_anticipo_nomina_desde_cartola(db,i+1,1,'2026-11'))
        self.assertEqual([r[0] for r in resultados],['correcto','correcto'])
        self.assertNotEqual(resultados[0][1][0],resultados[1][1][0])
        self.assertEqual(conteos,dict(nomina_anticipos=2,libro_diario=4,auditoria=2))

    def test_dos_sesiones_no_duplican_reverso(self):
        self.crear()
        resultados,conteos=self.ejecutar_dos_sesiones(lambda db,i:
            servicios.revertir_anticipo_nomina_cartola(db,1))
        self.assertCountEqual([r[0] for r in resultados],['correcto','rechazado'])
        self.assertEqual(conteos,dict(nomina_anticipos=1,libro_diario=4,auditoria=2))

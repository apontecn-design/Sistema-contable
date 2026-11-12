import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from modulos import conciliacion_documental as servicio,usuarios
from tests.soporte_flujos import preparar


class TestVacacionesAutorizadas(unittest.TestCase):
    def setUp(self):
        self.db=preparar(self)
        self.db.execute("INSERT INTO nomina_trabajadores(id,rut,nombre) VALUES(1,'1-9','Propio'),(2,'2-7','Ajeno')")
        self.db.execute("INSERT INTO sgci_usuario_trabajador VALUES('finanzas@example.com',1)");self.db.commit()
        p=patch.dict(vars(servicio),{'sgci_rrhh_ids_autorizados':usuarios.sgci_rrhh_ids_autorizados})
        p.start();self.addCleanup(p.stop)

    def movimiento(self,tipo='ASIGNACION',dias=5,trabajador=1):
        return servicio.rrhh_registrar_vacaciones(self.db,trabajador,'2030-01-01',tipo,dias,'Prueba')

    def solicitar(self,trabajador=1):
        return servicio.rrhh_solicitar_vacaciones(self.db,trabajador,'2030-01-02','2030-01-04',3,'Prueba')

    def test_asignacion_ajuste_y_descuento_manuales_sin_asiento(self):
        self.movimiento();self.movimiento('AJUSTE',0.5);self.movimiento('DESCUENTO',2)
        saldo=self.db.execute("SELECT SUM(CASE WHEN tipo='DESCUENTO' THEN -dias ELSE dias END) FROM rrhh_vacaciones_movimientos").fetchone()[0]
        self.assertEqual(saldo,3.5)
        self.assertEqual(self.db.execute('SELECT count(*) FROM libro_diario').fetchone()[0],0)

    def test_descuento_excesivo_no_modifica_saldo_ni_auditoria(self):
        self.movimiento();antes=list(self.db.iterdump())
        with self.assertRaises(ValueError):self.movimiento('DESCUENTO',6)
        self.assertEqual(list(self.db.iterdump()),antes)

    def test_solicitar_y_aprobar_no_descuenta_dias_automaticamente(self):
        self.movimiento();solicitud=self.solicitar()
        servicio.rrhh_resolver_vacaciones(self.db,1,solicitud,'APROBADA','Responsable')
        self.assertEqual(self.db.execute('SELECT estado FROM rrhh_vacaciones_solicitudes').fetchone()[0],'APROBADA')
        self.assertEqual(self.db.execute('SELECT count(*) FROM rrhh_vacaciones_movimientos').fetchone()[0],1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM libro_diario').fetchone()[0],0)
        self.assertEqual(self.db.execute("SELECT usuario FROM auditoria WHERE accion='RESOLVER VACACIONES'").fetchone()[0],'finanzas@example.com')

    def test_resolver_dos_veces_se_rechaza(self):
        solicitud=self.solicitar()
        servicio.rrhh_resolver_vacaciones(self.db,1,solicitud,'RECHAZADA','Responsable')
        antes=list(self.db.iterdump())
        with self.assertRaises(ValueError):servicio.rrhh_resolver_vacaciones(self.db,1,solicitud,'APROBADA','Responsable')
        self.assertEqual(list(self.db.iterdump()),antes)

    def test_anulacion_requiere_permiso_anular(self):
        solicitud=self.solicitar()
        self.db.execute("INSERT INTO sgci_usuario_permisos_detalle VALUES('finanzas@example.com','nomina','Vacaciones','anular',0)");self.db.commit()
        with self.assertRaises(PermissionError):servicio.rrhh_resolver_vacaciones(self.db,1,solicitud,'ANULADA','Responsable')
        servicio.rrhh_resolver_vacaciones(self.db,1,solicitud,'APROBADA','Responsable')

    def test_alcance_bloquea_trabajador_ajeno_en_todas_las_operaciones(self):
        for llamada in (lambda:self.movimiento(trabajador=2),lambda:self.solicitar(2),
                        lambda:servicio.rrhh_resolver_vacaciones(self.db,2,1,'APROBADA','Responsable'),
                        lambda:servicio.rrhh_exportar_vacaciones(self.db,2)):
            with self.assertRaises(PermissionError):llamada()

    def test_solicitud_de_otro_trabajador_no_se_resuelve_con_id_propio(self):
        with patch.dict(vars(servicio),{'sgci_rrhh_ids_autorizados':lambda *a:None}):solicitud=self.solicitar(2)
        with self.assertRaises(ValueError):servicio.rrhh_resolver_vacaciones(self.db,1,solicitud,'APROBADA','Responsable')
        self.assertEqual(self.db.execute('SELECT estado FROM rrhh_vacaciones_solicitudes').fetchone()[0],'PENDIENTE')

    def test_dias_fechas_y_estados_invalidos_no_se_guardan(self):
        for dias in (0,-1,float('nan'),float('inf')):
            with self.subTest(dias=dias),self.assertRaises(ValueError):self.movimiento(dias=dias)
        with self.assertRaises(ValueError):servicio.rrhh_solicitar_vacaciones(self.db,1,'2030-01-04','2030-01-02',1)
        with self.assertRaises(ValueError):servicio.rrhh_resolver_vacaciones(self.db,1,1,'OTRO','Responsable')
        with self.assertRaises(ValueError):servicio.rrhh_resolver_vacaciones(self.db,1,1,'APROBADA','')

    def test_exportacion_exige_permiso_y_no_consulta_historial_si_se_revoca(self):
        self.movimiento()
        csv=servicio.rrhh_exportar_vacaciones(self.db,1)
        self.assertIn('ASIGNACION',csv.decode('utf-8-sig'))
        self.db.execute("INSERT INTO sgci_usuario_permisos_detalle VALUES('finanzas@example.com','nomina','Vacaciones','exportar',0)");self.db.commit()
        consultas=[];self.db.set_trace_callback(consultas.append)
        with self.assertRaises(PermissionError):servicio.rrhh_exportar_vacaciones(self.db,1)
        self.db.set_trace_callback(None)
        self.assertFalse(any('FROM rrhh_vacaciones_movimientos' in sql for sql in consultas))

    def test_fallo_auditoria_revierte_creacion_y_resolucion(self):
        solicitud=self.solicitar()
        self.db.execute("CREATE TRIGGER fallo_auditoria BEFORE INSERT ON auditoria BEGIN SELECT RAISE(ABORT,'Fallo de prueba'); END");self.db.commit()
        antes=list(self.db.iterdump())
        for llamada in (self.movimiento,self.solicitar,lambda:servicio.rrhh_resolver_vacaciones(self.db,1,solicitud,'APROBADA','Responsable')):
            with self.assertRaises(sqlite3.IntegrityError):llamada()
        self.assertEqual(list(self.db.iterdump()),antes)

    def test_transaccion_ajena_se_conserva(self):
        self.db.execute("UPDATE bancos SET nombre='Pendiente' WHERE id=1")
        for llamada in (self.movimiento,self.solicitar,lambda:servicio.rrhh_resolver_vacaciones(self.db,1,1,'APROBADA','Responsable')):
            with self.assertRaises(RuntimeError):llamada()
        self.assertTrue(self.db.in_transaction);self.db.rollback()

    def test_dos_sesiones_no_pueden_descontar_el_mismo_saldo(self):
        self.movimiento(dias=5)
        with tempfile.TemporaryDirectory() as carpeta:
            ruta=Path(carpeta)/'concurrencia.db'
            with closing(sqlite3.connect(ruta)) as db:self.db.backup(db)
            barrera=threading.Barrier(2)
            def descontar():
                with closing(sqlite3.connect(ruta,timeout=10)) as db:
                    db.row_factory=sqlite3.Row;barrera.wait(timeout=10)
                    try:
                        servicio.rrhh_registrar_vacaciones(db,1,'2030-01-02','DESCUENTO',5)
                        return 'correcto'
                    except ValueError:return 'rechazado'
            with ThreadPoolExecutor(max_workers=2) as ejecutor:
                futuros=[ejecutor.submit(descontar) for _ in range(2)]
                self.assertCountEqual([f.result(timeout=20) for f in futuros],['correcto','rechazado'])
            with closing(sqlite3.connect(ruta)) as db:
                self.assertEqual(db.execute("SELECT SUM(CASE WHEN tipo='DESCUENTO' THEN -dias ELSE dias END) FROM rrhh_vacaciones_movimientos").fetchone()[0],0)

import sqlite3
import unittest
from unittest.mock import patch
from modulos import conciliacion_documental as servicio, usuarios
from tests.soporte_flujos import preparar


class TestAltasMovimientosRRHH(unittest.TestCase):
    def setUp(self):
        self.db=preparar(self)
        self.db.execute("INSERT INTO nomina_trabajadores(id,rut,nombre,activo) VALUES(1,'1-9','Propio',1),(2,'2-7','Ajeno',1),(3,'3-5','Inactivo',0)")
        self.db.execute("INSERT INTO sgci_usuario_trabajador VALUES('finanzas@example.com',1)")
        self.db.commit()
        p=patch.dict(vars(servicio),{'sgci_rrhh_ids_autorizados':usuarios.sgci_rrhh_ids_autorizados})
        p.start();self.addCleanup(p.stop)

    def anticipo(self,**cambios):
        datos=dict(trabajador_id=1,periodo='2026-11',fecha='2026-11-12',monto=100,observacion='Prueba')
        datos.update(cambios);return servicio.nomina_crear_anticipo(self.db,**datos)

    def prestamo(self,**cambios):
        datos=dict(trabajador_id=1,fecha='2026-11-12',monto=100,numero_cuotas=2,cuota=0,primera_cuota='2026-12')
        datos.update(cambios);return servicio.nomina_crear_prestamo(self.db,**datos)

    def test_anticipo_propio_registra_y_audita_sin_asiento(self):
        nuevo=self.anticipo()
        self.assertEqual(tuple(self.db.execute('SELECT trabajador_id,periodo,monto,contabilizado FROM nomina_anticipos WHERE id=?',(nuevo,)).fetchone()),(1,'2026-11',100,0))
        self.assertEqual(self.db.execute('SELECT usuario FROM auditoria').fetchone()[0],'finanzas@example.com')
        self.assertEqual(self.db.execute('SELECT count(*) FROM libro_diario').fetchone()[0],0)

    def test_prestamo_mensual_conserva_calculo_cuota_y_saldo(self):
        nuevo=self.prestamo(monto=101)
        self.assertEqual(tuple(self.db.execute('SELECT numero_cuotas,cuota,primera_cuota,saldo FROM nomina_prestamos WHERE id=?',(nuevo,)).fetchone()),(2,50.5,'2026-12',101))
        self.assertEqual(self.db.execute('SELECT count(*) FROM libro_diario').fetchone()[0],0)

    def test_calendario_especifico_conserva_fechas_importes_y_saldo(self):
        nuevo=self.prestamo(fechas_cuotas=[('2026-11-15',40),('2026-11-30',60)])
        self.assertEqual([tuple(r) for r in self.db.execute('SELECT fecha,monto FROM nomina_prestamo_cuotas_programadas WHERE prestamo_id=? ORDER BY fecha',(nuevo,))],[('2026-11-15',40),('2026-11-30',60)])
        self.assertEqual(self.db.execute('SELECT primera_cuota FROM nomina_prestamos').fetchone()[0],'2026-11')

    def test_alcance_bloquea_ajeno_antes_de_consultar_ficha(self):
        for funcion in (self.anticipo,self.prestamo):
            consultas=[];self.db.set_trace_callback(consultas.append)
            with self.assertRaises(PermissionError):funcion(trabajador_id=2)
            self.db.set_trace_callback(None)
            self.assertFalse(any('FROM nomina_trabajadores' in sql for sql in consultas))

    def test_revocacion_individual_precede_validacion(self):
        self.db.execute("INSERT INTO sgci_usuario_permisos_detalle VALUES('finanzas@example.com','nomina','Anticipos y préstamos','crear',0)")
        self.db.commit()
        for funcion in (self.anticipo,self.prestamo):
            with self.assertRaises(PermissionError):funcion(monto=-1)

    def test_inactivo_o_inexistente_no_admite_movimientos(self):
        with patch.dict(vars(servicio),{'sgci_rrhh_ids_autorizados':lambda *a:None}):
            for trabajador in (3,999):
                for funcion in (self.anticipo,self.prestamo):
                    with self.subTest(trabajador=trabajador),self.assertRaises(ValueError):funcion(trabajador_id=trabajador)

    def test_no_trunca_montos_o_identificadores(self):
        for funcion in (self.anticipo,self.prestamo):
            for cambio in ({'monto':0},{'monto':1.5},{'monto':float('nan')},{'monto':float('inf')},{'trabajador_id':1.5}):
                with self.subTest(cambio=cambio),self.assertRaises(ValueError):funcion(**cambio)

    def test_periodo_y_fechas_invalidos_se_rechazan(self):
        with self.assertRaises(ValueError):self.anticipo(periodo='2026-13')
        for funcion in (self.anticipo,self.prestamo):
            with self.assertRaises(ValueError):funcion(fecha='2026-02-30')
        with self.assertRaises(ValueError):self.prestamo(primera_cuota='2026-13')

    def test_cuotas_invalidas_o_calendario_inconsistente_no_guardan(self):
        for cambio in ({'numero_cuotas':0},{'numero_cuotas':1.5},{'cuota':float('inf')},{'cuota':'1e1000'},
                       {'fechas_cuotas':[('2026-11-15',40),('2026-11-30',59)]},
                       {'fechas_cuotas':[('2026-11-15',50),('2026-11-15',50)]},
                       {'fechas_cuotas':[('2026-11-01',50),('2026-11-30',50)]}):
            with self.subTest(cambio=cambio),self.assertRaises(ValueError):self.prestamo(**cambio)
        self.assertEqual(self.db.execute('SELECT count(*) FROM nomina_prestamos').fetchone()[0],0)

    def test_nomina_contabilizada_bloquea_anticipo_retroactivo(self):
        self.db.execute("INSERT INTO nomina_periodos(periodo,estado,asiento_id) VALUES('2026-11','CONTABILIZADO',1)")
        self.db.commit()
        with self.assertRaises(ValueError):self.anticipo()
        self.assertEqual(self.db.execute('SELECT count(*) FROM nomina_anticipos').fetchone()[0],0)

    def test_cierre_contable_bloquea_movimientos(self):
        self.db.execute("INSERT INTO periodos_contables(periodo,estado) VALUES('2026-11','CERRADO')");self.db.commit()
        for funcion in (self.anticipo,self.prestamo):
            with self.assertRaises(ValueError):funcion()

    def test_fallo_auditoria_revierte_anticipo_prestamo_y_calendario(self):
        self.db.execute("CREATE TRIGGER fallo_auditoria BEFORE INSERT ON auditoria BEGIN SELECT RAISE(ABORT,'Fallo de prueba'); END");self.db.commit()
        antes=list(self.db.iterdump())
        with self.assertRaises(sqlite3.IntegrityError):self.anticipo()
        with self.assertRaises(sqlite3.IntegrityError):self.prestamo(fechas_cuotas=[('2026-11-15',50),('2026-11-30',50)])
        self.assertEqual(list(self.db.iterdump()),antes)

    def test_fallo_segunda_cuota_revierte_prestamo_completo(self):
        self.db.execute("CREATE TRIGGER fallo_cuota BEFORE INSERT ON nomina_prestamo_cuotas_programadas WHEN NEW.fecha='2026-11-30' BEGIN SELECT RAISE(ABORT,'Fallo de prueba'); END");self.db.commit()
        with self.assertRaises(sqlite3.IntegrityError):self.prestamo(fechas_cuotas=[('2026-11-15',50),('2026-11-30',50)])
        self.assertEqual(self.db.execute('SELECT count(*) FROM nomina_prestamos').fetchone()[0],0)
        self.assertEqual(self.db.execute('SELECT count(*) FROM nomina_prestamo_cuotas_programadas').fetchone()[0],0)

    def test_transaccion_previa_no_se_confirma_ni_revierte(self):
        self.db.execute("UPDATE bancos SET nombre='Pendiente' WHERE id=1")
        for funcion in (self.anticipo,self.prestamo):
            with self.assertRaises(RuntimeError):funcion()
        self.assertTrue(self.db.in_transaction);self.db.rollback()

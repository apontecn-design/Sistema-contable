import sqlite3
import unittest
from datetime import timedelta
from unittest.mock import patch
from modulos import conciliacion_documental as servicio
from tests.soporte_flujos import preparar


class TestGuardadoLiquidacion(unittest.TestCase):
    def setUp(self):
        self.db=preparar(self)
        servicio.instalar_cuentas_nomina(self.db)
        self.db.execute("INSERT INTO nomina_trabajadores(id,rut,nombre) VALUES(1,'1-9','Propio'),(2,'2-7','Ajeno')")
        self.db.commit()
        p=patch.dict(vars(servicio),{'sgci_rrhh_ids_autorizados':lambda *a:{1},'timedelta':timedelta})
        p.start();self.addCleanup(p.stop)

    def valores(self,**cambios):
        datos={c:0 for c in servicio.NOMINA_CAMPOS_LIQUIDACION}
        datos.update(periodo='2026-11',trabajador_id=1,dias_trabajados=30,sueldo_base=100,sueldo_periodo=100,
                     total_imponible=100,total_haberes=100,liquido_periodo=100,saldo_pagar=100,
                     afp_nombre='Uno',salud_tipo='Fonasa',salud_modalidad='7% legal',estado='CALCULADO',observacion='Prueba')
        datos.update(cambios)
        return tuple(datos[c] for c in servicio.NOMINA_CAMPOS_LIQUIDACION)

    def guardar(self,**cambios):return servicio.nomina_guardar_liquidacion(self.db,self.valores(**cambios))

    def test_crea_y_actualiza_borrador_sin_duplicar_ni_contabilizar(self):
        self.guardar();self.guardar(observacion='Corrección')
        self.assertEqual(self.db.execute('SELECT count(*) FROM nomina_liquidaciones').fetchone()[0],1)
        self.assertEqual(self.db.execute('SELECT observacion FROM nomina_liquidaciones').fetchone()[0],'Corrección')
        self.assertEqual(self.db.execute('SELECT count(*) FROM auditoria').fetchone()[0],2)
        self.assertEqual(self.db.execute('SELECT count(*) FROM libro_diario').fetchone()[0],0)

    def test_contabilizacion_real_impide_recalcular_y_conserva_asiento(self):
        self.guardar()
        with patch.dict(vars(servicio),{'sgci_rrhh_ids_autorizados':lambda *a:None}):
            servicio.nomina_contabilizar_periodo(self.db,'2026-11')
        antes=list(self.db.iterdump())
        with self.assertRaises(ValueError):self.guardar(sueldo_periodo=999)
        self.assertEqual(list(self.db.iterdump()),antes)
        self.assertEqual(self.db.execute('SELECT count(*) FROM libro_diario').fetchone()[0],2)

    def test_estado_individual_contabilizado_bloquea_aunque_periodo_sea_borrador(self):
        self.guardar()
        self.db.execute("UPDATE nomina_liquidaciones SET estado='CONTABILIZADO'");self.db.commit()
        antes=list(self.db.iterdump())
        with self.assertRaises(ValueError):self.guardar()
        self.assertEqual(list(self.db.iterdump()),antes)

    def test_periodo_con_asiento_impide_agregar_liquidacion(self):
        self.db.execute("INSERT INTO nomina_periodos(periodo,estado,asiento_id) VALUES('2026-11','BORRADOR',5)")
        self.db.commit()
        with self.assertRaises(ValueError):self.guardar()
        self.assertEqual(self.db.execute('SELECT count(*) FROM nomina_liquidaciones').fetchone()[0],0)

    def test_cierre_contable_bloquea_guardado(self):
        self.db.execute("INSERT INTO periodos_contables(periodo,estado) VALUES('2026-11','CERRADO')");self.db.commit()
        with self.assertRaises(ValueError):self.guardar()

    def test_alcance_impide_consultar_liquidacion_ajena(self):
        consultas=[];self.db.set_trace_callback(consultas.append)
        with self.assertRaises(PermissionError):self.guardar(trabajador_id=2)
        self.db.set_trace_callback(None)
        self.assertFalse(any('FROM nomina_liquidaciones' in sql for sql in consultas))

    def test_denegacion_individual_precede_validacion(self):
        self.db.execute("INSERT INTO sgci_usuario_permisos_detalle VALUES('finanzas@example.com','nomina','Liquidación mensual','editar',0)")
        self.db.commit()
        with self.assertRaises(PermissionError):servicio.nomina_guardar_liquidacion(self.db,())

    def test_fallo_auditoria_revierte_liquidacion_y_periodo(self):
        self.db.execute("CREATE TRIGGER fallo_auditoria BEFORE INSERT ON auditoria BEGIN SELECT RAISE(ABORT,'Fallo de prueba'); END")
        self.db.commit()
        antes=list(self.db.iterdump())
        with self.assertRaises(sqlite3.IntegrityError):self.guardar()
        self.assertEqual(list(self.db.iterdump()),antes)

    def test_transaccion_ajena_se_conserva(self):
        self.db.execute("UPDATE bancos SET nombre='Pendiente' WHERE id=1")
        with self.assertRaises(RuntimeError):self.guardar()
        self.assertTrue(self.db.in_transaction);self.db.rollback()

    def test_rechaza_periodo_estado_y_montos_no_finitos(self):
        for cambio in ({'periodo':'2026-13'},{'estado':'CONTABILIZADO'},{'sueldo_periodo':float('nan')},{'anticipo':float('inf')},{'trabajador_id':1.5}):
            with self.subTest(cambio=cambio),self.assertRaises(ValueError):self.guardar(**cambio)
        self.assertEqual(self.db.execute('SELECT count(*) FROM nomina_liquidaciones').fetchone()[0],0)

    def test_trabajador_inexistente_no_genera_periodo(self):
        with patch.dict(vars(servicio),{'sgci_rrhh_ids_autorizados':lambda *a:None}):
            with self.assertRaises(ValueError):self.guardar(trabajador_id=999)
        self.assertEqual(self.db.execute('SELECT count(*) FROM nomina_periodos').fetchone()[0],0)

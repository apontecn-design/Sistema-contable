import unittest
import sqlite3
from datetime import timedelta
from unittest.mock import patch
from modulos import conciliacion_documental as servicio,usuarios,utilidades
from tests.soporte_flujos import preparar


class TestReportesGlobalesRRHH(unittest.TestCase):
    def setUp(self):
        self.db=preparar(self)
        servicio.instalar_cuentas_nomina(self.db)
        self.db.executescript("""
            INSERT INTO nomina_trabajadores(id,rut,nombre) VALUES(1,'1-9','Propio'),(2,'2-7','Ajeno');
            INSERT INTO sgci_usuario_trabajador VALUES('finanzas@example.com',1);
            INSERT INTO sgci_alcance_rrhh VALUES('finanzas@example.com','todos');
            INSERT INTO nomina_periodos(periodo) VALUES('2026-11');
            INSERT INTO nomina_liquidaciones(periodo,trabajador_id,sueldo_periodo,total_imponible,total_haberes,liquido_periodo,saldo_pagar,estado)
                VALUES('2026-11',1,100,100,100,100,100,'CALCULADO'),('2026-11',2,200,200,200,200,200,'CALCULADO');
        """)
        p=patch.dict(vars(servicio),{'sgci_rrhh_ids_autorizados':usuarios.sgci_rrhh_ids_autorizados,'money':utilidades.money,'timedelta':timedelta})
        p.start();self.addCleanup(p.stop)

    def propios(self):
        self.db.execute("UPDATE sgci_alcance_rrhh SET alcance='propios'");self.db.commit()

    def test_global_autorizado_lee_periodos_resumen_y_totales_sin_escribir(self):
        antes=list(self.db.iterdump())
        self.assertEqual(servicio.rrhh_periodos_nomina(self.db)['periodo'].tolist(),['2026-11'])
        self.assertEqual(len(servicio.rrhh_resumen_nomina(self.db,'2026-11')),2)
        self.assertEqual(servicio.rrhh_totales_nomina(self.db,'2026-11').iloc[0]['haberes'],300)
        self.assertEqual(servicio.rrhh_pendientes_nomina(self.db)['periodo'].tolist(),['2026-11'])
        self.assertEqual(list(self.db.iterdump()),antes)

    def test_alcance_propio_bloquea_todas_las_consultas_globales_antes_de_leer_nomina(self):
        self.propios();consultas=[];self.db.set_trace_callback(consultas.append)
        llamadas=(lambda:servicio.rrhh_periodos_nomina(self.db),lambda:servicio.rrhh_resumen_nomina(self.db,'2026-11'),
                  lambda:servicio.rrhh_totales_nomina(self.db,'2026-11'),lambda:servicio.rrhh_pendientes_nomina(self.db),
                  lambda:servicio.nomina_vista_previa(self.db,'2026-11'))
        for llamada in llamadas:
            with self.assertRaises(PermissionError):llamada()
        self.db.set_trace_callback(None)
        self.assertFalse(any('FROM nomina_liquidaciones' in s or 'FROM nomina_periodos' in s for s in consultas))

    def test_permiso_contabilizacion_no_concede_resumen(self):
        self.db.execute("DELETE FROM sgci_perfil_permisos WHERE modulo='nomina' AND submodulo='Resumen y reportes'");self.db.commit()
        self.assertEqual(len(servicio.rrhh_periodos_nomina(self.db,'Contabilización')),1)
        with self.assertRaises(PermissionError):servicio.rrhh_resumen_nomina(self.db,'2026-11')

    def test_revocar_exportacion_no_impide_ver_pero_bloquea_generacion(self):
        self.db.execute("INSERT INTO sgci_usuario_permisos_detalle VALUES('finanzas@example.com','nomina','Resumen y reportes','exportar',0)");self.db.commit()
        self.assertEqual(len(servicio.rrhh_resumen_nomina(self.db,'2026-11')),2)
        consultas=[];self.db.set_trace_callback(consultas.append)
        with patch.dict(vars(servicio),{'nomina_pdf':lambda *a:self.fail('No debe generar PDF')}):
            for formato in ('csv','pdf'):
                with self.assertRaises(PermissionError):servicio.rrhh_exportar_resumen_nomina(self.db,'2026-11',formato)
        self.db.set_trace_callback(None)
        self.assertFalse(any('FROM nomina_liquidaciones' in s for s in consultas))

    def test_ver_revocado_prevalece_sobre_exportar(self):
        self.db.execute("INSERT INTO sgci_usuario_permisos_detalle VALUES('finanzas@example.com','nomina','Resumen y reportes','ver',0)");self.db.commit()
        with self.assertRaises(PermissionError):servicio.rrhh_exportar_resumen_nomina(self.db,'2026-11','csv')

    def test_exportaciones_autorizadas_conservan_filas_y_no_escriben(self):
        antes=list(self.db.iterdump())
        csv=servicio.rrhh_exportar_resumen_nomina(self.db,'2026-11','csv').decode('utf-8-sig')
        self.assertIn('Propio',csv);self.assertIn('Ajeno',csv)
        with patch.dict(vars(servicio),{'nomina_pdf':lambda titulo,sub,headers,filas,totales=None:(headers,filas,totales)}):
            headers,filas,totales=servicio.rrhh_exportar_resumen_nomina(self.db,'2026-11')
        self.assertEqual(len(headers),16);self.assertEqual(len(filas),2)
        self.assertEqual(totales[1],'TOTALES')
        self.assertEqual(list(self.db.iterdump()),antes)

    def test_historial_individual_respeta_alcance(self):
        self.propios()
        self.assertEqual(servicio.rrhh_historial_nomina(self.db,1)['total_haberes'].tolist(),[100])
        with self.assertRaises(PermissionError):servicio.rrhh_historial_nomina(self.db,2)
        with self.assertRaises(PermissionError):servicio.rrhh_exportar_historial_nomina(self.db,2)

    def test_historial_exportacion_revocada_no_consulta_importes(self):
        self.db.execute("INSERT INTO sgci_usuario_permisos_detalle VALUES('finanzas@example.com','nomina','Resumen y reportes','exportar',0)");self.db.commit()
        consultas=[];self.db.set_trace_callback(consultas.append)
        with self.assertRaises(PermissionError):servicio.rrhh_exportar_historial_nomina(self.db,1)
        self.db.set_trace_callback(None)
        self.assertFalse(any('FROM nomina_liquidaciones' in s for s in consultas))

    def test_periodo_o_formato_invalido_se_rechaza(self):
        with self.assertRaises(ValueError):servicio.rrhh_resumen_nomina(self.db,'2026-13')
        with self.assertRaises(ValueError):servicio.rrhh_exportar_resumen_nomina(self.db,'2026-11','otro')

    def test_contabilizacion_real_audita_una_vez_en_la_misma_transaccion(self):
        asiento=servicio.nomina_contabilizar_periodo(self.db,'2026-11')
        self.assertEqual(tuple(self.db.execute('SELECT SUM(debe),SUM(haber) FROM libro_diario WHERE asiento_id=?',(asiento,)).fetchone()),(300,300))
        self.assertEqual(self.db.execute("SELECT count(*) FROM auditoria WHERE accion='CONTABILIZAR NÓMINA'").fetchone()[0],1)
        with self.assertRaises(ValueError):servicio.nomina_contabilizar_periodo(self.db,'2026-11')

    def test_fallo_de_auditoria_revierte_contabilizacion_real_completa(self):
        self.db.execute("CREATE TRIGGER fallo_auditoria BEFORE INSERT ON auditoria BEGIN SELECT RAISE(ABORT,'Fallo de prueba'); END");self.db.commit()
        antes=list(self.db.iterdump())
        with self.assertRaises(sqlite3.IntegrityError):servicio.nomina_contabilizar_periodo(self.db,'2026-11')
        self.assertEqual(list(self.db.iterdump()),antes)

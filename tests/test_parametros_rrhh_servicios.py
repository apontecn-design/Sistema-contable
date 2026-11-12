import sqlite3
import unittest
from modulos import conciliacion_documental as servicio
from tests.soporte_flujos import preparar


class TestParametrosRRHH(unittest.TestCase):
    def setUp(self):self.db=preparar(self)

    def test_afp_autorizada_guarda_vigencia_y_audita(self):
        servicio.nomina_guardar_parametro_afp(self.db,'Uno',1.25,'2026-11-01')
        self.assertEqual(tuple(self.db.execute("SELECT comision,vigente_desde FROM nomina_parametros_afp WHERE afp='Uno'").fetchone()),(1.25,'2026-11-01'))
        self.assertEqual(self.db.execute('SELECT usuario FROM auditoria').fetchone()[0],'finanzas@example.com')

    def test_uf_crea_y_actualiza_sin_duplicar_periodo(self):
        servicio.nomina_guardar_valor_uf(self.db,'2026-11',40000.12)
        servicio.nomina_guardar_valor_uf(self.db,'2026-11',40001.23)
        self.assertEqual(self.db.execute('SELECT count(*) FROM nomina_parametros_mensuales').fetchone()[0],1)
        self.assertEqual(self.db.execute('SELECT valor_uf FROM nomina_parametros_mensuales').fetchone()[0],40001.23)
        self.assertEqual(self.db.execute('SELECT count(*) FROM libro_diario').fetchone()[0],0)

    def test_denegacion_individual_bloquea_antes_de_validacion(self):
        self.db.execute("INSERT INTO sgci_usuario_permisos_detalle VALUES('finanzas@example.com','nomina','Parámetros','editar',0)")
        self.db.commit()
        with self.assertRaises(PermissionError):servicio.nomina_guardar_parametro_afp(self.db,'Uno',-1)
        with self.assertRaises(PermissionError):servicio.nomina_guardar_valor_uf(self.db,'inválido',0)

    def test_otro_submodulo_no_concede_parametros(self):
        self.db.execute("DELETE FROM sgci_perfil_permisos WHERE modulo='nomina' AND submodulo='Parámetros'");self.db.commit()
        with self.assertRaises(PermissionError):servicio.nomina_guardar_valor_uf(self.db,'2026-11',40000)

    def test_afp_inexistente_fecha_invalida_o_comision_fuera_de_rango(self):
        for afp,comision,fecha in [('No existe',1,''),('Uno',-1,''),('Uno',11,''),('Uno',float('nan'),''),('Uno',1,'2026-02-30')]:
            with self.subTest(afp=afp,comision=comision),self.assertRaises(ValueError):servicio.nomina_guardar_parametro_afp(self.db,afp,comision,fecha)

    def test_uf_periodo_o_valor_invalido_no_se_guarda(self):
        for periodo,valor in [('2026-13',40000),('2026-11',0),('2026-11',-1),('2026-11',float('inf')),('2026-11','1e1000')]:
            with self.subTest(periodo=periodo,valor=valor),self.assertRaises(ValueError):servicio.nomina_guardar_valor_uf(self.db,periodo,valor)
        self.assertEqual(self.db.execute('SELECT count(*) FROM nomina_parametros_mensuales').fetchone()[0],0)

    def test_periodo_contabilizado_o_cierre_contable_bloquea_uf(self):
        self.db.execute("INSERT INTO nomina_periodos(periodo,estado,asiento_id) VALUES('2026-11','CONTABILIZADO',1)")
        self.db.execute("INSERT INTO periodos_contables(periodo,estado) VALUES('2026-12','CERRADO')");self.db.commit()
        for periodo in ('2026-11','2026-12'):
            with self.subTest(periodo=periodo),self.assertRaises(ValueError):servicio.nomina_guardar_valor_uf(self.db,periodo,40000)

    def test_fallo_auditoria_revierte_ambos_parametros(self):
        self.db.execute("CREATE TRIGGER fallo_auditoria BEFORE INSERT ON auditoria BEGIN SELECT RAISE(ABORT,'Fallo de prueba'); END");self.db.commit()
        antes=list(self.db.iterdump())
        with self.assertRaises(sqlite3.IntegrityError):servicio.nomina_guardar_parametro_afp(self.db,'Uno',1.25)
        with self.assertRaises(sqlite3.IntegrityError):servicio.nomina_guardar_valor_uf(self.db,'2026-11',40000)
        self.assertEqual(list(self.db.iterdump()),antes)

    def test_transaccion_ajena_se_conserva(self):
        self.db.execute("UPDATE bancos SET nombre='Pendiente' WHERE id=1")
        with self.assertRaises(RuntimeError):servicio.nomina_guardar_parametro_afp(self.db,'Uno',1.25)
        with self.assertRaises(RuntimeError):servicio.nomina_guardar_valor_uf(self.db,'2026-11',40000)
        self.assertTrue(self.db.in_transaction);self.db.rollback()

"""Alcance laboral en creación y reversión bancaria, con servicios y SQLite reales."""
import unittest
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

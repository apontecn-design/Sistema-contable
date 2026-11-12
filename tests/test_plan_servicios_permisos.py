import sqlite3
import unittest
from unittest.mock import patch
from modulos import plan_cuentas as servicio
from tests.soporte_flujos import preparar


class TestPlanAutorizado(unittest.TestCase):
    def setUp(self):self.db=preparar(self)

    def guardar(self,crear=True,**cambios):
        datos=dict(codigo='1.1.02.99',nombre='Banco sintético',categoria='Activo',tipo='Activo',padre_codigo='1.1.02',nivel=4)
        datos.update(cambios)
        return servicio.sgci_guardar_cuenta(self.db,**datos,crear=crear)

    def negar(self,accion):
        self.db.execute("INSERT INTO sgci_usuario_permisos_detalle VALUES('finanzas@example.com','contabilidad','Plan de Cuentas',?,0)",(accion,))
        self.db.commit()

    def test_crea_y_edita_con_auditoria_sin_asientos(self):
        codigo=self.guardar()
        self.guardar(False,nombre='Banco corregido')
        self.assertEqual(self.db.execute('SELECT nombre FROM plan_cuentas WHERE codigo=?',(codigo,)).fetchone()[0],'Banco corregido')
        self.assertEqual(self.db.execute('SELECT count(*) FROM auditoria').fetchone()[0],2)
        self.assertEqual(self.db.execute('SELECT count(*) FROM libro_diario').fetchone()[0],0)

    def test_categoria_historica_de_gastos_se_conserva_al_editar_nombre(self):
        self.guardar(codigo='5.2.99',categoria='Gastos',tipo='Gastos',padre_codigo='5.2',nivel=3)
        self.guardar(False,codigo='5.2.99',nombre='Nombre corregido',categoria='Gastos',tipo='Gastos',padre_codigo='5.2',nivel=3)
        self.assertEqual(tuple(self.db.execute("SELECT categoria,tipo FROM plan_cuentas WHERE codigo='5.2.99'").fetchone()),('Gastos','Gastos'))

    def test_denegacion_crear_precede_validacion_y_consultas_plan(self):
        self.negar('crear')
        consultas=[];self.db.set_trace_callback(consultas.append)
        with self.assertRaises(PermissionError):self.guardar(nombre='')
        self.db.set_trace_callback(None)
        self.assertFalse(any('FROM plan_cuentas' in sql or 'INTO plan_cuentas' in sql for sql in consultas))

    def test_revocacion_editar_no_cambia_registro(self):
        self.guardar();self.negar('editar')
        antes=list(self.db.iterdump())
        with self.assertRaises(PermissionError):self.guardar(False,nombre='Cambio prohibido')
        self.assertEqual(list(self.db.iterdump()),antes)

    def test_otro_submodulo_no_concede_edicion(self):
        self.guardar()
        self.db.execute("DELETE FROM sgci_perfil_permisos WHERE modulo='contabilidad' AND submodulo='Plan de Cuentas'")
        self.db.commit()
        with self.assertRaises(PermissionError):self.guardar(False)

    def test_no_admite_cuenta_padre_inexistente_o_circular(self):
        for padre in ('inexistente','1.1.02.99'):
            with self.subTest(padre=padre),self.assertRaises(ValueError):self.guardar(padre_codigo=padre)
        self.guardar()
        with self.assertRaises(ValueError):
            self.guardar(False,codigo='1.1.02',padre_codigo='1.1.02.99',nivel=3)

    def test_datos_vacios_nivel_o_clasificacion_invalidos(self):
        for cambio in ({'codigo':''},{'nombre':' '},{'nivel':0},{'nivel':1.5},{'nivel':True},{'tipo':'otro'},{'categoria':'otra'}):
            with self.subTest(cambio=cambio),self.assertRaises(ValueError):self.guardar(**cambio)

    def test_codigo_duplicado_no_genera_auditoria_adicional(self):
        self.guardar()
        with self.assertRaises(sqlite3.IntegrityError):self.guardar()
        self.assertEqual(self.db.execute('SELECT count(*) FROM auditoria').fetchone()[0],1)

    def test_editar_inexistente_no_crea_cuenta(self):
        with self.assertRaises(ValueError):self.guardar(False)

    def test_fallo_auditoria_revierte_creacion_y_edicion(self):
        self.guardar()
        self.db.execute("CREATE TRIGGER fallo_auditoria BEFORE INSERT ON auditoria BEGIN SELECT RAISE(ABORT,'Fallo de prueba'); END")
        self.db.commit()
        antes=list(self.db.iterdump())
        with self.assertRaises(sqlite3.IntegrityError):self.guardar(False,nombre='Cambio')
        with self.assertRaises(sqlite3.IntegrityError):self.guardar(codigo='1.1.02.98')
        self.assertEqual(list(self.db.iterdump()),antes)

    def test_no_confirma_ni_revierte_transaccion_ajena(self):
        self.db.execute("UPDATE bancos SET nombre='Pendiente' WHERE id=1")
        with self.assertRaises(RuntimeError):self.guardar()
        self.assertTrue(self.db.in_transaction)
        self.db.rollback()
        self.assertNotEqual(self.db.execute('SELECT nombre FROM bancos WHERE id=1').fetchone()[0],'Pendiente')

    def test_editar_conserva_codigo_y_movimientos_historicos(self):
        self.db.execute("INSERT INTO libro_diario(fecha,cuenta,debe,haber,codigo_cuenta,asiento_id) VALUES('2026-11-01','Banco',100,0,'1.1.02',1)")
        self.db.commit()
        antes=list(self.db.execute('SELECT * FROM libro_diario'))
        self.guardar(False,codigo='1.1.02',nombre='Nombre corregido',padre_codigo='1.1',nivel=3)
        self.assertEqual(list(self.db.execute('SELECT * FROM libro_diario')),antes)
        self.assertEqual(self.db.execute("SELECT count(*) FROM plan_cuentas WHERE codigo='1.1.02'").fetchone()[0],1)

    def test_exportacion_exige_ver_y_exportar_antes_de_generar_pdf(self):
        for accion in ('ver','exportar'):
            self.negar(accion)
            with patch.dict(vars(servicio),{'pdf_desde_dataframe':lambda *a:self.fail('No debe generar PDF')}):
                with self.assertRaises(PermissionError):servicio.sgci_exportar_plan(self.db)
            self.db.execute('DELETE FROM sgci_usuario_permisos_detalle');self.db.commit()

    def test_exportacion_autorizada_no_escribe(self):
        antes=list(self.db.iterdump())
        with patch.dict(vars(servicio),{'pdf_desde_dataframe':lambda titulo,subtitulo,df:df}):
            df=servicio.sgci_exportar_plan(self.db)
        self.assertIn('Código',df.columns)
        self.assertEqual(list(self.db.iterdump()),antes)

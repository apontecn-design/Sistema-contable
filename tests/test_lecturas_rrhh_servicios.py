import unittest
from unittest.mock import patch
from modulos import conciliacion_documental as servicio,usuarios
from tests.soporte_flujos import preparar


class TestLecturasRRHH(unittest.TestCase):
    def setUp(self):
        self.db=preparar(self)
        self.db.executescript("""
            INSERT INTO nomina_trabajadores(id,rut,nombre,sueldo_base) VALUES(1,'1-9','Propio',100),(2,'2-7','Ajeno',200);
            INSERT INTO sgci_usuario_trabajador VALUES('finanzas@example.com',1);
            INSERT INTO nomina_anticipos(id,trabajador_id,periodo,monto) VALUES(1,1,'2030-01',10),(2,2,'2030-01',20);
            INSERT INTO nomina_prestamos(id,trabajador_id,monto_original) VALUES(1,1,100),(2,2,200);
            INSERT INTO rrhh_vacaciones_movimientos(trabajador_id,fecha,tipo,dias,creado_en) VALUES(1,'2030-01-01','ASIGNACION',5,'2030-01-01'),(2,'2030-01-01','ASIGNACION',10,'2030-01-01');
            INSERT INTO nomina_historial_condiciones(trabajador_id,vigente_desde,sueldo_base) VALUES(1,'2030-01-01',100),(2,'2030-01-01',200);
        """)
        p=patch.dict(vars(servicio),{'sgci_rrhh_ids_autorizados':usuarios.sgci_rrhh_ids_autorizados})
        p.start();self.addCleanup(p.stop)

    def test_listados_filtran_trabajador_en_sql_y_vacaciones_no_devuelve_datos_bancarios(self):
        for sub in ('Trabajadores','Vacaciones','Anticipos y préstamos','Liquidación mensual'):
            with self.subTest(sub=sub):self.assertEqual(servicio.rrhh_listar_trabajadores(self.db,sub)['id'].tolist(),[1])
        self.assertEqual(list(servicio.rrhh_listar_trabajadores(self.db,'Vacaciones').columns),['id','rut','nombre'])

    def test_listados_movimientos_no_devuelven_registros_ajenos(self):
        for tipo in ('anticipos','prestamos'):
            with self.subTest(tipo=tipo):self.assertEqual(servicio.rrhh_listar_movimientos_nomina(self.db,tipo)['id'].tolist(),[1])

    def test_ficha_historial_documentos_y_vacaciones_rechazan_id_ajeno(self):
        llamadas=(servicio.rrhh_obtener_ficha,servicio.rrhh_historial_condiciones,servicio.rrhh_listar_documentos,servicio.rrhh_vacaciones_datos)
        for funcion in llamadas:
            with self.subTest(funcion=funcion.__name__),self.assertRaises(PermissionError):funcion(self.db,2)
        self.assertEqual(servicio.rrhh_obtener_ficha(self.db,1)['nombre'],'Propio')
        self.assertEqual(servicio.rrhh_historial_condiciones(self.db,1)['sueldo_base'].tolist(),[100])
        self.assertEqual(servicio.rrhh_vacaciones_datos(self.db,1)['dias'].tolist(),[5])

    def test_revocacion_ver_precede_consultas_personales(self):
        self.db.execute("INSERT INTO sgci_usuario_permisos_detalle VALUES('finanzas@example.com','nomina','Trabajadores','ver',0)");self.db.commit()
        consultas=[];self.db.set_trace_callback(consultas.append)
        with self.assertRaises(PermissionError):servicio.rrhh_listar_trabajadores(self.db)
        with self.assertRaises(PermissionError):servicio.rrhh_obtener_ficha(self.db,1)
        self.db.set_trace_callback(None)
        self.assertFalse(any('FROM nomina_trabajadores' in sql for sql in consultas))

    def test_sin_vinculo_no_devuelve_fichas_ni_movimientos(self):
        self.db.execute('DELETE FROM sgci_usuario_trabajador');self.db.commit()
        self.assertTrue(servicio.rrhh_listar_trabajadores(self.db).empty)
        self.assertTrue(servicio.rrhh_listar_movimientos_nomina(self.db,'anticipos').empty)

    def test_exportar_ficha_exige_permiso_antes_de_cargar_historial_o_generar_pdf(self):
        self.db.execute("INSERT INTO sgci_usuario_permisos_detalle VALUES('finanzas@example.com','nomina','Trabajadores','exportar',0)");self.db.commit()
        consultas=[];self.db.set_trace_callback(consultas.append)
        with patch.dict(vars(servicio),{'nomina_pdf':lambda *a:self.fail('No debe generar PDF')}):
            with self.assertRaises(PermissionError):servicio.rrhh_exportar_ficha(self.db,1)
        self.db.set_trace_callback(None)
        self.assertFalse(any('FROM nomina_historial_condiciones' in sql or 'SELECT * FROM nomina_trabajadores' in sql for sql in consultas))

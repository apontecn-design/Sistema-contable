import re
import unittest
from unittest.mock import patch
from modulos import conciliacion_documental as servicio,usuarios
from tests.soporte_flujos import preparar


class TestListadosBancoPermisos(unittest.TestCase):
    def setUp(self):
        self.db=preparar(self)
        p=patch.dict(vars(servicio),{'sgci_rrhh_ids_autorizados':usuarios.sgci_rrhh_ids_autorizados})
        p.start();self.addCleanup(p.stop)
        self.db.executescript("""
            INSERT INTO clientes(id,rut,nombre,razon_social) VALUES(1,'1-9','Cliente prueba','Cliente autorizado');
            INSERT INTO nomina_trabajadores(id,rut,nombre,activo) VALUES(1,'1-9','Trabajador propio',1),(2,'2-7','Trabajador ajeno',1);
            INSERT INTO nomina_anticipos(id,trabajador_id,periodo,fecha,monto) VALUES(1,1,'2026-11','2026-11-01',100),(2,2,'2026-11','2026-11-01',100);
            INSERT INTO sgci_usuario_trabajador VALUES('finanzas@example.com',1);
        """)
        tipos=[None,'CLIENTE','CLIENTE_ANTICIPO','PROVEEDOR','PROVEEDOR_SIN_DOCUMENTO','DEVOLUCION_PROVEEDOR','TESORERIA','NOMINA_ANTICIPO','NOMINA_ANTICIPO','IMPUTACION_MANUAL']
        for i,tipo in enumerate(tipos,1):
            self.db.execute("INSERT INTO cartola_bancaria(id,banco_id,fecha,descripcion,cargo,abono,saldo,conciliado,match_tipo,match_id) VALUES(?,1,'2026-11-16',?,100,100,1000,1,?,?)",
                (i,f'MOV-{i}',tipo,2 if i==9 else 1))
        self.db.commit()

    def denegar(self,mod,sub):
        self.db.execute('INSERT INTO sgci_usuario_permisos_detalle VALUES(?,?,?,?,0)',('finanzas@example.com',mod,sub,'ver'));self.db.commit()

    def movs(self):return set(servicio.banco_movimientos_autorizados(self.db,1).descripcion)

    def test_movimientos_filtran_alcance_laboral_y_omiten_saldos(self):
        df=servicio.banco_movimientos_autorizados(self.db,1)
        self.assertIn('MOV-8',set(df.descripcion));self.assertNotIn('MOV-9',set(df.descripcion))
        self.assertTrue(df.attrs['vista_restringida']);self.assertTrue(df.saldo.isna().all())

    def test_sin_lectura_nomina_no_consulta_anticipos(self):
        self.denegar('nomina','Anticipos y préstamos');consultas=[];self.db.set_trace_callback(consultas.append)
        movs=self.movs();self.db.set_trace_callback(None)
        self.assertFalse({'MOV-8','MOV-9'}&movs)
        self.assertFalse(any('FROM nomina_anticipos' in q for q in consultas))

    def test_cada_auxiliar_filtra_sus_tipos_sin_afectar_otros(self):
        for mod,sub,ocultos in [('cxc','Pagos de clientes',{'MOV-2','MOV-3'}),('cxp','Pagos de proveedores',{'MOV-4','MOV-5','MOV-6'}),('tesoreria','Historial',{'MOV-7'})]:
            with self.subTest(mod=mod):
                self.denegar(mod,sub);movs=self.movs()
                self.assertFalse(movs&ocultos);self.assertIn('MOV-1',movs);self.assertIn('MOV-10',movs)
                self.db.execute('DELETE FROM sgci_usuario_permisos_detalle');self.db.commit()

    def test_propietario_conserva_todos_los_movimientos_y_saldos(self):
        with patch.object(usuarios,'sgci_es_propietario',return_value=True):
            df=servicio.banco_movimientos_autorizados(self.db,1)
        self.assertEqual(len(df),10);self.assertFalse(df.attrs['vista_restringida']);self.assertTrue((df.saldo==1000).all())

    def test_alcance_todos_permite_ambos_trabajadores(self):
        self.db.execute("INSERT INTO sgci_alcance_rrhh VALUES('finanzas@example.com','todos')");self.db.commit()
        self.assertTrue({'MOV-8','MOV-9'}<=self.movs())

    def test_alcance_sin_trabajadores_no_muestra_nomina(self):
        self.db.execute('DELETE FROM sgci_usuario_trabajador');self.db.commit()
        self.assertFalse({'MOV-8','MOV-9'}&self.movs())

    def test_reversos_nomina_filtran_antes_de_devolver_nombres(self):
        df=servicio.banco_reversibles_nomina(self.db,1)
        self.assertEqual(df.id.tolist(),[8]);self.assertEqual(df.trabajador.tolist(),['Trabajador propio'])
        self.db.execute("UPDATE sgci_usuario_trabajador SET trabajador_id=2");self.db.commit()
        self.assertEqual(servicio.banco_reversibles_nomina(self.db,1).id.tolist(),[9])

    def test_revocacion_individual_tiene_efecto_en_siguiente_consulta(self):
        self.assertIn('MOV-2',self.movs());self.denegar('cxc','Pagos de clientes')
        self.assertNotIn('MOV-2',self.movs())
        self.db.execute('DELETE FROM sgci_usuario_permisos_detalle');self.db.commit()
        self.assertIn('MOV-2',self.movs())

    def test_variantes_de_mayusculas_no_eluden_filtros(self):
        self.db.execute('UPDATE cartola_bancaria SET match_tipo=LOWER(match_tipo)');self.db.commit()
        self.denegar('cxc','Pagos de clientes')
        self.assertFalse({'MOV-2','MOV-3','MOV-9'}&self.movs())

    def test_listados_exigen_permiso_antes_de_leer_datos(self):
        casos=[('banco','Bancos y cartolas',lambda:servicio.banco_cuentas_movimientos(self.db)),
               ('banco','Bancos y cartolas',lambda:servicio.banco_movimientos_autorizados(self.db,1)),
               ('cxp','Pagos de proveedores',lambda:servicio.banco_reversibles_proveedor(self.db,1)),
               ('cxc','Pagos de clientes',lambda:servicio.banco_reversibles_cliente(self.db,1)),
               ('nomina','Anticipos y préstamos',lambda:servicio.banco_reversibles_nomina(self.db,1)),
               ('banco','Conciliación bancaria',lambda:servicio.banco_corregibles_manual(self.db,1))]
        for mod,sub,op in casos:
            with self.subTest(mod=mod,sub=sub):
                self.denegar(mod,sub);consultas=[];self.db.set_trace_callback(consultas.append)
                with self.assertRaises(PermissionError):op()
                self.db.set_trace_callback(None)
                self.assertFalse(any(re.search(r'\b(?:FROM|JOIN)\s+(?:bancos|cartola_bancaria|clientes|nomina_anticipos|nomina_trabajadores)\b',q,re.I) for q in consultas))
                self.db.execute('DELETE FROM sgci_usuario_permisos_detalle');self.db.commit()

    def test_reversos_auxiliares_exigen_tambien_lectura_bancaria(self):
        self.denegar('banco','Conciliación bancaria')
        for op in (servicio.banco_reversibles_proveedor,servicio.banco_reversibles_cliente,servicio.banco_reversibles_nomina):
            with self.assertRaises(PermissionError):op(self.db,1)

    def test_listados_autorizados_preservan_proyecciones_y_filtro_de_banco(self):
        self.assertEqual(set(servicio.banco_reversibles_proveedor(self.db,1).id),{4,5})
        self.assertEqual(servicio.banco_reversibles_cliente(self.db,1).id.tolist(),[3])
        self.assertEqual(servicio.banco_corregibles_manual(self.db,1).id.tolist(),[10])
        self.assertTrue(servicio.banco_movimientos_autorizados(self.db,999).empty)
        self.assertTrue(servicio.banco_reversibles_cliente(self.db,999).empty)

    def test_lecturas_no_confirman_transaccion_ajena(self):
        self.db.execute("UPDATE bancos SET nombre='Pendiente'");antes=list(self.db.iterdump())
        servicio.banco_cuentas_movimientos(self.db);self.movs()
        servicio.banco_reversibles_proveedor(self.db,1);servicio.banco_reversibles_cliente(self.db,1)
        servicio.banco_reversibles_nomina(self.db,1);servicio.banco_corregibles_manual(self.db,1)
        self.assertEqual(list(self.db.iterdump()),antes);self.assertTrue(self.db.in_transaction);self.db.rollback()

    def test_secciones_respetan_submodulos_independientes(self):
        self.assertEqual(len(servicio.banco_secciones_autorizadas(self.db)),6)
        self.denegar('banco','Conciliación bancaria')
        self.assertEqual([x[0] for x in servicio.banco_secciones_autorizadas(self.db)],['Cuentas bancarias','Cargar cartola','Movimiento manual','Movimientos'])
        self.db.execute('DELETE FROM sgci_usuario_permisos_detalle');self.db.commit()
        self.denegar('banco','Bancos y cartolas')
        self.assertEqual([x[0] for x in servicio.banco_secciones_autorizadas(self.db)],['Conciliación','Operaciones manuales'])

    def test_sin_secciones_autorizadas_no_se_ofrece_menu_bancario(self):
        self.denegar('banco','Bancos y cartolas');self.denegar('banco','Conciliación bancaria')
        self.assertEqual(servicio.banco_secciones_autorizadas(self.db),[])


if __name__=='__main__':unittest.main()

import unittest
import re
from modulos import reportes_contables as servicio
from tests.soporte_flujos import preparar


class TestPanelInicio(unittest.TestCase):
    def setUp(self):
        self.db=preparar(self)

    def solo_inicio(self):
        self.db.execute("DELETE FROM sgci_perfil_permisos WHERE modulo!='inicio'")
        self.db.commit()

    def conceder(self,modulo,sub):
        self.db.execute('INSERT INTO sgci_perfil_permisos VALUES(?,?,?,?,1)',('Finanzas',modulo,sub,'ver'))

    def test_inicio_solo_no_consulta_tablas_de_negocio(self):
        self.solo_inicio(); consultas=[]
        self.db.set_trace_callback(consultas.append)
        panel=servicio.panel_inicio_datos(self.db,'2026-11')
        self.db.set_trace_callback(None)
        self.assertTrue(all(v is None or v is False for v in panel.values()))
        tablas=('libro_diario','bancos','cartola_bancaria','tes_solicitudes','compras','proveedores')
        self.assertFalse(any(re.search(r'\b(?:FROM|JOIN)\s+(?:'+ '|'.join(tablas)+r')\b',q,re.I) for q in consultas))

    def test_sin_inicio_deniega(self):
        self.db.execute("DELETE FROM sgci_perfil_permisos WHERE modulo='inicio'")
        with self.assertRaises(PermissionError):servicio.panel_inicio_datos(self.db,'2026-11')

    def test_finanzas_no_concede_diario_ni_bancos(self):
        self.solo_inicio();self.conceder('contabilidad','Estados Financieros')
        panel=servicio.panel_inicio_datos(self.db,'2026-11')
        self.assertEqual(panel['ingresos'],0)
        self.assertEqual(panel['gastos'],0)
        self.assertIsNotNone(panel['flujo'])
        self.assertIsNotNone(panel['categorias'])
        for campo in ('actividad','saldo_banco','solicitudes','pendientes'):self.assertIsNone(panel[campo])

    def test_bancos_no_concede_conciliacion(self):
        self.solo_inicio();self.conceder('banco','Bancos y cartolas')
        panel=servicio.panel_inicio_datos(self.db,'2026-11')
        self.assertEqual(panel['saldo_banco'],0)
        self.assertIsNone(panel['pendientes_cartola'])

    def test_conciliacion_no_concede_saldo(self):
        self.solo_inicio();self.conceder('banco','Conciliación bancaria')
        panel=servicio.panel_inicio_datos(self.db,'2026-11')
        self.assertEqual(panel['pendientes_cartola'],0)
        self.assertIsNone(panel['saldo_banco'])

    def test_componentes_independientes(self):
        for modulo,sub,campo in (('contabilidad','Libro Diario','actividad'),('tesoreria','Historial','solicitudes'),('cxp','Proveedores y estados de cuenta','pendientes')):
            with self.subTest(sub=sub):
                self.solo_inicio();self.conceder(modulo,sub)
                panel=servicio.panel_inicio_datos(self.db,'2026-11')
                self.assertIsNotNone(panel[campo])
                self.assertIsNone(panel['ingresos'])

    def test_excepcion_y_revocacion_tienen_efecto_en_siguiente_consulta(self):
        self.assertIsNotNone(servicio.panel_inicio_datos(self.db,'2026-11')['actividad'])
        self.db.execute("INSERT INTO sgci_usuario_permisos_detalle VALUES('finanzas@example.com','contabilidad','Libro Diario','ver',0)")
        self.assertIsNone(servicio.panel_inicio_datos(self.db,'2026-11')['actividad'])
        self.db.execute('DELETE FROM sgci_usuario_permisos_detalle')
        self.assertIsNotNone(servicio.panel_inicio_datos(self.db,'2026-11')['actividad'])

    def test_lectura_preserva_datos_y_transaccion_pendiente(self):
        self.db.execute("UPDATE proveedores SET nombre='Cambio pendiente' WHERE id=1")
        antes=list(self.db.iterdump())
        servicio.panel_inicio_datos(self.db,'2026-11')
        self.assertEqual(list(self.db.iterdump()),antes)
        self.assertTrue(self.db.in_transaction)
        self.db.rollback()
        self.assertEqual(self.db.execute('SELECT nombre FROM proveedores WHERE id=1').fetchone()[0],'Proveedor de prueba')

    def test_periodo_invalido(self):
        for periodo in ('2026-13','2026-1',None,"2026-11' OR 1=1"):
            with self.subTest(periodo=periodo),self.assertRaises(ValueError):servicio.panel_inicio_datos(self.db,periodo)

    def test_importes_y_periodos_preservan_el_calculo_del_panel(self):
        self.db.executemany('INSERT INTO libro_diario(fecha,codigo_cuenta,debe,haber) VALUES(?,?,?,?)',[
            ('2026-11-01','4.1',0,1000),('2026-11-02','4.1',100,0),
            ('2026-11-03','5.1',300,0),('2026-11-04','6.1',50,0),
            ('2026-10-01','4.1',0,2000),('2026-11-05','1.1.02',800,0)])
        panel=servicio.panel_inicio_datos(self.db,'2026-11')
        self.assertEqual((panel['ingresos'],panel['gastos'],panel['saldo_banco']),(900,350,800))
        flujo=panel['flujo'].set_index('mes')
        self.assertEqual(flujo.loc['2026-10','Ingresos'],2000)
        self.assertEqual(flujo.loc['2026-11','Egresos'],350)
        self.assertEqual(panel['categorias']['Monto'].sum(),350)
        self.assertEqual(len(panel['actividad']),6)


if __name__=='__main__':unittest.main()

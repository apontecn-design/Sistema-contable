"""Pruebas de acceso denegado en operaciones reales de Compras, Ventas y Bancos.

Sin credenciales ni bases de producción; comprueba autorización previa a
consultas y escrituras. Los flujos contables exitosos requieren pruebas aparte.
"""
import sqlite3
import unittest
from unittest.mock import patch
from modulos import usuarios, compras_rcv, ventas_dte, contabilidad_asientos


class TestOperacionesInternas(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript("""
            CREATE TABLE sgci_usuarios(email TEXT PRIMARY KEY, rol TEXT, activo INTEGER);
            CREATE TABLE sgci_permisos(email TEXT, modulo TEXT, accion TEXT, permitido INTEGER);
            CREATE TABLE sgci_perfil_permisos(perfil TEXT, modulo TEXT, submodulo TEXT, accion TEXT, permitido INTEGER);
            CREATE TABLE sgci_usuario_permisos_detalle(email TEXT, modulo TEXT, submodulo TEXT, accion TEXT, permitido INTEGER);
            INSERT INTO sgci_usuarios VALUES('empleado@example.com','Operaciones',1);
        """)
        self.patches = [
            patch.object(usuarios,'sgci_es_propietario',return_value=False),
            patch.object(usuarios,'sgci_identidad_actual',return_value='empleado@example.com'),
        ]
        for p in self.patches: p.start()
        self.globals_patches=[]
        for func in (
            compras_rcv.recuperar_datos_tributarios_rcv,
            ventas_dte.dte_guardar,
            ventas_dte.tes_conciliar_pago,
            contabilidad_asientos.contabilizar_rcv,
        ):
            p=patch.dict(func.__globals__,{'sgci_autorizar_operacion':usuarios.sgci_autorizar_operacion})
            p.start()
            self.globals_patches.append(p)

    def tearDown(self):
        for p in reversed(self.globals_patches): p.stop()
        for p in reversed(self.patches): p.stop()
        self.conn.close()

    def test_compras_rcv_rechaza_sin_permiso(self):
        with self.assertRaises(PermissionError):
            compras_rcv.recuperar_datos_tributarios_rcv(self.conn,None)

    def test_ventas_importacion_xml_rechaza_sin_permiso(self):
        with self.assertRaises(PermissionError):
            ventas_dte.dte_guardar(self.conn,b'<DTE/>','prueba.xml')

    def test_bancos_conciliacion_rechaza_sin_permiso(self):
        with self.assertRaises(PermissionError):
            ventas_dte.tes_conciliar_pago(self.conn,1,1)

    def test_contabilizacion_compras_rechaza_sin_permiso(self):
        with self.assertRaises(PermissionError):
            contabilidad_asientos.contabilizar_rcv(self.conn,'compras',[])

    def test_contabilizacion_ventas_rechaza_sin_permiso(self):
        with self.assertRaises(PermissionError):
            contabilidad_asientos.contabilizar_rcv(self.conn,'ventas',[])

    def test_tipo_rcv_invalido_rechazado(self):
        with self.assertRaises(ValueError):
            contabilidad_asientos.contabilizar_rcv(self.conn,'invalido',[])

    def test_permisos_heredados_no_bastan_para_mutar(self):
        self.conn.execute("""INSERT INTO sgci_permisos VALUES
            ('empleado@example.com','cxp','contabilizar',1)""")
        self.conn.commit()
        with self.assertRaises(PermissionError):
            contabilidad_asientos.contabilizar_rcv(self.conn,'compras',[])


if __name__ == '__main__':
    unittest.main()

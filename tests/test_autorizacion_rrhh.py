"""Pruebas de autorización: solo datos propios, permisos y denegación por defecto."""
import sqlite3
import unittest

from sgci_rrhh_autorizacion import permiso_efectivo, ids_permitidos
from sgci_rrhh_seguridad import AccesoDenegado, obtener_trabajador, obtener_liquidacion, listar_liquidaciones


class TestAutorizacionRRHH(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript('''
            CREATE TABLE sgci_usuarios(email TEXT PRIMARY KEY, rol TEXT, activo INTEGER);
            CREATE TABLE sgci_perfil_permisos(perfil TEXT, modulo TEXT, submodulo TEXT, accion TEXT, permitido INTEGER);
            CREATE TABLE sgci_usuario_permisos_detalle(email TEXT, modulo TEXT, submodulo TEXT, accion TEXT, permitido INTEGER);
            CREATE TABLE sgci_alcance_rrhh(email TEXT, alcance TEXT);
            CREATE TABLE sgci_usuario_trabajador(email TEXT, trabajador_id INTEGER);
            CREATE TABLE sgci_rrhh_autorizados(email TEXT, trabajador_id INTEGER);
            CREATE TABLE nomina_trabajadores(id INTEGER PRIMARY KEY, nombre TEXT);
            CREATE TABLE nomina_liquidaciones(id INTEGER PRIMARY KEY, periodo TEXT, trabajador_id INTEGER);
            INSERT INTO sgci_usuarios VALUES('empleado@example.com','Personal',1);
            INSERT INTO sgci_perfil_permisos VALUES('Personal','nomina','Trabajadores','ver',1);
            INSERT INTO sgci_perfil_permisos VALUES('Personal','nomina','Liquidación mensual','ver',1);
            INSERT INTO sgci_perfil_permisos VALUES('Personal','nomina','Liquidación mensual','exportar',1);
            INSERT INTO sgci_usuario_trabajador VALUES('empleado@example.com',1);
            INSERT INTO nomina_trabajadores VALUES(1,'Empleado propio');
            INSERT INTO nomina_trabajadores VALUES(2,'Otro empleado');
            INSERT INTO nomina_liquidaciones VALUES(10,'2026-10',1);
            INSERT INTO nomina_liquidaciones VALUES(20,'2026-10',2);
        ''')
        self.email = 'empleado@example.com'

    def tearDown(self): self.conn.close()

    def test_solo_datos_propios_por_defecto(self):
        self.assertEqual(ids_permitidos(self.conn,self.email), {1})
        self.assertEqual([r['id'] for r in listar_liquidaciones(self.conn,self.email)], [10])
        self.assertEqual(obtener_trabajador(self.conn,self.email,1)['nombre'],'Empleado propio')
        with self.assertRaises(AccesoDenegado): obtener_trabajador(self.conn,self.email,2)
        with self.assertRaises(AccesoDenegado): obtener_liquidacion(self.conn,self.email,20)

    def test_exportacion_exige_ver_y_exportar(self):
        self.assertEqual(obtener_liquidacion(self.conn,self.email,10,'exportar')['id'],10)
        self.conn.execute("UPDATE sgci_perfil_permisos SET permitido=0 WHERE accion='ver' AND submodulo='Liquidación mensual'")
        with self.assertRaises(AccesoDenegado): obtener_liquidacion(self.conn,self.email,10,'exportar')

    def test_denegacion_individual_prevalece(self):
        self.conn.execute("INSERT INTO sgci_usuario_permisos_detalle VALUES(?, 'nomina','Liquidación mensual','ver',0)",(self.email,))
        with self.assertRaises(AccesoDenegado): listar_liquidaciones(self.conn,self.email)

    def test_usuario_inactivo(self):
        self.conn.execute("UPDATE sgci_usuarios SET activo=0 WHERE email=?",(self.email,))
        self.assertFalse(permiso_efectivo(self.conn,self.email,'Liquidaciones'))
        with self.assertRaises(AccesoDenegado): listar_liquidaciones(self.conn,self.email)

    def test_sin_vinculo_no_autoriza(self):
        self.conn.execute('DELETE FROM sgci_usuario_trabajador')
        with self.assertRaises(AccesoDenegado): listar_liquidaciones(self.conn,self.email)

    def test_autorizados_no_equivale_a_todos(self):
        self.conn.execute("INSERT INTO sgci_alcance_rrhh VALUES(?,'autorizados')",(self.email,))
        self.assertEqual(ids_permitidos(self.conn,self.email),{1})
        self.conn.execute('INSERT INTO sgci_rrhh_autorizados VALUES(?,2)',(self.email,))
        self.assertEqual(ids_permitidos(self.conn,self.email),{1,2})

    def test_otro_usuario_no_hereda_vinculo_ajeno(self):
        self.conn.execute("INSERT INTO sgci_usuarios VALUES('otro@example.com','Personal',1)")
        self.assertEqual(ids_permitidos(self.conn,'otro@example.com'),set())
        with self.assertRaises(AccesoDenegado):
            listar_liquidaciones(self.conn,'otro@example.com')
        with self.assertRaises(AccesoDenegado):
            obtener_liquidacion(self.conn,'otro@example.com',10)

    def test_solo_ver_no_autoriza_exportacion(self):
        self.conn.execute("""UPDATE sgci_perfil_permisos SET permitido=0
                             WHERE accion='exportar' AND submodulo='Liquidación mensual'""")
        self.assertEqual(obtener_liquidacion(self.conn,self.email,10)['id'],10)
        with self.assertRaises(AccesoDenegado):
            obtener_liquidacion(self.conn,self.email,10,'exportar')

    def test_reasignacion_vinculo_revoca_acceso_anterior(self):
        self.assertEqual(ids_permitidos(self.conn,self.email),{1})
        self.conn.execute("""UPDATE sgci_usuario_trabajador SET trabajador_id=2
                             WHERE email=?""",(self.email,))
        self.assertEqual(ids_permitidos(self.conn,self.email),{2})
        with self.assertRaises(AccesoDenegado):
            obtener_liquidacion(self.conn,self.email,10)
        self.assertEqual(obtener_liquidacion(self.conn,self.email,20)['id'],20)

    def test_desactivacion_revoca_exportacion(self):
        self.conn.execute("UPDATE sgci_usuarios SET activo=0 WHERE email=?",(self.email,))
        with self.assertRaises(AccesoDenegado):
            obtener_liquidacion(self.conn,self.email,10,'exportar')

    def test_modulo_y_accion_no_validos_denegados(self):
        self.assertFalse(permiso_efectivo(self.conn,self.email,'Inexistente'))
        with self.assertRaises(AccesoDenegado): obtener_liquidacion(self.conn,self.email,10,'eliminar')


if __name__ == '__main__': unittest.main()

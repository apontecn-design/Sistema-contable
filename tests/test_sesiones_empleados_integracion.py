"""Pruebas de sesiones simuladas contra las funciones reales de permisos de CONTEM."""
import os
import sqlite3
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from modulos import usuarios


class TestSesionesEmpleados(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:')
        self.db.row_factory=sqlite3.Row
        self.db.execute('CREATE TABLE nomina_trabajadores(id INTEGER PRIMARY KEY)')
        usuarios.sgci_crear_seguridad(self.db)
        self.db.execute("""INSERT INTO sgci_usuarios(email,rol,activo)
                           VALUES('empleado@example.com','Ventas',1)""")
        self.db.execute("""INSERT INTO sgci_perfil_permisos
            (perfil,modulo,submodulo,accion,permitido)
            VALUES('Ventas','cxc','RCV Ventas','contabilizar',1)""")
        self.db.commit()
        self.sesion={'sgci_sb_email':'empleado@example.com','sgci_auth_tipo':'supabase'}
        self.patcher=patch.dict(usuarios.sgci_puede.__globals__,
            {'st':SimpleNamespace(session_state=self.sesion),
             'os':os})
        self.patcher.start()
        self.env=patch.dict(os.environ,{'SGCI_ADMIN_EMAIL':'admin@example.com'})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.patcher.stop()
        self.db.close()

    def test_permiso_de_perfil_y_denegacion_otra_accion(self):
        usuarios.sgci_autorizar_operacion(self.db,'cxc','contabilizar','RCV Ventas')
        with self.assertRaises(PermissionError):
            usuarios.sgci_autorizar_operacion(self.db,'cxp','contabilizar','RCV Compras')

    def test_excepcion_individual_deniega_perfil(self):
        self.db.execute("""INSERT INTO sgci_usuario_permisos_detalle
            VALUES('empleado@example.com','cxc','RCV Ventas','contabilizar',0)""")
        with self.assertRaises(PermissionError):
            usuarios.sgci_autorizar_operacion(self.db,'cxc','contabilizar','RCV Ventas')

    def test_excepcion_individual_concede_sin_perfil(self):
        self.db.execute("""INSERT INTO sgci_usuario_permisos_detalle
            VALUES('empleado@example.com','cxp','RCV Compras','contabilizar',1)""")
        usuarios.sgci_autorizar_operacion(self.db,'cxp','contabilizar','RCV Compras')

    def test_inactivo_bloqueado_aun_con_perfil(self):
        self.db.execute("UPDATE sgci_usuarios SET activo=0")
        with self.assertRaises(PermissionError):
            usuarios.sgci_autorizar_operacion(self.db,'cxc','contabilizar','RCV Ventas')

    def test_sin_sesion_denegado(self):
        self.sesion['sgci_sb_email']=''
        with self.assertRaises(PermissionError):
            usuarios.sgci_autorizar_operacion(self.db,'cxc','contabilizar','RCV Ventas')

    def test_sin_vinculo_rrhh_no_puede_ver_otros(self):
        self.assertEqual(usuarios.sgci_rrhh_ids_autorizados(
            self.db,'empleado@example.com'),set())
        self.db.execute('INSERT INTO nomina_trabajadores VALUES(1),(2)')
        self.db.execute("""INSERT INTO sgci_usuario_trabajador
            VALUES('empleado@example.com',1)""")
        self.assertEqual(usuarios.sgci_rrhh_ids_autorizados(
            self.db,'empleado@example.com'),{1})

    def test_propietario_es_excepcion_controlada(self):
        self.sesion['sgci_sb_email']='admin@example.com'
        usuarios.sgci_autorizar_operacion(self.db,'cxc','contabilizar','RCV Ventas')


if __name__=='__main__':
    unittest.main()

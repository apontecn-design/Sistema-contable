"""Pruebas de consistencia entre menú y matriz de permisos.

No se habilita navegación administrativa de empleados con estas pruebas.
"""
import sqlite3
import unittest
from unittest.mock import patch

from modulos import usuarios


class TestMenuPermisos(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            CREATE TABLE sgci_usuarios(email TEXT PRIMARY KEY, rol TEXT, activo INTEGER);
            CREATE TABLE sgci_permisos(email TEXT, modulo TEXT, accion TEXT, permitido INTEGER);
            CREATE TABLE sgci_perfil_permisos(perfil TEXT, modulo TEXT, submodulo TEXT, accion TEXT, permitido INTEGER);
            CREATE TABLE sgci_usuario_permisos_detalle(email TEXT, modulo TEXT, submodulo TEXT, accion TEXT, permitido INTEGER);
            INSERT INTO sgci_usuarios VALUES('test@example.com','Ventas',1);
            INSERT INTO sgci_permisos VALUES('test@example.com','cxc','ver',1);
        """)
        self.owner = patch.object(usuarios, "sgci_es_propietario", return_value=False, create=True)
        self.identity = patch.object(usuarios, "sgci_identidad_actual", return_value="test@example.com", create=True)
        self.owner.start()
        self.identity.start()

    def tearDown(self):
        self.owner.stop()
        self.identity.stop()
        self.db.close()

    def test_legacy_menu_without_matrix(self):
        self.assertTrue(usuarios.sgci_puede(self.db, "cxc", "ver"))

    def test_profile_grant_enables_module(self):
        self.db.execute("""INSERT INTO sgci_perfil_permisos VALUES
            ('Ventas','cxc','Clientes y estados de cuenta','ver',1)""")
        self.assertTrue(usuarios.sgci_puede(self.db, "cxc", "ver"))

    def test_individual_denial_overrides_legacy(self):
        self.db.execute("""INSERT INTO sgci_perfil_permisos VALUES
            ('Ventas','cxc','Clientes y estados de cuenta','ver',1)""")
        self.db.execute("""INSERT INTO sgci_usuario_permisos_detalle VALUES
            ('test@example.com','cxc','Clientes y estados de cuenta','ver',0)""")
        self.assertFalse(usuarios.sgci_puede(self.db, "cxc", "ver"))

    def test_profile_denial_overrides_legacy(self):
        self.db.execute("""INSERT INTO sgci_perfil_permisos VALUES
            ('Ventas','cxc','Clientes y estados de cuenta','ver',0)""")
        self.assertFalse(usuarios.sgci_puede(self.db, "cxc", "ver"))

    def test_mutation_requires_explicit_submodule_permission(self):
        self.db.execute("""INSERT INTO sgci_permisos VALUES
            ('test@example.com','cxc','editar',1)""")
        self.db.execute("""INSERT INTO sgci_perfil_permisos VALUES
            ('Ventas','cxc','Clientes y estados de cuenta','editar',0)""")
        with self.assertRaises(PermissionError):
            usuarios.sgci_autorizar_operacion(
                self.db, 'cxc', 'editar', 'Clientes y estados de cuenta'
            )

    def test_mutation_with_specific_permission(self):
        self.db.execute("""INSERT INTO sgci_perfil_permisos VALUES
            ('Ventas','cxc','Clientes y estados de cuenta','editar',1)""")
        self.assertIsNone(usuarios.sgci_autorizar_operacion(
            self.db, 'cxc', 'editar', 'Clientes y estados de cuenta'
        ))

    def test_mutation_denial_override(self):
        self.db.execute("""INSERT INTO sgci_perfil_permisos VALUES
            ('Ventas','cxc','Clientes y estados de cuenta','editar',1)""")
        self.db.execute("""INSERT INTO sgci_usuario_permisos_detalle VALUES
            ('test@example.com','cxc','Clientes y estados de cuenta','editar',0)""")
        with self.assertRaises(PermissionError):
            usuarios.sgci_autorizar_operacion(
                self.db, 'cxc', 'editar', 'Clientes y estados de cuenta'
            )

    def test_unknown_submodule_is_denied(self):
        with self.assertRaises(PermissionError):
            usuarios.sgci_autorizar_operacion(self.db, 'cxc', 'editar', 'Inexistente')

    def test_inactive_user_denied(self):
        self.db.execute("UPDATE sgci_usuarios SET activo=0")
        self.assertFalse(usuarios.sgci_puede(self.db, "cxc", "ver"))

    def test_view_grant_does_not_grant_mutation(self):
        self.db.execute("""INSERT INTO sgci_perfil_permisos VALUES
            ('Ventas','cxc','Clientes y estados de cuenta','ver',1)""")
        self.assertFalse(usuarios.sgci_puede(self.db, "cxc", "editar"))


if __name__ == "__main__":
    unittest.main()

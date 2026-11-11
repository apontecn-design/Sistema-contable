"""Pruebas de privilegios administrativos con la implementación real de CONTEM."""
import os
import sqlite3
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from modulos import usuarios


class TestAdministracionPermisos(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.execute("CREATE TABLE nomina_trabajadores(id INTEGER PRIMARY KEY)")
        usuarios.sgci_crear_seguridad(self.db)
        self.db.execute("INSERT INTO sgci_usuarios(email,rol,activo) VALUES('empleado@example.com','Ventas',1)")
        self.db.commit()
        self.sesion = {"sgci_sb_email":"empleado@example.com","sgci_auth_tipo":"supabase"}
        self.patch_globals = patch.dict(usuarios.sgci_guardar_perfil.__globals__, {
            "st":SimpleNamespace(session_state=self.sesion), "os":os
        })
        self.patch_globals.start()
        self.patch_env = patch.dict(os.environ, {"SGCI_ADMIN_EMAIL":"admin@example.com"})
        self.patch_env.start()

    def tearDown(self):
        self.patch_env.stop()
        self.patch_globals.stop()
        self.db.close()

    def test_empleado_no_puede_crear_perfil(self):
        with self.assertRaises(PermissionError):
            usuarios.sgci_guardar_perfil(self.db, "Superadministrador", set())
        self.assertIsNone(self.db.execute(
            "SELECT 1 FROM sgci_perfiles WHERE nombre='Superadministrador'").fetchone())

    def test_empleado_no_puede_asignarse_permisos(self):
        with self.assertRaises(PermissionError):
            usuarios.sgci_guardar_permisos(self.db, "empleado@example.com", "Ventas", True,
                                          {("administracion","editar")})
        self.assertFalse(self.db.execute(
            "SELECT 1 FROM sgci_permisos WHERE email='empleado@example.com'").fetchone())

    def test_empleado_no_puede_crear_otra_cuenta(self):
        with self.assertRaises(PermissionError):
            usuarios.sgci_provisionar_cuenta(self.db,"otra@example.com","ClaveSegura12345")
        self.assertIsNone(self.db.execute(
            "SELECT 1 FROM sgci_usuarios WHERE email='otra@example.com'").fetchone())

    def test_perfil_desconocido_no_es_aceptado(self):
        self.sesion["sgci_sb_email"]="admin@example.com"
        with self.assertRaises(ValueError):
            usuarios.sgci_guardar_permisos(self.db,"otro@example.com","Perfil inexistente",True,set())
        self.assertIsNone(self.db.execute(
            "SELECT 1 FROM sgci_usuarios WHERE email='otro@example.com'").fetchone())


if __name__ == "__main__":
    unittest.main()

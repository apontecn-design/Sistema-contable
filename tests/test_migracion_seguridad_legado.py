"""Verifica migración aditiva de seguridad en esquema legado SQLite."""
import sqlite3
import unittest
from modulos import usuarios


class TestMigracionSeguridadLegado(unittest.TestCase):
    def test_crea_matriz_sin_perder_usuarios_ni_permisos(self):
        conn=sqlite3.connect(':memory:')
        try:
            conn.executescript("""
                CREATE TABLE sgci_usuarios(
                    email TEXT PRIMARY KEY,rol TEXT,activo INTEGER);
                CREATE TABLE sgci_permisos(
                    email TEXT,modulo TEXT,accion TEXT,permitido INTEGER);
                CREATE TABLE nomina_trabajadores(id INTEGER PRIMARY KEY);
                INSERT INTO sgci_usuarios VALUES('test@example.com','Ventas',1);
                INSERT INTO sgci_permisos VALUES('test@example.com','cxc','ver',1);
            """)
            usuarios.sgci_crear_seguridad(conn)
            tablas={r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertIn('sgci_perfil_permisos',tablas)
            self.assertIn('sgci_usuario_permisos_detalle',tablas)
            self.assertIn('sgci_alcance_rrhh',tablas)
            self.assertEqual(conn.execute('SELECT count(*) FROM sgci_usuarios').fetchone()[0],1)
            self.assertEqual(conn.execute('SELECT count(*) FROM sgci_permisos').fetchone()[0],1)
            self.assertEqual(conn.execute(
                "SELECT alcance FROM sgci_alcance_rrhh WHERE email='test@example.com'"
            ).fetchone()[0],'propios')
            usuarios.sgci_crear_seguridad(conn)
            self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone()[0],'ok')
        finally:
            conn.close()


if __name__=='__main__':
    unittest.main()

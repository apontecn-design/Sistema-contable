"""Pruebas de autorización dentro de la función contable de Tesorería.

Ejecutan la función real extraída con un entorno de prueba aislado.
No conectan con la base de producción ni generan asientos reales.
"""
import sqlite3
import unittest
from unittest.mock import patch
from modulos import tesoreria, usuarios


class TestTesoreriaProteccionInterna(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript("""
            CREATE TABLE sgci_usuarios(email TEXT PRIMARY KEY, rol TEXT, activo INTEGER);
            CREATE TABLE sgci_permisos(email TEXT, modulo TEXT, accion TEXT, permitido INTEGER);
            CREATE TABLE sgci_perfil_permisos(perfil TEXT, modulo TEXT, submodulo TEXT, accion TEXT, permitido INTEGER);
            CREATE TABLE sgci_usuario_permisos_detalle(email TEXT, modulo TEXT, submodulo TEXT, accion TEXT, permitido INTEGER);
            CREATE TABLE tes_solicitudes(id INTEGER PRIMARY KEY, estado TEXT);
            INSERT INTO sgci_usuarios VALUES('empleado@example.com','Finanzas',1);
            INSERT INTO tes_solicitudes VALUES(1,'PENDIENTE_CONTABILIZACION');
        """)
        self.patches = [
            patch.object(usuarios, 'sgci_es_propietario', return_value=False),
            patch.object(usuarios, 'sgci_identidad_actual', return_value='empleado@example.com'),
        ]
        for p in self.patches:
            p.start()
        self.original = tesoreria.tes_contabilizar_pago.__globals__.get('sgci_autorizar_operacion')
        tesoreria.tes_contabilizar_pago.__globals__['sgci_autorizar_operacion'] = usuarios.sgci_autorizar_operacion

    def tearDown(self):
        if self.original is None:
            tesoreria.tes_contabilizar_pago.__globals__.pop('sgci_autorizar_operacion', None)
        else:
            tesoreria.tes_contabilizar_pago.__globals__['sgci_autorizar_operacion'] = self.original
        for p in reversed(self.patches):
            p.stop()
        self.conn.close()

    def test_pago_ya_contabilizado_no_se_duplica(self):
        self.conn.execute("""CREATE TABLE tes_confirmaciones_pago (
            solicitud_id INTEGER PRIMARY KEY, asiento_id INTEGER, estado TEXT)""")
        self.conn.execute("""INSERT INTO tes_confirmaciones_pago VALUES
            (1,42,'CONTABILIZADO')""")
        self.conn.execute("""INSERT INTO sgci_perfil_permisos VALUES
            ('Finanzas','tesoreria','Confirmación de pagos','contabilizar',1)""")
        self.conn.commit()
        with self.assertRaisesRegex(ValueError, 'ya fue contabilizada'):
            tesoreria.tes_contabilizar_pago(self.conn, 1, 99)
        self.assertEqual(self.conn.execute(
            'SELECT asiento_id FROM tes_confirmaciones_pago WHERE solicitud_id=1'
        ).fetchone()[0], 42)
        self.assertEqual(self.conn.execute(
            'SELECT COUNT(*) FROM tes_confirmaciones_pago'
        ).fetchone()[0], 1)
        self.assertFalse(self.conn.in_transaction)

    def test_solicitud_inexistente_no_genera_pago(self):
        self.conn.execute("""CREATE TABLE tes_confirmaciones_pago (
            solicitud_id INTEGER PRIMARY KEY, asiento_id INTEGER, estado TEXT)""")
        self.conn.execute("""INSERT INTO sgci_perfil_permisos VALUES
            ('Finanzas','tesoreria','Confirmación de pagos','contabilizar',1)""")
        self.conn.commit()
        with self.assertRaisesRegex(ValueError, 'no está pendiente'):
            tesoreria.tes_contabilizar_pago(self.conn, 999, 99)
        self.assertEqual(self.conn.execute(
            'SELECT COUNT(*) FROM tes_confirmaciones_pago'
        ).fetchone()[0], 0)
        self.assertFalse(self.conn.in_transaction)

    def test_sin_permiso_rechaza_antes_de_mutar(self):
        with self.assertRaises(PermissionError):
            tesoreria.tes_contabilizar_pago(self.conn, 1, 99)
        self.assertEqual(
            self.conn.execute('SELECT estado FROM tes_solicitudes WHERE id=1').fetchone()[0],
            'PENDIENTE_CONTABILIZACION'
        )
        self.assertFalse(self.conn.in_transaction)

    def test_permiso_heredado_no_es_suficiente(self):
        self.conn.execute("""INSERT INTO sgci_permisos VALUES
            ('empleado@example.com','tesoreria','contabilizar',1)""")
        self.conn.commit()
        with self.assertRaises(PermissionError):
            tesoreria.tes_contabilizar_pago(self.conn, 1, 99)

    def test_denegacion_individual_anula_perfil(self):
        self.conn.execute("""INSERT INTO sgci_perfil_permisos VALUES
            ('Finanzas','tesoreria','Confirmación de pagos','contabilizar',1)""")
        self.conn.execute("""INSERT INTO sgci_usuario_permisos_detalle VALUES
            ('empleado@example.com','tesoreria','Confirmación de pagos','contabilizar',0)""")
        self.conn.commit()
        with self.assertRaises(PermissionError):
            tesoreria.tes_contabilizar_pago(self.conn, 1, 99)


if __name__ == '__main__':
    unittest.main()

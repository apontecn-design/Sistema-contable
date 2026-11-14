"""Integración SQLite de Tesorería: asiento balanceado, unicidad y reversión atómica.

Todos los datos son sintéticos y se ejecutan exclusivamente en memoria.
"""
import sqlite3
import unittest
from unittest.mock import patch
from modulos import tesoreria, usuarios


class _PlanFalso:
    def __init__(self, conn):
        self.hojas = {'1.1.01', '5.1.01'}


class TestTesoreriaFlujoContable(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            CREATE TABLE sgci_usuarios(email TEXT PRIMARY KEY, rol TEXT, activo INTEGER);
            CREATE TABLE sgci_permisos(email TEXT, modulo TEXT, accion TEXT, permitido INTEGER);
            CREATE TABLE sgci_perfil_permisos(perfil TEXT, modulo TEXT, submodulo TEXT, accion TEXT, permitido INTEGER);
            CREATE TABLE sgci_usuario_permisos_detalle(email TEXT, modulo TEXT, submodulo TEXT, accion TEXT, permitido INTEGER);
            INSERT INTO sgci_usuarios VALUES('tes@example.com','Finanzas',1);
            INSERT INTO sgci_perfil_permisos VALUES
                ('Finanzas','tesoreria','Confirmación de pagos','contabilizar',1);
            CREATE TABLE tes_solicitudes (
                id INTEGER PRIMARY KEY, estado TEXT, beneficiario TEXT, proveedor_id INTEGER);
            INSERT INTO tes_solicitudes VALUES(1,'PENDIENTE_CONTABILIZACION','Proveedor sintético',NULL);
            CREATE TABLE tes_confirmaciones_pago (
                solicitud_id INTEGER PRIMARY KEY, fecha_pago TEXT, referencia TEXT,
                cuenta_contrapartida TEXT, medio TEXT, asiento_id INTEGER,
                banco_id INTEGER, pago_proveedor_id INTEGER, fecha_contabilizacion TEXT,
                estado TEXT, error_contabilizacion TEXT);
            INSERT INTO tes_confirmaciones_pago
                (solicitud_id,fecha_pago,referencia,cuenta_contrapartida,medio,estado)
                VALUES(1,'2026-10-15','TRANSFER-001','5.1.01','TRANSFERENCIA','PENDIENTE_CONTABILIZACION');
            CREATE TABLE bancos(id INTEGER PRIMARY KEY, activo INTEGER, cuenta_contable TEXT);
            INSERT INTO bancos VALUES(7,1,'1.1.01');
            CREATE TABLE tes_solicitud_detalle(
                id INTEGER PRIMARY KEY, solicitud_id INTEGER, monto INTEGER,
                compra_id INTEGER, tratamiento TEXT, cuenta_contable TEXT, descripcion TEXT);
            INSERT INTO tes_solicitud_detalle VALUES
                (1,1,12500,NULL,'Pendiente de reconocimiento contable','5.1.01','Servicio');
            CREATE TABLE asientos_prueba(
                numero INTEGER, cuenta TEXT, debe INTEGER, haber INTEGER);
        """)
        self.db.commit()
        def linea(conn, fecha, cuenta, debe, haber, glosa, asiento, origen):
            conn.execute('INSERT INTO asientos_prueba VALUES(?,?,?,?)',
                         (asiento, cuenta, debe, haber))
        self.mocks = [
            patch.object(usuarios,'sgci_es_propietario',return_value=False),
            patch.object(usuarios,'sgci_identidad_actual',return_value='tes@example.com'),
        ]
        for p in self.mocks:
            p.start()
        self.globals_patch = patch.dict(tesoreria.tes_contabilizar_pago.__globals__, {
            'sgci_autorizar_operacion': usuarios.sgci_autorizar_operacion,
            'periodo_cerrado': lambda conn, fecha: False,
            'Plan': _PlanFalso,
            'siguiente_asiento': lambda conn: 100,
            'nomina_asiento_linea': linea,
        })
        self.globals_patch.start()

    def tearDown(self):
        self.globals_patch.stop()
        for p in reversed(self.mocks):
            p.stop()
        self.db.close()

    def test_contabilizacion_balanceada_y_reintento_sin_duplicados(self):
        numero = tesoreria.tes_contabilizar_pago(self.db,1,7)
        self.assertEqual(numero,101)
        filas=self.db.execute('SELECT cuenta,debe,haber FROM asientos_prueba ORDER BY rowid').fetchall()
        self.assertEqual([tuple(x) for x in filas],[
            ('5.1.01',12500,0),('1.1.01',0,12500)])
        self.assertEqual(self.db.execute(
            'SELECT estado FROM tes_solicitudes WHERE id=1').fetchone()[0],
            'CONTABILIZADA')
        with self.assertRaises(ValueError):
            tesoreria.tes_contabilizar_pago(self.db,1,7)
        self.assertEqual(self.db.execute(
            'SELECT COUNT(*) FROM asientos_prueba').fetchone()[0],2)

    def test_error_durante_asiento_revierte_toda_la_operacion(self):
        def falla(conn,fecha,cuenta,debe,haber,glosa,asiento,origen):
            conn.execute('INSERT INTO asientos_prueba VALUES(?,?,?,?)',
                         (asiento,cuenta,debe,haber))
            raise RuntimeError('Error simulado en asiento')
        with patch.dict(tesoreria.tes_contabilizar_pago.__globals__,
                        {'nomina_asiento_linea': falla}):
            with self.assertRaisesRegex(RuntimeError,'Error simulado'):
                tesoreria.tes_contabilizar_pago(self.db,1,7)
        self.assertEqual(self.db.execute(
            'SELECT COUNT(*) FROM asientos_prueba').fetchone()[0],0)
        self.assertEqual(self.db.execute(
            'SELECT asiento_id FROM tes_confirmaciones_pago WHERE solicitud_id=1'
        ).fetchone()[0],None)
        self.assertEqual(self.db.execute(
            'SELECT estado FROM tes_solicitudes WHERE id=1').fetchone()[0],
            'PENDIENTE_CONTABILIZACION')


if __name__ == '__main__':
    unittest.main()

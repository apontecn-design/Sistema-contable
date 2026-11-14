"""Pruebas de conciliación bancaria de Tesorería sobre SQLite en memoria."""
import sqlite3
import unittest
from unittest.mock import patch
from modulos import usuarios, ventas_dte


class TestConciliacionTesoreria(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:')
        self.db.row_factory=sqlite3.Row
        self.db.executescript("""
            CREATE TABLE sgci_usuarios(email TEXT PRIMARY KEY,rol TEXT,activo INTEGER);
            CREATE TABLE sgci_permisos(email TEXT,modulo TEXT,accion TEXT,permitido INTEGER);
            CREATE TABLE sgci_perfil_permisos(perfil TEXT,modulo TEXT,submodulo TEXT,accion TEXT,permitido INTEGER);
            CREATE TABLE sgci_usuario_permisos_detalle(email TEXT,modulo TEXT,submodulo TEXT,accion TEXT,permitido INTEGER);
            INSERT INTO sgci_usuarios VALUES('banco@example.com','Finanzas',1);
            INSERT INTO sgci_perfil_permisos VALUES
                ('Finanzas','banco','Conciliación bancaria','conciliar',1),
                ('Finanzas','tesoreria','Historial','ver',1);
            CREATE TABLE cartola_bancaria(
                id INTEGER PRIMARY KEY,banco_id INTEGER,conciliado INTEGER,
                cargo REAL,abono REAL,match_tipo TEXT,match_id INTEGER,
                asiento_id INTEGER,match_confianza INTEGER,observacion TEXT);
            INSERT INTO cartola_bancaria VALUES(10,7,0,12500,0,NULL,NULL,NULL,NULL,NULL);
            INSERT INTO cartola_bancaria VALUES(11,7,0,12500,0,NULL,NULL,NULL,NULL,NULL);
            CREATE TABLE tes_confirmaciones_pago(
                solicitud_id INTEGER PRIMARY KEY,banco_id INTEGER,asiento_id INTEGER);
            INSERT INTO tes_confirmaciones_pago VALUES(1,7,101);
            CREATE TABLE tes_solicitudes(id INTEGER PRIMARY KEY,estado TEXT);
            INSERT INTO tes_solicitudes VALUES(1,'CONTABILIZADA');
            CREATE TABLE tes_solicitud_detalle(
                solicitud_id INTEGER,monto INTEGER);
            INSERT INTO tes_solicitud_detalle VALUES(1,12500);
        """)
        self.db.commit()
        self.patches=[
            patch.object(usuarios,'sgci_es_propietario',return_value=False),
            patch.object(usuarios,'sgci_identidad_actual',return_value='banco@example.com'),
            patch.dict(ventas_dte.tes_conciliar_pago.__globals__,
                {'sgci_autorizar_operacion':usuarios.sgci_autorizar_operacion}),
        ]
        for p in self.patches:p.start()

    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.db.close()

    def test_conciliacion_una_vez_sin_nuevo_asiento(self):
        asiento=ventas_dte.tes_conciliar_pago(self.db,10,1)
        self.assertEqual(asiento,101)
        fila=self.db.execute(
            'SELECT conciliado,match_tipo,match_id,asiento_id FROM cartola_bancaria WHERE id=10'
        ).fetchone()
        self.assertEqual(tuple(fila),(1,'TESORERIA',1,101))
        with self.assertRaises(ValueError):
            ventas_dte.tes_conciliar_pago(self.db,11,1)
        self.assertEqual(self.db.execute(
            'SELECT conciliado FROM cartola_bancaria WHERE id=11').fetchone()[0],0)

    def test_monto_diferente_revierte(self):
        self.db.execute('UPDATE cartola_bancaria SET cargo=12501 WHERE id=10')
        self.db.commit()
        with self.assertRaises(ValueError):
            ventas_dte.tes_conciliar_pago(self.db,10,1)
        self.assertEqual(self.db.execute(
            'SELECT conciliado FROM cartola_bancaria WHERE id=10').fetchone()[0],0)

    def test_banco_distinto_revierte(self):
        self.db.execute('UPDATE cartola_bancaria SET banco_id=8 WHERE id=10')
        self.db.commit()
        with self.assertRaises(ValueError):
            ventas_dte.tes_conciliar_pago(self.db,10,1)
        self.assertEqual(self.db.execute(
            'SELECT conciliado FROM cartola_bancaria WHERE id=10').fetchone()[0],0)

    def test_denegacion_individual_no_modifica_cartola(self):
        self.db.execute("""INSERT INTO sgci_usuario_permisos_detalle VALUES
            ('banco@example.com','banco','Conciliación bancaria','conciliar',0)""")
        self.db.commit()
        with self.assertRaises(PermissionError):
            ventas_dte.tes_conciliar_pago(self.db,10,1)
        self.assertEqual(self.db.execute(
            'SELECT conciliado FROM cartola_bancaria WHERE id=10').fetchone()[0],0)

    def test_sin_historial_no_lee_tesoreria_ni_movimiento(self):
        self.db.execute("DELETE FROM sgci_perfil_permisos WHERE modulo='tesoreria'");self.db.commit()
        consultas=[];self.db.set_trace_callback(consultas.append)
        with self.assertRaises(PermissionError):ventas_dte.tes_conciliar_pago(self.db,10,1)
        self.db.set_trace_callback(None)
        self.assertFalse(any('FROM tes_' in q or 'FROM cartola_bancaria' in q for q in consultas))

    def test_transaccion_previa_no_se_revierte(self):
        self.db.execute('UPDATE cartola_bancaria SET cargo=123 WHERE id=10')
        with self.assertRaises(RuntimeError):ventas_dte.tes_conciliar_pago(self.db,10,1)
        self.assertTrue(self.db.in_transaction)
        self.assertEqual(self.db.execute('SELECT cargo FROM cartola_bancaria WHERE id=10').fetchone()[0],123)
        self.db.rollback()

    def test_revocacion_tras_reserva_no_deja_cambios(self):
        def autorizar(conn,modulo,accion,sub):
            usuarios.sgci_autorizar_operacion(conn,modulo,accion,sub)
            if modulo=='tesoreria' and conn.in_transaction:raise PermissionError('Revocado')
        antes=list(self.db.iterdump())
        with patch.dict(vars(ventas_dte),{'sgci_autorizar_operacion':autorizar}):
            with self.assertRaises(PermissionError):ventas_dte.tes_conciliar_pago(self.db,10,1)
        self.assertEqual(list(self.db.iterdump()),antes)


if __name__=='__main__':
    unittest.main()

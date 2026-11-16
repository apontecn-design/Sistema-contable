import unittest
from modulos import tesoreria,usuarios
from unittest.mock import patch
from tests.soporte_flujos import preparar


class TestCrucesLecturaTesoreria(unittest.TestCase):
    def setUp(self):
        self.db=preparar(self)
        self.sid=tesoreria.tes_guardar_solicitud(self.db,'2026-11-16','Beneficiario',None,'Pago',
            '2026-11-16','',[dict(tipo='Otro',descripcion='Partida',monto=80)])
        self.db.execute("UPDATE tes_solicitudes SET estado='CONTABILIZADA' WHERE id=?",(self.sid,))
        self.db.execute("INSERT INTO tes_confirmaciones_pago(solicitud_id,medio,fecha_pago,banco_descripcion,referencia,nombre_comprobante,comprobante,fecha_registro,asiento_id) VALUES(?,'TRANSFERENCIA','2026-11-16','Banco','REF','pago.pdf',?,'2026-11-16',10)",(self.sid,b'PDF'))
        self.db.executescript("""
            INSERT INTO libro_diario(fecha,cuenta,codigo_cuenta,debe,haber,glosa,asiento_id)
                VALUES('2026-11-16','Gasto','5.1.01',80,0,'Pago propio',10),
                ('2026-11-16','Banco','1.1.02',0,80,'Pago propio',10),
                ('2026-11-16','Ajeno','5.1.01',999,0,'No corresponde',11);
        """)
        self.db.execute("INSERT INTO cartola_bancaria(banco_id,fecha,descripcion,cargo,abono,conciliado,match_tipo,match_id,asiento_id) VALUES(1,'2026-11-16','Pago',80,0,1,'TESORERIA',?,10)",(self.sid,));self.db.commit()

    def denegar(self,mod,sub,accion='ver'):
        self.db.execute('INSERT INTO sgci_usuario_permisos_detalle VALUES(?,?,?,?,0)',
            ('finanzas@example.com',mod,sub,accion));self.db.commit()

    def sin_leer(self,fn,tabla):
        consultas=[];self.db.set_trace_callback(consultas.append)
        try:
            with self.assertRaises(PermissionError):fn()
        finally:self.db.set_trace_callback(None)
        self.assertFalse(any(tabla in q for q in consultas))

    def test_solo_asiento_vinculado_y_proyeccion_original(self):
        df=tesoreria.tes_asiento_pago_autorizado(self.db,self.sid)
        self.assertEqual(df.columns.tolist(),['fecha','codigo_cuenta','cuenta','debe','haber','glosa'])
        self.assertEqual(len(df),2);self.assertEqual(df.debe.sum(),80);self.assertEqual(df.haber.sum(),80)

    def test_tesoreria_no_concede_diario(self):
        self.denegar('contabilidad','Libro Diario')
        self.sin_leer(lambda:tesoreria.tes_asiento_pago_autorizado(self.db,self.sid),'libro_diario')

    def test_diario_no_concede_confirmacion(self):
        self.denegar('tesoreria','Confirmación de pagos')
        self.sin_leer(lambda:tesoreria.tes_asiento_pago_autorizado(self.db,self.sid),'libro_diario')

    def test_exportar_exige_ambos_permisos(self):
        for mod,sub in [('contabilidad','Libro Diario'),('tesoreria','Confirmación de pagos')]:
            with self.subTest(mod=mod):
                self.denegar(mod,sub,'exportar')
                self.assertEqual(len(tesoreria.tes_asiento_pago_autorizado(self.db,self.sid)),2)
                self.sin_leer(lambda:tesoreria.tes_asiento_pago_autorizado(self.db,self.sid,True),'libro_diario')
                self.db.execute('DELETE FROM sgci_usuario_permisos_detalle');self.db.commit()

    def test_exportar_no_sustituye_lectura(self):
        self.denegar('contabilidad','Libro Diario')
        self.sin_leer(lambda:tesoreria.tes_asiento_pago_autorizado(self.db,self.sid,True),'libro_diario')

    def test_revocacion_inmediata_diario(self):
        tesoreria.tes_asiento_pago_autorizado(self.db,self.sid,True)
        self.denegar('contabilidad','Libro Diario')
        with self.assertRaises(PermissionError):tesoreria.tes_asiento_pago_autorizado(self.db,self.sid,True)

    def test_solicitud_inexistente_o_no_contabilizada_no_entrega_asiento(self):
        self.assertTrue(tesoreria.tes_asiento_pago_autorizado(self.db,999).empty)
        self.db.execute("UPDATE tes_solicitudes SET estado='APROBADA'")
        self.assertTrue(tesoreria.tes_asiento_pago_autorizado(self.db,self.sid).empty)

    def test_conciliacion_exige_lectura_bancaria(self):
        self.denegar('banco','Conciliación bancaria')
        self.sin_leer(lambda:tesoreria.tes_conciliacion_pago_autorizada(self.db,self.sid),'cartola_bancaria')

    def test_conciliacion_exige_confirmacion(self):
        self.denegar('tesoreria','Confirmación de pagos')
        self.sin_leer(lambda:tesoreria.tes_conciliacion_pago_autorizada(self.db,self.sid),'cartola_bancaria')

    def test_conciliacion_debe_coincidir_con_asiento_y_solicitud(self):
        self.assertTrue(tesoreria.tes_conciliacion_pago_autorizada(self.db,self.sid))
        self.assertFalse(tesoreria.tes_conciliacion_pago_autorizada(self.db,999))
        self.db.execute('UPDATE cartola_bancaria SET asiento_id=11')
        self.assertFalse(tesoreria.tes_conciliacion_pago_autorizada(self.db,self.sid))

    def test_consultas_no_confirman_transaccion(self):
        self.db.execute("UPDATE libro_diario SET glosa='Temporal' WHERE asiento_id=10")
        tesoreria.tes_asiento_pago_autorizado(self.db,self.sid,True)
        tesoreria.tes_conciliacion_pago_autorizada(self.db,self.sid)
        self.assertTrue(self.db.in_transaction);self.db.rollback()
        self.assertEqual(tesoreria.tes_asiento_pago_autorizado(self.db,self.sid).iloc[0].glosa,'Pago propio')

    def test_propietario_conserva_consultas_completas(self):
        self.denegar('contabilidad','Libro Diario');self.denegar('banco','Conciliación bancaria')
        with patch.object(usuarios,'sgci_es_propietario',return_value=True):
            self.assertEqual(len(tesoreria.tes_asiento_pago_autorizado(self.db,self.sid,True)),2)
            self.assertTrue(tesoreria.tes_conciliacion_pago_autorizada(self.db,self.sid))

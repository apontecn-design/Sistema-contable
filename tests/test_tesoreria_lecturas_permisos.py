import unittest
from unittest.mock import patch, Mock
from modulos import tesoreria, ventas_dte, usuarios
from tests.soporte_flujos import preparar


class TestLecturasTesoreria(unittest.TestCase):
    def setUp(self):
        self.db=preparar(self)
        self.sid=tesoreria.tes_guardar_solicitud(self.db,'2026-11-16','Beneficiario prueba',None,
            'Concepto prueba','2026-11-16','',[dict(tipo='Otro',descripcion='Partida',monto=120)])
        self.db.execute("INSERT INTO tes_confirmaciones_pago(solicitud_id,medio,fecha_pago,banco_descripcion,referencia,nombre_comprobante,comprobante,fecha_registro) VALUES(?,'TRANSFERENCIA','2026-11-16','Banco prueba','REF','pago.pdf',?,'2026-11-16')",(self.sid,b'%PDF-prueba'))
        self.db.commit()

    def denegar(self,sub,accion='ver'):
        self.db.execute('INSERT INTO sgci_usuario_permisos_detalle VALUES(?,?,?,?,0)',
            ('finanzas@example.com','tesoreria',sub,accion));self.db.commit()

    def sin_consulta(self,fn,tabla):
        consultas=[];self.db.set_trace_callback(consultas.append)
        try:
            with self.assertRaises(PermissionError):fn()
        finally:self.db.set_trace_callback(None)
        self.assertFalse(any(tabla in q for q in consultas))

    def test_historial_conserva_proyeccion_y_totales(self):
        df=tesoreria.tes_historial_autorizado(self.db)
        self.assertEqual(df.columns.tolist(),['solicitud','fecha','beneficiario','concepto','estado','monto','fecha_pago','referencia','asiento_id'])
        self.assertEqual(df.iloc[0].monto,120)

    def test_solicitudes_no_concede_historial(self):
        self.denegar('Historial')
        self.sin_consulta(lambda:tesoreria.tes_historial_autorizado(self.db),'tes_solicitudes')

    def test_exportar_historial_requiere_lectura(self):
        self.denegar('Historial')
        self.sin_consulta(lambda:tesoreria.tes_historial_autorizado(self.db,True),'tes_solicitudes')

    def test_historial_visible_sin_exportar(self):
        self.denegar('Historial','exportar')
        self.assertEqual(len(tesoreria.tes_historial_autorizado(self.db)),1)
        self.sin_consulta(lambda:tesoreria.tes_historial_autorizado(self.db,True),'tes_solicitudes')

    def test_comprobante_requiere_confirmacion(self):
        self.denegar('Confirmación de pagos')
        self.sin_consulta(lambda:tesoreria.tes_comprobante_autorizado(self.db,self.sid),'tes_confirmaciones_pago')

    def test_comprobante_exportacion_independiente(self):
        self.denegar('Confirmación de pagos','exportar')
        self.assertEqual(bytes(tesoreria.tes_comprobante_autorizado(self.db,self.sid)['comprobante']),b'%PDF-prueba')
        self.sin_consulta(lambda:tesoreria.tes_comprobante_autorizado(self.db,self.sid,True),'tes_confirmaciones_pago')

    def test_revocacion_inmediata(self):
        tesoreria.tes_comprobante_autorizado(self.db,self.sid,True)
        self.denegar('Confirmación de pagos')
        with self.assertRaises(PermissionError):tesoreria.tes_comprobante_autorizado(self.db,self.sid,True)

    def test_solicitud_inexistente_no_retorna_otro_comprobante(self):
        with self.assertRaises(ValueError):tesoreria.tes_comprobante_autorizado(self.db,999)

    def test_lecturas_no_confirman_transaccion_ajena(self):
        self.db.execute("UPDATE tes_solicitudes SET concepto='Temporal' WHERE id=?",(self.sid,))
        tesoreria.tes_historial_autorizado(self.db,True)
        tesoreria.tes_comprobante_autorizado(self.db,self.sid,True)
        self.assertTrue(self.db.in_transaction)
        self.db.rollback()
        self.assertEqual(tesoreria.tes_historial_autorizado(self.db).iloc[0].concepto,'Concepto prueba')

    def test_pdf_no_se_genera_sin_exportar(self):
        self.denegar('Solicitudes de fondos','exportar')
        reporte=Mock();ui=Mock()
        with patch.dict(vars(ventas_dte),{'sgci_puede_submodulo':usuarios.sgci_puede_submodulo,
                'sgci_autorizar_operacion':usuarios.sgci_autorizar_operacion,'tes_reporte_imprimible':reporte,'st':ui}):
            ventas_dte.tes_boton_imprimir(self.db,'Prueba',None,'prueba')
        reporte.assert_not_called();ui.download_button.assert_not_called()

    def test_pdf_pago_usa_su_submodulo(self):
        self.denegar('Solicitudes de fondos','exportar')
        reporte=Mock(return_value=b'PDF');ui=Mock()
        with patch.dict(vars(ventas_dte),{'sgci_puede_submodulo':usuarios.sgci_puede_submodulo,
                'sgci_autorizar_operacion':usuarios.sgci_autorizar_operacion,'tes_reporte_imprimible':reporte,'st':ui}):
            ventas_dte.tes_boton_imprimir(self.db,'Prueba',None,'prueba','Confirmación de pagos')
        reporte.assert_called_once();ui.download_button.assert_called_once()

    def test_visor_revocado_no_muestra_bytes_guardados(self):
        self.denegar('Confirmación de pagos')
        ui=Mock();ui.session_state={f'tes_show_{self.sid}':True}
        with patch.dict(vars(ventas_dte),{'tes_comprobante_autorizado':tesoreria.tes_comprobante_autorizado,'st':ui}):
            with self.assertRaises(PermissionError):ventas_dte.tes_vista_comprobante(self.db,self.sid)
        ui.markdown.assert_not_called();ui.image.assert_not_called();ui.download_button.assert_not_called()

    def test_visor_sin_exportar_no_entrega_descarga(self):
        self.denegar('Confirmación de pagos','exportar')
        ui=Mock();ui.button.return_value=False;ui.session_state={f'tes_show_{self.sid}':True}
        with patch.dict(vars(ventas_dte),{'tes_comprobante_autorizado':tesoreria.tes_comprobante_autorizado,
                'sgci_puede_submodulo':usuarios.sgci_puede_submodulo,'st':ui}):
            ventas_dte.tes_vista_comprobante(self.db,self.sid)
        ui.markdown.assert_called_once();ui.download_button.assert_not_called()

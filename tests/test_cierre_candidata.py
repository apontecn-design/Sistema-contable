import unittest
from unittest.mock import patch,MagicMock
from modulos import contabilidad_asientos as servicio,usuarios,ventas_dte,bancos,tesoreria
from tests.soporte_flujos import preparar


class TestCierreCandidata(unittest.TestCase):
    def setUp(self):
        self.db=preparar(self)
        self.filas=[dict(fecha='2026-11-16',codigo='5.1.01',debe=100,haber=0,glosa='Prueba'),
                    dict(fecha='2026-11-16',codigo='1.1.02',debe=0,haber=100,glosa='Prueba')]

    def denegar(self,mod,sub,accion):
        self.db.execute('INSERT INTO sgci_usuario_permisos_detalle VALUES(?,?,?,?,0)',
            ('finanzas@example.com',mod,sub,accion));self.db.commit()

    def test_manual_y_auditoria_juntos(self):
        r=servicio.contem_guardar_asientos(self.db,self.filas)
        self.assertEqual(len(r['asientos']),1)
        self.assertEqual(tuple(self.db.execute('SELECT SUM(debe),SUM(haber) FROM libro_diario').fetchone()),(100,100))
        self.assertEqual(self.db.execute('SELECT usuario FROM auditoria').fetchone()[0],'finanzas@example.com')

    def test_manual_sin_permiso_no_lee_negocio(self):
        self.denegar('contabilidad','Asientos y Saldos','contabilizar');traza=[]
        self.db.set_trace_callback(traza.append)
        with self.assertRaises(PermissionError):servicio.contem_guardar_asientos(self.db,self.filas)
        self.db.set_trace_callback(None)
        self.assertFalse(any('libro_diario' in q for q in traza))

    def test_manual_revalida_dentro_de_reserva(self):
        original=usuarios.sgci_autorizar_operacion;llamadas=[]
        def autorizar(*args):
            llamadas.append(self.db.in_transaction)
            if len(llamadas)==2:raise PermissionError('Revocado')
            return original(*args)
        with patch.dict(vars(servicio),{'sgci_autorizar_operacion':autorizar}):
            with self.assertRaises(PermissionError):servicio.contem_guardar_asientos(self.db,self.filas)
        self.assertEqual(llamadas,[False,True]);self.assertEqual(self.db.execute('SELECT COUNT(*) FROM libro_diario').fetchone()[0],0)

    def test_manual_cerrado_no_escribe(self):
        self.db.execute("INSERT INTO periodos_contables(periodo,estado) VALUES('2026-11','CERRADO')");self.db.commit()
        with self.assertRaisesRegex(ValueError,'cerrado'):servicio.contem_guardar_asientos(self.db,self.filas)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM libro_diario').fetchone()[0],0)

    def test_manual_rechaza_importes_y_desbalance(self):
        for valor in [-1,0,100.5,float('nan'),float('inf'),99]:
            with self.subTest(valor=valor):
                filas=[dict(f) for f in self.filas];filas[0]['debe']=valor
                with self.assertRaises(ValueError):servicio.contem_guardar_asientos(self.db,filas)
                self.assertEqual(self.db.execute('SELECT COUNT(*) FROM libro_diario').fetchone()[0],0)

    def test_manual_lote_completo_rechaza_segundo_grupo_invalido(self):
        filas=self.filas+[dict(self.filas[0],grupo=2)]
        with self.assertRaises(ValueError):servicio.contem_guardar_asientos(self.db,filas)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM libro_diario').fetchone()[0],0)

    def test_manual_lote_genera_asientos_distintos(self):
        r=servicio.contem_guardar_asientos(self.db,self.filas+[dict(f,grupo=2) for f in self.filas],'Saldo inicial')
        self.assertEqual(len(set(r['asientos'])),2)

    def test_manual_fallo_auditoria_revierte_todo(self):
        self.db.execute("CREATE TRIGGER falla_auditoria BEFORE INSERT ON auditoria BEGIN SELECT RAISE(ABORT,'fallo simulado'); END");self.db.commit()
        with self.assertRaises(Exception):servicio.contem_guardar_asientos(self.db,self.filas)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM libro_diario').fetchone()[0],0)

    def test_manual_no_confirma_transaccion_ajena(self):
        self.db.execute("UPDATE bancos SET nombre='Temporal'")
        with self.assertRaisesRegex(ValueError,'pendiente'):servicio.contem_guardar_asientos(self.db,self.filas)
        self.assertTrue(self.db.in_transaction);self.db.rollback()
        self.assertEqual(self.db.execute('SELECT nombre FROM bancos').fetchone()[0],'Banco de prueba')

    def test_f29_cuadra_y_bloquea_reintento(self):
        asiento=servicio.contem_guardar_f29(self.db,'2026-11','2026-11-30',100,70)
        self.assertEqual(tuple(self.db.execute('SELECT SUM(debe),SUM(haber) FROM libro_diario WHERE asiento_id=?',(asiento,)).fetchone()),(100,100))
        with self.assertRaisesRegex(ValueError,'compensado'):servicio.contem_guardar_f29(self.db,'2026-11','2026-11-30',100,70)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM libro_diario').fetchone()[0],3)

    def test_f29_periodo_o_fecha_cerrados(self):
        self.db.execute("INSERT INTO periodos_contables(periodo,estado) VALUES('2026-11','CERRADO')");self.db.commit()
        with self.assertRaisesRegex(ValueError,'cerrado'):servicio.contem_guardar_f29(self.db,'2026-11','2026-12-01',100,70)

    def test_f29_sin_permiso(self):
        self.denegar('contabilidad','Asientos y Saldos','contabilizar')
        with self.assertRaises(PermissionError):servicio.contem_guardar_f29(self.db,'2026-11','2026-11-30',100,70)

    def test_f29_fallo_auditoria_revierte_asiento_y_control(self):
        self.db.execute("CREATE TRIGGER falla_auditoria BEFORE INSERT ON auditoria BEGIN SELECT RAISE(ABORT,'fallo simulado'); END");self.db.commit()
        with self.assertRaises(Exception):servicio.contem_guardar_f29(self.db,'2026-11','2026-11-30',100,70)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM libro_diario').fetchone()[0],0)

    def test_dte_pestanas_denegadas_no_consultan(self):
        for sub in ('Importar XML','Documentos y visor','Reportería'):self.denegar('dte',sub,'ver')
        ui=MagicMock();ui.tabs.return_value=[MagicMock(),MagicMock(),MagicMock()]
        traza=[];self.db.set_trace_callback(traza.append)
        with patch.dict(vars(ventas_dte),{'st':ui,'sgci_puede_submodulo':usuarios.sgci_puede_submodulo,
                'sgci_autorizar_operacion':usuarios.sgci_autorizar_operacion}):
            ventas_dte.pantalla_dte(self.db)
        self.db.set_trace_callback(None)
        self.assertFalse(any('dte_documentos' in q for q in traza));ui.file_uploader.assert_not_called()

    def test_cierre_reapertura_auditados(self):
        servicio.contem_cambiar_cierre(self.db,'2026-11')
        self.assertEqual(self.db.execute('SELECT estado FROM periodos_contables').fetchone()[0],'CERRADO')
        servicio.contem_cambiar_cierre(self.db,'2026-11',False)
        self.assertEqual(self.db.execute('SELECT estado FROM periodos_contables').fetchone()[0],'ABIERTO')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM auditoria').fetchone()[0],2)

    def test_cierre_no_usa_cuadratura_obsoleta(self):
        self.db.execute("INSERT INTO libro_diario(fecha,codigo_cuenta,cuenta,debe,haber) VALUES('2026-11-16','5.1.01','Gasto',100,0)");self.db.commit()
        with self.assertRaisesRegex(ValueError,'descuadrado'):servicio.contem_cambiar_cierre(self.db,'2026-11')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM periodos_contables').fetchone()[0],0)

    def test_cierre_sin_permiso(self):
        self.denegar('administracion','Cierre Mensual','aprobar')
        with self.assertRaises(PermissionError):servicio.contem_cambiar_cierre(self.db,'2026-11')

    def test_banco_y_vinculo_auditados(self):
        bid=bancos.contem_guardar_banco(self.db,'Nuevo','123','Cuenta corriente','1.1.02',0)
        bancos.contem_vincular_banco(self.db,bid,'1.1.01')
        self.assertEqual(self.db.execute('SELECT cuenta_contable FROM bancos WHERE id=?',(bid,)).fetchone()[0],'1.1.01')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM auditoria').fetchone()[0],2)

    def test_banco_fallo_auditoria_revierte_creacion(self):
        self.db.execute("CREATE TRIGGER falla_auditoria BEFORE INSERT ON auditoria BEGIN SELECT RAISE(ABORT,'fallo simulado'); END");self.db.commit()
        with self.assertRaises(Exception):bancos.contem_guardar_banco(self.db,'Nuevo','123','Cuenta corriente','1.1.02',0)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM bancos').fetchone()[0],1)

    def test_banco_no_admite_cuenta_padre(self):
        with self.assertRaises(ValueError):bancos.contem_guardar_banco(self.db,'Nuevo','123','Cuenta corriente','1',0)

    def test_catalogos_tesoreria_no_eluden_auxiliares(self):
        self.denegar('cxp','Proveedores y estados de cuenta','ver')
        self.denegar('banco','Bancos y cartolas','ver');consultas=[];self.db.set_trace_callback(consultas.append)
        with self.assertRaises(PermissionError):tesoreria.tes_proveedores_autorizados(self.db)
        with self.assertRaises(PermissionError):tesoreria.tes_bancos_autorizados(self.db)
        self.db.set_trace_callback(None)
        self.assertFalse(any('FROM proveedores' in q or 'FROM bancos' in q for q in consultas))

    def test_exportar_requiere_ver_y_exportar(self):
        self.assertTrue(usuarios.contem_puede_exportar(self.db,'contabilidad','Libro Diario'))
        self.denegar('contabilidad','Libro Diario','exportar')
        self.assertFalse(usuarios.contem_puede_exportar(self.db,'contabilidad','Libro Diario'))

    def test_empresarial_desactivado_conserva_portal(self):
        with patch.dict('os.environ',{'CONTEM_MULTIUSUARIO_HABILITADO':'NO'}):
            self.assertFalse(usuarios.contem_acceso_empresarial(self.db))

    def test_empresarial_exige_cuenta_activa_y_cambio_completo(self):
        with patch.dict('os.environ',{'CONTEM_MULTIUSUARIO_HABILITADO':'SI'}):
            self.assertTrue(usuarios.contem_acceso_empresarial(self.db))
            self.db.execute('UPDATE sgci_usuarios SET debe_cambiar_clave=1')
            self.assertFalse(usuarios.contem_acceso_empresarial(self.db))
            self.db.execute('UPDATE sgci_usuarios SET debe_cambiar_clave=0,activo=0')
            self.assertFalse(usuarios.contem_acceso_empresarial(self.db))

    def test_liquidacion_personal_no_activa_empresarial(self):
        self.db.execute("DELETE FROM sgci_perfil_permisos WHERE NOT (modulo='nomina' AND submodulo='Liquidación mensual')");self.db.commit()
        with patch.dict('os.environ',{'CONTEM_MULTIUSUARIO_HABILITADO':'SI'}):
            self.assertFalse(usuarios.contem_acceso_empresarial(self.db))

    def test_visibilidad_respeta_revocacion(self):
        self.assertIn('Libro Diario',usuarios.contem_submodulos_visibles(self.db,'contabilidad'))
        self.denegar('contabilidad','Libro Diario','ver')
        self.assertNotIn('Libro Diario',usuarios.contem_submodulos_visibles(self.db,'contabilidad'))

from io import BytesIO
import unittest
from openpyxl import Workbook
from modulos import tesoreria
from tests.soporte_flujos import preparar


class TestCicloTesoreria(unittest.TestCase):
    def setUp(self):
        self.db = preparar(self)
        self.detalles = [dict(tipo='Documento sin DTE',descripcion='Gasto de prueba',referencia='REF',
            monto=100,tratamiento='Pendiente de reconocimiento contable'),
            dict(tipo='Anticipo',descripcion='Anticipo',monto=50,tratamiento='Anticipo a proveedor / beneficiario')]

    def crear(self, adjunto=None):
        return tesoreria.tes_guardar_solicitud(self.db,'2026-11-11','Proveedor',1,'Solicitud',
            '2026-11-12','',self.detalles,adjunto)

    def preparar_pago(self):
        sid = self.crear()
        ids = [r[0] for r in self.db.execute('SELECT id FROM tes_solicitud_detalle WHERE solicitud_id=? ORDER BY id',(sid,))]
        tesoreria.tes_guardar_clasificacion(self.db,sid,{ids[0]:'5.1.01',ids[1]:'1.1.01'})
        tesoreria.tes_cambiar_estado(self.db,sid,'ENVIADA')
        tesoreria.tes_cambiar_estado(self.db,sid,'APROBADA')
        return sid

    def confirmar(self,sid):
        tesoreria.tes_confirmar_pago(self.db,sid,'TRANSFERENCIA','2026-11-11',1,'Banco','REF-1','pago.pdf',b'%PDF-1.4 prueba')

    def test_ciclo_con_cuentas_por_linea_y_asiento_real(self):
        sid = self.preparar_pago()
        self.confirmar(sid)
        asiento = tesoreria.tes_contabilizar_pago(self.db,sid,1)
        filas = self.db.execute('SELECT codigo_cuenta,debe,haber FROM libro_diario WHERE asiento_id=? ORDER BY id',(asiento,)).fetchall()
        self.assertEqual([tuple(r) for r in filas],[('5.1.01',100,0),('1.1.01',50,0),('1.1.02',0,150)])
        self.assertEqual(self.db.execute('SELECT estado FROM tes_solicitudes WHERE id=?',(sid,)).fetchone()[0],'CONTABILIZADA')
        with self.assertRaises(ValueError):tesoreria.tes_contabilizar_pago(self.db,sid,1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM libro_diario').fetchone()[0],3)

    def test_adjunto_excel_se_conserva_sin_ejecutarse(self):
        archivo = BytesIO(); Workbook().save(archivo)
        sid = self.crear(('../solicitud.xlsx',archivo.getvalue()))
        nombre,contenido = tesoreria.tes_descargar_adjunto(self.db,sid,1)
        self.assertEqual(nombre,'solicitud.xlsx')
        self.assertEqual(contenido,archivo.getvalue())

    def test_archivo_falso_no_deja_solicitud_parcial(self):
        with self.assertRaises(ValueError):self.crear(('archivo.xlsx',b'no es Excel'))
        self.assertEqual(self.db.execute('SELECT count(*) FROM tes_solicitudes').fetchone()[0],0)

    def test_aprobar_sin_enviar_rechaza(self):
        sid = self.crear()
        with self.assertRaises(ValueError):tesoreria.tes_cambiar_estado(self.db,sid,'APROBADA')

    def test_confirmacion_duplicada_no_duplica_pago(self):
        sid = self.preparar_pago();self.confirmar(sid)
        with self.assertRaises(ValueError):self.confirmar(sid)
        self.assertEqual(self.db.execute('SELECT count(*) FROM tes_confirmaciones_pago').fetchone()[0],1)

    def test_confirmacion_invalida_revierte_estado(self):
        sid = self.preparar_pago()
        with self.assertRaises(ValueError):
            tesoreria.tes_confirmar_pago(self.db,sid,'TRANSFERENCIA','2026-11-11',999,'Banco','REF','p.pdf',b'%PDF-1.4 prueba')
        self.assertEqual(self.db.execute('SELECT estado FROM tes_solicitudes').fetchone()[0],'APROBADA')

    def test_permiso_de_confirmar_no_concede_contabilizar(self):
        sid = self.preparar_pago()
        self.db.execute("DELETE FROM sgci_perfil_permisos WHERE accion='contabilizar'");self.db.commit()
        self.confirmar(sid)
        with self.assertRaises(PermissionError):tesoreria.tes_contabilizar_pago(self.db,sid,1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM libro_diario').fetchone()[0],0)

    def test_desactivacion_revoca_creacion(self):
        self.db.execute('UPDATE sgci_usuarios SET activo=0');self.db.commit()
        with self.assertRaises(PermissionError):self.crear()

    def test_no_modifica_lineas_de_otra_solicitud(self):
        a = self.crear();b = self.crear()
        did = self.db.execute('SELECT id FROM tes_solicitud_detalle WHERE solicitud_id=?',(b,)).fetchone()[0]
        with self.assertRaises(ValueError):tesoreria.tes_guardar_clasificacion(self.db,a,{did:'5.1.01'})
        self.assertIsNone(self.db.execute('SELECT cuenta_contable FROM tes_solicitud_detalle WHERE id=?',(did,)).fetchone()[0])

    def test_sin_permiso_exportar_no_recupera_adjunto(self):
        sid = self.crear(('s.pdf',b'%PDF-1.4 prueba'))
        self.db.execute("DELETE FROM sgci_perfil_permisos WHERE accion='exportar'");self.db.commit()
        with self.assertRaises(PermissionError):tesoreria.tes_descargar_adjunto(self.db,sid,1)

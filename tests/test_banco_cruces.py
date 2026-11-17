import re
import unittest
from unittest.mock import patch
from modulos import conciliacion_documental as servicio,contabilidad_reportes as reportes,ventas_dte
from tests.soporte_flujos import preparar


class TestCrucesBanco(unittest.TestCase):
    def setUp(self):
        self.db=preparar(self)
        servicio.sgci_conc_esquema(self.db)
        servicio.sgci_crear_devoluciones_proveedor(self.db)
        self.db.execute("INSERT INTO clientes(id,rut,nombre) VALUES(1,'1-9','Cliente de prueba')")
        self.db.commit()
        p=patch.dict(vars(servicio),{'documentos_pendientes_cliente':reportes.documentos_pendientes_cliente})
        p.start();self.addCleanup(p.stop)
        p=patch.dict(vars(reportes),{'sgci_conc_esquema':servicio.sgci_conc_esquema})
        p.start();self.addCleanup(p.stop)

    def denegar(self,modulo,sub,accion='ver'):
        self.db.execute('INSERT INTO sgci_usuario_permisos_detalle VALUES(?,?,?,?,0)',('finanzas@example.com',modulo,sub,accion))
        self.db.commit()

    def sin_lecturas(self,llamada):
        consultas=[];antes=list(self.db.iterdump());self.db.set_trace_callback(consultas.append)
        with self.assertRaises(PermissionError):llamada()
        self.db.set_trace_callback(None)
        self.assertFalse(any(re.search(r'\b(?:FROM|JOIN)\s+(?:clientes|proveedores|compras|ventas|tes_\w+|cartola_bancaria)\b',q,re.I) for q in consultas))
        self.assertEqual(list(self.db.iterdump()),antes)

    def test_listas_exigen_lectura_bancaria_y_del_origen(self):
        for modulo,sub in [('cxc','Pagos de clientes'),('cxp','Pagos de proveedores')]:
            for denegado,subdenegado in [('banco','Conciliación bancaria'),(modulo,sub)]:
                with self.subTest(modulo=modulo,denegado=denegado):
                    self.denegar(denegado,subdenegado)
                    self.sin_lecturas(lambda:servicio.banco_entidades_pago(self.db,modulo))
                    self.sin_lecturas(lambda:servicio.banco_documentos_pago(self.db,modulo,1))
                    self.db.execute('DELETE FROM sgci_usuario_permisos_detalle');self.db.commit()

    def test_listas_autorizadas_y_revocacion(self):
        self.assertEqual(servicio.banco_entidades_pago(self.db,'cxc').id.tolist(),[1])
        self.assertEqual(servicio.banco_entidades_pago(self.db,'cxp').id.tolist(),[2,1])
        self.denegar('cxp','Pagos de proveedores')
        self.sin_lecturas(lambda:servicio.banco_entidades_pago(self.db,'cxp'))
        self.db.execute('DELETE FROM sgci_usuario_permisos_detalle')
        self.assertEqual(len(servicio.banco_entidades_pago(self.db,'cxp')),2)

    def test_documentos_reembolso_y_aplicaciones_protegidos(self):
        self.assertTrue(servicio.banco_documentos_pago(self.db,'cxp',1,True).empty)
        self.assertEqual(servicio.banco_devolucion_aplicada(self.db,1,2),0)
        self.denegar('cxp','Pagos de proveedores')
        self.sin_lecturas(lambda:servicio.banco_documentos_pago(self.db,'cxp',1,True))
        self.sin_lecturas(lambda:servicio.banco_devolucion_aplicada(self.db,1,2))

    def test_historial_tesoreria_exige_ambas_lecturas(self):
        self.assertTrue(servicio.banco_pagos_tesoreria(self.db,1,100).empty)
        for modulo,sub in [('banco','Conciliación bancaria'),('tesoreria','Historial')]:
            self.denegar(modulo,sub)
            self.sin_lecturas(lambda:servicio.banco_pagos_tesoreria(self.db,1,100))
            self.db.execute('DELETE FROM sgci_usuario_permisos_detalle');self.db.commit()

    def test_consultas_no_confirman_transaccion_ajena(self):
        self.db.execute("UPDATE proveedores SET nombre='Pendiente' WHERE id=1")
        antes=list(self.db.iterdump())
        servicio.banco_entidades_pago(self.db,'cxp')
        servicio.banco_documentos_pago(self.db,'cxp',1)
        servicio.banco_documentos_pago(self.db,'cxc',1)
        servicio.banco_pagos_tesoreria(self.db,1,100)
        servicio.banco_devolucion_aplicada(self.db,1,2)
        self.assertEqual(list(self.db.iterdump()),antes)
        self.assertTrue(self.db.in_transaction)
        self.db.rollback()
        self.assertEqual(self.db.execute('SELECT nombre FROM proveedores WHERE id=1').fetchone()[0],'Proveedor de prueba')

    def test_modulo_no_admite_identificadores_arbitrarios(self):
        for modulo in ('otro','clientes; DROP TABLE clientes',''):
            with self.assertRaises(ValueError):servicio.banco_entidades_pago(self.db,modulo)
            with self.assertRaises(ValueError):servicio.banco_documentos_pago(self.db,modulo,1)

    def test_permiso_bancario_no_concede_acciones_del_auxiliar(self):
        operaciones=[
            ('cxp','contabilizar',lambda:servicio.sgci_contabilizar_devolucion_proveedor(self.db,1,1,1,2)),
            ('cxp','contabilizar',lambda:servicio.contabilizar_pago_proveedor_desde_cartola(self.db,1,1,[1])),
            ('cxp','contabilizar',lambda:servicio.contabilizar_pago_proveedor_sin_documento(self.db,1,1)),
            ('cxp','anular',lambda:servicio.revertir_pago_proveedor_cartola(self.db,1)),
            ('cxc','anular',lambda:servicio.revertir_abono_cliente_cartola(self.db,1)),
            ('cxc','contabilizar',lambda:reportes.sgci_cobro_mixto(self.db,1,1,[],0)),
            ('cxc','contabilizar',lambda:reportes.contabilizar_cobro_cliente_desde_cartola(self.db,1,1,[1])),
            ('cxc','contabilizar',lambda:reportes.contabilizar_cobro_cliente_sin_documento(self.db,1,1,'1.1.02'))]
        for modulo,accion,llamada in operaciones:
            with self.subTest(modulo=modulo,accion=accion,llamada=llamada):
                self.denegar(modulo,'Pagos de clientes' if modulo=='cxc' else 'Pagos de proveedores',accion)
                self.sin_lecturas(llamada)
                self.db.execute('DELETE FROM sgci_usuario_permisos_detalle');self.db.commit()

    def test_sugerencias_no_leen_auxiliares_sin_permiso(self):
        for cargo,abono,modulo,sub in [(100,0,'cxp','Pagos de proveedores'),(0,100,'cxc','Pagos de clientes')]:
            self.db.execute('DELETE FROM cartola_bancaria')
            self.db.execute("INSERT INTO cartola_bancaria(id,banco_id,fecha,cargo,abono) VALUES(1,1,'2026-11-13',?,?)",(cargo,abono))
            self.denegar(modulo,sub)
            consultas=[];self.db.set_trace_callback(consultas.append)
            self.assertTrue(reportes.candidatos_conciliacion(self.db,1).empty)
            self.db.set_trace_callback(None)
            self.assertFalse(any(re.search(r'\b(?:FROM|JOIN)\s+(?:clientes|proveedores|compras|ventas)\b',q,re.I) for q in consultas))
            self.db.execute('DELETE FROM sgci_usuario_permisos_detalle');self.db.commit()

    def test_sugerencias_exigen_lectura_bancaria(self):
        self.denegar('banco','Conciliación bancaria')
        self.sin_lecturas(lambda:reportes.candidatos_conciliacion(self.db,1))

    def test_sugerencia_no_elude_permiso_de_contabilizar(self):
        for tipo,modulo,sub in [('PROVEEDOR','cxp','Pagos de proveedores'),('CLIENTE','cxc','Pagos de clientes'),('MANUAL','banco','Conciliación bancaria')]:
            self.denegar(modulo,sub,'contabilizar')
            self.sin_lecturas(lambda:reportes.contabilizar_conciliacion_bancaria(self.db,1,tipo,1))
            self.db.execute('DELETE FROM sgci_usuario_permisos_detalle');self.db.commit()


if __name__=='__main__':unittest.main()

import inspect
import unittest
from unittest.mock import patch
from modulos import usuarios, reportes_contables, compras_reclasificacion, compras_iva
from modulos import plan_cuentas, reglas_contables_ui, conciliacion_documental, contabilidad_reportes
from tests.soporte_flujos import preparar


class TestGuardasServicios(unittest.TestCase):
    def setUp(self):
        self.db=preparar(self)

    def test_denegacion_individual_bloquea_antes_de_escribir(self):
        casos=[(reportes_contables.deshacer_lote,'administracion','anular','Lotes'),
            (compras_reclasificacion.reclasificar_compras,'cxp','contabilizar','RCV Compras'),
            (compras_iva.regularizar_iva_historico_compras,'cxp','contabilizar','RCV Compras'),
            (plan_cuentas.guardar_rol,'administracion','editar','Matriz Contable'),
            (reglas_contables_ui.guardar_regla,'administracion','editar','Reglas Contables'),
            (conciliacion_documental.aplicar_abono_auxiliar_cliente,'cxc','editar','Pagos de clientes'),
            (conciliacion_documental.aplicar_pago_auxiliar_proveedor,'cxp','editar','Pagos de proveedores'),
            (contabilidad_reportes.asignar_anticipo_contable_a_cliente,'cxc','editar','Pagos de clientes'),
            (contabilidad_reportes.recuperar_anticipos_historicos_cliente,'cxc','editar','Pagos de clientes')]
        for funcion,modulo,accion,sub in casos:
            with self.subTest(funcion=funcion.__name__):
                self.db.execute('INSERT OR REPLACE INTO sgci_usuario_permisos_detalle VALUES(?,?,?,?,0)',
                                ('finanzas@example.com',modulo,sub,accion));self.db.commit()
                antes=list(self.db.iterdump())
                args=[self.db]+[1 for p in list(inspect.signature(funcion).parameters.values())[1:] if p.default is inspect.Parameter.empty]
                with patch.dict(funcion.__globals__,{'sgci_autorizar_operacion':usuarios.sgci_autorizar_operacion}):
                    with self.assertRaises(PermissionError):funcion(*args)
                self.assertEqual(list(self.db.iterdump()),antes)

    def test_permiso_contabilizar_nomina_no_amplia_alcance_rrhh(self):
        with patch.dict(conciliacion_documental.nomina_contabilizar_periodo.__globals__,{
            'sgci_rrhh_ids_autorizados':usuarios.sgci_rrhh_ids_autorizados,
            'sgci_identidad_actual':usuarios.sgci_identidad_actual}):
            with self.assertRaises(PermissionError):
                conciliacion_documental.nomina_contabilizar_periodo(self.db,'2026-11')

    def test_exportacion_balance_exige_exportar_ademas_de_ver(self):
        self.db.execute("DELETE FROM sgci_perfil_permisos WHERE accion='exportar'");self.db.commit()
        with patch.dict(reportes_contables.exportar_balance_ocho.__globals__,{'sgci_autorizar_operacion':usuarios.sgci_autorizar_operacion}):
            with self.assertRaises(PermissionError):reportes_contables.exportar_balance_ocho(self.db)

import inspect
import sqlite3
from datetime import date
from contextlib import closing
from pathlib import Path
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
import unittest
from unittest.mock import patch
from modulos import usuarios, reportes_contables, compras_reclasificacion, compras_iva
from modulos import plan_cuentas, reglas_contables_ui, conciliacion_documental, contabilidad_reportes, empresa
from tests.soporte_flujos import preparar


class TestGuardasServicios(unittest.TestCase):
    def setUp(self):
        self.db=preparar(self)

    def test_denegacion_individual_bloquea_antes_de_escribir(self):
        casos=[(conciliacion_documental.nomina_registrar_pago_activo,'nomina','contabilizar','Contabilización'),
            (compras_iva.registrar_pago_cliente,'cxc','crear','Pagos de clientes'),
            (compras_iva.registrar_pago_proveedor,'cxp','crear','Pagos de proveedores'),
            (reportes_contables.deshacer_lote,'administracion','anular','Lotes'),
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


class TestAltaTercerosAutorizada(unittest.TestCase):
    def setUp(self):self.db=preparar(self)

    def crear(self,tipo='cliente',**cambios):
        datos=dict(rut='12.345.678-5',nombre='Tercero sintético',email='prueba@example.com',telefono='123')
        datos.update(cambios)
        return empresa.sgci_crear_tercero(self.db,tipo,**datos)

    def test_cliente_y_proveedor_conservan_campos_y_auditan_sin_asiento(self):
        for tipo,tabla in [('cliente','clientes'),('proveedor','proveedores')]:
            nuevo=self.crear(tipo)
            fila=self.db.execute(f'SELECT rut,nombre,razon_social,email,telefono,activo FROM {tabla} WHERE id=?',(nuevo,)).fetchone()
            self.assertEqual(tuple(fila),('12345678-5','Tercero sintético','Tercero sintético','prueba@example.com','123',1))
        self.assertEqual(self.db.execute('SELECT count(*) FROM auditoria').fetchone()[0],2)
        self.assertEqual(self.db.execute('SELECT count(*) FROM libro_diario').fetchone()[0],0)

    def test_denegacion_individual_bloquea_antes_de_validar_o_escribir(self):
        self.db.execute("INSERT INTO sgci_usuario_permisos_detalle VALUES('finanzas@example.com','cxc','Clientes y estados de cuenta','crear',0)")
        self.db.commit()
        antes=list(self.db.iterdump())
        with self.assertRaises(PermissionError):self.crear(rut='inválido')
        self.assertEqual(list(self.db.iterdump()),antes)

    def test_permiso_de_compras_no_concede_alta_cliente(self):
        self.db.execute("DELETE FROM sgci_perfil_permisos WHERE modulo='cxc'");self.db.commit()
        self.crear('proveedor')
        with self.assertRaises(PermissionError):self.crear('cliente')

    def test_revocacion_de_perfil_impide_siguiente_alta(self):
        self.crear()
        self.db.execute("DELETE FROM sgci_perfil_permisos WHERE modulo='cxc' AND accion='crear'")
        self.db.commit()
        with self.assertRaises(PermissionError):self.crear(rut='11.111.111-1')

    def test_error_de_auditoria_revierte_alta(self):
        self.db.execute("CREATE TRIGGER fallo_auditoria BEFORE INSERT ON auditoria BEGIN SELECT RAISE(ABORT,'Fallo de prueba'); END")
        self.db.commit()
        with self.assertRaises(sqlite3.IntegrityError):self.crear()
        self.assertEqual(self.db.execute('SELECT count(*) FROM clientes').fetchone()[0],0)

    def test_duplicado_no_inserta_otra_fila_ni_auditoria(self):
        self.crear()
        with self.assertRaises(sqlite3.IntegrityError):self.crear()
        self.assertEqual(self.db.execute('SELECT count(*) FROM clientes').fetchone()[0],1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM auditoria').fetchone()[0],1)

    def test_transaccion_pendiente_no_se_confirma(self):
        self.db.execute("UPDATE bancos SET nombre='Pendiente' WHERE id=1")
        with self.assertRaises(RuntimeError):self.crear()
        self.assertTrue(self.db.in_transaction)
        self.db.rollback()
        self.assertEqual(self.db.execute('SELECT count(*) FROM clientes').fetchone()[0],0)

    def test_datos_invalidos_y_tabla_no_permitida_no_escriben(self):
        for cambio in ({'rut':'inválido'},{'nombre':'   '}):
            with self.subTest(cambio=cambio),self.assertRaises(ValueError):self.crear(**cambio)
        with self.assertRaises(ValueError):self.crear('auditoria')
        self.assertEqual(self.db.execute('SELECT count(*) FROM clientes').fetchone()[0],0)


class TestEntregaNominaAutorizada(unittest.TestCase):
    def setUp(self):
        self.db=preparar(self)
        self.db.execute("INSERT INTO nomina_anticipos(id,trabajador_id,periodo,fecha,monto) VALUES(1,1,'2026-11','2026-11-10',100)")
        self.db.commit()
        p=patch.dict(vars(conciliacion_documental),{
            'sgci_rrhh_ids_autorizados':lambda *a:{1}})
        p.start();self.addCleanup(p.stop)

    def contabilizar(self,**cambios):
        datos=dict(tabla='nomina_anticipos',registro_id=1,fecha='2026-11-10',monto=100,
                   cuenta_activo='1.1.07.01',cuenta_banco='1.1.02',glosa='Entrega de prueba')
        datos.update(cambios)
        return conciliacion_documental.nomina_registrar_pago_activo(self.db,**datos)

    def test_entrega_autorizada_cuadra_y_no_admite_reintento(self):
        asiento=self.contabilizar()
        fila=self.db.execute('SELECT SUM(debe),SUM(haber) FROM libro_diario WHERE asiento_id=?',(asiento,)).fetchone()
        self.assertEqual(tuple(fila),(100,100))
        with self.assertRaises(ValueError):self.contabilizar()
        self.assertEqual(self.db.execute('SELECT count(*) FROM libro_diario').fetchone()[0],2)

    def test_trabajador_ajeno_no_se_consulta_ni_contabiliza(self):
        with patch.dict(vars(conciliacion_documental),{'sgci_rrhh_ids_autorizados':lambda *a:{2}}):
            with self.assertRaises(ValueError):self.contabilizar()
        self.assertEqual(self.db.execute('SELECT count(*) FROM libro_diario').fetchone()[0],0)

    def test_tabla_no_permitida_se_rechaza(self):
        with self.assertRaises(ValueError):self.contabilizar(tabla='libro_diario')

    def test_datos_desactualizados_o_cuenta_incorrecta_se_rechazan(self):
        for cambio in ({'monto':101},{'fecha':'2026-11-11'},{'cuenta_activo':'1.1.07.02'},{'cuenta_banco':'inexistente'}):
            with self.subTest(cambio=cambio),self.assertRaises(ValueError):self.contabilizar(**cambio)
        self.assertEqual(self.db.execute('SELECT count(*) FROM libro_diario').fetchone()[0],0)

    def test_periodo_cerrado_bloquea_salida(self):
        with patch.dict(vars(conciliacion_documental),{'periodo_cerrado':lambda *a:True}):
            with self.assertRaises(ValueError):self.contabilizar()
        self.assertEqual(self.db.execute('SELECT count(*) FROM libro_diario').fetchone()[0],0)

    def test_error_de_auditoria_revierte_asiento_y_estado(self):
        self.db.execute("CREATE TRIGGER fallo_auditoria BEFORE INSERT ON auditoria BEGIN SELECT RAISE(ABORT,'Fallo de prueba'); END")
        self.db.commit()
        with self.assertRaises(sqlite3.IntegrityError):self.contabilizar()
        self.assertEqual(self.db.execute('SELECT count(*) FROM libro_diario').fetchone()[0],0)
        self.assertEqual(self.db.execute('SELECT contabilizado FROM nomina_anticipos WHERE id=1').fetchone()[0],0)

    def test_prestamo_usa_cuenta_y_monto_del_registro(self):
        self.db.execute("INSERT INTO nomina_prestamos(id,trabajador_id,fecha,monto_original) VALUES(1,1,'2026-11-10',100)")
        self.db.commit()
        self.contabilizar(tabla='nomina_prestamos',cuenta_activo='1.1.07.02')
        self.assertEqual(self.db.execute('SELECT contabilizado FROM nomina_prestamos WHERE id=1').fetchone()[0],1)


class TestAuxiliaresAutorizados(unittest.TestCase):
    def setUp(self):
        self.db=preparar(self)
        conciliacion_documental.sgci_conc_esquema(self.db)
        self.db.execute("INSERT INTO clientes(id,rut,nombre) VALUES(1,'3-5','Cliente de prueba')")
        self.db.executescript('''
            INSERT INTO compras(id,proveedor_id,monto_total,tipo_doc,folio) VALUES
                (1,1,100,33,'F1'),(2,1,-100,61,'NC1');
            INSERT INTO ventas(id,cliente_id,monto_total,tipo_doc,folio) VALUES
                (1,1,100,33,'V1'),(2,1,-100,61,'NCV1');
        ''')
        self.db.commit()

    def compensar(self,modulo='COMPRAS',monto=100,db=None):
        return conciliacion_documental.sgci_compensar_nc(db or self.db,modulo,1,2,1,monto,'Prueba')

    def test_compensacion_y_reversion_no_crean_asiento(self):
        self.compensar()
        self.assertEqual(self.db.execute('SELECT monto FROM sgci_compensaciones_documentos').fetchone()[0],100)
        conciliacion_documental.sgci_anular_compensacion(self.db,1,'Reversión autorizada')
        self.assertEqual(self.db.execute('SELECT anulada FROM sgci_compensaciones_documentos').fetchone()[0],1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM libro_diario').fetchone()[0],0)
        self.assertEqual(self.db.execute('SELECT count(*) FROM auditoria').fetchone()[0],2)

    def test_lectura_sin_permiso_no_devuelve_documentos(self):
        self.db.execute("DELETE FROM sgci_perfil_permisos WHERE modulo='cxc' AND submodulo='Clientes y estados de cuenta' AND accion='ver'")
        self.db.commit()
        with self.assertRaises(PermissionError):conciliacion_documental.sgci_nc_disponibles(self.db,'VENTAS',1)

    def test_permiso_compras_no_autoriza_operacion_de_ventas(self):
        self.db.execute("DELETE FROM sgci_perfil_permisos WHERE modulo='cxc'");self.db.commit()
        antes=list(self.db.iterdump())
        with self.assertRaises(PermissionError):self.compensar('VENTAS')
        self.assertEqual(list(self.db.iterdump()),antes)

    def test_reversion_filtra_el_auxiliar_autorizado_en_sql(self):
        self.compensar()
        self.db.execute("DELETE FROM sgci_perfil_permisos WHERE modulo='cxp' AND accion='anular'");self.db.commit()
        consultas=[];self.db.set_trace_callback(consultas.append)
        with self.assertRaises(ValueError):conciliacion_documental.sgci_anular_compensacion(self.db,1,'Motivo')
        self.assertTrue(any("modulo IN ('VENTAS')" in sql for sql in consultas))
        self.assertEqual(self.db.execute('SELECT anulada FROM sgci_compensaciones_documentos').fetchone()[0],0)

    def test_monto_fraccionario_o_no_finito_no_se_trunca(self):
        for valor in (1.5,'NaN','Infinity',0,-1,True):
            with self.subTest(valor=valor),self.assertRaises(ValueError):self.compensar(monto=valor)
        self.assertEqual(self.db.execute('SELECT count(*) FROM sgci_compensaciones_documentos').fetchone()[0],0)

    def test_error_de_auditoria_revierte_compensacion(self):
        self.db.execute("CREATE TRIGGER fallo_auditoria BEFORE INSERT ON auditoria BEGIN SELECT RAISE(ABORT,'Fallo de prueba'); END")
        self.db.commit()
        with self.assertRaises(sqlite3.IntegrityError):self.compensar()
        self.assertEqual(self.db.execute('SELECT count(*) FROM sgci_compensaciones_documentos').fetchone()[0],0)

    def test_reintento_no_sobreaplica_el_documento(self):
        self.compensar()
        with self.assertRaises(ValueError):self.compensar()
        self.assertEqual(self.db.execute('SELECT count(*) FROM sgci_compensaciones_documentos').fetchone()[0],1)

    def test_operacion_no_confirma_transaccion_ajena(self):
        self.db.execute("UPDATE proveedores SET nombre='Pendiente' WHERE id=1")
        with self.assertRaises(RuntimeError):self.compensar()
        self.assertTrue(self.db.in_transaction)
        self.db.rollback()
        self.assertNotEqual(self.db.execute('SELECT nombre FROM proveedores WHERE id=1').fetchone()[0],'Pendiente')

    def test_esquema_anidado_respeta_rollback_del_llamador(self):
        self.db.execute("UPDATE proveedores SET nombre='Pendiente' WHERE id=1")
        conciliacion_documental.sgci_conc_esquema(self.db)
        self.assertTrue(self.db.in_transaction)
        self.db.rollback()
        self.assertNotEqual(self.db.execute('SELECT nombre FROM proveedores WHERE id=1').fetchone()[0],'Pendiente')

    def test_pago_historico_no_se_consume_dos_veces(self):
        for ref in ('A','B'):
            conciliacion_documental.sgci_registrar_saldo_ejercicio(self.db,'COMPRAS',1,date.today().year-1,ref,100)
        self.db.execute("INSERT INTO pagos_proveedores(id,proveedor_id,monto) VALUES(1,1,100)");self.db.commit()
        conciliacion_documental.sgci_aplicar_pago_ejercicio(self.db,'COMPRAS',1,1,1,100)
        with self.assertRaises(ValueError):conciliacion_documental.sgci_aplicar_pago_ejercicio(self.db,'COMPRAS',1,2,1,1)
        self.assertEqual(self.db.execute('SELECT SUM(monto) FROM sgci_aplicaciones_ejercicios').fetchone()[0],100)

    def test_tercero_inexistente_no_genera_saldo(self):
        with self.assertRaises(ValueError):
            conciliacion_documental.sgci_registrar_saldo_ejercicio(self.db,'COMPRAS',999,date.today().year-1,'R',100)
        self.assertEqual(self.db.execute('SELECT count(*) FROM sgci_saldos_ejercicios').fetchone()[0],0)

    def test_dos_sesiones_no_compensan_dos_veces_el_mismo_saldo(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta=Path(carpeta)/'concurrencia.db'
            with closing(sqlite3.connect(ruta)) as copia:self.db.backup(copia)
            barrera=threading.Barrier(2)
            def ejecutar():
                with closing(sqlite3.connect(ruta,timeout=10)) as db:
                    db.row_factory=sqlite3.Row
                    barrera.wait(timeout=10)
                    try:
                        self.compensar(db=db)
                        return 'aplicado'
                    except ValueError:
                        return 'sin saldo'
            with ThreadPoolExecutor(max_workers=2) as ejecutor:
                futuros=[ejecutor.submit(ejecutar) for _ in range(2)]
                resultados=[f.result(timeout=20) for f in futuros]
            self.assertCountEqual(resultados,['aplicado','sin saldo'])
            with closing(sqlite3.connect(ruta)) as db:
                self.assertEqual(db.execute('SELECT SUM(monto) FROM sgci_compensaciones_documentos').fetchone()[0],100)

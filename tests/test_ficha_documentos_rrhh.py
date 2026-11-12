import sqlite3
import unittest
from hashlib import sha256
from unittest.mock import patch
from modulos import conciliacion_documental as servicio,usuarios
from tests.soporte_flujos import preparar


class TestFichaDocumentosRRHH(unittest.TestCase):
    def setUp(self):
        self.db=preparar(self)
        self.db.execute("INSERT INTO nomina_trabajadores(id,rut,nombre,fecha_creacion,tipo_cuenta) VALUES(1,'1-9','Propio','2020-01-01','Vista'),(2,'2-7','Ajeno','2020-01-02','Corriente')")
        self.db.execute("INSERT INTO sgci_usuario_trabajador VALUES('finanzas@example.com',1)")
        self.db.execute("INSERT INTO sgci_alcance_rrhh VALUES('finanzas@example.com','todos')")
        self.db.commit()
        p=patch.dict(vars(servicio),{'sgci_rrhh_ids_autorizados':usuarios.sgci_rrhh_ids_autorizados,'sha256':sha256})
        p.start();self.addCleanup(p.stop)

    def valores(self,**cambios):
        datos=dict(rut='1-9',nombre='Propio corregido',fecha_ingreso='2020-01-01',cargo='Cargo',tipo_contrato='Indefinido',sueldo_base=100,
            gratificacion_tipo='Monto mensual',gratificacion_valor=0,afp='Uno',salud_tipo='Fonasa',isapre='',salud_modalidad='7% legal',salud_valor=7,
            afc=1,anticipo_quincenal=1,anticipo_porcentaje=50,banco='Banco',tipo_cuenta='Vista',numero_cuenta='123',activo=1,fecha_creacion='2099-01-01')
        datos.update(cambios);return tuple(datos[c] for c in servicio.RRHH_CAMPOS_FICHA)

    def guardar(self,trabajador=1,vigencia='2030-01-01',**cambios):
        return servicio.nomina_guardar_ficha(self.db,self.valores(**cambios),vigencia,trabajador)

    def propios(self):
        self.db.execute("UPDATE sgci_alcance_rrhh SET alcance='propios'");self.db.commit()

    def documento(self,trabajador=1,**cambios):
        datos=dict(tipo='Contrato de trabajo',nombre_archivo='contrato.pdf',fecha='2030-01-01',observacion='Prueba',contenido=b'%PDF-1.4\nPrueba')
        datos.update(cambios);return servicio.rrhh_adjuntar_documento(self.db,trabajador,**datos)

    def test_crear_con_alcance_global_guarda_ficha_historial_y_auditoria(self):
        nuevo=self.guardar(None,rut='3-5',nombre='Nuevo')
        self.assertEqual(self.db.execute('SELECT trabajador_id FROM nomina_historial_condiciones').fetchone()[0],nuevo)
        self.assertEqual(self.db.execute('SELECT usuario FROM auditoria').fetchone()[0],'finanzas@example.com')
        self.assertEqual(self.db.execute('SELECT count(*) FROM libro_diario').fetchone()[0],0)

    def test_crear_con_alcance_propio_no_amplia_acceso(self):
        self.propios()
        with self.assertRaises(PermissionError):self.guardar(None,rut='3-5')
        self.assertEqual(self.db.execute('SELECT count(*) FROM nomina_trabajadores').fetchone()[0],2)

    def test_editar_propio_conserva_fecha_creacion_y_tipo_cuenta(self):
        self.propios();self.guardar()
        self.assertEqual(tuple(self.db.execute('SELECT fecha_creacion,tipo_cuenta FROM nomina_trabajadores WHERE id=1').fetchone()),('2020-01-01','Vista'))

    def test_editar_ajeno_se_rechaza_antes_de_leer_ficha(self):
        self.propios();consultas=[];self.db.set_trace_callback(consultas.append)
        with self.assertRaises(PermissionError):self.guardar(2,rut='2-7')
        self.db.set_trace_callback(None)
        self.assertFalse(any('FROM nomina_trabajadores' in sql for sql in consultas))

    def test_denegacion_individual_impide_editar_y_adjuntar(self):
        self.db.execute("INSERT INTO sgci_usuario_permisos_detalle VALUES('finanzas@example.com','nomina','Trabajadores','editar',0)");self.db.commit()
        with self.assertRaises(PermissionError):self.guardar()
        with self.assertRaises(PermissionError):self.documento()

    def test_condiciones_pasadas_no_se_sobrescriben_si_hay_nomina_contabilizada(self):
        self.guardar(vigencia='2026-01-01')
        self.db.execute("INSERT INTO nomina_liquidaciones(periodo,trabajador_id,estado) VALUES('2026-11',1,'CONTABILIZADO')");self.db.commit()
        antes=list(self.db.iterdump())
        with self.assertRaises(ValueError):self.guardar(vigencia='2026-01-01',sueldo_base=200)
        self.assertEqual(list(self.db.iterdump()),antes)
        self.guardar(vigencia='2027-01-01',sueldo_base=200)
        self.assertEqual(self.db.execute('SELECT count(*) FROM nomina_historial_condiciones').fetchone()[0],2)

    def test_editar_nombre_sin_cambiar_condiciones_preserva_historial_contabilizado(self):
        self.guardar(vigencia='2026-01-01')
        historial=list(self.db.execute('SELECT * FROM nomina_historial_condiciones'))
        self.db.execute("INSERT INTO nomina_liquidaciones(periodo,trabajador_id,estado) VALUES('2026-11',1,'CONTABILIZADO')");self.db.commit()
        self.guardar(vigencia='2026-01-01',nombre='Nombre corregido')
        self.assertEqual(list(self.db.execute('SELECT * FROM nomina_historial_condiciones')),historial)

    def test_fallo_historial_revierte_ficha_completa(self):
        self.db.execute("CREATE TRIGGER fallo_historial BEFORE INSERT ON nomina_historial_condiciones BEGIN SELECT RAISE(ABORT,'Fallo de prueba'); END");self.db.commit()
        antes=list(self.db.iterdump())
        with self.assertRaises(sqlite3.IntegrityError):self.guardar()
        self.assertEqual(list(self.db.iterdump()),antes)

    def test_ficha_invalida_no_modifica_datos(self):
        for cambio in ({'nombre':''},{'sueldo_base':float('nan')},{'fecha_ingreso':'2026-02-30'},{'anticipo_porcentaje':101}):
            with self.subTest(cambio=cambio),self.assertRaises(ValueError):self.guardar(**cambio)

    def test_documento_autorizado_sanea_nombre_y_conserva_contenido(self):
        nuevo=self.documento(nombre_archivo=r'C:\carpeta\contrato.pdf')
        doc=servicio.rrhh_descargar_documento(self.db,1,nuevo)
        self.assertEqual(doc['nombre_archivo'],'contrato.pdf')
        self.assertEqual(doc['contenido'],b'%PDF-1.4\nPrueba')
        self.assertIsNone(servicio.rrhh_descargar_documento(self.db,2,nuevo))

    def test_documento_ajeno_o_exportacion_revocada_no_devuelven_blob(self):
        nuevo=self.documento(2)
        self.propios()
        with self.assertRaises(PermissionError):servicio.rrhh_descargar_documento(self.db,2,nuevo)
        self.db.execute("INSERT INTO sgci_usuario_permisos_detalle VALUES('finanzas@example.com','nomina','Trabajadores','exportar',0)");self.db.commit()
        consultas=[];self.db.set_trace_callback(consultas.append)
        with self.assertRaises(PermissionError):servicio.rrhh_descargar_documento(self.db,1,nuevo)
        self.db.set_trace_callback(None)
        self.assertFalse(any('FROM rrhh_documentos' in sql for sql in consultas))

    def test_documento_invalido_o_excesivo_no_se_guarda(self):
        for cambio in ({'contenido':b'No PDF'},{'contenido':b'%PDF-'+b'x'*(8*1024*1024)},{'nombre_archivo':'archivo.txt'},{'tipo':'otro'}):
            with self.subTest(cambio=list(cambio)),self.assertRaises(ValueError):self.documento(**cambio)
        self.assertEqual(self.db.execute('SELECT count(*) FROM rrhh_documentos').fetchone()[0],0)

    def test_error_auditoria_revierte_ficha_y_documento(self):
        self.db.execute("CREATE TRIGGER fallo_auditoria BEFORE INSERT ON auditoria BEGIN SELECT RAISE(ABORT,'Fallo de prueba'); END");self.db.commit()
        antes=list(self.db.iterdump())
        with self.assertRaises(sqlite3.IntegrityError):self.guardar()
        with self.assertRaises(sqlite3.IntegrityError):self.documento()
        self.assertEqual(list(self.db.iterdump()),antes)

    def test_transaccion_ajena_se_conserva(self):
        self.db.execute("UPDATE bancos SET nombre='Pendiente' WHERE id=1")
        with self.assertRaises(RuntimeError):self.guardar()
        with self.assertRaises(RuntimeError):self.documento()
        self.assertTrue(self.db.in_transaction);self.db.rollback()

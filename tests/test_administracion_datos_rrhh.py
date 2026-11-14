import os
import sqlite3
import unittest
from unittest.mock import patch
from modulos import usuarios


class TestAdministracionDatosRRHH(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:')
        self.db.row_factory=sqlite3.Row
        self.addCleanup(self.db.close)
        self.db.execute('CREATE TABLE nomina_trabajadores(id INTEGER PRIMARY KEY)')
        usuarios.sgci_crear_seguridad(self.db)
        self.db.execute('INSERT INTO nomina_trabajadores VALUES(1),(2)');self.db.commit()
        p=patch.dict(vars(usuarios),{'os':os});p.start();self.addCleanup(p.stop)
        p=patch.object(usuarios,'sgci_es_propietario',return_value=True);p.start();self.addCleanup(p.stop)
        p=patch.object(usuarios,'sgci_identidad_actual',return_value='admin@example.com');p.start();self.addCleanup(p.stop)
        p=patch.dict(os.environ,{'SGCI_ADMIN_EMAIL':'admin@example.com'});p.start();self.addCleanup(p.stop)

    def crear(self,email='persona@example.com'):
        usuarios.sgci_guardar_usuario(self.db,email,'Finanzas',True,'Persona','Cargo')

    def test_usuario_nuevo_tiene_alcance_propio(self):
        self.crear()
        self.assertEqual(self.db.execute('SELECT alcance FROM sgci_alcance_rrhh').fetchone()[0],'propios')

    def test_empleado_no_puede_ampliar_alcance_ni_vinculos(self):
        self.crear()
        antes=list(self.db.iterdump())
        with patch.object(usuarios,'sgci_es_propietario',return_value=False):
            for funcion,args in ((usuarios.sgci_guardar_usuario,('otro@example.com','Finanzas',True)),
                                 (usuarios.sgci_vincular_trabajador,('persona@example.com',2)),
                                 (usuarios.sgci_guardar_alcance_rrhh,('persona@example.com','todos'))):
                with self.subTest(funcion=funcion.__name__),self.assertRaises(PermissionError):funcion(self.db,*args)
        self.assertEqual(list(self.db.iterdump()),antes)

    def test_autorizacion_explicita_y_revocacion(self):
        self.crear()
        usuarios.sgci_vincular_trabajador(self.db,'persona@example.com',1)
        usuarios.sgci_guardar_alcance_rrhh(self.db,'persona@example.com','autorizados',[2])
        with patch.object(usuarios,'sgci_es_propietario',return_value=False):
            self.assertEqual(usuarios.sgci_rrhh_ids_autorizados(self.db,'persona@example.com'),{1,2})
        usuarios.sgci_guardar_alcance_rrhh(self.db,'persona@example.com','propios')
        with patch.object(usuarios,'sgci_es_propietario',return_value=False):
            self.assertEqual(usuarios.sgci_rrhh_ids_autorizados(self.db,'persona@example.com'),{1})

    def test_ficha_inexistente_no_revoca_autorizacion_anterior(self):
        self.crear()
        usuarios.sgci_guardar_alcance_rrhh(self.db,'persona@example.com','autorizados',[1])
        with self.assertRaises(ValueError):usuarios.sgci_guardar_alcance_rrhh(self.db,'persona@example.com','autorizados',[999])
        self.assertEqual(self.db.execute('SELECT trabajador_id FROM sgci_rrhh_autorizados').fetchone()[0],1)

    def test_dos_usuarios_no_comparten_identidad_laboral(self):
        self.crear();self.crear('otra@example.com')
        usuarios.sgci_vincular_trabajador(self.db,'persona@example.com',1)
        with self.assertRaises(sqlite3.IntegrityError):usuarios.sgci_vincular_trabajador(self.db,'otra@example.com',1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM sgci_usuario_trabajador').fetchone()[0],1)

    def test_no_modifica_cuenta_del_administrador(self):
        with self.assertRaises(ValueError):usuarios.sgci_guardar_usuario(self.db,'admin@example.com','Finanzas',False)

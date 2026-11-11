"""Autorización real antes de consultas y escrituras bancarias, con SQLite sintético."""
import importlib
import inspect
import sqlite3
import unittest
from unittest.mock import patch
from modulos import usuarios

OPERACIONES = {
  "modulos/contabilidad_reportes.py": {
    "sgci_conciliar_lineas_existentes": [
      "banco",
      "conciliar",
      "Conciliación bancaria"
    ],
    "sgci_conciliar_cheque_protestado": [
      "banco",
      "conciliar",
      "Conciliación bancaria"
    ],
    "importar_cartola": [
      "banco",
      "importar",
      "Bancos y cartolas"
    ],
    "eliminar_importacion_cartola": [
      "banco",
      "eliminar",
      "Bancos y cartolas"
    ],
    "sgci_corregir_signo_cartola_pendiente": [
      "banco",
      "editar",
      "Bancos y cartolas"
    ],
    "crear_obligacion_manual": [
      "banco",
      "crear",
      "Conciliación bancaria"
    ],
    "sgci_cobro_mixto": [
      "banco",
      "contabilizar",
      "Conciliación bancaria"
    ],
    "registrar_movimiento_manual": [
      "banco",
      "crear",
      "Bancos y cartolas"
    ],
    "contabilizar_conciliacion_bancaria": [
      "banco",
      "conciliar",
      "Conciliación bancaria"
    ],
    "contabilizar_imputacion_manual_bancaria": [
      "banco",
      "contabilizar",
      "Conciliación bancaria"
    ],
    "contabilizar_imputacion_multiple_bancaria": [
      "banco",
      "contabilizar",
      "Conciliación bancaria"
    ],
    "contabilizar_cobro_cliente_desde_cartola": [
      "banco",
      "contabilizar",
      "Conciliación bancaria"
    ],
    "contabilizar_cobro_cliente_sin_documento": [
      "banco",
      "contabilizar",
      "Conciliación bancaria"
    ]
  },
  "modulos/conciliacion_documental.py": {
    "revertir_pago_proveedor_cartola": [
      "banco",
      "anular",
      "Conciliación bancaria"
    ],
    "corregir_conciliacion_manual": [
      "banco",
      "anular",
      "Conciliación bancaria"
    ],
    "revertir_abono_cliente_cartola": [
      "banco",
      "anular",
      "Conciliación bancaria"
    ],
    "revertir_anticipo_nomina_cartola": [
      "banco",
      "anular",
      "Conciliación bancaria"
    ],
    "sgci_contabilizar_devolucion_proveedor": [
      "banco",
      "contabilizar",
      "Conciliación bancaria"
    ],
    "contabilizar_pago_proveedor_desde_cartola": [
      "banco",
      "contabilizar",
      "Conciliación bancaria"
    ],
    "contabilizar_pago_proveedor_sin_documento": [
      "banco",
      "contabilizar",
      "Conciliación bancaria"
    ],
    "contabilizar_anticipo_nomina_desde_cartola": [
      "banco",
      "contabilizar",
      "Conciliación bancaria"
    ]
  }
}

class AccesoNegocio(Exception):
    pass

class ConexionVigilada:
    def __init__(self, db):
        self.db = db
        self.negocio = 0
    def execute(self, sql, args=()):
        if any(tabla in sql for tabla in (
                'sgci_usuarios', 'sgci_perfil_permisos',
                'sgci_usuario_permisos_detalle', 'sgci_permisos')):
            return self.db.execute(sql, args)
        self.negocio += 1
        raise AccesoNegocio('Primera consulta de negocio')
    def __getattr__(self, nombre):
        self.negocio += 1
        raise AccesoNegocio(nombre)

class TestServiciosBancarios(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.db.row_factory = sqlite3.Row
        usuarios.sgci_crear_seguridad(self.db)
        self.db.execute("INSERT INTO sgci_usuarios(email,rol,activo) VALUES('banco@example.com','Finanzas',1)")
        self.conn = ConexionVigilada(self.db)
        self.addCleanup(self.db.close)
        for nombre, valor in [('sgci_es_propietario',False), ('sgci_identidad_actual','banco@example.com')]:
            p = patch.object(usuarios, nombre, return_value=valor)
            p.start()
            self.addCleanup(p.stop)

    def ejecutar(self, archivo, nombre, permiso, caso):
        modulo, accion, sub = permiso
        if caso in ('perfil', 'revocado', 'inactivo'):
            self.db.execute('INSERT INTO sgci_perfil_permisos VALUES(?,?,?,?,1)', ('Finanzas',modulo,sub,accion))
        if caso == 'individual':
            self.db.execute('INSERT INTO sgci_usuario_permisos_detalle VALUES(?,?,?,?,1)', ('banco@example.com',modulo,sub,accion))
        if caso == 'revocado':
            self.db.execute('INSERT INTO sgci_usuario_permisos_detalle VALUES(?,?,?,?,0)', ('banco@example.com',modulo,sub,accion))
        if caso == 'inactivo':
            self.db.execute('UPDATE sgci_usuarios SET activo=0')
        if caso == 'heredado':
            self.db.execute('INSERT INTO sgci_permisos VALUES(?,?,?,1)', ('banco@example.com',modulo,accion))
        if caso == 'otro_submodulo':
            otro = next(s for s in usuarios.SGCI_SUBMODULOS[modulo] if s != sub)
            self.db.execute('INSERT INTO sgci_perfil_permisos VALUES(?,?,?,?,1)', ('Finanzas',modulo,otro,accion))
        func = getattr(importlib.import_module(archivo[:-3].replace('/','.')), nombre)
        args = [self.conn] + [1 for p in list(inspect.signature(func).parameters.values())[1:] if p.default is inspect.Parameter.empty]
        esperado = AccesoNegocio if caso in ('perfil','individual') else PermissionError
        def autorizar(*args, **kwargs):
            usuarios.sgci_autorizar_operacion(*args, **kwargs)
            raise AccesoNegocio('Autorización concedida; flujo contable se prueba aparte')
        with patch.dict(func.__globals__, {'sgci_autorizar_operacion': autorizar}):
            with self.assertRaises(esperado):
                func(*args)
        self.assertEqual(self.conn.negocio, 0)


def crear_prueba(archivo, nombre, permiso, caso):
    def prueba(self):
        self.ejecutar(archivo, nombre, permiso, caso)
    return prueba

for archivo, funciones in OPERACIONES.items():
    for nombre, permiso in funciones.items():
        for caso in ('sin_permiso','perfil','individual','revocado','inactivo','heredado','otro_submodulo'):
            setattr(TestServiciosBancarios, 'test_'+nombre+'_'+caso,
                    crear_prueba(archivo,nombre,permiso,caso))

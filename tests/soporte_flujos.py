"""Dependencias reales de servicios y SQLite sintético; sin red ni Streamlit."""
from datetime import datetime, date
from decimal import Decimal, ROUND_HALF_UP
import sqlite3
import re
from unittest.mock import patch
import pandas as pd
from modulos import esquema, contabilidad, plan_cuentas, reglas_contables, utilidades
from modulos import conciliacion_documental, contabilidad_reportes, usuarios, empresa, tesoreria
from modulos import contabilidad_asientos, reportes_contables


def preparar(test):
    db = sqlite3.connect(':memory:')
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    test.addCleanup(db.close)
    simbolos = {'pd':pd, 're':re, 'datetime':datetime, 'date':date, 'Decimal':Decimal,'ROUND_HALF_UP':ROUND_HALF_UP,
                'ROLES':contabilidad.ROLES, 'Plan':plan_cuentas.Plan,
                'DOC_NOTA_CREDITO':utilidades.DOC_NOTA_CREDITO,
                'agregar_columna':esquema.agregar_columna,
                'sgci_autorizar_operacion':usuarios.sgci_autorizar_operacion,
                'sgci_puede_submodulo':usuarios.sgci_puede_submodulo,
                'tabla_existe':esquema.tabla_existe,
                'sgci_identidad_actual':lambda:'finanzas@example.com',
                'periodo_cerrado':contabilidad_reportes.periodo_cerrado,
                'siguiente_asiento':reglas_contables.siguiente_asiento,
                'nomina_asiento_linea':conciliacion_documental.nomina_asiento_linea,
                'armar_asiento':reglas_contables.armar_asiento,
                'obtener_entidad':contabilidad_asientos.obtener_entidad,
                'nombre_documento':utilidades.nombre_documento,
                'validar_rut':utilidades.validar_rut,
                'normalizar_rut':utilidades.normalizar_rut,
                'cargar_roles':plan_cuentas.cargar_roles}
    simbolos.update({n:getattr(utilidades,n) for n in ('clp_round','limpiar_texto','fecha_iso','numero','normalizar_columnas')})
    for modulo in (esquema,plan_cuentas,utilidades,conciliacion_documental,tesoreria,empresa,contabilidad_reportes,contabilidad_asientos,reglas_contables,reportes_contables):
        p = patch.dict(vars(modulo),simbolos)
        p.start(); test.addCleanup(p.stop)
    for nombre, valor in (('sgci_es_propietario',False),('sgci_identidad_actual','finanzas@example.com')):
        p = patch.object(usuarios,nombre,return_value=valor)
        p.start(); test.addCleanup(p.stop)
    esquema.crear_esquema(db)
    db.execute('CREATE TABLE IF NOT EXISTS nomina_trabajadores(id INTEGER PRIMARY KEY)')
    usuarios.sgci_crear_seguridad(db)
    empresa.oc_crear_tablas(db)
    tesoreria.tes_crear_tablas(db)
    plan_cuentas.instalar_plan_base(db)
    db.execute("INSERT INTO sgci_usuarios(email,rol,activo) VALUES('finanzas@example.com','Finanzas',1)")
    db.executemany('INSERT INTO sgci_perfil_permisos(perfil,modulo,submodulo,accion,permitido) VALUES(?,?,?,?,1)',
        [('Finanzas',m,s,a) for m,subs in usuarios.SGCI_SUBMODULOS.items() for s in subs for a in usuarios.SGCI_ACCIONES_SUB])
    db.execute("INSERT INTO proveedores(id,rut,nombre) VALUES(1,'1-9','Proveedor de prueba'),(2,'2-7','Otro proveedor')")
    db.execute("INSERT INTO bancos(id,nombre,cuenta_contable) VALUES(1,'Banco de prueba','1.1.02')")
    db.commit()
    return db

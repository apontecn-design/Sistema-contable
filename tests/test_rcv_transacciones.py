"""Pruebas de reversión de transacciones RCV con la función real de CONTEM."""
import sqlite3
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from modulos import contabilidad_asientos


class Documentos:
    def __init__(self,filas):
        self.filas=filas
    def itertuples(self):
        return iter(self.filas)


class TestRCVTransacciones(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:')
        self.db.row_factory=sqlite3.Row
        self.db.executescript("""
            CREATE TABLE proveedores(id INTEGER PRIMARY KEY,rut TEXT,nombre TEXT,
                razon_social TEXT,activo INTEGER,fecha_creacion TEXT,centro_costo TEXT,
                cuenta_defecto TEXT);
            CREATE TABLE clientes(id INTEGER PRIMARY KEY,rut TEXT,nombre TEXT,
                razon_social TEXT,activo INTEGER,fecha_creacion TEXT,cuenta_defecto TEXT);
            CREATE TABLE compras(id INTEGER PRIMARY KEY,fecha TEXT,proveedor_id INTEGER,
                cuenta_gasto TEXT,centro_costo TEXT,monto_neto REAL,iva REAL,
                monto_total REAL,glosa TEXT,tipo_doc INTEGER,folio TEXT,lote_id TEXT);
            CREATE TABLE ventas(id INTEGER PRIMARY KEY,fecha TEXT,cliente_id INTEGER,
                cuenta_ingreso TEXT,monto_neto REAL,iva REAL,monto_total REAL,
                glosa TEXT,tipo_doc INTEGER,folio TEXT,lote_id TEXT);
            CREATE TABLE libro_diario(id INTEGER PRIMARY KEY,fecha TEXT,cuenta TEXT,
                debe REAL,haber REAL,glosa TEXT,centro_costo TEXT,codigo_cuenta TEXT,
                asiento_id INTEGER,lote_id TEXT,origen TEXT);
        """)
        self.db.commit()
        self.base={
            'sgci_autorizar_operacion':lambda *args:None,
            'Plan':lambda conn:SimpleNamespace(hojas={'100':'Gasto'},todos={'100':'Gasto'}),
            'cargar_roles':lambda conn:{},
            'siguiente_asiento':lambda conn:0,
            'normalizar_rut':lambda rut:rut,
            'nombre_documento':lambda tipo:'Factura',
            'datetime':__import__('datetime').datetime,
        }
        self.fila=SimpleNamespace(cuenta_codigo='100',cuenta_sugerida='100',
            rut='11-1',razon_social='Proveedor',fecha_doc='2026-11-10',
            fecha_recepcion='2026-11-10',tipo_doc=33,folio='1',signo=1,
            neto=100,exento=0,neto_af=0,iva=19,iva_af=0,total=119)

    def tearDown(self):
        self.db.close()

    def conteos(self):
        return tuple(self.db.execute('SELECT count(*) FROM '+t).fetchone()[0]
            for t in ('compras','ventas','proveedores','clientes','libro_diario'))

    def test_compras_reversion_por_error_de_asiento(self):
        def fallo(*args):
            raise RuntimeError('Error simulado al generar asiento')
        with patch.dict(contabilidad_asientos.contabilizar_rcv.__globals__,
                        {**self.base,'armar_asiento':fallo,
                         'obtener_entidad':contabilidad_asientos.obtener_entidad}):
            with self.assertRaises(RuntimeError):
                contabilidad_asientos.contabilizar_rcv(
                    self.db,'compras',Documentos([self.fila]))
        self.assertEqual(self.conteos(),(0,0,0,0,0))

    def test_ventas_reversion_por_error_de_asiento(self):
        def fallo(*args):
            raise RuntimeError('Error simulado al generar asiento')
        with patch.dict(contabilidad_asientos.contabilizar_rcv.__globals__,
                        {**self.base,'armar_asiento':fallo,
                         'obtener_entidad':contabilidad_asientos.obtener_entidad}):
            with self.assertRaises(RuntimeError):
                contabilidad_asientos.contabilizar_rcv(
                    self.db,'ventas',Documentos([self.fila]))
        self.assertEqual(self.conteos(),(0,0,0,0,0))

    def test_compra_exitosa_cuadra_debe_haber(self):
        with patch.dict(contabilidad_asientos.contabilizar_rcv.__globals__,
                        {**self.base,
                         'armar_asiento':lambda *args:[('100',119,0),('100',0,119)],
                         'obtener_entidad':contabilidad_asientos.obtener_entidad}):
            r=contabilidad_asientos.contabilizar_rcv(
                self.db,'compras',Documentos([self.fila]))
        self.assertEqual(r['documentos'],1)
        self.assertEqual(self.conteos(),(1,0,1,0,2))
        debe,haber=self.db.execute(
            'SELECT sum(debe),sum(haber) FROM libro_diario').fetchone()
        self.assertEqual(debe,haber)


if __name__=='__main__':
    unittest.main()

import sqlite3
from types import SimpleNamespace
import unittest
from modulos import contabilidad_asientos
from tests.soporte_flujos import preparar


class Documentos:
    def __init__(self,filas):self.filas=filas
    def itertuples(self):return iter(self.filas)


class TestRCVIntegracionReal(unittest.TestCase):
    def setUp(self):self.db=preparar(self)

    def fila(self,tipo='compras',folio='F1',documento=33,neto=100):
        return SimpleNamespace(cuenta_codigo='5.1.01' if tipo=='compras' else '4.1.01',
            cuenta_sugerida='5.1.01' if tipo=='compras' else '4.1.01',rut='1-9',razon_social='Tercero de prueba',
            fecha_doc='2026-11-11',fecha_recepcion='2026-11-11',tipo_doc=documento,folio=folio,
            signo=-1 if documento==61 else 1,neto=neto,exento=0,neto_af=0,iva=neto*.19,iva_af=0,total=neto*1.19)

    def test_factura_y_nota_credito_compra_con_reglas_reales(self):
        contabilidad_asientos.contabilizar_rcv(self.db,'compras',Documentos([self.fila(),self.fila(folio='NC1',documento=61,neto=30)]))
        gasto=self.db.execute("SELECT SUM(debe-haber) FROM libro_diario WHERE codigo_cuenta='5.1.01'").fetchone()[0]
        self.assertAlmostEqual(gasto,70)
        self.assertAlmostEqual(self.db.execute('SELECT SUM(debe-haber) FROM libro_diario').fetchone()[0],0)

    def test_factura_venta_con_iva_y_balance(self):
        contabilidad_asientos.contabilizar_rcv(self.db,'ventas',Documentos([self.fila('ventas')]))
        self.assertAlmostEqual(self.db.execute("SELECT SUM(haber) FROM libro_diario WHERE codigo_cuenta='2.1.01.02'").fetchone()[0],19)
        self.assertAlmostEqual(self.db.execute('SELECT SUM(debe-haber) FROM libro_diario').fetchone()[0],0)

    def test_reimportacion_duplicada_preserva_asientos_y_documentos(self):
        docs=Documentos([self.fila()])
        contabilidad_asientos.contabilizar_rcv(self.db,'compras',docs)
        antes=list(self.db.iterdump())
        with self.assertRaises(sqlite3.IntegrityError):contabilidad_asientos.contabilizar_rcv(self.db,'compras',docs)
        self.assertEqual(list(self.db.iterdump()),antes)

    def test_periodo_cerrado_rechaza_antes_de_cambiar_tercero(self):
        self.db.execute("INSERT INTO periodos_contables(periodo,estado) VALUES('2026-11','CERRADO')");self.db.commit()
        antes=list(self.db.iterdump())
        with self.assertRaises(ValueError):contabilidad_asientos.contabilizar_rcv(self.db,'compras',Documentos([self.fila()]))
        self.assertEqual(list(self.db.iterdump()),antes)

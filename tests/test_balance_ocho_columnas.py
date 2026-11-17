from decimal import Decimal
from io import BytesIO
import sqlite3
import unittest
from openpyxl import load_workbook
from pypdf import PdfReader
from modulos.balance_ocho_columnas import generar_balance_ocho_columnas, balance_ocho_excel, balance_ocho_pdf


class TestBalanceOchoColumnas(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.addCleanup(self.db.close)
        self.db.executescript('''
            CREATE TABLE plan_cuentas(codigo TEXT PRIMARY KEY,nombre TEXT,tipo TEXT);
            CREATE TABLE libro_diario(fecha TEXT,codigo_cuenta TEXT,debe REAL,haber REAL);
            INSERT INTO plan_cuentas VALUES('1','Banco','Activo'),('2','IVA','Pasivo'),
                ('3','Capital','Patrimonio'),('4','Ventas','Ingresos'),('5','Gasto','Gastos');
            INSERT INTO libro_diario VALUES
                ('2026-01-01','1',1000,0),('2026-01-01','3',0,1000),
                ('2026-02-01','1',119,0),('2026-02-01','4',0,100),('2026-02-01','2',0,19),
                ('2026-02-02','5',40,0),('2026-02-02','1',0,40);
        ''')

    def test_utilidad_cuadra_los_cuatro_pares(self):
        informe = generar_balance_ocho_columnas(self.db)
        self.assertTrue(informe['cuadrado'])
        self.assertEqual(informe['resultado'], 60)
        cierre = informe['resumen'].iloc[1]
        self.assertEqual(cierre['Pasivo'], 60)
        self.assertEqual(cierre['Pérdidas'], 60)
        banco = informe['detalle'].set_index('Codigo').loc['1']
        self.assertEqual((banco['Debe'],banco['Haber'],banco['Deudor'],banco['Activo']), (1119,40,1079,1079))

    def test_perdida_se_traslada_a_activo_y_ganancias(self):
        self.db.executescript("INSERT INTO libro_diario VALUES('2026-02-03','5',100,0),('2026-02-03','1',0,100)")
        informe = generar_balance_ocho_columnas(self.db)
        self.assertEqual(informe['resultado'], -40)
        self.assertTrue(informe['cuadrado'])
        self.assertEqual(informe['resumen'].iloc[1]['Activo'], 40)
        self.assertEqual(informe['resumen'].iloc[1]['Ganancias'], 40)

    def test_saldos_inversos_respetan_signo_y_naturaleza(self):
        self.db.execute('DELETE FROM libro_diario')
        self.db.executescript("INSERT INTO libro_diario VALUES('2026-01-01','1',0,50),('2026-01-01','2',50,0),('2026-01-01','4',20,0),('2026-01-01','5',0,20)")
        detalle = generar_balance_ocho_columnas(self.db)['detalle'].set_index('Codigo')
        self.assertEqual(detalle.loc['1','Pasivo'], 50)
        self.assertEqual(detalle.loc['2','Activo'], 50)
        self.assertEqual(detalle.loc['4','Pérdidas'], 20)
        self.assertEqual(detalle.loc['5','Ganancias'], 20)

    def test_intervalo_no_incorpora_otros_periodos(self):
        informe = generar_balance_ocho_columnas(self.db, '2026-02-01', '2026-02-01')
        self.assertEqual(informe['resumen'].iloc[0]['Debe'], 119)
        self.assertEqual(informe['resumen'].iloc[0]['Haber'], 119)

    def test_no_oculta_desbalance(self):
        self.db.execute("INSERT INTO libro_diario VALUES('2026-01-01','1',1,0)")
        informe = generar_balance_ocho_columnas(self.db)
        self.assertFalse(informe['cuadrado'])
        self.assertEqual(informe['cuadraturas']['inventario'], 1)

    def test_rechaza_cuenta_sin_plan(self):
        self.db.execute("INSERT INTO libro_diario VALUES('2026-01-01','ausente',1,0)")
        with self.assertRaises(ValueError): generar_balance_ocho_columnas(self.db)

    def test_rechaza_clasificacion_desconocida(self):
        self.db.execute("UPDATE plan_cuentas SET tipo='sin clasificar' WHERE codigo='1'")
        with self.assertRaises(ValueError): generar_balance_ocho_columnas(self.db)

    def test_fechas_invertidas(self):
        with self.assertRaises(ValueError): generar_balance_ocho_columnas(self.db,'2026-12-01','2026-01-01')

    def test_importes_decimales_no_generan_descuadres_binarios(self):
        self.db.execute('DELETE FROM libro_diario')
        for monto in (0.1,0.2,0.3):
            self.db.execute("INSERT INTO libro_diario VALUES('2026-01-01','1',?,0)",(monto,))
            self.db.execute("INSERT INTO libro_diario VALUES('2026-01-01','3',0,?)",(monto,))
        informe = generar_balance_ocho_columnas(self.db)
        self.assertEqual(informe['resumen'].iloc[0]['Debe'], Decimal('0.6'))
        self.assertTrue(informe['cuadrado'])

    def test_excel_tiene_8_columnas_numericas_y_no_formulas_de_nombres(self):
        self.db.execute("UPDATE plan_cuentas SET nombre='=1+1' WHERE codigo='1'")
        libro = load_workbook(BytesIO(balance_ocho_excel(generar_balance_ocho_columnas(self.db))))
        hoja = libro.active
        self.assertEqual(hoja.max_column, 10)
        self.assertEqual(hoja['B5'].value, '=1+1')
        self.assertEqual(hoja['B5'].data_type, 's')
        self.assertEqual(hoja['C5'].value, 1119)
        self.assertEqual(hoja.page_setup.orientation, 'landscape')

    def test_pdf_imprimible_contiene_resumen(self):
        pdf = PdfReader(BytesIO(balance_ocho_pdf(generar_balance_ocho_columnas(self.db))))
        self.assertGreater(float(pdf.pages[0].mediabox.width),float(pdf.pages[0].mediabox.height))
        contenido = ''.join(p.extract_text() for p in pdf.pages)
        self.assertIn('Utilidad del ejercicio',contenido)
        self.assertIn('Banco',contenido)

    def test_consulta_y_exportacion_no_modifican_datos(self):
        antes = self.db.total_changes
        informe = generar_balance_ocho_columnas(self.db)
        balance_ocho_pdf(informe)
        balance_ocho_excel(informe)
        self.assertEqual(self.db.total_changes, antes)

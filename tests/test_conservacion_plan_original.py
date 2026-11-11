"""Regresión: instalar el catálogo base nunca sustituye el plan contable existente."""
import sqlite3
import unittest

from modulos.plan_cuentas import instalar_plan_base, reorganizar_plan_2026_seguro


class TestConservacionPlanOriginal(unittest.TestCase):
    def test_conserva_cuentas_personalizadas_y_saldos(self):
        with sqlite3.connect(":memory:") as db:
            db.execute("""CREATE TABLE plan_cuentas (
                codigo TEXT PRIMARY KEY, nombre TEXT, categoria TEXT,
                tipo TEXT, padre_codigo TEXT, nivel INTEGER)""")
            db.execute("""CREATE TABLE libro_diario (
                id INTEGER PRIMARY KEY, codigo_cuenta TEXT, debe INTEGER, haber INTEGER)""")
            db.execute("""INSERT INTO plan_cuentas VALUES
                ('1.1.02','Banco histórico de la empresa','Activo','Activo','1.1',3)""")
            db.execute("""INSERT INTO plan_cuentas VALUES
                ('9.9.99','Cuenta personalizada','Activo','Activo',NULL,3)""")
            db.execute("INSERT INTO libro_diario VALUES (1,'1.1.02',15000,0)")
            antes = db.execute("SELECT * FROM libro_diario").fetchall()
            instalar_plan_base(db)
            self.assertEqual(db.execute(
                "SELECT nombre FROM plan_cuentas WHERE codigo='1.1.02'"
            ).fetchone()[0], "Banco histórico de la empresa")
            self.assertEqual(db.execute(
                "SELECT nombre FROM plan_cuentas WHERE codigo='9.9.99'"
            ).fetchone()[0], "Cuenta personalizada")
            self.assertEqual(db.execute("SELECT * FROM libro_diario").fetchall(), antes)
            self.assertIsNotNone(db.execute(
                "SELECT 1 FROM plan_cuentas WHERE codigo='4.1.01'"
            ).fetchone())
            # Las cuentas exigidas por Nómina deben existir y conservar su jerarquía.
            for codigo in ("2.1.02.01", "2.1.02.02", "2.1.02.03",
                           "2.1.02.04", "2.1.02.05"):
                cuenta = db.execute(
                    "SELECT padre_codigo, categoria FROM plan_cuentas WHERE codigo=?",
                    (codigo,)
                ).fetchone()
                self.assertEqual(cuenta, ("2.1.02", "Pasivo"))
            # Una segunda instalación tampoco altera datos ni denominaciones.
            instalar_plan_base(db)
            self.assertEqual(db.execute("SELECT * FROM libro_diario").fetchall(), antes)



    def test_reorganizacion_no_renombra_cuentas_historicas(self):
        with sqlite3.connect(":memory:") as db:
            db.execute("""CREATE TABLE plan_cuentas (
                codigo TEXT PRIMARY KEY, nombre TEXT, categoria TEXT,
                tipo TEXT, padre_codigo TEXT, nivel INTEGER)""")
            db.execute("CREATE TABLE config_cuentas (rol TEXT, codigo TEXT)")
            db.execute("""INSERT INTO plan_cuentas VALUES
                ('5.2.03','Nombre definido por el contador','Nominal','Gastos','5.2',3)""")
            reorganizar_plan_2026_seguro(db)
            nombre = db.execute(
                "SELECT nombre FROM plan_cuentas WHERE codigo='5.2.03'"
            ).fetchone()[0]
            self.assertEqual(nombre, "Nombre definido por el contador")


if __name__ == "__main__":
    unittest.main()

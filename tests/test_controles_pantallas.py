"""Regresión de barreras de permisos en las pantallas de operaciones.

Esta comprobación estructural complementa las pruebas de permisos y no
sustituye las pruebas de integración de las funciones contables.
"""
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "modulos" / "interfaz.py"
TESORERIA = ROOT / "modulos" / "tesoreria.py"


class TestControlesPantallas(unittest.TestCase):
    def test_operaciones_criticas_tienen_barrera_inmediata(self):
        contenido = SOURCE.read_text(encoding="utf-8")
        casos = (
            ("CONTABILIZAR COMPRAS", "cxp", "contabilizar", "RCV Compras"),
            ("CONTABILIZAR VENTAS", "cxc", "contabilizar", "RCV Ventas"),
            ("Contabilizar asiento manual", "contabilidad", "contabilizar", "Asientos y Saldos"),
            ("Contabilizar pago a proveedor", "banco", "contabilizar", "Conciliación bancaria"),
            ("Contabilizar cobro de cliente", "banco", "contabilizar", "Conciliación bancaria"),
            ("Importar cartola", "banco", "importar", "Bancos y cartolas"),
            ("CERRAR PERÍODO", "administracion", "aprobar", "Cierre Mensual"),
            ("DESHACER LOTE", "administracion", "anular", "Lotes"),
        )
        for etiqueta, modulo, accion, submodulo in casos:
            with self.subTest(etiqueta=etiqueta):
                patron = (re.escape(etiqueta) + r'(?s:.{0,350}?)'
                          + re.escape(f"sgci_exigir_permiso(conn, '{modulo}', '{accion}', '{submodulo}')"))
                self.assertRegex(contenido, patron)

    def test_tesoreria_contabilizacion_requiere_permiso_especifico(self):
        contenido = TESORERIA.read_text(encoding="utf-8")
        self.assertIn(
            "sgci_autorizar_operacion(conn, 'tesoreria', 'contabilizar', 'Confirmación de pagos')",
            contenido,
        )


if __name__ == "__main__":
    unittest.main()

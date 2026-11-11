"""Invariantes de aislamiento de empleados durante la habilitación gradual.

Estas pruebas NO certifican el acceso multiusuario general: evitan que se
retire accidentalmente la barrera antes de auditar todos los módulos.
"""
import ast
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
INTERFAZ = ROOT / "modulos" / "interfaz.py"


class TestBarreraMultiusuario(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = INTERFAZ.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)

    def test_empleado_bloqueado_antes_de_navegacion_general(self):
        source = self.source
        start = source.index("if not sgci_es_propietario():")
        navigation = source.index("sgci_nav_modulos = [", start)
        barrier = source[start:navigation]
        self.assertIn("sgci_sesion_valida()", barrier)
        self.assertIn("mostrar_portal_con_sesion(", barrier)
        self.assertIn("st.stop()", barrier)
        self.assertLess(start, navigation)

    def test_menu_general_verifica_permiso_servidor(self):
        source = self.source
        navigation = source.index("sgci_nav_modulos = [")
        authorization = source.index(
            "sgci_exigir_permiso(conn, sgci_modulo_elegido, 'ver')", navigation)
        first_module = source.index('if menu == "🏠 Inicio"', navigation) if 'if menu == "🏠 Inicio"' in source else -1
        self.assertGreater(authorization, navigation)
        if first_module >= 0:
            self.assertLess(authorization, first_module)

    def test_respaldo_base_datos_restringido_a_propietario(self):
        self.assertIn("if sgci_es_propietario() and os.path.exists(DB_FILE):", self.source)
        self.assertIn("st.sidebar.download_button(", self.source)


if __name__ == "__main__":
    unittest.main()

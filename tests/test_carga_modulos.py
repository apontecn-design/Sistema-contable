"""Prueba de integración sin servidor web: carga los 22 componentes y crea esquemas en una copia."""
import os
import sqlite3
import sys
import tempfile
import types
import pandas  # precargar NumPy fuera del parche temporal de sys.modules
import unittest
from pathlib import Path
from unittest.mock import patch

class DetenerEnMenu(Exception): pass

class TestCargaModular(unittest.TestCase):
    def test_migraciones_y_navegacion_inicial(self):
        origen = os.getenv('CONTEM_TEST_DB')
        if not origen or not Path(origen).is_file():
            self.skipTest('Requiere CONTEM_TEST_DB con una copia no productiva')
        with tempfile.TemporaryDirectory() as carpeta:
            db = Path(carpeta)/'sgci.db'
            with sqlite3.connect(origen) as a, sqlite3.connect(str(db)) as b:
                a.backup(b)
            st = types.ModuleType('streamlit')
            st.session_state={'authenticated':True,'sgci_auth_tipo':'argon2'}
            st.set_page_config=lambda **k:None
            st.markdown=lambda *a,**k:None
            activado=[]
            def detener_menu(*a,**k):
                activado.append('navegacion')
                raise DetenerEnMenu()
            st.sidebar=types.SimpleNamespace(
                markdown=lambda *a,**k:None,
                caption=lambda *a,**k:None,
                radio=detener_menu
            )
            # Las importaciones inyectadas requieren módulos siempre frescos entre pruebas.
            for key in list(sys.modules):
                if key.startswith('modulos.'):
                    del sys.modules[key]
            raiz=str(Path(__file__).resolve().parents[1])
            if raiz not in sys.path:sys.path.insert(0,raiz)
            with patch.dict(sys.modules,{'streamlit':st}),patch.dict(os.environ,{'SGCI_DATA_DIR':carpeta,'SGCI_LAB_MODE':'0'}):
                import app
                with self.assertRaises(DetenerEnMenu):
                    app.iniciar()
                self.assertEqual(activado,['navegacion'])
            with sqlite3.connect(str(db)) as con:
                self.assertEqual(con.execute('PRAGMA integrity_check').fetchone()[0],'ok')
                self.assertTrue(con.execute("SELECT name FROM sqlite_master WHERE name='sgci_perfiles'").fetchone())

if __name__=='__main__':unittest.main()

"""Abrir Cierre Mensual debe consultar datos sin crear períodos."""
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
from scripts.comparar_historicos import comparar

try:
    from streamlit.testing.v1 import AppTest
except ImportError:
    AppTest = None


@unittest.skipIf(AppTest is None, 'Requiere Streamlit para comprobar la pantalla real')
class TestNavegacionSinEscrituras(unittest.TestCase):
    def test_abrir_cierre_no_crea_periodo(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / 'prueba.db'
            referencia = Path(carpeta) / 'referencia.db'
            conexiones = []
            conectar = sqlite3.connect
            def registrar(*args, **kwargs):
                db = conectar(*args, **kwargs)
                conexiones.append(db)
                return db
            env = {'CONTEM_ENTORNO':'test', 'SGCI_DATA_DIR':carpeta,
                   'CONTEM_STAGING_DB':str(ruta), 'CONTEM_STAGING_AUTORIZADO':'SI',
                   'SGCI_ADMIN_EMAIL':'test@example.com', 'SGCI_LAB_MODE':'0',
                   'SUPABASE_URL':'', 'SGCI_PASSWORD_HASH':''}
            with patch.dict(os.environ, env), patch.object(sqlite3, 'connect', registrar):
                try:
                    app = str(Path(__file__).resolve().parents[1] / 'app.py')
                    at = AppTest.from_file(app, default_timeout=30)
                    at.session_state['authenticated'] = True
                    at.session_state['sgci_auth_tipo'] = 'argon2'
                    at.run()
                    self.assertFalse(list(at.exception))
                    with closing(conectar(ruta)) as entrada, closing(conectar(referencia)) as salida:
                        entrada.backup(salida)
                    at.sidebar.radio[0].set_value('⚙️ Administración').run()
                    self.assertFalse(list(at.exception))
                    at.selectbox(key='nav_admin').set_value('Cierre Mensual').run()
                    self.assertFalse(list(at.exception))
                    self.assertTrue(comparar(referencia, ruta)['aprobado'])
                finally:
                    for db in conexiones:
                        db.close()

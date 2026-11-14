"""La aplicación usa la base aislada declarada y falla antes de abrir producción."""
import importlib.util
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

class ConfiguracionLeida(Exception):
    pass

class TestRutaSQLite(unittest.TestCase):
    def cargar(self, env, error=ConfiguracionLeida):
        ruta = Path(__file__).resolve().parents[1] / 'modulos/configuracion.py'
        spec = importlib.util.spec_from_file_location('contem_config_prueba', ruta)
        modulo = importlib.util.module_from_spec(spec)
        def detener(**kwargs):
            raise ConfiguracionLeida()
        with patch.dict(os.environ, env), patch.dict('sys.modules', {'streamlit': SimpleNamespace(set_page_config=detener)}), patch.object(sqlite3, 'connect') as conectar:
            with self.assertRaises(error):
                spec.loader.exec_module(modulo)
            conectar.assert_not_called()
        return modulo

    def test_base_de_prueba_es_la_declarada(self):
        with tempfile.TemporaryDirectory() as carpeta:
            destino = str(Path(carpeta) / 'copia_autorizada.db')
            m = self.cargar({'CONTEM_ENTORNO':'test', 'SGCI_DATA_DIR':carpeta,
                'CONTEM_STAGING_DB':destino, 'SGCI_ADMIN_EMAIL':'test@example.com',
                'CONTEM_STAGING_AUTORIZADO':'SI'})
            self.assertEqual(m.DB_FILE, destino)
            self.assertFalse(Path(destino).exists())

    def test_produccion_no_cambia_ruta_historica(self):
        with tempfile.TemporaryDirectory() as carpeta:
            m = self.cargar({'CONTEM_ENTORNO':'production', 'SGCI_DATA_DIR':carpeta})
            self.assertEqual(m.DB_FILE, os.path.join(carpeta, 'sgci.db'))

    def test_staging_inseguro_se_rechaza_antes_de_abrir_sqlite(self):
        self.cargar({'CONTEM_ENTORNO':'staging', 'SGCI_DATA_DIR':'/var/data',
            'CONTEM_STAGING_DB':'/var/data/sgci.db', 'SGCI_ADMIN_EMAIL':'test@example.com',
            'CONTEM_STAGING_AUTORIZADO':'SI'}, RuntimeError)

    def test_staging_sin_confirmacion_se_rechaza(self):
        with tempfile.TemporaryDirectory() as carpeta:
            self.cargar({'CONTEM_ENTORNO':'staging', 'SGCI_DATA_DIR':carpeta,
                'CONTEM_STAGING_DB':str(Path(carpeta)/'prueba.db'),
                'SGCI_ADMIN_EMAIL':'test@example.com', 'CONTEM_STAGING_AUTORIZADO':'NO'}, RuntimeError)

"""Pruebas de bloqueo de configuración insegura en CONTEM staging."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

SCRIPT=Path(__file__).resolve().parents[1]/'scripts'/'validar_entorno_aislado.py'
SPEC=importlib.util.spec_from_file_location('contem_staging_preflight',SCRIPT)
MOD=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class TestEntornoAislado(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.base={
            'CONTEM_ENTORNO':'staging',
            'CONTEM_STAGING_DB':str(Path(self.temp.name)/'staging.db'),
            'SGCI_DATA_DIR':self.temp.name,
            'SGCI_ADMIN_EMAIL':'admin@example.com',
            'CONTEM_STAGING_AUTORIZADO':'SI',
        }

    def tearDown(self):
        self.temp.cleanup()

    def test_configuracion_aislada_permitida(self):
        self.assertTrue(MOD.validar(self.base)['aprobado'])

    def test_produccion_bloqueada(self):
        env={**self.base,'CONTEM_STAGING_DB':'/var/data/sgci.db',
             'SGCI_DATA_DIR':'/var/data'}
        self.assertFalse(MOD.validar(env)['aprobado'])

    def test_sin_autorizacion_bloqueada(self):
        env={**self.base,'CONTEM_STAGING_AUTORIZADO':'NO'}
        self.assertFalse(MOD.validar(env)['aprobado'])

    def test_sin_administrador_bloqueado(self):
        env={**self.base,'SGCI_ADMIN_EMAIL':''}
        self.assertFalse(MOD.validar(env)['aprobado'])

    def test_base_fuera_del_directorio_bloqueada(self):
        env={**self.base,'CONTEM_STAGING_DB':'/tmp/otra/staging.db'}
        self.assertFalse(MOD.validar(env)['aprobado'])

    def test_entorno_productivo_bloqueado(self):
        env={**self.base,'CONTEM_ENTORNO':'production'}
        self.assertFalse(MOD.validar(env)['aprobado'])


if __name__=='__main__':
    unittest.main()

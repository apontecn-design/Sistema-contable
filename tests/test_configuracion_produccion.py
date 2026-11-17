import unittest
from scripts.verificar_configuracion_produccion import verificar


class TestConfiguracionProduccion(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.carpeta=tempfile.TemporaryDirectory()
        self.addCleanup(self.carpeta.cleanup)
        self.env={'SGCI_DATA_DIR':self.carpeta.name,'SGCI_ADMIN_EMAIL':'admin@example.com',
                  'SUPABASE_URL':'https://ejemplo.supabase.co','SUPABASE_ANON_KEY':'clave_publica_sintetica'}

    def test_configuracion_coherente(self):
        self.assertTrue(verificar(self.env,verificar_montaje=False)['aprobado'])

    def test_rechaza_laboratorio(self):
        self.assertFalse(verificar({**self.env,'SGCI_LAB_MODE':'1'},False)['aprobado'])

    def test_rechaza_auth_incompleta(self):
        self.assertFalse(verificar({**self.env,'SUPABASE_ANON_KEY':''},False)['aprobado'])

    def test_rechaza_base_staging(self):
        self.assertFalse(verificar({**self.env,'CONTEM_STAGING_DB':'copia.db'},False)['aprobado'])

    def test_no_imprime_claves(self):
        self.assertNotIn(self.env['SUPABASE_ANON_KEY'],str(verificar(self.env,False)))

    def test_no_certifica_carpeta_temporal_como_disco(self):
        self.assertFalse(verificar(self.env)['aprobado'])

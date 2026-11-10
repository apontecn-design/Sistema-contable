"""Smoke test: sin credenciales ni sesión válida, no se carga la navegación."""
import os
import sys
import types
import unittest
from unittest.mock import patch
from pathlib import Path

class InterrupcionStreamlit(Exception): pass

class Contexto:
    def __enter__(self):return self
    def __exit__(self,*a):return False

class TestInicioSinSesion(unittest.TestCase):
    def test_sin_sesion_deniega_acceso(self):
        fake=types.ModuleType('streamlit')
        fake.session_state={}
        fake.set_page_config=lambda *a,**k:None
        fake.markdown=lambda *a,**k:None
        fake.columns=lambda *a,**k:[Contexto(),Contexto(),Contexto()]
        fake.title=lambda *a,**k:None
        fake.radio=lambda _label,opts,**k:opts[0]
        fake.form=lambda *a,**k:Contexto()
        fake.text_input=lambda *a,**k:''
        fake.form_submit_button=lambda *a,**k:False
        fake.error=lambda *a,**k:None
        fake.info=lambda *a,**k:None
        fake.stop=lambda: (_ for _ in ()).throw(InterrupcionStreamlit())
        folder=Path(__file__).resolve().parents[1]
        with patch.dict(sys.modules, {'streamlit':fake}),patch.dict(os.environ, {'SGCI_DATA_DIR':str(folder/'tests'/'sandbox_data'),'SUPABASE_URL':'','SGCI_PASSWORD_HASH':''}):
            if str(folder) not in sys.path:sys.path.insert(0,str(folder))
            import app
            with self.assertRaises(InterrupcionStreamlit): app.iniciar()
            self.assertFalse(fake.session_state['authenticated'])
            self.assertNotIn('modulos.interfaz', sys.modules)

if __name__=='__main__': unittest.main()

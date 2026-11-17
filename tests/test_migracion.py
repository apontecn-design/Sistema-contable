"""Comprueba migración aditiva de permisos sin tocar la base original."""
import os
from contextlib import closing
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path
from modulos.usuarios import sgci_crear_seguridad


class TestMigracion(unittest.TestCase):
    def test_seguridad_en_copia_sqlite(self):
        ruta = os.getenv('CONTEM_TEST_DB')
        if not ruta or not Path(ruta).is_file():
            self.skipTest('Se requiere CONTEM_TEST_DB con una copia NO productiva de SQLite')
        with tempfile.TemporaryDirectory() as temporal:
            copia = Path(temporal) / 'copia.db'
            # API de backup de SQLite, no copia de bytes de una BD con actividad.
            with closing(sqlite3.connect(ruta)) as origen, closing(sqlite3.connect(str(copia))) as destino, destino:
                origen.backup(destino)
            with closing(sqlite3.connect(str(copia))) as conexion, conexion:
                conexion.row_factory = sqlite3.Row
                conexion.execute('PRAGMA foreign_keys=ON')
                tablas_antes = {r['name'] for r in conexion.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                saldos_antes = {
                    t: conexion.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
                    for t in tablas_antes if not t.startswith('sgci_') and not t.startswith('sqlite_')
                }
                sgci_crear_seguridad(conexion)
                sgci_crear_seguridad(conexion)  # debe ser idempotente
                self.assertEqual(conexion.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
                self.assertFalse(conexion.execute('PRAGMA foreign_key_check').fetchall())
                saldos_despues = {t:conexion.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in saldos_antes}
                self.assertEqual(saldos_antes,saldos_despues)
                self.assertTrue(tablas_antes.issubset({r['name'] for r in conexion.execute("SELECT name FROM sqlite_master WHERE type='table'")}))
                self.assertTrue({'nombre_completo','cargo','debe_cambiar_clave'}.issubset({r['name'] for r in conexion.execute('PRAGMA table_info(sgci_usuarios)')}))

if __name__ == '__main__': unittest.main()

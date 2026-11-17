from contextlib import closing
"""Ensayo aislado de respaldo y restauración SQLite. No toca Render.

Uso: python scripts/ensayar_recuperacion.py /ruta/copia.db
Crea ficheros temporales; nunca escribe sobre la base de origen.
"""
import json
import sqlite3
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.comparar_historicos import comparar


def ensayar(origen):
    origen=Path(origen).resolve()
    if not origen.is_file():
        raise FileNotFoundError(origen)
    with tempfile.TemporaryDirectory(prefix='contem_recovery_') as temp:
        respaldo=Path(temp)/'respaldo.db'
        restaurada=Path(temp)/'restaurada.db'
        with closing(sqlite3.connect(origen.as_uri()+'?mode=ro',uri=True)) as db_origen, db_origen:
            with closing(sqlite3.connect(respaldo)) as db_respaldo, db_respaldo:
                db_origen.backup(db_respaldo)
        with closing(sqlite3.connect(respaldo.as_uri()+'?mode=ro',uri=True)) as db_respaldo, db_respaldo:
            with closing(sqlite3.connect(restaurada)) as db_restaurada, db_restaurada:
                db_respaldo.backup(db_restaurada)
        with closing(sqlite3.connect(origen.as_uri()+'?mode=ro',uri=True)) as db_origen, db_origen:
            esquema_origen=db_origen.execute(
                "SELECT type,name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"
            ).fetchall()
        with closing(sqlite3.connect(restaurada.as_uri()+'?mode=ro',uri=True)) as db_restaurada, db_restaurada:
            integridad=db_restaurada.execute('PRAGMA integrity_check').fetchone()[0]
            fk=db_restaurada.execute('PRAGMA foreign_key_check').fetchall()
            esquema_restaurado=db_restaurada.execute(
                "SELECT type,name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"
            ).fetchall()
        historicos = comparar(origen, restaurada)
        return {'integridad_restaurada':integridad,
                'claves_foraneas_invalidas':len(fk),
                'esquema_identico':esquema_origen==esquema_restaurado,
                'contenido_preservado':historicos['aprobado'],
                'aprobado':integridad=='ok' and not fk and esquema_origen==esquema_restaurado and historicos['aprobado'],
                'nota':'Ensayo local de backup/restore; no prueba despliegue Render ni migración.'}


if __name__=='__main__':
    if len(sys.argv)!=2:
        raise SystemExit('Uso: python scripts/ensayar_recuperacion.py /ruta/copia.db')
    print(json.dumps(ensayar(sys.argv[1]),ensure_ascii=False,indent=2))

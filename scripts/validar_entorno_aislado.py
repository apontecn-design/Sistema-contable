"""Verificación preventiva para CONTEM staging. No despliega ni modifica bases.

Uso: python scripts/validar_entorno_aislado.py
Requiere CONTEM_ENTORNO=staging, CONTEM_STAGING_DB=/ruta/aislada.db,
SGCI_DATA_DIR distinto de /var/data y configuración de autenticación.
"""
import json
import os
import sys
from pathlib import Path
from posixpath import normpath


def es_ruta_productiva(valor):
    # Reconocer también rutas declaradas para Linux al validar desde Windows.
    declarada = normpath(str(valor).replace('\\', '/'))
    resuelta = Path(valor).expanduser().resolve().as_posix()
    return any(p == '/var/data' or p.startswith('/var/data/')
               for p in (declarada, resuelta))


def validar(config=None):
    env=dict(os.environ if config is None else config)
    errores=[]
    if env.get('CONTEM_ENTORNO','').strip().lower() not in ('staging','test'):
        errores.append('CONTEM_ENTORNO debe ser staging o test')
    db=env.get('CONTEM_STAGING_DB','').strip()
    data_dir=env.get('SGCI_DATA_DIR','').strip()
    if not db:
        errores.append('CONTEM_STAGING_DB es obligatorio')
    if not data_dir:
        errores.append('SGCI_DATA_DIR aislado es obligatorio')
    if db:
        ruta=Path(db).expanduser().resolve()
        if es_ruta_productiva(db):
            errores.append('Prohibido usar base de producción en /var/data')
        if ruta.suffix.lower()!='.db':
            errores.append('CONTEM_STAGING_DB debe apuntar a SQLite .db')
    if data_dir:
        carpeta=Path(data_dir).expanduser().resolve()
        if es_ruta_productiva(data_dir):
            errores.append('SGCI_DATA_DIR no puede apuntar a producción')
        if db and (ruta.parent!=carpeta):
            errores.append('La base staging debe estar dentro de SGCI_DATA_DIR')
    if not env.get('SGCI_ADMIN_EMAIL','').strip():
        errores.append('SGCI_ADMIN_EMAIL debe estar configurado')
    if env.get('CONTEM_STAGING_AUTORIZADO','')!='SI':
        errores.append('Falta confirmación explícita CONTEM_STAGING_AUTORIZADO=SI')
    return {'aprobado':not errores,'errores':errores,
            'nota':'Preflight de configuración; no prueba login real ni despliegue Render.'}


if __name__=='__main__':
    resultado=validar()
    print(json.dumps(resultado,ensure_ascii=False,indent=2))
    if not resultado['aprobado']:
        raise SystemExit(1)

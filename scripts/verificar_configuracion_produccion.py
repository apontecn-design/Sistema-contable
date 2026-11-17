"""Comprobación de configuración de producción, sin modificar servicios ni mostrar secretos."""
import json
import os
from pathlib import Path


def verificar(config=None, verificar_montaje=True):
    env = dict(os.environ if config is None else config)
    errores = []
    if env.get('SGCI_LAB_MODE','0') != '0':
        errores.append('SGCI_LAB_MODE debe estar desactivado.')
    if env.get('CONTEM_ENTORNO','production').strip().lower() not in ('production','produccion'):
        errores.append('El entorno no está identificado como producción.')
    carpeta = env.get('SGCI_DATA_DIR','').strip()
    if not carpeta or not Path(carpeta).is_absolute():
        errores.append('SGCI_DATA_DIR debe ser una carpeta persistente absoluta.')
    elif verificar_montaje and not os.path.ismount(carpeta):
        errores.append('SGCI_DATA_DIR no es un punto de montaje persistente verificado.')
    if not env.get('SGCI_ADMIN_EMAIL','').strip() or '@' not in env.get('SGCI_ADMIN_EMAIL',''):
        errores.append('Configura la identidad del administrador principal.')
    url = env.get('SUPABASE_URL','').strip()
    publica = (env.get('SUPABASE_ANON_KEY','') or env.get('SUPABASE_PUBLISHABLE_KEY','')).strip()
    if bool(url) != bool(publica) or (url and not url.startswith('https://')):
        errores.append('La configuración de autenticación Supabase está incompleta o no usa HTTPS.')
    if not (url and publica) and not env.get('SGCI_PASSWORD_HASH','').startswith('$argon2'):
        errores.append('No hay un método de acceso configurado y verificable.')
    if env.get('CONTEM_STAGING_DB','').strip():
        errores.append('Retira CONTEM_STAGING_DB de la configuración de producción.')
    return {'aprobado':not errores,'errores':errores,
            'nota':'Valida configuración y montaje; no prueba credenciales, respaldos ni seguridad funcional.'}


if __name__=='__main__':
    resultado=verificar()
    print(json.dumps(resultado,ensure_ascii=False,indent=2))
    raise SystemExit(0 if resultado['aprobado'] else 1)

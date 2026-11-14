"""Política de autorización de lectura por perfil y alcance de RR. HH.

No autentica sesiones ni incorpora interfaces de simulación.
La autenticación se verifica separadamente antes de consultar datos.
"""
SUBMODULOS = {'Trabajadores': 'Trabajadores', 'Liquidaciones': 'Liquidación mensual'}


def permiso_efectivo(conn, email, submodulo, accion='ver'):
    if submodulo not in SUBMODULOS or accion not in ('ver','exportar'):
        return False
    usuario = conn.execute('SELECT rol,activo FROM sgci_usuarios WHERE email=?',(email,)).fetchone()
    if not usuario or not usuario['activo']:
        return False
    override = conn.execute('''SELECT permitido FROM sgci_usuario_permisos_detalle
        WHERE email=? AND modulo='nomina' AND submodulo=? AND accion=?''',
        (email,SUBMODULOS[submodulo],accion)).fetchone()
    if override is not None:
        return bool(override['permitido'])
    base = conn.execute('''SELECT permitido FROM sgci_perfil_permisos
        WHERE perfil=? AND modulo='nomina' AND submodulo=? AND accion=?''',
        (usuario['rol'],SUBMODULOS[submodulo],accion)).fetchone()
    return bool(base and base['permitido'])


def ids_permitidos(conn,email):
    usuario=conn.execute('SELECT activo FROM sgci_usuarios WHERE email=?',(email,)).fetchone()
    if not usuario or not usuario['activo']:
        return set()
    row=conn.execute('SELECT alcance FROM sgci_alcance_rrhh WHERE email=?',(email,)).fetchone()
    alcance=row['alcance'] if row else 'propios'
    if alcance=='todos':
        return None
    propio=conn.execute('SELECT trabajador_id FROM sgci_usuario_trabajador WHERE email=?',(email,)).fetchone()
    ids={int(propio['trabajador_id'])} if propio else set()
    if alcance=='autorizados':
        ids.update(int(r['trabajador_id']) for r in conn.execute('SELECT trabajador_id FROM sgci_rrhh_autorizados WHERE email=?',(email,)))
    return ids



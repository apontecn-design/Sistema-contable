"""SGCI 6.8B: puerta de sesión y usuario para portal RRHH.
No habilita módulos empresariales ni sustituye controles de cada operación.
"""

def exigir_portal_autenticado(conn, sesion, identidad):
    """Rechaza sesiones no Supabase, identidad divergente y cuentas inactivas."""
    from sgci_rrhh_seguridad import AccesoDenegado
    email = str(identidad or '').strip().lower()
    correo_sesion = str(sesion.get('sgci_sb_email') or '').strip().lower()
    if (not sesion.get('authenticated') or
        sesion.get('sgci_auth_tipo') != 'supabase' or
        not sesion.get('sgci_sb_access') or
        not email or email != correo_sesion):
        raise AccesoDenegado('Sesión de empleado no autorizada')
    cuenta = conn.execute('SELECT activo, debe_cambiar_clave FROM sgci_usuarios WHERE email=?',
                          (email,)).fetchone()
    if not cuenta or not cuenta['activo'] or cuenta['debe_cambiar_clave']:
        raise AccesoDenegado('Cuenta de empleado no habilitada')
    return email


def mostrar_portal_con_sesion(st, conn, sesion, identidad, generador_pdf):
    from sgci_rrhh_seguridad import AccesoDenegado
    try:
        email = exigir_portal_autenticado(conn, sesion, identidad)
    except AccesoDenegado:
        st.error('Acceso al portal no autorizado.')
        st.stop()
    from sgci_rrhh_portal_aislado import mostrar_portal_rrhh
    return mostrar_portal_rrhh(st, conn, email, generador_pdf)

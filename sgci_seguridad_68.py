"""Etapa 6.8 - guardias reutilizables; NO habilita navegación de empleados."""
import sqlite3

class SGCIAccesoDenegado(PermissionError):
    pass

def identidad_verificada(session, validar_sesion):
    """Obtiene correo exclusivamente de sesión Supabase verificada."""
    if session.get('sgci_auth_tipo') != 'supabase' or not validar_sesion():
        raise SGCIAccesoDenegado('Sesión Supabase inválida')
    email = str(session.get('sgci_sb_email') or '').strip().lower()
    if not email or '@' not in email:
        raise SGCIAccesoDenegado('Identidad ausente')
    return email

def exigir_modulo(conn, email, modulo, accion='ver'):
    """Política restrictiva: solo permisos explícitos, nunca permisos implícitos de perfil."""
    if modulo not in ('inicio','banco','tesoreria','cxc','cxp','dte','nomina','contabilidad','administracion'):
        raise SGCIAccesoDenegado('Módulo inválido')
    if accion not in ('ver','ingresar','editar','eliminar','exportar','aprobar','contabilizar'):
        raise SGCIAccesoDenegado('Acción inválida')
    u = conn.execute('SELECT activo FROM sgci_usuarios WHERE lower(email)=?', (email.lower(),)).fetchone()
    if not u or not u[0]:
        raise SGCIAccesoDenegado('Cuenta inactiva')
    p = conn.execute('SELECT permitido FROM sgci_permisos WHERE lower(email)=? AND modulo=? AND accion=?', (email.lower(),modulo,accion)).fetchone()
    if not p or not p[0]:
        raise SGCIAccesoDenegado('Permiso explícito requerido')
    return True

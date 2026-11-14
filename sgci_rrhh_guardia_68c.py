"""6.8C: defensa adicional para PDF individual del portal RRHH (laboratorio)."""
from sgci_rrhh_guardia_68b import exigir_portal_autenticado
from sgci_rrhh_seguridad import AccesoDenegado, obtener_liquidacion
from sgci_rrhh_pdf_controlado import pdf_liquidacion_autorizado

def validar_descarga_sesion(conn, sesion, identidad, liquidacion_id):
    email = exigir_portal_autenticado(conn, sesion, identidad)
    autorizado = obtener_liquidacion(conn, email, liquidacion_id, accion='exportar')
    if autorizado is None:
        raise AccesoDenegado('Documento no autorizado')
    return autorizado

def preparar_pdf_sesion(conn, sesion, identidad, liquidacion_id, generador):
    autorizado = validar_descarga_sesion(conn, sesion, identidad, liquidacion_id)
    pdf = pdf_liquidacion_autorizado(conn, identidad, autorizado['id'], generador)
    if not isinstance(pdf, (bytes, bytearray)) or not bytes(pdf).startswith(b'%PDF-'):
        raise ValueError('Documento PDF inválido')
    return bytes(pdf)

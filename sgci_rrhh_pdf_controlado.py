"""Etapa 6.3: comprobación ADMINISTRATIVA de PDF con autorización por registro.
No habilita acceso real de empleados ni altera pantallas operativas.
"""
from sgci_rrhh_seguridad import AccesoDenegado, obtener_liquidacion, listar_liquidaciones

def pdf_liquidacion_autorizado(conn, email, liquidacion_id, generador):
    # Autorizar exportación ANTES de leer datos sensibles o generar el PDF.
    autorizado = obtener_liquidacion(conn, email, liquidacion_id, accion='exportar')
    if autorizado is None:
        raise AccesoDenegado('Liquidación inexistente o no disponible')
    registro = conn.execute(
        """SELECT l.*,t.rut,t.nombre,t.cargo FROM nomina_liquidaciones l
           JOIN nomina_trabajadores t ON t.id=l.trabajador_id WHERE l.id=?""",
        (int(autorizado['id']),)
    ).fetchone()
    if registro is None:
        raise AccesoDenegado('Liquidación no disponible')
    # Compatible con rrhh_pdf_liquidacion, que usa atributos en el registro.
    from types import SimpleNamespace
    return generador(conn, SimpleNamespace(**dict(registro)))

def interfaz_pdf_controlado(st, conn, generador):
    st.divider()
    st.subheader('🔒 Etapa 6.3 · Exportación PDF protegida (solo administrador)')
    st.caption('Comprueba permisos de exportación y alcance por trabajador. No inicia sesión como empleado.')
    usuarios = conn.execute(
        'SELECT email,nombre_completo FROM sgci_usuarios WHERE activo=1 ORDER BY email'
    ).fetchall()
    if not usuarios:
        st.info('No hay usuarios activos para comprobar.')
        return
    etiquetas = {u['email']: (u['nombre_completo'] or 'Sin nombre')+' · '+u['email'] for u in usuarios}
    email = st.selectbox('Cuenta para comprobar exportación', list(etiquetas),
                         format_func=lambda e:etiquetas[e], key='sgci_e63_email')
    try:
        opciones = listar_liquidaciones(conn, email)
    except (AccesoDenegado, ValueError) as exc:
        st.info('No se permite listar liquidaciones: '+str(exc))
        return
    if not opciones:
        st.info('Sin liquidaciones autorizadas.')
        return
    nombres = {int(r['id']): str(r['periodo'])+' · '+str(r['nombre'])+' · #'+str(r['id']) for r in opciones}
    elegido = st.selectbox('Liquidación', list(nombres),
                           format_func=lambda k:nombres[k], key='sgci_e63_liquidacion')
    if st.button('Comprobar permiso de exportación', key='sgci_e63_verificar'):
        try:
            # No se almacena el PDF en session_state: se verifica de nuevo por cada ejecución.
            pdf = pdf_liquidacion_autorizado(conn, email, elegido, generador)
            st.success('Exportación autorizada. PDF generado para comprobación administrativa.')
            st.download_button('Descargar PDF de comprobación', data=pdf,
                file_name=f'liquidacion_comprobacion_{elegido}.pdf',
                mime='application/pdf', key='sgci_e63_pdf')
        except (AccesoDenegado, ValueError) as exc:
            st.error('Exportación denegada: '+str(exc))
        except Exception as exc:
            st.error('No se pudo generar el PDF: '+type(exc).__name__+': '+str(exc))
    st.warning('Esta prueba NO protege todavía todos los botones PDF operativos ni habilita acceso de empleados.')

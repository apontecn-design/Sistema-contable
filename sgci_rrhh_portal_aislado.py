"""Portal de consulta individual, solo para sesiones autenticadas no administrativas.
El bloqueo general SGCI_LAB_MODE sigue impidiendo acceso operativo en laboratorio.
No sustituye una auditoría de todas las rutas ni protege módulos ajenos a RRHH.
"""
from sgci_rrhh_seguridad import AccesoDenegado, listar_liquidaciones, obtener_liquidacion
from sgci_rrhh_pdf_controlado import pdf_liquidacion_autorizado


def mostrar_portal_rrhh(st, conn, email_autenticado, generador_pdf):
    # El llamador DEBE suministrar identidad derivada de la sesión autenticada.
    email = str(email_autenticado or '').strip().lower()
    if not email or email == 'administrador_respaldo':
        st.error('Sesión de empleado no válida.')
        st.stop()
    cuenta = conn.execute('SELECT activo FROM sgci_usuarios WHERE email=?', (email,)).fetchone()
    if cuenta is None or not cuenta['activo']:
        st.error('Cuenta no autorizada.')
        st.stop()
    st.subheader('Mi ficha laboral')
    vinculo = conn.execute('SELECT trabajador_id FROM sgci_usuario_trabajador WHERE email=?', (email,)).fetchone()
    if vinculo is None:
        st.info('No hay ficha laboral vinculada a esta cuenta.')
    else:
        from sgci_rrhh_seguridad import obtener_trabajador
        try:
            ficha = obtener_trabajador(conn, email, vinculo['trabajador_id'])
            if ficha is not None:
                st.write('Trabajador:', ficha['nombre'])
                st.caption('Ficha individual autorizada; no se muestran datos de terceros.')
            else:
                st.info('Ficha laboral no disponible.')
        except (AccesoDenegado, ValueError, TypeError):
            st.info('No tienes permiso para consultar tu ficha laboral.')
    st.divider()
    st.subheader('Mis liquidaciones')
    try:
        registros = listar_liquidaciones(conn, email)
    except (AccesoDenegado, ValueError):
        st.warning('No tienes permiso para consultar liquidaciones.')
        return
    if not registros:
        st.info('No hay liquidaciones autorizadas para tu cuenta.')
        return
    opciones = {int(r['id']): str(r['periodo']) + ' · ' + str(r['nombre']) for r in registros}
    elegido = st.selectbox('Período autorizado', list(opciones), format_func=lambda x: opciones[x], key='sgci_66_liq')
    # Revalidar antes de mostrar el registro, no confiar en el selectbox.
    try:
        registro = obtener_liquidacion(conn, email, elegido, accion='ver')
    except (AccesoDenegado, ValueError):
        st.error('Consulta no autorizada.')
        return
    if registro is None:
        st.error('Liquidación no disponible.')
        return
    st.write('Período:', registro['periodo'])
    st.write('Trabajador:', registro['nombre'])
    st.caption('La descarga requiere además autorización individual para Exportar.')
    if st.button('Preparar PDF autorizado', key='sgci_66_preparar_pdf'):
        try:
            from sgci_rrhh_guardia_68c import preparar_pdf_sesion, validar_descarga_sesion
            pdf = preparar_pdf_sesion(conn, st.session_state, email, elegido, generador_pdf)
            # Comprobar nuevamente al pulsar Descargar (además de la autorización al generar).
            # No guardar bytes ni permisos en session_state.
            st.download_button('Descargar liquidación', data=pdf,
                file_name=f'liquidacion_{elegido}.pdf', mime='application/pdf',
                key='sgci_66_descarga_pdf',
                on_click=validar_descarga_sesion,
                args=(conn, st.session_state, email, elegido))
        except (AccesoDenegado, ValueError):
            st.error('No tienes permiso para exportar esta liquidación.')
        except Exception as exc:
            st.error('No se pudo preparar el documento: ' + type(exc).__name__)

"""Vista administrativa de verificación. No suplanta sesiones ni abre navegación."""
from sgci_rrhh_seguridad import AccesoDenegado, obtener_trabajador
from sgci_rrhh_autorizacion import ids_permitidos

def interfaz_vista_empleado(st, conn):
    st.divider()
    st.subheader('🧪 Vista de empleado · comprobación administrativa')
    st.caption('Simulación de lectura limitada. No inicia sesión como empleado ni concede acceso real.')
    usuarios=conn.execute('SELECT email,nombre_completo FROM sgci_usuarios WHERE activo=1 ORDER BY email').fetchall()
    if not usuarios:
        st.info('No hay usuarios activos para probar.')
        return
    etiquetas={u['email']:(u['nombre_completo'] or 'Sin nombre')+' · '+u['email'] for u in usuarios}
    email=st.selectbox('Usuario de prueba (solo administración)',list(etiquetas),format_func=lambda e:etiquetas[e],key='sgci_vista_empleado_email')
    if st.button('Comprobar acceso a ficha propia',key='sgci_vista_empleado_comprobar'):
        fila=conn.execute('SELECT trabajador_id FROM sgci_usuario_trabajador WHERE email=?',(email,)).fetchone()
        if fila is None:
            st.warning('Usuario sin ficha vinculada. Acceso denegado.')
            return
        try:
            trabajador=obtener_trabajador(conn,email,fila['trabajador_id'])
            if trabajador is None:
                st.warning('Ficha no disponible.')
            else:
                st.success('Lectura autorizada de la ficha vinculada.')
                st.write({'ID':trabajador['id'],'Trabajador':trabajador['nombre']})
        except (AccesoDenegado,ValueError,TypeError):
            st.error('Acceso denegado: no se revela información de la ficha.')
    st.warning('Esta simulación no prueba sesiones Supabase ni protege otras pantallas del SGCI.')

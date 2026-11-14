"""Prueba administrativa de acceso a IDs concretos mediante política de RRHH."""
from sgci_rrhh_seguridad import AccesoDenegado, obtener_trabajador, obtener_liquidacion

def interfaz_lectura_controlada(st, conn):
    st.divider()
    st.subheader('🔒 Lectura controlada RRHH · prueba por registro')
    st.caption('Prueba administrativa de acceso permitido y denegado, sin suplantar sesión.')
    usuarios=conn.execute('SELECT email,nombre_completo FROM sgci_usuarios WHERE activo=1 ORDER BY email').fetchall()
    if not usuarios:
        st.info('Sin usuarios activos.')
        return
    etiquetas={r['email']:(r['nombre_completo'] or 'Sin nombre')+' · '+r['email'] for r in usuarios}
    email=st.selectbox('Cuenta de prueba',list(etiquetas),format_func=lambda e:etiquetas[e],key='sgci_lectura_email')
    tipo=st.selectbox('Registro que se intenta consultar',['Trabajadores','Liquidaciones'],key='sgci_lectura_tipo')
    tabla='nomina_trabajadores' if tipo=='Trabajadores' else 'nomina_liquidaciones'
    registros=conn.execute(f'SELECT id FROM {tabla} ORDER BY id').fetchall()
    if not registros:
        st.info('No hay registros de este tipo para probar.')
        return
    id_reg=st.selectbox('ID del registro (incluye IDs ajenos para comprobar denegación)',[int(r['id']) for r in registros],key='sgci_lectura_id')
    if st.button('Probar lectura autorizada',key='sgci_lectura_comprobar'):
        try:
            r=(obtener_trabajador(conn,email,id_reg) if tipo=='Trabajadores'
               else obtener_liquidacion(conn,email,id_reg))
            if r is None:
                st.info('Registro inexistente o no disponible.')
            else:
                st.success('Permitido por política de RRHH.')
                st.write({'ID':r['id'],'Trabajador':r['nombre']})
        except (AccesoDenegado,ValueError,TypeError):
            st.error('Denegado por política de RRHH. No se devuelve el registro.')
    st.warning('Prueba limitada a estas funciones; no acredita protección integral de rutas, reportes o PDF.')

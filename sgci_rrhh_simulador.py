"""SGCI: simulación administrativa, NO autenticación ni autorización operativa."""
import sqlite3
from sgci_rrhh_autorizacion import SUBMODULOS, permiso_efectivo, ids_permitidos

def consulta_simulada(conn,email,submodulo):
    """Devuelve SOLO identificadores y etiquetas; el filtrado ocurre en SQL."""
    if not permiso_efectivo(conn,email,submodulo):
        return []
    ids=ids_permitidos(conn,email)
    if ids is not None and not ids:
        return []
    if submodulo=='Trabajadores':
        sql='SELECT id,nombre FROM nomina_trabajadores'
    elif submodulo=='Liquidaciones':
        sql='SELECT l.id,l.periodo,l.trabajador_id,t.nombre FROM nomina_liquidaciones l JOIN nomina_trabajadores t ON t.id=l.trabajador_id'
    else:
        return []
    if ids is not None:
        column='id' if submodulo=='Trabajadores' else 'l.trabajador_id'
        sql+=' WHERE '+column+' IN ('+','.join('?' for _ in ids)+')'
        rows=conn.execute(sql,tuple(sorted(ids))).fetchall()
    else:
        rows=conn.execute(sql).fetchall()
    if submodulo=='Trabajadores':
        return [{'ID':r['id'],'Trabajador':r['nombre']} for r in rows]
    return [{'ID liquidación':r['id'],'Período':r['periodo'],'Trabajador':r['nombre']} for r in rows]


def interfaz_simulador(st,conn):
    st.divider()
    st.subheader('🔎 Simulador de acceso a Recursos Humanos (solo administrador)')
    st.caption('Consulta de solo lectura sobre una copia de datos. No inicia sesión como empleado ni habilita accesos operativos.')
    usuarios=conn.execute('SELECT email,nombre_completo,rol FROM sgci_usuarios ORDER BY email').fetchall()
    if not usuarios:
        st.info('Crea primero un usuario de prueba, asígnale perfil y vincúlalo con su ficha de Nómina.')
        return
    emails=[r['email'] for r in usuarios]
    labels={r['email']: (r['nombre_completo'] or 'Sin nombre')+' · '+r['email'] for r in usuarios}
    email=st.selectbox('Simular cuenta',emails,format_func=lambda e:labels[e],key='sgci_sim_email')
    sub=st.selectbox('Simular consulta',list(SUBMODULOS),key='sgci_sim_sub')
    autorizado=permiso_efectivo(conn,email,sub)
    ids=ids_permitidos(conn,email)
    alcance=conn.execute('SELECT alcance FROM sgci_alcance_rrhh WHERE email=?',(email,)).fetchone()
    st.write('Permiso Ver:', 'Permitido' if autorizado else 'Denegado')
    st.write('Alcance:', {'propios':'Solo mis datos','autorizados':'Registros autorizados','todos':'Todos los registros'}.get(alcance['alcance'] if alcance else 'propios','Solo mis datos'))
    st.write('Fichas accesibles:', 'Todas (según permiso)' if ids is None else len(ids))
    if st.button('Ejecutar consulta simulada',key='sgci_sim_ejecutar'):
        resultado=consulta_simulada(conn,email,sub)
        st.write('Registros devueltos:',len(resultado))
        if resultado:
            st.dataframe(resultado,hide_index=True,use_container_width=True)
        else:
            st.info('No se devuelven registros: permiso denegado o sin fichas autorizadas.')
    st.warning('No usar esta simulación como prueba de seguridad integral. Falta proteger cada operación real, los PDF y el acceso Supabase.')

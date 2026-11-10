# CONTEM: componente extraído del app.py original; ejecución secuencial compartida.
SGCI_MODULOS = {
    "inicio": "Inicio", "banco": "Banco", "tesoreria": "Tesorería",
    "cxc": "Ventas/clientes", "cxp": "Compras/proveedores",
    "dte": "Facturación y DTE", "nomina": "Recursos Humanos",
    "contabilidad": "Contabilidad", "administracion": "Administración",
}
SGCI_ACCIONES = ("ver", "crear", "editar", "aprobar", "contabilizar", "conciliar", "eliminar", "exportar")
SGCI_ROLES_BASE = ("Administración", "Ventas", "Operaciones", "Almacén", "Solicitante", "Contabilidad", "Finanzas", "Tesorería", "Auditoría", "Personalizado")
SGCI_SUBMODULOS = {
    'inicio': ['Panel principal'],
    'banco': ['Bancos y cartolas', 'Conciliación bancaria'],
    'tesoreria': ['Solicitudes de fondos', 'Confirmación de pagos', 'Historial'],
    'cxc': ['Clientes y estados de cuenta', 'Pagos de clientes', 'RCV Ventas', 'Antigüedad de saldos', 'Conciliación auxiliar'],
    'cxp': ['Proveedores y estados de cuenta', 'Pagos de proveedores', 'RCV Compras', 'Órdenes de compra', 'Antigüedad de saldos', 'Conciliación auxiliar'],
    'dte': ['Importar XML', 'Documentos y visor', 'Reportería'],
    'nomina': ['Trabajadores', 'Vacaciones', 'Anticipos y préstamos', 'Liquidación mensual', 'Resumen y reportes', 'Parámetros', 'Contabilización'],
    'contabilidad': ['Asientos y Saldos', 'Plan de Cuentas', 'Libro Diario', 'Libro Mayor', 'Balance de Comprobación', 'Estados Financieros'],
    'administracion': ['Datos de la empresa', 'Cierre Mensual', 'Reglas Contables', 'Lotes', 'Matriz Contable'],
}
SGCI_ACCIONES_SUB = SGCI_ACCIONES + ('importar', 'anular', 'confirmar')


def sgci_crear_seguridad(conn):
    # Migración aditiva: no se alteran ni eliminan permisos históricos.
    conn.execute("""CREATE TABLE IF NOT EXISTS sgci_usuarios (
        email TEXT PRIMARY KEY COLLATE NOCASE,
        rol TEXT NOT NULL DEFAULT 'Personalizado',
        activo INTEGER NOT NULL DEFAULT 1,
        creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS sgci_permisos (
        email TEXT NOT NULL COLLATE NOCASE,
        modulo TEXT NOT NULL,
        accion TEXT NOT NULL,
        permitido INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY(email,modulo,accion),
        FOREIGN KEY(email) REFERENCES sgci_usuarios(email)
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS sgci_auditoria_permisos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        actor TEXT NOT NULL, usuario TEXT NOT NULL,
        detalle TEXT NOT NULL
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS sgci_perfiles (
        nombre TEXT PRIMARY KEY, descripcion TEXT DEFAULT '',
        creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS sgci_perfil_permisos (
        perfil TEXT NOT NULL, modulo TEXT NOT NULL, submodulo TEXT NOT NULL,
        accion TEXT NOT NULL, permitido INTEGER NOT NULL DEFAULT 1,
        PRIMARY KEY(perfil,modulo,submodulo,accion),
        FOREIGN KEY(perfil) REFERENCES sgci_perfiles(nombre)
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS sgci_usuario_permisos_detalle (
        email TEXT NOT NULL COLLATE NOCASE, modulo TEXT NOT NULL,
        submodulo TEXT NOT NULL, accion TEXT NOT NULL,
        permitido INTEGER NOT NULL,
        PRIMARY KEY(email,modulo,submodulo,accion),
        FOREIGN KEY(email) REFERENCES sgci_usuarios(email)
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS sgci_usuario_trabajador (
        email TEXT PRIMARY KEY COLLATE NOCASE, trabajador_id INTEGER NOT NULL UNIQUE,
        FOREIGN KEY(email) REFERENCES sgci_usuarios(email),
        FOREIGN KEY(trabajador_id) REFERENCES nomina_trabajadores(id)
    )""")
    # Campos aditivos; nunca se alteran ni eliminan los datos existentes.
    cols={r[1] for r in conn.execute('PRAGMA table_info(sgci_usuarios)')}
    for col,tipo in [('nombre_completo','TEXT NOT NULL DEFAULT ""'),('cargo','TEXT NOT NULL DEFAULT ""'),('debe_cambiar_clave','INTEGER NOT NULL DEFAULT 0')]:
        if col not in cols:
            conn.execute(f'ALTER TABLE sgci_usuarios ADD COLUMN {col} {tipo}')
    conn.execute("""CREATE TABLE IF NOT EXISTS sgci_alcance_rrhh (
        email TEXT PRIMARY KEY COLLATE NOCASE,
        alcance TEXT NOT NULL DEFAULT 'propios'
            CHECK(alcance IN ('propios','autorizados','todos')),
        FOREIGN KEY(email) REFERENCES sgci_usuarios(email)
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS sgci_rrhh_autorizados (
        email TEXT NOT NULL COLLATE NOCASE,
        trabajador_id INTEGER NOT NULL,
        PRIMARY KEY(email, trabajador_id),
        FOREIGN KEY(email) REFERENCES sgci_usuarios(email),
        FOREIGN KEY(trabajador_id) REFERENCES nomina_trabajadores(id)
    )""")
    conn.execute("""INSERT OR IGNORE INTO sgci_alcance_rrhh(email,alcance)
                    SELECT email,'propios' FROM sgci_usuarios""")
    for nombre in SGCI_ROLES_BASE:
        conn.execute('INSERT OR IGNORE INTO sgci_perfiles(nombre) VALUES(?)',(nombre,))
    conn.commit()


def sgci_identidad_actual():
    if st.session_state.get('sgci_auth_tipo') == 'argon2':
        return 'ADMINISTRADOR_RESPALDO'
    return str(st.session_state.get('sgci_sb_email') or '').strip().lower()


def sgci_es_propietario():
    if st.session_state.get('sgci_auth_tipo') == 'argon2':
        return True  # Acceso de recuperación: custodiar la contraseña fuera de la app.
    propietario = os.getenv('SGCI_ADMIN_EMAIL', '').strip().lower()
    return bool(propietario and sgci_identidad_actual() == propietario)


def sgci_puede(conn, modulo, accion='ver'):
    if sgci_es_propietario():
        return True
    email = sgci_identidad_actual()
    if not email or modulo not in SGCI_MODULOS or accion not in SGCI_ACCIONES:
        return False
    fila = conn.execute('SELECT activo FROM sgci_usuarios WHERE email=?', (email,)).fetchone()
    if not fila or not fila['activo']:
        return False
    # La visibilidad del menú refleja los permisos efectivos de submódulos.
    # Esta comprobación NO concede permisos para modificar registros.
    if accion == 'ver' and modulo in SGCI_SUBMODULOS:
        submodulos = SGCI_SUBMODULOS[modulo]
        if any(sgci_puede_submodulo(conn, modulo, sub, 'ver') for sub in submodulos):
            return True
        # Si ya existe una matriz de permisos para este módulo, la ausencia
        # de autorizaciones efectivas debe denegar el acceso, incluso cuando
        # persista una concesión heredada en sgci_permisos.
        configurado = conn.execute(
            """SELECT 1 FROM sgci_perfil_permisos
               WHERE perfil=(SELECT rol FROM sgci_usuarios WHERE email=?)
                 AND modulo=? AND accion='ver'
               UNION ALL
               SELECT 1 FROM sgci_usuario_permisos_detalle
               WHERE email=? AND modulo=? AND accion='ver'
               LIMIT 1""", (email, modulo, email, modulo)
        ).fetchone()
        if configurado:
            return False
    # Compatibilidad con permisos históricos: las operaciones mutantes
    # siguen sujetas a controles adicionales por submódulo y registro.
    permiso = conn.execute('SELECT permitido FROM sgci_permisos WHERE email=? AND modulo=? AND accion=?',
                          (email, modulo, accion)).fetchone()
    return bool(permiso and permiso['permitido'])


def sgci_autorizar_operacion(conn, modulo, accion, submodulo=None):
    """Control del servidor; las operaciones nuevas deben indicar submódulo.

    Sin submódulo se conserva temporalmente la API histórica. Cuando se
    proporciona, se exige el permiso específico y se respetan las excepciones.
    La autorización por registro (p. ej. RR. HH.) se comprueba por separado.
    """
    if submodulo is not None:
        if not sgci_puede_submodulo(conn, modulo, submodulo, accion):
            raise PermissionError(
                f'Acceso denegado: {modulo} / {submodulo} / {accion}.'
            )
        return
    if not sgci_puede(conn, modulo, accion):
        raise PermissionError(f'Acceso denegado: {modulo} / {accion}. Contacta al administrador.')


def sgci_exigir_permiso(conn, modulo, accion='ver', submodulo=None):
    permitido = (sgci_puede_submodulo(conn, modulo, submodulo, accion)
                 if submodulo is not None else sgci_puede(conn, modulo, accion))
    if not permitido:
        st.error('No tienes autorización para esta operación. Contacta al administrador.')
        st.stop()


def sgci_guardar_permisos(conn, email, rol, activo, permisos):
    if not sgci_es_propietario():
        raise PermissionError('Solo el administrador principal puede gestionar permisos.')
    email = str(email).strip().lower()
    propietario = os.getenv('SGCI_ADMIN_EMAIL', '').strip().lower()
    if not email or '@' not in email or email == propietario:
        raise ValueError('Indica un correo válido distinto al del administrador principal.')
    if not conn.execute('SELECT 1 FROM sgci_perfiles WHERE nombre=?',(rol,)).fetchone():
        raise ValueError('Perfil no válido.')
    if any(mod not in SGCI_MODULOS or accion not in SGCI_ACCIONES for mod, accion in permisos):
        raise ValueError('Permisos inválidos.')
    with conn:
        conn.execute('INSERT INTO sgci_usuarios(email,rol,activo) VALUES(?,?,?) '
                     'ON CONFLICT(email) DO UPDATE SET rol=excluded.rol,activo=excluded.activo',
                     (email,rol,int(activo)))
        conn.execute('DELETE FROM sgci_permisos WHERE email=?',(email,))
        conn.executemany('INSERT INTO sgci_permisos(email,modulo,accion,permitido) VALUES(?,?,?,1)',
                         [(email,m,a) for m,a in permisos])
        conn.execute('INSERT INTO sgci_auditoria_permisos(actor,usuario,detalle) VALUES(?,?,?)',
                     (sgci_identidad_actual(),email,'Rol: '+rol+'; activo: '+str(activo)+'; permisos: '+repr(sorted(permisos))))


def sgci_puede_submodulo(conn, modulo, submodulo, accion='ver'):
    """Permiso efectivo: denegación individual > autorización individual > perfil.
    No se utiliza como sustituto de filtrado por registro ni de validación en mutaciones.
    """
    if sgci_es_propietario():
        return True
    email=sgci_identidad_actual()
    if not email or modulo not in SGCI_SUBMODULOS or submodulo not in SGCI_SUBMODULOS[modulo] or accion not in SGCI_ACCIONES_SUB:
        return False
    usuario=conn.execute('SELECT rol,activo FROM sgci_usuarios WHERE email=?',(email,)).fetchone()
    if not usuario or not usuario['activo']:
        return False
    override=conn.execute('SELECT permitido FROM sgci_usuario_permisos_detalle WHERE email=? AND modulo=? AND submodulo=? AND accion=?',
        (email,modulo,submodulo,accion)).fetchone()
    if override is not None:
        return bool(override['permitido'])
    perfil=conn.execute('SELECT permitido FROM sgci_perfil_permisos WHERE perfil=? AND modulo=? AND submodulo=? AND accion=?',
        (usuario['rol'],modulo,submodulo,accion)).fetchone()
    return bool(perfil and perfil['permitido'])


def sgci_guardar_perfil(conn, nombre, permisos):
    if not sgci_es_propietario():
        raise PermissionError('Solo el administrador puede gestionar perfiles.')
    nombre=str(nombre).strip()
    if not nombre or len(nombre)>80:
        raise ValueError('Nombre de perfil inválido.')
    if any(m not in SGCI_SUBMODULOS or sub not in SGCI_SUBMODULOS[m] or a not in SGCI_ACCIONES_SUB for m,sub,a in permisos):
        raise ValueError('Se detectaron permisos no válidos.')
    with conn:
        conn.execute('INSERT OR IGNORE INTO sgci_perfiles(nombre) VALUES(?)',(nombre,))
        conn.execute('DELETE FROM sgci_perfil_permisos WHERE perfil=?',(nombre,))
        conn.executemany('INSERT INTO sgci_perfil_permisos(perfil,modulo,submodulo,accion,permitido) VALUES(?,?,?,?,1)',
            [(nombre,m,sub,a) for m,sub,a in sorted(permisos)])
        conn.execute('INSERT INTO sgci_auditoria_permisos(actor,usuario,detalle) VALUES(?,?,?)',
            (sgci_identidad_actual(),nombre,'Perfil actualizado; '+str(len(permisos))+' autorizaciones'))


def sgci_guardar_excepciones(conn, email, excepciones):
    if not sgci_es_propietario():
        raise PermissionError('Solo el administrador puede gestionar permisos.')
    if not conn.execute('SELECT 1 FROM sgci_usuarios WHERE email=?',(email,)).fetchone():
        raise ValueError('Registra primero el usuario.')
    if any(m not in SGCI_SUBMODULOS or sub not in SGCI_SUBMODULOS[m] or a not in SGCI_ACCIONES_SUB or v not in (0,1)
           for m,sub,a,v in excepciones):
        raise ValueError('Excepciones inválidas.')
    with conn:
        conn.execute('DELETE FROM sgci_usuario_permisos_detalle WHERE email=?',(email,))
        conn.executemany('INSERT INTO sgci_usuario_permisos_detalle(email,modulo,submodulo,accion,permitido) VALUES(?,?,?,?,?)',
            [(email,m,sub,a,v) for m,sub,a,v in excepciones])
        conn.execute('INSERT INTO sgci_auditoria_permisos(actor,usuario,detalle) VALUES(?,?,?)',
            (sgci_identidad_actual(),email,'Excepciones actualizadas: '+str(len(excepciones))))


def sgci_editor_permisos(conn, base, guardados, key_prefix, con_herencia=False):
    resultado=[]
    for modulo,submodulos in SGCI_SUBMODULOS.items():
        with st.expander(SGCI_MODULOS[modulo],expanded=(modulo=='nomina')):
            for sub in submodulos:
                st.markdown('**'+sub+'**')
                columnas=st.columns(4)
                for i,accion in enumerate(SGCI_ACCIONES_SUB):
                    k=(modulo,sub,accion)
                    opciones=['Heredar','Permitir','Denegar'] if con_herencia else ['No','Sí']
                    actual=guardados.get(k,None if con_herencia else 0)
                    inicial=(0 if actual is None else (1 if actual==1 else 2)) if con_herencia else int(bool(actual))
                    with columnas[i%4]:
                        valor=st.selectbox(accion.capitalize(),opciones,index=inicial,
                            key=f'{key_prefix}_{modulo}_{sub}_{accion}')
                    if con_herencia and valor!='Heredar':
                        resultado.append((modulo,sub,accion,1 if valor=='Permitir' else 0))
                    elif not con_herencia and valor=='Sí':
                        resultado.append(k)
    return resultado


def sgci_alcance_rrhh(conn,email):
    """El alcance predeterminado de RR.HH. es siempre 'propios'."""
    fila=conn.execute('SELECT alcance FROM sgci_alcance_rrhh WHERE email=?',(email,)).fetchone()
    return fila['alcance'] if fila else 'propios'


def sgci_rrhh_ids_autorizados(conn,email):
    """Devuelve los IDs permitidos por alcance; no concede permisos de acción."""
    if sgci_es_propietario():
        return None  # Sin filtro para administrador principal
    if not conn.execute('SELECT 1 FROM sgci_usuarios WHERE email=? AND activo=1',(email,)).fetchone():
        return set()
    alcance=sgci_alcance_rrhh(conn,email)
    if alcance=='todos':
        return None
    propio=conn.execute('SELECT trabajador_id FROM sgci_usuario_trabajador WHERE email=?',(email,)).fetchone()
    ids={int(propio['trabajador_id'])} if propio else set()
    if alcance=='autorizados':
        ids.update(int(r['trabajador_id']) for r in conn.execute('SELECT trabajador_id FROM sgci_rrhh_autorizados WHERE email=?',(email,)))
    return ids


def sgci_validar_clave_nueva(clave,confirmar):
    if len(clave)<12 or not any(c.isalpha() for c in clave) or not any(c.isdigit() for c in clave):
        raise ValueError('La contraseña debe tener al menos 12 caracteres, letras y números.')
    if clave!=confirmar:
        raise ValueError('Las contraseñas no coinciden.')


def sgci_admin_auth_request(metodo,ruta,datos):
    """Uso EXCLUSIVO del servidor. No exponer la service-role key en Colab ni GitHub."""
    config=sgci_supabase_config()
    secreto=os.getenv('SUPABASE_SERVICE_ROLE_KEY','').strip()
    if not config or not secreto or os.getenv('SGCI_LAB_MODE','0')=='1':
        raise ValueError('Creación de cuentas deshabilitada en este laboratorio. Requiere un servidor privado configurado.')
    url,_=config
    req=urllib.request.Request(url+'/auth/v1/admin/'+ruta,
        data=json.dumps(datos).encode('utf-8'),
        headers={'apikey':secreto,'Authorization':'Bearer '+secreto,'Content-Type':'application/json'},method=metodo)
    try:
        with urllib.request.urlopen(req,timeout=15) as r:
            return json.loads(r.read().decode('utf-8'))
    except (urllib.error.HTTPError,urllib.error.URLError,TimeoutError):
        raise ValueError('No se pudo completar la operación administrativa de Supabase.') from None


def sgci_provisionar_cuenta(conn,email,clave):
    """Solo en servidor privado; no crea cuentas en el laboratorio público."""
    if not sgci_es_propietario():
        raise PermissionError('Solo el administrador puede crear accesos.')
    if not conn.execute('SELECT 1 FROM sgci_usuarios WHERE email=? AND activo=1',(email,)).fetchone():
        raise ValueError('Primero registra y habilita el usuario en SGCI.')
    sgci_validar_clave_nueva(clave,clave)
    sgci_admin_auth_request('POST','users',{'email':email,'password':clave,'email_confirm':True})
    with conn:
        conn.execute('UPDATE sgci_usuarios SET debe_cambiar_clave=1 WHERE email=?',(email,))
        conn.execute('INSERT INTO sgci_auditoria_permisos(actor,usuario,detalle) VALUES(?,?,?)',
            (sgci_identidad_actual(),email,'Cuenta Supabase creada; cambio de contraseña obligatorio'))


def sgci_pantalla_permisos(conn):
    """Panel único de configuración de permisos; no activa acceso operativo granular."""
    sgci_exigir_permiso(conn, 'administracion', 'ver')
    if not sgci_es_propietario():
        st.error('Solo el administrador principal puede gestionar usuarios y permisos.')
        return
    st.title('🛡️ Usuarios y permisos')
    st.warning('Laboratorio: la configuración detallada NO habilita todavía acceso seguro a datos de trabajadores. No compartir este entorno con otros usuarios.')
    tab_usuarios, tab_perfiles, tab_excepciones = st.tabs(['👥 Usuarios', '🛡️ Perfiles y permisos', '⚙️ Excepciones individuales'])

    with tab_usuarios:
        st.subheader('Cuentas de acceso y vinculación laboral')
        st.caption('Registrar un correo aquí NO crea una cuenta en Supabase ni asigna contraseñas. Esa integración está pendiente.')
        existentes=[r['email'] for r in conn.execute('SELECT email FROM sgci_usuarios ORDER BY email')]
        etiquetas={r['email']:(r['nombre_completo']+' · '+r['email']).strip(' ·') for r in conn.execute('SELECT email,nombre_completo FROM sgci_usuarios ORDER BY email')}
        elegido=st.selectbox('Seleccionar usuario', ['Crear nuevo usuario']+existentes,
                             format_func=lambda e: etiquetas.get(e,e), key='usr_sel')
        correo='' if elegido=='Crear nuevo usuario' else elegido
        previo=conn.execute('SELECT rol,activo,nombre_completo,cargo FROM sgci_usuarios WHERE email=?',(correo,)).fetchone() if correo else None
        perfiles=[r['nombre'] for r in conn.execute('SELECT nombre FROM sgci_perfiles ORDER BY nombre')]
        with st.form('sgci_usuario_unificado'):
            email=st.text_input('Correo electrónico de acceso', value=correo, disabled=bool(correo)).strip().lower()
            nombre_usuario=st.text_input('Nombre completo',value=previo['nombre_completo'] if previo else '')
            cargo_usuario=st.text_input('Cargo (escribe libremente)',value=previo['cargo'] if previo else '')
            rol=st.selectbox('Perfil asignado', ['Seleccionar perfil']+perfiles,index=(perfiles.index(previo['rol'])+1) if previo and previo['rol'] in perfiles else 0)
            activo=st.checkbox('Usuario habilitado (registro interno)',value=bool(previo['activo']) if previo else True)
            guardar=st.form_submit_button('Guardar usuario',type='primary')
        if guardar:
            try:
                # Conserva intactos los permisos antiguos; la nueva matriz detallada se administra en las otras pestañas.
                if rol=='Seleccionar perfil':
                    raise ValueError('Selecciona un perfil antes de guardar.')
                if not email or '@' not in email or email==os.getenv('SGCI_ADMIN_EMAIL','').strip().lower():
                    raise ValueError('Introduce un correo válido distinto del administrador principal.')
                with conn:
                    conn.execute('INSERT INTO sgci_usuarios(email,rol,activo,nombre_completo,cargo) VALUES(?,?,?,?,?) ON CONFLICT(email) DO UPDATE SET rol=excluded.rol,activo=excluded.activo,nombre_completo=excluded.nombre_completo,cargo=excluded.cargo',(email,rol,int(activo),nombre_usuario.strip(),cargo_usuario.strip()))
                    conn.execute("INSERT OR IGNORE INTO sgci_alcance_rrhh(email,alcance) VALUES(?,'propios')",(email,))
                    conn.execute('INSERT INTO sgci_auditoria_permisos(actor,usuario,detalle) VALUES(?,?,?)',(sgci_identidad_actual(),email,'Usuario creado/actualizado; perfil='+rol+'; habilitado='+str(activo)))
                st.session_state['_sgci_ultimo_exito']='Usuario guardado correctamente: '+email
                st.rerun()
            except (ValueError,sqlite3.Error) as exc:
                st.error(str(exc))
        st.divider()
        st.subheader('Vincular con ficha de Nómina')
        if existentes:
            email_v=st.selectbox('Usuario',existentes,format_func=lambda e:etiquetas.get(e,e),key='vinculo_usuario')
            trabajadores=conn.execute('SELECT id,nombre,rut FROM nomina_trabajadores ORDER BY nombre').fetchall()
            if trabajadores:
                opciones={'Sin vinculación':None}
                opciones.update({f"{r['nombre']} · {r['rut']}":r['id'] for r in trabajadores})
                vinculo=conn.execute('SELECT trabajador_id FROM sgci_usuario_trabajador WHERE email=?',(email_v,)).fetchone()
                actual=vinculo['trabajador_id'] if vinculo else None
                etiquetas_trabajador=list(opciones)
                idx=next((i for i,k in enumerate(etiquetas_trabajador) if opciones[k]==actual),0)
                etiqueta=st.selectbox('Ficha de trabajador',etiquetas_trabajador,index=idx)
                if st.button('Guardar vinculación',type='primary'):
                    try:
                        with conn:
                            if opciones[etiqueta] is None:
                                conn.execute('DELETE FROM sgci_usuario_trabajador WHERE email=?',(email_v,))
                            else:
                                conn.execute('INSERT INTO sgci_usuario_trabajador(email,trabajador_id) VALUES(?,?) ON CONFLICT(email) DO UPDATE SET trabajador_id=excluded.trabajador_id',(email_v,opciones[etiqueta]))
                            conn.execute('INSERT INTO sgci_auditoria_permisos(actor,usuario,detalle) VALUES(?,?,?)',(sgci_identidad_actual(),email_v,'Vinculación laboral actualizada'))
                        st.success('Vinculación guardada. El alcance de RR.HH. permanece en Solo mis datos.')
                    except sqlite3.IntegrityError:
                        st.error('La ficha seleccionada ya está vinculada a otra cuenta.')
            else:
                st.info('No hay trabajadores registrados.')
        else:
            st.info('Crea primero un usuario.')
        st.divider()
        st.subheader('Alcance de información de Recursos Humanos')
        st.caption('Predeterminado: Solo mis datos. El alcance no sustituye los permisos de acción.')
        if existentes:
            alcance_email=st.selectbox('Cuenta a configurar',existentes,format_func=lambda e:etiquetas.get(e,e),key='alcance_email')
            actual=sgci_alcance_rrhh(conn,alcance_email)
            niveles={'propios':'Solo mis datos','autorizados':'Registros autorizados','todos':'Todos los registros'}
            alcance_nuevo=st.selectbox('Alcance de RR.HH.',list(niveles),index=list(niveles).index(actual),format_func=lambda x:niveles[x])
            vinculacion=conn.execute('SELECT trabajador_id FROM sgci_usuario_trabajador WHERE email=?',(alcance_email,)).fetchone()
            st.caption('Ficha vinculada: '+str(vinculacion['trabajador_id']) if vinculacion else 'Sin ficha vinculada: el alcance propio no autoriza ningún registro.')
            autorizados=[]
            if alcance_nuevo=='autorizados':
                opciones_trab={f"{r['nombre']} · {r['rut']}":r['id'] for r in conn.execute('SELECT id,nombre,rut FROM nomina_trabajadores ORDER BY nombre')}
                actuales={r['trabajador_id'] for r in conn.execute('SELECT trabajador_id FROM sgci_rrhh_autorizados WHERE email=?',(alcance_email,))}
                autorizados=st.multiselect('Fichas adicionales autorizadas',list(opciones_trab),default=[k for k,v in opciones_trab.items() if v in actuales])
            if st.button('Guardar alcance de RR.HH.'):
                with conn:
                    conn.execute('INSERT INTO sgci_alcance_rrhh(email,alcance) VALUES(?,?) ON CONFLICT(email) DO UPDATE SET alcance=excluded.alcance',(alcance_email,alcance_nuevo))
                    conn.execute('DELETE FROM sgci_rrhh_autorizados WHERE email=?',(alcance_email,))
                    if alcance_nuevo=='autorizados':
                        conn.executemany('INSERT INTO sgci_rrhh_autorizados(email,trabajador_id) VALUES(?,?)',[(alcance_email,opciones_trab[k]) for k in autorizados])
                    conn.execute('INSERT INTO sgci_auditoria_permisos(actor,usuario,detalle) VALUES(?,?,?)',(sgci_identidad_actual(),alcance_email,'Alcance RR.HH. actualizado: '+alcance_nuevo))
                st.success('Alcance guardado correctamente.')
        st.divider()
        st.subheader('Contraseña temporal · Integración Supabase')
        st.info('La creación de cuentas Supabase está deshabilitada en Colab. En un servidor privado se habilitará con una clave administrativa guardada únicamente en variables de entorno.')
        if existentes:
            email_provision=st.selectbox('Cuenta',existentes,format_func=lambda e:etiquetas.get(e,e),key='provision_email')
            with st.form('provision_cuenta'):
                temporal=st.text_input('Contraseña temporal',type='password')
                confirmar_temp=st.text_input('Confirmar contraseña temporal',type='password')
                enviar_temp=st.form_submit_button('Crear cuenta Supabase',disabled=os.getenv('SGCI_LAB_MODE','0')=='1')
            if enviar_temp:
                try:
                    sgci_validar_clave_nueva(temporal,confirmar_temp)
                    sgci_provisionar_cuenta(conn,email_provision,temporal)
                    st.success('Cuenta creada; cambio obligatorio en el primer ingreso.')
                except (ValueError,PermissionError) as exc:
                    st.error(str(exc))
        st.divider()
        st.subheader('Usuarios registrados')
        st.dataframe(pd.read_sql_query('SELECT nombre_completo AS Nombre,email AS Correo,cargo AS Cargo,rol AS Perfil,activo AS Activo,creado_en AS Creado FROM sgci_usuarios ORDER BY email',conn),hide_index=True,use_container_width=True)

        # Las pantallas de simulación son exclusivamente para laboratorio.
        # SGCI_LAB_MODE por defecto está DESACTIVADO en producción.
        if sgci_es_propietario() and os.getenv('SGCI_LAB_MODE', '0') == '1':
            from sgci_rrhh_simulador import interfaz_simulador
            interfaz_simulador(st, conn)
            # Pantallas auxiliares de laboratorio: no bloquear Usuarios y permisos
            # cuando no fueron incluidas en el paquete entregado.
            try:
                from sgci_vista_empleado import interfaz_vista_empleado
            except ModuleNotFoundError as exc:
                if exc.name != 'sgci_vista_empleado':
                    raise
                st.warning('Vista de empleado no instalada en este laboratorio; prueba pendiente.')
            else:
                interfaz_vista_empleado(st, conn)
            try:
                from sgci_rrhh_lectura_controlada import interfaz_lectura_controlada
            except ModuleNotFoundError as exc:
                if exc.name != 'sgci_rrhh_lectura_controlada':
                    raise
                st.warning('Lectura controlada de RRHH no instalada; prueba pendiente.')
            else:
                interfaz_lectura_controlada(st, conn)
            from sgci_rrhh_pdf_controlado import interfaz_pdf_controlado
            interfaz_pdf_controlado(st, conn, rrhh_pdf_liquidacion)

    with tab_perfiles:
        st.subheader('Permisos por módulo, submódulo y acción')
        st.caption('Un perfil define permisos generales reutilizables. Marca Sí únicamente en las acciones que quieras autorizar.')
        perfiles=[r['nombre'] for r in conn.execute('SELECT nombre FROM sgci_perfiles ORDER BY nombre')]
        nuevo=st.text_input('Crear perfil nuevo (opcional)',key='perfil_nuevo').strip()
        opciones=perfiles+(['Nuevo: '+nuevo] if nuevo and nuevo not in perfiles else [])
        seleccionado=st.selectbox('Perfil a configurar',opciones,key='perfil_elegido')
        nombre=seleccionado[7:] if seleccionado.startswith('Nuevo: ') else seleccionado
        guardados={(r['modulo'],r['submodulo'],r['accion']):r['permitido'] for r in conn.execute('SELECT modulo,submodulo,accion,permitido FROM sgci_perfil_permisos WHERE perfil=?',(nombre,))}
        with st.form('perfil_detalle_unificado'):
            permisos=sgci_editor_permisos(conn,nombre,guardados,'perfil_unificado_'+nombre)
            enviar=st.form_submit_button('Guardar permisos del perfil',type='primary')
        if enviar:
            try:
                sgci_guardar_perfil(conn,nombre,permisos)
                st.success('Perfil guardado. No se han habilitado todavía controles operativos granulares.')
            except (ValueError,PermissionError) as exc:
                st.error(str(exc))

    with tab_excepciones:
        st.subheader('Personalizar permisos de una persona')
        st.caption('Heredar = usar perfil; Permitir = autorizar individualmente; Denegar = bloquear individualmente.')
        existentes=[r['email'] for r in conn.execute('SELECT email FROM sgci_usuarios ORDER BY email')]
        if not existentes:
            st.info('Registra primero un usuario en la pestaña Usuarios.')
        else:
            email=st.selectbox('Usuario',existentes,key='excepcion_usuario')
            usuario=conn.execute('SELECT rol FROM sgci_usuarios WHERE email=?',(email,)).fetchone()
            st.info('Perfil asignado: '+str(usuario['rol']))
            guardados={(r['modulo'],r['submodulo'],r['accion']):r['permitido'] for r in conn.execute('SELECT modulo,submodulo,accion,permitido FROM sgci_usuario_permisos_detalle WHERE email=?',(email,))}
            with st.form('excepciones_unificadas'):
                excepciones=sgci_editor_permisos(conn,email,guardados,'excepcion_unificada_'+email,con_herencia=True)
                enviar=st.form_submit_button('Guardar excepciones',type='primary')
            if enviar:
                try:
                    sgci_guardar_excepciones(conn,email,excepciones)
                    st.success('Excepciones individuales guardadas.')
                except (ValueError,PermissionError) as exc:
                    st.error(str(exc))
            st.divider()
            st.subheader('Resumen de permisos efectivos configurados')
            filas=[]
            for modulo,subs in SGCI_SUBMODULOS.items():
                for sub in subs:
                    for accion in SGCI_ACCIONES_SUB:
                        k=(modulo,sub,accion)
                        override=guardados.get(k)
                        if override is None:
                            fila=conn.execute('SELECT permitido FROM sgci_perfil_permisos WHERE perfil=? AND modulo=? AND submodulo=? AND accion=?',(usuario['rol'],*k)).fetchone()
                            permitido=bool(fila and fila['permitido'])
                            origen='Perfil'
                        else:
                            permitido=bool(override)
                            origen='Excepción individual'
                        if permitido or override is not None:
                            filas.append({'Módulo':SGCI_MODULOS[modulo],'Submódulo':sub,'Acción':accion.capitalize(),'Resultado':'Permitido' if permitido else 'Denegado','Origen':origen})
            if filas:
                st.dataframe(pd.DataFrame(filas),hide_index=True,use_container_width=True)
            else:
                st.info('No hay autorizaciones configuradas para este usuario.')
            st.caption('Este resumen describe la configuración; no certifica aún aislamiento de datos ni habilita el acceso operativo.')


# ============================================================
# PERFIL DE EMPRESA / MEMBRETE DE REPORTES (SGCI)
# ============================================================

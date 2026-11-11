# CONTEM: componente extraído del app.py original; ejecución secuencial compartida.
conn = conectar()

crear_esquema(conn)
oc_crear_tablas(conn)
sgci_crear_seguridad(conn)
dte_crear_tablas(conn)
sgci_empresa_esquema(conn)
reorganizar_plan_2026_seguro(conn)
instalar_cuentas_nomina(conn)

# Primer ingreso: forzar cambio antes de mostrar cualquier módulo.
if st.session_state.get('sgci_auth_tipo')=='supabase' and not sgci_es_propietario():
    email_login=sgci_identidad_actual()
    estado=conn.execute('SELECT activo,debe_cambiar_clave FROM sgci_usuarios WHERE email=?',(email_login,)).fetchone()
    if not estado or not estado['activo']:
        sgci_cerrar_sesion()
        st.error('Cuenta no autorizada o deshabilitada en SGCI.')
        st.stop()
    if estado['debe_cambiar_clave']:
        st.title('🔐 Cambio obligatorio de contraseña')
        st.info('Debes establecer una contraseña personal antes de continuar.')
        with st.form('sgci_cambio_inicial'):
            nueva=st.text_input('Nueva contraseña',type='password')
            confirmar=st.text_input('Confirmar nueva contraseña',type='password')
            guardar_clave=st.form_submit_button('Cambiar contraseña',type='primary')
        if guardar_clave:
            try:
                sgci_validar_clave_nueva(nueva,confirmar)
                sgci_auth_request('user',{'password':nueva},access_token=st.session_state['sgci_sb_access'])
                with conn:
                    conn.execute('UPDATE sgci_usuarios SET debe_cambiar_clave=0 WHERE email=?',(email_login,))
                    conn.execute('INSERT INTO sgci_auditoria_permisos(actor,usuario,detalle) VALUES(?,?,?)',(email_login,email_login,'Contraseña inicial modificada'))
                st.success('Contraseña actualizada. Vuelve a ingresar con tu nueva contraseña.')
                sgci_cerrar_sesion()
            except (ValueError,sqlite3.Error) as exc:
                st.error(str(exc))
        st.stop()

roles_actuales = cargar_roles(conn)

if "config_cuentas" not in st.session_state:
    st.session_state["config_cuentas"] = roles_actuales


# ============================================================
# SIDEBAR
# ============================================================

from modulos.tema_contem import aplicar_tema_contem
aplicar_tema_contem()
st.sidebar.markdown(
    '<div class="contem-brand"><div class="contem-brand-icon">C</div>'
    '<div><div class="contem-brand-name">CONTEM</div>'
    '<div class="contem-brand-sub">Sistema Contable y Empresarial</div></div></div>',
    unsafe_allow_html=True
)
st.sidebar.markdown("---")

# LABORATORIO: nunca permitir acceso operativo de empleados antes de terminar
# y auditar las validaciones por acción y por registro en TODOS los módulos.
if not sgci_es_propietario():
    # Portal aislado: NO entrar en la navegación general, incluso con LAB_MODE=0.
    # Solo sesiones verificadas por Supabase; no se admite identidad simulada.
    if st.session_state.get('sgci_auth_tipo') != 'supabase' or not sgci_sesion_valida():
        st.error('Para consultar tus liquidaciones debes iniciar sesión con Supabase.')
        st.stop()
    email_portal = sgci_identidad_actual()
    cuenta_portal = conn.execute(
        'SELECT activo,debe_cambiar_clave FROM sgci_usuarios WHERE email=?',
        (email_portal,)
    ).fetchone()
    if not cuenta_portal or not cuenta_portal['activo'] or cuenta_portal['debe_cambiar_clave']:
        st.error('Cuenta no habilitada para el portal de empleados.')
        st.stop()
    from sgci_rrhh_guardia_68b import mostrar_portal_con_sesion
    st.sidebar.info('Portal de empleado · Recursos Humanos')
    mostrar_portal_con_sesion(st, conn, st.session_state, email_portal, rrhh_pdf_liquidacion)
    st.stop()  # Invariante: empleados nunca alcanzan módulos administrativos.

sgci_nav_modulos = [
    ("🏠 Inicio","inicio"), ("🏦 Banco","banco"), ("💼 Tesorería","tesoreria"),
    ("💰 Ventas/clientes","cxc"), ("💳 Compras/proveedores","cxp"),
    ("🧾 Facturación y DTE","dte"), ("👥 Recursos Humanos","nomina"),
    ("📚 Contabilidad","contabilidad"), ("⚙️ Administración","administracion")
]
sgci_nav_permitidos = [etiqueta for etiqueta,codigo in sgci_nav_modulos if sgci_puede(conn,codigo,'ver')]
if not sgci_nav_permitidos:
    st.error('Tu usuario no tiene módulos habilitados. Solicita permisos al administrador.')
    st.stop()
modulo_principal = st.sidebar.radio(
    "Navegación",
    sgci_nav_permitidos,
    label_visibility="collapsed",
    key="nav_modulo_principal"
)

nav_context = None
if modulo_principal == "🏠 Inicio":
    menu = "🏠 Inicio"
elif modulo_principal == "🏦 Banco":
    menu = "🏦 Bancos y Cartolas"
elif modulo_principal == "💼 Tesorería":
    menu = "💼 Tesorería"
elif modulo_principal == "💰 Ventas/clientes":
    sub = st.selectbox("Sección de Cuentas por Cobrar", ["Clientes y estados de cuenta", "Pagos de clientes", "RCV Ventas", "Antigüedad de saldos", "Conciliación auxiliar"], key="nav_cxc")
    if sub == "Clientes y estados de cuenta": menu = "👥 Clientes"
    elif sub == "Pagos de clientes": menu = "💵 Pagos"; nav_context = "clientes"
    elif sub == "RCV Ventas": menu = "📤 RCV Ventas"
    elif sub == "Antigüedad de saldos": menu = "📌 Cuentas por Cobrar/Pagar"; nav_context = "clientes"
    else: menu = "📊 Conciliación"; nav_context = "clientes"
elif modulo_principal == "💳 Compras/proveedores":
    sub = st.selectbox("Sección de Cuentas por Pagar", ["Proveedores y estados de cuenta", "Pagos de proveedores", "RCV Compras", "Órdenes de compra", "Antigüedad de saldos", "Conciliación auxiliar"], key="nav_cxp")
    if sub == "Proveedores y estados de cuenta": menu = "🏢 Proveedores"
    elif sub == "Pagos de proveedores": menu = "💵 Pagos"; nav_context = "proveedores"
    elif sub == "RCV Compras": menu = "📥 RCV Compras"
    elif sub == "Órdenes de compra": menu = "🧾 Órdenes de compra"
    elif sub == "Antigüedad de saldos": menu = "📌 Cuentas por Cobrar/Pagar"; nav_context = "proveedores"
    else: menu = "📊 Conciliación"; nav_context = "proveedores"
elif modulo_principal == "🧾 Facturación y DTE":
    menu = "🧾 Facturación y DTE"
elif modulo_principal == "👥 Recursos Humanos":
    menu = "👥 Recursos Humanos"
elif modulo_principal == "📚 Contabilidad":
    sub = st.selectbox("Sección de Contabilidad", ["Asientos y Saldos", "Plan de Cuentas", "Libro Diario", "Libro Mayor", "Balance de Comprobación", "Estados Financieros"], key="nav_conta")
    menu = {
        "Asientos y Saldos":"✍️ Asientos y Saldos", "Plan de Cuentas":"📋 Plan de Cuentas",
        "Libro Diario":"📒 Libro Diario", "Libro Mayor":"📚 Mayor",
        "Balance de Comprobación":"⚖️ Balance de Comprobación", "Estados Financieros":"📊 Estados Financieros"
    }[sub]
else:
    sub = st.selectbox("Sección de Administración", (["Usuarios y permisos"] if sgci_es_propietario() else []) + ["Datos de la empresa", "Cierre Mensual", "Reglas Contables", "Lotes", "Matriz Contable"], key="nav_admin")
    menu = {"Datos de la empresa":"🏢 Datos de la empresa", "Usuarios y permisos":"🛡️ Usuarios y permisos", "Cierre Mensual":"🔒 Cierre Mensual", "Reglas Contables":"⚙️ Reglas Contables", "Lotes":"📦 Lotes", "Matriz Contable":"🧰 Matriz Contable"}[sub]

# Etapa 6.8A: comprobación de permiso de módulo en el servidor,
# después de resolver la navegación y antes de ejecutar cualquier pantalla.
# La barrera independiente del portal de empleados permanece intacta.
sgci_modulo_elegido = next(
    (codigo for etiqueta, codigo in sgci_nav_modulos if etiqueta == modulo_principal),
    None
)
if sgci_modulo_elegido is None:
    st.error('Módulo desconocido.')
    st.stop()
sgci_exigir_permiso(conn, sgci_modulo_elegido, 'ver')

st.sidebar.divider()
st.sidebar.caption("Respaldo de Datos")
if sgci_es_propietario() and os.path.exists(DB_FILE):
    with open(DB_FILE, "rb") as f:
        db_bytes = f.read()
    st.sidebar.download_button(
        label="💾 Descargar Respaldo BD",
        data=db_bytes,
        file_name=f"sgci_respaldo_{date.today().strftime('%Y%m%d')}.db",
        mime="application/octet-stream",
        help="Descarga una copia de seguridad exacta de tu base de datos local."
    )


if st.sidebar.button("🚪 Cerrar sesión"):
    sgci_cerrar_sesion()
    st.rerun()



# ============================================================
# INICIO
# ============================================================

# ============================================================
# SGCI: REPORTES DE PARTIDAS ABIERTAS (solo lectura)
# ============================================================

def sgci_reporte_partidas_abiertas(conn, modulo, tercero_id):
    """Separa deuda documental y créditos no aplicados sin netear dos veces."""
    if modulo not in ('VENTAS', 'COMPRAS'):
        raise ValueError('Auxiliar no permitido')
    sgci_conc_esquema(conn)
    documentos = sgci_facturas_compensables(conn, modulo, tercero_id).copy()
    nc = sgci_nc_disponibles(conn, modulo, tercero_id).copy()
    pagos = (abonos_disponibles_cliente(conn, tercero_id) if modulo == 'VENTAS'
             else pagos_disponibles_proveedor(conn, tercero_id)).copy()
    # Los saldos de ejercicios anteriores son desglose auxiliar de la apertura,
    # no nuevas ventas ni nuevos asientos contables.
    historicos = pd.read_sql_query("""
        SELECT s.ejercicio, s.referencia, s.fecha, s.monto,
               COALESCE((SELECT SUM(a.monto)
                         FROM sgci_aplicaciones_ejercicios a
                         WHERE a.saldo_id=s.id),0) aplicado
        FROM sgci_saldos_ejercicios s
        WHERE s.modulo=? AND s.tercero_id=?
        ORDER BY s.ejercicio,s.referencia
    """, conn, params=(modulo,int(tercero_id)))
    filas = []
    for r in historicos.itertuples(index=False):
        pendiente=max(0,clp_round(r.monto)-clp_round(r.aplicado))
        if pendiente<=0:
            continue
        filas.append({'Fecha':r.fecha,
                      'Documento':f'Factura anterior {r.referencia} ({r.ejercicio})',
                      'Clase':'Saldo histórico por cobrar' if modulo=='VENTAS' else 'Saldo histórico por pagar',
                      'Monto original':clp_round(r.monto),
                      'Aplicado':clp_round(r.aplicado),
                      'Saldo pendiente':pendiente})
    for r in documentos.itertuples(index=False):
        filas.append({'Fecha':r.fecha,'Documento':f'Factura / ND {r.folio or r.id}',
                      'Clase':'Documento por cobrar' if modulo=='VENTAS' else 'Documento por pagar',
                      'Monto original':clp_round(r.total),'Aplicado':clp_round(r.total-r.pendiente),
                      'Saldo pendiente':clp_round(r.pendiente)})
    for r in nc.itertuples(index=False):
        filas.append({'Fecha':r.fecha,'Documento':f'Nota de crédito {r.folio or r.id}',
                      'Clase':'Crédito disponible','Monto original':clp_round(r.total),
                      'Aplicado':clp_round(r.aplicado),'Saldo pendiente':-clp_round(r.disponible)})
    for r in pagos.itertuples(index=False):
        filas.append({'Fecha':r.fecha,'Documento':f'Pago / anticipo #{r.id}',
                      'Clase':'Pago o anticipo disponible','Monto original':clp_round(r.monto),
                      'Aplicado':clp_round(r.monto-r.disponible),'Saldo pendiente':-clp_round(r.disponible)})
    df = pd.DataFrame(filas,columns=['Fecha','Documento','Clase','Monto original','Aplicado','Saldo pendiente'])
    if not df.empty:
        df = df.sort_values(['Fecha','Documento'],kind='stable').reset_index(drop=True)
    return df


def sgci_mostrar_partidas_abiertas(conn, modulo, tercero_id, etiqueta):
    df = sgci_reporte_partidas_abiertas(conn, modulo, tercero_id)
    if df.empty:
        st.info('No hay partidas abiertas para este tercero.')
        return
    deuda = clp_round(df.loc[df['Saldo pendiente']>0,'Saldo pendiente'].sum())
    creditos = -clp_round(df.loc[df['Saldo pendiente']<0,'Saldo pendiente'].sum())
    a,b,c=st.columns(3)
    a.metric('Documentos pendientes',money(deuda))
    b.metric('NC y pagos / anticipos disponibles',money(creditos))
    c.metric('Posición neta',money(deuda-creditos))
    st.caption('La posición neta es informativa: los créditos disponibles no se consideran aplicados a una factura hasta compensarlos. No se descuentan dos veces los pagos ya aplicados.')
    st.dataframe(formatear_montos_df(df),use_container_width=True,hide_index=True)
    st.download_button('⬇️ Exportar partidas abiertas (CSV)',df.to_csv(index=False).encode('utf-8-sig'),
                       f'partidas_abiertas_{modulo.lower()}_{tercero_id}.csv','text/csv',
                       key=f'sgci_abiertas_csv_{modulo}_{tercero_id}')
    if modulo=='COMPRAS':
        # Estado de cuenta de deuda documental; créditos disponibles por separado.
        docs=df[df['Saldo pendiente']>0].copy()
        creditos_df=df[df['Saldo pendiente']<0].copy()
        filas_prov=[]
        for _,r in docs.iterrows():
            filas_prov.append([str(r['Fecha']),str(r['Documento']),money(r['Monto original']),
                               money(r['Aplicado']),money(r['Saldo pendiente'])])
        filas_prov.append(['','TOTAL DOCUMENTOS','','',money(deuda)])
        if not creditos_df.empty:
            filas_prov.append(['','CRÉDITOS SIN APLICAR','','',''])
            for _,r in creditos_df.iterrows():
                filas_prov.append([str(r['Fecha']),str(r['Documento']),money(r['Monto original']),
                                   money(r['Aplicado']),money(r['Saldo pendiente'])])
        filas_prov.append(['','CRÉDITOS DISPONIBLES','','',money(creditos)])
        filas_prov.append(['','POSICIÓN NETA INFORMATIVA','','',money(deuda-creditos)])
        pdf_prov=nomina_pdf('Estado de cuenta de proveedor - partidas abiertas',etiqueta,
                             ['Fecha','Documento','Monto original','Aplicado','Saldo pendiente'],filas_prov)
        st.download_button('🖨️ Imprimir estado de cuenta de proveedor (PDF)',pdf_prov,
                           f'estado_cuenta_pendiente_proveedor_{tercero_id}.pdf',
                           'application/pdf',key=f'sgci_prov_abierto_pdf_{tercero_id}')
        st.caption('El total por pagar corresponde a documentos pendientes; los créditos sin aplicar se informan por separado.')
    if modulo=='VENTAS':
        # Reporte de cobranza a partir de partidas abiertas; vencimiento configurable.
        dias=st.number_input('Plazo de pago (días, si el XML no informa vencimiento)',
                             min_value=0,max_value=365,value=30,step=1,key='sgci_plazo_cobranza')
        corte=st.date_input('Fecha de corte para mora',date.today(),key='sgci_corte_cobranza')
        venc=df[df['Saldo pendiente']>0].copy()
        venc['Vencimiento']=pd.to_datetime(venc['Fecha'],errors='coerce')+pd.to_timedelta(dias,unit='D')
        venc['Días vencidos']=venc['Vencimiento'].apply(lambda d:max(0,(corte-d.date()).days) if pd.notna(d) else 0)
        venc['Estado']=venc['Días vencidos'].apply(lambda d:'VENCIDO' if d>0 else 'VIGENTE')
        venc['Vencimiento']=venc['Vencimiento'].dt.strftime('%d-%m-%Y')
        vencido=clp_round(venc.loc[venc['Estado']=='VENCIDO','Saldo pendiente'].sum())
        st.metric('Saldo vencido de documentos',money(vencido))
        st.caption('Vencimientos estimados usando el plazo indicado; validar condiciones contractuales. Las referencias y descripciones XML no se inventan si no están almacenadas.')
        st.dataframe(formatear_montos_df(venc),use_container_width=True,hide_index=True)
        # Enriquecimiento documental: el saldo procede del auxiliar; referencias/descripción del repositorio XML.
        perfil=sgci_perfil(conn)
        rut_cliente=conn.execute('SELECT rut FROM clientes WHERE id=?',(tercero_id,)).fetchone()
        rut_cli=normalizar_rut(rut_cliente['rut']) if rut_cliente else ''
        detalle=[]
        for _,r in venc.iterrows():
            folio=str(r['Documento']).split()[-1]
            xml=conn.execute("""SELECT id FROM dte_documentos WHERE folio=? AND
                REPLACE(REPLACE(UPPER(rut_receptor),'.',''),'-','')=?
                AND tipo_doc IN (33,34,56) ORDER BY id DESC LIMIT 1""",
                (folio,re.sub(r'[^0-9K]','',rut_cli.upper()))).fetchone()
            refs='';descripcion=''
            if xml:
                rr=conn.execute('SELECT folio_ref,razon_ref FROM dte_referencias WHERE documento_id=? ORDER BY linea LIMIT 4',(xml['id'],)).fetchall()
                refs='; '.join(' / '.join(filter(None,[str(x['folio_ref'] or ''),str(x['razon_ref'] or '')])) for x in rr)
                items=conn.execute('SELECT nombre,descripcion FROM dte_items WHERE documento_id=? ORDER BY linea LIMIT 3',(xml['id'],)).fetchall()
                descripcion='; '.join(' - '.join(filter(None,[str(x['nombre'] or ''),str(x['descripcion'] or '')])) for x in items)
            detalle.append([str(r['Fecha']),folio,refs or '—',descripcion or '—',
                money(r['Monto original']),money(r['Aplicado']),money(r['Saldo pendiente']),
                str(r['Vencimiento']),str(r['Estado']),str(r['Días vencidos'])])
        st.caption('Las referencias y conceptos se muestran cuando el folio y el RUT receptor coinciden con un XML almacenado. Un guion indica información documental no encontrada.')
        pdf=nomina_pdf('Estado de cuenta detallado de cobranza',etiqueta,
            ['Fecha','Factura','Referencia XML','Servicio / descripción XML','Monto','Aplicado','Pendiente','Vence','Estado','Días'],
            detalle,['','TOTAL','','','', '',money(deuda),'','',''])
        st.download_button('🖨️ PDF detallado de cobranza',pdf,f'cobranza_cliente_{tercero_id}.pdf',
                           'application/pdf',key=f'sgci_cobranza_pdf_{tercero_id}')


if menu == "🏢 Datos de la empresa":
    sgci_pantalla_empresa(conn)
elif menu == "🛡️ Usuarios y permisos":
    sgci_pantalla_permisos(conn)
elif menu == "💼 Tesorería":
    pantalla_tesoreria(conn)
elif menu == "🧾 Facturación y DTE":
    pantalla_dte(conn)
elif menu == "🏠 Inicio":
    st.markdown(
        '<div class="contem-hero"><h2>Bienvenido a CONTEM</h2>'
        '<p>Tu empresa, tus finanzas y tus tareas en un solo lugar.</p></div>',
        unsafe_allow_html=True
    )
    st.title('Panel de control')
    st.caption('Indicadores y tareas prioritarias · información basada en los registros contables de CONTEM')
    hoy=date.today().isoformat()
    mes=hoy[:7]
    def _sgci_valor(sql,params=()):
        try:
            return float(conn.execute(sql,params).fetchone()[0] or 0)
        except sqlite3.Error:
            return 0.0
    ingresos=_sgci_valor("SELECT COALESCE(SUM(haber-debe),0) FROM libro_diario WHERE substr(fecha,1,7)=? AND codigo_cuenta LIKE '4.%'",(mes,))
    gastos=_sgci_valor("SELECT COALESCE(SUM(debe-haber),0) FROM libro_diario WHERE substr(fecha,1,7)=? AND (codigo_cuenta LIKE '5.%' OR codigo_cuenta LIKE '6.%')",(mes,))
    saldo_banco=_sgci_valor("SELECT COALESCE(SUM(d.debe-d.haber),0) FROM libro_diario d WHERE d.codigo_cuenta IN (SELECT cuenta_contable FROM bancos WHERE activo=1)")
    c1,c2,c3,c4=st.columns(4)
    c1.metric('Saldo contable en bancos',money(saldo_banco))
    c2.metric('Ingresos del mes',money(ingresos))
    c3.metric('Gastos del mes',money(gastos))
    c4.metric('Resultado del mes',money(ingresos-gastos))
    st.caption('Montos del Libro Diario · período '+mes+' · el saldo bancario puede diferir de la cartola hasta su conciliación.')
    st.write('')
    col_tareas,col_flujo,col_gastos=st.columns([1.25,1.25,1])
    with col_tareas:
        st.subheader('✅ Tareas pendientes')
        pendientes_pago=int(_sgci_valor("SELECT COUNT(*) FROM tes_solicitudes WHERE estado='PENDIENTE_CONTABILIZACION'"))
        pendientes_tes=int(_sgci_valor("SELECT COUNT(*) FROM tes_solicitudes WHERE estado IN ('BORRADOR','ENVIADA','APROBADA')"))
        pendientes_cartola=int(_sgci_valor('SELECT COUNT(*) FROM cartola_bancaria WHERE conciliado=0'))
        if pendientes_pago: st.warning(f'💳 {pendientes_pago} pago(s) por contabilizar')
        if pendientes_tes: st.info(f'📋 {pendientes_tes} solicitud(es) de Tesorería por gestionar')
        if pendientes_cartola: st.info(f'🏦 {pendientes_cartola} movimiento(s) bancario(s) sin conciliar')
        if not (pendientes_pago or pendientes_tes or pendientes_cartola): st.success('Sin tareas pendientes en los controles principales.')
    with col_flujo:
        st.subheader('📊 Ingresos y egresos · 6 meses')
        try:
            flujo=pd.read_sql_query('''SELECT substr(fecha,1,7) AS mes,
                SUM(CASE WHEN codigo_cuenta LIKE '4.%' THEN haber-debe ELSE 0 END) AS Ingresos,
                SUM(CASE WHEN codigo_cuenta LIKE '5.%' OR codigo_cuenta LIKE '6.%' THEN debe-haber ELSE 0 END) AS Egresos
                FROM libro_diario WHERE fecha IS NOT NULL GROUP BY substr(fecha,1,7) ORDER BY mes DESC LIMIT 6''',conn)
            if flujo.empty: st.info('Aún no hay movimientos para graficar.')
            else:
                flujo=flujo.sort_values('mes').set_index('mes')
                st.bar_chart(flujo[['Ingresos','Egresos']],height=225,color=['#2E906A','#E2A25B'])
        except (sqlite3.Error,ValueError): st.info('Gráfico disponible cuando existan movimientos contables.')
    with col_gastos:
        st.subheader('📌 Gastos del mes')
        try:
            categorias=pd.read_sql_query('''SELECT COALESCE(NULLIF(c.nombre,''),d.codigo_cuenta) AS Cuenta,
                SUM(d.debe-d.haber) AS Monto FROM libro_diario d
                LEFT JOIN plan_cuentas c ON c.codigo=d.codigo_cuenta
                WHERE substr(d.fecha,1,7)=? AND (d.codigo_cuenta LIKE '5.%' OR d.codigo_cuenta LIKE '6.%')
                GROUP BY d.codigo_cuenta HAVING ABS(SUM(d.debe-d.haber))>0 ORDER BY ABS(SUM(d.debe-d.haber)) DESC LIMIT 6''',conn,params=(mes,))
            if categorias.empty: st.info('Sin gastos registrados en este período.')
            else: st.dataframe(formatear_montos_df(categorias),hide_index=True,use_container_width=True,height=225)
        except sqlite3.Error: st.info('Sin información disponible.')
    st.divider()
    st.subheader('Actividad y operaciones recientes')
    col_actividad,col_tes,col_pagar=st.columns(3)
    with col_actividad:
        st.markdown('**Actividad contable**')
        actividad=pd.read_sql_query('SELECT fecha,cuenta,glosa,debe,haber FROM libro_diario ORDER BY id DESC LIMIT 7',conn)
        if actividad.empty: st.info('Sin movimientos contables registrados.')
        else: st.dataframe(formatear_montos_df(actividad),hide_index=True,use_container_width=True,height=270)
    with col_tes:
        st.markdown('**Solicitudes de Tesorería**')
        tes_crear_tablas(conn)
        tes_inicio=pd.read_sql_query('''SELECT s.id,s.beneficiario,s.estado,COALESCE(SUM(d.monto),0) AS monto
            FROM tes_solicitudes s LEFT JOIN tes_solicitud_detalle d ON d.solicitud_id=s.id
            GROUP BY s.id ORDER BY s.id DESC LIMIT 7''',conn)
        if tes_inicio.empty: st.info('No hay solicitudes registradas.')
        else: st.dataframe(formatear_montos_df(tes_inicio),hide_index=True,use_container_width=True,height=270)
    with col_pagar:
        st.markdown('**Cuentas por pagar**')
        pendientes=pd.read_sql_query('''SELECT p.nombre AS proveedor,c.folio,c.fecha,
            ROUND(ABS(COALESCE(c.monto_total,0))-COALESCE((SELECT SUM(ABS(a.monto)) FROM aplicaciones_proveedores a WHERE a.compra_id=c.id),0)) AS saldo
            FROM compras c LEFT JOIN proveedores p ON p.id=c.proveedor_id
            WHERE c.tipo_doc NOT IN (60,61,52) OR c.tipo_doc IS NULL
            ORDER BY c.fecha DESC LIMIT 100''',conn)
        pendientes=pendientes[pendientes.saldo>0].head(7) if not pendientes.empty else pendientes
        if pendientes.empty: st.info('No hay documentos pendientes en esta vista.')
        else: st.dataframe(formatear_montos_df(pendientes),hide_index=True,use_container_width=True,height=270)
    st.divider()
    st.subheader('⚡ Accesos rápidos')
    accesos=[('💼 Tesorería','💼 Tesorería'),('🏦 Bancos','🏦 Banco'),('💰 Ventas','💰 Ventas/clientes'),('💳 Compras','💳 Compras/proveedores'),('📚 Contabilidad','📚 Contabilidad')]
    cols=st.columns(5)
    def _ir_inicio_sgci(destino):
        st.session_state['nav_modulo_principal']=destino
    for col,(nombre,destino) in zip(cols,accesos):
        with col:
            st.button(nombre,use_container_width=True,disabled=destino not in sgci_nav_permitidos,
                      key='inicio_acceso_'+destino,on_click=_ir_inicio_sgci,args=(destino,))

elif menu == "👥 Recursos Humanos":
    st.title("👥 Recursos Humanos")
    if not sgci_es_propietario():
        # Etapa 6.6: rama aislada. El bloqueo global de laboratorio permanece activo.
        # No reutilizar las pantallas administrativas de Nómina para empleados.
        from sgci_rrhh_guardia_68b import mostrar_portal_con_sesion
        mostrar_portal_con_sesion(st, conn, st.session_state, sgci_identidad_actual(), rrhh_pdf_liquidacion)
        st.stop()
    st.caption("Expedientes laborales, documentos, vacaciones y remuneraciones, con la contabilización histórica de CONTEM.")
    # Navegación persistente: evita que las actualizaciones de Streamlit devuelvan
    # al usuario a la primera pestaña al cambiar trabajadores u otros controles.
    nomina_opciones = ["Trabajadores", "Vacaciones", "Anticipos y préstamos", "Liquidación mensual",
                      "Resumen y reportes", "Parámetros", "Contabilización"]
    nomina_seccion = st.selectbox("Sección de Recursos Humanos", nomina_opciones,
                                  key="sgci_nomina_seccion")

    if nomina_seccion == 'Trabajadores':
        st.subheader("Ficha del trabajador")
        trabajadores=pd.read_sql_query("SELECT * FROM nomina_trabajadores ORDER BY activo DESC,nombre",conn)
        if not trabajadores.empty:
            vista=trabajadores[['rut','nombre','cargo','fecha_ingreso','sueldo_base','afp','salud_tipo','banco','activo']].copy(); vista['sueldo_base']=vista['sueldo_base'].map(lambda x: money(x)); vista['activo']=vista['activo'].map({1:'Activo',0:'Inactivo'})
            st.dataframe(vista.rename(columns={'rut':'RUT','nombre':'Nombre','cargo':'Cargo','fecha_ingreso':'Ingreso','sueldo_base':'Sueldo base','afp':'AFP','salud_tipo':'Salud','banco':'Banco','activo':'Estado'}),use_container_width=True,hide_index=True)
        if not trabajadores.empty:
            st.markdown("### Expediente del trabajador · Vista completa")
            opciones_exp={f"{r.rut} · {r.nombre}":int(r.id) for r in trabajadores.itertuples()}
            sel_exp=st.selectbox("Consultar expediente",list(opciones_exp),key="rrhh_exp_trab")
            exp=conn.execute("SELECT * FROM nomina_trabajadores WHERE id=?",(opciones_exp[sel_exp],)).fetchone()
            with st.container(border=True):
                st.subheader(exp["nombre"])
                a,b,c=st.columns(3)
                a.metric("Sueldo base",money(exp["sueldo_base"]))
                b.metric("Estado","Activo" if exp["activo"] else "Inactivo")
                c.metric("Fecha de ingreso",exp["fecha_ingreso"] or "—")
                campos=[("RUT","rut"),("Cargo","cargo"),("Tipo de contrato","tipo_contrato"),
                        ("Gratificación","gratificacion_tipo"),("Valor gratificación","gratificacion_valor"),
                        ("AFP","afp"),("Salud","salud_tipo"),("Isapre","isapre"),
                        ("Modalidad salud","salud_modalidad"),("Valor salud","salud_valor"),
                        ("AFC","afc"),("Anticipo quincenal","anticipo_quincenal"),
                        ("Porcentaje anticipo","anticipo_porcentaje"),("Banco","banco"),
                        ("Tipo de cuenta","tipo_cuenta"),("Número de cuenta","numero_cuenta")]
                for ix in range(0,len(campos),3):
                    columnas=st.columns(3)
                    for col,(etiqueta,campo) in zip(columnas,campos[ix:ix+3]):
                        valor=exp[campo]
                        if campo in ("afc","anticipo_quincenal"): valor="Sí" if valor else "No"
                        elif campo=="gratificacion_valor": valor=money(valor)
                        col.text_input(etiqueta,value=str(valor if valor is not None else "—"),disabled=True,key=f"rrhh_exp_{campo}_{exp['id']}")
                st.markdown("#### Contratos y anexos")
                docs=pd.read_sql_query("SELECT id,tipo,nombre_archivo,fecha_documento,observacion,creado_en FROM rrhh_documentos WHERE trabajador_id=? AND activo=1 ORDER BY id DESC",conn,params=(exp["id"],))
                if not docs.empty:
                    st.dataframe(docs,hide_index=True,use_container_width=True)
                    for dr in docs.itertuples():
                        with st.expander(f"{dr.tipo} · {dr.nombre_archivo} · #{dr.id}"):
                            doc=conn.execute("SELECT contenido FROM rrhh_documentos WHERE id=? AND trabajador_id=? AND activo=1",(dr.id,exp["id"])).fetchone()
                            if doc:
                                st.download_button("Descargar PDF",bytes(doc["contenido"]),file_name=dr.nombre_archivo,mime="application/pdf",key=f"rrhh_desc_doc_{dr.id}")
                            st.caption(dr.observacion or "Sin observaciones")
                with st.expander("➕ Adjuntar contrato o anexo",expanded=False):
                    with st.form(f"rrhh_form_doc_{exp['id']}",clear_on_submit=True):
                        tipo_doc=st.selectbox("Tipo de documento",["Contrato de trabajo","Anexo de contrato","Otro documento laboral"])
                        fecha_doc=st.date_input("Fecha del documento",value=date.today(),key=f"rrhh_doc_fecha_{exp['id']}")
                        archivo=st.file_uploader("Adjuntar PDF (máximo 8 MB)",type=["pdf"],key=f"rrhh_upload_{exp['id']}")
                        obs_doc=st.text_area("Observaciones",key=f"rrhh_doc_obs_{exp['id']}")
                        guardar_doc=st.form_submit_button("Guardar documento")
                    if guardar_doc:
                        if archivo is None:
                            st.error("Selecciona un PDF.")
                        else:
                            contenido=archivo.getvalue()
                            if len(contenido)>8*1024*1024 or not contenido.startswith(b"%PDF-"):
                                st.error("El archivo debe ser un PDF válido de hasta 8 MB.")
                            else:
                                conn.execute("""INSERT INTO rrhh_documentos
                                    (trabajador_id,tipo,nombre_archivo,fecha_documento,observacion,contenido,sha256,creado_en)
                                    VALUES(?,?,?,?,?,?,?,?)""",
                                    (exp["id"],tipo_doc,os.path.basename(archivo.name),fecha_doc.isoformat(),obs_doc,sqlite3.Binary(contenido),sha256(contenido).hexdigest(),datetime.now().isoformat(timespec="seconds")))
                                conn.commit()
                                sgci_exito("Documento incorporado al expediente.");st.rerun()
                st.markdown("#### Últimas liquidaciones")
                hist_exp=pd.read_sql_query("SELECT periodo,total_haberes,total_descuentos,saldo_pagar,estado FROM nomina_liquidaciones WHERE trabajador_id=? ORDER BY periodo DESC LIMIT 12",conn,params=(exp["id"],))
                if not hist_exp.empty: st.dataframe(formatear_montos_df(hist_exp),use_container_width=True,hide_index=True)

        modo_trab=st.selectbox("Acción",["Nuevo trabajador","Editar trabajador"],key='nom_modo_trab')
        edit_row=None
        if modo_trab=='Editar trabajador' and not trabajadores.empty:
            labels={f"{r.id} - {r.rut} - {r.nombre}":r for r in trabajadores.itertuples()}; sel=st.selectbox('Trabajador',list(labels)); edit_row=labels[sel]
        with st.form('nom_ficha_trab'):
            a,b,c=st.columns(3)
            rut=a.text_input('RUT',value=getattr(edit_row,'rut','') if edit_row else '')
            nombre=b.text_input('Nombre completo',value=getattr(edit_row,'nombre','') if edit_row else '')
            cargo=c.text_input('Cargo',value=getattr(edit_row,'cargo','') if edit_row else '')
            ingreso=a.date_input('Fecha de ingreso',value=pd.to_datetime(getattr(edit_row,'fecha_ingreso',date.today()) or date.today()).date())
            contrato=b.selectbox('Tipo de contrato',['Indefinido','Plazo fijo','Obra o faena','Otro'],index=['Indefinido','Plazo fijo','Obra o faena','Otro'].index(getattr(edit_row,'tipo_contrato','Indefinido') or 'Indefinido') if edit_row and (getattr(edit_row,'tipo_contrato','Indefinido') or 'Indefinido') in ['Indefinido','Plazo fijo','Obra o faena','Otro'] else 0)
            sueldo=c.number_input('Sueldo base mensual',min_value=0.0,value=float(getattr(edit_row,'sueldo_base',0) or 0),step=10000.0,format='%.0f')
            vigencia_cond=a.date_input('Condiciones vigentes desde',value=date.today(),help='Fecha desde la cual rigen sueldo, AFP y plan de salud. Los cambios quedan en historial.')
            grat_tipo=a.selectbox('Gratificación',['Monto mensual','Sin gratificación / manual'],index=0 if not edit_row or getattr(edit_row,'gratificacion_tipo','Monto mensual')=='Monto mensual' else 1)
            grat=b.number_input('Gratificación habitual',min_value=0.0,value=float(getattr(edit_row,'gratificacion_valor',0) or 0),step=1000.0,format='%.0f')
            afps=pd.read_sql_query("SELECT afp FROM nomina_parametros_afp WHERE activo=1 ORDER BY afp",conn)['afp'].tolist(); afp_actual=getattr(edit_row,'afp','Uno') if edit_row else 'Uno'; afp=c.selectbox('AFP',afps,index=afps.index(afp_actual) if afp_actual in afps else 0)
            salud_tipo=a.selectbox('Sistema de salud',['Fonasa','Isapre'],index=1 if edit_row and getattr(edit_row,'salud_tipo','Fonasa')=='Isapre' else 0)
            isapre=b.text_input('Isapre (si corresponde)',value=getattr(edit_row,'isapre','') or '' if edit_row else '')
            modalidades=['7% legal','Porcentaje pactado','Plan en UF','Monto pactado en pesos']; mod_actual=getattr(edit_row,'salud_modalidad','7% legal') if edit_row else '7% legal'; salud_modalidad=c.selectbox('Modalidad salud',modalidades,index=modalidades.index(mod_actual) if mod_actual in modalidades else 0)
            valor_def=float(getattr(edit_row,'salud_valor',7) or 7) if edit_row else 7.0; salud_valor=a.number_input('Porcentaje o monto pactado',min_value=0.0,value=valor_def,step=.01,help='7% legal: 7. Porcentaje: ej. 8,5. Plan en UF: ej. 4,25. Monto pactado: pesos.')
            afc=b.checkbox('Afecto a AFC',value=bool(getattr(edit_row,'afc',1)) if edit_row else True)
            anticipo=c.checkbox('Anticipo quincenal',value=bool(getattr(edit_row,'anticipo_quincenal',1)) if edit_row else True)
            ant_pct=a.number_input('% anticipo habitual',min_value=0.0,max_value=100.0,value=float(getattr(edit_row,'anticipo_porcentaje',50) or 50) if edit_row else 50.0)
            banco=b.text_input('Banco',value=getattr(edit_row,'banco','') or '' if edit_row else '')
            tipo_cta=c.selectbox('Tipo de cuenta',['Corriente','Vista','Ahorro','Otra'],index=0)
            nro=a.text_input('N° de cuenta',value=getattr(edit_row,'numero_cuenta','') or '' if edit_row else '')
            activo=b.checkbox('Trabajador activo',value=bool(getattr(edit_row,'activo',1)) if edit_row else True)
            guardar=st.form_submit_button('💾 Guardar ficha',type='primary')
            if guardar:
                if not rut.strip() or not nombre.strip(): st.error('RUT y nombre son obligatorios.')
                else:
                    vals=(rut.strip(),nombre.strip(),ingreso.isoformat(),cargo.strip(),contrato,clp_round(sueldo),grat_tipo,clp_round(grat),afp,salud_tipo,isapre.strip(),salud_modalidad,salud_valor,int(afc),int(anticipo),ant_pct,banco.strip(),tipo_cta,nro.strip(),int(activo),datetime.now().isoformat(timespec='seconds'))
                    if edit_row:
                        conn.execute("UPDATE nomina_trabajadores SET rut=?,nombre=?,fecha_ingreso=?,cargo=?,tipo_contrato=?,sueldo_base=?,gratificacion_tipo=?,gratificacion_valor=?,afp=?,salud_tipo=?,isapre=?,salud_modalidad=?,salud_valor=?,afc=?,anticipo_quincenal=?,anticipo_porcentaje=?,banco=?,tipo_cuenta=?,numero_cuenta=?,activo=?,fecha_creacion=? WHERE id=?",vals+(edit_row.id,))
                    else:
                        conn.execute("INSERT INTO nomina_trabajadores(rut,nombre,fecha_ingreso,cargo,tipo_contrato,sueldo_base,gratificacion_tipo,gratificacion_valor,afp,salud_tipo,isapre,salud_modalidad,salud_valor,afc,anticipo_quincenal,anticipo_porcentaje,banco,tipo_cuenta,numero_cuenta,activo,fecha_creacion) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",vals)
                    trabajador_id = edit_row.id if edit_row else conn.execute("SELECT id FROM nomina_trabajadores WHERE rut=?",(rut.strip(),)).fetchone()[0]
                    conn.execute("INSERT INTO nomina_historial_condiciones(trabajador_id,vigente_desde,sueldo_base,gratificacion_tipo,gratificacion_valor,afp,salud_tipo,isapre,salud_modalidad,salud_valor,observacion,fecha_registro) VALUES(?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(trabajador_id,vigente_desde) DO UPDATE SET sueldo_base=excluded.sueldo_base,gratificacion_tipo=excluded.gratificacion_tipo,gratificacion_valor=excluded.gratificacion_valor,afp=excluded.afp,salud_tipo=excluded.salud_tipo,isapre=excluded.isapre,salud_modalidad=excluded.salud_modalidad,salud_valor=excluded.salud_valor,fecha_registro=excluded.fecha_registro",(trabajador_id,vigencia_cond.isoformat(),clp_round(sueldo),grat_tipo,clp_round(grat),afp,salud_tipo,isapre.strip(),salud_modalidad,salud_valor,'Cambio desde ficha',datetime.now().isoformat(timespec='seconds')))
                    conn.commit(); sgci_exito('Ficha y vigencia histórica guardadas.'); st.rerun()

        if edit_row:
            st.markdown('#### Historial de sueldo y condiciones previsionales')
            hc=pd.read_sql_query("SELECT vigente_desde,sueldo_base,afp,salud_tipo,isapre,salud_modalidad,salud_valor FROM nomina_historial_condiciones WHERE trabajador_id=? ORDER BY vigente_desde DESC",conn,params=(edit_row.id,))
            if not hc.empty:
                hc_show=hc.copy(); hc_show['sueldo_base']=hc_show['sueldo_base'].map(money)
                st.dataframe(hc_show,use_container_width=True,hide_index=True)
                pdf_ficha=nomina_pdf('Ficha e historial del trabajador',f'{edit_row.nombre} · RUT {edit_row.rut}',['Vigente desde','Sueldo','AFP','Salud','Isapre','Modalidad','Valor'],[[r.vigente_desde,money(r.sueldo_base),r.afp,r.salud_tipo,r.isapre or '',r.salud_modalidad,r.salud_valor] for r in hc.itertuples()])
                st.download_button('🖨️ PDF ficha / historial',pdf_ficha,f'ficha_{edit_row.rut}.pdf','application/pdf',key='pdf_ficha_nom')

    if nomina_seccion == 'Vacaciones':
        st.subheader("Vacaciones · Control manual")
        st.caption("Los días se asignan y descuentan manualmente. Las solicitudes y sus aprobaciones NO generan descuentos automáticos ni asientos contables.")
        tdf=pd.read_sql_query("SELECT id,rut,nombre FROM nomina_trabajadores ORDER BY activo DESC,nombre",conn)
        if tdf.empty:
            st.info("Primero registra trabajadores.")
        else:
            tm={f"{r.rut} · {r.nombre}":int(r.id) for r in tdf.itertuples()}
            elegido=st.selectbox("Trabajador",list(tm),key="rrhh_vac_trab")
            tid=tm[elegido]
            registros=pd.read_sql_query("SELECT id,fecha,tipo,dias,observacion FROM rrhh_vacaciones_movimientos WHERE trabajador_id=? ORDER BY fecha DESC,id DESC",conn,params=(tid,))
            asignados=float(registros.loc[registros.tipo=="ASIGNACION","dias"].sum()) if not registros.empty else 0
            ajustes=float(registros.loc[registros.tipo=="AJUSTE","dias"].sum()) if not registros.empty else 0
            usados=float(registros.loc[registros.tipo=="DESCUENTO","dias"].sum()) if not registros.empty else 0
            c1,c2,c3=st.columns(3)
            c1.metric("Días asignados / ajustes",f"{asignados+ajustes:g}")
            c2.metric("Días descontados",f"{usados:g}")
            c3.metric("Saldo disponible",f"{asignados+ajustes-usados:g}")
            with st.expander("Registrar asignación o descuento manual",expanded=False):
                with st.form("rrhh_vac_mov_form",clear_on_submit=True):
                    a,b,c=st.columns(3)
                    tipo_mov=a.selectbox("Movimiento",["ASIGNACION","DESCUENTO","AJUSTE"],format_func=lambda x:{"ASIGNACION":"Asignar días","DESCUENTO":"Descontar días","AJUSTE":"Ajuste positivo"}[x])
                    fecha_mov=b.date_input("Fecha del movimiento",value=date.today())
                    dias_mov=c.number_input("Cantidad de días",min_value=0.5,value=1.0,step=0.5)
                    obs_mov=st.text_input("Motivo / referencia")
                    confirmar_mov=st.form_submit_button("Guardar movimiento")
                if confirmar_mov:
                    if tipo_mov=="DESCUENTO" and dias_mov>asignados+ajustes-usados:
                        st.error("El descuento supera el saldo disponible.")
                    else:
                        conn.execute("INSERT INTO rrhh_vacaciones_movimientos(trabajador_id,fecha,tipo,dias,observacion,creado_en) VALUES(?,?,?,?,?,?)",
                                     (tid,fecha_mov.isoformat(),tipo_mov,float(dias_mov),obs_mov,datetime.now().isoformat(timespec="seconds")))
                        conn.commit();sgci_exito("Movimiento de vacaciones registrado.");st.rerun()
            st.markdown("#### Solicitudes")
            with st.expander("➕ Nueva solicitud",expanded=False):
                with st.form("rrhh_vac_sol_form",clear_on_submit=True):
                    a,b=st.columns(2)
                    desde=a.date_input("Desde",value=date.today())
                    hasta=b.date_input("Hasta",value=date.today())
                    dias_sol=st.number_input("Días solicitados (ingreso manual)",min_value=0.5,value=1.0,step=0.5)
                    obs_sol=st.text_area("Observación")
                    crear_sol=st.form_submit_button("Registrar solicitud")
                if crear_sol:
                    if hasta<desde:
                        st.error("La fecha final no puede ser anterior a la inicial.")
                    else:
                        conn.execute("""INSERT INTO rrhh_vacaciones_solicitudes
                            (trabajador_id,fecha_solicitud,desde,hasta,dias_solicitados,estado,observacion,creado_en)
                            VALUES(?,?,?,?,?,'PENDIENTE',?,?)""",
                            (tid,date.today().isoformat(),desde.isoformat(),hasta.isoformat(),float(dias_sol),obs_sol,datetime.now().isoformat(timespec="seconds")))
                        conn.commit();sgci_exito("Solicitud registrada como pendiente.");st.rerun()
            solicitudes=pd.read_sql_query("SELECT id,fecha_solicitud,desde,hasta,dias_solicitados,estado,observacion,revisado_por,fecha_revision FROM rrhh_vacaciones_solicitudes WHERE trabajador_id=? ORDER BY id DESC",conn,params=(tid,))
            if not solicitudes.empty:
                st.dataframe(solicitudes,use_container_width=True,hide_index=True)
                pendientes=solicitudes[solicitudes.estado=="PENDIENTE"]
                if not pendientes.empty:
                    with st.expander("Resolver solicitud pendiente"):
                        opciones={f"#{r.id} · {r.desde} al {r.hasta} · {r.dias_solicitados:g} días":int(r.id) for r in pendientes.itertuples()}
                        elegida=st.selectbox("Solicitud",list(opciones),key="rrhh_vac_sel_sol")
                        decision=st.selectbox("Decisión",["APROBADA","RECHAZADA","ANULADA"])
                        responsable=st.text_input("Responsable de la decisión")
                        obs_revision=st.text_input("Observación de revisión")
                        if st.button("Guardar decisión",key="rrhh_vac_resolver"):
                            sgci_exigir_permiso(conn, 'nomina', 'aprobar', 'Vacaciones')
                            if not responsable.strip(): st.error("Indica quién resuelve.")
                            else:
                                cur=conn.execute("""UPDATE rrhh_vacaciones_solicitudes SET estado=?,revisado_por=?,fecha_revision=?,observacion_revision=?
                                    WHERE id=? AND trabajador_id=? AND estado='PENDIENTE'""",
                                    (decision,responsable.strip(),datetime.now().isoformat(timespec="seconds"),obs_revision,opciones[elegida],tid))
                                conn.commit()
                                if cur.rowcount: sgci_exito("Estado actualizado. Si se utilizaron días, regístralos manualmente como descuento.");st.rerun()
                                else: st.warning("La solicitud ya no está pendiente.")
            st.markdown("#### Historial de días")
            if not registros.empty:
                st.dataframe(registros,use_container_width=True,hide_index=True)
                st.download_button("Exportar historial CSV",registros.to_csv(index=False,sep=";").encode("utf-8-sig"),file_name=f"vacaciones_{tid}.csv",mime="text/csv")
            else: st.info("Aún no hay movimientos de días registrados.")

    if nomina_seccion == 'Anticipos y préstamos':
        trab=pd.read_sql_query("SELECT id,rut,nombre,sueldo_base,anticipo_porcentaje FROM nomina_trabajadores WHERE activo=1 ORDER BY nombre",conn)
        if trab.empty: st.info('Primero crea trabajadores activos.')
        else:
            mapa={f"{r.rut} - {r.nombre}":r for r in trab.itertuples()}
            c1,c2=st.columns(2)
            with c1:
                st.markdown('#### Anticipo quincenal')
                quien=st.selectbox('Trabajador',list(mapa),key='ant_trab'); tr=mapa[quien]
                periodo=st.text_input('Período (AAAA-MM)',value=date.today().strftime('%Y-%m'),key='ant_per')
                sugerido=round(float(tr.sueldo_base or 0)*float(tr.anticipo_porcentaje or 50)/100)
                fecha_ant=st.date_input('Fecha del anticipo',date.today(),key='ant_fecha'); monto_ant=st.number_input('Monto',min_value=0.0,value=float(sugerido),step=10000.0,format='%.0f',key='ant_monto')
                obs_ant=st.text_input('Observación',key='ant_obs')
                if st.button('Registrar anticipo',key='ant_save'):
                    sgci_exigir_permiso(conn, 'nomina', 'crear', 'Anticipos y préstamos')
                    conn.execute("INSERT INTO nomina_anticipos(trabajador_id,periodo,fecha,monto,observacion) VALUES(?,?,?,?,?)",(tr.id,periodo,fecha_ant.isoformat(),monto_ant,obs_ant)); conn.commit(); sgci_exito('Anticipo registrado.'); st.rerun()
            with c2:
                st.markdown('#### Préstamo al trabajador')
                quienp=st.selectbox('Trabajador',list(mapa),key='pre_trab'); tp=mapa[quienp]
                fecha_p=st.date_input('Fecha préstamo',date.today(),key='pre_fecha')
                monto_p=st.number_input('Monto original',min_value=0.0,value=0.0,step=10000.0,format='%.0f',key='pre_monto')
                modalidad=st.radio('Calendario de descuentos',['Mensual (actual)','Fechas específicas / quincenal'],horizontal=True,key='pre_modalidad')
                obs_p=st.text_input('Observación',key='pre_obs')
                fechas_cuotas=[]
                if modalidad=='Mensual (actual)':
                    cuotas=st.number_input('N° cuotas',min_value=1,max_value=120,value=1,key='pre_cuotas')
                    cuota=st.number_input('Cuota mensual',min_value=0.0,value=0.0,step=1000.0,format='%.0f',key='pre_cuota')
                    primera=st.text_input('Primera cuota (AAAA-MM)',value=date.today().strftime('%Y-%m'),key='pre_primera')
                else:
                    cuotas=st.number_input('Número de descuentos',min_value=1,max_value=48,value=4,key='pre_cuotas_fechas')
                    importe_base=int(round(monto_p))//int(cuotas) if cuotas else 0
                    restante=int(round(monto_p))
                    for ix in range(int(cuotas)):
                        colf,colm=st.columns(2)
                        sugerida=date(2026,9,30) if ix==0 else (date(2026,10,15) if ix==1 else (date(2026,10,30) if ix==2 else date(2026,11,15)+timedelta(days=15*(ix-3))))
                        fecha_c=colf.date_input(f'Fecha descuento {ix+1}',value=sugerida,key=f'pre_fecha_c_{ix}')
                        valor_sug=importe_base if ix<int(cuotas)-1 else restante
                        valor_c=colm.number_input(f'Monto descuento {ix+1}',min_value=0,value=max(0,valor_sug),step=1000,key=f'pre_monto_c_{ix}')
                        fechas_cuotas.append((fecha_c.isoformat(),int(valor_c)))
                        restante-=int(valor_c)
                    st.caption(f'Total programado: {money(sum(x[1] for x in fechas_cuotas))} / Préstamo: {money(monto_p)}')
                if st.button('Registrar préstamo',key='pre_save'):
                    sgci_exigir_permiso(conn, 'nomina', 'crear', 'Anticipos y préstamos')
                    if monto_p<=0:
                        st.error('El préstamo debe ser mayor que cero.')
                    elif modalidad=='Fechas específicas / quincenal' and (sum(x[1] for x in fechas_cuotas)!=int(round(monto_p)) or any(x[1]<=0 for x in fechas_cuotas) or len(set(x[0] for x in fechas_cuotas))!=len(fechas_cuotas) or any(x[0]<fecha_p.isoformat() for x in fechas_cuotas)):
                        st.error('Las cuotas deben sumar exactamente el préstamo, tener fechas distintas posteriores a la entrega y montos positivos.')
                    elif modalidad=='Mensual (actual)' and not re.fullmatch(r'\\d{4}-(0[1-9]|1[0-2])',primera):
                        st.error('Primera cuota debe tener formato AAAA-MM.')
                    else:
                        if modalidad=='Mensual (actual)':
                            cuota_final=cuota or (monto_p/cuotas if cuotas else monto_p)
                            primera_final=primera
                        else:
                            cuota_final=0
                            primera_final=min(f[:7] for f,_ in fechas_cuotas)
                        try:
                            cursor=conn.execute("INSERT INTO nomina_prestamos(trabajador_id,fecha,monto_original,numero_cuotas,cuota,primera_cuota,saldo,observacion) VALUES(?,?,?,?,?,?,?,?)",(tp.id,fecha_p.isoformat(),monto_p,int(cuotas),cuota_final,primera_final,monto_p,obs_p))
                            if modalidad=='Fechas específicas / quincenal':
                                conn.executemany("INSERT INTO nomina_prestamo_cuotas_programadas(prestamo_id,fecha,monto) VALUES(?,?,?)",[(cursor.lastrowid,f,v) for f,v in fechas_cuotas])
                            conn.commit()
                            sgci_exito('Préstamo y calendario registrados.'); st.rerun()
                        except Exception:
                            conn.rollback()
                            raise
            st.divider(); st.markdown('#### Movimientos registrados')
            ants=pd.read_sql_query("SELECT a.id,t.nombre,a.periodo,a.fecha,a.monto,a.contabilizado,a.asiento_id FROM nomina_anticipos a JOIN nomina_trabajadores t ON t.id=a.trabajador_id WHERE COALESCE(a.anulado,0)=0 ORDER BY a.id DESC",conn)
            pres=pd.read_sql_query("SELECT p.id,t.nombre,p.fecha,p.monto_original,p.numero_cuotas,p.cuota,p.saldo,p.estado,p.contabilizado,p.asiento_id FROM nomina_prestamos p JOIN nomina_trabajadores t ON t.id=p.trabajador_id ORDER BY p.id DESC",conn)
            st.dataframe(formatear_montos_df(ants),use_container_width=True,hide_index=True); st.dataframe(formatear_montos_df(pres),use_container_width=True,hide_index=True)
            if not ants.empty:
                pdf_ant=nomina_pdf('Anticipos de remuneraciones','SGCI',['ID','Trabajador','Período','Fecha','Monto','Contabilizado','Asiento'],[[r.id,r.nombre,r.periodo,r.fecha,money(r.monto),'Sí' if r.contabilizado else 'No',r.asiento_id or ''] for r in ants.itertuples()]); st.download_button('🖨️ PDF anticipos',pdf_ant,'anticipos_remuneraciones.pdf','application/pdf',key='pdf_anticipos')
            if not pres.empty:
                pdf_pre=nomina_pdf('Préstamos a trabajadores','SGCI',['ID','Trabajador','Fecha','Monto','Cuotas','Cuota','Saldo','Estado'],[[r.id,r.nombre,r.fecha,money(r.monto_original),r.numero_cuotas,money(r.cuota),money(r.saldo),r.estado] for r in pres.itertuples()]); st.download_button('🖨️ PDF préstamos',pdf_pre,'prestamos_trabajadores.pdf','application/pdf',key='pdf_prestamos')
            st.markdown('#### Contabilizar entrega de anticipo/préstamo')
            bancos=pd.read_sql_query("SELECT id,nombre,numero_cuenta,cuenta_contable FROM bancos WHERE activo=1 AND cuenta_contable IS NOT NULL",conn)
            pendientes=[]
            for r in ants[ants.contabilizado==0].itertuples(): pendientes.append((f"Anticipo #{r.id} · {r.nombre} · {money(r.monto)}",'nomina_anticipos',r.id,r.fecha,r.monto,'1.1.07.01'))
            for r in pres[pres.contabilizado==0].itertuples(): pendientes.append((f"Préstamo #{r.id} · {r.nombre} · {money(r.monto_original)}",'nomina_prestamos',r.id,r.fecha,r.monto_original,'1.1.07.02'))
            if pendientes and not bancos.empty:
                op=st.selectbox('Movimiento pendiente',[x[0] for x in pendientes]); mov=next(x for x in pendientes if x[0]==op)
                bm={f"{r.nombre} - {r.numero_cuenta} ({r.cuenta_contable})":r for r in bancos.itertuples()}; bl=st.selectbox('Banco utilizado',list(bm)); br=bm[bl]
                if st.button('Contabilizar salida bancaria',type='primary'):
                    sgci_exigir_permiso(conn, 'nomina', 'contabilizar', 'Contabilización')
                    asi=nomina_registrar_pago_activo(conn,mov[1],mov[2],mov[3],mov[4],mov[5],br.cuenta_contable,mov[0]); sgci_exito(f'Asiento N° {asi} generado.'); st.rerun()
            elif pendientes: st.warning('Hay movimientos pendientes, pero no existe una cuenta bancaria activa vinculada contablemente.')

    if nomina_seccion == 'Liquidación mensual':
        st.subheader('Liquidación mensual')
        periodo=st.text_input('Período a liquidar (AAAA-MM)',value=date.today().strftime('%Y-%m'),key='liq_periodo')
        trab=pd.read_sql_query("SELECT * FROM nomina_trabajadores WHERE activo=1 ORDER BY nombre",conn)
        if trab.empty: st.info('No hay trabajadores activos.')
        else:
            labels={f"{r.rut} - {r.nombre}":r for r in trab.itertuples()}; lab=st.selectbox('Trabajador',list(labels),key='liq_trab'); tr=labels[lab]
            existente=conn.execute("SELECT * FROM nomina_liquidaciones WHERE periodo=? AND trabajador_id=?",(periodo,tr.id)).fetchone(); ex=dict(existente) if existente else {}
            fecha_periodo=f'{periodo}-01'
            hist_cond=conn.execute("SELECT * FROM nomina_historial_condiciones WHERE trabajador_id=? AND vigente_desde<=? ORDER BY vigente_desde DESC LIMIT 1",(tr.id,fecha_periodo)).fetchone()
            cond=dict(hist_cond) if hist_cond else dict(tr._asdict())
            st.caption('La liquidación toma automáticamente la última condición vigente al inicio del período y la congela históricamente.')
            c1,c2,c3=st.columns(3)
            dias=c1.number_input('Días trabajados',min_value=0.0,max_value=30.0,value=float(ex.get('dias_trabajados',30)),step=1.0)
            sueldo_base=c2.number_input('Sueldo base',min_value=0.0,value=float(ex.get('sueldo_base',cond.get('sueldo_base',tr.sueldo_base) or 0)),step=10000.0,format='%.0f')
            sueldo_periodo=c3.number_input('Sueldo del período',min_value=0.0,value=float(ex.get('sueldo_periodo',clp_round((cond.get('sueldo_base',tr.sueldo_base) or 0)*dias/30))),step=1000.0,format='%.0f')
            grat=c1.number_input('Gratificación',min_value=0.0,value=float(ex.get('gratificacion',cond.get('gratificacion_valor',tr.gratificacion_valor) or 0)),step=1000.0,format='%.0f')
            horas=c2.number_input('Horas extras ($)',min_value=0.0,value=float(ex.get('horas_extras',0)),step=1000.0,format='%.0f')
            bonos=c3.number_input('Bonos imponibles',min_value=0.0,value=float(ex.get('bonos_imponibles',0)),step=1000.0,format='%.0f')
            otros_imp=c1.number_input('Otros imponibles',min_value=0.0,value=float(ex.get('otros_imponibles',0)),step=1000.0,format='%.0f')
            bono_noimp=c2.number_input('Bono no imponible',min_value=0.0,value=float(ex.get('bono_no_imponible',0)),step=1000.0,format='%.0f',
                                       help='Haber no imponible: aumenta el total de haberes, pero no integra la base para AFP, AFC ni Salud.')
            noimp=c3.number_input('Otras asignaciones no imponibles',min_value=0.0,value=float(ex.get('asignacion_no_imponible',0)),step=1000.0,format='%.0f',
                                  help='Ej.: colación, movilización u otra asignación no imponible que corresponda.')
            otros_noimp=c1.number_input('Otros haberes no imponibles',min_value=0.0,value=float(ex.get('otros_no_imponibles',0)),step=1000.0,format='%.0f')
            total_imp=clp_round(sueldo_periodo+grat+horas+bonos+otros_imp)
            total_noimp=clp_round(bono_noimp+noimp+otros_noimp)
            afp_vig=cond.get('afp',tr.afp); com=conn.execute("SELECT comision FROM nomina_parametros_afp WHERE afp=?",(afp_vig,)).fetchone(); comision=float(com[0] if com else 0)
            st.markdown('##### Descuentos')
            d1,d2,d3=st.columns(3)
            afp_auto=clp_round(total_imp*(10+comision)/100); usar_afp_manual=d1.checkbox(f'AFP manual (auto {money(afp_auto)})',value=False); afp_manual=d1.number_input('AFP a descontar',min_value=0.0,value=float(ex.get('afp_descuento',afp_auto)),step=1000.0,format='%.0f',disabled=not usar_afp_manual)
            salud_tipo_vig=cond.get('salud_tipo',tr.salud_tipo) or 'Fonasa'; mod=cond.get('salud_modalidad',tr.salud_modalidad) or '7% legal'; sval=float(cond.get('salud_valor',tr.salud_valor) or 7); uf_row=conn.execute("SELECT valor_uf FROM nomina_parametros_mensuales WHERE periodo=?",(periodo,)).fetchone(); uf_valor=float(uf_row[0] if uf_row else ex.get('uf_valor',0) or 0); legal_salud=total_imp*0.07; plan_salud=(sval*uf_valor if mod=='Plan en UF' else (sval if mod=='Monto pactado en pesos' else total_imp*sval/100)); salud_auto=clp_round(legal_salud if salud_tipo_vig=='Fonasa' else max(legal_salud,plan_salud))
            usar_salud_manual=d2.checkbox(f'Salud manual (auto {money(salud_auto)})',value=False); salud_manual=d2.number_input('Salud a descontar',min_value=0.0,value=float(ex.get('salud_descuento',salud_auto)),step=1000.0,format='%.0f',disabled=not usar_salud_manual)
            salud_legal=clp_round(legal_salud)
            salud_final=clp_round(salud_manual if usar_salud_manual else salud_auto)
            salud_adicional=max(0, salud_final-salud_legal) if salud_tipo_vig=='Isapre' else 0
            d2.caption(f'7% legal: {money(salud_legal)}' + (f' · Adicional Isapre: {money(salud_adicional)}' if salud_tipo_vig=='Isapre' else ''))
            if salud_tipo_vig=='Isapre' and mod=='Plan en UF': d2.caption(f'Plan: {sval:.2f} UF · equivalente {money(plan_salud)} · UF usada {uf_valor:,.2f}')
            afc=d3.number_input('AFC trabajador',min_value=0.0,value=float(ex.get('afc_descuento',0)),step=1000.0,format='%.0f',help='Editable para cuadrar con Previred.')
            impuesto=d1.number_input('Impuesto Único',min_value=0.0,value=float(ex.get('impuesto_unico',0)),step=1000.0,format='%.0f')
            prestamos=pd.read_sql_query("SELECT * FROM nomina_prestamos WHERE trabajador_id=? AND estado='VIGENTE' AND saldo>0 AND primera_cuota<=?",conn,params=(tr.id,periodo))
            pre_sug=0.0
            for pp in prestamos.itertuples():
                programadas=conn.execute("SELECT COUNT(*) FROM nomina_prestamo_cuotas_programadas WHERE prestamo_id=?",(pp.id,)).fetchone()[0]
                if programadas:
                    pre_sug+=float(conn.execute("SELECT COALESCE(SUM(monto),0) FROM nomina_prestamo_cuotas_programadas WHERE prestamo_id=? AND substr(fecha,1,7)=?",(pp.id,periodo)).fetchone()[0])
                else:
                    pre_sug+=float(pp.cuota or 0)
            if not prestamos.empty:
                st.caption('Cuotas programadas del mes: '+money(pre_sug)+'. Las fechas quincenales se consolidan en la liquidación mensual; no se registran descuentos bancarios separados automáticamente.')
            pre_desc=d2.number_input('Descuento préstamos',min_value=0.0,value=float(ex.get('prestamo_descuento',pre_sug)),step=1000.0,format='%.0f')
            otros_desc=d3.number_input('Otros descuentos',min_value=0.0,value=float(ex.get('otros_descuentos',0)),step=1000.0,format='%.0f')
            ant=conn.execute("SELECT COALESCE(SUM(monto),0) FROM nomina_anticipos WHERE trabajador_id=? AND periodo=? AND COALESCE(anulado,0)=0",(tr.id,periodo)).fetchone()[0] or 0
            calc=nomina_calcular(total_imp,total_noimp,comision,salud_tipo_vig,mod,sval,uf_valor,afc,impuesto,pre_desc,otros_desc,ant,afp_manual if usar_afp_manual else None,salud_manual if usar_salud_manual else None)
            a,b,c,d=st.columns(4); a.metric('Total imponible',money(total_imp)); b.metric('Total no imponible',money(total_noimp)); c.metric('Total haberes',money(total_imp+total_noimp)); d.metric('Líquido período',money(calc['liquido']))
            e,f,g=st.columns(3); e.metric('Total descuentos',money(calc['total_desc'])); f.metric('Anticipo día 15',money(ant)); g.metric('Saldo fin de mes',money(calc['saldo']))
            st.info(f"AFP {afp_vig}: 10% + comisión {comision:.2f}% | Salud: {salud_tipo_vig} · {mod} | Anticipo registrado: {money(ant)}")
            obs=st.text_area('Observaciones',value=ex.get('observacion','') or '')
            if st.button('💾 Guardar / recalcular liquidación',type='primary'):
                sgci_exigir_permiso(conn, 'nomina', 'editar', 'Liquidación mensual')
                vals=(periodo,tr.id,dias,sueldo_base,sueldo_periodo,grat,horas,bonos,otros_imp,bono_noimp,noimp,otros_noimp,total_imp,total_noimp,clp_round(total_imp+total_noimp),afp_vig,comision,calc['afp'],salud_tipo_vig,mod,sval,calc['salud'],afc,impuesto,pre_desc,otros_desc,calc['total_desc'],calc['liquido'],ant,calc['saldo'],uf_valor,calc['salud_plan_pesos'],'CALCULADO',obs)
                conn.execute("""INSERT INTO nomina_liquidaciones(periodo,trabajador_id,dias_trabajados,sueldo_base,sueldo_periodo,gratificacion,horas_extras,bonos_imponibles,otros_imponibles,bono_no_imponible,asignacion_no_imponible,otros_no_imponibles,total_imponible,total_no_imponible,total_haberes,afp_nombre,afp_comision,afp_descuento,salud_tipo,salud_modalidad,salud_valor,salud_descuento,afc_descuento,impuesto_unico,prestamo_descuento,otros_descuentos,total_descuentos,liquido_periodo,anticipo,saldo_pagar,uf_valor,salud_plan_pesos,estado,observacion) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(periodo,trabajador_id) DO UPDATE SET dias_trabajados=excluded.dias_trabajados,sueldo_base=excluded.sueldo_base,sueldo_periodo=excluded.sueldo_periodo,gratificacion=excluded.gratificacion,horas_extras=excluded.horas_extras,bonos_imponibles=excluded.bonos_imponibles,otros_imponibles=excluded.otros_imponibles,bono_no_imponible=excluded.bono_no_imponible,asignacion_no_imponible=excluded.asignacion_no_imponible,otros_no_imponibles=excluded.otros_no_imponibles,total_imponible=excluded.total_imponible,total_no_imponible=excluded.total_no_imponible,total_haberes=excluded.total_haberes,afp_nombre=excluded.afp_nombre,afp_comision=excluded.afp_comision,afp_descuento=excluded.afp_descuento,salud_tipo=excluded.salud_tipo,salud_modalidad=excluded.salud_modalidad,salud_valor=excluded.salud_valor,salud_descuento=excluded.salud_descuento,afc_descuento=excluded.afc_descuento,impuesto_unico=excluded.impuesto_unico,prestamo_descuento=excluded.prestamo_descuento,otros_descuentos=excluded.otros_descuentos,total_descuentos=excluded.total_descuentos,liquido_periodo=excluded.liquido_periodo,anticipo=excluded.anticipo,saldo_pagar=excluded.saldo_pagar,uf_valor=excluded.uf_valor,salud_plan_pesos=excluded.salud_plan_pesos,estado=CASE WHEN nomina_liquidaciones.estado='CONTABILIZADO' THEN nomina_liquidaciones.estado ELSE 'CALCULADO' END,observacion=excluded.observacion""",vals)
                conn.execute("INSERT OR IGNORE INTO nomina_periodos(periodo) VALUES(?)",(periodo,)); conn.commit(); sgci_exito('Liquidación guardada.'); st.rerun()

    if nomina_seccion == 'Resumen y reportes':
        # Etapa 6.4: este reporte agrega datos de TODOS los trabajadores.
        # No debe abrirse con permisos individuales de lectura o exportación.
        # Los informes de empleados requieren una vista separada filtrada por registro.
        if not sgci_es_propietario():
            st.error('Acceso restringido: los reportes globales de Nómina son exclusivos del administrador.')
            st.stop()
        st.subheader('Resumen de nómina y reportes')
        periodos=pd.read_sql_query("SELECT DISTINCT periodo FROM nomina_liquidaciones ORDER BY periodo DESC",conn)['periodo'].tolist()
        if not periodos: st.info('Aún no existen liquidaciones.')
        else:
            per=st.selectbox('Período',periodos,key='rep_per')
            df=pd.read_sql_query("""SELECT l.*,t.rut,t.nombre,t.cargo FROM nomina_liquidaciones l JOIN nomina_trabajadores t ON t.id=l.trabajador_id WHERE l.periodo=? ORDER BY t.nombre""",conn,params=(per,))
            cols=['rut','nombre','sueldo_periodo','gratificacion','bono_no_imponible','asignacion_no_imponible','otros_no_imponibles','total_imponible','total_no_imponible','afp_descuento','salud_descuento','afc_descuento','impuesto_unico','prestamo_descuento','anticipo','saldo_pagar']
            vista=df[cols].copy(); st.dataframe(formatear_montos_df(vista),use_container_width=True,hide_index=True)
            st.download_button('📥 Exportar resumen CSV',vista.to_csv(index=False,sep=';').encode('utf-8-sig'),f'nomina_{per}.csv','text/csv')
            headers=['RUT','Trabajador','Sueldo','Gratif.','Bono no impon.','Otras asig. no impon.','Otros no impon.','Imponible','No impon.','AFP','Salud','AFC','Impuesto','Préstamo','Anticipo','Saldo final']
            filas=[]
            for r in vista.itertuples(index=False): filas.append([r[0],r[1]]+[money(x) for x in r[2:]])
            tot=['','TOTALES']+[money(vista[c].sum()) for c in cols[2:]]
            pdf=nomina_pdf(f'Resumen de Nómina - {per}','SGCI - Sistema de Gestión Contable Integral',headers,filas,tot)
            st.download_button('🖨️ PDF resumen de nómina',pdf,f'resumen_nomina_{per}.pdf','application/pdf')
            st.markdown('#### Liquidación individual imprimible')
            lm={f"{r.rut} - {r.nombre}":r for r in df.itertuples()}; ls=st.selectbox('Trabajador para reporte',list(lm),key='rep_trab'); rr=lm[ls]
            detalle=[['Sueldo período',money(rr.sueldo_periodo)],['Gratificación',money(rr.gratificacion)],['Horas extras',money(rr.horas_extras)],['Bonos imponibles',money(rr.bonos_imponibles)],['Bono no imponible',money(getattr(rr,'bono_no_imponible',0))],['Otras asignaciones no imponibles',money(rr.asignacion_no_imponible)],['Otros no imponibles',money(rr.otros_no_imponibles)],['Total imponible',money(rr.total_imponible)],['Total no imponible',money(rr.total_no_imponible)],['AFP',money(rr.afp_descuento)],['Salud 7% legal',money(clp_round(rr.total_imponible*0.07))],['Adicional Isapre',money(max(0,clp_round(rr.salud_descuento)-clp_round(rr.total_imponible*0.07)) if rr.salud_tipo=='Isapre' else 0)],['Total Salud',money(rr.salud_descuento)],['Plan salud equivalente',money(getattr(rr,'salud_plan_pesos',0))],['UF utilizada',f"{float(getattr(rr,'uf_valor',0) or 0):,.2f}"],['AFC',money(rr.afc_descuento)],['Impuesto Único',money(rr.impuesto_unico)],['Préstamo',money(rr.prestamo_descuento)],['Otros descuentos',money(rr.otros_descuentos)],['Líquido período',money(rr.liquido_periodo)],['Anticipo quincenal',money(rr.anticipo)],['SALDO A PAGAR',money(rr.saldo_pagar)]]
            pdfi=rrhh_pdf_liquidacion(conn,rr)
            st.download_button('🖨️ PDF liquidación individual',pdfi,f'liquidacion_{rr.rut}_{per}.pdf','application/pdf')
            st.markdown('#### Historial del trabajador')
            hist=pd.read_sql_query("SELECT periodo,total_haberes,total_descuentos,liquido_periodo,anticipo,saldo_pagar,estado FROM nomina_liquidaciones WHERE trabajador_id=? ORDER BY periodo DESC",conn,params=(rr.trabajador_id,)); st.dataframe(formatear_montos_df(hist),use_container_width=True,hide_index=True)
            pdfh=nomina_pdf('Historial de Remuneraciones',f'{rr.nombre} · RUT {rr.rut}',['Período','Haberes','Descuentos','Líquido','Anticipo','Saldo final','Estado'],[[x.periodo,money(x.total_haberes),money(x.total_descuentos),money(x.liquido_periodo),money(x.anticipo),money(x.saldo_pagar),x.estado] for x in hist.itertuples()])
            st.download_button('🖨️ PDF historial trabajador',pdfh,f'historial_nomina_{rr.rut}.pdf','application/pdf')

    if nomina_seccion == 'Parámetros':
        st.subheader('Parámetros previsionales')
        st.caption('Las comisiones AFP se guardan como parámetros editables para no depender de cambios en el código. Verifica vigencia antes de cerrar cada nómina.')
        afpdf=pd.read_sql_query("SELECT afp,comision,vigente_desde,activo FROM nomina_parametros_afp ORDER BY afp",conn); st.dataframe(afpdf,use_container_width=True,hide_index=True)
        amap={r.afp:r for r in afpdf.itertuples()}; aa=st.selectbox('AFP a modificar',list(amap)); ar=amap[aa]; nueva=st.number_input('Comisión %',min_value=0.0,max_value=10.0,value=float(ar.comision),step=.01); vig=st.text_input('Vigente desde',value=ar.vigente_desde or '')
        if st.button('Guardar parámetro AFP'):
            sgci_exigir_permiso(conn, 'nomina', 'editar', 'Parámetros')
            conn.execute("UPDATE nomina_parametros_afp SET comision=?,vigente_desde=? WHERE afp=?",(nueva,vig,aa)); conn.commit(); sgci_exito('Parámetro actualizado.'); st.rerun()
        st.info('Salud: Fonasa usa 7% legal. Isapre admite 7%, porcentaje pactado, plan en UF o monto pactado en pesos; la liquidación conserva el valor UF utilizado y permite ajuste manual.')
        st.markdown('#### Valor UF por período')
        pu=st.text_input('Período UF (AAAA-MM)',value=date.today().strftime('%Y-%m'),key='uf_per'); vu=st.number_input('Valor UF del período',min_value=0.0,value=0.0,step=1.0,key='uf_val')
        if st.button('Guardar valor UF',key='uf_save'):
            sgci_exigir_permiso(conn, 'nomina', 'editar', 'Parámetros')
            conn.execute("INSERT INTO nomina_parametros_mensuales(periodo,valor_uf) VALUES(?,?) ON CONFLICT(periodo) DO UPDATE SET valor_uf=excluded.valor_uf",(pu,vu)); conn.commit(); sgci_exito('UF guardada para el período.'); st.rerun()
        ufdf=pd.read_sql_query("SELECT periodo,valor_uf FROM nomina_parametros_mensuales ORDER BY periodo DESC",conn)
        if not ufdf.empty: st.dataframe(ufdf,use_container_width=True,hide_index=True)

    if nomina_seccion == 'Contabilización':
        st.subheader('Contabilización de nómina')
        periodos=pd.read_sql_query("SELECT periodo,estado,fecha_cierre,asiento_id FROM nomina_periodos ORDER BY periodo DESC",conn)
        st.dataframe(periodos,use_container_width=True,hide_index=True)
        candidatos=pd.read_sql_query("SELECT DISTINCT periodo FROM nomina_liquidaciones WHERE estado<>'CONTABILIZADO' ORDER BY periodo DESC",conn)['periodo'].tolist()
        if candidatos:
            per=st.selectbox('Período a contabilizar',candidatos,key='cont_nom_per')
            df=pd.read_sql_query("SELECT COUNT(*) n,COALESCE(SUM(total_haberes),0) haberes,COALESCE(SUM(total_descuentos),0) descuentos,COALESCE(SUM(anticipo),0) anticipos,COALESCE(SUM(saldo_pagar),0) saldo FROM nomina_liquidaciones WHERE periodo=?",conn,params=(per,)).iloc[0]
            a,b,c,d=st.columns(4); a.metric('Trabajadores',int(df.n)); b.metric('Haberes',money(df.haberes)); c.metric('Anticipos',money(df.anticipos)); d.metric('Saldo fin de mes',money(df.saldo))
            st.warning('Al contabilizar, el período queda marcado como CONTABILIZADO. Revisa primero el resumen y las liquidaciones.')
            try:
                fecha_previa, partidas, total_debe, total_haber=nomina_vista_previa(conn,per)
                st.markdown('#### Vista previa del asiento contable (sin guardar)')
                st.caption(f'Fecha del asiento: {fecha_previa}. Los anticipos se compensan como activo; no se registra un nuevo movimiento de Banco.')
                st.dataframe(pd.DataFrame(partidas),use_container_width=True,hide_index=True)
                c1,c2,c3=st.columns(3)
                c1.metric('Debe',money(total_debe)); c2.metric('Haber',money(total_haber)); c3.metric('Diferencia',money(total_debe-total_haber))
                if total_debe==total_haber:
                    st.success('Vista previa cuadrada. Revisa las cuentas antes de confirmar.')
                else:
                    st.error('Asiento descuadrado. No se permite contabilizar.')
                st.info('Las cotizaciones de cargo del empleador no están incluidas en este asiento y requieren su registro separado. Los anticipos deben imputarse exclusivamente al período que corresponda.')
                confirma=st.checkbox('Revisé las cuentas y los montos de la vista previa.',key=f'confirmar_nomina_{per}')
                if st.button('🧾 Contabilizar nómina',type='primary',disabled=(not confirma or total_debe!=total_haber)):
                    sgci_exigir_permiso(conn, 'nomina', 'contabilizar', 'Contabilización')
                    try:
                        asi=nomina_contabilizar_periodo(conn,per)
                        registrar_auditoria(conn,'CONTABILIZAR NÓMINA',f'{per} asiento {asi}')
                        sgci_exito(f'Nómina {per} contabilizada correctamente. Asiento N° {asi}.')
                        st.rerun()
                    except Exception as e: st.error(f'No se contabilizó la nómina: {e}')
            except Exception as e:
                st.error(f'No se puede preparar el asiento: {e}')
        else: st.info('No hay períodos pendientes de contabilización.')


# ESTADOS FINANCIEROS
# ============================================================

elif menu == "📊 Estados Financieros":
    st.title("📊 Estados Financieros")
    c1,c2,c3=st.columns(3)
    desde=c1.date_input("Desde", date(date.today().year,1,1), key="ef_desde")
    hasta=c2.date_input("Hasta", date.today(), key="ef_hasta")
    modo=c3.selectbox("Informe",["Estado de Resultados","Estado de Situación Financiera","Balance de Comprobación"])
    ds=desde.strftime("%Y-%m-%d"); hs=hasta.strftime("%Y-%m-%d")
    if modo=="Estado de Resultados":
        df=estado_resultados(conn,hs,ds)
        if df.empty: st.info("No hay movimientos para el período seleccionado.")
        else:
            ingresos=df[df.tipo=="Ingresos"]["saldo"].sum(); gastos=df[df.tipo=="Gastos"]["saldo"].sum(); resultado=ingresos-gastos
            a,b,c=st.columns(3); a.metric("Ingresos",money(ingresos)); b.metric("Gastos",money(gastos)); c.metric("Resultado",money(resultado))
            mostrar_ef=df[["codigo","nombre","saldo"]].rename(columns={"codigo":"Código","nombre":"Cuenta","saldo":"Saldo"})
            st.dataframe(mostrar_ef,use_container_width=True,hide_index=True)
            pdf_ef=nomina_pdf("Estado de Resultados",f"Desde {ds} hasta {hs}",["Código","Cuenta","Saldo"],[[r.Código,r.Cuenta,money(r.Saldo)] for r in mostrar_ef.itertuples(index=False)],["","RESULTADO",money(resultado)])
            st.download_button("🖨️ Imprimir / PDF Estado de Resultados",pdf_ef,f"estado_resultados_{hs}.pdf","application/pdf",key="pdf_er")
            sgci_exito(f"Resultado del período: {money(resultado)}" if resultado>=0 else f"Resultado del período: {money(resultado)} (pérdida)")
    elif modo=="Estado de Situación Financiera":
        df=estado_situacion(conn,hs)
        if df.empty: st.info("No hay movimientos para la fecha seleccionada.")
        else:
            activos=df[df.tipo=="Activo"]["saldo"].sum(); pasivos=-df[df.tipo=="Pasivo"]["saldo"].sum(); patrimonio=-df[df.tipo=="Patrimonio"]["saldo"].sum()
            a,b,c=st.columns(3); a.metric("Activos",money(activos)); b.metric("Pasivos",money(pasivos)); c.metric("Patrimonio",money(patrimonio))
            mostrar_esf=df[["codigo","nombre","tipo","saldo"]].rename(columns={"codigo":"Código","nombre":"Cuenta","tipo":"Tipo","saldo":"Saldo"})
            st.dataframe(mostrar_esf,use_container_width=True,hide_index=True)
            pdf_esf=nomina_pdf("Estado de Situación Financiera",f"Al {hs}",["Código","Cuenta","Tipo","Saldo"],[[r.Código,r.Cuenta,r.Tipo,money(r.Saldo)] for r in mostrar_esf.itertuples(index=False)],["","TOTAL ACTIVO / P+P","",f"{money(activos)} / {money(pasivos+patrimonio)}"] )
            st.download_button("🖨️ Imprimir / PDF Estado de Situación",pdf_esf,f"estado_situacion_{hs}.pdf","application/pdf",key="pdf_esf")
            st.info(f"Control: Activo = {money(activos)} | Pasivo + Patrimonio = {money(pasivos+patrimonio)} | Diferencia = {money(activos-pasivos-patrimonio)}")
    else:
        df=resumen_financiero(conn,hs)
        if df.empty: st.info("No hay movimientos.")
        else:
            df["saldo_deudor"]=df["debe"]-df["haber"].clip(upper=df["debe"])
            df["saldo_acreedor"]=df["haber"]-df["debe"].clip(upper=df["haber"])
            mostrar_bc=df[["codigo","nombre","debe","haber","saldo"]].rename(columns={"codigo":"Código","nombre":"Cuenta","debe":"Debe","haber":"Haber","saldo":"Saldo"})
            st.dataframe(mostrar_bc,use_container_width=True,hide_index=True)
            pdf_bc=nomina_pdf("Balance de Comprobación",f"Al {hs}",["Código","Cuenta","Debe","Haber","Saldo"],[[r.Código,r.Cuenta,money(r.Debe),money(r.Haber),money(r.Saldo)] for r in mostrar_bc.itertuples(index=False)],["","TOTALES",money(df.debe.sum()),money(df.haber.sum()),money(df.saldo.sum())])
            st.download_button("🖨️ Imprimir / PDF Balance",pdf_bc,f"balance_comprobacion_{hs}.pdf","application/pdf",key="pdf_bc_ef")
            sgci_exito("🟢 Balance cuadrado" if abs(df.debe.sum()-df.haber.sum())<0.01 else f"🔴 Diferencia: {money(df.debe.sum()-df.haber.sum())}")


# ============================================================
# BANCOS Y CARTOLAS
# ============================================================

elif menu == "🏦 Bancos y Cartolas":
    st.title("🏦 Banco")
    st.caption("Gestión bancaria, cartolas, movimientos y conciliación bancaria.")
    # La navegación se guarda en session_state: st.tabs vuelve a la primera pestaña
    # en cada rerun (selectbox, radio, botones, conciliaciones, etc.).
    banco_secciones = ["Cuentas bancarias", "Cargar cartola", "Movimiento manual", "Conciliación", "Operaciones manuales", "Movimientos"]
    if st.session_state.get("sgci_banco_seccion") not in banco_secciones:
        st.session_state["sgci_banco_seccion"] = "Conciliación"
    banco_seccion = st.selectbox(
        "Sección bancaria", banco_secciones,
        key="sgci_banco_seccion", label_visibility="collapsed"
    )

    if banco_seccion == "Cuentas bancarias":
        df = pd.read_sql_query("SELECT b.id AS ID,b.nombre AS Banco,b.numero_cuenta AS Cuenta,b.tipo AS Tipo,b.moneda AS Moneda,b.cuenta_contable AS Cuenta_Contable,b.saldo_inicial AS Saldo_Inicial FROM bancos b WHERE activo=1 ORDER BY nombre", conn)
        if not df.empty:
            st.dataframe(formatear_montos_df(df), use_container_width=True, hide_index=True)
        with st.form("nuevo_banco"):
            a,b,c = st.columns(3)
            nombre = a.text_input("Banco")
            numero_cuenta = b.text_input("N° cuenta")
            tipo = c.selectbox("Tipo", ["Cuenta corriente","Cuenta vista","Cuenta empresa","Otra"])
            cuentas = cuentas_imputables(conn)
            mapa = dict(zip(cuentas.etiqueta, cuentas.codigo))
            cuenta = c.selectbox("Cuenta contable bancaria", list(mapa.keys())) if mapa else ""
            saldo = st.number_input("Saldo inicial", value=0.0, step=1000.0,format='%.0f')
            if st.form_submit_button("Guardar cuenta bancaria"):
                sgci_exigir_permiso(conn, 'banco', 'crear', 'Bancos y cartolas')
                conn.execute("INSERT INTO bancos(nombre,numero_cuenta,tipo,cuenta_contable,saldo_inicial) VALUES(?,?,?,?,?)", (nombre,numero_cuenta,tipo,mapa.get(cuenta),saldo))
                conn.commit(); registrar_auditoria(conn,"NUEVO BANCO",nombre); sgci_exito("Cuenta bancaria creada.")

        st.divider()
        st.subheader("Vinculación contable de cuentas bancarias")
        st.caption("Cada cuenta bancaria debe apuntar a su cuenta del plan contable. Los cargos de cartola acreditarán esta cuenta; no Caja.")
        bancos_cfg = pd.read_sql_query("SELECT id,nombre,numero_cuenta,cuenta_contable FROM bancos WHERE activo=1 ORDER BY nombre", conn)
        if not bancos_cfg.empty and mapa:
            banco_cfg_label = st.selectbox("Cuenta bancaria a configurar", [f"{r.id} - {r.nombre} - {r.numero_cuenta}" for r in bancos_cfg.itertuples()], key="cfg_banco_sel")
            banco_cfg_id = int(banco_cfg_label.split(" - ")[0])
            actual = bancos_cfg.loc[bancos_cfg["id"]==banco_cfg_id,"cuenta_contable"].iloc[0]
            etiquetas = list(mapa.keys())
            idx_actual = next((i for i,e in enumerate(etiquetas) if mapa[e] == actual), 0)
            nueva_etiqueta = st.selectbox("Cuenta contable vinculada", etiquetas, index=idx_actual, key="cfg_banco_cuenta")
            if actual:
                st.info(f"Actualmente vinculada a: {actual} - {Plan(conn).todos.get(actual, actual)}")
            if st.button("💾 Guardar vinculación bancaria", key="guardar_cfg_banco"):
                sgci_exigir_permiso(conn, 'banco', 'editar', 'Bancos y cartolas')
                conn.execute("UPDATE bancos SET cuenta_contable=? WHERE id=?", (mapa[nueva_etiqueta], banco_cfg_id))
                conn.commit(); registrar_auditoria(conn,"VINCULACIÓN BANCO",f"Banco {banco_cfg_id} -> {mapa[nueva_etiqueta]}")
                sgci_exito("Vinculación actualizada. Los próximos asientos de esta cartola usarán esa cuenta bancaria.")
                st.rerun()

    if banco_seccion == "Cargar cartola":
        bancos = pd.read_sql_query("SELECT id,nombre,numero_cuenta FROM bancos WHERE activo=1 ORDER BY nombre", conn)
        if bancos.empty:
            st.warning("Primero crea una cuenta bancaria.")
        else:
            banco_label = st.selectbox("Cuenta bancaria", [f"{r.id} - {r.nombre} - {r.numero_cuenta}" for r in bancos.itertuples()], key="carga_banco")
            banco_id = int(banco_label.split(" - ")[0])
            archivo = st.file_uploader("Cartola bancaria PDF, CSV o Excel", type=["pdf","csv","xlsx","xls"], key="cartola_file")
            password_pdf = st.text_input("Contraseña del PDF (solo si está protegido)", type="password", key="cartola_pwd")
            st.caption("La contraseña se usa únicamente para abrir el PDF durante esta carga; SGCI no la guarda.")

            if archivo:
                try:
                    archivo_hash = hash_archivo(archivo)
                    previa = importacion_archivo_existente(conn, "CARTOLA", archivo_hash)
                    if previa:
                        st.error(f"⚠️ Este mismo archivo ya fue importado el {previa['fecha_hora']}. Archivo: {previa['nombre_archivo']} · Lote: {previa['lote_id'] or 'sin lote'}. SGCI bloqueó la recarga.")
                    else:
                        if archivo.name.lower().endswith(".pdf"):
                            dfc = leer_cartola_pdf(archivo, password_pdf)
                        else:
                            dfc = leer_archivo_tabular(archivo)
                        st.write("Vista previa — verifica cargos y abonos antes de importar")
                        if archivo.name.lower().endswith(".pdf"):
                            st.info("Puedes corregir Cargo y Abono directamente en la vista previa. En particular, revisa las transferencias entrantes que no dicen expresamente 'abono'.")
                            dfc = st.data_editor(dfc, use_container_width=True, hide_index=True,
                                disabled=[c for c in dfc.columns if c not in ("cargo", "abono")],
                                key="sgci_previa_pdf_editable")
                        else:
                            st.dataframe(dfc.head(50), use_container_width=True, hide_index=True)
                        errores_signo = []
                        if "cargo" in dfc.columns and "abono" in dfc.columns:
                            for idx, rr in dfc.iterrows():
                                ca = numero_cartola_clp(rr["cargo"])
                                ab = numero_cartola_clp(rr["abono"])
                                if ca < 0 or ab < 0 or (ca <= 0 and ab <= 0):
                                    errores_signo.append(idx + 1)
                        if "revision" in dfc.columns and (dfc["revision"] == "REVISAR SIGNO").any():
                            st.warning("Hay un primer movimiento con signo no verificable por la descripción. Comprueba su naturaleza contra la cartola original.")
                        if "cargo" in dfc.columns and "abono" in dfc.columns and any(
                            numero_cartola_clp(r["cargo"]) > 0 and numero_cartola_clp(r["abono"]) > 0 for _, r in dfc.iterrows()
                        ):
                            st.warning("La cartola contiene filas con cargo y abono simultáneos. Se conservarán ambos importes; no concilies automáticamente esas filas con facturas o pagos.")
                        confirmar_signos = st.checkbox("He comprobado los cargos y abonos contra la cartola original", key="sgci_confirma_signos_pdf") if archivo.name.lower().endswith(".pdf") else True
                        if errores_signo:
                            st.error(f"Movimientos con cargo/abono inválidos en filas: {errores_signo[:12]}")
                        if st.button("Importar cartola", type="primary", disabled=bool(errores_signo) or not confirmar_signos):
                            sgci_exigir_permiso(conn, 'banco', 'importar', 'Bancos y cartolas')
                            nuevos,repetidos,lote = importar_cartola(conn, dfc, banco_id, origen="PDF" if archivo.name.lower().endswith(".pdf") else "ARCHIVO")
                            registrar_importacion_archivo(conn,"CARTOLA",archivo.name,archivo_hash,lote,len(dfc),nuevos,repetidos)
                            sgci_exito(f"Importados {nuevos} movimientos. Repetidos omitidos: {repetidos}.")
                            st.rerun()
                except Exception as e:
                    st.error(str(e))

            plantilla = pd.DataFrame([{"fecha":"2026-09-30","descripcion":"TRANSFERENCIA EJEMPLO","referencia":"12345","cargo":0,"abono":100000,"saldo":100000}])
            st.download_button("📥 Descargar plantilla de cartola", plantilla.to_csv(index=False,sep=";").encode("utf-8-sig"), "plantilla_cartola_bancaria.csv", "text/csv")

            st.divider()
            st.subheader("Historial de cartolas importadas")
            st.caption("Puedes eliminar una carga equivocada completa siempre que ninguno de sus movimientos haya sido conciliado.")
            hist_cart = historial_importaciones_cartola(conn, banco_id)
            if hist_cart.empty:
                st.info("Esta cuenta todavía no tiene importaciones de cartola registradas.")
            else:
                vista_hist = hist_cart.rename(columns={
                    "lote":"Lote","desde":"Desde","hasta":"Hasta","origen":"Origen","archivo":"Archivo",
                    "movimientos":"Movimientos","cargos":"Cargos","abonos":"Abonos","conciliados":"Conciliados"
                })
                st.dataframe(formatear_montos_df(vista_hist),use_container_width=True,hide_index=True)
                etiquetas_lotes = []
                mapa_lotes = {}
                for r in hist_cart.itertuples(index=False):
                    etiqueta=f"{r.lote} | {r.desde} a {r.hasta} | {int(r.movimientos)} mov. | {int(r.conciliados)} conciliados"
                    etiquetas_lotes.append(etiqueta); mapa_lotes[etiqueta]=r.lote
                lote_sel_label=st.selectbox("Importación a administrar",etiquetas_lotes,key="cartola_lote_admin")
                lote_sel=mapa_lotes[lote_sel_label]
                fila_sel=hist_cart.loc[hist_cart["lote"]==lote_sel].iloc[0]
                if int(fila_sel["conciliados"])>0:
                    st.warning("Esta importación contiene movimientos conciliados y está protegida contra eliminación.")
                else:
                    confirmar_borrado=st.checkbox(
                        "Confirmo que deseo eliminar todos los movimientos de esta importación",
                        key="confirmar_borrar_cartola"
                    )
                    if st.button("🗑️ Eliminar importación seleccionada",disabled=not confirmar_borrado,key="borrar_lote_cartola"):
                        sgci_exigir_permiso(conn, 'banco', 'eliminar', 'Bancos y cartolas')
                        try:
                            n=eliminar_importacion_cartola(conn,banco_id,lote_sel)
                            sgci_exito(f"Importación eliminada correctamente: {n} movimiento(s).")
                            st.rerun()
                        except Exception as e:
                            st.error(str(e))

    if banco_seccion == "Movimiento manual":
        bancos = pd.read_sql_query("SELECT id,nombre,numero_cuenta FROM bancos WHERE activo=1 ORDER BY nombre", conn)
        if bancos.empty:
            st.warning("Primero crea una cuenta bancaria.")
        else:
            with st.form("movimiento_bancario_manual"):
                label = st.selectbox("Cuenta bancaria", [f"{r.id} - {r.nombre} - {r.numero_cuenta}" for r in bancos.itertuples()])
                banco_id = int(label.split(" - ")[0])
                c1,c2 = st.columns(2)
                fecha_mov = c1.date_input("Fecha", date.today())
                naturaleza = c2.selectbox("Movimiento", ["Cargo / salida de dinero", "Abono / entrada de dinero"])
                descripcion = st.text_input("Descripción")
                referencia = st.text_input("Referencia / N° documento")
                monto = st.number_input("Monto", min_value=0.0, step=1000.0,format='%.0f')
                saldo = st.number_input("Saldo después del movimiento (opcional)", value=0.0, step=1000.0,format='%.0f')
                if st.form_submit_button("Guardar movimiento manual", type="primary"):
                    sgci_exigir_permiso(conn, 'banco', 'crear', 'Bancos y cartolas')
                    if not descripcion or monto <= 0:
                        st.error("Indica descripción y un monto mayor que cero.")
                    else:
                        cargo = monto if naturaleza.startswith("Cargo") else 0
                        abono = monto if naturaleza.startswith("Abono") else 0
                        nuevos,repetidos,_ = registrar_movimiento_manual(conn,banco_id,fecha_mov.strftime("%Y-%m-%d"),descripcion,referencia,cargo,abono,saldo)
                        if nuevos:
                            sgci_exito("Movimiento guardado. Ya está disponible para conciliación.")
                        else:
                            st.warning("Ese movimiento ya existe y no se duplicó.")

    if banco_seccion == "Conciliación":
        bancos = pd.read_sql_query("SELECT id,nombre,numero_cuenta FROM bancos WHERE activo=1 ORDER BY nombre", conn)
        if bancos.empty:
            st.info("No hay cuentas bancarias.")
        else:
            label = st.selectbox("Cuenta a conciliar", [f"{r.id} - {r.nombre} - {r.numero_cuenta}" for r in bancos.itertuples()], key="conc_banco")
            banco_id = int(label.split(" - ")[0])
            info = conciliacion_banco(conn,banco_id)
            if info:
                sc,ss,dif,movs = info
                a,b,c = st.columns(3); a.metric("Saldo cartola",money(sc)); b.metric("Saldo contable",money(ss)); c.metric("Diferencia",money(dif))
                if abs(dif)<0.01:
                    st.success("🟢 Conciliación sin diferencia")
                else:
                    st.warning("🟡 Revisar diferencias")

            pendientes = pd.read_sql_query("""SELECT id,fecha,descripcion,referencia,cargo,abono,saldo,origen
                                                FROM cartola_bancaria WHERE banco_id=? AND conciliado=0
                                                ORDER BY fecha,id""", conn, params=[banco_id])
            if pendientes.empty:
                sgci_exito("No hay movimientos pendientes de conciliación.")
            else:
                st.subheader("Movimientos pendientes")
                opciones_mov = []
                for r in pendientes.itertuples():
                    cargo=float(r.cargo or 0)
                    abono=float(r.abono or 0)
                    if cargo>0 and abono>0:
                        etiqueta=f"Cargo {money(cargo)} + Abono {money(abono)} (neto {money(abono-cargo)})"
                    elif cargo>0:
                        etiqueta=f"Cargo {money(cargo)}"
                    else:
                        etiqueta=f"Abono {money(abono)}"
                    opciones_mov.append(f"{r.id} | {r.fecha} | {etiqueta} | {r.descripcion}")
                elegido = st.selectbox("Selecciona un movimiento", opciones_mov)
                movimiento_id = int(elegido.split(" | ",1)[0])
                grupo_protesto=sgci_grupo_cheque_protestado(conn,movimiento_id)
                if grupo_protesto:
                    st.warning("Cheque protestado detectado: el débito original, la devolución y la reversa suman $0. No se debe aplicar este cheque como pago de la factura de VALVAL.")
                    st.dataframe(pd.DataFrame([{'ID':int(r['id']),'Fecha':r['fecha'],
                        'Descripción':r['descripcion'],'Cargo':money(r['cargo']),
                        'Abono':money(r['abono'])} for r in grupo_protesto]),
                        use_container_width=True,hide_index=True)
                    confirmar_protesto=st.checkbox('Confirmo que este cheque fue protestado y que no existe pago contabilizado asociado.',key=f'protesto_ok_{movimiento_id}')
                    if st.button('Conciliar grupo de cheque protestado (sin contabilizar)',
                                 disabled=not confirmar_protesto,key=f'protesto_btn_{movimiento_id}'):
                        sgci_exigir_permiso(conn, 'banco', 'conciliar', 'Conciliación bancaria')
                        try:
                            ids=sgci_conciliar_cheque_protestado(conn,movimiento_id)
                            sgci_exito(f'Grupo {ids} conciliado sin generar pagos ni asientos.')
                            st.rerun()
                        except Exception as exc:
                            st.error(str(exc))
                    st.info('Para evitar pagos incorrectos, no se ofrecen coincidencias con facturas para esta devolución.')
                cand = pd.DataFrame() if grupo_protesto else candidatos_conciliacion(conn,movimiento_id)
                if cand.empty and not grupo_protesto:
                    st.warning("No encontré coincidencias exactas por monto. Puedes imputar este movimiento directamente a contabilidad aquí mismo.")
                elif not grupo_protesto:
                    mostrar = cand[["confianza","tipo","fecha","descripcion","referencia","monto","cuenta"]].copy()
                    mostrar["confianza"] = mostrar["confianza"].apply(lambda x: f"{x:.0f}%")
                    st.dataframe(mostrar.rename(columns={"confianza":"Coincidencia","tipo":"Origen","fecha":"Fecha","descripcion":"Detalle","referencia":"Referencia","monto":"Monto","cuenta":"Cuenta"}), use_container_width=True, hide_index=True)
                    opciones_cand = [f"{i} | {r.tipo} | {r.descripcion} | {money(r.monto)} | {r.confianza:.0f}%" for i,r in cand.iterrows()]
                    sel = st.selectbox("Coincidencia propuesta", opciones_cand)
                    idx = int(sel.split(" | ",1)[0])
                    elegido_c = cand.iloc[idx]
                    st.info("Si el movimiento ya fue contabilizado en Tesorería, usa la opción 💼 Tesorería más abajo: NO confirmes aquí una nueva contabilización.")
                    if st.button("✅ Confirmar y contabilizar coincidencia", type="primary"):
                        sgci_exigir_permiso(conn, 'banco', 'conciliar', 'Conciliación bancaria')
                        try:
                            asiento = contabilizar_conciliacion_bancaria(conn,movimiento_id,elegido_c["tipo"],int(elegido_c["id"]))
                            sgci_exito(f"Movimiento conciliado y contabilizado en el asiento {asiento}.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"No se pudo conciliar: {e}")

                mov_sel = pendientes.loc[pendientes["id"] == movimiento_id].iloc[0]
                if grupo_protesto:
                    st.stop()  # La devolución neutra solo admite la conciliación controlada anterior.
                with st.expander("🛠️ Corregir cargo/abono del movimiento pendiente"):
                    st.warning("Solo para errores de importación. No crea asientos ni altera movimientos conciliados. Comprueba el PDF original antes de guardar.")
                    st.write(f"Movimiento #{movimiento_id} · {mov_sel['fecha']} · {mov_sel['descripcion']}")
                    actual_tipo = "Cargo" if float(mov_sel["cargo"] or 0) > 0 else "Abono"
                    tipo_nuevo = st.radio("Naturaleza correcta", ["Cargo", "Abono"],
                                         index=0 if actual_tipo == "Cargo" else 1,
                                         horizontal=True, key=f"sgci_signo_{movimiento_id}")
                    confirmar_signo = st.checkbox("Verifiqué la naturaleza de este movimiento en la cartola bancaria original.",
                                                  key=f"sgci_confirma_signo_{movimiento_id}")
                    if st.button("Guardar corrección de signo", key=f"sgci_guardar_signo_{movimiento_id}",
                                 disabled=not confirmar_signo or tipo_nuevo == actual_tipo):
                        sgci_exigir_permiso(conn, 'banco', 'editar', 'Bancos y cartolas')
                        try:
                            sgci_corregir_signo_cartola_pendiente(conn, movimiento_id, tipo_nuevo)
                            sgci_exito(f"Movimiento #{movimiento_id} corregido a {tipo_nuevo} y registrado en auditoría.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"No se pudo corregir: {e}")
                es_cargo = float(mov_sel["cargo"] or 0) > 0
                es_abono = float(mov_sel["abono"] or 0) > 0
                metodos = (["💼 Tesorería", "👤 Nómina", "🏢 Proveedor"] if es_cargo else []) + (["👥 Cliente", "↩️ Devolución de proveedor"] if es_abono else []) + ["🔗 Asientos existentes", "✏️ Una cuenta", "🧩 Varias cuentas"]
                metodo_conc = st.radio("¿Cómo quieres conciliar este movimiento?", metodos, horizontal=True, key=f"metodo_conc_{movimiento_id}")
                if metodo_conc == "🔗 Asientos existentes":
                    st.divider()
                    st.subheader('🔗 Conciliar asientos ya contabilizados')
                    st.caption('Relaciona una o varias líneas de Banco del Libro Diario con este movimiento. No crea asientos, pagos ni descuentos nuevos.')
                    lineas_disp=sgci_lineas_bancarias_disponibles(conn,movimiento_id)
                    if lineas_disp.empty:
                        st.warning('No hay líneas bancarias disponibles para la cuenta de este banco y naturaleza del movimiento. Verifica que los pagos estén contabilizados y que el banco tenga cuenta contable asignada.')
                    else:
                        etiquetas={f"Línea {int(r.id)} · Asiento {int(r.asiento_id)} · {r.fecha} · {money(r.monto)} · {str(r.glosa or '')[:85]}":int(r.id)
                                   for r in lineas_disp.itertuples(index=False)}
                        elegidas=st.multiselect('Selecciona las líneas bancarias ya registradas',list(etiquetas),key=f'lineas_existentes_{movimiento_id}')
                        ids_elegidos=[etiquetas[x] for x in elegidas]
                        suma=float(lineas_disp[lineas_disp['id'].isin(ids_elegidos)]['monto'].sum())
                        objetivo=float(mov_sel['cargo'] if es_cargo else mov_sel['abono'])
                        c1,c2,c3=st.columns(3)
                        c1.metric('Cartola',money(objetivo)); c2.metric('Líneas seleccionadas',money(suma)); c3.metric('Diferencia',money(objetivo-suma))
                        if ids_elegidos:
                            st.dataframe(lineas_disp[lineas_disp['id'].isin(ids_elegidos)],use_container_width=True,hide_index=True)
                        correcto=bool(ids_elegidos) and abs(suma-objetivo)<0.005
                        if not correcto:
                            st.info('Selecciona únicamente las líneas bancarias cuya suma coincida exactamente con la cartola.')
                        confirmar=st.checkbox('Confirmo que estas líneas corresponden a esta misma operación bancaria y que no debo generar otro asiento.',key=f'conf_lineas_existentes_{movimiento_id}')
                        if st.button('🔗 Conciliar sin contabilizar nuevamente',type='primary',disabled=not (correcto and confirmar),key=f'btn_lineas_existentes_{movimiento_id}'):
                            sgci_exigir_permiso(conn, 'banco', 'conciliar', 'Conciliación bancaria')
                            try:
                                n=sgci_conciliar_lineas_existentes(conn,movimiento_id,ids_elegidos)
                                sgci_exito(f'Movimiento {movimiento_id} conciliado con {n} líneas existentes. Sin asiento adicional.')
                                st.rerun()
                            except Exception as exc:
                                st.error(f'No se pudo conciliar: {exc}')
                if es_cargo and metodo_conc == '💼 Tesorería':
                    st.divider()
                    st.subheader('💼 Conciliar pago ya contabilizado en Tesorería')
                    tes_crear_tablas(conn)
                    pendientes_tes=pd.read_sql_query("""SELECT s.id,s.beneficiario,p.fecha_pago,p.referencia,
                        SUM(d.monto) AS monto,p.asiento_id FROM tes_solicitudes s
                        JOIN tes_confirmaciones_pago p ON p.solicitud_id=s.id
                        JOIN tes_solicitud_detalle d ON d.solicitud_id=s.id
                        WHERE s.estado='CONTABILIZADA' AND p.banco_id=?
                        AND NOT EXISTS(SELECT 1 FROM cartola_bancaria cb WHERE cb.conciliado=1
                        AND cb.match_tipo='TESORERIA' AND cb.match_id=s.id)
                        GROUP BY s.id HAVING ROUND(SUM(d.monto))=? ORDER BY p.fecha_pago DESC""",conn,
                        params=(banco_id,int(round(float(mov_sel['cargo'] or 0)))))
                    if pendientes_tes.empty:
                        st.info('No hay pagos contabilizados en Tesorería pendientes de conciliación con este banco y monto.')
                    else:
                        st.dataframe(pendientes_tes,hide_index=True,use_container_width=True)
                        opciones_tes={f'SF-{int(r.id):06d} · {r.beneficiario} · {r.fecha_pago} · {r.referencia}':int(r.id)
                            for r in pendientes_tes.itertuples(index=False)}
                        eleg_tes=st.selectbox('Selecciona el pago de Tesorería',list(opciones_tes),key=f'tes_match_{movimiento_id}')
                        confirma_tes=st.checkbox('Confirmo que corresponde a la misma transferencia; no se generará otro asiento.',key=f'tes_match_ok_{movimiento_id}')
                        if st.button('Conciliar sin contabilizar nuevamente',type='primary',disabled=not confirma_tes,key=f'tes_match_btn_{movimiento_id}'):
                            sgci_exigir_permiso(conn, 'banco', 'conciliar', 'Conciliación bancaria')
                            try:
                                asiento_tes=tes_conciliar_pago(conn,movimiento_id,opciones_tes[eleg_tes])
                                sgci_exito(f'Conciliación registrada con asiento existente {asiento_tes}. Sin duplicar contabilidad.')
                                st.rerun()
                            except Exception as exc:
                                st.error(str(exc))
                if es_cargo and metodo_conc == "👤 Nómina":
                    st.divider()
                    st.subheader("👤 Nómina / trabajador")
                    st.caption("Úsalo para conciliar anticipos quincenales pagados por cheque o transferencia. SGCI carga Anticipos de remuneraciones, acredita Banco y vincula el pago al trabajador y período.")
                    trabajadores_banco=pd.read_sql_query(
                        "SELECT id,rut,nombre,sueldo_base,anticipo_porcentaje FROM nomina_trabajadores WHERE activo=1 ORDER BY nombre",
                        conn
                    )
                    if trabajadores_banco.empty:
                        st.info("No hay trabajadores activos registrados en Nómina.")
                    else:
                        mapa_trab_banco={f"{r.rut} | {r.nombre}":r for r in trabajadores_banco.itertuples()}
                        trab_label_banco=st.selectbox("Trabajador",list(mapa_trab_banco.keys()),key=f"nomina_trab_banco_{movimiento_id}")
                        trab_banco=mapa_trab_banco[trab_label_banco]
                        periodo_sugerido=str(mov_sel["fecha"])[:7] if str(mov_sel["fecha"] or "") else date.today().strftime("%Y-%m")
                        periodo_banco=st.text_input("Período de nómina (AAAA-MM)",value=periodo_sugerido,key=f"nomina_periodo_banco_{movimiento_id}")
                        monto_banco_nom=clp_round(float(mov_sel["cargo"] or 0))
                        sugerido_nom=clp_round(float(trab_banco.sueldo_base or 0)*float(trab_banco.anticipo_porcentaje or 50)/100)
                        a_nom,b_nom=st.columns(2)
                        st.caption(f"Movimiento seleccionado: #{movimiento_id} · {mov_sel['fecha']} · {mov_sel['descripcion']}")
                        a_nom.metric("Cargo de este movimiento",money(monto_banco_nom))
                        b_nom.metric("Anticipo referencial (NO es pago registrado)",money(sugerido_nom))
                        if monto_banco_nom != sugerido_nom:
                            st.warning("El cargo bancario NO coincide con el anticipo habitual. Confirma que realmente corresponde al trabajador y período antes de contabilizar.")
                        obs_nom=st.text_input("Observación",value=f"Anticipo quincenal {periodo_banco}",key=f"nomina_obs_banco_{movimiento_id}")
                        confirma_nom=st.checkbox(
                            f"Confirmo que el movimiento #{movimiento_id} por {money(monto_banco_nom)} corresponde a {trab_banco.nombre} y al período {periodo_banco}.",
                            key=f"nomina_conf_banco_{movimiento_id}"
                        )
                        if st.button("👤 Contabilizar y vincular anticipo",type="primary",disabled=not confirma_nom,key=f"nomina_btn_banco_{movimiento_id}"):
                            sgci_exigir_permiso(conn, 'banco', 'contabilizar', 'Conciliación bancaria')
                            try:
                                asiento_nom, anticipo_id=contabilizar_anticipo_nomina_desde_cartola(
                                    conn,movimiento_id,trab_banco.id,periodo_banco,obs_nom
                                )
                                sgci_exito(f"Anticipo registrado en Nómina y conciliado. Asiento {asiento_nom} · Anticipo #{anticipo_id}.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"No se pudo registrar el anticipo: {e}")

                if es_cargo and metodo_conc == "🏢 Proveedor":
                    st.divider()
                    st.subheader("🏢 Pago a proveedor")
                    st.caption("Úsalo cuando el cargo bancario paga una factura ya contabilizada en RCV. SGCI rebaja Proveedores, acredita Banco y actualiza el auxiliar del proveedor y sus documentos.")
                    proveedores_pago = pd.read_sql_query("SELECT id,rut,COALESCE(NULLIF(razon_social,''),nombre) nombre FROM proveedores WHERE activo=1 ORDER BY nombre", conn)
                    if proveedores_pago.empty:
                        st.info("No hay proveedores registrados.")
                    else:
                        prov_labels = [f"{r.id} | {r.rut} | {r.nombre}" for r in proveedores_pago.itertuples()]
                        prov_label = st.selectbox("Proveedor", prov_labels, key=f"pago_prov_{movimiento_id}")
                        prov_id = int(prov_label.split(" | ",1)[0])
                        docs_pend = documentos_pendientes_proveedor(conn, prov_id)
                        modo_pago_prov = st.radio(
                            "Aplicación del pago",
                            ["Aplicar a documento(s) pendiente(s)", "Pago sin documento / saldo anterior"],
                            key=f"modo_pago_prov_{movimiento_id}",
                            horizontal=True
                        )

                        if modo_pago_prov == "Aplicar a documento(s) pendiente(s)":
                            if docs_pend.empty:
                                st.info("Este proveedor no tiene documentos con saldo pendiente. Si el pago corresponde a un período anterior, usa ‘Pago sin documento / saldo anterior’.")
                            else:
                                docs_show = docs_pend.copy()
                                for col in ["total","aplicado","pendiente"]:
                                    docs_show[col] = docs_show[col].apply(money)
                                st.dataframe(docs_show.rename(columns={"fecha":"Fecha","folio":"Folio","tipo_doc":"Tipo doc.","total":"Total","aplicado":"Pagado","pendiente":"Saldo pendiente"}), use_container_width=True, hide_index=True)
                                doc_map = {f"{int(r.id)} | {r.fecha} | Folio {r.folio} | pendiente {money(r.pendiente)}": int(r.id) for r in docs_pend.itertuples()}
                                docs_sel_labels = st.multiselect("Documento(s) que paga este movimiento", list(doc_map.keys()), key=f"docs_pago_{movimiento_id}")
                                docs_ids = [doc_map[x] for x in docs_sel_labels]
                                disponible = clp_round(float(docs_pend[docs_pend["id"].isin(docs_ids)]["pendiente"].sum())) if docs_ids else 0
                                monto_mov = clp_round(float(mov_sel["cargo"] or 0))
                                cuenta_dif_codigo = None
                                glosa_dif = ""
                                diferencia_pago = max(0, clp_round(monto_mov-disponible)) if docs_ids else 0

                                if docs_ids:
                                    a1,a2,a3=st.columns(3)
                                    a1.metric("Cargo bancario", money(monto_mov))
                                    a2.metric("Aplicado a documentos", money(min(monto_mov,disponible)))
                                    a3.metric("Diferencia por imputar", money(diferencia_pago))
                                    if disponible > monto_mov:
                                        st.info(f"Pago parcial: quedarán {money(disponible-monto_mov)} pendientes en los documentos seleccionados.")
                                    elif diferencia_pago > 0:
                                        st.warning("El cargo bancario es mayor que el saldo de los documentos. La diferencia no se cargará al proveedor: debes indicar otra cuenta contable.")
                                        cuentas_dif=cuentas_imputables(conn)
                                        mapa_dif=dict(zip(cuentas_dif.etiqueta,cuentas_dif.codigo))
                                        cuenta_dif_label=st.selectbox("Cuenta contable para la diferencia",list(mapa_dif.keys()),key=f"cuenta_dif_prov_{movimiento_id}")
                                        cuenta_dif_codigo=mapa_dif.get(cuenta_dif_label)
                                        glosa_dif=st.text_input("Glosa de la diferencia",value=f"Diferencia pago proveedor {prov_label.split(' | ',2)[-1]}",key=f"glosa_dif_prov_{movimiento_id}")
                                        st.caption("Ejemplos: diferencia de pago, anticipo al proveedor, comisión bancaria u otra cuenta que corresponda según la naturaleza real.")

                                confirma_prov = st.checkbox("Confirmo que este movimiento corresponde al pago del proveedor y documentos seleccionados.", key=f"conf_pago_prov_{movimiento_id}")
                                falta_cuenta_dif = bool(docs_ids and diferencia_pago>0 and not cuenta_dif_codigo)
                                if st.button("💳 Contabilizar pago a proveedor", type="primary", disabled=(not confirma_prov or not docs_ids or falta_cuenta_dif), key=f"btn_pago_prov_{movimiento_id}"):
                                    sgci_exigir_permiso(conn, 'banco', 'contabilizar', 'Conciliación bancaria')
                                    try:
                                        asiento, aplicaciones, diferencia = contabilizar_pago_proveedor_desde_cartola(
                                            conn, movimiento_id, prov_id, docs_ids,
                                            cuenta_diferencia=cuenta_dif_codigo,
                                            glosa_diferencia=glosa_dif
                                        )
                                        msg=f"Pago contabilizado y conciliado en el asiento {asiento}. Auxiliar del proveedor actualizado."
                                        if diferencia>0:
                                            msg += f" Diferencia imputada: {money(diferencia)}."
                                        sgci_exito(msg)
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"No se pudo contabilizar el pago: {e}")
                        else:
                            monto_mov = float(mov_sel["cargo"] or 0)
                            st.info(f"Se registrará {money(monto_mov)} como pago de {prov_label.split(' | ',2)[-1]}, sin asociarlo a una factura. Quedará visible en el estado de cuenta del proveedor.")
                            st.caption("Esta opción es apropiada para saldos anteriores o documentos que aún no están cargados. Hasta incorporar el saldo inicial, el auxiliar puede mostrar temporalmente un saldo deudor.")
                            confirma_sin_doc = st.checkbox("Confirmo que el pago corresponde a este proveedor y no deseo asociarlo a un documento.", key=f"conf_pago_prov_sd_{movimiento_id}")
                            if st.button("💳 Contabilizar pago sin documento", type="primary", disabled=not confirma_sin_doc, key=f"btn_pago_prov_sd_{movimiento_id}"):
                                sgci_exigir_permiso(conn, 'banco', 'contabilizar', 'Conciliación bancaria')
                                try:
                                    asiento = contabilizar_pago_proveedor_sin_documento(conn, movimiento_id, prov_id)
                                    sgci_exito(f"Pago sin documento contabilizado y conciliado en el asiento {asiento}. Auxiliar del proveedor actualizado.")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"No se pudo contabilizar el pago: {e}")

                if es_abono and metodo_conc == "↩️ Devolución de proveedor":
                    st.divider()
                    st.subheader('↩️ Devolución de proveedor')
                    st.caption('Reembolso de una nota de crédito que excede una factura del mismo proveedor. Un solo asiento Banco / Proveedores, auxiliar actualizado y movimiento conciliado.')
                    sgci_crear_devoluciones_proveedor(conn)
                    proveedores_dev = pd.read_sql_query('''SELECT id,rut,COALESCE(NULLIF(razon_social,''),nombre) AS nombre
                        FROM proveedores WHERE activo=1 ORDER BY nombre''', conn)
                    if proveedores_dev.empty:
                        st.info('No hay proveedores activos.')
                    else:
                        etiquetas_dev = {f'{int(r.id)} | {r.rut} | {r.nombre}':int(r.id) for r in proveedores_dev.itertuples()}
                        etiqueta_dev = st.selectbox('Proveedor que realizó el reembolso',list(etiquetas_dev),key=f'dev_prov_{movimiento_id}')
                        prov_dev = etiquetas_dev[etiqueta_dev]
                        documentos_dev = pd.read_sql_query('''SELECT id,fecha,folio,tipo_doc,monto_total FROM compras
                            WHERE proveedor_id=? ORDER BY fecha DESC,id DESC''',conn,params=[prov_dev])
                        notas_dev = documentos_dev[documentos_dev['tipo_doc'].isin([60,61])]
                        facturas_dev = documentos_dev[~documentos_dev['tipo_doc'].isin([60,61])]
                        if notas_dev.empty or facturas_dev.empty:
                            st.warning('El proveedor debe tener una nota de crédito y una factura registradas en compras.')
                        else:
                            mapa_nc_dev = {f'NC {r.folio} | {r.fecha} | {money(abs(float(r.monto_total)))}':int(r.id) for r in notas_dev.itertuples()}
                            mapa_fac_dev = {f'Factura {r.folio} | {r.fecha} | {money(abs(float(r.monto_total)))}':int(r.id) for r in facturas_dev.itertuples()}
                            etiqueta_nc = st.selectbox('Nota de crédito que originó el saldo a favor',list(mapa_nc_dev),key=f'dev_nc_{movimiento_id}')
                            etiqueta_fac = st.selectbox('Factura que se compensa con la nota de crédito',list(mapa_fac_dev),key=f'dev_fac_{movimiento_id}')
                            id_nc,id_fac = mapa_nc_dev[etiqueta_nc],mapa_fac_dev[etiqueta_fac]
                            total_nc = abs(float(notas_dev.loc[notas_dev['id']==id_nc,'monto_total'].iloc[0]))
                            total_fac = abs(float(facturas_dev.loc[facturas_dev['id']==id_fac,'monto_total'].iloc[0]))
                            aplicado_dev = conn.execute('''SELECT COALESCE(SUM(monto),0) FROM sgci_devoluciones_proveedor
                                WHERE nota_credito_id=? AND factura_id=?''',(id_nc,id_fac)).fetchone()[0]
                            saldo_dev = clp_round(total_nc-total_fac-float(aplicado_dev or 0))
                            abono_dev = clp_round(float(mov_sel['abono'] or 0))
                            c1,c2,c3=st.columns(3)
                            c1.metric('Diferencia NC menos factura',money(total_nc-total_fac))
                            c2.metric('Abono bancario',money(abono_dev))
                            c3.metric('Diferencia por devolver restante',money(saldo_dev-abono_dev))
                            st.info('Se contabilizará Banco al Debe y Proveedores al Haber. No se volverán a registrar la factura, la nota de crédito ni el IVA.')
                            glosa_dev = st.text_input('Glosa',value=f'Devolución proveedor - NC {notas_dev.loc[notas_dev["id"]==id_nc,"folio"].iloc[0]} / Factura {facturas_dev.loc[facturas_dev["id"]==id_fac,"folio"].iloc[0]}',key=f'dev_glosa_{movimiento_id}')
                            confirma_dev = st.checkbox('Confirmo que el abono corresponde a la diferencia de estos documentos y que no fue contabilizado anteriormente.',key=f'dev_confirm_{movimiento_id}')
                            valido_dev = saldo_dev > 0 and abono_dev <= saldo_dev
                            if not valido_dev:
                                st.error('La diferencia disponible no alcanza para este abono. Verifica los documentos y reembolsos anteriores.')
                            if st.button('↩️ Contabilizar y conciliar devolución',type='primary',disabled=not (confirma_dev and valido_dev),key=f'dev_btn_{movimiento_id}'):
                                sgci_exigir_permiso(conn, 'banco', 'contabilizar', 'Conciliación bancaria')
                                try:
                                    asiento_dev=sgci_contabilizar_devolucion_proveedor(conn,movimiento_id,prov_dev,id_nc,id_fac,glosa_dev)
                                    sgci_exito(f'Devolución conciliada. Asiento N.º {asiento_dev}. Auxiliar del proveedor actualizado sin duplicar IVA.')
                                    st.rerun()
                                except Exception as exc:
                                    st.error(f'No se pudo contabilizar la devolución: {exc}')

                if es_abono and metodo_conc == "👥 Cliente":
                    st.divider()
                    st.subheader("👥 Cobro / anticipo de cliente")
                    st.caption("Aplica el abono a facturas pendientes o regístralo como anticipo/saldo a favor del cliente. Si el abono supera las facturas elegidas, puedes enviar el sobrante a Anticipos de clientes u otra cuenta.")
                    clientes_cobro=pd.read_sql_query("SELECT id,rut,COALESCE(NULLIF(razon_social,''),nombre) nombre FROM clientes WHERE activo=1 ORDER BY nombre",conn)
                    if clientes_cobro.empty:
                        st.info("No hay clientes activos registrados.")
                    else:
                        cli_labels=[f"{r.id} | {r.rut} | {r.nombre}" for r in clientes_cobro.itertuples()]
                        cli_label=st.selectbox("Cliente",cli_labels,key=f"cobro_cli_{movimiento_id}")
                        cli_id=int(cli_label.split(" | ",1)[0])
                        docs_cli=documentos_pendientes_cliente(conn,cli_id)
                        sgci_saldos_apertura_clientes(conn)
                        with st.expander("📘 Saldo inicial 2026 del cliente (auxiliar, sin asiento contable)"):
                            registro=conn.execute("SELECT monto FROM sgci_apertura_clientes WHERE cliente_id=?",(cli_id,)).fetchone()
                            monto_reg=int(registro[0]) if registro else 0
                            saldo_nuevo=st.number_input("Saldo inicial total del cliente al 01-01-2026 (CLP)",
                                min_value=0,step=1000,value=monto_reg,key=f"apert_cli_monto_{cli_id}")
                            st.caption("Solo registra el auxiliar; el saldo ya está en el Libro Diario. Verifica que coincida con el detalle del asiento de apertura.")
                            if st.button("Guardar saldo inicial auxiliar",key=f"apert_cli_save_{cli_id}"):
                                sgci_exigir_permiso(conn, 'cxc', 'editar', 'Clientes y estados de cuenta')
                                aplicado=conn.execute("SELECT COALESCE(SUM(monto),0) FROM sgci_aplicaciones_apertura_clientes WHERE cliente_id=?",(cli_id,)).fetchone()[0]
                                if int(saldo_nuevo)<int(aplicado):
                                    st.error("El saldo inicial no puede ser menor que lo ya aplicado.")
                                else:
                                    conn.execute("""INSERT INTO sgci_apertura_clientes(cliente_id,monto,observacion)
                                      VALUES(?,?,'Saldo de apertura ya contabilizado')
                                      ON CONFLICT(cliente_id) DO UPDATE SET monto=excluded.monto""",(cli_id,int(saldo_nuevo)))
                                    conn.commit()
                                    sgci_exito("Saldo inicial auxiliar guardado; no se generó asiento.")
                                    st.rerun()
                        apertura_disponible=sgci_saldo_apertura_disponible(conn,cli_id)
                        st.caption(f"Saldo de apertura disponible para aplicar: {money(apertura_disponible)}")
                        with st.expander("🧩 Cobro mixto: varias facturas + saldo inicial"):
                            st.caption("Marca las facturas de 2026 y asigna la parte del cobro correspondiente a 2025. Un solo asiento Banco / Clientes.")
                            opciones={f"{r.folio} | {r.fecha} | {money(r.pendiente)}":int(r.id) for r in docs_cli.itertuples()}
                            elegidas=st.multiselect("Facturas a cancelar",list(opciones),key=f"mix_docs_{movimiento_id}")
                            ids_mix=[opciones[x] for x in elegidas]
                            suma_docs=clp_round(float(docs_cli[docs_cli.id.isin(ids_mix)].pendiente.sum())) if ids_mix else 0
                            importe_banco=clp_round(float(mov_sel["abono"] or 0))
                            aplicar_apertura=st.number_input("Aplicar a saldo inicial 2025",min_value=0,
                                max_value=max(0,min(apertura_disponible,importe_banco)),step=1,
                                value=0,key=f"mix_apert_{movimiento_id}")
                            diferencia_mix=importe_banco-suma_docs-int(aplicar_apertura)
                            c1,c2,c3=st.columns(3)
                            c1.metric("Abono bancario",money(importe_banco))
                            c2.metric("Total distribuido",money(suma_docs+int(aplicar_apertura)))
                            c3.metric("Diferencia",money(diferencia_mix))
                            if diferencia_mix==0 and (ids_mix or aplicar_apertura):
                                sgci_exito("Distribución cuadrada.")
                            else:
                                st.warning("La suma de facturas y apertura debe coincidir exactamente con el abono.")
                            confirm_mix=st.checkbox("Confirmo el cobro mixto y su imputación al cliente.",key=f"mix_conf_{movimiento_id}")
                            if st.button("💰 Contabilizar y conciliar cobro mixto",
                                disabled=not(confirm_mix and diferencia_mix==0 and (ids_mix or aplicar_apertura)),
                                key=f"mix_btn_{movimiento_id}",type="primary"):
                                sgci_exigir_permiso(conn, 'banco', 'contabilizar', 'Conciliación bancaria')
                                try:
                                    asi=sgci_cobro_mixto(conn,movimiento_id,cli_id,ids_mix,int(aplicar_apertura))
                                    sgci_exito(f"Cobro mixto contabilizado en asiento {asi}.")
                                    st.rerun()
                                except Exception as e: st.error(f"No se pudo conciliar: {e}")
                        modo_cli=st.radio("Aplicación del abono",
                                          ["Aplicar a factura(s) pendiente(s)","Anticipo / cobro sin documento"],
                                          key=f"modo_cobro_cli_{movimiento_id}",horizontal=True)
                        if modo_cli=="Aplicar a factura(s) pendiente(s)":
                            if docs_cli.empty:
                                st.info("Este cliente no tiene facturas pendientes. Usa ‘Anticipo / cobro sin documento’ si corresponde.")
                            else:
                                show=docs_cli.copy()
                                for col in ["total","aplicado","pendiente"]: show[col]=show[col].apply(money)
                                st.dataframe(show.rename(columns={"fecha":"Fecha","folio":"Folio","tipo_doc":"Tipo doc.","total":"Total","aplicado":"Cobrado","pendiente":"Saldo pendiente"}),use_container_width=True,hide_index=True)
                                docmap={f"{int(r.id)} | {r.fecha} | Folio {r.folio} | pendiente {money(r.pendiente)}":int(r.id) for r in docs_cli.itertuples()}
                                sellabs=st.multiselect("Factura(s) que paga este abono",list(docmap.keys()),key=f"docs_cobro_cli_{movimiento_id}")
                                ids=[docmap[x] for x in sellabs]
                                disponible=clp_round(float(docs_cli[docs_cli["id"].isin(ids)]["pendiente"].sum())) if ids else 0
                                monto=clp_round(float(mov_sel["abono"] or 0))
                                sobrante=max(0,clp_round(monto-disponible)) if ids else 0
                                cuenta_sobrante=None; glosa_sobrante=""
                                if ids:
                                    x1,x2,x3=st.columns(3)
                                    x1.metric("Abono bancario",money(monto)); x2.metric("Aplicado a facturas",money(min(monto,disponible))); x3.metric("Sobrante",money(sobrante))
                                    if disponible>monto:
                                        st.info(f"Cobro parcial: quedarán {money(disponible-monto)} pendientes en las facturas seleccionadas.")
                                    elif sobrante>0:
                                        st.warning("El cliente pagó más que las facturas seleccionadas. Indica dónde registrar el sobrante; normalmente Anticipos recibidos de clientes.")
                                        cd=cuentas_imputables(conn); md=dict(zip(cd.etiqueta,cd.codigo))
                                        labels=list(md.keys())
                                        pred=next((x for x in labels if x.startswith("2.1.03.01") or "Anticipos recibidos de clientes" in x),labels[0] if labels else "")
                                        idxpred=labels.index(pred) if pred in labels else 0
                                        sl=st.selectbox("Cuenta para el sobrante",labels,index=idxpred,key=f"sobrante_cli_{movimiento_id}")
                                        cuenta_sobrante=md.get(sl)
                                        glosa_sobrante=st.text_input("Glosa del sobrante",value=f"Anticipo/sobrante {cli_label.split(' | ',2)[-1]}",key=f"glosa_sobrante_cli_{movimiento_id}")
                                conf=st.checkbox("Confirmo la aplicación de este abono al cliente y facturas seleccionadas.",key=f"conf_cobro_cli_{movimiento_id}")
                                falta=bool(ids and sobrante>0 and not cuenta_sobrante)
                                if st.button("💰 Contabilizar cobro de cliente",type="primary",disabled=(not conf or not ids or falta),key=f"btn_cobro_cli_{movimiento_id}"):
                                    sgci_exigir_permiso(conn, 'banco', 'contabilizar', 'Conciliación bancaria')
                                    try:
                                        asi,aps,sob=contabilizar_cobro_cliente_desde_cartola(conn,movimiento_id,cli_id,ids,cuenta_sobrante,glosa_sobrante)
                                        sgci_exito(f"Cobro contabilizado y conciliado en asiento {asi}."+ (f" Sobrante registrado: {money(sob)}." if sob else ""))
                                        st.rerun()
                                    except Exception as e: st.error(f"No se pudo contabilizar el cobro: {e}")
                        else:
                            cuentas=cuentas_imputables(conn); mapa=dict(zip(cuentas.etiqueta,cuentas.codigo)); labels=list(mapa.keys())
                            pred=next((x for x in labels if x.startswith("2.1.03.01") or "Anticipos recibidos de clientes" in x),labels[0] if labels else "")
                            idxpred=labels.index(pred) if pred in labels else 0
                            selcta=st.selectbox("Cuenta de anticipo / saldo a favor",labels,index=idxpred,key=f"cta_ant_cli_{movimiento_id}")
                            st.info(f"Se registrará {money(float(mov_sel['abono'] or 0))} como anticipo/cobro sin documento del cliente seleccionado, sin cancelar facturas.")
                            conf=st.checkbox("Confirmo que este abono corresponde al cliente y no deseo aplicarlo a una factura.",key=f"conf_ant_cli_{movimiento_id}")
                            if st.button("💰 Registrar anticipo de cliente",type="primary",disabled=not conf,key=f"btn_ant_cli_{movimiento_id}"):
                                sgci_exigir_permiso(conn, 'banco', 'contabilizar', 'Conciliación bancaria')
                                try:
                                    asi=contabilizar_cobro_cliente_sin_documento(conn,movimiento_id,cli_id,mapa.get(selcta))
                                    sgci_exito(f"Anticipo/cobro sin documento contabilizado y conciliado en asiento {asi}.")
                                    st.rerun()
                                except Exception as e: st.error(f"No se pudo registrar el anticipo: {e}")

                if metodo_conc == "✏️ Una cuenta":
                    st.divider()
                    st.subheader("Imputación manual del movimiento")
                    st.caption("Úsala cuando no exista una coincidencia adecuada. Al confirmar, SGCI genera el asiento y marca el movimiento como conciliado. Si el gasto ya fue provisionado, selecciona la cuenta por pagar correspondiente; no vuelvas a seleccionar la cuenta de gasto.")
                    cuentas_manual = cuentas_imputables(conn)
                    if cuentas_manual.empty:
                        st.info("No hay cuentas imputables disponibles en el plan de cuentas.")
                    else:
                        mapa_manual = dict(zip(cuentas_manual.etiqueta, cuentas_manual.codigo))
                        cuenta_manual = st.selectbox("Cuenta contable de contrapartida", list(mapa_manual.keys()), key=f"imputacion_cuenta_{movimiento_id}")
                        mov_sel = pendientes.loc[pendientes["id"] == movimiento_id].iloc[0]
                        glosa_base = limpiar_texto(mov_sel["descripcion"])
                        glosa_manual = st.text_input("Glosa del asiento", value=glosa_base, key=f"imputacion_glosa_{movimiento_id}")
                        monto_sel = float(mov_sel["cargo"] or 0) if float(mov_sel["cargo"] or 0) > 0 else float(mov_sel["abono"] or 0)
                        naturaleza_sel = "Cargo / salida" if float(mov_sel["cargo"] or 0) > 0 else "Abono / entrada"
                        st.info(f"Movimiento: {naturaleza_sel} por {money(monto_sel)}. SGCI usará automáticamente la cuenta bancaria como la otra línea del asiento.")
                        confirmar_manual = st.checkbox("Confirmo que revisé la cuenta contable y deseo contabilizar y conciliar este movimiento.", key=f"imputacion_confirma_{movimiento_id}")
                        if st.button("🧾 Contabilizar e imputar manualmente", type="primary", disabled=not confirmar_manual, key=f"imputacion_btn_{movimiento_id}"):
                            sgci_exigir_permiso(conn, 'banco', 'contabilizar', 'Conciliación bancaria')
                            try:
                                asiento = contabilizar_imputacion_manual_bancaria(conn,movimiento_id,mapa_manual[cuenta_manual],glosa_manual)
                                sgci_exito(f"Movimiento imputado, conciliado y contabilizado en el asiento {asiento}.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"No se pudo imputar el movimiento: {e}")


                if metodo_conc == "🧩 Varias cuentas":
                    # Este formulario es autosuficiente: no depende de variables
                    # creadas por "Una cuenta" u otros métodos de conciliación.
                    monto_multi = clp_round(float(mov_sel["cargo"] or mov_sel["abono"] or 0))
                    glosa_multi_base = str(mov_sel["descripcion"] or "Movimiento bancario")
                    st.divider()
                    st.subheader("🧩 Distribuir movimiento entre varias cuentas")
                    st.caption("Úsala cuando un solo cargo o abono bancario corresponde a conceptos distintos. SGCI generará un único asiento y exigirá que la suma distribuida sea exactamente igual al movimiento bancario.")
                    # La lista de cuentas debe existir también cuando "Una cuenta" no está seleccionada.
                    cuentas_multi = cuentas_imputables(conn)
                    mapa_multi = dict(zip(cuentas_multi["etiqueta"], cuentas_multi["codigo"])) if not cuentas_multi.empty else {}
                    if not mapa_multi:
                        st.info("No hay cuentas imputables disponibles en el plan de cuentas.")
                        st.stop()
                    n_dist = st.number_input("Cantidad de cuentas a distribuir", min_value=2, max_value=10, value=2, step=1, key=f"multi_n_{movimiento_id}")
                    distribuciones_ui = []
                    for j in range(int(n_dist)):
                        cta_col, monto_col = st.columns([3,1])
                        etiqueta = cta_col.selectbox(f"Cuenta {j+1}", list(mapa_multi.keys()), key=f"multi_cta_{movimiento_id}_{j}")
                        importe = monto_col.number_input(f"Monto {j+1}", min_value=0, step=1000, format="%d", key=f"multi_monto_{movimiento_id}_{j}")
                        distribuciones_ui.append((mapa_multi[etiqueta], int(importe)))
                    total_dist = sum(x[1] for x in distribuciones_ui)
                    diferencia_dist = clp_round(monto_multi - total_dist)
                    m1,m2,m3 = st.columns(3)
                    m1.metric("Movimiento bancario", money(monto_multi))
                    m2.metric("Total distribuido", money(total_dist))
                    m3.metric("Diferencia", money(diferencia_dist))
                    glosa_multi = st.text_input("Glosa del asiento distribuido", value=glosa_multi_base, key=f"multi_glosa_{movimiento_id}")
                    cuadra_multi = (clp_round(total_dist) == clp_round(monto_multi)) and sum(1 for _,v in distribuciones_ui if v>0) >= 2
                    if cuadra_multi:
                        sgci_exito("La distribución cuadra exactamente con el movimiento bancario.")
                    else:
                        st.warning("La distribución debe sumar exactamente el monto bancario y contener al menos dos montos mayores que cero.")
                    confirma_multi = st.checkbox("Confirmo la distribución y deseo contabilizar y conciliar este movimiento.", key=f"multi_conf_{movimiento_id}")
                    if st.button("🧩 Contabilizar distribución", type="primary", disabled=not (confirma_multi and cuadra_multi), key=f"multi_btn_{movimiento_id}"):
                        sgci_exigir_permiso(conn, 'banco', 'contabilizar', 'Conciliación bancaria')
                        try:
                            asiento = contabilizar_imputacion_multiple_bancaria(conn, movimiento_id, distribuciones_ui, glosa_multi)
                            sgci_exito(f"Movimiento distribuido, conciliado y contabilizado en el asiento {asiento}.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"No se pudo contabilizar la distribución: {e}")

    if banco_seccion == "Operaciones manuales":
        st.subheader("Servicios, nómina y otros pagos/abonos")
        st.caption("Registra aquí operaciones que no provienen del RCV. Luego SGCI las buscará por coincidencia de monto contra la cartola.")
        cuentas = cuentas_imputables(conn)
        mapa = dict(zip(cuentas.etiqueta,cuentas.codigo))
        with st.form("nueva_operacion_manual"):
            c1,c2 = st.columns(2)
            fecha_op = c1.date_input("Fecha de la operación", date.today())
            tipo_op = c2.selectbox("Tipo", ["PAGO","ABONO"])
            descripcion_op = st.text_input("Descripción (ej.: Nómina septiembre, Internet, Arriendo)")
            referencia_op = st.text_input("Referencia (opcional)")
            monto_op = st.number_input("Monto de la operación", min_value=0.0, step=1000.0,format='%.0f')
            cuenta_op = st.selectbox("Cuenta contable de contrapartida", list(mapa.keys())) if mapa else ""
            if st.form_submit_button("Guardar operación"):
                if not descripcion_op or monto_op <= 0 or not cuenta_op:
                    st.error("Completa descripción, monto y cuenta contable.")
                else:
                    crear_obligacion_manual(conn,fecha_op.strftime("%Y-%m-%d"),tipo_op,descripcion_op,referencia_op,monto_op,mapa[cuenta_op])
                    sgci_exito("Operación guardada. SGCI podrá encontrarla por coincidencia de monto.")
                    st.rerun()

        ops = pd.read_sql_query("""SELECT o.id,o.fecha,o.tipo,o.descripcion,o.referencia,o.monto,o.codigo_cuenta,
                                     CASE WHEN o.conciliado=1 THEN 'Conciliado' ELSE 'Pendiente' END estado
                                     FROM obligaciones_manuales o ORDER BY o.fecha DESC,o.id DESC""", conn)
        if not ops.empty:
            st.dataframe(ops, use_container_width=True, hide_index=True)

    if banco_seccion == "Movimientos":
        bancos = pd.read_sql_query("SELECT id,nombre FROM bancos WHERE activo=1 ORDER BY nombre", conn)
        if not bancos.empty:
            label = st.selectbox("Cuenta", [f"{r.id} - {r.nombre}" for r in bancos.itertuples()], key="mov_banco")
            dfm = pd.read_sql_query("""SELECT fecha,descripcion,referencia,cargo,abono,saldo,
                                        CASE WHEN conciliado=1 THEN 'Sí' ELSE 'No' END conciliado,
                                        origen,match_tipo,match_id,asiento_id,observacion
                                        FROM cartola_bancaria WHERE banco_id=? ORDER BY fecha,id DESC""", conn, params=[int(label.split(" - ")[0])])
            st.dataframe(dfm, use_container_width=True, hide_index=True)

            pagos_para_revertir=pd.read_sql_query("""SELECT id,fecha,descripcion,referencia,cargo,asiento_id
                FROM cartola_bancaria WHERE banco_id=? AND conciliado=1
                AND match_tipo IN ('PROVEEDOR','PROVEEDOR_SIN_DOCUMENTO')
                ORDER BY fecha DESC,id DESC""",conn,params=[int(label.split(' - ')[0])])
            if not pagos_para_revertir.empty:
                st.divider()
                st.subheader('Revertir conciliación de proveedor')
                st.caption('Genera asiento reverso, retira el pago y sus aplicaciones y reabre el movimiento. Bloquea asociaciones ambiguas.')
                opciones={f"{r.id} | {r.fecha} | {money(r.cargo)} | ref. {r.referencia} | asiento {r.asiento_id} | {r.descripcion}":int(r.id)
                          for r in pagos_para_revertir.itertuples()}
                opcion=st.selectbox('Pago a proveedor para revertir',list(opciones),key='sgci_rev_prov_sel')
                confirma=st.checkbox('Confirmo que quiero revertir este pago y sus aplicaciones.',key='sgci_rev_prov_confirm')
                if st.button('↩️ Revertir pago a proveedor',disabled=not confirma,key='sgci_rev_prov_btn'):
                    sgci_exigir_permiso(conn, 'banco', 'anular', 'Conciliación bancaria')
                    try:
                        nuevo=revertir_pago_proveedor_cartola(conn,opciones[opcion])
                        sgci_exito(f'Asiento reverso {nuevo} creado. Movimiento pendiente para conciliar nuevamente.')
                        st.rerun()
                    except Exception as e:
                        st.error(f'No se realizaron cambios: {e}')

            abonos_cliente_reversibles = pd.read_sql_query("""SELECT cb.id,cb.fecha,cb.descripcion,cb.referencia,
                    cb.abono,cb.asiento_id,c.razon_social AS cliente
                    FROM cartola_bancaria cb
                    LEFT JOIN clientes c ON c.id=cb.match_id
                    WHERE cb.banco_id=? AND cb.conciliado=1
                      AND cb.match_tipo='CLIENTE_ANTICIPO' AND COALESCE(cb.abono,0)>0
                    ORDER BY cb.fecha DESC,cb.id DESC""", conn,
                    params=[int(label.split(' - ')[0])])
            if not abonos_cliente_reversibles.empty:
                st.divider()
                st.subheader('Revertir conciliación de abonos de clientes')
                st.caption('Solo anticipos sin aplicaciones. Crea asiento reverso, retira el abono del auxiliar y reabre la cartola. No borra el asiento original.')
                mapa_rev_cli = {
                    f"Cartola {r.id} | {r.fecha} | {money(r.abono)} | {r.cliente or 'Cliente'} | asiento {r.asiento_id} | {r.descripcion}": int(r.id)
                    for r in abonos_cliente_reversibles.itertuples()
                }
                sel_rev_cli = st.selectbox('Abono conciliado para revertir', list(mapa_rev_cli), key='sgci_rev_cli_sel')
                conf_rev_cli = st.checkbox('Confirmo que este anticipo NO ha sido aplicado y deseo revertir su conciliación.', key='sgci_rev_cli_conf')
                if st.button('↩️ Revertir abono de cliente y reabrir movimiento',
                             disabled=not conf_rev_cli, key='sgci_rev_cli_btn'):
                    sgci_exigir_permiso(conn, 'banco', 'anular', 'Conciliación bancaria')
                    try:
                        rev_cli = revertir_abono_cliente_cartola(conn, mapa_rev_cli[sel_rev_cli])
                        sgci_exito(f'Asiento reverso {rev_cli} registrado. Abono retirado del auxiliar y cartola pendiente para conciliar nuevamente.')
                        st.rerun()
                    except Exception as e:
                        st.error(f'No se realizaron cambios: {e}')

            anticipos_reversibles=pd.read_sql_query("""SELECT cb.id,cb.fecha,cb.descripcion,cb.cargo,cb.asiento_id,
                a.id anticipo_id,t.nombre trabajador
                FROM cartola_bancaria cb JOIN nomina_anticipos a ON a.id=cb.match_id
                JOIN nomina_trabajadores t ON t.id=a.trabajador_id
                WHERE cb.banco_id=? AND cb.conciliado=1 AND cb.match_tipo='NOMINA_ANTICIPO'
                AND COALESCE(a.anulado,0)=0 ORDER BY cb.fecha DESC,cb.id DESC""",conn,
                params=[int(label.split(' - ')[0])])
            if not anticipos_reversibles.empty:
                st.divider()
                st.subheader('Revertir anticipo de trabajador mal conciliado')
                st.caption('Genera asiento reverso, conserva el anticipo anulado y deja la transferencia pendiente. No elimina el asiento original.')
                ant_map={f"Cartola {r.id} | {r.fecha} | {money(r.cargo)} | {r.trabajador} | anticipo {r.anticipo_id} | asiento {r.asiento_id}":int(r.id)
                         for r in anticipos_reversibles.itertuples()}
                ant_sel=st.selectbox('Anticipo a corregir',list(ant_map),key='sgci_rev_ant_sel')
                ant_confirm=st.checkbox('Confirmo que esta transferencia NO corresponde a un anticipo del trabajador y debe volver a quedar pendiente.',key='sgci_rev_ant_conf')
                if st.button('↩️ Revertir anticipo y reabrir transferencia',disabled=not ant_confirm,key='sgci_rev_ant_btn'):
                    sgci_exigir_permiso(conn, 'banco', 'anular', 'Conciliación bancaria')
                    try:
                        rev=revertir_anticipo_nomina_cartola(conn,ant_map[ant_sel])
                        sgci_exito(f'Anticipo revertido mediante asiento {rev}. Transferencia pendiente para conciliar con el proveedor.')
                        st.rerun()
                    except Exception as e:
                        st.error(f'No se realizaron cambios: {e}')

            corregibles = pd.read_sql_query("""SELECT id,fecha,descripcion,cargo,abono,asiento_id
                                               FROM cartola_bancaria
                                               WHERE banco_id=? AND conciliado=1 AND match_tipo='IMPUTACION_MANUAL'
                                               ORDER BY fecha,id DESC""", conn, params=[int(label.split(" - ")[0])])
            if not corregibles.empty:
                st.divider()
                st.subheader("Corregir imputación manual")
                st.caption("Si una imputación fue enviada a una cuenta equivocada, SGCI genera un asiento reverso y deja el movimiento pendiente para volver a conciliarlo. No elimina el asiento histórico.")
                corr_map = {}
                for r in corregibles.itertuples():
                    monto_corr = float(r.cargo or 0) if float(r.cargo or 0)>0 else float(r.abono or 0)
                    lab = f"{r.id} | {r.fecha} | {money(monto_corr)} | asiento {r.asiento_id} | {r.descripcion}"
                    corr_map[lab] = int(r.id)
                corr_label = st.selectbox("Movimiento a corregir", list(corr_map.keys()), key="corr_mov_banco")
                confirma_corr = st.checkbox("Confirmo que deseo revertir contablemente esta imputación y volver a dejar el movimiento pendiente.", key="corr_confirma")
                if st.button("↩️ Revertir y reabrir movimiento", disabled=not confirma_corr, key="corr_btn"):
                    sgci_exigir_permiso(conn, 'banco', 'anular', 'Conciliación bancaria')
                    try:
                        rev = corregir_conciliacion_manual(conn, corr_map[corr_label])
                        sgci_exito(f"Imputación revertida mediante el asiento {rev}. El movimiento vuelve a estar pendiente de conciliación.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"No se pudo corregir la imputación: {e}")


# ============================================================
# CIERRE MENSUAL
# ============================================================

elif menu == "🔒 Cierre Mensual":
    st.title("🔒 Cierre Mensual")
    st.info("El cierre evita que se modifique accidentalmente un período ya revisado. Los ajustes posteriores deben registrarse en un período abierto.")
    periodos=pd.read_sql_query("SELECT periodo,estado,fecha_cierre,observacion FROM periodos_contables ORDER BY periodo DESC",conn)
    st.dataframe(periodos,use_container_width=True,hide_index=True)
    periodo=st.text_input("Período a revisar (AAAA-MM)",date.today().strftime("%Y-%m"))
    try:
        datetime.strptime(periodo,"%Y-%m")
        asegurar_periodo(conn,periodo)
        df=periodos.copy()
        desde=periodo+"-01"; ultimo=(pd.Period(periodo).end_time).strftime("%Y-%m-%d")
        diario=pd.read_sql_query("SELECT COALESCE(SUM(debe),0) debe,COALESCE(SUM(haber),0) haber FROM libro_diario WHERE fecha BETWEEN ? AND ?",conn,params=[desde,ultimo]).iloc[0]
        dif=float(diario.debe-diario.haber)
        c1,c2,c3=st.columns(3); c1.metric("Debe",money(diario.debe)); c2.metric("Haber",money(diario.haber)); c3.metric("Diferencia",money(dif))
        alertas=[]
        cc=conciliacion_clientes(conn); cp=conciliacion_proveedores(conn)
        if not cc.empty and abs(float(cc.iloc[0].Diferencia))>0.01: alertas.append("Diferencia en clientes")
        if not cp.empty and abs(float(cp.iloc[0].Diferencia))>0.01: alertas.append("Diferencia en proveedores")
        if abs(dif)>0.01: alertas.append("Libro diario descuadrado")
        st.subheader("Lista de comprobación")
        if alertas:
            for x in alertas: st.error("🔴 "+x)
        else: sgci_exito("🟢 No se detectaron diferencias básicas. El período está listo para revisión final.")
        if periodo_estado(conn,periodo)=="ABIERTO":
            if st.button("🔒 CERRAR PERÍODO",type="primary"):
                sgci_exigir_permiso(conn, 'administracion', 'aprobar', 'Cierre Mensual')
                if alertas: st.error("No se recomienda cerrar mientras existan alertas.")
                else:
                    conn.execute("UPDATE periodos_contables SET estado='CERRADO',fecha_cierre=? WHERE periodo=?",(datetime.now().strftime("%Y-%m-%d %H:%M:%S"),periodo)); conn.commit(); registrar_auditoria(conn,"CIERRE CONTABLE",periodo); sgci_exito("Período cerrado."); st.rerun()
        else:
            sgci_exito("🔒 Período cerrado")
            if st.button("Reabrir período"):
                sgci_exigir_permiso(conn, 'administracion', 'aprobar', 'Cierre Mensual')
                conn.execute("UPDATE periodos_contables SET estado='ABIERTO',fecha_cierre=NULL WHERE periodo=?",(periodo,)); conn.commit(); registrar_auditoria(conn,"REAPERTURA CONTABLE",periodo); st.warning("Período reabierto."); st.rerun()
    except Exception as e: st.error(f"Período inválido: {e}")


# ============================================================
# CUENTAS POR COBRAR/PAGAR
# ============================================================

elif menu == "📌 Cuentas por Cobrar/Pagar":
    st.title("📌 Cuentas por Cobrar y por Pagar")
    t1,t2=st.tabs(["Clientes","Proveedores"])
    with t1:
        df=antiguedad_documentos(conn,"clientes")
        if df.empty: st.info("No hay saldos pendientes.")
        else:
            resumen=df.groupby("tramo",observed=False)["saldo"].sum().reindex(["0-30","31-60","61-90","+90"],fill_value=0).reset_index(); st.dataframe(resumen.rename(columns={"tramo":"Antigüedad","saldo":"Saldo"}),use_container_width=True,hide_index=True); st.dataframe(df[["entidad","fecha","folio","saldo","dias","tramo"]],use_container_width=True,hide_index=True)
    with t2:
        df=antiguedad_documentos(conn,"proveedores")
        if df.empty: st.info("No hay saldos pendientes.")
        else:
            resumen=df.groupby("tramo",observed=False)["saldo"].sum().reindex(["0-30","31-60","61-90","+90"],fill_value=0).reset_index(); st.dataframe(resumen.rename(columns={"tramo":"Antigüedad","saldo":"Saldo"}),use_container_width=True,hide_index=True); st.dataframe(df[["entidad","fecha","folio","saldo","dias","tramo"]],use_container_width=True,hide_index=True)

# ============================================================
# RCV COMPRAS
# ============================================================

elif menu == "🧾 Órdenes de compra":
    oc_pantalla(conn)

elif menu == "📥 RCV Compras":

    st.title("📥 Registro de Compras - SII")

    pestañas_compras = st.tabs(["📂 Cargar Archivo CSV", "📥 Plantilla Descargable y Carga de Excel", "🔄 Reclasificar contabilizadas", "📚 Recuperar RCV histórico", "🧾 Regularizar IVA histórico"])

    with pestañas_compras[0]:
        archivo = st.file_uploader(
            "Cargar RCV de Compras",
            type=["csv", "xlsx", "xls"],
            key="rcv_compras_file"
        )

        if archivo:
            try:
                archivo_hash = hash_archivo(archivo)
                previa = importacion_archivo_existente(conn,"RCV_COMPRAS",archivo_hash)
                if previa:
                    st.error(f"⚠️ Este mismo RCV de Compras ya fue procesado el {previa['fecha_hora']} ({previa['nombre_archivo']}). SGCI bloqueó la recarga.")
                    st.session_state.pop("rcv_compras",None); st.session_state.pop("rcv_compras_archivo",None)
                else:
                    df_original = leer_archivo_tabular(archivo)
                    sgci_exito(f"Archivo leído: {len(df_original):,} filas")
                    df = normalizar_rcv(df_original,"compras")
                    df = preparar_documentos(conn,df,"compras")
                    st.session_state["rcv_compras"] = df
                    st.session_state["rcv_compras_archivo"]={"nombre":archivo.name,"hash":archivo_hash,"leidos":len(df_original)}
            except Exception as e:
                st.error(f"Error: {e}")

    with pestañas_compras[1]:
        st.info("Descarga la plantilla modelo, rellénala en tu Excel con tus compras y súbela aquí adjunta para procesarla de inmediato.")

        df_plantilla_modelo = pd.DataFrame([
            {
                "tipo_doc": 33,
                "folio": "147039",
                "fecha_doc": str(date.today()),
                "rut": "76123456-7",
                "razon_social": "PROVEEDOR EJEMPLO SPA",
                "exento": 0.0,
                "neto": 130125.0,
                "iva": 24724.0,
                "total": 154849.0
            }
        ])

        csv_plantilla = df_plantilla_modelo.to_csv(index=False, sep=";").encode("utf-8-sig")

        st.download_button(
            label="📥 Descargar Plantilla Modelo (CSV/Excel)",
            data=csv_plantilla,
            file_name="plantilla_rcv_compras.csv",
            mime="text/csv",
            type="secondary"
        )

        st.divider()

        archivo_subido = st.file_uploader(
            "Adjuntar Plantilla Rellenada",
            type=["csv"],
            key="archivo_plantilla_compras"
        )

        if archivo_subido:
            try:
                df_subido = leer_archivo_tabular(archivo_subido)
                df_prep = df_subido.copy()
                df_prep["fecha_doc"] = df_prep["fecha_doc"].apply(fecha_iso)
                df_prep["neto"] = df_prep["neto"].apply(numero)
                df_prep["iva"] = df_prep["iva"].apply(numero)
                df_prep["exento"] = df_prep["exento"].apply(numero)
                df_prep["total"] = df_prep["total"].apply(numero)
                df_prep["iva_no_rec"] = 0.0
                df_prep["neto_af"] = 0.0
                df_prep["iva_af"] = 0.0
                df_prep["iva_uso_comun"] = 0.0
                df_prep["fecha_recepcion"] = df_prep["fecha_doc"]
                df_prep["ref_type"] = None
                df_prep["ref_folio"] = ""

                archivo_hash = hash_archivo(archivo_subido)
                previa = importacion_archivo_existente(conn,"RCV_COMPRAS",archivo_hash)
                if previa:
                    st.error(f"⚠️ Esta misma plantilla ya fue procesada el {previa['fecha_hora']}. SGCI bloqueó la recarga.")
                    st.session_state.pop("rcv_compras",None); st.session_state.pop("rcv_compras_archivo",None)
                else:
                    df_procesado = preparar_documentos(conn,df_prep,"compras")
                    st.session_state["rcv_compras"] = df_procesado
                    st.session_state["rcv_compras_archivo"]={"nombre":archivo_subido.name,"hash":archivo_hash,"leidos":len(df_subido)}
                    sgci_exito("¡Plantilla adjuntada y procesada con éxito! Revisa la bandeja de revisión abajo.")
            except Exception as e:
                st.error(f"Error procesando la plantilla adjunta: {e}")


    with pestañas_compras[2]:
        st.subheader("🔄 Reclasificar compras ya contabilizadas")
        st.caption("Genera un asiento de reclasificación. No modifica IVA Crédito Fiscal ni Proveedores y mantiene el documento original.")

        compras_reclas = compras_para_reclasificar(conn)
        if compras_reclas.empty:
            st.info("No hay compras contabilizadas para reclasificar.")
        else:
            filtro = st.text_input("Buscar por proveedor, RUT o folio", key="buscar_reclas_compra")
            vista = compras_reclas.copy()
            if filtro.strip():
                q = filtro.strip().lower()
                mascara = (
                    vista["proveedor"].fillna("").astype(str).str.lower().str.contains(q, regex=False)
                    | vista["rut"].fillna("").astype(str).str.lower().str.contains(q, regex=False)
                    | vista["folio"].fillna("").astype(str).str.lower().str.contains(q, regex=False)
                )
                vista = vista[mascara].copy()

            vista["Seleccionar"] = False
            vista["Neto"] = vista["monto_neto"].apply(money)
            vista["Total"] = vista["monto_total"].apply(money)
            editor = st.data_editor(
                vista[["Seleccionar", "compra_id", "fecha", "rut", "proveedor", "tipo_doc", "folio", "Neto", "Total", "cuenta_gasto"]].rename(columns={
                    "compra_id":"ID", "fecha":"Fecha", "rut":"RUT", "proveedor":"Proveedor", "tipo_doc":"Tipo", "folio":"Folio", "cuenta_gasto":"Cuenta actual"
                }),
                use_container_width=True,
                hide_index=True,
                disabled=["ID","Fecha","RUT","Proveedor","Tipo","Folio","Neto","Total","Cuenta actual"],
                key="editor_reclas_compras"
            )

            seleccionados = editor.loc[editor["Seleccionar"] == True, "ID"].astype(int).tolist()
            opciones_reclas = cuentas_imputables(conn)
            etiquetas_reclas = opciones_reclas["etiqueta"].tolist()
            nueva_etiqueta = st.selectbox("Nueva cuenta contable", etiquetas_reclas, key="nueva_cuenta_reclas")
            nueva_codigo = nueva_etiqueta.split(" - ", 1)[0]
            recordar = st.checkbox("Usar esta cuenta para futuras compras de estos proveedores", value=False, key="recordar_reclas")

            if seleccionados:
                st.info(f"{len(seleccionados)} compra(s) seleccionada(s). Se generará un asiento de reclasificación por cada documento.")
            confirmar = st.checkbox("Confirmo la reclasificación contable seleccionada", key="confirmar_reclas")
            if st.button("🔄 RECLASIFICAR COMPRAS", type="primary", disabled=(not seleccionados or not confirmar), key="btn_reclas_compras"):
                sgci_exigir_permiso(conn, 'cxp', 'editar', 'RCV Compras')
                try:
                    r = reclasificar_compras(conn, seleccionados, nueva_codigo, recordar)
                    sgci_exito(f"Reclasificación completada: {r['reclasificadas']} compra(s). Omitidas: {r['omitidas']}.")
                    st.rerun()
                except Exception as e:
                    st.error(f"No fue posible reclasificar: {e}")

    if "rcv_compras" in st.session_state and isinstance(st.session_state["rcv_compras"], pd.DataFrame):

        df = st.session_state["rcv_compras"].copy()

        st.divider()
        st.subheader("Resumen de importación")

        # Criterio corregido considerando el signo (-1 para NC)
        total = (df["total"] * df["signo"]).sum()
        neto = (df["neto"] * df["signo"]).sum()
        iva = (df["iva"] * df["signo"]).sum()

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Documentos", len(df))
        c2.metric("Neto", money(neto))
        c3.metric("IVA", money(iva))
        c4.metric("Total", money(total))

        st.divider()
        st.subheader("Bandeja de revisión")

        columnas = [
            "estado",
            "fecha_doc",
            "rut",
            "razon_social",
            "tipo_doc",
            "folio",
            "neto",
            "iva",
            "total",
            "cuenta_codigo",
            "cuenta_origen",
            "observaciones",
        ]

        mostrar = df[[c for c in columnas if c in df.columns]].copy()
        mostrar = mostrar.rename(
            columns={
                "estado": "Estado",
                "fecha_doc": "Fecha",
                "rut": "RUT",
                "razon_social": "Proveedor",
                "tipo_doc": "Tipo",
                "folio": "Folio",
                "neto": "Neto",
                "iva": "IVA",
                "total": "Total",
                "cuenta_codigo": "Cuenta",
                "cuenta_origen": "Origen cuenta",
                "observaciones": "Observaciones",
            }
        )

        st.dataframe(mostrar, use_container_width=True, hide_index=True)

        st.divider()
        st.subheader("Revisión y asignación de cuentas")

        opciones = cuentas_imputables(conn)
        etiquetas = opciones["etiqueta"].tolist()

        for i in range(len(df)):
            estado = df.loc[i, "estado"]
            if estado.startswith("🔁") or estado.startswith("❌") or estado.startswith("⚠️"):
                continue

            cuenta_actual = df.loc[i, "cuenta_codigo"]
            if cuenta_actual in opciones["codigo"].values:
                indice = opciones["codigo"].tolist().index(cuenta_actual)
            else:
                indice = 0

            nueva = st.selectbox(
                f"{df.loc[i, 'fecha_doc']} | {df.loc[i, 'razon_social']} | Doc. {df.loc[i, 'folio']}",
                etiquetas,
                index=indice,
                key=f"compra_cta_{i}"
            )

            codigo = nueva.split(" - ", 1)[0]
            df.loc[i, "cuenta_codigo"] = codigo

        st.session_state["rcv_compras"] = df

        validos = df[df["estado"].isin(["🟢 Nuevo", "🟡 Revisar cuenta"])].copy()

        st.divider()

        if not validos.empty:
            st.warning(f"{len(validos)} documento(s) listos para contabilizar.")

            if st.button("✅ CONTABILIZAR COMPRAS", type="primary"):
                sgci_exigir_permiso(conn, 'cxp', 'contabilizar', 'RCV Compras')
                try:
                    resultado = contabilizar_rcv(conn,"compras",validos)
                    meta=st.session_state.get("rcv_compras_archivo")
                    if meta:
                        duplicados=int(df["estado"].astype(str).str.startswith("🔁").sum())
                        registrar_importacion_archivo(conn,"RCV_COMPRAS",meta["nombre"],meta["hash"],resultado.get("lote"),meta["leidos"],resultado["documentos"],duplicados)
                    sgci_exito(f"Se contabilizaron {resultado['documentos']} documentos. Los documentos ya existentes fueron omitidos.")
                    st.session_state.pop("rcv_compras",None); st.session_state.pop("rcv_compras_archivo",None)
                except Exception as e:
                    st.error(f"No se contabilizó el lote: {e}")


    with pestañas_compras[3]:
        st.subheader("📚 Recuperar datos tributarios desde RCV histórico")
        st.caption(
            "Sube aquí un RCV Compras ORIGINAL del SII ya contabilizado. "
            "SGCI lo cruza por RUT + tipo de documento + folio y recupera neto, "
            "exento, IVA recuperable, IVA no recuperable y activo fijo. "
            "Esta operación NO crea compras ni asientos y NO toca Proveedores, Banco o pagos."
        )
        archivo_hist = st.file_uploader(
            "RCV Compras histórico original (CSV, XLSX o XLS)",
            type=["csv","xlsx","xls"],
            key="rcv_compras_historico_recuperar"
        )
        if archivo_hist:
            try:
                df_hist_original = leer_archivo_tabular(archivo_hist)
                df_hist_norm = normalizar_rcv(df_hist_original,"compras")
                cruces_hist, faltantes_hist = cruzar_rcv_historico_compras(conn,df_hist_norm,devolver_no_encontrados=True)
                total_archivo=len(df_hist_norm)
                encontrados=len(cruces_hist)
                c1,c2,c3=st.columns(3)
                c1.metric("Documentos en RCV",f"{total_archivo:,}".replace(",","."))
                c2.metric("Coincidencias SGCI",f"{encontrados:,}".replace(",","."))
                c3.metric("Sin coincidencia",f"{len(faltantes_hist):,}".replace(",","."))
                if not faltantes_hist.empty:
                    st.warning(
                        f"⚠️ {len(faltantes_hist)} documento(s) del RCV no fueron encontrados en SGCI. "
                        "Estos documentos NO serán modificados ni recuperados automáticamente."
                    )
                    st.markdown("#### ⚠️ Documentos del RCV no encontrados en SGCI")
                    columnas_faltantes=["rut","tipo_doc","folio","proveedor","neto_rcv","exento_rcv","iva_rcv","iva_no_rec_rcv","total_rcv"]
                    st.dataframe(
                        faltantes_hist[[c for c in columnas_faltantes if c in faltantes_hist.columns]],
                        use_container_width=True,
                        hide_index=True
                    )
                if cruces_hist.empty:
                    st.warning("No encontré documentos coincidentes. Revisa que sea el RCV de la misma empresa/período.")
                else:
                    vista=cruces_hist[["rut","tipo_doc","folio","proveedor","neto_rcv","exento_rcv","iva_rcv","iva_no_rec_rcv","total_rcv"]].copy()
                    st.dataframe(vista,use_container_width=True,hide_index=True)
                    total_iva_real=float(cruces_hist["iva_rcv"].abs().sum()+cruces_hist["iva_af_rcv"].abs().sum())
                    st.info(f"IVA recuperable real identificado en este archivo: {money(total_iva_real)}")
                    conf_rec=st.checkbox(
                        "Confirmo que este es un RCV Compras original del SII y deseo recuperar únicamente sus datos tributarios.",
                        key="conf_recuperar_rcv_hist"
                    )
                    if st.button("📚 Recuperar datos tributarios",type="primary",disabled=not conf_rec,key="btn_recuperar_rcv_hist"):
                        sgci_exigir_permiso(conn, 'cxp', 'editar', 'RCV Compras')
                        try:
                            res=recuperar_datos_tributarios_rcv(conn,cruces_hist)
                            if res["actualizados"] == res["verificados"] and not res["errores"]:
                                sgci_exito(
                                    f"✅ {res['verificados']} documento(s) actualizados y verificados en SQLite. "
                                    f"IVA recuperable guardado: {money(res['iva'])}. "
                                    "No se generaron asientos contables."
                                )
                                st.info(
                                    "Ahora puedes abrir «Regularizar IVA histórico». "
                                    "Estos documentos deben aparecer con fuente «RCV original SII»."
                                )
                            else:
                                st.error(
                                    f"Se intentaron actualizar {res['actualizados']} documentos, pero solo "
                                    f"{res['verificados']} pudieron verificarse. No continúes con la regularización."
                                )
                                if res["errores"]:
                                    st.write(res["errores"][:20])
                        except Exception as e:
                            st.error(f"No se pudieron guardar/verificar los datos tributarios: {e}")
            except Exception as e:
                st.error(f"No se pudo procesar el RCV histórico: {e}")

    with pestañas_compras[4]:
        st.subheader("🧾 Regularizar IVA Crédito Fiscal de compras ya contabilizadas")
        st.caption(
            "Detecta compras RCV históricas que fueron contabilizadas sin movimiento "
            "en 1.1.03.02 IVA Crédito Fiscal. La corrección se hace mediante asientos "
            "de reclasificación auditables; no modifica Proveedores, Banco ni los asientos originales."
        )

        pendientes_iva = compras_pendientes_regularizar_iva(conn)
        if pendientes_iva.empty:
            sgci_exito("No hay compras históricas pendientes de regularizar en IVA Crédito Fiscal.")
        else:
            total_iva_pend = float(pendientes_iva["iva"].abs().sum())
            civa1,civa2 = st.columns(2)
            civa1.metric("Documentos a regularizar", f"{len(pendientes_iva):,}".replace(",","."))
            civa2.metric("IVA identificado", money(total_iva_pend))
            columnas_auditoria = [
                "fecha","tipo_doc","folio","rut","proveedor",
                "monto_neto","iva","monto_total","fuente_iva",
                "codigo_cuenta_actual","cuenta_gasto"
            ]
            st.dataframe(
                pendientes_iva[[c for c in columnas_auditoria if c in pendientes_iva.columns]],
                use_container_width=True,
                hide_index=True
            )
            reconstruidos = int((pendientes_iva.get("fuente_iva", pd.Series(dtype=str)) == "Reconstruido 19/119").sum())
            if reconstruidos:
                st.warning(
                    f"{reconstruidos} documento(s) no conservan el IVA histórico en la base y "
                    "SGCI lo reconstruyó como 19/119 del total. Revísalos especialmente antes de confirmar."
                )
            sin_cuenta = pendientes_iva[pendientes_iva.get("codigo_cuenta_actual","").astype(str).str.strip() == ""]
            if not sin_cuenta.empty:
                st.error(
                    f"{len(sin_cuenta)} documento(s) no tienen cuenta actual identificable. "
                    "No ejecutes la regularización hasta corregirlos."
                )
            confirma_iva_hist = st.checkbox(
                "Confirmo que deseo generar la regularización histórica del IVA Crédito Fiscal.",
                key="conf_regularizar_iva_hist"
            )
            if st.button(
                "🧾 Regularizar IVA Crédito Fiscal",
                type="primary",
                disabled=(not confirma_iva_hist) or (not sin_cuenta.empty),
                key="btn_regularizar_iva_hist"
            ):
                sgci_exigir_permiso(conn, 'cxp', 'contabilizar', 'RCV Compras')
                try:
                    res_iva = regularizar_iva_historico_compras(conn)
                    sgci_exito(
                        f"Regularización completada: {res_iva['documentos']} documento(s) · "
                        f"IVA neto {money(res_iva['iva'])} · Lote {res_iva['lote']}."
                    )
                    st.rerun()
                except Exception as e:
                    st.error(f"No se pudo regularizar el IVA histórico: {e}")

    st.divider()
    st.subheader("Historial RCV Compras")
    mostrar_historial_rcv_completo(conn, "compras")


# ============================================================
# RCV VENTAS
# ============================================================

elif menu == "📤 RCV Ventas":

    st.title("📤 Registro de Ventas - SII")

    archivo = st.file_uploader(
        "Cargar RCV de Ventas",
        type=["csv"],
        key="rcv_ventas_file"
    )

    if archivo:
        try:
            archivo_hash=hash_archivo(archivo)
            previa=importacion_archivo_existente(conn,"RCV_VENTAS",archivo_hash)
            if previa:
                st.error(f"⚠️ Este mismo RCV de Ventas ya fue procesado el {previa['fecha_hora']} ({previa['nombre_archivo']}). SGCI bloqueó la recarga.")
                st.session_state.pop("rcv_ventas",None); st.session_state.pop("rcv_ventas_archivo",None)
            else:
                df_original=leer_archivo_tabular(archivo)
                df=normalizar_rcv(df_original,"ventas")
                df=preparar_documentos(conn,df,"ventas")
                st.session_state["rcv_ventas"]=df
                st.session_state["rcv_ventas_archivo"]={"nombre":archivo.name,"hash":archivo_hash,"leidos":len(df_original)}
                sgci_exito(f"{len(df):,} documentos encontrados.")
        except Exception as e:
            st.error(f"Error: {e}")

    if "rcv_ventas" in st.session_state and isinstance(st.session_state["rcv_ventas"], pd.DataFrame):

        df = st.session_state["rcv_ventas"].copy()

        # Criterio corregido considerando el signo (-1 para NC)
        total_v = (df["total"] * df["signo"]).sum()
        neto_v = (df["neto"] * df["signo"]).sum()
        iva_v = (df["iva"] * df["signo"]).sum()

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Documentos", len(df))
        c2.metric("Neto", money(neto_v))
        c3.metric("IVA", money(iva_v))
        c4.metric("Total", money(total_v))

        st.divider()
        st.subheader("Bandeja de revisión")

        mostrar = df[
            [
                "estado",
                "fecha_doc",
                "rut",
                "razon_social",
                "tipo_doc",
                "folio",
                "neto",
                "iva",
                "total",
                "cuenta_codigo",
                "cuenta_origen",
                "observaciones",
            ]
        ].rename(
            columns={
                "estado": "Estado",
                "fecha_doc": "Fecha",
                "rut": "RUT",
                "razon_social": "Cliente",
                "tipo_doc": "Tipo",
                "folio": "Folio",
                "neto": "Neto",
                "iva": "IVA",
                "total": "Total",
                "cuenta_codigo": "Cuenta",
                "cuenta_origen": "Origen cuenta",
                "observaciones": "Observaciones",
            }
        )

        st.dataframe(mostrar, use_container_width=True, hide_index=True)

        st.subheader("Asignación de cuentas de ingreso")

        opciones = cuentas_imputables(conn)
        etiquetas = opciones["etiqueta"].tolist()

        for i in range(len(df)):
            estado = df.loc[i, "estado"]
            if estado.startswith("🔁") or estado.startswith("❌") or estado.startswith("⚠️"):
                continue

            actual = df.loc[i, "cuenta_codigo"]
            if actual in opciones["codigo"].values:
                indice = opciones["codigo"].tolist().index(actual)
            else:
                indice = 0

            nueva = st.selectbox(
                f"{df.loc[i, 'fecha_doc']} | {df.loc[i, 'razon_social']} | Doc. {df.loc[i, 'folio']}",
                etiquetas,
                index=indice,
                key=f"venta_cta_{i}"
            )

            df.loc[i, "cuenta_codigo"] = nueva.split(" - ", 1)[0]

        st.session_state["rcv_ventas"] = df

        validos = df[df["estado"].isin(["🟢 Nuevo", "🟡 Revisar cuenta"])].copy()

        if not validos.empty:
            if st.button("✅ CONTABILIZAR VENTAS", type="primary"):
                sgci_exigir_permiso(conn, 'cxc', 'contabilizar', 'RCV Ventas')
                try:
                    resultado=contabilizar_rcv(conn,"ventas",validos)
                    meta=st.session_state.get("rcv_ventas_archivo")
                    if meta:
                        duplicados=int(df["estado"].astype(str).str.startswith("🔁").sum())
                        registrar_importacion_archivo(conn,"RCV_VENTAS",meta["nombre"],meta["hash"],resultado.get("lote"),meta["leidos"],resultado["documentos"],duplicados)
                    sgci_exito(f"Se contabilizaron {resultado['documentos']} documentos. Los documentos ya existentes fueron omitidos.")
                    st.session_state.pop("rcv_ventas",None); st.session_state.pop("rcv_ventas_archivo",None)
                except Exception as e:
                    st.error(f"No se contabilizó el lote: {e}")

    st.divider()
    st.subheader("Historial RCV Ventas")
    mostrar_historial_rcv_completo(conn, "ventas")


# ============================================================
# ASIENTOS MANUALES Y SALDOS INICIALES
# ============================================================

elif menu == "✍️ Asientos y Saldos":

    st.title("✍️ Asientos Manuales y Saldos Iniciales")

    # ------------------------------------------------------------
    # COMPENSACIÓN MENSUAL IVA / F29
    # ------------------------------------------------------------
    conn.execute("""
        CREATE TABLE IF NOT EXISTS compensaciones_iva_f29 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            periodo TEXT NOT NULL UNIQUE,
            fecha_contable TEXT NOT NULL,
            iva_debito REAL NOT NULL DEFAULT 0,
            iva_credito REAL NOT NULL DEFAULT 0,
            iva_por_pagar REAL NOT NULL DEFAULT 0,
            asiento_id INTEGER,
            creado_en TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()

    with st.expander("🧾 Compensación mensual IVA / F29", expanded=False):
        def _f29_clp(valor):
            return "$" + f"{clp_round(valor):,.0f}".replace(",", ".")

        st.caption(
            "Úsalo mes por mes para cerrar el IVA del período. SGCI debita IVA Débito Fiscal, "
            "abona IVA Crédito Fiscal utilizado y lleva la diferencia a IVA por pagar. "
            "No mueve Banco ni registra el pago del F29."
        )

        periodo_f29 = st.text_input("Período tributario (AAAA-MM)", value="2026-01", key="f29_periodo")
        fecha_f29 = st.date_input("Fecha contable del cierre", key="f29_fecha")
        c1,c2,c3 = st.columns(3)
        with c1:
            debito_f29 = st.number_input("IVA Débito Fiscal del período", min_value=0, step=1, value=0, key="f29_debito")
        with c2:
            credito_f29 = st.number_input("IVA Crédito Fiscal utilizado", min_value=0, step=1, value=0, key="f29_credito")
        iva_pagar_f29 = max(clp_round(debito_f29 - credito_f29),0)
        with c3:
            st.metric("IVA por pagar determinado", _f29_clp(iva_pagar_f29))

        existe_f29 = conn.execute(
            "SELECT id, asiento_id FROM compensaciones_iva_f29 WHERE periodo=?",
            (periodo_f29.strip(),)
        ).fetchone() if periodo_f29.strip() else None

        if credito_f29 > debito_f29:
            st.warning("El crédito fiscal supera al débito. Este formulario está diseñado para períodos con IVA por pagar; no contabilices hasta revisar el remanente.")
        elif existe_f29:
            st.warning(f"El período {periodo_f29} ya fue compensado en el asiento {existe_f29[1]}. SGCI bloquea una segunda contabilización.")
        elif debito_f29 > 0:
            st.info(
                f"Asiento que se generará: Debe IVA Débito Fiscal {_f29_clp(debito_f29)} · "
                f"Haber IVA Crédito Fiscal {_f29_clp(credito_f29)} · Haber IVA por pagar {_f29_clp(iva_pagar_f29)}."
            )

        confirma_f29 = st.checkbox(
            "Confirmo que estos valores corresponden al F29 del período indicado.",
            key="f29_confirma"
        )
        if st.button("🧾 Registrar compensación IVA / F29", type="primary", key="f29_registrar"):
            sgci_exigir_permiso(conn, 'contabilidad', 'contabilizar', 'Asientos y Saldos')
            if not periodo_f29.strip() or len(periodo_f29.strip()) != 7:
                st.error("Indica el período en formato AAAA-MM.")
            elif existe_f29:
                st.error("Ese período ya fue compensado. No se generó ningún asiento.")
            elif debito_f29 <= 0:
                st.error("El IVA Débito Fiscal debe ser mayor que cero.")
            elif credito_f29 > debito_f29:
                st.error("El crédito fiscal supera al débito. Este caso requiere tratamiento de remanente y no se registró automáticamente.")
            elif not confirma_f29:
                st.error("Debes confirmar los valores antes de contabilizar.")
            else:
                asiento = siguiente_asiento(conn) + 1
                fecha_iso_f29 = fecha_f29.strftime("%Y-%m-%d")
                glosa_f29 = f"Compensación IVA F29 período {periodo_f29.strip()}"
                try:
                    cur=conn.cursor()
                    cur.execute("BEGIN")
                    lineas=[
                        ("2.1.01.02","IVA Débito Fiscal",float(debito_f29),0.0),
                    ]
                    if credito_f29 > 0:
                        lineas.append(("1.1.03.02","IVA Crédito Fiscal",0.0,float(credito_f29)))
                    if iva_pagar_f29 > 0:
                        lineas.append(("2.1.01.03","IVA por pagar",0.0,float(iva_pagar_f29)))
                    for codigo,cuenta,debe,haber in lineas:
                        cur.execute("""
                            INSERT INTO libro_diario
                            (fecha,cuenta,debe,haber,glosa,centro_costo,codigo_cuenta,asiento_id,lote_id,origen)
                            VALUES (?,?,?,?,?,?,?,?,?,?)
                        """,(fecha_iso_f29,cuenta,debe,haber,glosa_f29,"General / Ninguno",codigo,asiento,
                             f"F29-{periodo_f29.strip()}","Compensación IVA F29"))
                    cur.execute("""
                        INSERT INTO compensaciones_iva_f29
                        (periodo,fecha_contable,iva_debito,iva_credito,iva_por_pagar,asiento_id)
                        VALUES (?,?,?,?,?,?)
                    """,(periodo_f29.strip(),fecha_iso_f29,float(debito_f29),float(credito_f29),float(iva_pagar_f29),asiento))
                    conn.commit()
                    sgci_exito(f"Compensación registrada. Asiento {asiento}. IVA por pagar: {_f29_clp(iva_pagar_f29)}")
                    st.rerun()
                except Exception as e:
                    conn.rollback()
                    st.error(f"No se pudo registrar la compensación: {e}")

        hist_f29=pd.read_sql_query("""
            SELECT periodo AS Período, fecha_contable AS Fecha,
                   iva_debito AS `IVA Débito`, iva_credito AS `IVA Crédito utilizado`,
                   iva_por_pagar AS `IVA por pagar`, asiento_id AS Asiento
            FROM compensaciones_iva_f29 ORDER BY periodo DESC
        """,conn)
        if not hist_f29.empty:
            st.markdown("#### Historial de compensaciones")
            st.dataframe(hist_f29,use_container_width=True,hide_index=True)

    # ============================================================
    # NUEVO: ASIENTO MANUAL DIRECTAMENTE EN PANTALLA
    # ============================================================
    st.subheader("🖊️ Nuevo asiento manual en pantalla")
    st.caption("Registra ajustes y reclasificaciones sin CSV. El asiento original no se modifica.")
    plan_manual = Plan(conn)
    opciones_manual = [f"{c} - {n}" for c, n in plan_manual.hojas.items()]
    if len(opciones_manual) < 2:
        st.warning("Necesitas al menos dos cuentas imputables en el plan de cuentas.")
    else:
        ejemplo_manual = pd.DataFrame([
            {"Cuenta": "", "Debe": 0, "Haber": 0},
            {"Cuenta": "", "Debe": 0, "Haber": 0},
        ])
        with st.form("sgci_asiento_manual_form", clear_on_submit=False):
            fecha_manual = st.date_input("Fecha contable", value=date.today(), key="sgci_manual_fecha")
            glosa_manual = st.text_input("Glosa del asiento", key="sgci_manual_glosa",
                                         placeholder="Ej.: Reclasificación pago Previred, asiento 824")
            centro_manual = st.text_input("Centro de costo", value="General / Ninguno",
                                          key="sgci_manual_centro")
            st.caption("Agrega o elimina filas. Selecciona cuentas imputables del plan; ingresa importes en pesos, sin puntos de miles.")
            lineas_manual = st.data_editor(
                ejemplo_manual, num_rows="dynamic", hide_index=True,
                use_container_width=True, key="sgci_manual_lineas",
                column_config={
                    "Cuenta": st.column_config.SelectboxColumn(
                        "Cuenta contable", options=opciones_manual, required=True, width="large"),
                    "Debe": st.column_config.NumberColumn("Debe ($)", min_value=0, step=1, format="%d"),
                    "Haber": st.column_config.NumberColumn("Haber ($)", min_value=0, step=1, format="%d"),
                },
            )
            validar_manual = st.form_submit_button("🔎 Validar y previsualizar", type="primary")

        if validar_manual:
            errores_manual = []
            fecha_str_manual = fecha_manual.strftime("%Y-%m-%d")
            if not glosa_manual.strip():
                errores_manual.append("La glosa es obligatoria.")
            if periodo_cerrado(conn, fecha_str_manual):
                errores_manual.append("El período contable está cerrado.")
            detalle_manual = []
            for idx, fila in lineas_manual.iterrows():
                cuenta_et = str(fila.get("Cuenta") or "").strip()
                debe_raw = fila.get("Debe", 0)
                haber_raw = fila.get("Haber", 0)
                try:
                    debe_val = float(debe_raw) if pd.notna(debe_raw) else 0.0
                    haber_val = float(haber_raw) if pd.notna(haber_raw) else 0.0
                except (ValueError, TypeError):
                    errores_manual.append(f"Fila {idx+1}: importe no válido.")
                    continue
                if not cuenta_et and debe_val == 0 and haber_val == 0:
                    continue
                cuenta_res = plan_manual.resolver(cuenta_et)
                if cuenta_res is None:
                    errores_manual.append(f"Fila {idx+1}: selecciona una cuenta imputable válida.")
                if not (0 <= debe_val < 1e15 and 0 <= haber_val < 1e15):
                    errores_manual.append(f"Fila {idx+1}: importe fuera de rango.")
                if debe_val > 0 and haber_val > 0:
                    errores_manual.append(f"Fila {idx+1}: no puede haber Debe y Haber simultáneos.")
                if debe_val == 0 and haber_val == 0:
                    errores_manual.append(f"Fila {idx+1}: debe existir un importe.")
                if debe_val != int(debe_val) or haber_val != int(haber_val):
                    errores_manual.append(f"Fila {idx+1}: usa pesos enteros.")
                if cuenta_res:
                    detalle_manual.append((cuenta_res[0], cuenta_res[1], int(debe_val), int(haber_val)))
            total_debe = sum(r[2] for r in detalle_manual)
            total_haber = sum(r[3] for r in detalle_manual)
            if len(detalle_manual) < 2:
                errores_manual.append("El asiento necesita al menos dos líneas válidas.")
            if total_debe <= 0 or total_haber <= 0 or total_debe != total_haber:
                errores_manual.append("El asiento debe cuadrar y tener Debe y Haber mayores que cero.")
            if errores_manual:
                st.session_state.pop("sgci_manual_borrador_validado", None)
                for err in errores_manual:
                    st.error(err)
            else:
                st.session_state["sgci_manual_borrador_validado"] = {
                    "fecha": fecha_str_manual, "glosa": glosa_manual.strip(),
                    "centro": centro_manual.strip() or "General / Ninguno",
                    "detalle": detalle_manual,
                }

        borrador_manual = st.session_state.get("sgci_manual_borrador_validado")
        if borrador_manual:
            st.markdown("**Vista previa del asiento (todavía sin guardar)**")
            vista_manual = pd.DataFrame(borrador_manual["detalle"],
                                        columns=["Código", "Cuenta", "Debe", "Haber"])
            st.dataframe(formatear_montos_df(vista_manual), use_container_width=True, hide_index=True)
            col_debe, col_haber, col_dif = st.columns(3)
            suma_debe = int(vista_manual["Debe"].sum())
            suma_haber = int(vista_manual["Haber"].sum())
            col_debe.metric("Debe", money(suma_debe))
            col_haber.metric("Haber", money(suma_haber))
            col_dif.metric("Diferencia", money(suma_debe - suma_haber))
            st.info("Revisa fecha, glosa y cuentas. No se generará movimiento de Banco salvo que incluyas esa cuenta.")
            confirmar_manual = st.checkbox("Confirmo que revisé el asiento y deseo contabilizarlo.",
                                           key="sgci_manual_confirmar")
            if st.button("✅ Contabilizar asiento manual", type="primary",
                         disabled=not confirmar_manual, key="sgci_manual_guardar"):
                sgci_exigir_permiso(conn, 'contabilidad', 'contabilizar', 'Asientos y Saldos')
                try:
                    # Revalidación de cierre y cuentas justo antes de escribir.
                    if periodo_cerrado(conn, borrador_manual["fecha"]):
                        raise ValueError("El período está cerrado.")
                    plan_actual = Plan(conn)
                    for cod, nombre, debe, haber in borrador_manual["detalle"]:
                        if cod not in plan_actual.hojas:
                            raise ValueError(f"La cuenta {cod} ya no es imputable.")
                    if sum(x[2] for x in borrador_manual["detalle"]) != sum(x[3] for x in borrador_manual["detalle"]):
                        raise ValueError("El asiento no cuadra.")
                    cur = conn.cursor()
                    cur.execute("BEGIN IMMEDIATE")
                    nuevo_asiento = int(cur.execute(
                        "SELECT COALESCE(MAX(asiento_id),0)+1 FROM libro_diario"
                    ).fetchone()[0])
                    lote_manual = "MANUAL-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f")
                    for cod, nombre, debe, haber in borrador_manual["detalle"]:
                        cur.execute("""INSERT INTO libro_diario
                            (fecha,cuenta,debe,haber,glosa,centro_costo,codigo_cuenta,asiento_id,lote_id,origen)
                            VALUES (?,?,?,?,?,?,?,?,?,?)""",
                            (borrador_manual["fecha"], nombre, debe, haber,
                             borrador_manual["glosa"], borrador_manual["centro"],
                             cod, nuevo_asiento, lote_manual, "Asiento manual"))
                    conn.commit()
                    registrar_auditoria(conn, "ASIENTO MANUAL EN PANTALLA",
                                       f"Asiento {nuevo_asiento}; fecha {borrador_manual['fecha']}; "
                                       f"glosa {borrador_manual['glosa']}; total {suma_debe}")
                    st.session_state.pop("sgci_manual_borrador_validado", None)
                    sgci_exito(f"Asiento manual N.º {nuevo_asiento} contabilizado correctamente.")
                    st.rerun()
                except Exception as exc:
                    conn.rollback()
                    st.error(f"No se pudo contabilizar: {exc}")

    st.divider()
    st.subheader("📥 Importación masiva de asientos por CSV")
    st.divider()
    st.info(
        """
        Sube una matriz en Excel (CSV) para registrar asientos manuales o cargar los saldos iniciales de tu plan de cuentas.
        Columnas requeridas: **fecha, codigo_cuenta, debe, haber, glosa** (Opcional: **asiento, centro_costo**).
        """
    )

    df_modelo_asiento = pd.DataFrame([
        {"fecha": "2026-01-01", "codigo_cuenta": "1.1.01", "debe": 500000.0, "haber": 0.0, "glosa": "Saldo inicial Caja", "asiento": 1, "centro_costo": "General / Ninguno"},
        {"fecha": "2026-01-01", "codigo_cuenta": "3.1.01", "debe": 0.0, "haber": 500000.0, "glosa": "Saldo inicial Capital", "asiento": 1, "centro_costo": "General / Ninguno"}
    ])
    csv_modelo_asiento = df_modelo_asiento.to_csv(index=False, sep=";").encode("utf-8-sig")

    st.download_button(
        label="📥 Descargar Plantilla de Asientos y Saldos",
        data=csv_modelo_asiento,
        file_name="plantilla_asientos_saldos.csv",
        mime="text/csv",
        type="secondary"
    )

    st.divider()
    st.subheader("Reporte de asientos manuales y saldos iniciales")
    df_rep_asientos = pd.read_sql_query("""
        SELECT fecha AS Fecha, asiento_id AS Asiento, codigo_cuenta AS Código,
               cuenta AS Cuenta, debe AS Debe, haber AS Haber, glosa AS Glosa,
               origen AS Origen
        FROM libro_diario
        WHERE origen IN ('Saldo inicial','Asiento manual')
        ORDER BY fecha DESC, asiento_id DESC, id DESC
    """, conn)
    if df_rep_asientos.empty:
        st.caption("Aún no existen asientos manuales o saldos iniciales para imprimir.")
    else:
        pdf = pdf_desde_dataframe("Asientos Manuales y Saldos Iniciales","SGCI - Sistema de Gestión Contable Integral",df_rep_asientos,{"Debe","Haber"})
        st.download_button("🖨️ Imprimir / PDF Asientos y Saldos",pdf,"asientos_y_saldos.pdf","application/pdf",key="pdf_asientos_saldos")

    tipo_carga = st.radio("Seleccione el origen del lote", ["Saldo inicial", "Asiento manual"])
    archivo_asiento = st.file_uploader("Adjuntar matriz rellenada", type=["csv"], key="subir_asientos")

    if archivo_asiento:
        try:
            df = leer_csv(archivo_asiento)
            df.columns = [str(c).strip().lower() for c in df.columns]

            obligatorias = ["fecha", "codigo_cuenta", "debe", "haber", "glosa"]
            faltantes = [c for c in obligatorias if c not in df.columns]

            if faltantes:
                st.error("Faltan columnas obligatorias: " + ", ".join(faltantes))
            else:
                plan = Plan(conn)
                resultado = pd.DataFrame()

                resultado["fecha"] = df["fecha"].apply(fecha_iso)
                resultado["cuenta_original"] = df["codigo_cuenta"].astype(str).str.strip()

                resuelto = resultado["cuenta_original"].apply(plan.resolver)
                resultado["codigo"] = resuelto.apply(lambda x: x[0] if x else None)
                resultado["cuenta"] = resuelto.apply(lambda x: x[1] if x else None)
                resultado["debe"] = df["debe"].apply(numero)
                resultado["haber"] = df["haber"].apply(numero)
                resultado["glosa"] = df["glosa"].fillna("").astype(str)

                resultado["centro_costo"] = df["centro_costo"].fillna("General / Ninguno") if "centro_costo" in df.columns else "General / Ninguno"
                resultado["asiento"] = pd.to_numeric(df["asiento"], errors="coerce") if "asiento" in df.columns else 1

                errores = []
                for i, fila in resultado.iterrows():
                    if not fila["fecha"]:
                        errores.append(f"Línea {i+2}: fecha inválida.")
                    if not fila["codigo"]:
                        errores.append(f"Línea {i+2}: cuenta '{fila['cuenta_original']}' no encontrada en el plan.")
                    if fila["debe"] > 0 and fila["haber"] > 0:
                        errores.append(f"Línea {i+2}: Debe y Haber simultáneos.")
                    if fila["debe"] == 0 and fila["haber"] == 0:
                        errores.append(f"Línea {i+2}: Debe y Haber están en cero.")

                for asiento_id, grupo in resultado.groupby("asiento"):
                    if abs(grupo["debe"].sum() - grupo["haber"].sum()) > 0.01:
                        errores.append(f"Asiento {asiento_id}: descuadrado (Debe={grupo['debe'].sum()}, Haber={grupo['haber'].sum()}).")

                if errores:
                    st.error("Se encontraron errores en la matriz:\n\n" + "\n".join(errores[:30]))
                else:
                    sgci_exito("¡Matriz validada y cuadrada correctamente!")
                    st.dataframe(resultado, use_container_width=True, hide_index=True)

                    if st.button("✅ REGISTRAR EN LIBRO DIARIO", type="primary"):
                        sgci_exigir_permiso(conn, 'contabilidad', 'contabilizar', 'Asientos y Saldos')
                        prefix = "SALDO-INI-" if tipo_carga == "Saldo inicial" else "ASIENTOS-MAN-"
                        lote = prefix + datetime.now().strftime("%Y%m%d-%H%M%S")
                        cur = conn.cursor()
                        base = siguiente_asiento(conn)

                        mapa_asientos = {
                            n: i + 1
                            for i, n in enumerate(sorted(resultado["asiento"].unique()))
                        }

                        try:
                            for fila in resultado.itertuples():
                                asiento = base + mapa_asientos[fila.asiento]
                                cur.execute(
                                    """
                                    INSERT INTO libro_diario
                                    (
                                        fecha,
                                        cuenta,
                                        debe,
                                        haber,
                                        glosa,
                                        centro_costo,
                                        codigo_cuenta,
                                        asiento_id,
                                        lote_id,
                                        origen
                                    )
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                    """,
                                    (
                                        fila.fecha,
                                        fila.cuenta,
                                        fila.debe,
                                        fila.haber,
                                        fila.glosa,
                                        fila.centro_costo,
                                        fila.codigo,
                                        asiento,
                                        lote,
                                        tipo_carga
                                    )
                                )

                            conn.commit()
                            sgci_exito(f"¡Registrado con éxito! Lote generado: {lote}")
                        except Exception as e:
                            conn.rollback()
                            st.error(f"Error al guardar: {e}")

        except Exception as e:
            st.error(f"Error leyendo el archivo: {e}")


# ============================================================
# CLIENTES
# ============================================================

elif menu == "👥 Clientes":

    st.title("👥 Clientes")

    # Radio conserva selección al ejecutar de nuevo Streamlit.
    sgci_vista_cliente = st.radio('Sección', ['Listado','Estado de cuenta','Nuevo cliente'],
                                horizontal=True,key='sgci_vista_cliente',label_visibility='collapsed')

    if sgci_vista_cliente == "Listado":
        df = pd.read_sql_query(
            """
            SELECT
                id,
                rut AS RUT,
                COALESCE(
                    NULLIF(razon_social, ''),
                    nombre
                ) AS Cliente,
                email AS Email,
                telefono AS Teléfono,
                cuenta_defecto AS Cuenta
            FROM clientes
            ORDER BY Cliente
            """,
            conn
        )
        st.dataframe(formatear_montos_df(df), use_container_width=True, hide_index=True)

    if sgci_vista_cliente == "Estado de cuenta":
        clientes = conn.execute(
            """
            SELECT
                id,
                rut,
                COALESCE(
                    NULLIF(razon_social, ''),
                    nombre
                ) AS nombre
            FROM clientes
            ORDER BY nombre
            """
        ).fetchall()

        if clientes:
            opciones = {f"{x['rut']} - {x['nombre']}": x["id"] for x in clientes}
            seleccionado = st.selectbox("Cliente", list(opciones.keys()))
            cliente_id = opciones[seleccionado]

            modo_ec=st.radio('Modalidad del estado de cuenta',
                             ['Partidas abiertas','Histórico'],horizontal=True,key='sgci_ec_cliente_modo')
            if modo_ec=='Partidas abiertas':
                sgci_mostrar_partidas_abiertas(conn,'VENTAS',cliente_id,seleccionado)
            df = estado_cuenta_cliente(conn, cliente_id) if modo_ec=='Histórico' else pd.DataFrame()
            if modo_ec=='Histórico':
                sgci_conc_esquema(conn)
                detalle_apertura=pd.read_sql_query("""
                    SELECT s.ejercicio AS Ejercicio, s.referencia AS Factura,
                           s.monto AS 'Monto original',
                           COALESCE((SELECT SUM(a.monto) FROM sgci_aplicaciones_ejercicios a
                                     WHERE a.saldo_id=s.id),0) AS Aplicado,
                           MAX(0,s.monto-COALESCE((SELECT SUM(a.monto)
                                     FROM sgci_aplicaciones_ejercicios a
                                     WHERE a.saldo_id=s.id),0)) AS 'Saldo pendiente'
                    FROM sgci_saldos_ejercicios s
                    WHERE s.modulo='VENTAS' AND s.tercero_id=?
                    ORDER BY s.ejercicio,s.referencia
                """,conn,params=(int(cliente_id),))
                if not detalle_apertura.empty:
                    st.markdown('#### Facturas de ejercicios anteriores incluidas en la apertura')
                    st.caption('Detalle auxiliar de saldos ya contabilizados en la apertura. No se suma otra vez al saldo contable del histórico.')
                    st.dataframe(formatear_montos_df(detalle_apertura),use_container_width=True,hide_index=True)


            if df.empty and modo_ec=='Histórico':
                st.info("El cliente no tiene movimientos.")
            elif not df.empty:
                cargo = df["cargo"].sum()
                abono = df["abono"].sum()
                saldo = df.iloc[-1]["saldo"]

                c1, c2, c3 = st.columns(3)
                c1.metric("Facturado", money(cargo))
                c2.metric("Pagado", money(abono))
                c3.metric("Saldo", money(saldo))

                mostrar = df[
                    [
                        "fecha",
                        "Documento",
                        "glosa",
                        "cargo",
                        "abono",
                        "saldo",
                    ]
                ].rename(
                    columns={
                        "fecha": "Fecha",
                        "Documento": "Documento",
                        "glosa": "Glosa",
                        "cargo": "Cargo",
                        "abono": "Abono",
                        "saldo": "Saldo",
                    }
                )

                st.dataframe(mostrar, use_container_width=True, hide_index=True)
                filas_pdf=[[r.Fecha,r.Documento,r.Glosa,money(r.Cargo),money(r.Abono),money(r.Saldo)] for r in mostrar.itertuples(index=False)]
                pdf_ec=nomina_pdf("Estado de Cuenta de Cliente",seleccionado,["Fecha","Documento","Glosa","Cargo","Abono","Saldo"],filas_pdf,["","","TOTALES",money(cargo),money(abono),money(saldo)])
                st.download_button("🖨️ Imprimir / PDF estado de cuenta",pdf_ec,f"estado_cuenta_cliente_{cliente_id}.pdf","application/pdf",key=f"pdf_cliente_{cliente_id}")

    if sgci_vista_cliente == "Nuevo cliente":
        with st.form("nuevo_cliente"):
            rut = st.text_input("RUT")
            nombre = st.text_input("Razón social")
            email = st.text_input("Email")
            telefono = st.text_input("Teléfono")

            if st.form_submit_button("Guardar cliente"):
                if not validar_rut(rut):
                    st.error("RUT inválido.")
                elif not nombre.strip():
                    st.error("Debe indicar razón social.")
                else:
                    try:
                        conn.execute(
                            """
                            INSERT INTO clientes
                            (
                                rut,
                                nombre,
                                razon_social,
                                email,
                                telefono,
                                activo,
                                fecha_creacion
                            )
                            VALUES (?, ?, ?, ?, ?, 1, ?)
                            """,
                            (
                                normalizar_rut(rut),
                                nombre,
                                nombre,
                                email,
                                telefono,
                                datetime.now().isoformat()
                            )
                        )
                        conn.commit()
                        sgci_exito("Cliente creado.")
                    except Exception as e:
                        st.error(str(e))


# ============================================================
# PROVEEDORES
# ============================================================

elif menu == "🏢 Proveedores":

    st.title("🏢 Proveedores")

    # Radio conserva selección al ejecutar de nuevo Streamlit.
    sgci_vista_proveedor = st.radio('Sección', ['Listado','Estado de cuenta','Nuevo proveedor'],
                                horizontal=True,key='sgci_vista_proveedor',label_visibility='collapsed')

    if sgci_vista_proveedor == "Listado":
        df = pd.read_sql_query(
            """
            SELECT
                id,
                rut AS RUT,
                COALESCE(
                    NULLIF(razon_social, ''),
                    nombre
                ) AS Proveedor,
                email AS Email,
                telefono AS Teléfono,
                cuenta_defecto AS Cuenta
            FROM proveedores
            ORDER BY Proveedor
            """,
            conn
        )
        st.dataframe(formatear_montos_df(df), use_container_width=True, hide_index=True)

    if sgci_vista_proveedor == "Estado de cuenta":
        proveedores = conn.execute(
            """
            SELECT
                id,
                rut,
                COALESCE(
                    NULLIF(razon_social, ''),
                    nombre
                ) AS nombre
            FROM proveedores
            ORDER BY nombre
            """
        ).fetchall()

        if proveedores:
            opciones = {f"{x['rut']} - {x['nombre']}": x["id"] for x in proveedores}
            seleccionado = st.selectbox("Proveedor", list(opciones.keys()))
            proveedor_id = opciones[seleccionado]

            modo_ec=st.radio('Modalidad del estado de cuenta',
                             ['Partidas abiertas','Histórico'],horizontal=True,key='sgci_ec_proveedor_modo')
            if modo_ec=='Partidas abiertas':
                sgci_mostrar_partidas_abiertas(conn,'COMPRAS',proveedor_id,seleccionado)
            df = estado_cuenta_proveedor(conn, proveedor_id) if modo_ec=='Histórico' else pd.DataFrame()

            if df.empty and modo_ec=='Histórico':
                st.info("El proveedor no tiene movimientos.")
            elif not df.empty:
                cargo = df["cargo"].sum()
                abono = df["abono"].sum()
                saldo = df.iloc[-1]["saldo"]

                c1, c2, c3 = st.columns(3)
                c1.metric("Compras", money(cargo))
                c2.metric("Pagado", money(abono))
                c3.metric("Saldo", money(saldo))

                mostrar_prov=df[["fecha","Documento","glosa","cargo","abono","saldo"]].copy()
                st.dataframe(mostrar_prov,use_container_width=True,hide_index=True)
                filas_pdf=[[r.fecha,r.Documento,r.glosa,money(r.cargo),money(r.abono),money(r.saldo)] for r in mostrar_prov.itertuples(index=False)]
                pdf_ec=nomina_pdf("Estado de Cuenta de Proveedor",seleccionado,["Fecha","Documento","Glosa","Cargo","Abono","Saldo"],filas_pdf,["","","TOTALES",money(cargo),money(abono),money(saldo)])
                st.download_button("🖨️ Imprimir / PDF estado de cuenta",pdf_ec,f"estado_cuenta_proveedor_{proveedor_id}.pdf","application/pdf",key=f"pdf_proveedor_{proveedor_id}")

    if sgci_vista_proveedor == "Nuevo proveedor":
        with st.form("nuevo_proveedor"):
            rut = st.text_input("RUT")
            nombre = st.text_input("Razón social")
            email = st.text_input("Email")
            telefono = st.text_input("Teléfono")

            if st.form_submit_button("Guardar proveedor"):
                if not validar_rut(rut):
                    st.error("RUT inválido.")
                elif not nombre.strip():
                    st.error("Debe indicar razón social.")
                else:
                    try:
                        conn.execute(
                            """
                            INSERT INTO proveedores
                            (
                                rut,
                                nombre,
                                razon_social,
                                email,
                                telefono,
                                activo,
                                fecha_creacion
                            )
                            VALUES (?, ?, ?, ?, ?, 1, ?)
                            """,
                            (
                                normalizar_rut(rut),
                                nombre,
                                nombre,
                                email,
                                telefono,
                                datetime.now().isoformat()
                            )
                        )
                        conn.commit()
                        sgci_exito("Proveedor creado.")
                    except Exception as e:
                        st.error(str(e))


# ============================================================
# PAGOS
# ============================================================

elif menu == "💵 Pagos":

    st.title("💵 Pagos y cobranzas")

    pestañas = st.tabs(["Cobranza clientes", "Pago proveedores"])
    cuentas = cuentas_imputables(conn)
    cuentas_banco = cuentas[cuentas["codigo"].str.startswith("1.1.02")]

    with pestañas[0]:
        clientes = conn.execute(
            """
            SELECT id, rut,
            COALESCE(
                NULLIF(razon_social, ''),
                nombre
            ) AS nombre
            FROM clientes
            ORDER BY nombre
            """
        ).fetchall()

        if not clientes:
            st.info("No hay clientes registrados. Debe crear al menos un cliente para registrar cobranzas.")
        else:
            opciones = {f"{x['rut']} - {x['nombre']}": x["id"] for x in clientes}

            with st.form("pago_cliente"):
                seleccionado = st.selectbox("Cliente", list(opciones.keys()))
                fecha_pago = st.date_input("Fecha", date.today())
                monto_pago = st.number_input("Monto", min_value=0.0, step=1000.0,format='%.0f')
                medio = st.selectbox("Medio de pago", ["Transferencia", "Cheque", "Efectivo", "Tarjeta", "Otro"])

                if cuentas_banco.empty:
                    st.warning("No existen cuentas bajo 1.1.02.")
                    cuenta_banco = None
                else:
                    opciones_banco = dict(zip(cuentas_banco["etiqueta"], cuentas_banco["codigo"]))
                    cuenta_banco_label = st.selectbox("Cuenta bancaria", list(opciones_banco.keys()))
                    cuenta_banco = opciones_banco[cuenta_banco_label]

                glosa = st.text_input("Glosa")
                guardar = st.form_submit_button("Registrar cobranza")

                if guardar:
                    try:
                        lote = registrar_pago_cliente(
                            conn,
                            opciones[seleccionado],
                            fecha_pago.strftime("%Y-%m-%d"),
                            monto_pago,
                            medio,
                            cuenta_banco,
                            glosa
                        )
                        sgci_exito(f"Pago registrado. Lote: {lote}")
                    except Exception as e:
                        st.error(str(e))

    with pestañas[1]:
        proveedores = conn.execute(
            """
            SELECT id, rut,
            COALESCE(
                NULLIF(razon_social, ''),
                nombre
            ) AS nombre
            FROM proveedores
            ORDER BY nombre
            """
        ).fetchall()

        if not proveedores:
            st.info("No hay proveedores registrados. Debe crear al menos un proveedor para registrar pagos.")
        else:
            opciones = {f"{x['rut']} - {x['nombre']}": x["id"] for x in proveedores}

            with st.form("pago_proveedor"):
                seleccionado = st.selectbox("Proveedor", list(opciones.keys()))
                fecha_pago = st.date_input("Fecha", date.today(), key="fecha_pago_proveedor")
                monto_pago = st.number_input("Monto", min_value=0.0, step=1000.0, key="monto_pago_proveedor")
                medio = st.selectbox("Medio de pago", ["Transferencia", "Cheque", "Efectivo", "Tarjeta", "Otro"], key="medio_proveedor")

                if cuentas_banco.empty:
                    st.warning("No existen cuentas bajo 1.1.02.")
                    cuenta_banco = None
                else:
                    opciones_banco = dict(zip(cuentas_banco["etiqueta"], cuentas_banco["codigo"]))
                    cuenta_label = st.selectbox("Cuenta bancaria", list(opciones_banco.keys()), key="cuenta_proveedor")
                    cuenta_banco = opciones_banco[cuenta_label]

                glosa = st.text_input("Glosa", key="glosa_proveedor")
                guardar_proveedor = st.form_submit_button("Registrar pago")

                if guardar_proveedor:
                    try:
                        lote = registrar_pago_proveedor(
                            conn,
                            opciones[seleccionado],
                            fecha_pago.strftime("%Y-%m-%d"),
                            monto_pago,
                            medio,
                            cuenta_banco,
                            glosa
                        )
                        sgci_exito(f"Pago registrado. Lote: {lote}")
                    except Exception as e:
                        st.error(str(e))


# ============================================================
# LIBRO DIARIO
# ============================================================

elif menu == "📒 Libro Diario":

    st.title("📒 Libro Diario")

    df = pd.read_sql_query(
        """
        SELECT
            fecha AS Fecha,
            asiento_id AS Asiento,
            codigo_cuenta AS Código,
            cuenta AS Cuenta,
            debe AS Debe,
            haber AS Haber,
            glosa AS Glosa,
            origen AS Origen
        FROM libro_diario
        ORDER BY
            fecha DESC,
            asiento_id DESC,
            id DESC
        """,
        conn
    )

    if not df.empty:
        # Control por asiento: no confundir el total del libro con el de un comprobante.
        asientos = df["Asiento"].dropna().unique().tolist()
        opciones_asiento = ["Todos los asientos"] + [
            f"Asiento N.º {int(n) if float(n).is_integer() else n}" for n in asientos
        ]
        seleccion_asiento = st.selectbox(
            "Consultar asiento contable", opciones_asiento, key="diario_asiento_consulta"
        )
        if seleccion_asiento == "Todos los asientos":
            vista_diario = df
            st.caption("Totales del Libro Diario para todos los movimientos mostrados.")
        else:
            numero_asiento = asientos[opciones_asiento.index(seleccion_asiento) - 1]
            vista_diario = df.loc[df["Asiento"] == numero_asiento].copy()
            st.caption(f"Control contable del {seleccion_asiento}.")
        total_debe = float(pd.to_numeric(vista_diario["Debe"], errors="coerce").fillna(0).sum())
        total_haber = float(pd.to_numeric(vista_diario["Haber"], errors="coerce").fillna(0).sum())
        diferencia = total_debe - total_haber
        col_debe, col_haber, col_diferencia = st.columns(3)
        col_debe.metric("Total Debe", money(total_debe))
        col_haber.metric("Total Haber", money(total_haber))
        col_diferencia.metric("Diferencia", money(diferencia))
        if abs(diferencia) < 0.01:
            st.success("Asiento cuadrado." if seleccion_asiento != "Todos los asientos" else "Movimientos mostrados cuadrados.")
        else:
            st.error("Diferencia contable detectada. Revise las partidas antes de continuar.")
        st.dataframe(formatear_montos_df(vista_diario), use_container_width=True, hide_index=True)
        pdf = pdf_desde_dataframe(
            "Libro Diario", "CONTEM - Sistema Contable y Empresarial",
            vista_diario, {"Debe", "Haber"}
        )
        st.download_button(
            "🖨️ Imprimir / PDF Libro Diario", pdf, "libro_diario.pdf",
            "application/pdf", key="pdf_libro_diario"
        )
    else:
        st.info("No hay movimientos registrados en el Libro Diario.")


# ============================================================
# MAYOR
# ============================================================

elif menu == "📚 Mayor":

    st.title("📚 Libro Mayor")

    cuentas = cuentas_imputables(conn)
    opciones = dict(zip(cuentas["etiqueta"], cuentas["codigo"]))

    seleccion = st.selectbox("Cuenta", list(opciones.keys()))
    codigo = opciones[seleccion]

    df = obtener_mayor(conn, codigo)

    if df.empty:
        st.info("La cuenta no tiene movimientos.")
    else:
        saldo = df.iloc[-1]["Saldo"]
        st.metric("Saldo", money(saldo))
        st.dataframe(formatear_montos_df(df), use_container_width=True, hide_index=True)
        pdf = pdf_desde_dataframe("Libro Mayor",seleccion,df,{"Debe","Haber","Saldo"})
        st.download_button("🖨️ Imprimir / PDF Libro Mayor",pdf,f"libro_mayor_{codigo.replace('.','_')}.pdf","application/pdf",key="pdf_libro_mayor")


# ============================================================
# BALANCE DE COMPROBACIÓN
# ============================================================

elif menu == "⚖️ Balance de Comprobación":

    st.title("⚖ Balance de Comprobación")

    col1, col2 = st.columns(2)

    with col1:
        desde = st.date_input("Desde", date(date.today().year, 1, 1))

    with col2:
        hasta = st.date_input("Hasta", date.today())

    df = balance_comprobacion(
        conn,
        desde.strftime("%Y-%m-%d"),
        hasta.strftime("%Y-%m-%d")
    )

    if not df.empty:
        debe = df["Debe"].sum()
        haber = df["Haber"].sum()

        c1, c2, c3 = st.columns(3)
        c1.metric("Debe", money(debe))
        c2.metric("Haber", money(haber))
        c3.metric("Diferencia", money(debe - haber))

        if abs(debe - haber) < 0.01:
            sgci_exito("🟢 Balance cuadrado.")
        else:
            st.error("🔴 Existe diferencia.")

        st.dataframe(formatear_montos_df(df), use_container_width=True, hide_index=True)
        pdf = pdf_desde_dataframe(
            "Balance de Comprobación",
            f"Desde {desde.strftime('%Y-%m-%d')} hasta {hasta.strftime('%Y-%m-%d')}",
            df, {"Debe","Haber","Saldo"},
            ["","TOTALES",money(debe),money(haber),money(df["Saldo"].sum())] if len(df.columns) >= 5 else None
        )
        st.download_button("🖨️ Imprimir / PDF Balance de Comprobación",pdf,f"balance_{hasta.strftime('%Y%m%d')}.pdf","application/pdf",key="pdf_balance_modulo")


# ============================================================
# CONCILIACIÓN
# ============================================================

elif menu == "📊 Conciliación":

    st.title("📊 Conciliación de auxiliares")

    sgci_vista_conc = "Clientes" if nav_context == "clientes" else "Proveedores"
    st.caption("Auxiliar activo: " + sgci_vista_conc)

    sgci_conc_esquema(conn)
    if sgci_vista_conc == "Clientes":
        with st.expander("🧩 Compensar notas de crédito contra facturas", expanded=False):
            modulo_doc="VENTAS"
            tabla_tercero='clientes' if modulo_doc=='VENTAS' else 'proveedores'
            terceros=pd.read_sql_query(f"SELECT id,rut,COALESCE(NULLIF(razon_social,''),nombre) nombre FROM {tabla_tercero} ORDER BY nombre",conn)
            if terceros.empty:
                st.info("No existen terceros registrados.")
            else:
                mapa={f"{r.rut} | {r.nombre}":int(r.id) for r in terceros.itertuples()}
                tercero=mapa[st.selectbox("Cliente" if modulo_doc=="VENTAS" else "Proveedor",list(mapa),key="sgci_ventas_tercero_nc")]
                ncs=sgci_nc_disponibles(conn,modulo_doc,tercero)
                facturas=sgci_facturas_compensables(conn,modulo_doc,tercero)
                a,b=st.columns(2)
                a.metric("NC disponibles",money(ncs.disponible.sum() if not ncs.empty else 0))
                b.metric("Facturas pendientes",money(facturas.pendiente.sum() if not facturas.empty else 0))
                if ncs.empty or facturas.empty:
                    st.info("Se requiere una nota de crédito y una factura con saldo disponible.")
                else:
                    mapa_nc={f"NC {r.folio} ({r.fecha}) | {money(r.disponible)}":int(r.id) for r in ncs.itertuples()}
                    mapa_f={f"Factura {r.folio} ({r.fecha}) | {money(r.pendiente)}":int(r.id) for r in facturas.itertuples()}
                    nc_id=mapa_nc[st.selectbox("Nota de crédito",list(mapa_nc),key="sgci_ventas_nc_sel")]
                    fac_id=mapa_f[st.selectbox("Factura a compensar",list(mapa_f),key="sgci_ventas_fac_sel")]
                    disponible_nc=int(ncs.loc[ncs.id==nc_id,'disponible'].iloc[0]);pendiente_fac=int(facturas.loc[facturas.id==fac_id,'pendiente'].iloc[0])
                    importe=st.number_input("Monto a compensar (CLP)",min_value=1,max_value=max(1,min(disponible_nc,pendiente_fac)),value=max(1,min(disponible_nc,pendiente_fac)),step=1,key="sgci_ventas_nc_monto")
                    obs=st.text_input("Referencia / observación",key="sgci_ventas_nc_obs")
                    conf=st.checkbox("Confirmo que los documentos corresponden a la misma operación y que su efecto contable ya está registrado.",key="sgci_ventas_nc_conf")
                    if st.button("🔗 Compensar documentos",disabled=not conf,type="primary",key="sgci_ventas_nc_aplicar"):
                        sgci_exigir_permiso(conn, 'cxc', 'editar', 'Clientes y estados de cuenta')
                        try:
                            sgci_compensar_nc(conn,modulo_doc,tercero,nc_id,fac_id,importe,obs)
                            sgci_exito("Compensación auxiliar registrada sin generar asientos.");st.rerun()
                        except Exception as exc: st.error(str(exc))
                historial=pd.read_sql_query("SELECT id,fecha,documento_credito_id NC_ID,documento_factura_id Factura_ID,monto,observacion FROM sgci_compensaciones_documentos WHERE modulo=? AND tercero_id=? AND anulada=0 ORDER BY id DESC",conn,params=(modulo_doc,tercero))
                if not historial.empty:
                    st.dataframe(formatear_montos_df(historial),hide_index=True,use_container_width=True)
                    with st.expander("Revertir una compensación"):
                        cid=st.selectbox("Registro",historial.id.astype(int).tolist(),key="sgci_ventas_rev_id")
                        motivo=st.text_input("Motivo obligatorio",key="sgci_ventas_rev_motivo")
                        if st.button("Revertir",disabled=not motivo.strip(),key="sgci_ventas_rev_btn"):
                            sgci_exigir_permiso(conn, 'cxc', 'anular', 'Clientes y estados de cuenta')
                            try: sgci_anular_compensacion(conn,cid,motivo);st.rerun()
                            except Exception as exc: st.error(str(exc))

        with st.expander("📘 Aplicar cobros o pagos a saldos de ejercicios anteriores", expanded=False):
            modulo_ant="VENTAS"
            tabla_t='clientes' if modulo_ant=='VENTAS' else 'proveedores'
            tabla_p='pagos_clientes' if modulo_ant=='VENTAS' else 'pagos_proveedores'
            campo_t='cliente_id' if modulo_ant=='VENTAS' else 'proveedor_id'
            terceros=pd.read_sql_query(f"SELECT id,rut,COALESCE(NULLIF(razon_social,''),nombre) nombre FROM {tabla_t} ORDER BY nombre",conn)
            if not terceros.empty:
                mapa={f"{r.rut} | {r.nombre}":int(r.id) for r in terceros.itertuples()}
                tercero=mapa[st.selectbox("Tercero",list(mapa),key="sgci_ventas_tercero_ant")]
                st.caption("Registra solo saldos que YA existen en el asiento de apertura. No crea saldos contables.")
                with st.form("sgci_ventas_nuevo_saldo_ant"):
                    ej=st.number_input("Ejercicio de origen",min_value=2000,max_value=date.today().year-1,value=date.today().year-1,step=1)
                    ref=st.text_input("Folio / referencia del saldo anterior")
                    monto=st.number_input("Saldo histórico (CLP)",min_value=1,step=1,value=1)
                    guardar=st.form_submit_button("Registrar saldo histórico")
                if guardar:
                    try: sgci_registrar_saldo_ejercicio(conn,modulo_ant,tercero,ej,ref,monto);st.rerun()
                    except Exception as exc: st.error(str(exc))
                saldos=sgci_saldos_ejercicio_disponibles(conn,modulo_ant,tercero)
                if not saldos.empty:
                    st.dataframe(formatear_montos_df(saldos),hide_index=True,use_container_width=True)
                    pagos=pd.read_sql_query(f"SELECT id,fecha,monto,COALESCE(glosa,'') glosa FROM {tabla_p} WHERE {campo_t}=? ORDER BY fecha DESC,id DESC",conn,params=(tercero,))
                    if not pagos.empty:
                        mapa_s={f"{r.ejercicio} | {r.referencia} | {money(r.disponible)}":int(r.id) for r in saldos.itertuples()}
                        sid=mapa_s[st.selectbox("Saldo anterior",list(mapa_s),key="sgci_ventas_saldo_ant_sel")]
                        mapa_p={f"#{int(r.id)} | {r.fecha} | {money(r.monto)} | {r.glosa}":int(r.id) for r in pagos.itertuples()}
                        pid=mapa_p[st.selectbox("Cobro / pago ya contabilizado",list(mapa_p),key="sgci_ventas_pago_ant_sel")]
                        limite=int(saldos.loc[saldos.id==sid,'disponible'].iloc[0])
                        imp=st.number_input("Importe a aplicar",min_value=1,max_value=max(1,limite),value=max(1,limite),step=1,key="sgci_ventas_imp_ant")
                        conf=st.checkbox("Verifiqué que el pago corresponde al saldo histórico y que no se aplicó anteriormente.",key="sgci_ventas_conf_ant")
                        if st.button("Aplicar a ejercicio anterior",disabled=not conf,key="sgci_ventas_aplicar_ant"):
                            sgci_exigir_permiso(conn, 'cxc', 'editar', 'Pagos de clientes')
                            try: sgci_aplicar_pago_ejercicio(conn,modulo_ant,tercero,sid,pid,imp);st.rerun()
                            except Exception as exc: st.error(str(exc))

        st.subheader("Aplicar abonos de clientes")
        st.caption("Relaciona abonos ya registrados con facturas pendientes. No vuelve a mover Banco. Si el saldo estaba contabilizado como anticipo de cliente, SGCI genera únicamente la reclasificación Anticipos → Clientes necesaria al aplicarlo.")

        clientes_aux=conn.execute("""
            SELECT id,rut,COALESCE(NULLIF(razon_social,''),nombre) nombre
            FROM clientes WHERE activo=1 ORDER BY nombre
        """).fetchall()

        with st.expander("🧾 Asignar anticipo existente a un cliente"):
            st.caption("Úsalo para anticipos que ya fueron contabilizados directamente contra la cuenta Anticipos de clientes, pero quedaron sin cliente en el auxiliar. No crea ni modifica el asiento original.")
            ant_sin_asig=anticipos_contables_sin_asignar(conn)
            if ant_sin_asig.empty:
                st.info("No hay anticipos contables pendientes de asignar.")
            elif not clientes_aux:
                st.info("No hay clientes activos.")
            else:
                ver_ant=ant_sin_asig[["asiento_id","fecha","cuenta_anticipo","monto","glosa"]].rename(
                    columns={"asiento_id":"Asiento","fecha":"Fecha","cuenta_anticipo":"Cuenta","monto":"Monto","glosa":"Glosa"}
                )
                st.dataframe(formatear_montos_df(ver_ant),use_container_width=True,hide_index=True)
                mapa_ant={
                    f"Asiento {int(r.asiento_id)} | {r.fecha} | {money(r.monto)} | {r.glosa}":int(r.asiento_id)
                    for r in ant_sin_asig.itertuples()
                }
                ant_lab=st.selectbox("Anticipo contable",list(mapa_ant.keys()),key="asignar_ant_existente")
                mapa_cli_asig={f"{x['rut']} - {x['nombre']}":x["id"] for x in clientes_aux}
                cli_lab_asig=st.selectbox("Asignar al cliente",list(mapa_cli_asig.keys()),key="asignar_ant_cliente")
                conf_asig=st.checkbox(
                    "Confirmo que este anticipo pertenece al cliente seleccionado.",
                    key="confirmar_asignacion_anticipo"
                )
                if st.button("🔗 Asignar anticipo al auxiliar",type="primary",
                             disabled=not conf_asig,key="btn_asignar_ant_existente"):
                    sgci_exigir_permiso(conn, 'cxc', 'editar', 'Pagos de clientes')
                    try:
                        monto_asig=asignar_anticipo_contable_a_cliente(
                            conn,mapa_ant[ant_lab],mapa_cli_asig[cli_lab_asig]
                        )
                        sgci_exito(f"Anticipo por {money(monto_asig)} asignado al auxiliar. El asiento contable original no fue modificado.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"No se pudo asignar el anticipo: {e}")
        if not clientes_aux:
            st.info("No hay clientes activos.")
        else:
            mapa_cli_aux={f"{x['rut']} - {x['nombre']}":x["id"] for x in clientes_aux}
            lab_cli_aux=st.selectbox("Cliente",list(mapa_cli_aux.keys()),key="aux_cliente_sel")
            id_cli_aux=mapa_cli_aux[lab_cli_aux]
            abonos_aux=abonos_disponibles_cliente(conn,id_cli_aux)
            docs_aux=documentos_pendientes_cliente(conn,id_cli_aux)

            c1,c2=st.columns(2)
            c1.metric("Abonos disponibles",money(abonos_aux["disponible"].sum() if not abonos_aux.empty else 0))
            c2.metric("Facturas pendientes",money(docs_aux["pendiente"].sum() if not docs_aux.empty else 0))

            if abonos_aux.empty:
                st.info("Este cliente no tiene abonos pendientes de aplicar.")
            elif docs_aux.empty:
                st.info("Este cliente tiene abonos disponibles, pero no tiene facturas pendientes.")
                ver_ab=abonos_aux[["fecha","glosa","monto","aplicado","disponible"]].copy()
                st.dataframe(formatear_montos_df(ver_ab),use_container_width=True,hide_index=True)
            else:
                st.markdown("#### 1. Selecciona el abono")
                ver_ab=abonos_aux[["id","fecha","glosa","monto","aplicado","disponible"]].copy()
                st.dataframe(formatear_montos_df(ver_ab),use_container_width=True,hide_index=True)
                mapa_ab={f"#{int(r.id)} | {r.fecha} | {money(r.disponible)} disponibles | {r.glosa}":int(r.id) for r in abonos_aux.itertuples()}
                lab_ab=st.selectbox("Abono disponible",list(mapa_ab.keys()),key="aux_abono_sel")
                pago_id_aux=mapa_ab[lab_ab]
                fila_ab=abonos_aux.loc[abonos_aux["id"]==pago_id_aux].iloc[0]
                disponible_aux=clp_round(float(fila_ab["disponible"]))

                st.markdown("#### 2. Selecciona las facturas")
                ver_docs=docs_aux[["id","fecha","folio","tipo_doc","total","aplicado","pendiente"]].copy()
                st.dataframe(formatear_montos_df(ver_docs),use_container_width=True,hide_index=True)
                mapa_docs_aux={f"#{int(r.id)} | {r.fecha} | Folio {r.folio} | saldo {money(r.pendiente)}":int(r.id) for r in docs_aux.itertuples()}
                labs_docs_aux=st.multiselect("Factura(s) a conciliar",list(mapa_docs_aux.keys()),key="aux_docs_sel")
                ids_docs_aux=[mapa_docs_aux[x] for x in labs_docs_aux]
                total_docs_aux=clp_round(float(docs_aux[docs_aux["id"].isin(ids_docs_aux)]["pendiente"].sum())) if ids_docs_aux else 0
                aplicar_aux=min(disponible_aux,total_docs_aux)
                saldo_ab_aux=clp_round(disponible_aux-aplicar_aux)
                saldo_docs_aux=clp_round(total_docs_aux-aplicar_aux)

                m1,m2,m3=st.columns(3)
                m1.metric("Saldo del abono",money(disponible_aux))
                m2.metric("Se aplicará",money(aplicar_aux))
                m3.metric("Quedará disponible",money(saldo_ab_aux))
                if ids_docs_aux and saldo_docs_aux>0:
                    st.info(f"Las facturas seleccionadas conservarán {money(saldo_docs_aux)} pendientes después de esta aplicación.")

                confirma_aux=st.checkbox(
                    "Confirmo la aplicación. Si corresponde a un anticipo, SGCI realizará automáticamente la reclasificación contable sin volver a mover Banco.",
                    key="aux_confirma_cliente"
                )
                if st.button("🔗 Aplicar abono a factura(s)",type="primary",
                             disabled=(not confirma_aux or not ids_docs_aux),key="aux_aplicar_cliente"):
                    sgci_exigir_permiso(conn, 'cxc', 'editar', 'Pagos de clientes')
                    try:
                        apps_aux,saldo_aux=aplicar_abono_auxiliar_cliente(conn,id_cli_aux,pago_id_aux,ids_docs_aux)
                        total_ap_aux=sum(x[1] for x in apps_aux)
                        sgci_exito(f"Aplicación auxiliar realizada por {money(total_ap_aux)}. Saldo disponible del abono: {money(saldo_aux)}.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"No se pudo aplicar el abono: {e}")

        st.divider()
        st.subheader("Control contable del auxiliar")
        df = conciliacion_clientes(conn)
        if df.empty:
            st.warning("No se pudo determinar la cuenta de clientes.")
        else:
            st.dataframe(formatear_montos_df(df), use_container_width=True, hide_index=True)
            diferencia = df.iloc[0]["Diferencia"]
            if abs(diferencia) < 0.01:
                sgci_exito("🟢 Auxiliar de clientes conciliado.")
            else:
                st.error(f"🔴 Diferencia: {money(diferencia)}")

    if sgci_vista_conc == "Proveedores":
        with st.expander("🧩 Compensar notas de crédito contra facturas", expanded=False):
            modulo_doc="COMPRAS"
            tabla_tercero='clientes' if modulo_doc=='VENTAS' else 'proveedores'
            terceros=pd.read_sql_query(f"SELECT id,rut,COALESCE(NULLIF(razon_social,''),nombre) nombre FROM {tabla_tercero} ORDER BY nombre",conn)
            if terceros.empty:
                st.info("No existen terceros registrados.")
            else:
                mapa={f"{r.rut} | {r.nombre}":int(r.id) for r in terceros.itertuples()}
                tercero=mapa[st.selectbox("Cliente" if modulo_doc=="VENTAS" else "Proveedor",list(mapa),key="sgci_compras_tercero_nc")]
                ncs=sgci_nc_disponibles(conn,modulo_doc,tercero)
                facturas=sgci_facturas_compensables(conn,modulo_doc,tercero)
                a,b=st.columns(2)
                a.metric("NC disponibles",money(ncs.disponible.sum() if not ncs.empty else 0))
                b.metric("Facturas pendientes",money(facturas.pendiente.sum() if not facturas.empty else 0))
                if ncs.empty or facturas.empty:
                    st.info("Se requiere una nota de crédito y una factura con saldo disponible.")
                else:
                    mapa_nc={f"NC {r.folio} ({r.fecha}) | {money(r.disponible)}":int(r.id) for r in ncs.itertuples()}
                    mapa_f={f"Factura {r.folio} ({r.fecha}) | {money(r.pendiente)}":int(r.id) for r in facturas.itertuples()}
                    nc_id=mapa_nc[st.selectbox("Nota de crédito",list(mapa_nc),key="sgci_compras_nc_sel")]
                    fac_id=mapa_f[st.selectbox("Factura a compensar",list(mapa_f),key="sgci_compras_fac_sel")]
                    disponible_nc=int(ncs.loc[ncs.id==nc_id,'disponible'].iloc[0]);pendiente_fac=int(facturas.loc[facturas.id==fac_id,'pendiente'].iloc[0])
                    importe=st.number_input("Monto a compensar (CLP)",min_value=1,max_value=max(1,min(disponible_nc,pendiente_fac)),value=max(1,min(disponible_nc,pendiente_fac)),step=1,key="sgci_compras_nc_monto")
                    obs=st.text_input("Referencia / observación",key="sgci_compras_nc_obs")
                    conf=st.checkbox("Confirmo que los documentos corresponden a la misma operación y que su efecto contable ya está registrado.",key="sgci_compras_nc_conf")
                    if st.button("🔗 Compensar documentos",disabled=not conf,type="primary",key="sgci_compras_nc_aplicar"):
                        sgci_exigir_permiso(conn, 'cxp', 'editar', 'Proveedores y estados de cuenta')
                        try:
                            sgci_compensar_nc(conn,modulo_doc,tercero,nc_id,fac_id,importe,obs)
                            sgci_exito("Compensación auxiliar registrada sin generar asientos.");st.rerun()
                        except Exception as exc: st.error(str(exc))
                historial=pd.read_sql_query("SELECT id,fecha,documento_credito_id NC_ID,documento_factura_id Factura_ID,monto,observacion FROM sgci_compensaciones_documentos WHERE modulo=? AND tercero_id=? AND anulada=0 ORDER BY id DESC",conn,params=(modulo_doc,tercero))
                if not historial.empty:
                    st.dataframe(formatear_montos_df(historial),hide_index=True,use_container_width=True)
                    with st.expander("Revertir una compensación"):
                        cid=st.selectbox("Registro",historial.id.astype(int).tolist(),key="sgci_compras_rev_id")
                        motivo=st.text_input("Motivo obligatorio",key="sgci_compras_rev_motivo")
                        if st.button("Revertir",disabled=not motivo.strip(),key="sgci_compras_rev_btn"):
                            sgci_exigir_permiso(conn, 'cxp', 'anular', 'Proveedores y estados de cuenta')
                            try: sgci_anular_compensacion(conn,cid,motivo);st.rerun()
                            except Exception as exc: st.error(str(exc))

        with st.expander("📘 Aplicar cobros o pagos a saldos de ejercicios anteriores", expanded=False):
            modulo_ant="COMPRAS"
            tabla_t='clientes' if modulo_ant=='VENTAS' else 'proveedores'
            tabla_p='pagos_clientes' if modulo_ant=='VENTAS' else 'pagos_proveedores'
            campo_t='cliente_id' if modulo_ant=='VENTAS' else 'proveedor_id'
            terceros=pd.read_sql_query(f"SELECT id,rut,COALESCE(NULLIF(razon_social,''),nombre) nombre FROM {tabla_t} ORDER BY nombre",conn)
            if not terceros.empty:
                mapa={f"{r.rut} | {r.nombre}":int(r.id) for r in terceros.itertuples()}
                tercero=mapa[st.selectbox("Tercero",list(mapa),key="sgci_compras_tercero_ant")]
                st.caption("Registra solo saldos que YA existen en el asiento de apertura. No crea saldos contables.")
                with st.form("sgci_compras_nuevo_saldo_ant"):
                    ej=st.number_input("Ejercicio de origen",min_value=2000,max_value=date.today().year-1,value=date.today().year-1,step=1)
                    ref=st.text_input("Folio / referencia del saldo anterior")
                    monto=st.number_input("Saldo histórico (CLP)",min_value=1,step=1,value=1)
                    guardar=st.form_submit_button("Registrar saldo histórico")
                if guardar:
                    try: sgci_registrar_saldo_ejercicio(conn,modulo_ant,tercero,ej,ref,monto);st.rerun()
                    except Exception as exc: st.error(str(exc))
                saldos=sgci_saldos_ejercicio_disponibles(conn,modulo_ant,tercero)
                if not saldos.empty:
                    st.dataframe(formatear_montos_df(saldos),hide_index=True,use_container_width=True)
                    pagos=pd.read_sql_query(f"SELECT id,fecha,monto,COALESCE(glosa,'') glosa FROM {tabla_p} WHERE {campo_t}=? ORDER BY fecha DESC,id DESC",conn,params=(tercero,))
                    if not pagos.empty:
                        mapa_s={f"{r.ejercicio} | {r.referencia} | {money(r.disponible)}":int(r.id) for r in saldos.itertuples()}
                        sid=mapa_s[st.selectbox("Saldo anterior",list(mapa_s),key="sgci_compras_saldo_ant_sel")]
                        mapa_p={f"#{int(r.id)} | {r.fecha} | {money(r.monto)} | {r.glosa}":int(r.id) for r in pagos.itertuples()}
                        pid=mapa_p[st.selectbox("Cobro / pago ya contabilizado",list(mapa_p),key="sgci_compras_pago_ant_sel")]
                        limite=int(saldos.loc[saldos.id==sid,'disponible'].iloc[0])
                        imp=st.number_input("Importe a aplicar",min_value=1,max_value=max(1,limite),value=max(1,limite),step=1,key="sgci_compras_imp_ant")
                        conf=st.checkbox("Verifiqué que el pago corresponde al saldo histórico y que no se aplicó anteriormente.",key="sgci_compras_conf_ant")
                        if st.button("Aplicar a ejercicio anterior",disabled=not conf,key="sgci_compras_aplicar_ant"):
                            sgci_exigir_permiso(conn, 'cxp', 'editar', 'Pagos de proveedores')
                            try: sgci_aplicar_pago_ejercicio(conn,modulo_ant,tercero,sid,pid,imp);st.rerun()
                            except Exception as exc: st.error(str(exc))

        st.subheader("Aplicar pagos de proveedores")
        st.caption("Relaciona pagos ya contabilizados con documentos pendientes. Esta operación solo concilia el auxiliar: no genera un nuevo asiento contable ni vuelve a mover Banco.")

        proveedores_aux=conn.execute("""
            SELECT id,rut,COALESCE(NULLIF(razon_social,''),nombre) nombre
            FROM proveedores WHERE activo=1 ORDER BY nombre
        """).fetchall()

        if not proveedores_aux:
            st.info("No hay proveedores activos.")
        else:
            mapa_prov_aux={f"{x['rut']} - {x['nombre']}":x["id"] for x in proveedores_aux}
            lab_prov_aux=st.selectbox("Proveedor",list(mapa_prov_aux.keys()),key="aux_proveedor_sel")
            id_prov_aux=mapa_prov_aux[lab_prov_aux]

            pagos_aux=pagos_disponibles_proveedor(conn,id_prov_aux)
            docs_prov_aux=documentos_pendientes_proveedor(conn,id_prov_aux)

            p1,p2=st.columns(2)
            p1.metric("Pagos disponibles",money(pagos_aux["disponible"].sum() if not pagos_aux.empty else 0))
            p2.metric("Documentos pendientes",money(docs_prov_aux["pendiente"].sum() if not docs_prov_aux.empty else 0))

            if pagos_aux.empty:
                st.info("Este proveedor no tiene pagos pendientes de aplicar.")
            elif docs_prov_aux.empty:
                st.info("Este proveedor tiene pagos disponibles, pero no tiene documentos pendientes.")
                ver_pag=pagos_aux[["fecha","glosa","monto","aplicado","disponible"]].copy()
                st.dataframe(formatear_montos_df(ver_pag),use_container_width=True,hide_index=True)
            else:
                st.markdown("#### 1. Selecciona el pago")
                ver_pag=pagos_aux[["id","fecha","glosa","monto","aplicado","disponible"]].copy()
                st.dataframe(formatear_montos_df(ver_pag),use_container_width=True,hide_index=True)

                mapa_pag={
                    f"#{int(r.id)} | {r.fecha} | {money(r.disponible)} disponibles | {r.glosa}":int(r.id)
                    for r in pagos_aux.itertuples()
                }
                lab_pag=st.selectbox("Pago disponible",list(mapa_pag.keys()),key="aux_pago_prov_sel")
                pago_id_prov=mapa_pag[lab_pag]
                fila_pag=pagos_aux.loc[pagos_aux["id"]==pago_id_prov].iloc[0]
                disponible_prov=clp_round(float(fila_pag["disponible"]))

                st.markdown("#### 2. Selecciona los documentos")
                ver_docs_prov=docs_prov_aux[["id","fecha","folio","tipo_doc","total","aplicado","pendiente"]].copy()
                st.dataframe(formatear_montos_df(ver_docs_prov),use_container_width=True,hide_index=True)

                mapa_docs_prov={
                    f"#{int(r.id)} | {r.fecha} | Folio {r.folio} | saldo {money(r.pendiente)}":int(r.id)
                    for r in docs_prov_aux.itertuples()
                }
                labs_docs_prov=st.multiselect(
                    "Documento(s) a conciliar",
                    list(mapa_docs_prov.keys()),
                    key="aux_docs_proveedor_sel"
                )
                ids_docs_prov=[mapa_docs_prov[x] for x in labs_docs_prov]
                total_docs_prov=clp_round(
                    float(docs_prov_aux[docs_prov_aux["id"].isin(ids_docs_prov)]["pendiente"].sum())
                ) if ids_docs_prov else 0

                aplicar_prov=min(disponible_prov,total_docs_prov)
                saldo_pago_prov=clp_round(disponible_prov-aplicar_prov)
                saldo_docs_prov=clp_round(total_docs_prov-aplicar_prov)

                q1,q2,q3=st.columns(3)
                q1.metric("Saldo del pago",money(disponible_prov))
                q2.metric("Se aplicará",money(aplicar_prov))
                q3.metric("Quedará disponible",money(saldo_pago_prov))

                if ids_docs_prov and saldo_docs_prov>0:
                    st.info(f"Los documentos seleccionados conservarán {money(saldo_docs_prov)} pendientes después de esta aplicación.")

                confirma_prov_aux=st.checkbox(
                    "Confirmo que deseo aplicar este pago a los documentos seleccionados. No se generará un nuevo asiento contable.",
                    key="aux_confirma_proveedor"
                )

                if st.button(
                    "🔗 Aplicar pago a documento(s)",
                    type="primary",
                    disabled=(not confirma_prov_aux or not ids_docs_prov),
                    key="aux_aplicar_proveedor"
                ):
                    sgci_exigir_permiso(conn, 'cxp', 'editar', 'Pagos de proveedores')
                    try:
                        apps_prov,saldo_prov=aplicar_pago_auxiliar_proveedor(
                            conn,id_prov_aux,pago_id_prov,ids_docs_prov
                        )
                        total_ap_prov=sum(x[1] for x in apps_prov)
                        sgci_exito(
                            f"Aplicación auxiliar realizada por {money(total_ap_prov)}. "
                            f"Saldo disponible del pago: {money(saldo_prov)}."
                        )
                        st.rerun()
                    except Exception as e:
                        st.error(f"No se pudo aplicar el pago: {e}")

        st.divider()
        st.subheader("Control contable del auxiliar")
        df = conciliacion_proveedores(conn)
        if df.empty:
            st.warning("No se pudo determinar la cuenta de proveedores.")
        else:
            st.dataframe(formatear_montos_df(df), use_container_width=True, hide_index=True)
            diferencia = df.iloc[0]["Diferencia"]
            if abs(diferencia) < 0.01:
                sgci_exito("🟢 Auxiliar de proveedores conciliado.")
            else:
                st.error(f"🔴 Diferencia: {money(diferencia)}")


# ============================================================
# PLAN DE CUENTAS
# ============================================================

elif menu == "📋 Plan de Cuentas":

    st.title("📋 Plan de Cuentas")

    pestañas = st.tabs(["Plan", "Cuentas de enlace", "Nueva cuenta", "Editar cuenta"])

    with pestañas[0]:
        df = pd.read_sql_query(
            """
            SELECT
                codigo AS Código,
                nombre AS Cuenta,
                categoria AS Categoría,
                tipo AS Tipo,
                padre_codigo AS Padre,
                nivel AS Nivel
            FROM plan_cuentas
            ORDER BY codigo
            """,
            conn
        )
        st.dataframe(formatear_montos_df(df), use_container_width=True, hide_index=True)
        if not df.empty:
            pdf = pdf_desde_dataframe("Plan de Cuentas","SGCI - Sistema de Gestión Contable Integral",df)
            st.download_button("🖨️ Imprimir / PDF Plan de Cuentas",pdf,"plan_de_cuentas.pdf","application/pdf",key="pdf_plan_cuentas")

    with pestañas[1]:
        roles = cargar_roles(conn)

        for rol, (descripcion, defecto) in ROLES.items():
            actual = roles.get(rol)
            opciones = cuentas_imputables(conn)
            mapa = dict(zip(opciones["etiqueta"], opciones["codigo"]))

            codigo_actual = actual[0] if actual else defecto
            etiquetas = list(mapa.keys())
            seleccionado = None

            for etiqueta in etiquetas:
                if etiqueta.startswith(codigo_actual + " - "):
                    seleccionado = etiqueta
                    break

            if seleccionado is None:
                seleccionado = etiquetas[0]

            nuevo = st.selectbox(
                descripcion,
                etiquetas,
                index=etiquetas.index(seleccionado),
                key=f"rol_{rol}"
            )

            if st.button(f"Guardar {descripcion}", key=f"guardar_rol_{rol}"):
                guardar_rol(conn, rol, mapa[nuevo])
                sgci_exito("Configuración guardada.")

    with pestañas[2]:
        with st.form("nueva_cuenta"):
            codigo = st.text_input("Código")
            nombre = st.text_input("Nombre")
            categoria = st.selectbox("Categoría", ["Activo", "Pasivo", "Patrimonio", "Nominal"])
            tipo = st.selectbox("Tipo", ["Activo", "Pasivo", "Patrimonio", "Ingresos", "Gastos"])
            padre = st.text_input("Código padre")
            nivel = st.number_input("Nivel", min_value=1, max_value=10, value=3)

            if st.form_submit_button("Crear cuenta"):
                try:
                    conn.execute(
                        """
                        INSERT INTO plan_cuentas
                        (
                            codigo,
                            nombre,
                            categoria,
                            tipo,
                            padre_codigo,
                            nivel
                        )
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            codigo.strip(),
                            nombre.strip(),
                            categoria,
                            tipo,
                            padre.strip() or None,
                            nivel
                        )
                    )
                    conn.commit()
                    sgci_exito("Cuenta creada.")
                except Exception as e:
                    st.error(str(e))

    with pestañas[3]:
        st.subheader("Editar cuenta existente")
        st.caption("Permite corregir la estructura de una cuenta sin cambiar su código contable ni eliminar sus movimientos.")

        cuentas_editar = pd.read_sql_query(
            """
            SELECT codigo, nombre, categoria, tipo, padre_codigo, nivel
            FROM plan_cuentas
            ORDER BY codigo
            """,
            conn
        )

        if cuentas_editar.empty:
            st.info("No hay cuentas contables para editar.")
        else:
            etiquetas_editar = (cuentas_editar["codigo"] + " - " + cuentas_editar["nombre"]).tolist()
            seleccion_editar = st.selectbox(
                "Cuenta a editar",
                etiquetas_editar,
                key="editar_cuenta_seleccion"
            )
            codigo_editar = seleccion_editar.split(" - ", 1)[0]
            fila_editar = cuentas_editar.loc[cuentas_editar["codigo"] == codigo_editar].iloc[0]

            categorias = ["Activo", "Pasivo", "Patrimonio", "Nominal"]
            tipos = ["Activo", "Pasivo", "Patrimonio", "Ingresos", "Gastos"]

            padres_df = cuentas_editar.loc[cuentas_editar["codigo"] != codigo_editar, ["codigo", "nombre"]].copy()
            opciones_padre = ["Sin cuenta padre"] + (padres_df["codigo"] + " - " + padres_df["nombre"]).tolist()
            padre_actual = fila_editar["padre_codigo"]
            padre_actual = "" if pd.isna(padre_actual) else str(padre_actual).strip()
            indice_padre = 0
            if padre_actual:
                for i, etiqueta in enumerate(opciones_padre):
                    if etiqueta.startswith(padre_actual + " - "):
                        indice_padre = i
                        break

            with st.form("editar_cuenta_form"):
                st.text_input("Código", value=codigo_editar, disabled=True)
                nombre_editar = st.text_input("Nombre", value=str(fila_editar["nombre"] or ""))
                categoria_actual = str(fila_editar["categoria"] or "Activo")
                tipo_actual = str(fila_editar["tipo"] or "Activo")
                categoria_editar = st.selectbox(
                    "Categoría",
                    categorias,
                    index=categorias.index(categoria_actual) if categoria_actual in categorias else 0
                )
                tipo_editar = st.selectbox(
                    "Tipo",
                    tipos,
                    index=tipos.index(tipo_actual) if tipo_actual in tipos else 0
                )
                padre_editar = st.selectbox(
                    "Cuenta padre",
                    opciones_padre,
                    index=indice_padre
                )
                nivel_editar = st.number_input(
                    "Nivel",
                    min_value=1,
                    max_value=10,
                    value=int(fila_editar["nivel"] or 1),
                    step=1
                )

                guardar_edicion = st.form_submit_button("Guardar cambios", type="primary")

            if guardar_edicion:
                nuevo_padre = None if padre_editar == "Sin cuenta padre" else padre_editar.split(" - ", 1)[0]
                try:
                    if nuevo_padre == codigo_editar:
                        raise ValueError("Una cuenta no puede ser padre de sí misma.")

                    ancestro = nuevo_padre
                    visitados = set()
                    while ancestro:
                        if ancestro == codigo_editar:
                            raise ValueError("La cuenta padre seleccionada generaría una jerarquía circular.")
                        if ancestro in visitados:
                            break
                        visitados.add(ancestro)
                        row_padre = conn.execute(
                            "SELECT padre_codigo FROM plan_cuentas WHERE codigo = ?",
                            (ancestro,)
                        ).fetchone()
                        if not row_padre:
                            break
                        ancestro = row_padre[0]

                    conn.execute(
                        """
                        UPDATE plan_cuentas
                        SET nombre = ?, categoria = ?, tipo = ?, padre_codigo = ?, nivel = ?
                        WHERE codigo = ?
                        """,
                        (
                            nombre_editar.strip(),
                            categoria_editar,
                            tipo_editar,
                            nuevo_padre,
                            int(nivel_editar),
                            codigo_editar
                        )
                    )
                    conn.commit()
                    sgci_exito(f"Cuenta {codigo_editar} actualizada correctamente.")
                    st.rerun()
                except Exception as e:
                    conn.rollback()
                    st.error(f"No se pudo actualizar la cuenta: {e}")


# ============================================================
# REGLAS CONTABLES
# ============================================================

elif menu == "⚙️ Reglas Contables":

    st.title("⚙️ Reglas de clasificación contable")
    st.info(
        """
        Las reglas tienen prioridad sobre la cuenta habitual del cliente/proveedor. 
        Esto permite que el SGCI aprenda la clasificación contable de cada empresa.
        """
    )

    cuentas = cuentas_imputables(conn)
    mapa_cuentas = dict(zip(cuentas["etiqueta"], cuentas["codigo"]))

    with st.form("nueva_regla"):
        tipo = st.selectbox("Tipo", ["compras", "ventas"])
        rut = st.text_input("RUT específico (opcional)")
        patron = st.text_input("Texto que debe contener la razón social (opcional)")
        tipo_doc = st.number_input("Tipo de documento (0 = cualquiera)", min_value=0, max_value=999, value=0)
        cuenta_label = st.selectbox("Cuenta contable", list(mapa_cuentas.keys()))
        prioridad = st.number_input("Prioridad", min_value=1, max_value=1000, value=100)
        descripcion = st.text_input("Descripción")

        if st.form_submit_button("Guardar regla"):
            guardar_regla(
                conn,
                tipo,
                rut,
                patron,
                None if tipo_doc == 0 else tipo_doc,
                mapa_cuentas[cuenta_label],
                prioridad,
                descripcion
            )
            sgci_exito("Regla guardada.")

    st.divider()
    st.subheader("Reglas configuradas actualmente")

    reglas = pd.read_sql_query(
        """
        SELECT
            r.id AS ID,
            r.tipo AS Tipo,
            r.rut AS RUT,
            r.patron AS Patrón,
            r.tipo_doc AS Tipo_Doc,
            r.codigo_cuenta AS Cuenta,
            p.nombre AS Nombre_Cuenta,
            r.prioridad AS Prioridad,
            r.activa AS Activa,
            r.descripcion AS Descripción
        FROM reglas_contables r
        LEFT JOIN plan_cuentas p
            ON p.codigo = r.codigo_cuenta
        ORDER BY
            r.tipo,
            r.prioridad DESC
        """,
        conn
    )

    if reglas.empty:
        st.info("No hay reglas contables registradas todavía.")
    else:
        st.dataframe(reglas, use_container_width=True, hide_index=True)


# ============================================================
# LOTES
# ============================================================

elif menu == "📦 Lotes":

    st.title("📦 Lotes de contabilización")
    df = listar_lotes(conn)

    if df.empty:
        st.info("No existen lotes.")
    else:
        st.dataframe(formatear_montos_df(df), use_container_width=True, hide_index=True)
        st.divider()

        lote = st.selectbox("Seleccionar lote", df["Lote"].tolist())
        st.warning(
            "Deshacer un lote elimina los movimientos "
            "contables y documentos asociados a ese lote."
        )

        if st.button("🗑️ DESHACER LOTE", type="secondary"):
            sgci_exigir_permiso(conn, 'administracion', 'anular', 'Lotes')
            try:
                resultado = deshacer_lote(conn, lote)
                sgci_exito(f"Lote eliminado: {resultado}")
            except Exception as e:
                st.error(f"No fue posible eliminar el lote: {e}")


# ============================================================
# MATRIZ CONTABLE
# ============================================================

elif menu == "🧰 Matriz Contable":

    st.title("🧰 Importación de matriz contable")
    st.info(
        """
        Formato esperado:
        fecha | cuenta | debe | haber | glosa

        Opcionales:
        asiento | centro_costo
        """
    )

    archivo = st.file_uploader("Cargar matriz contable", type=["csv", "xlsx", "xls"], key="matriz")

    if archivo:
        try:
            df = leer_archivo_tabular(archivo)
            df.columns = [str(c).strip().lower() for c in df.columns]

            obligatorias = ["fecha", "cuenta", "debe", "haber", "glosa"]
            faltantes = [c for c in obligatorias if c not in df.columns]

            if faltantes:
                st.error("Faltan columnas: " + ", ".join(faltantes))
            else:
                plan = Plan(conn)
                resultado = pd.DataFrame()

                resultado["fecha"] = df["fecha"].apply(fecha_iso)
                resultado["cuenta_original"] = df["cuenta"].astype(str).str.strip()

                resuelto = resultado["cuenta_original"].apply(plan.resolver)

                resultado["codigo"] = resuelto.apply(lambda x: x[0] if x else None)
                resultado["cuenta"] = resuelto.apply(lambda x: x[1] if x else None)
                resultado["debe"] = df["debe"].apply(numero)
                resultado["haber"] = df["haber"].apply(numero)
                resultado["glosa"] = df["glosa"].fillna("").astype(str)

                if "centro_costo" in df.columns:
                    resultado["centro_costo"] = df["centro_costo"].fillna("General / Ninguno")
                else:
                    resultado["centro_costo"] = "General / Ninguno"

                if "asiento" in df.columns:
                    resultado["asiento"] = pd.to_numeric(df["asiento"], errors="coerce")
                else:
                    resultado["asiento"] = 1

                errores = []

                for i, fila in resultado.iterrows():
                    if not fila["fecha"]:
                        errores.append(f"Línea {i+2}: fecha inválida.")
                    if not fila["codigo"]:
                        errores.append(f"Línea {i+2}: cuenta '{fila['cuenta_original']}' no encontrada.")
                    if fila["debe"] > 0 and fila["haber"] > 0:
                        errores.append(f"Línea {i+2}: Debe y Haber simultáneos.")
                    if fila["debe"] == 0 and fila["haber"] == 0:
                        errores.append(f"Línea {i+2}: Debe y Haber están en cero.")

                for asiento_id, grupo in resultado.groupby("asiento"):
                    if abs(grupo["debe"].sum() - grupo["haber"].sum()) > 0.01:
                        errores.append(f"Asiento {asiento_id}: descuadrado.")

                if errores:
                    st.error("\n".join(errores[:30]))
                else:
                    sgci_exito("Matriz validada correctamente.")
                    st.dataframe(resultado, use_container_width=True, hide_index=True)

                    if st.button("✅ IMPORTAR MATRIZ", type="primary"):
                        sgci_exigir_permiso(conn, 'administracion', 'importar', 'Matriz Contable')
                        lote = "MATRIZ-" + datetime.now().strftime("%Y%m%d-%H%M%S")
                        cur = conn.cursor()
                        base = siguiente_asiento(conn)

                        mapa_asientos = {
                            n: i + 1
                            for i, n in enumerate(sorted(resultado["asiento"].unique()))
                        }

                        try:
                            for fila in resultado.itertuples():
                                asiento = base + mapa_asientos[fila.asiento]

                                cur.execute(
                                    """
                                    INSERT INTO libro_diario
                                    (
                                        fecha,
                                        cuenta,
                                        debe,
                                        haber,
                                        glosa,
                                        centro_costo,
                                        codigo_cuenta,
                                        asiento_id,
                                        lote_id,
                                        origen
                                    )
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                    """,
                                    (
                                        fila.fecha,
                                        fila.cuenta,
                                        fila.debe,
                                        fila.haber,
                                        fila.glosa,
                                        fila.centro_costo,
                                        fila.codigo,
                                        asiento,
                                        lote,
                                        "Matriz contable"
                                    )
                                )

                            conn.commit()
                            sgci_exito(f"Matriz importada. Lote: {lote}")
                        except Exception as e:
                            conn.rollback()
                            st.error(f"Error: {e}")

        except Exception as e:
            st.error(f"Error leyendo matriz: {e}")


# ============================================================
# PIE
# ============================================================

st.sidebar.divider()
st.sidebar.caption("SGCI • Sistema de Gestión Contable Integral")
st.sidebar.caption("Motor contable + auxiliares + RCV + conciliación")

conn.close()

from contextlib import closing
# CONTEM: componente extraído del app.py original; ejecución secuencial compartida.
def sgci_empresa_esquema(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS sgci_perfil_empresa (
        id INTEGER PRIMARY KEY CHECK (id=1), razon_social TEXT NOT NULL DEFAULT '',
        rut TEXT DEFAULT '', giro TEXT DEFAULT '', direccion TEXT DEFAULT '',
        comuna TEXT DEFAULT '', ciudad TEXT DEFAULT '', telefono TEXT DEFAULT '',
        correo TEXT DEFAULT '', sitio_web TEXT DEFAULT '', logo BLOB,
        logo_mime TEXT DEFAULT '', actualizado TEXT DEFAULT '')""")
    conn.commit()

def sgci_perfil(conn):
    sgci_empresa_esquema(conn)
    fila=conn.execute('SELECT * FROM sgci_perfil_empresa WHERE id=1').fetchone()
    return dict(fila) if fila else {}

def sgci_membrete_pdf(canvas, doc):
    """Encabezado de empresa en cada página de los PDF ReportLab SGCI."""
    from reportlab.lib.utils import ImageReader
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.pdfbase.pdfmetrics import stringWidth
    # El callback ReportLab se ejecuta al construir el PDF, fuera del
    # alcance de la conexión de la pantalla. Leer el perfil desde SQLite
    # sin escribir ni depender de un 'conn' global inexistente.
    perfil = {}
    try:
        with closing(sqlite3.connect('file:' + os.path.abspath(DB_FILE) + '?mode=ro', uri=True)) as pdf_conn, pdf_conn:
            pdf_conn.row_factory = sqlite3.Row
            fila = pdf_conn.execute('SELECT * FROM sgci_perfil_empresa WHERE id=1').fetchone()
            perfil = dict(fila) if fila else {}
    except (sqlite3.Error, OSError):
        pass
    w,h=doc.pagesize
    x=doc.leftMargin
    y=h-11*mm
    logo=perfil.get('logo')
    if logo:
        try:
            from PIL import Image as PILImage
            pic=PILImage.open(io.BytesIO(logo))
            pic.thumbnail((260,130))
            canvas.drawImage(ImageReader(pic),x,y-17*mm,width=27*mm,height=17*mm,preserveAspectRatio=True,anchor='c',mask='auto')
            x+=31*mm
        except Exception:
            pass
    nombre=str(perfil.get('razon_social') or 'Empresa sin configurar')[:110]
    canvas.setFont('Helvetica-Bold',10)
    canvas.setFillColor(colors.HexColor('#35432D'))
    canvas.drawString(x,y,nombre)
    canvas.setFont('Helvetica',7.5)
    canvas.setFillColor(colors.HexColor('#5C6459'))
    linea='RUT: '+str(perfil.get('rut') or 'Sin RUT')
    if perfil.get('giro'): linea+='  |  '+str(perfil['giro'])
    canvas.drawString(x,y-10,linea[:140])
    ubicacion=', '.join(filter(None,[perfil.get('direccion'),perfil.get('comuna'),perfil.get('ciudad')]))
    contacto=' | '.join(filter(None,[ubicacion,perfil.get('telefono'),perfil.get('correo')]))
    canvas.drawString(x,y-20,contacto[:155])
    canvas.setStrokeColor(colors.HexColor('#A8B6A0'))
    canvas.line(doc.leftMargin,h-31*mm,w-doc.rightMargin,h-31*mm)
    canvas.setFont('Helvetica',7)
    canvas.drawRightString(w-doc.rightMargin,9*mm,f'Página {doc.page}')

def sgci_pantalla_empresa(conn):
    sgci_exigir_permiso(conn,'administracion','ver')
    if not sgci_es_propietario():
        st.error('La configuración de empresa requiere acceso del administrador principal.')
        return
    st.title('🏢 Datos de la empresa y logo')
    st.caption('Estos datos se utilizarán en el membrete de los reportes PDF compatibles. No altera asientos ni documentos.')
    actual=sgci_perfil(conn)
    with st.form('sgci_form_empresa'):
        razon=st.text_input('Razón social *',value=actual.get('razon_social') or '')
        rut=st.text_input('RUT',value=actual.get('rut') or '')
        giro=st.text_input('Giro',value=actual.get('giro') or '')
        direccion=st.text_input('Dirección',value=actual.get('direccion') or '')
        a,b=st.columns(2)
        comuna=a.text_input('Comuna',value=actual.get('comuna') or '')
        ciudad=b.text_input('Ciudad',value=actual.get('ciudad') or '')
        telefono=st.text_input('Teléfono',value=actual.get('telefono') or '')
        correo=st.text_input('Correo electrónico',value=actual.get('correo') or '')
        web=st.text_input('Sitio web',value=actual.get('sitio_web') or '')
        logo=st.file_uploader('Logo PNG o JPG (máximo 2 MB)',type=['png','jpg','jpeg'],key='sgci_logo_empresa')
        quitar=st.checkbox('Eliminar logo guardado')
        guardar=st.form_submit_button('Guardar datos de empresa',type='primary')
    if actual.get('logo'):
        st.image(bytes(actual['logo']),width=180,caption='Logo guardado actualmente')
    if guardar:
        if not razon.strip():
            st.error('La razón social es obligatoria.')
            return
        imagen=None if quitar else actual.get('logo')
        mime='' if quitar else (actual.get('logo_mime') or '')
        if logo is not None:
            datos=logo.getvalue()
            if len(datos)>2*1024*1024:
                st.error('El logo supera 2 MB.');return
            from PIL import Image as PILImage
            try:
                pic=PILImage.open(io.BytesIO(datos));pic.verify()
                if pic.format not in ('PNG','JPEG'): raise ValueError('Formato no permitido')
            except Exception:
                st.error('El archivo no es una imagen PNG/JPG válida.');return
            imagen=datos;mime=logo.type
        conn.execute("""INSERT INTO sgci_perfil_empresa
            (id,razon_social,rut,giro,direccion,comuna,ciudad,telefono,correo,sitio_web,logo,logo_mime,actualizado)
            VALUES (1,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
            razon_social=excluded.razon_social,rut=excluded.rut,giro=excluded.giro,
            direccion=excluded.direccion,comuna=excluded.comuna,ciudad=excluded.ciudad,
            telefono=excluded.telefono,correo=excluded.correo,sitio_web=excluded.sitio_web,
            logo=excluded.logo,logo_mime=excluded.logo_mime,actualizado=excluded.actualizado""",
            (razon.strip(),rut.strip(),giro.strip(),direccion.strip(),comuna.strip(),ciudad.strip(),
             telefono.strip(),correo.strip(),web.strip(),imagen,mime,datetime.now().isoformat(timespec='seconds')))
        conn.commit()
        st.success('Datos de empresa guardados. Se aplicarán a los nuevos PDF generados.')

# ============================================================
# ORDENES DE COMPRA - modulo aislado, sin asientos contables
# ============================================================
def oc_crear_tablas(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS ordenes_compra (
      id INTEGER PRIMARY KEY AUTOINCREMENT, numero TEXT UNIQUE,
      proveedor_id INTEGER NOT NULL REFERENCES proveedores(id), fecha TEXT NOT NULL,
      condicion_pago TEXT, observaciones TEXT, estado TEXT NOT NULL DEFAULT 'BORRADOR',
      neto INTEGER NOT NULL DEFAULT 0, iva INTEGER NOT NULL DEFAULT 0,
      total INTEGER NOT NULL DEFAULT 0, creado_en TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS ordenes_compra_detalle (
      id INTEGER PRIMARY KEY AUTOINCREMENT, oc_id INTEGER NOT NULL REFERENCES ordenes_compra(id),
      descripcion TEXT NOT NULL, cantidad REAL NOT NULL, precio_unitario REAL NOT NULL,
      afecto_iva INTEGER NOT NULL DEFAULT 1, neto INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS ordenes_compra_facturas (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      oc_id INTEGER NOT NULL REFERENCES ordenes_compra(id),
      compra_id INTEGER NOT NULL REFERENCES compras(id),
      monto_asociado INTEGER NOT NULL CHECK(monto_asociado > 0),
      creado_en TEXT NOT NULL, UNIQUE(oc_id, compra_id));
    CREATE INDEX IF NOT EXISTS idx_oc_proveedor ON ordenes_compra(proveedor_id);
    CREATE INDEX IF NOT EXISTS idx_oc_factura ON ordenes_compra_facturas(compra_id);
    """)
    conn.commit()

def oc_pdf(conn, oc_id):
    """OC corporativa: reutiliza el perfil y logotipo ya configurados en SGCI."""
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, KeepTogether
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_RIGHT, TA_CENTER
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from xml.sax.saxutils import escape
    oc=conn.execute("""SELECT o.*,p.rut,p.nombre,p.razon_social,p.direccion,p.comuna,p.ciudad,
        p.email,p.telefono FROM ordenes_compra o JOIN proveedores p ON p.id=o.proveedor_id
        WHERE o.id=?""",(oc_id,)).fetchone()
    if oc is None: raise ValueError('Orden de compra no encontrada.')
    detalle=conn.execute('SELECT * FROM ordenes_compra_detalle WHERE oc_id=? ORDER BY id',(oc_id,)).fetchall()
    perfil=sgci_perfil(conn)
    if not perfil.get('razon_social'):
        emp=conn.execute('SELECT * FROM empresa ORDER BY id LIMIT 1').fetchone()
        if emp: perfil={**dict(emp),**{k:v for k,v in perfil.items() if v}}
    e=lambda x:escape(str(x or ''))
    navy=colors.HexColor('#23618C'); gray=colors.HexColor('#F0F4F6')
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name='OCtitle',parent=styles['Title'],fontSize=17,leading=21,textColor=navy,spaceAfter=12))
    styles.add(ParagraphStyle(name='OCsmall',parent=styles['Normal'],fontSize=8.5,leading=12))
    styles.add(ParagraphStyle(name='OChead',parent=styles['Normal'],fontSize=8,leading=11,textColor=colors.white,fontName='Helvetica-Bold'))
    styles.add(ParagraphStyle(name='OCright',parent=styles['Normal'],fontSize=9,leading=13,alignment=TA_RIGHT))
    buf=io.BytesIO()
    doc=SimpleDocTemplate(buf,pagesize=A4,topMargin=39*mm,bottomMargin=23*mm,leftMargin=18*mm,rightMargin=18*mm)
    width=A4[0]-36*mm
    story=[Paragraph('ORDEN DE COMPRA',styles['OCtitle'])]
    def cell(label,value):return Paragraph('<b>'+e(label)+'</b> '+e(value),styles['OCsmall'])
    meta=Table([[cell('N.º OC:',oc['numero']),cell('Fecha:',oc['fecha'])],
                [cell('Estado:',oc['estado']),cell('Condición de pago:',oc['condicion_pago'])]],colWidths=[width*.48,width*.52])
    meta.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),gray),('BOX',(0,0),(-1,-1),.5,colors.HexColor('#CED9DF')),('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),8)]))
    story.extend([meta,Spacer(1,15),Paragraph('<b>DATOS DEL PROVEEDOR</b>',styles['Heading3'])])
    prov=[cell('Razón social:',oc['razon_social'] or oc['nombre']),cell('RUT:',oc['rut']),
          cell('Dirección:',', '.join(filter(None,[oc['direccion'],oc['comuna'],oc['ciudad']]))),
          cell('Contacto:',' | '.join(filter(None,[oc['email'],oc['telefono']]))) ]
    story.extend(prov+[Spacer(1,15)])
    rows=[[Paragraph(h,styles['OChead']) for h in ('CANT.','DESCRIPCIÓN','PRECIO UNIT.','TOTAL NETO')]]
    for d in detalle:
        rows.append([Paragraph(e(f"{d['cantidad']:g}"),styles['OCsmall']),Paragraph(e(d['descripcion'])+(' (Exento)' if not d['afecto_iva'] else ''),styles['OCsmall']),Paragraph(e(money(d['precio_unitario'])),styles['OCsmall']),Paragraph(e(money(d['neto'])),styles['OCsmall'])])
    tab=Table(rows,colWidths=[width*.12,width*.48,width*.20,width*.20],repeatRows=1,hAlign='LEFT')
    tab.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),navy),('GRID',(0,0),(-1,-1),.35,colors.HexColor('#CBD5DA')),('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),8)]))
    story.extend([tab,Spacer(1,12)])
    totals=Table([[Paragraph('Subtotal neto',styles['OCright']),Paragraph(money(oc['neto']),styles['OCright'])],
                  [Paragraph('IVA',styles['OCright']),Paragraph(money(oc['iva']),styles['OCright'])],
                  [Paragraph('<b>TOTAL</b>',styles['OCright']),Paragraph('<b>'+money(oc['total'])+'</b>',styles['OCright'])]],colWidths=[width*.77,width*.23],hAlign='RIGHT')
    totals.setStyle(TableStyle([('LINEABOVE',(0,2),(-1,2),1,navy),('BACKGROUND',(0,2),(-1,2),gray),('BOTTOMPADDING',(0,0),(-1,-1),7)]))
    story.extend([totals,Spacer(1,15),Paragraph('<b>OBSERVACIONES Y CONDICIONES</b>',styles['Heading3']),Paragraph(e(oc['observaciones']) or 'Sin observaciones adicionales.',styles['OCsmall']),Spacer(1,35)])
    sign=Table([['________________________________','________________________________'],['Autorizado por','Fecha / Firma']],colWidths=[width/2,width/2])
    sign.setStyle(TableStyle([('ALIGN',(0,0),(-1,-1),'CENTER'),('FONTSIZE',(0,0),(-1,-1),8),('TEXTCOLOR',(0,0),(-1,-1),colors.HexColor('#59636A'))]))
    story.append(sign)
    def header(canvas,doc):
        from reportlab.lib.utils import ImageReader
        from PIL import Image as PILImage
        canvas.saveState()
        x=doc.leftMargin; y=A4[1]-15*mm
        logo=perfil.get('logo')
        if logo:
            try:
                pic=PILImage.open(io.BytesIO(logo))
                canvas.drawImage(ImageReader(pic),x,y-16*mm,width=26*mm,height=16*mm,preserveAspectRatio=True,anchor='c',mask='auto')
                x+=30*mm
            except Exception:pass
        canvas.setFillColor(navy);canvas.setFont('Helvetica-Bold',11)
        canvas.drawString(x,y,e(perfil.get('razon_social') or 'Empresa sin configurar')[:65])
        canvas.setFillColor(colors.HexColor('#485760'));canvas.setFont('Helvetica',7.5)
        canvas.drawString(x,y-10,('RUT: '+str(perfil.get('rut') or '')+'  |  '+str(perfil.get('giro') or ''))[:105])
        canvas.drawString(x,y-20,', '.join(filter(None,[perfil.get('direccion'),perfil.get('comuna'),perfil.get('ciudad')]))[:105])
        canvas.drawString(x,y-30,' | '.join(filter(None,[perfil.get('telefono'),perfil.get('correo')]))[:105])
        canvas.setStrokeColor(navy);canvas.line(doc.leftMargin,A4[1]-34*mm,A4[0]-doc.rightMargin,A4[1]-34*mm)
        canvas.setFont('Helvetica',7);canvas.drawRightString(A4[0]-doc.rightMargin,10*mm,f'Página {doc.page}')
        canvas.restoreState()
    doc.build(story,onFirstPage=header,onLaterPages=header)
    return buf.getvalue()

def oc_pantalla(conn):
    st.title('🧾 Órdenes de compra')
    t_crear,t_listar,t_asociar=st.tabs(['➕ Crear OC','📋 Administrar OC','🔗 Asociar facturas RCV'])
    proveedores=conn.execute("SELECT id,rut,COALESCE(NULLIF(razon_social,''),nombre,rut) nombre FROM proveedores WHERE COALESCE(activo,1)=1 ORDER BY nombre").fetchall()
    opciones={f"{p['nombre']} ({p['rut']})":p['id'] for p in proveedores}
    with t_crear:
        if not opciones: st.warning('Primero registra un proveedor en Compras → Proveedores.')
        else:
            with st.form('oc_nueva',clear_on_submit=True):
                proveedor=st.selectbox('Proveedor',list(opciones))
                fecha=st.date_input('Fecha de emisión',value=date.today())
                condicion=st.selectbox('Condición de pago',['Crédito 30 días','Contado','Crédito 15 días','Crédito 60 días','Otra'])
                observaciones=st.text_area('Observaciones')
                st.caption('Ingresa precios netos. Cada línea puede ser afecta o exenta de IVA.')
                lineas=st.data_editor(pd.DataFrame([{'Descripción':'','Cantidad':1.0,'Precio neto':0.0,'Afecto IVA':True}]),num_rows='dynamic',hide_index=True,use_container_width=True,key='oc_lineas')
                guardar=st.form_submit_button('Guardar borrador de OC',type='primary')
            if guardar:
                detalles=[]
                for _,r in lineas.iterrows():
                    desc=str(r.get('Descripción') or '').strip()
                    if not desc: continue
                    try: cantidad=float(r['Cantidad']); precio=float(r['Precio neto'])
                    except (ValueError,TypeError): cantidad=0;precio=-1
                    if cantidad<=0 or precio<0: st.error('Cada línea debe tener cantidad positiva y precio no negativo.');st.stop()
                    neto=clp_round(cantidad*precio)
                    detalles.append((desc,cantidad,precio,int(bool(r['Afecto IVA'])),neto))
                if not detalles: st.error('Agrega al menos una línea con descripción.')
                else:
                    neto=sum(d[4] for d in detalles)
                    iva=sum(clp_round(d[4]*0.19) for d in detalles if d[3])
                    try:
                        with conn:
                            cur=conn.execute('INSERT INTO ordenes_compra(proveedor_id,fecha,condicion_pago,observaciones,neto,iva,total,creado_en) VALUES(?,?,?,?,?,?,?,?)',(opciones[proveedor],fecha.isoformat(),condicion,observaciones,neto,iva,neto+iva,datetime.now().isoformat(timespec='seconds')))
                            oc_id=cur.lastrowid; numero=f'OC-{oc_id:06d}'
                            conn.execute('UPDATE ordenes_compra SET numero=? WHERE id=?',(numero,oc_id))
                            conn.executemany('INSERT INTO ordenes_compra_detalle(oc_id,descripcion,cantidad,precio_unitario,afecto_iva,neto) VALUES(?,?,?,?,?,?)',[(oc_id,*d) for d in detalles])
                        st.success(f'{numero} guardada. Total: {money(neto+iva)}. No se generó asiento contable.')
                    except sqlite3.Error as ex: st.error(f'No se pudo guardar la OC: {ex}')
    with t_listar:
        filas=conn.execute("""SELECT o.*,COALESCE(NULLIF(p.razon_social,''),p.nombre,p.rut) proveedor,
          COALESCE((SELECT SUM(monto_asociado) FROM ordenes_compra_facturas a WHERE a.oc_id=o.id),0) facturado
          FROM ordenes_compra o JOIN proveedores p ON p.id=o.proveedor_id ORDER BY o.id DESC""").fetchall()
        if not filas: st.info('No hay órdenes de compra todavía.')
        else:
            st.dataframe(pd.DataFrame([{'OC':r['numero'],'Fecha':r['fecha'],'Proveedor':r['proveedor'],'Estado':r['estado'],'Total':r['total'],'Facturado':r['facturado'],'Pendiente':r['total']-r['facturado']} for r in filas]),hide_index=True,use_container_width=True)
            seleccion=st.selectbox('Selecciona OC',range(len(filas)),format_func=lambda i:f"{filas[i]['numero']} · {filas[i]['proveedor']}",key='oc_admin_sel')
            oc=filas[seleccion]
            st.dataframe(pd.read_sql_query('SELECT descripcion,cantidad,precio_unitario,afecto_iva,neto FROM ordenes_compra_detalle WHERE oc_id=?',conn,params=(oc['id'],)),hide_index=True,use_container_width=True)
            estados=['BORRADOR','EMITIDA','ANULADA']
            estado=st.selectbox('Estado administrativo',estados,index=estados.index(oc['estado']) if oc['estado'] in estados else 0)
            if st.button('Actualizar estado',key='oc_estado'):
                if oc['facturado'] and estado=='ANULADA': st.error('No se puede anular una OC con facturas asociadas.')
                else:
                    with conn:conn.execute('UPDATE ordenes_compra SET estado=? WHERE id=?',(estado,oc['id']))
                    st.success('Estado actualizado.');st.rerun()
            try:
                st.download_button('📄 Descargar OC en PDF',oc_pdf(conn,oc['id']),file_name=oc['numero']+'.pdf',mime='application/pdf')
            except ImportError:st.warning('Para generar PDF instala reportlab en requirements.txt.')
    with t_asociar:
        st.caption('La asociación es administrativa: no crea ni modifica asientos, pagos ni documentos del RCV.')
        ordenes=conn.execute("SELECT o.id,o.numero,o.proveedor_id,o.total,o.estado,p.rut FROM ordenes_compra o JOIN proveedores p ON p.id=o.proveedor_id WHERE o.estado!='ANULADA' ORDER BY o.id DESC").fetchall()
        if not ordenes: st.info('Primero crea una OC.')
        else:
            elegido=st.selectbox('Orden de compra',range(len(ordenes)),format_func=lambda i:ordenes[i]['numero'],key='oc_asoc_sel')
            oc=ordenes[elegido]
            asignado=conn.execute('SELECT COALESCE(SUM(monto_asociado),0) FROM ordenes_compra_facturas WHERE oc_id=?',(oc['id'],)).fetchone()[0]
            st.metric('Saldo OC por asociar',money(oc['total']-asignado))
            facturas=conn.execute("""SELECT c.id,c.fecha,c.tipo_doc,c.folio,c.monto_total,
              COALESCE((SELECT SUM(a.monto_asociado) FROM ordenes_compra_facturas a WHERE a.compra_id=c.id),0) asociado
              FROM compras c WHERE c.proveedor_id=? AND COALESCE(c.monto_total,0)>0 AND COALESCE(c.tipo_doc,33) NOT IN (60,61)
              ORDER BY c.fecha DESC,c.id DESC""",(oc['proveedor_id'],)).fetchall()
            candidatas=[f for f in facturas if f['monto_total']-f['asociado']>0 and not conn.execute('SELECT 1 FROM ordenes_compra_facturas WHERE oc_id=? AND compra_id=?',(oc['id'],f['id'])).fetchone()]
            if not candidatas:st.info('No hay facturas disponibles de este proveedor para asociar.')
            else:
                ix=st.selectbox('Factura importada / registrada',range(len(candidatas)),format_func=lambda i:f"{candidatas[i]['fecha']} · Tipo {candidatas[i]['tipo_doc']} · Folio {candidatas[i]['folio']} · Disponible {money(candidatas[i]['monto_total']-candidatas[i]['asociado'])}",key='oc_fact_sel')
                factura=candidatas[ix]
                maximo=max(0,min(clp_round(oc['total']-asignado),clp_round(factura['monto_total']-factura['asociado'])))
                if maximo:
                    monto=st.number_input('Monto a asociar (CLP, IVA incluido)',min_value=1,max_value=maximo,value=maximo,step=1,key='oc_monto_asoc')
                    if st.button('🔗 Asociar factura',type='primary'):
                        try:
                            with conn:
                                saldo_oc=conn.execute('SELECT total-COALESCE((SELECT SUM(monto_asociado) FROM ordenes_compra_facturas WHERE oc_id=?),0) FROM ordenes_compra WHERE id=?',(oc['id'],oc['id'])).fetchone()[0]
                                saldo_fac=conn.execute('SELECT monto_total-COALESCE((SELECT SUM(monto_asociado) FROM ordenes_compra_facturas WHERE compra_id=?),0) FROM compras WHERE id=? AND proveedor_id=?',(factura['id'],factura['id'],oc['proveedor_id'])).fetchone()
                                if not saldo_fac or monto>min(saldo_oc,saldo_fac[0]):raise ValueError('Saldo insuficiente o proveedor distinto.')
                                conn.execute('INSERT INTO ordenes_compra_facturas(oc_id,compra_id,monto_asociado,creado_en) VALUES(?,?,?,?)',(oc['id'],factura['id'],monto,datetime.now().isoformat(timespec='seconds')))
                            st.success('Factura asociada sin generar asiento contable.');st.rerun()
                        except (sqlite3.Error,ValueError) as ex:st.error(str(ex))
            links=conn.execute('SELECT a.id,c.fecha,c.folio,a.monto_asociado FROM ordenes_compra_facturas a JOIN compras c ON c.id=a.compra_id WHERE a.oc_id=?',(oc['id'],)).fetchall()
            if links:
                st.subheader('Facturas asociadas')
                st.dataframe(pd.DataFrame([dict(x) for x in links]),hide_index=True,use_container_width=True)
                borrar=st.selectbox('Desvincular asociación',range(len(links)),format_func=lambda i:f"Folio {links[i]['folio']} · {money(links[i]['monto_asociado'])}")
                if st.button('Desvincular factura'):
                    with conn:conn.execute('DELETE FROM ordenes_compra_facturas WHERE id=?',(links[borrar]['id'],))
                    st.success('Asociación eliminada; factura y contabilidad intactas.');st.rerun()

# ============================================================
# INICIALIZACIÓN
# ============================================================


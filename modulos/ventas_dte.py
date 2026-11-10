# CONTEM: componente extraído del app.py original; ejecución secuencial compartida.
def dte_html_factura(fila, items, refs):
    # Representación documental HTML basada en XML; no es DTE oficial.
    esc=lambda x: html.escape(str(x if x is not None else ''), quote=True)
    def pesos(x):
        return '$ ' + f'{round(float(x or 0)):,}'.replace(',', '.')
    def numero(x):
        if x is None: return '—'
        return f'{float(x):,.3f}'.rstrip('0').rstrip('.').replace(',', 'X').replace('.', ',').replace('X','.')
    fecha=esc(fila['fecha'])
    try: fecha= datetime.strptime(str(fila['fecha']), '%Y-%m-%d').strftime('%d/%m/%Y')
    except (ValueError,TypeError): pass
    filas=[]
    for item in items.itertuples(index=False):
        desc=esc(item.nombre or '')
        if item.descripcion: desc += '<div class="desc">'+esc(item.descripcion).replace('\n','<br>')+'</div>'
        filas.append('<tr><td>'+esc(item.codigo or '—')+'</td><td>'+desc+'</td><td class="num">'+numero(item.cantidad)+'</td><td>'+esc(item.unidad or '—')+'</td><td class="num">'+pesos(item.precio)+'</td><td class="num">'+pesos(item.descuento)+'</td><td class="num">'+pesos(item.monto)+'</td></tr>')
    referencias=''.join('<div><b>'+esc(r.tipo_ref or 'Referencia')+' '+esc(r.folio_ref)+'</b> · '+esc(r.fecha_ref)+' · '+esc(r.razon_ref)+'</div>' for r in refs.itertuples(index=False)) or '<div>Sin referencias</div>'
    tipo=esc(nombre_documento(fila['tipo_doc']).upper())
    return f'''<html lang="es"><head><meta charset="utf-8"><style>
    *{{box-sizing:border-box}} body{{font-family:Arial,Helvetica,sans-serif;color:#273326;background:#fff;margin:0;padding:18px;font-size:12px}}
    .sheet{{max-width:940px;margin:auto;border:1px solid #c7d0c4;padding:24px;background:white}}
    .head{{display:flex;justify-content:space-between;gap:18px;align-items:flex-start}}
    .emisor{{flex:1;line-height:1.65}} .emisor strong{{font-size:17px}}
    .folio{{width:255px;border:2px solid #a53232;text-align:center;padding:13px 8px;color:#a53232;font-weight:bold;line-height:1.65;font-size:15px}}
    .folio .numfolio{{font-size:22px}} .subtitle{{text-align:right;margin-top:5px;font-size:11px}}
    .section{{margin-top:22px;border:1px solid #c7d0c4;padding:12px 14px;line-height:1.75}}
    .sectiontitle{{font-size:11px;letter-spacing:.7px;text-transform:uppercase;color:#586854;font-weight:bold;margin-bottom:5px}}
    .receptor{{display:grid;grid-template-columns:1fr 1fr;gap:4px 20px}}
    table{{width:100%;border-collapse:collapse;margin-top:20px;table-layout:fixed}}
    th{{background:#edf1ea;text-align:left;border:1px solid #b9c5b7;padding:9px 6px;font-size:11px}}
    td{{border:1px solid #d3dad1;padding:10px 6px;vertical-align:top;overflow-wrap:anywhere}}
    th:nth-child(1){{width:9%}} th:nth-child(2){{width:35%}} th:nth-child(3){{width:9%}} th:nth-child(4){{width:9%}} th:nth-child(5){{width:13%}} th:nth-child(6){{width:12%}} th:nth-child(7){{width:13%}}
    .num{{text-align:right;white-space:nowrap}} .desc{{margin-top:6px;color:#455444;white-space:normal;line-height:1.45}}
    .bottom{{display:grid;grid-template-columns:1fr 285px;gap:24px;margin-top:20px}}
    .totales{{border:1px solid #b9c5b7;padding:12px}} .totalrow{{display:flex;justify-content:space-between;padding:7px 0;border-bottom:1px solid #e6e9e3}}
    .totalrow.grand{{font-size:16px;font-weight:bold;border-top:2px solid #61725b;border-bottom:0}}
    .nota{{font-size:10px;color:#5e6a5b;margin-top:18px;border-top:1px solid #d3dad1;padding-top:10px}}
    @media print{{body{{padding:0}}.sheet{{border:none;padding:4mm;max-width:none}} @page{{size:A4;margin:12mm}}}}
    </style></head><body><div class="sheet">
    <div class="head"><div class="emisor"><strong>{esc(fila['razon_emisor'])}</strong><br>
    <b>RUT:</b> {esc(fila['rut_emisor'])}<br><b>Giro:</b> {esc(fila['giro_emisor'])}<br>
    <b>Dirección:</b> {esc(fila['direccion_emisor'])}<br><b>Comuna:</b> {esc(fila['comuna_emisor'])}</div>
    <div><div class="folio">R.U.T. {esc(fila['rut_emisor'])}<br>{tipo}<br><span class="numfolio">N.º {esc(fila['folio'])}</span></div>
    <div class="subtitle">Fecha de emisión: {fecha}</div></div></div>
    <div class="section"><div class="sectiontitle">Datos del receptor</div><div class="receptor">
    <div><b>Señor(es):</b> {esc(fila['razon_receptor'])}</div><div><b>RUT:</b> {esc(fila['rut_receptor'])}</div>
    <div><b>Giro:</b> {esc(fila['giro_receptor'])}</div><div><b>Comuna:</b> {esc(fila['comuna_receptor'])}</div>
    <div><b>Dirección:</b> {esc(fila['direccion_receptor'])}</div><div><b>Ciudad:</b> {esc(fila['ciudad_receptor'])}</div>
    </div></div>
    <table><thead><tr><th>Código</th><th>Descripción</th><th>Cantidad</th><th>Unidad</th><th>Precio</th><th>Descuento</th><th>Valor</th></tr></thead>
    <tbody>{''.join(filas)}</tbody></table>
    <div class="bottom"><div><div class="sectiontitle">Referencias</div>{referencias}<p><b>Forma de pago:</b> {esc(fila['forma_pago'])}</p></div>
    <div class="totales"><div class="totalrow"><span>Monto neto</span><b>{pesos(fila['neto'])}</b></div>
    <div class="totalrow"><span>Exento</span><b>{pesos(fila['exento'])}</b></div>
    <div class="totalrow"><span>IVA ({numero(fila['tasa_iva'])}%)</span><b>{pesos(fila['iva'])}</b></div>
    <div class="totalrow grand"><span>TOTAL</span><span>{pesos(fila['total'])}</span></div></div></div>
    <div class="nota">Vista documental generada por SGCI a partir de XML importado. No reemplaza la representación oficial del SII; no incluye timbre electrónico ni certifica validez tributaria. No genera asientos contables.</div>
    </div></body></html>'''


def dte_crear_tablas(conn):
    # Solo tablas documentales. No toca ventas, RCV ni libro diario.
    conn.execute("""CREATE TABLE IF NOT EXISTS dte_documentos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        rut_emisor TEXT NOT NULL, tipo_doc INTEGER NOT NULL, folio TEXT NOT NULL,
        fecha TEXT, razon_emisor TEXT, rut_receptor TEXT, razon_receptor TEXT,
        giro_emisor TEXT, giro_receptor TEXT, direccion_receptor TEXT,
        forma_pago TEXT, neto INTEGER DEFAULT 0, exento INTEGER DEFAULT 0,
        iva INTEGER DEFAULT 0, total INTEGER DEFAULT 0,
        xml_original BLOB NOT NULL, archivo TEXT, fecha_importacion TEXT,
        UNIQUE(rut_emisor, tipo_doc, folio))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS dte_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT, documento_id INTEGER NOT NULL,
        linea INTEGER, codigo TEXT, nombre TEXT, descripcion TEXT,
        cantidad REAL, unidad TEXT, precio REAL, descuento REAL,
        monto INTEGER, FOREIGN KEY(documento_id) REFERENCES dte_documentos(id))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS dte_referencias (
        id INTEGER PRIMARY KEY AUTOINCREMENT, documento_id INTEGER NOT NULL,
        linea INTEGER, tipo_ref TEXT, folio_ref TEXT, fecha_ref TEXT,
        codigo_ref TEXT, razon_ref TEXT,
        FOREIGN KEY(documento_id) REFERENCES dte_documentos(id))""")
    columnas_doc={r[1] for r in conn.execute('PRAGMA table_info(dte_documentos)')}
    columnas_item={r[1] for r in conn.execute('PRAGMA table_info(dte_items)')}
    extras_doc={'periodo':'TEXT','tasa_iva':'REAL','descuento_global':'REAL',
        'recargo_global':'REAL','ciudad_receptor':'TEXT','comuna_receptor':'TEXT',
        'direccion_emisor':'TEXT','comuna_emisor':'TEXT','estado_documental':'TEXT'}
    extras_item={'ind_exento':'TEXT','descuento_pct':'REAL','recargo':'REAL',
        'recargo_pct':'REAL','tipo_codigo':'TEXT'}
    for campo,tipo in extras_doc.items():
        if campo not in columnas_doc:
            conn.execute(f'ALTER TABLE dte_documentos ADD COLUMN {campo} {tipo}')
    for campo,tipo in extras_item.items():
        if campo not in columnas_item:
            conn.execute(f'ALTER TABLE dte_items ADD COLUMN {campo} {tipo}')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_dte_fecha ON dte_documentos(fecha)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_dte_receptor ON dte_documentos(rut_receptor)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_dte_periodo ON dte_documentos(periodo)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_dte_item_doc ON dte_items(documento_id)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_dte_ref_doc ON dte_referencias(documento_id)')
    conn.commit()


def dte_texto(nodo, ruta, defecto=''):
    if nodo is None:
        return defecto
    encontrado=nodo.find(ruta)
    return (encontrado.text or '').strip() if encontrado is not None else defecto


def dte_numero(valor):
    try:
        return float(valor or 0)
    except (ValueError,TypeError):
        return 0.0


def dte_parsear(datos):
    # Acepta SetDTE del portal gratuito, EnvioDTE y DTE individuales,
    # tanto con namespace SII como sin namespace.
    if len(datos)>15*1024*1024:
        raise ValueError('XML excede 15 MB.')
    if b'<!DOCTYPE' in datos.upper() or b'<!ENTITY' in datos.upper():
        raise ValueError('XML con DTD o entidades no permitido.')
    raiz=ET.fromstring(datos)
    def local(tag): return tag.split('}',1)[-1]
    def hijos(n,etiqueta): return [x for x in n if local(x.tag)==etiqueta]
    def hijo(n,etiqueta):
        return next(iter(hijos(n,etiqueta)),None) if n is not None else None
    def valor(n,ruta,defecto=''):
        for parte in ruta.split('/'):
            n=hijo(n,parte)
            if n is None: return defecto
        return (n.text or '').strip()
    documentos=[]
    if local(raiz.tag)=='Documento': documentos=[raiz]
    elif local(raiz.tag)=='DTE': documentos=hijos(raiz,'Documento')
    else:
        for elemento in raiz.iter():
            if local(elemento.tag)=='DTE': documentos.extend(hijos(elemento,'Documento'))
    if not documentos: raise ValueError('No se encontraron documentos DTE en el XML.')
    resultado=[]
    for doc in documentos:
        enc=hijo(doc,'Encabezado')
        if enc is None: raise ValueError('Documento sin encabezado.')
        get=lambda ruta: valor(enc,ruta)
        rut=normalizar_rut(get('Emisor/RUTEmisor'))
        receptor=normalizar_rut(get('Receptor/RUTRecep'))
        tipo=int(get('IdDoc/TipoDTE') or 0)
        folio=get('IdDoc/Folio')
        if not rut or not folio or not tipo or not validar_rut(rut):
            raise ValueError('DTE con emisor, tipo o folio inválido.')
        fecha=get('IdDoc/FchEmis')
        items=[]
        for lin in hijos(doc,'Detalle'):
            codigo=hijo(lin,'CdgItem')
            items.append(dict(linea=int(valor(lin,'NroLinDet') or len(items)+1),
                codigo=valor(codigo,'VlrCodigo'),tipo_codigo=valor(codigo,'TpoCodigo'),
                nombre=valor(lin,'NmbItem'),descripcion=valor(lin,'DscItem'),
                cantidad=dte_numero(valor(lin,'QtyItem')),unidad=valor(lin,'UnmdItem'),
                precio=dte_numero(valor(lin,'PrcItem')),
                descuento=dte_numero(valor(lin,'DescuentoMonto')),
                descuento_pct=dte_numero(valor(lin,'DescuentoPct')),
                recargo=dte_numero(valor(lin,'RecargoMonto')),
                recargo_pct=dte_numero(valor(lin,'RecargoPct')),
                ind_exento=valor(lin,'IndExe'),monto=round(dte_numero(valor(lin,'MontoItem')))))
        refs=[]
        for ref in hijos(doc,'Referencia'):
            refs.append(dict(linea=int(valor(ref,'NroLinRef') or len(refs)+1),
                tipo_ref=valor(ref,'TpoDocRef'),folio_ref=valor(ref,'FolioRef'),
                fecha_ref=valor(ref,'FchRef'),codigo_ref=valor(ref,'CodRef'),
                razon_ref=valor(ref,'RazonRef')))
        descuentos=recargos=0.0
        for dr in hijos(doc,'DscRcgGlobal'):
            monto=dte_numero(valor(dr,'ValorDR'))
            if valor(dr,'TpoValor')=='%':
                # Se conserva la magnitud informada; no se interpreta como monto en pesos.
                continue
            if valor(dr,'TpoMov')=='D': descuentos+=monto
            elif valor(dr,'TpoMov')=='R': recargos+=monto
        cab=dict(rut_emisor=rut,tipo_doc=tipo,folio=folio,fecha=fecha,
            periodo=fecha[:7],razon_emisor=get('Emisor/RznSoc'),rut_receptor=receptor,
            razon_receptor=get('Receptor/RznSocRecep'),giro_emisor=get('Emisor/GiroEmis'),
            giro_receptor=get('Receptor/GiroRecep'),direccion_receptor=get('Receptor/DirRecep'),
            comuna_receptor=get('Receptor/CmnaRecep'),ciudad_receptor=get('Receptor/CiudadRecep'),
            direccion_emisor=get('Emisor/DirOrigen'),comuna_emisor=get('Emisor/CmnaOrigen'),
            forma_pago={'1':'Contado','2':'Crédito','3':'Sin costo'}.get(get('IdDoc/FmaPago'),'No informado'),
            neto=round(dte_numero(get('Totales/MntNeto'))),
            exento=round(dte_numero(get('Totales/MntExe'))),
            iva=round(dte_numero(get('Totales/IVA'))),
            tasa_iva=dte_numero(get('Totales/TasaIVA')),
            total=round(dte_numero(get('Totales/MntTotal'))),
            descuento_global=descuentos,recargo_global=recargos,
            estado_documental='SOLO DOCUMENTAL')
        resultado.append((cab,items,refs))
    return resultado


def dte_guardar(conn,datos,archivo,rut_permitido=None):
    registros=dte_parsear(datos)
    nuevos=duplicados=0
    for cab,items,refs in registros:
        if rut_permitido and cab['rut_emisor']!=normalizar_rut(rut_permitido):
            raise ValueError('El XML contiene un emisor diferente de la empresa seleccionada.')
        existe=conn.execute('SELECT id FROM dte_documentos WHERE rut_emisor=? AND tipo_doc=? AND folio=?',
            (cab['rut_emisor'],cab['tipo_doc'],cab['folio'])).fetchone()
        if existe:
            duplicados+=1;continue
        campos=list(cab)+['xml_original','archivo','fecha_importacion']
        valores=list(cab.values())+[datos,archivo,datetime.now().isoformat(timespec='seconds')]
        cur=conn.execute('INSERT INTO dte_documentos ('+','.join(campos)+') VALUES ('+','.join(['?']*len(campos))+')',valores)
        for item in items:
            campos_item=['documento_id']+list(item)
            conn.execute('INSERT INTO dte_items ('+','.join(campos_item)+') VALUES ('+','.join(['?']*len(campos_item))+')',
                [cur.lastrowid]+list(item.values()))
        for ref in refs:
            campos_ref=['documento_id']+list(ref)
            conn.execute('INSERT INTO dte_referencias ('+','.join(campos_ref)+') VALUES ('+','.join(['?']*len(campos_ref))+')',
                [cur.lastrowid]+list(ref.values()))
        nuevos+=1
    return nuevos,duplicados


def dte_archivos_extraer(archivos):
    salida=[]
    for archivo in archivos:
        datos=archivo.getvalue()
        if archivo.name.lower().endswith('.zip'):
            with zipfile.ZipFile(io.BytesIO(datos)) as z:
                miembros=[m for m in z.infolist() if m.filename.lower().endswith('.xml') and not m.is_dir()]
                if len(miembros)>1000: raise ValueError('ZIP supera 1000 XML.')
                for m in miembros:
                    if m.file_size>15*1024*1024: raise ValueError('XML supera 15 MB.')
                    with z.open(m) as f: salida.append((m.filename,f.read(15*1024*1024+1)))
        else: salida.append((archivo.name,datos))
    return salida


def dte_excel(df):
    salida=io.BytesIO()
    with pd.ExcelWriter(salida,engine='openpyxl') as writer:
        df.to_excel(writer,index=False,sheet_name='Reporte DTE')
    return salida.getvalue()


def dte_reporte_pdf(titulo, df, filtros=''):
    # PDF horizontal con celdas multilínea; no modifica datos contables.
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, KeepTogether
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from xml.sax.saxutils import escape
    buffer=io.BytesIO()
    doc=SimpleDocTemplate(buffer,pagesize=A4,rightMargin=12*mm,leftMargin=12*mm,topMargin=37*mm,bottomMargin=12*mm)
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name='DTECell',fontName='Helvetica',fontSize=6,leading=7.5,alignment=TA_LEFT,wordWrap='CJK'))
    styles.add(ParagraphStyle(name='DTEHeader',parent=styles['DTECell'],fontName='Helvetica-Bold',textColor=colors.white))
    story=[Paragraph(escape('SGCI | '+titulo),styles['Heading2']),Paragraph(escape(filtros),styles['Normal']),Spacer(1,6*mm)]
    if df.empty:
        story.append(Paragraph('No hay registros para los filtros seleccionados.',styles['Normal']))
    else:
        tabla=[ [Paragraph(escape(str(c)),styles['DTEHeader']) for c in df.columns] ]
        for fila in df.fillna('').itertuples(index=False,name=None):
            tabla.append([Paragraph(escape(str(v)).replace('\n','<br/>'),styles['DTECell']) for v in fila])
        anchos=[max(15,len(str(c))) for c in df.columns]
        if 'descripcion' in df.columns:
            anchos[df.columns.get_loc('descripcion')]=48
        total=sum(anchos)
        disponible=A4[0]-24*mm
        anchos=[disponible*a/total for a in anchos]
        t=Table(tabla,colWidths=anchos,repeatRows=1,hAlign='LEFT')
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#176B55')),
            ('VALIGN',(0,0),(-1,-1),'TOP'),('GRID',(0,0),(-1,-1),.25,colors.HexColor('#DCE8E3')),
            ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#F2F7F4')]),
            ('LEFTPADDING',(0,0),(-1,-1),2),('RIGHTPADDING',(0,0),(-1,-1),2),
            ('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
        story.append(t)
    story.extend([Spacer(1,6*mm),Paragraph('Reporte documental; no representa contabilización ni conciliación con RCV.',styles['Normal'])])
    doc.build(story,onFirstPage=sgci_membrete_pdf,onLaterPages=sgci_membrete_pdf)
    return buffer.getvalue()


def pantalla_dte(conn):
    st.title('🧾 Facturación y DTE')
    st.caption('Repositorio documental independiente. La importación NO crea ventas, cuentas por cobrar ni asientos contables.')
    tab1,tab2,tab3 = st.tabs(['📥 Importar XML','🔎 Documentos y visor','📊 Reportería'])
    with tab1:
        st.info('Importa XML del SII (SetDTE mensual, DTE individuales o ZIP). Solo se agregan registros documentales: RCV sigue siendo la fuente contable.')
        archivos=st.file_uploader('XML o ZIP',type=['xml','zip'],accept_multiple_files=True,key='dte_carga')
        if archivos:
            try:
                paquetes=dte_archivos_extraer(archivos)
                resumen=[]; errores=[]; vistos=set()
                for nombre,datos in paquetes:
                    try:
                        for cab,items,refs in dte_parsear(datos):
                            clave=(cab['rut_emisor'],cab['tipo_doc'],cab['folio'])
                            existe=conn.execute('SELECT 1 FROM dte_documentos WHERE rut_emisor=? AND tipo_doc=? AND folio=?',clave).fetchone()
                            estado='Duplicado' if existe or clave in vistos else 'Nuevo'
                            vistos.add(clave)
                            resumen.append(dict(Archivo=nombre,Estado=estado,Emisor=cab['rut_emisor'],
                                Fecha=cab['fecha'],Tipo=cab['tipo_doc'],Folio=cab['folio'],
                                Cliente=cab['razon_receptor'],Total=cab['total'],Items=len(items),Referencias=len(refs)))
                    except Exception as e: errores.append(f'{nombre}: {e}')
                if resumen:
                    previa=pd.DataFrame(resumen)
                    st.subheader('Vista previa antes de importar')
                    st.dataframe(previa,use_container_width=True,hide_index=True)
                    st.caption(f"Nuevos: {(previa['Estado']=='Nuevo').sum()} · Duplicados: {(previa['Estado']=='Duplicado').sum()}")
                    emisores=sorted(previa['Emisor'].unique())
                    if len(emisores)>1:
                        st.error('El lote contiene varios RUT emisores. Sepáralos antes de importar.')
                    else:
                        st.caption('Verifica que el RUT emisor corresponda a la empresa piloto seleccionada.')
                    confirmado=st.checkbox('Confirmo que el RUT emisor corresponde a la empresa seleccionada y autorizo únicamente la carga documental.',key='dte_confirma')
                    if st.button('Guardar documentos (sin contabilizar)',type='primary',disabled=not confirmado or len(emisores)!=1,key='dte_importar'):
                        nuevos=duplicados=0; fallas=[]
                        for nombre,datos in paquetes:
                            try:
                                with conn:
                                    a,b=dte_guardar(conn,datos,nombre,rut_permitido=emisores[0])
                                nuevos+=a;duplicados+=b
                            except Exception as e: fallas.append(f'{nombre}: {e}')
                        st.success(f'Documentos guardados: {nuevos} · Duplicados omitidos: {duplicados}. No se generaron asientos.')
                        if fallas: st.warning('Observaciones: '+'; '.join(fallas[:10]))
                if errores: st.warning('XML no procesados: '+'; '.join(errores[:10]))
            except Exception as e: st.error(f'No se pudo preparar el lote: {e}')
    with tab2:
        df=pd.read_sql_query('''SELECT id,fecha,tipo_doc,folio,razon_receptor,rut_receptor,neto,iva,total
            FROM dte_documentos ORDER BY fecha DESC,id DESC''',conn)
        if df.empty:
            st.info('Aún no hay documentos importados.')
        else:
            busqueda=st.text_input('Buscar cliente, RUT o folio',key='dte_busqueda')
            if busqueda:
                df=df[df[['razon_receptor','rut_receptor','folio']].fillna('').astype(str).apply(
                    lambda x:x.str.contains(busqueda,case=False,regex=False)).any(axis=1)]
            st.caption('Pulsa 🔍 en la factura que quieras consultar. Ningún documento se abre automáticamente.')
            if df.empty:
                st.info('No hay documentos que coincidan con la búsqueda.')
            else:
                tamano=15
                paginas=max(1,(len(df)+tamano-1)//tamano)
                pagina=st.number_input('Página',min_value=1,max_value=paginas,value=1,step=1,key='dte_pagina')
                visible=df.iloc[(pagina-1)*tamano:pagina*tamano]
                cab=st.columns([1.1,.7,.8,2.6,1.25,1.15,.45])
                for c,t in zip(cab,['Fecha','Tipo','Folio','Cliente','RUT','Total','Ver']): c.markdown('**'+t+'**')
                for r in visible.itertuples(index=False):
                    c=st.columns([1.1,.7,.8,2.6,1.25,1.15,.45],vertical_alignment='center')
                    for col,val in zip(c[:6],[r.fecha,r.tipo_doc,r.folio,r.razon_receptor,r.rut_receptor,money(r.total)]):
                        col.write(str(val or ''))
                    if c[6].button('🔍',key=f'dte_lupa_{r.id}',help='Ver factura '+str(r.folio)):
                        st.session_state['dte_documento_abierto']=int(r.id)
                abierto=st.session_state.get('dte_documento_abierto')
                if abierto is not None:
                    fila=conn.execute('SELECT * FROM dte_documentos WHERE id=?',(abierto,)).fetchone()
                    if fila:
                        st.divider()
                        c_t,c_x=st.columns([5,1])
                        c_t.subheader(f"{nombre_documento(fila['tipo_doc'])} N.º {fila['folio']}")
                        if c_x.button('✖ Cerrar vista',key='dte_cerrar'):
                            st.session_state['dte_documento_abierto']=None
                            st.rerun()
                        items=pd.read_sql_query("""SELECT linea,codigo,nombre,descripcion,cantidad,unidad,precio,descuento,monto
                            FROM dte_items WHERE documento_id=? ORDER BY linea""",conn,params=(fila['id'],))
                        refs=pd.read_sql_query('SELECT linea,tipo_ref,folio_ref,fecha_ref,codigo_ref,razon_ref FROM dte_referencias WHERE documento_id=? ORDER BY linea',conn,params=(fila['id'],))
                        vista_html=dte_html_factura(fila,items,refs)
                        import streamlit.components.v1 as components
                        st.caption('Representación documental similar al formato de factura del SII. No es copia oficial ni afecta contabilidad.')
                        components.html(vista_html,height=780,scrolling=True)
                        b1,b2=st.columns(2)
                        with b1:
                            st.download_button('🖨️ Descargar vista para imprimir (HTML)',vista_html.encode('utf-8'),
                                file_name=f"Vista_DTE_{fila['tipo_doc']}_{fila['folio']}.html",mime='text/html',key=f"dte_print_{fila['id']}")
                        with b2:
                            st.download_button('⬇️ XML original',bytes(fila['xml_original']),
                                file_name=f"DTE_{fila['tipo_doc']}_{fila['folio']}.xml",mime='application/xml',key=f"dte_xml_{fila['id']}")
                        with st.expander('Ver datos estructurados para reportes'):
                            st.markdown('**Detalle de ítems**')
                            st.dataframe(items,use_container_width=True,hide_index=True)
                            if not refs.empty:
                                st.markdown('**Referencias**')
                                st.dataframe(refs,use_container_width=True,hide_index=True)
    with tab3:
        df=pd.read_sql_query('''SELECT fecha,tipo_doc,folio,rut_receptor,razon_receptor,neto,exento,iva,total
            FROM dte_documentos ORDER BY fecha DESC''',conn)
        if df.empty:
            st.info('Importa documentos para visualizar reportes.')
        else:
            df['periodo']=df['fecha'].fillna('').str[:7]
            periodos=sorted(df['periodo'].unique(),reverse=True)
            elegidos=st.multiselect('Períodos',periodos,default=periodos,key='dte_periodos')
            filtrado=df[df['periodo'].isin(elegidos)].copy()
            st.caption('Los importes de notas de crédito se presentan sin signo ajustado; no equivalen a ventas netas tributarias.')
            reporte=st.selectbox('Selecciona el reporte',[
                'Por período','Por fecha','Por cliente','Por tipo de documento','Documentos individuales','Ítems facturados','Buscar descripciones','Cantidades por ítem','Referencias y notas de crédito','Resumen neto ajustado por NC'],key='dte_tipo_reporte')
            if reporte=='Por período':
                tabla=filtrado.groupby('periodo',as_index=False)[['neto','exento','iva','total']].sum()
            elif reporte=='Por fecha':
                tabla=filtrado.groupby('fecha',as_index=False)[['neto','exento','iva','total']].sum()
            elif reporte=='Por cliente':
                clientes=sorted(filtrado['razon_receptor'].dropna().unique())
                seleccion=st.multiselect('Filtrar clientes',clientes,default=clientes,key='dte_reporte_clientes')
                filtrado=filtrado[filtrado['razon_receptor'].isin(seleccion)]
                tabla=filtrado.groupby(['rut_receptor','razon_receptor'],as_index=False)[['neto','exento','iva','total']].sum()
            elif reporte=='Por tipo de documento':
                tabla=filtrado.groupby('tipo_doc',as_index=False)[['neto','exento','iva','total']].sum()
                tabla.insert(1,'documento',tabla['tipo_doc'].apply(nombre_documento))
            elif reporte=='Documentos individuales':
                tabla=filtrado[['fecha','tipo_doc','folio','razon_receptor','neto','exento','iva','total']].copy()
            elif reporte in ('Ítems facturados','Buscar descripciones','Cantidades por ítem'):
                tabla=pd.read_sql_query('''SELECT d.fecha,d.tipo_doc,d.folio,d.razon_receptor,
                    i.nombre,i.descripcion,i.cantidad,i.precio,i.monto
                    FROM dte_items i JOIN dte_documentos d ON d.id=i.documento_id
                    ORDER BY d.fecha DESC''',conn)
                tabla=tabla[tabla['fecha'].fillna('').str[:7].isin(elegidos)].copy()
                if reporte=='Buscar descripciones':
                    palabra=st.text_input('Buscar texto en nombre o descripción',key='dte_palabra')
                    if palabra:
                        mascara=tabla[['nombre','descripcion']].fillna('').astype(str).apply(lambda col:col.str.contains(palabra,case=False,regex=False)).any(axis=1)
                        tabla=tabla[mascara]
                elif reporte=='Cantidades por ítem':
                    tabla=tabla.groupby('nombre',dropna=False,as_index=False).agg(cantidad=('cantidad','sum'),monto=('monto','sum'),lineas=('folio','size'))
                st.caption('Reporte documental. Los montos de ítems no equivalen necesariamente a ventas netas tributarias.')
            elif reporte=='Referencias y notas de crédito':
                tabla=pd.read_sql_query('''SELECT d.fecha,d.tipo_doc,d.folio,d.razon_receptor,r.tipo_ref,r.folio_ref,r.fecha_ref,r.codigo_ref,r.razon_ref
                    FROM dte_referencias r JOIN dte_documentos d ON d.id=r.documento_id ORDER BY d.fecha DESC''',conn)
                tabla=tabla[tabla['fecha'].fillna('').str[:7].isin(elegidos)].copy()
            else:
                tabla=filtrado.copy()
                tabla['signo']=tabla['tipo_doc'].apply(lambda x:-1 if x==61 else 1)
                for campo in ['neto','exento','iva','total']:
                    tabla[campo]=tabla[campo]*tabla['signo']
                tabla=tabla.groupby('periodo',as_index=False)[['neto','exento','iva','total']].sum()
                st.caption('Resumen documental estimado: resta notas de crédito tipo 61; no sustituye al RCV ni constituye conciliación tributaria.')
            st.subheader(reporte)
            st.metric('Documentos incluidos en el filtro',len(filtrado))
            st.dataframe(formatear_montos_df(tabla),use_container_width=True,hide_index=True,
                column_config={'descripcion':st.column_config.TextColumn('Descripción',width='large')} if 'descripcion' in tabla else None)
            col1,col2,col3=st.columns(3)
            with col1:
                st.download_button('⬇️ Exportar CSV',tabla.to_csv(index=False).encode('utf-8-sig'),
                    file_name='SGCI_'+reporte.lower().replace(' ','_')+'.csv',mime='text/csv',key='dte_csv_reporte')
            with col3:
                try:
                    st.download_button('⬇️ Exportar Excel',dte_excel(tabla),file_name='SGCI_'+reporte.lower().replace(' ','_')+'.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',key='dte_excel_reporte')
                except ImportError:
                    st.warning('Para Excel, instalar openpyxl.')
            with col2:
                try:
                    pdf=dte_reporte_pdf('Facturación DTE - '+reporte,formatear_montos_df(tabla),
                        'Períodos: '+(', '.join(elegidos) if elegidos else 'Ninguno'))
                    st.download_button('🖨️ Generar PDF para imprimir',pdf,
                        file_name='SGCI_'+reporte.lower().replace(' ','_')+'.pdf',mime='application/pdf',key='dte_pdf_reporte')
                except ImportError:
                    st.warning('Para generar PDF, agrega reportlab a requirements.txt y vuelve a desplegar la aplicación.')



# TESORERÍA - reportes imprimibles con ReportLab

def tes_reporte_imprimible(titulo, datos):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import landscape, A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, LongTable, TableStyle
    from reportlab.lib.enums import TA_CENTER
    import io as _io
    buffer=_io.BytesIO()
    doc=SimpleDocTemplate(buffer,pagesize=A4,leftMargin=25,rightMargin=25,topMargin=105,bottomMargin=30)
    styles=getSampleStyleSheet()
    styles['Title'].textColor=colors.HexColor('#46543A')
    story=[Paragraph('SGCI | '+str(titulo),styles['Title']),Spacer(1,12)]
    if datos is not None and not datos.empty:
        d=datos.copy().fillna('')
        # Ancho adaptable y texto ajustado para no cortar las columnas.
        ancho=A4[0]-50
        n=len(d.columns)
        celda=ancho/max(n,1)
        estilo=styles['BodyText'].clone('tescelda')
        estilo.fontSize=6
        estilo.leading=7.5
        estilo.wordWrap="CJK"
        filas=[[Paragraph(str(x),estilo) for x in d.columns]]
        for row in d.astype(str).itertuples(index=False,name=None):
            filas.append([Paragraph(__import__('html').escape(str(x)),estilo) for x in row])
        t=LongTable(filas,colWidths=[celda]*n,repeatRows=1,hAlign='LEFT')
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#B7C2A7')),
            ('GRID',(0,0),(-1,-1),.25,colors.HexColor('#DDE4D7')),
            ('VALIGN',(0,0),(-1,-1),'TOP'),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#F3F4EE')]),
            ('BOTTOMPADDING',(0,0),(-1,-1),6),('TOPPADDING',(0,0),(-1,-1),6)]))
        story.append(t)
    else:
        story.append(Paragraph('Sin registros para mostrar.',styles['Normal']))
    doc.build(story,onFirstPage=sgci_membrete_pdf,onLaterPages=sgci_membrete_pdf)
    return buffer.getvalue()


def tes_boton_imprimir(titulo,df,key):
    try:
        st.download_button('🖨️ Imprimir / PDF · '+titulo,
            data=tes_reporte_imprimible(titulo,df),file_name='SGCI_'+key+'.pdf',
            mime='application/pdf',key='tes_print_'+key)
    except ImportError:
        st.caption('Para imprimir en PDF, instalar reportlab en requirements.txt.')


def tes_vista_comprobante(pago,sid):
    nombre=str(pago['nombre_comprobante'] or '')
    datos=bytes(pago['comprobante'])
    if st.button('👁️ Visualizar comprobante',key=f'tes_view_{sid}'):
        st.session_state[f'tes_show_{sid}']=not st.session_state.get(f'tes_show_{sid}',False)
    if st.session_state.get(f'tes_show_{sid}',False):
        tipo=nombre.lower().rsplit('.',1)[-1]
        if tipo=='pdf':
            import base64
            b64=base64.b64encode(datos).decode('ascii')
            st.markdown(f'<iframe src="data:application/pdf;base64,{b64}" width="100%" height="580" title="Comprobante"></iframe>',unsafe_allow_html=True)
        elif tipo in ('jpg','jpeg','png'):
            st.image(datos,caption=nombre,use_container_width=True)
        else:
            st.warning('Formato no compatible con vista previa.')
        st.download_button('⬇️ Descargar desde el visor',datos,file_name=nombre,key=f'tes_view_download_{sid}')


def tes_conciliar_pago(conn,movimiento_id,solicitud_id):
    sgci_autorizar_operacion(conn, 'banco', 'conciliar')
    """Solo vincula cartola con asiento ya existente. No crea un asiento nuevo."""
    try:
        conn.execute('BEGIN IMMEDIATE')
        mov=conn.execute('SELECT * FROM cartola_bancaria WHERE id=?',(movimiento_id,)).fetchone()
        pago=conn.execute('SELECT * FROM tes_confirmaciones_pago WHERE solicitud_id=?',(solicitud_id,)).fetchone()
        sol=conn.execute('SELECT * FROM tes_solicitudes WHERE id=?',(solicitud_id,)).fetchone()
        if not mov or int(mov['conciliado'] or 0)!=0:
            raise ValueError('El movimiento ya fue conciliado o no existe.')
        if not pago or not sol or sol['estado']!='CONTABILIZADA' or pago['asiento_id'] is None:
            raise ValueError('Solo se pueden conciliar pagos de Tesorería ya contabilizados.')
        if int(pago['banco_id'] or 0)!=int(mov['banco_id'] or -1):
            raise ValueError('El banco de la transferencia no coincide con la cartola.')
        monto=conn.execute('SELECT COALESCE(SUM(monto),0) FROM tes_solicitud_detalle WHERE solicitud_id=?',(solicitud_id,)).fetchone()[0]
        if int(round(float(mov['cargo'] or 0)))!=int(round(float(monto))) or float(mov['abono'] or 0)>0:
            raise ValueError('El monto y la naturaleza del cargo no coinciden.')
        ya=conn.execute("SELECT 1 FROM cartola_bancaria WHERE match_tipo='TESORERIA' AND match_id=? AND conciliado=1",(solicitud_id,)).fetchone()
        if ya:
            raise ValueError('Esta solicitud ya está conciliada con otra cartola.')
        cur=conn.execute("""UPDATE cartola_bancaria SET conciliado=1,match_tipo='TESORERIA',match_id=?,asiento_id=?,match_confianza=100,
            observacion=? WHERE id=? AND conciliado=0""",(solicitud_id,int(pago['asiento_id']),f'Tesorería SF-{solicitud_id:06d}',movimiento_id))
        if cur.rowcount!=1: raise ValueError('La cartola ya no está disponible.')
        conn.commit()
        return int(pago['asiento_id'])
    except Exception:
        conn.rollback()
        raise

# ============================================================
# TESORERÍA - ETAPA 1: SOLICITUDES (SIN ASIENTOS CONTABLES)
# ============================================================

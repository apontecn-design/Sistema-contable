"""Balance de ocho columnas, calculado sin modificar el libro diario.

Clasificación según la naturaleza registrada del plan y el signo del saldo.
Referencia: SII, instrucciones DJ 1847, columnas del balance (no genera una DJ).
Las sumas corresponden al intervalo solicitado, incluidos sus asientos de apertura.
"""
from datetime import date
from decimal import Decimal
from io import BytesIO

import pandas as pd

COLUMNAS_BALANCE = ('Debe', 'Haber', 'Deudor', 'Acreedor',
                    'Activo', 'Pasivo', 'Pérdidas', 'Ganancias')


def generar_balance_ocho_columnas(conn, desde=None, hasta=None):
    if desde:
        desde = date.fromisoformat(str(desde)).isoformat()
    if hasta:
        hasta = date.fromisoformat(str(hasta)).isoformat()
    if desde and hasta and desde > hasta:
        raise ValueError('La fecha inicial no puede superar la fecha final.')
    condiciones, params = [], []
    for fecha, operador in ((desde, '>='), (hasta, '<=')):
        if fecha:
            condiciones.append('d.fecha ' + operador + ' ?')
            params.append(fecha)
    where = ' WHERE ' + ' AND '.join(condiciones) if condiciones else ''
    sql = '''SELECT d.codigo_cuenta,p.nombre,p.tipo,d.debe,d.haber
             FROM libro_diario d LEFT JOIN plan_cuentas p ON p.codigo=d.codigo_cuenta'''
    cuentas = {}
    for codigo, nombre, tipo, debe, haber in conn.execute(sql + where, params):
        if nombre is None:
            raise ValueError('Existe un movimiento sin cuenta válida en el plan: ' + str(codigo))
        tipo = str(tipo or '').strip().casefold()
        if tipo not in ('activo', 'pasivo', 'patrimonio', 'ingresos', 'gastos',
                        'costos', 'perdidas', 'pérdidas', 'ganancias'):
            raise ValueError('Clasificación contable no reconocida en la cuenta ' + str(codigo))
        item = cuentas.setdefault(str(codigo), [nombre, tipo, Decimal(0), Decimal(0)])
        for indice, valor in ((2, debe), (3, haber)):
            numero = Decimal(str(valor or 0))
            if not numero.is_finite():
                raise ValueError('Hay importes no finitos en el libro diario.')
            item[indice] += numero
    filas = []
    for codigo, (nombre, tipo, debe, haber) in sorted(cuentas.items()):
        if debe == 0 and haber == 0:
            continue
        deudor, acreedor = max(debe - haber, 0), max(haber - debe, 0)
        inventario = tipo in ('activo', 'pasivo', 'patrimonio')
        importes = (debe, haber, deudor, acreedor,
                    deudor if inventario else 0, acreedor if inventario else 0,
                    0 if inventario else deudor, 0 if inventario else acreedor)
        filas.append({'Codigo': codigo, 'Cuenta': nombre,
                      **dict(zip(COLUMNAS_BALANCE, importes))})
    sumas = {c: sum((Decimal(str(f[c])) for f in filas), Decimal(0)) for c in COLUMNAS_BALANCE}
    resultado = sumas['Ganancias'] - sumas['Pérdidas']
    ajuste = {c: Decimal(0) for c in COLUMNAS_BALANCE}
    if resultado >= 0:
        ajuste['Pasivo'] = ajuste['Pérdidas'] = resultado
    else:
        ajuste['Activo'] = ajuste['Ganancias'] = -resultado
    totales = {c: sumas[c] + ajuste[c] for c in COLUMNAS_BALANCE}
    resumen = [{'Codigo': '', 'Cuenta': etiqueta, **montos} for etiqueta, montos in (
        ('Sumas', sumas), ('Utilidad del ejercicio' if resultado >= 0 else 'Pérdida del ejercicio', ajuste),
        ('Totales', totales))]
    cuadraturas = {nombre: totales[a] - totales[b] for nombre, a, b in (
        ('sumas', 'Debe', 'Haber'), ('saldos', 'Deudor', 'Acreedor'),
        ('inventario', 'Activo', 'Pasivo'), ('resultados', 'Pérdidas', 'Ganancias'))}
    columnas = ['Codigo', 'Cuenta', *COLUMNAS_BALANCE]
    return {'detalle': pd.DataFrame(filas, columns=columnas),
            'resumen': pd.DataFrame(resumen, columns=columnas),
            'resultado': resultado, 'cuadraturas': cuadraturas,
            'cuadrado': all(abs(v) < Decimal('0.01') for v in cuadraturas.values())}


def balance_ocho_excel(informe, desde=None, hasta=None):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    libro = Workbook()
    hoja = libro.active
    hoja.title = 'Balance 8 columnas'
    hoja.append(['CONTEM · Balance de ocho columnas'])
    hoja.merge_cells('A1:J1')
    hoja.append(['Desde ' + str(desde or 'inicio') + ' hasta ' + str(hasta or 'último movimiento')])
    hoja.merge_cells('A2:J2')
    hoja.append(['Código', 'Cuenta', 'Sumas', '', 'Saldos', '', 'Inventario', '', 'Resultados', ''])
    hoja.append(['', '', *COLUMNAS_BALANCE])
    for rango in ('A3:A4', 'B3:B4', 'C3:D3', 'E3:F3', 'G3:H3', 'I3:J3'):
        hoja.merge_cells(rango)
    for tabla in (informe['detalle'], informe['resumen']):
        for fila in tabla.itertuples(index=False, name=None):
            hoja.append([str(fila[0]), str(fila[1]), *[float(v) for v in fila[2:]]])
            for celda in hoja[hoja.max_row][:2]:
                celda.data_type = 's'  # Los nombres de cuentas nunca se ejecutan como fórmulas.
    for fila in hoja.iter_rows(min_row=3):
        for celda in fila:
            celda.alignment = Alignment(vertical='center', wrap_text=True)
            if celda.column >= 3 and celda.row > 4:
                celda.number_format = '#,##0.00;[Red](#,##0.00)'
            if celda.row <= 4:
                celda.fill = PatternFill('solid', fgColor='176B55')
                celda.font = Font(color='FFFFFF', bold=True)
    for i in range(1, 11):
        hoja.column_dimensions[get_column_letter(i)].width = 42 if i == 2 else 18
    hoja.freeze_panes = 'C5'
    hoja.print_title_rows = '1:4'
    hoja.sheet_properties.pageSetUpPr.fitToPage = True
    hoja.page_setup.orientation = 'landscape'
    hoja.page_setup.paperSize = hoja.PAPERSIZE_A4
    hoja.page_setup.fitToWidth = 1
    hoja.page_setup.fitToHeight = 0
    salida = BytesIO()
    libro.save(salida)
    return salida.getvalue()


def balance_ocho_pdf(informe, desde=None, hasta=None, membrete=None):
    from html import escape
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, LongTable, TableStyle, Spacer
    salida = BytesIO()
    doc = SimpleDocTemplate(salida, pagesize=landscape(A4), leftMargin=24, rightMargin=24,
                            topMargin=92 if membrete else 24, bottomMargin=30)
    estilos = getSampleStyleSheet()
    celda = ParagraphStyle('BC8', parent=estilos['Normal'], fontSize=7, leading=9)
    datos = [['Código', 'Cuenta', 'Sumas', '', 'Saldos', '', 'Inventario', '', 'Resultados', ''],
             ['', '', *COLUMNAS_BALANCE]]
    for tabla in (informe['detalle'], informe['resumen']):
        for fila in tabla.itertuples(index=False, name=None):
            datos.append([Paragraph(escape(str(fila[0])), celda), Paragraph(escape(str(fila[1])), celda),
                          *[f'{v:,.2f}' for v in fila[2:]]])
    ancho = landscape(A4)[0] - 48
    tabla = LongTable(datos, colWidths=[56, ancho - 56 - 8*70, *([70]*8)], repeatRows=2)
    estilo = [('GRID', (0,0), (-1,-1), .3, colors.HexColor('#DCE8E3')),
              ('BACKGROUND', (0,0), (-1,1), colors.HexColor('#176B55')),
              ('TEXTCOLOR', (0,0), (-1,1), colors.white), ('FONTNAME', (0,0), (-1,1), 'Helvetica-Bold'),
              ('FONTSIZE', (0,0), (-1,-1), 7), ('ALIGN', (2,2), (-1,-1), 'RIGHT'),
              ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
              ('BACKGROUND', (0,-3), (-1,-1), colors.HexColor('#EAF5F0'))]
    for inicio, fin in ((0,0), (1,1), (2,3), (4,5), (6,7), (8,9)):
        estilo.append(('SPAN', (inicio,0), (fin,1 if inicio < 2 else 0)))
    tabla.setStyle(TableStyle(estilo))
    contenido = [Paragraph('CONTEM · Balance de ocho columnas', estilos['Title']),
                 Paragraph(escape(f'Desde {desde or "inicio"} hasta {hasta or "último movimiento"}'), estilos['Normal']),
                 Spacer(1, 12), tabla]
    opciones = {'onFirstPage': membrete, 'onLaterPages': membrete} if membrete else {}
    doc.build(contenido, **opciones)
    return salida.getvalue()

"""Inventario conservador de funciones con posibles escrituras sin barrera explícita.

Análisis estático: reporta candidatos; no determina explotabilidad.
Uso: python scripts/auditar_permisos.py
"""
import ast
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
TOKENS=('INSERT ','UPDATE ','DELETE ','REPLACE ','CREATE ','ALTER ','DROP ')
EXCLUSIONES={'sgci_crear_seguridad','tes_crear_tablas','dte_crear_tablas'}


def inventario():
    resultado=[]
    for archivo in sorted((ROOT/'modulos').glob('*.py')):
        try:
            codigo=archivo.read_text(encoding='utf-8')
            arbol=ast.parse(codigo,filename=str(archivo))
        except (OSError,SyntaxError) as exc:
            resultado.append({'archivo':archivo.name,'error':str(exc)})
            continue
        for nodo in arbol.body:
            if not isinstance(nodo,(ast.FunctionDef,ast.AsyncFunctionDef)):
                continue
            if nodo.name in EXCLUSIONES:
                continue
            segmento=ast.get_source_segment(codigo,nodo) or ''
            mayus=segmento.upper()
            if not any(t in mayus for t in TOKENS):
                continue
            # Una barrera visual no sustituye la autorización en servicios.
            protegido='sgci_autorizar_operacion(' in segmento
            resultado.append({'archivo':archivo.name,'funcion':nodo.name,
                              'linea':nodo.lineno,'autorizacion_explicita':protegido})
    return resultado


if __name__=='__main__':
    filas=inventario()
    print(json.dumps({'total_candidatas':len(filas),
                      'sin_barrera_explicita':sum(
                          not x.get('autorizacion_explicita',False) for x in filas),
                      'funciones':filas},ensure_ascii=False,indent=2))

"""Compara datos históricos de dos copias SQLite, sin escribir ni mostrar valores.

Uso: python scripts/comparar_historicos.py respaldo.db copia_migrada.db
Permite tablas y columnas nuevas; exige conservar todas las columnas y filas originales.
No certifica reglas contables ni reemplaza un respaldo consistente.
"""
import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3


def comparar(origen, destino):
    def uri(ruta):
        return Path(ruta).resolve().as_uri() + '?mode=ro'
    def identificador(nombre):
        return '"' + nombre.replace('"', '""') + '"'
    with closing(sqlite3.connect(uri(origen), uri=True)) as antes, \
            closing(sqlite3.connect(uri(destino), uri=True)) as despues:
        tablas = [r[0] for r in antes.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        existentes = {r[0] for r in despues.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        cambios = []
        for tabla in tablas:
            if tabla not in existentes:
                cambios.append({'tabla': tabla, 'motivo': 'Tabla original ausente'})
                continue
            nombre = identificador(tabla)
            columnas = [r[1] for r in antes.execute('PRAGMA table_info(' + nombre + ')')]
            actuales = {r[1] for r in despues.execute('PRAGMA table_info(' + nombre + ')')}
            if not set(columnas) <= actuales:
                cambios.append({'tabla': tabla, 'motivo': 'Columnas originales ausentes'})
                continue
            sql = 'SELECT ' + ','.join(identificador(c) for c in columnas) + ' FROM ' + nombre
            # La comparación incluye valores y duplicados; el orden físico no importa.
            filas_antes = sorted(repr(tuple(r)) for r in antes.execute(sql))
            filas_despues = sorted(repr(tuple(r)) for r in despues.execute(sql))
            if filas_antes != filas_despues:
                cambios.append({'tabla': tabla, 'motivo': 'Contenido original modificado',
                                'filas_antes': len(filas_antes), 'filas_despues': len(filas_despues)})
        return {'aprobado': not cambios, 'tablas_verificadas': len(tablas), 'cambios': cambios}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('origen')
    parser.add_argument('destino')
    args = parser.parse_args()
    resultado = comparar(args.origen, args.destino)
    print(json.dumps(resultado, ensure_ascii=False, indent=2))
    raise SystemExit(0 if resultado['aprobado'] else 1)

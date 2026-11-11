"""Auditoría de solo lectura de CONTEM; no modifica ni migra la base.

Uso: python scripts/auditar_sqlite.py /ruta/copia.db
Salida JSON. Los hallazgos deben revisarse antes de producción.
"""
import json
import sqlite3
import sys
from pathlib import Path


def auditar(ruta):
    uri=Path(ruta).resolve().as_uri()+'?mode=ro'
    conn=sqlite3.connect(uri,uri=True)
    try:
        integridad=conn.execute('PRAGMA integrity_check').fetchone()[0]
        fk=conn.execute('PRAGMA foreign_key_check').fetchall()
        tablas={r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        consultas={
            'pagos_clientes_sobreaplicados': (
                ('pagos_clientes','aplicaciones_clientes'),
                """SELECT count(*) FROM (SELECT p.id FROM pagos_clientes p
                   JOIN aplicaciones_clientes a ON a.pago_id=p.id
                   GROUP BY p.id HAVING sum(abs(a.monto))>abs(p.monto)+0.01)"""),
            'pagos_proveedores_sobreaplicados': (
                ('pagos_proveedores','aplicaciones_proveedores'),
                """SELECT count(*) FROM (SELECT p.id FROM pagos_proveedores p
                   JOIN aplicaciones_proveedores a ON a.pago_id=p.id
                   GROUP BY p.id HAVING sum(abs(a.monto))>abs(p.monto)+0.01)"""),
            'ventas_sobrepagadas': (
                ('ventas','aplicaciones_clientes'),
                """SELECT count(*) FROM (SELECT v.id FROM ventas v
                   JOIN aplicaciones_clientes a ON a.venta_id=v.id
                   GROUP BY v.id HAVING sum(abs(a.monto))>abs(v.monto_total)+0.01)"""),
            'compras_sobrepagadas': (
                ('compras','aplicaciones_proveedores'),
                """SELECT count(*) FROM (SELECT v.id FROM compras v
                   JOIN aplicaciones_proveedores a ON a.compra_id=v.id
                   GROUP BY v.id HAVING sum(abs(a.monto))>abs(v.monto_total)+0.01)"""),
            'aplicaciones_clientes_huerfanas': (
                ('aplicaciones_clientes','pagos_clientes','ventas'),
                """SELECT count(*) FROM aplicaciones_clientes a
                   LEFT JOIN pagos_clientes p ON p.id=a.pago_id
                   LEFT JOIN ventas v ON v.id=a.venta_id
                   WHERE p.id IS NULL OR v.id IS NULL"""),
            'aplicaciones_proveedores_huerfanas': (
                ('aplicaciones_proveedores','pagos_proveedores','compras'),
                """SELECT count(*) FROM aplicaciones_proveedores a
                   LEFT JOIN pagos_proveedores p ON p.id=a.pago_id
                   LEFT JOIN compras v ON v.id=a.compra_id
                   WHERE p.id IS NULL OR v.id IS NULL"""),
            'cartolas_conciliadas_sin_asiento': (
                ('cartola_bancaria',),
                """SELECT count(*) FROM cartola_bancaria
                   WHERE conciliado=1 AND asiento_id IS NULL"""),
            'cartolas_tesoreria_sin_asiento': (
                ('cartola_bancaria',),
                """SELECT count(*) FROM cartola_bancaria
                   WHERE conciliado=1 AND match_tipo='TESORERIA'
                   AND asiento_id IS NULL"""),
            'cartolas_sin_asiento_por_tipo': (
                ('cartola_bancaria',),
                """SELECT COALESCE(match_tipo,'SIN_TIPO'),count(*)
                   FROM cartola_bancaria
                   WHERE conciliado=1 AND asiento_id IS NULL
                   GROUP BY COALESCE(match_tipo,'SIN_TIPO')"""),
            'cartolas_tesoreria_duplicadas': (
                ('cartola_bancaria',),
                """SELECT count(*) FROM (SELECT match_id FROM cartola_bancaria
                   WHERE conciliado=1 AND match_tipo='TESORERIA'
                   GROUP BY match_id HAVING count(*)>1)"""),
        }
        hallazgos={}
        for nombre,(requeridas,sql) in consultas.items():
            if not set(requeridas)<=tablas:
                hallazgos[nombre]=None
            elif nombre=='cartolas_sin_asiento_por_tipo':
                hallazgos[nombre]={tipo:cantidad for tipo,cantidad in conn.execute(sql)}
            else:
                hallazgos[nombre]=conn.execute(sql).fetchone()[0]
        # Una conciliación documental puede abarcar varios asientos y no tener
        # un único asiento_id en la cartola. Verificar los vínculos reales.
        if {'cartola_bancaria','sgci_conciliacion_lineas','libro_diario'} <= tablas:
            hallazgos['conciliaciones_existentes_sin_respaldo_cuadrado'] = conn.execute('''
                SELECT count(*) FROM cartola_bancaria cb
                WHERE cb.conciliado=1 AND cb.match_tipo='ASIENTOS_EXISTENTES' AND (
                  NOT EXISTS(SELECT 1 FROM sgci_conciliacion_lineas x WHERE x.cartola_id=cb.id)
                  OR ABS(ABS(COALESCE(cb.abono,0)-COALESCE(cb.cargo,0))-
                    COALESCE((SELECT SUM(x.monto) FROM sgci_conciliacion_lineas x WHERE x.cartola_id=cb.id),0))>0.01
                  OR EXISTS(SELECT 1 FROM sgci_conciliacion_lineas x LEFT JOIN libro_diario ld ON ld.id=x.diario_id
                            WHERE x.cartola_id=cb.id AND ld.id IS NULL))''').fetchone()[0]
        else:
            hallazgos['conciliaciones_existentes_sin_respaldo_cuadrado'] = None
        cols_cartola = {r[1] for r in conn.execute('PRAGMA table_info(cartola_bancaria)')}
        if {'banco_id','fecha','abono','cargo'} <= cols_cartola:
            hallazgos['grupos_cheques_protestados_inconsistentes'] = conn.execute('''
                SELECT count(*) FROM (SELECT match_id FROM cartola_bancaria
                    WHERE conciliado=1 AND match_tipo='CHEQUE_PROTESTADO'
                    GROUP BY match_id HAVING match_id IS NULL OR count(*)!=3
                      OR count(DISTINCT banco_id)!=1 OR count(DISTINCT fecha)!=1
                      OR ABS(SUM(COALESCE(abono,0)-COALESCE(cargo,0)))>0.01
                      OR count(asiento_id)>0
                      OR SUM(CASE WHEN cargo>0 AND COALESCE(abono,0)=0 THEN 1 ELSE 0 END)!=1
                      OR SUM(CASE WHEN abono>0 AND COALESCE(cargo,0)=0 THEN 1 ELSE 0 END)!=1
                      OR SUM(CASE WHEN cargo>0 AND abono>0 AND ABS(cargo-abono)<0.01 THEN 1 ELSE 0 END)!=1
                      )''').fetchone()[0]
        else:
            hallazgos['grupos_cheques_protestados_inconsistentes'] = None
        return {'integridad':integridad,'infracciones_claves_foraneas':len(fk),
                'tablas':len(tablas),'hallazgos':hallazgos,
                'nota':'Cartolas sin asiento pueden ser conciliaciones documentales o cheques protestados; revisar match_tipo.'}
    finally:
        conn.close()


if __name__=='__main__':
    if len(sys.argv)!=2:
        raise SystemExit('Uso: python scripts/auditar_sqlite.py /ruta/copia.db')
    print(json.dumps(auditar(sys.argv[1]),ensure_ascii=False,indent=2))

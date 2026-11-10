"""Ensayo de migración de permisos en copia temporal; nunca modifica origen.

Uso: python scripts/validar_migracion_copia.py /ruta/sgci_respaldo.db
Requiere el código de CONTEM disponible en el mismo repositorio.
"""
import json
import sqlite3
import sys
import tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from modulos.usuarios import sgci_crear_seguridad


def validar(origen):
    origen=Path(origen).resolve()
    if not origen.is_file():
        raise FileNotFoundError(origen)
    with tempfile.TemporaryDirectory(prefix='contem_migracion_') as carpeta:
        destino=Path(carpeta)/'copia.db'
        with sqlite3.connect(origen.as_uri()+'?mode=ro',uri=True) as entrada:
            with sqlite3.connect(destino) as salida:
                entrada.backup(salida)
        with sqlite3.connect(destino) as db:
            db.row_factory=sqlite3.Row
            tablas_antes={r['name'] for r in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            protegidas=('libro_diario','compras','ventas','pagos_clientes',
                         'pagos_proveedores','sgci_usuarios','sgci_permisos')
            def resumen():
                return {t:db.execute('SELECT count(*) n FROM "'+t+'"').fetchone()['n']
                        for t in protegidas if t in tablas_antes}
            antes=resumen()
            total_antes=db.execute(
                'SELECT COALESCE(sum(debe),0),COALESCE(sum(haber),0) FROM libro_diario'
            ).fetchone() if 'libro_diario' in tablas_antes else None
            sgci_crear_seguridad(db)
            sgci_crear_seguridad(db)  # idempotencia
            despues=resumen()
            total_despues=db.execute(
                'SELECT COALESCE(sum(debe),0),COALESCE(sum(haber),0) FROM libro_diario'
            ).fetchone() if 'libro_diario' in tablas_antes else None
            integridad=db.execute('PRAGMA integrity_check').fetchone()[0]
            claves=len(db.execute('PRAGMA foreign_key_check').fetchall())
            requeridas={'sgci_perfiles','sgci_perfil_permisos',
                        'sgci_usuario_permisos_detalle','sgci_usuario_trabajador',
                        'sgci_alcance_rrhh','sgci_rrhh_autorizados'}
            tablas_despues={r['name'] for r in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            columnas={r['name'] for r in db.execute('PRAGMA table_info(sgci_usuarios)')}
            aprobado=(antes==despues and
                      (tuple(total_antes)==tuple(total_despues) if total_antes else True)
                      and integridad=='ok' and claves==0
                      and requeridas<=tablas_despues
                      and {'nombre_completo','cargo','debe_cambiar_clave'}<=columnas)
            return {'aprobado':aprobado,'integridad':integridad,
                    'infracciones_fk':claves,'registros_antes':antes,
                    'registros_despues':despues,
                    'tablas_seguridad_nuevas':sorted(requeridas-tablas_antes),
                    'totales_diario_preservados':tuple(total_antes)==tuple(total_despues)
                      if total_antes else None,
                    'nota':'Prueba de esquema y preservación; no valida acceso funcional multiusuario.'}


if __name__=='__main__':
    if len(sys.argv)!=2:
        raise SystemExit('Uso: python scripts/validar_migracion_copia.py /ruta/respaldo.db')
    resultado=validar(sys.argv[1])
    print(json.dumps(resultado,indent=2,ensure_ascii=False))
    if not resultado['aprobado']:
        raise SystemExit(1)

"""Etapa 6: política reutilizable de lectura RRHH. Sin acceso operativo ni autenticación."""
from sgci_rrhh_autorizacion import permiso_efectivo, ids_permitidos


class AccesoDenegado(PermissionError):
    pass


def exigir_lectura(conn, email, submodulo, accion='ver'):
    email = str(email or '').strip().lower()
    if submodulo not in ('Trabajadores', 'Liquidaciones') or accion not in ('ver', 'exportar'):
        raise AccesoDenegado('Función o acción no autorizada')
    if not permiso_efectivo(conn, email, submodulo, accion):
        raise AccesoDenegado('Permiso denegado')
    ids = ids_permitidos(conn, email)
    if ids is not None and not ids:
        raise AccesoDenegado('Sin fichas autorizadas')
    return ids


def obtener_trabajador(conn, email, trabajador_id):
    ids = exigir_lectura(conn, email, 'Trabajadores')
    if ids is not None and int(trabajador_id) not in ids:
        raise AccesoDenegado('Ficha fuera del alcance')
    return conn.execute('SELECT id,nombre FROM nomina_trabajadores WHERE id=?', (int(trabajador_id),)).fetchone()


def obtener_liquidacion(conn, email, liquidacion_id, accion='ver'):
    # Una exportación exige también permiso de lectura.
    if accion == 'exportar':
        exigir_lectura(conn, email, 'Liquidaciones', 'ver')
    ids = exigir_lectura(conn, email, 'Liquidaciones', accion)
    row = conn.execute('''SELECT l.id,l.periodo,l.trabajador_id,t.nombre
                          FROM nomina_liquidaciones l
                          JOIN nomina_trabajadores t ON t.id=l.trabajador_id
                          WHERE l.id=?''', (int(liquidacion_id),)).fetchone()
    if row is None:
        return None
    if ids is not None and int(row['trabajador_id']) not in ids:
        raise AccesoDenegado('Liquidación fuera del alcance')
    return row


def listar_liquidaciones(conn, email):
    ids = exigir_lectura(conn, email, 'Liquidaciones')
    sql = '''SELECT l.id,l.periodo,l.trabajador_id,t.nombre
             FROM nomina_liquidaciones l JOIN nomina_trabajadores t ON t.id=l.trabajador_id'''
    params = ()
    if ids is not None:
        ids = tuple(sorted(ids))
        sql += ' WHERE l.trabajador_id IN (' + ','.join('?' for _ in ids) + ')'
        params = ids
    sql += ' ORDER BY l.periodo DESC,l.id DESC'
    return conn.execute(sql, params).fetchall()

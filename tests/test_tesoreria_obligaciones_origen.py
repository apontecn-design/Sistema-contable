import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from modulos import tesoreria
from tests.soporte_flujos import preparar


class TestTesoreriaObligacionesOrigen(unittest.TestCase):
    def setUp(self):
        self.db=preparar(self)
        self.db.executescript("""
            INSERT INTO plan_cuentas(codigo,nombre,tipo) VALUES('2.1.99','Obligación sintética','Pasivo');
            INSERT INTO libro_diario(fecha,cuenta,codigo_cuenta,debe,haber,glosa,asiento_id,origen)
                VALUES('2026-11-01','Gasto','5.1.01',100,0,'Reconocimiento sintético',1,'PROVISION'),
                ('2026-11-01','Obligación','2.1.99',0,100,'Reconocimiento sintético',1,'PROVISION');
        """)
        self.linea=self.db.execute("SELECT id FROM libro_diario WHERE codigo_cuenta='2.1.99'").fetchone()[0]

    def crear(self,monto=70,vincular=True):
        sid=tesoreria.tes_guardar_solicitud(self.db,'2026-11-16','Beneficiario',1,'Pago obligación','2026-11-16','',
            [dict(tipo='Documento sin DTE',descripcion='Obligación reconocida',monto=monto,tratamiento='Obligación ya contabilizada')])
        did=self.db.execute('SELECT id FROM tes_solicitud_detalle WHERE solicitud_id=?',(sid,)).fetchone()[0]
        if vincular:tesoreria.tes_vincular_obligacion(self.db,sid,did,self.linea,True)
        return sid,did

    def preparar_pago(self,monto=70):
        sid,did=self.crear(monto)
        tesoreria.tes_cambiar_estado(self.db,sid,'ENVIADA');tesoreria.tes_cambiar_estado(self.db,sid,'APROBADA')
        tesoreria.tes_confirmar_pago(self.db,sid,'TRANSFERENCIA','2026-11-16',1,'Banco',f'REF-{sid}','pago.pdf',b'%PDF-1.4 prueba')
        return sid,did

    def test_pago_debita_pasivo_y_no_reconoce_gasto_de_nuevo(self):
        sid,did=self.preparar_pago();original=list(self.db.execute('SELECT * FROM libro_diario WHERE asiento_id=1'))
        asiento=tesoreria.tes_contabilizar_pago(self.db,sid,1)
        self.assertEqual([tuple(r) for r in self.db.execute('SELECT codigo_cuenta,debe,haber FROM libro_diario WHERE asiento_id=? ORDER BY id',(asiento,))],[('2.1.99',70,0),('1.1.02',0,70)])
        self.assertEqual(self.db.execute("SELECT SUM(debe-haber) FROM libro_diario WHERE codigo_cuenta='5.1.01'").fetchone()[0],100)
        self.assertEqual(list(self.db.execute('SELECT * FROM libro_diario WHERE asiento_id=1')),original)
        self.assertEqual(self.db.execute('SELECT monto FROM tes_aplicaciones_obligacion WHERE detalle_id=?',(did,)).fetchone()[0],70)
        self.assertEqual(self.db.execute("SELECT usuario FROM tes_eventos WHERE solicitud_id=? AND accion='CONTABILIZAR'",(sid,)).fetchone()[0],'finanzas@example.com')
        with self.assertRaises(ValueError):tesoreria.tes_contabilizar_pago(self.db,sid,1)

    def test_vinculo_guarda_cuenta_huella_y_confirmacion(self):
        sid,did=self.crear()
        self.assertEqual(self.db.execute('SELECT cuenta_contable FROM tes_solicitud_detalle WHERE id=?',(did,)).fetchone()[0],'2.1.99')
        fila=self.db.execute('SELECT * FROM tes_vinculos_obligacion WHERE detalle_id=?',(did,)).fetchone()
        self.assertEqual((fila['linea_origen_id'],fila['confirmado_por']),(self.linea,'finanzas@example.com'));self.assertEqual(len(fila['huella']),64)

    def test_vinculo_sin_confirmacion_no_muta(self):
        sid,did=self.crear(vincular=False);antes=list(self.db.iterdump())
        with self.assertRaises(ValueError):tesoreria.tes_vincular_obligacion(self.db,sid,did,self.linea,False)
        self.assertEqual(list(self.db.iterdump()),antes)

    def test_vinculo_rechaza_linea_de_gasto(self):
        sid,did=self.crear(vincular=False);gasto=self.db.execute("SELECT id FROM libro_diario WHERE codigo_cuenta='5.1.01'").fetchone()[0]
        antes=list(self.db.iterdump())
        with self.assertRaises(ValueError):tesoreria.tes_vincular_obligacion(self.db,sid,did,gasto,True)
        self.assertEqual(list(self.db.iterdump()),antes)

    def test_vinculo_rechaza_monto_mayor_a_saldo(self):
        sid,did=self.crear(101,False);antes=list(self.db.iterdump())
        with self.assertRaises(ValueError):tesoreria.tes_vincular_obligacion(self.db,sid,did,self.linea,True)
        self.assertEqual(list(self.db.iterdump()),antes)

    def test_origen_de_auxiliar_no_elude_flujo_documental(self):
        sid,did=self.crear(vincular=False)
        for origen in ('RCV Compras','NOMINA','CONCILIACION_PAGO_PROVEEDOR'):
            self.db.execute('UPDATE libro_diario SET origen=? WHERE id=?',(origen,self.linea));self.db.commit();antes=list(self.db.iterdump())
            with self.assertRaises(ValueError):tesoreria.tes_vincular_obligacion(self.db,sid,did,self.linea,True)
            self.assertEqual(list(self.db.iterdump()),antes)

    def test_asiento_origen_con_importes_invalidos_se_rechaza(self):
        sid,did=self.crear(vincular=False)
        self.db.execute("INSERT INTO libro_diario(fecha,cuenta,codigo_cuenta,debe,haber,asiento_id,origen) VALUES('2026-11-01','Inválido','5.1.01',-1,-1,1,'PROVISION')");self.db.commit()
        antes=list(self.db.iterdump())
        with self.assertRaises(ValueError):tesoreria.tes_vincular_obligacion(self.db,sid,did,self.linea,True)
        self.assertEqual(list(self.db.iterdump()),antes)

    def test_obligacion_sin_vinculo_sigue_bloqueada(self):
        sid,did=self.crear(vincular=False)
        tesoreria.tes_guardar_clasificacion(self.db,sid,{did:'2.1.99'})
        tesoreria.tes_cambiar_estado(self.db,sid,'ENVIADA');tesoreria.tes_cambiar_estado(self.db,sid,'APROBADA')
        tesoreria.tes_confirmar_pago(self.db,sid,'TRANSFERENCIA','2026-11-16',1,'Banco','REF','pago.pdf',b'%PDF-1.4 prueba')
        antes=list(self.db.iterdump())
        with self.assertRaises(ValueError):tesoreria.tes_contabilizar_pago(self.db,sid,1)
        self.assertEqual(list(self.db.iterdump()),antes)

    def test_revocacion_bajo_reserva_bloquea_vinculo_y_pago(self):
        sid,did=self.preparar_pago()
        original=tesoreria.sgci_autorizar_operacion
        for modulo,op in [('tesoreria',lambda:tesoreria.tes_contabilizar_pago(self.db,sid,1)),
                          ('contabilidad',lambda:tesoreria.tes_vincular_obligacion(self.db,sid,did,self.linea,True))]:
            def autorizar(conn,mod,*args):
                original(conn,mod,*args)
                if conn.in_transaction and mod==modulo:raise PermissionError('Revocado')
            antes=list(self.db.iterdump())
            with patch.dict(vars(tesoreria),{'sgci_autorizar_operacion':autorizar}):
                with self.assertRaises(PermissionError):op()
            self.assertEqual(list(self.db.iterdump()),antes)

    def test_origen_modificado_despues_de_vincular_bloquea_pago(self):
        sid,_=self.preparar_pago()
        self.db.execute("UPDATE libro_diario SET glosa='Modificado' WHERE asiento_id=1");self.db.commit();antes=list(self.db.iterdump())
        with self.assertRaises(ValueError):tesoreria.tes_contabilizar_pago(self.db,sid,1)
        self.assertEqual(list(self.db.iterdump()),antes)

    def test_cuenta_cambiada_despues_de_vincular_bloquea_pago(self):
        sid,did=self.preparar_pago()
        self.db.execute("UPDATE tes_solicitud_detalle SET cuenta_contable='5.1.01' WHERE id=?",(did,));self.db.commit();antes=list(self.db.iterdump())
        with self.assertRaises(ValueError):tesoreria.tes_contabilizar_pago(self.db,sid,1)
        self.assertEqual(list(self.db.iterdump()),antes)

    def test_fallo_evento_revierte_pago_asiento_y_aplicacion(self):
        sid,_=self.preparar_pago()
        self.db.execute("CREATE TRIGGER fallo BEFORE INSERT ON tes_eventos WHEN NEW.accion='CONTABILIZAR' BEGIN SELECT RAISE(ABORT,'fallo'); END");self.db.commit();antes=list(self.db.iterdump())
        with self.assertRaises(sqlite3.IntegrityError):tesoreria.tes_contabilizar_pago(self.db,sid,1)
        self.assertEqual(list(self.db.iterdump()),antes)

    def test_fallo_evento_revierte_vinculo_y_clasificacion(self):
        sid,did=self.crear(vincular=False)
        self.db.execute("CREATE TRIGGER fallo BEFORE INSERT ON tes_eventos WHEN NEW.accion='VINCULAR OBLIGACION' BEGIN SELECT RAISE(ABORT,'fallo'); END");self.db.commit();antes=list(self.db.iterdump())
        with self.assertRaises(sqlite3.IntegrityError):tesoreria.tes_vincular_obligacion(self.db,sid,did,self.linea,True)
        self.assertEqual(list(self.db.iterdump()),antes)

    def test_transaccion_ajena_se_preserva(self):
        sid,did=self.preparar_pago()
        self.db.execute("UPDATE bancos SET nombre='Pendiente'");antes=list(self.db.iterdump())
        with self.assertRaises(RuntimeError):tesoreria.tes_contabilizar_pago(self.db,sid,1)
        with self.assertRaises(RuntimeError):tesoreria.tes_vincular_obligacion(self.db,sid,did,self.linea,True)
        self.assertTrue(self.db.in_transaction);self.assertEqual(list(self.db.iterdump()),antes);self.db.rollback()

    def test_listado_y_vinculo_exigen_permiso_del_diario(self):
        sid,did=self.crear(vincular=False)
        self.db.execute("INSERT INTO sgci_usuario_permisos_detalle VALUES('finanzas@example.com','contabilidad','Libro Diario','ver',0)");self.db.commit()
        with self.assertRaises(PermissionError):tesoreria.tes_obligaciones_disponibles(self.db)
        with self.assertRaises(PermissionError):tesoreria.tes_vincular_obligacion(self.db,sid,did,self.linea,True)

    def test_saldo_global_insuficiente_bloquea_origen_aunque_no_tenga_aplicaciones(self):
        sid,_=self.preparar_pago()
        self.db.executescript("""INSERT INTO libro_diario(fecha,cuenta,codigo_cuenta,debe,haber,asiento_id,origen)
            VALUES('2026-11-15','Obligación','2.1.99',50,0,2,'PAGO EXTERNO'),('2026-11-15','Banco','1.1.02',0,50,2,'PAGO EXTERNO');""")
        antes=list(self.db.iterdump())
        with self.assertRaises(ValueError):tesoreria.tes_contabilizar_pago(self.db,sid,1)
        self.assertEqual(list(self.db.iterdump()),antes)

    def test_lineas_del_mismo_origen_no_exceden_su_saldo(self):
        sid,did=self.preparar_pago(60)
        otro=self.db.execute("INSERT INTO tes_solicitud_detalle(solicitud_id,tipo,descripcion,monto,tratamiento) VALUES(?,'Otro','Segunda línea',60,'Obligación ya contabilizada')",(sid,)).lastrowid;self.db.commit()
        tesoreria.tes_vincular_obligacion(self.db,sid,otro,self.linea,True);antes=list(self.db.iterdump())
        with self.assertRaises(ValueError):tesoreria.tes_contabilizar_pago(self.db,sid,1)
        self.assertEqual(list(self.db.iterdump()),antes)

    def test_despues_de_consumir_origen_desaparece_del_listado(self):
        sid,_=self.preparar_pago(100);tesoreria.tes_contabilizar_pago(self.db,sid,1)
        self.assertNotIn(self.linea,tesoreria.tes_obligaciones_disponibles(self.db).id.tolist())

    def concurrentes(self,sids):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta=Path(carpeta)/'obligaciones.db'
            with closing(sqlite3.connect(ruta)) as db:self.db.backup(db)
            barrera=threading.Barrier(2)
            def ejecutar(i):
                with closing(sqlite3.connect(ruta,timeout=10)) as db:
                    db.row_factory=sqlite3.Row;barrera.wait(timeout=10)
                    try:return ('ok',tesoreria.tes_contabilizar_pago(db,sids[i],1))
                    except ValueError:return ('rechazado',None)
            with ThreadPoolExecutor(max_workers=2) as pool:r=list(pool.map(ejecutar,range(2)))
            with closing(sqlite3.connect(ruta)) as db:aplicado=db.execute('SELECT SUM(monto) FROM tes_aplicaciones_obligacion').fetchone()[0]
            return r,aplicado

    def test_dos_solicitudes_no_sobrepagan_origen(self):
        s1,_=self.preparar_pago(70);s2,_=self.preparar_pago(70)
        r,a=self.concurrentes([s1,s2]);self.assertCountEqual([x[0] for x in r],['ok','rechazado']);self.assertEqual(a,70)

    def test_dos_pagos_parciales_validos_asignan_asientos_distintos(self):
        s1,_=self.preparar_pago(50);s2,_=self.preparar_pago(50)
        r,a=self.concurrentes([s1,s2]);self.assertEqual([x[0] for x in r],['ok','ok']);self.assertNotEqual(r[0][1],r[1][1]);self.assertEqual(a,100)

    def test_dos_sesiones_no_duplican_pago_de_solicitud(self):
        sid,_=self.preparar_pago(70)
        r,a=self.concurrentes([sid,sid]);self.assertCountEqual([x[0] for x in r],['ok','rechazado']);self.assertEqual(a,70)


if __name__=='__main__':unittest.main()

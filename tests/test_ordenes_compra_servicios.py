import unittest
from modulos import empresa
from tests.soporte_flujos import preparar


class TestOrdenesCompra(unittest.TestCase):
    def setUp(self):
        self.db = preparar(self)
        self.lineas = [dict(descripcion='Afecto',cantidad=2,precio_unitario=100,afecto_iva=True),
                       dict(descripcion='Exento',cantidad=1,precio_unitario=50,afecto_iva=False)]

    def guardar(self,oc_id=None):
        return empresa.oc_guardar(self.db,1,'2026-11-11','Contado','',self.lineas,oc_id)

    def compra(self,proveedor=1,total=500):
        self.db.execute("INSERT INTO compras(id,proveedor_id,monto_total,tipo_doc,folio) VALUES(1,?,?,33,'TEST')",(proveedor,total));self.db.commit()

    def test_crear_modificar_y_anular_sin_asientos(self):
        oc = self.guardar()
        self.assertEqual(tuple(self.db.execute('SELECT neto,iva,total FROM ordenes_compra').fetchone()),(250,38,288))
        self.lineas[0]['cantidad']=3
        self.guardar(oc)
        self.assertEqual(self.db.execute('SELECT total FROM ordenes_compra').fetchone()[0],407)
        empresa.oc_cambiar_estado(self.db,oc,'EMITIDA')
        empresa.oc_cambiar_estado(self.db,oc,'ANULADA')
        with self.assertRaises(ValueError):self.guardar(oc)
        self.assertEqual(self.db.execute('SELECT count(*) FROM libro_diario').fetchone()[0],0)

    def test_asociar_sin_recontabilizar_y_bloquear_anulacion(self):
        oc = self.guardar();self.compra()
        empresa.oc_asociar_factura(self.db,oc,1,100)
        with self.assertRaises(ValueError):empresa.oc_cambiar_estado(self.db,oc,'ANULADA')
        with self.assertRaises(ValueError):self.guardar(oc)
        empresa.oc_desvincular_factura(self.db,oc,1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM compras').fetchone()[0],1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM libro_diario').fetchone()[0],0)

    def test_factura_de_otro_proveedor_rechazada(self):
        oc = self.guardar();self.compra(proveedor=2)
        with self.assertRaises(ValueError):empresa.oc_asociar_factura(self.db,oc,1,100)

    def test_no_sobreasocia_factura_entre_ordenes(self):
        a = self.guardar();b = self.guardar();self.compra(total=300)
        empresa.oc_asociar_factura(self.db,a,1,250)
        with self.assertRaises(ValueError):empresa.oc_asociar_factura(self.db,b,1,100)

    def test_asociacion_duplicada_no_duplica_registro(self):
        oc = self.guardar();self.compra()
        empresa.oc_asociar_factura(self.db,oc,1,100)
        with self.assertRaises(Exception):empresa.oc_asociar_factura(self.db,oc,1,100)
        self.assertEqual(self.db.execute('SELECT count(*) FROM ordenes_compra_facturas').fetchone()[0],1)

    def test_modificacion_invalida_preserva_detalle(self):
        oc = self.guardar()
        antes = [tuple(r) for r in self.db.execute('SELECT * FROM ordenes_compra_detalle')]
        self.lineas[0]['cantidad']=-1
        with self.assertRaises(ValueError):self.guardar(oc)
        self.assertEqual([tuple(r) for r in self.db.execute('SELECT * FROM ordenes_compra_detalle')],antes)

    def test_empleado_sin_permiso_no_crea_oc(self):
        self.db.execute("DELETE FROM sgci_perfil_permisos WHERE accion='crear'");self.db.commit()
        with self.assertRaises(PermissionError):self.guardar()

    def test_permiso_editar_no_autoriza_anular(self):
        oc = self.guardar()
        self.db.execute("DELETE FROM sgci_perfil_permisos WHERE accion='anular'");self.db.commit()
        with self.assertRaises(PermissionError):empresa.oc_cambiar_estado(self.db,oc,'ANULADA')

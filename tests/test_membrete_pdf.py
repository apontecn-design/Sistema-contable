from contextlib import closing
"""Regresión: el membrete ReportLab no requiere 'conn' global."""
import io
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from modulos import empresa


class TestMembretePDF(unittest.TestCase):
    def test_pdf_con_perfil_sin_conn_global(self):
        with tempfile.TemporaryDirectory() as temp:
            db = str(Path(temp) / "sgci.db")
            with closing(sqlite3.connect(db)) as conn, conn:
                conn.execute("""CREATE TABLE sgci_perfil_empresa
                    (id INTEGER PRIMARY KEY, razon_social TEXT, rut TEXT,
                     giro TEXT, direccion TEXT, comuna TEXT, ciudad TEXT,
                     telefono TEXT, correo TEXT, logo BLOB)""")
                conn.execute("""INSERT INTO sgci_perfil_empresa
                    (id,razon_social,rut) VALUES (1,'Empresa de prueba','')""")
            buf = io.BytesIO()
            doc = SimpleDocTemplate(buf, pagesize=A4)
            with patch.dict(empresa.sgci_membrete_pdf.__globals__,
                            {"DB_FILE": db, "sqlite3": sqlite3, "os": os, "io": io}):
                doc.build([Paragraph("Prueba de membrete", getSampleStyleSheet()["Normal"])],
                          onFirstPage=empresa.sgci_membrete_pdf,
                          onLaterPages=empresa.sgci_membrete_pdf)
            self.assertTrue(buf.getvalue().startswith(b"%PDF-"))

    def test_pdf_sin_perfil_sigue_generandose(self):
        with tempfile.TemporaryDirectory() as temp:
            db = str(Path(temp) / "sgci.db")
            sqlite3.connect(db).close()
            buf = io.BytesIO()
            doc = SimpleDocTemplate(buf, pagesize=A4)
            with patch.dict(empresa.sgci_membrete_pdf.__globals__,
                            {"DB_FILE": db, "sqlite3": sqlite3, "os": os, "io": io}):
                doc.build([Paragraph("Prueba", getSampleStyleSheet()["Normal"])],
                          onFirstPage=empresa.sgci_membrete_pdf)
            self.assertTrue(buf.getvalue().startswith(b"%PDF-"))


if __name__ == "__main__":
    unittest.main()

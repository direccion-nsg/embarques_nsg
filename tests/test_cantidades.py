import io
import unittest

from pypdf import PdfReader

from modules.pdf_generator import generar_hoja_logistica
from modules.utils import parse_cantidad


class CantidadesTests(unittest.TestCase):
    def test_cantidades_invalidas_se_normalizan_a_cero(self):
        for valor in (None, "", " ", "texto", float("nan"), "NaN",
                      float("inf"), float("-inf"), "Infinity", "1e309"):
            with self.subTest(valor=valor):
                self.assertEqual(parse_cantidad(valor), 0.0)

    def test_conserva_formatos_validos(self):
        for valor, esperado in ((12, 12.0), (2.5, 2.5), ("1,234.00", 1234.0),
                                ("1,234", 1234.0), ("234,50", 234.5),
                                ("0", 0.0), ("-2", -2.0)):
            with self.subTest(valor=valor):
                self.assertEqual(parse_cantidad(valor), esperado)

    def test_pdf_omite_invalidas_y_conserva_cantidades_de_hoy(self):
        productos = [
            {"codigo": "OMITIR_NAN", "cantidad": 100, "cantidad_hoy": float("nan")},
            {"codigo": "OMITIR_INF", "cantidad": float("inf")},
            {"codigo": "OMITIR_VACIA", "cantidad": 100, "cantidad_hoy": None},
            {"codigo": "ENTERO", "cantidad": 100, "cantidad_hoy": 7},
            {"codigo": "DECIMAL", "cantidad": "2.5"},
        ]
        contenido, nombre = generar_hoja_logistica(
            {"folio": "PRUEBA", "productos": productos}, {}
        )
        texto = "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(contenido)).pages)
        self.assertTrue(nombre.endswith(".pdf"))
        self.assertNotIn("OMITIR", texto)
        self.assertIn("ENTERO", texto)
        self.assertIn("\n7\n", texto)
        self.assertIn("DECIMAL", texto)
        self.assertIn("2.5", texto)
        self.assertNotIn("100", texto)

    def test_pdf_con_todas_las_cantidades_invalidas(self):
        contenido, _ = generar_hoja_logistica(
            {"productos": [{"cantidad_hoy": float("nan")}]}, {}
        )
        texto = "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(contenido)).pages)
        self.assertIn("Sin productos", texto)


if __name__ == "__main__":
    unittest.main()

"""
Procesamiento del documento de remisión del cliente — versión en memoria.

Soporta:
  - PDF  → uso directo
  - JPG / JPEG / PNG / WEBP / BMP → convierte a PDF con Pillow + ReportLab

Retorna bytes (sin guardar en disco).
"""

import io
import os
import sys
from datetime import datetime

from PIL import Image
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate
from reportlab.platypus import Image as RLImage

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FORMATOS_IMAGEN  = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif"}
FORMATOS_PDF     = {".pdf"}
FORMATOS_VALIDOS = FORMATOS_PDF | FORMATOS_IMAGEN


def es_formato_valido(nombre: str) -> bool:
    return os.path.splitext(nombre)[1].lower() in FORMATOS_VALIDOS


def guardar_remision(uploaded_file) -> tuple:
    """
    Convierte el archivo de remisión subido a bytes PDF.
    Retorna (bytes_pdf, mensaje). En caso de error retorna (None, mensaje_error).
    """
    nombre = uploaded_file.name
    ext    = os.path.splitext(nombre)[1].lower()

    if ext not in FORMATOS_VALIDOS:
        return None, f"Formato '{ext}' no soportado. Sube PDF, JPG, PNG o WEBP."

    file_bytes = uploaded_file.getvalue()

    if ext in FORMATOS_IMAGEN:
        try:
            pdf_bytes = _imagen_a_pdf_bytes(file_bytes)
            return pdf_bytes, "Imagen convertida a PDF correctamente."
        except Exception as e:
            return None, f"Error al convertir imagen: {e}"

    return file_bytes, "PDF de remisión cargado correctamente."


def _imagen_a_pdf_bytes(imagen_bytes: bytes) -> bytes:
    """Convierte imagen a PDF carta con márgenes. Retorna bytes del PDF."""
    margen = 1.5 * cm
    max_w  = letter[0] - 2 * margen
    max_h  = letter[1] - 2 * margen

    img = Image.open(io.BytesIO(imagen_bytes))
    if img.mode in ("RGBA", "P", "LA", "CMYK"):
        img = img.convert("RGB")

    ancho_px, alto_px = img.size
    ratio  = min(max_w / ancho_px, max_h / alto_px)
    ancho_f = ancho_px * ratio
    alto_f  = alto_px  * ratio

    # Guardar imagen convertida en memoria para RLImage
    img_buf = io.BytesIO()
    img.save(img_buf, format="JPEG")
    img_buf.seek(0)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        leftMargin=margen, rightMargin=margen,
        topMargin=margen,  bottomMargin=margen,
    )
    doc.build([RLImage(img_buf, width=ancho_f, height=alto_f)])
    return buf.getvalue()

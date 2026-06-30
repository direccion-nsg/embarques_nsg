"""OCR para extracción automática de números de guía desde fotos de evidencia."""

import io
import os
import re

from PIL import Image, ImageEnhance, ImageFilter

# Ruta explícita al binario de Tesseract en Windows
_TESSERACT_WIN = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# Caracteres válidos en un número de guía: mayúsculas, dígitos, guiones
_PATTERN = re.compile(r'\b[A-Z0-9][A-Z0-9\-]{5,27}[A-Z0-9]\b')

_STOPWORDS = {
    "EMBARQUE", "CLIENTE", "FECHA", "TOTAL", "PRECIO", "CANTIDAD",
    "NSG", "GRUPO", "MEXICO", "CDMX", "TEOLOYUCAN", "MONTERREY",
    "RFC", "TEL", "FAX", "EMAIL", "PAGO", "IMPORTE", "SUBTOTAL",
    "FROM", "DATE", "TIME", "PAGE", "SEND", "RECEIVED", "DELIVER",
}


def _preprocesar(img: Image.Image) -> Image.Image:
    img = img.convert("L")
    w, h = img.size
    if w < 1000:
        scale = 1000 / w
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    img = ImageEnhance.Contrast(img).enhance(2.5)
    img = img.filter(ImageFilter.SHARPEN)
    return img


def _candidatos(texto: str) -> list:
    vistos: set = set()
    resultado = []
    for tok in _PATTERN.findall(texto.upper()):
        if tok not in _STOPWORDS and tok not in vistos:
            vistos.add(tok)
            resultado.append(tok)
    return resultado


def extraer_candidatos_guia(imagen_bytes: bytes) -> list | None:
    """
    Intenta leer posibles números de guía de la imagen.
    Retorna None si Tesseract no está disponible (para diferenciar de lista vacía).
    Retorna [] si Tesseract funciona pero no detectó candidatos.
    """
    try:
        import pytesseract
    except ImportError:
        return None

    # Apuntar al binario en Windows si no está en PATH
    if os.name == "nt" and os.path.isfile(_TESSERACT_WIN):
        pytesseract.pytesseract.tesseract_cmd = _TESSERACT_WIN

    try:
        img = Image.open(io.BytesIO(imagen_bytes))
        img = _preprocesar(img)
        cfg = (
            "--psm 6 "
            "-c tessedit_char_whitelist="
            "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-"
        )
        texto = pytesseract.image_to_string(img, lang="eng", config=cfg)
        return _candidatos(texto)
    except Exception:
        return None

"""
Combinación de PDFs para paquetes de embarque NSG.

Todos los PDFs se manejan en memoria (bytes).
Orden de páginas:
  Sin remisión : Hoja Logística → Hoja de Salida Bind
  Con remisión : Hoja Logística → Remisión cliente → Hoja de Salida Bind
"""

import io
import sys
import os
from datetime import datetime

from pypdf import PdfWriter, PdfReader

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def combinar_paquete_embarque(
    bytes_logistica: bytes,
    bytes_bind=None,        # bytes o list[bytes] cuando hay múltiples Binds
    bytes_remision: bytes = None,
) -> bytes:
    """
    Combina en memoria los PDFs de un embarque.
    Retorna los bytes del PDF combinado.
    """
    writer = PdfWriter()

    def _add(data):
        if data:
            try:
                for page in PdfReader(io.BytesIO(data)).pages:
                    writer.add_page(page)
            except Exception:
                pass

    _add(bytes_logistica)
    _add(bytes_remision)

    if isinstance(bytes_bind, list):
        for b in bytes_bind:
            _add(b)
    else:
        _add(bytes_bind)

    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def combinar_multiples_embarques(items: list) -> bytes:
    """
    Descarga y concatena los PDFs de paquete de varios embarques desde Supabase Storage.
    items: lista de dicts de la bandeja, cada uno con 'ruta_pdf_generado'.
    Retorna bytes del PDF combinado.
    """
    from modules.storage import descargar_pdf_bytes

    writer = PdfWriter()
    sin_pdf = 0

    for item in items:
        ruta = item.get("ruta_pdf_generado", "")
        if not ruta:
            sin_pdf += 1
            continue
        try:
            data = descargar_pdf_bytes(ruta)
            for page in PdfReader(io.BytesIO(data)).pages:
                writer.add_page(page)
        except Exception:
            sin_pdf += 1

    if not writer.pages:
        raise ValueError("Ningún embarque seleccionado tiene PDF disponible en Storage.")

    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


# Compatibilidad con código anterior
def combinar_pdfs(ruta_bind: str, ruta_logistica: str) -> bytes:
    raise NotImplementedError(
        "combinar_pdfs() fue reemplazado por combinar_paquete_embarque() con bytes."
    )

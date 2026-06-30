"""Supabase Storage para PDFs y evidencias de embarques NSG."""

import os
from supabase import create_client, Client

BUCKET_PDFS        = "embarques-pdfs"
BUCKET_EVIDENCIAS  = "embarques-evidencias"


def _creds():
    try:
        import streamlit as st
        return st.secrets["supabase"]["url"], st.secrets["supabase"]["service_role_key"]
    except Exception:
        return os.environ.get("SUPABASE_URL", ""), os.environ.get("SUPABASE_SERVICE_KEY", "")


def _client() -> Client:
    """Cliente fresco con service_role — sin cache para evitar contaminación por sign_in."""
    url, key = _creds()
    return create_client(url, key)


def init_storage():
    """Crea los buckets si no existen (idempotente)."""
    c = _client()
    for bucket in [BUCKET_PDFS, BUCKET_EVIDENCIAS]:
        try:
            c.storage.create_bucket(bucket, options={"public": False})
        except Exception:
            pass  # Ya existe


def subir_pdf(pdf_bytes: bytes, filename: str) -> str:
    """Sube el PDF al bucket y retorna la ruta en Storage."""
    c = _client()
    ruta = f"pdfs/{filename}"
    c.storage.from_(BUCKET_PDFS).upload(
        path=ruta,
        file=pdf_bytes,
        file_options={"content-type": "application/pdf", "upsert": "true"},
    )
    return ruta


def descargar_pdf_bytes(ruta_storage: str) -> bytes:
    """Descarga el PDF desde Storage y retorna bytes."""
    c = _client()
    return bytes(c.storage.from_(BUCKET_PDFS).download(ruta_storage))


def generar_url_firmada(ruta_storage: str, expira_segundos: int = 604800) -> str:
    """Genera URL firmada para el PDF (por defecto válida 7 días)."""
    c   = _client()
    res = c.storage.from_(BUCKET_PDFS).create_signed_url(ruta_storage, expira_segundos)
    return res.get("signedURL") or res.get("signed_url") or ""


def subir_pdf_combinado(pdf_bytes: bytes, filename: str) -> str:
    """Sube PDF combinado (bandeja) a Storage y retorna su ruta."""
    return subir_pdf(pdf_bytes, filename)


def descargar_evidencia_bytes(ruta_storage: str) -> bytes:
    """Descarga una evidencia (foto de guía) desde Storage y retorna bytes."""
    c = _client()
    return bytes(c.storage.from_(BUCKET_EVIDENCIAS).download(ruta_storage))


def subir_evidencia(archivo_bytes: bytes, filename: str) -> str:
    """Sube evidencia (foto/PDF de guía) y retorna la ruta en Storage."""
    c = _client()
    ruta = f"evidencias/{filename}"
    ext  = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    ct_map = {
        "jpg": "image/jpeg", "jpeg": "image/jpeg",
        "png": "image/png",  "heic": "image/heic",
        "pdf": "application/pdf",
    }
    c.storage.from_(BUCKET_EVIDENCIAS).upload(
        path=ruta,
        file=archivo_bytes,
        file_options={"content-type": ct_map.get(ext, "application/octet-stream"), "upsert": "true"},
    )
    return ruta

"""Utilidades generales de la aplicación."""

import os
import sys
import shutil
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import ENTRADA_DIR, ensure_dirs


def guardar_pdf_entrada(uploaded_file) -> str:
    """
    Guarda el PDF subido por el usuario en /data/entrada/ con nombre único.
    Retorna la ruta absoluta del archivo guardado.
    """
    ensure_dirs()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    nombre_seguro = _sanitizar_nombre(uploaded_file.name)
    nombre_final = f"{ts}_{nombre_seguro}"
    ruta = os.path.join(ENTRADA_DIR, nombre_final)
    with open(ruta, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return ruta


def _sanitizar_nombre(nombre: str) -> str:
    """Elimina caracteres no permitidos en nombres de archivo Windows."""
    chars_invalidos = r'\/:*?"<>|'
    for c in chars_invalidos:
        nombre = nombre.replace(c, "_")
    return nombre


def formatear_fecha_display(fecha_iso: str) -> str:
    """Convierte fecha ISO o datetime string a formato DD/MM/YYYY HH:MM."""
    if not fecha_iso:
        return ""
    try:
        dt = datetime.fromisoformat(fecha_iso.replace("T", " ").split(".")[0])
        return dt.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return fecha_iso


def construir_datos_mensaje(datos_bind: dict, datos_log: dict) -> dict:
    """
    Construye el dict de sustitución para las plantillas de mensajes.
    """
    return {
        "folio_bind":     datos_bind.get("folio", ""),
        "cliente":        datos_bind.get("cliente", ""),
        "fletera":        datos_log.get("fletera", ""),
        "tipo_entrega":   datos_log.get("tipo_entrega", ""),
        "condicion_flete":datos_log.get("condicion_flete", ""),
    }


def verificar_python_disponible() -> bool:
    return shutil.which("python") is not None or shutil.which("python3") is not None

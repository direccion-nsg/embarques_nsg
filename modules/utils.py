"""Utilidades generales de la aplicación."""

import os
import re
import sys
import shutil
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import ENTRADA_DIR, ensure_dirs


def parse_cantidad(v) -> float:
    """
    Convierte a float una cantidad que puede venir en distintos formatos
    (Bind ERP usa coma de miles + punto decimal, ej. "1,234.00").
    Reemplazar toda coma por punto rompe ese formato (produce "1.234.00",
    no parseable, y silenciosamente cae a 0.0), así que primero se
    eliminan las comas de miles y solo se trata como separador decimal
    si no hay un punto ya presente en el valor.
    """
    s = str(v).strip()
    if not s:
        return 0.0
    if "." in s:
        # Formato "#,###.##": la coma es separador de miles.
        s = s.replace(",", "")
    else:
        # Sin punto: la coma podría ser decimal (formato europeo) o de miles.
        # Se asume separador de miles si agrupa en bloques de 3 dígitos
        # (ej. "1,234"); si no, se trata como decimal (ej. "234,50").
        if re.fullmatch(r"-?\d{1,3}(,\d{3})+", s):
            s = s.replace(",", "")
        else:
            s = s.replace(",", ".")
    try:
        return float(s or 0)
    except (ValueError, TypeError):
        return 0.0


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

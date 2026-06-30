"""
Funciones de mensajería y notificación.

Los PDFs se comparten como links firmados de Supabase Storage (válidos 7 días),
ya que la app corre en la nube y no puede adjuntar archivos directamente.
"""

import os
import sys
import subprocess
import urllib.parse
import webbrowser
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (
    EMAIL_DESTINO, SALIDA_DIR,
    EMAIL_ASUNTO_TEMPLATE, EMAIL_CUERPO_TEMPLATE,
    TEAMS_MENSAJE_TEMPLATE,
    EMAIL_ASUNTO_MULTI_TEMPLATE, EMAIL_CUERPO_MULTI_TEMPLATE,
    TEAMS_MENSAJE_MULTI_TEMPLATE, LINEA_EMBARQUE_TEMPLATE,
)


# ──────────────────────────────────────────────────────────────────────────────
# Embarque individual
# ──────────────────────────────────────────────────────────────────────────────

def construir_mailto(datos: dict, url_pdf: str = "") -> str:
    ctx    = {**datos, "url_pdf": url_pdf or "(PDF no disponible)"}
    asunto = EMAIL_ASUNTO_TEMPLATE.format(**ctx)
    cuerpo = EMAIL_CUERPO_TEMPLATE.format(**ctx)
    params = urllib.parse.urlencode(
        {"subject": asunto, "body": cuerpo},
        quote_via=urllib.parse.quote,
    )
    return f"mailto:{urllib.parse.quote(EMAIL_DESTINO)}?{params}"


def construir_mensaje_teams(datos: dict, url_pdf: str = "") -> str:
    ctx = {**datos, "url_pdf": url_pdf or "(PDF no disponible)"}
    return TEAMS_MENSAJE_TEMPLATE.format(**ctx)


def abrir_mailto(datos: dict, url_pdf: str = ""):
    webbrowser.open(construir_mailto(datos, url_pdf))


# ──────────────────────────────────────────────────────────────────────────────
# Múltiples embarques (bandeja)
# ──────────────────────────────────────────────────────────────────────────────

def _lista_embarques_texto(items: list) -> str:
    lineas = []
    for item in items:
        lineas.append(LINEA_EMBARQUE_TEMPLATE.format(
            folio_bind      = item.get("folio_bind", "—"),
            cliente         = item.get("cliente", "—"),
            destinatario    = item.get("destinatario_nombre") or item.get("destinatario", "—"),
            fletera         = item.get("fletera", "—"),
            tipo_entrega    = item.get("tipo_entrega", "—"),
            condicion_flete = item.get("condicion_flete", "—"),
        ))
    return "\n".join(lineas)


def construir_mensaje_teams_multiple(items: list, url_pdf: str = "") -> str:
    lista = _lista_embarques_texto(items)
    return TEAMS_MENSAJE_MULTI_TEMPLATE.format(
        n=len(items),
        lista_embarques=lista,
        url_pdf=url_pdf or "(PDF no disponible)",
    )


def construir_mailto_multiple(items: list, url_pdf: str = "") -> str:
    fecha  = datetime.now().strftime("%d/%m/%Y")
    lista  = _lista_embarques_texto(items)
    asunto = EMAIL_ASUNTO_MULTI_TEMPLATE.format(n=len(items), fecha=fecha)
    cuerpo = EMAIL_CUERPO_MULTI_TEMPLATE.format(
        n=len(items),
        lista_embarques=lista,
        url_pdf=url_pdf or "(PDF no disponible)",
    )
    params = urllib.parse.urlencode(
        {"subject": asunto, "body": cuerpo},
        quote_via=urllib.parse.quote,
    )
    return f"mailto:{urllib.parse.quote(EMAIL_DESTINO)}?{params}"


def abrir_mailto_multiple(items: list, url_pdf: str = ""):
    webbrowser.open(construir_mailto_multiple(items, url_pdf))


# ──────────────────────────────────────────────────────────────────────────────
# Utilidades de carpeta
# ──────────────────────────────────────────────────────────────────────────────

def abrir_carpeta(ruta_pdf: str):
    """Abre en Explorer la carpeta que contiene el PDF."""
    carpeta = os.path.dirname(ruta_pdf) if os.path.isfile(ruta_pdf) else ruta_pdf
    if os.path.exists(carpeta):
        subprocess.Popen(f'explorer "{carpeta}"')


def abrir_carpeta_salida():
    """Abre directamente la carpeta /data/salida/ donde se guardan todos los paquetes."""
    if os.path.exists(SALIDA_DIR):
        subprocess.Popen(f'explorer "{SALIDA_DIR}"')


# ──────────────────────────────────────────────────────────────────────────────
# Preparado para Microsoft Graph API — implementar en siguiente fase
# ──────────────────────────────────────────────────────────────────────────────
#
# def enviar_por_outlook_graph(datos: dict, rutas_pdf: list, access_token: str):
#     import base64, requests
#     endpoint = "https://graph.microsoft.com/v1.0/me/sendMail"
#     headers  = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
#     adjuntos = []
#     for ruta in rutas_pdf:
#         with open(ruta, "rb") as f:
#             adjuntos.append({
#                 "@odata.type": "#microsoft.graph.fileAttachment",
#                 "name": os.path.basename(ruta),
#                 "contentBytes": base64.b64encode(f.read()).decode(),
#             })
#     asunto = EMAIL_ASUNTO_TEMPLATE.format(**datos)
#     cuerpo = EMAIL_CUERPO_TEMPLATE.format(**datos)
#     payload = {
#         "message": {
#             "subject": asunto,
#             "body": {"contentType": "Text", "content": cuerpo},
#             "toRecipients": [{"emailAddress": {"address": EMAIL_DESTINO}}],
#             "attachments": adjuntos,
#         }
#     }
#     requests.post(endpoint, headers=headers, json=payload)

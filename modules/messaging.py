"""
Funciones de mensajería y notificación.

Los PDFs se comparten como links firmados de Supabase Storage (válidos 7 días),
ya que la app corre en la nube y no puede adjuntar archivos directamente.
"""

import os
import sys
import smtplib
import subprocess
import urllib.parse
import webbrowser
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

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
# Envío SMTP automático — notificación a planta/almacén
# ──────────────────────────────────────────────────────────────────────────────

def _smtp_cfg() -> dict:
    """Lee credenciales SMTP desde st.secrets o variables de entorno."""
    try:
        import streamlit as st
        cfg = st.secrets.get("email", {})
    except Exception:
        cfg = {}
    return {
        "server":       cfg.get("smtp_server")   or os.environ.get("EMAIL_SMTP_SERVER", ""),
        "port":         int(cfg.get("smtp_port",  587)),
        "usuario":      cfg.get("usuario")        or os.environ.get("EMAIL_USUARIO", ""),
        "password":     cfg.get("password")       or os.environ.get("EMAIL_PASSWORD", ""),
        "destinatario": cfg.get("destinatario")   or EMAIL_DESTINO,
    }


def enviar_email_planta(items: list, url_pdf: str = "", enviado_por: str = "") -> tuple:
    """
    Envía email de notificación a almacén al marcar embarques como 'Enviado a Planta'.
    Retorna (True, "") o (False, mensaje_error).
    """
    cfg = _smtp_cfg()
    if not all([cfg["server"], cfg["usuario"], cfg["password"]]):
        return False, "Credenciales SMTP no configuradas en [email] de secrets."

    fecha  = datetime.now().strftime("%d/%m/%Y %H:%M")
    n      = len(items)
    lista  = _lista_embarques_texto(items)
    asunto = (
        f"🏭 {'Embarque listo' if n == 1 else f'{n} Embarques listos'} para Planta — {fecha}"
    )
    cuerpo = (
        f"Buen día equipo Planta/Almacén.\n\n"
        f"{'El siguiente embarque ha sido' if n == 1 else f'Los siguientes {n} embarques han sido'} "
        f"enviado(s) a Planta para preparación y despacho:\n\n"
        f"{lista}\n\n"
    )
    if url_pdf:
        cuerpo += f"📎 PDF con paquetes de embarque (válido 7 días):\n{url_pdf}\n\n"
    cuerpo += (
        f"Favor de preparar conforme a la hoja logística incluida en el PDF.\n\n"
        f"Enviado por: {enviado_por or 'Sistema NSG'}\n"
        f"Fecha y hora: {fecha}\n"
    )

    msg = MIMEMultipart()
    msg["From"]    = cfg["usuario"]
    msg["To"]      = cfg["destinatario"]
    msg["Subject"] = asunto
    msg.attach(MIMEText(cuerpo, "plain", "utf-8"))

    try:
        with smtplib.SMTP(cfg["server"], cfg["port"], timeout=15) as srv:
            srv.ehlo()
            srv.starttls()
            srv.login(cfg["usuario"], cfg["password"])
            srv.send_message(msg)
        return True, ""
    except Exception as e:
        return False, str(e)


def enviar_email_regreso_planta(emb: dict, motivo: str) -> tuple:
    """
    Notifica a Finanzas que Planta regresó un embarque a la Bandeja.
    Retorna (True, "") o (False, mensaje_error).
    """
    cfg = _smtp_cfg()
    if not all([cfg["server"], cfg["usuario"], cfg["password"]]):
        return False, "Credenciales SMTP no configuradas en [email] de secrets."

    fecha   = datetime.now().strftime("%d/%m/%Y %H:%M")
    folio   = emb.get("folios_bind") or emb.get("folio_bind", "—")
    cliente = emb.get("clientes")    or emb.get("cliente", "—")
    dest    = emb.get("destinatario_nombre", "—")
    fletera = emb.get("fletera", "—")

    asunto = f"⚠️ Embarque {folio} regresado a Bandeja por Planta — {fecha}"
    cuerpo = (
        f"Equipo Finanzas.\n\n"
        f"El equipo de Planta/Almacén regresó el siguiente embarque a la Bandeja:\n\n"
        f"  Folio Bind:   {folio}\n"
        f"  Cliente:      {cliente}\n"
        f"  Destinatario: {dest}\n"
        f"  Fletera:      {fletera}\n\n"
        f"Motivo indicado por Planta:\n"
        f"  {motivo}\n\n"
        f"Por favor revisa y corrige el embarque en la Bandeja antes de reenviarlo a Planta.\n\n"
        f"Fecha y hora: {fecha}\n"
    )

    msg = MIMEMultipart()
    msg["From"]    = cfg["usuario"]
    msg["To"]      = "finanzas@gruponsg.com"
    msg["Subject"] = asunto
    msg.attach(MIMEText(cuerpo, "plain", "utf-8"))

    try:
        with smtplib.SMTP(cfg["server"], cfg["port"], timeout=15) as srv:
            srv.ehlo()
            srv.starttls()
            srv.login(cfg["usuario"], cfg["password"])
            srv.send_message(msg)
        return True, ""
    except Exception as e:
        return False, str(e)


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

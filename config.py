import os
import sys

APP_NAME = "Preparación de Embarques NSG"
VERSION = "1.0.0"

# Hook de integración futura con ERP NSG
ERP_NSG_INTEGRATION_ENABLED = False
ERP_NSG_API_URL = ""  # Se configurará al integrar con ERP NSG


def get_app_dir():
    """Retorna el directorio base de la aplicación, compatible con PyInstaller."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


APP_DIR = get_app_dir()

DB_DIR = os.path.join(APP_DIR, "db")
DATA_DIR = os.path.join(APP_DIR, "data")
ENTRADA_DIR = os.path.join(DATA_DIR, "entrada")
SALIDA_DIR = os.path.join(DATA_DIR, "salida")
ASSETS_DIR = os.path.join(APP_DIR, "assets")

DB_PATH = os.path.join(DB_DIR, "embarques.db")

# Dirección de destino para envíos (Almacén Teoloyucan)
EMAIL_DESTINO = "almacen@gruponsg.com"
TEAMS_CANAL = ""  # Webhook Teams — se configura al implementar Microsoft Graph

EMAIL_ASUNTO_TEMPLATE = "Paquete de Embarque | Salida {folio_bind} | {cliente}"
EMAIL_CUERPO_TEMPLATE = (
    "Buen día.\n\n"
    "Se comparte el paquete de embarque correspondiente a la salida {folio_bind} del cliente {cliente}.\n\n"
    "Fletera:          {fletera}\n"
    "Tipo de entrega:  {tipo_entrega}\n"
    "Condición flete:  {condicion_flete}\n\n"
    "📎 Descargar PDF del paquete (válido 7 días):\n"
    "{url_pdf}\n\n"
    "Favor de preparar el embarque conforme a la hoja logística incluida en el PDF.\n\n"
    "Saludos,\nFinanzas — Grupo NSG"
)

TEAMS_MENSAJE_TEMPLATE = (
    "Buen día. Se comparte paquete de embarque — Salida {folio_bind} | {cliente}.\n"
    "Fletera: {fletera} | {tipo_entrega} | {condicion_flete}.\n"
    "📎 PDF: {url_pdf}"
)

# Plantillas para múltiples embarques en una sola notificación
EMAIL_ASUNTO_MULTI_TEMPLATE = "Paquetes de Embarque — {n} embarques — {fecha}"
EMAIL_CUERPO_MULTI_TEMPLATE = (
    "Buen día.\n\n"
    "Se comparten los siguientes {n} embarques para preparación en planta Teoloyucan:\n\n"
    "{lista_embarques}\n\n"
    "📎 Descargar PDF completo con todos los paquetes (válido 7 días):\n"
    "{url_pdf}\n\n"
    "Favor de preparar cada embarque conforme a su hoja logística incluida en el PDF.\n\n"
    "Saludos,\nFinanzas — Grupo NSG"
)
TEAMS_MENSAJE_MULTI_TEMPLATE = (
    "Buen día. Se comparten {n} embarques para preparación en planta Teoloyucan:\n\n"
    "{lista_embarques}\n\n"
    "📎 PDF completo: {url_pdf}"
)
# Formato de cada línea en la lista de embarques múltiples
LINEA_EMBARQUE_TEMPLATE = "• {folio_bind} | {cliente} | {destinatario} | {fletera} | {tipo_entrega} | {condicion_flete}"

# Datos del remitente por defecto (NSG) — extraídos del PDF Bind o de catálogo
NSG_REMITENTE_DEFAULT = {
    "nombre": "GRUPO COMERCIALIZADOR NSG",
    "rfc": "GCN1309264I6",
    "direccion": "LABORATORISTAS No. 58B, Col. SIFON C.P 09400, Iztapalapa, Ciudad de México, México",
    "telefono": "56332319",
}


def ensure_dirs():
    """Crea las carpetas necesarias si no existen."""
    for d in [DB_DIR, DATA_DIR, ENTRADA_DIR, SALIDA_DIR, ASSETS_DIR]:
        os.makedirs(d, exist_ok=True)

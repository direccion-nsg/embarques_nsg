"""
Funciones de alto nivel para los catálogos: remitentes, destinatarios, fleteras.
Actúa como capa intermedia entre la UI y database.py para
mantener la lógica de negocio separada de la base de datos.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from modules.database import (
    get_remitentes, upsert_remitente, delete_remitente,
    get_destinatarios, upsert_destinatario, delete_destinatario,
    get_fleteras, upsert_fletera, delete_fletera,
    get_domicilios_entrega, upsert_domicilio_entrega, delete_domicilio_entrega,
)


# ── Remitentes ────────────────────────────────────────────────────────────────

def listar_remitentes() -> list:
    return get_remitentes()


def nombres_remitentes() -> list:
    return [r["nombre"] for r in get_remitentes()]


def get_remitente_por_nombre(nombre: str) -> dict:
    for r in get_remitentes():
        if r["nombre"] == nombre:
            return r
    return {}


def guardar_remitente(data: dict):
    upsert_remitente(data)


def eliminar_remitente(id_: int):
    delete_remitente(id_)


# ── Destinatarios ─────────────────────────────────────────────────────────────

def listar_destinatarios() -> list:
    return get_destinatarios()


def nombres_destinatarios() -> list:
    return [d["nombre"] for d in get_destinatarios()]


def get_destinatario_por_nombre(nombre: str) -> dict:
    for d in get_destinatarios():
        if d["nombre"] == nombre:
            return d
    return {}


def guardar_destinatario(data: dict):
    upsert_destinatario(data)


def eliminar_destinatario(id_: int):
    delete_destinatario(id_)


# ── Fleteras ──────────────────────────────────────────────────────────────────

def listar_fleteras() -> list:
    return get_fleteras()


def nombres_fleteras() -> list:
    return [f["nombre"] for f in get_fleteras()]


def guardar_fletera(data: dict):
    upsert_fletera(data)


def eliminar_fletera(id_: int):
    delete_fletera(id_)


# ── Domicilios de entrega (vehículo propio NSG) ───────────────────────────────

def listar_domicilios_entrega() -> list:
    return get_domicilios_entrega()


def nombres_domicilios_entrega() -> list:
    return [d["nombre"] for d in get_domicilios_entrega()]


def get_domicilio_por_nombre(nombre: str) -> dict:
    for d in get_domicilios_entrega():
        if d["nombre"] == nombre:
            return d
    return {}


def guardar_domicilio_entrega(data: dict):
    upsert_domicilio_entrega(data)


def eliminar_domicilio_entrega(id_: int):
    delete_domicilio_entrega(id_)


# ── Generador de observaciones automáticas ────────────────────────────────────

def generar_observaciones(fletera: str, tipo_entrega: str, condicion_flete: str,
                           con_remision: bool, empresa_remision: str,
                           numero_remision: str, estado_remision: str = "",
                           notas_adicionales: str = "") -> str:
    partes = [p for p in [fletera, tipo_entrega, condicion_flete] if p]

    if con_remision:
        if empresa_remision:
            rem = f"Remisión {empresa_remision}"
            if numero_remision:
                rem += f" No. {numero_remision}"
            elif estado_remision == "Sin número":
                rem += " (sin número)"
        elif estado_remision == "Sin número":
            rem = "Remisión del cliente sin número visible"
        elif estado_remision == "Pendiente":
            rem = "Remisión del cliente pendiente de recibir"
        elif estado_remision == "En papel":
            rem = "Remisión del cliente (se adjunta en papel)"
        elif estado_remision == "Digital adjunta":
            rem = "Con remisión del cliente (digital)"
        else:
            rem = "Con remisión del cliente"
        partes.append(rem)

    obs = " | ".join(partes)
    if notas_adicionales and notas_adicionales.strip():
        obs += f" | {notas_adicionales.strip()}"
    return obs

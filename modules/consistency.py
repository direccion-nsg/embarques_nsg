"""
Asistente de Consistencia — detecta diferencias entre el PDF Bind
y los datos capturados en la hoja logística.
"""

import json
import re
import unicodedata
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ──────────────────────────────────────────────────────────────────────────────
# Utilidad interna
# ──────────────────────────────────────────────────────────────────────────────

def _norm(texto: str) -> str:
    """Minúsculas + sin acentos para comparaciones tolerantes."""
    sin_acentos = "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )
    return sin_acentos.lower()


# ──────────────────────────────────────────────────────────────────────────────
# extraer_cp
# ──────────────────────────────────────────────────────────────────────────────

_RE_CP = re.compile(r"C\.?P\.?\s*:?\s*(\d{5})", re.IGNORECASE)


def extraer_cp(texto: str) -> str:
    """
    Extrae código postal de 5 dígitos de un texto de dirección.
    Reconoce: C.P 58149 / CP 58149 / C.P. 58149 / C.P.58149 / CP: 58149
    Devuelve el CP como string o "" si no encuentra.
    """
    if not texto:
        return ""
    m = _RE_CP.search(texto)
    return m.group(1) if m else ""


# ──────────────────────────────────────────────────────────────────────────────
# interpretar_notas_bind
# ──────────────────────────────────────────────────────────────────────────────

def interpretar_notas_bind(notas: str, fleteras_catalogo: list) -> dict:
    """
    Analiza el texto de las notas del PDF Bind y sugiere valores logísticos.

    Parámetros:
        notas              — texto completo de la sección Notas del Bind
        fleteras_catalogo  — lista de nombres de fleteras del catálogo

    Retorna dict:
        fletera_sugerida          str   — nombre de fletera del catálogo, o ""
        tipo_entrega_sugerido     str   — "Ocurre" | "Domicilio" | ""
        condicion_flete_sugerida  str   — "Por cobrar" | "Pagado" | ""
        con_remision_sugerido     bool
    """
    resultado = {
        "fletera_sugerida":         "",
        "tipo_entrega_sugerido":    "",
        "condicion_flete_sugerida": "",
        "con_remision_sugerido":    False,
    }
    if not notas:
        return resultado

    texto_norm = _norm(notas)

    # Condición de flete
    if "por cobrar" in texto_norm:
        resultado["condicion_flete_sugerida"] = "Por cobrar"
    elif "pagado" in texto_norm:
        resultado["condicion_flete_sugerida"] = "Pagado"

    # Tipo de entrega
    if "ocurre" in texto_norm:
        resultado["tipo_entrega_sugerido"] = "Ocurre"
    elif "domicilio" in texto_norm:
        resultado["tipo_entrega_sugerido"] = "Domicilio"

    # Fletera: busca coincidencia contra el catálogo (insensible a acentos/mayúsculas)
    for nombre in fleteras_catalogo:
        if nombre and _norm(nombre) in texto_norm:
            resultado["fletera_sugerida"] = nombre
            break

    # Remisión
    resultado["con_remision_sugerido"] = bool(
        re.search(r"remisi[oó]n", notas, re.IGNORECASE)
    )

    return resultado


# ──────────────────────────────────────────────────────────────────────────────
# validar_consistencia
# ──────────────────────────────────────────────────────────────────────────────

def validar_consistencia(datos_bind: dict, datos_logisticos: dict) -> list:
    """
    Valida consistencia entre datos del Bind y la hoja logística.

    Retorna lista de dicts:
        campo           str   — campo involucrado
        nivel           str   — "ERROR" | "WARNING" | "OK"
        mensaje         str   — descripción legible
        valor_bind      str   — valor que indica el Bind
        valor_logistica str   — valor capturado en logística
        accion_sugerida str   — qué debe hacer el usuario
    """
    from modules.database import get_fleteras  # import local para evitar circular

    resultados = []
    notas      = datos_bind.get("notas", "")
    texto_norm = _norm(notas)
    fleteras_cat = [f["nombre"] for f in get_fleteras()]

    # ── ERRORs: campos obligatorios faltantes ─────────────────────────────────

    if not datos_bind.get("folio"):
        resultados.append(_entrada("folio", "ERROR",
            "El folio de salida Bind está vacío.",
            accion="Corrige el folio en el Paso 2."))

    if not datos_logisticos.get("destinatario_nombre"):
        resultados.append(_entrada("destinatario", "ERROR",
            "No hay destinatario capturado.",
            accion="Indica el nombre del destinatario en el Paso 3."))

    if not datos_logisticos.get("fletera"):
        resultados.append(_entrada("fletera", "ERROR",
            "No hay fletera capturada.",
            accion="Indica la fletera en el Paso 3."))

    if not datos_logisticos.get("tipo_entrega"):
        resultados.append(_entrada("tipo_entrega", "ERROR",
            "No hay tipo de entrega seleccionado.",
            accion="Selecciona el tipo de entrega en el Paso 3."))

    if not datos_logisticos.get("condicion_flete"):
        resultados.append(_entrada("condicion_flete", "ERROR",
            "No hay condición de flete seleccionada.",
            accion="Selecciona la condición de flete en el Paso 3."))

    # Domicilio requiere dirección + (teléfono o contacto)
    if datos_logisticos.get("tipo_entrega") == "Domicilio":
        if not datos_logisticos.get("destinatario_direccion"):
            resultados.append(_entrada("destinatario_direccion", "ERROR",
                "Entrega a domicilio requiere dirección del destinatario.",
                accion="Captura la dirección del destinatario en el Paso 3."))
        if not datos_logisticos.get("destinatario_tel") and \
           not datos_logisticos.get("destinatario_contacto"):
            resultados.append(_entrada("destinatario_contacto", "ERROR",
                "Entrega a domicilio requiere teléfono o contacto del destinatario.",
                accion="Captura el teléfono o contacto en el Paso 3."))

    # ── WARNINGs: inconsistencias contra notas del Bind ───────────────────────

    if notas:
        # Condición de flete
        cond_log = datos_logisticos.get("condicion_flete", "")
        if "por cobrar" in texto_norm and cond_log == "Pagado":
            resultados.append(_entrada("condicion_flete", "WARNING",
                "La Hoja de Salida Bind indica «Por cobrar» pero la hoja logística tiene «Pagado».",
                val_bind="Por cobrar", val_log="Pagado",
                accion="Verifica cuál es la condición correcta y corrige antes de generar."))
        elif "pagado" in texto_norm and cond_log == "Por cobrar":
            resultados.append(_entrada("condicion_flete", "WARNING",
                "La Hoja de Salida Bind indica «Pagado» pero la hoja logística tiene «Por cobrar».",
                val_bind="Pagado", val_log="Por cobrar",
                accion="Verifica cuál es la condición correcta y corrige antes de generar."))

        # Tipo de entrega
        tipo_log = datos_logisticos.get("tipo_entrega", "")
        if "ocurre" in texto_norm and tipo_log == "Domicilio":
            resultados.append(_entrada("tipo_entrega", "WARNING",
                "La Hoja de Salida Bind indica «Ocurre» pero la hoja logística tiene «Domicilio».",
                val_bind="Ocurre", val_log="Domicilio",
                accion="Verifica el tipo de entrega correcto."))
        elif "domicilio" in texto_norm and tipo_log == "Ocurre":
            resultados.append(_entrada("tipo_entrega", "WARNING",
                "La Hoja de Salida Bind indica «Domicilio» pero la hoja logística tiene «Ocurre».",
                val_bind="Domicilio", val_log="Ocurre",
                accion="Verifica el tipo de entrega correcto."))

        # Fletera
        fletera_log = datos_logisticos.get("fletera", "")
        for nombre in fleteras_cat:
            if nombre and _norm(nombre) in texto_norm and _norm(nombre) != _norm(fletera_log):
                resultados.append(_entrada("fletera", "WARNING",
                    f"Las notas del Bind mencionan «{nombre}» pero la fletera seleccionada es «{fletera_log}».",
                    val_bind=nombre, val_log=fletera_log,
                    accion="Verifica cuál es la fletera correcta."))
                break

        # Remisión mencionada en notas pero no activada
        bind_menciona_remision = bool(re.search(r"remisi[oó]n", notas, re.IGNORECASE))
        if bind_menciona_remision and not datos_logisticos.get("con_remision"):
            resultados.append(_entrada("con_remision", "WARNING",
                "Las notas del Bind mencionan «remisión» pero no se activó la opción.",
                val_bind="Con remisión", val_log="Sin remisión",
                accion="Activa «Con remisión del cliente» si corresponde."))

    # ── WARNINGs operativos: campos de remisión opcionales pero relevantes ────

    if datos_logisticos.get("con_remision"):
        if not datos_logisticos.get("empresa_remision"):
            resultados.append(_entrada("empresa_remision", "WARNING",
                "No se capturó la empresa que remisiona.",
                accion="Puedes capturarla ahora o continuar sin ella si no aplica."))

        if not datos_logisticos.get("numero_remision"):
            estado_rem = datos_logisticos.get("estado_remision", "")
            if estado_rem not in ("Sin número", "Pendiente"):
                resultados.append(_entrada("numero_remision", "WARNING",
                    "No se capturó el número de remisión.",
                    accion="Indica el número, o selecciona «Sin número» / «Pendiente» según corresponda."))

        if datos_logisticos.get("estado_remision") == "Digital adjunta" and \
                not datos_logisticos.get("ruta_pdf_remision"):
            resultados.append(_entrada("ruta_pdf_remision", "WARNING",
                "Estado de remisión es «Digital adjunta» pero no se subió ningún archivo.",
                accion="Sube el PDF o imagen de la remisión, o cambia el estado a «Pendiente» o «En papel»."))

    # ── WARNING: CP del destinatario no detectado ─────────────────────────────

    if not datos_logisticos.get("destinatario_cp"):
        if datos_logisticos.get("destinatario_direccion"):
            resultados.append(_entrada("destinatario_cp", "WARNING",
                "No se detectó el Código Postal en la dirección del destinatario.",
                accion="Captura el CP manualmente en el campo «CP (manual)», o agrégalo a la dirección en formato «C.P. 12345»."))

    return resultados


def _entrada(campo: str, nivel: str, mensaje: str,
             val_bind: str = "", val_log: str = "",
             accion: str = "") -> dict:
    return {
        "campo":           campo,
        "nivel":           nivel,
        "mensaje":         mensaje,
        "valor_bind":      val_bind,
        "valor_logistica": val_log,
        "accion_sugerida": accion,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Helpers de resultado
# ──────────────────────────────────────────────────────────────────────────────

def hay_errores(resultados: list) -> bool:
    return any(r["nivel"] == "ERROR" for r in resultados)


def hay_warnings(resultados: list) -> bool:
    return any(r["nivel"] == "WARNING" for r in resultados)


def detalle_warnings_json(resultados: list) -> str:
    """Serializa los warnings a JSON para guardar en historial."""
    warnings = [r for r in resultados if r["nivel"] == "WARNING"]
    return json.dumps(warnings, ensure_ascii=False) if warnings else ""

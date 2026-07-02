"""Captura de Guías de Embarque."""

import os
import sys
from datetime import date, datetime, time

import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import APP_NAME, VERSION, DATA_DIR, ensure_dirs
from modules.database import (
    init_database,
    get_embarques_filtrados,
    get_embarque_por_id,
    guardar_guia,
)
from modules.ocr import extraer_candidatos_guia
from modules.sidebar import render_sidebar
from modules.auth import require_auth

# ──────────────────────────────────────────────────────────────────────────────
# Configuración
# ──────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title=f"Guías — {APP_NAME}",
    page_icon="🧾",
    layout="wide",
)
ensure_dirs()
init_database()
require_auth("guias")
render_sidebar(APP_NAME, VERSION)

# Limpiar embarque pre-seleccionado si el usuario llegó desde el sidebar
# (no desde Historial — Historial setea _nav_to_guias_from_hist antes de switch_page)
if st.session_state.get("_current_page") != "guias":
    if not st.session_state.pop("_nav_to_guias_from_hist", False):
        st.session_state["embarque_seleccionado"] = None
    for _k in ("_ocr_guia", "_ocr_guia_emb"):
        st.session_state.pop(_k, None)
st.session_state["_current_page"] = "guias"

# ──────────────────────────────────────────────────────────────────────────────
# Estado de sesión
# ──────────────────────────────────────────────────────────────────────────────

if "embarque_seleccionado" not in st.session_state:
    st.session_state["embarque_seleccionado"] = None
if "guia_guardada" not in st.session_state:
    st.session_state["guia_guardada"] = False

# ──────────────────────────────────────────────────────────────────────────────
# Helper
# ──────────────────────────────────────────────────────────────────────────────

def _guardar_evidencia(archivo, embarque_id: int) -> str:
    """Sube la evidencia a Storage. Retorna la ruta o cadena vacía si falla."""
    try:
        from modules.storage import subir_evidencia
        ts     = datetime.now().strftime("%Y%m%d_%H%M%S")
        ext    = os.path.splitext(archivo.name)[1].lower() or ".bin"
        nombre = f"EVIDENCIA_{embarque_id}_{ts}{ext}"
        return subir_evidencia(archivo.getvalue(), nombre)
    except Exception as e:
        st.warning(f"La guía se guardó pero no se pudo subir la imagen: {e}")
        return ""


_ESTADO_ICON = {
    "Preparado":           "📄",
    "Enviado a Planta":    "🚚",
    "Embarcado sin guía":  "📦",
    "Guía capturada":      "✅",
    "Entregado a fletera": "🤝",
    "Cerrado":             "🔒",
    "Cancelado":           "❌",
}

# ──────────────────────────────────────────────────────────────────────────────
# Encabezado
# ──────────────────────────────────────────────────────────────────────────────

st.markdown("## 🧾 Captura de Guías de Embarque")
st.caption("Registra el número de guía y los datos de entrega a la fletera.")
st.divider()

# ──────────────────────────────────────────────────────────────────────────────
# Formulario de captura (si hay embarque seleccionado)
# ──────────────────────────────────────────────────────────────────────────────

emb_id = st.session_state["embarque_seleccionado"]

if emb_id:
    emb = get_embarque_por_id(emb_id)

    if not emb:
        st.error("No se encontró el embarque seleccionado.")
        st.session_state["embarque_seleccionado"] = None
        st.rerun()

    guias_previas = emb.get("guias", [])
    n_guias       = len(guias_previas)
    estado_emb    = emb.get("estado_embarque", "Preparado")
    icon_emb      = _ESTADO_ICON.get(estado_emb, "📦")
    es_domicilio  = emb.get("tipo_entrega", "") == "Domicilio del cliente"

    # ── Resumen del embarque ──────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown(f"#### {icon_emb} Embarque seleccionado")
        sal = emb.get("salidas", [{}])[0] if emb.get("salidas") else {}
        rc1, rc2, rc3, rc4 = st.columns(4)
        rc1.markdown(f"**Folio Bind:** {sal.get('folio_bind', '—')}")
        rc1.markdown(f"**Cliente:** {sal.get('cliente', '—')}")
        rc2.markdown(f"**Fletera:** {emb.get('fletera', '—')}")
        rc2.markdown(f"**Tipo:** {emb.get('tipo_entrega', '—')}")
        rc3.markdown(f"**Destino:** {emb.get('destinatario_nombre', '—')}")
        rc3.markdown(f"**Estado:** {icon_emb} {estado_emb}")
        rc4.markdown(f"**Guías previas:** {n_guias}")
        if guias_previas:
            for g in guias_previas:
                rc4.caption(f"• {g.get('numero_guia','—')} ({g.get('fecha_embarque_real','—')})")

        if n_guias > 0:
            st.info(
                f"Este embarque ya tiene {n_guias} guía(s) registrada(s). "
                "Puedes registrar una adicional si aplica."
            )

    st.markdown("---")

    # ── Evidencia + OCR (fuera del form para reaccionar al upload) ────────────
    st.markdown("#### Evidencia")
    archivo_ev = st.file_uploader(
        "Foto de la guía de embarque — opcional pero recomendado",
        type=["jpg", "jpeg", "png", "heic"],
        key=f"ev_{emb_id}",
        help=(
            "Sube la foto que el chofer mandó por WhatsApp. "
            "El sistema intentará detectar el número de guía automáticamente."
        ),
    )

    if archivo_ev:
        with st.spinner("Analizando imagen..."):
            candidatos = extraer_candidatos_guia(archivo_ev.getvalue())

        if candidatos is None:
            st.caption("OCR no disponible en este equipo — captura el número manualmente.")
        elif candidatos:
            st.caption("Número(s) detectado(s) — haz clic para usar:")
            btn_cols = st.columns(min(len(candidatos[:4]), 4))
            for i, cand in enumerate(candidatos[:4]):
                if btn_cols[i].button(f"✓  {cand}", key=f"ocr_{emb_id}_{cand}"):
                    st.session_state["_ocr_guia"]     = cand
                    st.session_state["_ocr_guia_emb"] = emb_id
                    st.rerun()
        else:
            st.caption(
                "No se detectó número legible en la imagen. "
                "Captúralo manualmente en el campo de abajo."
            )

    # Valor pre-llenado desde OCR (sólo si corresponde a este embarque)
    _ocr_val = ""
    if st.session_state.get("_ocr_guia_emb") == emb_id:
        _ocr_val = st.session_state.get("_ocr_guia", "")

    st.markdown("---")

    # ── Formulario de guía ────────────────────────────────────────────────────
    st.markdown("#### Datos de la entrega")

    if es_domicilio:
        st.info("🚗 Entrega a domicilio con vehículo propio — el número de guía es opcional.")

    with st.form("form_guia", clear_on_submit=False):
        fg1, fg2 = st.columns(2)
        with fg1:
            numero_guia = st.text_input(
                "Referencia de entrega" if es_domicilio else "Número de guía *",
                value=_ocr_val,
                placeholder="Ej. DOM-2026-001 (opcional)" if es_domicilio else "Ej. TG-20260625-001",
                key="inp_num_guia",
                help="Referencia interna opcional para la entrega." if es_domicilio
                     else "Número de guía o tracking asignado por la fletera al recoger el embarque.",
            )
            fletera_guia = st.text_input(
                "Transportista",
                value="Vehículo propio NSG" if es_domicilio else emb.get("fletera", ""),
                key="inp_fletera_guia",
                help="Vehículo o empresa que realizó la entrega.",
            )
            quien_entrego = st.text_input(
                "Quién realizó la entrega *",
                placeholder="Nombre del responsable en NSG",
                key="inp_quien",
                help="Nombre del empleado de NSG que realizó la entrega.",
            )
        with fg2:
            fecha_real = st.date_input(
                "Fecha real de embarque *",
                value=date.today(),
                key="inp_fecha_real",
                help="Fecha en que la fletera recogió el embarque (puede diferir de la fecha de generación del PDF).",
            )
            hora_emb = st.time_input(
                "Hora de entrega a fletera",
                value=time(hour=datetime.now().hour, minute=0),
                step=300,
                key="inp_hora",
                help="Hora aproximada de recolección. Útil para rastreo y aclaraciones.",
            )

        obs_guia = st.text_area(
            "Observaciones de entrega",
            placeholder="Sin novedad / incidencias / datos de recolección...",
            height=70,
            key="inp_obs_guia",
            help="Cualquier incidencia al momento de entrega: piezas faltantes, daños visibles, acuerdos especiales, etc.",
        )

        col_save, col_cancel = st.columns([1, 4])
        submitted = col_save.form_submit_button("💾 Guardar guía", type="primary")
        cancelled = col_cancel.form_submit_button("✖ Cancelar")

    if cancelled:
        st.session_state["embarque_seleccionado"] = None
        st.session_state.pop("_ocr_guia", None)
        st.session_state.pop("_ocr_guia_emb", None)
        st.rerun()

    if submitted:
        if not es_domicilio and not numero_guia.strip():
            st.error("El número de guía es obligatorio para entregas con fletera.")
        elif not quien_entrego.strip():
            st.error("Indica quién realizó la entrega.")
        else:
            ruta_ev = ""
            if archivo_ev:
                ruta_ev = _guardar_evidencia(archivo_ev, emb_id)

            guardar_guia(emb_id, {
                "numero_guia":         numero_guia.strip(),
                "fletera":             fletera_guia.strip(),
                "fecha_embarque_real": str(fecha_real),
                "hora_embarque":       hora_emb.strftime("%H:%M"),
                "quien_entrego":       quien_entrego.strip(),
                "ruta_evidencia":      ruta_ev,
                "observaciones":       obs_guia.strip(),
            })

            st.session_state["embarque_seleccionado"] = None
            st.session_state["guia_guardada"]         = True
            st.session_state.pop("_ocr_guia", None)
            st.session_state.pop("_ocr_guia_emb", None)
            st.rerun()

    st.divider()

# ── Mensaje de éxito post-rerun ───────────────────────────────────────────────
if st.session_state.get("guia_guardada"):
    st.success("✅ Guía guardada correctamente. La lista se actualizó.")
    st.page_link("pages/2_Historial.py", label="→ Ver en Historial", icon="📋")
    st.session_state["guia_guardada"] = False

# ──────────────────────────────────────────────────────────────────────────────
# Búsqueda de embarques
# ──────────────────────────────────────────────────────────────────────────────

st.markdown("### Embarques")

with st.expander("🔍 Filtros", expanded=True):
    bf1, bf2, bf3, bf4, bf5 = st.columns([2, 2, 2, 2, 2])
    filtro_folio    = bf1.text_input("Folio Bind",   placeholder="Ej. AFAD5267")
    filtro_cliente  = bf2.text_input("Cliente",       placeholder="Nombre parcial")
    filtro_fletera  = bf3.text_input("Fletera",       placeholder="Tres Guerras, DHL…")
    filtro_desde    = bf4.date_input("Fecha desde",   value=None)
    filtro_hasta    = bf5.date_input("Fecha hasta",   value=None)

    solo_pendientes = st.checkbox(
        "Mostrar solo embarques sin guía capturada",
        value=True,
        key="chk_pendientes",
        help="Filtra para ver únicamente los embarques que aún no tienen número de guía registrado.",
    )

desde_str = str(filtro_desde) if filtro_desde else ""
hasta_str = str(filtro_hasta) if filtro_hasta else ""

embarques = get_embarques_filtrados(
    folio=filtro_folio,
    cliente=filtro_cliente,
    fecha_desde=desde_str,
    fecha_hasta=hasta_str,
    pendiente_guia=solo_pendientes,
)

# Filtro local por fletera (no está en la query de DB)
if filtro_fletera.strip():
    term = filtro_fletera.strip().lower()
    embarques = [e for e in embarques
                 if term in (e.get("fletera") or "").lower()]

if not embarques:
    st.info(
        "No hay embarques que coincidan con los filtros."
        + (" Desmarca «Solo pendientes» para ver todos." if solo_pendientes else "")
    )
    st.stop()

st.markdown(f"**{len(embarques)} embarque(s) encontrado(s)**")
st.markdown("")

# ──────────────────────────────────────────────────────────────────────────────
# Lista de embarques
# ──────────────────────────────────────────────────────────────────────────────

# Cabecera de columnas
hdr = st.columns([2, 2, 2, 2, 2, 1, 1])
for col, lbl in zip(hdr, ["Folio(s)", "Cliente(s)", "Fletera",
                           "Destino", "Estado", "Guías", ""]):
    col.markdown(f"**{lbl}**")

st.markdown("<hr style='margin:4px 0'>", unsafe_allow_html=True)

for emb in embarques:
    estado_e = emb.get("estado_embarque", "Preparado")
    icon_e   = _ESTADO_ICON.get(estado_e, "📦")
    n_g      = int(emb.get("num_guias", 0) or 0)
    es_sel   = (st.session_state["embarque_seleccionado"] == emb["id"])

    row = st.columns([2, 2, 2, 2, 2, 1, 1])
    row[0].markdown(emb.get("folios_bind") or "—")
    row[1].markdown((emb.get("clientes") or "—")[:40])
    row[2].markdown(emb.get("fletera") or "—")
    row[3].markdown((emb.get("destinatario_nombre") or "—")[:35])
    row[4].markdown(f"{icon_e} {estado_e}")
    row[5].markdown(f"{'✅' if n_g > 0 else '—'} {n_g}")

    btn_lbl = "✏ Editar" if n_g > 0 else "📝 Capturar"
    if es_sel:
        row[6].markdown("**↑ activo**")
    else:
        if row[6].button(btn_lbl, key=f"sel_{emb['id']}"):
            st.session_state["embarque_seleccionado"] = emb["id"]
            st.rerun()

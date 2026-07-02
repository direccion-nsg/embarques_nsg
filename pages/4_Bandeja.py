"""
Bandeja de Embarques — gestión de múltiples embarques en sesión.

Desde aquí el usuario puede:
  - Ver todos los embarques preparados en la sesión actual
  - Seleccionar uno o varios y enviarlos a Planta (notificación automática a almacén)
  - Quitar embarques seleccionados o vaciar la bandeja
"""

import os
import sys
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import APP_NAME, VERSION, ensure_dirs
from modules.database import (
    init_database,
    get_bandeja as db_get_bandeja,
    quitar_de_bandeja as db_quitar_bandeja,
    vaciar_bandeja as db_vaciar_bandeja,
    actualizar_estado_embarque,
    cancelar_embarque,
)
from modules.sidebar import render_sidebar
from modules.auth import require_auth
from modules.storage import descargar_pdf_bytes
from modules.messaging import enviar_email_planta

# ──────────────────────────────────────────────────────────────────────────────
# Configuración
# ──────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title=f"Bandeja — {APP_NAME}",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)
ensure_dirs()
init_database()
require_auth("bandeja")
render_sidebar(APP_NAME, VERSION)

if st.session_state.get("_current_page") != "bandeja":
    for _k in list(st.session_state.keys()):
        if _k.startswith("_confirmar_cancel_bnd_"):
            del st.session_state[_k]
    st.session_state.pop("_confirm_vaciar", None)
st.session_state["_current_page"] = "bandeja"

# ──────────────────────────────────────────────────────────────────────────────
# Encabezado
# ──────────────────────────────────────────────────────────────────────────────

st.markdown("## 📦 Bandeja de Embarques")
st.caption("Embarques preparados en esta sesión — listos para enviar a Almacén Teoloyucan.")
st.divider()

if "_flash_planta" in st.session_state:
    _fl = st.session_state.pop("_flash_planta")
    st.success(f"✅ {_fl['n']} embarque(s) marcados como **Enviado a Planta**.")
    if _fl["ok_mail"]:
        st.info("📧 Notificación enviada a almacén.")
    else:
        st.warning(f"Embarques actualizados, pero no se pudo enviar el email: {_fl['err']}")

# Siempre cargar desde DB para reflejar cambios de otras páginas
st.session_state["bandeja"] = db_get_bandeja()
bandeja: list = st.session_state["bandeja"]

if not bandeja:
    st.info("La bandeja está vacía. Genera embarques desde **Nuevo Embarque** y agrégalos aquí.")
    st.page_link("app.py", label="➕ Ir a Nuevo Embarque")
    st.stop()

# ──────────────────────────────────────────────────────────────────────────────
# Tabla de embarques con selección
# ──────────────────────────────────────────────────────────────────────────────

st.markdown(f"**{len(bandeja)} embarque(s) en bandeja**")

# Procesar "seleccionar todos" ANTES de crear los checkboxes
if st.session_state.pop("_select_all_pending", False):
    for i in range(len(bandeja)):
        st.session_state[f"sel_{i}"] = True

# Encabezado de la tabla
hdr = st.columns([0.4, 1.2, 2, 2, 1.5, 1.2, 1.2, 1, 1])
for col, lbl in zip(hdr, ["","Folio","Cliente","Destinatario","Fletera",
                            "Tipo","Flete","Remisión","PDF"]):
    col.markdown(f"**{lbl}**")

seleccionados = []

for idx, item in enumerate(bandeja):
    cols = st.columns([0.4, 1.2, 2, 2, 1.5, 1.2, 1.2, 1, 1])
    sel = cols[0].checkbox("", key=f"sel_{idx}", label_visibility="collapsed")
    if sel:
        seleccionados.append(idx)

    cols[1].write(item.get("folio_bind","—"))
    cols[2].write(item.get("cliente","—"))
    cols[3].write(item.get("destinatario_nombre","—"))
    cols[4].write(item.get("fletera","—"))
    cols[5].write(item.get("tipo_entrega","—"))
    cols[6].write(item.get("condicion_flete","—"))

    # Indicador de remisión
    if item.get("con_remision"):
        cols[7].markdown("✅ Sí")
    else:
        cols[7].markdown("—")

    # Indicador de PDF disponible
    ruta = item.get("ruta_pdf_generado","")
    if ruta:
        cols[8].markdown("✅")
    else:
        cols[8].markdown("⚠")

st.divider()

# ──────────────────────────────────────────────────────────────────────────────
# Selección y acciones
# ──────────────────────────────────────────────────────────────────────────────

items_sel = [bandeja[i] for i in seleccionados]
n_sel     = len(items_sel)

col_info, col_todo = st.columns([3, 1])
with col_info:
    if n_sel:
        st.success(f"**{n_sel} embarque(s) seleccionado(s)**")
    else:
        st.caption("Marca la casilla de uno o varios embarques para habilitar las acciones.")

with col_todo:
    if st.button("Seleccionar todos", key="btn_sel_all"):
        st.session_state["_select_all_pending"] = True
        st.rerun()

st.markdown("#### Enviar a Planta")

if st.button("🏭 Enviar a Planta",
             disabled=(n_sel == 0),
             type="primary",
             help="Marca los embarques seleccionados como 'Enviado a Planta' y envía notificación automática a almacén.",
             key="btn_enviar_planta"):
    enviados = 0
    for item in items_sel:
        try:
            actualizar_estado_embarque(item["embarque_id"], "Enviado a Planta")
            enviados += 1
        except Exception as ex:
            st.error(f"Error en {item.get('folio_bind','?')}: {ex}")
    if enviados:
        nombre_user  = st.session_state.get("_auth_user", {}).get("nombre", "")
        ok_mail, err = enviar_email_planta(items_sel, "", nombre_user)
        st.session_state["_flash_planta"] = {"n": enviados, "ok_mail": ok_mail, "err": err}
        st.session_state["bandeja"] = db_get_bandeja()
        st.rerun()
    else:
        st.error("No se pudo actualizar el estado.")

st.divider()

# ──────────────────────────────────────────────────────────────────────────────
# Detalle expandible por embarque
# ──────────────────────────────────────────────────────────────────────────────

st.markdown("#### Detalle de embarques")

for idx, item in enumerate(bandeja):
    remision_badge = " 📄 Con remisión" if item.get("con_remision") else ""
    with st.expander(
        f"**{item.get('folio_bind','—')}** | {item.get('cliente','—')} "
        f"→ {item.get('destinatario_nombre','—')} | {item.get('fletera','—')}{remision_badge}",
        expanded=False,
    ):
        dc1, dc2 = st.columns(2)
        with dc1:
            st.markdown(f"**Folio Bind:** {item.get('folio_bind','—')}")
            st.markdown(f"**Cliente:** {item.get('cliente','—')}")
            st.markdown(f"**Destinatario:** {item.get('destinatario_nombre','—')}")
            st.markdown(f"**Fletera:** {item.get('fletera','—')}")
            if item.get("pedido_interno"):
                st.markdown(f"**Pedido interno Planta:** {item.get('pedido_interno')}")
        with dc2:
            st.markdown(f"**Tipo de entrega:** {item.get('tipo_entrega','—')}")
            st.markdown(f"**Condición flete:** {item.get('condicion_flete','—')}")
            if item.get("con_remision"):
                st.markdown(f"**Empresa remisión:** {item.get('empresa_remision','—')}")
                st.markdown(f"**No. remisión:** {item.get('numero_remision','—')}")

        if item.get("observaciones"):
            st.markdown(f"**Observaciones:** {item.get('observaciones','')}")

        ruta = item.get("ruta_pdf_generado","")
        btn_col1, btn_col2, btn_col3, btn_col4 = st.columns([1, 1, 1, 3])
        if ruta:
            with btn_col1:
                try:
                    from modules.storage import descargar_pdf_bytes
                    pdf_dl = descargar_pdf_bytes(ruta)
                    st.download_button(
                        "⬇ Descargar",
                        data=pdf_dl,
                        file_name=ruta.split("/")[-1],
                        mime="application/pdf",
                        key=f"dl_item_{idx}",
                    )
                except Exception:
                    st.caption("PDF no disponible")
        else:
            st.caption("⚠ PDF no disponible en la ruta original.")

        with btn_col2:
            if st.button("🗑 Quitar de bandeja", key=f"rm_{idx}"):
                db_quitar_bandeja(item.get("embarque_id"))
                st.session_state["bandeja"] = db_get_bandeja()
                st.session_state.pop("ruta_pdf_multi", None)
                st.rerun()

        with btn_col3:
            if st.button("❌ Cancelar embarque", key=f"cancel_bnd_{idx}"):
                st.session_state[f"_confirmar_cancel_bnd_{idx}"] = True

        if st.session_state.get(f"_confirmar_cancel_bnd_{idx}"):
            st.error(
                f"⚠️ ¿Cancelar definitivamente el embarque **{item.get('folio_bind','?')}**?\n\n"
                "Esta acción no se puede deshacer."
            )
            cc1, cc2 = st.columns(2)
            if cc1.button("❌ Sí, cancelar", key=f"conf_cancel_bnd_si_{idx}",
                          use_container_width=True):
                try:
                    cancelar_embarque(item.get("embarque_id"))
                    st.session_state.pop(f"_confirmar_cancel_bnd_{idx}", None)
                    st.session_state["bandeja"] = db_get_bandeja()
                    st.rerun()
                except Exception as ex:
                    st.error(f"Error: {ex}")
            if cc2.button("No, mantener", key=f"conf_cancel_bnd_no_{idx}",
                          use_container_width=True):
                st.session_state.pop(f"_confirmar_cancel_bnd_{idx}", None)
                st.rerun()

st.divider()

# ──────────────────────────────────────────────────────────────────────────────
# Acciones globales de bandeja
# ──────────────────────────────────────────────────────────────────────────────

col_vac1, col_vac2 = st.columns([1, 5])
with col_vac1:
    if st.button("🗑 Vaciar bandeja", key="btn_vaciar"):
        st.session_state["_confirm_vaciar"] = True
with col_vac2:
    st.caption("Vaciar quita todos los embarques de la bandeja de esta sesión. "
               "Los PDFs y el historial permanecen disponibles en la sección Historial.")

if st.session_state.get("_confirm_vaciar"):
    st.warning("¿Vaciar toda la bandeja? Los embarques no se eliminarán del historial, solo saldrán de esta vista.")
    _cv1, _cv2 = st.columns(2)
    if _cv1.button("Sí, vaciar", key="conf_vaciar_si", type="primary", use_container_width=True):
        db_vaciar_bandeja()
        st.session_state["bandeja"] = []
        for _k in ["ruta_pdf_multi", "mostrar_teams_msg", "_confirm_vaciar"]:
            st.session_state.pop(_k, None)
        st.rerun()
    if _cv2.button("Cancelar", key="conf_vaciar_no", use_container_width=True):
        st.session_state.pop("_confirm_vaciar", None)
        st.rerun()

"""
Bandeja de Embarques — gestión de múltiples embarques en sesión.

Desde aquí el usuario puede:
  - Ver todos los embarques preparados en la sesión actual
  - Seleccionar uno o varios
  - Generar PDF combinado de los seleccionados
  - Abrir carpeta con todos los archivos
  - Preparar correo (abre Outlook + carpeta para adjuntar manualmente)
  - Copiar mensaje para Teams
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
from modules.pdf_merger import combinar_multiples_embarques
from modules.storage import subir_pdf_combinado, generar_url_firmada
from modules.messaging import (
    construir_mensaje_teams_multiple,
    abrir_mailto_multiple,
)

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

# ──────────────────────────────────────────────────────────────────────────────
# Encabezado
# ──────────────────────────────────────────────────────────────────────────────

st.markdown("## 📦 Bandeja de Embarques")
st.caption("Embarques preparados en esta sesión — listos para enviar a Almacén Teoloyucan.")
st.divider()

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

st.markdown("#### Acciones sobre los seleccionados")

items_target = items_sel if items_sel else bandeja  # si nada seleccionado, aplica a todos

ac1, ac2, ac3, ac4 = st.columns(4)

# ── PDF Combinado ──────────────────────────────────────────────────────────────
with ac1:
    if st.button("📄 Generar PDF combinado",
                 disabled=(n_sel == 0),
                 help="Une los paquetes de los embarques seleccionados en un solo PDF.",
                 key="btn_pdf_multi"):
        with st.spinner("Combinando PDFs..."):
            try:
                bytes_multi = combinar_multiples_embarques(items_sel)
                st.session_state["bytes_pdf_multi"] = bytes_multi
                st.success(f"✅ PDF combinado ({len(bytes_multi)//1024} KB)")
            except Exception as ex:
                st.error(f"Error: {ex}")

# ── Correo ────────────────────────────────────────────────────────────────────
with ac2:
    if st.button("✉ Preparar correo",
                 disabled=(n_sel == 0),
                 help="Combina los PDFs, sube a Storage y abre Outlook con link de descarga.",
                 key="btn_mail_multi"):
        with st.spinner("Preparando PDF y generando link..."):
            try:
                from datetime import datetime as _dt
                bytes_correo = st.session_state.get("bytes_pdf_multi") or combinar_multiples_embarques(items_sel)
                fname_correo = f"BANDEJA_{_dt.now().strftime('%Y%m%d_%H%M%S')}.pdf"
                ruta_correo  = subir_pdf_combinado(bytes_correo, fname_correo)
                url_correo   = generar_url_firmada(ruta_correo)
                st.session_state["bytes_pdf_multi"]    = bytes_correo
                st.session_state["url_pdf_multi"]      = url_correo
                abrir_mailto_multiple(items_sel, url_correo)
                st.success("✉ Outlook abierto — el link del PDF está en el cuerpo del correo.")
            except Exception as ex:
                st.error(f"Error: {ex}")

# ── Enviar a Planta ───────────────────────────────────────────────────────────
with ac3:
    if st.button("🏭 Enviar a Planta",
                 disabled=(n_sel == 0),
                 type="primary",
                 help="Marca los embarques seleccionados como 'Enviado a Planta' para que Administración los vea.",
                 key="btn_enviar_planta"):
        enviados = 0
        for item in items_sel:
            try:
                actualizar_estado_embarque(item["embarque_id"], "Enviado a Planta")
                enviados += 1
            except Exception as ex:
                st.error(f"Error en {item.get('folio_bind','?')}: {ex}")
        if enviados:
            st.success(f"✅ {enviados} embarque(s) marcados como **Enviado a Planta**.")
            st.session_state["bandeja"] = db_get_bandeja()
            st.rerun()
        else:
            st.error("No se pudo actualizar el estado.")

# ── Mensaje Teams ─────────────────────────────────────────────────────────────
with ac4:
    if st.button("📋 Copiar mensaje Teams",
                 disabled=(n_sel == 0),
                 key="btn_teams_multi"):
        st.session_state["mostrar_teams_msg"] = True

if st.session_state.get("mostrar_teams_msg") and items_sel:
    url_teams = st.session_state.get("url_pdf_multi", "")
    if not url_teams:
        st.info("Primero usa '✉ Preparar correo' para generar el link del PDF.")
        url_teams = ""
    msg = construir_mensaje_teams_multiple(items_sel, url_teams)
    st.text_area("Mensaje para Teams (selecciona y copia con Ctrl+A, Ctrl+C):",
                 value=msg, height=160, key="teams_multi_txt")
    if st.button("Ocultar", key="btn_hide_teams"):
        st.session_state["mostrar_teams_msg"] = False
        st.rerun()

# ── Descarga del PDF combinado si ya se generó ────────────────────────────────
bytes_multi = st.session_state.get("bytes_pdf_multi")
if bytes_multi:
    from datetime import datetime as _dt
    fname_multi = f"BANDEJA_{_dt.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    st.markdown("---")
    st.download_button(
        "⬇ Descargar PDF combinado",
        data=bytes_multi,
        file_name=fname_multi,
        mime="application/pdf",
        key="btn_dl_multi",
    )

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
        db_vaciar_bandeja()
        st.session_state["bandeja"] = []
        for k in ["ruta_pdf_multi", "mostrar_teams_msg"]:
            st.session_state.pop(k, None)
        st.rerun()
with col_vac2:
    st.caption("Vaciar elimina todos los embarques de la bandeja de esta sesión. "
               "Los PDFs generados permanecen en la carpeta /data/salida/.")

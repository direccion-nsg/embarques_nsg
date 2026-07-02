"""
Vista de Embarques para Administración de Planta.

Muestra únicamente los embarques en estado 'Enviado a Planta'.
Permite:
  - Descargar el PDF del paquete
  - Marcar como 'Embarcado sin guía' cuando el camión sale de planta
"""

import base64
import os
import sys
import streamlit as st
import streamlit.components.v1 as components

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import APP_NAME, VERSION
from modules.database import (
    init_database, get_embarques_filtrados,
    actualizar_estado_embarque, regresar_embarque_a_bandeja, cancelar_embarque,
)
from modules.storage import descargar_pdf_bytes
from modules.sidebar import render_sidebar
from modules.auth import require_auth

# ──────────────────────────────────────────────────────────────────────────────
# Configuración
# ──────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title=f"Embarques Planta — {APP_NAME}",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_database()
require_auth("planta")
render_sidebar(APP_NAME, VERSION)

if st.session_state.get("_current_page") != "planta":
    for _k in list(st.session_state.keys()):
        if _k.startswith(("_confirmar_emb_", "_confirmar_regreso_", "_confirmar_cancel_planta_")):
            del st.session_state[_k]
st.session_state["_current_page"] = "planta"

# ──────────────────────────────────────────────────────────────────────────────
# Encabezado
# ──────────────────────────────────────────────────────────────────────────────

st.markdown("## 🏭 Embarques pendientes de despacho")
st.caption("Aquí aparecen los embarques que Finanzas ha enviado a Planta para su preparación y despacho.")

if st.button("🔄 Actualizar", key="btn_refresh"):
    st.rerun()

st.divider()

# ──────────────────────────────────────────────────────────────────────────────
# Cargar embarques en estado "Enviado a Planta"
# ──────────────────────────────────────────────────────────────────────────────

embarques = get_embarques_filtrados(estado_embarque="Enviado a Planta")

if not embarques:
    st.info("✅ No hay embarques pendientes en este momento.")
    st.markdown(
        "Cuando Finanzas envíe embarques a Planta desde la **Bandeja**, aparecerán aquí. "
        "Mientras tanto puedes revisar el historial completo."
    )
    st.page_link("pages/2_Historial.py", label="📋 Ver Historial")
    st.stop()

st.markdown(f"**{len(embarques)} embarque(s) pendiente(s) de despacho:**")

with st.container(border=True):
    st.markdown("**¿Qué hago aquí?**")
    st.markdown(
        "**1.** Descarga e imprime el PDF de cada embarque  \n"
        "*(Solo la hoja logística — entrega la hoja de salida Bind únicamente si la fletera la solicita)*\n\n"
        "**2.** Almacén prepara la mercancía según la hoja logística\n\n"
        "**3.** Cuando la camioneta salga de planta, haz clic en **🚛 Marcar como Embarcado** "
        "en los embarques que salieron  \n"
        "*(Si un embarque **no salió**, no lo marques — quedará pendiente para el siguiente despacho)*"
    )

st.divider()

# ──────────────────────────────────────────────────────────────────────────────
# Tarjeta por embarque
# ──────────────────────────────────────────────────────────────────────────────

for emb in embarques:
    folio          = emb.get("folios_bind") or emb.get("folio_bind", "—")
    cliente        = emb.get("clientes")   or emb.get("cliente", "—")
    destinatario   = emb.get("destinatario_nombre", "—")
    fletera        = emb.get("fletera", "—")
    tipo           = emb.get("tipo_entrega", "—")
    condicion      = emb.get("condicion_flete", "—")
    con_rem        = emb.get("con_remision", False)
    pedido_interno = emb.get("pedido_interno", "")
    emb_id         = emb["id"]
    ruta_pdf       = emb.get("ruta_pdf_generado", "")

    with st.container(border=True):
        col_info, col_acciones = st.columns([3, 1])

        with col_info:
            titulo = f"### 📦 {folio} — {cliente}"
            if pedido_interno:
                titulo += f"  |  🔖 Pedido interno: `{pedido_interno}`"
            st.markdown(titulo)
            c1, c2, c3 = st.columns(3)
            c1.markdown(f"**Destinatario:** {destinatario}")
            c2.markdown(f"**Fletera:** {fletera}")
            c3.markdown(f"**Tipo de entrega:** {tipo}")

            c4, c5, c6 = st.columns(3)
            c4.markdown(f"**Condición flete:** {condicion}")
            if con_rem:
                c5.markdown(f"**Remisión:** {emb.get('empresa_remision','—')} — {emb.get('numero_remision','—')}")
                c6.markdown(f"**Estado remisión:** {emb.get('estado_remision','—')}")

            obs = emb.get("observaciones", "")
            if obs:
                st.caption(f"📝 {obs}")

        with col_acciones:
            # ── Descargar / Imprimir PDF ──────────────────────────────────────
            _impreso_key = f"_impreso_{emb_id}"
            ya_impreso = st.session_state.get(_impreso_key, False)

            if ruta_pdf:
                try:
                    pdf_bytes = descargar_pdf_bytes(ruta_pdf)
                    st.download_button(
                        "⬇ Descargar PDF",
                        data=pdf_bytes,
                        file_name=f"EMBARQUE_{folio}.pdf",
                        mime="application/pdf",
                        key=f"dl_planta_{emb_id}",
                        use_container_width=True,
                    )
                    # Abrir en nueva pestaña para imprimir — Blob URL (compatible con Edge)
                    pdf_b64 = base64.b64encode(pdf_bytes).decode()
                    _link_label = "🔄 Reimprimir" if ya_impreso else "🖨️ Abrir para imprimir"
                    _link_color = "#2e7d32" if ya_impreso else "#333"
                    components.html(
                        f"""<style>
                        a{{display:block;text-align:center;padding:5px;border:1px solid #ccc;
                           border-radius:4px;margin-top:4px;text-decoration:none;
                           color:{_link_color};font-weight:{"bold" if ya_impreso else "normal"};
                           font-size:13px;font-family:sans-serif;background:white}}
                        a:hover{{background:#f5f5f5}}
                        </style>
                        <a id="pl" href="#" target="_blank">{_link_label}</a>
                        <script>(function(){{
                            var b=atob("{pdf_b64}"),n=new Uint8Array(b.length);
                            for(var i=0;i<b.length;i++)n[i]=b.charCodeAt(i);
                            document.getElementById("pl").href=URL.createObjectURL(
                                new Blob([n],{{type:"application/pdf"}}));
                        }})();</script>""",
                        height=40,
                    )
                    # Estado de impresión
                    if ya_impreso:
                        _ci, _cr = st.columns([3, 1])
                        _ci.caption("✅ Ya impreso")
                        if _cr.button("↩", key=f"reset_imp_{emb_id}",
                                      help="Desmarcar como impreso"):
                            st.session_state[_impreso_key] = False
                            st.rerun()
                    else:
                        if st.button("✅ Marcar impreso", key=f"marcar_imp_{emb_id}",
                                     use_container_width=True):
                            st.session_state[_impreso_key] = True
                            st.rerun()
                except Exception:
                    st.warning("PDF no disponible")
            else:
                st.warning("Sin PDF")

            st.markdown("<br>", unsafe_allow_html=True)

            # ── Marcar como embarcado ─────────────────────────────────────────
            if st.button(
                "🚛 Marcar como Embarcado",
                key=f"emb_{emb_id}",
                type="primary",
                use_container_width=True,
                help="Confirma que el camión salió de planta con esta mercancía.",
            ):
                st.session_state[f"_confirmar_emb_{emb_id}"] = True

            st.markdown("<br>", unsafe_allow_html=True)

            # ── Regresar a Bandeja ────────────────────────────────────────────
            if st.button(
                "↩ Regresar a Bandeja",
                key=f"regreso_{emb_id}",
                use_container_width=True,
                help="El embarque no pudo salir. Lo regresa a la Bandeja de Finanzas para reprogramar.",
            ):
                st.session_state[f"_confirmar_regreso_{emb_id}"] = True

            # ── Cancelar embarque ─────────────────────────────────────────────
            if st.button(
                "❌ Cancelar embarque",
                key=f"cancel_planta_{emb_id}",
                use_container_width=True,
                help="Cancela definitivamente este embarque.",
            ):
                st.session_state[f"_confirmar_cancel_planta_{emb_id}"] = True

        # ── Confirmaciones ────────────────────────────────────────────────────
        if st.session_state.get(f"_confirmar_emb_{emb_id}"):
            st.warning(
                f"¿Confirmas que el embarque **{folio}** ya salió de planta?\n\n"
                "Esto cambiará el estado a **Embarcado sin guía**."
            )
            bc1, bc2 = st.columns(2)
            if bc1.button("✅ Sí, ya salió", key=f"conf_si_{emb_id}", type="primary",
                          use_container_width=True):
                try:
                    actualizar_estado_embarque(emb_id, "Embarcado sin guía")
                    st.session_state.pop(f"_confirmar_emb_{emb_id}", None)
                    st.success(f"✅ Embarque **{folio}** marcado como **Embarcado sin guía**.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")
            if bc2.button("Cancelar", key=f"conf_no_{emb_id}", use_container_width=True):
                st.session_state.pop(f"_confirmar_emb_{emb_id}", None)
                st.rerun()

        if st.session_state.get(f"_confirmar_regreso_{emb_id}"):
            st.warning(
                f"¿Regresar el embarque **{folio}** a la Bandeja de Finanzas?\n\n"
                "El estado volverá a **Preparado** y Finanzas lo verá en su bandeja."
            )
            br1, br2 = st.columns(2)
            if br1.button("↩ Sí, regresar", key=f"conf_reg_si_{emb_id}", type="primary",
                          use_container_width=True):
                try:
                    regresar_embarque_a_bandeja(emb_id)
                    st.session_state.pop(f"_confirmar_regreso_{emb_id}", None)
                    st.success(f"↩ Embarque **{folio}** regresado a la Bandeja.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")
            if br2.button("No, mantener aquí", key=f"conf_reg_no_{emb_id}",
                          use_container_width=True):
                st.session_state.pop(f"_confirmar_regreso_{emb_id}", None)
                st.rerun()

        if st.session_state.get(f"_confirmar_cancel_planta_{emb_id}"):
            st.error(
                f"⚠️ ¿Cancelar definitivamente el embarque **{folio}**?\n\n"
                "Esta acción no se puede deshacer. El embarque quedará como **Cancelado**."
            )
            bx1, bx2 = st.columns(2)
            if bx1.button("❌ Sí, cancelar", key=f"conf_cx_si_{emb_id}",
                          use_container_width=True):
                try:
                    cancelar_embarque(emb_id)
                    st.session_state.pop(f"_confirmar_cancel_planta_{emb_id}", None)
                    st.warning(f"❌ Embarque **{folio}** cancelado.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")
            if bx2.button("No, mantener", key=f"conf_cx_no_{emb_id}",
                          use_container_width=True):
                st.session_state.pop(f"_confirmar_cancel_planta_{emb_id}", None)
                st.rerun()

st.divider()
st.info("📋 Una vez que el chofer entregue la guía de embarque, Finanzas o Ventas la registra en la sección **Guías**.")

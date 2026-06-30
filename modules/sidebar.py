"""Sidebar compartido para todas las páginas."""

import os
import streamlit as st

_LOGO_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "logo.png")


def render_sidebar(app_name: str, version: str):
    from modules.database import count_embarques_sin_guia, count_salidas_activas
    from modules.auth import get_user, logout, cambiar_password, puede, ETIQUETAS_ROL
    from modules.styles import inject_css

    inject_css()

    if "bandeja" not in st.session_state:
        from modules.database import get_bandeja as _db_get_bandeja
        st.session_state["bandeja"] = _db_get_bandeja()

    user = get_user()

    with st.sidebar:

        # ── 1. Logo / Branding ────────────────────────────────────────────────
        if os.path.exists(_LOGO_PATH):
            col_logo, col_txt = st.columns([1, 2], gap="small")
            with col_logo:
                st.image(_LOGO_PATH, width=68)
            with col_txt:
                st.markdown(
                    "<div style='padding-top:10px'>"
                    "<span style='color:#E84040;font-weight:800;font-size:1.3rem;"
                    "letter-spacing:3px;line-height:1'>NSG</span><br>"
                    "<span style='color:#94A3B8;font-size:0.6rem;letter-spacing:1px;"
                    "text-transform:uppercase'>Preparación de Embarques</span>"
                    "</div>",
                    unsafe_allow_html=True,
                )
        else:
            st.markdown(
                "<div class='nsg-brand'>"
                "<div class='nsg-brand-name'>NSG</div>"
                "<div class='nsg-brand-sub'>Preparación de Embarques</div>"
                "</div>",
                unsafe_allow_html=True,
            )

        st.caption(f"v{version}")
        st.divider()

        # ── 2. Bandeja ────────────────────────────────────────────────────────
        n_bandeja = len(st.session_state["bandeja"])
        if n_bandeja > 0:
            st.metric("📦 Bandeja", f"{n_bandeja} embarque{'s' if n_bandeja > 1 else ''}")
            st.page_link("pages/4_Bandeja.py", label="Ver Bandeja →", icon="📦")
        else:
            st.caption("📦 Bandeja vacía")

        # ── 3. Contadores operativos ──────────────────────────────────────────
        try:
            n_sin_guia = count_embarques_sin_guia()
            estados    = count_salidas_activas()
            n_parcial  = estados.get("Parcial", 0)
            n_pend     = estados.get("Pendiente", 0)

            st.divider()
            if n_sin_guia:
                st.markdown(
                    f"<p class='nsg-stat-warn'>⚠ {n_sin_guia} embarque(s) sin guía</p>",
                    unsafe_allow_html=True,
                )
            if n_parcial:
                st.markdown(
                    f"<p class='nsg-stat-err'>🔴 {n_parcial} salida(s) parciales</p>",
                    unsafe_allow_html=True,
                )
            if n_pend:
                st.caption(f"⬜ {n_pend} salida(s) pendientes")
            if not n_sin_guia and not n_parcial and not n_pend:
                st.markdown(
                    "<p class='nsg-stat-ok'>✅ Todo al día</p>",
                    unsafe_allow_html=True,
                )
        except Exception:
            pass

        st.divider()

        # ── 4. Navegación (según rol) ─────────────────────────────────────────
        if puede("nuevo"):
            st.page_link("app.py",               label="Nuevo Embarque")
        if puede("historial"):
            st.page_link("pages/2_Historial.py", label="Historial")
        if puede("catalogo"):
            st.page_link("pages/3_Catalogos.py", label="Catálogos")
        if puede("bandeja"):
            st.page_link("pages/4_Bandeja.py",   label="Bandeja")
        if puede("guias"):
            st.page_link("pages/5_Guias.py",     label="Guías")
        if puede("planta"):
            st.page_link("pages/7_Planta.py",    label="Embarques Planta")
        if puede("usuarios"):
            st.page_link("pages/6_Usuarios.py",  label="Usuarios")

        st.divider()

        # ── 5. Cuenta del usuario (al fondo) ─────────────────────────────────
        if user:
            nombre    = user.get("nombre") or user.get("email", "").split("@")[0]
            rol_label = ETIQUETAS_ROL.get(user.get("role", ""), user.get("role", ""))

            st.markdown(f"**👤 {nombre}**")
            st.markdown(
                f"<span class='nsg-rol-chip'>{rol_label}</span>",
                unsafe_allow_html=True,
            )
            st.write("")

            with st.expander("🔑 Cambiar contraseña"):
                with st.form("form_cambio_pw", clear_on_submit=True):
                    nueva  = st.text_input("Nueva contraseña", type="password",
                                           help="Mínimo 8 caracteres.")
                    nueva2 = st.text_input("Confirmar contraseña", type="password")
                    ok_btn = st.form_submit_button("Guardar", use_container_width=True)
                if ok_btn:
                    if len(nueva) < 8:
                        st.error("Mínimo 8 caracteres.")
                    elif nueva != nueva2:
                        st.error("Las contraseñas no coinciden.")
                    else:
                        exito, msg = cambiar_password(user["id"], nueva)
                        if exito:
                            st.success(msg)
                        else:
                            st.error(msg)

            if st.button("🚪 Cerrar sesión", use_container_width=True):
                logout()
                st.rerun()

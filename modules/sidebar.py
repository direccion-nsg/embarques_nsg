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

        # ── 2. Stepper (solo en Nuevo Embarque) ──────────────────────────────
        if st.session_state.get("_current_page") == "nuevo_embarque":
            _sp = 1
            if st.session_state.get("datos_bind"):
                _sp = 3  # PDF extraído → 1 y 2 completos, 3 activo
            if st.session_state.get("datos_logisticos"):
                _sp = 4  # Logística llena → 1,2,3 completos, 4 activo
            if st.session_state.get("_bytes_paquete"):
                _sp = 5  # Paquete generado → todos completos
            _pasos_lbl = ["Subir PDF", "Revisar datos", "Datos logísticos", "Generar"]
            _lineas = []
            for _pi, _pl in enumerate(_pasos_lbl, start=1):
                if _pi < _sp:
                    _lineas.append(
                        f"<div style='font-size:0.78rem;color:#4ADE80;padding:2px 0'>"
                        f"✔ {_pi} {_pl}</div>"
                    )
                elif _pi == _sp:
                    _lineas.append(
                        f"<div style='font-size:0.78rem;color:#F87171;font-weight:700;"
                        f"padding:2px 0'>▶ {_pi} {_pl}</div>"
                    )
                else:
                    _lineas.append(
                        f"<div style='font-size:0.78rem;color:#475569;padding:2px 0'>"
                        f"&nbsp;&nbsp;{_pi} {_pl}</div>"
                    )
            st.markdown(
                "<div style='margin-bottom:4px;font-size:0.7rem;color:#64748B;"
                "letter-spacing:0.5px;text-transform:uppercase'>Progreso</div>"
                + "".join(_lineas)
                + f"<div style='height:2px;background:linear-gradient(90deg,"
                f"#4ADE80 {(_sp-1)*25}%,#F87171 {(_sp-1)*25}% {_sp*25}%,"
                f"#334155 {_sp*25}%);border-radius:2px;margin-top:6px'></div>",
                unsafe_allow_html=True,
            )
            st.divider()

        # ── 3. Bandeja ────────────────────────────────────────────────────────
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
                st.markdown('<span class="nsg-btn-danger"></span>', unsafe_allow_html=True)
                if st.button(f"● {n_sin_guia} sin guía",
                             key="cnt_sin_guia", use_container_width=True,
                             help=f"{n_sin_guia} embarque(s) embarcados sin guía registrada — clic para ir a Guías"):
                    st.switch_page("pages/5_Guias.py")
            if n_parcial:
                st.markdown('<span class="nsg-btn-warn"></span>', unsafe_allow_html=True)
                if st.button(f"● {n_parcial} salidas parciales",
                             key="cnt_parciales", use_container_width=True,
                             help=f"{n_parcial} salida(s) con entregas incompletas — clic para filtrar en Historial"):
                    st.session_state["_hist_prefiltro_estado"] = "Parcial"
                    st.switch_page("pages/2_Historial.py")
            if n_pend:
                st.markdown('<span class="nsg-btn-info"></span>', unsafe_allow_html=True)
                if st.button(f"● {n_pend} pendientes",
                             key="cnt_pend", use_container_width=True,
                             help=f"{n_pend} salida(s) sin embarques — clic para filtrar en Historial"):
                    st.session_state["_hist_prefiltro_estado"] = "Pendiente"
                    st.switch_page("pages/2_Historial.py")
            if not n_sin_guia and not n_parcial and not n_pend:
                st.markdown(
                    "<p class='nsg-stat-ok'>✅ Todo al día</p>",
                    unsafe_allow_html=True,
                )
        except Exception:
            pass

        st.divider()

        # ── 4. Navegación (según rol) ─────────────────────────────────────────
        _cur = st.session_state.get("_current_page", "")

        def _nav(path, label, page_key, perm_key):
            if not puede(perm_key):
                return
            _lbl = f"● {label}" if _cur == page_key else label
            st.page_link(path, label=_lbl)

        _nav("app.py",               "Nuevo Embarque",   "nuevo_embarque", "nuevo")
        _nav("pages/2_Historial.py", "Historial",        "historial",      "historial")
        _nav("pages/3_Catalogos.py", "Catálogos",        "catalogo",       "catalogo")
        _nav("pages/4_Bandeja.py",   "Bandeja",          "bandeja",        "bandeja")
        _nav("pages/5_Guias.py",     "Guías",            "guias",          "guias")
        _nav("pages/7_Planta.py",    "Embarques Planta", "planta",         "planta")
        _nav("pages/6_Usuarios.py",  "Usuarios",         "usuarios",       "usuarios")

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

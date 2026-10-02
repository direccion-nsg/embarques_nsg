"""
Autenticación de usuarios — Supabase Auth con email + contraseña.

Roles y permisos:
  admin     → todo, incluyendo gestión de usuarios
  finanzas  → nuevo embarque, historial, catálogos, bandeja, guías
  ventas    → historial, guías (lectura)
  almacen   → historial (lectura)
  direccion → historial, bandeja, guías (lectura)
"""

import os
import re
from collections.abc import Mapping
from urllib.parse import urlsplit

import requests
import streamlit as st

# Permisos por rol — cada valor es el conjunto de secciones permitidas
ROLES = {
    "admin":     {"nuevo", "historial", "catalogo", "bandeja", "guias", "usuarios", "planta"},
    "finanzas":  {"nuevo", "historial", "catalogo", "bandeja", "guias"},
    "ventas":    {"historial", "guias"},
    "planta":    {"planta", "historial"},
    "direccion": {"historial", "bandeja", "guias", "planta"},
}

ETIQUETAS_ROL = {
    "admin":     "Administrador",
    "finanzas":  "Finanzas",
    "ventas":    "Ventas",
    "planta":    "Administración Planta",
    "direccion": "Dirección",
}

# Página de inicio por rol (a dónde redirigir si el rol no tiene acceso a la página actual)
LANDING_PAGE = {
    "admin":     "app.py",
    "finanzas":  "app.py",
    "ventas":    "pages/2_Historial.py",
    "planta":    "pages/7_Planta.py",
    "direccion": "pages/2_Historial.py",
}

_SSO_TICKET = re.compile(r"[A-Za-z0-9_-]{43}\Z")
_SSO_ERROR = "No se pudo iniciar sesión desde NSG OPS."


def _sso_config() -> tuple[str, str]:
    """Read optional server-side SSO settings without requiring local secrets."""
    try:
        section = st.secrets.get("nsg_ops", {})
    except Exception:
        section = {}
    if not isinstance(section, Mapping):
        section = {}
    url = section.get("sso_consume_url") or os.environ.get("NSG_OPS_SSO_CONSUME_URL") or ""
    secret = section.get("sso_secret") or os.environ.get("NSG_OPS_EMBARQUES_SSO_SECRET") or ""
    url = url.strip() if isinstance(url, str) else ""
    secret = secret.strip() if isinstance(secret, str) else ""
    return url, secret


def _consume_sso_ticket(ticket: str) -> dict | None:
    """Exchange an opaque ticket on the server and validate the legacy user contract."""
    if not isinstance(ticket, str) or not _SSO_TICKET.fullmatch(ticket):
        return None

    url, secret = _sso_config()
    if not url or not secret:
        return None
    try:
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https" or not parsed.hostname or
            parsed.username or parsed.password or parsed.query or parsed.fragment or
            parsed.path != "/api/sso/consume/EMBARQUES"
        ):
            return None
        response = requests.post(
            url,
            headers={"X-NSG-SSO-Secret": secret},
            json={"ticket": ticket},
            timeout=5,
            allow_redirects=False,
        )
        if response.status_code != 200:
            return None
        identity = response.json()
    except (ValueError, requests.RequestException):
        return None

    if not isinstance(identity, dict):
        return None
    user_id = identity.get("user_id")
    email = identity.get("email")
    name = identity.get("name")
    role = identity.get("module_role")
    if (
        not isinstance(user_id, str) or not user_id.strip() or
        (email is not None and not isinstance(email, str)) or
        not isinstance(name, str) or not name.strip() or
        identity.get("module_code") != "EMBARQUES" or
        not isinstance(role, str) or role not in ROLES
    ):
        return None
    return {"id": user_id, "email": email, "role": role, "nombre": name}


# ──────────────────────────────────────────────────────────────────────────────
# Clientes Supabase
# ──────────────────────────────────────────────────────────────────────────────

def _sb():
    """Cliente fresco con service_role — nunca cacheado para evitar contaminación de sesión."""
    from modules.storage import _client
    return _client()


# ──────────────────────────────────────────────────────────────────────────────
# Sesión en session_state
# ──────────────────────────────────────────────────────────────────────────────

def get_user() -> dict | None:
    """Retorna el dict del usuario autenticado o None."""
    return st.session_state.get("_auth_user")


def is_admin() -> bool:
    u = get_user()
    return u is not None and u.get("role") == "admin"


def puede(permiso: str) -> bool:
    u = get_user()
    if not u:
        return False
    return permiso in ROLES.get(u.get("role", ""), set())


# ──────────────────────────────────────────────────────────────────────────────
# Login / Logout
# ──────────────────────────────────────────────────────────────────────────────

def login(email: str, password: str) -> tuple:
    """Intenta autenticar. Retorna (True, "") o (False, mensaje_error)."""
    try:
        res  = _sb().auth.sign_in_with_password({"email": email, "password": password})
        user = res.user
        meta = user.user_metadata or {}
        st.session_state["_auth_user"] = {
            "id":     user.id,
            "email":  user.email,
            "role":   meta.get("role", "ventas"),
            "nombre": meta.get("nombre", user.email.split("@")[0]),
        }
        return True, ""
    except Exception as e:
        msg = str(e)
        if "Invalid login" in msg or "invalid" in msg.lower():
            return False, "Correo o contraseña incorrectos."
        return False, f"Error de conexión: {msg}"


def logout():
    """Cierra sesión y limpia session_state."""
    source = st.session_state.pop("_auth_source", None)
    if source != "sso":
        try:
            _sb().auth.sign_out()
        except Exception:
            pass
    st.session_state.pop("_auth_user", None)
    st.session_state.pop("_sso_error", None)


# ──────────────────────────────────────────────────────────────────────────────
# Guard — bloquea la página si no hay sesión o no hay permiso
# ──────────────────────────────────────────────────────────────────────────────

def require_auth(permiso: str = None):
    """
    Llama esta función al inicio de cada página.
    Si no hay sesión → muestra login y detiene la renderización.
    Si no hay permiso → muestra error y detiene la renderización.
    Retorna el dict del usuario si todo está bien.
    """
    user = get_user()
    if "sso_ticket" in st.query_params:
        ticket = st.query_params["sso_ticket"]
        try:
            sso_user = _consume_sso_ticket(ticket)
        except Exception:
            sso_user = None
        if sso_user:
            user = sso_user
            st.session_state["_auth_user"] = user
            st.session_state["_auth_source"] = "sso"
            st.session_state.pop("_sso_error", None)
        elif not user:
            st.session_state["_sso_error"] = True
        else:
            st.session_state.pop("_sso_error", None)
        del st.query_params["sso_ticket"]
        if sso_user:
            st.rerun()

    if not user:
        if st.session_state.pop("_sso_error", False):
            st.error(_SSO_ERROR)
        _render_login()
        st.stop()

    if permiso and not puede(permiso):
        landing = LANDING_PAGE.get(user.get("role", ""))
        if landing:
            st.switch_page(landing)
        st.error("🚫 No tienes permiso para acceder a esta sección.")
        st.caption(f"Tu rol es: **{ETIQUETAS_ROL.get(user.get('role',''), user.get('role',''))}**")
        st.stop()

    return user


def _render_login():
    """Formulario de login mostrado cuando no hay sesión."""
    import os as _os
    _logo = _os.path.join(_os.path.dirname(_os.path.dirname(__file__)), "assets", "logo.png")

    st.markdown("""
    <style>
      [data-testid="stSidebarNav"],
      section[data-testid="stSidebar"] { display: none !important; }

      .stApp {
          background: linear-gradient(150deg, #0F172A 0%, #1E293B 60%, #1a0f0f 100%);
      }
      header[data-testid="stHeader"] { background: transparent !important; }

      .main .block-container {
          padding-top: 4rem !important;
          max-width: 100% !important;
      }

      /* Tarjeta blanca — via bordered container */
      [data-testid="stVerticalBlockBorderWrapper"] {
          background: #FFFFFF !important;
          border-color: transparent !important;
          border-radius: 14px !important;
          box-shadow: 0 24px 64px rgba(0,0,0,0.5) !important;
          padding: 12px 8px !important;
      }

      /* Form dentro de la tarjeta: sin doble borde */
      [data-testid="stForm"] {
          background: transparent !important;
          border: none !important;
          box-shadow: none !important;
          padding: 0 !important;
      }

      /* Labels de inputs — claros sobre fondo oscuro */
      [data-testid="stTextInput"] label p,
      [data-testid="stTextInput"] label,
      [data-testid="stTextInput"] > div > label {
          color: #94A3B8 !important;
          font-size: 0.82rem !important;
          font-weight: 500 !important;
      }

      /* Inputs — fondo blanco, texto oscuro (contraste garantizado) */
      [data-testid="stTextInput"] input {
          background: #FFFFFF !important;
          border: 1.5px solid #D1D5DB !important;
          border-radius: 8px !important;
          color: #1F2937 !important;
          font-size: 0.95rem !important;
      }
      [data-testid="stTextInput"] input::placeholder {
          color: #9CA3AF !important;
      }
      [data-testid="stTextInput"] input:focus {
          border-color: #C0392B !important;
          box-shadow: 0 0 0 3px rgba(192,57,43,0.20) !important;
      }
    </style>
    """, unsafe_allow_html=True)

    _, mid, _ = st.columns([3, 2, 3])
    with mid:
        with st.container(border=True):
            # Logo
            if _os.path.exists(_logo):
                _, cl, _ = st.columns([1, 1, 1])
                with cl:
                    st.image(_logo, width=80)

            st.markdown(
                "<div style='text-align:center;margin-bottom:20px;padding-top:4px'>"
                "<div style='color:#C0392B;font-size:1.75rem;font-weight:800;"
                "letter-spacing:3px;line-height:1.1'>NSG</div>"
                "<div style='color:#CBD5E1;font-size:1.05rem;font-weight:600;"
                "letter-spacing:0.5px;margin-top:4px'>Preparación de Embarques</div>"
                "<div style='color:#9CA3AF;font-size:0.76rem;margin-top:6px'>"
                "Inicia sesión para continuar</div>"
                "</div>",
                unsafe_allow_html=True,
            )

            with st.form("form_login", clear_on_submit=False):
                email    = st.text_input("Correo electrónico", placeholder="usuario@gruponsg.com")
                password = st.text_input("Contraseña", type="password")
                ok       = st.form_submit_button("Entrar", type="primary", use_container_width=True)

            if ok:
                if not email or not password:
                    st.error("Ingresa tu correo y contraseña.")
                else:
                    with st.spinner("Verificando..."):
                        exito, msg = login(email, password)
                    if exito:
                        st.rerun()
                    else:
                        st.error(msg)

            st.markdown(
                "<p style='text-align:center;color:#9CA3AF;font-size:0.7rem;margin-top:8px'>"
                "© 2026 Grupo Comercializador NSG</p>",
                unsafe_allow_html=True,
            )


# ──────────────────────────────────────────────────────────────────────────────
# Cambio de contraseña (usuario cambia la suya)
# ──────────────────────────────────────────────────────────────────────────────

def cambiar_password(user_id: str, nueva: str) -> tuple:
    """Admin actualiza contraseña de cualquier usuario vía API."""
    try:
        _sb().auth.admin.update_user_by_id(user_id, {"password": nueva})
        return True, "Contraseña actualizada correctamente."
    except Exception as e:
        return False, f"Error: {e}"


# ──────────────────────────────────────────────────────────────────────────────
# Gestión de usuarios (solo admin)
# ──────────────────────────────────────────────────────────────────────────────

def listar_usuarios() -> list:
    """Retorna lista de dicts con los usuarios registrados en Supabase Auth."""
    try:
        users = _sb().auth.admin.list_users()
        result = []
        for u in users:
            meta = u.user_metadata or {}
            result.append({
                "id":            u.id,
                "email":         u.email,
                "role":          meta.get("role", "ventas"),
                "nombre":        meta.get("nombre", ""),
                "created_at":    str(u.created_at)[:10],
                "last_sign_in":  str(u.last_sign_in_at)[:10] if u.last_sign_in_at else "—",
            })
        return sorted(result, key=lambda x: x["email"])
    except Exception as e:
        st.error(f"Error al listar usuarios: {e}")
        return []


def crear_usuario(email: str, password: str, nombre: str, role: str) -> tuple:
    """Crea un usuario en Supabase Auth. Retorna (True, id) o (False, mensaje)."""
    try:
        res = _sb().auth.admin.create_user({
            "email":         email,
            "password":      password,
            "email_confirm": True,
            "user_metadata": {"role": role, "nombre": nombre},
        })
        return True, res.user.id
    except Exception as e:
        msg = str(e)
        if "already" in msg.lower():
            return False, "Ya existe un usuario con ese correo."
        return False, f"Error: {msg}"


def eliminar_usuario(user_id: str) -> tuple:
    """Elimina un usuario de Supabase Auth."""
    try:
        _sb().auth.admin.delete_user(user_id)
        return True, "Usuario eliminado."
    except Exception as e:
        return False, f"Error: {e}"


def actualizar_rol(user_id: str, role: str, nombre: str) -> tuple:
    """Actualiza el rol y nombre de un usuario."""
    try:
        _sb().auth.admin.update_user_by_id(
            user_id,
            {"user_metadata": {"role": role, "nombre": nombre}},
        )
        return True, "Usuario actualizado."
    except Exception as e:
        return False, f"Error: {e}"

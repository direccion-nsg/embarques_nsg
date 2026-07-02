"""
Gestión de Usuarios — solo accesible para el rol 'admin'.

Permite:
  - Ver todos los usuarios registrados
  - Agregar nuevos usuarios con rol y contraseña temporal
  - Restablecer contraseña de un usuario
  - Cambiar el rol de un usuario
  - Eliminar un usuario
"""

import os
import sys
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import APP_NAME, VERSION
from modules.database import init_database
from modules.sidebar import render_sidebar
from modules.auth import (
    require_auth,
    listar_usuarios,
    crear_usuario,
    eliminar_usuario,
    actualizar_rol,
    cambiar_password,
    ROLES,
    ETIQUETAS_ROL,
)

# ──────────────────────────────────────────────────────────────────────────────
# Configuración
# ──────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title=f"Usuarios — {APP_NAME}",
    page_icon="👥",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_database()
user_actual = require_auth("usuarios")
render_sidebar(APP_NAME, VERSION)

if st.session_state.get("_current_page") != "usuarios":
    for _k in ("_reset_uid", "_reset_email", "_del_uid", "_del_email"):
        st.session_state.pop(_k, None)
st.session_state["_current_page"] = "usuarios"

# ──────────────────────────────────────────────────────────────────────────────
# Encabezado
# ──────────────────────────────────────────────────────────────────────────────

st.markdown("## 👥 Gestión de Usuarios")
st.caption("Solo los administradores pueden ver y modificar usuarios.")

st.divider()

# ──────────────────────────────────────────────────────────────────────────────
# Lista de usuarios
# ──────────────────────────────────────────────────────────────────────────────

st.markdown("### Usuarios registrados")

if st.button("🔄 Actualizar lista", key="btn_refresh"):
    st.cache_data.clear()
    st.rerun()

usuarios = listar_usuarios()

if not usuarios:
    st.info("No hay usuarios registrados aún.")
else:
    # Encabezado tabla
    cols = st.columns([2.5, 2, 1.5, 1.2, 1.2, 1.5, 1.5])
    for h, c in zip(["Correo", "Nombre", "Rol", "Creado", "Último acceso", "", ""], cols):
        c.markdown(f"**{h}**")
    st.divider()

    for u in usuarios:
        es_yo = u["id"] == user_actual["id"]
        cols  = st.columns([2.5, 2, 1.5, 1.2, 1.2, 1.5, 1.5])

        cols[0].markdown(u["email"] + (" *(tú)*" if es_yo else ""))
        cols[1].markdown(u["nombre"] or "—")
        cols[2].markdown(ETIQUETAS_ROL.get(u["role"], u["role"]))
        cols[3].markdown(u["created_at"])
        cols[4].markdown(u["last_sign_in"])

        with cols[5]:
            if st.button("🔑 Reset pw", key=f"rst_{u['id']}", use_container_width=True,
                         help="Asigna una contraseña temporal"):
                st.session_state["_reset_uid"]   = u["id"]
                st.session_state["_reset_email"] = u["email"]
                st.rerun()

        with cols[6]:
            if not es_yo:
                if st.button("🗑 Eliminar", key=f"del_{u['id']}", use_container_width=True,
                             help="Elimina al usuario permanentemente"):
                    st.session_state["_del_uid"]   = u["id"]
                    st.session_state["_del_email"] = u["email"]
                    st.rerun()
            else:
                cols[6].caption("—")

    st.divider()

# ── Diálogo reset de contraseña ───────────────────────────────────────────────
if "_reset_uid" in st.session_state:
    uid   = st.session_state["_reset_uid"]
    email = st.session_state["_reset_email"]
    st.warning(f"**Restablecer contraseña de:** {email}")
    with st.form("form_reset_pw"):
        nueva  = st.text_input("Nueva contraseña temporal", type="password",
                               help="Mínimo 8 caracteres. El usuario puede cambiarla después.")
        nueva2 = st.text_input("Confirmar", type="password")
        c1, c2 = st.columns(2)
        ok_reset   = c1.form_submit_button("✅ Confirmar", type="primary",  use_container_width=True)
        cancel_rst = c2.form_submit_button("Cancelar",                       use_container_width=True)
    if ok_reset:
        if len(nueva) < 8:
            st.error("Mínimo 8 caracteres.")
        elif nueva != nueva2:
            st.error("Las contraseñas no coinciden.")
        else:
            exito, msg = cambiar_password(uid, nueva)
            if exito:
                st.success(f"✅ Contraseña de **{email}** actualizada.")
                st.session_state.pop("_reset_uid", None)
                st.session_state.pop("_reset_email", None)
                st.rerun()
            else:
                st.error(msg)
    if cancel_rst:
        st.session_state.pop("_reset_uid", None)
        st.session_state.pop("_reset_email", None)
        st.rerun()

# ── Diálogo eliminación ───────────────────────────────────────────────────────
if "_del_uid" in st.session_state:
    uid   = st.session_state["_del_uid"]
    email = st.session_state["_del_email"]
    st.error(f"⚠ ¿Eliminar al usuario **{email}**? Esta acción no se puede deshacer.")
    c1, c2 = st.columns(2)
    if c1.button("🗑 Sí, eliminar", type="primary", use_container_width=True):
        exito, msg = eliminar_usuario(uid)
        if exito:
            st.success(f"✅ Usuario **{email}** eliminado.")
        else:
            st.error(msg)
        st.session_state.pop("_del_uid", None)
        st.session_state.pop("_del_email", None)
        st.rerun()
    if c2.button("Cancelar", use_container_width=True):
        st.session_state.pop("_del_uid", None)
        st.session_state.pop("_del_email", None)
        st.rerun()

# ── Edición de rol y nombre ───────────────────────────────────────────────────
st.markdown("### Editar usuario")

if usuarios:
    opciones = {f"{u['email']} ({ETIQUETAS_ROL.get(u['role'], u['role'])})": u for u in usuarios}
    sel_label = st.selectbox("Selecciona usuario a editar", list(opciones.keys()),
                             key="edit_usr_sel")
    u_edit = opciones[sel_label]

    with st.form("form_editar_usuario"):
        col_n, col_r = st.columns(2)
        nuevo_nombre = col_n.text_input("Nombre completo", value=u_edit["nombre"])
        nuevo_rol    = col_r.selectbox(
            "Rol",
            list(ROLES.keys()),
            index=list(ROLES.keys()).index(u_edit["role"]) if u_edit["role"] in ROLES else 0,
            format_func=lambda r: ETIQUETAS_ROL.get(r, r),
        )
        guardar = st.form_submit_button("💾 Guardar cambios", type="primary")

    if guardar:
        exito, msg = actualizar_rol(u_edit["id"], nuevo_rol, nuevo_nombre)
        if exito:
            st.success(f"✅ {msg}")
            st.rerun()
        else:
            st.error(msg)

st.divider()

# ──────────────────────────────────────────────────────────────────────────────
# Agregar nuevo usuario
# ──────────────────────────────────────────────────────────────────────────────

st.markdown("### ➕ Agregar usuario")

with st.form("form_nuevo_usuario", clear_on_submit=True):
    col1, col2 = st.columns(2)
    email_nuevo  = col1.text_input("Correo electrónico", placeholder="nombre@gruponsg.com")
    nombre_nuevo = col2.text_input("Nombre completo",    placeholder="Juan Pérez")

    col3, col4 = st.columns(2)
    rol_nuevo  = col3.selectbox(
        "Rol",
        list(ROLES.keys()),
        format_func=lambda r: ETIQUETAS_ROL.get(r, r),
    )
    pw_nuevo   = col4.text_input(
        "Contraseña temporal",
        type="password",
        help="El usuario podrá cambiarla desde el sidebar.",
    )

    agregar = st.form_submit_button("➕ Crear usuario", type="primary")

if agregar:
    if not email_nuevo or not nombre_nuevo or not pw_nuevo:
        st.error("Completa todos los campos.")
    elif len(pw_nuevo) < 8:
        st.error("La contraseña temporal debe tener al menos 8 caracteres.")
    elif "@" not in email_nuevo:
        st.error("Ingresa un correo válido.")
    else:
        with st.spinner("Creando usuario..."):
            exito, resultado = crear_usuario(email_nuevo, pw_nuevo, nombre_nuevo, rol_nuevo)
        if exito:
            st.success(
                f"✅ Usuario **{email_nuevo}** creado con rol **{ETIQUETAS_ROL.get(rol_nuevo, rol_nuevo)}**. "
                f"Contraseña temporal configurada."
            )
            st.rerun()
        else:
            st.error(resultado)

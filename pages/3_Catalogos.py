"""Página de gestión de catálogos: remitentes, destinatarios, fleteras."""

import os
import sys
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import APP_NAME, VERSION, ensure_dirs
from modules.database import init_database
from modules.sidebar import render_sidebar
from modules.auth import require_auth
from modules.catalogs import (
    listar_remitentes, guardar_remitente, eliminar_remitente,
    listar_destinatarios, guardar_destinatario, eliminar_destinatario,
    listar_fleteras, guardar_fletera, eliminar_fletera,
    listar_domicilios_entrega, guardar_domicilio_entrega, eliminar_domicilio_entrega,
)

st.set_page_config(page_title=f"Catálogos — {APP_NAME}", page_icon="📚", layout="wide")
ensure_dirs()
init_database()
require_auth("catalogo")
render_sidebar(APP_NAME, VERSION)

st.markdown("## 📚 Catálogos")
st.markdown("Administra remitentes, destinatarios, fleteras y domicilios de entrega.")
st.divider()

tab1, tab2, tab3, tab4 = st.tabs(["🏭 Remitentes", "📍 Destinatarios", "🚚 Fleteras", "🏠 Domicilios de entrega"])


# ──────────────────────────────────────────────────────────────────────────────
# TAB 1 — REMITENTES
# ──────────────────────────────────────────────────────────────────────────────
with tab1:
    st.markdown("### Remitentes")
    remitentes = listar_remitentes()

    if remitentes:
        for r in remitentes:
            with st.expander(f"**{r['nombre']}** — RFC: {r.get('rfc','—')}", expanded=False):
                col1, col2 = st.columns(2)
                with col1:
                    new_nombre = st.text_input("Nombre *", value=r["nombre"], key=f"r_nom_{r['id']}")
                    new_rfc    = st.text_input("RFC", value=r.get("rfc",""), key=f"r_rfc_{r['id']}")
                with col2:
                    new_dir    = st.text_input("Dirección", value=r.get("direccion",""), key=f"r_dir_{r['id']}")
                    new_tel    = st.text_input("Teléfono", value=r.get("telefono",""), key=f"r_tel_{r['id']}")
                c1, c2 = st.columns([1, 5])
                with c1:
                    if st.button("💾 Guardar", key=f"r_save_{r['id']}"):
                        guardar_remitente({
                            "id": r["id"],
                            "nombre": new_nombre,
                            "rfc": new_rfc,
                            "direccion": new_dir,
                            "telefono": new_tel,
                        })
                        st.success("Remitente actualizado.")
                        st.rerun()
                with c2:
                    if st.button("🗑 Desactivar", key=f"r_del_{r['id']}"):
                        eliminar_remitente(r["id"])
                        st.warning("Remitente desactivado.")
                        st.rerun()
    else:
        st.info("No hay remitentes registrados.")

    st.markdown("---")
    st.markdown("#### Agregar nuevo remitente")
    with st.form("form_nuevo_remitente", clear_on_submit=True):
        n1, n2 = st.columns(2)
        with n1:
            nr_nombre = st.text_input("Nombre *")
            nr_rfc    = st.text_input("RFC")
        with n2:
            nr_dir    = st.text_input("Dirección")
            nr_tel    = st.text_input("Teléfono")
        if st.form_submit_button("➕ Agregar remitente"):
            if nr_nombre.strip():
                guardar_remitente({"nombre": nr_nombre, "rfc": nr_rfc, "direccion": nr_dir, "telefono": nr_tel})
                st.success(f"Remitente '{nr_nombre}' agregado.")
                st.rerun()
            else:
                st.error("El nombre es obligatorio.")


# ──────────────────────────────────────────────────────────────────────────────
# TAB 2 — DESTINATARIOS
# ──────────────────────────────────────────────────────────────────────────────
with tab2:
    st.markdown("### Destinatarios")
    destinatarios = listar_destinatarios()

    if destinatarios:
        for d in destinatarios:
            with st.expander(f"**{d['nombre']}** — {d.get('direccion','—')}", expanded=False):
                col1, col2 = st.columns(2)
                with col1:
                    dn_nombre   = st.text_input("Nombre *",      value=d["nombre"],              key=f"d_nom_{d['id']}")
                    dn_rfc      = st.text_input("RFC",           value=d.get("rfc",""),           key=f"d_rfc_{d['id']}")
                    dn_dir      = st.text_input("Dirección",     value=d.get("direccion",""),     key=f"d_dir_{d['id']}")
                with col2:
                    dn_tel      = st.text_input("Teléfono",      value=d.get("telefono",""),      key=f"d_tel_{d['id']}")
                    dn_contacto = st.text_input("Contacto",      value=d.get("contacto",""),      key=f"d_con_{d['id']}")
                    dn_refs     = st.text_input("Referencias",   value=d.get("referencias",""),   key=f"d_ref_{d['id']}")
                c1, c2 = st.columns([1, 5])
                with c1:
                    if st.button("💾 Guardar", key=f"d_save_{d['id']}"):
                        guardar_destinatario({
                            "id": d["id"],
                            "nombre": dn_nombre, "rfc": dn_rfc,
                            "direccion": dn_dir,
                            "telefono": dn_tel, "contacto": dn_contacto,
                            "referencias": dn_refs,
                        })
                        st.success("Destinatario actualizado.")
                        st.rerun()
                with c2:
                    if st.button("🗑 Desactivar", key=f"d_del_{d['id']}"):
                        eliminar_destinatario(d["id"])
                        st.warning("Destinatario desactivado.")
                        st.rerun()
    else:
        st.info("No hay destinatarios registrados.")

    st.markdown("---")
    st.markdown("#### Agregar nuevo destinatario")
    with st.form("form_nuevo_destinatario", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            nd_nombre   = st.text_input("Nombre *")
            nd_rfc      = st.text_input("RFC")
            nd_dir      = st.text_input("Dirección")
        with col2:
            nd_tel      = st.text_input("Teléfono")
            nd_contacto = st.text_input("Contacto")
            nd_refs     = st.text_input("Referencias")
        if st.form_submit_button("➕ Agregar destinatario"):
            if nd_nombre.strip():
                guardar_destinatario({
                    "nombre": nd_nombre, "rfc": nd_rfc,
                    "direccion": nd_dir,
                    "telefono": nd_tel, "contacto": nd_contacto,
                    "referencias": nd_refs,
                })
                st.success(f"Destinatario '{nd_nombre}' agregado.")
                st.rerun()
            else:
                st.error("El nombre es obligatorio.")


# ──────────────────────────────────────────────────────────────────────────────
# TAB 3 — FLETERAS
# ──────────────────────────────────────────────────────────────────────────────
with tab3:
    st.markdown("### Fleteras")
    fleteras = listar_fleteras()

    if fleteras:
        for f in fleteras:
            with st.expander(f"**{f['nombre']}**", expanded=False):
                nf_nombre = st.text_input("Nombre *", value=f["nombre"], key=f"f_nom_{f['id']}")
                c1, c2 = st.columns([1, 5])
                with c1:
                    if st.button("💾 Guardar", key=f"f_save_{f['id']}"):
                        guardar_fletera({"id": f["id"], "nombre": nf_nombre})
                        st.success("Fletera actualizada.")
                        st.rerun()
                with c2:
                    if st.button("🗑 Desactivar", key=f"f_del_{f['id']}"):
                        eliminar_fletera(f["id"])
                        st.warning("Fletera desactivada.")
                        st.rerun()
    else:
        st.info("No hay fleteras registradas.")

    st.markdown("---")
    st.markdown("#### Agregar nueva fletera")
    with st.form("form_nueva_fletera", clear_on_submit=True):
        nf_nuevo = st.text_input("Nombre fletera *")
        if st.form_submit_button("➕ Agregar fletera"):
            if nf_nuevo.strip():
                guardar_fletera({"nombre": nf_nuevo})
                st.success(f"Fletera '{nf_nuevo}' agregada.")
                st.rerun()
            else:
                st.error("El nombre es obligatorio.")


# ──────────────────────────────────────────────────────────────────────────────
# TAB 4 — DOMICILIOS DE ENTREGA
# ──────────────────────────────────────────────────────────────────────────────
with tab4:
    st.markdown("### Domicilios de entrega")
    st.caption("Puntos de entrega directa con vehículo propio NSG. Se usan cuando el tipo de entrega es «Domicilio del cliente».")
    domicilios = listar_domicilios_entrega()

    if domicilios:
        for d in domicilios:
            with st.expander(f"**{d['nombre']}** — {d.get('direccion','—')}", expanded=False):
                col1, col2 = st.columns(2)
                with col1:
                    dd_nombre   = st.text_input("Nombre / referencia *", value=d["nombre"],             key=f"de_nom_{d['id']}")
                    dd_dir      = st.text_input("Dirección",             value=d.get("direccion",""),   key=f"de_dir_{d['id']}")
                    dd_cp       = st.text_input("CP",                    value=d.get("cp",""),           key=f"de_cp_{d['id']}")
                with col2:
                    dd_tel      = st.text_input("Teléfono",              value=d.get("telefono",""),    key=f"de_tel_{d['id']}")
                    dd_contacto = st.text_input("Contacto",              value=d.get("contacto",""),    key=f"de_con_{d['id']}")
                    dd_refs     = st.text_input("Referencias / instrucciones", value=d.get("referencias",""), key=f"de_ref_{d['id']}")
                c1, c2 = st.columns([1, 5])
                with c1:
                    if st.button("💾 Guardar", key=f"de_save_{d['id']}"):
                        guardar_domicilio_entrega({
                            "id": d["id"],
                            "nombre": dd_nombre, "direccion": dd_dir, "cp": dd_cp,
                            "telefono": dd_tel, "contacto": dd_contacto,
                            "referencias": dd_refs,
                        })
                        st.success("Domicilio actualizado.")
                        st.rerun()
                with c2:
                    if st.button("🗑 Desactivar", key=f"de_del_{d['id']}"):
                        eliminar_domicilio_entrega(d["id"])
                        st.warning("Domicilio desactivado.")
                        st.rerun()
    else:
        st.info("No hay domicilios de entrega registrados. Agrega el primero abajo.")

    st.markdown("---")
    st.markdown("#### Agregar domicilio de entrega")
    with st.form("form_nuevo_domicilio", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            nd_nombre   = st.text_input("Nombre / referencia *", placeholder="Ej. AUSA - Bodega Vallejo")
            nd_dir      = st.text_input("Dirección",             placeholder="Calle, No., Colonia, Ciudad")
            nd_cp       = st.text_input("CP",                    placeholder="12345")
        with col2:
            nd_tel      = st.text_input("Teléfono",              placeholder="55 1234 5678")
            nd_contacto = st.text_input("Contacto",              placeholder="Nombre de quien recibe")
            nd_refs     = st.text_input("Referencias / instrucciones", placeholder="Entrada por Puerta 3, preguntar por…")
        if st.form_submit_button("➕ Agregar domicilio"):
            if nd_nombre.strip():
                guardar_domicilio_entrega({
                    "nombre": nd_nombre, "direccion": nd_dir, "cp": nd_cp,
                    "telefono": nd_tel, "contacto": nd_contacto,
                    "referencias": nd_refs,
                })
                st.success(f"Domicilio '{nd_nombre}' agregado.")
                st.rerun()
            else:
                st.error("El nombre / referencia es obligatorio.")

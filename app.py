"""
Preparación de Embarques NSG — Página principal: Nuevo Embarque  (modelo v2)

Flujo por embarque:
  1. Subir PDF Bind → extraer datos → detectar folio existente en DB
  2. Revisar y corregir datos + editar cantidades a embarcar por partida
  3. Capturar datos logísticos (+ remisión si aplica)
  4. Generar paquete PDF → registrar salida + embarque en DB
  5. Agregar a Bandeja para envío conjunto o individual
"""

import copy
import os
import sys
import traceback

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import APP_NAME, VERSION, ensure_dirs
from modules.database import (
    init_database,
    crear_salida, get_salida_por_folio, get_salida_por_id,
    crear_embarque,
    registrar_cambio,
    agregar_a_bandeja as db_agregar_bandeja,
    get_bandeja as db_get_bandeja,
)
from modules.pdf_reader import extraer_datos_bind
from modules.pdf_generator import generar_hoja_logistica
from modules.pdf_merger import combinar_paquete_embarque
from modules.pdf_remision import guardar_remision, FORMATOS_VALIDOS
from modules.catalogs import (
    nombres_remitentes, get_remitente_por_nombre,
    nombres_destinatarios, get_destinatario_por_nombre,
    nombres_fleteras, generar_observaciones,
    guardar_destinatario, guardar_fletera,
    nombres_domicilios_entrega, get_domicilio_por_nombre,
    guardar_domicilio_entrega,
)
from modules.utils import construir_datos_mensaje
from modules.storage import init_storage, subir_pdf, generar_url_firmada
from modules.messaging import construir_mensaje_teams
from modules.auth import require_auth
from modules.sidebar import render_sidebar
from modules.consistency import (
    interpretar_notas_bind, validar_consistencia,
    hay_errores, hay_warnings, detalle_warnings_json, extraer_cp,
)

# ──────────────────────────────────────────────────────────────────────────────
# Configuración de página
# ──────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title=APP_NAME,
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_database()
init_storage()
require_auth("nuevo")


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _to_float(v) -> float:
    try:
        return float(str(v).replace(",", ".") or 0)
    except (ValueError, TypeError):
        return 0.0


# ──────────────────────────────────────────────────────────────────────────────
# Estado de sesión
# ──────────────────────────────────────────────────────────────────────────────

def _init_state():
    # Bandeja se carga de DB para persistir entre sesiones
    if "bandeja" not in st.session_state:
        st.session_state["bandeja"] = db_get_bandeja()

    defaults = {
        "datos_bind":          None,
        "datos_bind_original": None,
        "salida_db":           None,   # dict de salida_bind existente (None = primera vez)
        "salida_id":           None,   # int: ID de la salida en DB
        "embarque_id":         None,   # int: ID del embarque generado
        "_bytes_pdf_original": None,   # bytes del PDF Bind subido (primero)
        "_bytes_pdf_remision": None,   # bytes del PDF de remisión
        "_bytes_paquete":      None,   # bytes del PDF de paquete generado
        "_filename_paquete":   None,   # nombre del archivo del paquete
        "_datos_adicionales":  [],     # lista de dicts para Binds extra [{datos_bind, salida_db, bytes}]
        "en_bandeja":          False,
        "paso":                1,
        "upload_key":          0,
        "sugerencias_notas":   {},
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


_init_state()


def _agregar_a_bandeja(embarque_id: int):
    # Bloquear duplicados
    ids_existentes = {e.get("embarque_id") for e in st.session_state["bandeja"]}
    if embarque_id and embarque_id in ids_existentes:
        st.warning("Este embarque ya está en la bandeja.")
        return
    # Persistir en DB y recargar bandeja completa desde DB
    db_agregar_bandeja(embarque_id)
    st.session_state["bandeja"] = db_get_bandeja()
    st.session_state["en_bandeja"] = True
    st.rerun()


def _resetear_flujo():
    keys = [
        "datos_bind", "datos_bind_original",
        "salida_db", "salida_id", "embarque_id",
        "_bytes_pdf_original", "_bytes_pdf_remision",
        "_bytes_paquete", "_filename_paquete", "_ruta_storage_paquete",
        "_datos_adicionales",
        "en_bandeja", "datos_logisticos", "sugerencias_notas",
        "editor_partidas", "_partidas_df",
        # widgets Paso 2
        "folio", "cliente", "rfc_cli", "fecha", "oc", "tel_cli",
        "dir_cli", "notas_bind",
        # widgets Paso 3
        "sel_rem", "rem_nom", "rem_rfc", "rem_tel", "rem_dir",
        "sel_dest", "dest_nom", "dest_rfc", "dest_dir", "dest_cp_manual",
        "dest_tel", "dest_con", "dest_ref",
        "sel_dom_ent",
        "sel_flet", "flet_nom", "tipo_ent", "cond_flet", "con_rem",
        "emp_rem", "num_rem", "est_rem", "notas_adic",
    ]
    for k in keys:
        st.session_state.pop(k, None)
    for k in [k for k in st.session_state if k.startswith("_partidas_df_adic_")
              or k.startswith("editor_partidas_adic_")]:
        st.session_state.pop(k, None)
    st.session_state["paso"]       = 1
    st.session_state["upload_key"] += 1
    st.rerun()


# ──────────────────────────────────────────────────────────────────────────────
# Sidebar y encabezado
# ──────────────────────────────────────────────────────────────────────────────

render_sidebar(APP_NAME, VERSION)
st.session_state["_current_page"] = "nuevo_embarque"

st.markdown(f'<p class="titulo-nsg">📦 {APP_NAME}</p>', unsafe_allow_html=True)
st.markdown(
    f'<p class="subtitulo">Finanzas CDMX → Almacén Teoloyucan &nbsp;|&nbsp; v{VERSION}</p>',
    unsafe_allow_html=True,
)

if st.session_state["en_bandeja"]:
    st.success("✅ Embarque agregado a la bandeja. Puedes procesar otro o ir a la Bandeja para enviar.")
    col_sig1, col_sig2 = st.columns(2)
    with col_sig1:
        if st.button("➕ Procesar otro embarque", type="primary"):
            _resetear_flujo()
    with col_sig2:
        st.page_link("pages/4_Bandeja.py", label="📦 Ir a Bandeja →")
    st.divider()
    st.stop()

st.divider()

# ──────────────────────────────────────────────────────────────────────────────
# PASO 1 — Subir PDF Bind
# ──────────────────────────────────────────────────────────────────────────────

st.markdown("### 1 — Subir Hoja de Salida Bind")

archivos = st.file_uploader(
    "Selecciona el/los PDF(s) de salida Bind",
    type=["pdf"],
    accept_multiple_files=True,
    key=f"uploader_pdf_{st.session_state['upload_key']}",
    help="Arrastra uno o varios archivos. Si el embarque agrupa varias salidas, sube todos sus PDFs Bind.",
)

if archivos:
    n_arch = len(archivos)
    if n_arch > 1:
        st.info(f"📄 {n_arch} PDFs seleccionados — se generará un solo embarque con todas las salidas.")
    if st.button("🔍 Extraer datos del PDF", type="primary"):
        with st.spinner(f"Leyendo {'PDFs' if n_arch > 1 else 'PDF'}..."):
            # ── Primer PDF (principal) ─────────────────────────────────────────
            pdf_bytes = archivos[0].getvalue()
            datos     = extraer_datos_bind(pdf_bytes)
            folio     = datos.get("folio", "")
            salida_base      = get_salida_por_folio(folio) if folio else None
            salida_existente = get_salida_por_id(salida_base["id"]) if salida_base else None

            # ── PDFs adicionales ───────────────────────────────────────────────
            datos_adicionales = []
            for archivo_extra in archivos[1:]:
                b_extra       = archivo_extra.getvalue()
                datos_extra   = extraer_datos_bind(b_extra)
                folio_extra   = datos_extra.get("folio", "")
                sb_extra      = get_salida_por_folio(folio_extra) if folio_extra else None
                salida_extra  = get_salida_por_id(sb_extra["id"]) if sb_extra else None
                datos_adicionales.append({
                    "datos_bind": datos_extra,
                    "salida_db":  salida_extra,
                    "bytes":      b_extra,
                })

            st.session_state.update({
                "datos_bind":          datos,
                "datos_bind_original": copy.deepcopy(datos),
                "salida_db":           salida_existente,
                "salida_id":           salida_existente["id"] if salida_existente else None,
                "embarque_id":         None,
                "_bytes_pdf_original": pdf_bytes,
                "_bytes_pdf_remision": None,
                "_bytes_paquete":      None,
                "_filename_paquete":   None,
                "_datos_adicionales":  datos_adicionales,
                "en_bandeja":          False,
                "paso":                2,
            })
            st.session_state.pop("editor_partidas", None)
            st.session_state.pop("_partidas_df", None)
            for _k in [k for k in st.session_state if k.startswith("_partidas_df_adic_")
                       or k.startswith("editor_partidas_adic_")]:
                st.session_state.pop(_k, None)

            # Interpretar notas y prellenar widgets logísticos
            sug = interpretar_notas_bind(datos.get("notas", ""), nombres_fleteras())
            st.session_state["sugerencias_notas"] = sug
            if sug["condicion_flete_sugerida"]:
                st.session_state["cond_flet"] = sug["condicion_flete_sugerida"]
            if sug["tipo_entrega_sugerido"]:
                st.session_state["tipo_ent"] = sug["tipo_entrega_sugerido"]
            st.session_state["con_rem"] = sug["con_remision_sugerido"]
            fletera_sug = sug["fletera_sugerida"]
            if fletera_sug and fletera_sug in nombres_fleteras():
                st.session_state["sel_flet"] = fletera_sug
            elif fletera_sug:
                st.session_state["sel_flet"] = "— Manual —"
                st.session_state["flet_nom"] = fletera_sug

        if datos.get("error"):
            st.error(f"Error al leer el PDF: {datos['error']}")
        elif salida_existente:
            n_emb = len(salida_existente.get("embarques", []))
            st.info(
                f"📋 Folio **{folio}** ya tiene **{n_emb}** embarque(s) registrado(s) "
                f"(estado: **{salida_existente.get('estado','—')}**). "
                "Se cargaron las cantidades pendientes."
            )
        else:
            st.success(f"Extraído: **{datos.get('folio','—')}** | {datos.get('cliente','—')}")

st.divider()

# Botón de escape: visible solo cuando ya hay un PDF cargado
if st.session_state.get("datos_bind"):
    _col_info, _col_btn = st.columns([5, 1])
    with _col_info:
        _folio_actual = st.session_state["datos_bind"].get("folio", "—")
        st.caption(f"📄 PDF cargado: **{_folio_actual}** — Si es incorrecto puedes cancelar y cargar otro.")
    with _col_btn:
        if st.button("↩ Nueva carga", use_container_width=True, help="Descarta el PDF actual y regresa al paso 1"):
            _resetear_flujo()
    st.divider()

# ──────────────────────────────────────────────────────────────────────────────
# PASO 2 — Revisar datos y cantidades a embarcar
# ──────────────────────────────────────────────────────────────────────────────

datos_bind = st.session_state.get("datos_bind") or {}

with st.expander(
    "2 — Revisar datos y cantidades a embarcar",
    expanded=(st.session_state["paso"] == 2),
):
    if not datos_bind:
        st.info("Sube un PDF de Bind para ver los datos aquí.")
    else:
        # ── Panel: folio existente ─────────────────────────────────────────────
        salida_db = st.session_state.get("salida_db")
        if salida_db:
            n_emb    = len(salida_db.get("embarques", []))
            est_sal  = salida_db.get("estado", "Pendiente")
            c_info, c_link = st.columns([4, 1])
            with c_info:
                st.info(
                    f"📋 Este folio ya tiene **{n_emb}** embarque(s) — "
                    f"Estado: **{est_sal}**. "
                    "Se muestran las cantidades **pendientes** para este nuevo embarque."
                )
            with c_link:
                st.page_link("pages/2_Historial.py", label="Ver historial →")

        # ── Datos encabezado ──────────────────────────────────────────────────
        st.caption("Edita cualquier campo si la extracción no fue exacta.")
        c1, c2, c3 = st.columns(3)
        with c1:
            datos_bind["folio"]       = st.text_input("Folio",       value=datos_bind.get("folio",""),       key="folio",
                help="Número de folio de la Hoja de Salida Bind. Identifica la salida en el sistema.")
            datos_bind["cliente"]     = st.text_input("Cliente",     value=datos_bind.get("cliente",""),     key="cliente",
                help="Nombre del cliente tal como aparece en el PDF.")
            datos_bind["rfc_cliente"] = st.text_input("RFC cliente", value=datos_bind.get("rfc_cliente",""), key="rfc_cli",
                help="RFC del cliente para documentación fiscal.")
        with c2:
            datos_bind["fecha"]        = st.text_input("Fecha",        value=datos_bind.get("fecha",""),        key="fecha",
                help="Fecha de emisión de la Hoja de Salida Bind.")
            datos_bind["orden_compra"] = st.text_input("Orden compra", value=datos_bind.get("orden_compra",""), key="oc",
                help="Número de orden de compra del cliente.")
            datos_bind["tel_cliente"]  = st.text_input("Tel. cliente", value=datos_bind.get("tel_cliente",""),  key="tel_cli",
                help="Teléfono del cliente para referencia de entrega.")
        with c3:
            datos_bind["direccion_cliente"] = st.text_area(
                "Dirección cliente",
                value=datos_bind.get("direccion_cliente", ""),
                height=90, key="dir_cli",
                help="Dirección completa del cliente extraída del PDF.",
            )

        datos_bind["notas"] = st.text_area(
            "Notas del PDF", value=datos_bind.get("notas", ""), key="notas_bind",
            help="Notas del PDF Bind. El sistema las analiza para sugerir fletera, tipo de entrega y condición de flete.",
        )
        st.session_state["datos_bind"] = datos_bind

        # ── Tabla de partidas con cantidades ──────────────────────────────────
        st.markdown("**Partidas:**")

        if salida_db and salida_db.get("partidas"):
            partidas_base = salida_db["partidas"]
            primera_vez   = False
        else:
            partidas_base = [
                {
                    "codigo":             p.get("codigo", ""),
                    "descripcion":        p.get("descripcion", ""),
                    "unidad":             p.get("unidad", ""),
                    "cantidad_bind":      _to_float(p.get("cantidad", 0)),
                    "cantidad_embarcada": 0.0,
                    "cantidad_pendiente": _to_float(p.get("cantidad", 0)),
                }
                for p in datos_bind.get("productos", [])
            ]
            primera_vez = True

        if partidas_base:
            df_partidas = pd.DataFrame([
                {
                    "Código":          p.get("codigo", ""),
                    "Descripción":     p.get("descripcion", ""),
                    "Unidad":          p.get("unidad", ""),
                    "Cant. Bind":      float(p.get("cantidad_bind", 0)),
                    "Embarcada":       float(p.get("cantidad_embarcada", 0)),
                    "Pendiente":       float(p.get("cantidad_pendiente",
                                               p.get("cantidad_bind", 0))),
                    "A embarcar hoy":  float(p.get("cantidad_pendiente",
                                               p.get("cantidad_bind", 0))),
                }
                for p in partidas_base
            ])

            edited = st.data_editor(
                df_partidas,
                column_config={
                    "Código":      st.column_config.TextColumn(disabled=True),
                    "Descripción": st.column_config.TextColumn(disabled=True),
                    "Unidad":      st.column_config.TextColumn(disabled=True),
                    "Cant. Bind":  st.column_config.NumberColumn(
                        disabled=True, format="%.2f",
                        help="Cantidad en la Hoja de Salida Bind"),
                    "Embarcada":   st.column_config.NumberColumn(
                        disabled=True, format="%.2f",
                        help="Acumulado de embarques anteriores"),
                    "Pendiente":   st.column_config.NumberColumn(
                        disabled=True, format="%.2f",
                        help="Cant. Bind - Embarcada acumulada"),
                    "A embarcar hoy": st.column_config.NumberColumn(
                        min_value=0, format="%.2f",
                        help="Cantidad que sale en ESTE embarque"),
                },
                hide_index=True,
                use_container_width=True,
                key="editor_partidas",
            )
            # Guardar el DataFrame completo (no el delta) para usarlo en Paso 4
            st.session_state["_partidas_df"] = edited

            # Advertir si se intenta embarcar más de lo pendiente
            if edited is not None:
                excedentes = edited[edited["A embarcar hoy"] > edited["Pendiente"] + 0.001]
                if not excedentes.empty:
                    for _, row in excedentes.iterrows():
                        st.warning(
                            f"⚠ **{row['Código']}**: se embarcan **{row['A embarcar hoy']:.2f}** "
                            f"pero solo quedan **{row['Pendiente']:.2f}** pendientes. "
                            "Confirma si es una excepción autorizada."
                        )
        else:
            st.warning(
                "No se extrajeron partidas del PDF — "
                "el PDF Bind se incluirá como referencia en el paquete."
            )

        # ── Salidas adicionales (editables, igual que la salida principal) ────
        datos_adicionales_vis = st.session_state.get("_datos_adicionales", [])
        if datos_adicionales_vis:
            st.markdown("---")
            st.markdown(f"**+ {len(datos_adicionales_vis)} salida(s) adicional(es) incluida(s) en este embarque:**")
            for i, adic in enumerate(datos_adicionales_vis):
                d = adic.get("datos_bind", {})
                sal_adic = adic.get("salida_db")
                lbl = f"Salida {i+2}: {d.get('folio','?')} — {d.get('cliente','?')}"
                with st.expander(lbl, expanded=True):
                    ac1, ac2 = st.columns(2)
                    ac1.markdown(f"**Folio:** {d.get('folio','—')}")
                    ac1.markdown(f"**Cliente:** {d.get('cliente','—')}")
                    ac1.markdown(f"**RFC:** {d.get('rfc_cliente','—')}")
                    ac2.markdown(f"**Fecha:** {d.get('fecha','—')}")
                    ac2.markdown(f"**OC:** {d.get('orden_compra','—')}")
                    if sal_adic:
                        n_e = len(sal_adic.get("embarques", []))
                        st.info(f"📋 Folio con {n_e} embarque(s) previo(s) — se embarcarán las cantidades **pendientes**.")

                    if sal_adic and sal_adic.get("partidas"):
                        partidas_base_adic = sal_adic["partidas"]
                    else:
                        partidas_base_adic = [
                            {
                                "codigo":             p.get("codigo", ""),
                                "descripcion":        p.get("descripcion", ""),
                                "unidad":             p.get("unidad", ""),
                                "cantidad_bind":      _to_float(p.get("cantidad", 0)),
                                "cantidad_embarcada": 0.0,
                                "cantidad_pendiente": _to_float(p.get("cantidad", 0)),
                            }
                            for p in d.get("productos", [])
                        ]

                    if partidas_base_adic:
                        df_partidas_adic = pd.DataFrame([
                            {
                                "Código":          p.get("codigo", ""),
                                "Descripción":     p.get("descripcion", ""),
                                "Unidad":          p.get("unidad", ""),
                                "Cant. Bind":      float(p.get("cantidad_bind", 0)),
                                "Embarcada":       float(p.get("cantidad_embarcada", 0)),
                                "Pendiente":       float(p.get("cantidad_pendiente",
                                                           p.get("cantidad_bind", 0))),
                                "A embarcar hoy":  float(p.get("cantidad_pendiente",
                                                           p.get("cantidad_bind", 0))),
                            }
                            for p in partidas_base_adic
                        ])

                        edited_adic = st.data_editor(
                            df_partidas_adic,
                            column_config={
                                "Código":      st.column_config.TextColumn(disabled=True),
                                "Descripción": st.column_config.TextColumn(disabled=True),
                                "Unidad":      st.column_config.TextColumn(disabled=True),
                                "Cant. Bind":  st.column_config.NumberColumn(
                                    disabled=True, format="%.2f",
                                    help="Cantidad en la Hoja de Salida Bind"),
                                "Embarcada":   st.column_config.NumberColumn(
                                    disabled=True, format="%.2f",
                                    help="Acumulado de embarques anteriores"),
                                "Pendiente":   st.column_config.NumberColumn(
                                    disabled=True, format="%.2f",
                                    help="Cant. Bind - Embarcada acumulada"),
                                "A embarcar hoy": st.column_config.NumberColumn(
                                    min_value=0, format="%.2f",
                                    help="Cantidad que sale en ESTE embarque"),
                            },
                            hide_index=True,
                            use_container_width=True,
                            key=f"editor_partidas_adic_{i}",
                        )
                        st.session_state[f"_partidas_df_adic_{i}"] = edited_adic

                        excedentes_adic = edited_adic[
                            edited_adic["A embarcar hoy"] > edited_adic["Pendiente"] + 0.001]
                        if not excedentes_adic.empty:
                            for _, row in excedentes_adic.iterrows():
                                st.warning(
                                    f"⚠ **{row['Código']}**: se embarcan **{row['A embarcar hoy']:.2f}** "
                                    f"pero solo quedan **{row['Pendiente']:.2f}** pendientes. "
                                    "Confirma si es una excepción autorizada."
                                )
                    else:
                        st.warning(
                            "No se extrajeron partidas del PDF — "
                            "el PDF Bind se incluirá como referencia en el paquete."
                        )

if datos_bind and not st.session_state.get("datos_logisticos"):
    st.info("👆 Revisa los datos del Paso 2 y luego abre el **Paso 3 — Datos logísticos** para capturar fletera, destinatario y condiciones de entrega.")

st.divider()

# ──────────────────────────────────────────────────────────────────────────────
# PASO 3 — Datos logísticos
# ──────────────────────────────────────────────────────────────────────────────

@st.fragment
def _paso3(datos_bind):
    with st.expander(
        "3 — Capturar datos logísticos",
        expanded=(bool(st.session_state.get("datos_logisticos")) and bool(datos_bind)),
    ):
        if not datos_bind:
            st.info("Completa el Paso 1 primero.")
        else:
            # ── Inicializar campos en primer render (desde datos_bind) ────────────
            if "rem_nom" not in st.session_state:
                st.session_state["rem_nom"] = datos_bind.get("remitente_nombre", "")
                st.session_state["rem_rfc"] = datos_bind.get("remitente_rfc", "")
                st.session_state["rem_tel"] = datos_bind.get("remitente_tel", "")
                st.session_state["rem_dir"] = datos_bind.get("remitente_direccion", "")
            if "dest_nom" not in st.session_state:
                st.session_state["dest_nom"] = datos_bind.get("cliente", "")
                st.session_state["dest_rfc"] = datos_bind.get("rfc_cliente", "")
                st.session_state["dest_dir"] = datos_bind.get("direccion_cliente", "")
                st.session_state["dest_tel"] = datos_bind.get("tel_cliente", "")
                st.session_state["dest_con"] = ""
                st.session_state["dest_ref"] = ""
            if "flet_nom" not in st.session_state:
                _flet_pre = st.session_state.get("sel_flet", "— Manual —")
                st.session_state["flet_nom"] = "" if _flet_pre == "— Manual —" else _flet_pre
    
            def _on_rem_change():
                sel = st.session_state["sel_rem"]
                if sel == "— Manual —":
                    st.session_state["rem_nom"] = ""
                    st.session_state["rem_rfc"] = ""
                    st.session_state["rem_tel"] = ""
                    st.session_state["rem_dir"] = ""
                    return
                cat = get_remitente_por_nombre(sel)
                st.session_state["rem_nom"] = cat.get("nombre", "")
                st.session_state["rem_rfc"] = cat.get("rfc", "")
                st.session_state["rem_tel"] = cat.get("telefono", "")
                st.session_state["rem_dir"] = cat.get("direccion", "")
    
            def _on_dest_change():
                sel = st.session_state["sel_dest"]
                if sel == "— Manual —":
                    st.session_state["dest_nom"] = ""
                    st.session_state["dest_rfc"] = ""
                    st.session_state["dest_dir"] = ""
                    st.session_state["dest_tel"] = ""
                    st.session_state["dest_con"] = ""
                    st.session_state["dest_ref"] = ""
                    return
                cat = get_destinatario_por_nombre(sel)
                st.session_state["dest_nom"] = cat.get("nombre", "")
                st.session_state["dest_rfc"] = cat.get("rfc", "")
                st.session_state["dest_dir"] = cat.get("direccion", "")
                st.session_state["dest_tel"] = cat.get("telefono", "")
                st.session_state["dest_con"] = cat.get("contacto", "")
                st.session_state["dest_ref"] = cat.get("referencias", "")
    
            def _on_flet_change():
                sel = st.session_state["sel_flet"]
                st.session_state["flet_nom"] = "" if sel == "— Manual —" else sel
    
            def _on_tipo_ent_change():
                # Al cambiar tipo, limpiar selección de domicilio de entrega
                st.session_state.pop("sel_dom_ent", None)
    
            def _on_dom_ent_change():
                sel = st.session_state.get("sel_dom_ent", "— Seleccionar —")
                if sel and sel != "— Seleccionar —":
                    dom = get_domicilio_por_nombre(sel)
                    st.session_state["dest_nom"] = dom.get("nombre", "")
                    st.session_state["dest_dir"] = dom.get("direccion", "")
                    st.session_state["dest_cp_manual"] = dom.get("cp", "")
                    st.session_state["dest_tel"] = dom.get("telefono", "")
                    st.session_state["dest_con"] = dom.get("contacto", "")
                    st.session_state["dest_ref"] = dom.get("referencias", "")
                else:
                    st.session_state["dest_nom"] = ""
                    st.session_state["dest_dir"] = ""
                    st.session_state["dest_cp_manual"] = ""
                    st.session_state["dest_tel"] = ""
                    st.session_state["dest_con"] = ""
                    st.session_state["dest_ref"] = ""
    
            # ── Remitente ─────────────────────────────────────────────────────────
            st.markdown('<div class="seccion"><b>Remitente (origen)</b></div>',
                        unsafe_allow_html=True)
            rem_sel = st.selectbox(
                "Del catálogo", ["— Manual —"] + nombres_remitentes(), key="sel_rem",
                on_change=_on_rem_change,
                help="Selecciona NSG u otro remitente del catálogo. Con «Manual» capturas uno nuevo.",
            )
            cr1, cr2 = st.columns(2)
            with cr1:
                rem_nombre = st.text_input(
                    "Nombre *",
                    key="rem_nom",
                    help="Nombre completo del remitente (origen del embarque).",
                )
                rem_rfc = st.text_input(
                    "RFC",
                    key="rem_rfc",
                    help="RFC del remitente para la hoja logística.",
                )
            with cr2:
                rem_tel = st.text_input(
                    "Teléfono",
                    key="rem_tel",
                    help="Teléfono de contacto del remitente.",
                )
                rem_dir = st.text_input(
                    "Dirección",
                    key="rem_dir",
                    help="Dirección de origen del embarque.",
                )
    
            # ── Destinatario ──────────────────────────────────────────────────────
            st.markdown('<div class="seccion"><b>Destinatario (destino)</b></div>',
                        unsafe_allow_html=True)
            if st.session_state.get("tipo_ent") == "Domicilio del cliente":
                _domicilios_cat = nombres_domicilios_entrega()
                if _domicilios_cat:
                    st.selectbox(
                        "🚗 Domicilio de entrega (vehículo propio NSG)",
                        ["— Seleccionar —"] + _domicilios_cat,
                        key="sel_dom_ent",
                        on_change=_on_dom_ent_change,
                        help="Selecciona el punto de entrega. Los campos se llenarán automáticamente y puedes editarlos.",
                    )
                else:
                    st.info(
                        "No hay domicilios de entrega registrados. "
                        "Agrégalos en **Catálogos → Domicilios de entrega** y luego vuelve aquí."
                    )
            dest_sel = st.selectbox(
                "Del catálogo", ["— Manual —"] + nombres_destinatarios(), key="sel_dest",
                on_change=_on_dest_change,
                help="Selecciona un destinatario guardado. Con «Manual» capturas uno nuevo y puedes guardarlo al catálogo.",
            )
            cd1, cd2 = st.columns(2)
            with cd1:
                dest_nombre = st.text_input(
                    "Nombre *",
                    key="dest_nom",
                    help="Nombre del consignatario al que se entrega el embarque.",
                )
                dest_rfc = st.text_input(
                    "RFC",
                    key="dest_rfc",
                    help="RFC del destinatario para documentación.",
                )
                dest_dir = st.text_input(
                    "Dirección",
                    key="dest_dir",
                    help="Dirección completa de entrega. Incluye el CP en formato «C.P. 12345» para detección automática.",
                )
                # CP: auto-detectado de la dirección o captura manual
                _cp_auto = extraer_cp(dest_dir)
                if _cp_auto:
                    st.caption(f"CP detectado automáticamente: **{_cp_auto}**")
                    dest_cp = _cp_auto
                else:
                    dest_cp = st.text_input(
                        "CP (no detectado — capturar manualmente)",
                        key="dest_cp_manual",
                        help="Código postal de 5 dígitos. Se imprime en la hoja logística y lo usa la fletera para la guía.",
                    )
            with cd2:
                dest_tel = st.text_input(
                    "Teléfono",
                    key="dest_tel",
                    help="Teléfono del destinatario. Obligatorio para entregas a domicilio.",
                )
                dest_contacto = st.text_input(
                    "Contacto",
                    key="dest_con",
                    help="Nombre de la persona que recibe en el destino.",
                )
                dest_refs = st.text_input(
                    "Referencias",
                    key="dest_ref",
                    help="Referencias de ubicación para la fletera: color de fachada, entre qué calles, etc.",
                )
    
            if dest_sel == "— Manual —" and dest_nombre and \
                    dest_nombre not in nombres_destinatarios():
                if st.button("💾 Guardar destinatario en catálogo", key="btn_guardar_dest"):
                    guardar_destinatario({
                        "nombre":      dest_nombre,
                        "rfc":         dest_rfc,
                        "direccion":   dest_dir,
                        "telefono":    dest_tel,
                        "contacto":    dest_contacto,
                        "referencias": dest_refs,
                    })
                    st.rerun()
    
            # Botón para guardar domicilio de entrega desde el formulario
            if (st.session_state.get("tipo_ent") == "Domicilio del cliente"
                    and st.session_state.get("sel_dom_ent", "— Seleccionar —") == "— Seleccionar —"
                    and dest_nombre
                    and dest_nombre not in nombres_domicilios_entrega()):
                if st.button("💾 Guardar domicilio en catálogo", key="btn_guardar_dom_ent"):
                    guardar_domicilio_entrega({
                        "nombre":      dest_nombre,
                        "direccion":   dest_dir,
                        "cp":          dest_cp if dest_cp else st.session_state.get("dest_cp_manual", ""),
                        "telefono":    dest_tel,
                        "contacto":    dest_contacto,
                        "referencias": dest_refs,
                    })
                    st.rerun()
    
            # ── Fletera y condiciones ──────────────────────────────────────────────
            st.markdown('<div class="seccion"><b>Fletera y condiciones</b></div>',
                        unsafe_allow_html=True)
    
            # Leer tipo_ent del estado anterior para condicionar cf1 (se renderiza antes de cf2)
            _es_domicilio_propio = st.session_state.get("tipo_ent", "Ocurre") == "Domicilio del cliente"
    
            cf1, cf2, cf3 = st.columns(3)
            with cf1:
                if _es_domicilio_propio:
                    st.info("🚗 Entrega con vehículo propio NSG — sin fletera externa.")
                    fletera  = "Vehículo propio NSG"
                    flet_sel = "— Manual —"
                else:
                    flet_sel = st.selectbox(
                        "Fletera *", ["— Manual —"] + nombres_fleteras(), key="sel_flet",
                        on_change=_on_flet_change,
                        help="Empresa transportista. El sistema compara con las notas del Bind y avisa si hay diferencia.",
                    )
                    fletera = st.text_input(
                        "Nombre fletera",
                        key="flet_nom",
                        help="Nombre exacto de la fletera tal como aparece en sus guías.",
                    )
                    if flet_sel == "— Manual —" and fletera and \
                            fletera not in nombres_fleteras():
                        if st.button("💾 Guardar fletera", key="btn_guardar_fletera"):
                            guardar_fletera({"nombre": fletera})
                            st.rerun()
            with cf2:
                tipo_entrega = st.selectbox(
                    "Tipo de entrega *",
                    ["Ocurre", "Domicilio", "Domicilio del cliente"],
                    key="tipo_ent",
                    on_change=_on_tipo_ent_change,
                    help=(
                        "Ocurre: el cliente recoge en la agencia de la fletera. "
                        "Domicilio: la fletera entrega en el domicilio del cliente. "
                        "Domicilio del cliente: NSG entrega directamente con vehículo propio."
                    ),
                )
                if _es_domicilio_propio:
                    condicion_flete = "Entrega directa"
                    st.caption("Sin cargo de flete — entrega directa con vehículo NSG.")
                else:
                    condicion_flete = st.selectbox(
                        "Condición del flete *", ["Por cobrar", "Pagado"], key="cond_flet",
                        help="Por cobrar: el destinatario paga el flete al recibirlo. Pagado: NSG cubre el costo del flete.",
                    )
            with cf3:
                con_remision = st.checkbox("Con remisión del cliente", key="con_rem",
                    help="Activa si el cliente envía una remisión que debe acompañar al embarque (física o digital).")
    
            # ── Pedido interno de Planta ───────────────────────────────────────────
            pi1, _ = st.columns([1, 2])
            with pi1:
                pedido_interno = st.text_input(
                    "Pedido interno de Planta (opcional)",
                    placeholder="Ej. P001  ó  P001, P002",
                    key="ped_int",
                    help="Número(s) de pedido internos de Planta. Si son varios, sepáralos con coma. Se puede buscar por número individual en el Historial.",
                )
    
            # ── Sección remisión ───────────────────────────────────────────────────
            empresa_remision = ""
            numero_remision  = ""
    
            if con_remision:
                st.markdown('<div class="seccion"><b>📄 Remisión del cliente</b></div>',
                            unsafe_allow_html=True)
                cr1r, cr2r = st.columns(2)
                with cr1r:
                    empresa_remision = st.text_input("Empresa que remisiona", key="emp_rem",
                        help="Nombre de la empresa que emite la remisión (ej. el propio cliente, su corporativo, etc.).")
                    numero_remision  = st.text_input("Número de remisión", key="num_rem",
                        help="Folio o número de la remisión del cliente. Déjalo vacío si no aplica y selecciona el estado correspondiente.")
                    estado_remision  = st.selectbox(
                        "Estado de la remisión",
                        ["Digital adjunta", "En papel", "Pendiente", "Sin número"],
                        key="est_rem",
                        help=(
                            "Digital adjunta: se subió el archivo PDF/imagen aquí. "
                            "En papel: viene físicamente con el embarque. "
                            "Pendiente: el cliente aún no la envía. "
                            "Sin número: existe la remisión pero no tiene folio visible."
                        ),
                    )
                with cr2r:
                    ext_list    = sorted({e.lstrip(".") for e in FORMATOS_VALIDOS})
                    archivo_rem = st.file_uploader(
                        "PDF o imagen de la remisión",
                        type=ext_list,
                        key=f"uploader_rem_{st.session_state['upload_key']}",
                        help="Sube el PDF o foto de la remisión del cliente.",
                    )
                    if archivo_rem is not None:
                        if st.button("📎 Procesar remisión", key="btn_rem"):
                            with st.spinner("Procesando remisión..."):
                                rem_bytes, msg_rem = guardar_remision(archivo_rem)
                            if rem_bytes:
                                st.session_state["_bytes_pdf_remision"] = rem_bytes
                                st.success(f"✅ {msg_rem}")
                            else:
                                st.error(msg_rem)
    
                    if st.session_state.get("_bytes_pdf_remision"):
                        st.caption(f"✅ Remisión lista ({len(st.session_state['_bytes_pdf_remision'])//1024} KB)")
                    else:
                        st.caption("Sin remisión digital — se puede continuar.")
            else:
                estado_remision = ""
    
            # ── Observaciones ─────────────────────────────────────────────────────
            obs_auto = generar_observaciones(
                fletera, tipo_entrega, condicion_flete,
                con_remision, empresa_remision, numero_remision,
                estado_remision=estado_remision,
            )
            st.caption("**Estructura logística generada automáticamente:**")
            st.code(obs_auto, language=None)
    
            notas_adicionales = st.text_area(
                "Notas adicionales (operativas, opcionales)",
                value="", height=60, key="notas_adic",
                help="Se añadirán al final. Usa este campo para información no estandarizada.",
            )
            observaciones = (
                obs_auto
                + (f" | {notas_adicionales.strip()}" if notas_adicionales.strip() else "")
            )
    
            # ── Guardar en session_state ───────────────────────────────────────────
            st.session_state["datos_logisticos"] = {
                "remitente_nombre":         rem_nombre,
                "remitente_rfc":            rem_rfc,
                "remitente_tel":            rem_tel,
                "remitente_direccion":      rem_dir,
                "destinatario_nombre":      dest_nombre,
                "destinatario_rfc":         dest_rfc,
                "destinatario_direccion":   dest_dir,
                "destinatario_cp":          dest_cp,
                "destinatario_tel":         dest_tel,
                "destinatario_contacto":    dest_contacto,
                "destinatario_referencias": dest_refs,
                "fletera":                  fletera,
                "tipo_entrega":             tipo_entrega,
                "condicion_flete":          condicion_flete,
                "con_remision":             con_remision,
                "empresa_remision":         empresa_remision,
                "numero_remision":          numero_remision,
                "estado_remision":          estado_remision,
                "ruta_pdf_remision":        "ok" if st.session_state.get("_bytes_pdf_remision") else "",
                "observaciones":            observaciones,
                "orden_compra":             datos_bind.get("orden_compra", ""),
                "pedido_interno":           pedido_interno,
            }

_paso3(datos_bind)

st.divider()

# ──────────────────────────────────────────────────────────────────────────────
# PASO 4 — Generar paquete de embarque
# ──────────────────────────────────────────────────────────────────────────────

st.markdown("### 4 — Generar paquete de embarque")

datos_log = st.session_state.get("datos_logisticos", {})

if not datos_bind:
    st.info("Completa los pasos anteriores para habilitar la generación.")
else:
    # ── Asistente de Consistencia ──────────────────────────────────────────────
    resultados_val = validar_consistencia(datos_bind, datos_log)
    errores_val    = [r for r in resultados_val if r["nivel"] == "ERROR"]
    warnings_val   = [r for r in resultados_val if r["nivel"] == "WARNING"]

    if errores_val:
        for e in errores_val:
            st.error(f"🚫 **{e['mensaje']}**  \n{e['accion_sugerida']}")

    if warnings_val:
        st.warning("⚠️ **INCONSISTENCIAS DETECTADAS**")
        for w in warnings_val:
            with st.expander(f"⚠ {w['mensaje']}", expanded=False):
                if w["valor_bind"]:
                    st.markdown(f"**Bind indica:** {w['valor_bind']}")
                if w["valor_logistica"]:
                    st.markdown(f"**Hoja logística tiene:** {w['valor_logistica']}")
                if w["accion_sugerida"]:
                    st.markdown(f"**Acción sugerida:** {w['accion_sugerida']}")
        confirmar = st.checkbox(
            "☑ Revisé las diferencias y deseo continuar con la generación.",
            key="warnings_confirmados",
        )
    else:
        confirmar = True

    # Info del paquete
    if datos_log.get("con_remision"):
        tiene_rem = bool(st.session_state.get("_bytes_pdf_remision"))
        if tiene_rem:
            st.info("📄 Paquete: **Hoja Logística → Remisión cliente → Hoja de Salida Bind**")
        else:
            st.info("📄 Paquete: **Hoja Logística → Hoja de Salida Bind** *(remisión sin archivo digital)*")
    else:
        st.info("📄 Paquete: **Hoja Logística → Hoja de Salida Bind**")

    btn_disabled = bool(errores_val) or (bool(warnings_val) and not confirmar)

    if st.button(
        "📦 Generar Paquete de Embarque",
        type="primary",
        disabled=btn_disabled,
        key="btn_generar",
    ):
        with st.spinner("Generando paquete PDF..."):
            try:
                edited_df = st.session_state.get("_partidas_df")

                # ── Preparar productos para PDF (salida principal) ────────────
                if edited_df is not None and not edited_df.empty:
                    productos_para_pdf = [
                        {
                            "codigo":       row["Código"],
                            "descripcion":  row["Descripción"],
                            "unidad":       row["Unidad"],
                            "cantidad":     row["Cant. Bind"],
                            "cantidad_hoy": row["A embarcar hoy"],
                        }
                        for _, row in edited_df.iterrows()
                    ]
                else:
                    productos_para_pdf = datos_bind.get("productos", [])

                # Agregar productos de salidas adicionales (usando cantidades editadas)
                for _i_adic, _adic in enumerate(st.session_state.get("_datos_adicionales", [])):
                    _edited_adic = st.session_state.get(f"_partidas_df_adic_{_i_adic}")
                    if _edited_adic is not None and not _edited_adic.empty:
                        for _, row in _edited_adic.iterrows():
                            productos_para_pdf.append({
                                "codigo":       row["Código"],
                                "descripcion":  row["Descripción"],
                                "unidad":       row["Unidad"],
                                "cantidad":     row["Cant. Bind"],
                                "cantidad_hoy": row["A embarcar hoy"],
                            })
                    else:
                        for p in _adic["datos_bind"].get("productos", []):
                            qty = _to_float(p.get("cantidad", 0))
                            productos_para_pdf.append({
                                "codigo":       p.get("codigo", ""),
                                "descripcion":  p.get("descripcion", ""),
                                "unidad":       p.get("unidad", ""),
                                "cantidad":     qty,
                                "cantidad_hoy": qty,
                            })

                # Folio combinado para el encabezado de la hoja logística
                _folios_pdf = [datos_bind.get("folio", "")] + [
                    a["datos_bind"].get("folio", "")
                    for a in st.session_state.get("_datos_adicionales", [])
                ]
                datos_bind_pdf = {
                    **datos_bind,
                    "productos": productos_para_pdf,
                    "folio": " / ".join(filter(None, _folios_pdf)),
                }

                # ── 1. Generar hoja logística en memoria ──────────────────────
                bytes_log, filename_log = generar_hoja_logistica(datos_bind_pdf, datos_log)

                # ── 2. Combinar PDF en memoria ────────────────────────────────
                bytes_rem = (
                    st.session_state.get("_bytes_pdf_remision")
                    if datos_log.get("con_remision")
                    else None
                )
                # Recopilar todos los Bind PDFs (principal + adicionales)
                _bytes_binds = [b for b in [
                    st.session_state.get("_bytes_pdf_original"),
                    *[a.get("bytes") for a in st.session_state.get("_datos_adicionales", [])],
                ] if b]
                bytes_paq = combinar_paquete_embarque(
                    bytes_log,
                    _bytes_binds if len(_bytes_binds) > 1 else (_bytes_binds[0] if _bytes_binds else None),
                    bytes_rem,
                )
                # Slug incluye todos los folios
                _folios_slug = [datos_bind.get("folio", "SIN_FOLIO")] + [
                    a["datos_bind"].get("folio","") for a in st.session_state.get("_datos_adicionales",[])
                ]
                folio_slug = "_".join(filter(None, _folios_slug))
                from datetime import datetime as _dt
                filename_paq  = f"EMBARQUE_{folio_slug}_{_dt.now().strftime('%Y%m%d_%H%M%S')}.pdf"

                # ── 3. Subir paquete a Supabase Storage ───────────────────────
                ruta_storage = subir_pdf(bytes_paq, filename_paq)
                st.session_state["_bytes_paquete"]        = bytes_paq
                st.session_state["_filename_paquete"]     = filename_paq
                st.session_state["_ruta_storage_paquete"] = ruta_storage

                # ── 3. Crear o recuperar salida en DB ─────────────────────────
                salida_id = st.session_state.get("salida_id")
                salida_db = st.session_state.get("salida_db")

                if salida_id is None:
                    # Primera vez: crear salida con las cantidades Bind originales
                    prods_para_salida = (
                        [
                            {
                                "codigo":      row["Código"],
                                "descripcion": row["Descripción"],
                                "unidad":      row["Unidad"],
                                "cantidad":    row["Cant. Bind"],
                            }
                            for _, row in edited_df.iterrows()
                        ]
                        if edited_df is not None and not edited_df.empty
                        else datos_bind.get("productos", [])
                    )
                    salida_id = crear_salida(
                        {
                            "folio_bind":        datos_bind.get("folio", ""),
                            "fecha_salida":      datos_bind.get("fecha", ""),
                            "cliente":           datos_bind.get("cliente", ""),
                            "rfc_cliente":       datos_bind.get("rfc_cliente", ""),
                            "direccion_cliente": datos_bind.get("direccion_cliente", ""),
                            "tel_cliente":       datos_bind.get("tel_cliente", ""),
                            "orden_compra":      datos_bind.get("orden_compra", ""),
                            "notas":             datos_bind.get("notas", ""),
                            "ruta_pdf_original": "",
                        },
                        prods_para_salida,
                    )
                    st.session_state["salida_id"] = salida_id
                    salida_recien  = get_salida_por_id(salida_id)
                    partidas_db    = salida_recien["partidas"] if salida_recien else []
                else:
                    # Folio existente: usar partidas ya en DB
                    partidas_db = salida_db["partidas"]

                # ── 4. Mapear cantidades hoy → partida_id (salida principal) ──
                partidas_cantidades = []
                if edited_df is not None and not edited_df.empty:
                    for i, (_, row) in enumerate(edited_df.iterrows()):
                        if i >= len(partidas_db):
                            break
                        qty = _to_float(row["A embarcar hoy"])
                        if qty > 0:
                            partidas_cantidades.append({
                                "partida_id":        partidas_db[i]["id"],
                                "cantidad_embarcada": qty,
                            })

                # ── 4b. Crear/recuperar salidas adicionales y sus partidas ────
                all_salida_ids = [salida_id]
                for i_adic, adic in enumerate(st.session_state.get("_datos_adicionales", [])):
                    datos_adic  = adic["datos_bind"]
                    salida_adic = adic.get("salida_db")
                    edited_adic = st.session_state.get(f"_partidas_df_adic_{i_adic}")

                    if salida_adic:
                        sid_adic      = salida_adic["id"]
                        partidas_adic = salida_adic.get("partidas", [])
                    else:
                        prods_adic = [
                            {
                                "codigo":      p.get("codigo",""),
                                "descripcion": p.get("descripcion",""),
                                "unidad":      p.get("unidad",""),
                                "cantidad":    _to_float(p.get("cantidad",0)),
                            }
                            for p in datos_adic.get("productos", [])
                        ]
                        sid_adic = crear_salida(
                            {
                                "folio_bind":        datos_adic.get("folio",""),
                                "fecha_salida":      datos_adic.get("fecha",""),
                                "cliente":           datos_adic.get("cliente",""),
                                "rfc_cliente":       datos_adic.get("rfc_cliente",""),
                                "direccion_cliente": datos_adic.get("direccion_cliente",""),
                                "tel_cliente":       datos_adic.get("tel_cliente",""),
                                "orden_compra":      datos_adic.get("orden_compra",""),
                                "notas":             datos_adic.get("notas",""),
                                "ruta_pdf_original": "",
                            },
                            prods_adic,
                        )
                        salida_adic_full = get_salida_por_id(sid_adic)
                        partidas_adic    = salida_adic_full.get("partidas", []) if salida_adic_full else []

                    all_salida_ids.append(sid_adic)

                    # Embarcar cantidades de la salida adicional: usar lo editado
                    # en la tabla si existe, si no, el pendiente completo
                    if edited_adic is not None and not edited_adic.empty:
                        for i, (_, row) in enumerate(edited_adic.iterrows()):
                            if i >= len(partidas_adic):
                                break
                            qty = _to_float(row["A embarcar hoy"])
                            if qty > 0:
                                partidas_cantidades.append({
                                    "partida_id":        partidas_adic[i]["id"],
                                    "cantidad_embarcada": qty,
                                })
                    else:
                        for p in partidas_adic:
                            qty = _to_float(p.get("cantidad_pendiente", p.get("cantidad_bind", 0)))
                            if qty > 0:
                                partidas_cantidades.append({
                                    "partida_id":        p["id"],
                                    "cantidad_embarcada": qty,
                                })

                # ── 5. Registrar correcciones en log de auditoría ─────────────
                original = st.session_state.get("datos_bind_original") or {}
                _campos  = ["folio", "cliente", "rfc_cliente", "fecha",
                            "orden_compra", "tel_cliente", "direccion_cliente", "notas"]
                for _c in _campos:
                    v_orig  = str(original.get(_c, ""))
                    v_final = str(datos_bind.get(_c, ""))
                    if v_orig != v_final and v_final:
                        registrar_cambio(
                            "salida", salida_id, _c, v_orig, v_final, "MANUAL"
                        )

                # ── 6. Crear embarque en DB (con todas las salidas) ───────────
                embarque_id = crear_embarque(
                    {
                        **datos_log,
                        "ruta_pdf_generado":     ruta_storage,
                        "warning_confirmado":    bool(warnings_val),
                        "detalle_warnings":      detalle_warnings_json(resultados_val),
                        "correcciones_manuales": "",
                    },
                    all_salida_ids,
                    partidas_cantidades,
                )
                st.session_state["embarque_id"] = embarque_id

                st.success(f"✅ Paquete generado y guardado en Storage ({len(bytes_paq)//1024} KB)")

            except Exception as ex:
                st.error(f"Error al generar paquete: {ex}")
                st.code(traceback.format_exc())

    # ── Acciones post-generación ───────────────────────────────────────────────
    bytes_paq    = st.session_state.get("_bytes_paquete")
    filename_paq = st.session_state.get("_filename_paquete")
    embarque_id  = st.session_state.get("embarque_id")

    if bytes_paq:
        st.markdown("---")
        if not st.session_state.get("en_bandeja"):
            st.info("📦 **Siguiente paso:** descarga el PDF y luego usa **➕ Agregar a Bandeja** para enviarlo a Planta desde la sección Bandeja.")
        col_dl, col_add, col_mail = st.columns(3)

        with col_dl:
            st.download_button(
                "⬇ Descargar PDF",
                data=bytes_paq,
                file_name=filename_paq or "embarque.pdf",
                mime="application/pdf",
                key="btn_dl",
            )

        with col_add:
            if st.button("➕ Agregar a Bandeja", type="primary", key="btn_add_bandeja"):
                _agregar_a_bandeja(embarque_id)

        with col_mail:
            datos_msg = construir_datos_mensaje(datos_bind, datos_log)
            ruta_storage = st.session_state.get("_ruta_storage_paquete", "")
            if st.button("✉ Abrir correo", key="btn_mail"):
                from modules.messaging import abrir_mailto
                with st.spinner("Generando link..."):
                    url_pdf = generar_url_firmada(ruta_storage) if ruta_storage else ""
                abrir_mailto(datos_msg, url_pdf)

        datos_msg = construir_datos_mensaje(datos_bind, datos_log)
        ruta_storage = st.session_state.get("_ruta_storage_paquete", "")
        url_pdf_teams = generar_url_firmada(ruta_storage) if ruta_storage else ""
        msg_teams = construir_mensaje_teams(datos_msg, url_pdf_teams)
        st.text_area("Mensaje Teams (copiar):", value=msg_teams, height=90, key="teams_ind")

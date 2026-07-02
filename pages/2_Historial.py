"""Historial de Salidas y Embarques — modelo v2 (Salida-céntrico)."""

import io
import os
import sys
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import APP_NAME, VERSION, ensure_dirs
from modules.database import (
    init_database,
    get_salidas_filtradas,
    get_historial_detalle,
    cancelar_embarque,
    get_reporte_exportacion,
)
from modules.sidebar import render_sidebar
from modules.auth import require_auth, puede


@st.cache_data(ttl=60, show_spinner=False)
def _salidas_cached(folio, cliente, estado, fecha_desde, fecha_hasta, pedido_interno):
    return get_salidas_filtradas(
        folio=folio, cliente=cliente, estado=estado,
        fecha_desde=fecha_desde, fecha_hasta=fecha_hasta,
        pedido_interno=pedido_interno,
    )


@st.cache_data(ttl=60, show_spinner=False)
def _detalle_cached(salida_ids_tuple):
    return get_historial_detalle(list(salida_ids_tuple))

# ──────────────────────────────────────────────────────────────────────────────
# Configuración
# ──────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title=f"Historial — {APP_NAME}",
    page_icon="📋",
    layout="wide",
)

ensure_dirs()
init_database()
require_auth("historial")
if st.session_state.get("_current_page") != "historial":
    for _k in list(st.session_state.keys()):
        if _k.startswith(("_hist_open_", "_ev_bytes_", "_conf_cancel_hist_")):
            del st.session_state[_k]
    for _k in ("_rep_excel", "_rep_csv", "_rep_filas"):
        st.session_state.pop(_k, None)
st.session_state["_current_page"] = "historial"
render_sidebar(APP_NAME, VERSION)

st.markdown("""
<style>
div[data-testid="stButton"] > button {
    text-align: left !important;
    justify-content: flex-start !important;
    padding-left: 0.75rem !important;
}
div[data-testid="stButton"] > button > div,
div[data-testid="stButton"] > button p {
    text-align: left !important;
    justify-content: flex-start !important;
    width: 100% !important;
}
</style>
""", unsafe_allow_html=True)


def _fmt_dt(val, chars=16) -> str:
    """Convierte datetime o str a string legible truncado a `chars` caracteres."""
    if val is None:
        return ""
    return str(val)[:chars]


# ──────────────────────────────────────────────────────────────────────────────
# Encabezado
# ──────────────────────────────────────────────────────────────────────────────

st.markdown("## 📋 Historial de Salidas y Embarques")
st.caption("Vista por Hoja de Salida Bind, agrupando todos sus embarques y cantidades.")
st.divider()

# ──────────────────────────────────────────────────────────────────────────────
# Helpers de visualización
# ──────────────────────────────────────────────────────────────────────────────

_ESTADO_SALIDA_ICON = {
    "Pendiente":  "🔴",
    "Parcial":    "🟡",
    "Completada": "🟢",
}

_ESTADO_EMB_ICON = {
    "Preparado":              "📄",
    "Enviado a Planta":       "🚚",
    "Embarcado sin guía":     "📦",
    "Guía capturada":         "✅",
    "Entregado a fletera":    "🤝",
    "Cerrado":                "🔒",
    "Cancelado":              "❌",
}

_ESTADOS_CANCELABLES = {
    "Preparado", "Enviado a Planta", "Embarcado sin guía",
}


def _fmt_qty(v) -> str:
    """Formatea float: entero si es .0, 2 decimales si no."""
    try:
        f = float(v)
        return str(int(f)) if f == int(f) else f"{f:.2f}"
    except (TypeError, ValueError):
        return str(v) if v else "—"


def _df_partidas_resumen(partidas: list) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "Código":      p.get("codigo", ""),
            "Descripción": p.get("descripcion", ""),
            "Unidad":      p.get("unidad", ""),
            "Bind":        _fmt_qty(p.get("cantidad_bind", 0)),
            "Embarcada":   _fmt_qty(p.get("cantidad_embarcada", 0)),
            "Pendiente":   _fmt_qty(p.get("cantidad_pendiente", 0)),
            "Estado":      p.get("estado", ""),
        }
        for p in partidas
    ])


def _df_partidas_embarque(partidas: list) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "Código":      p.get("codigo", ""),
            "Descripción": p.get("descripcion", ""),
            "Unidad":      p.get("unidad", ""),
            "En este embarque": _fmt_qty(p.get("cantidad_en_embarque", 0)),
        }
        for p in partidas
    ])


# ──────────────────────────────────────────────────────────────────────────────
# Filtros
# ──────────────────────────────────────────────────────────────────────────────

# Prefiltro desde sidebar (contadores operativos)
if "_hist_prefiltro_estado" in st.session_state:
    st.session_state["hist_estado"] = st.session_state.pop("_hist_prefiltro_estado")

with st.expander("🔍 Filtros de búsqueda", expanded=True):
    f1, f2, f3 = st.columns([2, 2, 2])
    filtro_folio         = f1.text_input("Folio Bind",  placeholder="Ej. AFAD5267",
        help="Búsqueda parcial — muestra todos los folios que contengan el texto.")
    filtro_cliente       = f2.text_input("Cliente",      placeholder="Nombre parcial",
        help="Búsqueda parcial por nombre de cliente.")
    filtro_pedido_interno = f3.text_input("Pedido interno Planta", placeholder="Ej. P001",
        help="Busca por número de pedido interno. Funciona aunque el embarque tenga varios pedidos separados por coma.")

    f4, f5, f6 = st.columns([2, 2, 2])
    filtro_estado  = f4.selectbox(
        "Estado salida",
        ["Todos", "Pendiente", "Parcial", "Completada"],
        key="hist_estado",
        help="Pendiente: ninguna partida embarcada. Parcial: algunas partidas embarcadas. Completada: todas las partidas cubiertas.",
    )
    filtro_desde   = f5.date_input(
        "Fecha desde", value=date.today() - timedelta(days=90),
        key="hist_desde",
        help="Filtra salidas con fecha de emisión igual o posterior a esta fecha. Por defecto: últimos 90 días.",
    )
    filtro_hasta   = f6.date_input("Fecha hasta", value=None,
        key="hist_hasta",
        help="Filtra salidas con fecha de emisión igual o anterior a esta fecha.")
    buscar = st.button("🔍 Buscar", type="primary")

# ──────────────────────────────────────────────────────────────────────────────
# Consulta
# ──────────────────────────────────────────────────────────────────────────────

if buscar:
    _salidas_cached.clear()

estado_q  = "" if filtro_estado == "Todos" else filtro_estado
desde_str = str(filtro_desde) if filtro_desde else ""
hasta_str = str(filtro_hasta) if filtro_hasta else ""

salidas = _salidas_cached(
    filtro_folio, filtro_cliente, estado_q,
    desde_str, hasta_str, filtro_pedido_interno,
)

# ──────────────────────────────────────────────────────────────────────────────
# Resultados
# ──────────────────────────────────────────────────────────────────────────────

if not salidas:
    _fecha_restrictiva = filtro_desde and (date.today() - filtro_desde).days < 365
    _filtros_activos   = any([filtro_folio, filtro_cliente, filtro_pedido_interno,
                               filtro_estado not in ("", "Todos"), filtro_hasta])
    st.warning("No se encontraron salidas con los criterios actuales.")
    if _fecha_restrictiva or _filtros_activos:
        _hint_partes = []
        if _fecha_restrictiva:
            _hint_partes.append(f"el rango de fechas cubre solo desde **{filtro_desde.strftime('%d/%m/%Y')}**")
        if filtro_estado not in ("", "Todos"):
            _hint_partes.append(f"el estado está filtrado a **{filtro_estado}**")
        if filtro_folio or filtro_cliente or filtro_pedido_interno:
            _hint_partes.append("hay filtros de texto activos")
        st.caption("Posible causa: " + " · ".join(_hint_partes) + ".")
        if st.button("↩ Ampliar búsqueda — quitar fechas y estado", key="btn_ampliar_hist"):
            st.session_state["hist_desde"] = date(2020, 1, 1)
            st.session_state["hist_hasta"] = None
            st.session_state["hist_estado"] = "Todos"
            _salidas_cached.clear()
            st.rerun()
    st.stop()

st.markdown(f"**{len(salidas)} salida(s) encontrada(s)**")

# ── Exportación ───────────────────────────────────────────────────────────────
_COL_NAMES = {
    "folio_bind":        "Folio Bind",
    "fecha_salida":      "Fecha Salida",
    "cliente":           "Cliente",
    "rfc_cliente":       "RFC",
    "orden_compra":      "OC Cliente",
    "estado_salida":     "Estado Salida",
    "codigo":            "Código",
    "descripcion":       "Descripción",
    "unidad":            "Unidad",
    "cantidad_bind":     "Cant. Bind",
    "total_embarcado":   "Total Embarcado",
    "pendiente":         "Pendiente",
    "estado_partida":    "Estado Partida",
    "pedido_interno":    "Pedido Interno",
    "fecha_embarque":    "Fecha Embarque",
    "fletera":           "Fletera",
    "tipo_entrega":      "Tipo Entrega",
    "condicion_flete":   "Condición Flete",
    "en_este_embarque":  "En este embarque",
    "estado_embarque":   "Estado Embarque",
    "guias":             "Guía(s)",
    "fecha_guia":        "Fecha Guía",
    "pdf_generado":      "PDF",
}

with st.expander("📊 Exportar informe", expanded=False):
    st.caption(
        "Una fila por (partida × embarque). "
        "Los filtros del historial se aplican automáticamente; "
        "el periodo del informe acota aún más."
    )
    _hoy   = datetime.now().date()
    _pm    = _hoy.replace(day=1)   # primer día del mes actual

    _ei1, _ei2 = st.columns(2)
    _exp_desde = _ei1.date_input(
        "Periodo desde", value=_pm, key="exp_desde",
        help="Filtra por fecha de la salida Bind.",
    )
    _exp_hasta = _ei2.date_input(
        "Periodo hasta", value=_hoy, key="exp_hasta",
    )

    # Combinar con filtros del historial (toma el más restrictivo)
    _fd = max(filtro_desde, _exp_desde) if filtro_desde else _exp_desde
    _fh = min(filtro_hasta, _exp_hasta) if filtro_hasta else _exp_hasta

    st.caption(
        f"Período aplicado: **{_fd.strftime('%d/%m/%Y')}** → **{_fh.strftime('%d/%m/%Y')}**"
        + (f" | Folio: *{filtro_folio}*" if filtro_folio else "")
        + (f" | Cliente: *{filtro_cliente}*" if filtro_cliente else "")
        + (f" | Pedido: *{filtro_pedido_interno}*" if filtro_pedido_interno else "")
    )

    if st.button("🔄 Generar informe", key="btn_gen_informe"):
        with st.spinner("Consultando base de datos..."):
            _filas = get_reporte_exportacion(
                folio=filtro_folio,
                cliente=filtro_cliente,
                estado=estado_q,
                fecha_desde=str(_fd),
                fecha_hasta=str(_fh),
                pedido_interno=filtro_pedido_interno,
            )
        if not _filas:
            st.warning("No hay datos para exportar con los filtros actuales.")
        else:
            _df = pd.DataFrame(_filas).rename(columns=_COL_NAMES)
            _buf = io.BytesIO()
            _df.to_excel(_buf, index=False, engine="openpyxl")
            st.session_state["_rep_excel"] = _buf.getvalue()
            st.session_state["_rep_csv"]   = _df.to_csv(index=False).encode("utf-8-sig")
            st.session_state["_rep_filas"] = len(_df)
            st.rerun()

    if st.session_state.get("_rep_excel"):
        _ts = datetime.now().strftime("%Y%m%d")
        _n  = st.session_state.get("_rep_filas", 0)
        st.success(f"✅ Informe listo — {_n} fila(s)")
        _dc1, _dc2 = st.columns(2)
        _dc1.download_button(
            "⬇ Descargar Excel (.xlsx)",
            data=st.session_state["_rep_excel"],
            file_name=f"embarques_{_ts}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="dl_xlsx",
            use_container_width=True,
        )
        _dc2.download_button(
            "⬇ Descargar CSV (.csv)",
            data=st.session_state["_rep_csv"],
            file_name=f"embarques_{_ts}.csv",
            mime="text/csv",
            key="dl_csv",
            use_container_width=True,
        )

st.divider()

# Carga batch: partidas + embarques de todas las salidas visibles en 4 queries
_detalle = _detalle_cached(tuple(s["id"] for s in salidas))

for sal in salidas:
    estado_sal  = sal.get("estado", "Pendiente")
    icon_sal    = _ESTADO_SALIDA_ICON.get(estado_sal, "⚪")
    n_emb       = int(sal.get("num_embarques", 0) or 0)
    n_tot       = int(sal.get("total_partidas", 0) or 0)
    n_pend      = int(sal.get("partidas_pendientes", 0) or 0)
    fecha_sal   = sal.get("fecha_salida", "")
    folio_bind  = sal.get("folio_bind", "—")
    cliente     = sal.get("cliente", "—")

    titulo = (
        f"{icon_sal} **{folio_bind}** &nbsp;|&nbsp; {cliente} &nbsp;|&nbsp; "
        f"{fecha_sal} &nbsp;|&nbsp; "
        f"{n_emb} embarque(s) &nbsp;|&nbsp; "
        f"Pendientes: {n_pend}/{n_tot}"
    )

    _key_open = f"_hist_open_{sal['id']}"
    _is_open  = st.session_state.get(_key_open, False)

    if st.button(
        f"{'▼' if _is_open else '▶'}  {titulo}",
        key=f"_tog_{sal['id']}",
        use_container_width=True,
    ):
        _new_open = not _is_open
        st.session_state[_key_open] = _new_open
        if not _new_open:
            # Limpiar fotos cargadas al cerrar el registro
            for _k in list(st.session_state.keys()):
                if _k.startswith(f"_ev_bytes_{sal['id']}_"):
                    del st.session_state[_k]
        st.rerun()

    if not _is_open:
        continue

    with st.container(border=True):

        _sal_detalle = _detalle.get(sal["id"], {})
        partidas     = _sal_detalle.get("partidas", [])
        embarques    = _sal_detalle.get("embarques", [])

        # ── Metadatos de la salida ────────────────────────────────────────────
        mc1, mc2, mc3 = st.columns(3)
        mc1.markdown(f"**Cliente:** {cliente}")
        mc1.markdown(f"**RFC:** {sal.get('rfc_cliente','—')}")
        mc2.markdown(f"**Fecha salida:** {fecha_sal}")
        mc2.markdown(f"**Orden compra:** {sal.get('orden_compra','—')}")
        mc3.markdown(f"**Estado salida:** {icon_sal} {estado_sal}")
        mc3.markdown(f"**Registrado:** {_fmt_dt(sal.get('created_at'))}")

        if sal.get("notas"):
            st.caption(f"Notas Bind: {sal['notas']}")

        st.markdown("---")

        # ── Tabla de partidas (totales acumulados) ────────────────────────────
        if partidas:
            st.markdown("**Partidas — cantidades acumuladas:**")
            st.dataframe(
                _df_partidas_resumen(partidas),
                hide_index=True,
                use_container_width=True,
                column_config={
                    "Bind":      st.column_config.TextColumn(width="small"),
                    "Embarcada": st.column_config.TextColumn(width="small"),
                    "Pendiente": st.column_config.TextColumn(width="small"),
                    "Estado":    st.column_config.TextColumn(width="small"),
                },
            )
        else:
            st.caption("Sin partidas registradas.")

        st.markdown("---")

        # ── Embarques de esta salida ──────────────────────────────────────────
        if not embarques:
            st.info("Esta salida aún no tiene embarques generados.")
        else:
            st.markdown(f"**{n_emb} Embarque(s) generado(s):**")

            for emb in embarques:

                estado_emb  = emb.get("estado_embarque", "Preparado")
                icon_emb    = _ESTADO_EMB_ICON.get(estado_emb, "📦")
                guias_emb   = emb.get("guias", [])
                n_guias     = len(guias_emb)
                fecha_gen   = _fmt_dt(emb.get("created_at"))

                with st.container(border=True):
                    # ── Cabecera del embarque ─────────────────────────────────
                    ec1, ec2, ec3, ec4 = st.columns([3, 3, 2, 2])
                    ec1.markdown(
                        f"**Fletera:** {emb.get('fletera','—')}  \n"
                        f"**Tipo:** {emb.get('tipo_entrega','—')} / "
                        f"{emb.get('condicion_flete','—')}"
                    )
                    ec2.markdown(
                        f"**Destinatario:** {emb.get('destinatario_nombre','—')}  \n"
                        f"**CP:** {emb.get('destinatario_cp','—')}"
                    )
                    ec3.markdown(
                        f"**Estado:** {icon_emb} {estado_emb}  \n"
                        f"**Generado:** {fecha_gen}"
                    )
                    ec4.markdown(
                        f"**Guías:** {n_guias}  \n"
                        + ("Sin guía capturada" if not guias_emb else
                           f"No. {guias_emb[0].get('numero_guia','—')}"
                           if n_guias == 1 else f"{n_guias} guías registradas")
                    )

                    # ── Remisión ──────────────────────────────────────────────
                    if emb.get("con_remision"):
                        rem_txt = (
                            f"Remisión {emb.get('empresa_remision','—')}"
                            f" No. {emb.get('numero_remision','—')}"
                            f" — {emb.get('estado_remision','')}"
                        )
                        st.caption(f"📄 {rem_txt}")

                    # ── Partidas en este embarque ─────────────────────────────
                    partidas_emb = emb.get("partidas", [])
                    if partidas_emb:
                        st.dataframe(
                            _df_partidas_embarque(partidas_emb),
                            hide_index=True,
                            use_container_width=True,
                            column_config={
                                "En este embarque": st.column_config.TextColumn(
                                    width="small"
                                ),
                            },
                        )

                    # ── Guías detalle ─────────────────────────────────────────
                    if guias_emb:
                        for g in guias_emb:
                            _gk = f"{sal['id']}_{emb['id']}_{g.get('id','')}"
                            _ruta_ev = g.get("ruta_evidencia", "")
                            _num_g   = g.get("numero_guia") or "—"
                            _linea   = (
                                f"**No. {_num_g}** &nbsp;|&nbsp; "
                                f"{g.get('fecha_embarque_real','—')} "
                                f"{g.get('hora_embarque','')} &nbsp;|&nbsp; "
                                f"Entregó: {g.get('quien_entrego','—')}"
                            )
                            if _ruta_ev:
                                _gc1, _gc2 = st.columns([6, 1])
                                _gc1.markdown(_linea)
                                if _gc2.button("📷 Foto", key=f"foto_{_gk}",
                                               help="Ver foto de evidencia"):
                                    _ev_key = f"_ev_bytes_{_gk}"
                                    if _ev_key not in st.session_state:
                                        try:
                                            from modules.storage import descargar_evidencia_bytes
                                            st.session_state[_ev_key] = descargar_evidencia_bytes(_ruta_ev)
                                        except Exception as _e:
                                            st.session_state[_ev_key] = None
                                            st.warning(f"No se pudo cargar la foto: {_e}")
                                    st.rerun()
                                if st.session_state.get(f"_ev_bytes_{_gk}"):
                                    st.image(st.session_state[f"_ev_bytes_{_gk}"],
                                             caption=f"Evidencia — guía {_num_g}",
                                             use_container_width=True)
                            else:
                                st.markdown(_linea)

                    # ── Acciones ──────────────────────────────────────────────
                    _k = f"{sal['id']}_{emb['id']}"
                    ruta_pdf = emb.get("ruta_pdf_generado", "")
                    btn_lbl_guia = (
                        "➕ Agregar guía" if n_guias > 0 else "🧾 Capturar guía"
                    )
                    pa, pb, pc, _ = st.columns([1, 1, 1, 3])

                    if ruta_pdf:
                        with pa:
                            try:
                                from modules.storage import descargar_pdf_bytes
                                pdf_dl = descargar_pdf_bytes(ruta_pdf)
                                st.download_button(
                                    "⬇ PDF",
                                    data=pdf_dl,
                                    file_name=ruta_pdf.split("/")[-1],
                                    mime="application/pdf",
                                    key=f"dl_emb_{_k}",
                                )
                            except Exception:
                                st.caption("PDF no disponible")
                    else:
                        pa.caption("⚠ PDF no encontrado.")

                    if estado_emb not in ("Cancelado", "Cerrado", "Guía capturada"):
                        with pb:
                            if st.button(btn_lbl_guia, key=f"guia_emb_{_k}",
                                         type="primary"):
                                st.session_state["_nav_to_guias_from_hist"] = True
                                st.session_state["embarque_seleccionado"] = emb["id"]
                                st.switch_page("pages/5_Guias.py")

                    if puede("bandeja") and estado_emb in _ESTADOS_CANCELABLES:
                        with pc:
                            if st.button("❌ Cancelar", key=f"cancel_hist_{_k}",
                                         help="Cancela definitivamente este embarque."):
                                st.session_state[f"_conf_cancel_hist_{_k}"] = True

                    if st.session_state.get(f"_conf_cancel_hist_{_k}"):
                        st.error(
                            f"⚠️ ¿Cancelar definitivamente este embarque "
                            f"(**{emb.get('fletera','?')} → {emb.get('destinatario_nombre','?')}**)?\n\n"
                            "Esta acción no se puede deshacer."
                        )
                        hc1, hc2 = st.columns(2)
                        if hc1.button("❌ Sí, cancelar", key=f"conf_ch_si_{_k}",
                                      use_container_width=True):
                            try:
                                cancelar_embarque(emb["id"])
                                st.session_state.pop(f"_conf_cancel_hist_{_k}", None)
                                st.warning("❌ Embarque cancelado.")
                                st.rerun()
                            except Exception as ex:
                                st.error(f"Error: {ex}")
                        if hc2.button("No, mantener", key=f"conf_ch_no_{_k}",
                                      use_container_width=True):
                            st.session_state.pop(f"_conf_cancel_hist_{_k}", None)
                            st.rerun()

                    # ── Observaciones del embarque ────────────────────────────
                    if emb.get("observaciones"):
                        st.caption(f"Obs: {emb['observaciones']}")

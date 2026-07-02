"""CSS global de la aplicación NSG. Llamar inject_css() en cada página."""
import streamlit as st

_CSS = """
<style>
/* ── Ocultar nav automática de Streamlit ── */
[data-testid="stSidebarNav"] { display: none; }

/* ── Títulos de página ── */
.titulo-nsg {
    color: #C0392B;
    font-size: 1.65rem;
    font-weight: 700;
    margin: 0 0 2px 0;
    letter-spacing: -0.3px;
    line-height: 1.2;
}
.subtitulo {
    color: #6B7280;
    font-size: 0.88rem;
    margin: 0 0 8px 0;
}

/* ── Etiqueta de sección con acento izquierdo rojo ── */
.seccion {
    background: #FFF7F6;
    border-left: 4px solid #C0392B;
    padding: 8px 14px;
    border-radius: 0 6px 6px 0;
    margin-bottom: 14px;
    font-weight: 600;
    color: #922B21;
    font-size: 0.92rem;
}

/* ── Badge azul de remisión ── */
.badge-remision {
    background: #2980b9;
    color: white;
    padding: 2px 10px;
    border-radius: 12px;
    font-size: 0.75rem;
    font-weight: 500;
    margin-left: 6px;
}

/* ── Sidebar: header de marca NSG (fallback sin logo) ── */
.nsg-brand {
    background: linear-gradient(135deg, #C0392B 0%, #7B241C 100%);
    border-radius: 8px;
    padding: 14px 10px 10px 10px;
    color: white;
    text-align: center;
    margin-bottom: 2px;
}
.nsg-brand-name {
    font-size: 1.5rem;
    font-weight: 800;
    letter-spacing: 3px;
    margin: 0;
    line-height: 1.1;
}
.nsg-brand-sub {
    font-size: 0.63rem;
    opacity: 0.85;
    letter-spacing: 1px;
    margin-top: 4px;
    text-transform: uppercase;
}

/* ── Sidebar: separador de rol ── */
.nsg-rol-chip {
    display: inline-block;
    background: #F3F4F6;
    color: #374151;
    border-radius: 20px;
    padding: 2px 10px;
    font-size: 0.72rem;
    font-weight: 500;
    border: 1px solid #E5E7EB;
}

/* ── Sidebar: indicadores de estado ── */
.nsg-stat-ok   { color: #16a34a; font-size: 0.8rem; }
.nsg-stat-warn { color: #d97706; font-size: 0.8rem; }
.nsg-stat-err  { color: #C0392B; font-size: 0.8rem; }

/* ── Contenedor de página con borde superior rojo ── */
.nsg-page-header {
    border-bottom: 2px solid #F3F4F6;
    padding-bottom: 10px;
    margin-bottom: 18px;
}

/* ════════════════════════════════════════════════════
   ZONAS DE CAPTURA — efecto tarjeta
   ════════════════════════════════════════════════════ */

/* Expanders (pasos 2, 3, etc.) */
[data-testid="stExpander"] {
    background: #F8F9FA;
    border: 1px solid #E5E7EB !important;
    border-radius: 8px !important;
    box-shadow: 0 1px 4px rgba(0,0,0,0.07);
}
[data-testid="stExpander"]:has(details[open]) {
    border-color: #C0392B !important;
    box-shadow: 0 2px 8px rgba(192,57,43,0.10);
}

/* File uploader */
[data-testid="stFileUploaderDropzone"] {
    background: #FFF8F7 !important;
    border: 2px dashed #D4A09A !important;
    border-radius: 8px !important;
    transition: border-color 0.2s;
}
[data-testid="stFileUploaderDropzone"]:hover {
    border-color: #C0392B !important;
}

/* Formularios (dentro de st.form) — fondo blanco para que los inputs contrasten */
[data-testid="stForm"] {
    background: #FFFFFF;
    border: 1px solid #E5E7EB;
    border-radius: 8px;
    padding: 16px 20px !important;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}

/* Inputs y textareas — borde claro en reposo, rojo NSG al enfocar */
input[type="text"],
input[type="password"],
input[type="email"],
input[type="number"],
textarea,
[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea,
[data-testid="stNumberInput"] input {
    background: #FFFFFF !important;
    border: 1.5px solid #D1D5DB !important;
    border-radius: 6px !important;
    color: #1F2937 !important;
}
input[type="text"]:focus,
input[type="password"]:focus,
input[type="email"]:focus,
input[type="number"]:focus,
textarea:focus,
[data-testid="stTextInput"] input:focus,
[data-testid="stTextArea"] textarea:focus,
[data-testid="stNumberInput"] input:focus {
    border-color: #C0392B !important;
    box-shadow: 0 0 0 3px rgba(192,57,43,0.12) !important;
    outline: none !important;
}

/* ════════════════════════════════════════════════════
   SIDEBAR OSCURO CORPORATIVO
   ════════════════════════════════════════════════════ */

section[data-testid="stSidebar"],
section[data-testid="stSidebar"] > div:first-child {
    background-color: #1E293B;
}

/* Texto general — cubre p, span, strong, label dentro del sidebar */
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] span,
section[data-testid="stSidebar"] strong,
section[data-testid="stSidebar"] label {
    color: #E2E8F0 !important;
}

/* Captions y texto secundario */
section[data-testid="stSidebar"] .stCaptionContainer p,
section[data-testid="stSidebar"] small {
    color: #64748B !important;
}

/* Dividers */
section[data-testid="stSidebar"] hr {
    border-color: rgba(255,255,255,0.10) !important;
}

/* Nav links — etiqueta dentro del page_link */
section[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"],
section[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"] p,
section[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"] span {
    color: #CBD5E1 !important;
    border-radius: 6px;
    border-left: 3px solid transparent;
    transition: background 0.15s, color 0.15s;
}
section[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"]:hover,
section[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"]:hover p,
section[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"]:hover span {
    background: rgba(192,57,43,0.18) !important;
    color: #FFFFFF !important;
    border-left: 3px solid #C0392B;
}

/* Metric en sidebar */
section[data-testid="stSidebar"] [data-testid="stMetricValue"] div {
    color: #F1F5F9 !important;
}
section[data-testid="stSidebar"] [data-testid="stMetricLabel"] p {
    color: #94A3B8 !important;
}

/* Expander (cambiar contraseña) */
section[data-testid="stSidebar"] details summary p,
section[data-testid="stSidebar"] details summary span,
section[data-testid="stSidebar"] details > summary,
section[data-testid="stSidebar"] [data-testid="stExpander"] summary,
section[data-testid="stSidebar"] .streamlit-expanderHeader,
section[data-testid="stSidebar"] .streamlit-expanderHeader p {
    color: #1F2937 !important;
}
section[data-testid="stSidebar"] details {
    border: 1px solid rgba(255,255,255,0.10) !important;
    border-radius: 6px !important;
    background: rgba(255,255,255,0.03) !important;
}

/* Inputs dentro del sidebar */
section[data-testid="stSidebar"] input {
    background: rgba(255,255,255,0.08) !important;
    color: #E2E8F0 !important;
    border-color: rgba(255,255,255,0.15) !important;
}
section[data-testid="stSidebar"] label {
    color: #94A3B8 !important;
}

/* Botones en sidebar — fondo oscuro, texto claro en el elemento raíz Y en los hijos */
section[data-testid="stSidebar"] button {
    background: rgba(255,255,255,0.08) !important;
    color: #CBD5E1 !important;
    border: 1px solid rgba(255,255,255,0.18) !important;
    border-radius: 6px !important;
}
section[data-testid="stSidebar"] button p,
section[data-testid="stSidebar"] button span,
section[data-testid="stSidebar"] button div {
    color: #CBD5E1 !important;
}
section[data-testid="stSidebar"] button:hover {
    background: rgba(192,57,43,0.30) !important;
    border-color: #C0392B !important;
    color: #FFFFFF !important;
}
section[data-testid="stSidebar"] button:hover p,
section[data-testid="stSidebar"] button:hover span,
section[data-testid="stSidebar"] button:hover div {
    color: #FFFFFF !important;
}

/* Indicadores de estado (override para sidebar oscuro) */
section[data-testid="stSidebar"] .nsg-stat-ok   { color: #4ADE80 !important; }
section[data-testid="stSidebar"] .nsg-stat-warn  { color: #FBBF24 !important; }
section[data-testid="stSidebar"] .nsg-stat-err   { color: #F87171 !important; }

/* Rol chip en sidebar oscuro */
section[data-testid="stSidebar"] .nsg-rol-chip {
    background: rgba(255,255,255,0.08) !important;
    color: #CBD5E1 !important;
    border-color: rgba(255,255,255,0.15) !important;
}
</style>
"""


def inject_css():
    """Inyectar estilos NSG. Se llama automáticamente desde render_sidebar()."""
    st.markdown(_CSS, unsafe_allow_html=True)

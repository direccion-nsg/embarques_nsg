"""
Generación de la Hoja Logística de Embarque en PDF usando ReportLab.

Diseño: rojo NSG (#C0392B) sólo en el encabezado principal y como acento
de color en los headers de sección (texto rojo + borde izquierdo rojo).
Los fondos de sección usan gris muy claro para no saturar el documento.
"""

import io
import os
import sys
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph,
    Spacer, HRFlowable,
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import SALIDA_DIR, ensure_dirs
from modules.consistency import extraer_cp

# ── Paleta de colores ─────────────────────────────────────────────────────────
ROJO_NSG    = colors.HexColor("#C0392B")   # rojo corporativo — solo header y texto de etiquetas
GRIS_COL    = colors.HexColor("#EEEEEE")   # encabezados de columna de productos
GRIS_BORDE  = colors.HexColor("#DDDDDD")   # bordes muy sutiles
GRIS_LINEA  = colors.HexColor("#E8E8E8")   # líneas separadoras entre filas
GRIS_OSCURO = colors.HexColor("#3A3A3A")   # texto principal
BLANCO      = colors.white


def generar_hoja_logistica(datos_bind: dict, datos_logisticos: dict) -> tuple:
    """Genera la Hoja Logística en memoria. Retorna (bytes, filename)."""
    folio    = datos_bind.get("folio", "SIN_FOLIO")
    ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"LOGISTICA_{folio}_{ts}.pdf"
    buffer   = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
    )

    estilos = _get_estilos()
    story   = []

    story.extend(_bloque_encabezado(
        estilos, folio, datos_bind.get("fecha", ""),
        datos_logisticos.get("pedido_interno", ""),
    ))
    story.append(Spacer(1, 0.4 * cm))

    story.append(_tabla_remitente_destinatario(estilos, datos_bind, datos_logisticos))
    story.append(Spacer(1, 0.4 * cm))

    story.append(_tabla_datos_logisticos(estilos, datos_logisticos))
    story.append(Spacer(1, 0.4 * cm))

    if datos_logisticos.get("con_remision"):
        story.append(_tabla_remision(estilos, datos_logisticos))
        story.append(Spacer(1, 0.4 * cm))

    story.append(_tabla_productos(estilos, datos_bind.get("productos", [])))
    story.append(Spacer(1, 0.4 * cm))

    obs = datos_logisticos.get("observaciones", "")
    if obs:
        story.append(_bloque_observaciones(estilos, obs))
        story.append(Spacer(1, 0.4 * cm))

    story.append(_tabla_empaque(estilos))
    story.append(Spacer(1, 0.4 * cm))

    story.append(_tabla_firmas(estilos))

    story.append(Spacer(1, 0.5 * cm))
    story.append(HRFlowable(width="100%", thickness=0.4, color=GRIS_BORDE))
    story.append(Spacer(1, 0.1 * cm))
    ts_gen = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    story.append(
        Paragraph(
            f"Documento generado por Preparación de Embarques NSG — {ts_gen}",
            estilos["pie"],
        )
    )

    doc.build(story)
    return buffer.getvalue(), filename


# ──────────────────────────────────────────────────────────────────────────────
# Bloques del documento
# ──────────────────────────────────────────────────────────────────────────────

def _bloque_encabezado(estilos, folio: str, fecha: str, pedido_interno: str = "") -> list:
    """Encabezado: panel rojo (marca) + panel blanco (folio/fecha/pedido)."""
    fecha_fmt  = _formatear_fecha(fecha)
    folio_txt  = f"<b>Folio Salida:</b> {folio}<br/><b>Fecha:</b> {fecha_fmt}"
    if pedido_interno:
        folio_txt += f"<br/><b>Pedido Int.:</b> {pedido_interno}"
    datos = [[
        Paragraph(
            "<b>GRUPO COMERCIALIZADOR NSG</b><br/>Hoja Logística de Embarque",
            estilos["empresa"],
        ),
        Paragraph(folio_txt, estilos["folio"]),
    ]]
    tabla = Table(datos, colWidths=["65%", "35%"])
    tabla.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (0, 0), ROJO_NSG),
        ("TEXTCOLOR",     (0, 0), (0, 0), BLANCO),
        ("BACKGROUND",    (1, 0), (1, 0), BLANCO),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING",    (0, 0), (-1, -1), 10),
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ("BOX",           (0, 0), (-1, -1), 1, ROJO_NSG),
        ("LINEAFTER",     (0, 0), (0, 0), 0.5, GRIS_BORDE),
    ]))
    return [tabla]


def _tabla_remitente_destinatario(estilos, datos_bind: dict, datos_log: dict) -> Table:
    """
    Tabla de dos columnas con encabezados separados REMITENTE | DESTINATARIO.
    La fila 0 NO lleva SPAN para que ambas etiquetas sean visibles.
    """
    def _p(txt):  return Paragraph(txt or "", estilos["celda"])
    def _ph(txt): return Paragraph(f"<b>{txt}</b>", estilos["col_header_rem"])
    def _pd(txt): return Paragraph(f"<b>{txt}</b>", estilos["col_header_dest"])

    rem_nombre    = datos_log.get("remitente_nombre",    datos_bind.get("remitente_nombre", ""))
    rem_rfc       = datos_log.get("remitente_rfc",       datos_bind.get("remitente_rfc", ""))
    rem_direccion = datos_log.get("remitente_direccion", datos_bind.get("remitente_direccion", ""))
    rem_tel       = datos_log.get("remitente_tel",       datos_bind.get("remitente_tel", ""))

    dest_nombre    = datos_log.get("destinatario_nombre",     datos_bind.get("cliente", ""))
    dest_rfc       = datos_log.get("destinatario_rfc",        datos_bind.get("rfc_cliente", ""))
    dest_direccion = datos_log.get("destinatario_direccion",  datos_bind.get("direccion_cliente", ""))
    dest_tel       = datos_log.get("destinatario_tel",        datos_bind.get("tel_cliente", ""))
    dest_contacto  = datos_log.get("destinatario_contacto",   "")
    dest_refs      = datos_log.get("destinatario_referencias","")
    dest_cp        = datos_log.get("destinatario_cp", "") or extraer_cp(dest_direccion)

    tel_cp = f"<b>Tel:</b> {dest_tel}"
    if dest_cp:
        tel_cp += f" &nbsp;&nbsp; <b>CP:</b> {dest_cp}"

    filas = [
        # Fila 0: dos encabezados de columna SEPARADOS (sin SPAN)
        [_ph("REMITENTE"), _pd("DESTINATARIO / CONSIGNATARIO")],
        [_p(f"<b>Nombre:</b> {rem_nombre}"),    _p(f"<b>Nombre:</b> {dest_nombre}")],
        [_p(f"<b>RFC:</b> {rem_rfc}"),           _p(f"<b>RFC:</b> {dest_rfc}")],
        [_p(f"<b>Dirección:</b> {rem_direccion}"), _p(f"<b>Dirección:</b> {dest_direccion}")],
        [_p(f"<b>Teléfono:</b> {rem_tel}"),      _p(tel_cp)],
        [Paragraph("", estilos["celda"]),         _p(f"<b>Contacto:</b> {dest_contacto}")],
        [Paragraph("", estilos["celda"]),         _p(f"<b>Referencias:</b> {dest_refs}")],
    ]

    GRIS_REM  = colors.HexColor("#EBEBEB")   # fondo columna remitente (imprime gris en B&W)
    GRIS_REM2 = colors.HexColor("#F4F4F4")   # fondo datos remitente (más sutil)

    tabla = Table(filas, colWidths=["50%", "50%"])
    tabla.setStyle(TableStyle([
        # ── Remitente (col 0): fondo gris en header y datos ──────────────────
        ("BACKGROUND",    (0, 0), (0, 0),  GRIS_REM),   # header gris medio
        ("TEXTCOLOR",     (0, 0), (0, 0),  ROJO_NSG),   # texto rojo (color) / oscuro (B&W)
        ("BACKGROUND",    (0, 1), (0, -1), GRIS_REM2),  # datos gris muy suave
        # ── Destinatario (col 1): fondo blanco ───────────────────────────────
        ("BACKGROUND",    (1, 0), (1, 0),  BLANCO),
        ("TEXTCOLOR",     (1, 0), (1, 0),  GRIS_OSCURO),
        ("BACKGROUND",    (1, 1), (1, -1), BLANCO),
        # ── Línea bajo encabezados ────────────────────────────────────────────
        ("LINEBELOW",     (0, 0), (-1, 0), 1,   ROJO_NSG),
        # ── Líneas horizontales sutiles entre filas de datos ─────────────────
        ("LINEBELOW",     (0, 1), (-1, -2), 0.4, GRIS_LINEA),
        # ── Separador vertical prominente (visible en B&W) ───────────────────
        ("LINEAFTER",     (0, 0), (0, -1), 1.2, GRIS_BORDE),
        # ── Caja exterior ─────────────────────────────────────────────────────
        ("BOX",           (0, 0), (-1, -1), 0.5, GRIS_BORDE),
        # ── Padding ───────────────────────────────────────────────────────────
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 7),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
    ]))
    return tabla


def _tabla_datos_logisticos(estilos, datos_log: dict) -> Table:
    def _p(txt): return Paragraph(txt or "", estilos["celda"])

    fletera    = datos_log.get("fletera", "")
    tipo_ent   = datos_log.get("tipo_entrega", "")
    cond_flete = datos_log.get("condicion_flete", "")
    oc         = datos_log.get("orden_compra", "")

    filas = [
        # Fila 0: encabezado de sección (span completo)
        [Paragraph("<b>DATOS LOGÍSTICOS</b>", estilos["sec_header"]), "", "", ""],
        [
            _p(f"<b>Fletera:</b> {fletera}"),
            _p(f"<b>Tipo de entrega:</b> {tipo_ent}"),
            _p(f"<b>Condición flete:</b> {cond_flete}"),
            _p(f"<b>OC Cliente:</b> {oc}"),
        ],
    ]

    tabla = Table(filas, colWidths=["28%", "25%", "25%", "22%"])
    tabla.setStyle(TableStyle([
        ("SPAN",          (0, 0), (-1, 0)),
        ("BACKGROUND",    (0, 0), (-1, 0), BLANCO),
        ("TEXTCOLOR",     (0, 0), (-1, 0), ROJO_NSG),
        ("LINEBELOW",     (0, 0), (-1, 0), 1, ROJO_NSG),
        ("BACKGROUND",    (0, 1), (-1, -1), BLANCO),
        ("BOX",           (0, 0), (-1, -1), 0.5, GRIS_BORDE),
        ("LINEAFTER",     (0, 0), (2, -1), 0.4, GRIS_BORDE),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("LEFTPADDING",   (0, 0), (-1, -1), 7),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return tabla


def _tabla_remision(estilos, datos_log: dict) -> Table:
    def _p(txt): return Paragraph(txt or "", estilos["celda"])

    empresa = datos_log.get("empresa_remision", "")
    numero  = datos_log.get("numero_remision", "")
    estado  = datos_log.get("estado_remision", "")

    filas = [
        [Paragraph("<b>REMISIÓN DEL CLIENTE</b>", estilos["sec_header"]), "", ""],
        [
            _p(f"<b>Empresa que remisiona:</b> {empresa}"),
            _p(f"<b>Número de remisión:</b> {numero}"),
            _p(f"<b>Estado:</b> {estado}"),
        ],
    ]
    tabla = Table(filas, colWidths=["45%", "35%", "20%"])
    tabla.setStyle(TableStyle([
        ("SPAN",          (0, 0), (-1, 0)),
        ("BACKGROUND",    (0, 0), (-1, 0), BLANCO),
        ("TEXTCOLOR",     (0, 0), (-1, 0), ROJO_NSG),
        ("LINEBELOW",     (0, 0), (-1, 0), 1, ROJO_NSG),
        ("BACKGROUND",    (0, 1), (-1, -1), BLANCO),
        ("BOX",           (0, 0), (-1, -1), 0.5, GRIS_BORDE),
        ("LINEAFTER",     (0, 1), (1, -1), 0.4, GRIS_BORDE),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("LEFTPADDING",   (0, 0), (-1, -1), 7),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
    ]))
    return tabla


_CLAVE_FISCAL = "39121409"


def _tabla_productos(estilos, productos: list) -> Table:
    def _p(txt): return Paragraph(str(txt) or "", estilos["celda_tabla"])
    def _ch(txt): return Paragraph(f"<b>{txt}</b>", estilos["col_header_prod"])

    filas = [
        # Fila 0: sección header (span)
        [Paragraph("<b>PRODUCTOS</b>", estilos["sec_header"]), "", "", "", ""],
        # Fila 1: encabezados de columnas
        [_ch("Código"), _ch("Clave Fiscal"), _ch("Cantidad"), _ch("Unidad"), _ch("Descripción")],
    ]

    productos_validos = []
    for p in (productos or []):
        qty_raw = p.get("cantidad_hoy", p.get("cantidad", ""))
        try:
            qty_val = float(str(qty_raw).replace(",", ".") or 0)
        except (ValueError, TypeError):
            qty_val = 0.0
        if qty_val <= 0:
            continue  # omitir partidas con cantidad 0
        qty_fmt = int(qty_val) if qty_val == int(qty_val) else qty_val
        productos_validos.append((p, qty_fmt))

    if productos_validos:
        for p, qty_fmt in productos_validos:
            filas.append([
                _p(p.get("codigo", "")),
                _p(_CLAVE_FISCAL),
                _p(str(qty_fmt)),
                _p(p.get("unidad", "")),
                _p(p.get("descripcion", "")),
            ])
    else:
        filas.append([_p("—"), _p(""), _p(""), _p(""), _p("Sin productos extraídos")])

    tabla = Table(filas, colWidths=["13%", "13%", "10%", "9%", "55%"])
    tabla.setStyle(TableStyle([
        # Sección header: sin fondo, solo texto rojo + línea roja abajo
        ("SPAN",          (0, 0), (-1, 0)),
        ("BACKGROUND",    (0, 0), (-1, 0), BLANCO),
        ("TEXTCOLOR",     (0, 0), (-1, 0), ROJO_NSG),
        ("LINEBELOW",     (0, 0), (-1, 0), 1, ROJO_NSG),
        # Encabezados de columnas: gris muy claro, texto oscuro
        ("BACKGROUND",    (0, 1), (-1, 1), GRIS_COL),
        ("TEXTCOLOR",     (0, 1), (-1, 1), GRIS_OSCURO),
        # Filas de datos: blanco limpio
        ("BACKGROUND",    (0, 2), (-1, -1), BLANCO),
        # Solo líneas horizontales sutiles entre filas
        ("LINEBELOW",     (0, 2), (-1, -2), 0.4, GRIS_LINEA),
        # Caja exterior y líneas verticales mínimas
        ("BOX",           (0, 0), (-1, -1), 0.5, GRIS_BORDE),
        ("LINEAFTER",     (0, 1), (3, -1), 0.4, GRIS_BORDE),
        # Padding
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN",         (1, 1), (3, -1), "CENTER"),
    ]))
    return tabla


def _bloque_observaciones(estilos, obs: str) -> Table:
    """Sección de observaciones con el mismo estilo de acento que las demás."""
    filas = [
        [Paragraph("<b>OBSERVACIONES</b>", estilos["sec_header"])],
        [Paragraph(obs, estilos["celda"])],
    ]
    tabla = Table(filas, colWidths=["100%"])
    tabla.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), BLANCO),
        ("TEXTCOLOR",     (0, 0), (-1, 0), ROJO_NSG),
        ("LINEBELOW",     (0, 0), (-1, 0), 1, ROJO_NSG),
        ("BACKGROUND",    (0, 1), (-1, -1), BLANCO),
        ("BOX",           (0, 0), (-1, -1), 0.5, GRIS_BORDE),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("LEFTPADDING",   (0, 0), (-1, -1), 7),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
    ]))
    return tabla


def _tabla_empaque(estilos) -> Table:
    """Bloque para registro manual de empaque en Almacén Teoloyucan."""
    def _campo(label):
        return Paragraph(
            f"<b>{label}</b><br/><br/><br/>{'_' * 30}",
            estilos["celda"],
        )

    filas = [
        [Paragraph("<b>EMPAQUE — ALMACÉN TEOLOYUCAN</b>", estilos["sec_header"]), "", ""],
        [
            _campo("No. de cajas:"),
            _campo("Empacó (nombre):"),
            _campo("Firma / Sello:"),
        ],
    ]
    tabla = Table(filas, colWidths=["28%", "38%", "34%"])
    tabla.setStyle(TableStyle([
        ("SPAN",          (0, 0), (-1, 0)),
        ("BACKGROUND",    (0, 0), (-1, 0), BLANCO),
        ("TEXTCOLOR",     (0, 0), (-1, 0), ROJO_NSG),
        ("LINEBELOW",     (0, 0), (-1, 0), 1, ROJO_NSG),
        ("BACKGROUND",    (0, 1), (-1, -1), BLANCO),
        ("BOX",           (0, 0), (-1, -1), 0.5, GRIS_BORDE),
        ("LINEAFTER",     (0, 1), (1, -1), 0.4, GRIS_BORDE),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 16),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("LEFTPADDING",   (0, 0), (-1, -1), 7),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
    ]))
    return tabla


def _tabla_firmas(estilos) -> Table:
    def _firma(titulo):
        return Paragraph(
            f"<br/><br/><br/>{'_' * 35}<br/><b>{titulo}</b>",
            estilos["firma"],
        )

    datos = [[
        _firma("Preparó — Finanzas CDMX"),
        _firma("Recibió — Almacén Teoloyucan"),
        _firma("Entregó — Fletera"),
    ]]
    tabla = Table(datos, colWidths=["33%", "33%", "34%"])
    tabla.setStyle(TableStyle([
        ("BOX",           (0, 0), (-1, -1), 0.5, GRIS_BORDE),
        ("INNERGRID",     (0, 0), (-1, -1), 0.5, GRIS_BORDE),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
    ]))
    return tabla


# ──────────────────────────────────────────────────────────────────────────────
# Estilos de texto
# ──────────────────────────────────────────────────────────────────────────────

def _get_estilos() -> dict:
    base = getSampleStyleSheet()
    return {
        "empresa": ParagraphStyle(
            "empresa", parent=base["Normal"],
            fontSize=12, leading=17, textColor=BLANCO, fontName="Helvetica-Bold",
        ),
        "folio": ParagraphStyle(
            "folio", parent=base["Normal"],
            fontSize=10, leading=14, alignment=TA_RIGHT, textColor=GRIS_OSCURO,
        ),
        # Etiqueta de sección: texto rojo sin fondo (la línea roja la pone la tabla)
        "sec_header": ParagraphStyle(
            "sec_header", parent=base["Normal"],
            fontSize=9, fontName="Helvetica-Bold", textColor=ROJO_NSG,
        ),
        # Encabezados de columna REMITENTE / DESTINATARIO
        "col_header_rem": ParagraphStyle(
            "col_header_rem", parent=base["Normal"],
            fontSize=8, fontName="Helvetica-Bold", textColor=ROJO_NSG,
        ),
        "col_header_dest": ParagraphStyle(
            "col_header_dest", parent=base["Normal"],
            fontSize=8, fontName="Helvetica-Bold", textColor=GRIS_OSCURO,
        ),
        # Encabezados de columnas en tabla de productos
        "col_header_prod": ParagraphStyle(
            "col_header_prod", parent=base["Normal"],
            fontSize=8, fontName="Helvetica-Bold", textColor=GRIS_OSCURO,
        ),
        "celda": ParagraphStyle(
            "celda", parent=base["Normal"],
            fontSize=8, leading=11, textColor=GRIS_OSCURO,
        ),
        "celda_tabla": ParagraphStyle(
            "celda_tabla", parent=base["Normal"],
            fontSize=8, leading=11, wordWrap="CJK", textColor=GRIS_OSCURO,
        ),
        "firma": ParagraphStyle(
            "firma", parent=base["Normal"],
            fontSize=8, alignment=TA_CENTER, textColor=GRIS_OSCURO,
        ),
        "pie": ParagraphStyle(
            "pie", parent=base["Normal"],
            fontSize=7, textColor=colors.grey, alignment=TA_CENTER,
        ),
    }


def _formatear_fecha(fecha_iso: str) -> str:
    try:
        dt = datetime.fromisoformat(fecha_iso.replace("T", " ").split(".")[0])
        return dt.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return fecha_iso

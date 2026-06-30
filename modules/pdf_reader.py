"""
Extracción de datos de la Hoja de Salida generada por Bind ERP.

Estrategia:
  - Cabecera (Folio, Fecha, OC): regex sobre texto completo de la página
  - Emisor / Receptor : page.crop() + extract_text() por columna separada
  - Productos: extract_tables() sobre región cropeada
  - Notas: regex en texto completo con filtrado de "Página N de N"
"""

import re
import os
import sys

import pdfplumber

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# RFC mexicano estándar: 3-4 letras + 6 dígitos + 3 alfanuméricos
# El PDF de Bind usa encoding con gaps inter-palabra muy pequeños (~1-2.5 pts)
# y gaps intra-palabra de 0 pts. x_tolerance=0.5 detecta correctamente las
# pausas entre palabras sin fragmentar caracteres individuales.
_XTOL = 0.5
_YTOL = 3

_RE_RFC = re.compile(r"RFC:\s*([A-Z&Ñ]{3,4}\d{6}[A-Z0-9]{3})")
_RE_TEL = re.compile(r"Tel\.:\s*([0-9]+)")
_RE_PAGINA = re.compile(r"^P[aá]gina\s+\d", re.IGNORECASE)

# Texto que marca el fin de la descripción de productos
_FIN_DESC = re.compile(
    r"(Nombre[,\s]*firma|sello\s*de|quien\s*recibe|^Notas?\s*$)",
    re.IGNORECASE | re.MULTILINE,
)


# ──────────────────────────────────────────────────────────────────────────────
# Función principal
# ──────────────────────────────────────────────────────────────────────────────

def extraer_datos_bind(pdf_input) -> dict:
    """Lee el PDF de Bind y retorna un dict con todos los campos extraídos.
    pdf_input puede ser una ruta (str) o bytes."""
    import io as _io
    if isinstance(pdf_input, (bytes, bytearray)):
        pdf_input = _io.BytesIO(pdf_input)
    try:
        with pdfplumber.open(pdf_input) as pdf:
            page     = pdf.pages[0]
            ancho    = page.width
            alto     = page.height
            # Texto completo con espacios (pdfplumber lo maneja bien sobre la página entera)
            texto    = page.extract_text(x_tolerance=_XTOL, y_tolerance=_YTOL) or ""
            # Palabras con posición para localizar regiones
            palabras = page.extract_words(x_tolerance=_XTOL, y_tolerance=_YTOL) or []

            emisor_txt, receptor_txt = _columnas_emisor_receptor(
                page, palabras, ancho
            )
            productos = _extraer_productos(page, palabras, ancho, alto)
    except Exception as exc:
        return _datos_vacios(error=str(exc))

    datos = {}
    datos["folio"]        = _folio(texto)
    datos["fecha"]        = _fecha(texto)
    datos["orden_compra"] = _orden_compra(texto)
    datos["sucursal"]     = _campo_cabecera(texto, "Sucursal")
    datos["almacen"]      = _campo_cabecera(texto, "Almacén")

    emisor   = _parsear_bloque(emisor_txt)
    receptor = _parsear_bloque(receptor_txt)

    datos["remitente_nombre"]    = emisor.get("nombre", "")
    datos["remitente_rfc"]       = emisor.get("rfc", "")
    datos["remitente_tel"]       = emisor.get("telefono", "")
    datos["remitente_direccion"] = emisor.get("direccion", "")

    datos["cliente"]           = receptor.get("nombre", "")
    datos["rfc_cliente"]       = receptor.get("rfc", "")
    datos["tel_cliente"]       = receptor.get("telefono", "")
    datos["direccion_cliente"] = receptor.get("direccion", "")

    datos["productos"] = productos
    datos["notas"]     = _notas(texto)
    datos["error"]     = ""
    return datos


# ──────────────────────────────────────────────────────────────────────────────
# Emisor / Receptor — extracción por columna con crop
# ──────────────────────────────────────────────────────────────────────────────

def _columnas_emisor_receptor(page, palabras: list, ancho: float):
    """
    Localiza las cabeceras 'Emisor' y 'Receptor' en coordenadas del PDF
    y extrae cada columna de forma independiente con extract_text().
    """
    emisor_w   = next((w for w in palabras if w["text"] == "Emisor"),   None)
    receptor_w = next((w for w in palabras if w["text"] == "Receptor"), None)

    if not emisor_w or not receptor_w:
        return "", ""

    top    = max(emisor_w["bottom"], receptor_w["bottom"]) + 1
    fin_w  = next(
        (w for w in palabras
         if w["text"] in ("Página", "Cód.", "Código") and w["top"] > top),
        None,
    )
    bottom  = (fin_w["top"] - 2) if fin_w else (page.height * 0.55)
    x_corte = receptor_w["x0"] - 4

    emisor_txt   = _crop_text(page, (0,       top, x_corte, bottom))
    receptor_txt = _crop_text(page, (x_corte, top, ancho,   bottom))
    return emisor_txt, receptor_txt


def _crop_text(page, bbox: tuple) -> str:
    """Cropea una región y extrae texto preservando espacios."""
    try:
        return (page.crop(bbox).extract_text(x_tolerance=_XTOL, y_tolerance=_YTOL) or "").strip()
    except Exception:
        return ""


def _parsear_bloque(texto: str) -> dict:
    """
    Parsea el texto de una columna Emisor o Receptor.
    RFC y Tel pueden estar en la misma línea; el regex de RFC mexicano
    estándar (12-13 chars) impide capturar la 'T' de 'Tel.'.
    """
    lineas = [l.strip() for l in texto.split("\n") if l.strip()]
    if not lineas:
        return {}

    resultado  = {}
    nombre_ok  = False
    dir_partes = []

    for linea in lineas:
        rfc_m = _RE_RFC.search(linea)
        tel_m = _RE_TEL.search(linea)

        if rfc_m:
            resultado["rfc"] = rfc_m.group(1)
        if tel_m:
            resultado["telefono"] = tel_m.group(1)

        if not rfc_m and not tel_m:
            if not nombre_ok:
                resultado["nombre"] = linea
                nombre_ok = True
            else:
                dir_partes.append(linea)

    resultado["direccion"] = ", ".join(dir_partes)
    return resultado


# ──────────────────────────────────────────────────────────────────────────────
# Productos
# ──────────────────────────────────────────────────────────────────────────────

_CABECERA_TABLA = {"Cód.", "Cód", "Código", "Codigo", "Art.", "Artículo",
                   "Articulo", "Clave", "SKU", "Cantidad"}
_FIN_TABLA      = {"Nombre,", "Notas", "Nombre", "firma", "sello"}


def _extraer_productos(page, palabras: list, ancho: float, alto: float) -> list:
    """Extrae productos usando la región de la tabla del PDF."""
    cod_w = next((w for w in palabras if w["text"] in _CABECERA_TABLA), None)

    # Si no encontramos ancla por encabezado, buscamos "Cantidad" como alternativa
    if not cod_w:
        cod_w = next((w for w in palabras if "Cantidad" in w["text"]), None)

    fin_w = next(
        (w for w in palabras
         if w["text"] in _FIN_TABLA and
         (cod_w is None or w["top"] > (cod_w["top"] if cod_w else 0))),
        None,
    )

    # Si aún no hay ancla, intentar con la mitad inferior de la página
    top    = (cod_w["top"] - 2) if cod_w else (alto * 0.35)
    bottom = (fin_w["top"] - 2) if fin_w else (alto * 0.85)

    # Intentar extracción por tablas en la región recortada
    try:
        region = page.crop((0, top, ancho, bottom))
        tablas = region.extract_tables({"text_x_tolerance": _XTOL}) or []
        resultado = _productos_desde_tablas(tablas)
        if resultado:
            return resultado
    except Exception:
        pass

    # Fallback: Bind no dibuja líneas de tabla y no respeta una fila de texto
    # por producto (código, cantidad+unidad y descripción caen en filas físicas
    # independientes, con el código partido en dos filas si es largo). Se
    # reconstruyen los productos directamente desde las palabras y su posición.
    cant_w = next((w for w in palabras if "Cantidad" in w["text"]), None)
    uni_w  = next((w for w in palabras if "Unidad" in w["text"]), None)
    x_cant_ini = (cant_w["x0"] - 15) if cant_w else 100.0
    x_cant_fin = (uni_w["x0"]  - 15) if uni_w  else (x_cant_ini + 100.0)

    # Excluir la fila de encabezado de la tabla (Cód. / Cantidad / Unidad / Descripción)
    top_filas = (cant_w["top"] + 3) if cant_w else top

    palabras_tabla = [w for w in palabras if top_filas < w["top"] < bottom]
    return _productos_desde_palabras(palabras_tabla, x_cant_ini, x_cant_fin)


def _productos_desde_tablas(tablas: list) -> list:
    productos = []
    for tabla in tablas:
        if not tabla or len(tabla) < 2:
            continue
        enc = [str(c or "").strip() for c in tabla[0]]
        if not any("Cód" in c or "Cantidad" in c for c in enc):
            continue
        for fila in tabla[1:]:
            if not fila:
                continue
            # Newlines dentro de celdas (código partido en varias líneas en el PDF)
            celdas = [str(c or "").replace("\n", "").strip() for c in fila]
            if not celdas[0] or not re.match(r"[A-Z0-9]", celdas[0]):
                continue
            cantidad = celdas[1] if len(celdas) > 1 else ""
            # Fila de continuación: código sin cantidad → pegar al producto anterior
            if not cantidad.strip() and productos and productos[-1]["codigo"].endswith("-"):
                productos[-1]["codigo"] += celdas[0]
                continue
            desc = celdas[3] if len(celdas) > 3 else ""
            desc = _limpiar_desc(desc)
            productos.append({
                "codigo":      celdas[0],
                "cantidad":    cantidad,
                "unidad":      celdas[2] if len(celdas) > 2 else "",
                "descripcion": desc,
            })
    return productos


_RE_NUM_CANT = re.compile(r"^[\d,]+\.?\d*$")


def _dedup_partes_desc(partes: list) -> list:
    """Bind imprime la descripción ajustada en varias líneas y luego la
    repite completa en una sola línea final. Si las partes anteriores
    (normalizadas, sin puntuación) coinciden con la última, se conserva
    solo la última (la versión completa y limpia)."""
    if len(partes) < 2:
        return partes
    norm = lambda s: re.sub(r"[^A-Z0-9]", "", s.upper())
    acumulado = norm("".join(partes[:-1]))
    ultimo    = norm(partes[-1])
    if acumulado and (acumulado == ultimo or acumulado in ultimo or ultimo in acumulado):
        return [partes[-1]]
    return partes


def _productos_desde_palabras(palabras: list, x_cant_ini: float, x_cant_fin: float) -> list:
    """Reconstruye productos agrupando palabras por fila física (mismo 'top').

    Bind no alinea código + cantidad + descripción en una sola línea de texto:
    cada celda puede caer en su propia fila física, y un código largo puede
    partirse en dos filas (ej. "NSG-P13-" + "4"). Se usa la fila que contiene
    la cantidad (columna numérica, por posición x) como ancla de cada producto,
    y las filas vecinas se reparten entre código (x a la izquierda de la
    columna Cantidad) y descripción (el resto), hasta la siguiente ancla.
    """
    if not palabras:
        return []

    filas = {}
    for w in palabras:
        filas.setdefault(round(w["top"], 1), []).append(w)
    tops = sorted(filas.keys())
    for t in tops:
        filas[t].sort(key=lambda w: w["x0"])

    anclas_idx = [
        i for i, t in enumerate(tops)
        if any(x_cant_ini <= w["x0"] < x_cant_fin and _RE_NUM_CANT.match(w["text"])
               for w in filas[t])
    ]
    if not anclas_idx:
        return []

    productos = []
    for n, ai in enumerate(anclas_idx):
        top_ancla = tops[ai]
        # Cada fila vecina se asigna al producto cuya ancla tenga el "top" más
        # cercano (punto medio entre anclas consecutivas), no a un rango fijo
        # de índices — así una fila no se atribuye al producto equivocado
        # cuando hay varios productos en la misma tabla.
        limite_izq = (tops[anclas_idx[n - 1]] + top_ancla) / 2 if n > 0 else -1.0
        limite_der = (
            (top_ancla + tops[anclas_idx[n + 1]]) / 2
            if n + 1 < len(anclas_idx) else float("inf")
        )

        cantidad, unidad = "", ""
        codigo_partes, desc_partes = [], []

        # Fila ancla: puede traer código + cantidad + unidad juntos (código corto)
        # o solo cantidad + unidad (código en fila propia, ej. código largo partido)
        for w in filas[top_ancla]:
            if w["x0"] < x_cant_ini:
                codigo_partes.append(w["text"])
            elif x_cant_ini <= w["x0"] < x_cant_fin and _RE_NUM_CANT.match(w["text"]):
                cantidad = w["text"]
            elif cantidad and not unidad:
                unidad = w["text"]
            elif unidad:
                desc_partes.append(w["text"])

        # Filas vecinas dentro de la ventana de este producto
        for t in tops:
            if t == top_ancla or not (limite_izq < t < limite_der):
                continue
            fila = filas[t]
            if fila[0]["x0"] < x_cant_ini:
                codigo_partes.append("".join(w["text"] for w in fila))
            else:
                desc_partes.append(" ".join(w["text"] for w in fila))

        codigo = "".join(codigo_partes)
        desc_partes = _dedup_partes_desc(desc_partes)
        descripcion = _limpiar_desc(" ".join(desc_partes), codigo)

        productos.append({
            "codigo":      codigo,
            "cantidad":    cantidad,
            "unidad":      unidad,
            "descripcion": descripcion,
        })

    return productos


def _limpiar_desc(desc: str, codigo: str = "") -> str:
    """Elimina texto de firma/notas y duplicados que Bind introduce."""
    m = _FIN_DESC.search(desc)
    if m:
        desc = desc[:m.start()].strip()
    # Bind imprime el código al inicio de la descripción (ej: "NSG-P8 GRAPA...")
    # y también la descripción completa al final — quitar el prefijo del código
    if codigo and desc.startswith(codigo):
        desc = desc[len(codigo):].strip()
    # Bind puede imprimir la descripción wrapped + completa en dos runs
    # Si la primera mitad está contenida en la segunda, conservar la última
    if len(desc) > 20:
        mitad = len(desc) // 2
        if desc[:mitad].strip() and desc[:mitad].strip() in desc[mitad:]:
            desc = desc[mitad:].strip()
    return desc.strip()


# ──────────────────────────────────────────────────────────────────────────────
# Campos de cabecera
# ──────────────────────────────────────────────────────────────────────────────

def _folio(texto: str) -> str:
    m = re.search(r"Hoja de Salida\s+([A-Z0-9]+)", texto)
    return m.group(1).strip() if m else ""


def _fecha(texto: str) -> str:
    m = re.search(r"(\d{4}-\d{2}-\d{2})[T\s](\d{2}:\d{2}:\d{2})", texto)
    return f"{m.group(1)} {m.group(2)}" if m else ""


def _orden_compra(texto: str) -> str:
    m = re.search(r"Orden\s+de\s+Compra:\s*\n?\s*([\w\-]+)", texto)
    if m:
        return m.group(1).strip()
    m = re.search(r"\b(\d{1,6}-\d{4})\b", texto)
    return m.group(1) if m else ""


def _campo_cabecera(texto: str, etiqueta: str) -> str:
    m = re.search(rf"{re.escape(etiqueta)}:?\s*\n?\s*([^\n]+)", texto)
    return m.group(1).strip() if m else ""


# ──────────────────────────────────────────────────────────────────────────────
# Notas
# ──────────────────────────────────────────────────────────────────────────────

def _notas(texto: str) -> str:
    """
    Extrae la sección Notas. Usa el texto completo (con x_tolerance=2).
    Filtra la línea 'Página N de N'.
    """
    # El texto ya viene con x_tolerance=2 por lo que tiene espacios
    m = re.search(r"Notas\s*\n(.+?)(?=\nP[aá]gina\s+\d|\Z)", texto, re.DOTALL)
    if m:
        lineas = [
            l.strip() for l in m.group(1).split("\n")
            if l.strip() and not _RE_PAGINA.match(l.strip())
        ]
        return " ".join(lineas)

    lineas_texto = texto.split("\n")
    for idx, linea in enumerate(lineas_texto):
        if linea.strip() == "Notas" and idx + 1 < len(lineas_texto):
            partes = []
            for j in range(idx + 1, min(idx + 10, len(lineas_texto))):
                l = lineas_texto[j].strip()
                if not l or _RE_PAGINA.match(l):
                    break
                partes.append(l)
            return " ".join(partes)
    return ""


# ──────────────────────────────────────────────────────────────────────────────
# Datos vacíos para errores
# ──────────────────────────────────────────────────────────────────────────────

def _datos_vacios(error: str = "") -> dict:
    return {
        "folio": "", "fecha": "", "orden_compra": "",
        "sucursal": "", "almacen": "",
        "remitente_nombre": "", "remitente_rfc": "",
        "remitente_tel": "", "remitente_direccion": "",
        "cliente": "", "rfc_cliente": "",
        "tel_cliente": "", "direccion_cliente": "",
        "productos": [], "notas": "", "error": error,
    }

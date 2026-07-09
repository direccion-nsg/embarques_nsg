"""
Base de datos — Preparación de Embarques NSG
Motor: Supabase PostgreSQL — schema prep_embarques
Las firmas de todas las funciones son idénticas a la versión SQLite.
"""

import os
import streamlit as st
import psycopg2
import psycopg2.pool
import psycopg2.extras

from config import NSG_REMITENTE_DEFAULT


# ──────────────────────────────────────────────────────────────────────────────
# Pool de conexiones (una instancia por servidor, cacheada por Streamlit)
# ──────────────────────────────────────────────────────────────────────────────

@st.cache_resource
def _pool() -> psycopg2.pool.ThreadedConnectionPool:
    try:
        dsn = st.secrets["database"]["url"]
    except Exception:
        dsn = os.environ.get("DATABASE_URL", "")
    # sslmode va en el DSN, no en options (es parámetro libpq, no GUC)
    if "sslmode" not in dsn:
        sep = "&" if "?" in dsn else "?"
        dsn = f"{dsn}{sep}sslmode=require"
    return psycopg2.pool.ThreadedConnectionPool(
        minconn=1,
        maxconn=20,
        dsn=dsn,
        options="-c search_path=prep_embarques",
    )


def get_connection():
    conn = _pool().getconn()
    conn.autocommit = False
    return conn


def _release(conn):
    try:
        _pool().putconn(conn)
    except Exception:
        pass


def _fetchall(conn, sql: str, params=None) -> list:
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(sql, params or [])
    return [dict(r) for r in cur.fetchall()]


def _fetchone(conn, sql: str, params=None):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(sql, params or [])
    row = cur.fetchone()
    return dict(row) if row else None


def _execute(conn, sql: str, params=None):
    cur = conn.cursor()
    cur.execute(sql, params or [])
    return cur


def _insert_returning(conn, sql: str, params=None) -> int:
    """Ejecuta un INSERT con RETURNING id y retorna el id generado."""
    cur = conn.cursor()
    cur.execute(sql, params or [])
    return cur.fetchone()[0]


# ──────────────────────────────────────────────────────────────────────────────
# Inicialización
# ──────────────────────────────────────────────────────────────────────────────

def init_database():
    """Verifica la conexión a Supabase y crea tablas opcionales si no existen."""
    conn = get_connection()
    try:
        _execute(conn, """
            CREATE TABLE IF NOT EXISTS domicilios_entrega (
                id          SERIAL PRIMARY KEY,
                nombre      VARCHAR(150) NOT NULL,
                direccion   TEXT         DEFAULT '',
                cp          VARCHAR(10)  DEFAULT '',
                contacto    VARCHAR(100) DEFAULT '',
                telefono    VARCHAR(30)  DEFAULT '',
                referencias TEXT         DEFAULT '',
                activo      INTEGER      DEFAULT 1
            )
        """)
        _execute(conn,
            "ALTER TABLE embarques ADD COLUMN IF NOT EXISTS impreso BOOLEAN DEFAULT FALSE"
        )
        _execute(conn,
            "ALTER TABLE embarques ADD COLUMN IF NOT EXISTS motivo_regreso TEXT DEFAULT ''"
        )
        conn.commit()
        row = _fetchone(conn, "SELECT COUNT(*) AS n FROM remitentes")
        if row and int(row["n"]) == 0:
            _seed_defaults(conn)
            conn.commit()
        # Reparación: embarques cancelados con embarque_partidas residuales
        _reparar_cancelados(conn)
    except Exception:
        conn.rollback()
    finally:
        _release(conn)


def _seed_defaults(conn):
    d = NSG_REMITENTE_DEFAULT
    _execute(conn,
        "INSERT INTO remitentes (nombre, rfc, direccion, telefono) VALUES (%s,%s,%s,%s)",
        (d["nombre"], d.get("rfc",""), d.get("direccion",""), d.get("telefono","")),
    )


def _reparar_cancelados(conn):
    """Limpia embarque_partidas residuales de embarques cancelados y recalcula estados."""
    cancelados = _fetchall(conn,
        "SELECT id FROM embarques WHERE estado_embarque='Cancelado'",
    )
    for emb in cancelados:
        eid = emb["id"]
        # ¿Quedan filas en embarque_partidas para este embarque?
        residuales = _fetchall(conn,
            "SELECT DISTINCT partida_id FROM embarque_partidas WHERE embarque_id=%s", (eid,)
        )
        if not residuales:
            continue
        _execute(conn, "DELETE FROM embarque_partidas WHERE embarque_id=%s", (eid,))
        for row in residuales:
            _actualizar_cantidad_partida(conn, row["partida_id"])
        salidas = _fetchall(conn,
            "SELECT DISTINCT salida_id FROM embarque_salidas WHERE embarque_id=%s", (eid,)
        )
        for row in salidas:
            _recalcular_estado_salida(conn, row["salida_id"])
    if cancelados:
        conn.commit()


# ──────────────────────────────────────────────────────────────────────────────
# CATÁLOGOS — Remitentes
# ──────────────────────────────────────────────────────────────────────────────

def get_remitentes(solo_activos=True) -> list:
    conn = get_connection()
    try:
        q = "SELECT * FROM remitentes"
        if solo_activos:
            q += " WHERE activo=1"
        q += " ORDER BY nombre"
        return _fetchall(conn, q)
    finally:
        _release(conn)


def upsert_remitente(data: dict):
    conn = get_connection()
    try:
        if data.get("id"):
            _execute(conn,
                "UPDATE remitentes SET nombre=%s, rfc=%s, direccion=%s, telefono=%s, activo=%s WHERE id=%s",
                (data["nombre"], data.get("rfc",""), data.get("direccion",""),
                 data.get("telefono",""), data.get("activo",1), data["id"]),
            )
        else:
            _execute(conn,
                "INSERT INTO remitentes (nombre, rfc, direccion, telefono) VALUES (%s,%s,%s,%s)",
                (data["nombre"], data.get("rfc",""), data.get("direccion",""), data.get("telefono","")),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _release(conn)


def delete_remitente(id_: int):
    conn = get_connection()
    try:
        _execute(conn, "UPDATE remitentes SET activo=0 WHERE id=%s", (id_,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _release(conn)


# ──────────────────────────────────────────────────────────────────────────────
# CATÁLOGOS — Destinatarios
# ──────────────────────────────────────────────────────────────────────────────

def get_destinatarios(solo_activos=True) -> list:
    conn = get_connection()
    try:
        q = "SELECT * FROM destinatarios"
        if solo_activos:
            q += " WHERE activo=1"
        q += " ORDER BY nombre"
        return _fetchall(conn, q)
    finally:
        _release(conn)


def upsert_destinatario(data: dict):
    conn = get_connection()
    try:
        if data.get("id"):
            _execute(conn,
                """UPDATE destinatarios
                   SET nombre=%s, rfc=%s, direccion=%s, cp=%s, telefono=%s,
                       contacto=%s, referencias=%s, activo=%s
                   WHERE id=%s""",
                (data["nombre"], data.get("rfc",""), data.get("direccion",""),
                 data.get("cp",""), data.get("telefono",""), data.get("contacto",""),
                 data.get("referencias",""), data.get("activo",1), data["id"]),
            )
        else:
            _execute(conn,
                """INSERT INTO destinatarios
                   (nombre, rfc, direccion, cp, telefono, contacto, referencias)
                   VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                (data["nombre"], data.get("rfc",""), data.get("direccion",""),
                 data.get("cp",""), data.get("telefono",""), data.get("contacto",""),
                 data.get("referencias","")),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _release(conn)


def delete_destinatario(id_: int):
    conn = get_connection()
    try:
        _execute(conn, "UPDATE destinatarios SET activo=0 WHERE id=%s", (id_,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _release(conn)


# ──────────────────────────────────────────────────────────────────────────────
# CATÁLOGOS — Fleteras
# ──────────────────────────────────────────────────────────────────────────────

def get_fleteras(solo_activos=True) -> list:
    conn = get_connection()
    try:
        q = "SELECT * FROM fleteras"
        if solo_activos:
            q += " WHERE activo=1"
        q += " ORDER BY nombre"
        return _fetchall(conn, q)
    finally:
        _release(conn)


def upsert_fletera(data: dict):
    conn = get_connection()
    try:
        if data.get("id"):
            _execute(conn,
                "UPDATE fleteras SET nombre=%s, activo=%s WHERE id=%s",
                (data["nombre"], data.get("activo",1), data["id"]),
            )
        else:
            _execute(conn,
                "INSERT INTO fleteras (nombre) VALUES (%s)", (data["nombre"],)
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _release(conn)


def delete_fletera(id_: int):
    conn = get_connection()
    try:
        _execute(conn, "UPDATE fleteras SET activo=0 WHERE id=%s", (id_,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _release(conn)


# ──────────────────────────────────────────────────────────────────────────────
# CATÁLOGOS — Domicilios de entrega (vehículo propio NSG)
# ──────────────────────────────────────────────────────────────────────────────

def get_domicilios_entrega(solo_activos=True) -> list:
    conn = get_connection()
    try:
        q = "SELECT * FROM domicilios_entrega"
        if solo_activos:
            q += " WHERE activo=1"
        q += " ORDER BY nombre"
        return _fetchall(conn, q)
    finally:
        _release(conn)


def upsert_domicilio_entrega(data: dict):
    conn = get_connection()
    try:
        if data.get("id"):
            _execute(conn,
                """UPDATE domicilios_entrega
                   SET nombre=%s, direccion=%s, cp=%s, contacto=%s,
                       telefono=%s, referencias=%s, activo=%s
                   WHERE id=%s""",
                (data["nombre"], data.get("direccion",""), data.get("cp",""),
                 data.get("contacto",""), data.get("telefono",""),
                 data.get("referencias",""), data.get("activo",1), data["id"]),
            )
        else:
            _execute(conn,
                """INSERT INTO domicilios_entrega
                   (nombre, direccion, cp, contacto, telefono, referencias)
                   VALUES (%s,%s,%s,%s,%s,%s)""",
                (data["nombre"], data.get("direccion",""), data.get("cp",""),
                 data.get("contacto",""), data.get("telefono",""),
                 data.get("referencias","")),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _release(conn)


def delete_domicilio_entrega(id_: int):
    conn = get_connection()
    try:
        _execute(conn, "UPDATE domicilios_entrega SET activo=0 WHERE id=%s", (id_,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _release(conn)


# ──────────────────────────────────────────────────────────────────────────────
# SALIDAS BIND
# ──────────────────────────────────────────────────────────────────────────────

def crear_salida(datos: dict, productos: list) -> int:
    conn = get_connection()
    try:
        salida_id = _insert_returning(conn,
            """INSERT INTO salidas_bind
               (folio_bind, fecha_salida, cliente, rfc_cliente,
                direccion_cliente, tel_cliente, orden_compra, notas, ruta_pdf_original)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
               RETURNING id""",
            (
                datos.get("folio_bind",""),
                datos.get("fecha_salida",""),
                datos.get("cliente",""),
                datos.get("rfc_cliente",""),
                datos.get("direccion_cliente",""),
                datos.get("tel_cliente",""),
                datos.get("orden_compra",""),
                datos.get("notas",""),
                datos.get("ruta_pdf_original",""),
            ),
        )
        for p in productos:
            try:
                cantidad = float(str(p.get("cantidad","0")).replace(",",".") or 0)
            except ValueError:
                cantidad = 0.0
            _execute(conn,
                """INSERT INTO partidas_bind
                   (salida_id, codigo, descripcion, unidad, cantidad_bind)
                   VALUES (%s,%s,%s,%s,%s)""",
                (salida_id, p.get("codigo",""), p.get("descripcion",""),
                 p.get("unidad",""), cantidad),
            )
        conn.commit()
        return salida_id
    except Exception:
        conn.rollback()
        raise
    finally:
        _release(conn)


def get_salida_por_folio(folio_bind: str) -> dict | None:
    conn = get_connection()
    try:
        row = _fetchone(conn,
            "SELECT * FROM salidas_bind WHERE folio_bind=%s ORDER BY id DESC LIMIT 1",
            (folio_bind,),
        )
        if not row:
            return None
        row["partidas"] = _get_partidas_con_pendiente(conn, row["id"])
        return row
    finally:
        _release(conn)


def get_salida_por_id(salida_id: int) -> dict | None:
    conn = get_connection()
    try:
        row = _fetchone(conn, "SELECT * FROM salidas_bind WHERE id=%s", (salida_id,))
        if not row:
            return None
        row["partidas"]  = _get_partidas_con_pendiente(conn, salida_id)
        row["embarques"] = _get_embarques_de_salida(conn, salida_id)
        return row
    finally:
        _release(conn)


def actualizar_salida(salida_id: int, datos: dict):
    conn = get_connection()
    try:
        _execute(conn,
            """UPDATE salidas_bind
               SET folio_bind=%s, fecha_salida=%s, cliente=%s, rfc_cliente=%s,
                   direccion_cliente=%s, tel_cliente=%s, orden_compra=%s, notas=%s
               WHERE id=%s""",
            (
                datos.get("folio_bind",""),
                datos.get("fecha_salida",""),
                datos.get("cliente",""),
                datos.get("rfc_cliente",""),
                datos.get("direccion_cliente",""),
                datos.get("tel_cliente",""),
                datos.get("orden_compra",""),
                datos.get("notas",""),
                salida_id,
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _release(conn)


def actualizar_partidas(salida_id: int, productos: list):
    conn = get_connection()
    try:
        existentes = {
            r["codigo"]: r["cantidad_embarcada"]
            for r in _fetchall(conn,
                "SELECT codigo, cantidad_embarcada FROM partidas_bind WHERE salida_id=%s",
                (salida_id,),
            )
        }
        _execute(conn, "DELETE FROM partidas_bind WHERE salida_id=%s", (salida_id,))

        for p in productos:
            try:
                cantidad = float(str(p.get("cantidad","0")).replace(",",".") or 0)
            except ValueError:
                cantidad = 0.0
            codigo = p.get("codigo","")
            ya_embarcada = existentes.get(codigo, 0.0)
            if ya_embarcada >= cantidad:
                estado = "Completa"
            elif ya_embarcada > 0:
                estado = "Parcial"
            else:
                estado = "Pendiente"
            _execute(conn,
                """INSERT INTO partidas_bind
                   (salida_id, codigo, descripcion, unidad, cantidad_bind,
                    cantidad_embarcada, estado)
                   VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                (salida_id, codigo, p.get("descripcion",""), p.get("unidad",""),
                 cantidad, ya_embarcada, estado),
            )

        _recalcular_estado_salida(conn, salida_id)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _release(conn)


def actualizar_estado_salida(salida_id: int):
    conn = get_connection()
    try:
        _recalcular_estado_salida(conn, salida_id)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _release(conn)


def get_salidas_filtradas(folio="", cliente="", estado="",
                          fecha_desde="", fecha_hasta="",
                          pedido_interno="", limit=200) -> list:
    conn = get_connection()
    try:
        q = """
            SELECT s.*,
                   COUNT(DISTINCT es.embarque_id)                                        AS num_embarques,
                   COUNT(DISTINCT p.id)                                                   AS total_partidas,
                   COUNT(DISTINCT CASE WHEN p.estado != 'Completa' THEN p.id END)        AS partidas_pendientes
            FROM salidas_bind s
            LEFT JOIN embarque_salidas es ON es.salida_id = s.id
            LEFT JOIN embarques        e  ON e.id = es.embarque_id
            LEFT JOIN partidas_bind    p  ON p.salida_id  = s.id
            WHERE 1=1
        """
        params = []
        if folio:
            q += " AND s.folio_bind ILIKE %s"
            params.append(f"%{folio}%")
        if cliente:
            q += " AND s.cliente ILIKE %s"
            params.append(f"%{cliente}%")
        if estado:
            q += " AND s.estado = %s"
            params.append(estado)
        if fecha_desde:
            q += " AND s.fecha_salida >= %s"
            params.append(fecha_desde)
        if fecha_hasta:
            q += " AND s.fecha_salida <= %s"
            params.append(fecha_hasta)
        if pedido_interno:
            q += " AND e.pedido_interno ILIKE %s"
            params.append(f"%{pedido_interno}%")
        q += " GROUP BY s.id ORDER BY s.created_at DESC LIMIT %s"
        params.append(limit)
        return _fetchall(conn, q, params)
    finally:
        _release(conn)


# ──────────────────────────────────────────────────────────────────────────────
# EMBARQUES
# ──────────────────────────────────────────────────────────────────────────────

def crear_embarque(datos_log: dict, salida_ids: list,
                   partidas_cantidades: list) -> int:
    conn = get_connection()
    try:
        embarque_id = _insert_returning(conn,
            """INSERT INTO embarques
               (remitente_nombre, remitente_rfc, remitente_tel, remitente_direccion,
                destinatario_nombre, destinatario_rfc, destinatario_direccion,
                destinatario_cp, destinatario_tel, destinatario_contacto,
                destinatario_referencias, fletera, tipo_entrega, condicion_flete,
                con_remision, empresa_remision, numero_remision, estado_remision,
                ruta_pdf_remision, observaciones, ruta_pdf_generado,
                warning_confirmado, detalle_warnings, correcciones_manuales,
                pedido_interno)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               RETURNING id""",
            (
                datos_log.get("remitente_nombre",""),
                datos_log.get("remitente_rfc",""),
                datos_log.get("remitente_tel",""),
                datos_log.get("remitente_direccion",""),
                datos_log.get("destinatario_nombre",""),
                datos_log.get("destinatario_rfc",""),
                datos_log.get("destinatario_direccion",""),
                datos_log.get("destinatario_cp",""),
                datos_log.get("destinatario_tel",""),
                datos_log.get("destinatario_contacto",""),
                datos_log.get("destinatario_referencias",""),
                datos_log.get("fletera",""),
                datos_log.get("tipo_entrega",""),
                datos_log.get("condicion_flete",""),
                1 if datos_log.get("con_remision") else 0,
                datos_log.get("empresa_remision",""),
                datos_log.get("numero_remision",""),
                datos_log.get("estado_remision",""),
                datos_log.get("ruta_pdf_remision",""),
                datos_log.get("observaciones",""),
                datos_log.get("ruta_pdf_generado",""),
                1 if datos_log.get("warning_confirmado") else 0,
                datos_log.get("detalle_warnings",""),
                datos_log.get("correcciones_manuales",""),
                datos_log.get("pedido_interno",""),
            ),
        )

        for sid in salida_ids:
            _execute(conn,
                "INSERT INTO embarque_salidas (embarque_id, salida_id) VALUES (%s,%s) ON CONFLICT DO NOTHING",
                (embarque_id, sid),
            )

        for pc in partidas_cantidades:
            qty = float(pc.get("cantidad_embarcada", 0) or 0)
            if qty <= 0:
                continue
            _execute(conn,
                "INSERT INTO embarque_partidas (embarque_id, partida_id, cantidad_embarcada) VALUES (%s,%s,%s)",
                (embarque_id, pc["partida_id"], qty),
            )
            _actualizar_cantidad_partida(conn, pc["partida_id"])

        for sid in salida_ids:
            _recalcular_estado_salida(conn, sid)

        conn.commit()
        return embarque_id
    except Exception:
        conn.rollback()
        raise
    finally:
        _release(conn)


def actualizar_ruta_pdf_embarque(embarque_id: int, ruta_pdf: str):
    conn = get_connection()
    try:
        _execute(conn,
            "UPDATE embarques SET ruta_pdf_generado=%s WHERE id=%s",
            (ruta_pdf, embarque_id),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _release(conn)


def get_embarque_por_id(embarque_id: int) -> dict | None:
    conn = get_connection()
    try:
        emb = _fetchone(conn, "SELECT * FROM embarques WHERE id=%s", (embarque_id,))
        if not emb:
            return None

        emb["salidas"] = _fetchall(conn,
            """SELECT s.* FROM salidas_bind s
               JOIN embarque_salidas es ON es.salida_id = s.id
               WHERE es.embarque_id=%s""",
            (embarque_id,),
        )
        emb["partidas"] = _fetchall(conn,
            """SELECT p.codigo, p.descripcion, p.unidad,
                      SUM(ep.cantidad_embarcada) AS cantidad_en_embarque
               FROM partidas_bind p
               JOIN embarque_partidas ep ON ep.partida_id = p.id
               WHERE ep.embarque_id=%s
               GROUP BY p.codigo, p.descripcion, p.unidad
               ORDER BY p.codigo""",
            (embarque_id,),
        )
        emb["guias"] = _fetchall(conn,
            "SELECT * FROM guias WHERE embarque_id=%s ORDER BY created_at DESC",
            (embarque_id,),
        )
        return emb
    finally:
        _release(conn)


def get_embarques_por_salida(salida_id: int) -> list:
    conn = get_connection()
    try:
        return _fetchall(conn,
            """SELECT e.* FROM embarques e
               JOIN embarque_salidas es ON es.embarque_id = e.id
               WHERE es.salida_id=%s
               ORDER BY e.created_at DESC""",
            (salida_id,),
        )
    finally:
        _release(conn)


_ESTADOS_FUERA_BANDEJA = {
    "Enviado a Planta", "Embarcado sin guía", "Guía capturada",
    "Entregado a fletera", "Cerrado", "Cancelado",
}

def actualizar_estado_embarque(embarque_id: int, estado: str):
    conn = get_connection()
    try:
        en_bandeja = 0 if estado in _ESTADOS_FUERA_BANDEJA else None
        if en_bandeja is not None:
            _execute(conn,
                "UPDATE embarques SET estado_embarque=%s, en_bandeja=%s WHERE id=%s",
                (estado, en_bandeja, embarque_id),
            )
        else:
            _execute(conn,
                "UPDATE embarques SET estado_embarque=%s WHERE id=%s",
                (estado, embarque_id),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _release(conn)


def actualizar_embarque_logistica(embarque_id: int, datos: dict):
    """Actualiza los datos logísticos de un embarque existente y limpia el motivo de regreso."""
    conn = get_connection()
    try:
        _execute(conn, """
            UPDATE embarques SET
                remitente_nombre=%s, remitente_rfc=%s, remitente_tel=%s, remitente_direccion=%s,
                destinatario_nombre=%s, destinatario_rfc=%s, destinatario_direccion=%s,
                destinatario_cp=%s, destinatario_tel=%s, destinatario_contacto=%s,
                destinatario_referencias=%s, fletera=%s, tipo_entrega=%s, condicion_flete=%s,
                con_remision=%s, empresa_remision=%s, numero_remision=%s, estado_remision=%s,
                observaciones=%s, pedido_interno=%s, ruta_pdf_generado=%s,
                warning_confirmado=%s, detalle_warnings=%s, motivo_regreso=''
            WHERE id=%s
        """, (
            datos.get("remitente_nombre",""),    datos.get("remitente_rfc",""),
            datos.get("remitente_tel",""),       datos.get("remitente_direccion",""),
            datos.get("destinatario_nombre",""), datos.get("destinatario_rfc",""),
            datos.get("destinatario_direccion",""), datos.get("destinatario_cp",""),
            datos.get("destinatario_tel",""),    datos.get("destinatario_contacto",""),
            datos.get("destinatario_referencias",""), datos.get("fletera",""),
            datos.get("tipo_entrega",""),        datos.get("condicion_flete",""),
            1 if datos.get("con_remision") else 0,
            datos.get("empresa_remision",""),    datos.get("numero_remision",""),
            datos.get("estado_remision",""),     datos.get("observaciones",""),
            datos.get("pedido_interno",""),      datos.get("ruta_pdf_generado",""),
            1 if datos.get("warning_confirmado") else 0, datos.get("detalle_warnings",""),
            embarque_id,
        ))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _release(conn)


def marcar_impreso(embarque_id: int, impreso: bool):
    conn = get_connection()
    try:
        _execute(conn, "UPDATE embarques SET impreso=%s WHERE id=%s", (impreso, embarque_id))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _release(conn)


def cancelar_embarque(embarque_id: int):
    """Marca el embarque como Cancelado, lo saca de la bandeja y revierte cantidades embarcadas."""
    conn = get_connection()
    try:
        _execute(conn,
            "UPDATE embarques SET estado_embarque='Cancelado', en_bandeja=0 WHERE id=%s",
            (embarque_id,),
        )
        # Obtener partidas afectadas antes de borrar los vínculos
        partidas_afectadas = _fetchall(conn,
            "SELECT DISTINCT partida_id FROM embarque_partidas WHERE embarque_id=%s",
            (embarque_id,),
        )
        # Eliminar las cantidades de este embarque de embarque_partidas
        _execute(conn,
            "DELETE FROM embarque_partidas WHERE embarque_id=%s",
            (embarque_id,),
        )
        # Recalcular cantidad_embarcada y estado de cada partida afectada
        for row in partidas_afectadas:
            _actualizar_cantidad_partida(conn, row["partida_id"])
        # Recalcular estado de cada salida vinculada a este embarque
        salidas_afectadas = _fetchall(conn,
            "SELECT DISTINCT salida_id FROM embarque_salidas WHERE embarque_id=%s",
            (embarque_id,),
        )
        for row in salidas_afectadas:
            _recalcular_estado_salida(conn, row["salida_id"])
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _release(conn)


def regresar_embarque_a_bandeja(embarque_id: int, motivo: str = ""):
    """Revierte un embarque a 'Preparado' y lo regresa a la bandeja de Finanzas."""
    conn = get_connection()
    try:
        _execute(conn,
            "UPDATE embarques SET estado_embarque='Preparado', en_bandeja=1, motivo_regreso=%s WHERE id=%s",
            (motivo, embarque_id),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _release(conn)


def get_embarques_filtrados(folio="", cliente="", fecha_desde="", fecha_hasta="",
                            estado_embarque="", pendiente_guia=False,
                            limit=200) -> list:
    conn = get_connection()
    try:
        q = """
            SELECT DISTINCT e.*,
                   STRING_AGG(DISTINCT s.folio_bind, ',') AS folios_bind,
                   STRING_AGG(DISTINCT s.cliente,    ',') AS clientes,
                   COUNT(DISTINCT g.id)                   AS num_guias
            FROM embarques e
            LEFT JOIN embarque_salidas es ON es.embarque_id = e.id
            LEFT JOIN salidas_bind     s  ON s.id = es.salida_id
            LEFT JOIN guias            g  ON g.embarque_id  = e.id
            WHERE 1=1
        """
        params = []
        if folio:
            q += " AND s.folio_bind ILIKE %s"
            params.append(f"%{folio}%")
        if cliente:
            q += " AND s.cliente ILIKE %s"
            params.append(f"%{cliente}%")
        if fecha_desde:
            q += " AND e.created_at::date >= %s"
            params.append(fecha_desde)
        if fecha_hasta:
            q += " AND e.created_at::date <= %s"
            params.append(fecha_hasta)
        if estado_embarque:
            q += " AND e.estado_embarque = %s"
            params.append(estado_embarque)
        if pendiente_guia:
            q += " AND e.estado_embarque NOT IN ('Guía capturada','Entregado a fletera','Cerrado','Cancelado')"

        q += " GROUP BY e.id ORDER BY e.created_at DESC LIMIT %s"
        params.append(limit)
        return _fetchall(conn, q, params)
    finally:
        _release(conn)


# ──────────────────────────────────────────────────────────────────────────────
# GUÍAS
# ──────────────────────────────────────────────────────────────────────────────

def guardar_guia(embarque_id: int, datos: dict) -> int:
    conn = get_connection()
    try:
        guia_id = _insert_returning(conn,
            """INSERT INTO guias
               (embarque_id, numero_guia, fletera, fecha_embarque_real,
                hora_embarque, quien_entrego, ruta_evidencia, observaciones)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
               RETURNING id""",
            (
                embarque_id,
                datos.get("numero_guia",""),
                datos.get("fletera",""),
                datos.get("fecha_embarque_real",""),
                datos.get("hora_embarque",""),
                datos.get("quien_entrego",""),
                datos.get("ruta_evidencia",""),
                datos.get("observaciones",""),
            ),
        )
        row = _fetchone(conn, "SELECT estado_embarque FROM embarques WHERE id=%s", (embarque_id,))
        if row and row["estado_embarque"] in ("Preparado","Enviado a Planta","Embarcado sin guía"):
            _execute(conn,
                "UPDATE embarques SET estado_embarque='Guía capturada' WHERE id=%s",
                (embarque_id,),
            )
        conn.commit()
        return guia_id
    except Exception:
        conn.rollback()
        raise
    finally:
        _release(conn)


def get_guias_por_embarque(embarque_id: int) -> list:
    conn = get_connection()
    try:
        return _fetchall(conn,
            "SELECT * FROM guias WHERE embarque_id=%s ORDER BY created_at DESC",
            (embarque_id,),
        )
    finally:
        _release(conn)


# ──────────────────────────────────────────────────────────────────────────────
# AUDITORÍA
# ──────────────────────────────────────────────────────────────────────────────

def registrar_cambio(entidad: str, entidad_id: int, campo: str,
                     valor_anterior: str, valor_nuevo: str, origen: str):
    conn = get_connection()
    try:
        _execute(conn,
            """INSERT INTO cambios_log
               (entidad, entidad_id, campo, valor_anterior, valor_nuevo, origen)
               VALUES (%s,%s,%s,%s,%s,%s)""",
            (entidad, entidad_id, campo, str(valor_anterior), str(valor_nuevo), origen),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _release(conn)


def get_cambios_log(entidad: str, entidad_id: int) -> list:
    conn = get_connection()
    try:
        return _fetchall(conn,
            "SELECT * FROM cambios_log WHERE entidad=%s AND entidad_id=%s ORDER BY created_at",
            (entidad, entidad_id),
        )
    finally:
        _release(conn)


# ──────────────────────────────────────────────────────────────────────────────
# BANDEJA
# ──────────────────────────────────────────────────────────────────────────────

def agregar_a_bandeja(embarque_id: int):
    conn = get_connection()
    try:
        _execute(conn, "UPDATE embarques SET en_bandeja=1 WHERE id=%s", (embarque_id,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _release(conn)


def quitar_de_bandeja(embarque_id: int):
    conn = get_connection()
    try:
        _execute(conn, "UPDATE embarques SET en_bandeja=0 WHERE id=%s", (embarque_id,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _release(conn)


def vaciar_bandeja():
    conn = get_connection()
    try:
        _execute(conn, "UPDATE embarques SET en_bandeja=0 WHERE en_bandeja=1")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _release(conn)


def get_bandeja() -> list:
    conn = get_connection()
    try:
        return _fetchall(conn, """
            SELECT e.id AS embarque_id,
                   MIN(es.salida_id)                          AS salida_id,
                   STRING_AGG(DISTINCT s.folio_bind, ',')     AS folio_bind,
                   STRING_AGG(DISTINCT s.cliente,    ',')     AS cliente,
                   e.destinatario_nombre,
                   e.fletera, e.tipo_entrega, e.condicion_flete,
                   e.con_remision, e.empresa_remision, e.numero_remision,
                   e.observaciones, e.ruta_pdf_generado,
                   e.estado_embarque, e.created_at, e.pedido_interno,
                   e.motivo_regreso
            FROM embarques e
            LEFT JOIN embarque_salidas es ON es.embarque_id = e.id
            LEFT JOIN salidas_bind     s  ON s.id = es.salida_id
            WHERE e.en_bandeja = 1
              AND e.estado_embarque NOT IN (
                    'Enviado a Planta','Embarcado sin guía','Guía capturada',
                    'Entregado a fletera','Cerrado','Cancelado'
              )
            GROUP BY e.id
            ORDER BY e.created_at
        """)
    finally:
        _release(conn)


# ──────────────────────────────────────────────────────────────────────────────
# CONTADORES — sidebar
# ──────────────────────────────────────────────────────────────────────────────

def count_embarques_sin_guia() -> int:
    conn = get_connection()
    try:
        row = _fetchone(conn,
            "SELECT COUNT(*) AS n FROM embarques WHERE estado_embarque NOT IN ('Guía capturada','Cerrado','Cancelado')"
        )
        return int(row["n"]) if row else 0
    finally:
        _release(conn)


def count_salidas_activas() -> dict:
    conn = get_connection()
    try:
        rows = _fetchall(conn,
            "SELECT estado, COUNT(*) AS n FROM salidas_bind GROUP BY estado"
        )
        return {r["estado"]: r["n"] for r in rows}
    finally:
        _release(conn)


# ──────────────────────────────────────────────────────────────────────────────
# HELPERS INTERNOS
# ──────────────────────────────────────────────────────────────────────────────

def get_historial_detalle(salida_ids: list) -> dict:
    """Carga partidas y embarques completos para un conjunto de salidas en 4 queries.

    Reemplaza el patrón N+1 del Historial (get_salida_por_id × N +
    get_embarque_por_id × N×M) con consultas únicas por tipo de dato.

    Retorna dict[salida_id → {"partidas": [...], "embarques": [...]}]
    donde cada embarque ya incluye sus sub-listas "partidas" y "guias".
    """
    if not salida_ids:
        return {}
    conn = get_connection()
    try:
        ids = list(salida_ids)

        # 1. Partidas de todas las salidas
        partidas_rows = _fetchall(conn,
            "SELECT * FROM partidas_bind WHERE salida_id = ANY(%s) ORDER BY salida_id, id",
            (ids,),
        )
        for p in partidas_rows:
            p["cantidad_pendiente"] = max(0.0, p["cantidad_bind"] - p["cantidad_embarcada"])
        partidas_by_salida: dict = {}
        for p in partidas_rows:
            partidas_by_salida.setdefault(p["salida_id"], []).append(p)

        # 2. Embarques de todas las salidas con contador de guías
        embarques_rows = _fetchall(conn,
            """SELECT e.*, es.salida_id, COUNT(DISTINCT g.id) AS num_guias
               FROM embarques e
               JOIN embarque_salidas es ON es.embarque_id = e.id
               LEFT JOIN guias g ON g.embarque_id = e.id
               WHERE es.salida_id = ANY(%s)
               GROUP BY e.id, es.salida_id
               ORDER BY es.salida_id, e.created_at DESC""",
            (ids,),
        )
        emb_ids = list({e["id"] for e in embarques_rows})

        # 3. Partidas por embarque y guías (solo si hay embarques)
        if emb_ids:
            partidas_emb_rows = _fetchall(conn,
                """SELECT ep.embarque_id, p.codigo, p.descripcion, p.unidad,
                          SUM(ep.cantidad_embarcada) AS cantidad_en_embarque
                   FROM embarque_partidas ep
                   JOIN partidas_bind p ON p.id = ep.partida_id
                   WHERE ep.embarque_id = ANY(%s)
                   GROUP BY ep.embarque_id, p.codigo, p.descripcion, p.unidad
                   ORDER BY ep.embarque_id, p.codigo""",
                (emb_ids,),
            )
            guias_rows = _fetchall(conn,
                "SELECT * FROM guias WHERE embarque_id = ANY(%s) ORDER BY embarque_id, created_at DESC",
                (emb_ids,),
            )
        else:
            partidas_emb_rows = []
            guias_rows = []

        # Ensamblar partidas y guías dentro de cada embarque
        partidas_emb_by_emb: dict = {}
        for p in partidas_emb_rows:
            partidas_emb_by_emb.setdefault(p["embarque_id"], []).append(p)
        guias_by_emb: dict = {}
        for g in guias_rows:
            guias_by_emb.setdefault(g["embarque_id"], []).append(g)

        embarques_by_salida: dict = {}
        for e in embarques_rows:
            emb = dict(e)
            emb["partidas"] = partidas_emb_by_emb.get(e["id"], [])
            emb["guias"]    = guias_by_emb.get(e["id"], [])
            embarques_by_salida.setdefault(e["salida_id"], []).append(emb)

        return {
            sid: {
                "partidas":  partidas_by_salida.get(sid, []),
                "embarques": embarques_by_salida.get(sid, []),
            }
            for sid in ids
        }
    finally:
        _release(conn)


def _get_partidas_con_pendiente(conn, salida_id: int) -> list:
    rows = _fetchall(conn,
        "SELECT * FROM partidas_bind WHERE salida_id=%s ORDER BY id",
        (salida_id,),
    )
    for p in rows:
        p["cantidad_pendiente"] = max(0.0, p["cantidad_bind"] - p["cantidad_embarcada"])
    return rows


def _get_embarques_de_salida(conn, salida_id: int) -> list:
    return _fetchall(conn,
        """SELECT e.*, COUNT(g.id) AS num_guias
           FROM embarques e
           JOIN embarque_salidas es ON es.embarque_id = e.id
           LEFT JOIN guias g ON g.embarque_id = e.id
           WHERE es.salida_id=%s
           GROUP BY e.id
           ORDER BY e.created_at DESC""",
        (salida_id,),
    )


def _actualizar_cantidad_partida(conn, partida_id: int):
    row = _fetchone(conn,
        "SELECT COALESCE(SUM(cantidad_embarcada),0) AS total FROM embarque_partidas WHERE partida_id=%s",
        (partida_id,),
    )
    total = float(row["total"])
    partida = _fetchone(conn,
        "SELECT cantidad_bind FROM partidas_bind WHERE id=%s", (partida_id,)
    )
    if not partida:
        return
    qty_bind = float(partida["cantidad_bind"])
    if total <= 0:
        estado = "Pendiente"
    elif total >= qty_bind:
        estado = "Completa"
    else:
        estado = "Parcial"
    _execute(conn,
        "UPDATE partidas_bind SET cantidad_embarcada=%s, estado=%s WHERE id=%s",
        (total, estado, partida_id),
    )


def _recalcular_estado_salida(conn, salida_id: int):
    rows = _fetchall(conn,
        "SELECT estado FROM partidas_bind WHERE salida_id=%s", (salida_id,)
    )
    if not rows:
        return
    estados = [r["estado"] for r in rows]
    if all(e == "Completa" for e in estados):
        nuevo = "Completada"
    elif all(e == "Pendiente" for e in estados):
        nuevo = "Pendiente"
    else:
        nuevo = "Parcial"
    _execute(conn,
        "UPDATE salidas_bind SET estado=%s WHERE id=%s", (nuevo, salida_id)
    )


# ──────────────────────────────────────────────────────────────────────────────
# REPORTE DE AUDITORÍA
# ──────────────────────────────────────────────────────────────────────────────

def get_reporte_exportacion(
    folio: str = "",
    cliente: str = "",
    estado: str = "",
    fecha_desde: str = "",
    fecha_hasta: str = "",
    pedido_interno: str = "",
) -> list:
    """Devuelve filas planas para exportar a Excel/CSV.

    Nivel de detalle: una fila por (partida, embarque).
    Partidas sin embarque aparecen con campos de embarque vacíos.
    """
    conn = get_connection()
    try:
        q = """
            SELECT
                s.folio_bind,
                TO_CHAR(s.fecha_salida::date, 'DD/MM/YYYY')  AS fecha_salida,
                s.cliente,
                s.rfc_cliente,
                s.orden_compra,
                s.estado                                       AS estado_salida,
                p.codigo,
                p.descripcion,
                p.unidad,
                p.cantidad_bind,
                p.cantidad_embarcada                           AS total_embarcado,
                GREATEST(0, p.cantidad_bind - p.cantidad_embarcada) AS pendiente,
                p.estado                                       AS estado_partida,
                COALESCE(e.pedido_interno,  '')                AS pedido_interno,
                CASE WHEN e.created_at IS NOT NULL
                     THEN TO_CHAR(e.created_at::date, 'DD/MM/YYYY')
                     ELSE '' END                               AS fecha_embarque,
                COALESCE(e.fletera,         '')                AS fletera,
                COALESCE(e.tipo_entrega,    '')                AS tipo_entrega,
                COALESCE(e.condicion_flete, '')                AS condicion_flete,
                COALESCE(ep.cantidad_embarcada, 0)             AS en_este_embarque,
                COALESCE(e.estado_embarque, 'Sin embarque')    AS estado_embarque,
                COALESCE(STRING_AGG(DISTINCT g.numero_guia, ', '), '') AS guias,
                COALESCE(MIN(g.fecha_embarque_real::text), '') AS fecha_guia,
                CASE WHEN e.ruta_pdf_generado IS NOT NULL AND e.ruta_pdf_generado != ''
                     THEN 'Sí' ELSE 'No' END                  AS pdf_generado
            FROM salidas_bind s
            JOIN partidas_bind p          ON p.salida_id  = s.id
            LEFT JOIN embarque_partidas ep ON ep.partida_id = p.id
            LEFT JOIN embarques e          ON e.id          = ep.embarque_id
            LEFT JOIN guias g              ON g.embarque_id = e.id
            WHERE 1=1
        """
        params: list = []

        if folio:
            q += " AND s.folio_bind ILIKE %s"
            params.append(f"%{folio}%")
        if cliente:
            q += " AND s.cliente ILIKE %s"
            params.append(f"%{cliente}%")
        if estado:
            q += " AND s.estado = %s"
            params.append(estado)
        if fecha_desde:
            q += " AND s.fecha_salida::date >= %s"
            params.append(fecha_desde)
        if fecha_hasta:
            q += " AND s.fecha_salida::date <= %s"
            params.append(fecha_hasta)
        if pedido_interno:
            q += " AND e.pedido_interno ILIKE %s"
            params.append(f"%{pedido_interno}%")

        q += """
            GROUP BY
                s.id, s.folio_bind, s.fecha_salida, s.cliente, s.rfc_cliente,
                s.orden_compra, s.estado,
                p.id, p.codigo, p.descripcion, p.unidad,
                p.cantidad_bind, p.cantidad_embarcada, p.estado,
                e.id, e.pedido_interno, e.created_at, e.fletera,
                e.tipo_entrega, e.condicion_flete, e.estado_embarque,
                e.ruta_pdf_generado, ep.cantidad_embarcada
            ORDER BY s.fecha_salida DESC NULLS LAST, s.folio_bind, p.codigo,
                     e.created_at NULLS LAST
        """
        return _fetchall(conn, q, params)
    finally:
        _release(conn)


# ──────────────────────────────────────────────────────────────────────────────
# STUBS de compatibilidad (eliminables una vez confirmado que nada los llama)
# ──────────────────────────────────────────────────────────────────────────────

def guardar_historial(data: dict) -> int:
    raise NotImplementedError("Reemplazado por crear_embarque()")

def get_historial(limit=200):
    raise NotImplementedError("Reemplazado por get_embarques_filtrados()")

def get_historial_filtrado(*args, **kwargs):
    raise NotImplementedError("Reemplazado por get_salidas_filtradas() / get_embarques_filtrados()")

-- ============================================================
-- PREPARACIÓN EMBARQUES NSG — DDL para Supabase (PostgreSQL)
-- Ejecutar COMPLETO en Supabase → SQL Editor → Run
-- Schema aislado: prep_embarques (convive con ERP_NSG)
-- ============================================================

-- 1. Schema
CREATE SCHEMA IF NOT EXISTS prep_embarques;

-- 2. Catálogos ────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS prep_embarques.remitentes (
    id         SERIAL PRIMARY KEY,
    nombre     TEXT NOT NULL,
    rfc        TEXT DEFAULT '',
    direccion  TEXT DEFAULT '',
    telefono   TEXT DEFAULT '',
    activo     INTEGER DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS prep_embarques.destinatarios (
    id          SERIAL PRIMARY KEY,
    nombre      TEXT NOT NULL,
    rfc         TEXT DEFAULT '',
    direccion   TEXT DEFAULT '',
    cp          TEXT DEFAULT '',
    telefono    TEXT DEFAULT '',
    contacto    TEXT DEFAULT '',
    referencias TEXT DEFAULT '',
    activo      INTEGER DEFAULT 1,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS prep_embarques.fleteras (
    id         SERIAL PRIMARY KEY,
    nombre     TEXT NOT NULL,
    activo     INTEGER DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 3. Salidas Bind ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS prep_embarques.salidas_bind (
    id                SERIAL PRIMARY KEY,
    folio_bind        TEXT NOT NULL,
    fecha_salida      TEXT DEFAULT '',
    cliente           TEXT DEFAULT '',
    rfc_cliente       TEXT DEFAULT '',
    direccion_cliente TEXT DEFAULT '',
    tel_cliente       TEXT DEFAULT '',
    orden_compra      TEXT DEFAULT '',
    notas             TEXT DEFAULT '',
    ruta_pdf_original TEXT DEFAULT '',
    estado            TEXT DEFAULT 'Pendiente',
    created_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS prep_embarques.partidas_bind (
    id                 SERIAL PRIMARY KEY,
    salida_id          INTEGER NOT NULL
                           REFERENCES prep_embarques.salidas_bind(id) ON DELETE CASCADE,
    codigo             TEXT DEFAULT '',
    descripcion        TEXT DEFAULT '',
    unidad             TEXT DEFAULT '',
    cantidad_bind      REAL NOT NULL DEFAULT 0,
    cantidad_embarcada REAL NOT NULL DEFAULT 0,
    estado             TEXT DEFAULT 'Pendiente'
);

-- 4. Embarques ────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS prep_embarques.embarques (
    id                       SERIAL PRIMARY KEY,
    numero_interno           TEXT DEFAULT '',
    remitente_nombre         TEXT DEFAULT '',
    remitente_rfc            TEXT DEFAULT '',
    remitente_tel            TEXT DEFAULT '',
    remitente_direccion      TEXT DEFAULT '',
    destinatario_nombre      TEXT DEFAULT '',
    destinatario_rfc         TEXT DEFAULT '',
    destinatario_direccion   TEXT DEFAULT '',
    destinatario_cp          TEXT DEFAULT '',
    destinatario_tel         TEXT DEFAULT '',
    destinatario_contacto    TEXT DEFAULT '',
    destinatario_referencias TEXT DEFAULT '',
    fletera                  TEXT DEFAULT '',
    tipo_entrega             TEXT DEFAULT '',
    condicion_flete          TEXT DEFAULT '',
    con_remision             INTEGER DEFAULT 0,
    empresa_remision         TEXT DEFAULT '',
    numero_remision          TEXT DEFAULT '',
    estado_remision          TEXT DEFAULT '',
    ruta_pdf_remision        TEXT DEFAULT '',
    observaciones            TEXT DEFAULT '',
    ruta_pdf_generado        TEXT DEFAULT '',
    estado_embarque          TEXT DEFAULT 'Preparado',
    warning_confirmado       INTEGER DEFAULT 0,
    detalle_warnings         TEXT DEFAULT '',
    correcciones_manuales    TEXT DEFAULT '',
    en_bandeja               INTEGER DEFAULT 0,
    created_at               TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS prep_embarques.embarque_salidas (
    embarque_id INTEGER NOT NULL
                    REFERENCES prep_embarques.embarques(id)    ON DELETE CASCADE,
    salida_id   INTEGER NOT NULL
                    REFERENCES prep_embarques.salidas_bind(id) ON DELETE CASCADE,
    PRIMARY KEY (embarque_id, salida_id)
);

CREATE TABLE IF NOT EXISTS prep_embarques.embarque_partidas (
    id                 SERIAL PRIMARY KEY,
    embarque_id        INTEGER NOT NULL
                           REFERENCES prep_embarques.embarques(id)     ON DELETE CASCADE,
    partida_id         INTEGER NOT NULL
                           REFERENCES prep_embarques.partidas_bind(id) ON DELETE CASCADE,
    cantidad_embarcada REAL NOT NULL DEFAULT 0
);

-- 5. Guías ───────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS prep_embarques.guias (
    id                  SERIAL PRIMARY KEY,
    embarque_id         INTEGER NOT NULL
                            REFERENCES prep_embarques.embarques(id) ON DELETE CASCADE,
    numero_guia         TEXT DEFAULT '',
    fletera             TEXT DEFAULT '',
    fecha_embarque_real TEXT DEFAULT '',
    hora_embarque       TEXT DEFAULT '',
    quien_entrego       TEXT DEFAULT '',
    ruta_evidencia      TEXT DEFAULT '',
    observaciones       TEXT DEFAULT '',
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- 6. Auditoría ───────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS prep_embarques.cambios_log (
    id             SERIAL PRIMARY KEY,
    entidad        TEXT DEFAULT '',
    entidad_id     INTEGER,
    campo          TEXT DEFAULT '',
    valor_anterior TEXT DEFAULT '',
    valor_nuevo    TEXT DEFAULT '',
    origen         TEXT DEFAULT '',
    created_at     TIMESTAMPTZ DEFAULT NOW()
);

-- 7. Semilla: remitente NSG por defecto ──────────────────────

INSERT INTO prep_embarques.remitentes (nombre, rfc, direccion, telefono)
SELECT 'GRUPO COMERCIALIZADOR NSG',
       'GCN1309264I6',
       'LABORATORISTAS No. 58B, Col. SIFON C.P 09400, Iztapalapa, Ciudad de México',
       '56332319'
WHERE NOT EXISTS (
    SELECT 1 FROM prep_embarques.remitentes
    WHERE nombre ILIKE '%NSG%'
);

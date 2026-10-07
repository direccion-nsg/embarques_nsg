"""Folio identity compatibility against an explicit disposable PostgreSQL DB."""

import os
import unittest
from unittest.mock import patch

import psycopg2
import psycopg2.extensions
import psycopg2.pool

from modules import database


class FolioIdentityPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        dsn = os.environ.get("EMBARQUES_TEST_DATABASE_URL")
        if not dsn:
            raise unittest.SkipTest("Set EMBARQUES_TEST_DATABASE_URL for disposable PostgreSQL tests")
        parsed = psycopg2.extensions.parse_dsn(dsn)
        if parsed.get("host") not in {"127.0.0.1", "localhost", "::1"} or not parsed.get(
            "dbname", ""
        ).startswith("embarques_test_"):
            raise AssertionError("Refusing a non-local or non-disposable PostgreSQL database")

        with psycopg2.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("DROP SCHEMA IF EXISTS prep_embarques CASCADE")
                cur.execute("CREATE SCHEMA prep_embarques")
                cur.execute("""
                    CREATE TABLE prep_embarques.salidas_bind (
                        id serial PRIMARY KEY, folio_bind text NOT NULL,
                        fecha_salida text DEFAULT '', cliente text DEFAULT '',
                        rfc_cliente text DEFAULT '', direccion_cliente text DEFAULT '',
                        tel_cliente text DEFAULT '', orden_compra text DEFAULT '',
                        notas text DEFAULT '', ruta_pdf_original text DEFAULT ''
                    )
                """)
                cur.execute("""
                    CREATE TABLE prep_embarques.partidas_bind (
                        id serial PRIMARY KEY, salida_id integer NOT NULL
                            REFERENCES prep_embarques.salidas_bind(id),
                        codigo text DEFAULT '', descripcion text DEFAULT '',
                        unidad text DEFAULT '',
                        cantidad_bind numeric(18,6) NOT NULL,
                        cantidad_embarcada numeric(18,6) NOT NULL DEFAULT 0
                    )
                """)
                cur.execute("""
                    CREATE UNIQUE INDEX uq_salidas_bind_normalized_folio
                    ON prep_embarques.salidas_bind (lower(btrim(folio_bind)))
                    WHERE btrim(folio_bind) <> ''
                """)
                cur.execute("""
                    INSERT INTO prep_embarques.salidas_bind (folio_bind)
                    VALUES ('AFAD5267') RETURNING id
                """)
                cls.existing_id = cur.fetchone()[0]
                cur.execute("""
                    INSERT INTO prep_embarques.partidas_bind
                        (salida_id, codigo, cantidad_bind)
                    VALUES (%s, 'SKU-1', 10)
                """, (cls.existing_id,))
        cls.pool = psycopg2.pool.ThreadedConnectionPool(
            1, 5, dsn=dsn, options="-c search_path=prep_embarques"
        )
        cls.pool_patch = patch.object(database, "_pool", lambda: cls.pool)
        cls.pool_patch.start()

    @classmethod
    def tearDownClass(cls):
        cls.pool_patch.stop()
        cls.pool.closeall()

    def test_exact_case_and_whitespace_variants_resolve_same_output(self):
        for folio in ("AFAD5267", "afad5267", " AFAD5267", "AFAD5267 "):
            with self.subTest(folio=folio):
                salida = database.get_salida_por_folio(folio)
                self.assertEqual(salida["id"], self.existing_id)
                self.assertEqual(salida["folio_bind"], "AFAD5267")
                self.assertEqual(len(salida["partidas"]), 1)

    def test_distinct_folio_does_not_match(self):
        self.assertIsNone(database.get_salida_por_folio("AFAD5268"))

    def test_legacy_flow_reuses_normalized_match_with_unique_index(self):
        with patch.object(database, "crear_salida", side_effect=AssertionError("duplicate insert")) as create:
            salida = database.get_salida_por_folio(" afad5267 ")
            if salida is None:
                database.crear_salida({}, [])
            self.assertEqual(salida["id"], self.existing_id)
            create.assert_not_called()

    def test_new_folio_still_creates_and_is_found(self):
        self.assertIsNone(database.get_salida_por_folio("NUEVO-13C1"))
        salida_id = database.crear_salida(
            {"folio_bind": "NUEVO-13C1"},
            [{"codigo": "SKU-2", "cantidad": "3"}],
        )
        self.assertEqual(database.get_salida_por_folio("nuevo-13c1")["id"], salida_id)


if __name__ == "__main__":
    unittest.main()

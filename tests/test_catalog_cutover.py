"""Catalog permissions move to NSG OPS without affecting other legacy pages."""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from modules import auth


class Redirected(Exception):
    pass


class CatalogCutoverTests(unittest.TestCase):
    def setUp(self):
        self.state = SimpleNamespace(
            session_state={},
            switch_page=Mock(side_effect=Redirected),
            error=Mock(), caption=Mock(), stop=Mock(side_effect=Redirected),
        )
        self.streamlit_patch = patch.object(auth, "st", self.state)
        self.streamlit_patch.start()
        self.addCleanup(self.streamlit_patch.stop)

    def test_admin_and_finanzas_lose_only_catalog_permission(self):
        expected = {
            "admin": {"nuevo", "historial", "bandeja", "guias", "usuarios", "planta"},
            "finanzas": {"nuevo", "historial", "bandeja", "guias"},
        }
        for role, permissions in expected.items():
            with self.subTest(role=role):
                self.state.session_state["_auth_user"] = {"role": role}
                self.assertFalse(auth.puede("catalogo"))
                self.assertEqual({name for name in permissions if auth.puede(name)}, permissions)
                self.assertEqual(auth.ROLES[role], permissions)

    def test_direct_catalog_page_guard_denies_both_legacy_writer_roles(self):
        for role in ("admin", "finanzas"):
            with self.subTest(role=role):
                self.state.session_state["_auth_user"] = {"role": role}
                self.state.switch_page.reset_mock()
                with self.assertRaises(Redirected):
                    auth.require_auth("catalogo")
                self.state.switch_page.assert_called_once_with("app.py")

    def test_other_roles_retain_their_permissions(self):
        expected = {
            "ventas": {"historial", "guias"},
            "planta": {"planta", "historial"},
            "direccion": {"historial", "bandeja", "guias", "planta"},
        }
        for role, permissions in expected.items():
            with self.subTest(role=role):
                self.assertEqual(auth.ROLES[role], permissions)

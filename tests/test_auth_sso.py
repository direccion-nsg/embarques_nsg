import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import requests

from modules import auth


TICKET = "A" * 43
URL = "https://ops.example.test/api/sso/consume/EMBARQUES"
SECRET = "example-only-secret"
IDENTITY = {
    "user_id": "user-123", "email": "user@example.test", "name": "Usuario NSG",
    "module_code": "EMBARQUES", "module_role": "direccion",
}
LEGACY_USER = {
    "id": "user-123", "email": "user@example.test",
    "role": "direccion", "nombre": "Usuario NSG",
}


class RerunSignal(Exception):
    pass


class StopSignal(Exception):
    pass


class SwitchSignal(Exception):
    pass


class AuthSSOTests(unittest.TestCase):
    def setUp(self):
        self.st = SimpleNamespace(
            secrets={"nsg_ops": {"sso_consume_url": URL, "sso_secret": SECRET}},
            session_state={}, query_params={},
            rerun=Mock(side_effect=RerunSignal),
            stop=Mock(side_effect=StopSignal),
            switch_page=Mock(side_effect=SwitchSignal),
            error=Mock(), caption=Mock(),
        )
        self.st_patch = patch.object(auth, "st", self.st)
        self.login_patch = patch.object(auth, "_render_login")
        self.st_patch.start()
        self.render_login = self.login_patch.start()
        self.addCleanup(self.st_patch.stop)
        self.addCleanup(self.login_patch.stop)

    @staticmethod
    def response(status=200, identity=None):
        return SimpleNamespace(
            status_code=status, json=Mock(return_value=IDENTITY if identity is None else identity)
        )

    def test_valid_ticket_creates_exact_legacy_user_clears_url_and_reruns(self):
        self.st.query_params.update({"sso_ticket": TICKET, "keep": "yes"})
        with patch.object(auth.requests, "post", return_value=self.response()) as post:
            with self.assertRaises(RerunSignal):
                auth.require_auth("historial")
        post.assert_called_once_with(
            URL, headers={"X-NSG-SSO-Secret": SECRET}, json={"ticket": TICKET},
            timeout=5, allow_redirects=False,
        )
        self.assertEqual(self.st.session_state["_auth_user"], LEGACY_USER)
        self.assertEqual(set(self.st.session_state["_auth_user"]), {"id", "email", "role", "nombre"})
        self.assertEqual(self.st.query_params, {"keep": "yes"})
        self.assertEqual(auth.require_auth("historial"), LEGACY_USER)
        self.assertTrue(auth.puede("bandeja"))
        self.assertFalse(auth.puede("usuarios"))
        self.st.rerun.assert_called_once()

    def test_valid_ticket_overrides_existing_admin_session(self):
        local_user = {"id": "legacy-admin", "email": "admin@example.test", "role": "admin", "nombre": "Admin local"}
        self.st.session_state["_auth_user"] = local_user
        self.st.query_params["sso_ticket"] = TICKET
        with patch.object(auth.requests, "post", return_value=self.response()) as post:
            with self.assertRaises(RerunSignal):
                auth.require_auth("historial")
        post.assert_called_once()
        self.assertEqual(self.st.session_state["_auth_user"], LEGACY_USER)
        self.assertEqual(self.st.session_state["_auth_user"]["role"], "direccion")
        self.assertEqual(self.st.session_state["_auth_source"], "sso")
        self.assertEqual(auth.require_auth("historial"), LEGACY_USER)
        self.assertFalse(auth.puede("usuarios"))
        self.assertNotIn("sso_ticket", self.st.query_params)

    def test_invalid_ticket_preserves_existing_local_session(self):
        local_user = {"id": "legacy-admin", "email": "admin@example.test", "role": "admin", "nombre": "Admin local"}
        self.st.session_state["_auth_user"] = local_user.copy()
        self.st.query_params["sso_ticket"] = TICKET
        with patch.object(auth.requests, "post", return_value=self.response(401)) as post:
            self.assertEqual(auth.require_auth("usuarios"), local_user)
        post.assert_called_once()
        self.assertEqual(self.st.session_state["_auth_user"], local_user)
        self.assertNotIn("_auth_source", self.st.session_state)
        self.assertNotIn("sso_ticket", self.st.query_params)
        self.st.error.assert_not_called()
        self.render_login.assert_not_called()

    def test_invalid_ticket_format_never_calls_endpoint_and_shows_local_login(self):
        self.st.query_params["sso_ticket"] = "bad-ticket"
        with patch.object(auth.requests, "post") as post:
            with self.assertRaises(StopSignal):
                auth.require_auth()
        post.assert_not_called()
        self.assertNotIn("_auth_user", self.st.session_state)
        self.assertNotIn("sso_ticket", self.st.query_params)
        self.st.error.assert_called_once_with(auth._SSO_ERROR)
        self.render_login.assert_called_once()

    def test_unknown_or_null_role_and_wrong_module_are_rejected(self):
        for change in (
            {"module_role": "unknown"}, {"module_role": None},
            {"module_code": "PULSO"}, {"user_id": ""}, {"name": ""},
            {"email": 7},
        ):
            with self.subTest(change=change):
                self.st.query_params["sso_ticket"] = TICKET
                with patch.object(auth.requests, "post", return_value=self.response(identity={**IDENTITY, **change})):
                    with self.assertRaises(StopSignal):
                        auth.require_auth()
                self.assertNotIn("_auth_user", self.st.session_state)
                self.assertNotIn("sso_ticket", self.st.query_params)
                self.assertEqual(self.st.error.call_args.args, (auth._SSO_ERROR,))

    def test_null_email_is_accepted_as_in_core_contract(self):
        with patch.object(auth.requests, "post", return_value=self.response(identity={**IDENTITY, "email": None})):
            result = auth._consume_sso_ticket(TICKET)
        self.assertEqual(result, {**LEGACY_USER, "email": None})

    def test_401_503_and_timeout_fall_back_without_leaking_credentials(self):
        for outcome in (self.response(401), self.response(503), requests.Timeout(f"{TICKET} {SECRET} {URL}")):
            with self.subTest(outcome=type(outcome)):
                self.st.query_params["sso_ticket"] = TICKET
                self.st.error.reset_mock()
                with patch.object(auth.requests, "post", side_effect=outcome if isinstance(outcome, Exception) else None,
                                  return_value=None if isinstance(outcome, Exception) else outcome):
                    with self.assertRaises(StopSignal):
                        auth.require_auth()
                self.assertNotIn("_auth_user", self.st.session_state)
                self.assertNotIn("sso_ticket", self.st.query_params)
                message = self.st.error.call_args.args[0]
                self.assertEqual(message, auth._SSO_ERROR)
                for sensitive in (TICKET, SECRET, URL):
                    self.assertNotIn(sensitive, message)

    def test_replay_after_logout_returns_to_local_login(self):
        self.st.query_params["sso_ticket"] = TICKET
        with patch.object(auth.requests, "post", return_value=self.response()):
            with self.assertRaises(RerunSignal):
                auth.require_auth()
        with patch.object(auth, "_sb") as sb:
            auth.logout()
        sb.assert_not_called()
        self.assertNotIn("_auth_user", self.st.session_state)
        self.st.query_params["sso_ticket"] = TICKET
        with patch.object(auth.requests, "post", return_value=self.response(401)):
            with self.assertRaises(StopSignal):
                auth.require_auth()
        self.render_login.assert_called_once()
        self.assertNotIn("sso_ticket", self.st.query_params)

    def test_local_password_login_and_logout_remain_functional(self):
        user = SimpleNamespace(id="local-1", email="local@example.test", user_metadata={"role": "ventas", "nombre": "Local"})
        sb_auth = SimpleNamespace(
            sign_in_with_password=Mock(return_value=SimpleNamespace(user=user)),
            sign_out=Mock(),
        )
        with patch.object(auth, "_sb", return_value=SimpleNamespace(auth=sb_auth)):
            self.assertEqual(auth.login("local@example.test", "password"), (True, ""))
            self.assertEqual(self.st.session_state["_auth_user"], {
                "id": "local-1", "email": "local@example.test", "role": "ventas", "nombre": "Local",
            })
            auth.logout()
        sb_auth.sign_in_with_password.assert_called_once()
        sb_auth.sign_out.assert_called_once()
        self.assertNotIn("_auth_user", self.st.session_state)

    def test_require_auth_keeps_role_redirect(self):
        self.st.session_state["_auth_user"] = {**LEGACY_USER, "role": "ventas"}
        with self.assertRaises(SwitchSignal):
            auth.require_auth("nuevo")
        self.st.switch_page.assert_called_once_with("pages/2_Historial.py")

    def test_missing_sso_secrets_does_not_affect_local_login(self):
        self.st.secrets = SimpleNamespace(get=Mock(side_effect=FileNotFoundError))
        self.st.query_params["sso_ticket"] = TICKET
        with patch.dict(os.environ, {}, clear=True), patch.object(auth.requests, "post") as post:
            with self.assertRaises(StopSignal):
                auth.require_auth()
        post.assert_not_called()
        self.render_login.assert_called_once()

    def test_environment_fallback_and_https_validation(self):
        self.st.secrets = SimpleNamespace(get=Mock(side_effect=FileNotFoundError))
        with patch.dict(os.environ, {
            "NSG_OPS_SSO_CONSUME_URL": URL,
            "NSG_OPS_EMBARQUES_SSO_SECRET": SECRET,
        }), patch.object(auth.requests, "post", return_value=self.response()) as post:
            self.assertEqual(auth._consume_sso_ticket(TICKET), LEGACY_USER)
        post.assert_called_once()

        self.st.secrets = {"nsg_ops": {"sso_consume_url": "http://ops.example.test/api/sso/consume/EMBARQUES", "sso_secret": SECRET}}
        with patch.object(auth.requests, "post") as post:
            self.assertIsNone(auth._consume_sso_ticket(TICKET))
        post.assert_not_called()


if __name__ == "__main__":
    unittest.main()

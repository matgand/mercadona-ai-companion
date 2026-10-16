"""Unit tests for server.py and scripts/build_full_catalog.py.

Covers:
- Google Identity OAuth / Session security checks:
  * Cookie parsing and HMAC signature validation
  * Allowlisted emails: matgand@gmail.com, mgandolfi@google.com, andrea.anaut@gmail.com, mattia@mgandolfi.altostrat.com
  * Unauthorized user rejection (401/403)
  * Direct Google ID token verification and IAP headers
- Dual microservice role behavior (SERVICE_ROLE=companion vs SERVICE_ROLE=campaign-library)
- REST API Endpoints:
  * GET /api/health (or 404 / custom fallback)
  * GET /api/auth/session
  * POST /api/auth/login
  * POST /api/auth/logout
  * GET /api/mercadona/session & POST /api/mercadona/session
  * GET /api/campaigns & POST /api/campaigns/sync, /api/campaigns/generate, /api/campaigns/status, /api/campaigns/update
  * GET /api/catalog
  * GET /api/parse-constraints
  * POST /api/postal-code
  * POST /api/plan
  * POST /api/recipe-swap
  * POST /api/cookidoo/send
  * POST /api/mercadona/cart
  * OPTIONS preflight requests
  * Static file serving and security (path traversal protection against ../ attacks)
- Catalog builder functions in scripts/build_full_catalog.py:
  * norm_text
  * infer_product_allergens
  * fetch_expanded_mercadona_products (mocked network)
  * build_ingredient_to_product_mapper
  * get_algolia_credentials (mocked network)
  * query_algolia_batch (mocked network)
  * extract_hl_val & extract_hl_list
  * build_cookidoo_5000_catalog (mocked Algolia and filesystem)
"""

from __future__ import annotations

import io
import json
import os
import unittest
from unittest.mock import MagicMock, patch

import scripts.build_full_catalog as catalog_builder
import server


class DummyRequestHandler(server.CompanionRequestHandler):
    """Helper subclass to invoke CompanionRequestHandler methods without opening real sockets."""

    def __init__(self, method: str, path: str, headers: dict[str, str] | None = None, body: bytes = b""):
        self.command = method
        self.path = path
        self.request_version = "HTTP/1.1"
        self.close_connection = True
        self.headers = headers or {}
        self.rfile = io.BytesIO(body)
        self.wfile = io.BytesIO()

        # State captured from send_response and headers
        self.sent_status: int | None = None
        self.sent_headers: list[tuple[str, str]] = []

    def send_response(self, code: int, message: str | None = None) -> None:
        self.sent_status = code

    def send_header(self, keyword: str, value: str) -> None:
        self.sent_headers.append((keyword, value))

    def end_headers(self) -> None:
        pass

    def send_error(self, code: int, message: str | None = None, explain: str | None = None) -> None:
        self.sent_status = code
        self.wfile.write(f"Error {code}: {message}".encode("utf-8"))

    def get_response_json(self) -> dict:
        self.wfile.seek(0)
        content = self.wfile.read().decode("utf-8")
        return json.loads(content) if content else {}


class TestServerSecurityAndAuth(unittest.TestCase):
    """Test suite covering OAuth token verification, HMAC session signing, allowlist enforcement."""

    def setUp(self):
        self.original_secret = server.SESSION_SECRET
        self.original_allowed = server.DEFAULT_ALLOWED_USERS
        server.SESSION_SECRET = "test-secret-key-12345"

    def tearDown(self):
        server.SESSION_SECRET = self.original_secret

    def test_sign_and_verify_valid_session_token(self):
        email = "matgand@gmail.com"
        token = server.sign_session_email(email)
        self.assertIn("|", token)
        verified = server.verify_session_token(token)
        self.assertEqual(verified, email)

    def test_verify_session_token_tampered_signature(self):
        email = "matgand@gmail.com"
        token = server.sign_session_email(email)
        parts = token.split("|")
        tampered_token = f"{parts[0]}|deadbeef12345678"
        self.assertIsNone(server.verify_session_token(tampered_token))

    def test_verify_session_token_empty_or_malformed(self):
        self.assertIsNone(server.verify_session_token(None))
        self.assertIsNone(server.verify_session_token(""))
        self.assertIsNone(server.verify_session_token("invalid-no-pipe"))

    def test_verify_session_token_unauthorized_user(self):
        email = "hacker@evil.com"
        token = server.sign_session_email(email)
        self.assertIsNone(server.verify_session_token(token))

    def test_allowlisted_users_retrieval_default(self):
        with patch.dict(os.environ, {"ALLOWED_USERS": ""}):
            users = server.get_allowed_users()
            self.assertIn("matgand@gmail.com", users)
            self.assertIn("mgandolfi@google.com", users)
            self.assertIn("andrea.anaut@gmail.com", users)
            self.assertIn("mattia@mgandolfi.altostrat.com", users)

    def test_allowlisted_users_retrieval_custom_env(self):
        with patch.dict(os.environ, {"ALLOWED_USERS": "custom1@google.com, custom2@gmail.com "}):
            users = server.get_allowed_users()
            self.assertEqual(users, ["custom1@google.com", "custom2@gmail.com"])

    @patch("urllib.request.urlopen")
    def test_verify_google_id_token_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "email": "mgandolfi@google.com",
            "email_verified": "true",
            "aud": "mock-client-id"
        }).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        with patch.object(server, "GOOGLE_CLIENT_ID", "mock-client-id"):
            email = server.verify_google_id_token("valid-jwt-token")
            self.assertEqual(email, "mgandolfi@google.com")

    @patch("urllib.request.urlopen")
    def test_verify_google_id_token_audience_mismatch(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "email": "mgandolfi@google.com",
            "email_verified": "true",
            "aud": "wrong-client-id"
        }).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        with patch.object(server, "GOOGLE_CLIENT_ID", "expected-client-id"):
            email = server.verify_google_id_token("jwt-token")
            self.assertIsNone(email)

    @patch("urllib.request.urlopen")
    def test_verify_google_id_token_unverified_email(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "email": "mgandolfi@google.com",
            "email_verified": "false",
            "aud": ""
        }).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        email = server.verify_google_id_token("jwt-token")
        self.assertIsNone(email)

    @patch("urllib.request.urlopen", side_effect=Exception("Network error connecting to oauth2 endpoint"))
    def test_verify_google_id_token_network_failure(self, mock_urlopen):
        email = server.verify_google_id_token("jwt-token")
        self.assertIsNone(email)

    def test_authenticated_user_via_iap_header(self):
        handler = DummyRequestHandler("GET", "/api/auth/session", headers={
            "X-Goog-Authenticated-User-Email": "accounts.google.com:mgandolfi@google.com"
        })
        self.assertEqual(handler._get_authenticated_user(), "mgandolfi@google.com")

    def test_authenticated_user_via_iap_header_unauthorized(self):
        handler = DummyRequestHandler("GET", "/api/auth/session", headers={
            "X-Goog-Authenticated-User-Email": "accounts.google.com:unauthorized@intruder.com"
        })
        self.assertIsNone(handler._get_authenticated_user())

    def test_authenticated_user_via_cookie(self):
        token = server.sign_session_email("andrea.anaut@gmail.com")
        handler = DummyRequestHandler("GET", "/api/auth/session", headers={
            "Cookie": f"mercadona_session={token}"
        })
        self.assertEqual(handler._get_authenticated_user(), "andrea.anaut@gmail.com")

    def test_internal_service_sync_token_validation(self):
        expected = server.hashlib.sha256(f"internal-sync:{server.SESSION_SECRET}".encode("utf-8")).hexdigest()[:32]
        valid_handler = DummyRequestHandler("POST", "/api/campaigns/sync", headers={
            "X-Internal-Sync-Token": expected
        })
        self.assertTrue(valid_handler._is_internal_service_sync())

        invalid_handler = DummyRequestHandler("POST", "/api/campaigns/sync", headers={
            "X-Internal-Sync-Token": "wrong-token"
        })
        self.assertFalse(invalid_handler._is_internal_service_sync())


class TestServerEndpoints(unittest.TestCase):
    """Test suite covering all REST endpoints and microservice roles."""

    def setUp(self):
        self.original_secret = server.SESSION_SECRET
        server.SESSION_SECRET = "test-secret-key-12345"

    def tearDown(self):
        server.SESSION_SECRET = self.original_secret

    def _auth_cookie(self, email: str = "matgand@gmail.com") -> str:
        token = server.sign_session_email(email)
        return f"mercadona_session={token}"

    def test_options_cors_preflight(self):
        handler = DummyRequestHandler("OPTIONS", "/api/plan")
        handler.do_OPTIONS()
        self.assertEqual(handler.sent_status, 204)
        header_keys = [h[0] for h in handler.sent_headers]
        self.assertIn("Access-Control-Allow-Origin", header_keys)
        self.assertIn("Access-Control-Allow-Methods", header_keys)
        self.assertIn("Access-Control-Allow-Headers", header_keys)

    def test_get_api_auth_session_unauthenticated(self):
        handler = DummyRequestHandler("GET", "/api/auth/session")
        handler.do_GET()
        self.assertEqual(handler.sent_status, 200)
        data = handler.get_response_json()
        self.assertFalse(data["authenticated"])
        self.assertIsNone(data["user"])
        self.assertIn("matgand@gmail.com", data["allowed_users"])

    def test_get_api_auth_session_authenticated(self):
        handler = DummyRequestHandler("GET", "/api/auth/session", headers={
            "Cookie": self._auth_cookie("mgandolfi@google.com")
        })
        handler.do_GET()
        self.assertEqual(handler.sent_status, 200)
        data = handler.get_response_json()
        self.assertTrue(data["authenticated"])
        self.assertEqual(data["user"], "mgandolfi@google.com")

    def test_post_api_auth_login_with_valid_google_token(self):
        with patch.object(server, "verify_google_id_token", return_value="matgand@gmail.com"):
            req_body = json.dumps({"credential": "valid_token"}).encode("utf-8")
            handler = DummyRequestHandler("POST", "/api/auth/login", headers={
                "Content-Length": str(len(req_body)),
                "Content-Type": "application/json"
            }, body=req_body)
            handler.do_POST()

            self.assertEqual(handler.sent_status, 200)
            data = handler.get_response_json()
            self.assertTrue(data["authenticated"])
            self.assertEqual(data["user"], "matgand@gmail.com")
            # Verify Set-Cookie is in headers
            cookie_headers = [v for k, v in handler.sent_headers if k == "Set-Cookie"]
            self.assertTrue(any("mercadona_session=" in c for c in cookie_headers))

    def test_post_api_auth_login_with_invalid_token(self):
        with patch.object(server, "verify_google_id_token", return_value=None):
            req_body = json.dumps({"credential": "bad_token"}).encode("utf-8")
            handler = DummyRequestHandler("POST", "/api/auth/login", headers={
                "Content-Length": str(len(req_body)),
                "Content-Type": "application/json"
            }, body=req_body)
            handler.do_POST()

            self.assertEqual(handler.sent_status, 401)
            data = handler.get_response_json()
            self.assertEqual(data["code"], "INVALID_GOOGLE_TOKEN")

    def test_post_api_auth_login_with_unauthorized_email(self):
        with patch.object(server, "verify_google_id_token", return_value="stranger@random.com"):
            req_body = json.dumps({"credential": "token_for_stranger"}).encode("utf-8")
            handler = DummyRequestHandler("POST", "/api/auth/login", headers={
                "Content-Length": str(len(req_body)),
                "Content-Type": "application/json"
            }, body=req_body)
            handler.do_POST()

            self.assertEqual(handler.sent_status, 403)
            data = handler.get_response_json()
            self.assertEqual(data["code"], "USER_NOT_ALLOWED")

    def test_post_api_auth_login_missing_credentials_and_no_iap(self):
        req_body = json.dumps({}).encode("utf-8")
        handler = DummyRequestHandler("POST", "/api/auth/login", headers={
            "Content-Length": str(len(req_body)),
            "Content-Type": "application/json"
        }, body=req_body)
        handler.do_POST()

        self.assertEqual(handler.sent_status, 401)
        data = handler.get_response_json()
        self.assertEqual(data["code"], "IAP_REQUIRED")

    def test_post_api_auth_logout(self):
        handler = DummyRequestHandler("POST", "/api/auth/logout")
        handler.do_POST()
        self.assertEqual(handler.sent_status, 200)
        data = handler.get_response_json()
        self.assertFalse(data["authenticated"])
        self.assertIsNone(data["user"])
        cookie_headers = [v for k, v in handler.sent_headers if k == "Set-Cookie"]
        self.assertTrue(any("Max-Age=0" in c for c in cookie_headers))

    def test_get_api_mercadona_session(self):
        with patch("server.get_mercadona_session_status", return_value={"connected": True, "warehouse": "mad3"}):
            handler = DummyRequestHandler("GET", "/api/mercadona/session", headers={
                "Cookie": self._auth_cookie("matgand@gmail.com")
            })
            handler.do_GET()
            self.assertEqual(handler.sent_status, 200)
            data = handler.get_response_json()
            self.assertTrue(data["connected"])
            self.assertEqual(data["warehouse"], "mad3")

    def test_get_api_campaigns_dual_microservice_behavior(self):
        dummy_campaigns = [
            {"id": "camp1", "title": "Dieta Mediterránea", "category": "Mediterránea", "status": "Activa"},
            {"id": "camp2", "title": "Cena Rápida", "category": "Rápida", "status": "Borrador"},
        ]

        # Case 1: SERVICE_ROLE=campaign-library (loads local campaigns directly)
        with patch.object(server, "SERVICE_ROLE", "campaign-library"):
            with patch("server.load_local_campaigns", return_value=dummy_campaigns):
                handler = DummyRequestHandler("GET", "/api/campaigns")
                handler.do_GET()
                self.assertEqual(handler.sent_status, 200)
                data = handler.get_response_json()
                self.assertEqual(data["service"], "campaign-library")
                self.assertEqual(len(data["campaigns"]), 2)
                self.assertEqual(len(data["active_campaigns"]), 1)

        # Case 2: SERVICE_ROLE=companion (fetches from remote or local)
        with patch.object(server, "SERVICE_ROLE", "companion"):
            with patch("server.fetch_campaigns_from_remote_or_local", return_value=dummy_campaigns):
                handler = DummyRequestHandler("GET", "/api/campaigns?status=Activa&category=Mediterránea")
                handler.do_GET()
                self.assertEqual(handler.sent_status, 200)
                data = handler.get_response_json()
                self.assertEqual(len(data["campaigns"]), 1)
                self.assertEqual(data["campaigns"][0]["id"], "camp1")

    def test_get_api_catalog(self):
        with patch("server.resolve_postal_code", return_value={"postal_code": "46001", "warehouse": "vlc1", "source": "test"}):
            with patch("server.load_snapshot_products", return_value={"p1": {"id": "p1", "name": "Leche"}}):
                with patch("server.load_cookidoo_catalog", return_value=[{"recipe_id": "r1", "name": "Tortilla"}]):
                    handler = DummyRequestHandler("GET", "/api/catalog?postal_code=46001")
                    handler.do_GET()
                    self.assertEqual(handler.sent_status, 200)
                    data = handler.get_response_json()
                    self.assertEqual(data["postal_code"], "46001")
                    self.assertEqual(data["warehouse"], "vlc1")
                    self.assertEqual(len(data["products"]), 1)
                    self.assertEqual(len(data["recipes"]), 1)

    def test_get_api_parse_constraints(self):
        with patch("server.parse_constraints", return_value={"quick": True, "vegetarian": False}):
            with patch("server.format_constraint_pills", return_value=["Rápido"]):
                handler = DummyRequestHandler("GET", "/api/parse-constraints?q=cenas+rapidas")
                handler.do_GET()
                self.assertEqual(handler.sent_status, 200)
                data = handler.get_response_json()
                self.assertEqual(data["constraints"]["quick"], True)
                self.assertEqual(data["pills"], ["Rápido"])

    def test_unauthenticated_post_api_rejection(self):
        # Protected endpoints must reject unauthenticated requests with 401
        req_body = json.dumps({"prompt": "cena rica"}).encode("utf-8")
        handler = DummyRequestHandler("POST", "/api/plan", headers={
            "Content-Length": str(len(req_body)),
            "Content-Type": "application/json"
        }, body=req_body)
        handler.do_POST()
        self.assertEqual(handler.sent_status, 401)
        data = handler.get_response_json()
        self.assertEqual(data["code"], "AUTHENTICATION_REQUIRED")

    def test_unauthorized_iap_post_api_rejection(self):
        # Protected endpoints must reject unauthorized IAP email with 403
        req_body = json.dumps({"prompt": "cena rica"}).encode("utf-8")
        handler = DummyRequestHandler("POST", "/api/plan", headers={
            "Content-Length": str(len(req_body)),
            "Content-Type": "application/json",
            "X-Goog-Authenticated-User-Email": "accounts.google.com:evil@attacker.com"
        }, body=req_body)
        handler.do_POST()
        self.assertEqual(handler.sent_status, 403)
        data = handler.get_response_json()
        self.assertEqual(data["code"], "USER_NOT_ALLOWED")

    def test_post_api_plan_success(self):
        req_body = json.dumps({"message": "Menu semanal equilibrado", "postalCode": "28001"}).encode("utf-8")
        dummy_plan = {"meals": [{"day": "Lunes", "lunch": "Ensalada"}], "summary": "Menu"}
        with patch("server.validate_meal_planning_prompt", return_value=(True, "")):
            with patch("server.build_weekly_plan", return_value=dummy_plan):
                handler = DummyRequestHandler("POST", "/api/plan", headers={
                    "Content-Length": str(len(req_body)),
                    "Content-Type": "application/json",
                    "Cookie": self._auth_cookie("matgand@gmail.com")
                }, body=req_body)
                handler.do_POST()
                self.assertEqual(handler.sent_status, 200)
                data = handler.get_response_json()
                self.assertEqual(data["summary"], "Menu")

    def test_post_api_plan_empty_prompt_400(self):
        req_body = json.dumps({"message": ""}).encode("utf-8")
        handler = DummyRequestHandler("POST", "/api/plan", headers={
            "Content-Length": str(len(req_body)),
            "Content-Type": "application/json",
            "Cookie": self._auth_cookie("matgand@gmail.com")
        }, body=req_body)
        handler.do_POST()
        self.assertEqual(handler.sent_status, 400)

    def test_post_api_plan_out_of_scope_422(self):
        req_body = json.dumps({"message": "Cuéntame un chiste de abogados"}).encode("utf-8")
        with patch("server.validate_meal_planning_prompt", return_value=(False, "Petición fuera de ámbito gastronómico.")):
            handler = DummyRequestHandler("POST", "/api/plan", headers={
                "Content-Length": str(len(req_body)),
                "Content-Type": "application/json",
                "Cookie": self._auth_cookie("matgand@gmail.com")
            }, body=req_body)
            handler.do_POST()
            self.assertEqual(handler.sent_status, 422)
            data = handler.get_response_json()
            self.assertEqual(data["code"], "OUT_OF_SCOPE_PROMPT")

    def test_post_api_recipe_swap(self):
        req_body = json.dumps({
            "targetRecipeId": "rec123",
            "postalCode": "28016",
            "rotation": 2
        }).encode("utf-8")
        swap_result = {"recipe": {"recipe_id": "rec456", "name": "Guiso"}}
        with patch("server.swap_single_recipe", return_value=swap_result):
            handler = DummyRequestHandler("POST", "/api/recipe-swap", headers={
                "Content-Length": str(len(req_body)),
                "Content-Type": "application/json",
                "Cookie": self._auth_cookie("mgandolfi@google.com")
            }, body=req_body)
            handler.do_POST()
            self.assertEqual(handler.sent_status, 200)
            data = handler.get_response_json()
            self.assertEqual(data["recipe"]["recipe_id"], "rec456")

    def test_post_api_postal_code(self):
        req_body = json.dumps({"postal_code": "46001"}).encode("utf-8")
        with patch("server.resolve_postal_code", return_value={"postal_code": "46001", "warehouse": "vlc1", "source": "hub"}):
            handler = DummyRequestHandler("POST", "/api/postal-code", headers={
                "Content-Length": str(len(req_body)),
                "Content-Type": "application/json",
                "Cookie": self._auth_cookie("andrea.anaut@gmail.com")
            }, body=req_body)
            handler.do_POST()
            self.assertEqual(handler.sent_status, 200)
            data = handler.get_response_json()
            self.assertEqual(data["postal_code"], "46001")
            self.assertEqual(data["warehouse"], "vlc1")

    def test_post_api_cookidoo_send(self):
        req_body = json.dumps({"recipe_id": "r999"}).encode("utf-8")
        with patch("server.send_recipe_to_thermomix", return_value={"success": True, "device": "TM6"}):
            handler = DummyRequestHandler("POST", "/api/cookidoo/send", headers={
                "Content-Length": str(len(req_body)),
                "Content-Type": "application/json",
                "Cookie": self._auth_cookie("matgand@gmail.com")
            }, body=req_body)
            handler.do_POST()
            self.assertEqual(handler.sent_status, 200)
            data = handler.get_response_json()
            self.assertTrue(data["success"])

    def test_post_api_mercadona_session_connect_and_disconnect(self):
        # 1. Connect
        req_connect = json.dumps({"auth_input": "user:pass", "postal_code": "28016"}).encode("utf-8")
        with patch("server.verify_and_save_mercadona_session", return_value={"connected": True, "email": "user@test.com"}):
            handler = DummyRequestHandler("POST", "/api/mercadona/session", headers={
                "Content-Length": str(len(req_connect)),
                "Content-Type": "application/json",
                "Cookie": self._auth_cookie("matgand@gmail.com")
            }, body=req_connect)
            handler.do_POST()
            self.assertEqual(handler.sent_status, 200)
            self.assertTrue(handler.get_response_json()["connected"])

        # 2. Disconnect
        req_disc = json.dumps({"action": "disconnect"}).encode("utf-8")
        with patch("server.clear_mercadona_session", return_value={"connected": False}):
            handler = DummyRequestHandler("POST", "/api/mercadona/session", headers={
                "Content-Length": str(len(req_disc)),
                "Content-Type": "application/json",
                "Cookie": self._auth_cookie("matgand@gmail.com")
            }, body=req_disc)
            handler.do_POST()
            self.assertEqual(handler.sent_status, 200)
            self.assertFalse(handler.get_response_json()["connected"])

    def test_post_api_mercadona_cart(self):
        req_body = json.dumps({
            "basket": [{"product_id": "123", "quantity": 2}],
            "postal_code": "28016",
            "mode": "add"
        }).encode("utf-8")
        cart_resp = {"cart_id": "cart_abc", "items_count": 2, "total_cost": 5.40}
        with patch("server.prepare_mercadona_oneclick_cart", return_value=cart_resp):
            handler = DummyRequestHandler("POST", "/api/mercadona/cart", headers={
                "Content-Length": str(len(req_body)),
                "Content-Type": "application/json",
                "Cookie": self._auth_cookie("matgand@gmail.com")
            }, body=req_body)
            handler.do_POST()
            self.assertEqual(handler.sent_status, 200)
            data = handler.get_response_json()
            self.assertEqual(data["cart_id"], "cart_abc")

    def test_post_api_campaigns_generate_status_update(self):
        # 1. Generate
        req_gen = json.dumps({"brief": "Promoción de verano", "category": "Verano"}).encode("utf-8")
        dummy_created = {"id": "c_new", "title": "Verano"}
        with patch("server.generate_campaign_from_brief", return_value=dummy_created):
            with patch("server.load_local_campaigns", return_value=[dummy_created]):
                handler = DummyRequestHandler("POST", "/api/campaigns/generate", headers={
                    "Content-Length": str(len(req_gen)),
                    "Content-Type": "application/json",
                    "Cookie": self._auth_cookie("matgand@gmail.com")
                }, body=req_gen)
                handler.do_POST()
                self.assertEqual(handler.sent_status, 200)
                data = handler.get_response_json()
                self.assertEqual(data["campaign"]["id"], "c_new")

        # 2. Status update
        req_status = json.dumps({"id": "c_new", "status": "Pausada"}).encode("utf-8")
        dummy_updated = {"id": "c_new", "status": "Pausada"}
        with patch("server.update_campaign_record", return_value=dummy_updated):
            with patch("server.load_local_campaigns", return_value=[dummy_updated]):
                handler = DummyRequestHandler("POST", "/api/campaigns/status", headers={
                    "Content-Length": str(len(req_status)),
                    "Content-Type": "application/json",
                    "Cookie": self._auth_cookie("matgand@gmail.com")
                }, body=req_status)
                handler.do_POST()
                self.assertEqual(handler.sent_status, 200)
                data = handler.get_response_json()
                self.assertEqual(data["campaign"]["status"], "Pausada")

        # 3. Arbitrary update
        req_upd = json.dumps({"id": "c_new", "updates": {"title": "Nuevo Titulo"}}).encode("utf-8")
        dummy_upd = {"id": "c_new", "title": "Nuevo Titulo"}
        with patch("server.update_campaign_record", return_value=dummy_upd):
            with patch("server.load_local_campaigns", return_value=[dummy_upd]):
                handler = DummyRequestHandler("POST", "/api/campaigns/update", headers={
                    "Content-Length": str(len(req_upd)),
                    "Content-Type": "application/json",
                    "Cookie": self._auth_cookie("matgand@gmail.com")
                }, body=req_upd)
                handler.do_POST()
                self.assertEqual(handler.sent_status, 200)
                data = handler.get_response_json()
                self.assertEqual(data["campaign"]["title"], "Nuevo Titulo")

    def test_post_api_campaigns_sync_via_internal_token(self):
        expected_token = server.hashlib.sha256(f"internal-sync:{server.SESSION_SECRET}".encode("utf-8")).hexdigest()[:32]
        payload = json.dumps({"campaigns": [{"id": "c1", "title": "Camp 1"}]}).encode("utf-8")
        with patch("server.save_local_campaigns", return_value=[{"id": "c1"}]):
            handler = DummyRequestHandler("POST", "/api/campaigns/sync", headers={
                "Content-Length": str(len(payload)),
                "Content-Type": "application/json",
                "X-Internal-Sync-Token": expected_token
            }, body=payload)
            handler.do_POST()
            self.assertEqual(handler.sent_status, 200)
            data = handler.get_response_json()
            self.assertTrue(data["ok"])
            self.assertEqual(data["count"], 1)

    def test_post_api_campaigns_sync_invalid_payload(self):
        expected_token = server.hashlib.sha256(f"internal-sync:{server.SESSION_SECRET}".encode("utf-8")).hexdigest()[:32]
        payload = json.dumps({"campaigns": "not-a-list"}).encode("utf-8")
        handler = DummyRequestHandler("POST", "/api/campaigns/sync", headers={
            "Content-Length": str(len(payload)),
            "Content-Type": "application/json",
            "X-Internal-Sync-Token": expected_token
        }, body=payload)
        handler.do_POST()
        self.assertEqual(handler.sent_status, 400)


class TestStaticFilesAndSecurity(unittest.TestCase):
    """Test suite covering static file serving and path traversal protection."""

    def test_path_traversal_protection(self):
        # Attempting directory traversal: ../server.py
        # server.py resolves path against PUBLIC_DIR. If not starting with PUBLIC_DIR or not file, falls back to default_html (index.html or marketing.html).
        handler = DummyRequestHandler("GET", "/../../server.py")
        handler.do_GET()
        self.assertEqual(handler.sent_status, 200)
        # Verify it served HTML content rather than Python source code
        content = handler.wfile.getvalue().decode("utf-8", "ignore")
        self.assertNotIn("class CompanionRequestHandler", content)
        self.assertTrue("<html" in content.lower() or "<!doctype html" in content.lower())

    def test_path_traversal_encoded_and_relative_attempts(self):
        traversal_attempts = [
            "/..%2f..%2fetc%2fpasswd",
            "/....//....//server.py",
            "/subdir/../../server.py",
            "/etc/passwd",
        ]
        for attempt in traversal_attempts:
            handler = DummyRequestHandler("GET", attempt)
            handler.do_GET()
            self.assertEqual(handler.sent_status, 200)
            content = handler.wfile.getvalue().decode("utf-8", "ignore")
            self.assertNotIn("root:", content)
            self.assertNotIn("class CompanionRequestHandler", content)
            self.assertTrue("<html" in content.lower() or "<!doctype html" in content.lower())

    def test_session_token_multiple_pipes_and_adversarial_shapes(self):
        # rsplit('|', 1) in server.py splits by last pipe
        token = "matgand@gmail.com|extra_data|invalid_sig"
        self.assertIsNone(server.verify_session_token(token))

        # Empty email part
        self.assertIsNone(server.verify_session_token("|some_sig"))
        self.assertIsNone(server.verify_session_token("   |   "))

    def test_expired_session_token_rejected(self):
        past_exp = int(server.time.time()) - 60
        expired_token = server.sign_session_email("matgand@gmail.com", exp=past_exp)
        self.assertIsNone(server.verify_session_token(expired_token))

    def test_iap_jwt_enforcement_when_enabled(self):
        with patch.dict(os.environ, {"ENFORCE_IAP_JWT": "1"}):
            # Missing X-Goog-IAP-JWT-Assertion when ENFORCE_IAP_JWT=1 must reject spoofed email header
            handler = DummyRequestHandler("GET", "/api/auth/session", headers={
                "X-Goog-Authenticated-User-Email": "accounts.google.com:mgandolfi@google.com"
            })
            self.assertIsNone(handler._get_authenticated_user())

    def test_oversized_and_invalid_content_length_rejected(self):
        # 1. Oversized Content-Length -> 413
        handler_413 = DummyRequestHandler("POST", "/api/postal-code", headers={
            "Content-Length": str(server.MAX_BODY_BYTES + 1024),
            "Content-Type": "application/json",
        }, body=b"{}")
        handler_413.do_POST()
        self.assertEqual(handler_413.sent_status, 413)

        # 2. Invalid non-numeric Content-Length -> 400
        handler_400 = DummyRequestHandler("POST", "/api/postal-code", headers={
            "Content-Length": "not-a-number",
            "Content-Type": "application/json",
        }, body=b"{}")
        handler_400.do_POST()
        self.assertEqual(handler_400.sent_status, 400)

        # 3. Negative Content-Length -> 400
        handler_neg = DummyRequestHandler("POST", "/api/postal-code", headers={
            "Content-Length": "-50",
            "Content-Type": "application/json",
        }, body=b"{}")
        handler_neg.do_POST()
        self.assertEqual(handler_neg.sent_status, 400)

    def test_unauthenticated_sensitive_get_endpoints_require_auth(self):
        for ep in ["/api/preferences", "/api/mercadona/session"]:
            handler = DummyRequestHandler("GET", ep)
            handler.do_GET()
            self.assertEqual(handler.sent_status, 401)

    def test_security_headers_present_on_responses(self):
        handler = DummyRequestHandler("GET", "/")
        handler.do_GET()
        header_dict = dict(handler.sent_headers)
        self.assertIn("Content-Security-Policy", header_dict)
        self.assertEqual(header_dict.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(header_dict.get("X-Frame-Options"), "DENY")

    def test_static_file_serving_index(self):
        handler = DummyRequestHandler("GET", "/")
        handler.do_GET()
        self.assertEqual(handler.sent_status, 200)
        content = handler.wfile.getvalue().decode("utf-8", "ignore")
        self.assertTrue("<html" in content.lower() or "<!doctype html" in content.lower())

    def test_static_file_serving_routes_alias(self):
        for route in ["/agent", "/catalog", "/sources", "/marketing"]:
            handler = DummyRequestHandler("GET", route)
            handler.do_GET()
            self.assertEqual(handler.sent_status, 200)

    def test_static_file_not_found_fallback(self):
        handler = DummyRequestHandler("GET", "/non_existent_page_12345")
        handler.do_GET()
        self.assertEqual(handler.sent_status, 200)
        # Should fallback to index.html or marketing.html


class TestCatalogBuilder(unittest.TestCase):
    """Test suite covering scripts/build_full_catalog.py algorithms and error handling."""

    def test_norm_text(self):
        self.assertEqual(catalog_builder.norm_text("Árbol de Limón!"), "arbol de limon")
        self.assertEqual(catalog_builder.norm_text("PIZZA IBÉRICA"), "pizza iberica")

    def test_infer_product_allergens(self):
        # Dairy
        d = catalog_builder.infer_product_allergens("Queso rallado Gouda")
        self.assertIn("leche", d.lower())

        # Gluten
        g = catalog_builder.infer_product_allergens("Pan de molde integral")
        self.assertIn("gluten", g.lower())

        # Eggs
        e = catalog_builder.infer_product_allergens("Mayonesa casera con huevos de gallina")
        self.assertIn("huevo", e.lower())

        # Fish & Crustaceans
        f = catalog_builder.infer_product_allergens("Filete de salmón fresco y langostinos")
        self.assertIn("pescado", f.lower())
        self.assertIn("crustáceos", f.lower())

        # Preserves explicit allergens if not default
        custom = "Alérgenos: Soja, Mostaza"
        self.assertEqual(catalog_builder.infer_product_allergens("Cualquier producto", custom), custom)

    def test_build_ingredient_to_product_mapper(self):
        mock_products = {
            "4740": {"name": "Aceite de oliva virgen extra", "unit_price": 4.50},
            "69089": {"name": "Cebolla", "unit_price": 1.20},
            "3400": {"name": "Pechuga de pollo", "unit_price": 5.00},
            "5044": {"name": "Arroz redondo", "unit_price": 1.30},
        }
        mapper = catalog_builder.build_ingredient_to_product_mapper(mock_products)

        # Mappings from direct rules
        mapped = mapper(["2 cebollas picadas", "pechuga de pollo"], ["poultry", "vegetables"])
        self.assertIn("69089", mapped)
        self.assertIn("3400", mapped)

    @patch("urllib.request.urlopen")
    def test_fetch_expanded_mercadona_products_mock(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "categories": [
                {
                    "products": [
                        {
                            "id": "9999",
                            "display_name": "Manzana Golden",
                            "price_instructions": {
                                "unit_price": "2.10",
                                "unit_size": "1",
                                "size_format": "kg"
                            },
                            "packaging": "Bolsa"
                        }
                    ]
                }
            ]
        }).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        with patch("pathlib.Path.read_text", return_value='[{"id": "1111", "name": "Existing"}]'):
            with patch.object(catalog_builder, "FOOD_SUBCATEGORIES", [27]):
                products = catalog_builder.fetch_expanded_mercadona_products()
                self.assertIn("1111", products)
                self.assertIn("9999", products)
                self.assertEqual(products["9999"]["name"], "Manzana Golden")
                self.assertEqual(products["9999"]["unit_price"], 2.10)

    def test_extract_hl_val_and_list(self):
        node_dict = {"value": "Hello World"}
        self.assertEqual(catalog_builder.extract_hl_val(node_dict), "Hello World")
        self.assertEqual(catalog_builder.extract_hl_val("plain text"), "")

        list_nodes = [{"value": "dairy"}, {"value": "gluten"}, {"missing": 123}]
        self.assertEqual(catalog_builder.extract_hl_list(list_nodes), ["dairy", "gluten"])
        self.assertEqual(catalog_builder.extract_hl_list(None), [])

    @patch("urllib.request.urlopen")
    def test_query_algolia_batch_mock(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "hits": [{"id": "rec_101", "title": "Paella Valenciana"}]
        }).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        hits = catalog_builder.query_algolia_batch("APP_ID", "API_KEY", ["facet:test"], hits_per_page=10)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["id"], "rec_101")


if __name__ == "__main__":
    unittest.main()

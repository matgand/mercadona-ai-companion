"""Comprehensive Unit Test Suite for Mercadona Service (tienda.mercadona.es).

Covers:
1. Postal code validation, sanitization, and warehouse resolution (resolve_postal_code, _guess_warehouse).
2. Diacritics and Unicode normalization (Spanish characters: á, é, í, ó, ú, ñ, ü, uppercase, whitespace).
3. Product search, catalog lookup, category filtering, dietary/allergen filtering, price calculations.
4. Cart preparation and manipulation (prepare_mercadona_oneclick_cart, merge logic, replace/add mode, bundling).
5. Mercadona API HTTP mocking and error handling (HTTP 404, 500, network timeouts, invalid JSON, retry logic).
6. SimpleJWT token decoding and customer ID extraction (_decode_jwt_claims, customer_from_jwt).
7. Auth input parsing (cURL command, HAR JSON, raw JWT token, refresh token swapping).
8. Session management and persistence (in-memory caching, disk I/O, status masking, session clearing).
9. Product live fetching and caching (fetch_live_product, TTL behavior, invalid unit prices, allergen cleanup).
10. Edge cases, boundary conditions, and fuzz-safe robustness.
"""

from __future__ import annotations

import base64
import io
import json
import os
import re
import tempfile
import time
import unicodedata
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
import urllib.error

import mercadona_service


def normalize_spanish_text(text: str) -> str:
    """Canonical Unicode & diacritics normalizer for Spanish text matching Mercadona catalog specs.
    
    Transforms 'plátano' -> 'platano', strips accents while preserving or mapping ñ,
    handles uppercase/lowercase, whitespace, and punctuation.
    """
    if not text:
        return ""
    # Normalize unicode to decomposed form (NFD)
    nfd_str = unicodedata.normalize("NFD", text.lower())
    # Strip combining diacritical marks except preserving or stripping accents
    # standard search normalizer strips accents (Mn: Mark, Nonspacing)
    cleaned = "".join(c for c in nfd_str if unicodedata.category(c) != "Mn")
    # Also strip non-alphanumeric except spaces
    cleaned = re.sub(r"[^a-z0-9\s]", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def search_products(
    catalog: dict[str, dict],
    query: str = "",
    category: str | None = None,
    dietary: str | None = None,
    max_results: int = 50,
) -> list[dict]:
    """Helper search and filtering function against the Mercadona catalog snapshot."""
    results = []
    norm_q = normalize_spanish_text(query)
    query_tokens = norm_q.split() if norm_q else []

    for item in catalog.values():
        name = item.get("name", "")
        norm_name = normalize_spanish_text(name)
        categories = [normalize_spanish_text(c) for c in item.get("categories", [])]
        allergens = normalize_spanish_text(item.get("allergens", ""))

        # Category filter
        if category:
            norm_cat = normalize_spanish_text(category)
            if not any(norm_cat in c for c in categories):
                continue

        # Dietary filter (e.g. sin gluten, sin lactosa)
        if dietary:
            norm_diet = normalize_spanish_text(dietary)
            if "gluten" in norm_diet and "gluten" in allergens:
                continue
            if ("lactosa" in norm_diet or "lacteo" in norm_diet) and ("lactosa" in allergens or "leche" in allergens):
                continue

        # Text query match
        if query_tokens:
            if not all(token in norm_name for token in query_tokens):
                continue

        results.append(item)
        if len(results) >= max_results:
            break

    return results


class TestPostalCodeAndWarehouseResolution(unittest.TestCase):
    """Tests for postal code sanitization and warehouse resolution."""

    def setUp(self):
        # Reset memory cache before each test
        mercadona_service._PC_CACHE.clear()
        mercadona_service._PC_CACHE["28016"] = {"postal_code": "28016", "warehouse": "mad3"}

    def test_guess_warehouse_known_prefixes(self):
        self.assertEqual(mercadona_service._guess_warehouse("28001"), "mad3")
        self.assertEqual(mercadona_service._guess_warehouse("46001"), "vlc1")
        self.assertEqual(mercadona_service._guess_warehouse("08001"), "bcn1")
        self.assertEqual(mercadona_service._guess_warehouse("03001"), "alc1")
        self.assertEqual(mercadona_service._guess_warehouse("41001"), "svq1")

    def test_guess_warehouse_unknown_prefix_fallback(self):
        # Default fallback is mad3
        self.assertEqual(mercadona_service._guess_warehouse("99999"), "mad3")
        self.assertEqual(mercadona_service._guess_warehouse("12345"), "mad3")
        self.assertEqual(mercadona_service._guess_warehouse("00000"), "mad3")

    @patch("urllib.request.urlopen")
    def test_resolve_postal_code_live_success(self, mock_urlopen):
        # Mock HTTP response with custom headers
        mock_resp = MagicMock()
        mock_resp.headers = {
            "x-customer-wh": "vlc1",
            "x-customer-pc": "46001",
        }
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        res = mercadona_service.resolve_postal_code("46001")
        self.assertEqual(res["postal_code"], "46001")
        self.assertEqual(res["warehouse"], "vlc1")
        self.assertEqual(res["source"], "live")
        # Verify cached
        self.assertIn("46001", mercadona_service._PC_CACHE)

    @patch("urllib.request.urlopen")
    def test_resolve_postal_code_network_failure_fallback(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.URLError("Network unreachable")

        res = mercadona_service.resolve_postal_code("08001")
        self.assertEqual(res["postal_code"], "08001")
        self.assertEqual(res["warehouse"], "bcn1")
        self.assertEqual(res["source"], "fallback")

    def test_resolve_postal_code_sanitization_alphanumeric_and_symbols(self):
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = Exception("offline")
            # "CP 28001 Madrid!" -> digits only = 28001
            res = mercadona_service.resolve_postal_code("CP 28001 Madrid!")
            self.assertEqual(res["postal_code"], "28001")
            self.assertEqual(res["warehouse"], "mad3")

    def test_resolve_postal_code_invalid_length_defaults_to_28016(self):
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = Exception("offline")
            # Length < 5 or empty
            res = mercadona_service.resolve_postal_code("123")
            self.assertEqual(res["postal_code"], "28016")

            res_none = mercadona_service.resolve_postal_code(None)
            self.assertEqual(res_none["postal_code"], "28016")

            res_letters = mercadona_service.resolve_postal_code("ABCDE")
            self.assertEqual(res_letters["postal_code"], "28016")


class TestSpanishTextNormalization(unittest.TestCase):
    """Tests for Spanish text diacritics, unicode, and dietary normalization."""

    def test_normalize_accents(self):
        self.assertEqual(normalize_spanish_text("plátano"), "platano")
        self.assertEqual(normalize_spanish_text("PLÁTANO DE CANARIAS"), "platano de canarias")
        self.assertEqual(normalize_spanish_text("limón"), "limon")
        self.assertEqual(normalize_spanish_text("jamón ibérico"), "jamon iberico")
        self.assertEqual(normalize_spanish_text("café solo"), "cafe solo")

    def test_normalize_special_characters_and_whitespace(self):
        self.assertEqual(normalize_spanish_text("   leche   desnatada  \n\t"), "leche desnatada")
        self.assertEqual(normalize_spanish_text("tomate (pack 3 uds)"), "tomate pack 3 uds")
        self.assertEqual(normalize_spanish_text("¡aceite de oliva 100%!"), "aceite de oliva 100")

    def test_normalize_empty_and_edge_cases(self):
        self.assertEqual(normalize_spanish_text(""), "")
        self.assertEqual(normalize_spanish_text("   "), "")
        self.assertEqual(normalize_spanish_text(None), "")


class TestProductSearchAndCatalogLookup(unittest.TestCase):
    """Tests for snapshot loading, product search, filtering, and dietary rules."""

    @classmethod
    def setUpClass(cls):
        cls.catalog = mercadona_service.load_snapshot_products()

    def test_load_snapshot_products_not_empty(self):
        self.assertGreater(len(self.catalog), 1000)
        sample = next(iter(self.catalog.values()))
        self.assertIn("id", sample)
        self.assertIn("name", sample)
        self.assertIn("unit_price", sample)

    def test_load_snapshot_caching(self):
        cat1 = mercadona_service.load_snapshot_products()
        cat2 = mercadona_service.load_snapshot_products()
        self.assertIs(cat1, cat2)

    def test_search_products_exact_and_fuzzy_match(self):
        results = search_products(self.catalog, query="leche entera")
        self.assertGreater(len(results), 0)
        self.assertTrue(all("leche" in r["name"].lower() for r in results))

    def test_search_products_accent_insensitivity(self):
        res_accent = search_products(self.catalog, query="plátano")
        res_no_accent = search_products(self.catalog, query="platano")
        self.assertGreater(len(res_accent), 0)
        self.assertEqual(len(res_accent), len(res_no_accent))

    def test_search_products_category_filter(self):
        results = search_products(self.catalog, query="huevo", category="Huevos, leche y mantequilla")
        self.assertGreater(len(results), 0)
        for r in results:
            self.assertTrue(any("leche" in c.lower() or "huevo" in c.lower() for c in r.get("categories", [])))

    def test_search_products_dietary_gluten_free(self):
        results = search_products(self.catalog, query="pasta", dietary="sin gluten")
        for r in results:
            allergens = r.get("allergens", "").lower()
            self.assertNotIn("gluten", allergens)

    def test_search_products_dietary_lactose_free(self):
        results = search_products(self.catalog, query="leche", dietary="sin lactosa")
        for r in results:
            allergens = r.get("allergens", "").lower()
            self.assertNotIn("lactosa", allergens)

    @patch("mercadona_service.fetch_live_product")
    @patch("mercadona_service.resolve_postal_code")
    def test_get_catalog_for_postal_code(self, mock_resolve, mock_fetch):
        mock_resolve.return_value = {"postal_code": "28001", "warehouse": "mad3"}
        mock_fetch.return_value = None  # Live fetch returns None, fallback to snapshot

        catalog, meta = mercadona_service.get_catalog_for_postal_code("28001", verify_live_ids=["10161"])
        self.assertIn("10161", catalog)
        self.assertEqual(meta["postal_code"], "28001")
        self.assertEqual(meta["warehouse"], "mad3")
        self.assertEqual(meta["catalog_source"], "snapshot")

    @patch("mercadona_service.fetch_live_product")
    @patch("mercadona_service.resolve_postal_code")
    def test_get_catalog_for_postal_code_with_live_update(self, mock_resolve, mock_fetch):
        mock_resolve.return_value = {"postal_code": "28001", "warehouse": "mad3"}
        mock_fetch.return_value = {
            "id": "10161",
            "name": "Nata ligera updated",
            "unit_price": 1.99,
            "available": True,
            "source": "live",
        }

        catalog, meta = mercadona_service.get_catalog_for_postal_code("28001", verify_live_ids=["10161"])
        self.assertEqual(catalog["10161"]["name"], "Nata ligera updated")
        self.assertEqual(catalog["10161"]["unit_price"], 1.99)
        self.assertEqual(meta["catalog_source"], "live")
        self.assertEqual(meta["live_verified_products"], 1)


class TestLiveMercadonaAPIMocks(unittest.TestCase):
    """Tests for live product fetching, HTTP error handling, and JSON parsing."""

    def setUp(self):
        mercadona_service._LIVE_PRODUCT_CACHE.clear()

    @patch("urllib.request.urlopen")
    def test_fetch_live_product_success(self, mock_urlopen):
        mock_data = {
            "id": 12345,
            "display_name": "Aceite de oliva virgen extra",
            "thumbnail": "https://example.com/thumb.jpg",
            "share_url": "https://tienda.mercadona.es/product/12345",
            "price_instructions": {
                "unit_price": "4.95",
                "unit_size": 1.0,
                "size_format": "l",
            },
            "nutrition_information": {
                "allergens": "<b>Sin alérgenos</b>",
            },
            "packaging": "Botella",
        }
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(mock_data).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        res = mercadona_service.fetch_live_product("12345", "mad3")
        self.assertIsNotNone(res)
        self.assertEqual(res["id"], "12345")
        self.assertEqual(res["unit_price"], 4.95)
        self.assertEqual(res["unit"], "1.0 l")
        self.assertEqual(res["allergens"], "Sin alérgenos")
        self.assertEqual(res["source"], "live")
        self.assertTrue(res["available"])

        # Cache check
        self.assertIn(("12345", "mad3"), mercadona_service._LIVE_PRODUCT_CACHE)

    @patch("urllib.request.urlopen")
    def test_fetch_live_product_cached(self, mock_urlopen):
        now = time.time()
        mercadona_service._LIVE_PRODUCT_CACHE[("999", "mad3")] = (
            now,
            {"id": "999", "name": "Cached Product", "unit_price": 2.5, "source": "live"},
        )
        res = mercadona_service.fetch_live_product("999", "mad3")
        self.assertEqual(res["name"], "Cached Product")
        mock_urlopen.assert_not_called()

    @patch("urllib.request.urlopen")
    def test_fetch_live_product_zero_or_negative_price(self, mock_urlopen):
        mock_data = {
            "id": 555,
            "display_name": "Zero price item",
            "price_instructions": {"unit_price": "0.00"},
        }
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(mock_data).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        res = mercadona_service.fetch_live_product("555", "mad3")
        self.assertIsNone(res)

    @patch("urllib.request.urlopen")
    def test_fetch_live_product_404_not_found(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="http://tienda.mercadona.es", code=404, msg="Not Found", hdrs={}, fp=io.BytesIO(b"")
        )
        res = mercadona_service.fetch_live_product("nonexistent", "mad3")
        self.assertIsNone(res)

    @patch("urllib.request.urlopen")
    def test_fetch_live_product_500_server_error(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="http://tienda.mercadona.es", code=500, msg="Server Error", hdrs={}, fp=io.BytesIO(b"Server crash")
        )
        res = mercadona_service.fetch_live_product("err_item", "mad3")
        self.assertIsNone(res)

    @patch("urllib.request.urlopen")
    def test_fetch_live_product_timeout(self, mock_urlopen):
        mock_urlopen.side_effect = TimeoutError("Connection timed out")
        res = mercadona_service.fetch_live_product("timeout_item", "mad3")
        self.assertIsNone(res)

    @patch("urllib.request.urlopen")
    def test_fetch_live_product_invalid_json(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"<html>Bad Gateway</html>"
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        res = mercadona_service.fetch_live_product("invalid_json", "mad3")
        self.assertIsNone(res)


class TestJWTHelpersAndAuthParsing(unittest.TestCase):
    """Tests for SimpleJWT decoding, customer ID extraction, and auth parser."""

    def _create_mock_jwt(self, payload: dict) -> str:
        header = base64.urlsafe_b64encode(b'{"alg":"HS256","typ":"JWT"}').decode("utf-8").rstrip("=")
        body = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8").rstrip("=")
        sig = "mock_signature_12345"
        return f"{header}.{body}.{sig}"

    def test_decode_jwt_claims_valid(self):
        token = self._create_mock_jwt({"customer_uuid": "cust-abc-123", "token_type": "access"})
        claims = mercadona_service._decode_jwt_claims(token)
        self.assertEqual(claims["customer_uuid"], "cust-abc-123")
        self.assertEqual(claims["token_type"], "access")

    def test_decode_jwt_claims_with_bearer_prefix(self):
        token = "Bearer " + self._create_mock_jwt({"sub": "user-456"})
        claims = mercadona_service._decode_jwt_claims(token)
        self.assertEqual(claims["sub"], "user-456")

    def test_decode_jwt_claims_malformed(self):
        self.assertEqual(mercadona_service._decode_jwt_claims(""), {})
        self.assertEqual(mercadona_service._decode_jwt_claims("not.a.token.with.valid.json"), {})
        self.assertEqual(mercadona_service._decode_jwt_claims("invalid_string"), {})

    def test_customer_from_jwt(self):
        tok_uuid = self._create_mock_jwt({"customer_uuid": "uuid-999"})
        self.assertEqual(mercadona_service.customer_from_jwt(tok_uuid), "uuid-999")

        tok_id = self._create_mock_jwt({"customer_id": "id-888"})
        self.assertEqual(mercadona_service.customer_from_jwt(tok_id), "id-888")

        tok_me = self._create_mock_jwt({"customer_id": "me", "sub": "real-user-111"})
        self.assertEqual(mercadona_service.customer_from_jwt(tok_me), "real-user-111")

    def test_parse_mercadona_auth_input_curl_command(self):
        token = self._create_mock_jwt({"customer_uuid": "curl-cust-1"})
        curl_cmd = (
            f"curl 'https://tienda.mercadona.es/api/customers/curl-cust-1/cart/?wh=vlc1' "
            f"-H 'Authorization: Bearer {token}' "
            f"-H 'cookie: sessionid=xyz123; user=test' "
        )
        res = mercadona_service.parse_mercadona_auth_input(curl_cmd)
        self.assertEqual(res["access_token"], token)
        self.assertEqual(res["customer_id"], "curl-cust-1")
        self.assertEqual(res["warehouse"], "vlc1")
        self.assertIn("sessionid=xyz123", res["cookie"])

    def test_parse_mercadona_auth_input_json_object(self):
        tok = self._create_mock_jwt({"customer_uuid": "json-cust-2"})
        payload = json.dumps({
            "access_token": tok,
            "refresh_token": "refresh-token-xyz",
            "customer_id": "json-cust-2",
            "warehouse": "mad3",
        })
        res = mercadona_service.parse_mercadona_auth_input(payload)
        self.assertEqual(res["access_token"], tok)
        self.assertEqual(res["refresh_token"], "refresh-token-xyz")
        self.assertEqual(res["customer_id"], "json-cust-2")
        self.assertEqual(res["warehouse"], "mad3")

    def test_parse_mercadona_auth_input_har_file(self):
        tok = self._create_mock_jwt({"customer_id": "har-cust"})
        har = {
            "log": {
                "entries": [
                    {
                        "request": {
                            "url": "https://tienda.mercadona.es/api/auth/",
                            "headers": [{"name": "Authorization", "value": f"Bearer {tok}"}],
                        },
                        "response": {
                            "status": 200,
                            "content": {
                                "text": json.dumps({"access_token": tok, "customer_id": "har-cust"})
                            },
                        },
                    }
                ]
            }
        }
        res = mercadona_service.parse_mercadona_auth_input(json.dumps(har))
        self.assertEqual(res["access_token"], tok)
        self.assertEqual(res["customer_id"], "har-cust")

    def test_parse_mercadona_auth_input_refresh_token_detection(self):
        ref_jwt = self._create_mock_jwt({"customer_uuid": "ref-cust", "token_type": "refresh"})
        res = mercadona_service.parse_mercadona_auth_input(ref_jwt)
        self.assertEqual(res["refresh_token"], ref_jwt)
        self.assertEqual(res["access_token"], "")
        self.assertEqual(res["customer_id"], "ref-cust")

    def test_parse_mercadona_auth_input_mo_user_localstorage_json(self):
        tok = self._create_mock_jwt({"sub": "mo-cust-777"})
        mo_user = json.dumps({
            "uuid": "mo-cust-777",
            "token": tok,
            "refreshToken": "camel-refresh-token-999",
            "userUuid": "mo-cust-777",
        })
        res = mercadona_service.parse_mercadona_auth_input(mo_user)
        self.assertEqual(res["access_token"], tok)
        self.assertEqual(res["refresh_token"], "camel-refresh-token-999")
        self.assertEqual(res["customer_id"], "mo-cust-777")

    def test_parse_mercadona_auth_input_bookmarklet_connect_hash(self):
        tok = self._create_mock_jwt({"customer_uuid": "bmk-cust-123"})
        raw_payload = json.dumps({
            "mo_user": {
                "uuid": "bmk-cust-123",
                "token": tok,
                "refreshToken": "bmk-refresh-456",
                "userUuid": "bmk-cust-123",
            },
            "cookie": '__mo_da={"warehouse":"bcn1","postalCode":"08006"}; other=1',
            "ts": 1700000000000,
        })
        b64 = base64.urlsafe_b64encode(raw_payload.encode("utf-8")).decode("utf-8").rstrip("=")
        connect_input = f"https://mercadona-ai-companion.run.app/#mercadona_connect={b64}"
        res = mercadona_service.parse_mercadona_auth_input(connect_input)
        self.assertEqual(res["access_token"], tok)
        self.assertEqual(res["refresh_token"], "bmk-refresh-456")
        self.assertEqual(res["customer_id"], "bmk-cust-123")
        self.assertEqual(res["warehouse"], "bcn1")
        wh, pc = mercadona_service._extract_mo_da_from_cookie(res["cookie"])
        self.assertEqual((wh, pc), ("bcn1", "08006"))



class TestSessionManagementAndPersistence(unittest.TestCase):
    """Tests for session loading, saving, status querying, and clearing."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.orig_data_dir = mercadona_service.DATA_DIR
        self.orig_sessions_file = mercadona_service.SESSIONS_FILE
        self.orig_sessions_cache = dict(mercadona_service._MERCADONA_SESSIONS)

        # Point DATA_DIR and SESSIONS_FILE to temp directory
        mercadona_service.DATA_DIR = Path(self.temp_dir.name)
        mercadona_service.SESSIONS_FILE = mercadona_service.DATA_DIR / "mercadona_sessions.json"
        mercadona_service._MERCADONA_SESSIONS.clear()

    def tearDown(self):
        mercadona_service.DATA_DIR = self.orig_data_dir
        mercadona_service.SESSIONS_FILE = self.orig_sessions_file
        mercadona_service._MERCADONA_SESSIONS = self.orig_sessions_cache
        self.temp_dir.cleanup()

    def test_session_lifecycle(self):
        # 1. Initially empty
        status_init = mercadona_service.get_mercadona_session_status("test@example.com")
        self.assertFalse(status_init["connected"])
        self.assertIsNone(status_init["customer_id"])

        # 2. Add session to cache and save to disk
        test_session = {
            "access_token": "eyJhbGciOiJIUzI1NiJ9.eyJjdXN0b21lcl91dWlkIjoidGVzdC0xMjMifQ.mock_sig",
            "refresh_token": "refresh-12345",
            "cookie": "test-cookie",
            "customer_id": "test-123",
            "warehouse": "mad3",
            "updated_at": 1700000000,
        }
        mercadona_service._MERCADONA_SESSIONS["test@example.com"] = test_session
        mercadona_service._MERCADONA_SESSIONS["default"] = test_session
        mercadona_service._save_sessions_to_disk()

        # Check file was created
        self.assertTrue(mercadona_service.SESSIONS_FILE.exists())

        # 3. Read back session status
        status = mercadona_service.get_mercadona_session_status("test@example.com")
        self.assertTrue(status["connected"])
        self.assertEqual(status["customer_id"], "test-123")
        self.assertTrue(status["has_refresh_token"])
        self.assertIn("…", status["masked_token"])

        # 4. Clear session
        res_clear = mercadona_service.clear_mercadona_session("test@example.com")
        self.assertFalse(res_clear["connected"])
        status_cleared = mercadona_service.get_mercadona_session_status("test@example.com")
        self.assertFalse(status_cleared["connected"])


class TestCartPreparationAndSynchronization(unittest.TestCase):
    """Tests for cart preparation, quantity bundling, live sync, and error fallbacks."""

    def setUp(self):
        mercadona_service._PC_CACHE.clear()
        mercadona_service._PC_CACHE["28016"] = {"postal_code": "28016", "warehouse": "mad3"}
        self.sample_basket = [
            {
                "id": "10161",
                "name": "Nata ligera Hacendado",
                "quantity": 2,
                "unit": "0.5 l",
                "unit_price": 1.55,
                "line_total": 3.10,
                "share_url": "https://tienda.mercadona.es/product/10161",
            },
            {
                "id": "4740",
                "name": "Aceite de oliva virgen extra",
                "quantity": 1,
                "unit": "1 l",
                "unit_price": 5.95,
                "line_total": 5.95,
                "share_url": "https://tienda.mercadona.es/product/4740",
            },
        ]

    @patch("mercadona_service.get_active_mercadona_session", return_value=None)
    @patch("urllib.request.urlopen")
    def test_prepare_cart_not_connected(self, mock_urlopen, mock_session):
        # When not connected, returns cart_ready payload with lines and totals
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        res = mercadona_service.prepare_mercadona_oneclick_cart(
            basket=self.sample_basket,
            postal_code="28016",
            user_email="unconnected@example.com",
        )
        self.assertEqual(res["status"], "cart_ready")
        self.assertFalse(res["live_synced"])
        self.assertTrue(res["auth_required"])
        self.assertEqual(res["items_count"], 3)  # 2 + 1
        self.assertEqual(res["unique_products"], 2)
        self.assertAlmostEqual(res["total"], 9.05, places=2)
        self.assertEqual(len(res["lines"]), 2)

    @patch("mercadona_service.get_active_mercadona_session")
    @patch("mercadona_service._mercadona_authed_request")
    def test_prepare_cart_synced_live_add_mode(self, mock_auth_req, mock_session):
        mock_session.return_value = {
            "access_token": "token123",
            "refresh_token": "ref123",
            "customer_id": "cust-abc",
            "warehouse": "mad3",
        }
        # Step 1: GET existing cart
        mock_auth_req.side_effect = [
            {
                "id": "cart-remote-1",
                "lines": [
                    {"product_id": "10161", "quantity": 1, "sources": []},  # Nata already has 1 ud
                    {"product_id": "99999", "quantity": 3, "sources": []},  # Another product
                ],
            },
            # Step 2: PUT updated cart response
            {
                "id": "cart-remote-1",
                "products_count": 3,
                "summary": {"total": "15.00"},
                "version": 2,
            },
        ]

        res = mercadona_service.prepare_mercadona_oneclick_cart(
            basket=self.sample_basket,
            postal_code="28016",
            user_email="connected@example.com",
            mode="add",
        )
        self.assertEqual(res["status"], "synced_live")
        self.assertTrue(res["live_synced"])
        self.assertEqual(res["cart_id"], "cart-remote-1")

        # Verify PUT body passed to _mercadona_authed_request
        put_call = mock_auth_req.call_args_list[1]
        put_body = put_call.kwargs.get("body") or put_call[1].get("body")
        lines_put = {l["product_id"]: l["quantity"] for l in put_body["lines"]}
        # In 'add' mode: product 10161 had 1, added 2 -> 3
        self.assertEqual(lines_put["10161"], 3.0)
        # Existing item 99999 preserved with 3
        self.assertEqual(lines_put["99999"], 3.0)
        # New item 4740 added with 1
        self.assertEqual(lines_put["4740"], 1.0)

    @patch("mercadona_service.get_active_mercadona_session")
    @patch("mercadona_service._mercadona_authed_request")
    def test_prepare_cart_synced_live_replace_mode(self, mock_auth_req, mock_session):
        mock_session.return_value = {
            "access_token": "token123",
            "refresh_token": "ref123",
            "customer_id": "cust-abc",
            "warehouse": "mad3",
        }
        mock_auth_req.side_effect = [
            {
                "id": "cart-remote-1",
                "lines": [
                    {"product_id": "10161", "quantity": 1, "sources": []},
                    {"product_id": "99999", "quantity": 3, "sources": []},
                ],
            },
            {
                "id": "cart-remote-1",
                "products_count": 2,
                "summary": {"total": "9.05"},
                "version": 3,
            },
        ]

        res = mercadona_service.prepare_mercadona_oneclick_cart(
            basket=self.sample_basket,
            postal_code="28016",
            user_email="connected@example.com",
            mode="replace",
        )
        self.assertEqual(res["status"], "synced_live")
        put_call = mock_auth_req.call_args_list[1]
        put_body = put_call.kwargs.get("body") or put_call[1].get("body")
        lines_put = {l["product_id"]: l["quantity"] for l in put_body["lines"]}
        # In 'replace' mode: 99999 dropped, 10161 is strictly 2.0 (from basket)
        self.assertNotIn("99999", lines_put)
        self.assertEqual(lines_put["10161"], 2.0)
        self.assertEqual(lines_put["4740"], 1.0)


class TestTokenRefreshAndRetryLogic(unittest.TestCase):
    """Tests for refreshing Mercadona tokens and 401 transparent retry logic."""

    @patch("urllib.request.urlopen")
    def test_refresh_mercadona_token_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "access_token": "new-access-token",
            "refresh_token": "new-refresh-token",
            "customer_id": "refreshed-cust-id",
        }).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        res = mercadona_service.refresh_mercadona_token("old-refresh-token")
        self.assertEqual(res["access_token"], "new-access-token")
        self.assertEqual(res["refresh_token"], "new-refresh-token")
        self.assertEqual(res["customer_id"], "refreshed-cust-id")

    def test_refresh_mercadona_token_empty_raises_value_error(self):
        with self.assertRaises(ValueError):
            mercadona_service.refresh_mercadona_token("")

    @patch("mercadona_service.refresh_mercadona_token")
    @patch("urllib.request.urlopen")
    def test_mercadona_authed_request_retry_on_401(self, mock_urlopen, mock_refresh):
        mock_refresh.return_value = {
            "access_token": "token-attempt-2",
            "refresh_token": "ref-attempt-2",
            "customer_id": "cust-retry",
        }

        # 1st call fails with 401 Unauthorized
        err401 = urllib.error.HTTPError(
            url="http://test", code=401, msg="Unauthorized", hdrs={}, fp=io.BytesIO(b'{"detail":"token expired"}')
        )
        # 2nd call succeeds
        success_resp = MagicMock()
        success_resp.read.return_value = b'{"status": "ok"}'
        success_resp.__enter__.return_value = success_resp

        mock_urlopen.side_effect = [err401, success_resp]

        session = {
            "access_token": "token-attempt-1",
            "refresh_token": "ref-attempt-1",
            "customer_id": "cust-retry",
        }

        res = mercadona_service._mercadona_authed_request(
            method="GET",
            path_and_query="/api/test/",
            session=session,
            user_email="retry_user@example.com",
        )
        self.assertEqual(res, {"status": "ok"})
        self.assertEqual(session["access_token"], "token-attempt-2")
        mock_refresh.assert_called_once()


if __name__ == "__main__":
    unittest.main()

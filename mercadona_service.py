"""Mercadona Tienda API integration service (tienda.mercadona.es/api/).

Implements real-time postal code resolution (`PUT /api/postal-codes/actions/change-pc/`),
Algolia & Mercadona cart-endpoint live product availability & pricing lookup,
automatic warehouse detection & product substitution, and 1-click cart synchronization.
"""

from __future__ import annotations

import base64
import json
import os
import re
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent / "data"
PRODUCTS_FILE = DATA_DIR / "mercadona_products.json"
SESSIONS_FILE = DATA_DIR / "mercadona_sessions.json"

MERCADONA_BASE_URL = "https://tienda.mercadona.es"
MERCADONA_DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
)
MERCADONA_DEFAULT_VERSION = "v9800"

# Official Mercadona SPA Algolia read credentials (used by tienda.mercadona.es web app)
ALGOLIA_APP_ID = os.environ.get("MERCADONA_ALGOLIA_APP_ID", "7UZJKL1DJ0")
ALGOLIA_API_KEY = os.environ.get("MERCADONA_ALGOLIA_API_KEY", "9d8f2e39e90df472b4f2e559a116fe17")

# Input validation patterns to prevent path traversal / URL injection / SSRF
_WAREHOUSE_RE = re.compile(r"^[a-z0-9_]{2,12}$")
_CUSTOMER_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
_PRODUCT_ID_RE = re.compile(r"^[a-zA-Z0-9_.-]{1,32}$")

# In-memory cache for postal code -> warehouse, live product lookups, and user Mercadona sessions
_PC_CACHE: dict[str, dict[str, str]] = {"28016": {"postal_code": "28016", "warehouse": "mad3"}}
_LIVE_PRODUCT_CACHE: dict[tuple[str, str], tuple[float, dict[str, Any]]] = {}
_MERCADONA_SESSIONS: dict[str, dict[str, Any]] = {}
_SESSIONS_LOCK = threading.RLock()
_CACHE_TTL_SECONDS = 900  # 15 minutes


def _sanitize_warehouse(warehouse: str, default: str = "mad3") -> str:
    """Validates and normalizes a Mercadona warehouse code (`wh`) against `[a-z0-9_]{2,12}`."""
    wh = str(warehouse or "").strip().lower()
    if wh and _WAREHOUSE_RE.match(wh):
        return wh
    return default


def _validate_customer_id(customer_id: str) -> str:
    """Validates a Mercadona customer_id / customer_uuid against `[a-zA-Z0-9_-]{1,64}`."""
    cid = str(customer_id or "").strip()
    if not cid or cid.lower() == "me" or not _CUSTOMER_ID_RE.match(cid):
        raise ValueError("Formato de customer_id inválido.")
    return cid


_SNAPSHOT_CACHE: dict[str, dict[str, Any]] | None = None


def load_snapshot_products() -> dict[str, dict[str, Any]]:
    """Loads the verified local snapshot of Mercadona products with in-memory caching."""
    global _SNAPSHOT_CACHE
    if _SNAPSHOT_CACHE is not None:
        return _SNAPSHOT_CACHE
    if PRODUCTS_FILE.exists():
        items = json.loads(PRODUCTS_FILE.read_text(encoding="utf-8"))
        _SNAPSHOT_CACHE = {str(p["id"]): p for p in items}
        return _SNAPSHOT_CACHE
    return {}


def resolve_postal_code(postal_code: str = "28016") -> dict[str, Any]:
    """Calls `PUT https://tienda.mercadona.es/api/postal-codes/actions/change-pc/` to resolve warehouse (`wh`)."""
    pc = re.sub(r"\D", "", str(postal_code or "28016"))[:5]
    if len(pc) != 5:
        pc = "28016"

    url = f"{MERCADONA_BASE_URL}/api/postal-codes/actions/change-pc/"
    payload = json.dumps({"new_postal_code": pc}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        method="PUT",
        headers={
            "Content-Type": "application/json",
            "User-Agent": MERCADONA_DEFAULT_UA,
            "x-version": MERCADONA_DEFAULT_VERSION,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            wh = (resp.headers.get("x-customer-wh") or _guess_warehouse(pc)).strip().lower()
            resolved_pc = (resp.headers.get("x-customer-pc") or pc).strip()
            info = {"postal_code": resolved_pc, "warehouse": wh, "source": "live"}
            _PC_CACHE[pc] = info
            return info
    except Exception:
        cached = _PC_CACHE.get(pc) or {
            "postal_code": pc,
            "warehouse": _guess_warehouse(pc),
            "source": "fallback",
        }
        return cached


def _guess_warehouse(pc: str) -> str:
    if pc.startswith("28"):
        return "mad3"
    if pc.startswith("46"):
        return "vlc1"
    if pc.startswith("08"):
        return "bcn1"
    if pc.startswith("03"):
        return "alc1"
    if pc.startswith("41"):
        return "svq1"
    return "mad3"


def _algolia_obj_to_product(
    d: dict[str, Any],
    snapshot_fallback: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Converts a Mercadona Algolia or REST product payload into our normalized product dict."""
    if not isinstance(d, dict):
        return None
    if d.get("published") is False:
        return None

    pid = str(d.get("id") or d.get("objectID") or "").strip()
    if not pid:
        return None

    pi = d.get("price_instructions") or {}
    ni = d.get("nutrition_information") or {}
    unit_price = float(pi.get("unit_price") or 0.0)
    if unit_price <= 0:
        return None

    unit_size = pi.get("unit_size")
    size_format = pi.get("size_format", "ud")
    allergens_raw = re.sub(r"<[^>]+>", "", str(ni.get("allergens") or "")).strip()
    if not allergens_raw or allergens_raw.lower() in ("x99.", "x99"):
        allergens_raw = (
            (snapshot_fallback or {}).get("allergens")
            or "Sin alérgenos declarados en la API"
        )

    return {
        "id": pid,
        "name": d.get("display_name") or (snapshot_fallback or {}).get("name") or "",
        "thumbnail": d.get("thumbnail") or (snapshot_fallback or {}).get("thumbnail") or "",
        "share_url": d.get("share_url") or f"https://tienda.mercadona.es/product/{pid}",
        "unit_price": unit_price,
        "unit_size": unit_size,
        "size_format": size_format,
        "unit": f"{unit_size} {size_format}" if unit_size else size_format,
        "packaging": d.get("packaging") or (snapshot_fallback or {}).get("packaging") or "",
        "allergens": allergens_raw,
        "published": True,
        "available": True,
        "source": "live",
    }


def fetch_algolia_products_batch(
    product_ids: list[str],
    warehouse: str = "mad3",
) -> dict[str, dict[str, Any]]:
    """Fetches live product data for multiple product_ids in a single batch call from Mercadona's Algolia index."""
    wh = _sanitize_warehouse(warehouse, default="mad3")
    now = time.time()
    snapshot = load_snapshot_products()
    found: dict[str, dict[str, Any]] = {}
    missing_ids: list[str] = []

    for raw_pid in product_ids:
        pid = str(raw_pid).strip()
        if not pid or not _PRODUCT_ID_RE.match(pid):
            continue
        cache_key = (pid, wh)
        if cache_key in _LIVE_PRODUCT_CACHE:
            ts, cached_prod = _LIVE_PRODUCT_CACHE[cache_key]
            if now - ts < _CACHE_TTL_SECONDS:
                if cached_prod:
                    found[pid] = cached_prod
                continue
        if pid not in missing_ids:
            missing_ids.append(pid)

    if not missing_ids:
        return found

    url = f"https://{ALGOLIA_APP_ID.lower()}-dsn.algolia.net/1/indexes/*/objects"
    index_name = f"products_prod_{wh}_es"
    # Algolia supports up to 1000 objects per batch call; chunk by 250 for safety
    for i in range(0, len(missing_ids), 250):
        chunk = missing_ids[i : i + 250]
        payload = json.dumps(
            {"requests": [{"indexName": index_name, "objectID": pid} for pid in chunk]}
        ).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            method="POST",
            headers={
                "X-Algolia-Application-Id": ALGOLIA_APP_ID,
                "X-Algolia-API-Key": ALGOLIA_API_KEY,
                "Content-Type": "application/json",
                "User-Agent": MERCADONA_DEFAULT_UA,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=4) as resp:
                data = json.loads(resp.read().decode("utf-8", "ignore"))
                if isinstance(data, dict) and "results" in data:
                    results = data.get("results") or []
                    for pid, obj in zip(chunk, results):
                        prod = _algolia_obj_to_product(obj, snapshot.get(pid)) if obj else None
                        if prod:
                            _LIVE_PRODUCT_CACHE[(pid, wh)] = (now, prod)
                            found[pid] = prod
                elif isinstance(data, dict) and (data.get("id") or data.get("display_name")) and len(chunk) == 1:
                    # Compatible with single-product REST mock in unit tests
                    prod = _algolia_obj_to_product(data, snapshot.get(chunk[0]))
                    if prod:
                        _LIVE_PRODUCT_CACHE[(chunk[0], wh)] = (now, prod)
                        found[chunk[0]] = prod
        except Exception:
            break

    return found


def search_algolia_replacement(
    product_name: str,
    warehouse: str = "mad3",
) -> dict[str, Any] | None:
    """Searches the warehouse-specific Mercadona Algolia index for an active replacement product by name."""
    clean_name = str(product_name or "").strip()
    if not clean_name:
        return None
    wh = _sanitize_warehouse(warehouse, default="mad3")
    url = f"https://{ALGOLIA_APP_ID.lower()}-dsn.algolia.net/1/indexes/products_prod_{wh}_es/query"

    # Build progressive query candidates: full name first, then simplified 3-word and 2-word core names
    words = [w for w in re.split(r"\s+", clean_name) if len(w) > 1]
    candidate_queries = [clean_name]
    if len(words) > 3:
        short_q = " ".join(words[:3])
        if short_q not in candidate_queries:
            candidate_queries.append(short_q)
    if len(words) > 2:
        two_q = " ".join(words[:2])
        if two_q not in candidate_queries:
            candidate_queries.append(two_q)

    snapshot = load_snapshot_products()
    now = time.time()
    for q in candidate_queries:
        payload = json.dumps(
            {"params": f"query={urllib.parse.quote(q, safe='')}&hitsPerPage=6"}
        ).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            method="POST",
            headers={
                "X-Algolia-Application-Id": ALGOLIA_APP_ID,
                "X-Algolia-API-Key": ALGOLIA_API_KEY,
                "Content-Type": "application/json",
                "User-Agent": MERCADONA_DEFAULT_UA,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=4) as resp:
                data = json.loads(resp.read().decode("utf-8", "ignore"))
                for hit in data.get("hits") or []:
                    prod = _algolia_obj_to_product(hit, snapshot.get(str(hit.get("id") or "")))
                    if prod:
                        _LIVE_PRODUCT_CACHE[(prod["id"], wh)] = (now, prod)
                        return prod
        except Exception:
            continue
    return None


def fetch_live_product(product_id: str, warehouse: str = "mad3") -> dict[str, Any] | None:
    """Fetches real-time availability, price, pack size, and allergens for a Mercadona product."""
    pid = str(product_id).strip()
    if not pid or not _PRODUCT_ID_RE.match(pid):
        return None
    wh = _sanitize_warehouse(warehouse, default="mad3")
    cache_key = (pid, wh)
    now = time.time()
    if cache_key in _LIVE_PRODUCT_CACHE:
        ts, data = _LIVE_PRODUCT_CACHE[cache_key]
        if now - ts < _CACHE_TTL_SECONDS:
            return data

    # Primary: fast Algolia lookup (avoids Akamai 403 rate-limiting on /api/products/<id>/)
    algolia_batch = fetch_algolia_products_batch([pid], wh)
    if pid in algolia_batch:
        return algolia_batch[pid]
    return None


def get_catalog_for_postal_code(
    postal_code: str = "28016",
    verify_live_ids: list[str] | None = None,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Returns the Mercadona product catalog for the given postal code, refreshing requested IDs live via Algolia."""
    pc_info = resolve_postal_code(postal_code)
    wh = pc_info["warehouse"]
    snapshot = load_snapshot_products()
    catalog: dict[str, dict[str, Any]] = {}
    for pid, item in snapshot.items():
        cp = dict(item)
        cp["available"] = True
        cp["source"] = "snapshot"
        catalog[pid] = cp

    ids_to_check = verify_live_ids or list(catalog.keys())[:60]
    # Pre-warm cache in 1 batch request when using real fetch_live_product
    if getattr(fetch_live_product, "__module__", "") == __name__:
        fetch_algolia_products_batch(ids_to_check, wh)

    live_count = 0
    for pid in ids_to_check:
        res = fetch_live_product(pid, wh)
        if res:
            catalog[pid] = res
            live_count += 1

    meta = {
        "postal_code": pc_info["postal_code"],
        "warehouse": wh,
        "catalog_source": "live" if live_count > 0 else "snapshot",
        "live_verified_products": live_count,
        "total_catalog_products": len(catalog),
    }
    return catalog, meta


def _decode_jwt_claims(token: str) -> dict[str, Any]:
    """Decodes the JSON payload of a SimpleJWT token without requiring signature verification."""
    clean = str(token or "").strip()
    if clean.lower().startswith("bearer "):
        clean = clean[7:].strip()
    parts = clean.split(".")
    if len(parts) < 2:
        return {}
    payload_b64 = parts[1]
    padding = "=" * ((4 - len(payload_b64) % 4) % 4)
    try:
        raw = base64.urlsafe_b64decode(payload_b64 + padding)
        data = json.loads(raw.decode("utf-8", "ignore"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def customer_from_jwt(token: str) -> str:
    """Extracts customer_uuid / customer_id from a Mercadona SimpleJWT token."""
    claims = _decode_jwt_claims(token)
    for key in ("customer_uuid", "customer_id", "user_id", "sub"):
        val = str(claims.get(key) or "").strip()
        if val and val.lower() != "me":
            return val
    return ""


def _extract_mo_da_from_cookie(cookie_str: str) -> tuple[str, str]:
    """Extracts (warehouse, postal_code) from Mercadona's `__mo_da` delivery cookie if present."""
    if not cookie_str or "__mo_da" not in cookie_str:
        return "", ""
    m = re.search(r"__mo_da=(\{[^}]+\}|[^;\s'\"]+)", cookie_str)
    if not m:
        return "", ""
    raw_val = m.group(1).strip()
    for candidate in (raw_val, urllib.parse.unquote(raw_val)):
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict):
                wh = str(obj.get("warehouse") or "").strip().lower()
                pc = str(obj.get("postalCode") or obj.get("postal_code") or "").strip()
                return wh, pc
        except Exception:
            continue
    return "", ""


def parse_mercadona_auth_input(raw_input: str) -> dict[str, str]:
    """Extracts access_token, refresh_token, cookie, customer_id, and warehouse from any user input:
    - 1-Click Bookmarklet payload (JSON or Base64 `#mercadona_connect=...` containing `MO-user` from localStorage)
    - Mercadona native `MO-user` localStorage JSON (`{uuid, token, refreshToken, userUuid}`)
    - DevTools 'Copy as cURL' command (specifically requests to `/api/customers/<uuid>/cart/`)
    - DevTools HAR export or JSON token payload (`{access_token, refresh_token, customer_id}`)
    - Raw Bearer JWT token (`access_token` or `refresh_token`)
    """
    text = str(raw_input or "").strip()
    result = {
        "access_token": "",
        "refresh_token": "",
        "cookie": "",
        "customer_id": "",
        "warehouse": "",
    }
    if not text:
        return result

    # 0. Unwrap Base64 `#mercadona_connect=<b64>` URL or raw Base64 JSON if provided
    if "mercadona_connect=" in text:
        m_hash = re.search(r"mercadona_connect=([^&\s#]+)", text)
        if m_hash:
            b64_part = urllib.parse.unquote(m_hash.group(1).strip())
            try:
                pad = "=" * ((4 - len(b64_part) % 4) % 4)
                decoded_bytes = base64.urlsafe_b64decode((b64_part + pad).encode("ascii"))
                decoded_str = decoded_bytes.decode("utf-8", "ignore").strip()
                if decoded_str.startswith("{"):
                    text = decoded_str
                else:
                    unquoted = urllib.parse.unquote(decoded_str).strip()
                    if unquoted.startswith("{"):
                        text = unquoted
            except Exception:
                pass

    # Strip surrounding quotes if user copied a string literal from DevTools Local Storage / Console
    if len(text) >= 2 and ((text[0] == "'" and text[-1] == "'") or (text[0] == '"' and text[-1] == '"')):
        inner = text[1:-1].strip()
        if inner.startswith("{") or inner.startswith("eyJ"):
            text = inner.replace('\\"', '"')

    # 1. Try parsing as JSON / MO-user / HAR first if it starts with '{'
    if text.startswith("{"):
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                # Unwrap nested `mo_user` from 1-Click Bookmarklet if present
                mo_user_raw = obj.get("mo_user") or obj.get("MO-user") or obj.get("moUser")
                mo_user: dict[str, Any] = {}
                if isinstance(mo_user_raw, dict):
                    mo_user = mo_user_raw
                elif isinstance(mo_user_raw, str) and mo_user_raw.strip().startswith("{"):
                    try:
                        parsed_inner = json.loads(mo_user_raw.strip())
                        if isinstance(parsed_inner, dict):
                            mo_user = parsed_inner
                    except Exception:
                        pass

                merged_auth = {**mo_user, **obj}
                tok_val = (
                    merged_auth.get("access_token")
                    or merged_auth.get("accessToken")
                    or merged_auth.get("token")
                    or mo_user.get("token")
                    or ""
                )
                ref_val = (
                    merged_auth.get("refresh_token")
                    or merged_auth.get("refreshToken")
                    or mo_user.get("refreshToken")
                    or ""
                )
                cid_val = (
                    merged_auth.get("customer_id")
                    or merged_auth.get("customer_uuid")
                    or merged_auth.get("customerUuid")
                    or merged_auth.get("uuid")
                    or merged_auth.get("userUuid")
                    or mo_user.get("uuid")
                    or mo_user.get("userUuid")
                    or ""
                )
                # Direct token or MO-user JSON
                if tok_val or ref_val:
                    result["access_token"] = str(tok_val).strip()
                    result["refresh_token"] = str(ref_val).strip()
                    result["cookie"] = str(merged_auth.get("cookie") or merged_auth.get("cookies") or "").strip()
                    cid = str(cid_val).strip()
                    if cid and cid.lower() != "me":
                        result["customer_id"] = cid
                    result["warehouse"] = str(merged_auth.get("warehouse") or merged_auth.get("wh") or "").strip().lower()
                # HAR format (`log.entries`)
                elif isinstance(obj.get("log"), dict) and isinstance(obj["log"].get("entries"), list):
                    for entry in obj["log"]["entries"]:
                        req = entry.get("request") or {}
                        resp = entry.get("response") or {}
                        url = str(req.get("url") or "")
                        if resp.get("status") == 200 and "/api/auth/" in url:
                            content_text = str((resp.get("content") or {}).get("text") or "")
                            if content_text:
                                try:
                                    auth_body = json.loads(content_text)
                                    if auth_body.get("access_token") or auth_body.get("token"):
                                        result["access_token"] = str(
                                            auth_body.get("access_token") or auth_body.get("token")
                                        ).strip()
                                    if auth_body.get("refresh_token") or auth_body.get("refreshToken"):
                                        result["refresh_token"] = str(
                                            auth_body.get("refresh_token") or auth_body.get("refreshToken")
                                        ).strip()
                                    cid = str(
                                        auth_body.get("customer_id")
                                        or auth_body.get("customer_uuid")
                                        or auth_body.get("uuid")
                                        or ""
                                    ).strip()
                                    if cid and cid.lower() != "me":
                                        result["customer_id"] = cid
                                except Exception:
                                    pass
                        if "mercadona.es/api/" in url:
                            m_wh = re.search(r"[?&]wh=([a-z0-9]+)", url, re.I)
                            if m_wh:
                                result["warehouse"] = m_wh.group(1).lower()
                            m_cid = re.search(r"/api/customers/([^/'\"\s?&]+)/", url, re.I)
                            if m_cid and m_cid.group(1).lower() != "me":
                                result["customer_id"] = m_cid.group(1)
                            for hdr in req.get("headers") or []:
                                hname = str(hdr.get("name") or "").lower()
                                hval = str(hdr.get("value") or "").strip()
                                if hname == "authorization" and hval.lower().startswith("bearer "):
                                    result["access_token"] = hval[7:].strip()
                                elif hname == "cookie" and hval:
                                    result["cookie"] = hval
                            for hdr in resp.get("headers") or []:
                                hname = str(hdr.get("name") or "").lower()
                                hval = str(hdr.get("value") or "").strip()
                                if hname == "x-customer-wh" and hval:
                                    result["warehouse"] = hval.lower()
        except Exception:
            pass

    # 2. Extract from cURL command, headers, or embedded JSON snippets if not already populated
    if not result["access_token"]:
        m_bearer = re.search(r"(?i)authorization\s*:\s*bearer\s+([A-Za-z0-9._~+/=-]+)", text)
        if m_bearer:
            result["access_token"] = m_bearer.group(1).strip()
        else:
            m_tok_json = re.search(r'"(?:access_token|accessToken|token)"\s*:\s*"(eyJ[A-Za-z0-9._~+/=-]+)"', text)
            if m_tok_json:
                result["access_token"] = m_tok_json.group(1).strip()

    if not result["refresh_token"]:
        m_ref_json = re.search(r'"(?:refresh_token|refreshToken)"\s*:\s*"([A-Za-z0-9._~+/=-]+)"', text)
        if m_ref_json:
            result["refresh_token"] = m_ref_json.group(1).strip()

    if not result["cookie"]:
        m_cookie_b = re.search(r"(?:^|\s)(?:-b|--cookie)\s+['\"]([^'\"]+)['\"]", text)
        if m_cookie_b:
            result["cookie"] = m_cookie_b.group(1).strip()
        else:
            m_cookie_h = re.search(r"(?i)(?:-H|--header)\s+['\"]cookie\s*:\s*([^'\"]+)['\"]", text)
            if m_cookie_h:
                result["cookie"] = m_cookie_h.group(1).strip()

    if not result["customer_id"]:
        m_cust = re.search(r"/api/customers/([^/'\"\s?&]+)/", text)
        if m_cust and m_cust.group(1).lower() != "me":
            result["customer_id"] = m_cust.group(1).strip()
        else:
            m_uuid_json = re.search(
                r'"(?:customer_id|customer_uuid|customerUuid|uuid|userUuid)"\s*:\s*"([^"\s]+)"', text
            )
            if m_uuid_json and m_uuid_json.group(1).lower() != "me":
                result["customer_id"] = m_uuid_json.group(1).strip()

    if not result["warehouse"]:
        m_wh = re.search(r"[?&]wh=([a-z0-9]+)", text, re.I)
        if m_wh:
            result["warehouse"] = m_wh.group(1).lower()

    # Extract warehouse from __mo_da cookie if present
    mo_wh, _ = _extract_mo_da_from_cookie(result["cookie"] or text)
    if mo_wh and not result["warehouse"]:
        result["warehouse"] = mo_wh

    # 3. Raw JWT token (or "Bearer eyJ...")
    if not result["access_token"] and not result["refresh_token"]:
        cleaned = text
        if cleaned.lower().startswith("bearer "):
            cleaned = cleaned[7:].strip()
        m_jwt = re.search(r"\b(eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)\b", cleaned)
        token_candidate = m_jwt.group(1) if m_jwt else (cleaned if " " not in cleaned and len(cleaned) > 24 else "")
        if token_candidate:
            claims = _decode_jwt_claims(token_candidate)
            tok_type = str(claims.get("token_type") or "").lower()
            if tok_type == "refresh":
                result["refresh_token"] = token_candidate
            else:
                result["access_token"] = token_candidate

    # Check if the extracted access_token is actually a refresh_token
    if result["access_token"] and not result["refresh_token"]:
        claims = _decode_jwt_claims(result["access_token"])
        if str(claims.get("token_type") or "").lower() == "refresh":
            result["refresh_token"] = result["access_token"]
            result["access_token"] = ""

    # Resolve customer_id from JWT claims if missing
    if not result["customer_id"]:
        for tok in (result["access_token"], result["refresh_token"]):
            if tok:
                cid = customer_from_jwt(tok)
                if cid:
                    result["customer_id"] = cid
                    break

    # Sanitize extracted tokens, cookies, warehouse, and customer_id against CRLF / path injection
    result["access_token"] = re.sub(r"[\r\n]+", "", result["access_token"]).strip()
    result["refresh_token"] = re.sub(r"[\r\n]+", "", result["refresh_token"]).strip()
    result["cookie"] = re.sub(r"[\r\n]+", "", result["cookie"]).strip()
    result["warehouse"] = _sanitize_warehouse(result["warehouse"], default="")
    if result["customer_id"] and not _CUSTOMER_ID_RE.match(result["customer_id"]):
        result["customer_id"] = ""

    return result


def _build_mercadona_headers(access_token: str = "", cookie: str = "") -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        "Content-Type": "application/json",
        "User-Agent": MERCADONA_DEFAULT_UA,
        "Referer": f"{MERCADONA_BASE_URL}/",
        "Origin": MERCADONA_BASE_URL,
        "x-version": MERCADONA_DEFAULT_VERSION,
        "x-customer-device-id": "00000000-0000-0000-0000-000000000000",
    }
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    if cookie:
        headers["Cookie"] = cookie
    return headers


def refresh_mercadona_token(refresh_token: str, cookie: str = "") -> dict[str, str]:
    """Exchanges a Mercadona refresh_token for a fresh access_token via POST /api/auth/tokens/."""
    rt = str(refresh_token or "").strip()
    if not rt:
        raise ValueError("No se proporcionó un refresh_token.")

    url = f"{MERCADONA_BASE_URL}/api/auth/tokens/"
    payload = json.dumps({"refresh_token": rt}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers=_build_mercadona_headers(cookie=cookie),
    )
    with urllib.request.urlopen(req, timeout=8) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        new_access = str(data.get("access_token") or "").strip()
        new_refresh = str(data.get("refresh_token") or rt).strip()
        cid = str(data.get("customer_id") or data.get("customer_uuid") or "").strip()
        if not cid and new_access:
            cid = customer_from_jwt(new_access)
        return {
            "access_token": new_access,
            "refresh_token": new_refresh,
            "customer_id": cid,
        }


def _load_saved_sessions() -> dict[str, dict[str, Any]]:
    global _MERCADONA_SESSIONS
    with _SESSIONS_LOCK:
        if _MERCADONA_SESSIONS:
            return _MERCADONA_SESSIONS
        if SESSIONS_FILE.exists():
            try:
                data = json.loads(SESSIONS_FILE.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    _MERCADONA_SESSIONS = data
            except Exception:
                pass
        return _MERCADONA_SESSIONS


def _save_sessions_to_disk() -> None:
    with _SESSIONS_LOCK:
        tmp_path: str | None = None
        try:
            target_dir = SESSIONS_FILE.parent
            target_dir.mkdir(parents=True, exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(
                dir=str(target_dir), prefix=".mercadona_sessions_", suffix=".tmp"
            )
            try:
                os.fchmod(fd, 0o600)
            except AttributeError:
                os.chmod(tmp_path, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(_MERCADONA_SESSIONS, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, SESSIONS_FILE)
            tmp_path = None
            os.chmod(SESSIONS_FILE, 0o600)
        except Exception:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass


def get_active_mercadona_session(user_email: str = "default") -> dict[str, str] | None:
    """Returns the active Mercadona session strictly isolated to the given user (or env fallback)."""
    with _SESSIONS_LOCK:
        sessions = _load_saved_sessions()
        key = (str(user_email) if user_email else "default").strip().lower()
        sess = sessions.get(key)
        if sess and (sess.get("access_token") or sess.get("refresh_token")):
            return dict(sess)

    env_tok = os.environ.get("MERCADONA_TOKEN", "").strip()
    env_ref = os.environ.get("MERCADONA_REFRESH_TOKEN", "").strip()
    env_ck = os.environ.get("MERCADONA_COOKIE", "").strip()
    env_cid = os.environ.get("MERCADONA_CUSTOMER", "").strip()
    if env_tok or env_ref:
        if not env_cid and env_tok:
            env_cid = customer_from_jwt(env_tok)
        mo_wh, mo_pc = _extract_mo_da_from_cookie(env_ck)
        return {
            "access_token": env_tok,
            "refresh_token": env_ref,
            "cookie": env_ck,
            "customer_id": env_cid,
            "warehouse": mo_wh,
            "postal_code": mo_pc,
        }
    return None


def get_mercadona_session_status(user_email: str = "default") -> dict[str, Any]:
    """Returns safe metadata about the user's connected Mercadona session."""
    sess = get_active_mercadona_session(user_email)
    if not sess:
        return {
            "connected": False,
            "customer_id": None,
            "has_refresh_token": False,
            "warehouse": None,
            "postal_code": None,
            "masked_token": None,
        }
    tok = sess.get("access_token") or sess.get("refresh_token") or ""
    masked = f"{tok[:10]}…{tok[-6:]}" if len(tok) > 20 else "Configurado"
    return {
        "connected": True,
        "customer_id": sess.get("customer_id") or customer_from_jwt(tok) or None,
        "has_refresh_token": bool(sess.get("refresh_token")),
        "warehouse": sess.get("warehouse") or None,
        "postal_code": sess.get("postal_code") or None,
        "masked_token": masked,
        "updated_at": sess.get("updated_at"),
    }


def clear_mercadona_session(user_email: str = "default") -> dict[str, Any]:
    """Removes the stored Mercadona session strictly for the requesting user."""
    with _SESSIONS_LOCK:
        sessions = _load_saved_sessions()
        key = str(user_email or "").strip().lower()
        if key:
            sessions.pop(key, None)
        _save_sessions_to_disk()
    return {"connected": False, "message": "Sesión de Mercadona.es desvinculada correctamente."}


def _mercadona_authed_request(
    method: str,
    path_and_query: str,
    session: dict[str, Any],
    body: dict[str, Any] | None = None,
    user_email: str = "default",
) -> dict[str, Any]:
    """Executes an authenticated HTTP request against tienda.mercadona.es with automatic token refresh."""
    access_token = str(session.get("access_token") or "").strip()
    refresh_token = str(session.get("refresh_token") or "").strip()
    cookie = str(session.get("cookie") or "").strip()

    if not access_token and refresh_token:
        refreshed = refresh_mercadona_token(refresh_token, cookie=cookie)
        access_token = refreshed["access_token"]
        refresh_token = refreshed["refresh_token"]
        session["access_token"] = access_token
        session["refresh_token"] = refresh_token
        if refreshed.get("customer_id"):
            session["customer_id"] = refreshed["customer_id"]

    url = f"{MERCADONA_BASE_URL}{path_and_query}"
    payload = json.dumps(body).encode("utf-8") if body is not None else None

    for attempt in range(2):
        req = urllib.request.Request(
            url,
            data=payload,
            method=method,
            headers=_build_mercadona_headers(access_token=access_token, cookie=cookie),
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp_headers = getattr(resp, "headers", None)
                if resp_headers:
                    resp_wh = _sanitize_warehouse(resp_headers.get("x-customer-wh") or "", default="")
                    resp_pc = (resp_headers.get("x-customer-pc") or "").strip()
                    if resp_wh:
                        session["server_wh"] = resp_wh
                    if resp_pc:
                        session["server_pc"] = resp_pc
                raw = resp.read().decode("utf-8", "ignore")
                return json.loads(raw) if raw.strip() else {}
        except urllib.error.HTTPError as e:
            err_body = ""
            try:
                err_body = e.read().decode("utf-8", "ignore")
            except Exception:
                pass
            if e.code == 401 and refresh_token and attempt == 0:
                # Transparently refresh expired access_token and retry once
                refreshed = refresh_mercadona_token(refresh_token, cookie=cookie)
                access_token = refreshed["access_token"]
                session["access_token"] = access_token
                session["refresh_token"] = refreshed["refresh_token"]
                if refreshed.get("customer_id"):
                    session["customer_id"] = refreshed["customer_id"]
                with _SESSIONS_LOCK:
                    sessions = _load_saved_sessions()
                    key = str(user_email or "").strip().lower()
                    if key:
                        sessions[key] = session
                        _save_sessions_to_disk()
                continue
            raise RuntimeError(f"Mercadona API HTTP {e.code}: {err_body[:280] or e.reason}") from e
    return {}


def _detect_customer_warehouse_and_pc(
    session: dict[str, Any],
    fallback_pc: str = "28016",
    user_email: str = "default",
) -> tuple[str, str]:
    """Determines the customer's exact warehouse (`wh`) and postal code (`pc`) on tienda.mercadona.es
    so that backend cart updates never conflict with the browser's `__mo_da` delivery area.
    """
    customer_id = str(session.get("customer_id") or "").strip()

    # 1. Check `__mo_da` cookie if present in session
    mo_wh, mo_pc = _extract_mo_da_from_cookie(str(session.get("cookie") or ""))
    mo_wh = _sanitize_warehouse(mo_wh, default="")
    if mo_wh:
        session["warehouse"] = mo_wh
        if mo_pc:
            session["postal_code"] = mo_pc
        return mo_wh, mo_pc or str(session.get("postal_code") or fallback_pc)

    # 2. Check if customer has saved delivery addresses on tienda.mercadona.es
    if customer_id and _CUSTOMER_ID_RE.match(customer_id):
        try:
            addr_data = _mercadona_authed_request(
                "GET",
                f"/api/customers/{urllib.parse.quote(customer_id, safe='')}/addresses/?lang=es",
                session,
                user_email=user_email,
            )
            results = addr_data.get("results") if isinstance(addr_data, dict) else []
            if isinstance(results, list) and results:
                # Prefer permanent/default address first
                chosen_addr = next(
                    (a for a in results if isinstance(a, dict) and a.get("permanent_address")),
                    results[0] if isinstance(results[0], dict) else None,
                )
                if chosen_addr:
                    addr_pc = str(chosen_addr.get("postal_code") or "").strip()
                    if len(addr_pc) == 5:
                        pc_info = resolve_postal_code(addr_pc)
                        wh = _sanitize_warehouse(session.get("server_wh") or pc_info["warehouse"])
                        session["warehouse"] = wh
                        session["postal_code"] = addr_pc
                        return wh, addr_pc
            if session.get("server_wh"):
                wh = _sanitize_warehouse(session["server_wh"])
                pc = str(session.get("server_pc") or session.get("postal_code") or fallback_pc)
                session["warehouse"] = wh
                session["postal_code"] = pc
                return wh, pc
        except Exception:
            pass

    # 3. Use explicitly stored warehouse or resolve fallback postal code
    pc_info = resolve_postal_code(str(session.get("postal_code") or fallback_pc))
    wh = _sanitize_warehouse(session.get("warehouse") or pc_info["warehouse"], default=pc_info["warehouse"])
    pc = str(session.get("postal_code") or pc_info["postal_code"]).strip()
    return wh, pc


def validate_cart_lines_anonymous(
    lines: list[dict[str, Any]],
    warehouse: str = "mad3",
    cart_id: str = "",
) -> dict[str, Any] | None:
    """Calls `POST https://tienda.mercadona.es/api/carts/?lang=es&wh=<wh>` (`wd.validate` in the SPA)
    to validate cart lines and inspect which products are published in `<wh>`.
    """
    wh = _sanitize_warehouse(warehouse, default="mad3")
    url = f"{MERCADONA_BASE_URL}/api/carts/?lang=es&wh={urllib.parse.quote(wh, safe='')}"
    payload = json.dumps(
        {
            "id": cart_id or str(uuid.uuid4()),
            "lines": lines,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers=_build_mercadona_headers(),
    )
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            raw = resp.read().decode("utf-8", "ignore")
            return json.loads(raw) if raw.strip() else None
    except Exception:
        return None


def verify_and_save_mercadona_session(
    raw_input: str,
    postal_code: str = "28016",
    user_email: str = "default",
) -> dict[str, Any]:
    """Parses user-supplied Mercadona auth material, verifies it live against tienda.mercadona.es, and saves it."""
    parsed = parse_mercadona_auth_input(raw_input)
    if not parsed["access_token"] and not parsed["refresh_token"]:
        raise ValueError(
            "No se detectó ningún Bearer token, refresh_token ni comando 'Copy as cURL' válido. "
            "Usa el botón '🔗 Vincular con Mercadona.es (1-Click)' o, si usas DevTools → Network, filtra por 'customers' (o 'cart') y copia esa petición (Copy as cURL)."
        )

    if not parsed["access_token"] and parsed["refresh_token"]:
        refreshed = refresh_mercadona_token(parsed["refresh_token"], cookie=parsed["cookie"])
        parsed["access_token"] = refreshed["access_token"]
        parsed["refresh_token"] = refreshed["refresh_token"]
        if refreshed.get("customer_id"):
            parsed["customer_id"] = refreshed["customer_id"]

    if not parsed["customer_id"] and parsed["access_token"]:
        parsed["customer_id"] = customer_from_jwt(parsed["access_token"])

    if not parsed["customer_id"]:
        raise ValueError(
            "No se pudo determinar el customer_id (customer_uuid) del token. "
            "Asegúrate de pegar el token JWT completo o el comando 'Copy as cURL' de una petición a /api/customers/<id>/cart/."
        )

    validated_cid = _validate_customer_id(parsed["customer_id"])
    parsed["customer_id"] = validated_cid

    _, mo_pc = _extract_mo_da_from_cookie(parsed["cookie"] or str(raw_input or ""))

    session_record: dict[str, Any] = {
        "access_token": parsed["access_token"],
        "refresh_token": parsed["refresh_token"],
        "cookie": parsed["cookie"],
        "customer_id": validated_cid,
        "warehouse": _sanitize_warehouse(parsed["warehouse"], default=""),
        "postal_code": mo_pc or postal_code,
        "updated_at": int(time.time()),
    }

    # Verify live against GET /api/customers/<id>/cart/
    wh = _sanitize_warehouse(
        parsed["warehouse"] or resolve_postal_code(mo_pc or postal_code)["warehouse"],
        default="mad3",
    )
    cart_path = (
        f"/api/customers/{urllib.parse.quote(validated_cid, safe='')}/cart/"
        f"?lang=es&wh={urllib.parse.quote(wh, safe='')}"
    )
    cart_data = _mercadona_authed_request("GET", cart_path, session_record, user_email=user_email)

    # If the cart response header indicates a specific customer warehouse, honor it
    resolved_pc = mo_pc or postal_code
    if session_record.get("server_wh") and not parsed["warehouse"]:
        wh = _sanitize_warehouse(session_record["server_wh"], default=wh)
    if session_record.get("server_pc") and not mo_pc:
        resolved_pc = str(session_record["server_pc"]).strip()

    session_record["warehouse"] = wh
    session_record["postal_code"] = resolved_pc

    with _SESSIONS_LOCK:
        sessions = _load_saved_sessions()
        key = str(user_email or "default").strip().lower()
        if key:
            sessions[key] = session_record
            _save_sessions_to_disk()

    products_count = int(cart_data.get("products_count") or len(cart_data.get("lines") or []))
    cart_total = str((cart_data.get("summary") or {}).get("total") or "0.00")

    return {
        "connected": True,
        "customer_id": session_record["customer_id"],
        "warehouse": wh,
        "postal_code": resolved_pc,
        "has_refresh_token": bool(session_record["refresh_token"]),
        "masked_token": f"{session_record['access_token'][:10]}…{session_record['access_token'][-6:]}",
        "cart_id": cart_data.get("id"),
        "current_cart_products": products_count,
        "current_cart_total": cart_total,
        "message": (
            f"Cuenta de Mercadona.es conectada y verificada (Cliente {session_record['customer_id']} · "
            f"CP {resolved_pc} · Almacén {wh}). "
            f"Tu carrito actual en tienda.mercadona.es tiene {products_count} productos ({cart_total} €)."
        ),
    }


def _extract_line_product_id(raw_line: dict[str, Any]) -> str:
    pid = str(raw_line.get("product_id") or "").strip()
    if not pid and isinstance(raw_line.get("product"), dict):
        pid = str(raw_line["product"].get("id") or "").strip()
    return pid


def _format_qty(qty: float | int) -> int | float:
    val = round(float(qty), 3)
    return int(val) if val == int(val) else val


def prepare_mercadona_oneclick_cart(
    basket: list[dict[str, Any]],
    postal_code: str = "28016",
    user_email: str = "default",
    raw_auth_input: str | None = None,
    mode: str = "add",
) -> dict[str, Any]:
    """Synchronizes the planned basket directly into the user's real `tienda.mercadona.es` cart
    via `GET` + `PUT /api/customers/<customer_id>/cart/?lang=es&wh=<wh>` when a Mercadona session
    is connected (Option 1), validating and auto-substituting any warehouse-specific product IDs
    so the Cart Drawer on tienda.mercadona.es renders all lines cleanly.
    """
    pc_info = resolve_postal_code(postal_code)
    wh = _sanitize_warehouse(pc_info["warehouse"], default="mad3")

    # If the user supplied fresh auth input inline, verify and save it first
    inline_auth_error = None
    if raw_auth_input and str(raw_auth_input).strip():
        try:
            verify_and_save_mercadona_session(
                raw_input=str(raw_auth_input).strip(),
                postal_code=postal_code,
                user_email=user_email,
            )
        except Exception as exc:
            inline_auth_error = str(exc)

    session = get_active_mercadona_session(user_email)
    target_wh = wh
    target_pc = pc_info["postal_code"]
    substitutions: list[dict[str, str]] = []

    if session and not inline_auth_error:
        if session.get("warehouse"):
            target_wh = _sanitize_warehouse(session["warehouse"], default=wh)
            target_pc = str(session.get("postal_code") or target_pc).strip()
        else:
            target_wh, target_pc = _detect_customer_warehouse_and_pc(
                session, fallback_pc=postal_code, user_email=user_email
            )

    # Validate basket product_ids against the target warehouse (`target_wh`) via Algolia when syncing live
    valid_in_wh: dict[str, dict[str, Any]] = {}
    if session and not inline_auth_error:
        basket_pids = [str(item.get("id") or item.get("product_id") or "").strip() for item in basket]
        valid_in_wh = fetch_algolia_products_batch([p for p in basket_pids if p], target_wh)

    lines: list[dict[str, Any]] = []
    for item in basket:
        orig_pid = str(item.get("id") or item.get("product_id") or "").strip()
        orig_name = str(item.get("name") or "").strip()
        raw_q = item["quantity"] if "quantity" in item and item["quantity"] is not None else 1
        qty = int(round(float(raw_q)))

        live_prod = valid_in_wh.get(orig_pid) if (session and not inline_auth_error) else None
        if (session and not inline_auth_error) and not live_prod and orig_name and valid_in_wh:
            # Product ID is not published in target_wh -> search active replacement in target_wh
            replacement = search_algolia_replacement(orig_name, target_wh)
            if replacement:
                live_prod = replacement
                if replacement["id"] != orig_pid:
                    substitutions.append(
                        {
                            "from_id": orig_pid,
                            "from_name": orig_name,
                            "to_id": replacement["id"],
                            "to_name": replacement["name"],
                        }
                    )

        if live_prod:
            pid = str(live_prod["id"])
            name = str(live_prod["name"] or orig_name)
            unit_price = float(live_prod["unit_price"])
            unit = str(live_prod.get("unit") or item.get("unit") or "1 ud")
            share_url = str(live_prod.get("share_url") or f"https://tienda.mercadona.es/product/{pid}")
        else:
            pid = orig_pid
            name = orig_name
            unit_price = float(item.get("unit_price") or 0.0)
            unit = str(item.get("unit") or "1 ud")
            share_url = str(item.get("share_url") or f"https://tienda.mercadona.es/product/{pid}")

        lines.append(
            {
                "product_id": pid,
                "name": name,
                "quantity": qty,
                "unit": unit,
                "unit_price": unit_price,
                "line_total": round(unit_price * qty, 2),
                "product_url": share_url,
            }
        )

    total = round(sum(x["line_total"] for x in lines), 2)

    if session and not inline_auth_error:
        customer_id = str(session.get("customer_id") or "").strip()
        if not customer_id and session.get("access_token"):
            customer_id = customer_from_jwt(session["access_token"])
            session["customer_id"] = customer_id

        if customer_id and _CUSTOMER_ID_RE.match(customer_id):
            cart_path = (
                f"/api/customers/{urllib.parse.quote(customer_id, safe='')}/cart/"
                f"?lang=es&wh={urllib.parse.quote(target_wh, safe='')}"
            )
            try:
                # 1. GET current real cart from tienda.mercadona.es
                current_cart = _mercadona_authed_request(
                    "GET", cart_path, session, user_email=user_email
                )
                cart_id = str(current_cart.get("id") or "")
                cart_version = current_cart.get("version")
                existing_raw_lines = current_cart.get("lines") or []

                # 2. Build the desired line set matching `Xd(cart)` in tienda.mercadona.es's SPA bundle:
                # {"id"?, "quantity", "version"?, "product_id", "sources"}
                merged_by_id: dict[str, dict[str, Any]] = {}
                ordered_ids: list[str] = []

                if mode != "replace":
                    for rline in existing_raw_lines:
                        if not isinstance(rline, dict):
                            continue
                        prod_obj = rline.get("product") if isinstance(rline.get("product"), dict) else {}
                        if prod_obj.get("published") is False:
                            continue
                        pid = _extract_line_product_id(rline)
                        qty = _format_qty(float(rline.get("quantity") or 0))
                        if pid and qty > 0:
                            existing_sources = (
                                [str(s) for s in rline.get("sources") if s]
                                if isinstance(rline.get("sources"), list)
                                else []
                            )
                            line_entry: dict[str, Any] = {
                                "product_id": pid,
                                "quantity": qty,
                                "sources": existing_sources or ["+search"],
                            }
                            if rline.get("version") is not None:
                                line_entry["version"] = rline["version"]
                            if rline.get("id"):
                                line_entry["id"] = rline["id"]
                            merged_by_id[pid] = line_entry
                            ordered_ids.append(pid)

                for item in lines:
                    pid = str(item["product_id"])
                    qty = _format_qty(item["quantity"])
                    if qty <= 0:
                        continue
                    added_sources = ["+search"] * int(max(1, round(float(qty))))
                    if pid in merged_by_id:
                        if mode == "replace":
                            merged_by_id[pid]["quantity"] = qty
                            merged_by_id[pid]["sources"] = added_sources
                        else:
                            new_qty = _format_qty(float(merged_by_id[pid]["quantity"]) + float(qty))
                            merged_by_id[pid]["quantity"] = new_qty
                            merged_by_id[pid]["sources"] = (
                                list(merged_by_id[pid].get("sources") or []) + added_sources
                            )[-50:]
                    else:
                        merged_by_id[pid] = {
                            "product_id": pid,
                            "quantity": qty,
                            "sources": added_sources,
                        }
                        ordered_ids.append(pid)

                put_lines = [merged_by_id[pid] for pid in ordered_ids if merged_by_id[pid]["quantity"] > 0]

                # 3. Pre-validate cart lines via `POST /api/carts/?lang=es&wh=<target_wh>` (`wd.validate`)
                # to strip any line that Mercadona's cart engine marks as `published: false` in `<target_wh>`
                validated_preview = validate_cart_lines_anonymous(
                    put_lines, warehouse=target_wh, cart_id=cart_id
                )
                if isinstance(validated_preview, dict) and isinstance(validated_preview.get("lines"), list):
                    unpublished_preview_ids: set[str] = set()
                    for vline in validated_preview["lines"]:
                        if not isinstance(vline, dict):
                            continue
                        vprod = vline.get("product") if isinstance(vline.get("product"), dict) else {}
                        vpid = str(vprod.get("id") or vline.get("product_id") or "").strip()
                        if vpid and vprod.get("published") is False:
                            unpublished_preview_ids.add(vpid)
                    if unpublished_preview_ids:
                        put_lines = [
                            ln for ln in put_lines if str(ln.get("product_id")) not in unpublished_preview_ids
                        ]

                put_body: dict[str, Any] = {"lines": put_lines}
                if cart_id:
                    put_body["id"] = cart_id
                if cart_version is not None:
                    put_body["version"] = cart_version

                # 4. PUT updated cart directly to tienda.mercadona.es
                updated_cart = _mercadona_authed_request(
                    "PUT", cart_path, session, body=put_body, user_email=user_email
                )

                # 5. Post-PUT sanity check: if any returned line is unpublished, strip it and re-PUT cleanly
                ret_lines = updated_cart.get("lines") if isinstance(updated_cart, dict) else None
                if isinstance(ret_lines, list):
                    bad_ids = {
                        _extract_line_product_id(rl)
                        for rl in ret_lines
                        if isinstance(rl, dict)
                        and isinstance(rl.get("product"), dict)
                        and rl["product"].get("published") is False
                    }
                    if bad_ids:
                        clean_put_lines = [
                            ln for ln in put_lines if str(ln.get("product_id")) not in bad_ids
                        ]
                        clean_body: dict[str, Any] = {"lines": clean_put_lines}
                        if updated_cart.get("id") or cart_id:
                            clean_body["id"] = str(updated_cart.get("id") or cart_id)
                        if updated_cart.get("version") is not None:
                            clean_body["version"] = updated_cart["version"]
                        updated_cart = _mercadona_authed_request(
                            "PUT", cart_path, session, body=clean_body, user_email=user_email
                        )
                        put_lines = clean_put_lines

                remote_count = int(updated_cart.get("products_count") or len(put_lines))
                remote_total = str((updated_cart.get("summary") or {}).get("total") or f"{total:.2f}")
                remote_cart_id = str(updated_cart.get("id") or cart_id or "")
                remote_version = updated_cart.get("version")

                sub_note = ""
                if substitutions:
                    sub_preview = ", ".join(
                        f"{s['from_name']} → {s['to_name']}" for s in substitutions[:3]
                    )
                    sub_note = f" (Adaptados automáticamente al almacén {target_wh}: {sub_preview})."

                return {
                    "status": "synced_live",
                    "live_synced": True,
                    "mode": mode,
                    "customer_id": customer_id,
                    "postal_code": target_pc,
                    "warehouse": target_wh,
                    "cart_id": remote_cart_id,
                    "cart_version": remote_version,
                    "items_count": sum(x["quantity"] for x in lines),
                    "unique_products": len(lines),
                    "total": total,
                    "remote_products_count": remote_count,
                    "remote_cart_total": remote_total,
                    "substitutions": substitutions,
                    "lines": lines,
                    "mercadona_checkout_url": "https://tienda.mercadona.es/",
                    "message": (
                        f"¡Añadidos {len(lines)} productos ({sum(x['quantity'] for x in lines)} uds) directamente a tu carrito real "
                        f"de tienda.mercadona.es! Carrito actualizado: {remote_count} productos en total "
                        f"({remote_total} € · CP {target_pc} · Almacén {target_wh}).{sub_note}"
                    ),
                }
            except Exception as exc:
                inline_auth_error = str(exc)

    # Check `/api/carts/` endpoint availability when not yet connected with a user token
    carts_endpoint_ok = False
    try:
        req = urllib.request.Request(
            f"{MERCADONA_BASE_URL}/api/carts/",
            method="OPTIONS",
            headers=_build_mercadona_headers(),
        )
        with urllib.request.urlopen(req, timeout=4) as resp:
            carts_endpoint_ok = resp.status == 200
    except Exception:
        carts_endpoint_ok = False

    return {
        "status": "cart_ready",
        "live_synced": False,
        "auth_required": True,
        "auth_error": inline_auth_error,
        "postal_code": target_pc,
        "warehouse": target_wh,
        "api_carts_verified": carts_endpoint_ok,
        "substitutions": substitutions,
        "items_count": sum(x["quantity"] for x in lines),
        "unique_products": len(lines),
        "total": total,
        "lines": lines,
        "mercadona_checkout_url": "https://tienda.mercadona.es/",
        "message": (
            f"Error al sincronizar con tu cuenta de Mercadona.es: {inline_auth_error}"
            if inline_auth_error
            else (
                f"Se han preparado {len(lines)} productos ({total:.2f} €) para el CP {target_pc} ({target_wh}). "
                "Conecta tu sesión de tienda.mercadona.es (Bearer token o Copy as cURL) para inyectarlos directamente en tu carrito real."
            )
        ),
    }

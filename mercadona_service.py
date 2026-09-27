"""Mercadona Tienda API integration service (tienda.mercadona.es/api/).

Implements real-time postal code resolution (`PUT /api/postal-codes/actions/change-pc/`),
live product availability & pricing lookup (`GET /api/products/<id>/?lang=es&wh=<wh>`),
category browsing (`GET /api/categories/`), and 1-click cart preparation.
"""

from __future__ import annotations

import base64
import concurrent.futures
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
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
MERCADONA_DEFAULT_VERSION = "v9200"

# In-memory cache for postal code -> warehouse, live product lookups, and user Mercadona sessions
_PC_CACHE: dict[str, dict[str, str]] = {"28016": {"postal_code": "28016", "warehouse": "mad3"}}
_LIVE_PRODUCT_CACHE: dict[tuple[str, str], tuple[float, dict[str, Any]]] = {}
_MERCADONA_SESSIONS: dict[str, dict[str, Any]] = {}
_CACHE_TTL_SECONDS = 900  # 15 minutes


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

    url = "https://tienda.mercadona.es/api/postal-codes/actions/change-pc/"
    payload = json.dumps({"new_postal_code": pc}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        method="PUT",
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Mercadona-AI-Companion)",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            wh = resp.headers.get("x-customer-wh") or _guess_warehouse(pc)
            resolved_pc = resp.headers.get("x-customer-pc") or pc
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


def fetch_live_product(product_id: str, warehouse: str = "mad3") -> dict[str, Any] | None:
    """Fetches real-time availability, price, pack size, and allergens for a Mercadona product."""
    pid = str(product_id).strip()
    cache_key = (pid, warehouse)
    now = time.time()
    if cache_key in _LIVE_PRODUCT_CACHE:
        ts, data = _LIVE_PRODUCT_CACHE[cache_key]
        if now - ts < _CACHE_TTL_SECONDS:
            return data

    url = f"https://tienda.mercadona.es/api/products/{pid}/?lang=es&wh={warehouse}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=4) as resp:
            d = json.loads(resp.read().decode("utf-8"))
            pi = d.get("price_instructions", {})
            ni = d.get("nutrition_information", {})
            unit_price = float(pi.get("unit_price") or 0.0)
            if unit_price <= 0:
                return None
            unit_size = pi.get("unit_size")
            size_format = pi.get("size_format", "ud")
            allergens_raw = re.sub(r"<[^>]+>", "", ni.get("allergens") or "").strip()
            if not allergens_raw or allergens_raw.lower() in ("x99.", "x99"):
                allergens_raw = "Sin alérgenos declarados en la API"

            product = {
                "id": str(d.get("id", pid)),
                "name": d.get("display_name", ""),
                "thumbnail": d.get("thumbnail", ""),
                "share_url": d.get("share_url", f"https://tienda.mercadona.es/product/{pid}"),
                "unit_price": unit_price,
                "unit_size": unit_size,
                "size_format": size_format,
                "unit": f"{unit_size} {size_format}" if unit_size else size_format,
                "packaging": d.get("packaging", ""),
                "allergens": allergens_raw,
                "available": True,
                "source": "live",
            }
            _LIVE_PRODUCT_CACHE[cache_key] = (now, product)
            return product
    except urllib.error.HTTPError as e:
        if e.code == 404:
            # Product unavailable in this postal code / warehouse
            return None
        return None
    except Exception:
        return None


def get_catalog_for_postal_code(
    postal_code: str = "28016",
    verify_live_ids: list[str] | None = None,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Returns the Mercadona product catalog for the given postal code, refreshing requested IDs live."""
    pc_info = resolve_postal_code(postal_code)
    wh = pc_info["warehouse"]
    snapshot = load_snapshot_products()
    catalog: dict[str, dict[str, Any]] = {}
    for pid, item in snapshot.items():
        cp = dict(item)
        cp["available"] = True
        cp["source"] = "snapshot"
        catalog[pid] = cp

    live_count = 0
    ids_to_check = verify_live_ids or list(catalog.keys())[:25]
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(fetch_live_product, pid, wh): pid for pid in ids_to_check}
        for fut in concurrent.futures.as_completed(futures):
            pid = futures[fut]
            res = fut.result()
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


def parse_mercadona_auth_input(raw_input: str) -> dict[str, str]:
    """Extracts access_token, refresh_token, cookie, customer_id, and warehouse from any user input:
    - DevTools 'Copy as cURL' command
    - DevTools HAR export or JSON token payload ({access_token, refresh_token, customer_id})
    - Raw Bearer JWT token (access_token or refresh_token)
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

    # 1. Try parsing as JSON / HAR first if it starts with '{'
    if text.startswith("{"):
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                # Direct token JSON
                if obj.get("access_token") or obj.get("refresh_token") or obj.get("token"):
                    result["access_token"] = str(obj.get("access_token") or obj.get("token") or "").strip()
                    result["refresh_token"] = str(obj.get("refresh_token") or "").strip()
                    result["cookie"] = str(obj.get("cookie") or "").strip()
                    cid = str(obj.get("customer_id") or obj.get("customer_uuid") or "").strip()
                    if cid and cid.lower() != "me":
                        result["customer_id"] = cid
                    result["warehouse"] = str(obj.get("warehouse") or obj.get("wh") or "").strip()
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
                                    if auth_body.get("access_token"):
                                        result["access_token"] = str(auth_body["access_token"]).strip()
                                    if auth_body.get("refresh_token"):
                                        result["refresh_token"] = str(auth_body["refresh_token"]).strip()
                                    cid = str(
                                        auth_body.get("customer_id") or auth_body.get("customer_uuid") or ""
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
        except Exception:
            pass

    # 2. Extract from cURL command or headers if not already populated
    if not result["access_token"]:
        m_bearer = re.search(r"(?i)authorization\s*:\s*bearer\s+([A-Za-z0-9._~+/=-]+)", text)
        if m_bearer:
            result["access_token"] = m_bearer.group(1).strip()

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

    if not result["warehouse"]:
        m_wh = re.search(r"[?&]wh=([a-z0-9]+)", text, re.I)
        if m_wh:
            result["warehouse"] = m_wh.group(1).lower()

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
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        SESSIONS_FILE.write_text(
            json.dumps(_MERCADONA_SESSIONS, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass


def get_active_mercadona_session(user_email: str = "default") -> dict[str, str] | None:
    """Returns the active Mercadona session for the given user (or env fallback)."""
    sessions = _load_saved_sessions()
    key = (user_email or "default").strip().lower()
    sess = sessions.get(key) or sessions.get("default")
    if sess and (sess.get("access_token") or sess.get("refresh_token")):
        return dict(sess)

    env_tok = os.environ.get("MERCADONA_TOKEN", "").strip()
    env_ref = os.environ.get("MERCADONA_REFRESH_TOKEN", "").strip()
    env_ck = os.environ.get("MERCADONA_COOKIE", "").strip()
    env_cid = os.environ.get("MERCADONA_CUSTOMER", "").strip()
    if env_tok or env_ref:
        if not env_cid and env_tok:
            env_cid = customer_from_jwt(env_tok)
        return {
            "access_token": env_tok,
            "refresh_token": env_ref,
            "cookie": env_ck,
            "customer_id": env_cid,
            "warehouse": "",
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
            "masked_token": None,
        }
    tok = sess.get("access_token") or sess.get("refresh_token") or ""
    masked = f"{tok[:10]}…{tok[-6:]}" if len(tok) > 20 else "Configurado"
    return {
        "connected": True,
        "customer_id": sess.get("customer_id") or customer_from_jwt(tok) or None,
        "has_refresh_token": bool(sess.get("refresh_token")),
        "warehouse": sess.get("warehouse") or None,
        "masked_token": masked,
        "updated_at": sess.get("updated_at"),
    }


def clear_mercadona_session(user_email: str = "default") -> dict[str, Any]:
    """Removes the stored Mercadona session for the user."""
    sessions = _load_saved_sessions()
    key = (user_email or "default").strip().lower()
    sessions.pop(key, None)
    sessions.pop("default", None)
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
                sessions = _load_saved_sessions()
                sessions[(user_email or "default").strip().lower()] = session
                _save_sessions_to_disk()
                continue
            raise RuntimeError(f"Mercadona API HTTP {e.code}: {err_body[:280] or e.reason}") from e


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
            "Copia una petición a /api/ desde tienda.mercadona.es (Copy as cURL) o pega tu Bearer token JWT."
        )

    pc_info = resolve_postal_code(postal_code)
    wh = parsed["warehouse"] or pc_info["warehouse"]

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

    session_record = {
        "access_token": parsed["access_token"],
        "refresh_token": parsed["refresh_token"],
        "cookie": parsed["cookie"],
        "customer_id": parsed["customer_id"],
        "warehouse": wh,
        "updated_at": int(time.time()),
    }

    # Verify live against GET /api/customers/<id>/cart/
    cart_path = f"/api/customers/{urllib.parse.quote(parsed['customer_id'])}/cart/?lang=es&wh={urllib.parse.quote(wh)}"
    cart_data = _mercadona_authed_request("GET", cart_path, session_record, user_email=user_email)

    sessions = _load_saved_sessions()
    key = (user_email or "default").strip().lower()
    sessions[key] = session_record
    sessions["default"] = session_record
    _save_sessions_to_disk()

    products_count = int(cart_data.get("products_count") or len(cart_data.get("lines") or []))
    cart_total = str((cart_data.get("summary") or {}).get("total") or "0.00")

    return {
        "connected": True,
        "customer_id": session_record["customer_id"],
        "warehouse": wh,
        "has_refresh_token": bool(session_record["refresh_token"]),
        "masked_token": f"{session_record['access_token'][:10]}…{session_record['access_token'][-6:]}",
        "cart_id": cart_data.get("id"),
        "current_cart_products": products_count,
        "current_cart_total": cart_total,
        "message": (
            f"Cuenta de Mercadona.es conectada y verificada (Cliente {session_record['customer_id']} · Almacén {wh}). "
            f"Tu carrito actual en tienda.mercadona.es tiene {products_count} productos ({cart_total} €)."
        ),
    }


def _extract_line_product_id(raw_line: dict[str, Any]) -> str:
    pid = str(raw_line.get("product_id") or "").strip()
    if not pid and isinstance(raw_line.get("product"), dict):
        pid = str(raw_line["product"].get("id") or "").strip()
    return pid


def prepare_mercadona_oneclick_cart(
    basket: list[dict[str, Any]],
    postal_code: str = "28016",
    user_email: str = "default",
    raw_auth_input: str | None = None,
    mode: str = "add",
) -> dict[str, Any]:
    """Synchronizes the planned basket directly into the user's real `tienda.mercadona.es` cart
    via `GET` + `PUT /api/customers/<customer_id>/cart/?lang=es&wh=<wh>` when a Mercadona session
    is connected (Option 1), or prepares the cart payload if not yet connected.
    """
    pc_info = resolve_postal_code(postal_code)
    wh = pc_info["warehouse"]

    lines = [
        {
            "product_id": str(item["id"]),
            "name": item["name"],
            "quantity": int(item["quantity"]),
            "unit": item["unit"],
            "unit_price": item["unit_price"],
            "line_total": item["line_total"],
            "product_url": item.get("share_url") or f"https://tienda.mercadona.es/product/{item['id']}",
        }
        for item in basket
    ]
    total = round(sum(x["line_total"] for x in lines), 2)

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
    if session and not inline_auth_error:
        customer_id = str(session.get("customer_id") or "").strip()
        if not customer_id and session.get("access_token"):
            customer_id = customer_from_jwt(session["access_token"])
            session["customer_id"] = customer_id
        target_wh = session.get("warehouse") or wh

        if customer_id:
            cart_path = (
                f"/api/customers/{urllib.parse.quote(customer_id)}/cart/"
                f"?lang=es&wh={urllib.parse.quote(target_wh)}"
            )
            try:
                # 1. GET current real cart from tienda.mercadona.es
                current_cart = _mercadona_authed_request(
                    "GET", cart_path, session, user_email=user_email
                )
                cart_id = str(current_cart.get("id") or "")
                existing_raw_lines = current_cart.get("lines") or []

                # 2. Build the desired line set in PUT format: {"product_id", "quantity", "sources"}
                merged_by_id: dict[str, dict[str, Any]] = {}
                ordered_ids: list[str] = []

                if mode != "replace":
                    for rline in existing_raw_lines:
                        pid = _extract_line_product_id(rline)
                        qty = float(rline.get("quantity") or 0)
                        if pid and qty > 0:
                            merged_by_id[pid] = {
                                "product_id": pid,
                                "quantity": qty,
                                "sources": rline.get("sources") if isinstance(rline.get("sources"), list) else [],
                            }
                            ordered_ids.append(pid)

                for item in lines:
                    pid = str(item["product_id"])
                    qty = float(item["quantity"])
                    if qty <= 0:
                        continue
                    if pid in merged_by_id:
                        if mode == "replace":
                            merged_by_id[pid]["quantity"] = qty
                        else:
                            merged_by_id[pid]["quantity"] = round(merged_by_id[pid]["quantity"] + qty, 2)
                    else:
                        merged_by_id[pid] = {
                            "product_id": pid,
                            "quantity": qty,
                            "sources": [],
                        }
                        ordered_ids.append(pid)

                put_lines = [merged_by_id[pid] for pid in ordered_ids if merged_by_id[pid]["quantity"] > 0]
                put_body: dict[str, Any] = {"lines": put_lines}
                if cart_id:
                    put_body["id"] = cart_id

                # 3. PUT updated cart directly to tienda.mercadona.es
                updated_cart = _mercadona_authed_request(
                    "PUT", cart_path, session, body=put_body, user_email=user_email
                )
                remote_count = int(updated_cart.get("products_count") or len(put_lines))
                remote_total = str((updated_cart.get("summary") or {}).get("total") or f"{total:.2f}")
                remote_cart_id = str(updated_cart.get("id") or cart_id or "")
                remote_version = updated_cart.get("version")

                return {
                    "status": "synced_live",
                    "live_synced": True,
                    "mode": mode,
                    "customer_id": customer_id,
                    "postal_code": pc_info["postal_code"],
                    "warehouse": target_wh,
                    "cart_id": remote_cart_id,
                    "cart_version": remote_version,
                    "items_count": sum(x["quantity"] for x in lines),
                    "unique_products": len(lines),
                    "total": total,
                    "remote_products_count": remote_count,
                    "remote_cart_total": remote_total,
                    "lines": lines,
                    "mercadona_checkout_url": "https://tienda.mercadona.es/",
                    "message": (
                        f"¡Añadidos {len(lines)} productos ({sum(x['quantity'] for x in lines)} uds) directamente a tu carrito real "
                        f"de tienda.mercadona.es! Carrito actualizado: {remote_count} productos en total ({remote_total} € · Almacén {target_wh})."
                    ),
                }
            except Exception as exc:
                inline_auth_error = str(exc)

    # Check `/api/carts/` endpoint availability when not yet connected with a user token
    carts_endpoint_ok = False
    try:
        req = urllib.request.Request(
            "https://tienda.mercadona.es/api/carts/",
            method="OPTIONS",
            headers={"User-Agent": "Mozilla/5.0"},
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
        "postal_code": pc_info["postal_code"],
        "warehouse": wh,
        "api_carts_verified": carts_endpoint_ok,
        "items_count": sum(x["quantity"] for x in lines),
        "unique_products": len(lines),
        "total": total,
        "lines": lines,
        "mercadona_checkout_url": "https://tienda.mercadona.es/",
        "message": (
            f"Error al sincronizar con tu cuenta de Mercadona.es: {inline_auth_error}"
            if inline_auth_error
            else (
                f"Se han preparado {len(lines)} productos ({total:.2f} €) para el CP {pc_info['postal_code']} ({wh}). "
                "Conecta tu sesión de tienda.mercadona.es (Bearer token o Copy as cURL) para inyectarlos directamente en tu carrito real."
            )
        ),
    }

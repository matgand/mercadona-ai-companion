"""HTTP Server for Mercadona AI Companion & Campaign Library Microservices.

Supports both microservices:
  - eci-ai-companion (main customer planner app, SERVICE_ROLE=companion)
  - campaign-library (Mercadona Marketing campaign microservice, SERVICE_ROLE=campaign-library)

Enforces Google Identity allowlist for:
  - matgand@gmail.com
  - mgandolfi@google.com
  - andrea.anaut@gmail.com
  - mattia@mgandolfi.altostrat.com
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import http.cookies
import json
import mimetypes
import os
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from campaign_service import (
    DEFAULT_RUNTIME_SECRET,
    PROFILES_METADATA,
    VALID_CATEGORIES,
    VALID_STATUSES,
    fetch_campaigns_from_remote_or_local,
    generate_campaign_from_brief,
    get_demand_sensing_analytics,
    is_campaign_library_role,
    load_local_campaigns,
    save_local_campaigns,
    update_campaign_record,
)
from cookidoo_service import (
    clear_cookidoo_session,
    get_cookidoo_session_status,
    load_cookidoo_catalog,
    schedule_weekly_plan_to_cookidoo,
    send_recipe_to_thermomix,
    verify_and_save_cookidoo_session,
)
from mercadona_service import (
    clear_mercadona_session,
    fetch_algolia_products_batch,
    get_catalog_for_postal_code,
    get_mercadona_session_status,
    load_snapshot_products,
    prepare_mercadona_oneclick_cart,
    resolve_postal_code,
    search_algolia_replacement,
    verify_and_save_mercadona_session,
)

# Backwards-compatible aliases for unified route handlers
get_eci_session_status = get_mercadona_session_status
verify_and_save_eci_session = verify_and_save_mercadona_session
clear_eci_session = clear_mercadona_session
prepare_eci_oneclick_cart = prepare_mercadona_oneclick_cart
get_dia_session_status = get_mercadona_session_status
verify_and_save_dia_session = verify_and_save_mercadona_session
clear_dia_session = clear_mercadona_session
prepare_dia_oneclick_cart = prepare_mercadona_oneclick_cart


def fetch_eci_categories() -> list[dict[str, Any]]:
    return []


def fetch_eci_offers() -> list[dict[str, Any]]:
    return []


def search_eci_live(query: str, postal_code: str = "28016") -> list[dict[str, Any]]:
    info = resolve_postal_code(postal_code)
    rep = search_algolia_replacement(query, info.get("warehouse", "mad3"))
    return [rep] if rep else []


def fetch_eci_products_batch(product_ids: list[str], warehouse: str = "mad3", postal_code: str = "28016") -> dict[str, dict[str, Any]]:
    return fetch_algolia_products_batch(product_ids, warehouse=warehouse)


def search_eci_replacement(product_name: str, warehouse: str = "mad3", postal_code: str = "28016") -> dict[str, Any] | None:
    return search_algolia_replacement(product_name, warehouse=warehouse)
from gemini_planner import (
    FRIDGE_VISION_PRESETS,
    analyze_fridge_vision,
    build_weekly_plan,
    clear_user_recipe_preferences,
    format_constraint_pills,
    get_user_recipe_preferences,
    parse_constraints,
    recalculate_plan_basket,
    record_recipe_vote,
    save_user_recipe_preferences,
    swap_single_recipe,
    validate_meal_planning_prompt,
)
from whatsapp_service import (
    format_whatsapp_share_link,
    get_whatsapp_state,
    handle_whatsapp_webhook_post,
    process_whatsapp_user_message,
    sync_active_plan_to_whatsapp,
    update_whatsapp_config,
    verify_whatsapp_webhook_get,
)

PUBLIC_DIR = Path(__file__).resolve().parent / "public"
SESSION_SECRET = os.environ.get("SESSION_SECRET", "").strip() or DEFAULT_RUNTIME_SECRET
SESSION_TTL_SECONDS = 604800  # 7 days
MAX_BODY_BYTES = 6_291_456  # 6 MB max request body (supports Fridge Vision multimodal image uploads)
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
SERVICE_ROLE = os.environ.get("SERVICE_ROLE", "companion").strip().lower()

DEFAULT_COMPANION_URL = "https://mercadona-ai-companion-905208270932.europe-west1.run.app"
DEFAULT_CAMPAIGN_LIBRARY_URL = "https://campaign-library-905208270932.europe-west1.run.app"

DEFAULT_ALLOWED_USERS = [
    "matgand@gmail.com",
    "mgandolfi@google.com",
    "andrea.anaut@gmail.com",
    "mattia@mgandolfi.altostrat.com",
    "barea@google.com",
    "estherarribas@google.com",
    "iolalla@google.com",
    "jamarmu@google.com",
    "lauramarse@google.com",
    "cmartintomas@google.com",
    "veronicapg@google.com",
    "mikelju@gmail.com",
]


class _PayloadError(Exception):
    """Raised when an HTTP request body is malformed or exceeds MAX_BODY_BYTES."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def get_session_secret() -> str:
    env_sec = os.environ.get("SESSION_SECRET", "").strip()
    if env_sec and SESSION_SECRET == DEFAULT_RUNTIME_SECRET:
        return env_sec
    return SESSION_SECRET or DEFAULT_RUNTIME_SECRET


def get_allowed_users() -> list[str]:
    env_val = os.environ.get("ALLOWED_USERS", "").strip()
    if env_val:
        return [u.strip().lower() for u in env_val.split(",") if u.strip()]
    return DEFAULT_ALLOWED_USERS


def get_companion_url() -> str:
    return os.environ.get("COMPANION_APP_URL", DEFAULT_COMPANION_URL).strip().rstrip("/")


def get_campaign_library_url() -> str:
    return os.environ.get("CAMPAIGN_LIBRARY_URL", DEFAULT_CAMPAIGN_LIBRARY_URL).strip().rstrip("/")


def sign_session_email(email: str, exp: int | None = None) -> str:
    clean = email.strip().lower()
    exp_ts = int(exp if exp is not None else (time.time() + SESSION_TTL_SECONDS))
    payload = f"{clean}|{exp_ts}"
    secret = get_session_secret()
    sig = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()[:32]
    return f"{payload}|{sig}"


def verify_session_token(token: str | None) -> str | None:
    if not token or "|" not in token:
        return None
    parts = token.split("|")
    secret = get_session_secret()
    if len(parts) == 3:
        email, exp_str, sig = parts[0].strip().lower(), parts[1].strip(), parts[2].strip()
        try:
            exp_ts = int(exp_str)
        except ValueError:
            return None
        if exp_ts < int(time.time()):
            return None
        payload = f"{email}|{exp_ts}"
        expected = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()[:32]
        if hmac.compare_digest(sig, expected) and email in get_allowed_users():
            return email
    return None


def _decode_unverified_jwt_payload(jwt_token: str) -> dict[str, Any]:
    parts = str(jwt_token or "").strip().split(".")
    if len(parts) != 3:
        return {}
    payload_b64 = parts[1]
    pad = "=" * ((4 - len(payload_b64) % 4) % 4)
    try:
        raw = base64.urlsafe_b64decode((payload_b64 + pad).encode("ascii"))
        data = json.loads(raw.decode("utf-8", "ignore"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def verify_google_id_token(id_token: str) -> str | None:
    """Verifies a Google Identity Services JWT against Google's tokeninfo endpoint."""
    url = f"https://oauth2.googleapis.com/tokeninfo?id_token={urllib.parse.quote(id_token, safe='')}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mercadona-AI-Companion"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if GOOGLE_CLIENT_ID and data.get("aud") != GOOGLE_CLIENT_ID:
                return None
            if data.get("email_verified") in ("true", True):
                return str(data.get("email", "")).strip().lower()
    except Exception:
        return None
    return None


class CompanionRequestHandler(BaseHTTPRequestHandler):
    server_version = "MercadonaAICompanion/2.0"

    def _get_iap_email(self) -> str | None:
        iap_email_hdr = self.headers.get("X-Goog-Authenticated-User-Email", "").strip()
        iap_jwt = self.headers.get("X-Goog-IAP-JWT-Assertion", "").strip()
        enforce_jwt = bool(
            os.environ.get("K_SERVICE") and os.environ.get("ENFORCE_IAP_JWT", "1") != "0"
        ) or os.environ.get("ENFORCE_IAP_JWT") == "1"

        if not iap_email_hdr:
            return None
        header_email = iap_email_hdr.split(":")[-1].strip().lower()
        if not header_email:
            return None

        if iap_jwt or enforce_jwt:
            if not iap_jwt:
                return None
            claims = _decode_unverified_jwt_payload(iap_jwt)
            jwt_email = str(claims.get("email") or "").strip().lower()
            if not jwt_email or jwt_email != header_email:
                return None
            iss = str(claims.get("iss") or "").strip()
            if iss and iss not in (
                "https://cloud.google.com/iap",
                "https://accounts.google.com",
                "accounts.google.com",
            ):
                return None
            exp = claims.get("exp")
            if exp is not None:
                try:
                    if int(exp) < int(time.time()):
                        return None
                except (ValueError, TypeError):
                    return None
        return header_email

    def _is_internal_service_sync(self) -> bool:
        secret = get_session_secret()
        expected = hashlib.sha256(f"internal-sync:{secret}".encode("utf-8")).hexdigest()[:32]
        provided = self.headers.get("X-Internal-Sync-Token", "").strip()
        return bool(provided and hmac.compare_digest(provided, expected))

    def _get_authenticated_user(self) -> str | None:
        allowed = get_allowed_users()

        # 1. Google Cloud Identity-Aware Proxy (IAP) verified header (Primary on Cloud Run)
        if self.headers.get("X-Goog-Authenticated-User-Email") or self.headers.get("X-Goog-IAP-JWT-Assertion"):
            clean_iap = self._get_iap_email()
            return clean_iap if (clean_iap and clean_iap in allowed) else None

        # 2. Cryptographically verified Google OAuth2 Bearer ID Token
        auth_hdr = self.headers.get("Authorization", "").strip()
        if auth_hdr.lower().startswith("bearer "):
            token = auth_hdr[7:].strip()
            verified_email = verify_google_id_token(token)
            return verified_email if (verified_email and verified_email in allowed) else None

        # 3. Signed session cookie (issued only after verified Google ID token or IAP authentication)
        cookie_hdr = self.headers.get("Cookie", "")
        if cookie_hdr:
            jar = http.cookies.SimpleCookie()
            try:
                jar.load(cookie_hdr)
            except Exception:
                return None
            for cookie_name in ("mercadona_session", "eci_session", "dia_session"):
                if cookie_name in jar:
                    val = urllib.parse.unquote(jar[cookie_name].value)
                    user = verify_session_token(val)
                    if user:
                        return user
            return None

        # 4. Local Cloudtop development fallback (only on real local socket connections when not on Cloud Run and JWT enforcement is off)
        if (
            not os.environ.get("K_SERVICE")
            and os.environ.get("ENFORCE_IAP_JWT", "0") != "1"
            and os.environ.get("ENFORCE_IAP_LOCAL", "0") != "1"
            and os.environ.get("ALLOW_LOCAL_DEV_FALLBACK", "1") == "1"
            and getattr(self, "client_address", None) is not None
        ):
            local_user = os.environ.get("LOCAL_DEV_USER", "mattia@mgandolfi.altostrat.com").strip().lower()
            if local_user in allowed:
                return local_user
        return None

    def _add_security_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("Permissions-Policy", "geolocation=(), microphone=(self), camera=(self)")
        self.send_header("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'self' https://accounts.google.com; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com data:; "
            "img-src 'self' https: data:; "
            "media-src 'self' blob: data:; "
            "connect-src 'self' https://accounts.google.com https://oauth2.googleapis.com; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "object-src 'none'",
        )

    def _add_cors_headers(self) -> None:
        allowed_origins = {
            get_companion_url(),
            get_campaign_library_url(),
            "https://mercadona-ai-companion-905208270932.europe-west1.run.app",
            "https://campaign-library-905208270932.europe-west1.run.app",
            "http://mgandolfi-cloudtop.c.googlers.com:8088",
            "http://localhost:8088",
            "http://localhost:8080",
            "http://127.0.0.1:8080",
        }
        req_origin = self.headers.get("Origin", "").strip().rstrip("/")
        cors_origin = req_origin if req_origin in allowed_origins else get_companion_url()
        self.send_header("Access-Control-Allow-Origin", cors_origin)
        self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def _is_https_request(self) -> bool:
        return bool(
            os.environ.get("K_SERVICE")
            or self.headers.get("X-Forwarded-Proto", "").strip().lower() == "https"
        )

    def _send_json(
        self,
        status: int,
        payload: dict[str, Any],
        set_cookie: str | list[str] | None = None,
    ) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self._add_security_headers()
        self._add_cors_headers()
        if isinstance(set_cookie, list):
            for c_val in set_cookie:
                self.send_header("Set-Cookie", c_val)
        elif set_cookie:
            self.send_header("Set-Cookie", set_cookie)
        self.end_headers()
        self.wfile.write(raw)

    def _send_raw(self, status: int, content_type: str, body_text: str) -> None:
        raw = body_text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self._add_security_headers()
        self._add_cors_headers()
        self.end_headers()
        self.wfile.write(raw)

    def _read_raw_body(self) -> bytes:
        raw_len = self.headers.get("Content-Length", "0") or "0"
        try:
            length = int(raw_len)
        except ValueError as exc:
            raise _PayloadError(400, "Cabecera Content-Length inválida.") from exc
        if length < 0:
            raise _PayloadError(400, "Cabecera Content-Length negativa.")
        if length > MAX_BODY_BYTES:
            raise _PayloadError(413, "El cuerpo de la petición supera el límite permitido (6 MB).")
        if length == 0:
            return b""
        return self.rfile.read(length)

    def _read_json_body(self) -> dict[str, Any]:
        raw_bytes = self._read_raw_body()
        if not raw_bytes:
            return {}
        raw = raw_bytes.decode("utf-8", "ignore")
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._add_security_headers()
        self._add_cors_headers()
        self.end_headers()

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)

        if path == "/api/auth/session":
            user = self._get_authenticated_user()
            iap_email = self._get_iap_email()
            hide_allowlist = bool(
                not user
                and (os.environ.get("K_SERVICE") or os.environ.get("HIDE_ALLOWED_USERS_UNAUTHED") == "1")
            )
            eci_status = (
                get_eci_session_status(user)
                if user
                else {
                    "connected": False,
                    "customer_id": None,
                    "has_refresh_token": False,
                    "warehouse": None,
                    "center_name": None,
                    "postal_code": None,
                    "masked_token": None,
                }
            )
            recipe_prefs = (
                get_user_recipe_preferences(user)
                if user
                else {"liked": [], "disliked": []}
            )
            cookidoo_status = (
                get_cookidoo_session_status(user)
                if user
                else {
                    "connected": False,
                    "live_authenticated": False,
                    "email": None,
                    "masked_email": None,
                    "device_name": None,
                    "auth_mode": None,
                    "planner_url": "https://cookidoo.es/planning/es-ES/my-week",
                    "last_scheduled_week": None,
                }
            )
            self._send_json(
                200,
                {
                    "authenticated": bool(user),
                    "user": user,
                    "iap_email": iap_email,
                    "auth_mode": "iap",
                    "allowed_users": [] if hide_allowlist else get_allowed_users(),
                    "google_client_id": GOOGLE_CLIENT_ID,
                    "service_role": SERVICE_ROLE,
                    "companion_app_url": get_companion_url(),
                    "campaign_library_url": get_campaign_library_url(),
                    "mercadona_session": eci_status,
                    "eci_session": eci_status,
                    "cookidoo_session": cookidoo_status,
                    "recipe_preferences": recipe_prefs,
                },
            )
            return

        if path == "/api/cookidoo/session":
            user = self._get_authenticated_user()
            if not user:
                self._send_json(
                    401,
                    {
                        "code": "AUTHENTICATION_REQUIRED",
                        "error": "Autenticación requerida para consultar la sesión de Cookidoo.",
                    },
                )
                return
            self._send_json(200, get_cookidoo_session_status(user))
            return

        if path == "/api/preferences":
            user = self._get_authenticated_user()
            if not user:
                self._send_json(
                    401,
                    {
                        "code": "AUTHENTICATION_REQUIRED",
                        "error": "Autenticación requerida para consultar preferencias.",
                    },
                )
                return
            self._send_json(200, get_user_recipe_preferences(user))
            return

        if path in ("/api/mercadona/session", "/api/eci/session", "/api/dia/session"):
            user = self._get_authenticated_user()
            if not user:
                self._send_json(
                    401,
                    {
                        "code": "AUTHENTICATION_REQUIRED",
                        "error": "Autenticación requerida para consultar la sesión de Mercadona.",
                    },
                )
                return
            status_fn = get_mercadona_session_status
            self._send_json(200, status_fn(user))
            return

        if path in ("/api/mercadona/categories", "/api/eci/categories", "/api/dia/categories"):
            self._send_json(200, {"categories": fetch_eci_categories()})
            return

        if path in ("/api/mercadona/offers", "/api/eci/offers", "/api/dia/offers"):
            self._send_json(200, {"offers": fetch_eci_offers()})
            return

        if path in ("/api/mercadona/search", "/api/eci/search", "/api/dia/search"):
            query = (qs.get("q") or [""])[0].strip()
            postal_code = (qs.get("postal_code") or ["28001"])[0].strip()
            results = search_eci_live(query, postal_code) if query else []
            self._send_json(200, {"query": query, "postal_code": postal_code, "results": results})
            return

        if path == "/api/campaigns":
            source = (qs.get("source") or [""])[0]
            if source == "internal" or is_campaign_library_role(SERVICE_ROLE):
                campaigns = load_local_campaigns()
            else:
                campaigns = fetch_campaigns_from_remote_or_local()

            status_filter = (qs.get("status") or [""])[0].strip()
            category_filter = (qs.get("category") or [""])[0].strip()
            if status_filter:
                campaigns = [c for c in campaigns if c["status"].lower() == status_filter.lower()]
            if category_filter:
                campaigns = [c for c in campaigns if c["category"].lower() == category_filter.lower()]

            self._send_json(
                200,
                {
                    "service": "campaign-library",
                    "campaigns": campaigns,
                    "active_campaigns": [c for c in campaigns if c["status"] == "Activa"],
                    "categories": VALID_CATEGORIES,
                    "statuses": VALID_STATUSES,
                    "profiles": PROFILES_METADATA,
                    "companion_app_url": get_companion_url(),
                    "campaign_library_url": get_campaign_library_url(),
                },
            )
            return

        if path == "/api/catalog":
            pc = (qs.get("postal_code") or ["28001"])[0]
            pc_info = resolve_postal_code(pc)
            cat_dict = load_snapshot_products()
            products = list(cat_dict.values())
            recipes = load_cookidoo_catalog()
            self._send_json(
                200,
                {
                    "postal_code": pc_info["postal_code"],
                    "warehouse": pc_info["warehouse"],
                    "center_name": pc_info.get("center_name", pc_info["warehouse"]),
                    "delivery_available": pc_info.get("delivery_available", True),
                    "source": pc_info.get("source", "snapshot"),
                    "total_products": len(products),
                    "products": products,
                    "recipes": recipes,
                },
            )
            return

        if path == "/api/parse-constraints":
            prompt = (qs.get("q") or [""])[0]
            c = parse_constraints(prompt)
            self._send_json(200, {"constraints": c, "pills": format_constraint_pills(c)})
            return

        if path == "/api/whatsapp/webhook":
            status_code, body_text = verify_whatsapp_webhook_get(qs)
            self._send_raw(status_code, "text/plain", body_text)
            return

        if path == "/api/whatsapp/state":
            user = self._get_authenticated_user()
            if not user:
                self._send_json(
                    401,
                    {
                        "code": "AUTHENTICATION_REQUIRED",
                        "error": "Autenticación requerida para consultar el estado de WhatsApp.",
                    },
                )
                return
            st = get_whatsapp_state(base_url=get_companion_url())
            self._send_json(200, st)
            return

        if path == "/api/fridge-vision/presets":
            self._send_json(200, {"presets": FRIDGE_VISION_PRESETS})
            return

        if path == "/api/campaigns/analytics":
            self._send_json(200, get_demand_sensing_analytics())
            return

        # Serve static files from public/
        default_html = "marketing.html" if is_campaign_library_role(SERVICE_ROLE) else "index.html"
        rel = path.lstrip("/") or default_html
        if rel == "marketing":
            rel = "marketing.html"
        elif rel == "favicon.svg":
            rel = "favicon.ico"
        elif rel in ("sources", "catalog", "agent"):
            rel = "index.html"

        public_root = PUBLIC_DIR.resolve()
        file_path = (public_root / rel).resolve()
        if not file_path.is_relative_to(public_root) or not file_path.is_file():
            file_path = public_root / default_html

        if not file_path.is_file():
            self.send_error(404, "Not Found")
            return

        ctype, _ = mimetypes.guess_type(str(file_path))
        if file_path.suffix == ".svg":
            ctype = "image/svg+xml"
        elif file_path.suffix == ".webp":
            ctype = "image/webp"
        elif file_path.suffix == ".ico":
            ctype = "image/x-icon"
        elif file_path.suffix == ".png":
            ctype = "image/png"
        elif file_path.suffix == ".mp4":
            ctype = "video/mp4"
        data = file_path.read_bytes()
        total_len = len(data)
        range_hdr = self.headers.get("Range", "").strip()
        if range_hdr.startswith("bytes=") and total_len > 0:
            try:
                spec = range_hdr[6:].split(",")[0].strip()
                s_str, e_str = spec.split("-", 1)
                start = int(s_str) if s_str else max(0, total_len - int(e_str))
                end = int(e_str) if (s_str and e_str) else (total_len - 1)
                start = max(0, min(start, total_len - 1))
                end = max(start, min(end, total_len - 1))
                chunk = data[start : end + 1]
                self.send_response(206)
                self.send_header("Content-Type", ctype or "application/octet-stream")
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Range", f"bytes {start}-{end}/{total_len}")
                self.send_header("Content-Length", str(len(chunk)))
                self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
                self._add_security_headers()
                self._add_cors_headers()
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(chunk)
                return
            except Exception:
                pass
        self.send_response(200)
        self.send_header("Content-Type", ctype or "application/octet-stream")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(total_len))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self._add_security_headers()
        self._add_cors_headers()
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        # Real external Webhook endpoint for Meta WhatsApp Cloud API & Twilio WhatsApp Sandbox
        if path == "/api/whatsapp/webhook":
            try:
                raw_bytes = self._read_raw_body()
            except _PayloadError as err:
                self._send_json(err.status, {"error": err.message})
                return
            content_type_hdr = self.headers.get("Content-Type", "application/json")
            sig_hdr = self.headers.get("X-Hub-Signature-256", "")
            status_code, resp_ctype, resp_bytes = handle_whatsapp_webhook_post(
                raw_body=raw_bytes,
                content_type=content_type_hdr,
                signature_header=sig_hdr,
            )
            self.send_response(status_code)
            self.send_header("Content-Type", resp_ctype)
            self.send_header("Content-Length", str(len(resp_bytes)))
            self.send_header("Cache-Control", "no-store")
            self._add_security_headers()
            self._add_cors_headers()
            self.end_headers()
            self.wfile.write(resp_bytes)
            return

        try:
            body = self._read_json_body()
        except _PayloadError as err:
            self._send_json(err.status, {"error": err.message})
            return

        if path == "/api/auth/login":
            id_token = str(body.get("credential") or "").strip()
            email = ""
            if id_token:
                verified = verify_google_id_token(id_token)
                if not verified:
                    self._send_json(
                        401,
                        {
                            "code": "INVALID_GOOGLE_TOKEN",
                            "error": "Token de Google Identity inválido o no verificado.",
                        },
                    )
                    return
                email = verified
            else:
                iap_email = self._get_iap_email()
                if not iap_email:
                    self._send_json(
                        401,
                        {
                            "code": "IAP_REQUIRED",
                            "error": (
                                "La autenticación directa sin verificar está deshabilitada. "
                                "Inicia sesión con tu cuenta de Google a través de Cloud Run Identity-Aware Proxy (IAP)."
                            ),
                        },
                    )
                    return
                email = iap_email

            allowed = get_allowed_users()
            if email not in allowed:
                self._send_json(
                    403,
                    {
                        "code": "USER_NOT_ALLOWED",
                        "error": (
                            f"Acceso restringido por Identity-Aware Proxy: la cuenta '{email}' no está en la allowlist "
                            "de usuarios autorizados."
                        ),
                    },
                )
                return

            signed = urllib.parse.quote(sign_session_email(email))
            secure_attr = "; Secure" if self._is_https_request() else ""
            cookies = [
                f"mercadona_session={signed}; Path=/; HttpOnly; SameSite=Lax; Max-Age={SESSION_TTL_SECONDS}{secure_attr}",
                f"eci_session={signed}; Path=/; HttpOnly; SameSite=Lax; Max-Age={SESSION_TTL_SECONDS}{secure_attr}",
                f"dia_session={signed}; Path=/; HttpOnly; SameSite=Lax; Max-Age={SESSION_TTL_SECONDS}{secure_attr}",
            ]
            self._send_json(200, {"authenticated": True, "user": email}, set_cookie=cookies)
            return

        if path == "/api/auth/logout":
            secure_attr = "; Secure" if self._is_https_request() else ""
            cookies = [
                f"mercadona_session=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0{secure_attr}",
                f"eci_session=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0{secure_attr}",
                f"dia_session=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0{secure_attr}",
            ]
            self._send_json(200, {"authenticated": False, "user": None}, set_cookie=cookies)
            return

        # Internal microservice-to-microservice campaign synchronization endpoint
        if path == "/api/campaigns/sync":
            if not (self._is_internal_service_sync() or self._get_authenticated_user()):
                self._send_json(401, {"error": "No autorizado para sincronización interna."})
                return
            incoming = body.get("campaigns")
            if isinstance(incoming, list) and len(incoming) > 0:
                saved = save_local_campaigns(incoming)
                self._send_json(200, {"ok": True, "count": len(saved)})
            else:
                self._send_json(400, {"error": "Lista de campañas inválida."})
            return

        # Require real Google Cloud IAP / verified Google authentication for BOTH main app AND Campaign Library
        user = self._get_authenticated_user()
        if not user:
            iap_raw = self._get_iap_email()
            self._send_json(
                403 if iap_raw else 401,
                {
                    "code": "USER_NOT_ALLOWED" if iap_raw else "AUTHENTICATION_REQUIRED",
                    "error": (
                        f"La cuenta '{iap_raw}' no está autorizada en la allowlist de Identity-Aware Proxy."
                        if iap_raw
                        else "Autenticación requerida mediante Google Cloud Identity-Aware Proxy (IAP)."
                    ),
                },
            )
            return

        # Campaign Library endpoints
        if path == "/api/campaigns/generate":
            brief = str(body.get("brief") or body.get("prompt") or "").strip()
            category = body.get("category")
            initial_status = str(body.get("status") or "Activa")
            try:
                created = generate_campaign_from_brief(
                    brief=brief,
                    category_hint=str(category) if category else None,
                    initial_status=initial_status,
                )
                all_campaigns = load_local_campaigns()
                self._send_json(200, {"campaign": created, "campaigns": all_campaigns})
            except Exception as exc:
                self._send_json(422, {"error": str(exc)})
            return

        if path == "/api/campaigns/status":
            cid = str(body.get("id") or body.get("campaign_id") or "").strip()
            new_status = str(body.get("status") or "").strip()
            try:
                updated = update_campaign_record(cid, {"status": new_status})
                all_campaigns = load_local_campaigns()
                self._send_json(200, {"campaign": updated, "campaigns": all_campaigns})
            except Exception as exc:
                self._send_json(422, {"error": str(exc)})
            return

        if path == "/api/campaigns/update":
            cid = str(body.get("id") or body.get("campaign_id") or "").strip()
            updates = body.get("updates") if isinstance(body.get("updates"), dict) else body
            try:
                updated = update_campaign_record(cid, updates)
                all_campaigns = load_local_campaigns()
                self._send_json(200, {"campaign": updated, "campaigns": all_campaigns})
            except Exception as exc:
                self._send_json(422, {"error": str(exc)})
            return

        if path == "/api/postal-code":
            pc = str(body.get("postal_code") or "28001").strip()
            info = resolve_postal_code(pc)
            if info.get("delivery_available"):
                msg = (
                    f"Código postal {info['postal_code']} verificado con cobertura de reparto a domicilio "
                    f"({info.get('center_name') or info['warehouse']})."
                )
            else:
                msg = (
                    f"El código postal {info['postal_code']} no tiene reparto a domicilio directo en Mercadona. "
                    f"Mostrando surtido de referencia ({info.get('center_name') or info['warehouse']})."
                )
            self._send_json(
                200,
                {
                    "postal_code": info["postal_code"],
                    "warehouse": info["warehouse"],
                    "center_name": info.get("center_name", info["warehouse"]),
                    "delivery_available": info.get("delivery_available", True),
                    "source": info["source"],
                    "message": msg,
                },
            )
            return

        if path in ("/api/mercadona/verify-stock", "/api/eci/verify-stock", "/api/dia/verify-stock"):
            postal_code = str(body.get("postal_code") or "28001").strip()
            product_ids = body.get("product_ids") or []
            if not isinstance(product_ids, list) or not product_ids:
                product_ids = []
            clean_ids = [str(pid).strip() for pid in product_ids if str(pid).strip()][:35]
            pc_info = resolve_postal_code(postal_code)
            wh = pc_info["warehouse"]
            live_map = (
                fetch_eci_products_batch(clean_ids, warehouse=wh, postal_code=pc_info["postal_code"])
                if clean_ids
                else {}
            )
            snapshot = load_snapshot_products()
            results: list[dict[str, Any]] = []
            for pid in clean_ids:
                prod = live_map.get(pid) or snapshot.get(pid)
                if not prod:
                    continue
                in_stock = prod.get("available", True) is not False and prod.get("in_stock", True) is not False
                replacement = None
                if not in_stock:
                    replacement = search_eci_replacement(
                        prod.get("name", ""), warehouse=wh, postal_code=pc_info["postal_code"]
                    )
                results.append(
                    {
                        "id": pid,
                        "name": prod.get("name"),
                        "price": prod.get("unit_price") or prod.get("price"),
                        "in_stock": in_stock,
                        "source": prod.get("source", "snapshot"),
                        "warehouse": wh,
                        "replacement": replacement,
                    }
                )
            self._send_json(
                200,
                {
                    "postal_code": pc_info["postal_code"],
                    "warehouse": pc_info["warehouse"],
                    "center_name": pc_info.get("center_name", pc_info["warehouse"]),
                    "delivery_available": pc_info.get("delivery_available", True),
                    "verified_count": len(results),
                    "items": results,
                },
            )
            return

        if path == "/api/preferences":
            action = str(body.get("action") or "").strip().lower()
            if action == "clear":
                prefs = clear_user_recipe_preferences(user or "default")
                self._send_json(200, prefs)
                return
            recipe_id = str(body.get("recipe_id") or body.get("recipeId") or "").strip()
            vote = str(body.get("vote") or "").strip()
            if recipe_id and vote:
                prefs = record_recipe_vote(user or "default", recipe_id, vote)
                self._send_json(200, prefs)
                return
            liked_in = (
                body.get("liked")
                if isinstance(body.get("liked"), list)
                else (body.get("liked_recipe_ids") or body.get("likedRecipeIds"))
            )
            disliked_in = (
                body.get("disliked")
                if isinstance(body.get("disliked"), list)
                else (body.get("disliked_recipe_ids") or body.get("dislikedRecipeIds"))
            )
            prefs = save_user_recipe_preferences(
                user_email=user or "default",
                liked_recipe_ids=liked_in if isinstance(liked_in, list) else None,
                disliked_recipe_ids=disliked_in if isinstance(disliked_in, list) else None,
                merge=bool(body.get("merge", False)),
            )
            self._send_json(200, prefs)
            return

        if path == "/api/plan":
            prompt = str(body.get("message") or body.get("prompt") or "").strip()
            postal_code = str(body.get("postalCode") or body.get("postal_code") or "28001").strip()
            current_plan = body.get("currentPlan")
            variety_seed = str(body.get("varietySeed") or "1")
            liked_ids = body.get("likedRecipeIds") if "likedRecipeIds" in body else body.get("liked_recipe_ids")
            disliked_ids = body.get("dislikedRecipeIds") if "dislikedRecipeIds" in body else body.get("disliked_recipe_ids")
            if not prompt:
                self._send_json(400, {"error": "Escribe una petición para planificar tu menú semanal."})
                return
            is_valid, scope_err = validate_meal_planning_prompt(prompt)
            if not is_valid:
                self._send_json(422, {"code": "OUT_OF_SCOPE_PROMPT", "error": scope_err})
                return
            try:
                plan = build_weekly_plan(
                    prompt=prompt,
                    postal_code=postal_code,
                    current_plan=current_plan,
                    variety_seed=variety_seed,
                    liked_recipe_ids=liked_ids if isinstance(liked_ids, list) else None,
                    disliked_recipe_ids=disliked_ids if isinstance(disliked_ids, list) else None,
                    user_email=user or "default",
                )
                try:
                    sync_active_plan_to_whatsapp(plan, postal_code=postal_code)
                except Exception:
                    pass
                self._send_json(200, plan)
            except Exception as exc:
                self._send_json(422, {"error": str(exc)})
            return

        if path == "/api/recipe-swap":
            current_meals = body.get("currentMeals") or []
            target_id = str(body.get("targetRecipeId") or "")
            constraints = body.get("constraints") or {}
            postal_code = str(body.get("postalCode") or "28001")
            try:
                rotation = int(body.get("rotation") or 1)
            except (TypeError, ValueError):
                rotation = 1
            liked_ids = body.get("likedRecipeIds") if "likedRecipeIds" in body else body.get("liked_recipe_ids")
            disliked_ids = body.get("dislikedRecipeIds") if "dislikedRecipeIds" in body else body.get("disliked_recipe_ids")
            try:
                res = swap_single_recipe(
                    current_meals=current_meals,
                    target_recipe_id=target_id,
                    constraints=constraints,
                    postal_code=postal_code,
                    rotation=rotation,
                    liked_recipe_ids=liked_ids if isinstance(liked_ids, list) else None,
                    disliked_recipe_ids=disliked_ids if isinstance(disliked_ids, list) else None,
                    user_email=user or "default",
                )
                try:
                    sync_active_plan_to_whatsapp(res, postal_code=postal_code)
                except Exception:
                    pass
                self._send_json(200, res)
            except Exception as exc:
                self._send_json(422, {"error": str(exc)})
            return

        if path == "/api/basket/recalculate":
            current_plan = body.get("currentPlan") or body.get("plan") or {}
            postal_code = str(body.get("postalCode") or body.get("postal_code") or "28001").strip()
            basket_tier = body.get("basketTier") or body.get("basket_tier")
            day_servings = body.get("dayServings") if isinstance(body.get("dayServings"), dict) else body.get("day_servings")
            custom_cuts = body.get("customCounterCuts") if isinstance(body.get("customCounterCuts"), dict) else body.get("custom_counter_cuts")
            include_sommelier = body.get("includeSommelierItem") if "includeSommelierItem" in body else body.get("include_sommelier_item")
            try:
                updated_plan = recalculate_plan_basket(
                    plan=current_plan,
                    basket_tier=str(basket_tier).strip().lower() if basket_tier else None,
                    day_servings=day_servings if isinstance(day_servings, dict) else None,
                    custom_counter_cuts=custom_cuts if isinstance(custom_cuts, dict) else None,
                    include_sommelier_item=bool(include_sommelier) if include_sommelier is not None else None,
                    postal_code=postal_code,
                )
                try:
                    sync_active_plan_to_whatsapp(updated_plan, postal_code=postal_code)
                except Exception:
                    pass
                self._send_json(200, updated_plan)
            except Exception as exc:
                self._send_json(422, {"error": str(exc)})
            return

        if path == "/api/fridge-vision":
            image_base64 = body.get("imageBase64") or body.get("image_base64")
            mime_type = str(body.get("mimeType") or body.get("mime_type") or "image/jpeg")
            preset_id = body.get("presetId") or body.get("preset_id")
            current_prompt = str(body.get("currentPrompt") or body.get("current_prompt") or "")
            postal_code = str(body.get("postalCode") or body.get("postal_code") or "28001").strip()
            current_plan = body.get("currentPlan") if isinstance(body.get("currentPlan"), dict) else None
            try:
                res = analyze_fridge_vision(
                    image_base64=str(image_base64) if image_base64 else None,
                    mime_type=mime_type,
                    preset_id=str(preset_id) if preset_id else None,
                    current_prompt=current_prompt,
                    postal_code=postal_code,
                    current_plan=current_plan,
                    user_email=user or "default",
                )
                if isinstance(res.get("plan"), dict):
                    try:
                        sync_active_plan_to_whatsapp(res["plan"], postal_code=postal_code)
                    except Exception:
                        pass
                self._send_json(200, res)
            except Exception as exc:
                self._send_json(422, {"error": str(exc)})
            return

        if path == "/api/whatsapp/send":
            text = str(body.get("text") or body.get("message") or "").strip()
            current_plan = body.get("currentPlan") if isinstance(body.get("currentPlan"), dict) else None
            postal_code = str(body.get("postalCode") or body.get("postal_code") or "28001").strip()
            msg_type = str(body.get("type") or "text").strip()
            image_b64 = body.get("imageBase64") or body.get("image_base64")
            if not text and not image_b64:
                self._send_json(400, {"error": "Escribe un mensaje o adjunta una foto para el asistente de WhatsApp."})
                return
            try:
                res = process_whatsapp_user_message(
                    user_text=text,
                    sender=user or "cliente_whatsapp",
                    message_type=msg_type,
                    image_base64=str(image_b64) if image_b64 else None,
                    postal_code=postal_code,
                    current_plan_override=current_plan,
                )
                st = get_whatsapp_state(base_url=get_companion_url())
                res["webhook_url"] = st["webhook_url"]
                res["webhook_stats"] = st["webhook_stats"]
                self._send_json(200, res)
            except Exception as exc:
                self._send_json(422, {"error": str(exc)})
            return

        if path == "/api/whatsapp/config":
            st = update_whatsapp_config(
                verify_token=body.get("verify_token") or body.get("verifyToken"),
                phone_number_id=body.get("phone_number_id") or body.get("phoneNumberId"),
                access_token=body.get("access_token") or body.get("accessToken"),
                recipient_phone=body.get("recipient_phone") or body.get("recipientPhone"),
                reset_chat=bool(body.get("reset_chat") or body.get("resetChat")),
            )
            st["webhook_url"] = f"{get_companion_url()}/api/whatsapp/webhook"
            self._send_json(200, st)
            return

        if path == "/api/cookidoo/session":
            action = str(body.get("action") or "").strip().lower()
            if action == "disconnect":
                self._send_json(200, clear_cookidoo_session(user or "default"))
                return
            cookidoo_email = str(body.get("cookidoo_email") or body.get("email") or "").strip()
            cookidoo_password = str(body.get("cookidoo_password") or body.get("password") or "").strip() or None
            demo_mode = bool(body.get("demo_mode") or body.get("demoMode"))
            try:
                res = verify_and_save_cookidoo_session(
                    email=cookidoo_email,
                    password=cookidoo_password,
                    user_email=user or "default",
                    demo_mode=demo_mode,
                )
                self._send_json(200, res)
            except ValueError as exc:
                self._send_json(422, {"connected": False, "error": str(exc)})
            return

        if path == "/api/cookidoo/schedule-week":
            meals = body.get("meals") or []
            cookidoo_email = str(body.get("cookidoo_email") or "").strip() or None
            cookidoo_password = str(body.get("cookidoo_password") or "").strip() or None
            week_mode = str(body.get("week_mode") or body.get("weekMode") or "current").strip()
            try:
                res = schedule_weekly_plan_to_cookidoo(
                    meals=meals if isinstance(meals, list) else [],
                    email=cookidoo_email,
                    password=cookidoo_password,
                    week_mode=week_mode,
                    user_email=user or "default",
                )
                self._send_json(200, res)
            except ValueError as exc:
                self._send_json(422, {"error": str(exc)})
            return

        if path == "/api/cookidoo/send":
            recipe_id = str(body.get("recipe_id") or "").strip()
            cookidoo_email = str(body.get("cookidoo_email") or "").strip() or None
            cookidoo_password = str(body.get("cookidoo_password") or "").strip() or None
            day_name = str(body.get("day") or body.get("day_name") or "").strip() or None
            week_mode = str(body.get("week_mode") or body.get("weekMode") or "current").strip()
            try:
                res = send_recipe_to_thermomix(
                    recipe_id=recipe_id,
                    email=cookidoo_email,
                    password=cookidoo_password,
                    day_name=day_name,
                    week_mode=week_mode,
                    user_email=user or "default",
                )
                self._send_json(200, res)
            except ValueError as exc:
                self._send_json(422, {"error": str(exc)})
            return

        if path in ("/api/mercadona/session", "/api/eci/session", "/api/dia/session"):
            action = str(body.get("action") or "").strip().lower()
            if action == "disconnect":
                res = clear_mercadona_session(user or "default")
                self._send_json(200, res)
                return
            auth_input = str(body.get("auth_input") or body.get("mercadona_auth") or body.get("eci_auth") or body.get("dia_auth") or "").strip()
            postal_code = str(body.get("postal_code") or "28016").strip()
            try:
                res = verify_and_save_mercadona_session(
                    raw_input=auth_input,
                    postal_code=postal_code,
                    user_email=user or "default",
                )
                self._send_json(200, res)
            except Exception as exc:
                self._send_json(422, {"connected": False, "error": str(exc)})
            return

        if path in ("/api/mercadona/cart", "/api/eci/cart", "/api/dia/cart"):
            basket = body.get("basket") or []
            postal_code = str(body.get("postal_code") or "28016")
            mercadona_auth = str(body.get("mercadona_auth") or body.get("eci_auth") or body.get("dia_auth") or "").strip() or None
            mode = str(body.get("mode") or "add").strip().lower()
            res = prepare_mercadona_oneclick_cart(
                basket=basket,
                postal_code=postal_code,
                user_email=user or "default",
                raw_auth_input=mercadona_auth,
                mode=mode if mode in ("add", "replace") else "add",
            )
            self._send_json(200, res)
            return

        self._send_json(404, {"error": "Endpoint no encontrado"})


def run_server() -> None:
    port = int(os.environ.get("PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), CompanionRequestHandler)
    print(f"Mercadona Service ({SERVICE_ROLE}) listening on http://0.0.0.0:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run_server()

"""HTTP Server for Mercadona AI Companion & Campaign Library Microservices.

Supports both microservices:
  - mercadona-ai-companion (main customer planner app, SERVICE_ROLE=companion)
  - campaign-library (Mercadona Marketing campaign microservice, SERVICE_ROLE=campaign-library)

Enforces Google Identity allowlist for:
  - matgand@gmail.com
  - mgandolfi@google.com
  - andrea.anaut@gmail.com
"""

from __future__ import annotations

import hashlib
import hmac
import http.cookies
import json
import mimetypes
import os
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from campaign_service import (
    PROFILES_METADATA,
    VALID_CATEGORIES,
    VALID_STATUSES,
    fetch_campaigns_from_remote_or_local,
    generate_campaign_from_brief,
    load_local_campaigns,
    save_local_campaigns,
    update_campaign_record,
)
from cookidoo_service import load_cookidoo_catalog, send_recipe_to_thermomix
from gemini_planner import (
    build_weekly_plan,
    format_constraint_pills,
    parse_constraints,
    swap_single_recipe,
    validate_meal_planning_prompt,
)
from mercadona_service import (
    load_snapshot_products,
    prepare_mercadona_oneclick_cart,
    resolve_postal_code,
)

PUBLIC_DIR = Path(__file__).resolve().parent / "public"
SESSION_SECRET = os.environ.get("SESSION_SECRET", "mercadona-companion-secret-key-2026")
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
SERVICE_ROLE = os.environ.get("SERVICE_ROLE", "companion").strip().lower()

DEFAULT_COMPANION_URL = "https://mercadona-ai-companion-905208270932.europe-west1.run.app"
DEFAULT_CAMPAIGN_LIBRARY_URL = "https://campaign-library-905208270932.europe-west1.run.app"

DEFAULT_ALLOWED_USERS = [
    "matgand@gmail.com",
    "mgandolfi@google.com",
    "andrea.anaut@gmail.com",
    "mattia@mgandolfi.altostrat.com",
]


def get_allowed_users() -> list[str]:
    env_val = os.environ.get("ALLOWED_USERS", "").strip()
    if env_val:
        return [u.strip().lower() for u in env_val.split(",") if u.strip()]
    return DEFAULT_ALLOWED_USERS


def get_companion_url() -> str:
    return os.environ.get("COMPANION_APP_URL", DEFAULT_COMPANION_URL).strip().rstrip("/")


def get_campaign_library_url() -> str:
    return os.environ.get("CAMPAIGN_LIBRARY_URL", DEFAULT_CAMPAIGN_LIBRARY_URL).strip().rstrip("/")


def sign_session_email(email: str) -> str:
    clean = email.strip().lower()
    sig = hmac.new(SESSION_SECRET.encode("utf-8"), clean.encode("utf-8"), hashlib.sha256).hexdigest()[:32]
    return f"{clean}|{sig}"


def verify_session_token(token: str | None) -> str | None:
    if not token or "|" not in token:
        return None
    email, sig = token.rsplit("|", 1)
    expected = hmac.new(SESSION_SECRET.encode("utf-8"), email.encode("utf-8"), hashlib.sha256).hexdigest()[:32]
    if hmac.compare_digest(sig, expected) and email in get_allowed_users():
        return email
    return None


def verify_google_id_token(id_token: str) -> str | None:
    """Verifies a Google Identity Services JWT against Google's tokeninfo endpoint."""
    url = f"https://oauth2.googleapis.com/tokeninfo?id_token={urllib.parse.quote(id_token)}"
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
        iap_email = self.headers.get("X-Goog-Authenticated-User-Email", "").strip()
        if iap_email:
            return iap_email.split(":")[-1].strip().lower()
        return None

    def _is_internal_service_sync(self) -> bool:
        expected = hashlib.sha256(f"internal-sync:{SESSION_SECRET}".encode("utf-8")).hexdigest()[:32]
        provided = self.headers.get("X-Internal-Sync-Token", "").strip()
        return bool(provided and hmac.compare_digest(provided, expected))

    def _get_authenticated_user(self) -> str | None:
        allowed = get_allowed_users()

        # 1. Google Cloud Identity-Aware Proxy (IAP) verified header (Primary on Cloud Run)
        clean_iap = self._get_iap_email()
        if clean_iap:
            return clean_iap if clean_iap in allowed else None

        # 2. Cryptographically verified Google OAuth2 Bearer ID Token
        auth_hdr = self.headers.get("Authorization", "").strip()
        if auth_hdr.lower().startswith("bearer "):
            token = auth_hdr[7:].strip()
            verified_email = verify_google_id_token(token)
            if verified_email and verified_email in allowed:
                return verified_email

        # 3. Signed session cookie (issued only after verified Google ID token or IAP authentication)
        cookie_hdr = self.headers.get("Cookie", "")
        if cookie_hdr:
            jar = http.cookies.SimpleCookie()
            jar.load(cookie_hdr)
            if "mercadona_session" in jar:
                val = urllib.parse.unquote(jar["mercadona_session"].value)
                user = verify_session_token(val)
                if user:
                    return user
        return None

    def _add_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def _send_json(self, status: int, payload: dict[str, Any], set_cookie: str | None = None) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self._add_cors_headers()
        if set_cookie:
            self.send_header("Set-Cookie", set_cookie)
        self.end_headers()
        self.wfile.write(raw)

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(min(length, 524288)).decode("utf-8", "ignore")
        try:
            return json.loads(raw)
        except Exception:
            return {}

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._add_cors_headers()
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)

        if path == "/api/auth/session":
            user = self._get_authenticated_user()
            iap_email = self._get_iap_email()
            self._send_json(
                200,
                {
                    "authenticated": bool(user),
                    "user": user,
                    "iap_email": iap_email,
                    "auth_mode": "iap",
                    "allowed_users": get_allowed_users(),
                    "google_client_id": GOOGLE_CLIENT_ID,
                    "service_role": SERVICE_ROLE,
                    "companion_app_url": get_companion_url(),
                    "campaign_library_url": get_campaign_library_url(),
                },
            )
            return

        if path == "/api/campaigns":
            source = (qs.get("source") or [""])[0]
            if source == "internal" or SERVICE_ROLE == "campaign-library":
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
            pc = (qs.get("postal_code") or ["28016"])[0]
            pc_info = resolve_postal_code(pc)
            products = list(load_snapshot_products().values())
            recipes = load_cookidoo_catalog()
            self._send_json(
                200,
                {
                    "postal_code": pc_info["postal_code"],
                    "warehouse": pc_info["warehouse"],
                    "source": pc_info["source"],
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

        # Serve static files from public/
        default_html = "marketing.html" if SERVICE_ROLE == "campaign-library" else "index.html"
        rel = path.lstrip("/") or default_html
        if rel == "marketing":
            rel = "marketing.html"
        elif rel == "favicon.svg":
            rel = "favicon.ico"
        elif rel in ("sources", "catalog", "agent"):
            rel = "index.html"

        file_path = (PUBLIC_DIR / rel).resolve()
        if not str(file_path).startswith(str(PUBLIC_DIR)) or not file_path.is_file():
            file_path = PUBLIC_DIR / default_html

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
        data = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self._add_cors_headers()
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        body = self._read_json_body()

        if path == "/api/auth/login":
            # Only allow cryptographically verified Google Identity JWT or Cloud Run IAP header.
            # Unverified plain-text email selection is strictly forbidden.
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
                            f"de usuarios autorizados ({', '.join(allowed)})."
                        ),
                    },
                )
                return

            signed = urllib.parse.quote(sign_session_email(email))
            cookie = f"mercadona_session={signed}; Path=/; HttpOnly; SameSite=Lax; Max-Age=604800"
            self._send_json(200, {"authenticated": True, "user": email}, set_cookie=cookie)
            return

        if path == "/api/auth/logout":
            cookie = "mercadona_session=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0"
            self._send_json(200, {"authenticated": False, "user": None}, set_cookie=cookie)
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

        # Campaign Library endpoints (protected by the same IAP + 4-user allowlist)
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
            pc = str(body.get("postal_code") or "28016").strip()
            info = resolve_postal_code(pc)
            self._send_json(
                200,
                {
                    "postal_code": info["postal_code"],
                    "warehouse": info["warehouse"],
                    "source": info["source"],
                    "message": f"Código postal actualizado a {info['postal_code']} (Almacén Mercadona: {info['warehouse']}).",
                },
            )
            return

        if path == "/api/plan":
            prompt = str(body.get("message") or body.get("prompt") or "").strip()
            postal_code = str(body.get("postalCode") or body.get("postal_code") or "28016").strip()
            current_plan = body.get("currentPlan")
            variety_seed = str(body.get("varietySeed") or "1")
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
                )
                self._send_json(200, plan)
            except Exception as exc:
                self._send_json(422, {"error": str(exc)})
            return

        if path == "/api/recipe-swap":
            current_meals = body.get("currentMeals") or []
            target_id = str(body.get("targetRecipeId") or "")
            constraints = body.get("constraints") or {}
            postal_code = str(body.get("postalCode") or "28016")
            rotation = int(body.get("rotation") or 1)
            try:
                res = swap_single_recipe(
                    current_meals=current_meals,
                    target_recipe_id=target_id,
                    constraints=constraints,
                    postal_code=postal_code,
                    rotation=rotation,
                )
                self._send_json(200, res)
            except Exception as exc:
                self._send_json(422, {"error": str(exc)})
            return

        if path == "/api/cookidoo/send":
            recipe_id = str(body.get("recipe_id") or "").strip()
            cookidoo_email = str(body.get("cookidoo_email") or "").strip() or None
            cookidoo_password = str(body.get("cookidoo_password") or "").strip() or None
            res = send_recipe_to_thermomix(recipe_id, cookidoo_email, cookidoo_password)
            self._send_json(200, res)
            return

        if path == "/api/mercadona/cart":
            basket = body.get("basket") or []
            postal_code = str(body.get("postal_code") or "28016")
            res = prepare_mercadona_oneclick_cart(basket, postal_code)
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

"""HTTP Server for Mercadona AI Companion (Gemini 3.8 Flash × Cookidoo × Mercadona).

Runs out-of-the-box with Python 3 standard library locally and in Google Cloud Run.
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

from cookidoo_service import load_cookidoo_catalog, send_recipe_to_thermomix
from gemini_planner import build_weekly_plan, format_constraint_pills, parse_constraints, swap_single_recipe
from mercadona_service import (
    get_catalog_for_postal_code,
    load_snapshot_products,
    prepare_mercadona_oneclick_cart,
    resolve_postal_code,
)

PUBLIC_DIR = Path(__file__).resolve().parent / "public"
SESSION_SECRET = os.environ.get("SESSION_SECRET", "mercadona-companion-secret-key-2026")
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")

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
    server_version = "MercadonaAICompanion/1.0"

    def _get_authenticated_user(self) -> str | None:
        # 1. Check Google Cloud IAP / Cloud Run authenticated header
        iap_email = self.headers.get("X-Goog-Authenticated-User-Email", "")
        if iap_email:
            # Format is usually "accounts.google.com:user@example.com"
            clean_iap = iap_email.split(":")[-1].strip().lower()
            if clean_iap in get_allowed_users():
                return clean_iap

        # 2. Check signed session cookie
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

    def _send_json(self, status: int, payload: dict[str, Any], set_cookie: str | None = None) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        if set_cookie:
            self.send_header("Set-Cookie", set_cookie)
        self.end_headers()
        self.wfile.write(raw)

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(min(length, 262144)).decode("utf-8", "ignore")
        try:
            return json.loads(raw)
        except Exception:
            return {}

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/auth/session":
            user = self._get_authenticated_user()
            self._send_json(
                200,
                {
                    "authenticated": bool(user),
                    "user": user,
                    "allowed_users": get_allowed_users(),
                    "google_client_id": GOOGLE_CLIENT_ID,
                },
            )
            return

        if path == "/api/catalog":
            qs = urllib.parse.parse_qs(parsed.query)
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
            qs = urllib.parse.parse_qs(parsed.query)
            prompt = (qs.get("q") or [""])[0]
            c = parse_constraints(prompt)
            self._send_json(200, {"constraints": c, "pills": format_constraint_pills(c)})
            return

        # Serve static files from public/
        rel = path.lstrip("/") or "index.html"
        if rel in ("sources", "catalog", "marketing", "agent"):
            rel = "index.html"
        file_path = (PUBLIC_DIR / rel).resolve()
        if not str(file_path).startswith(str(PUBLIC_DIR)) or not file_path.is_file():
            file_path = PUBLIC_DIR / "index.html"

        if not file_path.is_file():
            self.send_error(404, "Not Found")
            return

        ctype, _ = mimetypes.guess_type(str(file_path))
        if file_path.suffix == ".svg":
            ctype = "image/svg+xml"
        elif file_path.suffix == ".webp":
            ctype = "image/webp"
        data = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        body = self._read_json_body()

        if path == "/api/auth/login":
            id_token = str(body.get("credential") or "").strip()
            email = ""
            if id_token:
                verified = verify_google_id_token(id_token)
                if not verified:
                    self._send_json(401, {"error": "No se pudo verificar el token de Google Identity."})
                    return
                email = verified
            else:
                email = str(body.get("email") or "").strip().lower()

            allowed = get_allowed_users()
            if not email or email not in allowed:
                self._send_json(
                    403,
                    {
                        "code": "USER_NOT_ALLOWED",
                        "error": (
                            f"Acceso restringido: la cuenta '{email or 'desconocida'}' no está en la lista de "
                            f"usuarios autorizados ({', '.join(allowed)})."
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

        # Require authentication for planner, postal code, Cookidoo, and Mercadona cart operations
        user = self._get_authenticated_user()
        if not user:
            self._send_json(
                401,
                {
                    "code": "AUTHENTICATION_REQUIRED",
                    "error": "Inicia sesión con una cuenta de Google autorizada para utilizar el planificador.",
                },
            )
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
    print(f"Mercadona AI Companion listening on http://0.0.0.0:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run_server()

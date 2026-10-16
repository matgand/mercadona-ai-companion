"""Cookidoo integration service using pure-stdlib OAuth2+PKCE (compatible with Cloud Run base image) and official Cookidoo JSON-LD."""

from __future__ import annotations

import asyncio
import base64
from concurrent.futures import ThreadPoolExecutor
import datetime
import hashlib
import hmac
import html as html_mod
import http.cookiejar
import json
import os
import re
import secrets
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent / "data"
RECIPES_FILE = DATA_DIR / "cookidoo_recipes.json"
COOKIDOO_SESSION_FILE = Path(
    os.environ.get("COOKIDOO_SESSION_FILE")
    or (Path(tempfile.gettempdir()) / "eci_cookidoo_sessions.json")
)
_COOKIDOO_LOCK = threading.RLock()

# Official Vorwerk / Cookidoo OAuth2 + PKCE and Calendar/Shopping endpoints
CIAM_BASE_URL = "https://ciam.prod.cookidoo.vorwerk-digital.com"
CIAM_AUTHORIZE_URL = f"{CIAM_BASE_URL}/authz-srv/authz"
CIAM_LOGIN_SRV_URL = f"{CIAM_BASE_URL}/login-srv/login"
CIAM_TOKEN_URL = f"{CIAM_BASE_URL}/token-srv/token"
OAUTH_CLIENT_ID = "mobile-android"
OAUTH_REDIRECT_URI = "com.vorwerk.cookidoo://code-grant"
OAUTH_SCOPE = "openid profile email offline offline_access"

COOKIDOO_API_BASE = "https://cookidoo.es"
COOKIDOO_PLANNER_WEB_URL = "https://cookidoo.es/planning/es-ES/my-week"
COOKIDOO_MY_DAY_API_URL = f"{COOKIDOO_API_BASE}/planning/es-ES/api/my-day"
COOKIDOO_MY_WEEK_API_URL = f"{COOKIDOO_API_BASE}/planning/es-ES/api/my-week"
COOKIDOO_SHOPPING_ADD_API_URL = f"{COOKIDOO_API_BASE}/shopping/es-ES/recipes/add"
COOKIDOO_SHOPPING_REMOVE_API_URL = f"{COOKIDOO_API_BASE}/shopping/es-ES/recipes/remove"
COOKIDOO_DEVICES_API_URL = f"{COOKIDOO_API_BASE}/customer-devices/api/my-devices/versions"

COOKIDOO_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)

_RECIPES_CACHE: list[dict[str, Any]] | None = None
_VERIFIED_LIVE_IMAGES: dict[str, str] = {}


def sanitize_recipe_description(desc: str, ingredients: list[str] | None = None) -> str:
    """Ensures recipe descriptions never contain 'Receta oficial de Thermomix Cookidoo'."""
    cleaned = re.sub(
        r"^Receta\s+oficial\s+de\s+Thermomix\s+Cookidoo\s*(?:\([^)]*\))?\s*(?:con\s+)?",
        "",
        str(desc or "").strip(),
        flags=re.IGNORECASE,
    ).strip()
    if cleaned and cleaned != str(desc or "").strip():
        return f"Plato casero elaborado con {cleaned[0].lower() + cleaned[1:]}"
    return cleaned


_MEAT_KEYWORDS_RE = re.compile(
    r"\b(?:carne|carnes|pollo|alitas|pechuga|muslos|contramuslos|ternera|vitello|vacuno|buey|"
    r"cerdo|pavo|cordero|cabrito|conejo|pato|codorniz|perdiz|carrillera|carrillada|costilla|costillas|"
    r"secreto|presa|pluma|abanico|butifarra|chorizo|morcilla|salchicha|salchichas|longaniza|chistorra|"
    r"jam[oó]n|bacon|beicon|panceta|lomo\s+y\s+patatas|lomo\s+de\s+cerdo|lomo\s+adobado|lomo\s+en\s+salsa|"
    r"solomillo\s+de\s+(?:cerdo|ternera|pavo|buey)|goulash|boloñesa|bolonesa|rag[uú]|"
    r"estofado\s+de\s+(?:carne|ternera|cerdo|pavo|pollo|cordero)|caldo\s+de\s+(?:pollo|ave|carne))\b",
    re.IGNORECASE,
)

_TRUE_FISH_TITLE_RE = re.compile(
    r"\b(?:pescado|merluza|salm[oó]n|bacalao|at[uú]n|bonito|lubina|dorada\s+(?:al|a\s+la|con|en\s+salsa)|"
    r"emperador|pez\s+espada|rape|corvina|rodaballo|lenguado|trucha|rosada|sardinas?|boquer[oó]n|boquerones|"
    r"caballa|gambas?|gamb[oó]n|gambones|langostinos?|calamares?|calamar|chipir[oó]n|chipirones|sepia|pulpo|"
    r"mejill[oó]n|mejillones|almejas?|chirlas?|berberechos?|marisco|cigalas?|vieiras?|cangrejo|fumet|marmitako|suquet)\b",
    re.IGNORECASE,
)


def load_cookidoo_catalog() -> list[dict[str, Any]]:
    """Loads the verified Cookidoo recipe catalog (5,000 Spanish recipes) with in-memory caching."""
    global _RECIPES_CACHE
    if _RECIPES_CACHE is not None:
        return _RECIPES_CACHE
    if RECIPES_FILE.exists():
        loaded = json.loads(RECIPES_FILE.read_text(encoding="utf-8"))
        for r in loaded:
            r["description"] = sanitize_recipe_description(r.get("description", ""), r.get("ingredients"))
            name_str = str(r.get("name", ""))
            ings_str = " ".join(str(x) for x in (r.get("ingredients") or []))
            if _MEAT_KEYWORDS_RE.search(name_str) or _MEAT_KEYWORDS_RE.search(ings_str):
                r["is_fish"] = False
                r["is_vegetarian"] = False
            elif r.get("is_fish") and not _TRUE_FISH_TITLE_RE.search(name_str + " " + ings_str):
                r["is_fish"] = False
        _RECIPES_CACHE = loaded
        return _RECIPES_CACHE
    return []


def fetch_live_cookidoo_recipe(recipe_id: str, timeout: float = 4.0) -> dict[str, Any] | None:
    """Fetches real-time recipe metadata and cover image from Cookidoo's public JSON-LD."""
    clean_id = str(recipe_id or "").strip()
    if not re.match(r"^r\d{4,9}$", clean_id):
        return None
    for host, loc in [("cookidoo.es", "es-ES"), ("cookidoo.thermomix.com", "en-US")]:
        url = f"https://{host}/recipes/recipe/{loc}/{clean_id}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": COOKIDOO_USER_AGENT})
            page = urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "ignore")
            m = re.search(r'<script type="application/ld\+json">(.*?)</script>', page, re.S)
            if not m:
                continue
            d = json.loads(m.group(1))
            iso = d.get("totalTime") or d.get("cookTime") or "PT25M"
            hm = re.search(r"(\d+)H", iso)
            mm = re.search(r"(\d+)M", iso)
            minutes = (int(hm.group(1)) * 60 if hm else 0) + (int(mm.group(1)) if mm else 0) or 25
            cal_str = str(d.get("nutrition", {}).get("calories", "350 kcal"))
            cm = re.search(r"(\d+(?:\.\d+)?)", cal_str)
            calories = round(float(cm.group(1))) if cm else 350
            yield_str = str(d.get("recipeYield", "4"))
            ym = re.search(r"(\d+)", yield_str)
            servings = int(ym.group(1)) if ym else 4
            ings = [
                html_mod.unescape(re.sub(r"<[^>]+>", "", x)).strip()
                for x in d.get("recipeIngredient", [])
            ]
            img = d.get("image") or ""
            if isinstance(img, list):
                img = img[0] if img else ""
            img_str = str(img).strip()
            if img_str:
                _VERIFIED_LIVE_IMAGES[clean_id] = img_str
            return {
                "cookidoo_id": clean_id,
                "name": html_mod.unescape(d.get("name", clean_id)),
                "image_url": img_str,
                "minutes": minutes,
                "calories_per_serving": calories,
                "cookidoo_servings": servings,
                "ingredients": ings,
                "cookidoo_url": f"https://cookidoo.es/recipes/recipe/es-ES/{clean_id}",
                "source": "live",
            }
        except Exception:
            continue
    return None


def ensure_verified_cookidoo_image(recipe: dict[str, Any], timeout: float = 2.5) -> dict[str, Any]:
    """Verifies a recipe's cover image against live cookidoo.es JSON-LD (cached in memory) so photos always match."""
    if not isinstance(recipe, dict):
        return recipe
    rid = str(recipe.get("recipe_id") or recipe.get("cookidoo_id") or "").strip()
    if not rid:
        return recipe
    if rid in _VERIFIED_LIVE_IMAGES:
        recipe["image_url"] = _VERIFIED_LIVE_IMAGES[rid]
        return recipe
    live = fetch_live_cookidoo_recipe(rid, timeout=timeout)
    if live and live.get("image_url"):
        recipe["image_url"] = live["image_url"]
    return recipe


def ensure_verified_cookidoo_images_batch(recipes: list[dict[str, Any]], timeout: float = 2.5) -> list[dict[str, Any]]:
    """Verifies cover images in parallel for a list of selected recipes."""
    to_check = [
        r
        for r in recipes
        if isinstance(r, dict)
        and str(r.get("recipe_id") or r.get("cookidoo_id") or "").strip() not in _VERIFIED_LIVE_IMAGES
    ]
    if to_check:
        with ThreadPoolExecutor(max_workers=min(5, len(to_check))) as pool:
            list(pool.map(lambda item: ensure_verified_cookidoo_image(item, timeout=timeout), to_check))
    for r in recipes:
        if isinstance(r, dict):
            rid = str(r.get("recipe_id") or r.get("cookidoo_id") or "").strip()
            if rid in _VERIFIED_LIVE_IMAGES:
                r["image_url"] = _VERIFIED_LIVE_IMAGES[rid]
    return recipes


_WEEKDAY_TO_INDEX = {
    "lunes": 0,
    "monday": 0,
    "martes": 1,
    "tuesday": 1,
    "miércoles": 2,
    "miercoles": 2,
    "wednesday": 2,
    "jueves": 3,
    "thursday": 3,
    "viernes": 4,
    "friday": 4,
    "sábado": 5,
    "sabado": 5,
    "saturday": 5,
    "domingo": 6,
    "sunday": 6,
}

_SHORT_DAY_ES = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
_FULL_DAY_ES = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
_SHORT_MONTH_ES = ["", "ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def _get_at_rest_key() -> bytes:
    raw = (
        os.environ.get("SESSION_SECRET")
        or os.environ.get("COOKIDOO_TOKEN_KEY")
        or "eci-cookidoo-at-rest-key-v1"
    ).encode("utf-8")
    return hashlib.sha256(raw).digest()


def _encrypt_secret(plaintext: str | None) -> str | None:
    if not plaintext:
        return None
    text_str = str(plaintext)
    if text_str.startswith("enc:v1:"):
        return text_str
    key = _get_at_rest_key()
    nonce = secrets.token_bytes(16)
    pt_bytes = text_str.encode("utf-8")
    stream = bytearray()
    counter = 0
    while len(stream) < len(pt_bytes):
        block = hmac.new(key, nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest()
        stream.extend(block)
        counter += 1
    ct_bytes = bytes(a ^ b for a, b in zip(pt_bytes, stream[: len(pt_bytes)]))
    mac = hmac.new(key, b"enc:v1:" + nonce + ct_bytes, hashlib.sha256).digest()[:16]
    blob = base64.urlsafe_b64encode(nonce + mac + ct_bytes).decode("ascii")
    return f"enc:v1:{blob}"


def _decrypt_secret(ciphertext: str | None) -> str | None:
    if not ciphertext:
        return None
    text_str = str(ciphertext)
    if not text_str.startswith("enc:v1:"):
        return text_str
    try:
        key = _get_at_rest_key()
        raw = base64.urlsafe_b64decode(text_str[len("enc:v1:") :].encode("ascii"))
        if len(raw) < 32:
            return None
        nonce = raw[:16]
        mac = raw[16:32]
        ct_bytes = raw[32:]
        expected_mac = hmac.new(key, b"enc:v1:" + nonce + ct_bytes, hashlib.sha256).digest()[:16]
        if not hmac.compare_digest(mac, expected_mac):
            return None
        stream = bytearray()
        counter = 0
        while len(stream) < len(ct_bytes):
            block = hmac.new(key, nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest()
            stream.extend(block)
            counter += 1
        pt_bytes = bytes(a ^ b for a, b in zip(ct_bytes, stream[: len(ct_bytes)]))
        return pt_bytes.decode("utf-8")
    except Exception:
        return None


def _load_cookidoo_sessions() -> dict[str, dict[str, Any]]:
    with _COOKIDOO_LOCK:
        if not COOKIDOO_SESSION_FILE.is_file():
            return {}
        try:
            data = json.loads(COOKIDOO_SESSION_FILE.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return {}
            out: dict[str, dict[str, Any]] = {}
            for k, v in data.items():
                if not isinstance(v, dict):
                    continue
                item = dict(v)
                # Never retain real user passwords in memory or disk; only allow demo sentinel
                if item.get("password") and item.get("password") != "demo-thermomix-tm6":
                    item["password"] = None
                for tok_field in ("access_token", "refresh_token"):
                    if item.get(tok_field):
                        item[tok_field] = _decrypt_secret(str(item[tok_field]))
                out[k] = item
            return out
        except Exception:
            return {}


def _save_cookidoo_sessions(store: dict[str, dict[str, Any]]) -> None:
    with _COOKIDOO_LOCK:
        tmp_path: str | None = None
        try:
            sanitized_store: dict[str, dict[str, Any]] = {}
            for k, v in (store or {}).items():
                if not isinstance(v, dict):
                    continue
                clean_v = dict(v)
                # Security: never persist real plaintext Cookidoo passwords to disk
                if clean_v.get("password") and clean_v.get("password") != "demo-thermomix-tm6":
                    clean_v["password"] = None
                for tok_field in ("access_token", "refresh_token"):
                    if clean_v.get(tok_field):
                        clean_v[tok_field] = _encrypt_secret(str(clean_v[tok_field]))
                sanitized_store[k] = clean_v

            COOKIDOO_SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(
                dir=str(COOKIDOO_SESSION_FILE.parent), prefix=".cookidoo_sess_", suffix=".tmp"
            )
            try:
                os.fchmod(fd, 0o600)
            except AttributeError:
                pass
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(sanitized_store, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, COOKIDOO_SESSION_FILE)
            tmp_path = None
        except Exception:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass


def _mask_email(email: str) -> str:
    clean = (email or "").strip()
    if "@" not in clean:
        return clean
    local, domain = clean.split("@", 1)
    if len(local) <= 2:
        return f"{local[0]}***@{domain}" if local else clean
    return f"{local[:2]}***{local[-1]}@{domain}"


def resolve_weekday_date(
    day_name: str | None,
    week_mode: str = "current",
    reference_date: datetime.date | None = None,
) -> dict[str, str]:
    """Resolves a Spanish day name ('Lunes'..'Domingo') to a concrete calendar date in 'Mi Semana'."""
    today = reference_date or datetime.date.today()
    # Monday of the current week (or next Monday if today is Saturday/Sunday)
    base_monday = today - datetime.timedelta(days=today.weekday())
    if today.weekday() >= 5 and week_mode == "current":
        base_monday = base_monday + datetime.timedelta(days=7)
    elif week_mode in ("next", "next_week", "proxima"):
        base_monday = base_monday + datetime.timedelta(days=7)

    clean_day = (day_name or "Lunes").strip().lower()
    day_idx = _WEEKDAY_TO_INDEX.get(clean_day, 0)
    target_date = base_monday + datetime.timedelta(days=day_idx)
    short_label = f"{_SHORT_DAY_ES[day_idx]} {target_date.day} {_SHORT_MONTH_ES[target_date.month]}"
    full_label = f"{_FULL_DAY_ES[day_idx]} {target_date.day} de {_SHORT_MONTH_ES[target_date.month]}"
    return {
        "day": _FULL_DAY_ES[day_idx],
        "date_iso": target_date.isoformat(),
        "short_label": short_label,
        "full_label": full_label,
    }


def get_week_range_summary(week_mode: str = "current", reference_date: datetime.date | None = None) -> dict[str, Any]:
    """Returns concrete calendar dates for Lunes..Viernes for the selected week mode."""
    days = [resolve_weekday_date(d, week_mode=week_mode, reference_date=reference_date) for d in _FULL_DAY_ES[:5]]
    return {
        "week_mode": "next" if week_mode in ("next", "next_week", "proxima") else "current",
        "range_label": f"{days[0]['short_label']} – {days[-1]['short_label']}",
        "days": days,
    }


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Prevents urllib from automatically following 302 redirects to custom app schemes (com.vorwerk.cookidoo://)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _pkce_pair() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode("ascii")
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def _extract_request_id(login_html: str) -> str:
    m = re.search(
        r'<input\b[^>]*\bname=["\']requestId["\'][^>]*\bvalue=["\']([^"\']+)["\']',
        login_html,
        re.IGNORECASE,
    )
    if not m:
        m = re.search(
            r'<input\b[^>]*\bvalue=["\']([^"\']+)["\'][^>]*\bname=["\']requestId["\']',
            login_html,
            re.IGNORECASE,
        )
    if not m:
        raise ValueError("No se pudo iniciar el flujo de autenticación con Cookidoo (requestId no encontrado).")
    return m.group(1)


def _cookidoo_oauth_login_stdlib(email: str, password: str) -> dict[str, Any]:
    """Pure-Python standard library implementation of Cookidoo OAuth2 + PKCE authentication.

    Works on Cloud Run python312 base images without requiring external pip packages (aiohttp/cookidoo-api).
    """
    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(12)
    params = {
        "response_type": "code",
        "client_id": OAUTH_CLIENT_ID,
        "redirect_uri": OAUTH_REDIRECT_URI,
        "market": "es",
        "scope": OAUTH_SCOPE,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "ui_locales": "es-ES",
    }
    cookie_jar = http.cookiejar.CookieJar()
    std_opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
    no_redirect_opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(cookie_jar), _NoRedirectHandler()
    )

    # Step 1: GET the CIAM authorization page to obtain session cookies and `requestId`
    auth_url = f"{CIAM_AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"
    try:
        req = urllib.request.Request(auth_url, headers={"User-Agent": COOKIDOO_USER_AGENT})
        with std_opener.open(req, timeout=12) as resp:
            login_html = resp.read().decode("utf-8", "ignore")
    except Exception as exc:
        raise ValueError(f"No se pudo conectar con el servidor de acceso de Cookidoo: {exc}") from exc

    request_id = _extract_request_id(login_html)

    # Step 2: POST credentials to CIAM login service and follow redirects manually to capture `code`
    current_url = CIAM_LOGIN_SRV_URL
    form_bytes: bytes | None = urllib.parse.urlencode(
        {
            "requestId": request_id,
            "username": email,
            "password": password,
        }
    ).encode("utf-8")
    method = "POST"
    auth_code: str | None = None

    for _ in range(10):
        req_headers = {"User-Agent": COOKIDOO_USER_AGENT}
        if form_bytes is not None:
            req_headers["Content-Type"] = "application/x-www-form-urlencoded"
        step_req = urllib.request.Request(current_url, data=form_bytes, headers=req_headers, method=method)
        status_code = 200
        location: str | None = None
        try:
            with no_redirect_opener.open(step_req, timeout=12) as step_resp:
                status_code = step_resp.status
                location = step_resp.headers.get("Location")
        except urllib.error.HTTPError as e:
            status_code = e.code
            location = e.headers.get("Location")
        except Exception as exc:
            raise ValueError(f"Error de red al verificar credenciales en Cookidoo: {exc}") from exc

        if status_code in (301, 302, 303, 307, 308) and location:
            if location.startswith(OAUTH_REDIRECT_URI):
                parsed_loc = urllib.parse.urlparse(location)
                qs = urllib.parse.parse_qs(parsed_loc.query)
                if "error" in qs:
                    err_desc = (qs.get("error_description") or qs.get("error") or ["Credenciales inválidas"])[0]
                    raise ValueError(
                        f"Cookidoo rechazó el inicio de sesión ({err_desc}). Comprueba tu email y contraseña de cookidoo.es."
                    )
                codes = qs.get("code")
                if codes:
                    auth_code = codes[0]
                break

            # Check if CIAM redirected back to an error / failed login URL
            loc_low = location.lower()
            if "error=" in loc_low or "authentication_error" in loc_low or "login?error" in loc_low:
                raise ValueError(
                    "Email o contraseña de Cookidoo incorrectos. Verifica que puedes iniciar sesión en cookidoo.es."
                )

            current_url = urllib.parse.urljoin(current_url, location)
            method = "GET"
            form_bytes = None
            continue
        break

    if not auth_code:
        raise ValueError(
            "Email o contraseña de Cookidoo incorrectos. Comprueba tus credenciales de cookidoo.es e inténtalo de nuevo."
        )

    # Step 3: Exchange authorization code + PKCE verifier for OAuth2 access_token & refresh_token
    token_data = urllib.parse.urlencode(
        {
            "grant_type": "authorization_code",
            "code": auth_code,
            "redirect_uri": OAUTH_REDIRECT_URI,
            "code_verifier": verifier,
            "client_id": OAUTH_CLIENT_ID,
        }
    ).encode("utf-8")
    token_req = urllib.request.Request(
        CIAM_TOKEN_URL,
        data=token_data,
        headers={
            "User-Agent": COOKIDOO_USER_AGENT,
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with std_opener.open(token_req, timeout=12) as tok_resp:
            tok_payload = json.loads(tok_resp.read().decode("utf-8", "ignore"))
    except urllib.error.HTTPError as e:
        raise ValueError(f"Cookidoo rechazó el canje de token OAuth2 (HTTP {e.code}).") from e
    except Exception as exc:
        raise ValueError(f"No se pudo obtener el token de acceso de Cookidoo: {exc}") from exc

    access_token = str(tok_payload.get("access_token") or "").strip()
    refresh_token = str(tok_payload.get("refresh_token") or "").strip()
    expires_in = int(tok_payload.get("expires_in") or 43200)
    if not access_token:
        raise ValueError("Cookidoo no devolvió un access_token válido.")

    # Optional: detect paired Thermomix version (TM6 / TM7)
    device_name = "Thermomix® TM6 · Cookidoo España (API en vivo)"
    try:
        dev_req = urllib.request.Request(
            COOKIDOO_DEVICES_API_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                "User-Agent": COOKIDOO_USER_AGENT,
            },
        )
        with urllib.request.urlopen(dev_req, timeout=6) as dev_resp:
            dev_data = json.loads(dev_resp.read().decode("utf-8", "ignore"))
            if isinstance(dev_data, list) and dev_data:
                models = ", ".join(str(x) for x in dev_data if x)
                if models:
                    device_name = f"Thermomix® {models} · Cookidoo España (API en vivo)"
            elif isinstance(dev_data, dict) and dev_data.get("versions"):
                models = ", ".join(str(x) for x in dev_data["versions"] if x)
                if models:
                    device_name = f"Thermomix® {models} · Cookidoo España (API en vivo)"
    except Exception:
        pass

    return {
        "verified_live": True,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": time.time() + max(300, expires_in - 300),
        "device_name": device_name,
    }


def _cookidoo_refresh_token_stdlib(refresh_token: str) -> dict[str, Any]:
    """Refreshes an expired Cookidoo OAuth2 access_token using the stored refresh_token."""
    if not refresh_token:
        raise ValueError("No hay refresh_token disponible.")
    form_data = urllib.parse.urlencode(
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": OAUTH_CLIENT_ID,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        CIAM_TOKEN_URL,
        data=form_data,
        headers={
            "User-Agent": COOKIDOO_USER_AGENT,
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        payload = json.loads(resp.read().decode("utf-8", "ignore"))
    access_token = str(payload.get("access_token") or "").strip()
    if not access_token:
        raise ValueError("Respuesta de refresh_token inválida.")
    new_refresh = str(payload.get("refresh_token") or refresh_token).strip()
    expires_in = int(payload.get("expires_in") or 43200)
    return {
        "access_token": access_token,
        "refresh_token": new_refresh,
        "expires_at": time.time() + max(300, expires_in - 300),
    }


def _get_valid_cookidoo_access_token(
    user_key: str,
    email: str | None = None,
    password: str | None = None,
) -> tuple[str, str]:
    """Returns a valid `(access_token, effective_email)` for the user, refreshing or logging in as needed."""
    store = _load_cookidoo_sessions()
    entry = store.get(user_key) or {}

    eff_email = (email or entry.get("email") or os.environ.get("COOKIDOO_EMAIL") or "").strip()
    eff_pass = (password or entry.get("password") or os.environ.get("COOKIDOO_PASSWORD") or "").strip()

    # 1. If explicit new credentials were passed in the request and differ from stored token, or no token yet:
    access_token = str(entry.get("access_token") or "").strip()
    refresh_token = str(entry.get("refresh_token") or "").strip()
    expires_at = float(entry.get("expires_at") or 0.0)

    if access_token and expires_at > time.time() and (not email or email.strip().lower() == str(entry.get("email", "")).lower()):
        return access_token, eff_email

    # 2. Try refreshing via refresh_token
    if refresh_token and (not password or password == entry.get("password")):
        try:
            refreshed = _cookidoo_refresh_token_stdlib(refresh_token)
            with _COOKIDOO_LOCK:
                store = _load_cookidoo_sessions()
                curr = store.get(user_key) or {}
                curr.update(
                    {
                        "access_token": refreshed["access_token"],
                        "refresh_token": refreshed["refresh_token"],
                        "expires_at": refreshed["expires_at"],
                        "auth_mode": "live_api",
                    }
                )
                store[user_key] = curr
                _save_cookidoo_sessions(store)
            return refreshed["access_token"], eff_email
        except Exception:
            pass

    # 3. Perform fresh OAuth2 + PKCE login if real password is available
    if eff_email and eff_pass and eff_pass != "demo-thermomix-tm6":
        login_res = _cookidoo_oauth_login_stdlib(eff_email, eff_pass)
        with _COOKIDOO_LOCK:
            store = _load_cookidoo_sessions()
            curr = store.get(user_key) or {}
            curr.update(
                {
                    "connected": True,
                    "email": eff_email,
                    "password": None,
                    "access_token": login_res["access_token"],
                    "refresh_token": login_res["refresh_token"],
                    "expires_at": login_res["expires_at"],
                    "device_name": login_res.get("device_name") or "Thermomix® TM6 · Cookidoo España (API en vivo)",
                    "auth_mode": "live_api",
                }
            )
            store[user_key] = curr
            _save_cookidoo_sessions(store)
        return login_res["access_token"], eff_email

    raise ValueError(
        "Para sincronizar en tu cuenta real de Cookidoo.es, vincula tu email y contraseña reales de Cookidoo arriba."
    )


def _cookidoo_get_calendar_week_stdlib(
    access_token: str,
    target_date: datetime.date,
) -> dict[str, dict[str, list[str]]]:
    """Calls `GET https://cookidoo.es/planning/es-ES/api/my-week/{YYYY-MM-DD}` to read currently scheduled recipes per day."""
    url = f"{COOKIDOO_MY_WEEK_API_URL}/{target_date.isoformat()}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "User-Agent": COOKIDOO_USER_AGENT,
        },
        method="GET",
    )
    week_map: dict[str, dict[str, list[str]]] = {}
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            raw = resp.read().decode("utf-8", "ignore")
            data = json.loads(raw) if raw.strip() else {}
        for day_obj in data.get("myDays") or []:
            if not isinstance(day_obj, dict):
                continue
            day_id = str(day_obj.get("id") or "").strip()
            if not day_id:
                continue
            rids = [
                str(r.get("id")).strip()
                for r in (day_obj.get("recipes") or [])
                if isinstance(r, dict) and r.get("id")
            ]
            custom_rids = [
                str(r.get("id")).strip()
                for r in (day_obj.get("customerRecipes") or [])
                if isinstance(r, dict) and r.get("id")
            ] + [str(cid).strip() for cid in (day_obj.get("customerRecipeIds") or []) if cid]
            week_map[day_id] = {
                "recipes": list(dict.fromkeys(rids)),
                "custom_recipes": list(dict.fromkeys(custom_rids)),
            }
    except Exception:
        pass
    return week_map


def _cookidoo_put_calendar_day_stdlib(
    access_token: str,
    target_date: datetime.date | str,
    recipe_ids: list[str],
) -> dict[str, Any]:
    """Calls `PUT https://cookidoo.es/planning/es-ES/api/my-day` with `{"recipeIds": [...], "dayKey": "YYYY-MM-DD"}`."""
    day_iso = target_date.isoformat() if hasattr(target_date, "isoformat") else str(target_date)
    payload = json.dumps(
        {
            "recipeIds": recipe_ids,
            "dayKey": day_iso,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        COOKIDOO_MY_DAY_API_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": COOKIDOO_USER_AGENT,
        },
        method="PUT",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8", "ignore")
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        err_body = ""
        try:
            err_body = e.read().decode("utf-8", "ignore")[:200]
        except Exception:
            pass
        raise ValueError(
            f"Cookidoo API rechazó programar el día {day_iso} (HTTP {e.code}): {err_body}"
        ) from e


def _cookidoo_delete_calendar_day_recipe_stdlib(
    access_token: str,
    target_date: datetime.date | str,
    recipe_id: str,
    is_custom: bool = False,
) -> None:
    """Calls `DELETE https://cookidoo.es/planning/es-ES/api/my-day/{YYYY-MM-DD}/recipes/{recipe_id}` to remove an old recipe."""
    clean_rid = str(recipe_id or "").strip()
    if not clean_rid:
        return
    day_iso = target_date.isoformat() if hasattr(target_date, "isoformat") else str(target_date)
    url = f"{COOKIDOO_MY_DAY_API_URL}/{day_iso}/recipes/{urllib.parse.quote(clean_rid)}"
    if is_custom:
        url = f"{url}?recipeSource=CUSTOMER"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "User-Agent": COOKIDOO_USER_AGENT,
        },
        method="DELETE",
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            resp.read()
    except Exception:
        pass


def _cookidoo_replace_calendar_day_stdlib(
    access_token: str,
    target_date: datetime.date | str,
    desired_recipe_ids: list[str],
    preloaded_week_map: dict[str, dict[str, list[str]]] | None = None,
    previously_scheduled_ids: list[str] | None = None,
) -> list[str]:
    """Replaces the recipes on `target_date` in Cookidoo by adding `desired_recipe_ids` and deleting any older recipes on that day."""
    day_iso = target_date.isoformat() if hasattr(target_date, "isoformat") else str(target_date)
    desired_clean = [str(r).strip() for r in desired_recipe_ids if str(r).strip()]
    desired_set = set(desired_clean)

    existing_regular: list[str] = []
    if preloaded_week_map and day_iso in preloaded_week_map:
        day_entry = preloaded_week_map[day_iso]
        existing_regular.extend(day_entry.get("recipes") or day_entry.get("recipe_ids") or [])
    if previously_scheduled_ids:
        existing_regular.extend(str(r).strip() for r in previously_scheduled_ids if str(r).strip())

    # Add the desired recipe(s) for this day; PUT returns `{"content": {"recipes": [...]}}` with all recipes now on that day
    put_resp = _cookidoo_put_calendar_day_stdlib(access_token, day_iso, desired_clean)
    content_obj = put_resp.get("content") if isinstance(put_resp, dict) else None
    if isinstance(content_obj, dict):
        for r_obj in content_obj.get("recipes") or []:
            if isinstance(r_obj, dict) and r_obj.get("id"):
                existing_regular.append(str(r_obj["id"]).strip())

    # Remove every recipe on `target_date` that is not in `desired_set`
    removed_ids: list[str] = []
    for old_rid in dict.fromkeys(existing_regular):
        if old_rid and old_rid not in desired_set:
            _cookidoo_delete_calendar_day_recipe_stdlib(access_token, day_iso, old_rid, is_custom=False)
            removed_ids.append(old_rid)
    return removed_ids


def _cookidoo_add_shopping_list_recipes_stdlib(access_token: str, recipe_ids: list[str]) -> None:
    """Calls `POST https://cookidoo.es/shopping/es-ES/recipes/add` with `{"recipeIDs": [...]}`."""
    if not recipe_ids:
        return
    payload = json.dumps({"recipeIDs": recipe_ids}).encode("utf-8")
    req = urllib.request.Request(
        COOKIDOO_SHOPPING_ADD_API_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": COOKIDOO_USER_AGENT,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            resp.read()
    except Exception:
        # Shopping list addition is secondary to calendar scheduling; do not fail calendar sync if shopping list fails
        pass


def _cookidoo_remove_shopping_list_recipes_stdlib(access_token: str, recipe_ids: list[str]) -> None:
    """Calls `POST https://cookidoo.es/shopping/es-ES/recipes/remove` with `{"recipeIDs": [...]}` to clean up replaced recipes."""
    clean_ids = [str(r).strip() for r in recipe_ids if str(r).strip()]
    if not clean_ids:
        return
    payload = json.dumps({"recipeIDs": clean_ids}).encode("utf-8")
    req = urllib.request.Request(
        COOKIDOO_SHOPPING_REMOVE_API_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": COOKIDOO_USER_AGENT,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            resp.read()
    except Exception:
        pass


def get_cookidoo_session_status(user_email: str = "default") -> dict[str, Any]:
    """Returns the linked Cookidoo account status and last scheduled week for the given user."""
    key = (user_email or "default").strip().lower() or "default"
    store = _load_cookidoo_sessions()
    entry = store.get(key) or {}
    env_email = (os.environ.get("COOKIDOO_EMAIL") or "").strip()
    env_pass = (os.environ.get("COOKIDOO_PASSWORD") or "").strip()
    email = (entry.get("email") or env_email or "").strip()
    stored_pass = (entry.get("password") or env_pass or "").strip()
    has_live_token = bool(entry.get("access_token"))

    # If the user previously saved a real password before our stdlib OAuth2 upgrade, upgrade them to a live token now
    if entry.get("connected") and not has_live_token and email and stored_pass and stored_pass != "demo-thermomix-tm6":
        try:
            login_res = _cookidoo_oauth_login_stdlib(email, stored_pass)
            with _COOKIDOO_LOCK:
                store = _load_cookidoo_sessions()
                curr = store.get(key) or {}
                curr.update(
                    {
                        "access_token": login_res["access_token"],
                        "refresh_token": login_res["refresh_token"],
                        "expires_at": login_res["expires_at"],
                        "device_name": login_res.get("device_name") or curr.get("device_name"),
                        "auth_mode": "live_api",
                    }
                )
                store[key] = curr
                _save_cookidoo_sessions(store)
                entry = curr
                has_live_token = True
        except Exception:
            pass

    connected = bool(entry.get("connected") or (env_email and env_pass))
    auth_mode = entry.get("auth_mode") or ("live_api" if has_live_token else ("demo_mode" if connected else None))
    if auth_mode == "cookidoo_cloud_sync" and not has_live_token:
        auth_mode = "demo_mode"

    return {
        "connected": connected,
        "live_authenticated": bool(has_live_token and auth_mode == "live_api"),
        "email": email or None,
        "masked_email": _mask_email(email) if email else None,
        "device_name": entry.get("device_name")
        or (
            "Thermomix® TM6 · Cookidoo España (API en vivo)"
            if has_live_token
            else ("Perfil Demo Thermomix® TM6 (Simulación)" if connected else None)
        ),
        "auth_mode": auth_mode,
        "planner_url": COOKIDOO_PLANNER_WEB_URL,
        "last_scheduled_week": entry.get("last_scheduled_week"),
        "week_preview_current": get_week_range_summary("current"),
        "week_preview_next": get_week_range_summary("next"),
    }


def verify_and_save_cookidoo_session(
    email: str | None = None,
    password: str | None = None,
    user_email: str = "default",
    demo_mode: bool = False,
) -> dict[str, Any]:
    """Links a Cookidoo account via real OAuth2+PKCE (`ciam.prod.cookidoo.vorwerk-digital.com`) or explicit Demo mode."""
    clean_email = (email or "").strip()
    clean_pass = (password or "").strip()
    if demo_mode and not clean_email:
        clean_email = user_email if (user_email and "@" in user_email) else "thermomix.eci@cookidoo.es"
        clean_pass = "demo-thermomix-tm6"

    if not clean_email or "@" not in clean_email:
        raise ValueError("Introduce un email válido de tu cuenta de Cookidoo (cookidoo.es).")
    if not demo_mode and not clean_pass:
        raise ValueError("Introduce la contraseña de tu cuenta de Cookidoo (cookidoo.es).")

    key = (user_email or "default").strip().lower() or "default"

    if not demo_mode:
        # Real Cookidoo account linking: verify credentials live against Vorwerk CIAM and do NOT swallow errors!
        live_res = _cookidoo_oauth_login_stdlib(clean_email, clean_pass)
        auth_mode = "live_api"
        device_name = live_res.get("device_name") or "Thermomix® TM6 · Cookidoo España (API en vivo)"
        with _COOKIDOO_LOCK:
            store = _load_cookidoo_sessions()
            prev = store.get(key) or {}
            store[key] = {
                "connected": True,
                "email": clean_email,
                "password": None,
                "access_token": live_res["access_token"],
                "refresh_token": live_res["refresh_token"],
                "expires_at": live_res["expires_at"],
                "device_name": device_name,
                "auth_mode": auth_mode,
                "linked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "last_scheduled_week": prev.get("last_scheduled_week"),
            }
            _save_cookidoo_sessions(store)

        status = get_cookidoo_session_status(user_email)
        status["message"] = (
            f"✓ Cuenta real de Cookidoo ({_mask_email(clean_email)}) autenticada en vivo con {device_name}. "
            "Al confirmar tu menú, las 5 cenas se escribirán directamente en tu calendario real «Mi Semana» de cookidoo.es."
        )
        return status

    # Explicit Demo Mode
    auth_mode = "demo_mode"
    device_name = "Perfil Demo Thermomix® TM6 (Simulación local)"
    with _COOKIDOO_LOCK:
        store = _load_cookidoo_sessions()
        prev = store.get(key) or {}
        store[key] = {
            "connected": True,
            "email": clean_email,
            "password": "demo-thermomix-tm6",
            "access_token": None,
            "refresh_token": None,
            "expires_at": 0.0,
            "device_name": device_name,
            "auth_mode": auth_mode,
            "linked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "last_scheduled_week": prev.get("last_scheduled_week"),
        }
        _save_cookidoo_sessions(store)

    status = get_cookidoo_session_status(user_email)
    status["message"] = (
        f"Perfil Demo activado ({_mask_email(clean_email)}). "
        "Nota: el modo Demo simula la planificación en pantalla; para escribir en tu cuenta real de cookidoo.es, introduce tu email y contraseña reales de Cookidoo."
    )
    return status


def clear_cookidoo_session(user_email: str = "default") -> dict[str, Any]:
    """Unlinks the stored Cookidoo account for the given user."""
    key = (user_email or "default").strip().lower() or "default"
    with _COOKIDOO_LOCK:
        store = _load_cookidoo_sessions()
        if key in store:
            del store[key]
            _save_cookidoo_sessions(store)
    return get_cookidoo_session_status(user_email)


def _build_ics_calendar_data_uri(scheduled_days: list[dict[str, Any]]) -> str:
    """Builds a downloadable .ics calendar data URI so the user can also add the 5 Thermomix dinners to Google/Apple Calendar."""
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Supermercado El Corte Ingles x Cookidoo//AI Meal Planner//ES",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]
    for item in scheduled_days:
        dt_clean = str(item.get("date_iso", "20261019")).replace("-", "")
        rid = item.get("recipe_id", "")
        name = item.get("name", "Cena Thermomix")
        url = item.get("cookidoo_url", f"https://cookidoo.es/recipes/recipe/es-ES/{rid}")
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:eci-cookidoo-{dt_clean}-{rid}@elcorteingles.es",
                f"DTSTART:{dt_clean}T203000",
                f"DTEND:{dt_clean}T210000",
                f"SUMMARY:🍽️ Cena Thermomix ({item.get('day', '')}): {name}",
                f"DESCRIPTION:Receta Cookidoo {rid} planificada desde Supermercado El Corte Inglés AI Meal Planner. Abrir en Cookidoo: {url}",
                f"URL:{url}",
                "END:VEVENT",
            ]
        )
    lines.append("END:VCALENDAR")
    ics_text = "\r\n".join(lines)
    return "data:text/calendar;charset=utf-8," + urllib.parse.quote(ics_text)


async def _send_to_cookidoo_async(
    recipe_id: str,
    email: str,
    password: str,
    target_day: datetime.date | None = None,
) -> dict[str, Any]:
    """Uses `miaucl/cookidoo-api` to authenticate and add the recipe to the user's Thermomix/Cookidoo account."""
    import aiohttp  # type: ignore
    from cookidoo_api import Cookidoo  # type: ignore
    from cookidoo_api.helpers import get_localization_options  # type: ignore
    from cookidoo_api.types import CookidooConfig  # type: ignore

    jar = aiohttp.CookieJar(unsafe=True)
    async with aiohttp.ClientSession(cookie_jar=jar) as session:
        locs = await get_localization_options(country="es", language="es-ES")
        localization = locs[0] if locs else None
        cfg = (
            CookidooConfig(email=email, password=password, localization=localization)
            if localization
            else CookidooConfig(email=email, password=password)
        )
        cookidoo = Cookidoo(session, cfg=cfg)
        await cookidoo.login()
        day = target_day or datetime.date.today()
        await cookidoo.add_recipes_to_calendar(day, [recipe_id])
        await cookidoo.add_ingredient_items_for_recipes([recipe_id])
        return {
            "status": "added_via_api",
            "recipe_id": recipe_id,
            "scheduled_date": day.isoformat(),
            "cookidoo_url": f"https://cookidoo.es/recipes/recipe/es-ES/{recipe_id}",
            "message": f"Receta {recipe_id} enviada directamente a tu Thermomix (Mi Semana y Lista de Cookidoo) mediante cookidoo-api.",
        }


def send_recipe_to_thermomix(
    recipe_id: str,
    email: str | None = None,
    password: str | None = None,
    day_name: str | None = None,
    week_mode: str = "current",
    user_email: str = "default",
) -> dict[str, Any]:
    """Sends a recipe to the user's Cookidoo account on its specific assigned weekday ('Lunes'..'Viernes')."""
    clean_id = str(recipe_id or "").strip()
    if clean_id.isdigit():
        clean_id = f"r{clean_id}"
    if not re.match(r"^r\d{1,10}$", clean_id):
        raise ValueError("ID de receta de Cookidoo inválido.")
    cookidoo_url = f"https://cookidoo.es/recipes/recipe/es-ES/{clean_id}"

    key = (user_email or "default").strip().lower() or "default"
    stored = _load_cookidoo_sessions().get(key) or {}
    eff_email = (email or stored.get("email") or os.environ.get("COOKIDOO_EMAIL") or "").strip()
    eff_password = (password or stored.get("password") or os.environ.get("COOKIDOO_PASSWORD") or "").strip()

    day_info = resolve_weekday_date(day_name or "Lunes", week_mode=week_mode)
    target_date = datetime.date.fromisoformat(day_info["date_iso"])

    # 1. If the user has an active linked OAuth2 session in the session store, sync via stdlib REST API
    if stored.get("access_token") and not (email and password):
        try:
            access_token, resolved_email = _get_valid_cookidoo_access_token(
                user_key=key, email=email, password=password
            )
            prev_days = (stored.get("last_scheduled_week") or {}).get("days") or []
            prev_day_rids = [
                str(d.get("recipe_id") or "").strip()
                for d in prev_days
                if isinstance(d, dict)
                and (d.get("date_iso") == day_info["date_iso"] or d.get("day") == day_info["day"])
                and d.get("recipe_id")
            ]
            week_map = _cookidoo_get_calendar_week_stdlib(access_token, target_date)
            removed_rids = _cookidoo_replace_calendar_day_stdlib(
                access_token=access_token,
                target_date=target_date,
                desired_recipe_ids=[clean_id],
                preloaded_week_map=week_map,
                previously_scheduled_ids=prev_day_rids,
            )
            if removed_rids:
                _cookidoo_remove_shopping_list_recipes_stdlib(access_token, removed_rids)
            _cookidoo_add_shopping_list_recipes_stdlib(access_token, [clean_id])

            # Keep stored last_scheduled_week in sync if this day was part of it
            with _COOKIDOO_LOCK:
                store_now = _load_cookidoo_sessions()
                curr_entry = store_now.get(key) or {}
                last_wk = curr_entry.get("last_scheduled_week")
                if isinstance(last_wk, dict) and isinstance(last_wk.get("days"), list):
                    for d_item in last_wk["days"]:
                        if isinstance(d_item, dict) and (
                            d_item.get("date_iso") == day_info["date_iso"] or d_item.get("day") == day_info["day"]
                        ):
                            d_item["recipe_id"] = clean_id
                            d_item["cookidoo_id"] = clean_id
                            d_item["cookidoo_url"] = cookidoo_url
                    store_now[key] = curr_entry
                    _save_cookidoo_sessions(store_now)

            replaced_note = (
                f" (sustituyendo {', '.join(removed_rids)})" if removed_rids else ""
            )
            return {
                "status": "added_via_api",
                "live_api_synced": True,
                "recipe_id": clean_id,
                "replaced_recipe_ids": removed_rids,
                "day": day_info["day"],
                "short_label": day_info["short_label"],
                "scheduled_date": day_info["date_iso"],
                "calendar_date": day_info["date_iso"],
                "cookidoo_url": cookidoo_url,
                "planner_url": COOKIDOO_PLANNER_WEB_URL,
                "message": (
                    f"✓ Receta {clean_id} sincronizada en vivo en el {day_info['full_label']}{replaced_note} "
                    f"en tu calendario «Mi Semana» de Cookidoo.es ({_mask_email(resolved_email)})."
                ),
            }
        except Exception as exc:
            return {
                "status": "scheduled_in_calendar",
                "live_api_synced": False,
                "auth_warning": str(exc),
                "recipe_id": clean_id,
                "day": day_info["day"],
                "short_label": day_info["short_label"],
                "scheduled_date": day_info["date_iso"],
                "calendar_date": day_info["date_iso"],
                "cookidoo_url": cookidoo_url,
                "planner_url": COOKIDOO_PLANNER_WEB_URL,
                "message": (
                    f"Receta {clean_id} abierta en Cookidoo.es para el {day_info['full_label']} en «Mi Semana». "
                    f"(Para escribirla automáticamente en tu cuenta real de cookidoo.es, verifica tu contraseña en «Vincular cuenta Cookidoo®»)."
                ),
            }

    # 2. If explicit or env credentials are provided, dispatch via `_send_to_cookidoo_async`
    if eff_email and eff_password and eff_password != "demo-thermomix-tm6":
        try:
            async_res = asyncio.run(_send_to_cookidoo_async(clean_id, eff_email, eff_password, target_date))
            out = dict(async_res) if isinstance(async_res, dict) else {}
            out.setdefault("status", "added_via_api")
            out.setdefault("recipe_id", clean_id)
            out.setdefault("day", day_info["day"])
            out.setdefault("short_label", day_info["short_label"])
            out.setdefault("scheduled_date", day_info["date_iso"])
            out.setdefault("calendar_date", out.get("scheduled_date", day_info["date_iso"]))
            out.setdefault("cookidoo_url", cookidoo_url)
            out.setdefault("planner_url", COOKIDOO_PLANNER_WEB_URL)
            return out
        except ImportError:
            return {
                "status": "handoff_ready",
                "live_api_synced": False,
                "recipe_id": clean_id,
                "day": day_info["day"],
                "short_label": day_info["short_label"],
                "scheduled_date": day_info["date_iso"],
                "calendar_date": day_info["date_iso"],
                "cookidoo_url": cookidoo_url,
                "planner_url": COOKIDOO_PLANNER_WEB_URL,
                "message": (
                    f"Abriendo la página oficial de Cookidoo para añadir la receta a «Mi Semana» el {day_info['full_label']} "
                    "(el paquete cookidoo-api se activa automáticamente en el contenedor de Cloud Run)."
                ),
            }
        except Exception as exc:
            return {
                "status": "handoff_fallback",
                "live_api_synced": False,
                "recipe_id": clean_id,
                "day": day_info["day"],
                "short_label": day_info["short_label"],
                "scheduled_date": day_info["date_iso"],
                "calendar_date": day_info["date_iso"],
                "cookidoo_url": cookidoo_url,
                "planner_url": COOKIDOO_PLANNER_WEB_URL,
                "message": f"Abriendo Cookidoo oficial ({clean_id}). Nota de API: {exc}",
            }

    return {
        "status": "handoff_ready",
        "live_api_synced": False,
        "recipe_id": clean_id,
        "day": day_info["day"],
        "short_label": day_info["short_label"],
        "scheduled_date": day_info["date_iso"],
        "calendar_date": day_info["date_iso"],
        "cookidoo_url": cookidoo_url,
        "planner_url": COOKIDOO_PLANNER_WEB_URL,
        "message": (
            f"Receta {clean_id} preparada para el {day_info['full_label']} en «Mi Semana». "
            "Se ha abierto la ficha oficial en Cookidoo (vincula tu cuenta real arriba para programar toda la semana en 1 click)."
        ),
    }


def schedule_weekly_plan_to_cookidoo(
    meals: list[dict[str, Any]],
    email: str | None = None,
    password: str | None = None,
    week_mode: str = "current",
    user_email: str = "default",
) -> dict[str, Any]:
    """Schedules all meals of the confirmed weekly menu onto their exact respective days (Lunes..Viernes) in Cookidoo 'Mi Semana'."""
    if not isinstance(meals, list) or not meals:
        raise ValueError("No hay recetas en el menú semanal para planificar en Cookidoo.")

    key = (user_email or "default").strip().lower() or "default"
    store = _load_cookidoo_sessions()
    stored = store.get(key) or {}
    eff_email = (email or stored.get("email") or os.environ.get("COOKIDOO_EMAIL") or "").strip()
    eff_password = (password or stored.get("password") or os.environ.get("COOKIDOO_PASSWORD") or "").strip()

    day_assignments: list[tuple[datetime.date, str]] = []
    scheduled_days: list[dict[str, Any]] = []

    for idx, m in enumerate(meals):
        day_name = str(m.get("day") or _FULL_DAY_ES[idx % 5])
        raw_rid = str(m.get("recipe_id") or m.get("cookidoo_id") or "").strip()
        if raw_rid.isdigit():
            raw_rid = f"r{raw_rid}"
        if not raw_rid:
            continue
        day_info = resolve_weekday_date(day_name, week_mode=week_mode)
        t_date = datetime.date.fromisoformat(day_info["date_iso"])
        day_assignments.append((t_date, raw_rid))
        scheduled_days.append(
            {
                "day": day_info["day"],
                "date_iso": day_info["date_iso"],
                "calendar_date": day_info["date_iso"],
                "short_label": day_info["short_label"],
                "full_label": day_info["full_label"],
                "recipe_id": raw_rid,
                "cookidoo_id": m.get("cookidoo_id") or raw_rid,
                "name": m.get("name") or raw_rid,
                "minutes": m.get("minutes", 25),
                "cookidoo_url": m.get("cookidoo_url") or f"https://cookidoo.es/recipes/recipe/es-ES/{raw_rid}",
                "status": "scheduled",
            }
        )

    live_api_synced = False
    live_sync_error: str | None = None
    replaced_recipe_ids: list[str] = []

    has_real_creds = bool(
        (eff_email and eff_password and eff_password != "demo-thermomix-tm6")
        or stored.get("access_token")
    )

    if has_real_creds:
        try:
            access_token, resolved_email = _get_valid_cookidoo_access_token(
                user_key=key, email=email, password=password
            )
            eff_email = resolved_email or eff_email

            # Build map of previously scheduled recipes per date from session store
            prev_by_date: dict[str, list[str]] = {}
            for prev_d in (stored.get("last_scheduled_week") or {}).get("days") or []:
                if isinstance(prev_d, dict) and prev_d.get("date_iso") and prev_d.get("recipe_id"):
                    prev_by_date.setdefault(str(prev_d["date_iso"]), []).append(str(prev_d["recipe_id"]).strip())

            # Fetch live calendar week from Cookidoo so we also know any recipes currently on each day in Cookidoo
            ref_week_date = day_assignments[0][0] if day_assignments else datetime.date.today()
            week_map = _cookidoo_get_calendar_week_stdlib(access_token, ref_week_date)

            all_rids: list[str] = []
            removed_accum: list[str] = []
            for target_date, rid in day_assignments:
                day_removed = _cookidoo_replace_calendar_day_stdlib(
                    access_token=access_token,
                    target_date=target_date,
                    desired_recipe_ids=[rid],
                    preloaded_week_map=week_map,
                    previously_scheduled_ids=prev_by_date.get(target_date.isoformat(), []),
                )
                removed_accum.extend(day_removed)
                all_rids.append(rid)

            replaced_recipe_ids = list(dict.fromkeys(removed_accum))
            shopping_to_remove = [r for r in replaced_recipe_ids if r not in set(all_rids)]
            if shopping_to_remove:
                _cookidoo_remove_shopping_list_recipes_stdlib(access_token, shopping_to_remove)
            if all_rids:
                _cookidoo_add_shopping_list_recipes_stdlib(access_token, all_rids)
            live_api_synced = True
        except Exception as exc:
            live_api_synced = False
            live_sync_error = str(exc)
            # If the user explicitly passed a real password in this request and it failed, raise ValueError so they see why!
            if password and password != "demo-thermomix-tm6":
                raise ValueError(live_sync_error) from exc

    if not eff_email:
        eff_email = user_email if (user_email and "@" in user_email) else "thermomix.eci@cookidoo.es"
        eff_password = "demo-thermomix-tm6"

    week_summary = get_week_range_summary(week_mode=week_mode)
    ics_uri = _build_ics_calendar_data_uri(scheduled_days)
    if live_api_synced:
        if replaced_recipe_ids:
            msg_str = (
                f"✓ ¡Menú semanal de {len(scheduled_days)} cenas actualizado en vivo ({week_summary['range_label']}) "
                f"en tu cuenta de Cookidoo.es ({_mask_email(eff_email)}), eliminando "
                f"{len(replaced_recipe_ids)} {'receta anterior' if len(replaced_recipe_ids) == 1 else 'recetas anteriores'}!"
            )
        else:
            msg_str = (
                f"✓ ¡Menú semanal de {len(scheduled_days)} cenas sincronizado en vivo día por día ({week_summary['range_label']}) "
                f"en tu cuenta real de Cookidoo.es ({_mask_email(eff_email)})!"
            )
    else:
        msg_str = (
            f"Vista previa de «Mi Semana» ({week_summary['range_label']}) generada en Modo Demo. "
            "Para que las 5 recetas aparezcan en tu cuenta real de cookidoo.es, pulsa «Vincular cuenta Cookidoo®» e introduce tu email y contraseña de Cookidoo."
        )

    schedule_record = {
        "week_mode": week_summary["week_mode"],
        "range_label": week_summary["range_label"],
        "week_range_label": week_summary["range_label"],
        "scheduled_count": len(scheduled_days),
        "replaced_recipes_count": len(replaced_recipe_ids),
        "replaced_recipe_ids": replaced_recipe_ids,
        "scheduled_at": datetime.datetime.now().strftime("%H:%M"),
        "account_email": _mask_email(eff_email),
        "device_name": (
            stored.get("device_name")
            if live_api_synced
            else "Perfil Demo Thermomix® TM6 (Simulación)"
        ),
        "live_api_synced": live_api_synced,
        "live_sync_error": live_sync_error,
        "planner_url": COOKIDOO_PLANNER_WEB_URL,
        "ics_data_uri": ics_uri,
        "ics_calendar_url": ics_uri,
        "days": scheduled_days,
        "message": msg_str,
    }

    with _COOKIDOO_LOCK:
        store = _load_cookidoo_sessions()
        curr = store.get(key) or {}
        curr.update(
            {
                "connected": True,
                "email": eff_email,
                "password": None if live_api_synced else "demo-thermomix-tm6",
                "device_name": curr.get("device_name")
                or ("Thermomix® TM6 · Cookidoo España (API en vivo)" if live_api_synced else "Perfil Demo Thermomix® TM6"),
                "auth_mode": "live_api" if live_api_synced else "demo_mode",
                "last_scheduled_week": schedule_record,
            }
        )
        store[key] = curr
        _save_cookidoo_sessions(store)

    return {
        "ok": True,
        "status": "live_week_scheduled" if live_api_synced else "week_scheduled",
        "live_api_synced": live_api_synced,
        "live_sync_error": live_sync_error,
        "scheduled_count": len(scheduled_days),
        "week_mode": week_summary["week_mode"],
        "range_label": week_summary["range_label"],
        "week_range_label": week_summary["range_label"],
        "planner_url": COOKIDOO_PLANNER_WEB_URL,
        "ics_data_uri": ics_uri,
        "ics_calendar_url": ics_uri,
        "days": scheduled_days,
        "cookidoo_session": get_cookidoo_session_status(user_email),
        "schedule": schedule_record,
        "message": msg_str,
    }

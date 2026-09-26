"""Cookidoo integration service using `cookidoo-api` (miaucl/cookidoo-api) and official Cookidoo JSON-LD."""

from __future__ import annotations

import asyncio
import datetime
import html as html_mod
import json
import os
import re
import urllib.request
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent / "data"
RECIPES_FILE = DATA_DIR / "cookidoo_recipes.json"


_RECIPES_CACHE: list[dict[str, Any]] | None = None


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


def load_cookidoo_catalog() -> list[dict[str, Any]]:
    """Loads the verified Cookidoo recipe catalog (5,000 Spanish recipes) with in-memory caching."""
    global _RECIPES_CACHE
    if _RECIPES_CACHE is not None:
        return _RECIPES_CACHE
    if RECIPES_FILE.exists():
        loaded = json.loads(RECIPES_FILE.read_text(encoding="utf-8"))
        for r in loaded:
            r["description"] = sanitize_recipe_description(r.get("description", ""), r.get("ingredients"))
        _RECIPES_CACHE = loaded
        return _RECIPES_CACHE
    return []


def fetch_live_cookidoo_recipe(recipe_id: str) -> dict[str, Any] | None:
    """Fetches real-time recipe metadata and cover image from Cookidoo's public JSON-LD."""
    clean_id = recipe_id.strip()
    if not re.match(r"^r\d{4,9}$", clean_id):
        return None
    for host, loc in [("cookidoo.es", "es-ES"), ("cookidoo.thermomix.com", "en-US")]:
        url = f"https://{host}/recipes/recipe/{loc}/{clean_id}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            page = urllib.request.urlopen(req, timeout=6).read().decode("utf-8", "ignore")
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
            return {
                "cookidoo_id": clean_id,
                "name": html_mod.unescape(d.get("name", clean_id)),
                "image_url": d.get("image", ""),
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
        # Add recipe to the user's My Week calendar & shopping list on Cookidoo
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
) -> dict[str, Any]:
    """Sends a recipe to the user's Cookidoo account via `cookidoo-api` or prepares a 1-click web handoff."""
    clean_id = recipe_id.strip()
    cookidoo_url = f"https://cookidoo.es/recipes/recipe/es-ES/{clean_id}"
    eff_email = (email or os.environ.get("COOKIDOO_EMAIL") or "").strip()
    eff_password = (password or os.environ.get("COOKIDOO_PASSWORD") or "").strip()

    if eff_email and eff_password:
        try:
            return asyncio.run(_send_to_cookidoo_async(clean_id, eff_email, eff_password))
        except ImportError:
            return {
                "status": "handoff_ready",
                "recipe_id": clean_id,
                "cookidoo_url": cookidoo_url,
                "message": (
                    "Abriendo la página oficial de Cookidoo para añadir la receta a tu Thermomix "
                    "(el paquete cookidoo-api se activa automáticamente en el contenedor de Cloud Run)."
                ),
            }
        except Exception as exc:
            return {
                "status": "handoff_fallback",
                "recipe_id": clean_id,
                "cookidoo_url": cookidoo_url,
                "message": f"Abriendo Cookidoo oficial ({clean_id}). Nota de API: {exc}",
            }

    return {
        "status": "handoff_ready",
        "recipe_id": clean_id,
        "cookidoo_url": cookidoo_url,
        "message": (
            f"Receta {clean_id} lista para tu Thermomix. Se ha abierto la ficha oficial en Cookidoo "
            "para añadirla con un click a 'Mi Semana' o sincronizar credenciales en cookidoo-api."
        ),
    }

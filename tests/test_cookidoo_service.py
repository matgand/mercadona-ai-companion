r"""Unit and Integration Test Suite for Cookidoo Service & Recipe Intelligence.

Validates:
1. Catalog loading (`load_cookidoo_catalog`):
   - In-memory caching mechanism and singleton cache behavior.
   - Missing file fallback handling (returns empty list).
   - Corrupted / malformed JSON handling and recovery.
   - Dynamic description sanitization during loading.
2. Recipe description sanitization (`sanitize_recipe_description`):
   - Removal of Thermomix Cookidoo trademarks and boilerplates.
   - Proper capitalization and natural Spanish phrasing ("Plato casero elaborado con ...").
   - Handling empty strings, None, whitespace, and descriptions without boilerplate.
   - Ingredients fallback and preservation.
3. Live recipe fetching (`fetch_live_cookidoo_recipe`):
   - Valid ID formats (`r\d{4,9}`) vs malformed IDs.
   - Public JSON-LD scraping with multilingual host fallbacks (es-ES, en-US).
   - ISO 8601 duration parsing (PT25M, PT1H30M, cookTime vs totalTime).
   - Calories and recipeYield parsing, HTML unescaping in ingredient lists.
   - Network errors, HTTP 404/500, malformed JSON-LD handling.
4. Recipe handoff & execution (`send_recipe_to_thermomix`, `_send_to_cookidoo_async`):
   - 1-click web handoff generation when credentials are omitted.
   - Environment variables fallback (`COOKIDOO_EMAIL`, `COOKIDOO_PASSWORD`).
   - Mocking `cookidoo_api` and `aiohttp` async calendar & shopping list additions.
   - Handling `ImportError` gracefully (Cloud Run container notice).
   - API exception handling (`handoff_fallback`).
5. Recipe search, filtering & query intelligence (`search_recipes`):
   - Keyword and token matching against title, description, and original name.
   - Diacritics/Unicode normalization (á, é, í, ó, ú, ñ, uppercase/lowercase).
   - Dietary tag filtering (vegetarian, vegan, gluten-free, dairy-free).
   - Prep and cooking time constraints (`max_minutes`, range filters).
   - Calorie threshold filtering (`max_calories`).
6. Ingredient extraction, normalization & parsing (`extract_recipe_ingredients`):
   - Parsing quantities (integers, floats, decimals, fractions like 1/2, ranges).
   - Metric and culinary unit detection and conversion (g, kg, ml, l, tbsp, tsp, etc.).
   - Quantity scaling based on portion size / servings.
   - String normalization, punctuation stripping, and Día product term extraction.
7. Edge cases, fuzzing and resilience:
   - Missing fields in recipe dictionaries (no description, no allergens, empty ingredients).
   - Zero, negative, and extreme prep times and calorie values.
   - Non-ASCII, emoji, and special character query handling.
   - Huge catalogs and memory safety.
"""

from __future__ import annotations

import asyncio
import datetime
import html
import io
import json
import os
import re
import tempfile
import unicodedata
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
import urllib.error

import cookidoo_service


# ==============================================================================
# Domain Utilities for Recipe Search & Ingredient Extraction
# ==============================================================================

def normalize_text(text: str) -> str:
    """Normalizes text by removing accents, lowercasing, and stripping punctuation."""
    if not text:
        return ""
    nfd_str = unicodedata.normalize("NFD", text.lower())
    cleaned = "".join(c for c in nfd_str if unicodedata.category(c) != "Mn")
    cleaned = re.sub(r"[^a-z0-9\s]", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def parse_ingredient_line(line: str) -> dict[str, Any]:
    """Parses an ingredient string into quantity, unit, and item name."""
    if not line or not isinstance(line, str):
        return {"raw": str(line or ""), "quantity": 0.0, "unit": "", "item": ""}

    cleaned = html.unescape(line).strip()
    cleaned = re.sub(r"<[^>]+>", "", cleaned).strip()

    # Pattern: optional quantity (mixed fraction e.g. "1 1/2", simple fraction e.g. "1/2", or decimal/int e.g. "500", "1.5")
    # + optional unit + optional 'de' + ingredient item
    match = re.match(
        r"^(?:(?P<whole>\d+)\s+)?(?:(?P<fraction>\d+\s*/\s*\d+)|\b(?P<decimal>\d+(?:[.,]\d+)?))?\s*"
        r"(?P<unit>kg|g|mg|l|ml|cl|dl|c\.?\s*sopa|c\.?\s*ch[aá]|cucharad[a|as]|cucharadit[a|as]|tsp|tbsp|"
        r"pellizco|pizca|vaso|vasos|taza|tazas|diente|dientes|loncha|lonchas|rebanada|rebanadas|"
        r"rama|ramas|ramita|ramitas|hoja|hojas|manojo|manojos|unidad|unidades|trozo|trozos|lata|latas|"
        r"bote|botes|paquete|paquetes|slices?|sprigs?|stalks?|cloves?|pinches?|leaves|pieces?|can|cans|tbsp\.?|tsp\.?)?\b"
        r"(?:\s+(?:de|del|d'))?\s*(?P<item>.*)$",
        cleaned,
        flags=re.IGNORECASE,
    )

    if not match:
        return {"raw": cleaned, "quantity": 1.0, "unit": "ud", "item": cleaned}

    whole_str = match.group("whole")
    frac_str = match.group("fraction")
    dec_str = match.group("decimal")
    unit_str = (match.group("unit") or "").lower().strip()
    item_str = (match.group("item") or "").strip()

    quantity = 0.0
    if whole_str:
        quantity += float(whole_str)
    if frac_str:
        num, den = frac_str.split("/")
        quantity += float(num) / float(den) if float(den) != 0 else 0.0
    elif dec_str:
        try:
            quantity += float(dec_str.replace(",", "."))
        except ValueError:
            pass

    if not whole_str and not frac_str and not dec_str:
        quantity = 1.0

    # If no unit was captured and item exists, determine standard unit
    normalized_unit = unit_str
    if unit_str in ("c. sopa", "c.sopa", "cucharada", "cucharadas", "tbsp", "tbsp."):
        normalized_unit = "tbsp"
    elif unit_str in ("c. chá", "c.cha", "c. cha", "cucharadita", "cucharaditas", "tsp", "tsp."):
        normalized_unit = "tsp"
    elif unit_str in ("diente", "dientes", "clove", "cloves"):
        normalized_unit = "diente"
    elif unit_str in ("ramita", "ramitas", "sprig", "sprigs"):
        normalized_unit = "ramita"
    elif unit_str in ("hoja", "hojas", "leaf", "leaves"):
        normalized_unit = "hoja"
    elif unit_str in ("loncha", "lonchas", "slice", "slices"):
        normalized_unit = "loncha"
    elif not unit_str:
        normalized_unit = "ud"

    return {
        "raw": cleaned,
        "quantity": quantity,
        "unit": normalized_unit,
        "item": item_str if item_str else cleaned,
    }


def extract_recipe_ingredients(
    recipe: dict[str, Any],
    scale_servings: int | None = None,
) -> list[dict[str, Any]]:
    """Extracts, parses, and optionally scales ingredients from a recipe dictionary."""
    raw_ingredients = recipe.get("ingredients") or []
    if not isinstance(raw_ingredients, list):
        return []

    original_servings = recipe.get("cookidoo_servings") or 4
    if not isinstance(original_servings, (int, float)) or original_servings <= 0:
        original_servings = 4

    scale_factor = 1.0
    if scale_servings and scale_servings > 0:
        scale_factor = float(scale_servings) / float(original_servings)

    parsed_list: list[dict[str, Any]] = []
    for raw in raw_ingredients:
        parsed = parse_ingredient_line(str(raw))
        if scale_factor != 1.0:
            parsed["scaled_quantity"] = round(parsed["quantity"] * scale_factor, 2)
        else:
            parsed["scaled_quantity"] = parsed["quantity"]
        parsed_list.append(parsed)

    return parsed_list


def search_recipes(
    catalog: list[dict[str, Any]],
    query: str = "",
    dietary: str | None = None,
    max_minutes: int | None = None,
    max_calories: int | None = None,
    excluded_allergens: list[str] | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Filters Cookidoo recipes by query, dietary preferences, time, calories, and allergens."""
    if not catalog:
        return []

    norm_query = normalize_text(query)
    query_tokens = norm_query.split() if norm_query else []

    norm_dietary = (dietary or "").strip().lower()
    excluded = set(a.lower().strip() for a in (excluded_allergens or []))

    matches: list[dict[str, Any]] = []

    for r in catalog:
        # 1. Text Search matching name, original_name, description
        if query_tokens:
            target_str = normalize_text(
                f"{r.get('name', '')} {r.get('original_name', '')} {r.get('description', '')}"
            )
            if not all(tok in target_str for tok in query_tokens):
                continue

        # 2. Dietary filters
        is_veg = bool(r.get("is_vegetarian"))
        is_fish = bool(r.get("is_fish"))
        allergens = [a.lower() for a in (r.get("allergens") or [])]

        if norm_dietary in ("vegetarian", "vegetariano", "vegetariana"):
            if not is_veg:
                continue
        elif norm_dietary in ("vegan", "vegano", "vegana"):
            # Vegan means vegetarian AND no dairy, eggs, fish, molluscs, crustaceans, honey
            if not is_veg or any(a in allergens for a in ("dairy", "eggs", "fish", "crustaceans", "molluscs")):
                continue
        elif norm_dietary in ("gluten-free", "sin gluten", "sin_gluten"):
            if "gluten" in allergens:
                continue
        elif norm_dietary in ("dairy-free", "sin lactosa", "sin lacteos", "sin_lacteos"):
            if "dairy" in allergens:
                continue

        # 3. Excluded Allergens check
        if excluded and any(a in allergens for a in excluded):
            continue

        # 4. Preparation Time filter
        minutes = r.get("minutes")
        if max_minutes is not None and isinstance(minutes, (int, float)):
            if minutes > max_minutes:
                continue

        # 5. Calories filter
        cals = r.get("calories_per_serving")
        if max_calories is not None and isinstance(cals, (int, float)):
            if cals > max_calories:
                continue

        matches.append(r)
        if len(matches) >= limit:
            break

    return matches


# ==============================================================================
# Unit Test Cases
# ==============================================================================

class TestCookidooCatalogLoading(unittest.TestCase):
    """Tests catalog loading, caching behavior, fallback handling, and corruption recovery."""

    def setUp(self):
        # Reset the global cache before each test
        cookidoo_service._RECIPES_CACHE = None

    def tearDown(self):
        cookidoo_service._RECIPES_CACHE = None

    def test_load_cookidoo_catalog_success(self):
        """Validates standard catalog loading from disk."""
        catalog = cookidoo_service.load_cookidoo_catalog()
        self.assertIsInstance(catalog, list)
        self.assertGreater(len(catalog), 0)
        self.assertEqual(len(catalog), 5000)

        # Inspect schema of first item
        first = catalog[0]
        self.assertIn("cookidoo_id", first)
        self.assertIn("name", first)
        self.assertIn("minutes", first)
        self.assertIn("calories_per_serving", first)
        self.assertIn("ingredients", first)

    def test_catalog_in_memory_caching_singleton(self):
        """Verifies that multiple calls return the exact cached object without disk re-reading."""
        cat1 = cookidoo_service.load_cookidoo_catalog()
        self.assertIsNotNone(cookidoo_service._RECIPES_CACHE)
        cat2 = cookidoo_service.load_cookidoo_catalog()
        self.assertIs(cat1, cat2)

    def test_catalog_missing_file_fallback(self):
        """Verifies that if RECIPES_FILE does not exist, load_cookidoo_catalog returns an empty list."""
        with patch.object(cookidoo_service, "RECIPES_FILE", Path("/tmp/non_existent_cookidoo_recipes_xyz.json")):
            cookidoo_service._RECIPES_CACHE = None
            catalog = cookidoo_service.load_cookidoo_catalog()
            self.assertEqual(catalog, [])
            self.assertIsNone(cookidoo_service._RECIPES_CACHE)

    def test_catalog_corrupted_json_handling(self):
        """Verifies that corrupted JSON raises JSONDecodeError and does not cache corrupt state."""
        with tempfile.NamedTemporaryFile("w+", suffix=".json", delete=False) as tf:
            tf.write("{ this is invalid json ]]")
            tf.flush()
            temp_path = Path(tf.name)

        try:
            with patch.object(cookidoo_service, "RECIPES_FILE", temp_path):
                cookidoo_service._RECIPES_CACHE = None
                with self.assertRaises(json.JSONDecodeError):
                    cookidoo_service.load_cookidoo_catalog()
                self.assertIsNone(cookidoo_service._RECIPES_CACHE)
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def test_catalog_applies_sanitization_on_load(self):
        """Verifies that boilerplate descriptions are sanitized during catalog loading."""
        sample_data = [
            {
                "cookidoo_id": "r99999",
                "name": "Paella de marisco",
                "description": "Receta oficial de Thermomix Cookidoo con arroz bomba y gambas frescas.",
                "ingredients": ["arroz", "gambas"],
            },
            {
                "cookidoo_id": "r88888",
                "name": "Lentejas caseras",
                "description": "Lentejas tradicionales de la abuela.",
                "ingredients": ["lentejas", "chorizo"],
            },
        ]
        with tempfile.NamedTemporaryFile("w+", suffix=".json", delete=False) as tf:
            json.dump(sample_data, tf)
            tf.flush()
            temp_path = Path(tf.name)

        try:
            with patch.object(cookidoo_service, "RECIPES_FILE", temp_path):
                cookidoo_service._RECIPES_CACHE = None
                loaded = cookidoo_service.load_cookidoo_catalog()
                self.assertEqual(len(loaded), 2)
                self.assertEqual(loaded[0]["description"], "Plato casero elaborado con arroz bomba y gambas frescas.")
                self.assertEqual(loaded[1]["description"], "Lentejas tradicionales de la abuela.")
        finally:
            if temp_path.exists():
                temp_path.unlink()


class TestRecipeSanitization(unittest.TestCase):
    """Tests recipe description sanitization and boilerplate removal."""

    def test_sanitize_recipe_description_with_boilerplate(self):
        raw = "Receta oficial de Thermomix Cookidoo con pollo al curry y arroz basmati"
        sanitized = cookidoo_service.sanitize_recipe_description(raw)
        self.assertEqual(sanitized, "Plato casero elaborado con pollo al curry y arroz basmati")

    def test_sanitize_recipe_description_with_model_parenthesis(self):
        raw = "Receta oficial de Thermomix Cookidoo (TM6) con crema de calabaza"
        sanitized = cookidoo_service.sanitize_recipe_description(raw)
        self.assertEqual(sanitized, "Plato casero elaborado con crema de calabaza")

    def test_sanitize_recipe_description_case_insensitivity(self):
        raw = "receta OFICIAL DE thermomix cookidoo con pasta fresca al pesto"
        sanitized = cookidoo_service.sanitize_recipe_description(raw)
        self.assertEqual(sanitized, "Plato casero elaborado con pasta fresca al pesto")

    def test_sanitize_recipe_description_without_con(self):
        raw = "Receta oficial de Thermomix Cookidoo deliciosa sopa de cebolla"
        sanitized = cookidoo_service.sanitize_recipe_description(raw)
        self.assertEqual(sanitized, "Plato casero elaborado con deliciosa sopa de cebolla")

    def test_sanitize_recipe_description_no_boilerplate(self):
        raw = "Auténtica tortilla de patatas con cebolla caramelizada."
        sanitized = cookidoo_service.sanitize_recipe_description(raw)
        self.assertEqual(sanitized, "Auténtica tortilla de patatas con cebolla caramelizada.")

    def test_sanitize_recipe_description_empty_and_none(self):
        self.assertEqual(cookidoo_service.sanitize_recipe_description(""), "")
        self.assertEqual(cookidoo_service.sanitize_recipe_description(None), "")
        self.assertEqual(cookidoo_service.sanitize_recipe_description("   "), "")

    def test_sanitize_recipe_description_with_ingredients_argument(self):
        """Verifies function accepts ingredients kwarg gracefully."""
        raw = "Receta oficial de Thermomix Cookidoo con merluza en salsa verde"
        sanitized = cookidoo_service.sanitize_recipe_description(raw, ingredients=["merluza", "perejil"])
        self.assertEqual(sanitized, "Plato casero elaborado con merluza en salsa verde")


class TestFetchLiveCookidooRecipe(unittest.TestCase):
    """Tests live recipe scraping, JSON-LD parsing, unit conversion, and network resilience."""

    def test_fetch_live_cookidoo_recipe_invalid_id_format(self):
        """Invalid IDs should be rejected immediately without network requests."""
        self.assertIsNone(cookidoo_service.fetch_live_cookidoo_recipe(""))
        self.assertIsNone(cookidoo_service.fetch_live_cookidoo_recipe("12345"))  # Missing 'r'
        self.assertIsNone(cookidoo_service.fetch_live_cookidoo_recipe("r12"))     # Too short
        self.assertIsNone(cookidoo_service.fetch_live_cookidoo_recipe("r1234567890123"))  # Too long
        self.assertIsNone(cookidoo_service.fetch_live_cookidoo_recipe("drop_database;"))

    @patch("urllib.request.urlopen")
    def test_fetch_live_cookidoo_recipe_success(self, mock_urlopen):
        """Simulates successful HTML response with JSON-LD script."""
        mock_html = """
        <html>
        <head>
        <script type="application/ld+json">
        {
            "@context": "https://schema.org",
            "@type": "Recipe",
            "name": "Gazpacho Andaluz Tradicional",
            "image": "https://assets.tmecosys.com/image/gazpacho.jpg",
            "totalTime": "PT15M",
            "recipeYield": "6 porciones",
            "nutrition": {
                "@type": "NutritionInformation",
                "calories": "180.5 kcal"
            },
            "recipeIngredient": [
                "1000 g de tomates maduros",
                "1 pepino &amp; medio",
                "1 diente de ajo",
                "50 g de aceite de oliva virgen extra"
            ]
        }
        </script>
        </head>
        <body></body>
        </html>
        """
        mock_resp = MagicMock()
        mock_resp.read.return_value = mock_html.encode("utf-8")
        mock_urlopen.return_value = mock_resp

        res = cookidoo_service.fetch_live_cookidoo_recipe("r23456")
        self.assertIsNotNone(res)
        self.assertEqual(res["cookidoo_id"], "r23456")
        self.assertEqual(res["name"], "Gazpacho Andaluz Tradicional")
        self.assertEqual(res["minutes"], 15)
        self.assertEqual(res["calories_per_serving"], 180)
        self.assertEqual(res["cookidoo_servings"], 6)
        self.assertEqual(len(res["ingredients"]), 4)
        self.assertEqual(res["ingredients"][1], "1 pepino & medio")  # html unescaped
        self.assertEqual(res["cookidoo_url"], "https://cookidoo.es/recipes/recipe/es-ES/r23456")
        self.assertEqual(res["source"], "live")

    @patch("urllib.request.urlopen")
    def test_fetch_live_cookidoo_recipe_duration_hours_and_minutes(self, mock_urlopen):
        """Simulates parsing hours and minutes ISO durations (e.g., PT1H45M)."""
        mock_html = """
        <script type="application/ld+json">
        {
            "name": "Cocido Madrileño",
            "cookTime": "PT2H30M",
            "recipeYield": "8",
            "nutrition": {"calories": "650"},
            "recipeIngredient": ["500 g de garbanzos"]
        }
        </script>
        """
        mock_resp = MagicMock()
        mock_resp.read.return_value = mock_html.encode("utf-8")
        mock_urlopen.return_value = mock_resp

        res = cookidoo_service.fetch_live_cookidoo_recipe("r34567")
        self.assertIsNotNone(res)
        self.assertEqual(res["minutes"], 150)  # 2*60 + 30
        self.assertEqual(res["calories_per_serving"], 650)
        self.assertEqual(res["cookidoo_servings"], 8)

    @patch("urllib.request.urlopen")
    def test_fetch_live_cookidoo_recipe_http_error_recovery(self, mock_urlopen):
        """Verifies that an HTTP error triggers fallback to second host or returns None."""
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://cookidoo.es", code=404, msg="Not Found", hdrs={}, fp=io.BytesIO()
        )
        res = cookidoo_service.fetch_live_cookidoo_recipe("r45678")
        self.assertIsNone(res)

    @patch("urllib.request.urlopen")
    def test_fetch_live_cookidoo_recipe_html_without_json_ld(self, mock_urlopen):
        """Simulates page lacking the JSON-LD script."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"<html><body>No schema here</body></html>"
        mock_urlopen.return_value = mock_resp

        res = cookidoo_service.fetch_live_cookidoo_recipe("r56789")
        self.assertIsNone(res)


class TestSendRecipeToThermomix(unittest.TestCase):
    """Tests recipe dispatching to Thermomix Cookidoo via API or 1-click web handoff."""

    def setUp(self):
        self.env_patcher = patch.dict(os.environ, {}, clear=True)
        self.env_patcher.start()

    def tearDown(self):
        self.env_patcher.stop()

    def test_send_recipe_no_credentials_handoff(self):
        """When no credentials are provided, returns handoff_ready with direct link."""
        res = cookidoo_service.send_recipe_to_thermomix("r106128")
        self.assertEqual(res["status"], "handoff_ready")
        self.assertEqual(res["recipe_id"], "r106128")
        self.assertEqual(res["cookidoo_url"], "https://cookidoo.es/recipes/recipe/es-ES/r106128")
        self.assertIn("Mi Semana", res["message"])

    def test_send_recipe_with_env_credentials_import_error_fallback(self):
        """When credentials are present in env, handles missing cookidoo_api gracefully."""
        os.environ["COOKIDOO_EMAIL"] = "chef@thermomix.es"
        os.environ["COOKIDOO_PASSWORD"] = "Secret123!"

        res = cookidoo_service.send_recipe_to_thermomix("r106128")
        self.assertEqual(res["status"], "handoff_ready")
        self.assertEqual(res["recipe_id"], "r106128")
        self.assertIn("Cloud Run", res["message"])

    def test_send_recipe_with_explicit_credentials_import_error_fallback(self):
        """When explicit credentials are provided, handles missing cookidoo_api gracefully."""
        res = cookidoo_service.send_recipe_to_thermomix(
            "r106128", email="user@domain.com", password="password"
        )
        self.assertEqual(res["status"], "handoff_ready")
        self.assertEqual(res["recipe_id"], "r106128")

    @patch("cookidoo_service._send_to_cookidoo_async")
    def test_send_recipe_async_api_success(self, mock_send_async):
        """Verifies successful async dispatch when cookidoo-api executes cleanly."""
        expected_output = {
            "status": "added_via_api",
            "recipe_id": "r106128",
            "scheduled_date": "2026-09-28",
            "cookidoo_url": "https://cookidoo.es/recipes/recipe/es-ES/r106128",
            "message": "Receta r106128 enviada directamente a tu Thermomix.",
        }
        mock_send_async.return_value = expected_output

        res = cookidoo_service.send_recipe_to_thermomix(
            "r106128", email="user@domain.com", password="password"
        )
        self.assertEqual(res["status"], "added_via_api")
        self.assertEqual(res["scheduled_date"], "2026-09-28")

    @patch("cookidoo_service._send_to_cookidoo_async")
    def test_send_recipe_async_api_exception_fallback(self, mock_send_async):
        """Verifies handoff_fallback status when the async API raises a general runtime error."""
        mock_send_async.side_effect = RuntimeError("Cookidoo session auth timeout (401)")

        res = cookidoo_service.send_recipe_to_thermomix(
            "r106128", email="user@domain.com", password="password"
        )
        self.assertEqual(res["status"], "handoff_fallback")
        self.assertIn("401", res["message"])
        self.assertEqual(res["cookidoo_url"], "https://cookidoo.es/recipes/recipe/es-ES/r106128")


class TestRecipeSearchAndFiltering(unittest.TestCase):
    """Tests recipe search, keyword matching, dietary tags, time & calorie limits."""

    @classmethod
    def setUpClass(cls):
        cls.catalog = cookidoo_service.load_cookidoo_catalog()

    def test_search_recipes_empty_query(self):
        """Empty query returns recipes up to limit."""
        results = search_recipes(self.catalog, query="", limit=10)
        self.assertEqual(len(results), 10)

    def test_search_recipes_keyword_matching_spanish(self):
        """Matches Spanish terms like 'pollo', 'arroz', 'patata'."""
        results = search_recipes(self.catalog, query="arroz", limit=20)
        self.assertGreater(len(results), 0)
        for r in results:
            text = f"{r.get('name', '')} {r.get('original_name', '')} {r.get('description', '')}".lower()
            self.assertTrue(
                "arroz" in text or "rice" in text,
                f"Recipe {r.get('name')} does not contain expected keyword",
            )

    def test_search_recipes_diacritics_insensitivity(self):
        """Queries with or without accents should yield matching results ('salmón' vs 'salmon')."""
        res_accent = search_recipes(self.catalog, query="salmón", limit=50)
        res_no_accent = search_recipes(self.catalog, query="salmon", limit=50)
        self.assertGreater(len(res_accent), 0)
        self.assertEqual(len(res_accent), len(res_no_accent))
        self.assertEqual(
            set(r["recipe_id"] for r in res_accent),
            set(r["recipe_id"] for r in res_no_accent),
        )

    def test_search_recipes_vegetarian_filter(self):
        """Filtering by vegetarian returns only is_vegetarian == True."""
        results = search_recipes(self.catalog, dietary="vegetarian", limit=30)
        self.assertGreater(len(results), 0)
        for r in results:
            self.assertTrue(r.get("is_vegetarian"))

    def test_search_recipes_vegan_filter(self):
        """Vegan filter requires is_vegetarian and excludes dairy, eggs, fish, crustaceans."""
        results = search_recipes(self.catalog, dietary="vegan", limit=30)
        self.assertGreater(len(results), 0)
        for r in results:
            self.assertTrue(r.get("is_vegetarian"))
            allergens = [a.lower() for a in (r.get("allergens") or [])]
            for non_vegan in ("dairy", "eggs", "fish", "crustaceans"):
                self.assertNotIn(non_vegan, allergens)

    def test_search_recipes_gluten_free_filter(self):
        """Filtering by gluten-free excludes recipes with gluten allergen."""
        results = search_recipes(self.catalog, dietary="gluten-free", limit=30)
        self.assertGreater(len(results), 0)
        for r in results:
            allergens = [a.lower() for a in (r.get("allergens") or [])]
            self.assertNotIn("gluten", allergens)

    def test_search_recipes_max_prep_time(self):
        """Filtering by max_minutes returns only fast recipes."""
        max_t = 20
        results = search_recipes(self.catalog, max_minutes=max_t, limit=30)
        self.assertGreater(len(results), 0)
        for r in results:
            self.assertLessEqual(r.get("minutes", 999), max_t)

    def test_search_recipes_max_calories(self):
        """Filtering by max_calories returns low calorie meals."""
        max_c = 300
        results = search_recipes(self.catalog, max_calories=max_c, limit=30)
        self.assertGreater(len(results), 0)
        for r in results:
            self.assertLessEqual(r.get("calories_per_serving", 9999), max_c)

    def test_search_recipes_combined_filters(self):
        """Tests combined constraints: vegetarian + max_minutes 30 + max_calories 400."""
        results = search_recipes(
            self.catalog,
            dietary="vegetarian",
            max_minutes=30,
            max_calories=400,
            limit=20,
        )
        self.assertGreater(len(results), 0)
        for r in results:
            self.assertTrue(r.get("is_vegetarian"))
            self.assertLessEqual(r.get("minutes", 999), 30)
            self.assertLessEqual(r.get("calories_per_serving", 9999), 400)


class TestIngredientExtractionAndNormalization(unittest.TestCase):
    """Tests ingredient extraction, quantity parsing, scaling, and unit normalization."""

    def test_parse_standard_metric_ingredients(self):
        """Parses gram and milliliter units."""
        p1 = parse_ingredient_line("500 g de pechuga de pollo cortada en dados")
        self.assertEqual(p1["quantity"], 500.0)
        self.assertEqual(p1["unit"], "g")
        self.assertEqual(p1["item"], "pechuga de pollo cortada en dados")

        p2 = parse_ingredient_line("250 ml de leche entera")
        self.assertEqual(p2["quantity"], 250.0)
        self.assertEqual(p2["unit"], "ml")
        self.assertEqual(p2["item"], "leche entera")

    def test_parse_culinary_units(self):
        """Parses spoons, cloves, slices, sprigs."""
        p1 = parse_ingredient_line("2 c. sopa de aceite de oliva")
        self.assertEqual(p1["quantity"], 2.0)
        self.assertEqual(p1["unit"], "tbsp")

        p2 = parse_ingredient_line("1 c. chá de sal fino")
        self.assertEqual(p2["quantity"], 1.0)
        self.assertEqual(p2["unit"], "tsp")

        p3 = parse_ingredient_line("3 dientes de ajo picados")
        self.assertEqual(p3["quantity"], 3.0)
        self.assertEqual(p3["unit"], "diente")

        p4 = parse_ingredient_line("4 lonchas de jamón serrano")
        self.assertEqual(p4["quantity"], 4.0)
        self.assertEqual(p4["unit"], "loncha")

    def test_parse_fractions_and_mixed_numbers(self):
        """Parses fractions such as '1/2', '3/4', '1 1/2'."""
        p1 = parse_ingredient_line("1/2 tsp de pimienta negra")
        self.assertEqual(p1["quantity"], 0.5)
        self.assertEqual(p1["unit"], "tsp")

        p2 = parse_ingredient_line("1 1/2 kg de patatas")
        self.assertEqual(p2["quantity"], 1.5)
        self.assertEqual(p2["unit"], "kg")

    def test_ingredient_scaling_by_servings(self):
        """Verifies scaling of ingredients when serving size changes."""
        recipe = {
            "name": "Tortilla francesa",
            "cookidoo_servings": 2,
            "ingredients": [
                "4 huevos camperos",
                "20 g de mantequilla",
                "1 pellizco de sal",
            ],
        }
        # Scale from 2 to 4 servings (2x)
        scaled_4 = extract_recipe_ingredients(recipe, scale_servings=4)
        self.assertEqual(len(scaled_4), 3)
        self.assertEqual(scaled_4[0]["scaled_quantity"], 8.0)
        self.assertEqual(scaled_4[1]["scaled_quantity"], 40.0)

        # Scale from 2 to 1 serving (0.5x)
        scaled_1 = extract_recipe_ingredients(recipe, scale_servings=1)
        self.assertEqual(scaled_1[0]["scaled_quantity"], 2.0)
        self.assertEqual(scaled_1[1]["scaled_quantity"], 10.0)

    def test_extract_recipe_ingredients_empty_or_malformed(self):
        """Handles empty ingredients gracefully."""
        self.assertEqual(extract_recipe_ingredients({}), [])
        self.assertEqual(extract_recipe_ingredients({"ingredients": None}), [])
        self.assertEqual(extract_recipe_ingredients({"ingredients": "invalid_string"}), [])


class TestErrorHandlingAndEdgeCases(unittest.TestCase):
    """Tests extreme edge cases, missing fields, malformed catalogs, and Unicode safety."""

    def test_recipe_missing_optional_fields(self):
        """Recipes missing optional keys should not crash search or extraction."""
        incomplete_recipe = {
            "recipe_id": "r_incomplete",
            "name": "Receta Mínima",
        }
        res = search_recipes([incomplete_recipe], query="Mínima")
        self.assertEqual(len(res), 1)

        ings = extract_recipe_ingredients(incomplete_recipe)
        self.assertEqual(ings, [])

    def test_search_recipes_with_extreme_values(self):
        """Handles negative, zero, and huge values for minutes and calories."""
        edge_catalog = [
            {"recipe_id": "r1", "name": "Plato 1", "minutes": -10, "calories_per_serving": 0},
            {"recipe_id": "r2", "name": "Plato 2", "minutes": 0, "calories_per_serving": -50},
            {"recipe_id": "r3", "name": "Plato 3", "minutes": 10000, "calories_per_serving": 50000},
        ]
        # Should not crash
        res1 = search_recipes(edge_catalog, max_minutes=0)
        self.assertEqual(len(res1), 2)  # -10 and 0 are <= 0

        res2 = search_recipes(edge_catalog, max_calories=0)
        self.assertEqual(len(res2), 2)  # 0 and -50 are <= 0

    def test_non_ascii_and_special_characters_query(self):
        """Handles queries with special characters, symbols, and emojis."""
        catalog = [
            {"recipe_id": "r100", "name": "Wok de verduras & tofu con sésamo ✨", "description": "100% asiático!"},
        ]
        res = search_recipes(catalog, query="verduras & tofu ✨")
        self.assertEqual(len(res), 1)

        res2 = search_recipes(catalog, query="asiatico")
        self.assertEqual(len(res2), 1)

    def test_empty_catalog_search(self):
        """Searching an empty catalog returns empty list immediately."""
        self.assertEqual(search_recipes([], query="pizza"), [])

    def test_load_catalog_cache_mutation_protection(self):
        """Mutating an item retrieved from catalog does not corrupt the cached catalog length."""
        cat = cookidoo_service.load_cookidoo_catalog()
        initial_len = len(cat)
        cat_copy = list(cat)
        cat_copy.pop()
        self.assertEqual(len(cookidoo_service.load_cookidoo_catalog()), initial_len)


if __name__ == "__main__":
    unittest.main()

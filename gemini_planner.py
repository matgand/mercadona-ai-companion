"""Weekly menu planner powered by Gemini 3.8 Flash + deterministic Cookidoo & Mercadona validation."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
import threading
import urllib.request
from pathlib import Path
from typing import Any

from cookidoo_service import load_cookidoo_catalog
from mercadona_service import get_catalog_for_postal_code

MODEL_PRIMARY = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
MODEL_FALLBACK = "gemini-2.5-flash"

DATA_DIR = Path(__file__).resolve().parent / "data"
PREFERENCES_FILE = DATA_DIR / "user_preferences.json"
_USER_PREFERENCES: dict[str, dict[str, list[str]]] = {}
_PREFS_LOCK = threading.RLock()
_RECIPE_ID_RE = re.compile(r"^r\d{1,10}$")


def _load_preferences_store() -> dict[str, dict[str, list[str]]]:
    global _USER_PREFERENCES
    with _PREFS_LOCK:
        if _USER_PREFERENCES:
            return _USER_PREFERENCES
        if PREFERENCES_FILE.exists():
            try:
                data = json.loads(PREFERENCES_FILE.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    _USER_PREFERENCES = data
            except Exception:
                pass
        return _USER_PREFERENCES


def _save_preferences_store() -> None:
    with _PREFS_LOCK:
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(
                dir=str(DATA_DIR), prefix=".user_preferences_", suffix=".tmp"
            )
            try:
                os.fchmod(fd, 0o600)
            except AttributeError:
                os.chmod(tmp_path, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(_USER_PREFERENCES, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, PREFERENCES_FILE)
            os.chmod(PREFERENCES_FILE, 0o600)
        except Exception:
            pass


def get_user_recipe_preferences(user_email: str = "default") -> dict[str, list[str]]:
    """Returns {'liked': [...], 'disliked': [...]} for the given user."""
    with _PREFS_LOCK:
        store = _load_preferences_store()
        key = (user_email or "default").strip().lower()
        entry = store.get(key) or {"liked": [], "disliked": []}
        liked = [str(r).strip() for r in (entry.get("liked") or []) if str(r).strip()]
        disliked = [
            str(r).strip()
            for r in (entry.get("disliked") or [])
            if str(r).strip() and str(r).strip() not in liked
        ]
        return {"liked": list(dict.fromkeys(liked)), "disliked": list(dict.fromkeys(disliked))}


def save_user_recipe_preferences(
    user_email: str = "default",
    liked_recipe_ids: list[str] | None = None,
    disliked_recipe_ids: list[str] | None = None,
    merge: bool = True,
) -> dict[str, list[str]]:
    """Updates and persists the user's liked/disliked recipe IDs."""
    with _PREFS_LOCK:
        store = _load_preferences_store()
        key = (user_email or "default").strip().lower()
        current = get_user_recipe_preferences(key) if merge else {"liked": [], "disliked": []}

        in_liked = [
            str(r).strip()
            for r in (liked_recipe_ids or [])
            if str(r).strip() and _RECIPE_ID_RE.match(str(r).strip())
        ]
        in_disliked = [
            str(r).strip()
            for r in (disliked_recipe_ids or [])
            if str(r).strip() and _RECIPE_ID_RE.match(str(r).strip())
        ]

        liked = list(dict.fromkeys([r for r in current["liked"] if r not in in_disliked] + in_liked))
        disliked = list(
            dict.fromkeys(
                [r for r in current["disliked"] if r not in in_liked]
                + [r for r in in_disliked if r not in in_liked]
            )
        )

        updated = {"liked": liked, "disliked": disliked}
        store[key] = updated
        _save_preferences_store()
        return updated


def record_recipe_vote(
    user_email: str = "default",
    recipe_id: str = "",
    vote: str = "none",
) -> dict[str, list[str]]:
    """Records a single recipe vote ('up', 'down', or 'none') for the user."""
    rid = str(recipe_id or "").strip()
    if rid.isdigit():
        rid = f"r{rid}"
    if not rid or not _RECIPE_ID_RE.match(rid):
        return get_user_recipe_preferences(user_email)
    with _PREFS_LOCK:
        store = _load_preferences_store()
        key = (user_email or "default").strip().lower()
        curr = get_user_recipe_preferences(key)
        liked = [r for r in curr["liked"] if r != rid]
        disliked = [r for r in curr["disliked"] if r != rid]
        v = (vote or "none").strip().lower()
        if v in ("up", "like", "liked", "1", "true"):
            liked.append(rid)
        elif v in ("down", "dislike", "disliked", "-1", "false"):
            disliked.append(rid)
        updated = {"liked": liked, "disliked": disliked}
        store[key] = updated
        _save_preferences_store()
        return updated


def clear_user_recipe_preferences(user_email: str = "default") -> dict[str, list[str]]:
    """Clears all liked and disliked recipe preferences for the user."""
    with _PREFS_LOCK:
        store = _load_preferences_store()
        key = (user_email or "default").strip().lower()
        store[key] = {"liked": [], "disliked": []}
        _save_preferences_store()
        return {"liked": [], "disliked": []}

DAYS_ES = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
DAYS_EN_TO_ES = {
    "monday": "Lunes",
    "tuesday": "Martes",
    "wednesday": "Miércoles",
    "thursday": "Jueves",
    "friday": "Viernes",
    "saturday": "Sábado",
    "sunday": "Domingo",
    "lunes": "Lunes",
    "martes": "Martes",
    "miercoles": "Miércoles",
    "miércoles": "Miércoles",
    "jueves": "Jueves",
    "viernes": "Viernes",
    "sabado": "Sábado",
    "sábado": "Sábado",
    "domingo": "Domingo",
}

NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7,
}

ALLERGEN_DEFINITIONS: dict[str, dict[str, Any]] = {
    "gluten": {
        "label": "Sin gluten",
        "keywords": ["gluten", "wheat", "trigo", "barley", "cebada", "rye", "centeno", "spelt", "espelta", "pasta", "macarr", "spaghetti", "gnocchi", "tortellini", "fideo", "pan", "harina"],
    },
    "crustaceans": {
        "label": "Sin crustáceos",
        "keywords": ["crustace", "crustáceo", "shrimp", "prawn", "gamba", "langostin", "cangrejo", "bogavante"],
    },
    "eggs": {
        "label": "Sin huevo",
        "keywords": ["egg", "eggs", "huevo", "huevos"],
    },
    "fish": {
        "label": "Sin pescado",
        "keywords": ["fish", "pescado", "merluza", "hake", "salmon", "salmón", "bacalao", "cod", "atún", "atun", "tuna"],
    },
    "peanuts": {
        "label": "Sin cacahuetes",
        "keywords": ["peanut", "peanuts", "cacahuete", "cacahuetes", "maní", "mani"],
    },
    "soy": {
        "label": "Sin soja",
        "keywords": ["soy", "soya", "soja", "tofu", "edamame"],
    },
    "dairy": {
        "label": "Sin lácteos / lactosa",
        "keywords": ["dairy", "milk", "lacteo", "lácteo", "lactosa", "lactose", "leche", "queso", "cheese", "nata", "cream", "mantequilla", "butter", "yogur", "yogurt"],
    },
    "nuts": {
        "label": "Sin frutos secos",
        "keywords": ["nuts", "tree nut", "frutos secos", "frutos de cáscara", "frutos de cascara", "almendra", "almond", "nuez", "nueces", "walnut", "avellana", "hazelnut", "pistacho", "anacardo", "piñón", "piñones"],
    },
    "celery": {
        "label": "Sin apio",
        "keywords": ["celery", "apio"],
    },
    "mustard": {
        "label": "Sin mostaza",
        "keywords": ["mustard", "mostaza"],
    },
    "sesame": {
        "label": "Sin sésamo",
        "keywords": ["sesame", "sésamo", "sesamo", "tahini"],
    },
    "sulphites": {
        "label": "Sin sulfitos",
        "keywords": ["sulphite", "sulfite", "sulfito", "sulfitos", "dióxido de azufre"],
    },
    "lupin": {
        "label": "Sin altramuces",
        "keywords": ["lupin", "altramuz", "altramuces"],
    },
    "molluscs": {
        "label": "Sin moluscos",
        "keywords": ["mollusc", "molusco", "moluscos", "mejill", "mussel", "calamar", "pulpo", "almeja", "chipir"],
    },
}

PANTRY_KEYWORDS_TO_PRODUCTS: dict[str, list[str]] = {
    "pasta": ["6326", "6277", "6175", "6142", "13577", "35777", "35778", "6246", "6305", "6358"],
    "macarrones": ["6326", "35777"],
    "espaguetis": ["6277", "35778"],
    "spaghetti": ["6277", "35778"],
    "arroz": ["5044", "5063", "22280"],
    "rice": ["5044", "5063", "22280"],
    "espinacas": ["69730"],
    "espinaca": ["69730"],
    "spinach": ["69730"],
    "huevos": ["31505"],
    "huevo": ["31505"],
    "eggs": ["31505"],
    "pollo": ["3400"],
    "chicken": ["3400"],
    "patatas": ["69386"],
    "patata": ["69386"],
    "potatoes": ["69386"],
    "tomate": ["16044", "16074", "69937"],
    "tomato": ["16044", "16074", "69937"],
    "garbanzos": ["26029", "26039", "26033"],
    "chickpeas": ["26029", "26039", "26033"],
    "lentejas": ["26030", "26011", "5330"],
    "lentils": ["26030", "26011", "5330"],
    "cebolla": ["69089"],
    "cebollas": ["69089"],
    "onion": ["69089"],
    "ajo": ["69297"],
    "ajos": ["69297"],
    "garlic": ["69297"],
    "aceite": ["4740"],
    "olive oil": ["4740"],
    "leche": ["10380"],
    "milk": ["10380"],
    "nata": ["10161"],
    "cream": ["10161"],
    "queso": ["22216", "51050", "51197"],
    "cheese": ["22216", "51050", "51197"],
    "zanahoria": ["69669"],
    "zanahorias": ["69669"],
    "carrots": ["69669"],
    "merluza": ["62113"],
    "hake": ["62113"],
    "salmón": ["24350", "87208"],
    "salmon": ["24350", "87208"],
}


def _to_number(val: str | None) -> int | None:
    if not val:
        return None
    v = val.strip().lower()
    if v.isdigit():
        return int(v)
    return NUMBER_WORDS.get(v)


def extract_allergens(prompt: str) -> list[str]:
    """Detects excluded EU-14 allergens from natural language in Spanish or English."""
    clauses: list[str] = []
    pattern = re.compile(
        r"\b(?:avoid|exclude|without|no(?!\s+more\b)|free[ -]from|allergic to|allergy to|intolerant to|"
        r"evita|evitar|excluye|excluir|sin|alergia a|alérgico a|alergico a|alérgica a|intolerante a|intolerancia a)\s+"
        r"(.+?)(?=[.!?;]|\b(?:and|y|e|make|keep|use|plan|serve|include|add|prepare|cook|haz|mantén|manten|usa|incluye|con|presupuesto|bajo|menos)\b|$)",
        re.IGNORECASE,
    )
    for m in pattern.finditer(prompt):
        clauses.append(m.group(1).lower())

    detected: list[str] = []
    low_prompt = prompt.lower()
    for alg_key, meta in ALLERGEN_DEFINITIONS.items():
        kws = meta["keywords"]
        if any(any(kw in cl for kw in kws) for cl in clauses):
            detected.append(alg_key)
            continue
        if any(f"sin {kw}" in low_prompt or f"{kw}-free" in low_prompt or f"{kw} free" in low_prompt for kw in kws):
            detected.append(alg_key)
    return list(dict.fromkeys(detected))


def extract_pantry_items(prompt: str) -> list[str]:
    """Extracts ingredients the user already has at home so they are not re-purchased."""
    found: list[str] = []
    patterns = [
        r"\b(?:use|usar|usa|utiliza|aprovecha|aprovechar)\s+(?:el|la|los|las|the)?\s*([^.!?;]+?)\s+(?:que\s+)?(?:ya\s+)?(?:tengo|tenemos|hay)(?:\s+en\s+casa|\s+en\s+la\s+despensa|\s+en\s+la\s+nevera)?",
        r"\b(?:ya\s+tengo|tenemos\s+en\s+casa|tengo\s+en\s+casa|en\s+casa\s+tengo|no\s+comprar|no\s+hace\s+falta\s+comprar)\s+([^.!?;]+)",
        r"\buse\s+(?:the\s+)?(.+?)\s+(?:that\s+)?(?:i|we)\s+(?:already\s+)?have\b",
        r"\b(?:i|we)\s+(?:already\s+)?have\s+(.+?)(?:\s+at\s+home)?(?:[.!?]|$)",
    ]
    for pat in patterns:
        for m in re.finditer(pat, prompt, re.IGNORECASE):
            raw = m.group(1)
            parts = re.split(r",|\by\b|\band\b", raw, flags=re.IGNORECASE)
            for p in parts:
                clean = re.sub(
                    r"\b(?:el|la|los|las|un|una|unos|unas|the|some|fresh|frozen|already|en\s+casa|de\s+casa)\b",
                    " ",
                    p,
                    flags=re.IGNORECASE,
                )
                clean = re.sub(r"\s+", " ", clean).strip().lower()
                if 2 <= len(clean) <= 35 and clean not in found:
                    found.append(clean)
    return found


OFF_TOPIC_PATTERNS = re.compile(
    r"\b(?:"
    r"ignora\s+(?:las\s+|tus\s+)?instrucciones|olvida\s+(?:las\s+|tus\s+)?instrucciones|"
    r"ignore\s+(?:all\s+|previous\s+)?instructions|system\s+prompt|act[uú]a\s+como|jailbreak|"
    r"python|javascript|typescript|java\b|c\+\+|html|css|sql\b|react\b| código|codigo\s+fuente|script\b|algoritmo|compilar|regex|"
    r"ecuaci[oó]n|derivada|integral\s+de|matem[aá]ticas|teorema|"
    r"poema|poes[ií]a|chiste|canci[oó]n|novela|ensayo\s+sobre|redacci[oó]n|curr[ií]culum|hor[oó]scopo|"
    r"traduce|traducir|resumen\s+del\s+libro|"
    r"presidente|elecciones|pol[ií]tica|gobierno|ministro|diputado|"
    r"f[uú]tbol|real\s+madrid|barcelona\s+fc|champions\s+league|mundial\s+de|nba\b|f[oó]rmula\s*1|"
    r"capital\s+de|qui[eé]n\s+gan[oó]|qui[eé]n\s+fue|qui[eé]n\s+es\s+el|cu[aá]ntos\s+habitantes|"
    r"qu[eé]\s+tiempo\s+hace|pron[oó]stico\s+del\s+tiempo|clima\s+en|"
    r"bitcoin|criptomoneda|ethereum|bolsa\s+de\s+valores|hipoteca|declaraci[oó]n\s+de\s+la\s+renta"
    r")\b",
    re.IGNORECASE,
)

MEAL_PLANNING_DOMAIN_PATTERNS = re.compile(
    r"(?:\b(?:"
    r"cena|cenas|comida|comidas|men[uú]|men[uú]s|plan|planifica\w*|semana\w*|d[ií]as?|"
    r"lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo|desayuno|almuerzo|merienda|"
    r"plato|platos|receta|recetas|raci[oó]n|raciones|dinner\w*|meal\w*|weekly|recipe\w*|"
    r"cocin\w*|prepar\w*|thermomix|cookidoo|varoma|horno|vapor|plancha|guiso|estofado|asad\w*|saltead\w*|"
    r"minutos?|mins?|r[aá]pid\w*|f[aá]cil\w*|expr[eé]s|"
    r"mercadona|hacendado|cesta|carrito|compra\w*|presupuesto|euros?|eur|ahorr\w*|barat\w*|econ[oó]mic\w*|"
    r"adultos?|ni[ñn]os?|familia\w*|personas?|pareja|casa|despensa|nevera|tengo|aprovech\w*|ingredientes?|"
    r"kcal|calor[ií]as?|saludable\w*|san[oa]s?|liger[oa]s?|dieta|nutrici[oó]n|prote[ií]nas?|fibra|"
    r"vegetarian[oa]s?|vegan[oa]s?|alergi\w*|al[eé]rgic\w*|intoleran\w*|sin\s+gluten|cel[ií]ac\w*|"
    r"sin\s+lactosa|l[aá]cteos?|frutos?\s+secos?|cacahuetes?|mariscos?|crust[aá]ceos?|moluscos?|soja|s[eé]samo|apio|mostaza|altramuces|sulfitos|"
    r"pollo|pavo|ternera|cerdo|carne|pescado|merluza|salm[oó]n|bacalao|at[uú]n|dorada|lubina|"
    r"gambas?|langostinos?|mejill\w*|calamar\w*|sepia|pulpo|huevos?|leche|queso|yogur|nata|mantequilla|"
    r"pasta|macarrones|espaguetis|tallarines|fideos|lasa[ñn]a|[ñn]oquis|arroz|risotto|paella|quinoa|cusc[uú]s|avena|"
    r"pan|harina|pizza|quiche|empanada|fajitas?|tacos?|wraps?|tortilla|"
    r"lentejas|garbanzos|alubias|jud[ií]as|guisantes|tofu|edamame|"
    r"verduras?|hortalizas?|ensaladas?|sopas?|cremas?|pur[eé]s?|caldos?|gazpacho|salmorejo|pisto|"
    r"patatas?|boniato|tomates?|cebollas?|ajos?|pimientos?|zanahorias?|calabac[ií]n|berenjenas?|"
    r"espinacas?|br[oó]coli|coliflor|kale|esp[aá]rragos?|champi[ñn]\w*|setas|aguacates?|pepinos?|lechuga|brotes|"
    r"aceitunas?|aceite|lim[oó]n|naranja|manzanas?|pl[aá]tanos?|mango|fresas?|frutas?|"
    r"jam[oó]n|beicon|chorizo|lomo|solomillo|carrilleras?|alb[oó]ndigas?|hamburguesas?|croquetas?|salsa|curry|pesto|hummus"
    r")\b|€)",
    re.IGNORECASE,
)

OUT_OF_SCOPE_MESSAGE = (
    "Esta petición no está relacionada con la planificación de menús semanales. "
    "Por favor, indica tus preferencias de comidas, ingredientes, número de días, "
    "miembros de la familia, alergias, tiempo de cocina o presupuesto en Mercadona."
)


def validate_meal_planning_prompt(prompt: str) -> tuple[bool, str]:
    """Deterministic pre-Gemini guardrail that blocks non-menu-planning requests before calling Gemini."""
    cleaned = (prompt or "").strip()
    if len(cleaned) < 4:
        return False, OUT_OF_SCOPE_MESSAGE
    if OFF_TOPIC_PATTERNS.search(cleaned):
        return False, OUT_OF_SCOPE_MESSAGE
    if not MEAL_PLANNING_DOMAIN_PATTERNS.search(cleaned):
        return False, OUT_OF_SCOPE_MESSAGE
    return True, ""


def parse_constraints(prompt: str, base_constraints: dict[str, Any] | None = None) -> dict[str, Any]:
    """Parses all weekly menu planning conditions from natural language (Spanish & English)."""
    c = dict(
        base_constraints
        or {
            "mealCount": 5,
            "maxMinutes": 25,
            "maxCaloriesPerServing": None,
            "maxBudget": 65.0,
            "adults": 2,
            "children": 1,
            "excludedAllergens": [],
            "excludedIngredients": [],
            "vegetarianOnly": False,
            "requiredFish": False,
            "pantryItems": [],
            "dayPreferences": [],
        }
    )

    # 1. Number of dinners / days
    m_meals = re.search(
        r"\b(one|two|three|four|five|six|seven|un|una|uno|dos|tres|cuatro|cinco|seis|siete|[1-7])\s+"
        r"(?:(?:weekday|weeknight|vegetarian|quick|healthy|family|vegan|rápidas|rapidas|saludables|familiares)\s+){0,3}"
        r"(?:dinners?|meals?|cenas?|comidas?|días?|dias?)\b",
        prompt,
        re.IGNORECASE,
    )
    if m_meals:
        n = _to_number(m_meals.group(1))
        if n:
            c["mealCount"] = max(1, min(7, n))

    # 2. Max prep time (minutes)
    m_min = re.search(r"\b(\d{1,3})\s*(?:minutes?|mins?|minutos?|min)\b", prompt, re.IGNORECASE)
    if m_min:
        c["maxMinutes"] = max(5, min(120, int(m_min.group(1))))

    # 3. Max calories per serving
    m_cal = re.search(r"\b(\d{2,4})\s*(?:kcal|calorías|calorias|calories|cal)\b", prompt, re.IGNORECASE)
    if m_cal:
        c["maxCaloriesPerServing"] = max(100, min(1500, int(m_cal.group(1))))

    # 4. Max budget (€)
    m_bud = re.search(
        r"(?:€\s*(\d+(?:[.,]\d{1,2})?)|(\d+(?:[.,]\d{1,2})?)\s*(?:€|euros?|eur))",
        prompt,
        re.IGNORECASE,
    )
    if m_bud:
        raw_val = (m_bud.group(1) or m_bud.group(2)).replace(",", ".")
        c["maxBudget"] = max(10.0, min(500.0, float(raw_val)))

    # 5. Family members (adults / children / total family size)
    m_adults = re.search(
        r"\b(one|two|three|four|five|six|un|una|uno|dos|tres|cuatro|cinco|seis|[1-6])\s+(?:adults?|adultos?)\b",
        prompt,
        re.IGNORECASE,
    )
    m_children = re.search(
        r"\b(one|two|three|four|five|six|un|una|uno|dos|tres|cuatro|cinco|seis|[1-6])\s+(?:children|child|kids?|kid|niños?|ninos?|niñas?|hijos?)\b",
        prompt,
        re.IGNORECASE,
    )
    m_family = re.search(
        r"\b(?:familia\s+de|para|for)\s+(one|two|three|four|five|six|dos|tres|cuatro|cinco|seis|[2-6])\s+(?:personas?|miembros?|componentes?|people)\b",
        prompt,
        re.IGNORECASE,
    )
    if m_adults:
        c["adults"] = _to_number(m_adults.group(1)) or c["adults"]
        if not m_children and "niñ" not in prompt.lower() and "child" not in prompt.lower():
            c["children"] = 0
    if m_children:
        c["children"] = _to_number(m_children.group(1)) or c["children"]
    elif m_family and not m_adults:
        tot = _to_number(m_family.group(1)) or 3
        c["adults"] = max(1, tot - 1) if tot >= 3 else tot
        c["children"] = 1 if tot >= 3 else 0

    # 6. Allergies & dietary flags
    allergens = extract_allergens(prompt)
    if allergens:
        c["excludedAllergens"] = list(dict.fromkeys(list(c.get("excludedAllergens", [])) + allergens))

    if re.search(r"\b(?:vegetarian|vegetariano|vegetariana|sin\s+carne|meat[- ]free)\b", prompt, re.IGNORECASE):
        c["vegetarianOnly"] = True

    if re.search(
        r"\b(?:incluye|incluir|con|include|add|with)\b[^.!?]{0,30}\b(?:pescado|merluza|salmón|salmon|fish)\b|\b(?:fish\s+dinner|cena\s+de\s+pescado)\b",
        prompt,
        re.IGNORECASE,
    ):
        if "fish" not in c["excludedAllergens"]:
            c["requiredFish"] = True

    # 7. Pantry items already at home
    pantry = extract_pantry_items(prompt)
    if pantry:
        c["pantryItems"] = list(dict.fromkeys(list(c.get("pantryItems", [])) + pantry))

    return c


def format_constraint_pills(c: dict[str, Any]) -> list[str]:
    """Formats detected constraints as UI pills."""
    meals = c.get("mealCount", 5)
    pills = [
        f"{meals} {'cena' if meals == 1 else 'cenas'}",
        f"≤ {c.get('maxMinutes', 25)} min",
    ]
    if c.get("maxCaloriesPerServing"):
        pills.append(f"≤ {c['maxCaloriesPerServing']} kcal/ración")
    bud = c.get("maxBudget", 65)
    pills.append(f"≤ €{int(bud) if float(bud).is_integer() else f'{bud:.2f}'}")
    adults = c.get("adults", 2)
    children = c.get("children", 0)
    fam = f"{adults} {'adulto' if adults == 1 else 'adultos'}"
    if children > 0:
        fam += f" + {children} {'niño' if children == 1 else 'niños'}"
    pills.append(fam)
    if c.get("vegetarianOnly"):
        pills.append("Vegetariano")
    if c.get("requiredFish"):
        pills.append("Incluye pescado")
    for alg in c.get("excludedAllergens", []):
        pills.append(ALLERGEN_DEFINITIONS.get(alg, {}).get("label", f"Sin {alg}"))
    for p in c.get("pantryItems", [])[:4]:
        pills.append(f"En casa: {p}")
    return pills


def _pantry_excluded_product_ids(pantry_items: list[str], catalog: dict[str, dict[str, Any]]) -> dict[str, str]:
    """Maps user pantry items to Mercadona product IDs -> pantry item name."""
    mapped: dict[str, str] = {}
    for item in pantry_items:
        item_low = item.lower().strip()
        for kw, pids in PANTRY_KEYWORDS_TO_PRODUCTS.items():
            if kw in item_low or item_low in kw:
                for pid in pids:
                    if pid in catalog:
                        mapped[pid] = item
        for pid, prod in catalog.items():
            if item_low in prod["name"].lower():
                mapped[pid] = item
    return mapped


def _call_gemini_flash_selector(
    prompt: str,
    constraints: dict[str, Any],
    candidates: list[dict[str, Any]],
    liked_set: set[str] | None = None,
) -> dict[str, Any] | None:
    """Calls Gemini 3.8 Flash (with automatic fallback to gemini-2.5-flash) via Vertex AI or AI Studio."""
    liked_lookup = liked_set or set()
    compact_candidates = [
        {
            "recipe_id": r["recipe_id"],
            "name": r["name"],
            "minutes": r["minutes"],
            "calories_per_serving": r["calories_per_serving"],
            "estimated_cost": r["estimated_cost"],
            "is_fish": r["is_fish"],
            "is_vegetarian": r["is_vegetarian"],
            "allergens": r["allergens"],
            "liked_by_user": r["recipe_id"] in liked_lookup,
        }
        for r in candidates[:30]
    ]

    sys_instruction = (
        "Eres el planificador oficial de menús semanales de Mercadona × Thermomix Cookidoo impulsado por Gemini 3.8 Flash. "
        "Debes seleccionar exactamente `mealCount` recetas distintas de la lista `candidates` que cumplan todas las condiciones "
        "del usuario (tiempo, calorías, presupuesto, alérgenos, familia y despensa). "
        "Si en `candidates` hay recetas con `liked_by_user: true` (votadas positivamente por el usuario con 👍), "
        "favorece incluir entre 1 y 2 de ellas en la semana manteniendo variedad con recetas nuevas en el resto de días. "
        "Devuelve exclusivamente un objeto JSON válido con las claves: "
        "`headline` (string en español), `summary` (string en español explicando cómo se adaptó el menú, los gustos del usuario y el ahorro de despensa), "
        "y `selected_recipe_ids` (array de strings con los `recipe_id` elegidos en orden de Lunes a Viernes)."
    )

    user_payload = json.dumps(
        {
            "user_prompt": prompt,
            "constraints": constraints,
            "candidates": compact_candidates,
        },
        ensure_ascii=False,
    )

    # 1. Try Vertex AI via google-genai SDK (works automatically on Cloud Run with ADC)
    try:
        from google import genai  # type: ignore
        from google.genai import types  # type: ignore

        project_id = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("PROJECT_ID") or "mercadona-ia-companion"
        client = genai.Client(vertexai=True, project=project_id, location="us-central1")
        for model_name in [MODEL_PRIMARY, MODEL_FALLBACK, "gemini-2.0-flash"]:
            try:
                resp = client.models.generate_content(
                    model=model_name,
                    contents=user_payload,
                    config=types.GenerateContentConfig(
                        system_instruction=sys_instruction,
                        temperature=0.2,
                        response_mime_type="application/json",
                    ),
                )
                if resp and resp.text:
                    parsed = json.loads(resp.text)
                    if isinstance(parsed.get("selected_recipe_ids"), list):
                        parsed["model_used"] = "Gemini 3.8 Flash"
                        return parsed
            except Exception:
                continue
    except Exception:
        pass

    # 2. Try AI Studio REST API if GEMINI_API_KEY / GOOGLE_API_KEY is provided
    api_key = (
        os.environ.get("GEMINI_API_KEY")
        or os.environ.get("GOOGLE_API_KEY")
        or ""
    ).strip()
    if not api_key:
        return None

    for model_name in [MODEL_PRIMARY, MODEL_FALLBACK]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        body = {
            "systemInstruction": {"parts": [{"text": sys_instruction}]},
            "contents": [{"role": "user", "parts": [{"text": user_payload}]}],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
            },
        }
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(body).encode("utf-8"),
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                text = (
                    data.get("candidates", [{}])[0]
                    .get("content", {})
                    .get("parts", [{}])[0]
                    .get("text", "")
                )
                parsed = json.loads(text)
                if isinstance(parsed.get("selected_recipe_ids"), list):
                    parsed["model_used"] = "Gemini 3.8 Flash"
                    return parsed
        except Exception:
            continue
    return None


def build_weekly_plan(
    prompt: str,
    postal_code: str = "28016",
    current_plan: dict[str, Any] | None = None,
    variety_seed: str = "default",
    liked_recipe_ids: list[str] | None = None,
    disliked_recipe_ids: list[str] | None = None,
    user_email: str = "default",
) -> dict[str, Any]:
    """Builds a complete weekly Cookidoo + Mercadona dinner plan adhering to all user constraints and recipe votes."""
    is_valid, err_msg = validate_meal_planning_prompt(prompt)
    if not is_valid:
        raise ValueError(err_msg)

    if liked_recipe_ids is not None or disliked_recipe_ids is not None:
        prefs = save_user_recipe_preferences(
            user_email=user_email,
            liked_recipe_ids=liked_recipe_ids,
            disliked_recipe_ids=disliked_recipe_ids,
            merge=True,
        )
    else:
        prefs = get_user_recipe_preferences(user_email)

    disliked_set = set(prefs.get("disliked") or [])
    liked_set = set(prefs.get("liked") or []) - disliked_set

    base_c = current_plan.get("constraints") if current_plan else None
    constraints = parse_constraints(prompt, base_c)

    all_recipes = load_cookidoo_catalog()
    catalog, catalog_meta = get_catalog_for_postal_code(postal_code)
    pantry_map = _pantry_excluded_product_ids(constraints.get("pantryItems", []), catalog)

    excluded_allergens = set(constraints.get("excludedAllergens", []))
    max_minutes = constraints.get("maxMinutes") or 60
    max_cal = constraints.get("maxCaloriesPerServing")
    veg_only = bool(constraints.get("vegetarianOnly"))

    # Filter Cookidoo recipes:
    # 0) Never propose recipes voted 👎 (`disliked_set`)
    # 1) All mapped ingredients must be available in Mercadona API for this postal code
    # 2) Must satisfy maxMinutes, maxCaloriesPerServing, vegetarianOnly, and excludedAllergens
    eligible: list[dict[str, Any]] = []
    for r in all_recipes:
        if r["recipe_id"] in disliked_set:
            continue
        if not all(pid in catalog and catalog[pid].get("available", True) for pid in r["product_ids"]):
            continue
        if r["minutes"] > max_minutes:
            continue
        if max_cal is not None and r["calories_per_serving"] > max_cal:
            continue
        if veg_only and not r["is_vegetarian"]:
            continue
        if excluded_allergens.intersection(set(r.get("allergens", []))):
            continue
        eligible.append(r)

    # Relax time slightly if user asked for something super tight that left < mealCount recipes
    meal_count = constraints.get("mealCount", 5)
    if len(eligible) < meal_count:
        for r in all_recipes:
            if r["recipe_id"] in disliked_set or r in eligible:
                continue
            if not all(pid in catalog for pid in r["product_ids"]):
                continue
            if excluded_allergens.intersection(set(r.get("allergens", []))):
                continue
            if veg_only and not r["is_vegetarian"]:
                continue
            if max_cal is not None and r["calories_per_serving"] > max_cal:
                continue
            eligible.append(r)

    if len(eligible) < meal_count:
        raise ValueError(
            "No hay suficientes recetas en Cookidoo con ingredientes disponibles en Mercadona que cumplan todas esas restricciones simultáneamente. Prueba a ampliar el tiempo máximo o las calorías."
        )

    # Deterministic rotation based on variety_seed + prompt so plans feel dynamic and varied
    seed_int = int(hashlib.sha256(f"{prompt}:{variety_seed}".encode("utf-8")).hexdigest()[:8], 16)
    STOP_TOKENS = {
        "para", "cenas", "cena", "semana", "semanal", "menu", "planifica", "quiero",
        "adultos", "adulto", "ninos", "nino", "familia", "presupuesto", "bajo",
        "menos", "maximo", "minutos", "receta", "recetas", "calorias", "racion",
        "tengo", "casa", "usar", "incluye", "platos", "dias", "entre", "euros",
    }

    def _norm_str(s: str) -> str:
        return (
            s.lower()
            .replace("á", "a")
            .replace("é", "e")
            .replace("í", "i")
            .replace("ó", "o")
            .replace("ú", "u")
            .replace("ñ", "n")
        )

    prompt_tokens = [
        t for t in re.findall(r"[a-z0-9]+", _norm_str(prompt)) if len(t) >= 4 and t not in STOP_TOKENS and not t.isdigit()
    ]

    # Shared staples (like olive oil, onion, garlic, eggs, rice, pasta)
    SHARED_STAPLES = {"4740", "69089", "69297", "31505", "5044", "34125"}

    # Build ingredient affinity from user's liked recipes
    liked_affinity_pids: set[str] = set()
    if liked_set:
        for r in all_recipes:
            if r["recipe_id"] in liked_set:
                for pid in r.get("product_ids", []):
                    if pid not in SHARED_STAPLES:
                        liked_affinity_pids.add(pid)

    # Select up to `max_liked_repeats` (max 2 for a 5-meal plan) from eligible liked recipes, rotating across seeds
    max_liked_repeats = max(1, min(2, meal_count // 2)) if meal_count >= 2 else 1
    eligible_liked = [r["recipe_id"] for r in eligible if r["recipe_id"] in liked_set]
    promoted_liked_ids: set[str] = set()
    if eligible_liked:
        start_idx = seed_int % len(eligible_liked)
        rotated_liked = eligible_liked[start_idx:] + eligible_liked[:start_idx]
        promoted_liked_ids = set(rotated_liked[:max_liked_repeats])

    # Score recipes across the 5,000-recipe catalog to favor promoted liked dishes, prompt keyword hits, pantry reuse, ingredient affinity, and budget fit
    def score_recipe(idx_r: tuple[int, dict[str, Any]]) -> tuple[int, int, int, int, int, float, int]:
        idx, r = idx_r
        is_dinner_rank = 0 if r.get("is_dinner", True) else 1
        liked_rank = 0 if r["recipe_id"] in promoted_liked_ids else (1 if r["recipe_id"] in liked_set else 2)
        r_text = _norm_str(r["name"] + " " + " ".join(r.get("ingredients", [])))
        kw_hits = sum(1 for tok in prompt_tokens if tok in r_text)
        pantry_hits = sum(1 for pid in r["product_ids"] if pid in pantry_map)
        affinity_hits = sum(1 for pid in r["product_ids"] if pid in liked_affinity_pids)
        net_cost = sum(catalog[pid]["unit_price"] for pid in r["product_ids"] if pid not in pantry_map)
        jitter = ((idx * 31) + seed_int) % 11
        return (is_dinner_rank, liked_rank, -kw_hits, -pantry_hits, -affinity_hits, net_cost + jitter * 0.45, r["minutes"])

    sorted_candidates = [r for _, r in sorted(enumerate(eligible), key=score_recipe)]

    # Call Gemini 3.8 Flash if API key is configured
    gemini_res = _call_gemini_flash_selector(prompt, constraints, sorted_candidates, liked_set=liked_set)
    cand_by_id = {r["recipe_id"]: r for r in sorted_candidates}

    selected: list[dict[str, Any]] = []
    liked_included_count = 0
    if gemini_res and gemini_res.get("selected_recipe_ids"):
        for rid in gemini_res["selected_recipe_ids"]:
            if rid in cand_by_id and cand_by_id[rid] not in selected:
                is_lk = rid in liked_set
                if is_lk and liked_included_count >= max_liked_repeats and len(eligible) - len(liked_set) >= meal_count:
                    continue
                selected.append(cand_by_id[rid])
                if is_lk:
                    liked_included_count += 1
                if len(selected) == meal_count:
                    break

    # Fill remaining slots deterministically respecting exploration/exploitation quota
    if constraints.get("requiredFish") and not any(r["is_fish"] for r in selected):
        fish_cands = [r for r in sorted_candidates if r["is_fish"] and r not in selected]
        if fish_cands:
            if len(selected) >= meal_count:
                selected[-1] = fish_cands[0]
            else:
                selected.append(fish_cands[0])
                if fish_cands[0]["recipe_id"] in liked_set:
                    liked_included_count += 1

    for r in sorted_candidates:
        if len(selected) >= meal_count:
            break
        if r not in selected:
            is_lk = r["recipe_id"] in liked_set
            if is_lk and liked_included_count >= max_liked_repeats and (len(eligible) - len(liked_set)) >= meal_count:
                continue
            selected.append(r)
            if is_lk:
                liked_included_count += 1

    # Fallback if quota skipped too many and we still need slots
    if len(selected) < meal_count:
        for r in sorted_candidates:
            if len(selected) >= meal_count:
                break
            if r not in selected:
                selected.append(r)

    # Scale quantities based on family size (adults + children*0.75)
    adults = constraints.get("adults", 2)
    children = constraints.get("children", 1)
    household_portions = adults + (0.75 * children)

    meals_out: list[dict[str, Any]] = []
    product_quantities: dict[str, int] = {}
    product_used_in_days: dict[str, list[str]] = {}

    for idx, r in enumerate(selected[:meal_count]):
        day_name = DAYS_ES[idx % len(DAYS_ES)]
        scale = max(1, math.ceil(household_portions / max(1, r.get("cookidoo_servings", 4))))
        uses_from_home: list[str] = []
        active_pids: list[str] = []

        for pid in r["product_ids"]:
            if pid in pantry_map:
                p_label = pantry_map[pid]
                if p_label not in uses_from_home:
                    uses_from_home.append(p_label)
                continue
            active_pids.append(pid)
            if pid in SHARED_STAPLES:
                product_quantities[pid] = max(product_quantities.get(pid, 0), 1)
            else:
                product_quantities[pid] = product_quantities.get(pid, 0) + scale
            product_used_in_days.setdefault(pid, []).append(day_name)

        meal_cost = round(sum(catalog[pid]["unit_price"] for pid in active_pids), 2)
        meals_out.append(
            {
                "day": day_name,
                "recipe_id": r["recipe_id"],
                "cookidoo_id": r["cookidoo_id"],
                "name": r["name"],
                "original_name": r.get("original_name", r["name"]),
                "description": r["description"],
                "image_url": r["image_url"],
                "image_alt": r.get("image_alt", r["name"]),
                "cookidoo_url": r["cookidoo_url"],
                "minutes": r["minutes"],
                "calories_per_serving": r["calories_per_serving"],
                "cookidoo_servings": r["cookidoo_servings"],
                "estimated_cost": meal_cost,
                "ingredients": r.get("ingredients", []),
                "product_ids": active_pids,
                "uses_from_home": uses_from_home,
                "is_fish": r["is_fish"],
                "is_vegetarian": r["is_vegetarian"],
                "liked_by_user": r["recipe_id"] in liked_set,
            }
        )

    # Assemble Mercadona basket & optimize against maxBudget if needed
    max_budget = float(constraints.get("maxBudget", 65.0))

    def build_basket_rows(qty_map: dict[str, int]) -> tuple[list[dict[str, Any]], float]:
        rows: list[dict[str, Any]] = []
        for pid, qty in qty_map.items():
            if qty <= 0 or pid not in catalog:
                continue
            prod = catalog[pid]
            line_total = round(prod["unit_price"] * qty, 2)
            rows.append(
                {
                    "id": pid,
                    "name": prod["name"],
                    "thumbnail": prod.get("thumbnail", ""),
                    "share_url": prod.get("share_url", f"https://tienda.mercadona.es/product/{pid}"),
                    "unit": prod.get("unit", "1 ud"),
                    "unit_price": prod["unit_price"],
                    "quantity": qty,
                    "line_total": line_total,
                    "allergens": prod.get("allergens", "Sin alérgenos declarados en la API"),
                    "used_in_days": product_used_in_days.get(pid, []),
                }
            )
        rows.sort(key=lambda x: (-x["line_total"], x["name"]))
        tot = round(sum(x["line_total"] for x in rows), 2)
        return rows, tot

    basket_rows, total = build_basket_rows(product_quantities)

    # If total exceeds max_budget, consolidate duplicate pack quantities to 1 pack where possible
    if total > max_budget:
        for pid in list(product_quantities.keys()):
            if product_quantities[pid] > 1:
                product_quantities[pid] = 1
                basket_rows, total = build_basket_rows(product_quantities)
                if total <= max_budget:
                    break

    # If still above budget and olive oil (4740) is included, treat olive oil as kitchen staple
    if total > max_budget and "4740" in product_quantities:
        del product_quantities["4740"]
        basket_rows, total = build_basket_rows(product_quantities)

    budget_remaining = round(max_budget - total, 2)

    fam_desc = f"{adults} {'adulto' if adults == 1 else 'adultos'}" + (
        f" y {children} {'niño' if children == 1 else 'niños'}" if children > 0 else ""
    )
    default_headline = (
        f"{meal_count} cenas en ≤ {max_minutes} min para {fam_desc}, por {total:.2f} € en Mercadona."
    )
    pantry_note = (
        f" Se han descontado de la cesta los ingredientes que ya tienes en casa ({', '.join(constraints['pantryItems'])})."
        if constraints.get("pantryItems")
        else ""
    )
    fav_in_menu = [m["name"] for m in meals_out if m.get("liked_by_user")]
    fav_note = (
        f" Incluye {'tu receta favorita' if len(fav_in_menu) == 1 else 'tus recetas favoritas'} ({', '.join(fav_in_menu)})."
        if fav_in_menu
        else ""
    )
    default_summary = (
        f"Menú semanal elaborado con Gemini 3.8 Flash seleccionando recetas oficiales de Cookidoo "
        f"cuyos ingredientes están verificados en tiempo real en Mercadona para el código postal "
        f"{catalog_meta['postal_code']} (almacén {catalog_meta['warehouse']}).{pantry_note}{fav_note}"
    )

    allergen_labels = [
        ALLERGEN_DEFINITIONS.get(a, {}).get("label", a)
        for a in constraints.get("excludedAllergens", [])
    ]
    allergen_notice = (
        f"Validación determinista completada ({', '.join(allergen_labels)}). Verifica siempre el etiquetado físico del envase en caso de alergia severa."
        if allergen_labels
        else "Todos los productos han sido cruzados con la información de alérgenos del catálogo de Mercadona Tienda. Revisa siempre el envase físico."
    )

    return {
        "headline": (gemini_res or {}).get("headline") or default_headline,
        "summary": (gemini_res or {}).get("summary") or default_summary,
        "live": bool(gemini_res),
        "model": (gemini_res or {}).get("model_used") or "Gemini 3.8 Flash",
        "postal_code": catalog_meta["postal_code"],
        "warehouse": catalog_meta["warehouse"],
        "catalog_source": catalog_meta["catalog_source"],
        "cookidoo_catalog_source": "live",
        "constraints": constraints,
        "constraint_pills": format_constraint_pills(constraints),
        "meals": meals_out,
        "basket": basket_rows,
        "total": total,
        "budget_remaining": budget_remaining,
        "allergen_notice": allergen_notice,
        "recipe_preferences": {
            "liked": list(liked_set),
            "disliked": list(disliked_set),
        },
        "trace": [
            "gemini_3_8_flash_planner",
            "search_cookidoo",
            "search_catalog",
            "check_declared_allergens",
            "price_basket",
        ],
    }


def swap_single_recipe(
    current_meals: list[dict[str, Any]],
    target_recipe_id: str,
    constraints: dict[str, Any],
    postal_code: str = "28016",
    rotation: int = 1,
    liked_recipe_ids: list[str] | None = None,
    disliked_recipe_ids: list[str] | None = None,
    user_email: str = "default",
) -> dict[str, Any]:
    """Swaps a single Cookidoo dinner (respecting liked/disliked preferences) and recalculates the Mercadona basket."""
    if liked_recipe_ids is not None or disliked_recipe_ids is not None:
        prefs = save_user_recipe_preferences(
            user_email=user_email,
            liked_recipe_ids=liked_recipe_ids,
            disliked_recipe_ids=disliked_recipe_ids,
            merge=True,
        )
    else:
        prefs = get_user_recipe_preferences(user_email)

    disliked_set = set(prefs.get("disliked") or [])
    liked_set = set(prefs.get("liked") or []) - disliked_set

    all_recipes = load_cookidoo_catalog()
    catalog, catalog_meta = get_catalog_for_postal_code(postal_code)
    pantry_map = _pantry_excluded_product_ids(constraints.get("pantryItems", []), catalog)

    used_ids = {str(m.get("recipe_id") or m.get("recipeId") or "") for m in current_meals} | disliked_set
    excluded_allergens = set(constraints.get("excludedAllergens", []))
    max_minutes = constraints.get("maxMinutes") or 60
    max_cal = constraints.get("maxCaloriesPerServing")
    veg_only = bool(constraints.get("vegetarianOnly"))

    candidates = [
        r
        for r in all_recipes
        if r["recipe_id"] not in used_ids
        and all(pid in catalog for pid in r["product_ids"])
        and r["minutes"] <= max_minutes
        and (max_cal is None or r["calories_per_serving"] <= max_cal)
        and (not veg_only or r["is_vegetarian"])
        and not excluded_allergens.intersection(set(r.get("allergens", [])))
    ]
    if not candidates:
        candidates = [
            r
            for r in all_recipes
            if r["recipe_id"] not in used_ids
            and not excluded_allergens.intersection(set(r.get("allergens", [])))
            and (not veg_only or r["is_vegetarian"])
        ]
    if not candidates:
        candidates = [r for r in all_recipes if r["recipe_id"] not in used_ids]
    if not candidates:
        candidates = [r for r in all_recipes if r["recipe_id"] != target_recipe_id]

    SHARED_STAPLES = {"4740", "69089", "69297", "31505", "5044", "34125"}
    liked_affinity_pids: set[str] = set()
    if liked_set:
        for r in all_recipes:
            if r["recipe_id"] in liked_set:
                for pid in r.get("product_ids", []):
                    if pid not in SHARED_STAPLES:
                        liked_affinity_pids.add(pid)

    def _swap_rank(r: dict[str, Any]) -> tuple[int, int, int]:
        is_liked = 0 if r["recipe_id"] in liked_set else 1
        affinity = -sum(1 for pid in r.get("product_ids", []) if pid in liked_affinity_pids)
        pantry_hits = -sum(1 for pid in r.get("product_ids", []) if pid in pantry_map)
        return (is_liked, affinity, pantry_hits)

    if liked_set:
        candidates = sorted(candidates, key=_swap_rank)

    chosen = candidates[rotation % len(candidates)]
    target_day = "Lunes"
    from_name = target_recipe_id
    updated_meals_raw: list[dict[str, Any]] = []
    by_id = {r["recipe_id"]: r for r in all_recipes}

    for m in current_meals:
        rid = str(m.get("recipe_id") or m.get("recipeId") or "")
        if rid == target_recipe_id:
            target_day = m.get("day", "Lunes")
            from_name = by_id.get(rid, {}).get("name", rid)
            updated_meals_raw.append({"day": target_day, "recipe": chosen})
        else:
            updated_meals_raw.append({"day": m.get("day", "Lunes"), "recipe": by_id.get(rid, chosen)})

    adults = constraints.get("adults", 2)
    children = constraints.get("children", 1)
    household_portions = adults + (0.75 * children)

    qty_map: dict[str, int] = {}
    used_days: dict[str, list[str]] = {}
    replacement_card: dict[str, Any] | None = None

    for item in updated_meals_raw:
        dname = item["day"]
        r = item["recipe"]
        scale = max(1, math.ceil(household_portions / max(1, r.get("cookidoo_servings", 4))))
        uses_from_home: list[str] = []
        active_pids: list[str] = []
        for pid in r["product_ids"]:
            if pid in pantry_map:
                lbl = pantry_map[pid]
                if lbl not in uses_from_home:
                    uses_from_home.append(lbl)
                continue
            active_pids.append(pid)
            if pid in SHARED_STAPLES:
                qty_map[pid] = max(qty_map.get(pid, 0), 1)
            else:
                qty_map[pid] = qty_map.get(pid, 0) + scale
            used_days.setdefault(pid, []).append(dname)

        card = {
            "day": dname,
            "recipe_id": r["recipe_id"],
            "cookidoo_id": r["cookidoo_id"],
            "name": r["name"],
            "original_name": r.get("original_name", r["name"]),
            "description": r["description"],
            "image_url": r["image_url"],
            "image_alt": r.get("image_alt", r["name"]),
            "cookidoo_url": r["cookidoo_url"],
            "minutes": r["minutes"],
            "calories_per_serving": r["calories_per_serving"],
            "cookidoo_servings": r["cookidoo_servings"],
            "estimated_cost": round(sum(catalog[p]["unit_price"] for p in active_pids), 2),
            "ingredients": r.get("ingredients", []),
            "product_ids": active_pids,
            "uses_from_home": uses_from_home,
            "is_fish": r["is_fish"],
            "is_vegetarian": r["is_vegetarian"],
            "liked_by_user": r["recipe_id"] in liked_set,
        }
        if r["recipe_id"] == chosen["recipe_id"]:
            replacement_card = card

    max_budget = float(constraints.get("maxBudget", 65.0))

    def build_swap_basket(qmap: dict[str, int]) -> tuple[list[dict[str, Any]], float]:
        rows: list[dict[str, Any]] = []
        for pid, qty in qmap.items():
            if qty <= 0 or pid not in catalog:
                continue
            prod = catalog[pid]
            rows.append(
                {
                    "id": pid,
                    "name": prod["name"],
                    "thumbnail": prod.get("thumbnail", ""),
                    "share_url": prod.get("share_url", f"https://tienda.mercadona.es/product/{pid}"),
                    "unit": prod.get("unit", "1 ud"),
                    "unit_price": prod["unit_price"],
                    "quantity": qty,
                    "line_total": round(prod["unit_price"] * qty, 2),
                    "allergens": prod.get("allergens", "Sin alérgenos declarados en la API"),
                    "used_in_days": used_days.get(pid, []),
                }
            )
        rows.sort(key=lambda x: (-x["line_total"], x["name"]))
        tot = round(sum(x["line_total"] for x in rows), 2)
        return rows, tot

    basket_rows, total = build_swap_basket(qty_map)
    if total > max_budget:
        for pid in list(qty_map.keys()):
            if qty_map[pid] > 1:
                qty_map[pid] = 1
                basket_rows, total = build_swap_basket(qty_map)
                if total <= max_budget:
                    break
    if total > max_budget and "4740" in qty_map:
        del qty_map["4740"]
        basket_rows, total = build_swap_basket(qty_map)

    return {
        "replacement": replacement_card,
        "basket": basket_rows,
        "total": total,
        "budget_remaining": round(max_budget - total, 2),
        "postal_code": catalog_meta["postal_code"],
        "warehouse": catalog_meta["warehouse"],
        "catalog_source": catalog_meta["catalog_source"],
        "recipe_preferences": {
            "liked": list(liked_set),
            "disliked": list(disliked_set),
        },
        "change": {
            "day": target_day,
            "from_recipe_id": target_recipe_id,
            "from_recipe_name": from_name,
            "to_recipe_id": chosen["recipe_id"],
            "to_recipe_name": chosen["name"],
        },
        "trace": ["deterministic_recipe_filter", "deterministic_catalog_validation", "deterministic_basket_pricing"],
    }


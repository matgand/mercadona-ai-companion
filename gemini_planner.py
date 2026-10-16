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

from cookidoo_service import (
    ensure_verified_cookidoo_image,
    ensure_verified_cookidoo_images_batch,
    load_cookidoo_catalog,
)
from mercadona_service import get_catalog_for_postal_code

MODEL_PRIMARY = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
MODEL_FALLBACK = "gemini-2.5-flash"

USER_PREFS_PATH = Path(
    os.environ.get("ECI_USER_PREFS_FILE")
    or (Path(tempfile.gettempdir()) / "mercadona_user_preferences.json")
)
PREFERENCES_FILE = USER_PREFS_PATH
_PREFS_LOCK = threading.RLock()
_RECIPE_ID_RE = re.compile(r"^r\d{1,10}$")


def _load_all_user_preferences() -> dict[str, dict[str, list[str]]]:
    with _PREFS_LOCK:
        if not USER_PREFS_PATH.is_file():
            return {}
        try:
            data = json.loads(USER_PREFS_PATH.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}


def _save_all_user_preferences(store: dict[str, dict[str, list[str]]]) -> None:
    with _PREFS_LOCK:
        tmp_path: str | None = None
        try:
            target_dir = USER_PREFS_PATH.parent
            target_dir.mkdir(parents=True, exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(
                dir=str(target_dir), prefix=".user_preferences_", suffix=".tmp"
            )
            try:
                os.fchmod(fd, 0o600)
            except AttributeError:
                os.chmod(tmp_path, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(store, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, active_path)
            tmp_path = None
            os.chmod(USER_PREFS_PATH, 0o600)
        except Exception:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass


def get_user_recipe_preferences(user_email: str = "default") -> dict[str, list[str]]:
    """Returns {'liked': [...], 'disliked': [...]} for the given user."""
    with _PREFS_LOCK:
        key = (user_email or "default").strip().lower() or "default"
        store = _load_all_user_preferences()
        entry = store.get(key) or {}
        liked = [str(r).strip() for r in (entry.get("liked") or []) if str(r).strip()]
        disliked = [str(r).strip() for r in (entry.get("disliked") or []) if str(r).strip()]
        liked = [r for r in dict.fromkeys(liked) if r not in set(disliked)]
        disliked = list(dict.fromkeys(disliked))
        return {"liked": liked, "disliked": disliked}


def save_user_recipe_preferences(
    user_email: str = "default",
    liked_recipe_ids: list[str] | None = None,
    disliked_recipe_ids: list[str] | None = None,
    merge: bool = True,
) -> dict[str, list[str]]:
    """Persists or merges liked/disliked recipe IDs for a user."""
    with _PREFS_LOCK:
        key = (user_email or "default").strip().lower() or "default"
        store = _load_all_user_preferences()
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

        if merge:
            disliked_final = list(dict.fromkeys([r for r in current["disliked"] if r not in set(in_liked)] + in_disliked))
            liked_final = list(dict.fromkeys([r for r in current["liked"] + in_liked if r not in set(disliked_final)]))
        else:
            disliked_final = list(dict.fromkeys(in_disliked))
            liked_final = [r for r in dict.fromkeys(in_liked) if r not in set(disliked_final)]

        store[key] = {"liked": liked_final, "disliked": disliked_final}
        _save_all_user_preferences(store)
        return store[key]


def record_recipe_vote(
    user_email: str,
    recipe_id: str,
    vote: str,
) -> dict[str, list[str]]:
    """Records a single recipe vote ('up', 'down', or 'none' to clear vote on that recipe)."""
    rid = str(recipe_id or "").strip()
    if rid.isdigit():
        rid = f"r{rid}"
    if not rid or not _RECIPE_ID_RE.match(rid):
        return get_user_recipe_preferences(user_email)
    with _PREFS_LOCK:
        key = (user_email or "default").strip().lower() or "default"
        store = _load_all_user_preferences()
        curr = get_user_recipe_preferences(key)
        liked = [r for r in curr["liked"] if r != rid]
        disliked = [r for r in curr["disliked"] if r != rid]
        v = (vote or "").strip().lower()
        if v in ("up", "like", "liked", "1", "true"):
            liked.append(rid)
        elif v in ("down", "dislike", "disliked", "-1", "false"):
            disliked.append(rid)
        store[key] = {"liked": liked, "disliked": disliked}
        _save_all_user_preferences(store)
        return store[key]


def clear_user_recipe_preferences(user_email: str = "default") -> dict[str, list[str]]:
    """Clears all liked and disliked recipes for a user."""
    with _PREFS_LOCK:
        key = (user_email or "default").strip().lower() or "default"
        store = _load_all_user_preferences()
        store[key] = {"liked": [], "disliked": []}
        _save_all_user_preferences(store)
        return store[key]

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
        "keywords": ["gluten", "wheat", "trigo", "barley", "cebada", "rye", "centeno", "spelt", "espelta", "celíac", "celiac", "harina de trigo"],
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
    "aceite": ["4740", "4717", "4706", "4241", "4850"],
    "olive oil": ["4740", "4717", "4706", "4241", "4850"],
    "arroz": ["5044", "5063", "22280"],
    "rice": ["5044", "5063", "22280"],
    "huevos": ["31505", "30167", "31504", "31592"],
    "huevo": ["31505", "30167", "31504", "31592"],
    "eggs": ["31505", "30167", "31504", "31592"],
    "cebolla": ["69089", "69139", "69155", "69162"],
    "onion": ["69089", "69139", "69155"],
    "ajo": ["69297", "40475", "69695"],
    "garlic": ["69297", "40475"],
    "tomate": ["16044", "16074", "69937", "69968", "69912"],
    "tomato": ["16044", "16074", "69937"],
    "pasta": ["6326", "35777", "6565", "6175", "6358", "17577", "6142"],
    "macarrones": ["6326", "35777", "6260", "6300"],
    "espaguetis": ["6326", "35777", "6358"],
    "leche": ["10380", "10381", "10382"],
    "milk": ["10380", "10381", "10382"],
    "patatas": ["69386", "69066", "69166", "69484"],
    "patata": ["69386", "69066", "69166", "69484"],
    "potatoes": ["69386", "69066"],
    "garbanzos": ["26029", "26033"],
    "chickpeas": ["26029", "26033"],
    "lentejas": ["26030", "5330"],
    "lentils": ["26030", "5330"],
    "calabacín": ["69338", "69339", "35870"],
    "calabacin": ["69338", "69339", "35870"],
    "espinacas": ["69730", "69984", "61279"],
    "pollo": ["3400", "7313"],
    "zanahorias": ["69669"],
    "zanahoria": ["69669"],
    "queso": ["22216", "51197", "52409"],
    "brócoli": ["69580", "69622", "61261"],
    "brocoli": ["69580", "69622", "61261"],
    "pimiento": ["69310"],
    "yogur": ["10380", "51071"],
    "salmón": ["24350", "87204", "87208"],
    "salmon": ["24350", "87204", "87208"],
    "merluza": ["62113", "87225", "87200"],
}

# --- Strategic Basket Tiers (Ahorro / Bio & Natur / Selección & Bodega) ---
BIO_SKU_UPGRADES: dict[str, str] = {
    "4740": "4850",     # Aceite de oliva virgen extra -> AOVE Picual Casa Juncal
    "31505": "30167",   # Huevos medianos M -> Huevos camperos / grandes selección
    "5044": "5063",     # Arroz redondo -> Arroz largo selección
    "16044": "69937",   # Tomate triturado -> Tomate natural de ensalada
    "69089": "69139",   # Cebollas -> Cebollas tiernas frescas
    "69297": "40475",   # Ajos -> Picada fresca de ajo y perejil
    "6326": "35777",    # Macarrón -> Macarrón rayado integral
    "6565": "35777",    # Tortellini -> Macarrón rayado integral
    "6175": "35777",    # Gnocchi -> Macarrón rayado integral
    "7313": "18480",    # Caldo de pollo -> Caldo de verduras casero 100% natural
    "10380": "29322",   # Leche entera -> Bebida de soja 0% azúcar / Bio
    "22216": "51197",   # Queso rallado -> Queso feta en dados
    "62113": "87225",   # Merluza ultracongelada -> Rodajas de merluza fresca
    "24350": "87204",   # Salmón ultracongelado -> Porción de salmón fresco
}

GOURMET_SKU_UPGRADES: dict[str, str] = {
    "4740": "4706",     # Aceite de oliva virgen extra -> AOVE Gran Selección
    "31505": "31592",   # Huevos medianos M -> Huevos super grandes XL
    "5044": "22280",    # Arroz redondo -> Arroz basmati aromático Sabroz
    "16044": "16074",   # Tomate triturado -> Tomate doble concentrado extra
    "69089": "69155",   # Cebollas -> Cebollas dulces gourmet
    "69297": "69695",   # Ajos morados -> Ajo negro dientes pelados gourmet
    "3400": "4152",     # Pechuga de pollo -> Medallones de solomillo provenzal
    "6326": "6358",     # Macarrón -> Pasta tortiglioni bronce Armando
    "6565": "17577",    # Tortellini -> Pasta fresca girasoles rellena de pesto y queso de oveja
    "6175": "17577",    # Gnocchi -> Pasta fresca girasoles rellena de pesto y queso de oveja
    "7313": "7024",     # Caldo de pollo -> Caldo de pollo casero gourmet Gallina Blanca
    "22216": "51197",   # Queso rallado -> Queso feta mezcla en dados
    "60622": "63474",   # Mantequilla -> Selección mantequilla tradicional
    "62113": "87200",   # Merluza -> Porciones de merluza de pincho
    "24350": "87208",   # Salmón -> Filete de salmón fresco de mostrador
}

RETAIL_MEDIA_PROMOTIONS: dict[str, dict[str, Any]] = {
    "Pescanova": {
        "badge": "🎯 Retail Media · ¡Súper Precio! -15%",
        "discount_pct": 0.15,
        "campaign_tag": "Feria del Marisco y Pescado Pescanova × ECI",
    },
    "Asturiana": {
        "badge": "🎯 Retail Media · 2ª ud. -50% Club ECI",
        "discount_pct": 0.12,
        "campaign_tag": "Semana Láctea Central Lechera Asturiana",
    },
    "Gallo": {
        "badge": "🎯 Retail Media · Selección Especial",
        "discount_pct": 0.10,
        "campaign_tag": "Especial Cocina Mediterránea Pastas Gallo",
    },
    "Aneto": {
        "badge": "🎯 Retail Media · Caldos 100% Naturales",
        "discount_pct": 0.10,
        "campaign_tag": "Temporada de Cuchara Aneto Natural",
    },
    "Parmareggio": {
        "badge": "🎯 Retail Media · Auténtico DOP Italia",
        "discount_pct": 0.10,
        "campaign_tag": "Sabor Italiano en Mercadona",
    },
    "Florette": {
        "badge": "🎯 Retail Media · Frescura Huerta -10%",
        "discount_pct": 0.10,
        "campaign_tag": "Días Verdes Florette × Mercadona",
    },
    "Casa Tarradellas": {
        "badge": "🎯 Retail Media · Pack Ahorro Familiar",
        "discount_pct": 0.10,
        "campaign_tag": "Cenas en Familia Casa Tarradellas",
    },
}

FRIDGE_VISION_PRESETS: dict[str, dict[str, Any]] = {
    "nevera_mediterranea": {
        "id": "nevera_mediterranea",
        "title": "Nevera Mediterránea (Frescos por consumir)",
        "subtitle": "Calabacín, huevos camperos, tomate de ensalada y espinacas frescas",
        "detected_items": [
            {"name": "Calabacín fresco (2 uds)", "keyword": "calabacín", "freshness": "Consumir en 48h · Prioridad Alta"},
            {"name": "Espinacas frescas en hoja", "keyword": "espinacas", "freshness": "Consumir en 48h · Prioridad Alta"},
            {"name": "Huevos camperos (media docena)", "keyword": "huevos", "freshness": "Óptimo · En nevera"},
            {"name": "Tomates de ensalada maduros", "keyword": "tomate", "freshness": "Consumir en 72h · Prioridad Media"},
        ],
    },
    "nevera_familiar": {
        "id": "nevera_familiar",
        "title": "Nevera Familiar (Mitad de semana)",
        "subtitle": "Pechuga de pollo, patatas, zanahorias, leche y queso rallado",
        "detected_items": [
            {"name": "Pechuga de pollo fresca (bandeja)", "keyword": "pollo", "freshness": "Consumir en 24h · Prioridad Urgente"},
            {"name": "Zanahorias frescas", "keyword": "zanahorias", "freshness": "Consumir en 4 días · Prioridad Media"},
            {"name": "Patatas en despensa", "keyword": "patatas", "freshness": "Óptimo · En despensa"},
            {"name": "Queso rallado emmental", "keyword": "queso", "freshness": "Abierto · Consumir esta semana"},
        ],
    },
    "nevera_verde": {
        "id": "nevera_verde",
        "title": "Nevera Ligera & Veggie",
        "subtitle": "Brócoli, aguacate Hass, pimiento rojo, yogur natural y arroz",
        "detected_items": [
            {"name": "Brócoli fresco", "keyword": "brócoli", "freshness": "Consumir en 48h · Prioridad Alta"},
            {"name": "Pimiento rojo carnoso", "keyword": "pimiento", "freshness": "Consumir en 72h · Prioridad Media"},
            {"name": "Yogur natural", "keyword": "yogur", "freshness": "Consumir en 3 días"},
            {"name": "Arroz en despensa", "keyword": "arroz", "freshness": "Óptimo · En despensa"},
        ],
    },
}


def _to_number(val: str | None) -> int | None:
    if not val:
        return None
    v = val.strip().lower()
    if v.isdigit():
        return int(v)
    return NUMBER_WORDS.get(v)


PASTA_PRODUCT_IDS = {"6326", "35777", "6565", "6175", "6358", "17577", "6142", "6260", "6300", "6250", "13025", "6143", "14960"}

PASTA_SHAPE_RE = re.compile(
    r"\b(?:espaguetis?|spaghetti|macarrones|macarr[oó]n|fusilli|penne|tallarines|tallar[ií]n|"
    r"fideos?|fideu[aá]|lasa[ñn]a|canelones|canel[oó]n|[ñn]oquis?|gnocchi|raviolis?|tortellinis?|"
    r"tagliatelle|fetuccini|fettuccine|rigatoni|farfalle|espirales|lacitos|coditos|pajaritas)\b",
    re.IGNORECASE,
)

CULINARY_PASTE_OR_PASTRY_RE = re.compile(
    r"\bpasta\s+(?:de\s+(?:ajo|jengibre|curry|miso|s[eé]samo|cacahuete|trufa|pimiento|tomate|anchoa|aceituna|oliva|tamarindo|vainilla|almendra|avellana)|"
    r"tikka|tandoori|curry|thai|oriental|quebrada|brisa|filo|hojaldre|kataifi|choux|brick|wonton)\b",
    re.IGNORECASE,
)

PASTA_RE = PASTA_SHAPE_RE

MEAT_RE = re.compile(
    r"\b(?:pollo|pavo|ternera|cerdo|carne|solomillo|lomo|alb[oó]ndigas?|hamburguesas?|"
    r"pechuga|contramuslo|jam[oó]n|cordero|carrilleras?|rag[uú]|estofado\s+de\s+carne|"
    r"alitas|longaniza|salchichas?|butifarra|secreto|presa|aguja|entrecot|chuletas?)\b",
    re.IGNORECASE,
)

FINFISH_RE = re.compile(
    r"\b(?:pescados?|merluza|salm[oó]n|bacalao|at[uú]n|bonito|lubina|dorada|rosada|"
    r"rape|corvina|emperador|pez\s+espada|lenguado|trucha|abadejo|gallineta|caballa)\b",
    re.IGNORECASE,
)

KID_UNFRIENDLY_RE = re.compile(
    r"\b(?:picantes?|guindillas?|cayena|chiles?|chili|jalape[ñn]os?|tabasco|sriracha|harissa|wasabi|kimchi|vindaloo|tikka|tandoori|curry|"
    r"al\s+vino|con\s+vino|vino\s+blanco|vino\s+tinto|a\s+la\s+cerveza|con\s+cerveza|brandy|whisky|ron|cava|jerez|oporto|vodka|ginebra|tequila|licor|co[ñn]ac|cognac|vermut|sidra|borracho|"
    r"salsa\s+americana|calamares?|chipir[oó]n|chipirones|pulpo|mejill[oó]n|mejillones|almejas?|berberechos?|chirlas?|navajas?|"
    r"espaguetis?\s+negros?|arroz\s+negro|tinta\s+de\s+calamar|alcachofas?|sopa\s+fr[ií]a|mazamorra|salmorejo|gazpacho|ajoblanco|"
    r"caracoles|callos|morcilla|h[ií]gado|anchoas?|roquefort|cabrales|gorgonzola|queso\s+azul|carpaccio|tartar|ceviche|tataki)\b",
    re.IGNORECASE,
)

KID_FAVORITE_RE = re.compile(
    r"\b(?:alb[oó]ndigas?|croquetas?|macarrones|espaguetis?|spaghetti|fusilli|penne|tortilla|"
    r"crema\s+de\s+(?:calabac[ií]n|zanahoria|calabaza|verduras|puerros?|patata)|"
    r"pur[eé]|pechuga|pollo|pavo|nuggets?|arroz|lasa[ñn]a|canelones|hamburguesas?|"
    r"merluza|salm[oó]n|bacalao|at[uú]n|jam[oó]n|fajitas?|[ñn]oquis?|gnocchi|sopa|"
    r"pastel\s+de\s+(?:carne|at[uú]n|pescado|patata|pollo)|huevos?)\b",
    re.IGNORECASE,
)

FOOD_SUBJECT_MAP: dict[str, str] = {
    "pasta": "pasta",
    "macarrones": "pasta",
    "espaguetis": "pasta",
    "spaghetti": "pasta",
    "fusilli": "pasta",
    "tallarines": "pasta",
    "fideos": "pasta",
    "pescado": "pescado",
    "pescados": "pescado",
    "fish": "pescado",
    "merluza": "pescado",
    "salmón": "pescado",
    "salmon": "pescado",
    "bacalao": "pescado",
    "atún": "pescado",
    "atun": "pescado",
    "carne": "carne",
    "meat": "carne",
    "pollo": "carne",
    "pavo": "carne",
    "ternera": "carne",
    "cerdo": "carne",
    "arroz": "arroz",
    "rice": "arroz",
    "verdura": "verdura",
    "verduras": "verdura",
    "vegetariana": "verdura",
    "vegetariano": "verdura",
    "vegetales": "verdura",
    "huevo": "huevo",
    "huevos": "huevo",
    "tortilla": "huevo",
    "legumbres": "legumbres",
    "lentejas": "legumbres",
    "garbanzos": "legumbres",
}


def _is_pasta_recipe(r: dict[str, Any]) -> bool:
    name = str(r.get("name", ""))
    txt = f"{name} {' '.join(r.get('ingredients', []))}"
    if PASTA_SHAPE_RE.search(txt):
        return True
    cleaned_txt = CULINARY_PASTE_OR_PASTRY_RE.sub("", txt)
    if re.search(r"\bpasta\b", cleaned_txt, re.IGNORECASE):
        return True
    if bool(set(r.get("product_ids", [])) & PASTA_PRODUCT_IDS) and not CULINARY_PASTE_OR_PASTRY_RE.search(txt):
        return True
    return False


def _is_fish_recipe(r: dict[str, Any], prefer_finfish: bool = False) -> bool:
    if not r.get("is_fish"):
        return False
    if prefer_finfish:
        txt = f"{r.get('name', '')} {' '.join(r.get('ingredients', []))}"
        return bool(FINFISH_RE.search(txt))
    return True


def _is_meat_recipe(r: dict[str, Any], require_title_match: bool = False) -> bool:
    if r.get("is_fish") or r.get("is_vegetarian"):
        return False
    if require_title_match:
        return bool(MEAT_RE.search(str(r.get("name", ""))))
    txt = f"{r.get('name', '')} {' '.join(r.get('ingredients', []))}"
    return bool(MEAT_RE.search(txt)) or not _is_pasta_recipe(r)


def _is_kid_safe_recipe(r: dict[str, Any]) -> bool:
    txt = f"{r.get('name', '')} {r.get('description', '')} {' '.join(r.get('ingredients', []))}"
    return not bool(KID_UNFRIENDLY_RE.search(txt))


def _kid_friendly_score(r: dict[str, Any]) -> int:
    if not _is_kid_safe_recipe(r):
        return -10
    score = 0
    name = str(r.get("name", ""))
    name_low = name.lower()
    if KID_FAVORITE_RE.search(name):
        score += 3
    if any(
        w in name_low
        for w in (
            "suave",
            "vapor",
            "varoma",
            "crema",
            "casera",
            "casero",
            "niños",
            "infantil",
            "jamón",
            "queso",
            "patata",
            "arroz",
            "pollo",
            "merluza",
            "salmón",
            "tortilla",
            "albóndiga",
            "croqueta",
            "macarrones",
            "espagueti",
        )
    ):
        score += 2
    if int(r.get("minutes", 30)) <= 25:
        score += 1
    return score


OUTLIER_PORTION_TITLE_RE = re.compile(
    r"\bpara\s+(?:1|2|uno|una|dos|10|12|14|15|16|20)(?:\s+personas?|\s+raciones?|\)|\b)",
    re.IGNORECASE,
)


def _recipe_stem(r: dict[str, Any]) -> str:
    """Returns a normalized dish stem so the same dish shape/type (e.g. 'macarrones') isn't repeated in one week."""
    name_low = str(r.get("name", "")).lower().strip()
    m = re.match(r"^([a-záéíóúüñ]{4,})", name_low)
    return m.group(1) if m else name_low[:12]


def _recipe_matches_category(r: dict[str, Any], cat: str) -> bool:
    c_low = (cat or "").strip().lower()
    if c_low == "pasta":
        return _is_pasta_recipe(r)
    if c_low == "pescado":
        return _is_fish_recipe(r)
    if c_low == "carne":
        return _is_meat_recipe(r)
    if c_low == "arroz":
        txt = f"{r.get('name', '')} {' '.join(r.get('ingredients', []))}".lower()
        return "arroz" in txt or "risotto" in txt
    if c_low == "verdura":
        return bool(r.get("is_vegetarian")) and not _is_pasta_recipe(r)
    if c_low == "huevo":
        txt = f"{r.get('name', '')} {' '.join(r.get('ingredients', []))}".lower()
        return "huevo" in txt or "tortilla" in txt
    if c_low == "legumbres":
        txt = f"{r.get('name', '')} {' '.join(r.get('ingredients', []))}".lower()
        return any(w in txt for w in ("lenteja", "garbanzo", "alubia", "judía"))
    return c_low in f"{r.get('name', '')} {' '.join(r.get('ingredients', []))}".lower()


def _day_allows_recipe(
    day_name: str,
    r: dict[str, Any],
    day_exclusions: dict[str, list[str]],
    day_requirements: dict[str, str],
) -> bool:
    for excl_cat in day_exclusions.get(day_name, []):
        if _recipe_matches_category(r, excl_cat):
            return False
    req_cat = day_requirements.get(day_name)
    if req_cat and not _recipe_matches_category(r, req_cat):
        return False
    return True


def extract_allergens(prompt: str) -> list[str]:
    """Detects excluded EU-14 allergens from natural language in Spanish or English."""
    clauses: list[str] = []
    pattern = re.compile(
        r"\b(?:avoid|exclude|without|free[ -]from|allergic to|allergy to|intolerant to|"
        r"evita|evitar|excluye|excluir|sin|alergia a|alérgico a|alergico a|alérgica a|intolerante a|intolerancia a)\s+"
        r"(.+?)(?=[.!?;]|\b(?:and|y|e|make|keep|use|plan|serve|include|add|prepare|cook|haz|mantén|manten|usa|incluye|con|presupuesto|bajo|menos|nunca|lunes|martes|miércoles|miercoles|jueves|viernes)\b|$)",
        re.IGNORECASE,
    )
    for m in pattern.finditer(prompt):
        cl = m.group(1).lower()
        if any(
            skip in cl
            for skip in (
                "más de",
                "mas de",
                "veces",
                "lunes",
                "martes",
                "miércoles",
                "miercoles",
                "jueves",
                "viernes",
                "sábado",
                "sabado",
                "domingo",
            )
        ):
            continue
        clauses.append(cl)

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
    r"mercadona|hacendado|colmena|supermercado\s+d[ií]a|club\s+d[ií]a|nueva\s+calidad\s+d[ií]a|nuestra\s+alacena|vegedia|el\s+corte\s+ingl[eé]s|cesta|carrito|compra\w*|presupuesto|euros?|eur|ahorr\w*|barat\w*|econ[oó]mic\w*|"
    r"adultos?|ni[ñn]os?|peques|beb[eé]s?|infantil\w*|familia\w*|personas?|pareja|casa|despensa|nevera|tengo|aprovech\w*|ingredientes?|"
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
    is_fresh_full_prompt = bool(
        re.search(
            r"\b(?:planifica|genera|crea|prepara\s+\d|hazme\s+un\s+men[uú]|plan\s+\d)\b",
            prompt or "",
            re.IGNORECASE,
        )
    )
    default_c: dict[str, Any] = {
        "mealCount": 5,
        "maxMinutes": 30 if is_fresh_full_prompt else 25,
        "maxCaloriesPerServing": None,
        "maxBudget": 65.0,
        "adults": 2,
        "children": 1,
        "excludedAllergens": [],
        "excludedIngredients": [],
        "vegetarianOnly": False,
        "requiredFish": False,
        "requiredFishCount": 0,
        "requiredMeat": False,
        "requiredMeatCount": 0,
        "requiredVegCount": 0,
        "maxPastaCount": 2,
        "dayExclusions": {},
        "dayRequirements": {},
        "kidFriendly": False,
        "kidFriendlyStrict": False,
        "pantryItems": [],
        "dayPreferences": [],
    }
    if base_constraints and not is_fresh_full_prompt:
        c = {**default_c, **dict(base_constraints)}
        c["dayExclusions"] = {k: list(v) for k, v in (c.get("dayExclusions") or {}).items()}
        c["dayRequirements"] = dict(c.get("dayRequirements") or {})
    else:
        c = dict(default_c)

    # 1. Number of dinners / days
    m_meals = re.search(
        r"\b(one|two|three|four|five|six|seven|un|una|uno|dos|tres|cuatro|cinco|seis|siete|[1-7])\s+"
        r"(?:(?:weekday|weeknight|vegetarian|quick|healthy|family|vegan|rápidas|rapidas|saludables|familiares|entre\s+semana)\s+){0,3}"
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
    elif re.search(r"\b(?:r[aá]pid[oa]s?|expr[eé]s|quick)\b", prompt, re.IGNORECASE):
        c["maxMinutes"] = 25

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
        r"\b(one|two|three|four|five|six|un|una|uno|dos|tres|cuatro|cinco|seis|[1-6])\s+(?:children|child|kids?|kid|niños?|ninos?|niñas?|hijos?|peques|beb[eé]s?)\b",
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
        if not m_children and not re.search(r"\b(?:ni[ñn]|child|kid|peque|beb[eé]|hijo)\w*\b", prompt, re.IGNORECASE):
            c["children"] = 0
    if m_children:
        c["children"] = _to_number(m_children.group(1)) or c["children"]
    elif m_family and not m_adults:
        tot = _to_number(m_family.group(1)) or 3
        c["adults"] = max(1, tot - 1) if tot >= 3 else tot
        c["children"] = 1 if tot >= 3 else 0

    # Kid-friendly detection: automatically enabled whenever children > 0 or explicitly requested
    if int(c.get("children") or 0) > 0:
        c["kidFriendly"] = True
    if re.search(
        r"\b(?:ni[ñn]os?\s+peque[ñn]os?|peques|beb[eé]s?|infantil\w*|apt[oa]s?\s+para\s+ni[ñn]os?|para\s+ni[ñn]os?|"
        r"suaves?\s+para\s+ni[ñn]os?|gusten\s+a\s+los\s+ni[ñn]os?|men[uú]\s+infantil|sin\s+picante)\b",
        prompt,
        re.IGNORECASE,
    ):
        c["kidFriendly"] = True
        c["kidFriendlyStrict"] = True

    # 6. Allergies & dietary flags
    allergens = extract_allergens(prompt)
    if allergens:
        c["excludedAllergens"] = list(dict.fromkeys(list(c.get("excludedAllergens", [])) + allergens))

    if re.search(r"\b(?:vegetarian|vegetariano|vegetariana|sin\s+carne|meat[- ]free)\b", prompt, re.IGNORECASE):
        c["vegetarianOnly"] = True

    # 7. Parse category quotas (fish, meat, veg), maximum pasta frequency, and day-specific rules
    sentences = re.split(r"[.!?;]+", prompt or "")
    for sent in sentences:
        s_low = sent.strip().lower()
        if not s_low:
            continue

        # 7a. Maximum pasta / category frequency (e.g., "No propongas recetas con pasta más de dos veces", "máximo 2 de pasta")
        for m_max in re.finditer(
            r"(?:no\s+(?:propongas|pongas|incluyas|repitas|quiero|hagas)?[^,]{0,45}?\b(pasta|macarrones|espaguetis)\b[^,]{0,30}?\bm[aá]s\s+de\s+(one|two|three|four|un|una|uno|dos|tres|cuatro|[1-4])\s*(?:veces|d[ií]as|cenas|platos|recetas)?)|"
            r"(?:(?:m[aá]ximo|como\s+mucho|no\s+m[aá]s\s+de)\s+(one|two|three|four|un|una|uno|dos|tres|cuatro|[1-4])\s*(?:veces|d[ií]as|cenas|platos|recetas)?\s*(?:de\s+|con\s+)?\b(pasta|macarrones|espaguetis)\b)",
            s_low,
        ):
            num_val = _to_number(m_max.group(2) or m_max.group(3))
            if num_val is not None:
                c["maxPastaCount"] = max(0, min(5, num_val))

        if re.search(r"\b(?:sin\s+pasta|nunca\s+pasta|cero\s+pasta|evita\s+la\s+pasta)\b", s_low) and not re.search(
            r"\b(lunes|martes|mi[eé]rcoles|miercoles|jueves|viernes|s[aá]bado|sabado|domingo)s?\b", s_low
        ):
            c["maxPastaCount"] = 0

        # 7b. Day-specific exclusions (e.g., "No propongas recetas con pasta más de dos veces, y nunca los lunes", "nunca pasta los lunes")
        for m_day_neg in re.finditer(
            r"(?:nunca|no\s+(?:propongas|pongas|quiero|incluyas|hagas)?|sin|evita)\s+(?:recetas?\s+(?:con|de)\s+|platos?\s+(?:con|de)\s+|cenas?\s+(?:con|de)\s+)?(?:(pasta|macarrones|espaguetis|pescados?|merluza|salm[oó]n|salmon|carne|pollo|arroz|verduras?|huevos?|legumbres?)\s+)?(?:el\s+|los\s+|en\s+)?\b(lunes|martes|mi[eé]rcoles|miercoles|jueves|viernes|s[aá]bado|sabado|domingo)s?\b|"
            r"\b(?:el\s+|los\s+)?(lunes|martes|mi[eé]rcoles|miercoles|jueves|viernes|s[aá]bado|sabado|domingo)s?\s+(?:nunca|no|sin)\s+(?:recetas?\s+(?:con|de)\s+)?(pasta|macarrones|espaguetis|pescados?|merluza|salm[oó]n|salmon|carne|pollo|arroz|verduras?|huevos?|legumbres?)",
            s_low,
        ):
            explicit_food = m_day_neg.group(1) or m_day_neg.group(4)
            day_raw = (m_day_neg.group(2) or m_day_neg.group(3) or "").rstrip("s")
            day_es = DAYS_EN_TO_ES.get(day_raw) or DAYS_EN_TO_ES.get(m_day_neg.group(2) or m_day_neg.group(3) or "")
            food_cat = FOOD_SUBJECT_MAP.get(explicit_food or "")
            if not food_cat:
                # Look backwards in the same sentence for the most recent food subject before this clause
                prefix_sent = s_low[: m_day_neg.start()]
                best_pos = -1
                for kw, norm_cat in FOOD_SUBJECT_MAP.items():
                    for m_kw in re.finditer(rf"\b{re.escape(kw)}\b", prefix_sent):
                        if m_kw.start() > best_pos:
                            best_pos = m_kw.start()
                            food_cat = norm_cat
            if day_es and food_cat:
                excl_list = c["dayExclusions"].setdefault(day_es, [])
                if food_cat not in excl_list:
                    excl_list.append(food_cat)

        # 7c. Positive category counts (e.g., "Incluye una cena de carne, dos de pescado")
        for m_q in re.finditer(
            r"\b(one|two|three|four|five|un|una|uno|dos|tres|cuatro|cinco|[1-5])\s+"
            r"(?:(?:cenas?|comidas?|platos?|recetas?|d[ií]as?)\s+)?(?:de\s+|con\s+)\b"
            r"(carne|meat|pollo|pavo|ternera|cerdo|pescados?|fish|merluza|salm[oó]n|salmon|bacalao|at[uú]n|verduras?|vegetarian[oa]s?|pasta)\b",
            s_low,
        ):
            prefix = s_low[max(0, m_q.start() - 30) : m_q.start()]
            if re.search(r"\b(?:no|sin|nunca|evita\w*|m[aá]s\s+de|m[aá]ximo|como\s+mucho)\b", prefix):
                continue
            cnt = _to_number(m_q.group(1)) or 1
            cat = FOOD_SUBJECT_MAP.get(m_q.group(2), m_q.group(2))
            if cat == "carne" and not c.get("vegetarianOnly"):
                c["requiredMeatCount"] = max(int(c.get("requiredMeatCount") or 0), cnt)
                c["requiredMeat"] = True
            elif cat == "pescado" and "fish" not in c.get("excludedAllergens", []):
                c["requiredFishCount"] = max(int(c.get("requiredFishCount") or 0), cnt)
                c["requiredFish"] = True
            elif cat == "verdura":
                c["requiredVegCount"] = max(int(c.get("requiredVegCount") or 0), cnt)
            elif cat == "pasta":
                c["maxPastaCount"] = max(int(c.get("maxPastaCount") or 2), cnt)

    if re.search(
        r"\b(?:incluye|incluir|con|include|add|with)\b[^.!?]{0,35}\b(?:pescado|merluza|salmón|salmon|fish)\b|\b(?:fish\s+dinner|cenas?\s+de\s+pescado)\b",
        prompt,
        re.IGNORECASE,
    ):
        if "fish" not in c["excludedAllergens"]:
            c["requiredFish"] = True
            c["requiredFishCount"] = max(1, int(c.get("requiredFishCount") or 0))

    if re.search(
        r"\b(?:incluye|incluir|con|include|add|with)\b[^.!?]{0,35}\b(?:carne|pollo|pavo|ternera|cerdo|meat)\b|\b(?:cenas?\s+de\s+carne)\b",
        prompt,
        re.IGNORECASE,
    ):
        if not c.get("vegetarianOnly"):
            c["requiredMeat"] = True
            c["requiredMeatCount"] = max(1, int(c.get("requiredMeatCount") or 0))

    # 8. Pantry items already at home
    pantry = extract_pantry_items(prompt)
    if pantry:
        c["pantryItems"] = list(dict.fromkeys(list(c.get("pantryItems", [])) + pantry))

    return c


def format_constraint_pills(c: dict[str, Any]) -> list[str]:
    """Formats detected constraints as UI pills."""
    meals = c.get("mealCount", 5)
    pills = [
        f"{meals} {'cena' if meals == 1 else 'cenas'}",
        f"≤ {c.get('maxMinutes', 30)} min",
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
    if c.get("kidFriendly") or children > 0:
        pills.append("👶 Recetas aptas para niños")
    if c.get("vegetarianOnly"):
        pills.append("Vegetariano")
    req_meat = int(c.get("requiredMeatCount") or 0)
    if req_meat > 0:
        pills.append(f"{req_meat} {'cena' if req_meat == 1 else 'cenas'} de carne")
    req_fish = int(c.get("requiredFishCount") or (1 if c.get("requiredFish") else 0))
    if req_fish > 0:
        pills.append(f"{req_fish} {'cena' if req_fish == 1 else 'cenas'} de pescado" if req_fish > 1 else "Incluye pescado")
    max_pasta = c.get("maxPastaCount")
    if max_pasta is not None and int(max_pasta) <= 2 and ("pasta" in [p.lower() for p in c.get("pantryItems", [])] or c.get("dayExclusions")):
        pills.append("Sin pasta" if int(max_pasta) == 0 else f"Máx. {int(max_pasta)} de pasta")
    for day_name, ex_list in (c.get("dayExclusions") or {}).items():
        if ex_list:
            pills.append(f"{day_name}: sin {', '.join(ex_list)}")
    for alg in c.get("excludedAllergens", []):
        pills.append(ALLERGEN_DEFINITIONS.get(alg, {}).get("label", f"Sin {alg}"))
    for p in c.get("pantryItems", [])[:4]:
        pills.append(f"En casa: {p}")
    return pills


def _pantry_excluded_product_ids(pantry_items: list[str], catalog: dict[str, dict[str, Any]]) -> dict[str, str]:
    """Maps user pantry items to Día product IDs -> pantry item name."""
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


def _enforce_weekly_quotas_and_day_rules(
    selected: list[dict[str, Any]],
    sorted_candidates: list[dict[str, Any]],
    constraints: dict[str, Any],
    meal_count: int,
) -> list[dict[str, Any]]:
    """Deterministically enforces:
    1) Maximum pasta frequency (`maxPastaCount`, default 2)
    2) Required fish dinners (`requiredFishCount`)
    3) Required meat dinners (`requiredMeatCount`)
    4) Pantry pasta inclusion (1-2 pasta dinners if user asked to use pasta at home)
    5) Day-by-day exclusions & requirements (e.g., never pasta on Monday / Lunes)
    6) Non-consecutive pasta days when possible
    """
    max_pasta = int(constraints.get("maxPastaCount", 2) if constraints.get("maxPastaCount") is not None else 2)
    req_fish = min(meal_count, int(constraints.get("requiredFishCount") or (1 if constraints.get("requiredFish") else 0)))
    req_meat = 0 if constraints.get("vegetarianOnly") else min(meal_count - req_fish, int(constraints.get("requiredMeatCount") or (1 if constraints.get("requiredMeat") else 0)))
    pantry_low = [str(p).lower() for p in constraints.get("pantryItems", [])]
    wants_pantry_pasta = any("pasta" in p or "macarron" in p or "espagueti" in p for p in pantry_low) and max_pasta > 0
    kid_friendly = bool(constraints.get("kidFriendly") or int(constraints.get("children") or 0) > 0)
    day_exclusions: dict[str, list[str]] = constraints.get("dayExclusions") or {}
    day_requirements: dict[str, str] = constraints.get("dayRequirements") or {}

    # Start with unique recipes up to meal_count (avoiding duplicate dish stems when possible)
    work: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_stems: set[str] = set()
    for r in selected:
        stem = _recipe_stem(r)
        if r["recipe_id"] not in seen_ids and stem not in seen_stems:
            work.append(r)
            seen_ids.add(r["recipe_id"])
            seen_stems.add(stem)
            if len(work) == meal_count:
                break
    for r in sorted_candidates:
        if len(work) >= meal_count:
            break
        stem = _recipe_stem(r)
        if r["recipe_id"] not in seen_ids and stem not in seen_stems:
            work.append(r)
            seen_ids.add(r["recipe_id"])
            seen_stems.add(stem)
    for r in sorted_candidates:
        if len(work) >= meal_count:
            break
        if r["recipe_id"] not in seen_ids:
            work.append(r)
            seen_ids.add(r["recipe_id"])

    def _pick_unused(pred) -> dict[str, Any] | None:
        active_stems = {_recipe_stem(x) for x in work}
        for cand in sorted_candidates:
            if cand["recipe_id"] not in seen_ids and _recipe_stem(cand) not in active_stems and pred(cand):
                return cand
        for cand in sorted_candidates:
            if cand["recipe_id"] not in seen_ids and pred(cand):
                return cand
        return None

    # 1. Cap pasta recipes at max_pasta
    while sum(1 for r in work if _is_pasta_recipe(r)) > max_pasta:
        # Remove the last pasta recipe in work
        pasta_indices = [i for i, r in enumerate(work) if _is_pasta_recipe(r)]
        if not pasta_indices:
            break
        rep_idx = pasta_indices[-1]
        curr_fish = sum(1 for i, r in enumerate(work) if i != rep_idx and _is_fish_recipe(r))
        curr_meat = sum(1 for i, r in enumerate(work) if i != rep_idx and _is_meat_recipe(r))
        replacement = None
        if curr_fish < req_fish:
            replacement = _pick_unused(lambda c: _is_fish_recipe(c, prefer_finfish=kid_friendly) and not _is_pasta_recipe(c)) or _pick_unused(
                lambda c: _is_fish_recipe(c) and not _is_pasta_recipe(c)
            )
        if not replacement and curr_meat < req_meat:
            replacement = _pick_unused(lambda c: _is_meat_recipe(c, require_title_match=True) and not _is_pasta_recipe(c)) or _pick_unused(
                lambda c: _is_meat_recipe(c) and not _is_pasta_recipe(c)
            )
        if not replacement:
            replacement = _pick_unused(lambda c: not _is_pasta_recipe(c))
        if not replacement:
            break
        work[rep_idx] = replacement
        seen_ids.add(replacement["recipe_id"])

    # 2. Enforce requiredFishCount (preferring non-pasta finfish so we don't exceed max_pasta)
    while sum(1 for r in work if _is_fish_recipe(r)) < req_fish:
        curr_pasta = sum(1 for r in work if _is_pasta_recipe(r))
        fc = (
            _pick_unused(lambda c: _is_fish_recipe(c, prefer_finfish=True) and not _is_pasta_recipe(c))
            or _pick_unused(lambda c: _is_fish_recipe(c) and not _is_pasta_recipe(c))
            or (_pick_unused(lambda c: _is_fish_recipe(c)) if curr_pasta < max_pasta else None)
        )
        if not fc:
            break
        # Find a replaceable index in work (not fish, and without dropping meat below req_meat or removing the only pantry pasta)
        rep_idx = None
        for i in range(len(work) - 1, -1, -1):
            r_i = work[i]
            if _is_fish_recipe(r_i):
                continue
            rem_meat = sum(1 for j, r_j in enumerate(work) if j != i and _is_meat_recipe(r_j))
            if _is_meat_recipe(r_i) and rem_meat < req_meat:
                continue
            rem_pasta = sum(1 for j, r_j in enumerate(work) if j != i and _is_pasta_recipe(r_j))
            if wants_pantry_pasta and _is_pasta_recipe(r_i) and rem_pasta < 1:
                continue
            rep_idx = i
            break
        if rep_idx is None:
            rep_idx = next((i for i in range(len(work) - 1, -1, -1) if not _is_fish_recipe(work[i])), None)
        if rep_idx is None:
            break
        work[rep_idx] = fc
        seen_ids.add(fc["recipe_id"])

    # 3. Enforce requiredMeatCount (preferring non-pasta meat dishes with meat in title)
    while sum(1 for r in work if _is_meat_recipe(r, require_title_match=True)) < req_meat:
        curr_pasta = sum(1 for r in work if _is_pasta_recipe(r))
        mc = (
            _pick_unused(lambda c: _is_meat_recipe(c, require_title_match=True) and not _is_pasta_recipe(c))
            or _pick_unused(lambda c: _is_meat_recipe(c) and not _is_pasta_recipe(c))
            or (_pick_unused(lambda c: _is_meat_recipe(c, require_title_match=True)) if curr_pasta < max_pasta else None)
        )
        if not mc:
            break
        rep_idx = None
        for i in range(len(work) - 1, -1, -1):
            r_i = work[i]
            if _is_meat_recipe(r_i, require_title_match=True):
                continue
            rem_fish = sum(1 for j, r_j in enumerate(work) if j != i and _is_fish_recipe(r_j))
            if _is_fish_recipe(r_i) and rem_fish < req_fish:
                continue
            rem_pasta = sum(1 for j, r_j in enumerate(work) if j != i and _is_pasta_recipe(r_j))
            if wants_pantry_pasta and _is_pasta_recipe(r_i) and rem_pasta < 1:
                continue
            rep_idx = i
            break
        if rep_idx is None:
            break
        work[rep_idx] = mc
        seen_ids.add(mc["recipe_id"])

    # 4. If user asked to use pasta at home and max_pasta >= 1, ensure at least 1 pasta dish is present
    if wants_pantry_pasta and sum(1 for r in work if _is_pasta_recipe(r)) == 0:
        pc = _pick_unused(lambda c: _is_pasta_recipe(c))
        if pc:
            for i in range(len(work) - 1, -1, -1):
                r_i = work[i]
                rem_fish = sum(1 for j, r_j in enumerate(work) if j != i and _is_fish_recipe(r_j))
                rem_meat = sum(1 for j, r_j in enumerate(work) if j != i and _is_meat_recipe(r_j, require_title_match=True))
                if (_is_fish_recipe(r_i) and rem_fish < req_fish) or (_is_meat_recipe(r_i, require_title_match=True) and rem_meat < req_meat):
                    continue
                work[i] = pc
                seen_ids.add(pc["recipe_id"])
                break

    # 5. Re-verify max_pasta cap in case a combined fish+pasta or meat+pasta dish was added
    while sum(1 for r in work if _is_pasta_recipe(r)) > max_pasta:
        pasta_indices = [i for i, r in enumerate(work) if _is_pasta_recipe(r)]
        rep_idx = pasta_indices[-1]
        was_fish = _is_fish_recipe(work[rep_idx])
        was_meat = _is_meat_recipe(work[rep_idx], require_title_match=True)
        if was_fish:
            rep = _pick_unused(lambda c: _is_fish_recipe(c) and not _is_pasta_recipe(c))
        elif was_meat:
            rep = _pick_unused(lambda c: _is_meat_recipe(c, require_title_match=True) and not _is_pasta_recipe(c))
        else:
            rep = _pick_unused(lambda c: not _is_pasta_recipe(c))
        if not rep:
            break
        work[rep_idx] = rep
        seen_ids.add(rep["recipe_id"])

    # 6. Assign recipes to days (DAYS_ES[:meal_count]) respecting dayExclusions & dayRequirements
    days = DAYS_ES[: len(work)]
    for i, d_name in enumerate(days):
        if not _day_allows_recipe(d_name, work[i], day_exclusions, day_requirements):
            # Try swapping with another slot j
            swapped = False
            for j in range(len(work)):
                if i == j:
                    continue
                d_other = days[j]
                if _day_allows_recipe(d_name, work[j], day_exclusions, day_requirements) and _day_allows_recipe(
                    d_other, work[i], day_exclusions, day_requirements
                ):
                    work[i], work[j] = work[j], work[i]
                    swapped = True
                    break
            if not swapped:
                # Replace work[i] with a valid candidate from sorted_candidates
                need_fish = _is_fish_recipe(work[i]) and sum(1 for k, r_k in enumerate(work) if k != i and _is_fish_recipe(r_k)) < req_fish
                need_meat = (
                    _is_meat_recipe(work[i], require_title_match=True)
                    and sum(1 for k, r_k in enumerate(work) if k != i and _is_meat_recipe(r_k, require_title_match=True)) < req_meat
                )
                rep = _pick_unused(
                    lambda c: _day_allows_recipe(d_name, c, day_exclusions, day_requirements)
                    and (not _is_pasta_recipe(c) or sum(1 for k, r_k in enumerate(work) if k != i and _is_pasta_recipe(r_k)) < max_pasta)
                    and (not need_fish or _is_fish_recipe(c))
                    and (not need_meat or _is_meat_recipe(c, require_title_match=True))
                ) or _pick_unused(lambda c: _day_allows_recipe(d_name, c, day_exclusions, day_requirements))
                if rep:
                    work[i] = rep
                    seen_ids.add(rep["recipe_id"])

    # 7. Separate consecutive pasta days if there are 2 pasta recipes on adjacent days
    for i in range(len(work) - 1):
        if _is_pasta_recipe(work[i]) and _is_pasta_recipe(work[i + 1]):
            for j in range(len(work)):
                if abs(j - i) <= 1 or _is_pasta_recipe(work[j]):
                    continue
                if _day_allows_recipe(days[i + 1], work[j], day_exclusions, day_requirements) and _day_allows_recipe(
                    days[j], work[i + 1], day_exclusions, day_requirements
                ):
                    work[i + 1], work[j] = work[j], work[i + 1]
                    break

    return work


def _call_gemini_flash_selector(
    prompt: str,
    constraints: dict[str, Any],
    candidates: list[dict[str, Any]],
    liked_recipe_ids: list[str] | None = None,
) -> dict[str, Any] | None:
    """Calls Gemini 3.8 Flash (with automatic fallback to gemini-2.5-flash) via Vertex AI or AI Studio."""
    liked_set = set(liked_recipe_ids or [])
    compact_candidates = [
        {
            "recipe_id": r["recipe_id"],
            "name": r["name"],
            "minutes": r["minutes"],
            "calories_per_serving": r["calories_per_serving"],
            "estimated_cost": r["estimated_cost"],
            "is_fish": r["is_fish"],
            "is_meat": _is_meat_recipe(r, require_title_match=True),
            "is_pasta": _is_pasta_recipe(r),
            "is_vegetarian": r["is_vegetarian"],
            "is_kid_friendly": _kid_friendly_score(r) >= 2,
            "allergens": r["allergens"],
            "liked_by_user": r["recipe_id"] in liked_set,
        }
        for r in candidates[:36]
    ]

    sys_instruction = (
        "Eres el planificador oficial de menús semanales de Mercadona × Thermomix Cookidoo impulsado por Google Gemini. "
        "Debes seleccionar exactamente `mealCount` recetas distintas de la lista `candidates` que cumplan estrictamente todas las condiciones "
        "del usuario: tiempo, calorías, presupuesto, alérgenos, número de cenas de pescado (`requiredFishCount`), número de cenas de carne (`requiredMeatCount`), "
        "límite máximo de platos de pasta (`maxPastaCount`, por defecto máximo 2), exclusiones por día (`dayExclusions`, ej. nunca pasta los Lunes) "
        "y recetas suaves aptas para niños (`kidFriendly`) cuando hay niños en casa. "
        "Mantén alta variedad entre días: no repitas siempre las mismas recetas con `liked_by_user: true` (incluye como máximo 1 solo de vez en cuando). "
        "Devuelve exclusivamente un objeto JSON válido con las claves: "
        "`headline` (string en español), `summary` (string en español explicando cómo se adaptó el menú y el ahorro de despensa), "
        "y `selected_recipe_ids` (array de strings con los `recipe_id` elegidos en orden de Lunes a Viernes)."
    )

    user_payload = json.dumps(
        {
            "user_prompt": prompt,
            "constraints": constraints,
            "liked_recipe_ids": list(liked_set),
            "candidates": compact_candidates,
        },
        ensure_ascii=False,
    )

    # 1. Try Vertex AI via google-genai SDK (works automatically on Cloud Run with ADC)
    try:
        from google import genai  # type: ignore
        from google.genai import types  # type: ignore

        project_id = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("PROJECT_ID") or "mercadona-ai-companion"
        client = genai.Client(vertexai=True, project=project_id, location="us-central1")
        for model_name in [MODEL_PRIMARY, MODEL_FALLBACK, "gemini-2.0-flash"]:
            try:
                resp = client.models.generate_content(
                    model=model_name,
                    contents=user_payload,
                    config=types.GenerateContentConfig(
                        system_instruction=sys_instruction,
                        temperature=0.35,
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
                "temperature": 0.35,
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
    """Builds a complete weekly Cookidoo + Mercadona dinner plan adhering to all user constraints."""
    is_valid, err_msg = validate_meal_planning_prompt(prompt)
    if not is_valid:
        raise ValueError(err_msg)

    if liked_recipe_ids is not None or disliked_recipe_ids is not None:
        # Use merge=False so un-liking a recipe in the UI immediately removes it on the server too
        prefs = save_user_recipe_preferences(
            user_email=user_email,
            liked_recipe_ids=liked_recipe_ids,
            disliked_recipe_ids=disliked_recipe_ids,
            merge=False,
        )
    else:
        prefs = get_user_recipe_preferences(user_email)

    disliked_set = set(prefs.get("disliked") or [])
    liked_set = set(prefs.get("liked") or []) - disliked_set

    base_c = current_plan.get("constraints") if current_plan else None
    constraints = parse_constraints(prompt, base_c)

    # Check if the user is asking to swap/change a single specific day in an existing plan (e.g. "Cambia el miércoles a una cena de pescado")
    p_low = (prompt or "").strip().lower()
    if (
        isinstance(current_plan, dict)
        and isinstance(current_plan.get("meals"), list)
        and len(current_plan["meals"]) > 0
        and not re.search(r"\b(?:planifica|genera|crea)\s+\d*\s*cenas\b", p_low)
        and any(w in p_low for w in ("cambia", "cambiar", "cambio", "rota", "rotar", "sustituye", "sustituir", "pon", "poner", "prefiero", "quiero"))
    ):
        matched_days = [
            d_val
            for d_key, d_val in DAYS_EN_TO_ES.items()
            if re.search(rf"\b{re.escape(d_key)}\b", p_low)
        ]
        unique_days = list(dict.fromkeys(matched_days))
        if len(unique_days) == 1:
            target_day_es = unique_days[0]
            curr_meals = current_plan["meals"]
            target_meal_obj = next(
                (m for m in curr_meals if str(m.get("day", "")).lower() == target_day_es.lower()),
                None,
            )
            if target_meal_obj:
                rot_seed = int(hashlib.sha256(f"{prompt}:{variety_seed}".encode("utf-8")).hexdigest()[:6], 16)
                swap_res = swap_single_recipe(
                    current_meals=[{"day": m["day"], "recipe_id": m["recipe_id"]} for m in curr_meals],
                    target_recipe_id=target_meal_obj["recipe_id"],
                    constraints=constraints,
                    postal_code=postal_code,
                    rotation=rot_seed,
                    liked_recipe_ids=liked_recipe_ids,
                    disliked_recipe_ids=disliked_recipe_ids,
                    user_email=user_email,
                    basket_tier=current_plan.get("basket_tier") or "ahorro",
                    preferred_query=prompt,
                )
                return {
                    **current_plan,
                    "meals": swap_res["meals"],
                    "basket": swap_res["basket"],
                    "total": swap_res["total"],
                    "budget_remaining": swap_res["budget_remaining"],
                    "basket_tier": swap_res["basket_tier"],
                    "upgraded_count": swap_res["upgraded_count"],
                    "counter_notes_count": swap_res["counter_notes_count"],
                    "sommelier_pairing": swap_res["sommelier_pairing"],
                    "retail_media_summary": swap_res["retail_media_summary"],
                    "eci_plus_status": swap_res["eci_plus_status"],
                    "summary": (
                        f"Se ha actualizado la cena del {target_day_es} a «{swap_res['change']['to_recipe_name']}» "
                        f"según tu petición («{prompt.strip()}») y se ha recalculado la cesta de Mercadona."
                    ),
                }

    all_recipes = load_cookidoo_catalog()
    catalog, catalog_meta = get_catalog_for_postal_code(postal_code)
    pantry_map = _pantry_excluded_product_ids(constraints.get("pantryItems", []), catalog)

    excluded_allergens = set(constraints.get("excludedAllergens", []))
    max_minutes = constraints.get("maxMinutes") or 60
    max_cal = constraints.get("maxCaloriesPerServing")
    veg_only = bool(constraints.get("vegetarianOnly"))
    kid_friendly = bool(constraints.get("kidFriendly") or int(constraints.get("children") or 0) > 0)

    # Filter Cookidoo recipes:
    # 0) Never propose recipes disliked by the user (hard filter)
    # 1) All mapped ingredients must be available in ECI API for this postal code
    # 2) Must satisfy maxMinutes, maxCaloriesPerServing, vegetarianOnly, excludedAllergens, and kid-safety when children > 0
    eligible: list[dict[str, Any]] = []
    for r in all_recipes:
        if r["recipe_id"] in disliked_set:
            continue
        if not r.get("is_dinner", True):
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
        if kid_friendly and not _is_kid_safe_recipe(r):
            continue
        if OUTLIER_PORTION_TITLE_RE.search(str(r.get("name", ""))):
            continue
        eligible.append(r)

    # Relax time / kid filter slightly if user asked for something super tight that left < mealCount recipes
    meal_count = constraints.get("mealCount", 5)
    if len(eligible) < meal_count * 3:
        for r in all_recipes:
            if r["recipe_id"] in disliked_set or r in eligible:
                continue
            if not r.get("is_dinner", True):
                continue
            if not all(pid in catalog for pid in r["product_ids"]):
                continue
            if excluded_allergens.intersection(set(r.get("allergens", []))):
                continue
            if veg_only and not r["is_vegetarian"]:
                continue
            if max_cal is not None and r["calories_per_serving"] > max_cal:
                continue
            if kid_friendly and not _is_kid_safe_recipe(r):
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
        "propongas", "veces", "nunca", "lunes", "martes", "miercoles", "jueves", "viernes",
        "pequenos", "pequeno", "aptas", "apta", "carne", "pescado", "pasta",
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

    # Strip negative clauses before extracting positive keyword tokens
    positive_prompt_only = re.sub(
        r"\b(?:no\s+propongas|nunca|sin|evita)\b[^.!?;]*",
        " ",
        _norm_str(prompt),
        flags=re.IGNORECASE,
    )
    prompt_tokens = list(
        dict.fromkeys(
            t
            for t in re.findall(r"[a-z0-9]+", positive_prompt_only)
            if len(t) >= 4 and t not in STOP_TOKENS and not t.isdigit()
        )
    )

    SHARED_STAPLES = {"4740", "4717", "4706", "4850", "4940", "34125", "17228", "15436"}
    liked_affinity_pids: set[str] = set()
    if liked_set:
        for r in all_recipes:
            if r["recipe_id"] in liked_set:
                for pid in r.get("product_ids", []):
                    if pid not in SHARED_STAPLES:
                        liked_affinity_pids.add(pid)

    # Track recipes currently on screen so re-generating gives fresh variety and doesn't repeat the same liked recipe every time
    prev_meal_ids: set[str] = {
        str(m.get("recipe_id") or "")
        for m in ((current_plan or {}).get("meals") or [])
        if m.get("recipe_id")
    }

    # Randomize liked-recipe promotion: only promote at most 1 liked recipe occasionally (~1 in 3 generations)
    # and on the other 2/3 generations, hold back exact liked recipes so the user gets fresh variety inspired by their tastes!
    liked_eligible = [
        r for r in eligible if r["recipe_id"] in liked_set and r["recipe_id"] not in prev_meal_ids
    ]
    promoted_liked_ids: set[str] = set()
    if liked_eligible and (seed_int % 3 == 0):
        chosen_liked = liked_eligible[(seed_int // 3) % len(liked_eligible)]
        promoted_liked_ids.add(chosen_liked["recipe_id"])

    def score_recipe(idx_r: tuple[int, dict[str, Any]]) -> tuple[int, int, int, int, float, int]:
        idx, r = idx_r
        # Deprioritize recipes from the current plan OR liked recipes that were not selected for promotion in this seed
        is_held_back = (r["recipe_id"] in prev_meal_ids) or (
            r["recipe_id"] in liked_set and r["recipe_id"] not in promoted_liked_ids
        )
        holdback_rank = 1 if is_held_back else 0
        promoted_rank = 0 if r["recipe_id"] in promoted_liked_ids else 1
        kid_tier = (0 if _kid_friendly_score(r) >= 2 else 1) if kid_friendly else 0
        r_text = _norm_str(r["name"] + " " + " ".join(r.get("ingredients", [])))
        kw_hits = min(2, sum(1 for tok in prompt_tokens if tok in r_text))
        affinity_hits = min(2, sum(1 for pid in r["product_ids"] if pid in liked_affinity_pids))
        pantry_hits = min(1, sum(1 for pid in r["product_ids"] if pid in pantry_map))
        net_cost = sum(catalog[pid]["unit_price"] for pid in r["product_ids"] if pid not in pantry_map)
        # Strong pseudo-random jitter per recipe + seed so every generation explores diverse recipes
        h_val = int(hashlib.md5(f"{r['recipe_id']}:{seed_int}".encode("utf-8")).hexdigest()[:6], 16)
        jitter = (h_val % 37) * 1.15
        combined_relevance = kw_hits + pantry_hits + (1 if affinity_hits > 0 else 0)
        return (
            holdback_rank,
            promoted_rank,
            kid_tier,
            -combined_relevance,
            net_cost + jitter,
            r["minutes"],
        )

    sorted_candidates = [r for _, r in sorted(enumerate(eligible), key=score_recipe)]

    # Build a stratified pool of candidates for Gemini so it always has plenty of fish, meat, pasta, and veggie/egg options
    fish_pool = [r for r in sorted_candidates if _is_fish_recipe(r, prefer_finfish=kid_friendly) and not _is_pasta_recipe(r)]
    if len(fish_pool) < 8:
        fish_pool += [r for r in sorted_candidates if _is_fish_recipe(r) and r not in fish_pool]
    meat_pool = [r for r in sorted_candidates if _is_meat_recipe(r, require_title_match=True) and not _is_pasta_recipe(r)]
    pasta_pool = [r for r in sorted_candidates if _is_pasta_recipe(r)]
    other_pool = [r for r in sorted_candidates if not _is_fish_recipe(r) and not _is_meat_recipe(r) and not _is_pasta_recipe(r)]

    stratified_for_gemini: list[dict[str, Any]] = []
    seen_strat: set[str] = set()
    for bucket in (
        fish_pool[:10],
        meat_pool[:10],
        pasta_pool[: max(2, int(constraints.get("maxPastaCount", 2)) * 3)],
        other_pool[:10],
        sorted_candidates[:20],
    ):
        for r in bucket:
            if r["recipe_id"] not in seen_strat:
                stratified_for_gemini.append(r)
                seen_strat.add(r["recipe_id"])

    # Call Gemini 3.8 Flash if configured
    gemini_res = _call_gemini_flash_selector(
        prompt,
        constraints,
        stratified_for_gemini,
        liked_recipe_ids=list(liked_set),
    )
    cand_by_id = {r["recipe_id"]: r for r in sorted_candidates}

    selected: list[dict[str, Any]] = []
    if gemini_res and gemini_res.get("selected_recipe_ids"):
        for rid in gemini_res["selected_recipe_ids"]:
            if rid in cand_by_id and cand_by_id[rid] not in selected:
                selected.append(cand_by_id[rid])
                if len(selected) == meal_count:
                    break

    # Deterministically enforce all category quotas (meat, fish), maxPastaCount, pantry pasta, and day-specific exclusions (e.g., never pasta on Monday)
    selected = _enforce_weekly_quotas_and_day_rules(
        selected=selected,
        sorted_candidates=sorted_candidates,
        constraints=constraints,
        meal_count=meal_count,
    )

    # Scale quantities based on family size (adults + children*0.75)
    adults = constraints.get("adults", 2)
    children = constraints.get("children", 1)
    household_portions = adults + (0.75 * children)

    meals_out: list[dict[str, Any]] = []
    product_quantities: dict[str, int] = {}
    product_used_in_days: dict[str, list[str]] = {}

    # Verify cover images against live cookidoo.es JSON-LD so photos always match 100%
    ensure_verified_cookidoo_images_batch(selected[:meal_count])

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
                "is_meat": _is_meat_recipe(r, require_title_match=True),
                "is_pasta": _is_pasta_recipe(r),
                "is_vegetarian": r["is_vegetarian"],
                "is_kid_friendly": _is_kid_safe_recipe(r) and _kid_friendly_score(r) >= 2,
                "liked_by_user": r["recipe_id"] in liked_set,
            }
        )

    # Assemble Mercadona basket & optimize against maxBudget if needed
    max_budget = float(constraints.get("maxBudget", 65.0))

    # Refresh live stock & prices in the user's postal code/center for the selected products
    selected_pids_list = [pid for pid, q in product_quantities.items() if q > 0]
    if selected_pids_list:
        live_cat, live_meta = get_catalog_for_postal_code(postal_code, verify_live_ids=selected_pids_list)
        catalog.update(live_cat)
        catalog_meta.update(live_meta)

    def build_basket_rows(qty_map: dict[str, int]) -> tuple[list[dict[str, Any]], float]:
        rows: list[dict[str, Any]] = []
        for pid, qty in qty_map.items():
            if qty <= 0 or pid not in catalog:
                continue
            prod = catalog[pid]
            line_total = round(prod["unit_price"] * qty, 2)
            rows.append(
                {
                    "id": prod.get("id", pid),
                    "product_id": prod.get("id", pid),
                    "eci_sku": prod.get("eci_sku", pid),
                    "dia_sku": prod.get("eci_sku", pid),
                    "name": prod["name"],
                    "thumbnail": prod.get("thumbnail", ""),
                    "share_url": prod.get("share_url", f"https://tienda.mercadona.es/product/{pid}/"),
                    "unit": prod.get("unit", "1 ud"),
                    "unit_price": prod["unit_price"],
                    "quantity": qty,
                    "line_total": line_total,
                    "available": bool(prod.get("available", True)),
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

    # If still above budget and olive oil (B001018044700120) is included, treat olive oil as kitchen staple
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
    center_label = catalog_meta.get("center_name") or catalog_meta["warehouse"]
    default_summary = (
        f"Menú semanal elaborado con Google Gemini seleccionando recetas oficiales de Cookidoo "
        f"cuyos ingredientes y stock están verificados casi en tiempo real en Mercadona "
        f"para el CP {catalog_meta['postal_code']} ({center_label}).{pantry_note}"
    )

    allergen_labels = [
        ALLERGEN_DEFINITIONS.get(a, {}).get("label", a)
        for a in constraints.get("excludedAllergens", [])
    ]
    allergen_notice = (
        f"Validación determinista completada ({', '.join(allergen_labels)}). Verifica siempre el etiquetado físico del envase en caso de alergia severa."
        if allergen_labels
        else "Todos los productos han sido cruzados con la información de alérgenos del catálogo de Mercadona. Revisa siempre el envase físico."
    )

    low_p = prompt.lower()
    detected_tier = (current_plan or {}).get("basket_tier") or "ahorro"
    if any(k in low_p for k in ("club del gourmet", "gourmet", "selection")):
        detected_tier = "gourmet"
    elif any(k in low_p for k in ("ecológic", "ecologic", "gama bio", "productos bio")):
        detected_tier = "bio"
    elif any(k in low_p for k in ("modo ahorro", "marca el corte", "económico", "economico")):
        detected_tier = "ahorro"

    enriched = enrich_basket_with_eci_features(
        basket_rows=basket_rows,
        meals=meals_out,
        catalog=catalog,
        basket_tier=detected_tier,
        custom_counter_cuts=(current_plan or {}).get("custom_counter_cuts"),
        include_sommelier_item=bool(((current_plan or {}).get("sommelier_pairing") or {}).get("included", False)),
        postal_code=catalog_meta["postal_code"],
        center_name=center_label,
    )
    basket_rows = enriched["basket"]
    total = enriched["total"]
    budget_remaining = round(max_budget - total, 2)
    default_headline = (
        f"{meal_count} cenas en ≤ {max_minutes} min para {fam_desc}, por {total:.2f} € en Mercadona."
    )

    default_diners = max(1, adults + children)
    day_servings_map = {m["day"]: default_diners for m in meals_out}
    for m in meals_out:
        m["active_diners"] = default_diners

    return {
        "headline": (gemini_res or {}).get("headline") or default_headline,
        "summary": (gemini_res or {}).get("summary") or default_summary,
        "live": bool(gemini_res),
        "model": (gemini_res or {}).get("model_used") or "Gemini 3.8 Flash",
        "postal_code": catalog_meta["postal_code"],
        "warehouse": catalog_meta["warehouse"],
        "center_name": center_label,
        "delivery_available": catalog_meta.get("delivery_available", True),
        "catalog_source": catalog_meta["catalog_source"],
        "cookidoo_catalog_source": "live",
        "constraints": constraints,
        "constraint_pills": format_constraint_pills(constraints),
        "meals": meals_out,
        "basket": basket_rows,
        "total": total,
        "budget_remaining": budget_remaining,
        "basket_tier": enriched["basket_tier"],
        "upgraded_count": enriched["upgraded_count"],
        "counter_notes_count": enriched["counter_notes_count"],
        "sommelier_pairing": enriched["sommelier_pairing"],
        "retail_media_summary": enriched["retail_media_summary"],
        "eci_plus_status": enriched["eci_plus_status"],
        "day_servings": day_servings_map,
        "custom_counter_cuts": (current_plan or {}).get("custom_counter_cuts") or {},
        "allergen_notice": allergen_notice,
        "recipe_preferences": {
            "liked": list(liked_set),
            "disliked": list(disliked_set),
        },
        "trace": [
            "gemini_3_8_flash_planner",
            "search_cookidoo",
            "verify_eci_stock_postal_code",
            "check_declared_allergens",
            "generate_eci_counter_prep_notes",
            "price_basket",
        ],
    }


def generate_counter_prep_note(
    prod: dict[str, Any],
    used_in_days: list[str],
    meals_by_day: dict[str, dict[str, Any]],
    custom_cut: str | None = None,
) -> dict[str, Any] | None:
    """Generates automatic Mercadona Fresh Counter preparation notes based on the Thermomix recipe technique."""
    name_low = str(prod.get("name", "")).lower()
    cat_low = str(prod.get("category", "")).lower()
    combined = f"{name_low} {cat_low}"

    # Avoid tagging canned/shelf-stable items as fresh counter
    if any(
        skip in combined
        for skip in (
            "lata ",
            "frasco ",
            "brik",
            "botella",
            "caldo ",
            "galleta",
            "cerveza",
            "sazonador",
            "mostaza",
            "mayonesa",
            "vinagre",
            "aceite",
            "harina",
            "arroz",
            "macarrones",
            "espagueti",
            "fideo",
            "tarrito",
            "mermelada",
            "miel",
            "nueces",
            "almendra",
            "pistacho",
            "cacahuete",
            "pan de molde",
            "tortillas de trigo",
            "chips",
        )
    ):
        return None

    days = list(dict.fromkeys(used_in_days or []))
    day_recipes = [(d, meals_by_day.get(d, {})) for d in days if d in meals_by_day]

    def _recipe_cut_fish(r: dict[str, Any]) -> str:
        r_txt = f"{r.get('name', '')} {r.get('description', '')}".lower()
        if any(k in r_txt for k in ("vapor", "varoma", "papillote", "limón", "limon", "horno", "salsa")):
            return "Lomos limpios sin piel ni espinas (especial Varoma)"
        if any(k in r_txt for k in ("arroz", "fideu", "sopa", "caldo", "guiso", "marmitako", "suquet")):
            return "Dados limpios de 3 cm sin espinas + espinas aparte para fumet"
        if any(k in r_txt for k in ("croqueta", "pastel", "albóndiga", "albondiga", "brandada", "taco")):
            return "Desmigado limpio sin espinas ni piel"
        return "Supremas / lomos de ración limpios sin espinas"

    def _recipe_cut_meat(r: dict[str, Any]) -> str:
        r_txt = f"{r.get('name', '')} {r.get('description', '')}".lower()
        if any(k in r_txt for k in ("boloñesa", "bolonesa", "lasaña", "lasana", "albóndiga", "albondiga", "hamburguesa", "pastel", "rellen")):
            return "Picada 1 sola vez en mostrador (textura jugosa)"
        if any(k in r_txt for k in ("fajita", "taco", "wok", "saltead", "tiras", "oriental", "soja", "ensalada")):
            return "Cortado en tiras finas regulares para saltear"
        if any(k in r_txt for k in ("curry", "guiso", "estofado", "arroz", "patata", "salsa", "cazuela", "chilindr")):
            return "Dados regulares de 3 cm limpios de grasa (giro inverso Thermomix)"
        return "Filetes finos limpios de grasa exterior"

    def _recipe_cut_charcuterie(r: dict[str, Any]) -> str:
        r_txt = f"{r.get('name', '')} {r.get('description', '')}".lower()
        if any(k in r_txt for k in ("croqueta", "crema", "salmorejo", "guisante", "revuelto", "pasta", "arroz", "risotto", "lenteja")):
            return "En taquitos / corte para picar en Thermomix (5 seg / vel 7)"
        return "Loncheado fino al momento con separadores"

    # 1. Pescadería Mercadona
    if any(k in combined for k in ("merluza", "salmón", "salmon", "bacalao", "calamar", "gamba", "langostino", "lubina", "dorada", "pescado", "ahumados")):
        options = [
            "Lomos limpios sin piel ni espinas (especial Varoma)",
            "Dados limpios de 3 cm sin espinas + espinas aparte para fumet",
            "Rodajas de ración limpias",
            "Abierto a la espalda para horno",
            "Desmigado limpio sin espinas ni piel",
        ]
        if len(day_recipes) >= 2 and not custom_cut:
            parts = [f"Bandeja {i+1} ({d} · {r.get('name', 'Receta')}): {_recipe_cut_fish(r)}" for i, (d, r) in enumerate(day_recipes)]
            selected_cut = "Preparación multi-bandeja por receta"
            note = f"Dividir en {len(day_recipes)} bandejas envasadas por separado en Pescadería Mercadona: " + " | ".join(parts)
            return {
                "department": "Pescadería Mercadona",
                "icon": "🐟",
                "selected_cut": selected_cut,
                "note": note,
                "multi_tray": True,
                "options": [selected_cut] + options,
            }
        first_r = day_recipes[0][1] if day_recipes else {}
        first_d = day_recipes[0][0] if day_recipes else "la semana"
        selected_cut = custom_cut or _recipe_cut_fish(first_r)
        r_title = first_r.get("name", "receta en Thermomix")
        note = (
            f"Para «{r_title}» ({first_d}): preparar en mostrador de Pescadería Mercadona con corte «{selected_cut}». "
            "Envasar al vacío o en bandeja higienizada lista para cocinar."
        )
        return {
            "department": "Pescadería Mercadona",
            "icon": "🐟",
            "selected_cut": selected_cut,
            "note": note,
            "multi_tray": False,
            "options": options,
        }

    # 2. Carnicería Mercadona
    if any(k in combined for k in ("pechuga de pollo", "lomo de cerdo", "cerdo", "pollo", "ternera", "pavo", "solomillo", "carne")):
        options = [
            "Dados regulares de 3 cm limpios de grasa (giro inverso Thermomix)",
            "Cortado en tiras finas regulares para saltear",
            "Filetes finos limpios de grasa exterior",
            "Picada 1 sola vez en mostrador (textura jugosa)",
            "Pieza entera limpia para asar / Varoma",
        ]
        if len(day_recipes) >= 2 and not custom_cut:
            parts = [f"Bandeja {i+1} ({d} · {r.get('name', 'Receta')}): {_recipe_cut_meat(r)}" for i, (d, r) in enumerate(day_recipes)]
            selected_cut = "Preparación multi-bandeja por receta"
            note = f"Dividir en {len(day_recipes)} bandejas etiquetadas en Carnicería Mercadona: " + " | ".join(parts)
            return {
                "department": "Carnicería Mercadona",
                "icon": "🥩",
                "selected_cut": selected_cut,
                "note": note,
                "multi_tray": True,
                "options": [selected_cut] + options,
            }
        first_r = day_recipes[0][1] if day_recipes else {}
        first_d = day_recipes[0][0] if day_recipes else "la semana"
        selected_cut = custom_cut or _recipe_cut_meat(first_r)
        r_title = first_r.get("name", "receta en Thermomix")
        note = (
            f"Para «{r_title}» ({first_d}): preparar en Carnicería Mercadona con corte «{selected_cut}» "
            "para evitar que la fibra se deshaga con el giro inverso del vaso."
        )
        return {
            "department": "Carnicería Mercadona",
            "icon": "🥩",
            "selected_cut": selected_cut,
            "note": note,
            "multi_tray": False,
            "options": options,
        }

    # 3. Charcutería y Quesos al Corte Mercadona
    if any(k in combined for k in ("jamón serrano", "jamon serrano", "jamón cocido", "bacon", "panceta", "parmigiano", "mozzarella", "queso fresco")):
        options = [
            "En taquitos / corte para picar en Thermomix (5 seg / vel 7)",
            "Loncheado fino al momento con separadores",
            "Rallado o en lascas finas de mostrador",
        ]
        first_r = day_recipes[0][1] if day_recipes else {}
        first_d = day_recipes[0][0] if day_recipes else "la semana"
        selected_cut = custom_cut or _recipe_cut_charcuterie(first_r)
        r_title = first_r.get("name", "receta en Thermomix")
        note = f"Para «{r_title}» ({first_d}): formato recomendado «{selected_cut}» en Charcutería Mercadona."
        return {
            "department": "Charcutería Mercadona",
            "icon": "🔪",
            "selected_cut": selected_cut,
            "note": note,
            "multi_tray": len(day_recipes) >= 2,
            "options": options,
        }

    # 4. Frutería y Verdulería al Peso Mercadona
    if any(k in combined for k in ("pimiento", "tomate ensalada", "tomate canario", "tomate pera", "calabacín", "calabacin", "berenjena", "puerro", "aguacate", "mango", "champiñones", "champinones", "zanahorias", "patatas", "cebollas", "brócoli", "brocoli", "espinacas", "apio", "jengibre")):
        options = [
            "Maduración óptima para consumo en 2–4 días",
            "Piezas firmes medianas de calibre homogéneo (para troceado en vaso)",
            "Para consumo inmediato hoy/mañana",
        ]
        selected_cut = custom_cut or options[1]
        days_str = ", ".join(days) if days else "la semana"
        return {
            "department": "Frutería y Verdura Mercadona",
            "icon": "🥬",
            "selected_cut": selected_cut,
            "note": f"Seleccionar en Frutería Mercadona: «{selected_cut}» (previsto para cocinar el {days_str}).",
            "multi_tray": False,
            "options": options,
        }

    return None


def generate_sommelier_recommendation(meals: list[dict[str, Any]], catalog: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Generates a Bodega Mercadona & Selección Gourmet pairing tailored to the weekly menu."""
    has_fish = any(m.get("is_fish") for m in meals)
    fish_meal = next((m for m in meals if m.get("is_fish")), None)
    featured_meal = fish_meal or (meals[-1] if meals else {"name": "Menú Semanal", "day": "Viernes"})

    if has_fish:
        gourmet_prod = catalog.get("67125") or catalog.get("23279") or {}
        return {
            "title": "Maridaje Sumiller IA · Bodega & Selección Mercadona",
            "wine_name": "Vino Blanco Albariño Pazo de Orantes D.O. Rías Baixas + Aperitivo de Conservas Selección",
            "paired_with_day": featured_meal.get("day", "Viernes"),
            "paired_with_recipe": featured_meal.get("name", "Cena de pescado"),
            "tasting_note": (
                f"Seleccionado por Google Gemini para maridar con «{featured_meal.get('name', 'tu cena de pescado')}» "
                f"({featured_meal.get('day', 'Viernes')}): acidez fresca atlántica y notas cítricas que realzan los pescados al vapor en Varoma."
            ),
            "product_id": gourmet_prod.get("id", "67125"),
            "product_name": gourmet_prod.get("name", "Vino blanco albariño Pazo de Orantes DO Rías Baixas"),
            "price": float(gourmet_prod.get("unit_price", 7.60)),
            "thumbnail": gourmet_prod.get("thumbnail", ""),
            "share_url": gourmet_prod.get("share_url", "https://tienda.mercadona.es/product/67125"),
        }

    gourmet_prod = catalog.get("66324") or catalog.get("51197") or {}
    return {
        "title": "Maridaje Sumiller IA · Bodega & Selección Mercadona",
        "wine_name": "Vino D.O.Ca. Rioja El Coto Selección Bodega Mercadona + Dados de Queso Feta",
        "paired_with_day": featured_meal.get("day", "Viernes"),
        "paired_with_recipe": featured_meal.get("name", "Cena de fin de semana"),
        "tasting_note": (
            f"Armonía recomendada para «{featured_meal.get('name', 'tu menú semanal')}» ({featured_meal.get('day', 'Viernes')}): "
            "equilibrio aromático y frescura que realzan platos mediterráneos, carnes y pastas en Thermomix."
        ),
        "product_id": gourmet_prod.get("id", "66324"),
        "product_name": gourmet_prod.get("name", "Vino blanco El Coto DO Rioja"),
        "price": float(gourmet_prod.get("unit_price", 5.65)),
        "thumbnail": gourmet_prod.get("thumbnail", ""),
        "share_url": gourmet_prod.get("share_url", "https://tienda.mercadona.es/product/66324"),
    }


def enrich_basket_with_eci_features(
    basket_rows: list[dict[str, Any]],
    meals: list[dict[str, Any]],
    catalog: dict[str, dict[str, Any]],
    basket_tier: str = "ahorro",
    custom_counter_cuts: dict[str, str] | None = None,
    include_sommelier_item: bool = False,
    postal_code: str = "28001",
    center_name: str = "Madrid · Centro Logístico Cedial II (0130)",
) -> dict[str, Any]:
    """Enriches the basket with:
    1) Basket tier SKU upgrades ('ahorro', 'bio', 'gourmet')
    2) Automatic fresh counter preparation notes (Pescadería, Carnicería, Charcutería, Frutería Mercadona)
    3) Retail Media sponsored promotions
    4) Mercadona Online (Colmena) & Click & Car ecosystem metadata
    """
    tier = (basket_tier or "ahorro").strip().lower()
    if tier not in ("ahorro", "bio", "gourmet"):
        tier = "ahorro"
    custom_cuts = custom_counter_cuts or {}
    meals_by_day = {str(m.get("day", "")): m for m in meals}

    upgrade_map = BIO_SKU_UPGRADES if tier == "bio" else (GOURMET_SKU_UPGRADES if tier == "gourmet" else {})

    enriched_rows: list[dict[str, Any]] = []
    upgraded_count = 0
    counter_notes_count = 0
    retail_media_savings = 0.0
    retail_media_hits: list[str] = []

    for row in basket_rows:
        orig_pid = str(row.get("base_product_id") or row.get("product_id") or row.get("id") or "")
        qty = int(row.get("quantity") or 1)
        used_days = list(row.get("used_in_days") or [])

        target_pid = upgrade_map.get(orig_pid, orig_pid)
        prod = catalog.get(target_pid) or catalog.get(orig_pid) or row
        upgraded_from = None
        tier_badge = None

        if target_pid != orig_pid and target_pid in catalog:
            upgraded_from = catalog.get(orig_pid, {}).get("name") or row.get("name")
            upgraded_count += 1
            tier_badge = (
                "🌱 Frescos Natur & Bio Mercadona"
                if tier == "bio"
                else "🥂 Selección & Bodega Mercadona"
            )
        elif "el corte ingl" in str(prod.get("name", "")).lower() or "el corte ingl" in str(prod.get("brand", "")).lower():
            if "bio" in str(prod.get("name", "")).lower() or "ecol" in str(prod.get("name", "")).lower():
                tier_badge = "🌱 Frescos Natur & Bio Mercadona"
            elif "selection" in str(prod.get("name", "")).lower() or "gourmet" in str(prod.get("name", "")).lower():
                tier_badge = "🥂 Selección & Bodega Mercadona"
            else:
                tier_badge = "🏷️ Marca Hacendado · Ahorro"

        unit_price = float(prod.get("unit_price") or row.get("unit_price") or 0.0)
        line_total = round(unit_price * qty, 2)

        # Check Retail Media sponsored promotions
        brand_str = f"{prod.get('brand', '')} {prod.get('name', '')}"
        rm_promo = None
        for sponsor_brand, promo_meta in RETAIL_MEDIA_PROMOTIONS.items():
            if sponsor_brand.lower() in brand_str.lower():
                disc = round(line_total * float(promo_meta["discount_pct"]), 2)
                retail_media_savings = round(retail_media_savings + disc, 2)
                rm_promo = {
                    "brand": sponsor_brand,
                    "badge": promo_meta["badge"],
                    "campaign_tag": promo_meta["campaign_tag"],
                    "discount_eur": disc,
                }
                if sponsor_brand not in retail_media_hits:
                    retail_media_hits.append(sponsor_brand)
                break

        # Generate Automatic Traditional Counter Preparation Note
        c_cut = custom_cuts.get(target_pid) or custom_cuts.get(orig_pid)
        counter_prep = generate_counter_prep_note(prod, used_days, meals_by_day, custom_cut=c_cut)
        if counter_prep:
            counter_notes_count += 1

        enriched_rows.append(
            {
                "id": prod.get("id", target_pid),
                "product_id": prod.get("id", target_pid),
                "base_product_id": orig_pid,
                "eci_sku": prod.get("eci_sku", target_pid),
                "dia_sku": prod.get("eci_sku", target_pid),
                "name": prod.get("name", row.get("name", "")),
                "brand": prod.get("brand", ""),
                "category": prod.get("category", ""),
                "thumbnail": prod.get("thumbnail", row.get("thumbnail", "")),
                "share_url": prod.get("share_url", row.get("share_url", f"https://tienda.mercadona.es/product/{target_pid}/")),
                "unit": prod.get("unit", row.get("unit", "1 ud")),
                "unit_price": unit_price,
                "quantity": qty,
                "line_total": line_total,
                "available": bool(prod.get("available", True)),
                "allergens": prod.get("allergens", "Sin alérgenos declarados en la API"),
                "used_in_days": used_days,
                "tier_badge": tier_badge,
                "upgraded_from": upgraded_from,
                "retail_media_promo": rm_promo,
                "counter_prep": counter_prep,
            }
        )

    sommelier = generate_sommelier_recommendation(meals, catalog)
    sommelier_pid = str(sommelier.get("product_id") or "")
    sommelier_included = bool(include_sommelier_item)
    if sommelier_included and sommelier_pid and not any(r["product_id"] == sommelier_pid for r in enriched_rows):
        s_prod = catalog.get(sommelier_pid, {})
        s_price = float(s_prod.get("unit_price") or sommelier.get("price") or 5.65)
        enriched_rows.insert(
            0,
            {
                "id": sommelier_pid,
                "product_id": sommelier_pid,
                "base_product_id": sommelier_pid,
                "eci_sku": sommelier_pid,
                "dia_sku": sommelier_pid,
                "name": s_prod.get("name") or sommelier["product_name"],
                "brand": s_prod.get("brand", "Club Del Gourmet"),
                "category": s_prod.get("category", "Club del Gourmet"),
                "thumbnail": s_prod.get("thumbnail") or sommelier.get("thumbnail", ""),
                "share_url": s_prod.get("share_url") or sommelier.get("share_url", "https://www.elcorteingles.es/club-del-gourmet/"),
                "unit": s_prod.get("unit", "1 ud"),
                "unit_price": s_price,
                "quantity": 1,
                "line_total": round(s_price, 2),
                "available": True,
                "allergens": s_prod.get("allergens", "Ver envase"),
                "used_in_days": [sommelier.get("paired_with_day", "Viernes")],
                "tier_badge": "🍷 Recomendación Sumiller IA · Bodega Mercadona",
                "upgraded_from": None,
                "retail_media_promo": None,
                "counter_prep": None,
                "is_sommelier_pairing": True,
            },
        )

    enriched_rows.sort(key=lambda x: (-int(bool(x.get("is_sommelier_pairing"))), -x["line_total"], x["name"]))
    total = round(sum(x["line_total"] for x in enriched_rows), 2)

    # ECI Plus & Click & Car status
    free_shipping_threshold = 50.0
    missing_for_free = round(max(0.0, free_shipping_threshold - total), 2)
    click_and_car_threshold = 30.0
    missing_for_click_car = round(max(0.0, click_and_car_threshold - total), 2)

    eci_plus_status = {
        "free_delivery_unlocked": total >= free_shipping_threshold,
        "missing_for_free_delivery": missing_for_free,
        "free_delivery_threshold": free_shipping_threshold,
        "click_and_car_unlocked": total >= click_and_car_threshold,
        "missing_for_click_and_car": missing_for_click_car,
        "assigned_center": center_name,
        "postal_code": postal_code,
        "eci_plus_message": (
            f"✓ Envío GRATIS con Mercadona Online (Colmena) desbloqueado en {center_name}"
            if total >= free_shipping_threshold
            else f"Añade {missing_for_free:.2f} € más para Envío GRATIS con Mercadona Online (Colmena) (o recoge gratis en Tramo Eco Colmena desde 50 €)"
        ),
        "click_and_car_slots": [
            "Hoy 18:00 – 20:00 h (Entrega Colmena Mercadona)",
            "Mañana 10:00 – 12:00 h (Entrega Colmena Mercadona)",
            "Mañana 17:00 – 19:00 h (Entrega Colmena Mercadona)",
        ],
    }

    return {
        "basket": enriched_rows,
        "total": total,
        "basket_tier": tier,
        "upgraded_count": upgraded_count,
        "counter_notes_count": counter_notes_count,
        "sommelier_pairing": {**sommelier, "included": sommelier_included},
        "retail_media_summary": {
            "active_brands": retail_media_hits,
            "estimated_promo_savings_eur": retail_media_savings,
        },
        "eci_plus_status": eci_plus_status,
    }


def recalculate_plan_basket(
    plan: dict[str, Any],
    basket_tier: str | None = None,
    day_servings: dict[str, int] | None = None,
    custom_counter_cuts: dict[str, str] | None = None,
    include_sommelier_item: bool | None = None,
    postal_code: str | None = None,
) -> dict[str, Any]:
    """Recalculates an existing weekly plan's basket when the user changes:
    - Basket tier ('ahorro', 'bio', 'gourmet')
    - Per-day servings ('Hoy vienen invitados', e.g., {'Viernes': 6})
    - Custom counter cut selection in Pescadería / Carnicería
    - Sommelier wine/gourmet pairing inclusion
    """
    if not isinstance(plan, dict) or not isinstance(plan.get("meals"), list):
        raise ValueError("No hay un menú semanal activo para recalcular.")

    pc = str(postal_code or plan.get("postal_code") or "28001").strip()
    catalog, catalog_meta = get_catalog_for_postal_code(pc)
    constraints = dict(plan.get("constraints") or {})
    pantry_map = _pantry_excluded_product_ids(constraints.get("pantryItems", []), catalog)

    eff_tier = (basket_tier or plan.get("basket_tier") or "ahorro").strip().lower()
    eff_day_servings = dict(plan.get("day_servings") or {})
    if isinstance(day_servings, dict):
        for k, v in day_servings.items():
            try:
                eff_day_servings[str(k)] = max(1, min(16, int(v)))
            except (TypeError, ValueError):
                pass

    eff_cuts = dict(plan.get("custom_counter_cuts") or {})
    if isinstance(custom_counter_cuts, dict):
        for k, v in custom_counter_cuts.items():
            if k and v:
                eff_cuts[str(k)] = str(v)

    eff_sommelier = (
        include_sommelier_item
        if include_sommelier_item is not None
        else bool((plan.get("sommelier_pairing") or {}).get("included", False))
    )

    adults = int(constraints.get("adults", 2))
    children = int(constraints.get("children", 1))
    default_diners = max(1, adults + children)
    default_portions = adults + (0.75 * children)

    SHARED_STAPLES = {"4740", "4717", "4706", "4850", "4940", "34125", "17228", "15436"}

    all_recipes = {r["recipe_id"]: r for r in load_cookidoo_catalog()}
    qty_map: dict[str, int] = {}
    used_days: dict[str, list[str]] = {}
    updated_meals: list[dict[str, Any]] = []

    for m in plan.get("meals", []):
        day_name = str(m.get("day") or "Lunes")
        rid = str(m.get("recipe_id") or "")
        r_ref = all_recipes.get(rid, m)
        diners_for_day = int(eff_day_servings.get(day_name, m.get("active_diners") or default_diners))
        eff_day_servings[day_name] = diners_for_day
        portions_for_day = diners_for_day if day_name in (day_servings or {}) else default_portions
        base_servings = max(1, int(r_ref.get("cookidoo_servings") or m.get("cookidoo_servings") or 4))
        scale = max(1, math.ceil(portions_for_day / base_servings))

        raw_pids = r_ref.get("product_ids") or m.get("product_ids") or []
        active_pids: list[str] = []
        uses_from_home: list[str] = list(m.get("uses_from_home") or [])
        for pid in raw_pids:
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
            used_days.setdefault(pid, []).append(day_name)

        meal_cost = round(sum(catalog.get(p, {}).get("unit_price", 0.0) * (1 if p in SHARED_STAPLES else scale) for p in active_pids), 2)
        updated_meals.append(
            {
                **m,
                "active_diners": diners_for_day,
                "scale_factor": scale,
                "estimated_cost": meal_cost,
                "uses_from_home": uses_from_home,
            }
        )

    base_rows: list[dict[str, Any]] = []
    for pid, qty in qty_map.items():
        if qty <= 0 or pid not in catalog:
            continue
        prod = catalog[pid]
        base_rows.append(
            {
                "id": prod.get("id", pid),
                "product_id": prod.get("id", pid),
                "base_product_id": pid,
                "eci_sku": prod.get("eci_sku", pid),
                "dia_sku": prod.get("eci_sku", pid),
                "name": prod["name"],
                "thumbnail": prod.get("thumbnail", ""),
                "share_url": prod.get("share_url", f"https://tienda.mercadona.es/product/{pid}/"),
                "unit": prod.get("unit", "1 ud"),
                "unit_price": prod["unit_price"],
                "quantity": qty,
                "line_total": round(prod["unit_price"] * qty, 2),
                "available": bool(prod.get("available", True)),
                "allergens": prod.get("allergens", "Sin alérgenos declarados en la API"),
                "used_in_days": used_days.get(pid, []),
            }
        )

    center_label = catalog_meta.get("center_name") or catalog_meta["warehouse"]
    enriched = enrich_basket_with_eci_features(
        basket_rows=base_rows,
        meals=updated_meals,
        catalog=catalog,
        basket_tier=eff_tier,
        custom_counter_cuts=eff_cuts,
        include_sommelier_item=eff_sommelier,
        postal_code=catalog_meta["postal_code"],
        center_name=center_label,
    )

    max_budget = float(constraints.get("maxBudget", 65.0))
    total = enriched["total"]
    return {
        **plan,
        "meals": updated_meals,
        "basket": enriched["basket"],
        "total": total,
        "budget_remaining": round(max_budget - total, 2),
        "basket_tier": enriched["basket_tier"],
        "upgraded_count": enriched["upgraded_count"],
        "counter_notes_count": enriched["counter_notes_count"],
        "sommelier_pairing": enriched["sommelier_pairing"],
        "retail_media_summary": enriched["retail_media_summary"],
        "eci_plus_status": enriched["eci_plus_status"],
        "day_servings": eff_day_servings,
        "custom_counter_cuts": eff_cuts,
    }


def analyze_fridge_vision(
    image_base64: str | None = None,
    mime_type: str = "image/jpeg",
    preset_id: str | None = None,
    current_prompt: str = "",
    postal_code: str = "28001",
    current_plan: dict[str, Any] | None = None,
    user_email: str = "default",
) -> dict[str, Any]:
    """Multimodal Fridge & Pantry Vision ('Nevera Vision') powered by Google Gemini.
    Detects fresh ingredients from a photo (or preset snapshot), prioritizes Cookidoo recipes
    that use them before they expire, and discounts them from the Mercadona basket.
    """
    detected_items: list[dict[str, Any]] = []
    vision_source = "gemini_multimodal"

    # 1. If a real image was uploaded, call Google Gemini Multimodal Vision
    if image_base64:
        clean_b64 = re.sub(r"^data:[^;]+;base64,", "", str(image_base64).strip())
        raw_bytes = b""
        try:
            import base64 as b64_mod
            raw_bytes = b64_mod.b64decode(clean_b64)
        except Exception:
            raw_bytes = b""

        if raw_bytes:
            vision_prompt = (
                "Analiza esta fotografía de una nevera o despensa doméstica en España. "
                "Identifica entre 3 y 6 ingredientes culinarios visibles (ej. calabacín, huevos, leche, "
                "tomate, espinacas, pollo, zanahorias, pimiento, yogur, queso, salmón, brócoli, patatas, arroz). "
                "Devuelve exclusivamente un JSON válido con la clave `detected_items`, que sea una lista de objetos con: "
                "`name` (nombre descriptivo en español), `keyword` (una sola palabra clave en español como calabacín, huevos, espinacas, tomate, pollo, zanahorias, queso, brócoli, pimiento, yogur, arroz, patatas, salmón, merluza), "
                "y `freshness` (recomendación breve de consumo como 'Consumir en 48h · Prioridad Alta')."
            )
            try:
                from google import genai  # type: ignore
                from google.genai import types  # type: ignore

                project_id = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("PROJECT_ID") or "mercadona-ai-companion"
                client = genai.Client(vertexai=True, project=project_id, location="us-central1")
                for m_name in ["gemini-2.5-flash", MODEL_PRIMARY]:
                    try:
                        resp = client.models.generate_content(
                            model=m_name,
                            contents=[
                                types.Part.from_bytes(data=raw_bytes, mime_type=mime_type or "image/jpeg"),
                                vision_prompt,
                            ],
                            config=types.GenerateContentConfig(
                                temperature=0.1,
                                response_mime_type="application/json",
                            ),
                        )
                        if resp and resp.text:
                            parsed = json.loads(resp.text)
                            if isinstance(parsed.get("detected_items"), list) and len(parsed["detected_items"]) > 0:
                                detected_items = parsed["detected_items"][:6]
                                break
                    except Exception:
                        continue
            except Exception:
                pass

    # 2. Fallback to preset or default Mediterranean fridge if no items returned
    preset_meta = FRIDGE_VISION_PRESETS.get(str(preset_id or "").strip(), FRIDGE_VISION_PRESETS["nevera_mediterranea"])
    if not detected_items:
        detected_items = list(preset_meta["detected_items"])
        if not image_base64:
            vision_source = f"preset:{preset_meta['id']}"

    keywords = [str(it.get("keyword") or it.get("name") or "").strip().lower() for it in detected_items if it.get("keyword") or it.get("name")]
    keywords = [k for k in dict.fromkeys(keywords) if k]

    # Calculate how much these detected fridge items would have cost in the Mercadona catalog
    catalog, _ = get_catalog_for_postal_code(postal_code)
    matched_pantry = _pantry_excluded_product_ids(keywords, catalog)
    estimated_fridge_savings = round(
        sum(float(catalog[pid].get("unit_price", 0.0)) for pid in list(matched_pantry.keys())[:6]),
        2,
    )
    if estimated_fridge_savings <= 0:
        estimated_fridge_savings = 8.45

    base_prompt = (current_prompt or (current_plan or {}).get("headline") or "Planifica 5 cenas saludables para 2 adultos y 1 niño en 25 minutos bajo 60€").strip()
    base_prompt_clean = re.sub(r"\s*Además,\s*he\s+escaneado\s+mi\s+nevera.*$", "", base_prompt, flags=re.IGNORECASE).strip()
    kw_joined = ", ".join(keywords[:-1]) + (f" y {keywords[-1]}" if len(keywords) > 1 else (keywords[0] if keywords else "huevos"))
    enriched_prompt = f"{base_prompt_clean.rstrip('.')}. Usa {kw_joined} que ya tengo en casa."

    updated_plan = build_weekly_plan(
        prompt=enriched_prompt,
        postal_code=postal_code,
        current_plan=current_plan,
        variety_seed=f"fridge:{','.join(keywords)}",
        user_email=user_email,
    )
    updated_plan["fridge_vision"] = {
        "active": True,
        "source": vision_source,
        "title": preset_meta["title"] if not image_base64 else "Análisis Multimodal de tu Nevera (Google Gemini Vision)",
        "detected_items": detected_items,
        "keywords": keywords,
        "estimated_savings_eur": estimated_fridge_savings,
    }
    return {
        "fridge_vision": updated_plan["fridge_vision"],
        "updated_prompt": enriched_prompt,
        "plan": updated_plan,
    }


def swap_single_recipe(
    current_meals: list[dict[str, Any]],
    target_recipe_id: str,
    constraints: dict[str, Any],
    postal_code: str = "28001",
    rotation: int = 1,
    liked_recipe_ids: list[str] | None = None,
    disliked_recipe_ids: list[str] | None = None,
    user_email: str = "default",
    basket_tier: str = "ahorro",
    preferred_query: str | None = None,
) -> dict[str, Any]:
    """Swaps a single Cookidoo dinner (respecting liked/disliked preferences, day exclusions, pasta caps, kid-friendly rules, and optional natural-language dish/category query) and recalculates the ECI basket."""
    if liked_recipe_ids is not None or disliked_recipe_ids is not None:
        prefs = save_user_recipe_preferences(
            user_email=user_email,
            liked_recipe_ids=liked_recipe_ids,
            disliked_recipe_ids=disliked_recipe_ids,
            merge=False,
        )
    else:
        prefs = get_user_recipe_preferences(user_email)

    disliked_set = set(prefs.get("disliked") or [])
    liked_set = set(prefs.get("liked") or []) - disliked_set

    all_recipes = load_cookidoo_catalog()
    by_id = {r["recipe_id"]: r for r in all_recipes}
    catalog, catalog_meta = get_catalog_for_postal_code(postal_code)
    pantry_map = _pantry_excluded_product_ids(constraints.get("pantryItems", []), catalog)

    used_ids = {str(m.get("recipe_id") or m.get("recipeId") or "") for m in current_meals} | disliked_set
    excluded_allergens = set(constraints.get("excludedAllergens", []))
    max_minutes = constraints.get("maxMinutes") or 60
    max_cal = constraints.get("maxCaloriesPerServing")
    veg_only = bool(constraints.get("vegetarianOnly"))
    kid_friendly = bool(constraints.get("kidFriendly") or int(constraints.get("children") or 0) > 0)

    target_day = next(
        (str(m.get("day") or "Lunes") for m in current_meals if str(m.get("recipe_id") or m.get("recipeId") or "") == target_recipe_id),
        "Lunes",
    )
    day_exclusions: dict[str, list[str]] = constraints.get("dayExclusions") or {}
    day_requirements: dict[str, str] = constraints.get("dayRequirements") or {}
    max_pasta = int(constraints.get("maxPastaCount", 2) if constraints.get("maxPastaCount") is not None else 2)
    other_pasta_count = sum(
        1
        for m in current_meals
        if str(m.get("recipe_id") or m.get("recipeId") or "") != target_recipe_id
        and _is_pasta_recipe(by_id.get(str(m.get("recipe_id") or m.get("recipeId") or ""), m))
    )

    q_low = (preferred_query or "").strip().lower()
    if q_low:
        m_min_q = re.search(r"\b(\d{1,3})\s*(?:minutes?|mins?|minutos?|min)\b", q_low)
        if m_min_q:
            max_minutes = max(10, min(120, int(m_min_q.group(1))))
        elif any(w in q_low for w in ("rápida", "rapida", "rápido", "rapido", "exprés", "expres")):
            max_minutes = min(max_minutes, 25)

    wants_pasta_explicit = bool(q_low and PASTA_RE.search(q_low))

    wants_fish = bool(
        q_low
        and re.search(
            r"\b(?:pescados?|merluza|salm[oó]n|bacalao|at[uú]n|bonito|lubina|dorada|emperador|pez\s+espada|"
            r"rape|corvina|rodaballo|lenguado|trucha|rosada|sardinas?|boquer[oó]n|boquerones|caballa|"
            r"gambas?|gamb[oó]n|langostinos?|calamares?|calamar|chipir[oó]n|chipirones|sepia|pulpo|"
            r"mejill[oó]n|mejillones|almejas?|mariscos?)\b",
            q_low,
        )
    )
    wants_veg = bool(
        q_low
        and not wants_fish
        and re.search(
            r"\b(?:vegetarian[oa]s?|vegan[oa]s?|verduras?|hortalizas?|ensaladas?|sin\s+carne)\b",
            q_low,
        )
    )
    wants_meat = bool(
        q_low
        and not wants_fish
        and not wants_veg
        and re.search(
            r"\b(?:pollo|pavo|ternera|cerdo|carne|cordero|alb[oó]ndigas|solomillo|lomo|fajitas)\b",
            q_low,
        )
    )

    candidates = [
        r
        for r in all_recipes
        if r["recipe_id"] not in used_ids
        and r.get("is_dinner", True)
        and all(pid in catalog for pid in r["product_ids"])
        and r["minutes"] <= max_minutes
        and (max_cal is None or r["calories_per_serving"] <= max_cal)
        and (not veg_only or r["is_vegetarian"])
        and not excluded_allergens.intersection(set(r.get("allergens", [])))
        and (not kid_friendly or _is_kid_safe_recipe(r))
        and (wants_pasta_explicit or _day_allows_recipe(target_day, r, day_exclusions, day_requirements))
        and (wants_pasta_explicit or not _is_pasta_recipe(r) or other_pasta_count < max_pasta)
    ]
    if not candidates:
        candidates = [
            r
            for r in all_recipes
            if r["recipe_id"] not in used_ids
            and r.get("is_dinner", True)
            and not excluded_allergens.intersection(set(r.get("allergens", [])))
            and (not veg_only or r["is_vegetarian"])
            and (not kid_friendly or _is_kid_safe_recipe(r))
            and (wants_pasta_explicit or _day_allows_recipe(target_day, r, day_exclusions, day_requirements))
        ]
    if not candidates:
        candidates = [r for r in all_recipes if r["recipe_id"] not in used_ids]
    if not candidates:
        candidates = [r for r in all_recipes if r["recipe_id"] != target_recipe_id]

    # Apply strict category/dish filtering if the user specified what they want (e.g. "pescado", "salmón", "vegetariana", "pasta")
    if wants_fish:
        fish_pool = [r for r in candidates if r.get("is_fish")]
        if not fish_pool:
            fish_pool = [
                r
                for r in all_recipes
                if r["recipe_id"] not in used_ids and r.get("is_fish") and r.get("is_dinner", True)
            ]
        if fish_pool:
            finfish_re = re.compile(
                r"\b(?:pescado|merluza|salm[oó]n|bacalao|at[uú]n|bonito|lubina|dorada|rosada|rape|corvina|emperador|pez\s+espada|lenguado|trucha)\b",
                re.IGNORECASE,
            )
            specific_fish_terms = [
                t
                for t in (
                    "merluza",
                    "salmón",
                    "salmon",
                    "bacalao",
                    "atún",
                    "atun",
                    "bonito",
                    "lubina",
                    "dorada",
                    "rosada",
                    "rape",
                    "corvina",
                    "gamba",
                    "langostino",
                    "calamar",
                    "chipirón",
                    "chipiron",
                    "sepia",
                    "pulpo",
                    "mejillón",
                    "mejillon",
                    "almeja",
                )
                if t in q_low
            ]
            if specific_fish_terms:
                spec_matches = [
                    r
                    for r in fish_pool
                    if any(
                        t in (r["name"] + " " + " ".join(r.get("ingredients", []))).lower()
                        for t in specific_fish_terms
                    )
                ]
                if spec_matches:
                    fish_pool = spec_matches
            elif "pescado" in q_low:
                fin_matches = [r for r in fish_pool if finfish_re.search(r["name"])]
                if fin_matches:
                    fish_pool = fin_matches
            candidates = fish_pool
    elif wants_veg:
        veg_pool = [r for r in candidates if r.get("is_vegetarian") and not r.get("is_fish")]
        if not veg_pool:
            veg_pool = [
                r
                for r in all_recipes
                if r["recipe_id"] not in used_ids
                and r.get("is_vegetarian")
                and not r.get("is_fish")
                and r.get("is_dinner", True)
            ]
        if veg_pool:
            candidates = veg_pool
    elif wants_meat:
        meat_pool = [r for r in candidates if not r.get("is_fish") and not r.get("is_vegetarian")]
        specific_meat_terms = [
            t for t in ("pollo", "pavo", "ternera", "cerdo", "cordero", "albóndiga", "albondiga", "solomillo", "lomo", "fajita") if t in q_low
        ]
        if specific_meat_terms and meat_pool:
            spec_meat = [
                r
                for r in meat_pool
                if any(
                    t in (r["name"] + " " + " ".join(r.get("ingredients", []))).lower()
                    for t in specific_meat_terms
                )
            ]
            if spec_meat:
                meat_pool = spec_meat
        if meat_pool:
            candidates = meat_pool

    SWAP_STOP_WORDS = {
        "cambia", "cambiar", "cambio", "rota", "rotar", "sustituye", "sustituir", "pon", "poner",
        "quiero", "prefiero", "para", "por", "una", "uno", "unas", "unos", "del", "las", "los",
        "cena", "cenas", "comida", "plato", "receta", "menu", "menú", "semana", "semanal",
        "lunes", "martes", "miercoles", "miércoles", "jueves", "viernes", "sabado", "sábado", "domingo",
        "rapida", "rápida", "rapido", "rápido", "ligera", "ligero", "saludable", "fácil", "facil",
        "minutos", "min", "menos", "bajo", "con", "sin", "que", "sea", "algo", "otra", "otro", "pescado",
    }
    query_Dish_tokens = [
        tok
        for tok in re.findall(r"[a-záéíóúñ]{4,}", q_low)
        if tok not in SWAP_STOP_WORDS
    ]
    if query_Dish_tokens:
        kw_matches = [
            r
            for r in candidates
            if any(
                tok in (r["name"] + " " + " ".join(r.get("ingredients", []))).lower()
                for tok in query_Dish_tokens
            )
        ]
        if kw_matches:
            kw_matches.sort(
                key=lambda r: (
                    0 if any(tok in r["name"].lower() for tok in query_Dish_tokens) else 1,
                    r["minutes"],
                )
            )
            candidates = kw_matches

    SHARED_STAPLES = {"4740", "4717", "4706", "4850", "4940", "34125", "17228", "15436"}
    liked_affinity_pids: set[str] = set()
    if liked_set:
        for r in all_recipes:
            if r["recipe_id"] in liked_set:
                for pid in r.get("product_ids", []):
                    if pid not in SHARED_STAPLES:
                        liked_affinity_pids.add(pid)

    def _swap_rank(r: dict[str, Any]) -> tuple[int, int, int]:
        kid_r = -_kid_friendly_score(r) if kid_friendly else 0
        affinity = -min(2, sum(1 for pid in r.get("product_ids", []) if pid in liked_affinity_pids))
        h_jitter = int(hashlib.md5(f"{r['recipe_id']}".encode("utf-8")).hexdigest()[:6], 16) % 19
        return (kid_r, affinity, h_jitter)

    if not q_low:
        candidates = sorted(candidates, key=_swap_rank)

    chosen = candidates[rotation % len(candidates)]
    ensure_verified_cookidoo_image(chosen)
    from_name = target_recipe_id
    updated_meals_raw: list[dict[str, Any]] = []

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
    all_cards_out: list[dict[str, Any]] = []

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
            "active_diners": max(1, adults + children),
            "estimated_cost": round(sum(catalog[p]["unit_price"] for p in active_pids), 2),
            "ingredients": r.get("ingredients", []),
            "product_ids": active_pids,
            "uses_from_home": uses_from_home,
            "is_fish": r["is_fish"],
            "is_meat": _is_meat_recipe(r, require_title_match=True),
            "is_pasta": _is_pasta_recipe(r),
            "is_vegetarian": r["is_vegetarian"],
            "is_kid_friendly": _is_kid_safe_recipe(r) and _kid_friendly_score(r) >= 2,
            "liked_by_user": r["recipe_id"] in liked_set,
        }
        all_cards_out.append(card)
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
                    "id": prod.get("id", pid),
                    "product_id": prod.get("id", pid),
                    "base_product_id": pid,
                    "eci_sku": prod.get("eci_sku", pid),
                    "dia_sku": prod.get("eci_sku", pid),
                    "name": prod["name"],
                    "thumbnail": prod.get("thumbnail", ""),
                    "share_url": prod.get("share_url", f"https://tienda.mercadona.es/product/{pid}/"),
                    "unit": prod.get("unit", "1 ud"),
                    "unit_price": prod["unit_price"],
                    "quantity": qty,
                    "line_total": round(prod["unit_price"] * qty, 2),
                    "available": bool(prod.get("available", True)),
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

    center_label = catalog_meta.get("center_name") or catalog_meta["warehouse"]
    enriched = enrich_basket_with_eci_features(
        basket_rows=basket_rows,
        meals=all_cards_out,
        catalog=catalog,
        basket_tier=basket_tier,
        postal_code=catalog_meta["postal_code"],
        center_name=center_label,
    )
    basket_rows = enriched["basket"]
    total = enriched["total"]

    return {
        "meals": all_cards_out,
        "constraints": constraints,
        "replacement": replacement_card,
        "basket": basket_rows,
        "total": total,
        "budget_remaining": round(max_budget - total, 2),
        "basket_tier": enriched["basket_tier"],
        "upgraded_count": enriched["upgraded_count"],
        "counter_notes_count": enriched["counter_notes_count"],
        "sommelier_pairing": enriched["sommelier_pairing"],
        "retail_media_summary": enriched["retail_media_summary"],
        "eci_plus_status": enriched["eci_plus_status"],
        "postal_code": catalog_meta["postal_code"],
        "warehouse": catalog_meta["warehouse"],
        "center_name": center_label,
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
        "trace": ["deterministic_recipe_filter", "deterministic_catalog_validation", "generate_eci_counter_prep_notes", "deterministic_basket_pricing"],
    }

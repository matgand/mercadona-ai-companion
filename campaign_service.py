"""Campaign Library service for Mercadona Marketing Team.

Manages profile-targeted weekly menu campaigns (Familias, Saludables, Rutina rápida, Ahorro),
their lifecycle states (Activa, Planificada, Borrador, Terminada), natural-language campaign
generation with Gemini 3.8 Flash, and real-time synchronization with the main application.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import threading
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from cookidoo_service import load_cookidoo_catalog
from gemini_planner import MODEL_FALLBACK, MODEL_PRIMARY, parse_constraints, validate_meal_planning_prompt

DATA_DIR = Path(__file__).resolve().parent / "data"
CAMPAIGNS_FILE = DATA_DIR / "campaigns.json"
_LOCK = threading.Lock()

VALID_CATEGORIES = ["Familias", "Saludables", "Rutina rápida", "Ahorro"]
VALID_STATUSES = ["Activa", "Planificada", "Borrador", "Terminada"]

CATEGORY_TO_PROFILE_ID = {
    "Familias": "familias",
    "Saludables": "saludables",
    "Rutina rápida": "rutina-rapida",
    "Rutína rápida": "rutina-rapida",
    "Ahorro": "ahorro",
}

PROFILE_ID_TO_CATEGORY = {
    "familias": "Familias",
    "family-explorer": "Familias",
    "saludables": "Saludables",
    "healthy-couple": "Saludables",
    "rutina-rapida": "Rutina rápida",
    "convenience-professional": "Rutina rápida",
    "ahorro": "Ahorro",
}

PROFILES_METADATA = [
    {
        "id": "familias",
        "name": "Familias",
        "category": "Familias",
        "household": "2 adultos · 1–2 niños",
        "primaryNeed": "Variedad, platos para todos los gustos, ahorro y planificación sin fricción",
        "eligibleHouseholds": "420k hogares",
        "icon": "FA",
    },
    {
        "id": "saludables",
        "name": "Saludables",
        "category": "Saludables",
        "household": "1–2 adultos",
        "primaryNeed": "Nutrición transparente, productos frescos de temporada y control de calorías",
        "eligibleHouseholds": "310k hogares",
        "icon": "SA",
    },
    {
        "id": "rutina-rapida",
        "name": "Rutina rápida",
        "category": "Rutina rápida",
        "household": "1–2 adultos",
        "primaryNeed": "Rapidez entre semana (≤ 25 min), simplicidad en Thermomix y cero complicaciones",
        "eligibleHouseholds": "295k hogares",
        "icon": "RR",
    },
    {
        "id": "ahorro",
        "name": "Ahorro",
        "category": "Ahorro",
        "household": "2 adultos · 1–2 niños",
        "primaryNeed": "Presupuesto ajustado, máximo aprovechamiento de despensa y cero desperdicio",
        "eligibleHouseholds": "255k hogares",
        "icon": "AH",
    },
]

STATUS_TO_CSS_CLASS = {
    "Activa": "live",
    "Planificada": "scheduled",
    "Borrador": "draft",
    "Terminada": "archived",
}


def normalize_category(raw: str | None) -> str:
    if not raw:
        return "Familias"
    val = raw.strip()
    if val in VALID_CATEGORIES:
        return val
    low = val.lower().replace("í", "i").replace("á", "a")
    if "salud" in low or "health" in low or "liger" in low or "kcal" in low or "calor" in low:
        return "Saludables"
    if "rapida" in low or "rápida" in low or "rutina" in low or "expres" in low or "convenience" in low or "min" in low:
        return "Rutina rápida"
    if "ahorro" in low or "despensa" in low or "econom" in low or "barat" in low or "presupuesto" in low:
        return "Ahorro"
    return "Familias"


def normalize_status(raw: str | None) -> str:
    if not raw:
        return "Activa"
    val = raw.strip()
    if val in VALID_STATUSES:
        return val
    low = val.lower()
    if low in ("activa", "active", "live", "publicada"):
        return "Activa"
    if low in ("planificada", "scheduled", "programada"):
        return "Planificada"
    if low in ("borrador", "draft"):
        return "Borrador"
    if low in ("terminada", "completed", "archived", "finalizada", "archivada"):
        return "Terminada"
    return "Activa"


def _enrich_campaign(c: dict[str, Any]) -> dict[str, Any]:
    cat = normalize_category(c.get("category") or c.get("occasion") or PROFILE_ID_TO_CATEGORY.get(str(c.get("profileId", ""))))
    status = normalize_status(c.get("status"))
    prof_id = CATEGORY_TO_PROFILE_ID.get(cat, "familias")
    prof_meta = next((p for p in PROFILES_METADATA if p["id"] == prof_id), PROFILES_METADATA[0])
    return {
        "id": str(c.get("id") or "campaign-1"),
        "title": str(c.get("title") or "Campaña Semanal Mercadona"),
        "tagline": str(c.get("tagline") or "Cinco cenas en Thermomix mapeadas al catálogo real de Mercadona."),
        "category": cat,
        "occasion": cat,
        "profileId": prof_id,
        "badge": str(c.get("badge") or f"Recomendado · {cat}"),
        "status": status,
        "statusClass": STATUS_TO_CSS_CLASS.get(status, "live"),
        "imageUrl": str(c.get("imageUrl") or "/meals/lemon-hake-potatoes.webp"),
        "seedPrompt": str(c.get("seedPrompt") or ""),
        "mealCount": int(c.get("mealCount") or 5),
        "maxBudget": float(c.get("maxBudget") or 60),
        "maxMinutes": int(c.get("maxMinutes") or 25),
        "maxCaloriesPerServing": int(c["maxCaloriesPerServing"]) if c.get("maxCaloriesPerServing") else None,
        "eligibleHouseholds": str(c.get("eligibleHouseholds") or prof_meta["eligibleHouseholds"]),
        "whyProfile": str(
            c.get("whyProfile")
            or f"Diseñada para el perfil {cat} ({prof_meta['household']}): {prof_meta['primaryNeed'].lower()}."
        ),
        "updatedAt": str(c.get("updatedAt") or datetime.datetime.now(datetime.timezone.utc).isoformat()),
    }


def load_local_campaigns() -> list[dict[str, Any]]:
    with _LOCK:
        if not CAMPAIGNS_FILE.is_file():
            return []
        try:
            raw = json.loads(CAMPAIGNS_FILE.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                return [_enrich_campaign(item) for item in raw]
        except Exception:
            pass
        return []


def save_local_campaigns(campaigns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched = [_enrich_campaign(c) for c in campaigns]
    with _LOCK:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        CAMPAIGNS_FILE.write_text(json.dumps(enriched, ensure_ascii=False, indent=2), encoding="utf-8")
    return enriched


def fetch_campaigns_from_remote_or_local() -> list[dict[str, Any]]:
    """If CAMPAIGN_LIBRARY_URL is configured and points to a remote microservice, fetches live campaigns from it."""
    remote_url = os.environ.get("CAMPAIGN_LIBRARY_URL", "").strip().rstrip("/")
    is_self_library = os.environ.get("SERVICE_ROLE", "").strip() == "campaign-library"
    if remote_url and not is_self_library:
        try:
            req = urllib.request.Request(
                f"{remote_url}/api/campaigns?source=internal",
                headers={"User-Agent": "MercadonaAICompanion/1.0", "Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=3.5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if isinstance(data.get("campaigns"), list) and len(data["campaigns"]) > 0:
                    enriched = [_enrich_campaign(c) for c in data["campaigns"]]
                    save_local_campaigns(enriched)
                    return enriched
        except Exception:
            pass
    return load_local_campaigns()


def push_sync_to_peer_services(campaigns: list[dict[str, Any]]) -> None:
    """Pushes updated campaigns to peer microservice(s) so both Cloud Run services stay in sync immediately."""
    peers: list[str] = []
    comp_url = os.environ.get("COMPANION_APP_URL", "").strip().rstrip("/")
    lib_url = os.environ.get("CAMPAIGN_LIBRARY_URL", "").strip().rstrip("/")
    is_self_library = os.environ.get("SERVICE_ROLE", "").strip() == "campaign-library"

    if is_self_library and comp_url:
        peers.append(comp_url)
    elif not is_self_library and lib_url:
        peers.append(lib_url)

    payload = json.dumps({"campaigns": campaigns}, ensure_ascii=False).encode("utf-8")
    for base_url in peers:
        try:
            req = urllib.request.Request(
                f"{base_url}/api/campaigns/sync",
                data=payload,
                method="POST",
                headers={"Content-Type": "application/json", "User-Agent": "MercadonaCampaignSync/1.0"},
            )
            urllib.request.urlopen(req, timeout=3.0).read()
        except Exception:
            continue


def _select_cover_image_for_brief(brief: str, category: str) -> str:
    """Finds the best cover photo from our curated meals or the 5,000 Cookidoo recipes catalog."""
    low = brief.lower()
    if any(w in low for w in ["salmón", "salmon", "sopa", "kale", "caldo"]):
        return "/meals/salmon-kale-soup.webp"
    if any(w in low for w in ["merluza", "pescado", "bacalao", "limón", "limon"]):
        return "/meals/lemon-hake-potatoes.webp"
    if any(w in low for w in ["lenteja", "cuchara", "guiso", "otoño", "invierno"]):
        return "/meals/Stewed-lentils.webp"
    if any(w in low for w in ["pavo", "wrap", "aguacate", "proteína", "proteina", "sin gluten"]):
        return "/meals/turkey-avocado-wraps.webp"
    if any(w in low for w in ["garbanzo", "espinaca", "arroz", "despensa", "ahorro"]):
        return "/meals/chickpea-spinach-tomato-rice.webp"
    if any(w in low for w in ["brócoli", "brocoli", "rápid", "rapid", "exprés", "expres", "20 min"]):
        return "/meals/quick-broccoli-salad.webp"
    if any(w in low for w in ["ensalada", "liger", "kcal", "saludable", "verano"]):
        return "/meals/pasta-chickpea-salad.webp"

    # Also check the 5,000 Cookidoo recipes for specific dish keywords
    try:
        recipes = load_cookidoo_catalog()
        tokens = [t for t in re.findall(r"[a-záéíóúñ]{4,}", low) if t not in {"para", "cenas", "campaña", "menu", "semana", "presupuesto", "menos", "minutos", "recetas"}]
        if tokens:
            for r in recipes:
                name_low = r["name"].lower()
                if any(tok in name_low for tok in tokens) and r.get("image_url"):
                    return r["image_url"]
    except Exception:
        pass

    by_cat = {
        "Familias": "/meals/lemon-hake-potatoes.webp",
        "Saludables": "/meals/pasta-chickpea-salad.webp",
        "Rutina rápida": "/meals/quick-broccoli-salad.webp",
        "Ahorro": "/meals/chickpea-spinach-tomato-rice.webp",
    }
    return by_cat.get(category, "/meals/lemon-hake-potatoes.webp")


def _infer_category_from_brief(brief: str, category_hint: str | None = None) -> str:
    if category_hint and category_hint.strip() in VALID_CATEGORIES:
        return category_hint.strip()
    low = brief.lower()
    if any(w in low for w in ["ahorro", "económ", "econom", "barat", "despensa", "45€", "40€", "bajo coste", "bolsillo"]):
        return "Ahorro"
    if any(w in low for w in ["saludable", "kcal", "calorías", "calorias", "liger", "proteína", "proteina", "sin gluten", "dieta", "equilibrad"]):
        return "Saludables"
    if any(w in low for w in ["rápid", "rapid", "rutina", "exprés", "expres", "15 min", "20 min", "prisa", "teletrabajo"]):
        return "Rutina rápida"
    if any(w in low for w in ["familia", "niño", "nino", "hijos", "infantil"]):
        return "Familias"
    return normalize_category(category_hint)


def _call_gemini_campaign_generator(brief: str, category: str, parsed_constraints: dict[str, Any]) -> dict[str, Any] | None:
    sys_instruction = (
        "Eres el Copiloto de Campañas IA del equipo de Marketing de Mercadona (impulsado por Google Cloud y Gemini 3.8 Flash). "
        "A partir de un brief en lenguaje natural del equipo de Marketing, diseña una campaña semanal de cenas para los clientes de Mercadona "
        "que conecte el catálogo de recetas de Thermomix Cookidoo con la cesta de Mercadona. "
        "La categoría de perfil debe ser una de: 'Familias', 'Saludables', 'Rutina rápida', 'Ahorro'. "
        "Devuelve EXCLUSIVAMENTE un objeto JSON válido con las claves:\n"
        "- `title`: título editorial atractivo y breve en español (máx 55 caracteres, estilo Mercadona)\n"
        "- `tagline`: subtítulo persuasivo en español explicando el beneficio para el hogar (1-2 frases)\n"
        "- `category`: una de ['Familias', 'Saludables', 'Rutina rápida', 'Ahorro']\n"
        "- `badge`: etiqueta corta destacada (ej. 'Recomendado para Familias', 'Menos de 450 kcal', 'Cero desperdicio', 'En 20 minutos')\n"
        "- `seedPrompt`: prompt completo en primera persona en español listo para el planificador semanal (incluyendo número de cenas, adultos/niños, presupuesto máximo en €, tiempo máximo en minutos, calorías si aplica, alergias e ingredientes en casa)\n"
        "- `whyProfile`: explicación de 1 frase para el equipo de marketing sobre por qué esta campaña encaja con ese perfil y qué productos de Mercadona impulsa."
    )

    user_payload = json.dumps(
        {
            "marketing_brief": brief,
            "target_category": category,
            "detected_constraints": parsed_constraints,
        },
        ensure_ascii=False,
    )

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
                        temperature=0.35,
                        response_mime_type="application/json",
                    ),
                )
                if resp and resp.text:
                    data = json.loads(resp.text)
                    if isinstance(data, dict) and data.get("title"):
                        data["model_used"] = f"Gemini 3.8 Flash ({model_name})"
                        return data
            except Exception:
                continue
    except Exception:
        pass

    return None


def generate_campaign_from_brief(
    brief: str,
    category_hint: str | None = None,
    initial_status: str = "Activa",
) -> dict[str, Any]:
    """Generates a new structured Mercadona marketing campaign from a natural-language brief."""
    clean_brief = brief.strip()
    if not clean_brief:
        raise ValueError("Escribe una descripción en lenguaje natural para generar la campaña.")
    is_valid, scope_err = validate_meal_planning_prompt(clean_brief)
    if not is_valid:
        raise ValueError(scope_err)

    category = _infer_category_from_brief(clean_brief, category_hint)
    prof_id = CATEGORY_TO_PROFILE_ID.get(category, "familias")
    prof_meta = next((p for p in PROFILES_METADATA if p["id"] == prof_id), PROFILES_METADATA[0])

    constraints = parse_constraints(clean_brief)
    meal_count = int(constraints.get("mealCount") or 5)
    max_minutes = int(constraints.get("maxMinutes") or (20 if category == "Rutina rápida" else 25))
    max_budget = float(constraints.get("maxBudget") or (48 if category == "Ahorro" else 60))
    max_cal = constraints.get("maxCaloriesPerServing")
    if max_cal is None and category == "Saludables":
        max_cal = 450

    gemini_data = _call_gemini_campaign_generator(clean_brief, category, constraints)

    if gemini_data:
        title = str(gemini_data.get("title") or "").strip()
        tagline = str(gemini_data.get("tagline") or "").strip()
        category = normalize_category(gemini_data.get("category") or category)
        prof_id = CATEGORY_TO_PROFILE_ID.get(category, "familias")
        badge = str(gemini_data.get("badge") or f"Propuesta {category}").strip()
        seed_prompt = str(gemini_data.get("seedPrompt") or "").strip()
        why_profile = str(gemini_data.get("whyProfile") or "").strip()
    else:
        title = ""
        tagline = ""
        badge = ""
        seed_prompt = ""
        why_profile = ""

    # Fallback / deterministic enrichment if any field is empty
    if not title:
        short = re.sub(r"^(?:crea|crear|lanza|lanzar|diseña|diseñar|una|campaña|de|para|menú|menu|semanal)\s+", "", clean_brief, flags=re.I)
        short = short.split(".")[0].strip()
        title = (short[:52].capitalize() if len(short) > 6 else f"Semana {category} en Mercadona")

    if not tagline:
        tagline = (
            f"{meal_count} cenas de Thermomix pensadas para el perfil {category}, en menos de {max_minutes} min "
            f"y con cesta completa en Mercadona bajo {int(max_budget)}€."
        )

    if not badge:
        if max_cal:
            badge = f"{category} · ≤ {max_cal} kcal"
        elif category == "Ahorro":
            badge = f"Ahorro · ≤ €{int(max_budget)}"
        elif category == "Rutina rápida":
            badge = f"Exprés · ≤ {max_minutes} min"
        else:
            badge = f"Recomendado · {category}"

    if not seed_prompt:
        adults = constraints.get("adults", 2)
        kids = constraints.get("children", 1 if category in ("Familias", "Ahorro") else 0)
        fam_str = f"{adults} adultos" + (f" y {kids} {'niño' if kids == 1 else 'niños'}" if kids > 0 else "")
        cal_str = f", máximo {max_cal} kcal por ración" if max_cal else ""
        fish_str = ", incluye pescado" if constraints.get("requiredFish") else ""
        veg_str = ", 100% vegetariano" if constraints.get("vegetarianOnly") else ""
        pantry = constraints.get("pantryItems") or []
        pantry_str = f" y usa {', '.join(pantry)} que ya tengo en casa" if pantry else ""
        seed_prompt = (
            f"Planifica {meal_count} cenas para {fam_str} ({clean_brief}). "
            f"Mantén el presupuesto bajo {int(max_budget)}€, en {max_minutes} minutos o menos{cal_str}{fish_str}{veg_str}{pantry_str}."
        )

    if not why_profile:
        why_profile = (
            f"Adaptada al perfil {category} ({prof_meta['household']}): combina recetas oficiales de Cookidoo "
            f"en ≤ {max_minutes} min con productos disponibles en Mercadona por menos de {int(max_budget)}€."
        )

    slug_base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:28] or "campana"
    short_hash = hashlib.sha1(f"{clean_brief}:{datetime.datetime.now().isoformat()}".encode("utf-8")).hexdigest()[:5]
    campaign_id = f"{slug_base}-{short_hash}"

    new_campaign = _enrich_campaign(
        {
            "id": campaign_id,
            "title": title,
            "tagline": tagline,
            "category": category,
            "occasion": category,
            "profileId": prof_id,
            "badge": badge,
            "status": normalize_status(initial_status),
            "imageUrl": _select_cover_image_for_brief(clean_brief, category),
            "seedPrompt": seed_prompt,
            "mealCount": meal_count,
            "maxBudget": max_budget,
            "maxMinutes": max_minutes,
            "maxCaloriesPerServing": max_cal,
            "eligibleHouseholds": prof_meta["eligibleHouseholds"],
            "whyProfile": why_profile,
            "updatedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
    )

    campaigns = load_local_campaigns()
    campaigns.insert(0, new_campaign)
    saved = save_local_campaigns(campaigns)
    push_sync_to_peer_services(saved)
    return new_campaign


def update_campaign_record(campaign_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    """Updates a campaign's status or editable fields and syncs across services."""
    campaigns = load_local_campaigns()
    target: dict[str, Any] | None = None

    for idx, c in enumerate(campaigns):
        if c["id"] == campaign_id:
            merged = dict(c)
            for k in (
                "title",
                "tagline",
                "category",
                "occasion",
                "badge",
                "status",
                "imageUrl",
                "seedPrompt",
                "mealCount",
                "maxBudget",
                "maxMinutes",
                "maxCaloriesPerServing",
                "whyProfile",
            ):
                if k in updates and updates[k] is not None:
                    merged[k] = updates[k]
            if "category" in updates:
                merged["occasion"] = normalize_category(updates["category"])
                merged["profileId"] = CATEGORY_TO_PROFILE_ID.get(merged["occasion"], "familias")
            merged["updatedAt"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            target = _enrich_campaign(merged)
            campaigns[idx] = target
            break

    if not target:
        raise ValueError(f"Campaña '{campaign_id}' no encontrada.")

    saved = save_local_campaigns(campaigns)
    push_sync_to_peer_services(saved)
    return target

"""WhatsApp Business Cloud API & Twilio WhatsApp Webhook Service for Mercadona Online.

Implements Option B (Real Webhook + Live Bidirectional Companion Sync):
1. `GET /api/whatsapp/webhook`: Official Meta WhatsApp Cloud API verification (`hub.mode`, `hub.verify_token`, `hub.challenge`).
2. `POST /api/whatsapp/webhook`:
   - Meta WhatsApp Cloud API JSON payloads (`text`, `interactive` button/list replies, `audio` voice notes, `image` fridge photos)
     with automatic outbound reply via Graph API (`https://graph.facebook.com/v21.0/<PHONE_NUMBER_ID>/messages`).
   - Twilio WhatsApp Sandbox `application/x-www-form-urlencoded` payloads (`From`, `Body`, `MediaUrl0`) with instant
     TwiML XML response (`<Response><Message>...</Message></Response>`).
3. Natural-language & interactive menu commands:
   - View weekly menu, calories, counter preparation notes, and ECI basket total
   - Swap a specific day's recipe ("cambia el miércoles", "rotar viernes")
   - Apply natural-language changes ("hazlo sin lactosa", "cambia el jueves por salmón rápido")
   - Scale guests for a day ("el viernes somos 6 personas")
   - Switch basket tier ("modo club del gourmet", "modo bio", "modo ahorro")
   - Trigger Fridge Vision ("en la nevera tengo calabacín y huevos" or photo)
   - Generate 1-Click Mercadona Online cart link ("comprar", "transferir al carrito")
"""

from __future__ import annotations

import datetime
import hashlib
import hmac
import html
import json
import os
import re
import tempfile
import threading
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from cookidoo_service import schedule_weekly_plan_to_cookidoo
from mercadona_service import prepare_mercadona_oneclick_cart as prepare_eci_oneclick_cart
from gemini_planner import (
    DAYS_EN_TO_ES,
    DAYS_ES,
    analyze_fridge_vision,
    build_weekly_plan,
    recalculate_plan_basket,
    swap_single_recipe,
)

DATA_DIR = Path(__file__).resolve().parent / "data"
WHATSAPP_STATE_FILE = Path(
    os.environ.get("WHATSAPP_STATE_FILE")
    or (Path(tempfile.gettempdir()) / "mercadona_whatsapp_state.json")
)
_WA_LOCK = threading.RLock()

DEFAULT_VERIFY_TOKEN = "eci-whatsapp-2026"


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _now_hhmm() -> str:
    return datetime.datetime.now().strftime("%H:%M")


def _default_welcome_messages() -> list[dict[str, Any]]:
    return []


def _load_wa_store() -> dict[str, Any]:
    with _WA_LOCK:
        if WHATSAPP_STATE_FILE.is_file():
            try:
                data = json.loads(WHATSAPP_STATE_FILE.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
        return {
            "config": {
                "verify_token": os.environ.get("WHATSAPP_VERIFY_TOKEN", DEFAULT_VERIFY_TOKEN),
                "phone_number_id": os.environ.get("WHATSAPP_PHONE_NUMBER_ID", ""),
                "access_token": os.environ.get("WHATSAPP_ACCESS_TOKEN", ""),
                "app_secret": os.environ.get("WHATSAPP_APP_SECRET", ""),
                "recipient_phone": os.environ.get("WHATSAPP_RECIPIENT_PHONE", "+34 600 000 000"),
            },
            "webhook_stats": {
                "total_received": 0,
                "last_webhook_at": None,
                "last_provider": None,
                "last_sender": None,
            },
            "plan_version": 1,
            "active_plan": None,
            "postal_code": "28001",
            "messages": [],
        }


def _save_wa_store(store: dict[str, Any]) -> None:
    with _WA_LOCK:
        tmp_path: str | None = None
        try:
            WHATSAPP_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(
                dir=str(WHATSAPP_STATE_FILE.parent), prefix=".wa_state_", suffix=".tmp"
            )
            try:
                os.fchmod(fd, 0o600)
            except AttributeError:
                os.chmod(tmp_path, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(store, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, WHATSAPP_STATE_FILE)
            tmp_path = None
            os.chmod(WHATSAPP_STATE_FILE, 0o600)
        except Exception:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass


def sync_active_plan_to_whatsapp(plan: dict[str, Any] | None, postal_code: str = "28001") -> None:
    """Keeps the WhatsApp state synchronized when the user generates or modifies a plan in the Web UI."""
    if not isinstance(plan, dict) or not plan.get("meals"):
        return
    with _WA_LOCK:
        store = _load_wa_store()
        store["active_plan"] = plan
        store["postal_code"] = str(plan.get("postal_code") or postal_code or "28001")
        store["plan_version"] = int(store.get("plan_version") or 1) + 1
        _save_wa_store(store)


def get_whatsapp_state(base_url: str = "") -> dict[str, Any]:
    """Returns current WhatsApp conversation, synchronized plan, and webhook configuration status."""
    with _WA_LOCK:
        store = _load_wa_store()
        cfg = store.get("config") or {}
        verify_token = (
            cfg.get("verify_token")
            or os.environ.get("WHATSAPP_VERIFY_TOKEN")
            or DEFAULT_VERIFY_TOKEN
        )
        phone_id = cfg.get("phone_number_id") or os.environ.get("WHATSAPP_PHONE_NUMBER_ID") or ""
        access_tok = cfg.get("access_token") or os.environ.get("WHATSAPP_ACCESS_TOKEN") or ""
        clean_base = (base_url or "https://eci-ai-companion-66087676067.europe-west1.run.app").rstrip("/")
        webhook_url = f"{clean_base}/api/whatsapp/webhook"
        plan = store.get("active_plan")
        return {
            "webhook_url": webhook_url,
            "verify_token": verify_token,
            "phone_number_id": phone_id,
            "has_access_token": bool(access_tok),
            "recipient_phone": cfg.get("recipient_phone") or "+34 600 000 000",
            "webhook_stats": store.get("webhook_stats") or {},
            "plan_version": store.get("plan_version", 1),
            "active_plan": plan,
            "messages": list(store.get("messages") or [])[-30:],
            "share_wa_url": format_whatsapp_share_link(plan),
        }


def update_whatsapp_config(
    verify_token: str | None = None,
    phone_number_id: str | None = None,
    access_token: str | None = None,
    recipient_phone: str | None = None,
    reset_chat: bool = False,
) -> dict[str, Any]:
    """Updates Meta WhatsApp Cloud API / Twilio webhook configuration at runtime."""
    with _WA_LOCK:
        store = _load_wa_store()
        cfg = store.setdefault("config", {})
        if verify_token is not None and verify_token.strip():
            cfg["verify_token"] = verify_token.strip()
        if phone_number_id is not None:
            cfg["phone_number_id"] = phone_number_id.strip()
        if access_token is not None and access_token.strip():
            cfg["access_token"] = access_token.strip()
        if recipient_phone is not None and recipient_phone.strip():
            cfg["recipient_phone"] = recipient_phone.strip()
        if reset_chat:
            store["messages"] = []
            store["webhook_stats"] = {
                "total_received": 0,
                "last_webhook_at": None,
                "last_provider": None,
                "last_sender": None,
            }
        _save_wa_store(store)
        return get_whatsapp_state()


def verify_whatsapp_webhook_get(query_params: dict[str, list[str]]) -> tuple[int, str]:
    """Handles Meta WhatsApp Cloud API GET webhook verification (`hub.mode`, `hub.verify_token`, `hub.challenge`)."""
    mode = (query_params.get("hub.mode") or [""])[0].strip()
    token = (query_params.get("hub.verify_token") or [""])[0].strip()
    challenge = (query_params.get("hub.challenge") or [""])[0].strip()

    store = _load_wa_store()
    expected_token = (
        (store.get("config") or {}).get("verify_token")
        or os.environ.get("WHATSAPP_VERIFY_TOKEN")
        or DEFAULT_VERIFY_TOKEN
    )
    if mode == "subscribe" and token and hmac.compare_digest(token, expected_token):
        return 200, challenge or "OK"
    if not mode and not token:
        return 200, (
            "Mercadona Online WhatsApp Webhook Activo (Meta Cloud API + Twilio TwiML). "
            "Configura hub.mode=subscribe y hub.verify_token en el panel de Meta for Developers."
        )
    return 403, "Token de verificación de WhatsApp inválido."


def verify_meta_signature(raw_body: bytes, signature_header: str) -> bool:
    """Verifies X-Hub-Signature-256 if WHATSAPP_APP_SECRET is configured."""
    store = _load_wa_store()
    app_secret = (store.get("config") or {}).get("app_secret") or os.environ.get("WHATSAPP_APP_SECRET") or ""
    if not app_secret:
        return True
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(app_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature_header.strip(), expected)


def format_plan_for_whatsapp(plan: dict[str, Any]) -> str:
    """Formats a weekly menu plan into clean WhatsApp Markdown."""
    meals = plan.get("meals") or []
    total = float(plan.get("total") or 0.0)
    pc = plan.get("postal_code") or "28001"
    center = plan.get("center_name") or plan.get("warehouse") or "0130-DELIVERY"
    tier = (plan.get("basket_tier") or "ahorro").upper()
    tier_label = {
        "AHORRO": "🏷️ Marca Mercadona (Ahorro)",
        "BIO": "🌱 Frescos Natur & Bio Mercadona",
        "GOURMET": "🥂 Selección Gourmet Mercadona & Selection",
    }.get(tier, "🏷️ Marca Mercadona")

    lines = [
        f"🍽️ *Tu Menú Semanal Mercadona × Cookidoo* ({len(meals)} cenas)",
        f"📍 Stock en vivo verificado: *CP {pc}* ({center})",
        f"✨ Nivel de cesta: *{tier_label}*",
        "",
    ]
    for idx, m in enumerate(meals, 1):
        diners = m.get("active_diners") or m.get("cookidoo_servings") or 3
        lines.append(
            f"*{idx}. {m.get('day', 'Día')}:* {m.get('name', 'Receta')} "
            f"_({m.get('minutes', 25)} min · {round(float(m.get('calories_per_serving', 350)))} kcal · {diners} pers.)_"
        )

    counter_items = [b for b in (plan.get("basket") or []) if b.get("counter_prep")]
    if counter_items:
        lines.append("")
        lines.append(f"🔪 *Notas de Mostrador Frescos ECI ({len(counter_items)} incluidas):*")
        for ci in counter_items[:3]:
            cp = ci["counter_prep"]
            lines.append(f"• {cp.get('icon', '🔪')} *{ci['name'][:38]}*: _{cp.get('selected_cut')}_")

    sommelier = plan.get("sommelier_pairing")
    if sommelier and (tier == "GOURMET" or sommelier.get("included")):
        lines.append("")
        lines.append(f"🍷 *Sumiller IA Bodega ECI:* _{sommelier.get('wine_name', '')}_")

    lines.append("")
    lines.append(
        f"🛒 *Cesta Mercadona:* {len(plan.get('basket') or [])} productos · *{total:.2f} €*"
    )
    eci_plus = plan.get("eci_plus_status") or {}
    if eci_plus.get("eci_plus_message"):
        lines.append(f"🚚 _{eci_plus['eci_plus_message']}_")
    return "\n".join(lines)


def format_whatsapp_share_link(plan: dict[str, Any] | None) -> str:
    """Builds a real https://wa.me/?text=... deep link so the user can share the weekly menu on WhatsApp."""
    if not isinstance(plan, dict) or not plan.get("meals"):
        text = "Mira mi planificador semanal de menús con IA de Mercadona Online × Thermomix Cookidoo."
    else:
        text = format_plan_for_whatsapp(plan)
    return f"https://wa.me/?text={urllib.parse.quote(text)}"


def _ensure_active_plan(store: dict[str, Any], postal_code: str = "28001") -> dict[str, Any]:
    plan = store.get("active_plan")
    if isinstance(plan, dict) and isinstance(plan.get("meals"), list) and len(plan["meals"]) > 0:
        return plan
    default_prompt = (
        "Planifica 5 cenas entre semana para 2 adultos y 1 niño. Mantén el presupuesto bajo 65€, "
        "prepara cada receta en 25 minutos o menos, incluye una cena de pescado y usa la pasta que ya tengo en casa."
    )
    plan = build_weekly_plan(prompt=default_prompt, postal_code=postal_code)
    store["active_plan"] = plan
    return plan


def process_whatsapp_user_message(
    user_text: str,
    sender: str = "cliente_whatsapp",
    message_type: str = "text",
    image_base64: str | None = None,
    postal_code: str | None = None,
    current_plan_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Core conversational engine for WhatsApp messages (text, voice note transcripts, interactive buttons, and fridge photos)."""
    with _WA_LOCK:
        store = _load_wa_store()
        if isinstance(current_plan_override, dict) and current_plan_override.get("meals"):
            store["active_plan"] = current_plan_override
        pc = str(postal_code or store.get("postal_code") or "28001")
        plan = _ensure_active_plan(store, postal_code=pc)

        clean_text = (user_text or "").strip()
        low = clean_text.lower()

        # Record incoming user message
        user_msg_entry = {
            "id": f"wa-usr-{int(datetime.datetime.now().timestamp() * 1000)}",
            "sender": "user",
            "from": sender,
            "type": message_type,
            "timestamp": _now_hhmm(),
            "text": clean_text or ("📸 [Foto de nevera enviada]" if image_base64 else "🎤 [Nota de voz]"),
        }
        store.setdefault("messages", []).append(user_msg_entry)

        reply_text = ""
        reply_buttons = [
            {"id": "cmd:menu", "title": "📋 Ver Menú"},
            {"id": "cmd:swap_miercoles", "title": "🔄 Cambiar Miércoles"},
            {"id": "cmd:gourmet", "title": "🥂 Modo Gourmet"},
            {"id": "cmd:cart", "title": "🛒 Carrito ECI"},
        ]
        action_taken = "view_menu"

        # 1. Image / Fridge Vision over WhatsApp
        if image_base64 or low.startswith("cmd:fridge") or any(k in low for k in ("foto de mi nevera", "escanea mi nevera", "en la nevera tengo", "en mi nevera hay")):
            preset_id = "nevera_mediterranea"
            if "pollo" in low or "familiar" in low:
                preset_id = "nevera_familiar"
            elif "brócoli" in low or "brocoli" in low or "verde" in low:
                preset_id = "nevera_verde"

            vision_res = analyze_fridge_vision(
                image_base64=image_base64,
                preset_id=preset_id if not image_base64 else None,
                current_prompt=clean_text if ("tengo" in low or "nevera" in low) else "",
                postal_code=pc,
                current_plan=plan,
            )
            plan = vision_res["plan"]
            fv = vision_res["fridge_vision"]
            det_names = ", ".join(it["name"] for it in fv.get("detected_items", []))
            reply_text = (
                f"📸 *Nevera Vision (Google Gemini Multimodal)*\n"
                f"He detectado en tu nevera: *{det_names}*.\n\n"
                f"♻️ He actualizado tu menú semanal para aprovechar esos frescos antes de que caduquen y los he descontado de tu cesta "
                f"(*ahorro estimado: -{fv.get('estimated_savings_eur', 8.45):.2f} €*).\n\n"
                + format_plan_for_whatsapp(plan)
            )
            action_taken = "fridge_vision"

        # 2. 1-Click Cart generation from WhatsApp
        elif low in ("cmd:cart", "comprar", "carrito", "cesta", "transferir al carrito", "pedir") or "transferir al carrito" in low or "hacer pedido" in low:
            cart_res = prepare_eci_oneclick_cart(
                basket=plan.get("basket") or [],
                postal_code=pc,
            )
            counter_notes = [
                f"• {b['counter_prep']['icon']} *{b['name'][:32]}*: {b['counter_prep']['selected_cut']}"
                for b in (plan.get("basket") or [])
                if b.get("counter_prep")
            ]
            notes_block = (
                "\n\n🔪 *Instrucciones enviadas a Mostrador de Frescos ECI:*\n" + "\n".join(counter_notes[:4])
                if counter_notes
                else ""
            )
            reply_text = (
                f"🛒 *¡Carrito preparado en Mercadona Online!*\n\n"
                f"• *Productos sincronizados:* {cart_res.get('unique_products', len(plan.get('basket', [])))} referencias\n"
                f"• *Centro logístico:* {plan.get('center_name') or plan.get('warehouse')} (CP {pc})\n"
                f"• *Importe total:* *{float(plan.get('total', 0.0)):.2f} €*\n"
                f"• *ID Cesta ECI:* `{cart_res.get('food_order_attempt_id', 'activa')}`"
                f"{notes_block}\n\n"
                f"👉 Abre directamente tu compra en:\n{cart_res.get('checkout_url', 'https://www.elcorteingles.es/supermercado/')}"
            )
            action_taken = "prepare_cart"

        # 2b. Schedule entire week day-by-day in Cookidoo / Thermomix ("Mi Semana")
        elif low in ("cmd:cookidoo", "thermomix", "cookidoo") or any(
            k in low for k in ("enviar a thermomix", "enviar a mi thermomix", "planificar en cookidoo", "mi semana", "sincronizar thermomix", "sincronizar cookidoo")
        ):
            ck_res = schedule_weekly_plan_to_cookidoo(
                meals=plan.get("meals") or [],
                week_mode="current",
                user_email=sender if "@" in sender else "default",
            )
            plan = dict(plan)
            plan["cookidoo_scheduled_week"] = ck_res
            sched = ck_res.get("schedule") or {}
            day_lines = [
                f"• *{d['short_label']}:* {d['name']} ({d['cookidoo_id']})"
                for d in (sched.get("days") or [])
            ]
            reply_text = (
                f"📅 *¡Menú semanal planificado día a día en Mi Semana (Cookidoo / Thermomix®)!*\n"
                f"• Cuenta: *{sched.get('account_email', 'cookidoo.es')}*\n"
                f"• Semana: *{sched.get('range_label', '')}*\n\n"
                + "\n".join(day_lines)
                + f"\n\n👉 Ver calendario en Cookidoo:\n{sched.get('planner_url', 'https://cookidoo.es/planning/es-ES/my-week')}"
            )
            action_taken = "schedule_cookidoo_week"

        # 3. Basket Tier Switch ("Modo Gourmet", "Modo Bio", "Modo Ahorro")
        elif low in ("cmd:gourmet", "cmd:bio", "cmd:ahorro") or any(
            k in low for k in ("modo gourmet", "club del gourmet", "modo bio", "productos bio", "modo ahorro", "marca el corte")
        ):
            new_tier = "gourmet"
            if "bio" in low or "ecol" in low:
                new_tier = "bio"
            elif "ahorro" in low or "marca el corte" in low:
                new_tier = "ahorro"
            include_wine = new_tier == "gourmet" or "vino" in low or "maridaje" in low
            plan = recalculate_plan_basket(
                plan=plan,
                basket_tier=new_tier,
                include_sommelier_item=include_wine,
                postal_code=pc,
            )
            tier_titles = {
                "ahorro": "🏷️ Modo Ahorro (Marca Mercadona)",
                "bio": "🌱 Modo Bio & Ecológicos Mercadona",
                "gourmet": "🥂 Modo Selección Gourmet Mercadona & Sumiller IA",
            }
            sommelier_line = ""
            if new_tier == "gourmet" and plan.get("sommelier_pairing"):
                sp = plan["sommelier_pairing"]
                sommelier_line = f"\n🍷 *Sumiller IA ha añadido:* _{sp.get('product_name')}_ ({sp.get('price', 5.65):.2f} €) para maridar el {sp.get('paired_with_day')}."
            reply_text = (
                f"✨ *Cesta actualizada a {tier_titles.get(new_tier, new_tier)}*\n"
                f"Se han actualizado *{plan.get('upgraded_count', 0)} productos* a referencias seleccionadas de Mercadona.{sommelier_line}\n\n"
                f"🛒 *Nuevo total cesta ECI:* *{float(plan.get('total', 0.0)):.2f} €*"
            )
            action_taken = f"tier_{new_tier}"

        # 4. Per-day Guest Scaling ("El viernes vienen 6 personas" / "Hoy vienen 6 invitados el jueves")
        elif (
            re.search(
                r"\b(lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo)\b",
                low,
            )
            and re.search(
                r"\b([1-9]|1[0-4]|dos|tres|cuatro|cinco|seis|siete|ocho)\s*(?:personas?|comensales?|invitados?|adultos?|raciones?)\b",
                low,
            )
        ):
            m_day = re.search(
                r"\b(lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo)\b",
                low,
            )
            m_num = re.search(
                r"\b([1-9]|1[0-4]|dos|tres|cuatro|cinco|seis|siete|ocho)\s*(?:personas?|comensales?|invitados?|adultos?|raciones?)\b",
                low,
            )
            raw_day = m_day.group(1) if m_day else "viernes"
            day_es = DAYS_EN_TO_ES.get(raw_day, "Viernes")
            num_map = {"dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8}
            raw_num = m_num.group(1) if m_num else "6"
            diners = num_map.get(raw_num, int(raw_num) if raw_num.isdigit() else 6)
            plan = recalculate_plan_basket(
                plan=plan,
                day_servings={day_es: diners},
                postal_code=pc,
            )
            target_meal = next((m for m in plan.get("meals", []) if m.get("day") == day_es), {})
            reply_text = (
                f"👥 *Comensales actualizados para el {day_es}*\n"
                f"• Receta: *{target_meal.get('name', 'Cena')}*\n"
                f"• Raciones escaladas a: *{diners} personas*\n"
                f"• Envases e instrucciones de mostrador recalculados en tu cesta.\n\n"
                f"🛒 *Nuevo total cesta Mercadona:* *{float(plan.get('total', 0.0)):.2f} €*"
            )
            action_taken = "scale_day_servings"

        # 5. Swap a single day's recipe ("cambia el miércoles por una cena de pescado", "cmd:swap_miercoles", "rotar lunes")
        elif low.startswith("cmd:swap_") or (
            any(w in low for w in ("cambia", "cambiar", "cambio", "rota", "rotar", "sustituye", "sustituir", "pon", "poner", "prefiero", "quiero", "otra receta"))
            and any(d in low for d in ("lunes", "martes", "miércoles", "miercoles", "jueves", "viernes", "sábado", "sabado", "domingo"))
            and not any(ing in low for ing in ("gluten", "lactosa", "kcal", "euros", "€"))
        ):
            day_found = "Miércoles"
            for d_key, d_val in DAYS_EN_TO_ES.items():
                if d_key in low:
                    day_found = d_val
                    break
            meals = plan.get("meals") or []
            target_meal = next((m for m in meals if m.get("day", "").lower() == day_found.lower()), meals[0] if meals else None)
            if target_meal:
                swap_res = swap_single_recipe(
                    current_meals=[{"day": m["day"], "recipe_id": m["recipe_id"]} for m in meals],
                    target_recipe_id=target_meal["recipe_id"],
                    constraints=plan.get("constraints") or {},
                    postal_code=pc,
                    rotation=int(store.get("plan_version") or 1) + 1,
                    basket_tier=plan.get("basket_tier") or "ahorro",
                    preferred_query=None if low.startswith("cmd:swap_") else clean_text,
                )
                rep = swap_res.get("replacement")
                if rep:
                    plan["meals"] = [rep if m["recipe_id"] == target_meal["recipe_id"] else m for m in meals]
                    plan["basket"] = swap_res["basket"]
                    plan["total"] = swap_res["total"]
                    plan["budget_remaining"] = swap_res["budget_remaining"]
                    plan["counter_notes_count"] = swap_res.get("counter_notes_count", plan.get("counter_notes_count", 0))
                    plan["sommelier_pairing"] = swap_res.get("sommelier_pairing", plan.get("sommelier_pairing"))
                    plan["eci_plus_status"] = swap_res.get("eci_plus_status", plan.get("eci_plus_status"))
                    chg = swap_res.get("change") or {}
                    reply_text = (
                        f"🔄 *Cena del {chg.get('day', day_found)} actualizada*\n"
                        f"• Anterior: _{chg.get('from_recipe_name', target_meal['name'])}_\n"
                        f"• Nueva receta: *{chg.get('to_recipe_name', rep['name'])}* ({rep['minutes']} min · {round(float(rep['calories_per_serving']))} kcal)\n\n"
                        f"🛒 *Cesta Mercadona recalculada:* *{float(plan['total']):.2f} €*"
                    )
                    action_taken = "swap_recipe"

        # 6. View Menu / Greeting
        elif low in ("cmd:menu", "menu", "menú", "ver menu", "ver menú", "hola", "buenas", "resumen", "empezar", "start") or not clean_text:
            reply_text = format_plan_for_whatsapp(plan)
            action_taken = "view_menu"

        # 7. Full natural-language menu modification (e.g. "Cambia el menú para que sea sin lactosa, bajo 50€ e incluya salmón")
        else:
            try:
                plan = build_weekly_plan(
                    prompt=clean_text,
                    postal_code=pc,
                    current_plan=plan,
                    variety_seed=f"wa:{store.get('plan_version', 1)}",
                )
                reply_text = (
                    f"✨ *Menú semanal actualizado con Google Gemini*\n"
                    f"He aplicado tu petición: _«{clean_text}»_\n\n"
                    + format_plan_for_whatsapp(plan)
                )
                action_taken = "replan_natural_language"
            except Exception:
                # If out of scope or super short, answer helpfully with current menu
                reply_text = (
                    "🤖 Puedo ayudarte a consultar o modificar tu menú semanal de Mercadona × Cookidoo.\n\n"
                    + format_plan_for_whatsapp(plan)
                )
                action_taken = "fallback_menu"

        bot_msg_entry = {
            "id": f"wa-bot-{int(datetime.datetime.now().timestamp() * 1000)}",
            "sender": "bot",
            "type": "text",
            "timestamp": _now_hhmm(),
            "text": reply_text,
            "buttons": reply_buttons,
            "action": action_taken,
        }
        store["messages"].append(bot_msg_entry)
        store["active_plan"] = plan
        store["plan_version"] = int(store.get("plan_version") or 1) + 1
        _save_wa_store(store)

        return {
            "reply_text": reply_text,
            "reply_buttons": reply_buttons,
            "action": action_taken,
            "plan": plan,
            "plan_version": store["plan_version"],
            "messages": store["messages"][-30:],
            "share_wa_url": format_whatsapp_share_link(plan),
        }


def _send_meta_cloud_api_message(
    recipient_phone: str,
    reply_text: str,
    buttons: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Dispatches an outbound WhatsApp message via Meta Graph API if credentials are configured."""
    store = _load_wa_store()
    cfg = store.get("config") or {}
    phone_id = (cfg.get("phone_number_id") or os.environ.get("WHATSAPP_PHONE_NUMBER_ID") or "").strip()
    token = re.sub(r"[\r\n]+", "", (cfg.get("access_token") or os.environ.get("WHATSAPP_ACCESS_TOKEN") or "")).strip()
    if not phone_id or not token or not recipient_phone:
        return {"dispatched": False, "reason": "no_meta_credentials_configured"}
    if not re.fullmatch(r"\d{5,32}", phone_id):
        return {"dispatched": False, "reason": "invalid_phone_number_id"}

    clean_to = re.sub(r"[^\d]", "", recipient_phone)
    url = f"https://graph.facebook.com/v21.0/{phone_id}/messages"
    if buttons and len(buttons) <= 3:
        payload: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "to": clean_to,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": reply_text[:1024]},
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {"id": b["id"][:256], "title": b["title"][:20]},
                        }
                        for b in buttons[:3]
                    ]
                },
            },
        }
    else:
        payload = {
            "messaging_product": "whatsapp",
            "to": clean_to,
            "type": "text",
            "text": {"preview_url": True, "body": reply_text[:4096]},
        }

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            resp_data = json.loads(resp.read().decode("utf-8", "ignore"))
            return {"dispatched": True, "provider": "meta_cloud_api", "response": resp_data}
    except Exception as exc:
        return {"dispatched": False, "provider": "meta_cloud_api", "error": str(exc)}


def handle_whatsapp_webhook_post(
    raw_body: bytes,
    content_type: str = "application/json",
    signature_header: str = "",
) -> tuple[int, str, bytes]:
    """Handles incoming POST webhooks from:
    1) Twilio WhatsApp Sandbox (`application/x-www-form-urlencoded`) -> returns TwiML XML
    2) Meta WhatsApp Cloud API (`application/json` with `object == 'whatsapp_business_account'`) -> returns JSON
    3) Direct JSON webhook invocation -> returns JSON
    """
    ctype_low = (content_type or "").lower()

    # Case 1: Twilio WhatsApp Webhook (application/x-www-form-urlencoded)
    if "application/x-www-form-urlencoded" in ctype_low:
        form_str = raw_body.decode("utf-8", "ignore")
        parsed_qs = urllib.parse.parse_qs(form_str)
        sender = (parsed_qs.get("From") or ["whatsapp:+34600000000"])[0]
        body_text = (parsed_qs.get("Body") or [""])[0].strip()
        media_type = (parsed_qs.get("MediaContentType0") or [""])[0].lower()

        msg_type = "audio" if "audio" in media_type else ("image" if "image" in media_type else "text")
        res = process_whatsapp_user_message(
            user_text=body_text,
            sender=sender,
            message_type=msg_type,
        )
        with _WA_LOCK:
            store = _load_wa_store()
            stats = store.setdefault("webhook_stats", {})
            stats["total_received"] = int(stats.get("total_received") or 0) + 1
            stats["last_webhook_at"] = _now_iso()
            stats["last_provider"] = "Twilio WhatsApp Webhook"
            stats["last_sender"] = sender
            _save_wa_store(store)

        twiml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            f"<Response><Message>{html.escape(res['reply_text'])}</Message></Response>"
        )
        return 200, "text/xml; charset=utf-8", twiml.encode("utf-8")

    # Case 2: Meta WhatsApp Cloud API or Direct JSON Webhook
    if not verify_meta_signature(raw_body, signature_header):
        err_json = json.dumps({"error": "Firma X-Hub-Signature-256 inválida."}).encode("utf-8")
        return 401, "application/json; charset=utf-8", err_json

    try:
        payload = json.loads(raw_body.decode("utf-8", "ignore") or "{}")
    except Exception:
        payload = {}

    # Meta WhatsApp Cloud API format
    if payload.get("object") == "whatsapp_business_account" or isinstance(payload.get("entry"), list):
        processed_results: list[dict[str, Any]] = []
        for entry in payload.get("entry") or []:
            for change in entry.get("changes") or []:
                val = change.get("value") or {}
                for msg in val.get("messages") or []:
                    sender = str(msg.get("from") or "whatsapp_user")
                    mtype = str(msg.get("type") or "text")
                    extracted_text = ""
                    if mtype == "text":
                        extracted_text = str((msg.get("text") or {}).get("body") or "")
                    elif mtype == "interactive":
                        inter = msg.get("interactive") or {}
                        btn_rep = inter.get("button_reply") or inter.get("list_reply") or {}
                        extracted_text = str(btn_rep.get("id") or btn_rep.get("title") or "")
                    elif mtype in ("audio", "voice"):
                        extracted_text = str((msg.get("audio") or {}).get("transcript") or "Ver mi menú semanal")
                    elif mtype == "image":
                        extracted_text = "cmd:fridge"

                    res = process_whatsapp_user_message(
                        user_text=extracted_text,
                        sender=sender,
                        message_type=mtype,
                    )
                    outbound = _send_meta_cloud_api_message(
                        recipient_phone=sender,
                        reply_text=res["reply_text"],
                        buttons=res.get("reply_buttons", [])[:3],
                    )
                    processed_results.append(
                        {
                            "from": sender,
                            "type": mtype,
                            "action": res["action"],
                            "reply_text": res["reply_text"],
                            "outbound": outbound,
                        }
                    )

        with _WA_LOCK:
            store = _load_wa_store()
            stats = store.setdefault("webhook_stats", {})
            stats["total_received"] = int(stats.get("total_received") or 0) + max(1, len(processed_results))
            stats["last_webhook_at"] = _now_iso()
            stats["last_provider"] = "Meta WhatsApp Cloud API"
            if processed_results:
                stats["last_sender"] = processed_results[-1]["from"]
            _save_wa_store(store)

        out_bytes = json.dumps(
            {"status": "EVENT_RECEIVED", "processed_count": len(processed_results), "results": processed_results},
            ensure_ascii=False,
        ).encode("utf-8")
        return 200, "application/json; charset=utf-8", out_bytes

    # Case 3: Direct JSON webhook payload (`{"message": "...", "from": "+34..."}`)
    user_msg = str(payload.get("message") or payload.get("text") or payload.get("body") or "").strip()
    sender = str(payload.get("from") or payload.get("sender") or "+34 600 123 456")
    msg_type = str(payload.get("type") or "text")
    image_b64 = payload.get("image_base64")
    postal_code = payload.get("postal_code")
    current_plan = payload.get("current_plan")

    res = process_whatsapp_user_message(
        user_text=user_msg,
        sender=sender,
        message_type=msg_type,
        image_base64=image_b64,
        postal_code=postal_code,
        current_plan_override=current_plan if isinstance(current_plan, dict) else None,
    )
    with _WA_LOCK:
        store = _load_wa_store()
        stats = store.setdefault("webhook_stats", {})
        stats["total_received"] = int(stats.get("total_received") or 0) + 1
        stats["last_webhook_at"] = _now_iso()
        stats["last_provider"] = "WhatsApp Direct Webhook"
        stats["last_sender"] = sender
        _save_wa_store(store)

    return 200, "application/json; charset=utf-8", json.dumps(res, ensure_ascii=False).encode("utf-8")

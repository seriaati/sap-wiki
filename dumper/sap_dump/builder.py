import re

from .constants import TRIG_CLASS_TO_LOCO
from .linkbacks import apply_linkbacks


def camel_to_words(s: str) -> str:
    return re.sub(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", s)


_TRIGGER_LIMIT_TYPE = {0: "per turn", 1: "per battle", 2: "outside battle"}


def collapse_triggers(triggers_raw: list) -> dict:
    """
    Collapse raw trigger list (3 entries per ability, one per level) into
    one entry per unique ability name.
    Returns {ability_name: {trig_cls, enum_int, triggerLimit?, triggerLimitType?, triggerLevel?, finePrintKey?, customNote?}}.
    """
    seen = {}
    for entry in triggers_raw:
        name = entry.get("name")
        if not name:
            name = f"unknown_{entry.get('self', '')[-6:]}"
        if name in seen:
            continue
        info = {"trig_cls": entry.get("trig_cls") or "?"}
        for field in ("enum_int", "triggerLimit", "triggerLimitType", "triggerLevel", "finePrintKey", "customNote"):
            if field in entry:
                info[field] = entry[field]
        seen[name] = info
    return seen


def make_fine_print(trigger_info: dict, ab_loco: dict, lvl: str) -> str:
    """Build fine print text for one ability level."""
    # Explicit loco key from SetFinePrint hook
    fp_key = trigger_info.get("finePrintKey")
    if fp_key and fp_key in ab_loco:
        return ab_loco[fp_key]

    # From localization table (e.g. Ability.XAbility.1.FinePrint)
    loco_fp = ab_loco.get(f"{lvl}.FinePrint", "")
    if loco_fp:
        return loco_fp

    # Synthesize from trigger limit — only once we know the correct field
    limit = trigger_info.get("triggerLimit")
    if limit is not None and limit > 1:
        limit_type = _TRIGGER_LIMIT_TYPE.get(trigger_info.get("triggerLimitType", 0), "per turn")
        return f"Works {limit} times {limit_type}."

    return ""


def resolve_trigger_display(trig_cls: str, triggers_loco: dict) -> str:
    loco_key = TRIG_CLASS_TO_LOCO.get(trig_cls)
    if loco_key and loco_key in triggers_loco:
        return triggers_loco[loco_key].get("", loco_key)
    if trig_cls and trig_cls != "RectTransform":
        return trig_cls[7:] if trig_cls.startswith("Trigger") else trig_cls
    return ""


def _build_minion_entry(
    minion_name: str,
    stats: dict,
    abilities_db: dict,
    triggers_loco: dict,
    pet_names: dict,
    ability_trigger_map: dict,
    images: dict | None,
    display_name: str | None = None,
) -> dict:
    if display_name is None:
        display_name = pet_names.get(minion_name, camel_to_words(minion_name))
    ability_name = f"{minion_name}Ability"
    ab_loco = abilities_db.get(ability_name, {})

    trig_info = ability_trigger_map.get(ability_name, {})
    trig_cls = trig_info.get("trig_cls", "") if isinstance(trig_info, dict) else trig_info
    trigger_display = resolve_trigger_display(trig_cls, triggers_loco) if trig_cls else ""

    # Fall back to hardcoded custom note when no localization entry exists
    custom_note = trig_info.get("customNote", "") if isinstance(trig_info, dict) else ""
    def _ability_text(loco_key: str) -> str:
        text = ab_loco.get(loco_key, "")
        if not text and custom_note:
            return apply_linkbacks(custom_note)
        return apply_linkbacks(text)

    entry = {
        "name": display_name,
        "tier": stats.get("tier", 0),
        "cost": stats.get("price", 3),
        "attack": stats.get("attack", 0),
        "health": stats.get("health", 0),
        "active": stats.get("active", False),
        "rollable": stats.get("rollable", False),
        "trigger": trigger_display,
        "ability1": _ability_text("1.About"),
        "ability2": _ability_text("2.About"),
        "ability3": _ability_text("3.About"),
        "image": images.get(minion_name, "") if images else "",
        "types": stats.get("types", []),
    }
    for lvl in ("1", "2", "3"):
        fp = make_fine_print(trig_info if isinstance(trig_info, dict) else {}, ab_loco, lvl)
        if fp:
            entry[f"finePrint{lvl}"] = fp
    return entry


def build_final(
    unitypy_data: dict,
    frida_data: dict,
    pet_images: dict | None = None,
    food_images: dict | None = None,
    toy_images: dict | None = None,
) -> dict:
    abilities_db = unitypy_data["abilities"]
    triggers_loco = unitypy_data["triggers"]
    pet_names = unitypy_data["pet_names"]
    spell_descs = unitypy_data.get("spell_descs", {})

    pets_raw = frida_data["pets_raw"]
    foods_raw = frida_data["foods_raw"]
    triggers_raw = frida_data["triggers_raw"]

    ability_trigger_map = collapse_triggers(triggers_raw)

    # ── Split pets_raw: toys have Relic* prefix ───────────────────────────────
    real_pets_raw = {k: v for k, v in pets_raw.items() if not k.startswith("Relic")}
    toys_raw = {k: v for k, v in pets_raw.items() if k.startswith("Relic")}

    # ── Build pets dict ───────────────────────────────────────────────────────
    pets = {}
    for minion_name, stats in real_pets_raw.items():
        if not stats.get("active", False):
            continue
        pets[minion_name] = _build_minion_entry(
            minion_name, stats, abilities_db, triggers_loco, pet_names, ability_trigger_map, pet_images
        )

    pets = dict(sorted(pets.items(), key=lambda kv: (kv[1]["tier"], kv[0])))

    # Debug: log enum_int for pets with missing ability text
    missing = [
        (name, ability_trigger_map.get(f"{name}Ability", {}).get("enum_int", -1))
        for name, p in pets.items()
        if p.get("trigger") and not p.get("ability1")
    ]
    if missing:
        import sys
        print(f"[DEBUG] {len(missing)} active pets with trigger but no ability text:", file=sys.stderr)
        for name, ei in sorted(missing, key=lambda x: x[1]):
            print(f"  enum_int={ei:4d}  {name}", file=sys.stderr)

    # ── Build toys dict ───────────────────────────────────────────────────────
    toys = {}
    for relic_name, stats in toys_raw.items():
        if not stats.get("active", False):
            continue
        stripped = relic_name[len("Relic"):]
        display_name = pet_names.get(relic_name, camel_to_words(stripped))
        toys[relic_name] = _build_minion_entry(
            relic_name, stats, abilities_db, triggers_loco, pet_names, ability_trigger_map,
            toy_images, display_name=display_name,
        )

    toys = dict(sorted(toys.items(), key=lambda kv: (kv[1]["tier"], kv[0])))

    # ── Build foods dict ──────────────────────────────────────────────────────
    foods = {}
    for spell_name, stats in foods_raw.items():
        if not stats.get("active", False):
            continue

        display_name = camel_to_words(spell_name)
        food_ability_name = f"{spell_name}Ability"
        ab_loco = abilities_db.get(food_ability_name, {})
        spell_loco = spell_descs.get(spell_name, {})

        ability_text = ab_loco.get("1.About", "") or spell_loco.get("About", "")

        foods[spell_name] = {
            "name": display_name,
            "tier": stats.get("tier", 0),
            "cost": stats.get("price", 3),
            "active": stats.get("active", False),
            "rollable": stats.get("rollable", False),
            "ability": ability_text,
            "image": food_images.get(spell_name, "") if food_images else "",
        }

    foods = dict(sorted(foods.items(), key=lambda kv: (kv[1]["tier"], kv[0])))

    return {"pets": pets, "foods": foods, "toys": toys}

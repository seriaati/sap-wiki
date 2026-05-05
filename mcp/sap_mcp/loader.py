import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .cleaning import clean
from .models import Food, Pet, SearchDoc, Toy

_DATA_DIR = Path(os.getenv("SAP_DATA_DIR", Path(__file__).parent.parent.parent / "dumper" / "output"))

LOADED_AT = datetime.now(timezone.utc).isoformat()


def _clean_pet(key: str, raw: dict) -> Pet:
    return {
        "key": key,
        "slug": key.lower(),
        "name": clean(raw.get("name", "")),
        "tier": raw.get("tier", 0),
        "cost": raw.get("cost", 0),
        "attack": raw.get("attack", 0),
        "health": raw.get("health", 0),
        "active": raw.get("active", False),
        "rollable": raw.get("rollable", False),
        "trigger": clean(raw.get("trigger", "")),
        "ability1": clean(raw.get("ability1", "")),
        "ability2": clean(raw.get("ability2", "")),
        "ability3": clean(raw.get("ability3", "")),
        "image": raw.get("image", ""),
        "types": raw.get("types", []),
    }


def _clean_food(key: str, raw: dict) -> Food:
    return {
        "key": key,
        "slug": key.lower(),
        "name": clean(raw.get("name", "")),
        "tier": raw.get("tier", 0),
        "cost": raw.get("cost", 0),
        "active": raw.get("active", False),
        "rollable": raw.get("rollable", False),
        "ability": clean(raw.get("ability", "")),
        "image": raw.get("image", ""),
    }


def _clean_toy(key: str, raw: dict) -> Toy:
    return {
        "key": key,
        "slug": key.lower(),
        "name": clean(raw.get("name", "")),
        "tier": raw.get("tier", 0),
        "cost": raw.get("cost", 0),
        "attack": raw.get("attack", 0),
        "health": raw.get("health", 0),
        "active": raw.get("active", False),
        "rollable": raw.get("rollable", False),
        "trigger": clean(raw.get("trigger", "")),
        "ability1": clean(raw.get("ability1", "")),
        "ability2": clean(raw.get("ability2", "")),
        "ability3": clean(raw.get("ability3", "")),
        "image": raw.get("image", ""),
    }


def _load() -> tuple[list[Pet], list[Food], list[Toy], list[SearchDoc]]:
    with open(_DATA_DIR / "pets.json") as f:
        pets_raw: dict = json.load(f)
    with open(_DATA_DIR / "foods.json") as f:
        foods_raw: dict = json.load(f)
    with open(_DATA_DIR / "toys.json") as f:
        toys_raw: dict = json.load(f)

    pets = [_clean_pet(k, v) for k, v in pets_raw.items()]
    foods = [_clean_food(k, v) for k, v in foods_raw.items()]
    toys = [_clean_toy(k, v) for k, v in toys_raw.items()]

    search_docs: list[SearchDoc] = []
    for p in pets:
        text = " ".join(filter(None, [p["name"], p["trigger"], p["ability1"], p["ability2"], p["ability3"]])).lower()
        search_docs.append({"kind": "pet", "slug": p["slug"], "name": p["name"], "text": text})
    for f in foods:
        text = " ".join(filter(None, [f["name"], f["ability"]])).lower()
        search_docs.append({"kind": "food", "slug": f["slug"], "name": f["name"], "text": text})
    for t in toys:
        text = " ".join(filter(None, [t["name"], t["trigger"], t["ability1"], t["ability2"], t["ability3"]])).lower()
        search_docs.append({"kind": "toy", "slug": t["slug"], "name": t["name"], "text": text})

    return pets, foods, toys, search_docs


PETS, FOODS, TOYS, SEARCH_DOCS = _load()

PETS_BY_SLUG: dict[str, Pet] = {p["slug"]: p for p in PETS}
FOODS_BY_SLUG: dict[str, Food] = {f["slug"]: f for f in FOODS}
TOYS_BY_SLUG: dict[str, Toy] = {t["slug"]: t for t in TOYS}

PETS_BY_NAME: dict[str, Pet] = {p["name"].lower(): p for p in PETS}
FOODS_BY_NAME: dict[str, Food] = {f["name"].lower(): f for f in FOODS}
TOYS_BY_NAME: dict[str, Toy] = {t["name"].lower(): t for t in TOYS}

DATA_DIR = str(_DATA_DIR)

import os

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from . import loader
from .models import Food, FoodSummary, Pet, PetSummary, SearchResult, Toy, ToySummary
from .search import search as _search

_host = os.getenv("HOST", "0.0.0.0")
_transport_security = (
    None  # use FastMCP default (localhost-only protection) for local dev
    if _host in ("127.0.0.1", "localhost", "::1")
    else TransportSecuritySettings(enable_dns_rebinding_protection=False)
)

mcp = FastMCP(
    "sap-wiki",
    instructions=(
        "Read-only Super Auto Pets game data. "
        "Contains pets, foods, and toys with cleaned ability text. "
        "Use list_* tools to browse with filters, get_* tools for full detail, search for cross-entity keyword lookup."
    ),
    stateless_http=True,
    json_response=True,
    host=_host,
    transport_security=_transport_security,
)


# --- Pets ---

@mcp.tool()
def list_pets(
    tier: int | None = None,
    trigger: str | None = None,
    name_contains: str | None = None,
    rollable: bool | None = None,
) -> list[PetSummary]:
    """List pets with optional filters. Returns summary fields only."""
    results = loader.PETS
    if tier is not None:
        results = [p for p in results if p["tier"] == tier]
    if trigger is not None:
        results = [p for p in results if trigger.lower() in p["trigger"].lower()]
    if name_contains is not None:
        results = [p for p in results if name_contains.lower() in p["name"].lower()]
    if rollable is not None:
        results = [p for p in results if p["rollable"] == rollable]
    return [
        {"slug": p["slug"], "name": p["name"], "tier": p["tier"],
         "attack": p["attack"], "health": p["health"], "trigger": p["trigger"],
         "rollable": p["rollable"], "types": p["types"]}
        for p in results
    ]


@mcp.tool()
def get_pet(slug_or_name: str) -> Pet | dict:
    """Get full details for a pet by slug (e.g. 'ant') or display name (e.g. 'Ant')."""
    key = slug_or_name.lower()
    pet = loader.PETS_BY_SLUG.get(key) or loader.PETS_BY_NAME.get(key)
    if pet is None:
        return {"error": "not_found", "slug_or_name": slug_or_name}
    return pet


# --- Foods ---

@mcp.tool()
def list_foods(
    tier: int | None = None,
    name_contains: str | None = None,
    rollable: bool | None = None,
) -> list[FoodSummary]:
    """List foods with optional filters. Returns summary fields only."""
    results = loader.FOODS
    if tier is not None:
        results = [f for f in results if f["tier"] == tier]
    if name_contains is not None:
        results = [f for f in results if name_contains.lower() in f["name"].lower()]
    if rollable is not None:
        results = [f for f in results if f["rollable"] == rollable]
    return [
        {"slug": f["slug"], "name": f["name"], "tier": f["tier"], "rollable": f["rollable"]}
        for f in results
    ]


@mcp.tool()
def get_food(slug_or_name: str) -> Food | dict:
    """Get full details for a food by slug (e.g. 'apple') or display name (e.g. 'Apple')."""
    key = slug_or_name.lower()
    food = loader.FOODS_BY_SLUG.get(key) or loader.FOODS_BY_NAME.get(key)
    if food is None:
        return {"error": "not_found", "slug_or_name": slug_or_name}
    return food


# --- Toys ---

@mcp.tool()
def list_toys(
    tier: int | None = None,
    trigger: str | None = None,
    name_contains: str | None = None,
    rollable: bool | None = None,
) -> list[ToySummary]:
    """List toys with optional filters. Returns summary fields only."""
    results = loader.TOYS
    if tier is not None:
        results = [t for t in results if t["tier"] == tier]
    if trigger is not None:
        results = [t for t in results if trigger.lower() in t["trigger"].lower()]
    if name_contains is not None:
        results = [t for t in results if name_contains.lower() in t["name"].lower()]
    if rollable is not None:
        results = [t for t in results if t["rollable"] == rollable]
    return [
        {"slug": t["slug"], "name": t["name"], "tier": t["tier"],
         "trigger": t["trigger"], "rollable": t["rollable"]}
        for t in results
    ]


@mcp.tool()
def get_toy(slug_or_name: str) -> Toy | dict:
    """Get full details for a toy by slug (e.g. 'relicactionfigure') or display name (e.g. 'Action Figure')."""
    key = slug_or_name.lower()
    toy = loader.TOYS_BY_SLUG.get(key) or loader.TOYS_BY_NAME.get(key)
    if toy is None:
        return {"error": "not_found", "slug_or_name": slug_or_name}
    return toy


# --- Cross-entity search ---

@mcp.tool()
def search(
    query: str,
    kinds: list[str] | None = None,
    limit: int = 20,
) -> list[SearchResult]:
    """
    Full-text search across pets, foods, and toys.

    kinds: optional filter list, e.g. ["pet", "food"] or ["toy"]. Omit to search all.
    limit: max results (default 20, max 100).
    Results are ranked: name matches first, then ability/trigger matches.
    """
    return _search(loader.SEARCH_DOCS, query, kinds=kinds, limit=min(limit, 100))


# --- Metadata ---

@mcp.tool()
def get_stats() -> dict:
    """Return entity counts and server metadata."""
    return {
        "counts": {
            "pets": len(loader.PETS),
            "foods": len(loader.FOODS),
            "toys": len(loader.TOYS),
        },
        "data_dir": loader.DATA_DIR,
        "loaded_at": loader.LOADED_AT,
    }

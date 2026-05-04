"""
Post-process ability text strings to add [[display|slug]] link tokens.

Rendered by AbilityText.astro in the wiki as anchor links.
Syntax:
  [[DisplayText]]          -> /pets/{displaytext.lower().replace(' ','')}
  [[DisplayText|slug]]     -> /pets/{slug}
  [[DisplayText|food:key]] -> /foods/{key}

Rules are compiled into a single combined regex so each position in the text
is matched exactly once — longer/earlier rules win, preventing a shorter rule
from matching inside an already-substituted token.
"""

import re

# (regex_pattern, replacement_string)
# Order matters: longer/more-specific patterns MUST come before shorter ones.
_RULES: list[tuple[str, str]] = [
    # ── Pet tokens ────────────────────────────────────────────────────────────
    (r"\bLoyal Chinchillas\b",    "[[Loyal Chinchillas|chinchilla]]"),
    (r"\bLoyal Chinchilla\b",     "[[Loyal Chinchilla|chinchilla]]"),
    (r"\bDirty Rats\b",           "[[Dirty Rats|rattoken]]"),
    (r"\bDirty Rat\b",            "[[Dirty Rat|rattoken]]"),
    (r"\bOrchid Mantises\b",      "[[Orchid Mantises|orchidmantis]]"),
    (r"\bOrchid Mantis\b",        "[[Orchid Mantis|orchidmantis]]"),
    (r"\bZombie Flies\b",         "[[Zombie Flies|flytoken]]"),
    (r"\bZombie Fly\b",           "[[Zombie Fly|flytoken]]"),
    (r"\bZombie Crickets\b",      "[[Zombie Crickets|crickettoken]]"),
    (r"\bZombie Cricket\b",       "[[Zombie Cricket|crickettoken]]"),
    # Short names in ability text that differ from display names
    (r"(?<=\d/\d )Crickets\b",    "[[Crickets|crickettoken]]"),
    (r"(?<=\d/\d )Cricket\b",     "[[Cricket|crickettoken]]"),
    (r"(?<=\d/\d )fly\b",         "[[fly|flytoken]]"),
    # Mantis short name (Orchid Mantis ability says just "Mantis")
    (r"\bMantises\b",             "[[Mantises|orchidmantis]]"),
    (r"\bMantis\b",               "[[Mantis|orchidmantis]]"),
    # Single-word pet tokens
    (r"\bDolphins\b",             "[[Dolphins|dolphin]]"),
    (r"\bDolphin\b",              "[[Dolphin]]"),
    (r"\bChicks\b",               "[[Chicks|chick]]"),
    (r"\bChick\b",                "[[Chick]]"),
    (r"\bRams\b",                 "[[Rams|ram]]"),
    (r"\bRam\b",                  "[[Ram]]"),
    (r"\bMole\b",                 "[[Mole]]"),
    (r"\bBus\b",                  "[[Bus]]"),

    # ── Food items (multi-word names first) ───────────────────────────────────
    (r"\bPeanut Butters?\b",      "[[Peanut Butter|food:peanutbutter]]"),
    (r"\bMild Chili\b",           "[[Mild Chili|food:mildchili]]"),
    (r"\bBread Crumbs\b",         "[[Bread Crumbs|food:breadcrumbs]]"),
    (r"\bChicken Legs?\b",        "[[Chicken Leg|food:chickenleg]]"),
    (r"\bMelon Slice\b",          "[[Melon Slice|food:melon]]"),
    (r"\bSleeping Pill\b",        "[[Sleeping Pill|food:pill]]"),
    (r"\bHoly Water\b",           "[[Holy Water|food:holywater]]"),
    (r"\bSeed Pile\b",            "[[Seed Pile|food:seedpile]]"),
    (r"\bMeat Bone\b",            "[[Meat Bone|food:meatbone]]"),
    (r"\bWhite Okra\b",           "[[White Okra|food:whiteokra]]"),
    # "Corncob" is used in ability text for the Corn food
    (r"\bCorncobs\b",             "[[Corncobs|food:corn]]"),
    (r"\bCorncob\b",              "[[Corncob|food:corn]]"),
    # Single-word food names (after multi-word rules that share a root word)
    (r"\bStrawberries\b",         "[[Strawberries|food:strawberry]]"),
    (r"\bStrawberry\b",           "[[Strawberry|food:strawberry]]"),
    (r"\bstrawberries\b",         "[[strawberries|food:strawberry]]"),
    (r"\bstrawberry\b",           "[[strawberry|food:strawberry]]"),
    (r"\bEucalyptus\b",           "[[Eucalyptus|food:eucalyptus]]"),
    (r"\bRambutan\b",             "[[Rambutan|food:rambutan]]"),
    (r"\bChocolate\b",            "[[Chocolate|food:chocolate]]"),
    (r"\bPopcorn\b",              "[[Popcorn|food:popcorn]]"),
    (r"\bCoconuts?\b",            "[[Coconut|food:coconut]]"),
    (r"\bWalnuts?\b",             "[[Walnut|food:walnut]]"),
    (r"\bGarlic\b",               "[[Garlic|food:garlic]]"),
    (r"\bPeanuts?\b",             "[[Peanut|food:peanut]]"),
    (r"\bSkewer\b",               "[[Skewer|food:skewer]]"),
    (r"\bHoney\b",                "[[Honey|food:honey]]"),
    (r"\bGuava\b",                "[[Guava|food:guava]]"),
    (r"\bMelons?\b",              "[[Melon|food:melon]]"),
    (r"\bBacon\b",                "[[Bacon|food:bacon]]"),
    (r"\bChili\b",                "[[Chili|food:chili]]"),
    (r"\bApples?\b",              "[[Apple|food:apple]]"),
    (r"\bMilks?\b",               "[[Milk|food:milk]]"),
    (r"\bPears?\b",               "[[Pear|food:pear]]"),
    # Egg: skip "Cracked Egg" (pet token, not the food)
    (r"(?<!Cracked )\bEggs?\b",   "[[Egg|food:egg]]"),
]


def _build_combined(
    rules: list[tuple[str, str]],
) -> tuple[re.Pattern, list[str]]:
    """Compile all rules into one alternation regex with named groups."""
    parts = []
    for i, (pat, _) in enumerate(rules):
        parts.append(f"(?P<g{i}>{pat})")
    return re.compile("|".join(parts)), [rep for _, rep in rules]


_COMBINED, _REPLACEMENTS = _build_combined(_RULES)


def apply_linkbacks(text: str) -> str:
    """Replace known pet/food names in ability text with [[...]] link tokens."""
    def _replace(m: re.Match) -> str:
        for i, rep in enumerate(_REPLACEMENTS):
            if m.group(f"g{i}") is not None:
                return rep
        return m.group(0)

    return _COMBINED.sub(_replace, text)

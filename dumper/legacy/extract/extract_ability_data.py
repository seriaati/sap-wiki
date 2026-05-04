"""
Super Auto Pets - Ability Data Extractor
========================================
Extracts pet names, ability descriptions (per level), fine print text,
and trigger display names from an AssetRipper "Unity Project" dump of SAP.

Usage:
    python3 extract_ability_data.py <path/to/SAP_dump> [--output out.json]

Where SAP_dump is the root folder AssetRipper produced (contains
ExportedProject/ and AuxiliaryFiles/).

Output JSON structure:
{
  "abilities": {
    "AntAbility": {
      "1.About": "Give one random friend +1 {AttackIcon} attack ...",
      "2.About": "Give one random friend +2 {AttackIcon} attack ...",
      "3.About": "Give one random friend +3 {AttackIcon} attack ...",
      "1.FinePrint": "..."   # optional, not all abilities have this
    },
    ...
  },
  "triggers": {
    "Sell": {"": "Sell"},
    "Faint": {"": "Friend faints"},
    ...
  },
  "pet_names": {
    "Ant": "Ant",
    "Beaver": "Beaver",
    ...
  }
}

HOW THE DATA IS STORED IN SAP
==============================
SAP uses Unity's Addressables system. Actual game data lives inside
.bundle files under:
  ExportedProject/Assets/StreamingAssets/aa/StandaloneLinux64/

The relevant bundles are:

1. localization-assets-shared_assets_all.bundle
   Contains SharedTableData MonoBehaviours. These map numeric IDs to
   human-readable localization keys, e.g.:
     ID 6058870937669637  ->  "Ability.BeaverAbility.1.About"
     ID 1845511106875392  ->  "Minion.Ant.Name"
   This is the KEY→ID index.

2. localization-string-tables-english_assets_all.bundle
   Contains StringTable MonoBehaviours (one per locale). The English
   table maps the same numeric IDs to actual translated strings, e.g.:
     ID 6058870937669637  ->  "Give two random friends +1 attack ..."
   This is the ID→TEXT index.

Joining the two by ID gives us KEY→TEXT.

Key naming convention in GeneratedStrings:
  Ability.<AbilityName>.<level>.About      - ability description
  Ability.<AbilityName>.<level>.FinePrint  - small-print caveat
  Minion.<PetName>.Name                    - display name of the pet
  Trigger.<TriggerName>                    - trigger display name
  Spell.<SpellName>.About                  - food/spell description

NOTE: Ability trigger wiring (which trigger fires which ability, e.g.
"BeaverAbility fires on Sell") is compiled into AbilityConstants.cs
method bodies in SpacewoodCore2.dll. Those method bodies are stripped
in the shipped build, so they cannot be extracted from the dump alone.
The trigger display names ARE available (see "triggers" in output), but
the ability→trigger mapping is not.
"""

import argparse
import json
import os
import re
import sys

try:
    import UnityPy
except ImportError:
    sys.exit("UnityPy not installed. Run: pip install UnityPy")


BUNDLE_DIR_RELATIVE = os.path.join(
    "ExportedProject", "Assets", "StreamingAssets", "aa", "StandaloneLinux64"
)

SHARED_BUNDLE_NAME = "localization-assets-shared_assets_all.bundle"
ENGLISH_STRINGS_BUNDLE_NAME = "localization-string-tables-english_assets_all.bundle"


def load_id_to_key(shared_bundle_path: str) -> dict[int, str]:
    """
    Parse the shared localization bundle to build a map of numeric ID → key string.

    The shared bundle contains SharedTableData MonoBehaviours. Each has an
    m_Entries list where every entry carries:
      - m_Id   : the numeric ID used as the cross-reference handle
      - m_Key  : the human-readable dot-separated key, e.g. "Ability.Ant.1.About"

    We only care about the "GeneratedStrings" table because that is where
    all per-pet and per-ability entries live. The other tables (GeneralStrings,
    LocoStrings) contain UI copy and are not needed here.
    """
    env = UnityPy.load(shared_bundle_path)
    id_to_key = {}

    for obj in env.objects:
        try:
            data = obj.read()
            name = getattr(data, "m_Name", "") or ""
            d = data.__dict__

            if "GeneratedStrings" not in name:
                continue
            if "m_Entries" not in d:
                continue

            for entry in d["m_Entries"]:
                entry_str = str(entry)
                m_id = re.search(r"m_Id=(\d+)", entry_str)
                m_key = re.search(r"m_Key='(.*?)'", entry_str)
                if m_id and m_key:
                    id_to_key[int(m_id.group(1))] = m_key.group(1)

        except Exception:
            pass

    return id_to_key


def load_id_to_text(english_bundle_path: str) -> dict[int, str]:
    """
    Parse the English string table bundle to build a map of numeric ID → text.

    The bundle contains StringTable MonoBehaviours for each locale (en, fr, de…).
    We read only the "GeneratedStrings_en" table, which holds the English text
    for all generated/data-driven strings (pet names, ability descriptions, etc.).

    Each entry carries:
      - m_Id        : same numeric ID used in the shared table
      - m_Localized : the actual display string (may contain icon placeholders
                      like {AttackIcon}, {HealthIcon}, {GoldIcon})
    """
    env = UnityPy.load(english_bundle_path)
    id_to_text = {}

    for obj in env.objects:
        try:
            data = obj.read()
            name = getattr(data, "m_Name", "") or ""

            if "GeneratedStrings_en" not in name:
                continue
            if not hasattr(data, "m_TableData"):
                continue

            for entry in data.m_TableData:
                entry_str = str(entry)
                m_id = re.search(r"m_Id=(\d+)", entry_str)
                m_loc = re.search(r"m_Localized='(.*?)'", entry_str)
                if m_id and m_loc:
                    id_to_text[int(m_id.group(1))] = m_loc.group(1)

        except Exception:
            pass

    return id_to_text


def build_key_to_text(id_to_key: dict, id_to_text: dict) -> dict[str, str]:
    """Join the two maps on numeric ID to get key → text."""
    return {
        key: id_to_text[id_]
        for id_, key in id_to_key.items()
        if id_ in id_to_text
    }


def group_by_entity(key_to_text: dict) -> dict[str, dict[str, str]]:
    """
    Convert the flat key→text map into a nested dict keyed by entity.

    Input key format:  "<Type>.<EntityName>.<field...>"
    Output:            { "<Type>.<EntityName>": { "<field>": "<text>" } }

    Examples:
      "Ability.BeaverAbility.1.About" → entities["Ability.BeaverAbility"]["1.About"]
      "Minion.Ant.Name"               → entities["Minion.Ant"]["Name"]
      "Trigger.Sell."                 → entities["Trigger.Sell"][""]
    """
    entities: dict[str, dict[str, str]] = {}
    for key, text in key_to_text.items():
        parts = key.split(".", 2)
        if len(parts) < 2:
            continue
        entity_key = f"{parts[0]}.{parts[1]}"
        field = parts[2] if len(parts) == 3 else ""
        entities.setdefault(entity_key, {})[field] = text
    return entities


def extract(sap_root: str) -> dict:
    """
    Main extraction entry point.

    Loads both relevant bundles from the SAP dump, joins the localization
    data, and returns a structured dict with:
      - abilities  : per-ability description fields, keyed by AbilityName
      - triggers   : trigger display names, keyed by TriggerName
      - pet_names  : pet display names, keyed by internal PetName
    """
    bundle_dir = os.path.join(sap_root, BUNDLE_DIR_RELATIVE)

    shared_path = os.path.join(bundle_dir, SHARED_BUNDLE_NAME)
    english_path = os.path.join(bundle_dir, ENGLISH_STRINGS_BUNDLE_NAME)

    for path in (shared_path, english_path):
        if not os.path.exists(path):
            sys.exit(f"Bundle not found: {path}\nIs {sap_root} the correct SAP dump root?")

    print("Loading shared key index…")
    id_to_key = load_id_to_key(shared_path)
    print(f"  {len(id_to_key)} keys loaded")

    print("Loading English string table…")
    id_to_text = load_id_to_text(english_path)
    print(f"  {len(id_to_text)} strings loaded")

    key_to_text = build_key_to_text(id_to_key, id_to_text)
    entities = group_by_entity(key_to_text)

    abilities = {
        name.split(".", 1)[1]: fields
        for name, fields in entities.items()
        if name.startswith("Ability.")
    }

    triggers = {
        name.split(".", 1)[1]: fields
        for name, fields in entities.items()
        if name.startswith("Trigger.")
    }

    # Minion entries only have a Name field; no other fields exist in this data.
    # The per-ability stats and trigger mappings are compiled into
    # SpacewoodCore2.dll and are not present in any asset file.
    pet_names = {
        name.split(".", 1)[1]: fields.get("Name", "")
        for name, fields in entities.items()
        if name.startswith("Minion.") and "Name" in fields
    }

    print(f"  {len(abilities)} abilities, {len(triggers)} triggers, {len(pet_names)} pets")

    return {
        "abilities": abilities,
        "triggers": triggers,
        "pet_names": pet_names,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Extract SAP ability data from an AssetRipper Unity Project dump."
    )
    parser.add_argument(
        "sap_root",
        help="Path to the AssetRipper dump root (folder containing ExportedProject/)",
    )
    parser.add_argument(
        "--output",
        default="sap_ability_data.json",
        help="Output JSON file path (default: sap_ability_data.json)",
    )
    args = parser.parse_args()

    data = extract(args.sap_root)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"Saved to {args.output}")


if __name__ == "__main__":
    main()

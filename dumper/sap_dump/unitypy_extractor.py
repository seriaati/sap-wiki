import os
import re
import sys

from .constants import BUNDLE_DIR_RELATIVE, ENGLISH_STRINGS_BUNDLE_NAME, SHARED_BUNDLE_NAME


def load_id_to_key(shared_bundle_path: str) -> dict:
    import UnityPy

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


def load_id_to_text(english_bundle_path: str) -> dict:
    import UnityPy

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
                m_loc = re.search(r"m_Localized=(['\"])(.*?)\1", entry_str, re.DOTALL)
                if m_id and m_loc:
                    id_to_text[int(m_id.group(1))] = m_loc.group(2)
        except Exception:
            pass
    return id_to_text


def extract_unitypy(sap_root: str) -> dict:
    """
    Returns:
      {
        "abilities":  { "BeaverAbility": { "1.About": "...", ... }, ... },
        "triggers":   { "Sell": { "": "Sell" }, ... },
        "pet_names":  { "Ant": "Ant", ... },
      }
    """
    bundle_dir = os.path.join(sap_root, BUNDLE_DIR_RELATIVE)
    shared_path = os.path.join(bundle_dir, SHARED_BUNDLE_NAME)
    english_path = os.path.join(bundle_dir, ENGLISH_STRINGS_BUNDLE_NAME)

    for path in (shared_path, english_path):
        if not os.path.exists(path):
            sys.exit(
                f"Bundle not found: {path}\nIs {sap_root} the correct SAP dump root?"
            )

    print("[1] Loading shared key index...")
    id_to_key = load_id_to_key(shared_path)
    print(f"    {len(id_to_key)} keys loaded")

    print("[1] Loading English string table...")
    id_to_text = load_id_to_text(english_path)
    print(f"    {len(id_to_text)} strings loaded")

    key_to_text = {
        key: id_to_text[id_] for id_, key in id_to_key.items() if id_ in id_to_text
    }

    entities: dict = {}
    for key, text in key_to_text.items():
        parts = key.split(".", 2)
        if len(parts) < 2:
            continue
        entity_key = f"{parts[0]}.{parts[1]}"
        field = parts[2] if len(parts) == 3 else ""
        entities.setdefault(entity_key, {})[field] = text

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
    pet_names = {
        name.split(".", 1)[1]: fields.get("Name", "")
        for name, fields in entities.items()
        if name.startswith("Minion.") and "Name" in fields
    }
    spell_descs = {
        name.split(".", 1)[1]: fields
        for name, fields in entities.items()
        if name.startswith("Spell.")
    }

    print(
        f"    {len(abilities)} abilities, {len(triggers)} triggers, "
        f"{len(pet_names)} pet names, {len(spell_descs)} spell descs"
    )
    return {"abilities": abilities, "triggers": triggers, "pet_names": pet_names, "spell_descs": spell_descs}

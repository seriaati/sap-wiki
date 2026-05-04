"""
Super Auto Pets — All-in-one extractor.

Usage:
    uv run python main.py <SAP_DUMP_ROOT>

Where SAP_DUMP_ROOT is the AssetRipper dump root (contains ExportedProject/).

Output: output/pets.json  output/foods.json
"""

import argparse
import json
import os
import sys

from sap_dump.asset_extractor import copy_assets
from sap_dump.builder import build_final
from sap_dump.constants import TEXTURE2D_DIR_RELATIVE
from sap_dump.frida_runner import run_frida_session
from sap_dump.icon_map_extractor import extract_dice_map, extract_icon_map
from sap_dump.unitypy_extractor import extract_unitypy

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def main():
    parser = argparse.ArgumentParser(
        description="Extract all Super Auto Pets data and write output/pets.json and output/foods.json"
    )
    parser.add_argument(
        "sap_dump_root",
        help="Path to AssetRipper dump root (folder containing ExportedProject/)",
    )
    args = parser.parse_args()

    sap_root = os.path.abspath(args.sap_dump_root)
    if not os.path.isdir(sap_root):
        sys.exit(f"Not a directory: {sap_root}")

    print("=== Step 1: UnityPy extraction ===")
    unitypy_data = extract_unitypy(sap_root)

    print("\n=== Step 2: Frida extraction (single game session) ===")
    frida_data = run_frida_session()

    print(
        f"\n[2] Raw results: {len(frida_data['pets_raw'])} pets, "
        f"{len(frida_data['foods_raw'])} foods, "
        f"{len(frida_data['triggers_raw'])} trigger entries"
    )

    out_dir = os.path.join(SCRIPT_DIR, "output")
    os.makedirs(out_dir, exist_ok=True)

    print("\n=== Step 3: Building final JSON ===")

    print("\n=== Step 4: Copying assets ===")
    texture2d_dir = os.path.join(sap_root, TEXTURE2D_DIR_RELATIVE)
    out_assets_dir = os.path.join(out_dir, "assets")

    pet_keys = [k for k in frida_data["pets_raw"] if not k.startswith("Relic")]
    toy_keys = [k for k in frida_data["pets_raw"] if k.startswith("Relic")]
    food_keys = list(frida_data["foods_raw"].keys())

    pet_images = copy_assets(texture2d_dir, pet_keys, out_assets_dir)
    toy_key_map = {k[len("Relic"):]: k for k in toy_keys}  # stripped → Relic* original
    _toy_images_raw = copy_assets(texture2d_dir, list(toy_key_map.keys()), out_assets_dir)
    toy_images = {toy_key_map[s]: f for s, f in _toy_images_raw.items()}
    food_images = copy_assets(texture2d_dir, food_keys, out_assets_dir)
    print(f"[4] {len(pet_images)}/{len(pet_keys)} pet images, {len(toy_images)}/{len(toy_keys)} toy images, {len(food_images)}/{len(food_keys)} food images")

    icon_map_path = extract_icon_map(sap_root, out_assets_dir, out_dir)
    print(f"[4] Icon map saved to {icon_map_path}")

    dice_map_path = extract_dice_map(sap_root, out_assets_dir, out_dir)
    print(f"[4] Dice map saved to {dice_map_path}")

    print("\n=== Step 5: Building final JSON ===")
    out = build_final(
        unitypy_data, frida_data, pet_images=pet_images, food_images=food_images, toy_images=toy_images
    )

    active_pets = len(out["pets"])
    active_foods = len(out["foods"])
    active_toys = len(out["toys"])
    print(f"[5] Final: {active_pets} active pets, {active_foods} active foods, {active_toys} active toys")

    pets_path = os.path.join(out_dir, "pets.json")
    foods_path = os.path.join(out_dir, "foods.json")
    toys_path = os.path.join(out_dir, "toys.json")
    with open(pets_path, "w", encoding="utf-8") as f:
        json.dump(out["pets"], f, indent=2, ensure_ascii=False)
    with open(foods_path, "w", encoding="utf-8") as f:
        json.dump(out["foods"], f, indent=2, ensure_ascii=False)
    with open(toys_path, "w", encoding="utf-8") as f:
        json.dump(out["toys"], f, indent=2, ensure_ascii=False)
    print(f"\n[*] Saved to {pets_path}")
    print(f"[*] Saved to {foods_path}")
    print(f"[*] Saved to {toys_path}")
    print(f"[*] Assets in {out_assets_dir}")


if __name__ == "__main__":
    main()

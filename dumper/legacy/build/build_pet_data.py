"""
Build final combined pet data JSON.

Joins:
  pet_stats_raw.json       -> attack, health, tier, price, active, rollable
  ability_trigger_map.json -> trigger display name, ability descriptions per level
  sap_ability_data.json    -> display name

Output: pet_data_final.json
  {
    "Ant": {
      "displayName": "Ant",
      "tier": 1,
      "attack": 2,
      "health": 2,
      "price": 3,
      "active": true,
      "rollable": true,
      "trigger": "Faint",
      "triggerClass": "TriggerDeath",
      "ability1": "Give one random friend +1/+1.",
      "ability2": "Give one random friend +2/+2.",
      "ability3": "Give one random friend +3/+3."
    },
    ...
  }
"""
import json, os, re

HERE = os.path.dirname(os.path.abspath(__file__))

stats   = json.load(open(os.path.join(HERE, "pet_stats_raw.json")))
atm     = json.load(open(os.path.join(HERE, "ability_trigger_map.json")))
sad     = json.load(open(os.path.join(HERE, "sap_ability_data.json")))

pet_names    = sad.get("pet_names", {})   # "Ant" -> "Ant" (display)
abilities_db = sad.get("abilities", {})   # "AntAbility" -> {"1.About": ..., "2.About": ...}

# Build reverse lookup: pet_name -> ability_key in atm
# atm keys are like "AntAbility", "BeaverAbility", but also "Ant" for some
atm_by_pet = {}
for ability_key, adata in atm.items():
    # Strip trailing "Ability" if present
    pet_key = re.sub(r"Ability$", "", ability_key)
    atm_by_pet[pet_key] = adata

output = {}

for pet_name, s in stats.items():
    if not s.get("active"):
        continue

    # Display name from localization (fallback to pet_name)
    display = pet_names.get(pet_name, pet_name)

    # Look up ability data
    adata = atm_by_pet.get(pet_name, {})
    ability_key = pet_name + "Ability"
    adb = abilities_db.get(ability_key, {})

    entry = {
        "displayName": display,
        "tier":        s["tier"],
        "attack":      s["attack"],
        "health":      s["health"],
        "price":       s["price"],
        "active":      s["active"],
        "rollable":    s["rollable"],
        "trigger":     adata.get("trigger_display", ""),
        "triggerClass": adata.get("trigger_class", ""),
        "ability1":    adb.get("1.About", ""),
        "ability2":    adb.get("2.About", ""),
        "ability3":    adb.get("3.About", ""),
    }

    # Include finePrint if present
    fp1 = adb.get("1.FinePrint", "")
    if fp1:
        entry["finePrint1"] = fp1
        entry["finePrint2"] = adb.get("2.FinePrint", "")
        entry["finePrint3"] = adb.get("3.FinePrint", "")

    output[pet_name] = entry

# Sort by tier then name
output = dict(sorted(output.items(), key=lambda x: (x[1]["tier"], x[0])))

out_path = os.path.join(HERE, "pet_data_final.json")
with open(out_path, "w") as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

print(f"Saved {len(output)} pets to {out_path}")

# Summary
from collections import Counter
rollable = {k: v for k, v in output.items() if v["rollable"]}
with_trigger = {k: v for k, v in rollable.items() if v["trigger"]}
with_ability = {k: v for k, v in rollable.items() if v["ability1"]}

print(f"  Total active: {len(output)}")
print(f"  Rollable shop pets: {len(rollable)}")
print(f"  With trigger data: {len(with_trigger)}")
print(f"  With ability text: {len(with_ability)}")

tiers = Counter(v["tier"] for v in rollable.values())
print(f"  Tier breakdown: {dict(sorted(tiers.items()))}")

# Sample output
print("\nSample pets:")
for name in ["Ant", "Beaver", "Cat", "Leopard", "Dragon", "Mammoth"]:
    if name in output:
        v = output[name]
        print(f"  {v['displayName']} T{v['tier']}: {v['attack']}/{v['health']} "
              f"| trigger={v['trigger']} | {v['ability1'][:60]}")

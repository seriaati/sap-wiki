"""
Wire everything into one JSON: pets + foods.

Sources:
  pet_stats_raw.json       -> attack, health, tier, price, active, rollable
  ability_trigger_map.json -> trigger display name + class, ability descriptions per level
  sap_ability_data.json    -> display name (pets), ability texts
  food_prices_raw.json     -> food tier, price, active, rollable

Output: sap_data_final.json
  {
    "pets": {
      "Ant": {
        "name": "Ant",
        "tier": 1, "cost": 3,
        "attack": 2, "health": 2,
        "active": true, "rollable": true,
        "trigger": "Faint",
        "ability1": "...", "ability2": "...", "ability3": "..."
      }, ...
    },
    "foods": {
      "Apple": {
        "name": "Apple",
        "tier": 1, "cost": 3,
        "active": true, "rollable": true,
        "ability": "Give one friend +1 attack and +1 health."
      }, ...
    }
  }
"""
import json, os, re
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    return json.load(open(os.path.join(HERE, name)))


def camel_to_words(s):
    """'BirthdayCake' -> 'Birthday Cake'"""
    return re.sub(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", s)


# ── Load sources ──────────────────────────────────────────────────────────────
stats        = load("pet_stats_raw.json")        # {PetName: {attack, health, tier, price, active, rollable, ...}}
atm          = load("ability_trigger_map.json")  # {PetNameAbility: {trigger_display, trigger_class, ...}}
sad          = load("sap_ability_data.json")     # {abilities: {...}, pet_names: {...}}
food_prices  = load("food_prices_raw.json")      # {FoodName: {tier, price, active, rollable, ...}}

pet_names    = sad.get("pet_names", {})          # "Ant" -> display string
abilities_db = sad.get("abilities", {})          # "AntAbility" -> {"1.About": ..., ...}

# Reverse lookup: pet key -> ability_trigger_map entry (strip trailing "Ability")
atm_by_pet = {re.sub(r"Ability$", "", k): v for k, v in atm.items()}

# ── Build pets ────────────────────────────────────────────────────────────────
pets = {}

for pet_name, s in stats.items():
    if not s.get("active"):
        continue

    adata = atm_by_pet.get(pet_name, {})
    adb   = abilities_db.get(pet_name + "Ability", {})

    entry = {
        "name":     pet_names.get(pet_name, camel_to_words(pet_name)),
        "tier":     s["tier"],
        "cost":     s["price"],
        "attack":   s["attack"],
        "health":   s["health"],
        "active":   s["active"],
        "rollable": s["rollable"],
        "trigger":  adata.get("trigger_display", ""),
        "ability1": adb.get("1.About", ""),
        "ability2": adb.get("2.About", ""),
        "ability3": adb.get("3.About", ""),
    }

    fp1 = adb.get("1.FinePrint", "")
    if fp1:
        entry["finePrint1"] = fp1
        entry["finePrint2"] = adb.get("2.FinePrint", "")
        entry["finePrint3"] = adb.get("3.FinePrint", "")

    pets[pet_name] = entry

# Sort by tier then name
pets = dict(sorted(pets.items(), key=lambda x: (x[1]["tier"], x[0])))

# ── Build foods ───────────────────────────────────────────────────────────────
foods = {}

for food_name, f in food_prices.items():
    if not f.get("active"):
        continue

    adb = abilities_db.get(food_name + "Ability", {})

    foods[food_name] = {
        "name":     camel_to_words(food_name),
        "tier":     f["tier"],
        "cost":     f["price"],
        "active":   f["active"],
        "rollable": f["rollable"],
        "ability":  adb.get("1.About", ""),
    }

# Sort by tier then name
foods = dict(sorted(foods.items(), key=lambda x: (x[1]["tier"], x[0])))

# ── Write output ──────────────────────────────────────────────────────────────
out = {"pets": pets, "foods": foods}
out_path = os.path.join(HERE, "sap_data_final.json")
with open(out_path, "w") as fp:
    json.dump(out, fp, indent=2, ensure_ascii=False)

print(f"Saved to {out_path}")
print(f"  Pets:  {len(pets)}")
print(f"  Foods: {len(foods)}")

pet_tiers  = Counter(v["tier"] for v in pets.values())
food_tiers = Counter(v["tier"] for v in foods.values())
print(f"  Pet tiers:  {dict(sorted(pet_tiers.items()))}")
print(f"  Food tiers: {dict(sorted(food_tiers.items()))}")

# Spot-check
print("\nSample pets:")
for n in ["Ant", "Beaver", "Cat", "Dragon", "Mammoth"]:
    if n in pets:
        p = pets[n]
        print(f"  {p['name']} T{p['tier']} {p['attack']}/{p['health']} | {p['trigger']} | {p['ability1'][:50]}")

print("\nSample foods:")
for n in ["Apple", "Banana", "Pizza", "Sushi"]:
    if n in foods:
        f = foods[n]
        print(f"  {f['name']} T{f['tier']} ${f['cost']} | {f['ability'][:60]}")

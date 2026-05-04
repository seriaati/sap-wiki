# sap-wiki

Super Auto Pets wiki based on data directly extracted from the game files.

## Motive

I can't find wikis with up-to-date data. Also, existing wikis rely on manual updates, which means slow and difficult to keep up.

## How it works

The repo has two parts: a dumper that extracts data from the game, and a wiki that renders it.

### Dumper

The dumper runs in two parallel extraction passes then merges the results.

#### Step 1: UnityPy (static assets)

`sap_dump/unitypy_extractor.py` reads the game's Unity asset bundles using [UnityPy](https://github.com/K0lb3/UnityPy). It parses the localization bundles to extract ability descriptions, fine-print text, and item names in English. You need an [AssetRipper](https://github.com/AssetRipper/AssetRipper) dump of the game as input.

#### Step 2: Frida (runtime data)

`sap_dump/frida_runner.py` spawns the game process and injects `sap_dump/hooks.js` via [Frida](https://frida.re). The JS hooks into the Unity IL2CPP runtime and intercepts:

- `MinionTemplate` construction - captures each pet's attack, health, tier, cost, and enum ID
- `SetTrigger` / `SetAbout` calls on `Ability` objects - captures trigger class names and per-turn limits
- `SpellConstants` initialization - captures food item prices and stats

Frida sends all captured data back to the Python host over a message channel. The game is then killed.

#### Step 3: Build & merge

`sap_dump/builder.py` joins the UnityPy localization data with the Frida runtime data into a unified structure. It resolves trigger class names to human-readable display names, computes fine-print text (e.g. "Works 3 times per turn"), and splits the output into pets, foods, and toys.

#### Step 4: Asset extraction

`sap_dump/asset_extractor.py` copies Texture2D sprite images out of the AssetRipper dump for every pet, food, and toy. `sap_dump/icon_map_extractor.py` also extracts the icon atlas and dice skin maps.

Output (written to `dumper/output/`):

| File | Contents |
|------|----------|
| `pets.json` | All pets - stats, ability text, tier, images |
| `foods.json` | All food items - stats, price, images |
| `toys.json` | All toys (Relic* entries) - stats, ability text, images |
| `icon_map.json` | Icon atlas mapping |
| `dice_map.json` | Dice skin mapping |
| `assets/` | Extracted PNG sprites |

Running the dumper:

```bash
cd dumper
uv run python main.py /path/to/AssetRipper/dump/root
```

Requires the game to be installed (Linux Steam). Frida must be able to spawn the game binary.

### Wiki

An [Astro](https://astro.build) static site that reads directly from `dumper/output/`. A `prebuild` script copies the assets into `public/assets/`. Pages are generated at build time from the JSON files.

Routes:

| Path | Content |
|------|---------|
| `/pets` | Grid of all pets, filterable by tier |
| `/pets/[name]` | Individual pet page with stats and ability |
| `/foods` | Grid of all food items |
| `/foods/[name]` | Individual food page |
| `/toys` | Grid of all toys |
| `/toys/[name]` | Individual toy page |

Running the wiki:

```bash
cd wiki
npm install
npm run dev      # dev server
npm run build    # static build to dist/
```

## Todo

- Fix not showing "Works X times per turn" text for some abilities.
- Fix pets without localized ability descriptions missing their ability text entirely (like Peacock Spider).
- Add more detail about ability triggers (e.g. Dragon's "When level 1 summoned.")
- Add pet types (e.g. "Gold", "Cycle", etc.)
- Add switching between skin packs.
- Add MCP, so you can use AI to build decks.
- Add different languages.

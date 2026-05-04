"""
SAP food/spell price extractor.

Strategy:
  1. Hook MinionConstants.EnsureMinions (fires on game's main thread at startup).
  2. In that hook, invoke SpellConstants.CreateSpells() — same thread, no abort.
  3. After invoke, read SpellConstants.Spells (Dictionary<SpellEnum,ItemTemplate>)
     directly from memory: parse IL2CPP Dictionary layout to extract every
     (SpellEnum int, ItemTemplate*) pair without relying on inner hooks
     (which Frida's re-entrancy guard blocks).
  4. For each entry read Price@36, Tier@32, Active@48, Rollable@49.
  5. Map SpellEnum int→name via il2cpp_field_static_get_value at the same time.

Output: food_prices_raw.json
  { "Apple": { "price": 3, "tier": 1, "active": true, "rollable": true }, ... }
"""
import frida, json, signal, os, time, threading
from pathlib import Path

GAME_DIR = str(Path.home() / ".local/share/Steam/steamapps/common/Super Auto Pets")
GAME_BIN = f"{GAME_DIR}/superautopets.x86_64"
OUTPUT   = str(Path.home() / "Documents/GitHub/sap-data-scrape/food_prices_raw.json")

JS = r"""
"use strict";
function cstr(p) { try { return (p && !p.isNull()) ? p.readUtf8String() : null; } catch(e) { return null; } }

let g = {};
let doneSent = false;

// ── Read SpellEnum int→name ───────────────────────────────────────────────
function buildEnumNames() {
    const {classGetFields, fieldGetName, fieldStaticGetValue, spellEnumClass} = g;
    const names = {};
    const it = Memory.alloc(Process.pointerSize); it.writePointer(ptr(0));
    let fld;
    while (!(fld = classGetFields(spellEnumClass, it)).isNull()) {
        const fn_ = cstr(fieldGetName(fld));
        if (!fn_ || fn_ === "value__") continue;
        try {
            const buf = Memory.alloc(8); buf.writeU64(0n);
            fieldStaticGetValue(fld, buf);
            names[buf.readS32()] = fn_;
        } catch(e) {}
    }
    return names;
}

// ── Traverse IL2CPP Dictionary<SpellEnum,ItemTemplate*> ──────────────────
// Layout (64-bit IL2CPP):
//   Dictionary object header: klass*(8) + monitor*(8) = 16 bytes
//   +16: int[] buckets  (Il2CppArray*)
//   +24: Entry[] entries (Il2CppArray*)
//   +32: int count
//   Il2CppArray header: klass*(8)+monitor*(8)+bounds*(8)+length(8) = 32 bytes
//   Each Entry<int,ptr>: hashCode(4)+next(4)+key(4)+pad(4)+value*(8) = 24 bytes
function readSpellsDict(dictPtr) {
    const out = {}; // enumInt → ItemTemplate*
    try {
        if (!dictPtr || dictPtr.isNull()) return out;
        const entriesArr = dictPtr.add(24).readPointer();
        if (!entriesArr || entriesArr.isNull()) return out;
        const count = dictPtr.add(32).readS32();
        send({t:"log", m:`Dict: count=${count} entries@${entriesArr}`});
        // entries array data starts at offset 32 (Il2CppArray header)
        const DATA_OFFSET = 32;
        const ENTRY_SIZE  = 24;
        for (let i = 0; i < count; i++) {
            try {
                const base = entriesArr.add(DATA_OFFSET + i * ENTRY_SIZE);
                const hash = base.readS32();
                if (hash < 0) continue; // freed slot
                const enumInt = base.add(8).readS32();   // key (SpellEnum)
                const valPtr  = base.add(16).readPointer(); // value (ItemTemplate*)
                if (!valPtr || valPtr.isNull()) continue;
                out[enumInt] = valPtr;
            } catch(e) {}
        }
    } catch(e) {
        send({t:"log", m:"readSpellsDict error: " + e});
    }
    return out;
}

// ── Main extraction (called on game thread from EnsureMinions hook) ───────
function extractSpells() {
    const {classGetFields, fieldGetName, fieldStaticGetValue,
           spellEnumClass, spellConstClass,
           createSpellsMth, runtimeInvoke,
           spellsField} = g;

    // 1. Invoke CreateSpells (we're on game thread here)
    send({t:"log", m:"Invoking CreateSpells..."});
    try {
        const excPtr = Memory.alloc(Process.pointerSize); excPtr.writePointer(ptr(0));
        runtimeInvoke(createSpellsMth, ptr(0), ptr(0), excPtr);
        const exc = excPtr.readPointer();
        if (exc && !exc.isNull()) send({t:"log", m:"CreateSpells: got exception"});
        else                      send({t:"log", m:"CreateSpells: OK"});
    } catch(e) {
        send({t:"log", m:"CreateSpells invoke error: " + e});
        return {};
    }

    // 2. Read Spells static field → Dictionary pointer
    const buf = Memory.alloc(Process.pointerSize); buf.writePointer(ptr(0));
    fieldStaticGetValue(spellsField, buf);
    const dictPtr = buf.readPointer();
    send({t:"log", m:`Spells dict ptr: ${dictPtr}`});

    // 3. Traverse dictionary
    const enumToPtr = readSpellsDict(dictPtr);
    send({t:"log", m:`Dict entries found: ${Object.keys(enumToPtr).length}`});

    // 4. Build enum names
    const enumNames = buildEnumNames();
    send({t:"log", m:`SpellEnum names: ${Object.keys(enumNames).length}`});

    // 5. For each entry, read ItemTemplate fields
    const results = {};
    for (const [enumIntStr, p] of Object.entries(enumToPtr)) {
        const enumInt = parseInt(enumIntStr);
        const name = enumNames[enumInt];
        if (!name || name.startsWith("_Blank") || name.startsWith("_removed")) continue;
        try {
            const tier     = p.add(32).readS32();
            const price    = p.add(36).readS32();
            const active   = p.add(48).readU8() !== 0;
            const rollable = p.add(49).readU8() !== 0;
            results[name] = {price, tier, active, rollable, enumInt};
        } catch(e) {}
    }

    return results;
}

// ── Setup ─────────────────────────────────────────────────────────────────
function setupAfterInit(mod) {
    function nfn(name, ret, args) {
        const a = mod.findExportByName(name);
        if (!a) { send({t:"log", m:"Missing: "+name}); return null; }
        return new NativeFunction(a, ret, args);
    }
    const domainGet           = nfn("il2cpp_domain_get",           "pointer", []);
    const domainGetAssemblies = nfn("il2cpp_domain_get_assemblies","pointer", ["pointer","pointer"]);
    const assemblyGetImage    = nfn("il2cpp_assembly_get_image",   "pointer", ["pointer"]);
    const imageGetName        = nfn("il2cpp_image_get_name",       "pointer", ["pointer"]);
    const imageGetClassCount  = nfn("il2cpp_image_get_class_count","uint32",  ["pointer"]);
    const imageGetClass       = nfn("il2cpp_image_get_class",      "pointer", ["pointer","uint32"]);
    const classGetName        = nfn("il2cpp_class_get_name",       "pointer", ["pointer"]);
    const classGetFields      = nfn("il2cpp_class_get_fields",     "pointer", ["pointer","pointer"]);
    const fieldGetName        = nfn("il2cpp_field_get_name",       "pointer", ["pointer"]);
    const fieldStaticGetValue = nfn("il2cpp_field_static_get_value","void",   ["pointer","pointer"]);
    const classGetMethods     = nfn("il2cpp_class_get_methods",    "pointer", ["pointer","pointer"]);
    const methodGetName       = nfn("il2cpp_method_get_name",      "pointer", ["pointer"]);
    const runtimeInvoke       = nfn("il2cpp_runtime_invoke",       "pointer", ["pointer","pointer","pointer","pointer"]);

    const domain = domainGet();
    const sz = Memory.alloc(8); sz.writeU64(0);
    const asmArr = domainGetAssemblies(domain, sz);
    const asmCnt = sz.readU32();

    let spellConstClass = null, spellEnumClass = null, minionConstClass = null;
    for (let ai = 0; ai < asmCnt; ai++) {
        const asm   = asmArr.add(ai * Process.pointerSize).readPointer();
        const img   = assemblyGetImage(asm);
        const iname = cstr(imageGetName(img)) || "?";
        if (!iname.includes("SpacewoodCore2")) continue;
        const n = imageGetClassCount(img);
        for (let ci = 0; ci < n; ci++) {
            const klass = imageGetClass(img, ci);
            if (!klass || klass.isNull()) continue;
            const cname = cstr(classGetName(klass));
            if      (cname === "SpellConstants")  spellConstClass  = klass;
            else if (cname === "SpellEnum")        spellEnumClass   = klass;
            else if (cname === "MinionConstants")  minionConstClass = klass;
        }
    }
    send({t:"log", m:`const=${!!spellConstClass} enum=${!!spellEnumClass} minionConst=${!!minionConstClass}`});
    if (!spellConstClass || !spellEnumClass) { send({t:"log", m:"Missing classes"}); return; }

    // Find SpellConstants.Spells field
    let spellsField = null;
    {
        const it = Memory.alloc(Process.pointerSize); it.writePointer(ptr(0));
        let fld;
        while (!(fld = classGetFields(spellConstClass, it)).isNull()) {
            const fn_ = cstr(fieldGetName(fld));
            if (fn_ === "Spells") { spellsField = fld; break; }
        }
    }
    if (!spellsField) { send({t:"log", m:"Spells field not found"}); return; }
    send({t:"log", m:"Spells field found"});

    // Find SpellConstants.CreateSpells method
    let createSpellsMth = null;
    {
        const it = Memory.alloc(Process.pointerSize); it.writePointer(ptr(0));
        let mth;
        while (!(mth = classGetMethods(spellConstClass, it)).isNull()) {
            const mn = cstr(methodGetName(mth));
            if (mn === "CreateSpells") { createSpellsMth = mth; break; }
        }
    }
    if (!createSpellsMth) { send({t:"log", m:"CreateSpells method not found"}); return; }
    send({t:"log", m:"CreateSpells method found"});

    // Store in g for use in hooks
    g = {classGetFields, fieldGetName, fieldStaticGetValue,
         spellEnumClass, spellConstClass,
         createSpellsMth, runtimeInvoke,
         spellsField};

    // Find and hook MinionConstants.EnsureMinions
    if (minionConstClass) {
        const it = Memory.alloc(Process.pointerSize); it.writePointer(ptr(0));
        let mth;
        while (!(mth = classGetMethods(minionConstClass, it)).isNull()) {
            const mn = cstr(methodGetName(mth));
            if (mn !== "EnsureMinions") continue;
            let fnPtr = null;
            try { fnPtr = mth.readPointer(); } catch(e) { break; }
            if (!fnPtr || fnPtr.isNull()) break;
            try {
                Interceptor.attach(fnPtr, {
                    onLeave(retval) {
                        if (doneSent) return;
                        doneSent = true;
                        send({t:"log", m:"EnsureMinions fired — extracting spells on game thread"});
                        try {
                            const results = extractSpells();
                            const n = Object.keys(results).length;
                            send({t:"log", m:`Extracted ${n} spells`});
                            send({t:"results", data: results});
                        } catch(e) {
                            send({t:"log", m:"extractSpells error: " + e});
                            send({t:"results", data: {}});
                        }
                        send({t:"done"});
                    }
                });
                send({t:"log", m:"Hooked EnsureMinions"});
            } catch(e) {
                send({t:"log", m:"EnsureMinions hook failed: " + e});
            }
            break;
        }
    }

    send({t:"ready"});
}

// ── Ctrl-C / fallback dump via Python message ─────────────────────────────
recv("dump", function() {
    if (doneSent) { send({t:"done"}); return; }
    doneSent = true;
    try {
        const results = extractSpells();
        send({t:"results", data: results});
    } catch(e) {
        send({t:"log", m:"dump error: " + e});
        send({t:"results", data: {}});
    }
    send({t:"done"});
});

const pollTimer = setInterval(() => {
    const mod = Process.findModuleByName("GameAssembly.so");
    if (!mod) return;
    clearInterval(pollTimer);
    send({t:"log", m:`GameAssembly.so @ ${mod.base}`});
    try { setupAfterInit(mod); } catch(e) { send({t:"log", m:""+e}); }
}, 100);
"""

results = {}
done = False
script_ref = None

def on_message(msg, _data):
    global results, done
    if msg['type'] == 'send':
        p = msg['payload']
        t = p.get('t', '')
        if t == 'log':
            print(f"  [JS] {p['m']}", flush=True)
        elif t == 'ready':
            print("  [*] Hooks ready — waiting for EnsureMinions()", flush=True)
            def fallback():
                time.sleep(90)
                if not done:
                    print("  [*] Fallback dump (90s)", flush=True)
                    script_ref.post({"type": "dump"})
            threading.Thread(target=fallback, daemon=True).start()
        elif t == 'results':
            results = p['data']
            print(f"  [*] Got {len(results)} food/spells", flush=True)
        elif t == 'done':
            done = True
    elif msg['type'] == 'error':
        print(f"  [ERR] {msg.get('description','?')}", flush=True)


def main():
    global script_ref, done
    import subprocess

    existing = subprocess.run(["pgrep", "-f", "superautopets.x86_64"],
                              capture_output=True, text=True).stdout.strip()
    if existing:
        print(f"[*] Killing existing SAP instances: {existing.replace(chr(10), ' ')}")
        subprocess.run(["pkill", "-f", "superautopets.x86_64"], capture_output=True)
        time.sleep(2)

    env = {**os.environ, "DISPLAY": ":0"}
    print("[*] Spawning SAP...")
    pid = frida.spawn([GAME_BIN], cwd=GAME_DIR, env=env)
    print(f"[*] PID {pid}")

    sess = frida.attach(pid)
    scr = sess.create_script(JS)
    scr.on('message', on_message)
    scr.load()
    script_ref = scr
    frida.resume(pid)

    def handle_ctrl_c(sig, frame):
        print("\n[*] Ctrl-C — forcing dump")
        script_ref.post({"type": "dump"})
    signal.signal(signal.SIGINT, handle_ctrl_c)

    print("[*] Waiting for auto-extraction...")
    for _ in range(300):
        time.sleep(1)
        if done: break

    import subprocess as sp
    sp.run(["kill", str(pid)], capture_output=True)

    if not results:
        print("[!] No results")
        return

    with open(OUTPUT, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\n[*] Saved {len(results)} foods to {OUTPUT}")

    active   = {k: v for k, v in results.items() if v['active']}
    rollable = {k: v for k, v in active.items() if v['rollable']}
    print(f"[*] Active: {len(active)}, Rollable: {len(rollable)}")

    from collections import Counter
    prices = Counter(v['price'] for v in rollable.values())
    print(f"[*] Price distribution: {dict(sorted(prices.items()))}")
    print("\nSample foods:")
    for k, v in list(rollable.items())[:10]:
        print(f"  {k}: price={v['price']} tier={v['tier']}")


if __name__ == "__main__":
    main()

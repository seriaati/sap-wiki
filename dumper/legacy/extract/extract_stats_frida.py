"""
SAP pet stats extractor — hook-based approach.

Hooks MinionTemplate.SetStats(attack, health), SetTier(tier), SetActive(bool)
called during MinionConstants.EnsureMinions() initialization.

At Ctrl-C / auto-dump: for each hooked template pointer, reads Enum@192 to
identify the minion, then combines with captured stats.

MinionTemplate field offsets (from dump):
  Inherited from ItemTemplate: Tier@32, Price@36, Active@48, Rollable@49
  Own: Enum@192, Attack@208, AttackMax@212, Health@220, HealthMax@224, TierMax@264

Output: pet_stats_raw.json
  { "Ant": { "attack":1, "attackMax":2, "health":2, "healthMax":3,
             "tier":1, "price":3, "active":true, "rollable":true }, ... }
"""
import frida, json, signal, sys, os, time, threading
from pathlib import Path

GAME_DIR = str(Path.home() / ".local/share/Steam/steamapps/common/Super Auto Pets")
GAME_BIN = f"{GAME_DIR}/superautopets.x86_64"
OUTPUT   = str(Path.home() / "Documents/GitHub/sap-data-scrape/pet_stats_raw.json")

JS = r"""
"use strict";

function cstr(p) {
    try { return (p && !p.isNull()) ? p.readUtf8String() : null; }
    catch(e) { return null; }
}

// Globals
const hookedTemplates = new Map();  // ptr_str → {ptr, attack, attackMax, health, healthMax, tier}
let g = {};
let hooked = false;

// ── Dump triggered by Python ──────────────────────────────────────────────
function dumpAll() {
    const {classGetFields, fieldGetName, fieldStaticGetValue, minionEnumClass} = g;

    // Build MinionEnum int→name
    const enumNames = {};
    {
        const it = Memory.alloc(Process.pointerSize); it.writePointer(ptr(0));
        let fld;
        while (!(fld = classGetFields(minionEnumClass, it)).isNull()) {
            const fn_ = cstr(fieldGetName(fld));
            if (!fn_ || fn_ === "value__") continue;
            try {
                const buf = Memory.alloc(8); buf.writeU64(0n);
                fieldStaticGetValue(fld, buf);
                const val = buf.readS32();
                enumNames[val] = fn_;
            } catch(e) {}
        }
        send({t:"log", m:`MinionEnum: ${Object.keys(enumNames).length} values`});
    }

    send({t:"log", m:`Hooked templates: ${hookedTemplates.size}`});

    const results = {};
    for (const [key, info] of hookedTemplates) {
        const {ptr: p} = info;

        // Read Enum@192 to identify which minion this is
        let enumInt = -1;
        try { enumInt = p.add(192).readS32(); } catch(e) { continue; }

        const minionName = enumNames[enumInt];
        if (!minionName) continue;

        // Read all template fields directly from the object
        // (these are the final values after all SetXxx calls)
        let tier, price, active, rollable, attack, attackMax, health, healthMax, tierMax;
        try {
            tier      = p.add(32).readS32();
            price     = p.add(36).readS32();
            active    = p.add(48).readU8() !== 0;
            rollable  = p.add(49).readU8() !== 0;
            attack    = p.add(208).readS32();
            attackMax = p.add(212).readS32();
            health    = p.add(220).readS32();
            healthMax = p.add(224).readS32();
            tierMax   = p.add(264).readS32();
        } catch(e) { continue; }

        results[minionName] = {
            attack, attackMax, health, healthMax,
            tier, price, active, rollable, tierMax,
            enumInt
        };
    }

    send({t:"log", m:`Results: ${Object.keys(results).length} pets`});
    send({t:"results", data: results});
}

// ── Hook MinionTemplate methods ────────────────────────────────────────────
function hookMinionTemplate(mod, minionTemplClass) {
    const classGetMethods = new NativeFunction(
        mod.findExportByName("il2cpp_class_get_methods"), "pointer", ["pointer","pointer"]);
    const methodGetName = new NativeFunction(
        mod.findExportByName("il2cpp_method_get_name"), "pointer", ["pointer"]);

    const TARGET_METHODS = new Set(["SetStats", "SetStatsMax", "SetTier", "SetActive",
                                    "SetRollable", ".ctor"]);
    let hookCount = 0;

    const it = Memory.alloc(Process.pointerSize); it.writePointer(ptr(0));
    let mth;
    while (!(mth = classGetMethods(minionTemplClass, it)).isNull()) {
        const mn = cstr(methodGetName(mth));
        if (!mn || !TARGET_METHODS.has(mn)) continue;

        let fnPtr = null;
        try { fnPtr = mth.readPointer(); } catch(e) { continue; }
        if (!fnPtr || fnPtr.isNull()) continue;

        // We hook each method. In all cases args[0] = `this`.
        const methodName = mn;
        try {
            Interceptor.attach(fnPtr, {
                onEnter(args) {
                    const self = args[0];
                    if (!self || self.isNull()) return;
                    const key = self.toString();
                    if (!hookedTemplates.has(key)) {
                        hookedTemplates.set(key, {ptr: self});
                    }
                    // No need to capture individual arg values — we'll read all
                    // fields directly from the object at dump time.
                }
            });
            hookCount++;
        } catch(e) {
            send({t:"log", m:`Hook failed for ${methodName}: ${e}`});
        }
    }

    send({t:"log", m:`Hooked ${hookCount} MinionTemplate methods`});
    return hookCount;
}

// ── Also hook MinionConstants.EnsureMinions to know when init happens ─────
function hookEnsureMinions(mod, minionConstClass) {
    const classGetMethods = new NativeFunction(
        mod.findExportByName("il2cpp_class_get_methods"), "pointer", ["pointer","pointer"]);
    const methodGetName = new NativeFunction(
        mod.findExportByName("il2cpp_method_get_name"), "pointer", ["pointer"]);

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
                    send({t:"log", m:`EnsureMinions() returned — templates should be set up now. Count=${hookedTemplates.size}`});
                    send({t:"ensured"});
                }
            });
            send({t:"log", m:`Hooked EnsureMinions`});
        } catch(e) {
            send({t:"log", m:`EnsureMinions hook failed: ${e}`});
        }
        break;
    }
}

// ── Setup ──────────────────────────────────────────────────────────────────
function setupAfterInit(mod) {
    function nfn(name, ret, args) {
        const a = mod.findExportByName(name);
        if (!a) { send({t:"log", m:"Missing: " + name}); return null; }
        return new NativeFunction(a, ret, args);
    }

    const domainGet           = nfn("il2cpp_domain_get",           "pointer", []);
    const domainGetAssemblies = nfn("il2cpp_domain_get_assemblies", "pointer", ["pointer","pointer"]);
    const assemblyGetImage    = nfn("il2cpp_assembly_get_image",    "pointer", ["pointer"]);
    const imageGetName        = nfn("il2cpp_image_get_name",        "pointer", ["pointer"]);
    const imageGetClassCount  = nfn("il2cpp_image_get_class_count", "uint32",  ["pointer"]);
    const imageGetClass       = nfn("il2cpp_image_get_class",       "pointer", ["pointer","uint32"]);
    const classGetName        = nfn("il2cpp_class_get_name",        "pointer", ["pointer"]);
    const classGetFields      = nfn("il2cpp_class_get_fields",      "pointer", ["pointer","pointer"]);
    const fieldGetName        = nfn("il2cpp_field_get_name",        "pointer", ["pointer"]);
    const fieldStaticGetValue = nfn("il2cpp_field_static_get_value","void",    ["pointer","pointer"]);

    if (!domainGet) { send({t:"log", m:"Missing IL2CPP exports"}); return; }

    g.classGetFields    = classGetFields;
    g.fieldGetName      = fieldGetName;
    g.fieldStaticGetValue = fieldStaticGetValue;

    // Find classes
    const domain   = domainGet();
    const sizePtr  = Memory.alloc(8); sizePtr.writeU64(0);
    const asmArray = domainGetAssemblies(domain, sizePtr);
    const asmCount = sizePtr.readU32();

    let minionConstClass = null, minionTemplClass = null, minionEnumClass = null;
    for (let ai = 0; ai < asmCount; ai++) {
        const asm   = asmArray.add(ai * Process.pointerSize).readPointer();
        const img   = assemblyGetImage(asm);
        const iname = cstr(imageGetName(img)) || "?";
        if (!iname.includes("SpacewoodCore2")) continue;

        const n = imageGetClassCount(img);
        for (let ci = 0; ci < n; ci++) {
            const klass = imageGetClass(img, ci);
            if (!klass || klass.isNull()) continue;
            const cname = cstr(classGetName(klass));
            if (cname === "MinionConstants") minionConstClass = klass;
            else if (cname === "MinionTemplate") minionTemplClass = klass;
            else if (cname === "MinionEnum") minionEnumClass = klass;
        }
    }

    send({t:"log", m:`Classes: const=${!!minionConstClass} tmpl=${!!minionTemplClass} enum=${!!minionEnumClass}`});
    if (!minionConstClass || !minionTemplClass || !minionEnumClass) {
        send({t:"log", m:"Missing required classes"}); return;
    }

    g.minionEnumClass = minionEnumClass;

    // Hook MinionTemplate methods to capture template pointers
    hookMinionTemplate(mod, minionTemplClass);

    // Hook EnsureMinions to know when all templates are set up
    hookEnsureMinions(mod, minionConstClass);

    send({t:"ready"});
}

// ── Message handler ────────────────────────────────────────────────────────
recv("dump", function() {
    try { dumpAll(); } catch(e) {
        send({t:"log", m:"dumpAll error: " + e + "\n" + (e.stack||"")});
        send({t:"results", data: {}});
    }
    send({t:"done"});
});

const pollTimer = setInterval(() => {
    const mod = Process.findModuleByName("GameAssembly.so");
    if (!mod) return;
    clearInterval(pollTimer);
    send({t:"log", m:`GameAssembly.so @ ${mod.base}`});
    try { setupAfterInit(mod); }
    catch(e) { send({t:"log", m:"Setup error: " + e.message}); }
}, 100);
"""

results = {}
done = False
script_ref = None
ensured = False

def on_message(msg, _data):
    global results, done, ensured
    if msg['type'] == 'send':
        p = msg['payload']
        t = p.get('t', '')
        if t == 'log':
            print(f"  [JS] {p['m']}", flush=True)
        elif t == 'ready':
            print("  [*] Hooks installed — waiting for EnsureMinions() or Ctrl-C", flush=True)
            # Auto-dump fallback after 60s if EnsureMinions not seen
            def auto_dump_fallback():
                time.sleep(60)
                if not done:
                    print("  [*] Fallback auto-dump (60s)", flush=True)
                    script_ref.post({"type": "dump"})
            threading.Thread(target=auto_dump_fallback, daemon=True).start()
        elif t == 'ensured':
            ensured = True
            print("  [*] EnsureMinions done — auto-dumping in 2s", flush=True)
            def dump_after_ensure():
                time.sleep(2)
                if not done:
                    script_ref.post({"type": "dump"})
            threading.Thread(target=dump_after_ensure, daemon=True).start()
        elif t == 'results':
            results = p['data']
            print(f"  [*] Got {len(results)} pet templates", flush=True)
        elif t == 'done':
            done = True
    elif msg['type'] == 'error':
        print(f"  [ERR] {msg.get('description','?')}", flush=True)


def main():
    global script_ref, done

    env = {**os.environ, "DISPLAY": ":0"}
    print("[*] Spawning SAP...")
    pid = frida.spawn([GAME_BIN], cwd=GAME_DIR, env=env)
    print(f"[*] PID {pid}")

    sess = frida.attach(pid)
    scr  = sess.create_script(JS)
    scr.on('message', on_message)
    scr.load()
    script_ref = scr
    frida.resume(pid)

    print("[*] Waiting... game will auto-dump when MinionConstants initialises")
    print("[*] (Or Ctrl-C to force dump now)")

    def handle_ctrl_c(sig, frame):
        print("\n[*] Ctrl-C — posting dump")
        script_ref.post({"type": "dump"})

    signal.signal(signal.SIGINT, handle_ctrl_c)

    for _ in range(300):
        time.sleep(1)
        if done:
            break

    import subprocess
    subprocess.run(["kill", str(pid)], capture_output=True)

    if not results:
        print("[!] No results — EnsureMinions may not have been called yet")
        print("[!] Try: wait for game to reach main menu before Ctrl-C")
        return

    with open(OUTPUT, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\n[*] Saved {len(results)} pets to {OUTPUT}")

    active = {k: v for k, v in results.items() if v.get('active')}
    rollable = {k: v for k, v in active.items() if v.get('rollable')}
    print(f"[*] Active: {len(active)}, Rollable (shop pets): {len(rollable)}")
    for k, v in list(rollable.items())[:8]:
        print(f"  {k}: {v['attack']}/{v['health']} tier={v['tier']} price={v['price']}")


if __name__ == "__main__":
    main()

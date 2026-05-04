"""
SAP trigger extractor — deferred read approach.

SetTrigger(TriggerMinions) is called while the TriggerMinions object still has
TriggerType=0. The builder sets TriggerType AFTER storing the ref. So we save
every (ability_ptr, triggerMinions_ptr) pair during SetTrigger calls, then
on Ctrl-C read the CURRENT values from those (now-fully-initialised) objects.

Ability names come from UnityEngine.Object.get_name() via il2cpp_runtime_invoke.
Trigger type comes from il2cpp_object_get_class → il2cpp_class_get_name on the
TriggerMinions object (class name = trigger type, e.g. TriggerSell, TriggerDeath).
"""
import frida, json, signal, sys, os, time
from pathlib import Path

GAME_DIR = str(Path.home() / ".local/share/Steam/steamapps/common/Super Auto Pets")
GAME_BIN = f"{GAME_DIR}/superautopets.x86_64"
OUTPUT   = str(Path.home() / "Documents/GitHub/sap-data-scrape/trigger_mapping_frida.json")

JS = r"""
"use strict";

function cstr(p) {
    try { return (p && !p.isNull()) ? p.readUtf8String() : null; }
    catch(e) { return null; }
}
function readCsString(p) {
    try {
        if (!p || p.isNull()) return null;
        const len = p.add(12).readU32();
        if (len === 0 || len > 4096) return null;
        return p.add(16).readUtf16String(len);
    } catch(e) { return null; }
}

// State populated during hooks, read later on dump.
const savedAbilities = new Map();  // self_ptr_str → {self}
const hookNames      = new Map();  // self_ptr_str → locoKey (from SetAbout hook)

// Globals bound in setupAfterInit, used in dumpAll
let _objectGetClass  = null;
let _classGetName    = null;
let _classGetFields  = null;
let _fieldGetName    = null;
let _fieldStaticGetV = null;
let _abilityEnumClass = null;

// ── dump: called when Python sends {type:"dump"} ──────────────────────────
function dumpAll() {
    // Build AbilityEnum int→name map (deferred — statics initialized by now)
    const abilityEnumNames = {};
    if (_abilityEnumClass && _classGetFields && _fieldGetName && _fieldStaticGetV) {
        const it = Memory.alloc(Process.pointerSize); it.writePointer(ptr(0));
        let fld;
        while (!(fld = _classGetFields(_abilityEnumClass, it)).isNull()) {
            const fn_ = cstr(_fieldGetName(fld));
            if (fn_ && fn_ !== "value__") {
                try {
                    const buf = Memory.alloc(4);
                    _fieldStaticGetV(fld, buf);
                    abilityEnumNames[buf.readS32()] = fn_;
                } catch(e) {}
            }
        }
        send({t:"log", m:`AbilityEnum: ${Object.keys(abilityEnumNames).length} values`});
        const sample = Object.entries(abilityEnumNames).slice(0,5).map(([k,v])=>`${k}=${v}`).join(", ");
        send({t:"log", m:`  sample: ${sample}`});
    }

    const results = [];
    for (const [key, {self}] of savedAbilities) {
        // 1. Name from SetAbout hook (most reliable)
        let abilityName = hookNames.get(key) || null;

        // 2. Name from AbilityEnum field @ offset 16
        if (!abilityName && Object.keys(abilityEnumNames).length > 0) {
            try {
                const enumInt = self.add(16).readS32();
                abilityName = abilityEnumNames[enumInt] || null;
            } catch(e) {}
        }

        // 3. Raw enum int for diagnostics
        let enumInt = -1;
        try { enumInt = self.add(16).readS32(); } catch(e) {}

        // 4. Fallback: AboutLocoKey @ offset 40
        if (!abilityName) {
            try {
                const strPtr = self.add(40).readPointer();
                abilityName = readCsString(strPtr);
            } catch(e) {}
        }

        // Get trigger class name from TriggerMinions object at offset 440
        let trigPtr = null, trigClassName = null;
        try { trigPtr = self.add(440).readPointer(); } catch(e) {}
        if (trigPtr && !trigPtr.isNull() && _objectGetClass && _classGetName) {
            try {
                const tc = _objectGetClass(trigPtr);
                trigClassName = cstr(_classGetName(tc));
            } catch(e) {}
        }

        results.push({
            name:     abilityName,
            enum_int: enumInt,
            trig_cls: trigClassName,
            self:     key,
        });
    }
    send({t:"dump_result", data: results, count: results.length});
}

recv("dump", (_msg) => { dumpAll(); });

function setupAfterInit(mod) {
    function nfn(name, ret, args) {
        const a = mod.findExportByName(name);
        if (!a) { send({t:"log", m:"Missing export: " + name}); return null; }
        return new NativeFunction(a, ret, args);
    }

    const domainGet           = nfn("il2cpp_domain_get",            "pointer", []);
    const domainGetAssemblies = nfn("il2cpp_domain_get_assemblies", "pointer", ["pointer","pointer"]);
    const imageGetClassCount  = nfn("il2cpp_image_get_class_count", "uint32",  ["pointer"]);
    const imageGetClass       = nfn("il2cpp_image_get_class",       "pointer", ["pointer","uint32"]);
    const classGetName        = nfn("il2cpp_class_get_name",        "pointer", ["pointer"]);
    const classGetNamespace   = nfn("il2cpp_class_get_namespace",   "pointer", ["pointer"]);
    const classGetMethods     = nfn("il2cpp_class_get_methods",     "pointer", ["pointer","pointer"]);
    const classGetFields      = nfn("il2cpp_class_get_fields",      "pointer", ["pointer","pointer"]);
    const fieldGetName        = nfn("il2cpp_field_get_name",        "pointer", ["pointer"]);
    const fieldStaticGetValue = nfn("il2cpp_field_static_get_value","void",    ["pointer","pointer"]);
    const methodGetName       = nfn("il2cpp_method_get_name",       "pointer", ["pointer"]);
    const objectGetClass      = nfn("il2cpp_object_get_class",      "pointer", ["pointer"]);

    _objectGetClass  = objectGetClass;
    _classGetName    = classGetName;
    _classGetFields  = classGetFields;
    _fieldGetName    = fieldGetName;
    _fieldStaticGetV = fieldStaticGetValue;

    if (!domainGet) return;

    const domain   = domainGet();
    const sizePtr  = Memory.alloc(8); sizePtr.writeU64(0);
    const asmArray = domainGetAssemblies(domain, sizePtr);
    const asmCount = sizePtr.readU32();
    send({t:"log", m:`${asmCount} assemblies found`});

    const assemblyGetImage = nfn("il2cpp_assembly_get_image", "pointer", ["pointer"]);

    let abilityClass = null;

    for (let ai = 0; ai < asmCount; ai++) {
        const asmPtr = asmArray.add(ai * Process.pointerSize).readPointer();
        const img = assemblyGetImage(asmPtr);
        const n = imageGetClassCount(img);
        for (let ci = 0; ci < n; ci++) {
            const klass = imageGetClass(img, ci);
            if (!klass || klass.isNull()) continue;
            const cname = cstr(classGetName(klass));
            if (!cname) continue;

            if (cname === "Ability" && !abilityClass) {
                abilityClass = klass;
                send({t:"log", m:"Found Ability class"});
            }
            if (cname === "AbilityEnum" && !_abilityEnumClass) {
                _abilityEnumClass = klass;
                send({t:"log", m:"Found AbilityEnum class"});
            }
            if (abilityClass && _abilityEnumClass) break;
        }
        if (abilityClass && _abilityEnumClass) break;
    }

    if (!abilityClass)     { send({t:"log", m:"ERROR: Ability class not found"}); return; }
    if (!_abilityEnumClass){ send({t:"log", m:"WARNING: AbilityEnum not found — will use SetAbout hook only"}); }

    // Find and hook SetTrigger, SetAimAndTrigger, SetAbout
    const toHook = {SetTrigger: null, SetAimAndTrigger: null, SetAbout: null};
    {
        const it = Memory.alloc(Process.pointerSize); it.writePointer(ptr(0));
        let mth;
        while (!(mth = classGetMethods(abilityClass, it)).isNull()) {
            const mn = cstr(methodGetName(mth));
            if (mn && toHook.hasOwnProperty(mn) && !toHook[mn]) {
                toHook[mn] = mth.readPointer();
            }
        }
    }

    let hookedCount = 0;

    // SetAbout(string locoKey) — captures ability name→ptr mapping
    const setAboutPtr = toHook["SetAbout"];
    if (setAboutPtr && !setAboutPtr.isNull()) {
        try {
            Interceptor.attach(setAboutPtr, {
                onEnter(args) {
                    const s = readCsString(args[1]);
                    if (s) {
                        // locoKey format: "Ability.BeaverAbility.1.About" or just "BeaverAbility"
                        // Extract ability name from key
                        let name = s;
                        const parts = s.split('.');
                        if (parts.length >= 2 && parts[0] === 'Ability') name = parts[1];
                        hookNames.set(args[0].toString(), name);
                    }
                }
            });
            hookedCount++;
            send({t:"log", m:"Hooked SetAbout (for ability names)"});
        } catch(e) {
            send({t:"log", m:`SetAbout hook failed: ${e.message}`});
        }
    } else {
        send({t:"log", m:"SetAbout: not found"});
    }

    for (const label of ["SetTrigger", "SetAimAndTrigger"]) {
        const fnPtr = toHook[label];
        if (!fnPtr || fnPtr.isNull()) { send({t:"log", m:`${label}: not found`}); continue; }
        try {
            Interceptor.attach(fnPtr, {
                onEnter(args) {
                    savedAbilities.set(args[0].toString(), {self: args[0]});
                }
            });
            hookedCount++;
            send({t:"log", m:`Hooked ${label}`});
        } catch(e) {
            send({t:"log", m:`${label} hook failed: ${e.message}`});
        }
    }

    send({t:"log", m:`Ready. ${hookedCount} hooks active. Ctrl-C after game loads to dump.`});
}

const pollTimer = setInterval(() => {
    const mod = Process.findModuleByName("GameAssembly.so");
    if (!mod) return;
    clearInterval(pollTimer);
    send({t:"log", m:`GameAssembly.so @ ${mod.base}`});
    try { setupAfterInit(mod); }
    catch(e) { send({t:"log", m:"Error: " + e.message + "\n" + e.stack}); }
}, 100);
"""

saved_count = 0
dump_result = None


def on_message(msg, _data):
    global saved_count, dump_result
    if msg['type'] == 'send':
        p = msg['payload']
        t = p.get('t', '')
        if t == 'log':
            print(f"  [JS] {p['m']}", flush=True)
        elif t == 'dump_result':
            dump_result = p['data']
            print(f"  [*] Dump received: {p['count']} entries", flush=True)
        elif t == 'err':
            print(f"  [JS-ERR] {p['msg']}", flush=True)
    elif msg['type'] == 'error':
        print(f"  [FRIDA-ERR] {msg.get('description','?')}", flush=True)


def build_output(dump_result):
    """
    Collapse 3-level duplicates: each ability appears 3× (one per level) with
    identical trigger. Keep one entry per unique ability name.
    Output: { "BeaverAbility": "TriggerSell", ... }
    """
    seen = {}
    for entry in dump_result:
        name = entry.get('name')
        trig = entry.get('trig_cls')
        if not name:
            name = f"unknown_{entry.get('self','')[-6:]}"
        if name not in seen:
            seen[name] = trig or '?'
    return seen


def save_and_exit(pid, scr):
    print("\n[*] Requesting dump from JS...", flush=True)
    scr.post({"type": "dump"})
    for _ in range(30):
        time.sleep(0.2)
        if dump_result is not None:
            break
    else:
        print("[!] Dump timed out")

    mapping = build_output(dump_result or [])
    print(f"\n[*] {len(mapping)} unique ability→trigger mappings:")
    for k, v in sorted(mapping.items()):
        print(f"  {k:45s} -> {v}")

    with open(OUTPUT, 'w') as f:
        json.dump({"trigger_map": mapping, "raw_dump": dump_result}, f, indent=2)
    print(f"\n[*] Saved to {OUTPUT}")

    try:
        import subprocess
        subprocess.run(["kill", str(pid)], capture_output=True)
    except Exception:
        pass


def main():
    env = {**os.environ, "DISPLAY": ":0"}
    print("[*] Spawning SAP...")
    pid = frida.spawn([GAME_BIN], cwd=GAME_DIR, env=env)
    print(f"[*] PID {pid}")

    sess = frida.attach(pid)
    scr  = sess.create_script(JS)
    scr.on('message', on_message)
    scr.load()
    frida.resume(pid)

    print("[*] Hooks active. Wait for game to load fully, then press Ctrl-C.")

    def handle_sigint(_sig, _frame):
        save_and_exit(pid, scr)
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_sigint)
    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()

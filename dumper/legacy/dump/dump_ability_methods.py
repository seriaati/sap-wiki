"""
Dump all method names + code pointers for every XxxAbility class.
Runs at il2cpp_init time — no game navigation needed.
Output JSON: { "BeaverAbility": [{"name":"get_Trigger","ptr":"0x...","bytes":"hex..."},...], ... }
"""
import frida, json, signal, sys, os, time
from pathlib import Path

GAME_DIR = str(Path.home() / ".local/share/Steam/steamapps/common/Super Auto Pets")
GAME_BIN = f"{GAME_DIR}/superautopets.x86_64"
OUTPUT   = str(Path.home() / "Documents/GitHub/sap-data-scrape/ability_methods_dump.json")

JS = r"""
"use strict";

function cstr(p) {
    try { return (p && !p.isNull()) ? p.readUtf8String() : null; }
    catch(e) { return null; }
}

function setupAfterInit(mod) {
    function nfn(name, ret, args) {
        const a = mod.findExportByName(name);
        return a ? new NativeFunction(a, ret, args) : null;
    }

    const domainGet           = nfn("il2cpp_domain_get",           "pointer", []);
    const domainGetAssemblies = nfn("il2cpp_domain_get_assemblies", "pointer", ["pointer","pointer"]);
    const assemblyGetImage    = nfn("il2cpp_assembly_get_image",    "pointer", ["pointer"]);
    const imageGetName        = nfn("il2cpp_image_get_name",        "pointer", ["pointer"]);
    const imageGetClassCount  = nfn("il2cpp_image_get_class_count", "uint32",  ["pointer"]);
    const imageGetClass       = nfn("il2cpp_image_get_class",       "pointer", ["pointer","uint32"]);
    const classGetName        = nfn("il2cpp_class_get_name",        "pointer", ["pointer"]);
    const classGetNamespace   = nfn("il2cpp_class_get_namespace",   "pointer", ["pointer"]);
    const classGetMethods     = nfn("il2cpp_class_get_methods",     "pointer", ["pointer","pointer"]);
    const methodGetName       = nfn("il2cpp_method_get_name",       "pointer", ["pointer"]);
    const classGetFields      = nfn("il2cpp_class_get_fields",      "pointer", ["pointer","pointer"]);
    const fieldGetName        = nfn("il2cpp_field_get_name",        "pointer", ["pointer"]);
    const fieldGetOffset      = nfn("il2cpp_field_get_offset",      "uint32",  ["pointer"]);

    if (!domainGet) { send({t:"log", m:"Missing exports"}); return; }

    const domain   = domainGet();
    const sizePtr  = Memory.alloc(8); sizePtr.writeU64(0);
    const asmArray = domainGetAssemblies(domain, sizePtr);
    const asmCount = sizePtr.readU32();
    send({t:"log", m:`${asmCount} assemblies`});

    let found = 0;
    const results = {};

    for (let ai = 0; ai < asmCount; ai++) {
        const asm  = asmArray.add(ai * Process.pointerSize).readPointer();
        const img  = assemblyGetImage(asm);
        const iname = cstr(imageGetName(img));
        const n    = imageGetClassCount(img);

        for (let ci = 0; ci < n; ci++) {
            const klass = imageGetClass(img, ci);
            if (!klass || klass.isNull()) continue;
            const cname = cstr(classGetName(klass));
            if (!cname || !cname.endsWith("Ability")) continue;
            if (cname.startsWith("_") || cname.startsWith("<")) continue;

            // Collect fields
            const fields = [];
            {
                const it = Memory.alloc(Process.pointerSize); it.writePointer(ptr(0));
                let fld;
                while (!(fld = classGetFields(klass, it)).isNull()) {
                    const fn_ = cstr(fieldGetName(fld));
                    const off = fieldGetOffset(fld);
                    if (fn_) fields.push(`${fn_}@${off}`);
                }
            }

            // Collect methods: name + code pointer + first 32 bytes
            const methods = [];
            {
                const it = Memory.alloc(Process.pointerSize); it.writePointer(ptr(0));
                let mth;
                while (!(mth = classGetMethods(klass, it)).isNull()) {
                    const mn = cstr(methodGetName(mth));
                    if (!mn) continue;
                    // MethodInfo->methodPointer is at offset 0
                    let fnPtr = null;
                    let bytes = null;
                    try {
                        fnPtr = mth.readPointer();
                        if (fnPtr && !fnPtr.isNull()) {
                            const raw = Memory.readByteArray(fnPtr, 32);
                            bytes = Array.from(new Uint8Array(raw))
                                        .map(b => b.toString(16).padStart(2,'0'))
                                        .join('');
                        }
                    } catch(e) {}
                    methods.push({name: mn, ptr: fnPtr ? fnPtr.toString() : null, bytes: bytes});
                }
            }

            results[cname] = {image: iname, fields, methods};
            found++;
        }
    }

    send({t:"log", m:`Found ${found} Ability classes`});
    send({t:"results", data: results});
}

// GameAssembly.so appears in the module list only AFTER its .init_array runs
// (which includes il2cpp_init). IL2CPP is already initialized when we see it —
// call setup immediately, no init hook needed.
const pollTimer = setInterval(() => {
    const mod = Process.findModuleByName("GameAssembly.so");
    if (!mod) return;
    clearInterval(pollTimer);
    send({t:"log", m:`GameAssembly.so @ ${mod.base} — running setup immediately`});
    try { setupAfterInit(mod); }
    catch(e) { send({t:"log", m:"Error: " + e.message + "\\n" + e.stack}); }
    send({t:"done"});
}, 100);
"""

results = {}
done = False

def on_message(msg, _data):
    global results, done
    if msg['type'] == 'send':
        p = msg['payload']
        t = p.get('t','')
        if t == 'log':
            print(f"  [JS] {p['m']}", flush=True)
        elif t == 'results':
            results = p['data']
            print(f"  [*] Got data for {len(results)} ability classes", flush=True)
        elif t == 'done':
            done = True
    elif msg['type'] == 'error':
        print(f"  [ERR] {msg.get('description','?')}", flush=True)


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

    print("[*] Waiting for il2cpp_init to complete (~10-30s)...")
    timeout = 120
    for _ in range(timeout):
        time.sleep(1)
        if done:
            break
    else:
        print("[*] Timeout — saving whatever was captured")

    import subprocess
    subprocess.run(["kill", str(pid)], capture_output=True)

    with open(OUTPUT, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"[*] Saved to {OUTPUT}")

    # Quick summary: list all methods for Ability base + BeaverAbility
    for key in ("Ability", "BeaverAbility", "AntAbility"):
        if key in results:
            print(f"\n--- {key} ---")
            print(f"  fields: {results[key].get('fields', [])}")
            for m in results[key].get('methods', []):
                print(f"  method: {m['name']:40s} @ {m['ptr']}")


if __name__ == "__main__":
    main()

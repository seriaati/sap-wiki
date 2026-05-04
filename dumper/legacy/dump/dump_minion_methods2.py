"""
Extended dump: find concrete IMinionBuilder implementations + MinionTemplate/Spec classes.
Searches for any class with set_Attack + set_MinionEnum methods (= concrete builder).
Also dumps all classes with 'Template', 'Spec', 'Tier' in name from SpacewoodCore2.
"""
import frida, json, signal, sys, os, time
from pathlib import Path

GAME_DIR = str(Path.home() / ".local/share/Steam/steamapps/common/Super Auto Pets")
GAME_BIN = f"{GAME_DIR}/superautopets.x86_64"
OUTPUT   = str(Path.home() / "Documents/GitHub/sap-data-scrape/minion_methods_dump2.json")

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
    const classGetMethods     = nfn("il2cpp_class_get_methods",     "pointer", ["pointer","pointer"]);
    const methodGetName       = nfn("il2cpp_method_get_name",       "pointer", ["pointer"]);
    const classGetFields      = nfn("il2cpp_class_get_fields",      "pointer", ["pointer","pointer"]);
    const fieldGetName        = nfn("il2cpp_field_get_name",        "pointer", ["pointer"]);
    const fieldGetOffset      = nfn("il2cpp_field_get_offset",      "uint32",  ["pointer"]);
    const classGetParent      = nfn("il2cpp_class_get_parent",      "pointer", ["pointer"]);
    const classImplements     = nfn("il2cpp_class_is_assignable_from", "bool", ["pointer","pointer"]);
    const classFromName       = nfn("il2cpp_class_from_name",       "pointer", ["pointer","pointer","pointer"]);
    const imageFromName       = nfn("il2cpp_domain_get_assemblies", "pointer", ["pointer","pointer"]);

    if (!domainGet) { send({t:"log", m:"Missing exports"}); return; }

    const domain   = domainGet();
    const sizePtr  = Memory.alloc(8); sizePtr.writeU64(0);
    const asmArray = domainGetAssemblies(domain, sizePtr);
    const asmCount = sizePtr.readU32();
    send({t:"log", m:`${asmCount} assemblies found`});

    // Fragments to match on class name (lowercase)
    const FRAGS = [
        "template", "spec", "minionsetup", "minionstat",
        "createminion", "minionparam", "tieredminion",
        "minionshopitem", "minionshopmodel",
    ];
    // Also find any class with BOTH set_Attack and set_MinionEnum methods
    // (= concrete IMinionBuilder implementation)

    const results = {};
    let found = 0;

    // Two passes: first build index of all method signatures per class
    for (let ai = 0; ai < asmCount; ai++) {
        const asm   = asmArray.add(ai * Process.pointerSize).readPointer();
        const img   = assemblyGetImage(asm);
        const iname = cstr(imageGetName(img)) || "?";
        if (!iname.includes("SpacewoodCore2") && !iname.includes("Assembly-CSharp")) continue;

        const n = imageGetClassCount(img);
        for (let ci = 0; ci < n; ci++) {
            const klass = imageGetClass(img, ci);
            if (!klass || klass.isNull()) continue;
            const cname = cstr(classGetName(klass));
            if (!cname || cname.startsWith("<") || cname.startsWith("_")) continue;

            const clow = cname.toLowerCase();

            // Collect methods first to check for IMinionBuilder implementation
            const methodNames = new Set();
            const methods = [];
            if (classGetMethods) {
                const it = Memory.alloc(Process.pointerSize); it.writePointer(ptr(0));
                let mth;
                while (!(mth = classGetMethods(klass, it)).isNull()) {
                    const mn = cstr(methodGetName(mth));
                    if (mn) {
                        methodNames.add(mn);
                        let fnPtr = null;
                        try { fnPtr = mth.readPointer(); } catch(e) {}
                        methods.push({name: mn, ptr: fnPtr ? fnPtr.toString() : null});
                    }
                }
            }

            // Match criteria:
            // 1. Fragment match on class name
            // 2. OR: has both set_Attack AND set_MinionEnum (concrete IMinionBuilder)
            // 3. OR: has set_MinionEnum and set_Health
            const isConcrete = methodNames.has("set_Attack") && methodNames.has("set_MinionEnum");
            const isFragMatch = FRAGS.some(f => clow.includes(f));
            const hasMinionMethods = methodNames.has("set_MinionEnum") ||
                                     (methodNames.has("set_Attack") && methodNames.has("set_Health"));

            if (!isConcrete && !isFragMatch) continue;

            // Fields
            const fields = [];
            if (classGetFields) {
                const it = Memory.alloc(Process.pointerSize); it.writePointer(ptr(0));
                let fld;
                while (!(fld = classGetFields(klass, it)).isNull()) {
                    const fn_ = cstr(fieldGetName(fld));
                    const off = fieldGetOffset ? fieldGetOffset(fld) : -1;
                    if (fn_) fields.push(`${fn_}@${off}`);
                }
            }

            let parent = null;
            if (classGetParent) {
                try {
                    const pc = classGetParent(klass);
                    if (pc && !pc.isNull()) parent = cstr(classGetName(pc));
                } catch(e) {}
            }

            results[cname] = {
                image: iname,
                parent,
                isConcreteMinionBuilder: isConcrete,
                fields,
                methods
            };
            found++;
        }
    }

    send({t:"log", m:`Found ${found} matching classes`});
    send({t:"results", data: results});
    send({t:"done"});
}

const pollTimer = setInterval(() => {
    const mod = Process.findModuleByName("GameAssembly.so");
    if (!mod) return;
    clearInterval(pollTimer);
    send({t:"log", m:`GameAssembly.so @ ${mod.base}`});
    try { setupAfterInit(mod); }
    catch(e) { send({t:"log", m:"Error: " + e.message}); }
}, 100);
"""

results = {}
done = False

def on_message(msg, _data):
    global results, done
    if msg['type'] == 'send':
        p = msg['payload']
        t = p.get('t', '')
        if t == 'log':
            print(f"  [JS] {p['m']}", flush=True)
        elif t == 'results':
            results = p['data']
            print(f"  [*] Got data for {len(results)} classes", flush=True)
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

    print("[*] Waiting for il2cpp init (~10-30s)...")
    for _ in range(60):
        time.sleep(1)
        if done:
            break
    else:
        print("[*] Timeout")

    import subprocess
    subprocess.run(["kill", str(pid)], capture_output=True)

    with open(OUTPUT, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"[*] Saved to {OUTPUT}")

    for cls, info in results.items():
        tag = " [CONCRETE MINIONBUILDER]" if info.get('isConcreteMinionBuilder') else ""
        print(f"\n--- {cls} ({info['image']}) parent={info.get('parent')}{tag} ---")
        print(f"  fields: {info.get('fields', [])}")
        print(f"  methods: {[m['name'] for m in info.get('methods', [])]}")


if __name__ == "__main__":
    main()

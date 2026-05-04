"""
Dump SpellConstants, SpellTemplate, SpellEnum class fields/methods.
"""
import frida, json, os, time
from pathlib import Path

GAME_DIR = str(Path.home() / ".local/share/Steam/steamapps/common/Super Auto Pets")
GAME_BIN = f"{GAME_DIR}/superautopets.x86_64"
OUTPUT   = str(Path.home() / "Documents/GitHub/sap-data-scrape/spell_methods_dump.json")

JS = r"""
"use strict";
function cstr(p) { try { return (p && !p.isNull()) ? p.readUtf8String() : null; } catch(e) { return null; } }

function setupAfterInit(mod) {
    function nfn(name, ret, args) {
        const a = mod.findExportByName(name);
        return a ? new NativeFunction(a, ret, args) : null;
    }
    const domainGet           = nfn("il2cpp_domain_get",           "pointer", []);
    const domainGetAssemblies = nfn("il2cpp_domain_get_assemblies","pointer",["pointer","pointer"]);
    const assemblyGetImage    = nfn("il2cpp_assembly_get_image",   "pointer",["pointer"]);
    const imageGetName        = nfn("il2cpp_image_get_name",       "pointer",["pointer"]);
    const imageGetClassCount  = nfn("il2cpp_image_get_class_count","uint32", ["pointer"]);
    const imageGetClass       = nfn("il2cpp_image_get_class",      "pointer",["pointer","uint32"]);
    const classGetName        = nfn("il2cpp_class_get_name",       "pointer",["pointer"]);
    const classGetMethods     = nfn("il2cpp_class_get_methods",    "pointer",["pointer","pointer"]);
    const methodGetName       = nfn("il2cpp_method_get_name",      "pointer",["pointer"]);
    const classGetFields      = nfn("il2cpp_class_get_fields",     "pointer",["pointer","pointer"]);
    const fieldGetName        = nfn("il2cpp_field_get_name",       "pointer",["pointer"]);
    const fieldGetOffset      = nfn("il2cpp_field_get_offset",     "uint32", ["pointer"]);
    const classGetParent      = nfn("il2cpp_class_get_parent",     "pointer",["pointer"]);

    const domain  = domainGet();
    const szPtr   = Memory.alloc(8); szPtr.writeU64(0);
    const asmArr  = domainGetAssemblies(domain, szPtr);
    const asmCnt  = szPtr.readU32();

    const TARGETS = new Set(["SpellConstants","SpellTemplate","SpellEnum",
                              "SpellParsingTemplate","ItemTemplate"]);
    const results = {};

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
            if (!cname || !TARGETS.has(cname)) continue;

            const fields = [], methods = [];
            const fit = Memory.alloc(Process.pointerSize); fit.writePointer(ptr(0));
            let fld;
            while (!(fld = classGetFields(klass, fit)).isNull()) {
                const fn_ = cstr(fieldGetName(fld));
                const off = fieldGetOffset(fld);
                if (fn_) fields.push(`${fn_}@${off}`);
            }
            const mit = Memory.alloc(Process.pointerSize); mit.writePointer(ptr(0));
            let mth;
            while (!(mth = classGetMethods(klass, mit)).isNull()) {
                const mn = cstr(methodGetName(mth));
                if (mn) methods.push(mn);
            }
            let parent = null;
            try { const pc = classGetParent(klass); if (pc && !pc.isNull()) parent = cstr(classGetName(pc)); } catch(e) {}
            results[cname] = {image: iname, parent, fields, methods};
        }
    }

    send({t:"results", data: results});
    send({t:"done"});
}

const t = setInterval(() => {
    const mod = Process.findModuleByName("GameAssembly.so");
    if (!mod) return;
    clearInterval(t);
    try { setupAfterInit(mod); } catch(e) { send({t:"log", m:""+e}); }
}, 100);
"""

results = {}; done = False
def on_msg(msg, _):
    global results, done
    if msg['type'] == 'send':
        p = msg['payload']
        if p.get('t') == 'results': results = p['data']
        elif p.get('t') == 'done': done = True
        elif p.get('t') == 'log': print(f"  [JS] {p['m']}")

env = {**os.environ, "DISPLAY": ":0"}
pid = frida.spawn([GAME_BIN], cwd=GAME_DIR, env=env)
sess = frida.attach(pid); scr = sess.create_script(JS)
scr.on('message', on_msg); scr.load(); frida.resume(pid)
for _ in range(60):
    time.sleep(1)
    if done: break

import subprocess; subprocess.run(["kill", str(pid)], capture_output=True)
with open(OUTPUT, 'w') as f: json.dump(results, f, indent=2)
print(f"Saved to {OUTPUT}")
for cls, info in results.items():
    print(f"\n--- {cls} (parent={info['parent']}) ---")
    print(f"  fields:  {info['fields']}")
    print(f"  methods: {info['methods']}")

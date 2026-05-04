// Frida script: hook set_TriggerType to capture ability→trigger mappings
// Run after game initializes

"use strict";

const GAME_MODULE = "GameAssembly.so";

function readCString(ptr) {
    try { return ptr.isNull() ? null : ptr.readUtf8String(); } 
    catch(e) { return null; }
}

const results = {};

// Wait for game to initialize, then hook the TriggerType setter
// by finding the method via IL2CPP API
function setup() {
    const mod = Process.getModuleByName(GAME_MODULE);
    if (!mod) { console.log("[-] GameAssembly.so not found"); return; }
    
    const exports = {};
    const needed = [
        "il2cpp_class_from_name", "il2cpp_class_get_method_from_name",
        "il2cpp_method_get_pointer", "il2cpp_class_get_name",
        "il2cpp_object_get_class", "il2cpp_domain_get",
        "il2cpp_assembly_get_image", "il2cpp_domain_get_assemblies",
        "il2cpp_image_get_class_count", "il2cpp_image_get_class"
    ];
    
    for (const name of needed) {
        const addr = mod.findExportByName(name);
        if (addr) exports[name] = addr;
    }
    
    console.log("[*] Found exports:", Object.keys(exports).join(", "));
    
    // Hook il2cpp_runtime_class_init to detect when AbilityConstants type is initialized
    const classInit = mod.findExportByName("il2cpp_runtime_class_init");
    if (!classInit) { console.log("[-] class_init not found"); return; }
    
    const class_get_name = new NativeFunction(exports["il2cpp_class_get_name"], 'pointer', ['pointer']);
    
    let hooked = false;
    Interceptor.attach(classInit, {
        onEnter(args) {
            const klass = args[0];
            const name = readCString(class_get_name(klass));
            if (name === "AbilityConstants" && !hooked) {
                hooked = true;
                console.log("[+] AbilityConstants initializing! klass=", klass);
                
                // Now look for the TriggerType setter
                const setterName = Memory.allocUtf8String("set_TriggerType");
                const class_get_method = new NativeFunction(
                    exports["il2cpp_class_get_method_from_name"], 
                    'pointer', ['pointer', 'pointer', 'int']
                );
                const method_get_ptr = new NativeFunction(
                    exports["il2cpp_method_get_pointer"],
                    'pointer', ['pointer']
                );
                const obj_get_class = new NativeFunction(
                    exports["il2cpp_object_get_class"],
                    'pointer', ['pointer']
                );
                
                // Find Ability base class
                const nsName = Memory.allocUtf8String("Spacewood.Core.Models.Abilities");
                const abilityName = Memory.allocUtf8String("Ability");
                const class_from_name = new NativeFunction(
                    exports["il2cpp_class_from_name"],
                    'pointer', ['pointer', 'pointer', 'pointer']
                );
                
                // Search all images
                const domain = new NativeFunction(exports["il2cpp_domain_get"], 'pointer', [])();
                const getAssemblies = new NativeFunction(exports["il2cpp_domain_get_assemblies"], 'pointer', ['pointer', 'pointer']);
                const sizeRef = Memory.alloc(4);
                const asmArray = getAssemblies(domain, sizeRef);
                const count = sizeRef.readU32();
                console.log(`[*] ${count} assemblies`);
                
                const asmGet = new NativeFunction(exports["il2cpp_assembly_get_image"], 'pointer', ['pointer']);
                const imgGetCount = new NativeFunction(exports["il2cpp_image_get_class_count"], 'uint', ['pointer']);
                const imgGetClass = new NativeFunction(exports["il2cpp_image_get_class"], 'pointer', ['pointer', 'uint']);
                
                let abilityKlass = null;
                
                for (let i = 0; i < count; i++) {
                    const asm = asmArray.add(i * 8).readPointer();
                    const img = asmGet(asm);
                    const classCount = imgGetCount(img);
                    
                    for (let j = 0; j < classCount; j++) {
                        const k = imgGetClass(img, j);
                        const n = readCString(class_get_name(k));
                        if (n === "Ability") {
                            abilityKlass = k;
                            console.log(`[+] Found Ability class at ${k}`);
                            break;
                        }
                    }
                    if (abilityKlass) break;
                }
                
                if (!abilityKlass) {
                    console.log("[-] Ability class not found");
                    return;
                }
                
                // Get set_TriggerType method
                const method = class_get_method(abilityKlass, setterName, 1);
                if (!method.isNull()) {
                    const funcPtr = method_get_ptr(method);
                    console.log(`[+] set_TriggerType at ${funcPtr}`);
                    
                    // Hook it!
                    Interceptor.attach(funcPtr, {
                        onEnter(args) {
                            const thisObj = args[0];  // 'this' pointer
                            const triggerVal = args[1].toInt32();  // TriggerEvent enum value
                            const klass = obj_get_class(thisObj);
                            const className = readCString(class_get_name(klass));
                            if (className && className.endsWith("Ability")) {
                                results[className] = triggerVal;
                                console.log(`[*] ${className} -> TriggerEvent[${triggerVal}]`);
                            }
                        }
                    });
                }
            }
        }
    });
}

// Periodically dump results
setInterval(() => {
    if (Object.keys(results).length > 0) {
        console.log("=== RESULTS ===");
        console.log(JSON.stringify(results, null, 2));
    }
}, 5000);

// Start setup when script loads
setTimeout(setup, 100);

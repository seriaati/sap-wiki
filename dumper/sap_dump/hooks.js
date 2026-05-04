"use strict";

// ─── Utility ─────────────────────────────────────────────────────────────────
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

// ─── Global state ─────────────────────────────────────────────────────────────
const hookedTemplates = new Map();   // ptr_str → {ptr}   (MinionTemplate instances)
const savedAbilities  = new Map();   // ptr_str → {self, limit?, limitKind?}
const hookNames       = new Map();   // ptr_str → abilityName (from SetAbout)

let g = {};   // bound IL2CPP functions and classes

let statsFoodSent  = false;
let triggersSent   = false;
let gameReady      = false;
let lastTemplateMs = 0;

// ─── Pet stats + food prices extraction (called on game thread) ───────────────
function extractStatsFoods() {
    const {
        classGetFields, fieldGetName, fieldStaticGetValue,
        minionEnumClass,
        spellEnumClass, spellConstClass,
        createSpellsMth, runtimeInvoke,
        spellsField,
        minionDictFields,
    } = g;

    // Build MinionEnum int→name
    const minionEnumNames = {};
    {
        const it = Memory.alloc(Process.pointerSize); it.writePointer(ptr(0));
        let fld;
        while (!(fld = classGetFields(minionEnumClass, it)).isNull()) {
            const fn_ = cstr(fieldGetName(fld));
            if (!fn_ || fn_ === "value__") continue;
            try {
                const buf = Memory.alloc(8); buf.writeU64(0n);
                fieldStaticGetValue(fld, buf);
                minionEnumNames[buf.readS32()] = fn_;
            } catch(e) {}
        }
        send({t:"log", m:`MinionEnum: ${Object.keys(minionEnumNames).length} values`});
    }

    // Extract pet stats
    const pets = {};
    send({t:"log", m:`Hooked templates: ${hookedTemplates.size}`});
    for (const [key, info] of hookedTemplates) {
        const p = info.ptr;
        let enumInt = -1;
        try { enumInt = p.add(192).readS32(); } catch(e) { continue; }
        const minionName = minionEnumNames[enumInt];
        if (!minionName) continue;
        try {
            pets[minionName] = {
                tier:      p.add(32).readS32(),
                price:     p.add(36).readS32(),
                active:    p.add(48).readU8() !== 0,
                rollable:  p.add(49).readU8() !== 0,
                attack:    p.add(208).readS32(),
                attackMax: p.add(212).readS32(),
                health:    p.add(220).readS32(),
                healthMax: p.add(224).readS32(),
                tierMax:   p.add(264).readS32(),
                enumInt,
            };
        } catch(e) {}
    }
    send({t:"log", m:`Pet stats from hookedTemplates: ${Object.keys(pets).length} pets`});

    // Read MinionConstants dict fields (Minions, ActiveMinions, ReleasedMinions) to catch
    // templates whose .ctor fired before hook install (unowned DLC pack pets).
    // Log counts for all three so we can see which one has the full set.
    function readMinionDict(fieldName, fld) {
        const enumToPtr = {};
        try {
            const buf = Memory.alloc(Process.pointerSize); buf.writePointer(ptr(0));
            fieldStaticGetValue(fld, buf);
            const dictPtr = buf.readPointer();
            if (!dictPtr || dictPtr.isNull()) { send({t:"log", m:`${fieldName}: null ptr`}); return enumToPtr; }
            const entriesArr = dictPtr.add(24).readPointer();
            const count      = dictPtr.add(32).readS32();
            send({t:"log", m:`${fieldName}: count=${count}`});
            for (let i = 0; i < count; i++) {
                try {
                    const base   = entriesArr.add(32 + i * 24);
                    if (base.readS32() < 0) continue; // freed slot
                    const eInt   = base.add(8).readS32();
                    const valPtr = base.add(16).readPointer();
                    if (!valPtr || valPtr.isNull()) continue;
                    enumToPtr[eInt] = valPtr;
                } catch(e) {}
            }
        } catch(e) { send({t:"log", m:`${fieldName} read error: ${e}`}); }
        return enumToPtr;
    }

    for (const [fieldName, fld] of Object.entries(minionDictFields)) {
        const dictEnumToPtr = readMinionDict(fieldName, fld);
        let added = 0;
        for (const [eIntStr, p] of Object.entries(dictEnumToPtr)) {
            const eInt = parseInt(eIntStr);
            const minionName = minionEnumNames[eInt];
            if (!minionName || pets[minionName]) continue;
            try {
                pets[minionName] = {
                    tier:      p.add(32).readS32(),
                    price:     p.add(36).readS32(),
                    active:    p.add(48).readU8() !== 0,
                    rollable:  p.add(49).readU8() !== 0,
                    attack:    p.add(208).readS32(),
                    attackMax: p.add(212).readS32(),
                    health:    p.add(220).readS32(),
                    healthMax: p.add(224).readS32(),
                    tierMax:   p.add(264).readS32(),
                    enumInt: eInt,
                };
                added++;
            } catch(e) {}
        }
        if (added > 0) send({t:"log", m:`${fieldName}: added ${added} new pets (total now ${Object.keys(pets).length})`});
    }

    // Invoke SpellConstants.CreateSpells (safe — we're on game thread)
    send({t:"log", m:"Invoking CreateSpells..."});
    let foods = {};
    try {
        const excPtr = Memory.alloc(Process.pointerSize); excPtr.writePointer(ptr(0));
        runtimeInvoke(createSpellsMth, ptr(0), ptr(0), excPtr);
        const exc = excPtr.readPointer();
        if (exc && !exc.isNull()) {
            send({t:"log", m:"CreateSpells threw exception"});
        } else {
            send({t:"log", m:"CreateSpells OK"});
            // Read Spells static field → Dictionary<SpellEnum, ItemTemplate*>
            const buf = Memory.alloc(Process.pointerSize); buf.writePointer(ptr(0));
            fieldStaticGetValue(spellsField, buf);
            const dictPtr = buf.readPointer();
            send({t:"log", m:`Spells dict ptr: ${dictPtr}`});

            // Parse IL2CPP Dictionary layout
            // Object header 16 bytes; +16 buckets array; +24 entries array; +32 count
            // Il2CppArray header 32 bytes; each Entry: hashCode(4)+next(4)+key(4)+pad(4)+value*(8) = 24 bytes
            const enumToPtr = {};
            if (dictPtr && !dictPtr.isNull()) {
                try {
                    const entriesArr = dictPtr.add(24).readPointer();
                    const count      = dictPtr.add(32).readS32();
                    send({t:"log", m:`Dict: count=${count}`});
                    const DATA_OFFSET = 32;
                    const ENTRY_SIZE  = 24;
                    for (let i = 0; i < count; i++) {
                        try {
                            const base    = entriesArr.add(DATA_OFFSET + i * ENTRY_SIZE);
                            const hash    = base.readS32();
                            if (hash < 0) continue;  // freed slot
                            const enumInt = base.add(8).readS32();
                            const valPtr  = base.add(16).readPointer();
                            if (!valPtr || valPtr.isNull()) continue;
                            enumToPtr[enumInt] = valPtr;
                        } catch(e) {}
                    }
                } catch(e) {
                    send({t:"log", m:"Dict parse error: " + e});
                }
            }
            send({t:"log", m:`Dict entries found: ${Object.keys(enumToPtr).length}`});

            // Build SpellEnum int→name
            const spellEnumNames = {};
            {
                const it = Memory.alloc(Process.pointerSize); it.writePointer(ptr(0));
                let fld;
                while (!(fld = classGetFields(spellEnumClass, it)).isNull()) {
                    const fn_ = cstr(fieldGetName(fld));
                    if (!fn_ || fn_ === "value__") continue;
                    try {
                        const buf2 = Memory.alloc(8); buf2.writeU64(0n);
                        fieldStaticGetValue(fld, buf2);
                        spellEnumNames[buf2.readS32()] = fn_;
                    } catch(e) {}
                }
                send({t:"log", m:`SpellEnum names: ${Object.keys(spellEnumNames).length}`});
            }

            // Read ItemTemplate fields per spell
            for (const [enumIntStr, p] of Object.entries(enumToPtr)) {
                const enumInt = parseInt(enumIntStr);
                const name = spellEnumNames[enumInt];
                if (!name || name.startsWith("_Blank") || name.startsWith("_removed")) continue;
                try {
                    foods[name] = {
                        tier:     p.add(32).readS32(),
                        price:    p.add(36).readS32(),
                        active:   p.add(48).readU8() !== 0,
                        rollable: p.add(49).readU8() !== 0,
                        enumInt,
                    };
                } catch(e) {}
            }
            send({t:"log", m:`Foods extracted: ${Object.keys(foods).length}`});
        }
    } catch(e) {
        send({t:"log", m:"CreateSpells error: " + e});
    }

    return {pets, foods};
}

// ─── Trigger dump (called 5s after EnsureMinions) ────────────────────────────
function dumpTriggers() {
    const {objectGetClass, classGetName, classGetFields, fieldGetName,
           fieldStaticGetValue, abilityEnumClass} = g;

    // Build AbilityEnum int→name
    const abilityEnumNames = {};
    if (abilityEnumClass) {
        const it = Memory.alloc(Process.pointerSize); it.writePointer(ptr(0));
        let fld;
        while (!(fld = classGetFields(abilityEnumClass, it)).isNull()) {
            const fn_ = cstr(fieldGetName(fld));
            if (!fn_ || fn_ === "value__") continue;
            try {
                const buf = Memory.alloc(4);
                fieldStaticGetValue(fld, buf);
                abilityEnumNames[buf.readS32()] = fn_;
            } catch(e) {}
        }
        send({t:"log", m:`AbilityEnum: ${Object.keys(abilityEnumNames).length} values`});
    }

    const results = [];
    for (const [key, {self}] of savedAbilities) {
        // Ability name: prefer SetAbout hook name
        let abilityName = hookNames.get(key) || null;

        // Fallback: AbilityEnum int at offset 16
        if (!abilityName && Object.keys(abilityEnumNames).length > 0) {
            try {
                const enumInt = self.add(16).readS32();
                abilityName = abilityEnumNames[enumInt] || null;
            } catch(e) {}
        }

        // Fallback: read AboutLocoKey string at offset 40
        if (!abilityName) {
            try {
                const strPtr = self.add(40).readPointer();
                abilityName = readCsString(strPtr);
            } catch(e) {}
        }

        let enumInt = -1;
        try { enumInt = self.add(16).readS32(); } catch(e) {}

        // Trigger class name from TriggerMinions object at offset 440
        let trigClassName = null;
        try {
            const trigPtr = self.add(440).readPointer();
            if (trigPtr && !trigPtr.isNull() && objectGetClass && classGetName) {
                const tc = objectGetClass(trigPtr);
                trigClassName = cstr(classGetName(tc));
            }
        } catch(e) {}

        const stored = savedAbilities.get(key) || {};
        const entry = {name: abilityName, enum_int: enumInt, trig_cls: trigClassName};

        if (stored.triggerLimit     !== undefined) entry.triggerLimit     = stored.triggerLimit;
        if (stored.triggerLimitType !== undefined) entry.triggerLimitType = stored.triggerLimitType;
        if (stored.triggerLevel     !== undefined) entry.triggerLevel     = stored.triggerLevel;
        if (stored.finePrintKey)                   entry.finePrintKey     = stored.finePrintKey;
        if (stored.customNote)                     entry.customNote       = stored.customNote;
        if (stored.skipLocalization)               entry.skipLocalization = true;
        if (abilityName && abilityName.includes("PeacockSpider")) {
            send({t:"log", m:`DEBUG PeacockSpider entry: name=${abilityName} enumInt=${enumInt} trig=${trigClassName} stored_keys=${Object.keys(stored).join(",")}`});
        }
        results.push(entry);
    }

    return results;
}

// ─── Hook MinionTemplate methods to capture all template pointers ─────────────
function hookMinionTemplate(mod, minionTemplClass) {
    const classGetMethods = new NativeFunction(
        mod.findExportByName("il2cpp_class_get_methods"), "pointer", ["pointer","pointer"]);
    const methodGetName = new NativeFunction(
        mod.findExportByName("il2cpp_method_get_name"), "pointer", ["pointer"]);

    const TARGET_METHODS = new Set(["SetStats","SetStatsMax","SetTier","SetActive","SetRollable",".ctor"]);
    let hookCount = 0;

    const it = Memory.alloc(Process.pointerSize); it.writePointer(ptr(0));
    let mth;
    while (!(mth = classGetMethods(minionTemplClass, it)).isNull()) {
        const mn = cstr(methodGetName(mth));
        if (!mn || !TARGET_METHODS.has(mn)) continue;
        let fnPtr = null;
        try { fnPtr = mth.readPointer(); } catch(e) { continue; }
        if (!fnPtr || fnPtr.isNull()) continue;
        try {
            Interceptor.attach(fnPtr, {
                onEnter(args) {
                    const self = args[0];
                    if (!self || self.isNull()) return;
                    const key = self.toString();
                    if (!hookedTemplates.has(key)) {
                        hookedTemplates.set(key, {ptr: self});
                        lastTemplateMs = Date.now();
                    }
                }
            });
            hookCount++;
        } catch(e) {
            send({t:"log", m:`Hook failed for ${mn}: ${e}`});
        }
    }
    send({t:"log", m:`Hooked ${hookCount} MinionTemplate methods`});
}

// ─── Hook Ability methods for trigger mapping ─────────────────────────────────
function hookAbilityMethods(mod, abilityClass) {
    const classGetMethods = new NativeFunction(
        mod.findExportByName("il2cpp_class_get_methods"), "pointer", ["pointer","pointer"]);
    const methodGetName = new NativeFunction(
        mod.findExportByName("il2cpp_method_get_name"), "pointer", ["pointer"]);

    const HOOK_TARGETS = new Set([
        "SetTrigger", "SetAimAndTrigger", "SetAbout",
        "set_TriggerLimit", "set_TriggerLimitType", "SetTriggerLevel", "SetFinePrint",
        "SetCustomNote", "SkipLocalization",
        "SetAboutText", "SetDescription", "SetText",
    ]);
    const foundPtrs = {};
    const allMethodNames = [];
    const it = Memory.alloc(Process.pointerSize); it.writePointer(ptr(0));
    let mth;
    while (!(mth = classGetMethods(abilityClass, it)).isNull()) {
        const mn = cstr(methodGetName(mth));
        if (!mn) continue;
        allMethodNames.push(mn);
        if (HOOK_TARGETS.has(mn) && !foundPtrs[mn]) {
            try { foundPtrs[mn] = mth.readPointer(); } catch(e) {}
        }
    }
    send({t:"log", m:`Ability methods (${allMethodNames.length}): ${allMethodNames.join(", ")}`});
    const toHook = foundPtrs;

    // SetAbout(string locoKey)
    if (toHook["SetAbout"] && !toHook["SetAbout"].isNull()) {
        try {
            Interceptor.attach(toHook["SetAbout"], {
                onEnter(args) {
                    const s = readCsString(args[1]);
                    if (s) {
                        let name = s;
                        const parts = s.split('.');
                        if (parts.length >= 2 && parts[0] === 'Ability') name = parts[1];
                        hookNames.set(args[0].toString(), name);
                    }
                }
            });
            send({t:"log", m:"Hooked SetAbout"});
        } catch(e) { send({t:"log", m:"SetAbout hook failed: " + e}); }
    }

    // SetTrigger / SetAimAndTrigger — mark ability as having a trigger
    for (const label of ["SetTrigger", "SetAimAndTrigger"]) {
        const fnPtr = toHook[label];
        if (!fnPtr || fnPtr.isNull()) { send({t:"log", m:`${label}: not found`}); continue; }
        try {
            Interceptor.attach(fnPtr, {
                onEnter(args) {
                    const key = args[0].toString();
                    const existing = savedAbilities.get(key) || {};
                    existing.self = args[0];
                    savedAbilities.set(key, existing);
                }
            });
            send({t:"log", m:`Hooked ${label}`});
        } catch(e) { send({t:"log", m:`${label} hook failed: ${e}`}); }
    }

    // set_TriggerLimit property setter — the actual count
    if (toHook["set_TriggerLimit"] && !toHook["set_TriggerLimit"].isNull()) {
        try {
            Interceptor.attach(toHook["set_TriggerLimit"], {
                onEnter(args) {
                    const key = args[0].toString();
                    const existing = savedAbilities.get(key) || {self: args[0]};
                    try { existing.triggerLimit = args[1].toInt32(); } catch(e) {}
                    savedAbilities.set(key, existing);
                }
            });
            send({t:"log", m:"Hooked set_TriggerLimit"});
        } catch(e) { send({t:"log", m:"set_TriggerLimit hook failed: " + e}); }
    }

    // set_TriggerLimitType(self, int type) — 0=per turn, 1=per battle, 2=outside battle
    if (toHook["set_TriggerLimitType"] && !toHook["set_TriggerLimitType"].isNull()) {
        try {
            Interceptor.attach(toHook["set_TriggerLimitType"], {
                onEnter(args) {
                    const key = args[0].toString();
                    const existing = savedAbilities.get(key) || {self: args[0]};
                    try { existing.triggerLimitType = args[1].toInt32(); } catch(e) {}
                    savedAbilities.set(key, existing);
                }
            });
            send({t:"log", m:"Hooked set_TriggerLimitType"});
        } catch(e) { send({t:"log", m:"set_TriggerLimitType hook failed: " + e}); }
    }

    // SetTriggerLevel(self, int level) — e.g. tier 1 filter on Dragon
    if (toHook["SetTriggerLevel"] && !toHook["SetTriggerLevel"].isNull()) {
        try {
            Interceptor.attach(toHook["SetTriggerLevel"], {
                onEnter(args) {
                    const key = args[0].toString();
                    const existing = savedAbilities.get(key) || {self: args[0]};
                    try { existing.triggerLevel = args[1].toInt32(); } catch(e) {}
                    savedAbilities.set(key, existing);
                }
            });
            send({t:"log", m:"Hooked SetTriggerLevel"});
        } catch(e) { send({t:"log", m:"SetTriggerLevel hook failed: " + e}); }
    }

    // SetFinePrint(self, string locoKey) — explicit fine print override
    if (toHook["SetFinePrint"] && !toHook["SetFinePrint"].isNull()) {
        try {
            Interceptor.attach(toHook["SetFinePrint"], {
                onEnter(args) {
                    const key = args[0].toString();
                    const existing = savedAbilities.get(key) || {self: args[0]};
                    try { existing.finePrintKey = readCsString(args[1]); } catch(e) {}
                    savedAbilities.set(key, existing);
                }
            });
            send({t:"log", m:"Hooked SetFinePrint"});
        } catch(e) { send({t:"log", m:"SetFinePrint hook failed: " + e}); }
    }

    // SetCustomNote(self, string text) — hardcoded English fallback text for abilities
    // without localization keys (e.g. newly added pets whose loco entries aren't shipped yet)
    if (toHook["SetCustomNote"] && !toHook["SetCustomNote"].isNull()) {
        try {
            Interceptor.attach(toHook["SetCustomNote"], {
                onEnter(args) {
                    const key = args[0].toString();
                    const existing = savedAbilities.get(key) || {self: args[0]};
                    const note = readCsString(args[1]);
                    try { existing.customNote = note; } catch(e) {}
                    savedAbilities.set(key, existing);
                    send({t:"log", m:`SetCustomNote fired: key=${key} note=${note}`});
                }
            });
            send({t:"log", m:"Hooked SetCustomNote"});
        } catch(e) { send({t:"log", m:"SetCustomNote hook failed: " + e}); }
    } else {
        send({t:"log", m:"SetCustomNote: method not found in Ability class"});
    }

    // SkipLocalization() — marks ability as bypassing loco system entirely
    if (toHook["SkipLocalization"] && !toHook["SkipLocalization"].isNull()) {
        try {
            Interceptor.attach(toHook["SkipLocalization"], {
                onEnter(args) {
                    const key = args[0].toString();
                    const existing = savedAbilities.get(key) || {self: args[0]};
                    existing.skipLocalization = true;
                    savedAbilities.set(key, existing);
                    // read ability name from enum at offset 16 for logging
                    let nm = "(unknown)";
                    try {
                        const ei = args[0].add(16).readS32();
                        nm = String(ei);
                    } catch(e) {}
                    send({t:"log", m:`SkipLocalization fired: key=${key} enumInt=${nm}`});
                }
            });
            send({t:"log", m:"Hooked SkipLocalization"});
        } catch(e) { send({t:"log", m:"SkipLocalization hook failed: " + e}); }
    } else {
        send({t:"log", m:"SkipLocalization: method not found"});
    }
}

// ─── Main setup: find classes, hook everything ────────────────────────────────
function setupAfterInit(mod) {
    function nfn(name, ret, args) {
        const a = mod.findExportByName(name);
        if (!a) { send({t:"log", m:"Missing: " + name}); return null; }
        return new NativeFunction(a, ret, args);
    }

    const domainGet           = nfn("il2cpp_domain_get",            "pointer", []);
    const domainGetAssemblies = nfn("il2cpp_domain_get_assemblies", "pointer", ["pointer","pointer"]);
    const assemblyGetImage    = nfn("il2cpp_assembly_get_image",    "pointer", ["pointer"]);
    const imageGetName        = nfn("il2cpp_image_get_name",        "pointer", ["pointer"]);
    const imageGetClassCount  = nfn("il2cpp_image_get_class_count", "uint32",  ["pointer"]);
    const imageGetClass       = nfn("il2cpp_image_get_class",       "pointer", ["pointer","uint32"]);
    const classGetName        = nfn("il2cpp_class_get_name",        "pointer", ["pointer"]);
    const classGetFields      = nfn("il2cpp_class_get_fields",      "pointer", ["pointer","pointer"]);
    const fieldGetName        = nfn("il2cpp_field_get_name",        "pointer", ["pointer"]);
    const fieldStaticGetValue = nfn("il2cpp_field_static_get_value","void",    ["pointer","pointer"]);
    const classGetMethods     = nfn("il2cpp_class_get_methods",     "pointer", ["pointer","pointer"]);
    const methodGetName       = nfn("il2cpp_method_get_name",       "pointer", ["pointer"]);
    const runtimeInvoke       = nfn("il2cpp_runtime_invoke",        "pointer", ["pointer","pointer","pointer","pointer"]);
    const objectGetClass      = nfn("il2cpp_object_get_class",      "pointer", ["pointer"]);

    if (!domainGet) { send({t:"log", m:"Missing IL2CPP exports"}); return; }

    const domain   = domainGet();
    const sizePtr  = Memory.alloc(8); sizePtr.writeU64(0);
    const asmArray = domainGetAssemblies(domain, sizePtr);
    const asmCount = sizePtr.readU32();
    send({t:"log", m:`${asmCount} assemblies`});

    // Scan assemblies for needed classes
    let minionConstClass  = null;
    let minionTemplClass  = null;
    let minionEnumClass   = null;
    let spellConstClass   = null;
    let spellEnumClass    = null;
    let abilityClass      = null;
    let abilityEnumClass  = null;

    const WANT_CORE = new Set([
        "MinionConstants","MinionTemplate","MinionEnum",
        "SpellConstants","SpellEnum",
        "Ability","AbilityEnum",
    ]);

    for (let ai = 0; ai < asmCount; ai++) {
        const asm   = asmArray.add(ai * Process.pointerSize).readPointer();
        const img   = assemblyGetImage(asm);
        const iname = cstr(imageGetName(img)) || "";

        const isCore = iname.includes("SpacewoodCore2");
        const isCSharp = iname.includes("Assembly-CSharp");
        if (!isCore && !isCSharp) continue;

        const n = imageGetClassCount(img);
        for (let ci = 0; ci < n; ci++) {
            const klass = imageGetClass(img, ci);
            if (!klass || klass.isNull()) continue;
            const cname = cstr(classGetName(klass));
            if (!cname) continue;
            if (isCore && WANT_CORE.has(cname)) {
                if      (cname === "MinionConstants") minionConstClass = klass;
                else if (cname === "MinionTemplate")  minionTemplClass = klass;
                else if (cname === "MinionEnum")       minionEnumClass  = klass;
                else if (cname === "SpellConstants")   spellConstClass  = klass;
                else if (cname === "SpellEnum")        spellEnumClass   = klass;
                else if (cname === "Ability")          abilityClass     = klass;
                else if (cname === "AbilityEnum")      abilityEnumClass = klass;
            }
        }
    }

    send({t:"log", m:[
        `minionConst=${!!minionConstClass}`,
        `minionTempl=${!!minionTemplClass}`,
        `minionEnum=${!!minionEnumClass}`,
        `spellConst=${!!spellConstClass}`,
        `spellEnum=${!!spellEnumClass}`,
        `ability=${!!abilityClass}`,
        `abilityEnum=${!!abilityEnumClass}`,
    ].join(" ")});

    // Find SpellConstants fields/methods
    let spellsField    = null;
    let createSpellsMth = null;

    if (spellConstClass) {
        {
            const it = Memory.alloc(Process.pointerSize); it.writePointer(ptr(0));
            let fld;
            while (!(fld = classGetFields(spellConstClass, it)).isNull()) {
                if (cstr(fieldGetName(fld)) === "Spells") { spellsField = fld; break; }
            }
        }
        {
            const it = Memory.alloc(Process.pointerSize); it.writePointer(ptr(0));
            let mth;
            while (!(mth = classGetMethods(spellConstClass, it)).isNull()) {
                if (cstr(methodGetName(mth)) === "CreateSpells") { createSpellsMth = mth; break; }
            }
        }
        send({t:"log", m:`spellsField=${!!spellsField} createSpellsMth=${!!createSpellsMth}`});
    }

    // Find MinionConstants static dict fields — scan all three candidates, use highest-count at extraction time
    const minionDictFields = {};
    if (minionConstClass) {
        const SCAN_FIELDS = new Set(["Minions", "ActiveMinions", "ReleasedMinions"]);
        const it = Memory.alloc(Process.pointerSize); it.writePointer(ptr(0));
        let fld;
        const allFields = [];
        while (!(fld = classGetFields(minionConstClass, it)).isNull()) {
            const fn_ = cstr(fieldGetName(fld));
            if (fn_) { allFields.push(fn_); if (SCAN_FIELDS.has(fn_)) minionDictFields[fn_] = fld; }
        }
        send({t:"log", m:`MinionConstants fields: [${allFields.join(", ")}]`});
        send({t:"log", m:`minionDictFields found: [${Object.keys(minionDictFields).join(", ")}]`});
    }

    g = {
        classGetFields, fieldGetName, fieldStaticGetValue,
        minionEnumClass,
        spellEnumClass, spellConstClass,
        createSpellsMth, runtimeInvoke,
        spellsField,
        objectGetClass, classGetName,
        abilityEnumClass,
        minionDictFields,
    };

    // Hook MinionTemplate methods (to capture template pointers)
    if (minionTemplClass) hookMinionTemplate(mod, minionTemplClass);

    if (abilityClass) hookAbilityMethods(mod, abilityClass);

    // Hook MinionConstants.EnsureMinions — fires on game thread
    if (minionConstClass) {
        const it = Memory.alloc(Process.pointerSize); it.writePointer(ptr(0));
        let mth;
        while (!(mth = classGetMethods(minionConstClass, it)).isNull()) {
            if (cstr(methodGetName(mth)) !== "EnsureMinions") continue;
            let fnPtr = null;
            try { fnPtr = mth.readPointer(); } catch(e) { break; }
            if (!fnPtr || fnPtr.isNull()) break;
            try {
                Interceptor.attach(fnPtr, {
                    onLeave(_retval) {
                        if (gameReady) return;
                        gameReady = true;
                        lastTemplateMs = Date.now();
                        send({t:"log", m:`EnsureMinions fired — templates=${hookedTemplates.size}. Open pack edit screen now.`});
                    }
                });
                send({t:"log", m:"Hooked EnsureMinions"});
            } catch(e) {
                send({t:"log", m:"EnsureMinions hook failed: " + e});
            }
            break;
        }
    }

    // Debounce extraction: wait until templates stop arriving for 5s after EnsureMinions
    const STABLE_MS = 5000;
    const extractPoll = setInterval(function() {
        if (!gameReady) return;
        if (Date.now() - lastTemplateMs < STABLE_MS) return;
        clearInterval(extractPoll);

        if (statsFoodSent) return;
        statsFoodSent = true;
        send({t:"log", m:`Templates stable for ${STABLE_MS}ms — extracting (total=${hookedTemplates.size})`});

        let sfResult = {pets: {}, foods: {}};
        try { sfResult = extractStatsFoods(); } catch(e) {
            send({t:"log", m:"extractStatsFoods error: " + e});
        }
        send({t:"stats_food", pets: sfResult.pets, foods: sfResult.foods});

        setTimeout(function() {
            if (triggersSent) return;
            triggersSent = true;
            let trigData = [];
            try { trigData = dumpTriggers(); } catch(e) {
                send({t:"log", m:"dumpTriggers error: " + e});
            }
            send({t:"log", m:`Triggers: ${trigData.length} entries`});
            send({t:"triggers", data: trigData});
            send({t:"done"});
        }, 5000);
    }, 500);

    send({t:"ready"});
}

// ─── Poll for GameAssembly.so ─────────────────────────────────────────────────
const pollTimer = setInterval(function() {
    const mod = Process.findModuleByName("GameAssembly.so");
    if (!mod) return;
    clearInterval(pollTimer);
    send({t:"log", m:`GameAssembly.so @ ${mod.base}`});
    try { setupAfterInit(mod); }
    catch(e) { send({t:"log", m:"Setup error: " + e + "\n" + (e.stack||"")}); }
}, 100);

import os
import subprocess
import threading
import time

import frida

from .constants import GAME_BIN, GAME_DIR

_HOOKS_JS_PATH = os.path.join(os.path.dirname(__file__), "hooks.js")


def _load_hooks_js() -> str:
    with open(_HOOKS_JS_PATH, "r", encoding="utf-8") as f:
        return f.read()


def run_frida_session() -> dict:
    """
    Spawn the game once, hook everything, auto-dump when ready.
    Returns {"pets_raw": {...}, "foods_raw": {...}, "triggers_raw": [...]}.
    """

    frida_js = _load_hooks_js()

    results = {"pets_raw": {}, "foods_raw": {}, "triggers_raw": [], "ability_texts": {}}
    done_event = threading.Event()
    script_ref_holder = [None]

    def on_message(msg, _data):
        if msg["type"] == "send":
            p = msg["payload"]
            t = p.get("t", "")
            if t == "log":
                print(f"  [JS] {p['m']}", flush=True)
            elif t == "stats_food":
                results["pets_raw"] = p.get("pets", {})
                results["foods_raw"] = p.get("foods", {})
                print(
                    f"  [*] stats_food received: {len(results['pets_raw'])} pets, "
                    f"{len(results['foods_raw'])} foods",
                    flush=True,
                )
            elif t == "triggers":
                results["triggers_raw"] = p.get("data", [])
                print(f"  [*] triggers received: {len(results['triggers_raw'])} entries", flush=True)
            elif t == "ability_texts":
                results["ability_texts"] = p.get("data", {})
                print(f"  [*] ability_texts received: {len(results['ability_texts'])} abilities", flush=True)
            elif t == "ready":
                print(
                    "  [*] All hooks installed — click 'Pets' then open pack edit screen",
                    flush=True,
                )
            elif t == "done":
                print("  [*] JS signalled done", flush=True)
                done_event.set()
        elif msg["type"] == "error":
            print(f"  [ERR] {msg.get('description', '?')}", flush=True)

    existing = subprocess.run(
        ["pgrep", "-f", "superautopets.x86_64"], capture_output=True, text=True
    ).stdout.strip()
    if existing:
        print(f"[2] Killing existing SAP instances: {existing.replace(chr(10), ' ')}")
        subprocess.run(["pkill", "-f", "superautopets.x86_64"], capture_output=True)
        time.sleep(2)

    env = {**os.environ, "DISPLAY": ":0"}
    print("[2] Spawning SAP game...")
    pid = frida.spawn([GAME_BIN], cwd=GAME_DIR, env=env)
    print(f"[2] PID {pid}")

    sess = frida.attach(pid)
    scr = sess.create_script(frida_js)
    scr.on("message", on_message)
    scr.load()
    script_ref_holder[0] = scr
    frida.resume(pid)

    print("[2] Game launched — navigate: Pets → pack edit screen")
    print("[2] Stats fire ~5s after templates load; triggers + ability texts immediately after")
    print("[2] Waiting up to 240s for 'done' signal...")
    done_event.wait(timeout=240)
    if not done_event.is_set():
        print("[2] WARNING: timed out waiting for done signal")

    try:
        subprocess.run(["kill", str(pid)], capture_output=True)
        print(f"[2] Game process {pid} killed")
    except Exception as e:
        print(f"[2] Could not kill game: {e}")

    return results

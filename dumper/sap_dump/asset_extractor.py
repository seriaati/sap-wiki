import os
import shutil


def copy_assets(texture2d_dir: str, keys: list[str], out_assets_dir: str) -> dict[str, str]:
    """
    For each key, copy {key}_2x.png (or {key}.png) from texture2d_dir to out_assets_dir.
    Falls back to case-insensitive filename match when exact match fails.
    Returns {key: filename} for keys where an image was found.
    """
    os.makedirs(out_assets_dir, exist_ok=True)

    # Build lowercase index of available files for case-insensitive fallback
    available = {f.lower(): f for f in os.listdir(texture2d_dir) if f.endswith(".png")}

    result = {}
    for key in keys:
        src = None
        for candidate in (f"{key}_2x.png", f"{key}.png"):
            exact = os.path.join(texture2d_dir, candidate)
            if os.path.exists(exact):
                src = exact
                break
            # Case-insensitive fallback
            match = available.get(candidate.lower())
            if match:
                src = os.path.join(texture2d_dir, match)
                break
        if src is None:
            continue
        filename = os.path.basename(src)
        dst = os.path.join(out_assets_dir, filename)
        if not os.path.exists(dst):
            shutil.copy2(src, dst)
        result[key] = filename
    return result

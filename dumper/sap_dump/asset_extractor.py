import os
import shutil


def copy_assets(texture2d_dir: str, keys: list[str], out_assets_dir: str) -> dict[str, dict]:
    """
    For each key, find new skin ({key}_2x_0.png) and legacy skin ({key}_2x.png).
    Copies all found images to out_assets_dir.
    Returns {key: {"image": filename, "imageLegacy": filename_or_empty}}.
    If only one skin exists (no redesign), it becomes "image" with empty "imageLegacy".
    """
    os.makedirs(out_assets_dir, exist_ok=True)

    available = {f.lower(): f for f in os.listdir(texture2d_dir) if f.endswith(".png")}

    def _find_and_copy(candidate: str) -> str:
        exact = os.path.join(texture2d_dir, candidate)
        if os.path.exists(exact):
            src = exact
        else:
            match = available.get(candidate.lower())
            if not match:
                return ""
            src = os.path.join(texture2d_dir, match)
        filename = os.path.basename(src)
        dst = os.path.join(out_assets_dir, filename)
        if not os.path.exists(dst):
            shutil.copy2(src, dst)
        return filename

    result = {}
    for key in keys:
        new_skin = ""
        legacy_skin = ""

        for candidate in (f"{key}_2x_0.png", f"{key}_0.png"):
            found = _find_and_copy(candidate)
            if found:
                new_skin = found
                break

        for candidate in (f"{key}_2x.png", f"{key}.png"):
            found = _find_and_copy(candidate)
            if found:
                legacy_skin = found
                break

        if not new_skin and not legacy_skin:
            continue

        if new_skin:
            result[key] = {"image": new_skin, "imageLegacy": legacy_skin}
        else:
            result[key] = {"image": legacy_skin, "imageLegacy": ""}

    return result

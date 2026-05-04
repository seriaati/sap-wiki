import os
import re
import shutil

from .constants import EXPORTED_ASSETS_RELATIVE


SPRITE_ASSET_RELATIVE = os.path.join(
    EXPORTED_ASSETS_RELATIVE, "Resources", "sprites", "DefaultSpriteAsset.asset"
)
TEXTMAP_RELATIVE = os.path.join(EXPORTED_ASSETS_RELATIVE, "Texture2D", "TextMap.png")

DICE_SPRITE_DIR_RELATIVE = os.path.join(EXPORTED_ASSETS_RELATIVE, "Sprite")
DICE_TEXTURE_RELATIVE = os.path.join(EXPORTED_ASSETS_RELATIVE, "Texture2D", "Dice_0.png")


def _parse_sprite_asset(asset_path: str) -> dict[str, dict]:
    """
    Parse DefaultSpriteAsset.asset and return {name: {x, y, w, h}} in CSS coords
    (top-left origin). Unity uses bottom-left, so y is flipped using image height.
    """
    with open(asset_path, encoding="utf-8") as f:
        text = f.read()

    # Parse character table: name → glyphIndex
    char_blocks = re.findall(
        r"m_GlyphIndex:\s*(\d+).*?m_Name:\s*(\S+)", text, re.DOTALL
    )
    glyph_to_name: dict[int, str] = {}
    for glyph_idx, name in char_blocks:
        idx = int(glyph_idx)
        if idx not in glyph_to_name:
            glyph_to_name[idx] = name

    # Parse glyph table: index → rect
    glyph_blocks = re.findall(
        r"m_Index:\s*(\d+).*?m_GlyphRect:.*?m_X:\s*(\d+).*?m_Y:\s*(\d+).*?m_Width:\s*(\d+).*?m_Height:\s*(\d+)",
        text,
        re.DOTALL,
    )
    glyph_rects: dict[int, tuple] = {}
    for block in glyph_blocks:
        idx, x, y, w, h = (int(v) for v in block)
        if idx not in glyph_rects:
            glyph_rects[idx] = (x, y, w, h)

    # Image height needed to flip Y (Unity bottom-left → CSS top-left)
    from PIL import Image
    img_path = os.path.join(os.path.dirname(asset_path), "..", "..", "Texture2D", "TextMap.png")
    _, img_height = Image.open(img_path).size

    sprites: dict[str, dict] = {}
    for idx, name in glyph_to_name.items():
        if idx not in glyph_rects:
            continue
        x, unity_y, w, h = glyph_rects[idx]
        css_y = img_height - unity_y - h
        sprites[name] = {"x": x, "y": css_y, "w": w, "h": h}

    return sprites


def extract_icon_map(sap_root: str, out_assets_dir: str, out_dir: str) -> str:
    """
    Copy TextMap.png to out_assets_dir, parse sprite positions, write icon_map.json.
    Returns path to icon_map.json.
    """
    import json

    asset_path = os.path.join(sap_root, SPRITE_ASSET_RELATIVE)
    textmap_src = os.path.join(sap_root, TEXTMAP_RELATIVE)

    os.makedirs(out_assets_dir, exist_ok=True)
    textmap_dst = os.path.join(out_assets_dir, "TextMap.png")
    if not os.path.exists(textmap_dst):
        shutil.copy2(textmap_src, textmap_dst)

    from PIL import Image
    img_w, img_h = Image.open(textmap_src).size

    sprites = _parse_sprite_asset(asset_path)

    icon_map = {
        "image": "TextMap.png",
        "imageWidth": img_w,
        "imageHeight": img_h,
        "sprites": sprites,
    }

    out_path = os.path.join(out_dir, "icon_map.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(icon_map, f, indent=2, ensure_ascii=False)

    return out_path


def _parse_dice_sprites(sprite_dir: str, img_height: int) -> dict[str, dict]:
    """
    Parse Dice_N.asset files in sprite_dir.
    Returns {name: {x, y, w, h}} in CSS coords (top-left origin).
    """
    sprites: dict[str, dict] = {}
    for fname in sorted(os.listdir(sprite_dir)):
        if not (fname.startswith("Dice_") and fname.endswith(".asset")):
            continue
        with open(os.path.join(sprite_dir, fname), encoding="utf-8") as f:
            text = f.read()
        name_m = re.search(r"m_Name:\s*(\S+)", text)
        rect_m = re.search(
            r"m_Rect:.*?x:\s*([\d.E+\-]+).*?y:\s*([\d.E+\-]+).*?width:\s*([\d.E+\-]+).*?height:\s*([\d.E+\-]+)",
            text,
            re.DOTALL,
        )
        if not name_m or not rect_m:
            continue
        name = name_m.group(1)
        x, unity_y, w, h = (float(v) for v in rect_m.groups())
        css_y = img_height - unity_y - h
        sprites[name] = {"x": round(x), "y": round(css_y), "w": round(w), "h": round(h)}
    return sprites


def extract_dice_map(sap_root: str, out_assets_dir: str, out_dir: str) -> str:
    """
    Copy Dice_0.png to out_assets_dir, parse per-sprite rects, write dice_map.json.
    Returns path to dice_map.json.
    """
    import json

    texture_src = os.path.join(sap_root, DICE_TEXTURE_RELATIVE)
    sprite_dir = os.path.join(sap_root, DICE_SPRITE_DIR_RELATIVE)

    os.makedirs(out_assets_dir, exist_ok=True)
    texture_dst = os.path.join(out_assets_dir, "Dice_0.png")
    if not os.path.exists(texture_dst):
        shutil.copy2(texture_src, texture_dst)

    from PIL import Image
    img_w, img_h = Image.open(texture_src).size

    sprites = _parse_dice_sprites(sprite_dir, img_h)

    dice_map = {
        "image": "Dice_0.png",
        "imageWidth": img_w,
        "imageHeight": img_h,
        "sprites": sprites,
    }

    out_path = os.path.join(out_dir, "dice_map.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(dice_map, f, indent=2, ensure_ascii=False)

    return out_path

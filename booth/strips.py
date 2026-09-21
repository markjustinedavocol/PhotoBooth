"""Pure-Pillow photo strip composition. Nothing here touches the database."""
import math
import random
from functools import lru_cache

from django.conf import settings
from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps

CELL_W, CELL_H = 480, 360  # one partner's photo (4:3)
SEAM = 6  # gap between the two halves of a pair
PAIR_W = CELL_W * 2 + SEAM
HEART = object()  # marker for draw_segments

THEMES = {
    "classic": {
        "bg": (255, 255, 255), "ink": (43, 32, 36), "muted": (122, 106, 111),
        "accent": (184, 59, 94), "seam": (255, 255, 255),
        "pad": 48, "side": 48, "gap": 24, "footer": 250,
    },
    "polaroid": {
        "bg": (240, 234, 224), "ink": (62, 52, 46), "muted": (128, 116, 104),
        "accent": (184, 59, 94), "seam": (255, 255, 255), "card": (255, 255, 255),
        "pad": 56, "side": 56, "gap": 40, "footer": 260,
    },
    "film": {
        "bg": (22, 20, 20), "ink": (245, 238, 226), "muted": (172, 162, 152),
        "accent": (236, 112, 142), "seam": (22, 20, 20), "sprockets": (238, 230, 218),
        "pad": 56, "side": 96, "gap": 28, "footer": 250,
    },
    "pastel": {
        "bg": (253, 228, 236), "ink": (122, 52, 78), "muted": (168, 108, 132),
        "accent": (232, 106, 137), "seam": (253, 228, 236),
        "confetti": [(255, 255, 255), (246, 178, 199), (210, 194, 242), (255, 214, 170)],
        "pad": 56, "side": 64, "gap": 28, "footer": 260,
    },
}


# ---------------------------------------------------------------- fonts

FONT_CANDIDATES = {
    "script": [
        settings.BASE_DIR / "static" / "fonts" / "Caveat.ttf",
        "segoepr.ttf", "Inkfree.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ],
    "sans": [
        "segoeui.ttf", "arial.ttf", "Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "DejaVuSans.ttf",
    ],
}


@lru_cache(maxsize=64)
def load_font(kind, size):
    for candidate in FONT_CANDIDATES[kind]:
        try:
            font = ImageFont.truetype(str(candidate), size)
        except OSError:
            continue
        if kind == "script":
            try:
                font.set_variation_by_name("Bold")
            except (OSError, ValueError, AttributeError):
                pass
        return font
    return ImageFont.load_default(size=size)


# ---------------------------------------------------------------- drawing helpers

def draw_heart(draw, cx, cy, size, fill):
    """Parametric heart centred on (cx, cy), `size` pixels wide."""
    scale = size / 34
    points = []
    for i in range(72):
        t = 2 * math.pi * i / 72
        x = 16 * math.sin(t) ** 3
        y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        points.append((cx + x * scale, cy - (y + 2.5) * scale))
    draw.polygon(points, fill=fill)


def draw_segments(draw, cx, cy, segments, font, color, heart_color):
    """Draw text pieces and HEART markers as one centred line, vertically centred on cy."""
    heart_size = font.size * 0.8
    spacing = font.size * 0.35
    widths = [
        heart_size + 2 * spacing if seg is HEART else draw.textlength(seg, font=font)
        for seg in segments
    ]
    x = cx - sum(widths) / 2
    for seg, width in zip(segments, widths):
        if seg is HEART:
            draw_heart(draw, x + width / 2, cy, heart_size, heart_color)
        else:
            draw.text((x, cy), seg, font=font, fill=color, anchor="lm")
        x += width


def fit_font(draw, text, kind, size, max_width, min_size=24):
    font = load_font(kind, size)
    while size > min_size and draw.textlength(text, font=font) > max_width:
        size -= 4
        font = load_font(kind, size)
    return font


def apply_filter(img, name):
    if name == "bw":
        return ImageOps.autocontrast(ImageOps.grayscale(img), cutoff=1).convert("RGB")
    if name == "sepia":
        gray = ImageOps.grayscale(img)
        return ImageOps.colorize(gray, black=(38, 24, 12), white=(255, 242, 214), mid=(166, 124, 84))
    if name == "warm":
        r, g, b = img.split()
        r = r.point(lambda v: min(255, int(v * 1.08) + 6))
        b = b.point(lambda v: int(v * 0.88))
        return ImageEnhance.Color(Image.merge("RGB", (r, g, b))).enhance(1.15)
    return img


def placeholder_cell(theme):
    cell = Image.new("RGB", (CELL_W, CELL_H), tuple(max(0, c - 18) for c in theme["bg"]))
    draw = ImageDraw.Draw(cell)
    draw_heart(draw, CELL_W / 2, CELL_H / 2 - 18, 56, theme["muted"])
    draw.text(
        (CELL_W / 2, CELL_H / 2 + 34), "photo didn't arrive",
        font=load_font("sans", 22), fill=theme["muted"], anchor="mm",
    )
    return cell


def prepare_cell(img, photo_filter, theme):
    if img is None:
        return placeholder_cell(theme)
    img = ImageOps.exif_transpose(img).convert("RGB")
    img = ImageOps.fit(img, (CELL_W, CELL_H), method=Image.Resampling.LANCZOS)
    return apply_filter(img, photo_filter)


def _draw_sprockets(draw, width, height, theme):
    hole_w, hole_h, step = 34, 22, 52
    for y in range(18, height - hole_h, step):
        for x in (31, width - 31 - hole_w):
            draw.rounded_rectangle([x, y, x + hole_w, y + hole_h], radius=5, fill=theme["sprockets"])


def _draw_confetti(draw, width, height, theme, rng):
    footer_top = height - theme["footer"]
    placed = 0
    attempts = 0
    while placed < 46 and attempts < 2000:
        attempts += 1
        x, y = rng.uniform(8, width - 8), rng.uniform(8, height - 8)
        # keep hearts in the margins and out of the footer text
        in_margin = x < theme["side"] - 10 or x > width - theme["side"] + 10 or y < theme["pad"] - 10
        in_footer_corner = y > footer_top and (x < width * 0.12 or x > width * 0.88)
        if not (in_margin or in_footer_corner):
            continue
        draw_heart(draw, x, y, rng.uniform(14, 30), rng.choice(theme["confetti"]))
        placed += 1


def _draw_footer(draw, width, height, theme, caption, names, date_text, clocks):
    top = height - theme["footer"]
    cx = width / 2
    max_text = width - 2 * theme["side"]
    scale = 1.0 if width < 1400 else 1.35

    if theme is THEMES["classic"]:
        draw.line([(theme["side"], top + 8), (width - theme["side"], top + 8)], fill=theme["accent"], width=2)

    title = caption or f"{names[0]} & {names[1]}"
    title_font = fit_font(draw, title, "script", int(76 * scale), max_text)
    draw.text((cx, top + 70), title, font=title_font, fill=theme["ink"], anchor="mm")

    meta_font = load_font("sans", int(28 * scale))
    segments = [names[0], HEART, names[1]]
    if date_text:
        segments.append(f"   ·   {date_text}")
    draw_segments(draw, cx, top + 140 * min(scale, 1.15), segments, meta_font, theme["muted"], theme["accent"])

    if clocks:
        clock_font = load_font("sans", int(24 * scale))
        (city_a, time_a), (city_b, time_b) = clocks
        draw_segments(
            draw, cx, top + 188 * min(scale, 1.15),
            [f"{city_a} {time_a}", HEART, f"{city_b} {time_b}"],
            clock_font, theme["muted"], theme["accent"],
        )


# ---------------------------------------------------------------- public API

def compose(
    pairs,
    *,
    theme="classic",
    photo_filter="none",
    layout="strip",
    caption="",
    names=("", ""),
    date_text="",
    clocks=None,
    seed=0,
):
    """Build a strip image.

    pairs: list of (left_image, right_image) PIL images (either may be None).
    clocks: optional ((city_a, "9:14 PM"), (city_b, "9:14 AM")).
    """
    t = THEMES.get(theme, THEMES["classic"])
    cols = 2 if layout == "grid" else 1
    rows = max(1, math.ceil(len(pairs) / cols))
    border = 14 if "card" in t else 0
    unit_w, unit_h = PAIR_W + 2 * border, CELL_H + 2 * border

    width = 2 * t["side"] + cols * unit_w + (cols - 1) * t["gap"]
    height = t["pad"] + rows * unit_h + (rows - 1) * t["gap"] + t["footer"]
    canvas = Image.new("RGB", (width, height), t["bg"])
    draw = ImageDraw.Draw(canvas)

    if "sprockets" in t:
        _draw_sprockets(draw, width, height, t)
    if "confetti" in t:
        _draw_confetti(draw, width, height, t, random.Random(seed))

    for i, (left, right) in enumerate(pairs):
        row, col = divmod(i, cols)
        x = t["side"] + col * (unit_w + t["gap"])
        y = t["pad"] + row * (unit_h + t["gap"])
        if border:
            shade = tuple(max(0, c - 26) for c in t["bg"])
            draw.rectangle([x + 5, y + 7, x + unit_w + 5, y + unit_h + 7], fill=shade)
            draw.rectangle([x, y, x + unit_w - 1, y + unit_h - 1], fill=t["card"])
        px, py = x + border, y + border
        draw.rectangle([px, py, px + PAIR_W - 1, py + CELL_H - 1], fill=t["seam"])
        canvas.paste(prepare_cell(left, photo_filter, t), (px, py))
        canvas.paste(prepare_cell(right, photo_filter, t), (px + CELL_W + SEAM, py))
        # a little heart stitching the two halves together
        hx, hy = px + CELL_W + SEAM / 2, py + CELL_H - 30
        draw_heart(draw, hx, hy, 42, (255, 255, 255))
        draw_heart(draw, hx, hy, 30, t["accent"])

    _draw_footer(draw, width, height, t, caption, names, date_text, clocks)
    return canvas

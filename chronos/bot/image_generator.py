import io
import logging
import os
import urllib.request

from PIL import Image, ImageDraw, ImageFont

from .messaging import cf_rating_bands

logger = logging.getLogger(__name__)

# Cache fonts in the workspace data directory
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FONTS_DIR = os.path.join(BASE_DIR, "data", "fonts")

# Inter is distributed as a single variable font; weights are selected at load time.
FONTS = {
    "Inter.ttf": "https://raw.githubusercontent.com/google/fonts/main/ofl/inter/Inter%5Bopsz%2Cwght%5D.ttf",
}

# Legacy Roboto files are kept as a fallback if the Inter download fails.
LEGACY_FONT_FILES = {
    "regular": "Roboto-Regular.ttf",
    "medium": "Roboto-Medium.ttf",
    "bold": "Roboto-Bold.ttf",
}

LEETCODE_LOGO_URL = "https://upload.wikimedia.org/wikipedia/commons/8/8e/LeetCode_Logo_1.png"

# ---------------------------------------------------------------------------
# Design system
# ---------------------------------------------------------------------------
CARD_W = 1520
SOLVE_CARD_H = 620
SUMMARY_CARD_H = 740
CANVAS_MARGIN = 40                # Canvas padding around the card on every side
RADIUS = 48
BORDER_W = 6

CARD_BG = (13, 17, 23, 255)       # Deep slate-gray/dark blue background
BOX_BG = (22, 27, 34, 255)        # Slightly lighter slate box background
DIVIDER = (48, 54, 61, 255)
CANVAS_BG = (8, 11, 16)

TEXT_PRIMARY = (255, 255, 255, 255)
TEXT_SECONDARY = (139, 148, 158, 255)
TEXT_MUTED = (110, 118, 129, 255)

GREEN = (34, 197, 94)
YELLOW = (234, 179, 8)
RED = (239, 68, 68)

LC_ORANGE = (255, 161, 22)
CF_BLUE = (59, 130, 246)

FONT_WEIGHTS = {"regular": 400, "medium": 500, "bold": 700}

# Characters that Inter/Roboto cannot render are mapped to ASCII equivalents
# or stripped to avoid tofu boxes in problem titles.
_SYMBOL_MAP = {
    "√": "sqrt", "≤": "<=", "≥": ">=", "≠": "!=", "×": "x", "÷": "/",
    "±": "+/-", "—": "-", "–": "-", "’": "'", "‘": "'", "“": '"', "”": '"',
    "…": "...", "°": " deg ", "∑": "sum", "π": "pi", "∞": "inf",
}


def ensure_assets() -> None:
    """Downloads and caches necessary fonts and assets if not already present."""
    os.makedirs(FONTS_DIR, exist_ok=True)
    for name, url in FONTS.items():
        path = os.path.join(FONTS_DIR, name)
        if not os.path.exists(path):
            logger.info(f"Downloading font {name}...")
            try:
                # Add User-Agent header to avoid potential blocks
                req = urllib.request.Request(
                    url,
                    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
                )
                with urllib.request.urlopen(req) as response, open(path, 'wb') as out_file:
                    out_file.write(response.read())
                logger.info(f"Successfully downloaded {name}")
            except Exception as e:
                logger.error(f"Failed to download font {name} from {url}: {e}")

    # Download LeetCode logo
    logo_dir = os.path.join(BASE_DIR, "data")
    os.makedirs(logo_dir, exist_ok=True)
    logo_path = os.path.join(logo_dir, "leetcode.png")
    if not os.path.exists(logo_path):
        logger.info("Downloading LeetCode logo...")
        try:
            req = urllib.request.Request(
                LEETCODE_LOGO_URL,
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            )
            with urllib.request.urlopen(req) as response, open(logo_path, 'wb') as out_file:
                out_file.write(response.read())
            logger.info("Successfully downloaded LeetCode logo")
        except Exception as e:
            logger.error(f"Failed to download LeetCode logo from {LEETCODE_LOGO_URL}: {e}")


_font_cache = {}


def _load_font(size: int, weight: str = "regular"):
    """Loads Inter at the given size/weight with graceful fallbacks.

    Falls back to legacy Roboto files (if present) and finally to PIL's
    default bitmap font, so card generation never crashes on font issues.
    """
    key = (size, weight)
    if key in _font_cache:
        return _font_cache[key]

    font = None
    inter_path = os.path.join(FONTS_DIR, "Inter.ttf")
    try:
        font = ImageFont.truetype(inter_path, size)
        try:
            font.set_variation_by_axes([FONT_WEIGHTS.get(weight, 400)])
        except Exception:
            pass  # Not a variable font (e.g. unexpected file); default instance is fine
    except Exception:
        legacy = LEGACY_FONT_FILES.get(weight, LEGACY_FONT_FILES["regular"])
        try:
            font = ImageFont.truetype(os.path.join(FONTS_DIR, legacy), size)
        except Exception:
            logger.warning(f"Falling back to default bitmap font (size={size}, weight={weight})")
            font = ImageFont.load_default()

    _font_cache[key] = font
    return font


def create_gradient_fast(width: int, height: int, color1: tuple, color2: tuple) -> Image.Image:
    """Creates a smooth diagonal linear gradient by scaling a 2x2 grid."""
    img = Image.new("RGB", (2, 2))
    img.putpixel((0, 0), color1)
    img.putpixel((1, 1), color2)

    avg_color = (
        (color1[0] + color2[0]) // 2,
        (color1[1] + color2[1]) // 2,
        (color1[2] + color2[2]) // 2
    )
    img.putpixel((0, 1), avg_color)
    img.putpixel((1, 0), avg_color)

    return img.resize((width, height), Image.Resampling.BILINEAR).convert("RGBA")


def clean_text(text: str) -> str:
    """Sanitizes text for Inter: maps unsupported symbols to ASCII, strips the rest."""
    if not text:
        return ""
    out = []
    for c in str(text):
        if ord(c) < 0x2000:
            out.append(c)  # Latin, Greek, Cyrillic, common punctuation — Inter covers these
        elif c in _SYMBOL_MAP:
            out.append(_SYMBOL_MAP[c])
        # Anything else (emojis, math symbols, CJK) is dropped
    return "".join(out)


def cf_tier_color(rating) -> tuple | None:
    """Returns the authentic Codeforces rank color for a problem/user rating."""
    try:
        r = int(rating)
    except (TypeError, ValueError):
        return None
    if r < 1200:
        return (136, 136, 136)   # Newbie — gray
    if r < 1400:
        return (34, 197, 94)     # Pupil — green
    if r < 1600:
        return (3, 168, 158)     # Specialist — cyan
    if r < 1900:
        return (59, 130, 246)    # Expert — blue
    if r < 2100:
        return (192, 38, 211)    # Candidate Master — violet
    if r < 2400:
        return (249, 115, 22)    # Master / International Master — orange
    return (239, 68, 68)         # Grandmaster and above — red


def _create_card(card_w: int, card_h: int, grad_color1: tuple, grad_color2: tuple) -> Image.Image:
    """Builds the rounded card with a gradient border on a transparent canvas."""
    card = Image.new("RGBA", (card_w, card_h), (0, 0, 0, 0))
    gradient_img = create_gradient_fast(card_w, card_h, grad_color1, grad_color2)

    border_mask = Image.new("L", (card_w, card_h), 0)
    draw_bm = ImageDraw.Draw(border_mask)
    draw_bm.rounded_rectangle((0, 0, card_w, card_h), radius=RADIUS, fill=255)
    card.paste(gradient_img, (0, 0), mask=border_mask)

    inner_w = card_w - 2 * BORDER_W
    inner_h = card_h - 2 * BORDER_W
    inner_bg = Image.new("RGBA", (inner_w, inner_h), CARD_BG)
    inner_mask = Image.new("L", (inner_w, inner_h), 0)
    draw_im = ImageDraw.Draw(inner_mask)
    draw_im.rounded_rectangle((0, 0, inner_w, inner_h), radius=RADIUS - BORDER_W, fill=255)
    card.paste(inner_bg, (BORDER_W, BORDER_W), mask=inner_mask)

    return card


def _render_card(card: Image.Image) -> bytes:
    """Pastes the card onto the final canvas and returns PNG bytes at full 2x resolution."""
    canvas_w = card.width + 2 * CANVAS_MARGIN
    canvas_h = card.height + 2 * CANVAS_MARGIN
    canvas = Image.new("RGB", (canvas_w, canvas_h), CANVAS_BG)
    canvas.paste(card, (CANVAS_MARGIN, CANVAS_MARGIN), mask=card)
    img_byte_arr = io.BytesIO()
    canvas.save(img_byte_arr, format='PNG')
    return img_byte_arr.getvalue()


def _fit_text(draw: ImageDraw.ImageDraw, text: str, weight: str, start_size: int,
              min_size: int, max_width: int) -> tuple:
    """Shrinks (then truncates) text until it fits max_width. Returns (font, text)."""
    size = start_size
    font = _load_font(size, weight)
    while draw.textlength(text, font=font) > max_width and size > min_size:
        size -= 4
        font = _load_font(size, weight)

    if draw.textlength(text, font=font) > max_width:
        while text and draw.textlength(text + "...", font=font) > max_width:
            text = text[:-1]
        text = text + "..."
    return font, text


def _draw_tag_chips(draw: ImageDraw.ImageDraw, x: int, y: int, tags: list, max_width: int) -> None:
    """Draws up to 3 small rounded chips (e.g. Codeforces problem tags)."""
    chip_font = _load_font(24, "medium")
    chip_h = 44
    cx = x
    for tag in tags[:3]:
        text = clean_text(str(tag))
        if not text:
            continue
        text_w = draw.textlength(text, font=chip_font)
        chip_w = int(text_w) + 36
        if cx + chip_w > x + max_width:
            break
        draw.rounded_rectangle((cx, y, cx + chip_w, y + chip_h), radius=12,
                               fill=BOX_BG, outline=DIVIDER, width=2)
        draw.text((cx + chip_w // 2, y + chip_h // 2), text, fill=TEXT_SECONDARY,
                  font=chip_font, anchor="mm")
        cx += chip_w + 16


def generate_solve_card(platform: str, title: str, difficulty: str, stats: list[tuple[str, str]],
                        tags: list | None = None, footer_left: str | None = None,
                        footer_right: str | None = None) -> bytes:
    """Generates a beautifully formatted PNG card for a problem solve.

    Args:
        platform: "leetcode" or "codeforces"
        title: Problem name (e.g. "Two Sum")
        difficulty: Easy/Medium/Hard for LeetCode or Rating for Codeforces
        stats: List of (label, value) pairs to show in the grid columns (max 4).
        tags: Optional list of tag strings rendered as chips under the title.
        footer_left: Optional subtle footer text (e.g. solve date/time).
        footer_right: Optional subtle footer text (e.g. user handle).

    Returns:
        bytes: The PNG file bytes.
    """
    ensure_assets()

    is_leetcode = platform.lower() == "leetcode"

    # Platform-specific styling
    if is_leetcode:
        grad_color1 = LC_ORANGE         # Orange
        grad_color2 = (244, 63, 94)     # Rose
        platform_text = "LeetCode"
        platform_color = LC_ORANGE
    else:
        grad_color1 = CF_BLUE           # Blue
        grad_color2 = RED               # Red
        platform_text = "Codeforces"
        platform_color = CF_BLUE

    card = _create_card(CARD_W, SOLVE_CARD_H, grad_color1, grad_color2)
    draw = ImageDraw.Draw(card)

    # --- Header (centered at y=70) ---
    header_center_y = 70
    logo_img = Image.new("RGBA", (72, 72), (0, 0, 0, 0))
    logo_draw = ImageDraw.Draw(logo_img)

    if is_leetcode:
        logo_path = os.path.join(BASE_DIR, "data", "leetcode.png")
        loaded = False
        if os.path.exists(logo_path):
            try:
                loaded_logo = Image.open(logo_path).convert("RGBA")
                loaded_logo = loaded_logo.resize((72, 72), Image.Resampling.LANCZOS)
                card.paste(loaded_logo, (80, header_center_y - 36), mask=loaded_logo)
                loaded = True
            except Exception as e:
                logger.error(f"Error loading LeetCode logo: {e}")
        if not loaded:
            logo_draw.rounded_rectangle((0, 0, 72, 72), radius=16, fill=(255, 161, 22, 255))
            logo_font = _load_font(32, "bold")
            text = "LC"
            bbox = logo_draw.textbbox((0, 0), text, font=logo_font)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
            logo_draw.text(((72 - text_w) // 2, (72 - text_h) // 2 - 4), text,
                           fill=(255, 255, 255, 255), font=logo_font)
            card.paste(logo_img, (80, header_center_y - 36), mask=logo_img)
    else:
        # Draw Codeforces vertical bars
        logo_draw.rounded_rectangle((6, 30, 22, 66), radius=4, fill=(239, 68, 68, 255))   # Red
        logo_draw.rounded_rectangle((26, 6, 42, 66), radius=4, fill=(59, 130, 246, 255))  # Blue
        logo_draw.rounded_rectangle((46, 18, 62, 66), radius=4, fill=(250, 204, 21, 255)) # Yellow
        card.paste(logo_img, (80, header_center_y - 36), mask=logo_img)

    # Platform name
    platform_font = _load_font(44, "bold")
    draw.text((180, 85), platform_text, fill=TEXT_PRIMARY, font=platform_font, anchor="ls")

    # "NEW SOLVE" indicator on top right
    draw.text((CARD_W - 80, header_center_y), "NEW SOLVE", fill=platform_color + (255,),
              font=_load_font(28, "regular"), anchor="rm")

    # Difficulty / rating badge next to the platform name (hidden when unknown)
    badge_label = None
    badge_color = None
    if is_leetcode:
        lc_badge_colors = {"Easy": GREEN, "Medium": YELLOW, "Hard": RED}
        if difficulty in lc_badge_colors:
            badge_label = difficulty
            badge_color = lc_badge_colors[difficulty]
    else:
        tier_color = cf_tier_color(difficulty)
        if tier_color is not None:
            badge_label = str(difficulty)
            badge_color = tier_color

    if badge_label and badge_color:
        platform_bbox = draw.textbbox((180, 85), platform_text, font=platform_font, anchor="ls")
        badge_x = platform_bbox[2] + 32
        badge_h = 48
        badge_y = header_center_y - badge_h // 2
        badge_font = _load_font(24, "bold")
        badge_w = int(draw.textlength(badge_label, font=badge_font)) + 36
        draw.rounded_rectangle((badge_x, badge_y, badge_x + badge_w, badge_y + badge_h),
                               radius=12, fill=badge_color + (255,))
        draw.text((badge_x + 18, header_center_y), badge_label, fill=TEXT_PRIMARY,
                  font=badge_font, anchor="lm")

    # Divider line
    draw.line((80, 140, CARD_W - 80, 140), fill=DIVIDER, width=2)

    # Problem title (cleaned and dynamically sized)
    cleaned_title = clean_text(title)
    title_font, cleaned_title = _fit_text(draw, cleaned_title, "bold", 60, 36, CARD_W - 160)
    draw.text((80, 180), cleaned_title, fill=TEXT_PRIMARY, font=title_font)

    # Tag chips under the title (Codeforces problem tags)
    if tags:
        _draw_tag_chips(draw, 80, 272, tags, CARD_W - 160)

    # --- Stats grid ---
    start_x = 64
    start_y = 330
    grid_gap = 24
    box_w = 330
    box_h = 180

    for i, (label, val) in enumerate(stats):
        if i >= 4:
            break
        cleaned_val = clean_text(val) if val else "N/A"
        col_x = start_x + i * (box_w + grid_gap)

        # Stats box rounded card
        draw.rounded_rectangle((col_x, start_y, col_x + box_w, start_y + box_h),
                               radius=24, fill=BOX_BG)
        # Left colored accent line
        draw.rectangle((col_x, start_y + 20, col_x + 6, start_y + box_h - 20),
                       fill=platform_color + (255,))

        # Label
        draw.text((col_x + 36, start_y + 32), str(label).upper(), fill=TEXT_SECONDARY,
                  font=_load_font(22, "regular"))

        # Value (dynamically scaled down to prevent overflow)
        max_val_width = box_w - 36 - 16
        val_size = 32
        val_font = _load_font(val_size, "bold")
        while draw.textlength(cleaned_val, font=val_font) > max_val_width and val_size > 16:
            val_size -= 2
            val_font = _load_font(val_size, "medium" if val_size < 26 else "bold")
        if draw.textlength(cleaned_val, font=val_font) > max_val_width:
            while cleaned_val and draw.textlength(cleaned_val + "...", font=val_font) > max_val_width:
                cleaned_val = cleaned_val[:-1]
            cleaned_val = cleaned_val + "..."

        draw.text((col_x + 36, start_y + 80), cleaned_val, fill=TEXT_PRIMARY, font=val_font)

    # --- Footer (solve time + handle) ---
    if footer_left or footer_right:
        draw.line((80, 545, CARD_W - 80, 545), fill=DIVIDER, width=2)
        footer_font = _load_font(24, "medium")
        if footer_left:
            draw.text((80, 578), clean_text(footer_left), fill=TEXT_MUTED,
                      font=footer_font, anchor="lm")
        if footer_right:
            draw.text((CARD_W - 80, 578), clean_text(footer_right), fill=TEXT_MUTED,
                      font=footer_font, anchor="rm")

    return _render_card(card)


def _draw_progress_row(draw: ImageDraw.ImageDraw, bx: int, box_w: int, y: int,
                       label: str, val: int, target: int) -> None:
    """Draws a label, right-aligned value and (when a target exists) a full-width
    progress bar beneath the row."""
    draw.text((bx + 36, y), label, fill=TEXT_SECONDARY, font=_load_font(22, "regular"))
    val_str = f"{val} / {target}" if target > 0 else str(val)
    draw.text((bx + box_w - 36, y), val_str, fill=TEXT_PRIMARY,
              font=_load_font(22, "bold"), anchor="ra")

    if target > 0:
        bar_y = y + 32
        bar_w = box_w - 72
        draw.rounded_rectangle((bx + 36, bar_y, bx + 36 + bar_w, bar_y + 6),
                               radius=3, fill=DIVIDER)
        fill_w = int(min(1.0, val / target) * bar_w)
        if fill_w > 0:
            fill_color = GREEN if val >= target else YELLOW
            draw.rounded_rectangle((bx + 36, bar_y, bx + 36 + fill_w, bar_y + 6),
                                   radius=3, fill=fill_color + (255,))


def _draw_count_row(draw: ImageDraw.ImageDraw, bx: int, box_w: int, y: int,
                    label: str, val: int, bar_color: tuple, max_count: int) -> None:
    """Draws a label, right-aligned count and a relative-width bar beneath the row."""
    draw.text((bx + 36, y), label, fill=TEXT_SECONDARY, font=_load_font(22, "regular"))
    draw.text((bx + box_w - 36, y), str(val), fill=TEXT_PRIMARY,
              font=_load_font(22, "bold"), anchor="ra")

    bar_y = y + 28
    bar_w = box_w - 72
    draw.rounded_rectangle((bx + 36, bar_y, bx + 36 + bar_w, bar_y + 6),
                           radius=3, fill=DIVIDER)
    if val > 0 and max_count > 0:
        fill_w = max(8, int(val / max_count * bar_w))
        draw.rounded_rectangle((bx + 36, bar_y, bx + 36 + fill_w, bar_y + 6),
                               radius=3, fill=bar_color + (255,))


def generate_summary_card(summary_type: str, date_str: str, stats: dict,
                          targets: dict | None = None, extras: dict | None = None) -> bytes:
    """Generates a beautifully formatted Daily, Weekly, or Monthly summary progress card.

    Args:
        summary_type: "daily", "weekly", or "monthly"
        date_str: Date/Date range string to display in header
        stats: Dictionary containing leetcode and codeforces solve counts
        targets: Optional {'easy': int, 'medium': int, 'hard': int} LeetCode targets.
        extras: Optional dict with:
            - streak (int): current solve streak in days
            - delta (int): solve count difference vs the previous period
            - delta_label (str): e.g. "VS YESTERDAY"
            - activity (list[tuple[str, int]]): per-day (label, count) bars
            - activity_title (str): e.g. "LAST 7 DAYS"

    Returns:
        bytes: The PNG file bytes.
    """
    ensure_assets()

    targets = targets or {}
    extras = extras or {}

    # Gradient colors based on summary type
    stype = summary_type.lower()
    if stype == "daily":
        grad_color1 = (139, 92, 246)   # Violet
        grad_color2 = (6, 182, 212)    # Cyan
        accent_color = (139, 92, 246)
    elif stype == "weekly":
        grad_color1 = (16, 185, 129)   # Emerald
        grad_color2 = (20, 184, 166)   # Teal
        accent_color = (16, 185, 129)
    else:  # monthly
        grad_color1 = (245, 158, 11)   # Amber
        grad_color2 = (244, 63, 94)    # Rose
        accent_color = (245, 158, 11)

    card = _create_card(CARD_W, SUMMARY_CARD_H, grad_color1, grad_color2)
    draw = ImageDraw.Draw(card)

    # --- Header (centered at y=70) ---
    header_center_y = 70

    # Report chart icon
    logo_img = Image.new("RGBA", (72, 72), (0, 0, 0, 0))
    logo_draw = ImageDraw.Draw(logo_img)
    logo_draw.rounded_rectangle((6, 36, 22, 66), radius=4, fill=(16, 185, 129, 255))   # Green bar
    logo_draw.rounded_rectangle((26, 16, 42, 66), radius=4, fill=(99, 102, 241, 255))  # Violet bar
    logo_draw.rounded_rectangle((46, 26, 62, 66), radius=4, fill=(245, 158, 11, 255))  # Amber bar
    card.paste(logo_img, (80, header_center_y - 36), mask=logo_img)

    draw.text((180, 42), f"{summary_type.upper()} PROGRESS", fill=TEXT_PRIMARY,
              font=_load_font(38, "bold"))
    draw.text((180, 92), date_str, fill=TEXT_SECONDARY, font=_load_font(22, "regular"))
    draw.text((CARD_W - 80, header_center_y), "SUMMARY REPORT", fill=accent_color + (255,),
              font=_load_font(22, "regular"), anchor="rm")

    # Divider line
    draw.line((80, 140, CARD_W - 80, 140), fill=DIVIDER, width=2)

    # --- Process stats ---
    lc_stats = stats.get("leetcode", {})
    cf_stats = stats.get("codeforces", {})

    lc_easy = lc_stats.get("Easy", 0)
    lc_medium = lc_stats.get("Medium", 0)
    lc_hard = lc_stats.get("Hard", 0)
    lc_na = sum(count for diff, count in lc_stats.items() if diff not in ("Easy", "Medium", "Hard"))
    lc_total = sum(lc_stats.values())

    cf_bands = cf_rating_bands(cf_stats)

    cf_total = sum(cf_stats.values())
    grand_total = lc_total + cf_total

    # --- Two columns ---
    box_y = 170
    box_h = 320
    box_w = 672
    left_x = 64
    right_x = 784

    # --- LeetCode box ---
    draw.rounded_rectangle((left_x, box_y, left_x + box_w, box_y + box_h), radius=24, fill=BOX_BG)
    draw.rectangle((left_x, box_y + 20, left_x + 6, box_y + box_h - 20), fill=(255, 161, 22, 255))

    draw.text((left_x + 36, box_y + 22), "LEETCODE SUMMARY", fill=(255, 161, 22, 255),
              font=_load_font(28, "bold"))
    draw.line((left_x + 36, box_y + 56, left_x + box_w - 36, box_y + 56), fill=DIVIDER, width=1)

    lc_rows = [
        ("Easy", lc_easy, targets.get("easy", 0)),
        ("Medium", lc_medium, targets.get("medium", 0)),
        ("Hard", lc_hard, targets.get("hard", 0)),
        ("Other / Unrated", lc_na, 0),
    ]
    row_start_y = box_y + 76
    row_gap = 44
    for i, (label, val, target) in enumerate(lc_rows):
        _draw_progress_row(draw, left_x, box_w, row_start_y + i * row_gap, label, val, target)

    # Total LeetCode row
    total_line_y = box_y + 268
    draw.line((left_x + 36, total_line_y, left_x + box_w - 36, total_line_y), fill=DIVIDER, width=1)
    draw.text((left_x + 36, total_line_y + 10), "Total LeetCode", fill=TEXT_PRIMARY,
              font=_load_font(24, "bold"))
    draw.text((left_x + box_w - 36, total_line_y + 10), f"{lc_total} problems", fill=TEXT_PRIMARY,
              font=_load_font(24, "bold"), anchor="ra")

    # --- Codeforces box ---
    draw.rounded_rectangle((right_x, box_y, right_x + box_w, box_y + box_h), radius=24, fill=BOX_BG)
    draw.rectangle((right_x, box_y + 20, right_x + 6, box_y + box_h - 20), fill=(59, 130, 246, 255))

    draw.text((right_x + 36, box_y + 22), "CODEFORCES SUMMARY", fill=(59, 130, 246, 255),
              font=_load_font(28, "bold"))
    draw.line((right_x + 36, box_y + 56, right_x + box_w - 36, box_y + 56), fill=DIVIDER, width=1)

    cf_rows = [
        ("Rating 800 - 1000", cf_bands["800-1000"], (136, 136, 136)),
        ("Rating 1100 - 1300", cf_bands["1100-1300"], (34, 197, 94)),
        ("Rating 1400 - 1600", cf_bands["1400-1600"], (3, 168, 158)),
        ("Rating 1700+", cf_bands["1700+"], (59, 130, 246)),
        ("Unrated / Other", cf_bands["unrated"], (110, 118, 129)),
    ]
    cf_max = max([count for _, count, _ in cf_rows] + [1])
    cf_row_start_y = box_y + 74
    cf_row_gap = 38
    for i, (label, val, color) in enumerate(cf_rows):
        _draw_count_row(draw, right_x, box_w, cf_row_start_y + i * cf_row_gap,
                        label, val, color, cf_max)

    # Total Codeforces row
    draw.line((right_x + 36, total_line_y, right_x + box_w - 36, total_line_y), fill=DIVIDER, width=1)
    draw.text((right_x + 36, total_line_y + 10), "Total Codeforces", fill=TEXT_PRIMARY,
              font=_load_font(24, "bold"))
    draw.text((right_x + box_w - 36, total_line_y + 10), f"{cf_total} problems", fill=TEXT_PRIMARY,
              font=_load_font(24, "bold"), anchor="ra")

    # --- Activity strip (per-day mini bar chart) ---
    activity = extras.get("activity") or []
    if activity:
        activity_title = extras.get("activity_title", "")
        strip_label = f"ACTIVITY · {activity_title}" if activity_title else "ACTIVITY"
        draw.text((64, 514), strip_label, fill=TEXT_MUTED, font=_load_font(20, "medium"))

        n = len(activity)
        max_count = max([count for _, count in activity] + [1])
        gap = 16 if n <= 7 else 6
        strip_w = CARD_W - 128
        bar_w = min(56, (strip_w - (n - 1) * gap) // n)
        total_bars_w = n * bar_w + (n - 1) * gap
        bars_x = 64 + (strip_w - total_bars_w) // 2
        bars_bottom = 606
        max_bar_h = 60

        for i, (day_label, count) in enumerate(activity):
            bx = bars_x + i * (bar_w + gap)
            bar_h = max(6, int(count / max_count * max_bar_h)) if count > 0 else 6
            color = accent_color + (255,) if count > 0 else DIVIDER
            draw.rounded_rectangle((bx, bars_bottom - bar_h, bx + bar_w, bars_bottom),
                                   radius=3, fill=color)
            if n <= 7:
                draw.text((bx + bar_w / 2, bars_bottom + 10), str(day_label),
                          fill=TEXT_MUTED, font=_load_font(18, "regular"), anchor="ma")

    # --- Footer ---
    footer_center_y = 688
    draw.line((80, 660, CARD_W - 80, 660), fill=DIVIDER, width=2)
    draw.text((80, footer_center_y), f"GRAND TOTAL: {grand_total} SOLVED",
              fill=TEXT_PRIMARY, font=_load_font(28, "bold"), anchor="lm")

    # Streak + delta vs previous period
    footer_parts = []
    streak = extras.get("streak")
    if streak:
        footer_parts.append(f"STREAK {streak}D")
    delta = extras.get("delta")
    if delta is not None:
        sign = "+" if delta >= 0 else ""
        delta_label = extras.get("delta_label", "")
        footer_parts.append(f"{sign}{delta} {delta_label}".strip())
    if footer_parts:
        draw.text((CARD_W - 80, footer_center_y), " · ".join(footer_parts),
                  fill=accent_color + (255,), font=_load_font(24, "medium"), anchor="rm")

    return _render_card(card)

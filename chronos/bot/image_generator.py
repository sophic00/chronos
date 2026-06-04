import os
import io
import urllib.request
import logging
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

# Cache fonts in the workspace data directory
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FONTS_DIR = os.path.join(BASE_DIR, "data", "fonts")

FONTS = {
    "Roboto-Regular.ttf": "https://github.com/googlefonts/roboto-2/raw/main/src/hinted/Roboto-Regular.ttf",
    "Roboto-Medium.ttf": "https://github.com/googlefonts/roboto-2/raw/main/src/hinted/Roboto-Medium.ttf",
    "Roboto-Bold.ttf": "https://github.com/googlefonts/roboto-2/raw/main/src/hinted/Roboto-Bold.ttf"
}

LEETCODE_LOGO_URL = "https://upload.wikimedia.org/wikipedia/commons/8/8e/LeetCode_Logo_1.png"

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
    """Strips high-plane unicode characters (like emojis) that aren't supported by Roboto."""
    if not text:
        return ""
    return "".join(c for c in text if ord(c) < 0xffff)

def generate_solve_card(platform: str, title: str, difficulty: str, stats: list[tuple[str, str]]) -> bytes:
    """Generates a beautifully formatted PNG card for a problem solve.
    
    Args:
        platform: "leetcode" or "codeforces"
        title: Problem name (e.g. "Two Sum")
        difficulty: Easy/Medium/Hard for LeetCode or Rating for Codeforces
        stats: List of (label, value) pairs to show in the grid columns.
        
    Returns:
        bytes: The PNG file bytes.
    """
    ensure_assets()
    
    # 1. Config & Layout
    card_w = 1520
    card_h = 620
    radius = 48
    border_width = 6
    
    card_bg = (13, 17, 23, 255)       # Deep slate-gray/dark blue background
    stat_box_bg = (22, 27, 34, 255)   # Slightly lighter slate box background
    
    # Platform-specific styling
    if platform.lower() == "leetcode":
        grad_color1 = (255, 161, 22)   # Orange
        grad_color2 = (244, 63, 94)    # Rose
        platform_text = "LeetCode"
        platform_color = (255, 161, 22)
    else:
        grad_color1 = (59, 130, 246)   # Blue
        grad_color2 = (239, 68, 68)    # Red
        platform_text = "Codeforces"
        platform_color = (59, 130, 246)
        
    # Fonts
    font_reg_path = os.path.join(FONTS_DIR, "Roboto-Regular.ttf")
    font_med_path = os.path.join(FONTS_DIR, "Roboto-Medium.ttf")
    font_bold_path = os.path.join(FONTS_DIR, "Roboto-Bold.ttf")
    
    try:
        title_font = ImageFont.truetype(font_bold_path, 60)
        platform_font = ImageFont.truetype(font_bold_path, 44)
        subtitle_font = ImageFont.truetype(font_reg_path, 28)
        badge_font = ImageFont.truetype(font_bold_path, 24)
        stat_label_font = ImageFont.truetype(font_reg_path, 22)
        stat_val_font = ImageFont.truetype(font_bold_path, 32)
        stat_val_small_font = ImageFont.truetype(font_med_path, 26)
    except Exception as e:
        logger.error(f"Failed to load TrueType fonts, using fallback: {e}")
        title_font = platform_font = subtitle_font = badge_font = stat_label_font = stat_val_font = stat_val_small_font = ImageFont.load_default()

    # 2. Draw card on a transparent canvas
    card = Image.new("RGBA", (card_w, card_h), (0, 0, 0, 0))
    gradient_img = create_gradient_fast(card_w, card_h, grad_color1, grad_color2)
    
    border_mask = Image.new("L", (card_w, card_h), 0)
    draw_bm = ImageDraw.Draw(border_mask)
    draw_bm.rounded_rectangle((0, 0, card_w, card_h), radius=radius, fill=255)
    
    card.paste(gradient_img, (0, 0), mask=border_mask)
    
    inner_w = card_w - 2 * border_width
    inner_h = card_h - 2 * border_width
    inner_bg = Image.new("RGBA", (inner_w, inner_h), card_bg)
    inner_mask = Image.new("L", (inner_w, inner_h), 0)
    draw_im = ImageDraw.Draw(inner_mask)
    draw_im.rounded_rectangle((0, 0, inner_w, inner_h), radius=radius - border_width, fill=255)
    
    card.paste(inner_bg, (border_width, border_width), mask=inner_mask)
    
    # 3. Draw Elements on card
    draw = ImageDraw.Draw(card)
    
    # Logo drawing
    header_center_y = 70
    logo_img = Image.new("RGBA", (72, 72), (0, 0, 0, 0))
    logo_draw = ImageDraw.Draw(logo_img)
    
    if platform.lower() == "leetcode":
        logo_path = os.path.join(BASE_DIR, "data", "leetcode.png")
        if os.path.exists(logo_path):
            try:
                loaded_logo = Image.open(logo_path).convert("RGBA")
                loaded_logo = loaded_logo.resize((72, 72), Image.Resampling.LANCZOS)
                card.paste(loaded_logo, (80, header_center_y - 36), mask=loaded_logo)
            except Exception as e:
                logger.error(f"Error loading LeetCode logo: {e}")
                logo_draw.rounded_rectangle((0, 0, 72, 72), radius=16, fill=(255, 161, 22, 255))
                try:
                    logo_font = ImageFont.truetype(font_bold_path, 32)
                except Exception:
                    logo_font = ImageFont.load_default()
                text = "LC"
                bbox = logo_draw.textbbox((0, 0), text, font=logo_font)
                text_w = bbox[2] - bbox[0]
                text_h = bbox[3] - bbox[1]
                logo_draw.text(((72 - text_w) // 2, (72 - text_h) // 2 - 4), text, fill=(255, 255, 255, 255), font=logo_font)
                card.paste(logo_img, (80, header_center_y - 36), mask=logo_img)
        else:
            logo_draw.rounded_rectangle((0, 0, 72, 72), radius=16, fill=(255, 161, 22, 255))
            try:
                logo_font = ImageFont.truetype(font_bold_path, 32)
            except Exception:
                logo_font = ImageFont.load_default()
            text = "LC"
            bbox = logo_draw.textbbox((0, 0), text, font=logo_font)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
            logo_draw.text(((72 - text_w) // 2, (72 - text_h) // 2 - 4), text, fill=(255, 255, 255, 255), font=logo_font)
            card.paste(logo_img, (80, header_center_y - 36), mask=logo_img)
    else:
        # Draw Codeforces vertical bars
        logo_draw.rounded_rectangle((6, 30, 22, 66), radius=4, fill=(239, 68, 68, 255)) # Red
        logo_draw.rounded_rectangle((26, 6, 42, 66), radius=4, fill=(59, 130, 246, 255)) # Blue
        logo_draw.rounded_rectangle((46, 18, 62, 66), radius=4, fill=(250, 204, 21, 255)) # Yellow
        card.paste(logo_img, (80, header_center_y - 36), mask=logo_img)
        
    # Platform Text Header (centered at y=70, baseline at y=85 for 30px cap height)
    draw.text((180, 85), platform_text, fill=(255, 255, 255, 255), font=platform_font, anchor="ls")
    
    # "NEW SOLVE" Indicator on top right (aligned with divider right end at card_w - 80)
    draw.text((card_w - 80, header_center_y), "NEW SOLVE", fill=platform_color, font=subtitle_font, anchor="rm")
    
    # Difficulty Badge next to platform text
    platform_bbox = draw.textbbox((180, 85), platform_text, font=platform_font, anchor="ls")
    badge_x = platform_bbox[2] + 32
    badge_h = 48
    badge_y = header_center_y - badge_h // 2 # 46
    
    if platform.lower() == "leetcode":
        if difficulty == "Easy":
            diff_bg = (34, 197, 94, 255) # Green
        elif difficulty == "Medium":
            diff_bg = (234, 179, 8, 255) # Yellow
        else:
            diff_bg = (239, 68, 68, 255) # Red
    else:
        diff_bg = (59, 130, 246, 255) # Blue
        
    badge_text = f" {difficulty} "
    badge_bbox = draw.textbbox((badge_x, header_center_y), badge_text, font=badge_font, anchor="lm")
    badge_w = badge_bbox[2] - badge_bbox[0] + 32
    
    draw.rounded_rectangle((badge_x, badge_y, badge_x + badge_w, badge_y + badge_h), radius=12, fill=diff_bg)
    draw.text((badge_x + 16, header_center_y), badge_text.strip(), fill=(255, 255, 255, 255), font=badge_font, anchor="lm")
    
    # Divider Line (y=140)
    draw.line((80, 140, card_w - 80, 140), fill=(48, 54, 61, 255), width=2)
    
    # Problem Title (cleaned and dynamically sized)
    cleaned_title = clean_text(title)
    max_title_width = 1360
    title_font_size = 60
    title_font = ImageFont.truetype(font_bold_path, title_font_size)
    
    while draw.textlength(cleaned_title, font=title_font) > max_title_width and title_font_size > 36:
        title_font_size -= 4
        title_font = ImageFont.truetype(font_bold_path, title_font_size)
        
    if draw.textlength(cleaned_title, font=title_font) > max_title_width:
        while draw.textlength(cleaned_title + "...", font=title_font) > max_title_width and len(cleaned_title) > 0:
            cleaned_title = cleaned_title[:-1]
        cleaned_title = cleaned_title + "..."
        
    draw.text((80, 180), cleaned_title, fill=(255, 255, 255, 255), font=title_font)
    
    # Centered Stats Grid
    start_x = 64
    start_y = 360
    grid_gap = 24
    box_w = 330
    box_h = 180
    
    for i, (label, val) in enumerate(stats):
        if i >= 4:
            break
        cleaned_val = clean_text(val) if val else "N/A"
        col_x = start_x + i * (box_w + grid_gap)
        
        # Stats box rounded card
        draw.rounded_rectangle((col_x, start_y, col_x + box_w, start_y + box_h), radius=24, fill=stat_box_bg)
        # Left colored accent line
        draw.rectangle((col_x, start_y + 20, col_x + 6, start_y + box_h - 20), fill=platform_color)
        
        # Label
        draw.text((col_x + 36, start_y + 32), label.upper(), fill=(139, 148, 158, 255), font=stat_label_font)
        
        # Value (dynamically scale down font size to prevent overflow)
        max_val_width = box_w - 36 - 16 # 278 pixels
        val_font_size = 32
        val_font = ImageFont.truetype(font_bold_path, val_font_size)
        
        while draw.textlength(cleaned_val, font=val_font) > max_val_width and val_font_size > 16:
            val_font_size -= 2
            font_path = font_med_path if val_font_size < 26 else font_bold_path
            val_font = ImageFont.truetype(font_path, val_font_size)
            
        if draw.textlength(cleaned_val, font=val_font) > max_val_width:
            while draw.textlength(cleaned_val + "...", font=val_font) > max_val_width and len(cleaned_val) > 0:
                cleaned_val = cleaned_val[:-1]
            cleaned_val = cleaned_val + "..."
            
        draw.text((col_x + 36, start_y + 80), cleaned_val, fill=(255, 255, 255, 255), font=val_font)
        
    # 4. Create the final output image with solid rectangular background (no rounded corners, no transparency at the edges)
    final_w = 1600
    final_h = 700
    canvas = Image.new("RGB", (final_w, final_h), (8, 11, 16))
    canvas.paste(card, (40, 40), mask=card)
    
    # 5. Downscale with LANCZOS filter to 1x size (800x350)
    resized_canvas = canvas.resize((800, 350), Image.Resampling.LANCZOS)
    
    # Save to in-memory bytes
    img_byte_arr = io.BytesIO()
    resized_canvas.save(img_byte_arr, format='PNG')
    return img_byte_arr.getvalue()

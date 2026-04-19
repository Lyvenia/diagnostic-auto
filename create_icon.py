"""
Génère icon.ico pour RODIA — by Lyvenia.
Palette : vert forêt foncé + accent rose crème.
"""
from PIL import Image, ImageDraw, ImageFont
import os, math

BG       = (12, 24, 12)         # #0c180c  vert forêt profond
BG2      = (26, 46, 26)         # #1a2e1a  vert card
ACCENT   = (232, 180, 164)      # #e8b4a4  rose crème
ACCENT2  = (196, 146, 130)      # #c49282  rose dim
WHITE    = (240, 240, 236)      # #f0f0ec
BORDER   = (42, 66, 40)         # #2a4228


def make_frame(size):
    img  = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    r    = size // 6   # coins bien arrondis

    # ── Fond arrondi vert profond ────────────────────────────
    draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=r, fill=BG)

    # ── Liseré intérieur (frame) ─────────────────────────────
    if size >= 32:
        margin = max(2, size // 24)
        draw.rounded_rectangle(
            [margin, margin, size - 1 - margin, size - 1 - margin],
            radius=max(2, r - margin),
            outline=(*BORDER, 180),
            width=max(1, size // 40),
        )

    # ── Barre accent en haut ─────────────────────────────────
    bar_h = max(2, size // 14)
    draw.rounded_rectangle([0, 0, size - 1, bar_h + r], radius=r, fill=ACCENT)
    draw.rectangle([0, bar_h, size - 1, bar_h + r], fill=ACCENT)

    # ── Lettre "R" centrale ──────────────────────────────────
    font_size = max(8, int(size * 0.52))
    font = None
    for fname in ["segoeuib.ttf", "arialbd.ttf", "ariblk.ttf", "arial.ttf"]:
        try:
            font = ImageFont.truetype(fname, font_size)
            break
        except Exception:
            pass
    if font is None:
        font = ImageFont.load_default()

    text = "R"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = (size - tw) // 2 - bbox[0]
    # Légèrement au-dessus du centre (laisser place au sous-texte)
    ty = int(size * 0.18) - bbox[1]
    draw.text((tx, ty), text, font=font, fill=WHITE)

    # ── Sous-texte "OBD" en bas ──────────────────────────────
    if size >= 48:
        sub_size = max(5, int(size * 0.15))
        sub_font = None
        for fname in ["segoeuib.ttf", "arialbd.ttf", "arial.ttf"]:
            try:
                sub_font = ImageFont.truetype(fname, sub_size)
                break
            except Exception:
                pass
        if sub_font is None:
            sub_font = ImageFont.load_default()

        sub  = "OBD"
        sb   = draw.textbbox((0, 0), sub, font=sub_font)
        stw  = sb[2] - sb[0]
        sx   = (size - stw) // 2 - sb[0]
        sy   = size - int(size * 0.18) - sb[1]
        draw.text((sx, sy), sub, font=sub_font, fill=(*ACCENT2, 200))

    # ── Petit point de connectivité (coin bas-droite) ────────
    if size >= 48:
        dot_r = max(2, size // 14)
        cx = size - int(size * 0.18)
        cy = size - int(size * 0.18)
        draw.ellipse(
            [cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r],
            fill=(*ACCENT, 220),
        )
        # Anneau autour du point
        if size >= 64:
            draw.ellipse(
                [cx - dot_r - 2, cy - dot_r - 2, cx + dot_r + 2, cy + dot_r + 2],
                outline=(*ACCENT, 80),
                width=1,
            )

    return img


def create_icon(path="icon.ico"):
    sizes  = [256, 128, 64, 48, 32, 16]
    frames = [make_frame(s) for s in sizes]
    frames[0].save(
        path, format="ICO",
        sizes=[(s, s) for s in sizes],
        append_images=frames[1:],
    )
    print(f"icon.ico genere : {path}  ({os.path.getsize(path) // 1024} Ko)")


if __name__ == "__main__":
    create_icon()
    # Copie aussi dans frontend/ pour le favicon
    create_icon("frontend/favicon.ico")
    print("favicon.ico copié dans frontend/")

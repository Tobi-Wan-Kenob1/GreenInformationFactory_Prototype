#!/usr/bin/env python3
"""Render the guided-tour flipbook GIF for project reporting.

Builds one 1280x720 frame per tour station — brand header with the BioFairNet
logo, station title, short caption, and the real result figure(s) — and writes
an animated GIF. Fully deterministic (no screen recording), so the artifact
can be regenerated whenever the underlying figures change:

    python docs/make_tour_gif.py            # writes docs/assets/biofairnet_tour.gif

Requires Pillow (installed with matplotlib). Fonts fall back gracefully if the
preferred system faces are unavailable.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
ASSETS = HERE / "assets"
OUT = ASSETS / "biofairnet_tour.gif"

W, H = 1280, 720
# BioFairNet visual identity
TEAL = (10, 107, 101)
AMBER = (255, 190, 92)
INK = (56, 53, 53)
MUTED = (92, 102, 98)
FAINT = (138, 147, 143)
BG = (250, 251, 250)
LINE = (227, 232, 229)
WHITE = (255, 255, 255)

FRAME_MS = 4000  # per-station duration

STATIONS = [
    ("The Green Information Factory",
     "How open data becomes open evidence: an automated, reproducible "
     "pipeline for sustainability assessment in the circular bioeconomy.",
     []),
    ("1 · It starts and ends with open data",
     "Every input is a citable dataset in the BioFairNet community on Zenodo: "
     "pilot-plant measurements and the WP1 literature review, each with a "
     "permanent DOI.",
     []),
    ("2 · From measurements to models",
     "Eight machine-learning models compete on reproducibly prepared data. "
     "The best predicts unseen process behaviour almost perfectly.",
     ["val_scatter_top3.png"]),
    ("3 · Sustainability at a glance",
     "Models plus CO₂ and circularity indicators show where a process is "
     "sustainable — and which levers move it there.",
     ["scenario_co2_time_s_rf.png", "scenario_sustainable_region_pca_Stiring_rf.png"]),
    ("4 · Can the results be trusted?",
     "Indicators are computed on test AND never-seen validation data. "
     "Overlapping clouds = the evidence generalizes.",
     ["tradeoff_test_vs_validation_pca_rf.png"]),
    ("5 · What 366 studies tell us",
     "The hand-coded WP1 literature review becomes transparent statistics: "
     "the recurring barriers and drivers of the green transition.",
     ["lit_top_barriers.png"]),
    ("6 · Where the evidence comes from",
     "Hotspot analytics map the geography and momentum of the field — "
     "EU regions plus Canada and Kenya.",
     ["lit_country_counts.png", "lit_year_by_sector.png"]),
    ("7 · AI that assists the experts",
     "Classifiers trained on the researchers' own codes pre-sort new papers "
     "(sector correct for >9 of 10). Human judgement stays in charge.",
     ["lit_coding_f1_by_task.png"]),
    ("8 · The loop closes",
     "All results return to Zenodo under open licenses, machine-linked to "
     "their sources. Every output is an input for the next cycle. "
     "DOI 10.5281/zenodo.21168823",
     []),
]


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        ("/System/Library/Fonts/HelveticaNeue.ttc", 1 if bold else 0),
        ("/System/Library/Fonts/Helvetica.ttc", 1 if bold else 0),
        ("/Library/Fonts/Arial Bold.ttf" if bold else "/Library/Fonts/Arial.ttf", 0),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans%s.ttf"
         % ("-Bold" if bold else ""), 0),
    ]
    for path, index in candidates:
        try:
            return ImageFont.truetype(path, size, index=index)
        except Exception:
            continue
    return ImageFont.load_default()


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> list:
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if draw.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _paste_fit(canvas: Image.Image, img: Image.Image, box: tuple) -> None:
    """Paste img centred into box=(x, y, w, h), preserving aspect ratio."""
    x, y, bw, bh = box
    scale = min(bw / img.width, bh / img.height)
    nw, nh = int(img.width * scale), int(img.height * scale)
    img = img.resize((nw, nh), Image.LANCZOS)
    canvas.paste(img, (x + (bw - nw) // 2, y + (bh - nh) // 2),
                 img if img.mode == "RGBA" else None)


def render_frame(idx: int, title: str, caption: str, figs: list,
                 logo: Image.Image) -> Image.Image:
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)

    # header band
    d.rectangle([0, 0, W, 96], fill=WHITE)
    d.line([0, 96, W, 96], fill=LINE, width=2)
    _paste_fit(im, logo, (32, 12, 72, 72))
    d.text((124, 18), "BIOFAIRNET · HORIZON EUROPE", font=_font(15, True), fill=TEAL)
    d.text((124, 42), "The Green Information Factory — a guided tour",
           font=_font(26, True), fill=INK)

    has_figs = bool(figs)
    text_w = 480 if has_figs else 900
    tx, ty = 48, 150

    # station title + caption
    for line in _wrap(d, title, _font(30, True), text_w):
        d.text((tx, ty), line, font=_font(30, True), fill=INK)
        ty += 42
    ty += 10
    for line in _wrap(d, caption, _font(21), text_w):
        d.text((tx, ty), line, font=_font(21), fill=MUTED)
        ty += 32

    # figures on the right (one or two stacked)
    if has_figs:
        fx, fy, fw, fh = 560, 116, 672, 520
        if len(figs) == 1:
            fig = Image.open(ASSETS / figs[0])
            _paste_fit(im, fig, (fx, fy, fw, fh))
        else:
            half = (fh - 16) // 2
            for j, name in enumerate(figs[:2]):
                fig = Image.open(ASSETS / name)
                _paste_fit(im, fig, (fx, fy + j * (half + 16), fw, half))

    # progress dots
    n = len(STATIONS)
    dot_y, dot_r, gap = H - 52, 6, 22
    x0 = (W - (n - 1) * gap) // 2
    for j in range(n):
        cx = x0 + j * gap
        color = TEAL if j == idx else LINE
        r = dot_r + 2 if j == idx else dot_r
        d.ellipse([cx - r, dot_y - r, cx + r, dot_y + r], fill=color)

    # footer
    d.text((48, H - 34),
           "BioFairNet · funded by the European Union's Horizon Europe programme",
           font=_font(14), fill=FAINT)
    d.text((W - 48, H - 34), "github.com/Tobi-Wan-Kenob1/GreenInformationFactory_Prototype",
           font=_font(14), fill=FAINT, anchor="ra")
    return im


def main() -> None:
    logo = Image.open(ASSETS / "biofairnet_logo.png").convert("RGBA")
    frames = [render_frame(i, t, c, f, logo)
              for i, (t, c, f) in enumerate(STATIONS)]
    frames[0].save(
        OUT, save_all=True, append_images=frames[1:],
        duration=FRAME_MS, loop=0, optimize=True,
    )
    size_mb = OUT.stat().st_size / 1e6
    print(f"✅ wrote {OUT} ({len(frames)} frames, {FRAME_MS} ms each, {size_mb:.1f} MB)")


if __name__ == "__main__":
    main()

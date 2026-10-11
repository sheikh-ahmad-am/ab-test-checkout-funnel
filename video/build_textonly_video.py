#!/usr/bin/env python3
"""Build text-overlay-only walkthrough video for ab-test-checkout-funnel.
1920x1080, ~60s, no audio. Matches customer-churn-retention walkthrough_textonly.mp4 style."""
import os, subprocess
from PIL import Image, ImageDraw, ImageFont

W, H = 1920, 1080
IMG_DIR = os.path.expanduser("~/workspace/projects/ab-test-checkout-funnel/images")
OUT_DIR = os.path.expanduser("~/workspace/projects/ab-test-checkout-funnel/video")
FRAMES_DIR = os.path.join(OUT_DIR, "_textonly_frames")
os.makedirs(FRAMES_DIR, exist_ok=True)

def font(size, bold=True):
    path = "/usr/share/fonts/truetype/dejavu/DejaVuSans%s.ttf" % ("-Bold" if bold else "")
    return ImageFont.truetype(path, size)

BG = (10, 15, 25)
ACCENT = (0, 170, 255)
TXT = (255, 255, 255)
MUTED = (200, 210, 225)

def centered(d, y, line, size, bold=True, color=TXT):
    f = font(size, bold)
    bb = f.getbbox(line); tw = bb[2] - bb[0]
    d.text(((W - tw) / 2, y), line, font=f, fill=color)
    return y + (bb[3] - bb[1]) + 20

def header(draw, kicker):
    f = font(40, True)
    bb = f.getbbox(kicker); tw = bb[2] - bb[0]
    draw.rectangle([(W - tw) / 2 - 30, 40, (W + tw) / 2 + 30, 40 + (bb[3] - bb[1]) + 26], fill=ACCENT)
    draw.text(((W - tw) / 2, 54), kicker, font=f, fill=(5, 10, 18))

def text_card(main_lines, sub_lines, fname):
    c = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(c, "RGBA")
    y = 360
    for line in main_lines:
        y = centered(d, y, line, 88, True)
    y += 40
    for line in sub_lines:
        y = centered(d, y, line, 46, False, MUTED)
    c.save(os.path.join(FRAMES_DIR, fname), quality=95)

def chart_scene(img_name, kicker, headline, subline, fname):
    c = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(c, "RGBA")
    header(d, kicker)
    chart = Image.open(os.path.join(IMG_DIR, img_name)).convert("RGB")
    chart.thumbnail((1720, 470), Image.LANCZOS)  # band: y 250..720
    x = (W - chart.width) // 2
    y = 250 + (470 - chart.height) // 2
    d.rectangle([x - 8, y - 8, x + chart.width + 8, y + chart.height + 8], fill=(28, 38, 55))
    c.paste(chart, (x, y))
    # bottom bar: y 790..990 (no overlap with chart band)
    d.rectangle([120, 790, W - 120, 990], fill=(0, 0, 0, 170))
    yy = 812
    yy = centered(d, yy, headline, 52, True)
    centered(d, yy, subline, 38, False, MUTED)
    c.save(os.path.join(FRAMES_DIR, fname), quality=95)

scenes = [
    (8, lambda: text_card(
        ["A/B Test: Checkout Redesign"],
        ["20,000 users  ·  50/50 split", "MD AHMAD"], "s01.png")),
    (9, lambda: chart_scene("conversion_ci.png", "THE HEADLINE",
        "Purchases: 11.98% → 14.50%",
        "+2.52pp  ·  95% CI [+1.58, +3.45]  ·  p ≈ 0", "s02.png")),
    (9, lambda: chart_scene("lift_by_segment.png", "SEGMENT BEFORE YOU CONCLUDE",
        "Desktop +7.00pp  ·  Mobile flat",
        "Mobile not significant — ship desktop, hold mobile", "s03.png")),
    (9, lambda: chart_scene("funnel_comparison.png", "FUNNEL CHECK",
        "Lift landed exactly where it should",
        "Checkout → payment: +8.06pp", "s04.png")),
    (8, lambda: chart_scene("attribution.png", "ATTRIBUTION BONUS",
        "First-touch: social wins discovery",
        "Last-touch: paid wins closing", "s05.png")),
    (8, lambda: text_card(
        ["Ship to desktop. Diagnose mobile."],
        ["The headline metric is never the whole story"], "s06.png")),
    (7, lambda: text_card(
        ["SQL · Python · Statistics"],
        ["github.com/sheikh-ahmad-am/ab-test-checkout-funnel"], "s07.png")),
]

# concat demuxer inflates still durations by ~14%; compensate so total lands ~58-60s
SCALE = 0.88
imgs = []
for i, (dur, builder) in enumerate(scenes):
    builder()
    imgs.append(os.path.join(FRAMES_DIR, "s%02d.png" % (i + 1)))
total = sum(d for d, _ in scenes)
print("frames:", len(imgs), "intended:", total, "s; scaled to ~%.0f s" % (total * SCALE))

listfile = os.path.join(FRAMES_DIR, "concat.txt")
with open(listfile, "w") as f:
    for (dur, _), img in zip(scenes, imgs):
        f.write("file '%s'\nduration %.2f\n" % (img, dur * SCALE))
    f.write("file '%s'\n" % imgs[-1])

out = os.path.join(OUT_DIR, "walkthrough_textonly.mp4")
subprocess.run([
    "ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", listfile,
    "-vf", "format=yuv420p", "-r", "30", "-c:v", "libx264", "-crf", "20",
    "-preset", "medium", "-an", out
], check=True)
size = os.path.getsize(out) / 1e6
dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                      "-of", "csv=p=0", out], capture_output=True, text=True).stdout.strip()
print("WROTE", out, "| %.2f MB | %s s" % (size, dur))

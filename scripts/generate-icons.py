#!/usr/bin/env python3
"""Generate extension icons: white headset + AI sparkle on #0078d4 rounded background."""

from pathlib import Path

from PIL import Image, ImageDraw

ACCENT = (0, 120, 212)  # #0078d4
WHITE = (255, 255, 255)
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "extension" / "public" / "icons"


def draw_icon(size: int) -> Image.Image:
    """Draw a headset icon with optional sparkle at the given size."""
    # Work at 4x for anti-aliasing, then downsample
    scale = 4
    s = size * scale
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Rounded background
    margin = int(s * 0.06)
    radius = int(s * 0.22)
    draw.rounded_rectangle(
        [margin, margin, s - margin, s - margin],
        radius=radius,
        fill=ACCENT,
    )

    cx, cy = s // 2, s // 2

    if size <= 16:
        # Simplified icon at 16px: just headband arc + ear cups
        band_w = max(int(s * 0.07), 2)
        band_r = int(s * 0.28)
        band_box = [cx - band_r, cy - band_r - int(s * 0.05),
                     cx + band_r, cy + band_r - int(s * 0.05)]
        draw.arc(band_box, start=200, end=340, fill=WHITE, width=band_w)

        # Ear cups — rounded rectangles
        cup_w = int(s * 0.16)
        cup_h = int(s * 0.24)
        cup_r = int(s * 0.05)
        cup_y = cy - int(s * 0.02)
        # Left cup
        draw.rounded_rectangle(
            [cx - band_r - cup_w // 2, cup_y, cx - band_r + cup_w // 2, cup_y + cup_h],
            radius=cup_r, fill=WHITE,
        )
        # Right cup
        draw.rounded_rectangle(
            [cx + band_r - cup_w // 2, cup_y, cx + band_r + cup_w // 2, cup_y + cup_h],
            radius=cup_r, fill=WHITE,
        )
    else:
        # Full headset with sparkle
        # Headband arc
        band_w = max(int(s * 0.06), 2)
        band_r = int(s * 0.26)
        offset_y = -int(s * 0.04)
        band_box = [cx - band_r, cy - band_r + offset_y,
                     cx + band_r, cy + band_r + offset_y]
        draw.arc(band_box, start=195, end=345, fill=WHITE, width=band_w)

        # Ear cups
        cup_w = int(s * 0.14)
        cup_h = int(s * 0.26)
        cup_r = int(s * 0.04)
        cup_y = cy + offset_y + int(s * 0.04)

        # Left cup
        lx = cx - band_r
        draw.rounded_rectangle(
            [lx - cup_w // 2, cup_y, lx + cup_w // 2, cup_y + cup_h],
            radius=cup_r, fill=WHITE,
        )
        # Right cup
        rx = cx + band_r
        draw.rounded_rectangle(
            [rx - cup_w // 2, cup_y, rx + cup_w // 2, cup_y + cup_h],
            radius=cup_r, fill=WHITE,
        )

        # Microphone boom (small arc from left cup)
        mic_start_y = cup_y + cup_h - int(s * 0.04)
        mic_r = int(s * 0.12)
        mic_box = [lx - mic_r, mic_start_y - mic_r // 2,
                    lx + mic_r, mic_start_y + mic_r + mic_r // 2]
        draw.arc(mic_box, start=40, end=130, fill=WHITE, width=max(int(s * 0.035), 2))

        # Mic tip (small circle)
        tip_x = lx + int(mic_r * 0.65)
        tip_y = mic_start_y + int(mic_r * 0.85)
        tip_r = int(s * 0.025)
        draw.ellipse([tip_x - tip_r, tip_y - tip_r, tip_x + tip_r, tip_y + tip_r],
                      fill=WHITE)

        # AI sparkle (4-point star) — top-right area
        sx = cx + int(s * 0.22)
        sy = cy - int(s * 0.22)
        sp = int(s * 0.09)  # sparkle arm length
        sp_w = int(s * 0.03)  # arm width at center

        # Draw 4-point star as 4 triangles
        for dx, dy in [(0, -sp), (0, sp), (-sp, 0), (sp, 0)]:
            if dx == 0:
                # Vertical arm
                draw.polygon([
                    (sx - sp_w, sy),
                    (sx, sy + dy),
                    (sx + sp_w, sy),
                ], fill=WHITE)
            else:
                # Horizontal arm
                draw.polygon([
                    (sx, sy - sp_w),
                    (sx + dx, sy),
                    (sx, sy + sp_w),
                ], fill=WHITE)

    # Downsample with high-quality Lanczos
    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for size in (16, 48, 128):
        icon = draw_icon(size)
        out_path = OUTPUT_DIR / f"icon{size}.png"
        icon.save(out_path, "PNG")
        print(f"Generated {out_path} ({size}x{size})")


if __name__ == "__main__":
    main()

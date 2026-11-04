"""Generate the transparent HUD-ring layer used by the startup sequence."""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter


ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "assets" / "intro" / "intro-hud.webp"
Frames = 36
FrameDurationMs = 100


def draw_hud_frame(frame: int) -> Image.Image:
    size = 640
    center = size / 2
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image, "RGBA")
    progress = max(0.0, min(frame / 20, 1.0))
    radius = 185 * (0.72 + progress * 0.28)
    alpha = int(165 * progress)

    draw.ellipse(
        (center - radius, center - radius, center + radius, center + radius),
        outline=(61, 235, 255, alpha),
        width=2,
    )
    inner = radius * 0.72
    draw.ellipse(
        (
            center - inner,
            center - inner,
            center + inner,
            center + inner,
        ),
        outline=(123, 97, 255, int(alpha * 0.65)),
        width=1,
    )
    for index in range(48):
        angle = math.tau * index / 48
        length = 12 if index % 4 == 0 else 7
        draw.line(
            (
                center + math.cos(angle) * (radius + 6),
                center + math.sin(angle) * (radius + 6),
                center + math.cos(angle) * (radius + 6 + length),
                center + math.sin(angle) * (radius + 6 + length),
            ),
            fill=(61, 235, 255, int(105 * progress)),
            width=1,
        )
    sweep = math.tau * frame / 18
    draw.arc(
        (center - radius, center - radius, center + radius, center + radius),
        start=math.degrees(sweep),
        end=math.degrees(sweep + 0.82),
        fill=(61, 235, 255, 235),
        width=4,
    )

    pulse_progress = max(0.0, min((frame - 26) / 9, 1.0))
    if pulse_progress > 0:
        pulse_radius = radius * (0.3 + pulse_progress * 1.35)
        draw.ellipse(
            (
                center - pulse_radius,
                center - pulse_radius,
                center + pulse_radius,
                center + pulse_radius,
            ),
            outline=(61, 235, 255, int(110 * (1 - pulse_progress))),
            width=3,
        )

    glow = image.filter(ImageFilter.GaussianBlur(7))
    return Image.alpha_composite(glow, image)


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    frames = [draw_hud_frame(frame) for frame in range(Frames)]
    frames[0].save(
        OUTPUT,
        save_all=True,
        append_images=frames[1:],
        duration=FrameDurationMs,
        loop=1,
        lossless=False,
        quality=90,
        method=4,
        minimize_size=True,
    )
    print(f"Generated {OUTPUT}")


if __name__ == "__main__":
    main()

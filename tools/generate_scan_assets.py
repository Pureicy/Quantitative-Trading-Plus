"""Generate the client-side radar animation used by the scan overlay."""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "assets" / "scan" / "radar-sweep.webp"
SIZE = 280
SCALE = 2
FRAMES = 48
FRAME_DURATION_MS = 50


def draw_radar(frame: int) -> Image.Image:
    size = SIZE * SCALE
    center = size / 2
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image, "RGBA")

    cyan = (61, 235, 255)
    violet = (123, 97, 255)
    for ratio, alpha, width in ((0.94, 76, 2), (0.69, 42, 1), (0.43, 34, 1)):
        radius = center * ratio
        draw.ellipse(
            (center - radius, center - radius, center + radius, center + radius),
            outline=(*cyan, alpha),
            width=width * SCALE,
        )

    for index in range(64):
        angle = math.tau * index / 64
        outer = center * 0.94
        inner = center * (0.86 if index % 4 == 0 else 0.90)
        draw.line(
            (
                center + math.cos(angle) * inner,
                center + math.sin(angle) * inner,
                center + math.cos(angle) * outer,
                center + math.sin(angle) * outer,
            ),
            fill=(*cyan, 78 if index % 4 == 0 else 38),
            width=SCALE,
        )

    beam = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    beam_draw = ImageDraw.Draw(beam, "RGBA")
    sweep = math.tau * frame / FRAMES
    for step in range(12):
        start = sweep - step * 0.055
        end = start + 0.058
        alpha = 34 - step * 2
        radius = center * 0.91
        beam_draw.pieslice(
            (center - radius, center - radius, center + radius, center + radius),
            start=math.degrees(start),
            end=math.degrees(end),
            fill=(*cyan, max(4, alpha)),
        )

    lead = 0.91 * center
    beam_draw.line(
        (
            center,
            center,
            center + math.cos(sweep) * lead,
            center + math.sin(sweep) * lead,
        ),
        fill=(*cyan, 185),
        width=2 * SCALE,
    )
    image = Image.alpha_composite(image, beam)
    draw = ImageDraw.Draw(image, "RGBA")

    dot_radius = 4 * SCALE
    draw.ellipse(
        (
            center - dot_radius,
            center - dot_radius,
            center + dot_radius,
            center + dot_radius,
        ),
        fill=(*violet, 210),
        outline=(*cyan, 170),
        width=SCALE,
    )
    cross = 16 * SCALE
    draw.line((center - cross, center, center - 7 * SCALE, center), fill=(*cyan, 90), width=SCALE)
    draw.line((center + 7 * SCALE, center, center + cross, center), fill=(*cyan, 90), width=SCALE)
    draw.line((center, center - cross, center, center - 7 * SCALE), fill=(*cyan, 90), width=SCALE)
    draw.line((center, center + 7 * SCALE, center, center + cross), fill=(*cyan, 90), width=SCALE)

    return image.resize((SIZE, SIZE), Image.Resampling.LANCZOS)


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    frames = [draw_radar(frame) for frame in range(FRAMES)]
    frames[0].save(
        OUTPUT,
        save_all=True,
        append_images=frames[1:],
        duration=FRAME_DURATION_MS,
        loop=0,
        lossless=False,
        quality=92,
        method=4,
        minimize_size=True,
    )
    print(f"Generated {OUTPUT}")


if __name__ == "__main__":
    main()

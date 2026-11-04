"""Generate client-side animated particle layers for the Flet console."""

from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter


ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "assets" / "particles"

BACKGROUND_SIZE = (1600, 900)
BACKGROUND_COUNT = 4000
BACKGROUND_FRAMES = 40

CARD_SIZE = (420, 180)
CARD_COUNT = 36
CARD_FRAMES = 40

CONSTELLATION_SIZE = (960, 540)
CONSTELLATION_FRAMES = 36
CONSTELLATION_DURATION_MS = 140

STAR_DURATION_MS = 75


def make_particles(
    count: int,
    width: int,
    height: int,
    seed: int,
) -> list[tuple[float, float, float, tuple[int, int, int], int]]:
    rng = random.Random(seed)
    palette = (
        (118, 148, 255),
        (164, 132, 255),
        (96, 218, 255),
        (205, 220, 255),
    )
    particles = []
    for _ in range(count):
        roll = rng.random()
        if roll < 0.42:
            color = palette[0]
        elif roll < 0.68:
            color = palette[1]
        elif roll < 0.84:
            color = palette[2]
        else:
            color = palette[3]
        brightness = rng.uniform(0.72, 1.0)
        roll = rng.random()
        kind = 2 if roll > 0.978 else (1 if roll > 0.72 else 0)
        particles.append(
            (
                rng.uniform(0, width),
                rng.uniform(0, height),
                rng.uniform(0, math.tau),
                (
                    int(color[0] * brightness),
                    int(color[1] * brightness),
                    int(color[2] * brightness),
                ),
                kind,
            )
        )
    return particles


def render_star_loop(
    *,
    size: tuple[int, int],
    count: int,
    frames: int,
    seed: int,
) -> list[Image.Image]:
    width, height = size
    particles = make_particles(count, width, height, seed)
    rendered: list[Image.Image] = []
    x_amplitude = width * 0.006
    y_amplitude = height * 0.008

    for frame in range(frames):
        phase = math.tau * frame / frames
        image = Image.new("RGBA", size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        for base_x, base_y, offset, color, kind in particles:
            x = (
                base_x + math.sin(phase * 2 + offset) * x_amplitude
            ) % width
            y = (
                base_y + math.cos(phase + offset * 1.37) * y_amplitude
            ) % height
            twinkle = 0.72 + 0.28 * math.sin(phase * 2 + offset * 1.8)
            alpha = int((126 if kind == 0 else 224) * twinkle)
            if kind == 2:
                halo_alpha = int(42 * twinkle)
                draw.ellipse(
                    (x - 2.1, y - 2.1, x + 2.1, y + 2.1),
                    fill=(*color, halo_alpha),
                )
            radius = (0.42 if kind == 0 else 0.6) + 0.08
            draw.ellipse(
                (x - radius, y - radius, x + radius, y + radius),
                fill=(*color, max(40, alpha)),
            )
        rendered.append(image)
    return rendered


def constellation_groups(
    width: int,
    height: int,
    seed: int = 8102,
):
    rng = random.Random(seed)
    anchors = [
        (rng.uniform(width * 0.2, width * 0.8), rng.uniform(height * 0.24, height * 0.76)),
        (rng.uniform(width * 0.2, width * 0.8), rng.uniform(height * 0.24, height * 0.76)),
    ]
    groups = []
    for group_index, (anchor_x, anchor_y) in enumerate(anchors):
        points = []
        point_count = 25
        for index in range(point_count):
            t = -1.0 + 2.0 * index / (point_count - 1)
            if group_index == 0:
                x = anchor_x + t * 112
                y = anchor_y + math.sin(t * math.pi * 1.65) * 40
            else:
                x = anchor_x + math.sin(t * math.pi * 1.5) * 92
                y = anchor_y + math.sin(t * math.pi * 2.2) * 42
            points.append(
                (
                    x,
                    y,
                    (225, 245, 255) if index in (0, point_count - 1) else (155, 228, 255),
                )
            )
        groups.append(
            {
                "points": points,
                "phase": (0.6, 3.15)[group_index],
                "drift": (5.5, 4.0)[group_index],
                "curve": "sine" if group_index == 0 else "lissajous",
            }
        )
    return groups


def draw_constellation_group(
    draw: ImageDraw.ImageDraw,
    group: dict,
    phase: float,
) -> None:
    visibility = 0.12 + 0.88 * max(
        0.0,
        math.sin(phase + group["phase"]),
    ) ** 1.2
    offset_x = math.sin(phase * 0.7 + group["phase"]) * group["drift"]
    offset_y = math.cos(phase * 0.55 + group["phase"]) * group["drift"]
    angle = math.sin(phase * 0.45 + group["phase"]) * 0.025
    base_x = sum(point[0] for point in group["points"]) / len(group["points"])
    base_y = sum(point[1] for point in group["points"]) / len(group["points"])
    transformed = []
    for x, y, color in group["points"]:
        local_x, local_y = x - base_x, y - base_y
        rotated_x = local_x * math.cos(angle) - local_y * math.sin(angle)
        rotated_y = local_x * math.sin(angle) + local_y * math.cos(angle)
        transformed.append(
            (
                base_x + rotated_x + offset_x,
                base_y + rotated_y + offset_y,
                color,
            )
        )

    line_alpha = min(255, int(248 * visibility))
    for index in range(len(transformed) - 1):
        start = transformed[index]
        end = transformed[index + 1]
        draw.line(
            (start[0], start[1], end[0], end[1]),
            fill=(190, 240, 255, line_alpha),
            width=1,
        )

    for index, (x, y, color) in enumerate(transformed):
        if index % 4 != 0 and index not in (0, len(transformed) - 1):
            continue
        draw.ellipse(
            (x - 2.8, y - 2.8, x + 2.8, y + 2.8),
            fill=(*color, int(58 * visibility)),
        )
        draw.ellipse(
            (x - 0.9, y - 0.9, x + 0.9, y + 0.9),
            fill=(*color, min(255, int(255 * max(0.35, visibility)))),
        )


def render_constellation_loop() -> list[Image.Image]:
    width, height = CONSTELLATION_SIZE
    groups = constellation_groups(width, height)
    frames = []
    for frame in range(CONSTELLATION_FRAMES):
        phase = math.tau * frame / CONSTELLATION_FRAMES
        image = Image.new("RGBA", CONSTELLATION_SIZE, (0, 0, 0, 0))
        draw = ImageDraw.Draw(image, "RGBA")
        for group in groups:
            draw_constellation_group(draw, group, phase)
        frames.append(image)
    return frames


def make_grid() -> Image.Image:
    image = Image.new("RGBA", BACKGROUND_SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image, "RGBA")
    for x in range(0, BACKGROUND_SIZE[0], 64):
        draw.line((x, 0, x, BACKGROUND_SIZE[1]), fill=(61, 235, 255, 10), width=1)
    for y in range(0, BACKGROUND_SIZE[1], 64):
        draw.line((0, y, BACKGROUND_SIZE[0], y), fill=(61, 235, 255, 10), width=1)
    for x in range(0, BACKGROUND_SIZE[0], 256):
        draw.line((x, 0, x, BACKGROUND_SIZE[1]), fill=(80, 188, 255, 16), width=1)
    for y in range(0, BACKGROUND_SIZE[1], 256):
        draw.line((0, y, BACKGROUND_SIZE[0], y), fill=(80, 188, 255, 16), width=1)
    return image


def make_nebula() -> Image.Image:
    image = Image.new("RGBA", BACKGROUND_SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image, "RGBA")
    draw.ellipse(
        (70, 80, 690, 580),
        fill=(33, 136, 205, 24),
    )
    draw.ellipse(
        (850, 250, 1580, 880),
        fill=(103, 77, 210, 22),
    )
    return image.filter(ImageFilter.GaussianBlur(95))


def save_loop(
    frames: list[Image.Image],
    motion_path: Path,
    static_path: Path,
    duration: int,
) -> None:
    frames[0].save(
        motion_path,
        save_all=True,
        append_images=frames[1:],
        duration=duration,
        loop=0,
        lossless=False,
        quality=94,
        method=4,
        minimize_size=True,
    )
    frames[0].save(static_path, optimize=True)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    save_loop(
        render_star_loop(
            size=BACKGROUND_SIZE,
            count=BACKGROUND_COUNT,
            frames=BACKGROUND_FRAMES,
            seed=24001,
        ),
        OUTPUT_DIR / "background-motion.webp",
        OUTPUT_DIR / "background-static.png",
        STAR_DURATION_MS,
    )
    save_loop(
        render_star_loop(
            size=CARD_SIZE,
            count=CARD_COUNT,
            frames=CARD_FRAMES,
            seed=24002,
        ),
        OUTPUT_DIR / "card-motion.webp",
        OUTPUT_DIR / "card-static.png",
        STAR_DURATION_MS,
    )
    save_loop(
        render_constellation_loop(),
        OUTPUT_DIR / "constellation-motion.webp",
        OUTPUT_DIR / "constellation-static.png",
        CONSTELLATION_DURATION_MS,
    )
    make_grid().save(OUTPUT_DIR / "tech-grid.png", optimize=True)
    make_nebula().save(OUTPUT_DIR / "nebula-cloud.png", optimize=True)
    print(f"Generated particle assets in {OUTPUT_DIR}")


if __name__ == "__main__":
    main()

"""Design tokens for the convertible-bond assistant UI.

Visual direction
----------------
* Night-only deep charcoal theme (Apple HIG / Rams restraint).
* One single accent (amber) used sparingly for emphasis and primary actions.
* Neutral surfaces carry the layout; colour only encodes meaning
  (positive / negative / warning). No blue-purple gradient washes.
* Numerals are always rendered in a monospace face so columns stay aligned.

Everything here is pure data + tiny builders, so the UI layer stays declarative.
"""

from __future__ import annotations

from dataclasses import dataclass

try:
    import flet as ft
except ImportError:  # pragma: no cover - headless usage
    ft = None


def with_alpha(color: str, alpha: float) -> str:
    """Convert ``#RRGGBB`` to a translucent Flet ``#AARRGGBB`` colour."""
    value = (color or "").strip()
    if not value.startswith("#") or len(value) != 7:
        return value
    alpha_byte = max(0, min(255, round(alpha * 255)))
    return f"#{alpha_byte:02X}{value[1:].upper()}"


# --------------------------------------------------------------------------- #
# Typography
# --------------------------------------------------------------------------- #

SANS = "Inter"
SANS_FALLBACK = [
    "SF Pro Text",
    "Segoe UI",
    "PingFang SC",
    "Microsoft YaHei",
    "Noto Sans CJK SC",
    "Roboto",
    "sans-serif",
]

MONO = "JetBrains Mono"
MONO_FALLBACK = [
    "SF Mono",
    "Cascadia Mono",
    "Consolas",
    "Menlo",
    "Noto Sans Mono",
    "monospace",
]


# --------------------------------------------------------------------------- #
# Palette
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Palette:
    name: str
    is_dark: bool

    bg: str
    surface: str
    surface_alt: str
    surface_sunken: str
    border: str
    border_strong: str

    text: str
    text_muted: str
    text_faint: str

    accent: str
    accent_hover: str
    accent_soft: str
    on_accent: str

    positive: str
    positive_soft: str
    negative: str
    negative_soft: str
    neutral_soft: str

    shadow: str


LIGHT = Palette(
    name="light",
    is_dark=False,
    bg="#F5F3EE",
    surface="#FFFFFF",
    surface_alt="#FBFAF7",
    surface_sunken="#EFECE5",
    border="#E4DFD5",
    border_strong="#D5CFC2",
    text="#1B1A16",
    text_muted="#7C766A",
    text_faint="#A8A196",
    accent="#B07A1E",
    accent_hover="#96650F",
    accent_soft="#F6EBD6",
    on_accent="#FFFFFF",
    positive="#2E7D5B",
    positive_soft="#E2F0E8",
    negative="#B0473A",
    negative_soft="#F8E5E1",
    neutral_soft="#EFECE5",
    shadow="#14000000",
)

DARK = Palette(
    name="dark",
    is_dark=True,
    bg="#030711",
    surface="#07111F",
    surface_alt="#0A1A2D",
    surface_sunken="#040C16",
    border="#18364F",
    border_strong="#245B7A",
    text="#E6F1FF",
    text_muted="#91A5C3",
    text_faint="#5D708E",
    accent="#3DEBFF",
    accent_hover="#7DF2FF",
    accent_soft="#0C2A36",
    on_accent="#03111A",
    positive="#35D9A1",
    positive_soft="#103027",
    negative="#FF647C",
    negative_soft="#351923",
    neutral_soft="#102030",
    shadow="#80000A14",
)


def palette_for(dark: bool) -> Palette:
    return DARK if dark else LIGHT


# --------------------------------------------------------------------------- #
# Reusable builders
# --------------------------------------------------------------------------- #


def soft_shadow(p: Palette, blur: int = 20, y: int = 6) -> "ft.BoxShadow":
    return ft.BoxShadow(
        spread_radius=0,
        blur_radius=blur,
        color=p.shadow,
        blur_style=ft.BlurStyle.NORMAL,
        offset=ft.Offset(0, y),
    )


def card(
    p: Palette,
    content,
    *,
    padding: int = 20,
    radius: int = 16,
    bgcolor: str | None = None,
    border: str | None = None,
    on_click=None,
    ink: bool = False,
    shadow: bool = True,
    expand=None,
    on_hover=None,
    alignment=None,
    height=None,
):
    """The base surface used across the whole app."""
    # Keep the page's particle field visible through every card while retaining
    # enough contrast for dense tables and small labels.
    surface_color = bgcolor or p.surface
    if surface_color not in (None, "transparent", ft.Colors.TRANSPARENT):
        surface_color = with_alpha(surface_color, 0.88 if p.is_dark else 0.84)

    from console_particles import decorate_card

    decorated_content = decorate_card(content, p)
    resting_shadow = soft_shadow(p)
    resting_gradient = ft.LinearGradient(
        colors=[
            with_alpha(p.accent, 0.42),
            border if border is not None else p.border,
            with_alpha("#7B61FF", 0.32),
        ],
        begin=ft.Alignment(-1, -1),
        end=ft.Alignment(1, 1),
    )
    hover_gradient = ft.LinearGradient(
        colors=[
            with_alpha(p.accent, 0.82),
            with_alpha(p.accent_hover, 0.38),
            with_alpha("#8B7CFF", 0.55),
        ],
        begin=ft.Alignment(-1, -1),
        end=ft.Alignment(1, 1),
    )
    inner = ft.Container(
        content=decorated_content,
        padding=padding,
        bgcolor=surface_color,
        border_radius=max(1, radius - 1),
        alignment=alignment,
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        expand=True,
    )
    surface = ft.Container(
        content=inner,
        padding=1,
        gradient=resting_gradient,
        border_radius=radius,
        shadow=resting_shadow if shadow else None,
        on_click=on_click,
        expand=expand,
        height=height,
        ink=on_click is not None,
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        animate=ft.Animation(160, ft.AnimationCurve.EASE_OUT),
        animate_offset=ft.Animation(160, ft.AnimationCurve.EASE_OUT),
    )

    def handle_hover(event):
        hovered = event.data is True or str(event.data).lower() == "true"
        surface.offset = ft.Offset(0, -0.025 if hovered else 0)
        surface.gradient = hover_gradient if hovered else resting_gradient
        surface.shadow = (
            ft.BoxShadow(
                spread_radius=0,
                blur_radius=28,
                color=p.shadow,
                blur_style=ft.BlurStyle.NORMAL,
                offset=ft.Offset(0, 10),
            )
            if hovered and shadow
            else (resting_shadow if shadow else None)
        )
        try:
            surface.update()
        except Exception:
            pass
        if on_hover:
            on_hover(event)

    surface.on_hover = handle_hover
    return surface


def label(p: Palette, text: str, *, size: int = 11, color: str | None = None) -> "ft.Text":
    """Small uppercase-ish caption used above values and sections."""
    return ft.Text(
        text,
        size=size,
        color=color or p.text_faint,
        font_family=SANS,
        font_family_fallback=SANS_FALLBACK,
        weight=ft.FontWeight.W_500,
    )


def value(p: Palette, text: str, *, size: int = 26, color: str | None = None) -> "ft.Text":
    """Large numeral, monospaced so KPI tiles stay aligned."""
    return ft.Text(
        text,
        size=size,
        color=color or p.text,
        font_family=MONO,
        font_family_fallback=MONO_FALLBACK,
        weight=ft.FontWeight.W_600,
    )


def mono(text: str, *, size: int = 13, color: str | None = None, weight=None) -> "ft.Text":
    return ft.Text(
        text,
        size=size,
        color=color,
        font_family=MONO,
        font_family_fallback=MONO_FALLBACK,
        weight=weight or ft.FontWeight.W_400,
    )


def section_title(p: Palette, title: str, subtitle: str | None = None):
    """Card header: strong title + optional supporting line."""
    children = [
        ft.Text(
            title,
            size=16,
            color=p.text,
            font_family=SANS,
            font_family_fallback=SANS_FALLBACK,
            weight=ft.FontWeight.W_600,
        )
    ]
    if subtitle:
        children.append(
            ft.Text(
                subtitle,
                size=12,
                color=p.text_muted,
                font_family=SANS,
                font_family_fallback=SANS_FALLBACK,
            )
        )
    return ft.Column(children, spacing=3, tight=True)


def chip(p: Palette, text: str, *, tone: str = "neutral", size: int = 12):
    """Compact pill used for tags, statuses and source labels."""
    tones = {
        "neutral": (p.neutral_soft, p.text_muted),
        "accent": (p.accent_soft, p.accent),
        "positive": (p.positive_soft, p.positive),
        "negative": (p.negative_soft, p.negative),
    }
    bg, fg = tones.get(tone, tones["neutral"])
    return ft.Container(
        content=ft.Text(
            text,
            size=size,
            color=fg,
            font_family=SANS,
            font_family_fallback=SANS_FALLBACK,
            weight=ft.FontWeight.W_500,
        ),
        padding=ft.Padding.symmetric(horizontal=10, vertical=4),
        bgcolor=bg,
        border_radius=999,
    )


def stat_tile(p: Palette, caption: str, value_text: str, *, hint: str = "", tone: str = "neutral"):
    """KPI tile: caption, monospaced value, optional hint line."""
    tones = {
        "neutral": (p.text, p.text_faint),
        "accent": (p.accent, p.accent),
        "positive": (p.positive, p.positive),
        "negative": (p.negative, p.negative),
    }
    fg, hint_fg = tones.get(tone, tones["neutral"])
    children = [
        label(p, caption),
        ft.Container(height=8),
        value(p, value_text, size=28, color=fg),
    ]
    if hint:
        children += [
            ft.Container(height=4),
            ft.Text(
                hint,
                size=11,
                color=hint_fg,
                font_family=SANS,
                font_family_fallback=SANS_FALLBACK,
            ),
        ]
    return card(p, ft.Column(children, spacing=0, tight=True), padding=18, height=132)


def table_style(p: Palette):
    """Shared DataTable chrome so every table reads as one system."""
    return dict(
        border_radius=10,
        border=ft.Border.all(1, p.border),
        horizontal_lines=ft.BorderSide(1, p.border),
        vertical_lines=ft.BorderSide(0, p.border),
        heading_row_color=p.surface_sunken,
        heading_text_style=ft.TextStyle(
            size=11,
            color=p.text_muted,
            weight=ft.FontWeight.W_600,
            font_family=SANS,
            font_family_fallback=SANS_FALLBACK,
        ),
        data_text_style=ft.TextStyle(
            size=13,
            color=p.text,
            font_family=SANS,
            font_family_fallback=SANS_FALLBACK,
        ),
        column_spacing=18,
        horizontal_margin=14,
        data_row_min_height=42,
    )


def empty_state(p: Palette, title: str, hint: str):
    return ft.Container(
        content=ft.Column(
            [
                ft.Text(
                    title,
                    size=14,
                    color=p.text_muted,
                    font_family=SANS,
                    font_family_fallback=SANS_FALLBACK,
                    weight=ft.FontWeight.W_600,
                ),
                ft.Container(height=6),
                ft.Text(
                    hint,
                    size=12,
                    color=p.text_faint,
                    font_family=SANS,
                    font_family_fallback=SANS_FALLBACK,
                ),
            ],
            spacing=0,
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=ft.Padding.symmetric(vertical=36, horizontal=20),
        alignment=ft.Alignment.CENTER,
    )


def build_page_theme(dark: bool):
    """Material theme for Flet chrome that we do not style manually."""
    p = palette_for(dark)
    return ft.Theme(
        color_scheme_seed=p.accent,
        use_material3=True,
        font_family=SANS,
        scaffold_bgcolor=p.bg,
        canvas_color=p.bg,
        divider_color=p.border,
        splash_color=p.accent_soft,
        highlight_color=p.accent_soft,
        hover_color=p.surface_alt,
        visual_density=ft.VisualDensity.STANDARD,
        card_theme=ft.CardTheme(
            color=p.surface,
            elevation=0,
            margin=0,
            shape=ft.RoundedRectangleBorder(radius=16),
        ),
    )

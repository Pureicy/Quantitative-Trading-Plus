"""Client-side particle layers for the Flet desktop console.

Flet Canvas is server-driven. Updating thousands of point coordinates from
Python every frame competes with pointer events and makes the whole UI feel
laggy. The console therefore uses transparent, seamless WebP loops that Flutter
animates locally. Python only swaps between animated/static layers when the
user toggles performance modes.
"""

from __future__ import annotations

from dataclasses import dataclass

try:
    import flet as ft
except ImportError:  # pragma: no cover - headless test environment
    ft = None


BACKGROUND_PARTICLE_COUNT = 4000
CARD_PARTICLE_COUNT = 36

BACKGROUND_MOTION_SRC = "assets/particles/background-motion.webp"
BACKGROUND_STATIC_SRC = "assets/particles/background-static.png"
CONSTELLATION_MOTION_SRC = "assets/particles/constellation-motion.webp"
CONSTELLATION_STATIC_SRC = "assets/particles/constellation-static.png"
NEBULA_SRC = "assets/particles/nebula-cloud.png"
GRID_SRC = "assets/particles/tech-grid.png"
CARD_MOTION_SRC = "assets/particles/card-motion.webp"
CARD_STATIC_SRC = "assets/particles/card-static.png"


def _alpha(color: str, alpha: float) -> str:
    value = (color or "").strip()
    if not value.startswith("#") or len(value) != 7:
        return value
    alpha_byte = max(0, min(255, round(alpha * 255)))
    return f"#{alpha_byte:02X}{value[1:].upper()}"


_card_effects_enabled = True
_card_quality = "performance"


def begin_card_frame(enabled: bool = True, quality: str = "performance") -> None:
    """Set the particle state used by subsequent card builders."""
    global _card_effects_enabled, _card_quality
    _card_effects_enabled = bool(enabled)
    _card_quality = "power" if quality == "power" else "performance"


def card_effects_enabled() -> bool:
    return _card_effects_enabled


def _particle_image(
    src: str,
    *,
    visible: bool,
    fit: str,
    absolute: bool = False,
) -> object:
    image = ft.Image(
        src=src,
        visible=visible,
        fit=fit,
        gapless_playback=True,
        filter_quality=ft.FilterQuality.HIGH,
        anti_alias=True,
    )
    if absolute:
        image.left = 0
        image.top = 0
        image.right = 0
        image.bottom = 0
    else:
        image.expand = True
    return image


def decorate_card(content, _palette) -> object:
    """Put a client-animated particle layer behind a card's controls."""
    if ft is None or not _card_effects_enabled:
        return content

    motion = _particle_image(
        CARD_MOTION_SRC,
        visible=_card_quality == "performance",
        fit=ft.BoxFit.COVER,
        absolute=True,
    )
    static = _particle_image(
        CARD_STATIC_SRC,
        visible=_card_quality == "power",
        fit=ft.BoxFit.COVER,
        absolute=True,
    )
    corner_color = _alpha("#3DEBFF", 0.48)
    corners = [
        ft.Container(left=10, top=10, width=12, height=1, bgcolor=corner_color),
        ft.Container(left=10, top=10, width=1, height=12, bgcolor=corner_color),
        ft.Container(right=10, top=10, width=12, height=1, bgcolor=corner_color),
        ft.Container(right=10, top=10, width=1, height=12, bgcolor=corner_color),
        ft.Container(left=10, bottom=10, width=12, height=1, bgcolor=corner_color),
        ft.Container(left=10, bottom=10, width=1, height=12, bgcolor=corner_color),
        ft.Container(right=10, bottom=10, width=12, height=1, bgcolor=corner_color),
        ft.Container(right=10, bottom=10, width=1, height=12, bgcolor=corner_color),
    ]
    return ft.Stack(
        controls=[motion, static, content, *corners],
        fit=ft.StackFit.LOOSE,
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
    )


@dataclass
class ParticleState:
    enabled: bool
    quality: str


class ConsoleParticleController:
    """Build the background layers and apply lightweight pointer parallax."""

    def __init__(self, page, *, quality: str) -> None:
        self.page = page
        self.state = ParticleState(enabled=True, quality=quality)
        self.background_scene = None
        self.background_motion = None
        self.background_static = None
        self.constellation_motion = None
        self.constellation_static = None
        self.mobile = self._detect_mobile()
        self.parallax_x = 0.0
        self.parallax_y = 0.0
        self.target_x = 0.0
        self.target_y = 0.0

    @property
    def enabled(self) -> bool:
        return self.state.enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self.state.enabled = bool(value)

    def _detect_mobile(self) -> bool:
        platform = str(getattr(self.page, "platform", "")).lower()
        user_agent = str(getattr(self.page, "client_user_agent", "")).lower()
        return (
            any(token in platform for token in ("android", "ios"))
            or "mobile" in user_agent
            or "android" in user_agent
            or "iphone" in user_agent
        )

    def set_options(self, quality: str) -> None:
        self.state.quality = "power" if quality == "power" else "performance"
        if self.state.quality == "power":
            self.reset_parallax()

    def build_background(self, _dark: bool = True) -> object:
        if not self.enabled or ft is None:
            self.background_scene = None
            self.background_motion = None
            self.background_static = None
            self.constellation_motion = None
            self.constellation_static = None
            return ft.Container(expand=True, bgcolor=ft.Colors.TRANSPARENT)

        self.background_motion = _particle_image(
            BACKGROUND_MOTION_SRC,
            visible=self.state.quality == "performance",
            fit=ft.BoxFit.COVER,
        )
        self.background_static = _particle_image(
            BACKGROUND_STATIC_SRC,
            visible=self.state.quality == "power",
            fit=ft.BoxFit.COVER,
        )
        self.constellation_motion = _particle_image(
            CONSTELLATION_MOTION_SRC,
            visible=self.state.quality == "performance",
            fit=ft.BoxFit.COVER,
        )
        self.constellation_static = _particle_image(
            CONSTELLATION_STATIC_SRC,
            visible=self.state.quality == "power",
            fit=ft.BoxFit.COVER,
        )
        nebula = _particle_image(
            NEBULA_SRC,
            visible=True,
            fit=ft.BoxFit.COVER,
        )
        grid = _particle_image(
            GRID_SRC,
            visible=True,
            fit=ft.BoxFit.COVER,
        )
        grid.opacity = 0.72
        self.background_scene = ft.Stack(
            controls=[
                nebula,
                self.background_motion,
                self.background_static,
                self.constellation_motion,
                self.constellation_static,
                grid,
            ],
            expand=True,
            fit=ft.StackFit.EXPAND,
            animate_offset=ft.Animation(120, ft.AnimationCurve.EASE_OUT),
        )
        return self.background_scene

    def parallax_enabled(self, width: float | None = None) -> bool:
        viewport_width = float(width or getattr(self.page, "width", 0) or 0)
        return (
            self.enabled
            and self.state.quality == "performance"
            and not self.mobile
            and viewport_width >= 768
        )

    def set_parallax_position(
        self,
        local_x: float,
        local_y: float,
        width: float,
        height: float,
    ) -> None:
        if not self.parallax_enabled(width) or width <= 0 or height <= 0:
            self.reset_parallax()
            return
        ndc_x = (float(local_x) / float(width)) * 2.0 - 1.0
        ndc_y = -(float(local_y) / float(height)) * 2.0 + 1.0
        limit = 0.5
        self.target_x = max(-limit, min(ndc_x * limit, limit))
        self.target_y = max(-limit, min(ndc_y * limit * 0.6, limit))
        self.parallax_x += (self.target_x - self.parallax_x) * 0.22
        self.parallax_y += (self.target_y - self.parallax_y) * 0.22
        self._apply_parallax()

    def reset_parallax(self) -> None:
        self.target_x = 0.0
        self.target_y = 0.0
        self.parallax_x = 0.0
        self.parallax_y = 0.0
        self._apply_parallax()

    def _apply_parallax(self) -> None:
        if not self.background_scene:
            return
        self.background_scene.offset = ft.Offset(
            -self.parallax_x * 0.012,
            self.parallax_y * 0.008,
        )
        try:
            self.background_scene.update()
        except Exception:
            pass

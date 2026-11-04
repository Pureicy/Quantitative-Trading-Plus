"""Cinematic startup sequence for the Flet console."""

from __future__ import annotations

import asyncio
import math
import random

try:
    import flet as ft
except ImportError:  # pragma: no cover - headless tests
    ft = None


CYAN = "#3DEBFF"
VIOLET = "#8B7CFF"
TEXT = "#E6F1FF"
MUTED = "#91A5C3"

class SplashScreen:
    def __init__(self, page, on_finish) -> None:
        self.page = page
        self.on_finish = on_finish
        self.active = True
        self.finished = False
        self.overlay = None
        self.ray_layer = None
        self.hud = None
        self.boot_ring = None
        self.title = None
        self.subtitle = None
        self.progress = None
        self.status_lines = []
        viewport_width = float(getattr(self.page, "width", 0) or 1480)
        viewport_height = float(getattr(self.page, "height", 0) or 920)
        self.center_x = viewport_width / 2
        self.center_y = viewport_height / 2
        self.ray_target_length = math.hypot(viewport_width, viewport_height) * 1.35

    def build(self):
        self.hud = ft.Image(
            src="assets/intro/intro-hud.webp",
            width=520,
            height=520,
            fit=ft.BoxFit.CONTAIN,
            gapless_playback=True,
            filter_quality=ft.FilterQuality.HIGH,
            anti_alias=True,
            opacity=0,
            scale=0.82,
            animate_opacity=ft.Animation(620, ft.AnimationCurve.EASE_OUT),
            animate_scale=ft.Animation(760, ft.AnimationCurve.EASE_OUT),
        )
        self.boot_ring = ft.ProgressRing(
            width=38,
            height=38,
            stroke_width=1.5,
            color=CYAN,
            opacity=0.75,
            animate_opacity=ft.Animation(260, ft.AnimationCurve.EASE_OUT),
        )
        self.title = ft.Text(
            "双低量化",
            size=44,
            color=TEXT,
            weight=ft.FontWeight.W_700,
            opacity=0,
            scale=0.94,
            animate_opacity=ft.Animation(420, ft.AnimationCurve.EASE_OUT),
            animate_scale=ft.Animation(520, ft.AnimationCurve.EASE_OUT),
        )
        self.subtitle = ft.Text(
            "DOUBLE-LOW QUANT ENGINE",
            size=12,
            color=CYAN,
            opacity=0,
            animate_opacity=ft.Animation(360, ft.AnimationCurve.EASE_OUT),
        )
        self.progress = ft.ProgressBar(
            value=0,
            width=310,
            bar_height=3,
            color=CYAN,
            bgcolor="#203248",
            border_radius=999,
            track_gap=0,
            stop_indicator_radius=0,
        )
        self.status_lines = [
            ft.Text(
                text,
                size=10,
                color=MUTED,
                opacity=0,
                text_align=ft.TextAlign.CENTER,
                font_family="JetBrains Mono",
                font_family_fallback=["Consolas", "monospace"],
                animate_opacity=ft.Animation(220, ft.AnimationCurve.EASE_OUT),
            )
            for text in (
                "INITIALIZING MARKET ENGINE",
                "LOADING LOCAL SNAPSHOTS",
                "SYNCING PARTICLE MATRIX",
                "SYSTEM READY",
            )
        ]
        boot_marker = ft.Container(
            content=self.boot_ring,
            width=64,
            height=64,
            alignment=ft.Alignment.CENTER,
            border_radius=32,
            border=ft.Border.all(1, "#303DEBFF"),
        )
        content = ft.Column(
            [
                ft.Text(
                    "QUANTUM MARKET SYSTEM // BOOT",
                    size=9,
                    color=CYAN,
                    font_family="JetBrains Mono",
                    font_family_fallback=["Consolas", "monospace"],
                ),
                ft.Container(height=16),
                boot_marker,
                ft.Container(height=20),
                self.title,
                ft.Container(height=5),
                self.subtitle,
                ft.Container(height=20),
                self.progress,
                ft.Container(height=16),
                ft.Column(
                    self.status_lines,
                    spacing=5,
                    tight=True,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Container(height=16),
                ft.Text("点击任意位置跳过", size=10, color="#5D7597"),
            ],
            spacing=0,
            tight=True,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )
        self.ray_layer = ft.Stack(
            controls=[],
            expand=True,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
        )
        self.overlay = ft.GestureDetector(
            expand=True,
            on_tap=lambda _event: self.skip(),
            content=ft.Stack(
                controls=[
                    ft.Container(expand=True, bgcolor="#030711"),
                    self.ray_layer,
                    ft.Container(
                        content=self.hud,
                        expand=True,
                        alignment=ft.Alignment.CENTER,
                    ),
                    ft.Container(
                        content=content,
                        expand=True,
                        alignment=ft.Alignment.CENTER,
                    ),
                    ft.Container(
                        width=6,
                        height=6,
                        border_radius=3,
                        bgcolor=CYAN,
                        bottom=28,
                        right=30,
                    ),
                ],
                expand=True,
                fit=ft.StackFit.EXPAND,
            ),
        )
        return self.overlay

    async def play(self) -> None:
        if self.finished:
            return
        await self._play_full()
        if self.finished:
            return
        self.overlay.animate_opacity = ft.Animation(280, ft.AnimationCurve.EASE_OUT)
        self.overlay.opacity = 0
        self._update()
        await asyncio.sleep(0.32)
        self.finish()

    async def _play_full(self) -> None:
        await asyncio.sleep(0.6)
        if self.finished:
            return
        self.boot_ring.opacity = 1
        self._update()

        await asyncio.sleep(0.4)
        if self.finished:
            return
        await self._spawn_ray_wave(0)

        await asyncio.sleep(0.35)
        if self.finished:
            return
        await self._spawn_ray_wave(1)

        await asyncio.sleep(0.35)
        if self.finished:
            return
        await self._spawn_ray_wave(2)

        await asyncio.sleep(0.7)
        if self.finished:
            return
        self.hud.opacity = 1
        self.hud.scale = 1
        self.progress.value = 0.18
        self._update()

        await asyncio.sleep(0.95)
        if self.finished:
            return
        self.boot_ring.opacity = 0
        self.boot_ring.visible = False
        self.ray_layer.controls.clear()
        self._update()

        await asyncio.sleep(1.0)
        if self.finished:
            return
        self.title.opacity = 1
        self.title.scale = 1
        self.subtitle.opacity = 1
        self.progress.value = 0.34
        self._update()

        await asyncio.sleep(0.8)
        if self.finished:
            return
        self._show_status(0)
        self.progress.value = 0.54
        self._update()

        await asyncio.sleep(0.3)
        if self.finished:
            return
        self._show_status(1)
        self.progress.value = 0.7
        self._update()

        await asyncio.sleep(0.3)
        if self.finished:
            return
        self._show_status(2)
        self.progress.value = 0.86
        self._update()

        await asyncio.sleep(0.3)
        if self.finished:
            return
        self._show_status(3)
        self.status_lines[3].color = CYAN
        self.progress.value = 1
        self._update()

        await asyncio.sleep(0.77)

    async def _spawn_ray_wave(self, wave_index: int) -> None:
        rng = random.Random(1200 + wave_index)
        rays = []
        for index in range(48):
            angle = math.tau * index / 48 + rng.uniform(-0.035, 0.035)
            duration = rng.randint(1200, 1500)
            blur = rng.choice((0, 0, 1))
            height = rng.uniform(1.0, 1.8)
            colors = (
                ("#003DEBFF", "#B83DEBFF", "#FFDFF9FF")
                if index % 4
                else ("#007B61FF", "#B88B7CFF", "#FFF0DDFF")
            )
            ray = ft.Container(
                left=self.center_x,
                top=self.center_y - height / 2,
                width=2,
                height=height,
                gradient=ft.LinearGradient(
                    colors=list(colors),
                    begin=ft.Alignment(-1, 0),
                    end=ft.Alignment(1, 0),
                ),
                border_radius=height / 2,
                blur=blur,
                opacity=0.95,
                rotate=ft.Rotate(
                    angle=angle,
                    alignment=ft.Alignment(-1, 0),
                ),
                animate=ft.Animation(duration, ft.AnimationCurve.LINEAR),
                animate_opacity=ft.Animation(duration, ft.AnimationCurve.EASE_IN),
            )
            rays.append(ray)
        self.ray_layer.controls.extend(rays)
        self._update()
        # Give Flutter one rendered frame to commit the initial 2px width.
        # Updating in the same frame would jump straight to the final size.
        await asyncio.sleep(0.12)
        if self.finished:
            return
        for ray in rays:
            ray.width = self.ray_target_length
            ray.opacity = 0
        self._update()

    def _show_status(self, index: int) -> None:
        self.status_lines[index].opacity = 0.9

    def _update(self) -> None:
        try:
            self.page.update()
        except Exception:
            pass

    def skip(self) -> None:
        if self.finished:
            return
        self.finish()

    def finish(self) -> None:
        if self.finished:
            return
        self.finished = True
        self.active = False
        self.on_finish()

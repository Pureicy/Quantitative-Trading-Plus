"""Sci-fi market scan overlay for the Flet console."""

from __future__ import annotations

from dataclasses import dataclass

try:
    import flet as ft
except ImportError:  # pragma: no cover - headless tests
    ft = None


BACKGROUND = "#050B16"
SURFACE = "#071523"
SURFACE_ALT = "#0A1C30"
BORDER = "#1D4A6B"
CYAN = "#3DEBFF"
CYAN_SOFT = "#AF3DEBFF"
VIOLET = "#8B7CFF"
GREEN = "#35D9A1"
RED = "#FF647C"
TEXT = "#E6F1FF"
MUTED = "#8DA4C5"
FAINT = "#5D7597"


@dataclass(frozen=True)
class StageSpec:
    key: str
    title: str
    subtitle: str


STAGES = (
    StageSpec("MARKET_MATRIX", "MARKET MATRIX", "全市场可转债快照"),
    StageSpec("REDEEM_SHIELD", "REDEEM SHIELD", "强赎风险过滤"),
    StageSpec("LOCAL_PORTFOLIO", "LOCAL PORTFOLIO", "持仓与自选映射"),
    StageSpec("DOUBLE_LOW_RANK", "DOUBLE-LOW RANK", "双低评分与排序"),
    StageSpec("SNAPSHOT_ARCHIVE", "SNAPSHOT ARCHIVE", "写入本地快照"),
    StageSpec("REVIEW_SYNTHESIS", "REVIEW SYNTHESIS", "生成快照复盘"),
)

STAGE_INDEX = {stage.key: index for index, stage in enumerate(STAGES)}


class ScanHUD:
    """Mutable overlay whose text changes while its animation stays client-side."""

    def __init__(self, page) -> None:
        self.page = page
        self.active = False
        self.minimized = False
        self.completed = False
        self.failed = False
        self.current_stage = "PREPARE"
        self.current_detail = "正在初始化扫描环境"
        self.metrics: dict = {}
        self.rows: dict[str, dict] = {}
        self.overlay = None
        self.progress_bar = None
        self.percent_text = None
        self.stage_text = None
        self.detail_text = None
        self.elapsed_text = None
        self.mini_bar = None
        self.mini_progress = None
        self.mini_status = None
        self.minimize_button = None
        self.error_actions = None
        self.on_retry = None
        self.on_close = None

    def begin(self) -> None:
        self.active = True
        self.minimized = False
        self.completed = False
        self.failed = False
        self.current_stage = "PREPARE"
        self.current_detail = "正在初始化扫描环境"
        self.metrics = {}

    def build(self) -> object:
        self.rows = {}
        self.progress_bar = ft.ProgressBar(
            value=0,
            bar_height=6,
            color=CYAN,
            bgcolor="#14263A",
            border_radius=999,
            track_gap=0,
            stop_indicator_radius=0,
        )
        self.percent_text = ft.Text(
            "0%",
            size=16,
            color=CYAN,
            weight=ft.FontWeight.W_700,
            font_family="JetBrains Mono",
            font_family_fallback=["Consolas", "monospace"],
        )
        self.detail_text = ft.Text(
            self.current_detail,
            size=12,
            color=MUTED,
            max_lines=1,
            overflow=ft.TextOverflow.ELLIPSIS,
        )
        self.stage_text = ft.Text(
            self.current_stage,
            size=10,
            color=CYAN,
            weight=ft.FontWeight.W_700,
            font_family="JetBrains Mono",
            font_family_fallback=["Consolas", "monospace"],
        )
        self.elapsed_text = ft.Text(
            "00:00.0",
            size=11,
            color=FAINT,
            font_family="JetBrains Mono",
            font_family_fallback=["Consolas", "monospace"],
        )
        self.minimize_button = ft.TextButton(
            content=ft.Text("后台运行", size=12),
            visible=False,
            on_click=lambda _event: self.set_minimized(True),
            style=ft.ButtonStyle(color=MUTED),
        )
        retry_button = ft.Button(
            content=ft.Text("重新扫描", size=12, color=BACKGROUND),
            on_click=lambda _event: self._retry(),
            style=ft.ButtonStyle(
                bgcolor=CYAN,
                color=BACKGROUND,
                padding=ft.Padding.symmetric(horizontal=16, vertical=10),
                shape=ft.RoundedRectangleBorder(radius=9),
            ),
        )
        close_button = ft.OutlinedButton(
            content=ft.Text("关闭", size=12, color=MUTED),
            on_click=lambda _event: self._close(),
            style=ft.ButtonStyle(
                side=ft.BorderSide(1, BORDER),
                padding=ft.Padding.symmetric(horizontal=16, vertical=10),
                shape=ft.RoundedRectangleBorder(radius=9),
            ),
        )
        self.error_actions = ft.Row(
            [retry_button, close_button],
            visible=False,
            spacing=10,
            tight=True,
        )

        rows = [self._build_stage_row(index, stage) for index, stage in enumerate(STAGES)]
        radar = ft.Image(
            src="assets/scan/radar-sweep.webp",
            width=220,
            height=220,
            fit=ft.BoxFit.CONTAIN,
            gapless_playback=True,
            filter_quality=ft.FilterQuality.HIGH,
            anti_alias=True,
        )
        panel = ft.Container(
            width=720,
            height=470,
            padding=24,
            border_radius=18,
            gradient=ft.LinearGradient(
                colors=[SURFACE, SURFACE_ALT],
                begin=ft.Alignment(-1, -1),
                end=ft.Alignment(1, 1),
            ),
            border=ft.Border.all(1, BORDER),
            shadow=ft.BoxShadow(
                blur_radius=38,
                spread_radius=0,
                color="#660C6C8E",
                offset=ft.Offset(0, 16),
            ),
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Text(
                                        "MARKET RADAR SCAN",
                                        size=11,
                                        color=CYAN,
                                        weight=ft.FontWeight.W_700,
                                        font_family="JetBrains Mono",
                                        font_family_fallback=["Consolas", "monospace"],
                                    ),
                                    ft.Text(
                                        "双低量化扫描矩阵",
                                        size=22,
                                        color=TEXT,
                                        weight=ft.FontWeight.W_700,
                                    ),
                                ],
                                spacing=2,
                                tight=True,
                            ),
                            ft.Container(expand=True),
                            ft.Column(
                                [
                                    ft.Text(
                                        "DATA LINK",
                                        size=10,
                                        color=FAINT,
                                        text_align=ft.TextAlign.RIGHT,
                                    ),
                                    self.elapsed_text,
                                ],
                                spacing=2,
                                tight=True,
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.START,
                    ),
                    ft.Container(height=16),
                    ft.Row(
                        [
                            ft.Container(
                                content=radar,
                                width=238,
                                height=238,
                                alignment=ft.Alignment.CENTER,
                                border=ft.Border.all(1, "#173B58"),
                                border_radius=119,
                                bgcolor="#8A040C16",
                            ),
                            ft.Container(width=18),
                            ft.Column(rows, spacing=7, tight=True, expand=True),
                        ],
                        spacing=0,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Container(expand=True),
                    ft.Row(
                        [
                            self.stage_text,
                            ft.Container(expand=True),
                            self.percent_text,
                        ],
                        spacing=8,
                    ),
                    ft.Container(height=7),
                    self.progress_bar,
                    ft.Container(height=9),
                    ft.Row(
                        [
                            self.detail_text,
                            ft.Container(expand=True),
                            self.minimize_button,
                        ],
                        spacing=12,
                    ),
                    self.error_actions,
                ],
                spacing=0,
                tight=True,
            ),
        )

        full = ft.Container(
            content=panel,
            expand=True,
            bgcolor="#AD020711",
            alignment=ft.Alignment.CENTER,
            visible=not self.minimized,
        )
        self.mini_progress = ft.ProgressRing(
            width=16,
            height=16,
            stroke_width=2,
            color=CYAN,
            visible=True,
        )
        self.mini_status = ft.Text(
            "扫描中 · 0%",
            size=12,
            color=TEXT,
            weight=ft.FontWeight.W_600,
        )
        self.mini_bar = ft.Container(
            content=ft.Row(
                [
                    self.mini_progress,
                    ft.Column(
                        [
                            ft.Text(
                                "MARKET RADAR SCAN",
                                size=9,
                                color=CYAN,
                                font_family="JetBrains Mono",
                                font_family_fallback=["Consolas", "monospace"],
                            ),
                            self.mini_status,
                        ],
                        spacing=1,
                        tight=True,
                    ),
                ],
                spacing=10,
                tight=True,
            ),
            width=286,
            height=58,
            top=14,
            right=20,
            padding=ft.Padding.symmetric(horizontal=14, vertical=9),
            border_radius=12,
            bgcolor="#E6071523",
            border=ft.Border.all(1, BORDER),
            visible=self.minimized,
        )
        self.overlay = ft.Stack(
            controls=[full, self.mini_bar],
            expand=True,
            fit=ft.StackFit.EXPAND,
        )
        return self.overlay

    def _build_stage_row(self, index: int, stage: StageSpec):
        dot = ft.Container(
            width=7,
            height=7,
            border_radius=4,
            bgcolor=FAINT,
        )
        spinner = ft.ProgressRing(
            width=13,
            height=13,
            stroke_width=1.8,
            color=CYAN,
            visible=False,
        )
        title = ft.Text(stage.title, size=11, color=MUTED, weight=ft.FontWeight.W_600)
        subtitle = ft.Text(stage.subtitle, size=10, color=FAINT)
        status = ft.Text(
            "WAITING",
            size=9,
            color=FAINT,
            text_align=ft.TextAlign.RIGHT,
        )
        row = ft.Container(
            content=ft.Row(
                [
                    dot,
                    ft.Column([title, subtitle], spacing=1, tight=True, expand=True),
                    spinner,
                    status,
                ],
                spacing=9,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=10, vertical=6),
            border_radius=8,
            bgcolor="#38071423",
        )
        self.rows[stage.key] = {
            "row": row,
            "dot": dot,
            "spinner": spinner,
            "title": title,
            "subtitle": subtitle,
            "status": status,
        }
        return row

    def apply_progress(self, progress) -> None:
        self.current_stage = progress.stage
        self.current_detail = progress.detail or progress.label
        if self.stage_text:
            self.stage_text.value = progress.stage
        if progress.metrics:
            self.metrics.update(progress.metrics)
        self._refresh_stage_rows(progress.stage)
        if self.completed:
            return
        if self.percent_text:
            self.percent_text.value = f"{progress.percent}%"
        if self.detail_text:
            self.detail_text.value = progress.detail or progress.label
        if self.mini_status:
            self.mini_status.value = f"{progress.percent}% · {progress.label}"

    def set_display_percent(self, percent: float) -> None:
        bounded = max(0.0, min(float(percent), 100.0))
        if self.progress_bar:
            self.progress_bar.value = bounded / 100.0
        if self.percent_text:
            self.percent_text.value = f"{int(round(bounded))}%"
        if self.mini_status:
            self.mini_status.value = f"扫描中 · {int(round(bounded))}%"

    def set_elapsed(self, seconds: float) -> None:
        if not self.elapsed_text:
            return
        minutes = int(seconds // 60)
        remaining = seconds - minutes * 60
        self.elapsed_text.value = f"{minutes:02d}:{remaining:04.1f}"
        if seconds >= 3 and self.minimize_button and not self.failed:
            self.minimize_button.visible = True

    def set_minimized(self, minimized: bool) -> None:
        self.minimized = bool(minimized)
        if self.overlay and self.overlay.controls:
            self.overlay.controls[0].visible = not self.minimized
            self.overlay.controls[1].visible = self.minimized
        try:
            self.page.update()
        except Exception:
            pass

    def show_complete(self) -> None:
        self.completed = True
        self.current_stage = "SCAN COMPLETE"
        self.current_detail = "候选池与快照复盘已就绪"
        for controls in self.rows.values():
            self._set_row_state(controls, "done")
        if self.progress_bar:
            self.progress_bar.value = 1
            self.progress_bar.color = GREEN
        if self.percent_text:
            self.percent_text.value = "100%"
            self.percent_text.color = GREEN
        if self.stage_text:
            self.stage_text.value = "SCAN COMPLETE"
            self.stage_text.color = GREEN
        if self.detail_text:
            self.detail_text.value = "SCAN COMPLETE · 正在载入结果"
            self.detail_text.color = GREEN
        if self.minimize_button:
            self.minimize_button.visible = False
        if self.mini_status:
            self.mini_status.value = "扫描完成"
        if self.mini_progress:
            self.mini_progress.visible = False
        try:
            self.page.update()
        except Exception:
            pass

    def show_error(self, message: str) -> None:
        failed_stage = self.current_stage
        failed_index = STAGE_INDEX.get(failed_stage, -1)
        self.failed = True
        self.minimized = False
        if self.overlay and self.overlay.controls:
            self.overlay.controls[0].visible = True
            self.overlay.controls[1].visible = False
        self.current_stage = "SCAN INTERRUPTED"
        self.current_detail = message
        for key, controls in self.rows.items():
            stage_index = STAGE_INDEX.get(key, len(STAGES))
            if stage_index < failed_index:
                self._set_row_state(controls, "done")
            elif stage_index == failed_index:
                self._set_row_state(controls, "failed")
            else:
                self._set_row_state(controls, "waiting")
        if self.progress_bar:
            self.progress_bar.color = RED
        if self.stage_text:
            self.stage_text.value = "SCAN INTERRUPTED"
            self.stage_text.color = RED
        if self.detail_text:
            self.detail_text.value = message
            self.detail_text.color = RED
        if self.minimize_button:
            self.minimize_button.visible = False
        if self.error_actions:
            self.error_actions.visible = True
        if self.mini_status:
            self.mini_status.value = "扫描失败"
        if self.mini_progress:
            self.mini_progress.color = RED
        try:
            self.page.update()
        except Exception:
            pass

    def finish(self) -> None:
        self.active = False
        self.minimized = False
        self.overlay = None

    def _refresh_stage_rows(self, stage: str) -> None:
        current_index = STAGE_INDEX.get(stage, len(STAGES))
        for index, spec in enumerate(STAGES):
            state = "waiting"
            if current_index >= len(STAGES) or index < current_index:
                state = "done"
            elif index == current_index:
                state = "active"
            self._set_row_state(self.rows.get(spec.key), state)

    def _set_row_state(self, controls: dict | None, state: str) -> None:
        if not controls:
            return
        colors = {
            "waiting": FAINT,
            "active": CYAN,
            "done": GREEN,
            "failed": RED,
        }
        labels = {
            "waiting": "WAITING",
            "active": "SCANNING",
            "done": "DONE",
            "failed": "FAILED",
        }
        color = colors[state]
        controls["dot"].bgcolor = color
        controls["title"].color = TEXT if state != "waiting" else MUTED
        controls["subtitle"].color = MUTED if state != "waiting" else FAINT
        controls["status"].value = labels[state]
        controls["status"].color = color
        controls["spinner"].visible = state == "active"
        controls["row"].bgcolor = "#5C0A2233" if state == "active" else "#38071423"
        if state == "done":
            metric = self._metric_text(controls)
            if metric:
                controls["status"].value = metric

    def _metric_text(self, controls: dict) -> str:
        status = controls["status"]
        metric_values = {
            "MARKET MATRIX": self.metrics.get("market_count"),
            "REDEEM SHIELD": self.metrics.get("redeem_count"),
            "DOUBLE-LOW RANK": self.metrics.get("candidate_count"),
        }
        value = metric_values.get(controls["title"].value)
        return f"{value} 只" if value is not None else status.value

    def _retry(self) -> None:
        if callable(self.on_retry):
            self.on_retry()

    def _close(self) -> None:
        if callable(self.on_close):
            self.on_close()

"""Personal convertible-bond "double-low" scanner — Flet desktop UI.

Design direction
----------------
Night-only deep charcoal theme with one amber accent used sparingly,
generous spacing, monospaced numerals. The layout is a fixed
navigation rail + a single scrolling canvas, so the scan action and the
result table always stay one click apart.

Backend logic lives in `assistant_core.py`; all visual tokens live in
`ui_theme.py`.
"""

from __future__ import annotations

import asyncio
import os
import queue
import threading
import time
from datetime import datetime
from pathlib import Path

try:
    import flet as ft
except ImportError:
    ft = None

from assistant_core import DEFAULT_TOP_N, PersonalQuantAssistant
from console_particles import (
    ConsoleParticleController,
    begin_card_frame,
)
from scan_hud import ScanHUD
from splash_intro import SplashScreen
from ui_theme import (
    MONO,
    MONO_FALLBACK,
    SANS,
    SANS_FALLBACK,
    Palette,
    build_page_theme,
    card,
    chip,
    empty_state,
    mono,
    palette_for,
    section_title,
    stat_tile,
    table_style,
    with_alpha,
)


DATA_DIR = Path(__file__).resolve().parent / "data"
PARTICLE_COUNT = 4000

VIEWS = (
    ("overview", "概览", "全市场扫描总览与最近快照"),
    ("candidates", "候选池", "按双低总分排序的双低转债候选"),
    ("review", "快照复盘", "相邻两期扫描的名次与分数变化"),
    ("watchlist", "自选池", "本地自选转债清单"),
    ("holdings", "持仓维护", "本地持仓数量与成本"),
)
VIEW_KEYS = {view[0] for view in VIEWS}


# --------------------------------------------------------------------------- #
# Compatibility helpers (kept for the unit tests and for older Flet builds)
# --------------------------------------------------------------------------- #


def _parse_int(value: str, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int((value or "").strip())
    except ValueError:
        return default
    return max(minimum, min(parsed, maximum))


def _parse_optional_float(value: str) -> float | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _format_optional_number(value: float | None, suffix: str = "") -> str:
    return "" if value is None else f"{value:.2f}{suffix}"


def _format_rank_delta(value: int) -> str:
    if value > 0:
        return f"上升 {value}"
    if value < 0:
        return f"下降 {abs(value)}"
    return "不变"


def _format_score_delta(value: float) -> str:
    if value > 0:
        return f"+{value:.2f}"
    return f"{value:.2f}"


def _card_bgcolor_kwargs(value):
    return {"bgcolor": value}


def _border_side(width, color):
    return ft.border.BorderSide(width=width, color=color)


def _border_all(width, color):
    side = _border_side(width, color)
    return ft.border.Border(top=side, right=side, bottom=side, left=side)


def _button_content_kwargs(value):
    return {"content": value}


def _set_button_content(button, value):
    button.content = value


# --------------------------------------------------------------------------- #
# Application state
# --------------------------------------------------------------------------- #


class AppState:
    """Everything the UI needs, kept outside the control tree."""

    def __init__(self) -> None:
        requested_view = os.getenv("QUANT_VIEW", "overview") or "overview"
        self.view = requested_view if requested_view in VIEW_KEYS else "overview"
        self.dark = True
        self.busy = False
        self.status = "准备就绪。点击「一键扫描双低转债」拉取全市场行情。"

        self.rows: list[dict] = []
        self.result: dict | None = None
        self.watchlist_rows: list[dict] = []
        self.holdings_rows: list[dict] = []
        self.review: dict = {}
        self.recent_snapshots: list[dict] = []

        self.top_n = str(DEFAULT_TOP_N)
        self.max_premium = ""
        self.position_filter = "all"
        self.only_unheld = False

        self.particle_quality = "performance"
        self.particle_effects = os.getenv("QUANT_PARTICLES", "1") != "0"
        self.splash_enabled = os.getenv("QUANT_SKIP_SPLASH", "0") != "1"

        self.form = {
            "bond_code": "",
            "bond_name": "",
            "quantity": "",
            "avg_cost": "",
            "note": "",
        }


def main(page: ft.Page):
    if ft is None:
        raise RuntimeError("未安装 flet。请先执行 pip install -r requirements.txt")

    assistant = PersonalQuantAssistant(data_dir=DATA_DIR)
    state = AppState()

    page.title = "双低转债 · 个人量化助手"
    page.padding = 0
    page.spacing = 0
    page.window_width = 1480
    page.window_height = 940
    page.window_min_width = 1120
    page.window_min_height = 680
    page.theme_mode = ft.ThemeMode.DARK
    page.theme = build_page_theme(True)

    # ------------------------------------------------------------------ #
    # Small building blocks
    # ------------------------------------------------------------------ #

    def txt(text, *, size=13, color=None, weight=None, mono_font=False):
        return ft.Text(
            text,
            size=size,
            color=color,
            weight=weight,
            font_family=MONO if mono_font else SANS,
            font_family_fallback=MONO_FALLBACK if mono_font else SANS_FALLBACK,
        )

    def card_title(p: Palette, title, subtitle=None):
        return section_title(p, title, subtitle)

    def rank_badge(p: Palette, rank: int):
        hot = rank <= 3
        return ft.Container(
            content=mono(
                str(rank),
                size=12,
                color=p.accent if hot else p.text_muted,
                weight=ft.FontWeight.W_600,
            ),
            padding=ft.Padding.symmetric(horizontal=8, vertical=3),
            bgcolor=p.accent_soft if hot else p.neutral_soft,
            border_radius=6,
        )

    def signal_chip(p: Palette, signal: str):
        if not signal:
            return txt("")
        if signal == "重点机会":
            return chip(p, signal, tone="positive")
        if signal == "浮亏关注":
            return chip(p, signal, tone="negative")
        return chip(p, signal)

    def group_chip(p: Palette, group: str):
        return chip(p, group, tone="accent" if group == "持仓观察" else "neutral")

    def nav_item(p: Palette, key: str, label_text: str, icon, active: bool):
        accent_line = ft.Container(
            width=3,
            height=20,
            border_radius=2,
            bgcolor=p.accent if active else "transparent",
        )

        def on_hover(e):
            hovered = e.data == "true" or e.data is True
            item.bgcolor = with_alpha(p.surface_alt, 0.72) if hovered else (
                with_alpha(p.surface_alt, 0.52) if active else "transparent"
            )
            accent_line.bgcolor = p.accent if (active or hovered) else "transparent"
            item.update()

        item = ft.Container(
            content=ft.Row(
                [
                    accent_line,
                    ft.Icon(icon, size=18, color=p.accent if active else p.text_muted),
                    txt(
                        label_text,
                        size=13,
                        color=p.text if active else p.text_muted,
                        weight=ft.FontWeight.W_600 if active else ft.FontWeight.W_500,
                    ),
                ],
                spacing=10,
            ),
            padding=ft.Padding.symmetric(horizontal=10, vertical=10),
            border_radius=10,
            bgcolor=with_alpha(p.surface_alt, 0.52) if active else "transparent",
            on_click=lambda _, k=key: switch_view(k),
            on_hover=on_hover,
            ink=True,
            animate=ft.Animation(150, ft.AnimationCurve.EASE_OUT),
        )
        return item

    # ------------------------------------------------------------------ #
    # Actions
    # ------------------------------------------------------------------ #

    def set_status(text: str, tone: str = "neutral"):
        state.status = text

    def show_snack(message: str):
        page.snack_bar = ft.SnackBar(
            content=txt(message, size=13),
            bgcolor=palette_for(state.dark).text,
        )
        page.update()

    particle_controller = ConsoleParticleController(
        page,
        quality=state.particle_quality,
    )
    scan_hud = ScanHUD(page)

    def finish_splash():
        render()

    splash = SplashScreen(page, finish_splash)
    splash.active = state.splash_enabled

    def refresh_local_data():
        state.watchlist_rows = assistant.get_watchlist()
        try:
            state.holdings_rows = assistant.local_store.load_holdings()
        except Exception:
            state.holdings_rows = []

    def refresh_review_data():
        bundle = assistant.get_recent_snapshot_review(limit=5)
        state.review = bundle.get("snapshot_review") or {}
        state.recent_snapshots = bundle.get("recent_snapshots") or []

    def set_particle_quality(quality: str):
        state.particle_quality = "power" if quality == "power" else "performance"
        particle_controller.set_options(state.particle_quality)
        mode_text = "省电模式" if state.particle_quality == "power" else "性能模式"
        set_status(f"已切换到{mode_text}。")
        render()

    def toggle_particle_effects(enabled: bool):
        state.particle_effects = bool(enabled)
        particle_controller.enabled = state.particle_effects
        set_status("控制台粒子效果已开启。" if enabled else "控制台粒子效果已暂停。")
        render()

    def apply_scan_result(result: dict):
        state.result = result
        state.rows = result.get("rows") or []
        refresh_local_data()
        refresh_review_data()
        if state.rows:
            set_status(
                f"扫描完成，展示 {len(state.rows)} 条候选"
                f"（双低总分 = 现价 + 转股溢价率，越低越划算）。"
            )
        else:
            set_status("没有符合条件的候选，请放宽筛选条件后重试。")

    async def run_scan(_event=None):
        if state.busy:
            return
        state.busy = True
        set_status("正在执行全市场扫描…")
        scan_hud.begin()
        render()

        events: queue.Queue = queue.Queue()
        result_holder: dict = {}
        error_holder: dict = {}

        def progress_callback(progress):
            events.put(("progress", progress))

        def scan_worker():
            try:
                result_holder["result"] = assistant.scan_market(
                    max_premium_pct=_parse_optional_float(state.max_premium),
                    top_n=_parse_int(state.top_n, DEFAULT_TOP_N, 1, 200),
                    only_unheld=bool(state.only_unheld),
                    position_filter=state.position_filter or "all",
                    progress_callback=progress_callback,
                )
            except Exception as exc:  # pragma: no cover - network dependent
                error_holder["error"] = exc
            finally:
                events.put(("finished", None))

        worker = threading.Thread(
            target=scan_worker,
            name="market-scan",
            daemon=True,
        )
        started_at = time.monotonic()
        worker.start()

        target_percent = 0.0
        display_percent = 0.0
        finished = False
        while True:
            while True:
                try:
                    event_type, payload = events.get_nowait()
                except queue.Empty:
                    break
                if event_type == "progress":
                    target_percent = max(target_percent, float(payload.percent))
                    scan_hud.apply_progress(payload)
                elif event_type == "finished":
                    finished = True

            elapsed = time.monotonic() - started_at
            display_percent += (target_percent - display_percent) * 0.2
            if abs(target_percent - display_percent) < 0.15:
                display_percent = target_percent
            scan_hud.set_display_percent(display_percent)
            scan_hud.set_elapsed(elapsed)
            try:
                page.update()
            except Exception:
                pass

            if finished and (
                error_holder
                or (result_holder and display_percent >= 99.5)
            ):
                break
            await asyncio.sleep(0.1)

        if error_holder:
            state.busy = False
            error = error_holder["error"]
            set_status("扫描失败，请检查数据源访问或本地 CSV 格式。")
            scan_hud.show_error(f"SCAN FAILED · {str(error)[:180]}")
            return

        result = result_holder.get("result") or {}
        apply_scan_result(result)
        elapsed = time.monotonic() - started_at
        if elapsed < 0.9:
            await asyncio.sleep(0.9 - elapsed)
        scan_hud.show_complete()
        await asyncio.sleep(0.55)
        scan_hud.finish()
        state.busy = False
        render()
        if result.get("warning"):
            show_snack("数据源提示：" + str(result["warning"])[:120])

    def close_scan_error():
        scan_hud.finish()
        state.busy = False
        render()

    def retry_scan():
        scan_hud.finish()
        state.busy = False
        page.run_task(run_scan)

    scan_hud.on_retry = retry_scan
    scan_hud.on_close = close_scan_error

    def rescan_after_local_change():
        try:
            result = assistant.scan_market(
                max_premium_pct=_parse_optional_float(state.max_premium),
                top_n=_parse_int(state.top_n, DEFAULT_TOP_N, 1, 200),
                only_unheld=bool(state.only_unheld),
                position_filter=state.position_filter or "all",
            )
            apply_scan_result(result)
        except Exception:
            pass

    def switch_view(key: str):
        state.view = key
        render()

    def add_row_to_watchlist(row: dict):
        assistant.add_to_watchlist(row["bond_code"], row["bond_name"])
        row["is_watchlist"] = True
        refresh_local_data()
        set_status(f"{row['bond_name']} 已加入本地自选池。")
        show_snack(f"{row['bond_name']} 已加入自选")
        render()

    def remove_watchlist_code(bond_code: str, bond_name: str):
        assistant.remove_from_watchlist(bond_code)
        for row in state.rows:
            if row["bond_code"] == bond_code:
                row["is_watchlist"] = False
        refresh_local_data()
        set_status(f"{bond_name} 已从本地自选池移除。")
        show_snack(f"{bond_name} 已移除自选")
        render()

    def fill_holding_form(row: dict):
        state.form = {
            "bond_code": row.get("bond_code", ""),
            "bond_name": row.get("bond_name", ""),
            "quantity": _format_optional_number(row.get("held_quantity")),
            "avg_cost": _format_optional_number(row.get("held_avg_cost")),
            "note": row.get("held_note", row.get("note", "")),
        }
        set_status(f"已带入 {row.get('bond_name', '')} 的信息，可修改后保存持仓。")
        render()

    def update_form(field_name: str, value):
        state.form[field_name] = value

    def save_holding(_):
        code = (state.form["bond_code"] or "").strip()
        name = (state.form["bond_name"] or "").strip()
        quantity = _parse_optional_float(state.form["quantity"])
        avg_cost = _parse_optional_float(state.form["avg_cost"])
        note = (state.form["note"] or "").strip()

        if not code or not name:
            set_status("保存持仓前请先填写代码和名称。")
            show_snack("请先填写持仓代码和名称")
            render()
            return
        if quantity is None or quantity <= 0:
            set_status("持仓数量需要是大于 0 的数字。")
            show_snack("持仓数量需要大于 0")
            render()
            return

        assistant.add_or_update_holding(code, name, quantity, avg_cost, note)
        state.form = {"bond_code": "", "bond_name": "", "quantity": "", "avg_cost": "", "note": ""}
        rescan_after_local_change()
        refresh_local_data()
        set_status(f"{name} 持仓已保存到本地。")
        show_snack(f"{name} 持仓已保存")
        render()

    def clear_current_holding(_):
        code = (state.form["bond_code"] or "").strip()
        name = (state.form["bond_name"] or "").strip()
        if not code:
            set_status("清仓前请先填写持仓代码。")
            show_snack("请先填写持仓代码")
            render()
            return
        assistant.clear_holding(code, name)
        state.form = {"bond_code": "", "bond_name": "", "quantity": "", "avg_cost": "", "note": ""}
        rescan_after_local_change()
        refresh_local_data()
        set_status(f"{name or code} 持仓已从本地移除。")
        show_snack("持仓已清除")
        render()

    def clear_holding_form(_=None):
        state.form = {"bond_code": "", "bond_name": "", "quantity": "", "avg_cost": "", "note": ""}
        set_status("持仓表单已清空。")
        render()

    # ------------------------------------------------------------------ #
    # Native console particle controls
    # ------------------------------------------------------------------ #

    # ------------------------------------------------------------------ #
    # View builders
    # ------------------------------------------------------------------ #

    def build_candidates_table(p: Palette):
        columns = [
            ft.DataColumn(txt("排名", size=11, color=p.text_muted, weight=ft.FontWeight.W_600)),
            ft.DataColumn(txt("代码", size=11, color=p.text_muted, weight=ft.FontWeight.W_600)),
            ft.DataColumn(txt("名称", size=11, color=p.text_muted, weight=ft.FontWeight.W_600)),
            ft.DataColumn(txt("现价", size=11, color=p.text_muted, weight=ft.FontWeight.W_600), numeric=True),
            ft.DataColumn(txt("溢价率 %", size=11, color=p.text_muted, weight=ft.FontWeight.W_600), numeric=True),
            ft.DataColumn(txt("双低总分", size=11, color=p.text_muted, weight=ft.FontWeight.W_600), numeric=True),
            ft.DataColumn(txt("分组", size=11, color=p.text_muted, weight=ft.FontWeight.W_600)),
            ft.DataColumn(txt("持仓", size=11, color=p.text_muted, weight=ft.FontWeight.W_600)),
            ft.DataColumn(txt("数量", size=11, color=p.text_muted, weight=ft.FontWeight.W_600), numeric=True),
            ft.DataColumn(txt("成本", size=11, color=p.text_muted, weight=ft.FontWeight.W_600), numeric=True),
            ft.DataColumn(txt("状态", size=11, color=p.text_muted, weight=ft.FontWeight.W_600)),
            ft.DataColumn(txt("差额", size=11, color=p.text_muted, weight=ft.FontWeight.W_600), numeric=True),
            ft.DataColumn(txt("收益率", size=11, color=p.text_muted, weight=ft.FontWeight.W_600), numeric=True),
            ft.DataColumn(txt("信号", size=11, color=p.text_muted, weight=ft.FontWeight.W_600)),
            ft.DataColumn(txt("自选", size=11, color=p.text_muted, weight=ft.FontWeight.W_600)),
            ft.DataColumn(txt("操作", size=11, color=p.text_muted, weight=ft.FontWeight.W_600)),
        ]

        rows = []
        for row in state.rows:
            diff = row.get("cost_diff")
            diff_pct = row.get("cost_diff_pct")
            status_text = row.get("holding_status") or ""
            status_color = (
                p.positive
                if status_text == "浮盈"
                else p.negative
                if status_text == "浮亏"
                else p.text_muted
            )
            rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(rank_badge(p, row["rank"])),
                        ft.DataCell(mono(row["bond_code"], size=12, color=p.text_muted)),
                        ft.DataCell(txt(row["bond_name"], size=13, color=p.text, weight=ft.FontWeight.W_500)),
                        ft.DataCell(mono(f"{row['price']:.2f}", size=13)),
                        ft.DataCell(mono(f"{row['premium_pct']:.2f}", size=13)),
                        ft.DataCell(
                            mono(
                                f"{row['double_low_score']:.2f}",
                                size=13,
                                color=p.accent,
                                weight=ft.FontWeight.W_600,
                            )
                        ),
                        ft.DataCell(group_chip(p, row["position_group"])),
                        ft.DataCell(txt("是" if row["is_held"] else "—", size=12, color=p.text_muted)),
                        ft.DataCell(mono(_format_optional_number(row.get("held_quantity")), size=12, color=p.text_muted)),
                        ft.DataCell(mono(_format_optional_number(row.get("held_avg_cost")), size=12, color=p.text_muted)),
                        ft.DataCell(txt(status_text, size=12, color=status_color)),
                        ft.DataCell(mono(_format_optional_number(diff), size=12, color=status_color)),
                        ft.DataCell(mono(_format_optional_number(diff_pct, "%"), size=12, color=status_color)),
                        ft.DataCell(signal_chip(p, row.get("signal_label", ""))),
                        ft.DataCell(txt("★" if row.get("is_watchlist") else "—", size=12, color=p.accent)),
                        ft.DataCell(
                            ft.Row(
                                [
                                    ft.TextButton(
                                        "移除" if row.get("is_watchlist") else "自选",
                                        style=ft.ButtonStyle(
                                            color=p.accent if not row.get("is_watchlist") else p.text_muted,
                                            text_style=ft.TextStyle(size=12, font_family=SANS),
                                            padding=ft.Padding.symmetric(horizontal=8, vertical=0),
                                        ),
                                        expand=False,
                                        on_click=(
                                            (lambda _, item=row: remove_watchlist_code(item["bond_code"], item["bond_name"]))
                                            if row.get("is_watchlist")
                                            else (lambda _, item=row: add_row_to_watchlist(item))
                                        ),
                                    ),
                                    ft.TextButton(
                                        "持仓" if row["is_held"] else "建仓",
                                        style=ft.ButtonStyle(
                                            color=p.text_muted,
                                            text_style=ft.TextStyle(size=12, font_family=SANS),
                                            padding=ft.Padding.symmetric(horizontal=8, vertical=0),
                                        ),
                                        expand=False,
                                        on_click=(lambda _, item=row: fill_holding_form(item)),
                                    ),
                                ],
                                spacing=2,
                                tight=True,
                            )
                        ),
                    ]
                )
            )

        if not rows:
            return empty_state(
                p,
                "还没有候选数据",
                "点击右上角「一键扫描双低转债」拉取全市场行情。",
            )

        table = ft.DataTable(**table_style(p), columns=columns, rows=rows)
        return ft.Row([table], scroll=ft.ScrollMode.AUTO, tight=True)

    def build_review_table(p: Palette):
        review = state.review or {}
        columns = [
            ft.DataColumn(txt("变化", size=11, color=p.text_muted, weight=ft.FontWeight.W_600)),
            ft.DataColumn(txt("代码", size=11, color=p.text_muted, weight=ft.FontWeight.W_600)),
            ft.DataColumn(txt("名称", size=11, color=p.text_muted, weight=ft.FontWeight.W_600)),
            ft.DataColumn(txt("当前排名", size=11, color=p.text_muted, weight=ft.FontWeight.W_600), numeric=True),
            ft.DataColumn(txt("上期排名", size=11, color=p.text_muted, weight=ft.FontWeight.W_600), numeric=True),
            ft.DataColumn(txt("名次变化", size=11, color=p.text_muted, weight=ft.FontWeight.W_600)),
            ft.DataColumn(txt("分数变化", size=11, color=p.text_muted, weight=ft.FontWeight.W_600), numeric=True),
        ]

        rows = []
        for item in review.get("new_rows", [])[:6]:
            rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(chip(p, "新进榜", tone="positive")),
                        ft.DataCell(mono(item["bond_code"], size=12, color=p.text_muted)),
                        ft.DataCell(txt(item["bond_name"], size=13)),
                        ft.DataCell(mono(str(item["current_rank"]), size=13)),
                        ft.DataCell(mono("—", size=13, color=p.text_faint)),
                        ft.DataCell(txt("新进", size=12, color=p.positive)),
                        ft.DataCell(mono("—", size=12, color=p.text_faint)),
                    ]
                )
            )
        for item in review.get("dropped_rows", [])[:6]:
            rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(chip(p, "掉出榜", tone="negative")),
                        ft.DataCell(mono(item["bond_code"], size=12, color=p.text_muted)),
                        ft.DataCell(txt(item["bond_name"], size=13)),
                        ft.DataCell(mono("—", size=13, color=p.text_faint)),
                        ft.DataCell(mono(str(item["previous_rank"]), size=13)),
                        ft.DataCell(txt("掉出", size=12, color=p.negative)),
                        ft.DataCell(mono("—", size=12, color=p.text_faint)),
                    ]
                )
            )
        for item in review.get("changed_rows", [])[:8]:
            rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(chip(p, "名次变化")),
                        ft.DataCell(mono(item["bond_code"], size=12, color=p.text_muted)),
                        ft.DataCell(txt(item["bond_name"], size=13)),
                        ft.DataCell(mono(str(item["current_rank"]), size=13)),
                        ft.DataCell(mono(str(item["previous_rank"]), size=13)),
                        ft.DataCell(txt(_format_rank_delta(item["rank_delta"]), size=12)),
                        ft.DataCell(mono(_format_score_delta(item["score_delta"]), size=13)),
                    ]
                )
            )

        if not rows:
            return empty_state(p, "暂无快照对比", "连续扫描两次后即可看到名次与分数变化。")

        table = ft.DataTable(**table_style(p), columns=columns, rows=rows)
        return ft.Row([table], scroll=ft.ScrollMode.AUTO, tight=True)

    def build_watchlist_table(p: Palette):
        columns = [
            ft.DataColumn(txt("代码", size=11, color=p.text_muted, weight=ft.FontWeight.W_600)),
            ft.DataColumn(txt("名称", size=11, color=p.text_muted, weight=ft.FontWeight.W_600)),
            ft.DataColumn(txt("备注", size=11, color=p.text_muted, weight=ft.FontWeight.W_600)),
            ft.DataColumn(txt("操作", size=11, color=p.text_muted, weight=ft.FontWeight.W_600)),
        ]
        rows = []
        for row in state.watchlist_rows:
            rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(mono(row["bond_code"], size=12, color=p.text_muted)),
                        ft.DataCell(txt(row["bond_name"], size=13, weight=ft.FontWeight.W_500)),
                        ft.DataCell(txt(row.get("note", ""), size=12, color=p.text_muted)),
                        ft.DataCell(
                            ft.Row(
                                [
                                    ft.TextButton(
                                        "写入持仓",
                                        style=ft.ButtonStyle(
                                            color=p.accent,
                                            text_style=ft.TextStyle(size=12, font_family=SANS),
                                            padding=ft.Padding.symmetric(horizontal=8, vertical=0),
                                        ),
                                        expand=False,
                                        on_click=(
                                            lambda _, item=row: fill_holding_form(
                                                {
                                                    "bond_code": item["bond_code"],
                                                    "bond_name": item["bond_name"],
                                                    "held_note": item.get("note", ""),
                                                }
                                            )
                                        ),
                                    ),
                                    ft.TextButton(
                                        "移除",
                                        style=ft.ButtonStyle(
                                            color=p.text_muted,
                                            text_style=ft.TextStyle(size=12, font_family=SANS),
                                            padding=ft.Padding.symmetric(horizontal=8, vertical=0),
                                        ),
                                        expand=False,
                                        on_click=(
                                            lambda _, item=row: remove_watchlist_code(
                                                item["bond_code"], item["bond_name"]
                                            )
                                        ),
                                    ),
                                ],
                                spacing=2,
                                tight=True,
                            )
                        ),
                    ]
                )
            )
        if not rows:
            return empty_state(p, "自选池是空的", "在候选池点击「自选」即可加入本地清单。")
        table = ft.DataTable(**table_style(p), columns=columns, rows=rows)
        return ft.Row([table], scroll=ft.ScrollMode.AUTO, tight=True)

    def build_holdings_table(p: Palette):
        columns = [
            ft.DataColumn(txt("代码", size=11, color=p.text_muted, weight=ft.FontWeight.W_600)),
            ft.DataColumn(txt("名称", size=11, color=p.text_muted, weight=ft.FontWeight.W_600)),
            ft.DataColumn(txt("数量", size=11, color=p.text_muted, weight=ft.FontWeight.W_600), numeric=True),
            ft.DataColumn(txt("成本", size=11, color=p.text_muted, weight=ft.FontWeight.W_600), numeric=True),
            ft.DataColumn(txt("备注", size=11, color=p.text_muted, weight=ft.FontWeight.W_600)),
            ft.DataColumn(txt("操作", size=11, color=p.text_muted, weight=ft.FontWeight.W_600)),
        ]
        rows = []
        for row in state.holdings_rows:
            rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(mono(row["bond_code"], size=12, color=p.text_muted)),
                        ft.DataCell(txt(row["bond_name"], size=13, weight=ft.FontWeight.W_500)),
                        ft.DataCell(mono(_format_optional_number(row.get("quantity")), size=13)),
                        ft.DataCell(mono(_format_optional_number(row.get("avg_cost")), size=13)),
                        ft.DataCell(txt(row.get("note", ""), size=12, color=p.text_muted)),
                        ft.DataCell(
                            ft.TextButton(
                                "载入",
                                style=ft.ButtonStyle(
                                    color=p.accent,
                                    text_style=ft.TextStyle(size=12, font_family=SANS),
                                    padding=ft.Padding.symmetric(horizontal=8, vertical=0),
                                ),
                                expand=False,
                                on_click=(
                                    lambda _, item=row: fill_holding_form(
                                        {
                                            "bond_code": item["bond_code"],
                                            "bond_name": item["bond_name"],
                                            "held_quantity": item.get("quantity"),
                                            "held_avg_cost": item.get("avg_cost"),
                                            "held_note": item.get("note", ""),
                                        }
                                    )
                                ),
                            )
                        ),
                    ]
                )
            )
        if not rows:
            return empty_state(p, "还没有本地持仓", "在上方表单填写数量与成本后保存。")
        table = ft.DataTable(**table_style(p), columns=columns, rows=rows)
        return ft.Row([table], scroll=ft.ScrollMode.AUTO, tight=True)

    def build_overview(p: Palette):
        result = state.result or {}
        market_count = result.get("market_count", 0)
        candidate_count = result.get("candidate_count", len(state.rows))
        held_count = result.get("held_candidate_count", 0)
        redeem_count = result.get("redeem_count", 0)

        kpis = ft.ResponsiveRow(
            columns=12,
            spacing=16,
            run_spacing=16,
            controls=[
                stat_tile(p, "市场记录", str(market_count or 0), hint="全市场转债数量", tone="accent"),
                stat_tile(p, "入选候选", str(candidate_count or 0), hint="当前筛选结果"),
                stat_tile(p, "持仓观察", str(held_count or 0), hint="已持仓标的入选数", tone="positive"),
                stat_tile(p, "剔除强赎", str(redeem_count or 0), hint="已公告强赎过滤", tone="negative"),
            ],
        )
        for tile in kpis.controls:
            tile.col = {"sm": 12, "md": 6, "lg": 3}

        formula_card = card(
            p,
            ft.Column(
                [
                    card_title(p, "双低核心公式", "总分越低，债底保护越强、买入越划算"),
                    ft.Container(height=14),
                    ft.Container(
                        content=ft.Column(
                            [
                                mono("双低总分 = 转债现价 + 转股溢价率", size=15, color=p.accent, weight=ft.FontWeight.W_600),
                                ft.Container(height=8),
                                mono("现价 ≤ 130 元，且剔除已公告强赎标的", size=12, color=p.text_muted),
                            ],
                            spacing=0,
                        ),
                        padding=16,
                        bgcolor=p.surface_sunken,
                        border_radius=12,
                    ),
                    ft.Container(height=14),
                    txt(
                        "候选按总分升序排列，并优先展示「重点机会 / 浮亏关注 / 接近成本」等信号标的。",
                        size=12,
                        color=p.text_muted,
                    ),
                ],
                spacing=0,
                tight=True,
            ),
        )

        summary_items = [
            ("数据源", result.get("source_name", "尚未扫描")),
            ("扫描时间", result.get("scan_time", "—")),
            ("新机会", result.get("unheld_candidate_count", 0)),
            ("提醒数量", result.get("signal_candidate_count", 0)),
            ("快照文件", result.get("snapshot_path", "—")),
        ]
        summary_card = card(
            p,
            ft.Column(
                [
                    card_title(p, "扫描摘要", "每次扫描都会落盘一份本地快照"),
                    ft.Container(height=12),
                    ft.Column(
                        [
                            ft.Row(
                                [
                                    txt("数据源", size=12, color=p.text_muted),
                                    ft.Container(expand=True),
                                    txt(str(summary_items[0][1]), size=12, color=p.text),
                                ],
                                spacing=8,
                            ),
                            ft.Divider(height=14, color=p.border),
                            ft.Row(
                                [
                                    txt("扫描时间", size=12, color=p.text_muted),
                                    ft.Container(expand=True),
                                    txt(str(summary_items[1][1]), size=12, color=p.text, mono_font=True),
                                ],
                                spacing=8,
                            ),
                            ft.Divider(height=14, color=p.border),
                            ft.Row(
                                [
                                    txt("新机会 / 提醒", size=12, color=p.text_muted),
                                    ft.Container(expand=True),
                                    txt(
                                        f"{summary_items[2][1]} / {summary_items[3][1]}",
                                        size=12,
                                        color=p.text,
                                        mono_font=True,
                                    ),
                                ],
                                spacing=8,
                            ),
                            ft.Divider(height=14, color=p.border),
                            ft.Row(
                                [
                                    txt("快照文件", size=12, color=p.text_muted),
                                    ft.Container(expand=True),
                                    txt(str(summary_items[4][1]), size=11, color=p.text_faint, mono_font=True),
                                ],
                                spacing=8,
                            ),
                        ],
                        spacing=0,
                        tight=True,
                    ),
                ],
                spacing=0,
                tight=True,
            ),
            expand=3,
        )

        review = state.review or {}
        review_items = []
        for item in (review.get("new_rows") or [])[:4]:
            review_items.append((chip(p, "新进", tone="positive"), f"{item['bond_name']}  #1"))
        for item in (review.get("changed_rows") or [])[:4]:
            review_items.append((chip(p, "名次"), f"{item['bond_name']}  {_format_rank_delta(item['rank_delta'])}"))

        review_card = card(
            p,
            ft.Column(
                [
                    card_title(
                        p,
                        "最近快照复盘",
                        review.get("summary") or "暂无快照复盘信息。",
                    ),
                    ft.Container(height=12),
                    (
                        ft.Column(
                            [
                                ft.Row(
                                    [
                                        tag,
                                        ft.Container(expand=True),
                                        txt(detail, size=12, color=p.text_muted),
                                    ],
                                    spacing=10,
                                )
                                for tag, detail in review_items
                            ],
                            spacing=10,
                            tight=True,
                        )
                        if review_items
                        else empty_state(p, "暂无变化记录", "连续扫描两次后即可看到变化。")
                    ),
                ],
                spacing=0,
                tight=True,
            ),
            expand=4,
        )

        for panel, span in ((formula_card, 4), (summary_card, 4), (review_card, 4)):
            panel.col = {"sm": 12, "lg": span}

        return ft.Column(
            [
                kpis,
                ft.Container(height=16),
                ft.ResponsiveRow(
                    columns=12,
                    spacing=16,
                    run_spacing=16,
                    controls=[formula_card, summary_card, review_card],
                ),
            ],
            spacing=0,
            tight=True,
        )

    def build_candidates_view(p: Palette):
        return card(
            p,
            ft.Column(
                [
                    ft.Row(
                        [
                            card_title(
                                p,
                                "双低候选池",
                                "双低总分 = 现价 + 转股溢价率，升序排列取前 N 名",
                            ),
                            ft.Container(expand=True),
                            chip(p, f"{len(state.rows)} 条候选", tone="accent"),
                        ],
                        spacing=12,
                    ),
                    ft.Container(height=14),
                    build_candidates_table(p),
                ],
                spacing=0,
                tight=True,
            ),
        )

    def build_review_view(p: Palette):
        review = state.review or {}
        snapshots = state.recent_snapshots or []
        history = ft.Row(
            [chip(p, str(item.get("scan_time", "-")), tone="neutral") for item in snapshots[:6]],
            spacing=8,
            scroll=ft.ScrollMode.AUTO,
        )
        return ft.Column(
            [
                card(
                    p,
                    ft.Column(
                        [
                            card_title(p, "快照对比", review.get("summary") or "暂无快照复盘信息。"),
                            ft.Container(height=10),
                            history,
                        ],
                        spacing=0,
                        tight=True,
                    ),
                ),
                ft.Container(height=16),
                card(
                    p,
                    ft.Column(
                        [
                            card_title(p, "名次与分数变化", "新进榜 / 掉出榜 / 名次变化明细"),
                            ft.Container(height=14),
                            build_review_table(p),
                        ],
                        spacing=0,
                        tight=True,
                    ),
                ),
            ],
            spacing=0,
            tight=True,
        )

    def build_watchlist_view(p: Palette):
        return card(
            p,
            ft.Column(
                [
                    ft.Row(
                        [
                            card_title(p, "本地自选池", "自选清单保存在本地 CSV，与行情扫描相互独立"),
                            ft.Container(expand=True),
                            chip(p, f"{len(state.watchlist_rows)} 只", tone="accent"),
                        ],
                        spacing=12,
                    ),
                    ft.Container(height=14),
                    build_watchlist_table(p),
                ],
                spacing=0,
                tight=True,
            ),
        )

    def build_holdings_view(p: Palette):
        form = state.form
        field_style = dict(
            bgcolor=p.surface_alt,
            border_radius=10,
            border_color=p.border,
            focused_border_color=p.accent,
            label_style=ft.TextStyle(size=11, color=p.text_muted, font_family=SANS),
            text_style=ft.TextStyle(size=13, color=p.text, font_family=SANS),
            content_padding=ft.Padding.symmetric(horizontal=12, vertical=14),
        )

        def form_field(key, label_text, width, hint=None):
            return ft.TextField(
                label=label_text,
                hint_text=hint,
                width=width,
                value=form.get(key, ""),
                on_change=lambda e, k=key: update_form(k, e.control.value),
                **field_style,
            )

        editor = card(
            p,
            ft.Column(
                [
                    card_title(p, "持仓表单", "可以先在候选池或自选池点「建仓」自动带入，再微调数量与成本"),
                    ft.Container(height=14),
                    ft.Row(
                        [
                            form_field("bond_code", "持仓代码", 150),
                            form_field("bond_name", "持仓名称", 190),
                            form_field("quantity", "持仓数量", 140),
                            form_field("avg_cost", "持仓成本", 140),
                            form_field("note", "备注", 240),
                        ],
                        spacing=12,
                        wrap=True,
                        run_spacing=12,
                    ),
                    ft.Container(height=14),
                    ft.Row(
                        [
                            ft.Button(
                                content=ft.Row([ft.Icon(ft.Icons.SAVE, size=16), txt("保存持仓", size=13)], spacing=8),
                                on_click=save_holding,
                                expand=False,
                                style=ft.ButtonStyle(
                                    bgcolor=p.accent,
                                    color=p.on_accent,
                                    padding=ft.Padding.symmetric(horizontal=20, vertical=14),
                                    shape=ft.RoundedRectangleBorder(radius=12),
                                    elevation=2,
                                ),
                            ),
                            ft.OutlinedButton(
                                content=ft.Row([ft.Icon(ft.Icons.DELETE_OUTLINE, size=16), txt("清仓", size=13)], spacing=8),
                                on_click=clear_current_holding,
                                expand=False,
                                style=ft.ButtonStyle(
                                    color=p.text_muted,
                                    side=ft.BorderSide(1, p.border_strong),
                                    padding=ft.Padding.symmetric(horizontal=18, vertical=14),
                                    shape=ft.RoundedRectangleBorder(radius=12),
                                ),
                            ),
                            ft.TextButton(
                                content=txt("清空表单", size=13),
                                on_click=clear_holding_form,
                                expand=False,
                                style=ft.ButtonStyle(color=p.text_muted),
                            ),
                        ],
                        spacing=10,
                        wrap=True,
                    ),
                ],
                spacing=0,
                tight=True,
            ),
        )

        return ft.Column(
            [
                editor,
                ft.Container(height=16),
                card(
                    p,
                    ft.Column(
                        [
                            card_title(p, "当前持仓", f"本地文件：{DATA_DIR / 'holdings.csv'}"),
                            ft.Container(height=14),
                            build_holdings_table(p),
                        ],
                        spacing=0,
                        tight=True,
                    ),
                ),
            ],
            spacing=0,
            tight=True,
        )

    def build_view(p: Palette):
        return {
            "overview": build_overview,
            "candidates": build_candidates_view,
            "review": build_review_view,
            "watchlist": build_watchlist_view,
            "holdings": build_holdings_view,
        }[state.view](p)

    # ------------------------------------------------------------------ #
    # Shell
    # ------------------------------------------------------------------ #

    def build_filter_bar(p: Palette):
        field_style = dict(
            bgcolor=p.surface_alt,
            border_radius=10,
            border_color=p.border,
            focused_border_color=p.accent,
            label_style=ft.TextStyle(size=11, color=p.text_muted, font_family=SANS),
            text_style=ft.TextStyle(size=13, color=p.text, font_family=SANS),
            content_padding=ft.Padding.symmetric(horizontal=12, vertical=14),
        )

        return card(
            p,
            ft.Row(
                [
                    ft.TextField(
                        label="显示前 N 名",
                        value=state.top_n,
                        width=128,
                        keyboard_type=ft.KeyboardType.NUMBER,
                        on_change=lambda e: setattr(state, "top_n", e.control.value),
                        **field_style,
                    ),
                    ft.TextField(
                        label="最大溢价率 (%)",
                        hint_text="留空不过滤",
                        value=state.max_premium,
                        width=168,
                        keyboard_type=ft.KeyboardType.NUMBER,
                        on_change=lambda e: setattr(state, "max_premium", e.control.value),
                        **field_style,
                    ),
                    ft.Dropdown(
                        label="候选视角",
                        value=state.position_filter,
                        width=176,
                        options=[
                            ft.dropdown.Option("all", "全部候选"),
                            ft.dropdown.Option("unheld", "只看新机会"),
                            ft.dropdown.Option("held", "只看持仓观察"),
                            ft.dropdown.Option("watchlist", "只看自选池"),
                        ],
                        on_select=lambda e: setattr(state, "position_filter", e.control.value),
                        **field_style,
                    ),
                    ft.Container(
                        content=ft.Checkbox(
                            label=txt("只看未持有", size=13, color=p.text_muted),
                            value=state.only_unheld,
                            on_change=lambda e: setattr(state, "only_unheld", bool(e.control.value)),
                        ),
                        padding=ft.Padding.only(left=6, top=6),
                    ),
                    ft.Container(
                        content=ft.Row(
                            [ft.ProgressRing(width=16, height=16, visible=state.busy), txt("扫描中…", size=12, color=p.text_muted)],
                            spacing=8,
                        ),
                        visible=state.busy,
                    ),
                ],
                spacing=12,
                wrap=False,
            ),
            padding=16,
        )

    def build_sidebar(p: Palette):
        return ft.Container(
            width=236,
            bgcolor=with_alpha(p.surface, 0.88 if p.is_dark else 0.82),
            padding=ft.Padding.only(left=18, right=18, top=24, bottom=20),
            border=ft.Border.only(right=ft.BorderSide(1, p.border)),
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Container(
                                content=txt("低", size=16, color=p.on_accent, weight=ft.FontWeight.W_700),
                                width=38,
                                height=38,
                                bgcolor=p.accent,
                                border_radius=12,
                                alignment=ft.Alignment.CENTER,
                            ),
                            ft.Container(width=12),
                            ft.Column(
                                [
                                    txt("双低转债", size=15, color=p.text, weight=ft.FontWeight.W_700),
                                    txt("个人量化助手", size=11, color=p.text_faint),
                                ],
                                spacing=1,
                                tight=True,
                            ),
                        ],
                        spacing=0,
                    ),
                    ft.Container(height=28),
                    txt("工作区", size=11, color=p.text_faint),
                    ft.Container(height=8),
                    ft.Column(
                        [
                            nav_item(p, key, name, icon, state.view == key)
                            for key, name, icon in (
                                ("overview", "概览", ft.Icons.DASHBOARD_OUTLINED),
                                ("candidates", "候选池", ft.Icons.LEADERBOARD_OUTLINED),
                                ("review", "快照复盘", ft.Icons.HISTORY),
                                ("watchlist", "自选池", ft.Icons.BOOKMARK_OUTLINE),
                                ("holdings", "持仓维护", ft.Icons.ACCOUNT_BALANCE_WALLET_OUTLINED),
                            )
                        ],
                        spacing=4,
                        tight=True,
                    ),
                    ft.Container(expand=True),
                    ft.Container(height=12),
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.Text(
                                    "STORE://LOCAL CACHE",
                                    size=9,
                                    color=p.accent,
                                    font_family=MONO,
                                    font_family_fallback=MONO_FALLBACK,
                                ),
                                ft.Container(height=6),
                                mono(str(DATA_DIR), size=10, color=p.text_muted),
                            ],
                            spacing=0,
                            tight=True,
                        ),
                        padding=12,
                        bgcolor=p.surface_sunken,
                        border_radius=12,
                    ),
                ],
                spacing=0,
                tight=True,
            ),
        )

    def build_header(p: Palette):
        current = next((v for v in VIEWS if v[0] == state.view), VIEWS[0])
        result = state.result or {}
        feed_state = "SCANNING" if state.busy else ("ONLINE" if result else "STANDBY")
        feed_color = p.accent if state.busy or result else p.text_faint
        meta_chips = []
        if result.get("source_name"):
            meta_chips.append(chip(p, result["source_name"], tone="accent"))
        if result.get("scan_time"):
            meta_chips.append(chip(p, result["scan_time"]))

        scan_button = ft.Button(
            content=ft.Row(
                [
                    ft.ProgressRing(width=15, height=15, visible=state.busy, stroke_width=2),
                    ft.Icon(ft.Icons.SEARCH, size=16),
                    txt("扫描中…" if state.busy else "一键扫描双低转债", size=13),
                ],
                spacing=8,
                tight=True,
            ),
            on_click=run_scan,
            disabled=state.busy,
            expand=False,
            style=ft.ButtonStyle(
                bgcolor=p.accent,
                color=p.on_accent,
                padding=ft.Padding.symmetric(horizontal=22, vertical=15),
                shape=ft.RoundedRectangleBorder(radius=12),
                elevation=2,
                shadow_color=p.shadow,
            ),
        )

        particle_switch = ft.Switch(
            value=state.particle_effects,
            label=txt("粒子", size=11, color=p.text_muted),
            active_color=p.accent,
            on_change=lambda e: toggle_particle_effects(bool(e.control.value)),
        )
        power_switch = ft.Switch(
            value=state.particle_quality == "power",
            label=txt("省电", size=11, color=p.text_muted),
            active_color=p.accent,
            on_change=lambda e: set_particle_quality(
                "power" if e.control.value else "performance"
            ),
        )

        status_strip = ft.Container(
            content=ft.Row(
                [
                    ft.Container(
                        width=6,
                        height=6,
                        border_radius=3,
                        bgcolor=feed_color,
                    ),
                    ft.Text(
                        f"MARKET FEED {feed_state}",
                        size=9,
                        color=feed_color,
                        font_family=MONO,
                        font_family_fallback=MONO_FALLBACK,
                    ),
                    ft.Text("·", size=10, color=p.text_faint),
                    ft.Text(
                        "LOCAL SNAPSHOT SYNC",
                        size=9,
                        color=p.text_faint,
                        font_family=MONO,
                        font_family_fallback=MONO_FALLBACK,
                    ),
                    ft.Container(expand=True),
                    ft.Text(
                        f"{datetime.now():%H:%M:%S}  ·  QUANT CORE / 4K STARS",
                        size=9,
                        color=p.text_faint,
                        font_family=MONO,
                        font_family_fallback=MONO_FALLBACK,
                    ),
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            height=30,
            padding=ft.Padding.symmetric(horizontal=12, vertical=0),
            border_radius=8,
            bgcolor=with_alpha(p.surface_sunken, 0.72),
            border=ft.Border.all(1, with_alpha(p.border, 0.7)),
        )

        main_row = ft.Row(
            [
                ft.Column(
                    [
                        ft.Text(
                            current[0].upper(),
                            size=9,
                            color=p.accent,
                            font_family=MONO,
                            font_family_fallback=MONO_FALLBACK,
                            weight=ft.FontWeight.W_600,
                        ),
                        txt(current[1], size=26, color=p.text, weight=ft.FontWeight.W_700),
                        ft.Container(height=4),
                        txt(current[2], size=13, color=p.text_muted),
                    ],
                    spacing=1,
                    tight=True,
                ),
                ft.Container(expand=True),
                ft.Row(meta_chips, spacing=8),
                particle_switch,
                power_switch,
                scan_button,
            ],
            spacing=12,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        return ft.Column(
            [
                status_strip,
                ft.Container(height=12),
                main_row,
            ],
            spacing=0,
            tight=True,
        )

    def render():
        p = palette_for(state.dark)
        particle_controller.enabled = state.particle_effects
        particle_controller.set_options(state.particle_quality)
        begin_card_frame(state.particle_effects, state.particle_quality)
        warning_card = None
        if state.result and state.result.get("warning"):
            warning_card = card(
                p,
                ft.Row(
                    [
                        ft.Icon(ft.Icons.INFO_OUTLINE, size=18, color=p.accent),
                        ft.Container(width=10),
                        txt(state.result["warning"], size=12, color=p.text_muted),
                    ],
                    spacing=0,
                    tight=True,
                ),
                bgcolor=p.accent_soft,
                border=p.accent_soft,
                padding=14,
            )

        shell = ft.Row(
            [
                build_sidebar(p),
                ft.Container(
                    expand=True,
                    bgcolor=ft.Colors.TRANSPARENT,
                    padding=ft.Padding.only(left=28, right=28, top=24, bottom=24),
                    content=ft.Column(
                        [
                            build_header(p),
                            ft.Container(height=18),
                            build_filter_bar(p),
                            ft.Container(height=16),
                            ft.Container(
                                content=ft.Column(
                                    [
                                        build_view(p),
                                    ],
                                    spacing=0,
                                    expand=True,
                                    scroll=ft.ScrollMode.AUTO,
                                ),
                                expand=True,
                            ),
                            ft.Container(height=10),
                            txt(state.status, size=12, color=p.text_faint),
                        ],
                        spacing=0,
                        expand=True,
                    ),
                ),
            ],
            spacing=0,
            expand=True,
        )

        def on_console_hover(event):
            point = getattr(event, "local_position", None)
            if point is None:
                return
            particle_controller.set_parallax_position(
                point.x,
                point.y,
                float(page.width or 0),
                float(page.height or 0),
            )

        def on_console_exit(_event=None):
            particle_controller.reset_parallax()

        interactive_shell = ft.GestureDetector(
            content=shell,
            on_hover=on_console_hover,
            on_exit=on_console_exit,
            hover_interval=50,
            expand=True,
        )

        background_canvas = particle_controller.build_background(p.is_dark)
        root_controls = [background_canvas, interactive_shell]
        if scan_hud.active:
            root_controls.append(scan_hud.build())
        if splash.active:
            root_controls.append(splash.build())
        root = ft.Stack(
            controls=root_controls,
            expand=True,
            fit=ft.StackFit.EXPAND,
        )

        page.controls.clear()
        page.add(root)
        page.update()

    # ------------------------------------------------------------------ #
    # Boot
    # ------------------------------------------------------------------ #

    if os.getenv("QUANT_AUTOSCAN") == "1":
        try:
            apply_scan_result(assistant.scan_market(top_n=12))
        except Exception as exc:
            set_status(f"预扫描失败: {exc}")

    try:
        refresh_local_data()
        refresh_review_data()
        if state.recent_snapshots:
            set_status("已加载最近快照与本地自选池，可直接开始新一轮扫描。")
    except Exception:
        pass

    render()
    if splash.active:
        page.run_task(splash.play)


if __name__ == "__main__":
    if ft is None:
        raise RuntimeError("未安装 flet。请先执行 pip install -r requirements.txt")
    ft.run(
        main,
        assets_dir=str(Path(__file__).resolve().parent / "assets"),
    )

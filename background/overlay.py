"""Standalone launcher for the particle background.

Two roles in one file:

1. **Static + control server** (standard library only) — serves the
   `background/` folder and exposes a tiny JSON API the page talks to:
   * ``GET  /api/config`` -> ``{"count": 2000, "quality": "performance"}``
   * ``POST /api/event``  -> the page reports selections (e.g. the core mesh)
   * ``GET  /api/state``  -> the recorded events
   The Flet app reads/writes the same JSON files, so the desktop app and the
   background scene stay in sync without any IPC framework.

2. **Overlay window** — when ``pywebview`` is installed the scene can be shown
   in a frameless, transparent, always-on-top window that behaves like a
   dynamic wallpaper. Without pywebview the scene simply opens in the default
   browser (full screen for the "website background" use case).

Usage::

    python background/overlay.py                 # browser, default count
    python background/overlay.py --count 4000    # denser field
    python background/overlay.py --overlay       # frameless overlay window
    python background/overlay.py --port 9000
"""

from __future__ import annotations

import argparse
import json
import os
import threading
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
DATA_DIR = PROJECT_DIR / "data"
CONFIG_PATH = DATA_DIR / "particle_config.json"
EVENT_PATH = DATA_DIR / "particle_events.json"

DEFAULT_COUNT = 4000
DEFAULT_QUALITY = "performance"


# --------------------------------------------------------------------------- #
# Shared state (files, so the Flet app and the scene can talk without sockets)
# --------------------------------------------------------------------------- #


def read_config() -> dict:
    config = {"count": DEFAULT_COUNT, "quality": DEFAULT_QUALITY}
    try:
        if CONFIG_PATH.exists():
            stored = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(stored, dict):
                config.update(
                    {
                        "count": int(stored.get("count", config["count"])),
                        "quality": str(stored.get("quality", config["quality"])),
                    }
                )
    except (OSError, ValueError, TypeError):
        pass
    return config


def write_config(count: int | None = None, quality: str | None = None) -> dict:
    config = read_config()
    if count is not None:
        config["count"] = max(1, int(count))
    if quality is not None:
        config["quality"] = "power" if quality == "power" else "performance"
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(
            json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError:
        pass
    return config


def append_event(payload: dict) -> None:
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        events = []
        if EVENT_PATH.exists():
            loaded = json.loads(EVENT_PATH.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                events = loaded
        events.append(payload)
        events = events[-50:]
        EVENT_PATH.write_text(
            json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except (OSError, ValueError, TypeError):
        pass


def read_events() -> list:
    try:
        if EVENT_PATH.exists():
            loaded = json.loads(EVENT_PATH.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                return loaded
    except (OSError, ValueError, TypeError):
        pass
    return []


# --------------------------------------------------------------------------- #
# HTTP server
# --------------------------------------------------------------------------- #


class BackgroundRequestHandler(SimpleHTTPRequestHandler):
    """Serves the scene folder plus the tiny JSON control API."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BASE_DIR), **kwargs)

    def log_message(self, fmt, *args):  # keep the console quiet
        pass

    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802 - stdlib naming
        if self.path.startswith("/api/config"):
            self._send_json(read_config())
            return
        if self.path.startswith("/api/state"):
            events = read_events()
            self._send_json({"events": events, "last": events[-1] if events else None})
            return
        if self.path in ("/", "/index.html"):
            self.path = "/index.html"
        super().do_GET()

    def do_POST(self):  # noqa: N802 - stdlib naming
        if self.path.startswith("/api/event"):
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(raw.decode("utf-8") or "{}")
            except ValueError:
                payload = {}
            if not isinstance(payload, dict):
                payload = {"value": payload}
            append_event(payload)
            self._send_json({"ok": True})
            return
        if self.path.startswith("/api/config"):
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(raw.decode("utf-8") or "{}")
            except ValueError:
                payload = {}
            config = write_config(
                count=payload.get("count"),
                quality=payload.get("quality"),
            )
            self._send_json(config)
            return
        self._send_json({"ok": False, "error": "unknown endpoint"}, status=404)


def start_server(port: int) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", port), BackgroundRequestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


def main() -> None:
    parser = argparse.ArgumentParser(description="Particle background launcher")
    parser.add_argument("--port", type=int, default=8777)
    parser.add_argument("--count", type=int, default=None)
    parser.add_argument("--quality", choices=("performance", "power"), default=None)
    parser.add_argument(
        "--overlay",
        action="store_true",
        help="open a frameless transparent always-on-top window (needs pywebview)",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="only start the control server, do not open a window",
    )
    args = parser.parse_args()

    write_config(count=args.count, quality=args.quality)
    config = read_config()

    server = start_server(args.port)
    url = f"http://127.0.0.1:{args.port}/index.html"
    print(f"粒子背景服务已启动: {url}")
    print(f"配置: {json.dumps(config, ensure_ascii=False)}")

    if args.no_browser:
        try:
            while True:
                threading.Event().wait(3600)
        except KeyboardInterrupt:
            pass
        finally:
            server.shutdown()
        return

    if args.overlay:
        try:
            import webview  # pywebview
        except ImportError:
            print(
                "未安装 pywebview，改为在默认浏览器中打开。"
                "安装方式: pip install pywebview"
            )
            webbrowser.open(url)
        else:
            webview.create_window(
                "粒子背景",
                url,
                width=1280,
                height=800,
                frameless=True,
                transparent=True,
                on_top=True,
                easy_drag=False,
            )
            webview.start()
            return

    webbrowser.open(url)
    print("按 Ctrl+C 结束。")
    try:
        while True:
            threading.Event().wait(3600)
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()

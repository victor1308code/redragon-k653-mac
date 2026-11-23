#!/usr/bin/env python3
"""
Redragon K653-RGB-PRO macOS Control Center — Local HTTP & REST API server (127.0.0.1:18493).
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

BASE_DIR = Path(__file__).resolve().parent
UI_DIR = BASE_DIR / "ui"
ASSETS_DIR = BASE_DIR / "assets"

sys.path.insert(0, str(BASE_DIR))
import device_manager

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 18493


class ControlHandler(BaseHTTPRequestHandler):
    server_version = "RedragonK653Mac/1.0"

    def log_message(self, format: str, *args: Any) -> None:
        if getattr(self.server, "verbose", False):
            super().log_message(format, *args)

    def _send_json(self, payload: Any, status: int = 200) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def _send_file(self, path: Path) -> None:
        if not path.exists() or not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "File not found")
            return
        mime, _ = mimetypes.guess_type(str(path))
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mime or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        if not raw:
            return {}
        parsed = json.loads(raw.decode("utf-8"))
        return parsed if isinstance(parsed, dict) else {}

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        req_path = unquote(parsed.path)

        if req_path in ("/", "/index.html"):
            self._send_file(UI_DIR / "index.html")
            return

        if req_path.startswith("/assets/"):
            rel = req_path[len("/assets/"):]
            candidate = (ASSETS_DIR / rel).resolve()
            if ASSETS_DIR.resolve() not in candidate.parents:
                self.send_error(HTTPStatus.FORBIDDEN, "Forbidden")
                return
            self._send_file(candidate)
            return

        if req_path == "/api/status":
            self._send_json(device_manager.get_status(read_hw=False))
            return

        if req_path == "/api/health":
            self._send_json({"ok": True, "service": "RedragonK653Mac"})
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        req_path = unquote(parsed.path)
        try:
            body = self._read_json_body()
            if req_path == "/api/apply":
                updates = body.get("config") or body.get("updates") or body
                self._send_json(device_manager.apply_settings(updates=updates))
                return

            if req_path == "/api/reset":
                self._send_json(device_manager.apply_settings(reset_defaults=True))
                return

            if req_path == "/api/read-hw":
                self._send_json(device_manager.get_status(read_hw=True))
                return

            if req_path == "/api/live-rgb":
                self._send_json(device_manager.send_live_rgb(body.get("custom_key_colors")))
                return

            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
        except Exception as exc:
            self._send_json({"ok": False, "error": str(exc)}, status=400)


def main() -> int:
    parser = argparse.ArgumentParser(description="Redragon K653-RGB-PRO macOS Control Server")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    srv = ThreadingHTTPServer((args.host, args.port), ControlHandler)
    srv.daemon_threads = True
    srv.verbose = args.verbose  # type: ignore[attr-defined]
    device_manager.start_background_monitor()
    print(f"Redragon K653 Control running at http://{args.host}:{args.port}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Shared Playwright E2E test harness for Classic Tetris Web Application.

All helpers in this module are strictly opaque-box:
- Never access or mutate ``window.Tetris.*`` internal module state.
- Never assume uncontracted CSS class names such as ``.hidden`` or ``.active``;
  check computed DOM visibility via :func:`is_element_visible` instead.
- Drive user interactions exclusively via real browser surfaces (``file://``,
  local HTTP/subpath server, DOM selectors, keyboard, CDP touch events,
  mocked ``navigator.getGamepads()``, ``localStorage``, and Pillow pixel diffs).
"""

from __future__ import annotations

import io
import json
import math
import mimetypes
import re
import threading
import time
import unittest
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import unquote, urlsplit

from PIL import Image, ImageChops
from playwright.sync_api import Browser, BrowserContext, CDPSession, Page, Playwright, sync_playwright

# ---------------------------------------------------------------------------
# Constants & Interface Contracts (PROJECT.md § 2, § 7)
# ---------------------------------------------------------------------------

PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]

STORAGE_KEY: str = "tetris_clasico_v1"
CACHE_NAME: str = "tetris-clasico-v1"
CACHE_PREFIX: str = "tetris-clasico-"

DIANA_STORAGE_KEY: str = "diana_sudoku_v1"
DIANA_CACHE_NAME: str = "diana-sudoku-v1"

DEFAULT_STORAGE_STATE: dict[str, Any] = {
    "bestScore": 0,
    "bestLevel": 0,
    "bestLines": 0,
    "touchSensitivity": 5,
    "musicEnabled": True,
    "sfxEnabled": True,
    "startLevel": 1,
}

DESKTOP_VIEWPORT: tuple[int, int] = (1440, 900)
MOBILE_VIEWPORT: tuple[int, int] = (390, 844)
SMALL_MOBILE_VIEWPORT: tuple[int, int] = (375, 667)

PIECE_PALETTE: dict[str, tuple[int, int, int]] = {
    "I": (34, 211, 238),   # #22d3ee
    "O": (250, 204, 21),   # #facc15
    "T": (192, 132, 252),  # #c084fc
    "S": (74, 222, 128),   # #4ade80
    "Z": (248, 113, 113),  # #f87171
    "J": (96, 165, 250),   # #60a5fa
    "L": (251, 146, 60),   # #fb923c
}

SELECTORS: dict[str, str] = {
    "board_stage": "#board-stage",
    "board_canvas": "#board-canvas",
    "hold_box": "#hold-box",
    "hold_canvas": "#hold-canvas",
    "next_canvas": "#next-canvas",
    "score_value": "#score-value",
    "level_value": "#level-value",
    "lines_value": "#lines-value",
    "best_score_value": "#best-score-value",
    "best_level_value": "#best-level-value",
    "best_lines_value": "#best-lines-value",
    "btn_pause": "#btn-pause",
    "btn_settings": "#btn-settings",
    "btn_music": "#btn-music",
    "btn_sfx": "#btn-sfx",
    "gamepad_badge": "#gamepad-badge",
    "overlay_start": "#overlay-start",
    "btn_level_down": "#btn-level-down",
    "start_level_value": "#start-level-value",
    "btn_level_up": "#btn-level-up",
    "btn_play": "#btn-play",
    "btn_start_settings": "#btn-start-settings",
    "overlay_pause": "#overlay-pause",
    "btn_resume": "#btn-resume",
    "btn_pause_settings": "#btn-pause-settings",
    "btn_restart": "#btn-restart",
    "overlay_gameover": "#overlay-gameover",
    "final_score_value": "#final-score-value",
    "final_level_value": "#final-level-value",
    "final_lines_value": "#final-lines-value",
    "gameover_record_badge": "#gameover-record-badge",
    "btn_play_again": "#btn-play-again",
    "btn_gameover_settings": "#btn-gameover-settings",
    "modal_settings": "#modal-settings",
    "sensitivity_slider": "#sensitivity-slider",
    "sensitivity_value": "#sensitivity-value",
    "toggle_music": "#toggle-music",
    "toggle_sfx": "#toggle-sfx",
    "settings_gamepad_status": "#settings-gamepad-status",
    "btn_close_settings": "#btn-close-settings",
}

MIME_TYPES: dict[str, str] = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".webmanifest": "application/manifest+json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".json": "application/json; charset=utf-8",
    ".ico": "image/x-icon",
    ".txt": "text/plain; charset=utf-8",
}

_LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
_LOCAL_SCHEMES = frozenset({"http", "https", "file", "data", "blob", "about"})


# ---------------------------------------------------------------------------
# Local Static HTTP / GitHub Pages Subpath Server
# ---------------------------------------------------------------------------


class _StaticRequestHandler(BaseHTTPRequestHandler):
    """HTTP/1.1 static handler with strict traversal protection and Connection: close."""

    protocol_version = "HTTP/1.1"
    server: "_InternalHTTPServer"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return

    def handle(self) -> None:
        try:
            super().handle()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def _send_response_bytes(
        self,
        status: int,
        content_type: str,
        body: bytes,
        *,
        send_body: bool,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self.server.owner._record_request(self.command, self.path, status)
        try:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            cache_control = self.server.owner.cache_control
            if cache_control is not None:
                self.send_header("Cache-Control", cache_control)
            if extra_headers:
                for hdr_name, hdr_val in extra_headers.items():
                    self.send_header(hdr_name, hdr_val)
            self.end_headers()
            if send_body and body:
                self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def _handle_static(self, *, send_body: bool) -> None:
        raw_target = self.path.split("#", 1)[0]
        raw_path, _, raw_query = raw_target.partition("?")

        if not raw_path.startswith("/") or raw_path.startswith("//") or "://" in raw_path:
            self._send_response_bytes(
                404,
                "text/plain; charset=utf-8",
                b"Not Found",
                send_body=send_body,
            )
            return

        if "\x00" in raw_path:
            self._send_response_bytes(
                400,
                "text/plain; charset=utf-8",
                b"Bad Request",
                send_body=send_body,
            )
            return

        if "\\" in raw_path:
            self._send_response_bytes(
                403,
                "text/plain; charset=utf-8",
                b"Forbidden",
                send_body=send_body,
            )
            return

        unquoted_path = unquote(raw_path)

        if "\x00" in unquoted_path:
            self._send_response_bytes(
                400,
                "text/plain; charset=utf-8",
                b"Bad Request",
                send_body=send_body,
            )
            return

        if "\\" in unquoted_path or ".." in unquoted_path.split("/"):
            self._send_response_bytes(
                403,
                "text/plain; charset=utf-8",
                b"Forbidden",
                send_body=send_body,
            )
            return

        if unquoted_path.startswith("//"):
            self._send_response_bytes(
                404,
                "text/plain; charset=utf-8",
                b"Not Found",
                send_body=send_body,
            )
            return

        owner = self.server.owner
        if owner.bare_prefix is not None and unquoted_path == owner.bare_prefix:
            location = owner.base_prefix + (f"?{raw_query}" if raw_query else "")
            self._send_response_bytes(
                301,
                "text/plain; charset=utf-8",
                b"",
                send_body=send_body,
                extra_headers={"Location": location},
            )
            return

        if not unquoted_path.startswith(owner.base_prefix):
            self._send_response_bytes(
                404,
                "text/plain; charset=utf-8",
                b"Not Found",
                send_body=send_body,
            )
            return

        rel_path = unquoted_path[len(owner.base_prefix):].lstrip("/")
        if rel_path == "":
            rel_path = "index.html"

        try:
            target = (owner.root_dir / rel_path).resolve()
        except OSError:
            self._send_response_bytes(
                400,
                "text/plain; charset=utf-8",
                b"Bad Request",
                send_body=send_body,
            )
            return

        if not target.is_relative_to(owner.root_dir):
            self._send_response_bytes(
                403,
                "text/plain; charset=utf-8",
                b"Forbidden",
                send_body=send_body,
            )
            return

        if target.is_dir():
            index_candidate = (target / "index.html").resolve()
            if index_candidate.is_relative_to(owner.root_dir) and index_candidate.is_file():
                target = index_candidate
            else:
                self._send_response_bytes(
                    404,
                    "text/plain; charset=utf-8",
                    b"Not Found",
                    send_body=send_body,
                )
                return

        if not target.is_file():
            self._send_response_bytes(
                404,
                "text/plain; charset=utf-8",
                b"Not Found",
                send_body=send_body,
            )
            return

        suffix = target.suffix.lower()
        content_type = (
            MIME_TYPES.get(suffix)
            or mimetypes.guess_type(str(target))[0]
            or "application/octet-stream"
        )
        try:
            payload = target.read_bytes()
        except OSError:
            self._send_response_bytes(
                404,
                "text/plain; charset=utf-8",
                b"Not Found",
                send_body=send_body,
            )
            return

        self._send_response_bytes(200, content_type, payload, send_body=send_body)

    def do_GET(self) -> None:
        self._handle_static(send_body=True)

    def do_HEAD(self) -> None:
        self._handle_static(send_body=False)


class _InternalHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True
    request_queue_size = 64

    def __init__(self, server_address: tuple[str, int], owner: "StaticAppServer") -> None:
        self.owner = owner
        super().__init__(server_address, _StaticRequestHandler)


class StaticAppServer:
    """Thread-safe static HTTP server supporting root ``/`` or subpath prefixes.

    Mirrors GitHub Pages subpath hosting (e.g. ``/tetris-clasico/`` with ``301``
    trailing-slash redirect on ``/tetris-clasico``), enforces path/symlink
    containment, emits explicit MIME types, and closes cleanly without socket
    or thread leaks.
    """

    def __init__(
        self,
        root_dir: str | Path = PROJECT_ROOT,
        *,
        base_prefix: str = "/",
        cache_control: str | None = "no-store",
    ) -> None:
        self.root_dir: Path = Path(root_dir).resolve()
        normalized = base_prefix.strip()
        if not normalized or normalized == "/":
            self.base_prefix: str = "/"
            self.bare_prefix: str | None = None
        else:
            if not normalized.startswith("/"):
                normalized = "/" + normalized
            if not normalized.endswith("/"):
                normalized = normalized + "/"
            self.base_prefix = normalized
            self.bare_prefix = normalized.rstrip("/")
        self.cache_control: str | None = cache_control

        self._lock = threading.Lock()
        self._requests: list[dict[str, Any]] = []
        self._httpd: _InternalHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._port: int | None = None

    def _record_request(self, method: str, path: str, status: int) -> None:
        with self._lock:
            self._requests.append({"method": method, "path": path, "status": status})

    def get_requests(self) -> list[dict[str, Any]]:
        """Return a snapshot copy of recorded HTTP requests."""
        with self._lock:
            return [dict(item) for item in self._requests]

    def clear_requests(self) -> None:
        """Clear the recorded request log."""
        with self._lock:
            self._requests.clear()

    def start(self) -> "StaticAppServer":
        """Bind to ``127.0.0.1:0`` and begin serving in a daemon thread."""
        if self._httpd is not None:
            return self
        httpd = _InternalHTTPServer(("127.0.0.1", 0), self)
        self._port = int(httpd.server_address[1])
        self._httpd = httpd
        thread = threading.Thread(
            target=httpd.serve_forever,
            kwargs={"poll_interval": 0.1},
            name=f"StaticAppServer-{self._port}",
            daemon=True,
        )
        self._thread = thread
        thread.start()
        return self

    def stop(self) -> None:
        """Stop the server, close its listening socket, and join its thread."""
        httpd = self._httpd
        thread = self._thread
        self._httpd = None
        self._thread = None
        if httpd is not None:
            try:
                httpd.shutdown()
            finally:
                httpd.server_close()
        if thread is not None:
            thread.join(timeout=5.0)

    @property
    def port(self) -> int:
        """Bound TCP port (cached so it remains readable after ``stop()``)."""
        if self._port is None:
            raise RuntimeError("StaticAppServer has not been started yet.")
        return self._port

    @property
    def origin(self) -> str:
        """Origin string ``http://127.0.0.1:<port>``."""
        return f"http://127.0.0.1:{self.port}"

    @property
    def base_url(self) -> str:
        """Full base URL including trailing slash (e.g. ``http://127.0.0.1:PORT/``)."""
        return f"{self.origin}{self.base_prefix}"

    @property
    def bare_prefix_url(self) -> str | None:
        """Base URL without trailing slash when ``base_prefix != '/'``, else ``None``."""
        if self.bare_prefix is None:
            return None
        return f"{self.origin}{self.bare_prefix}"

    def url_for(self, rel_path: str = "") -> str:
        """Build an absolute URL under ``base_url`` for ``rel_path``."""
        if not rel_path:
            return self.base_url
        if rel_path.startswith("?"):
            return f"{self.base_url}{rel_path}"
        cleaned = rel_path.lstrip("/")
        if cleaned.startswith("./"):
            cleaned = cleaned[2:]
        return f"{self.base_url}{cleaned}"

    def __enter__(self) -> "StaticAppServer":
        return self.start()

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.stop()


# ---------------------------------------------------------------------------
# URL & Browser Init-Script Helpers (Opaque-Box Only)
# ---------------------------------------------------------------------------


def file_uri(path: str | Path) -> str:
    """Convert a local filesystem path into a canonical ``file://`` URI."""
    return Path(path).resolve().as_uri()


def make_gamepad_init_script() -> str:
    """Return an init script installing ``window.__e2eGamepad`` & dynamic ``navigator.getGamepads()``.

    Supports 4 gamepad slots, monotonic timestamps, ``GamepadEvent.prototype``
    events with own ``gamepad`` property, arbitrary button/axis counts, and
    non-standard ``mapping`` strings.
    """
    return """
(function () {
  var slots = [null, null, null, null];
  var lastTs = 0;

  function nextTimestamp() {
    var now = (typeof performance !== 'undefined' && performance.now) ? performance.now() : Date.now();
    if (now <= lastTs) now = lastTs + 1;
    lastTs = now;
    return now;
  }

  function clonePad(pad) {
    if (!pad) return null;
    return {
      id: pad.id,
      index: pad.index,
      connected: pad.connected,
      mapping: pad.mapping,
      timestamp: pad.timestamp,
      axes: pad.axes.slice(),
      buttons: pad.buttons.map(function (b) {
        return { pressed: !!b.pressed, touched: !!b.touched, value: Number(b.value) };
      }),
      vibrationActuator: null,
      hapticActuators: []
    };
  }

  function dispatchGamepadEvent(type, padSnapshot) {
    var ev = new Event(type);
    if (typeof GamepadEvent !== 'undefined' && GamepadEvent.prototype) {
      try { Object.setPrototypeOf(ev, GamepadEvent.prototype); } catch (_) {}
    }
    Object.defineProperty(ev, 'gamepad', {
      value: padSnapshot,
      enumerable: true,
      configurable: true
    });
    window.dispatchEvent(ev);
  }

  function makePad(opts) {
    opts = opts || {};
    var idx = typeof opts.index === 'number' ? opts.index : 0;
    if (idx < 0 || idx > 3) throw new RangeError('Gamepad index must be 0..3');
    var btnCount = typeof opts.buttonCount === 'number' ? opts.buttonCount : 17;
    var axisCount = typeof opts.axisCount === 'number' ? opts.axisCount : 4;
    var buttons = [];
    for (var i = 0; i < btnCount; i++) {
      buttons.push({ pressed: false, touched: false, value: 0 });
    }
    var axes = [];
    for (var j = 0; j < axisCount; j++) {
      axes.push(0);
    }
    return {
      id: opts.id !== undefined ? String(opts.id) : 'Xbox Wireless Controller (STANDARD GAMEPAD Vendor: 045e Product: 02fd)',
      index: idx,
      connected: true,
      mapping: opts.mapping !== undefined ? String(opts.mapping) : 'standard',
      timestamp: nextTimestamp(),
      axes: axes,
      buttons: buttons
    };
  }

  Object.defineProperty(navigator, 'getGamepads', {
    configurable: true,
    writable: true,
    value: function getGamepads() {
      return [clonePad(slots[0]), clonePad(slots[1]), clonePad(slots[2]), clonePad(slots[3])];
    }
  });

  window.__e2eGamepad = {
    connect: function (opts) {
      var pad = makePad(opts);
      slots[pad.index] = pad;
      var snap = clonePad(pad);
      dispatchGamepadEvent('gamepadconnected', snap);
      return snap;
    },
    disconnect: function (index) {
      var idx = typeof index === 'number' ? index : 0;
      var pad = slots[idx];
      if (!pad) return false;
      pad.connected = false;
      pad.timestamp = nextTimestamp();
      var snap = clonePad(pad);
      slots[idx] = null;
      dispatchGamepadEvent('gamepaddisconnected', snap);
      return true;
    },
    setButton: function (buttonIndex, pressed, value, padIndex) {
      var idx = typeof padIndex === 'number' ? padIndex : 0;
      var pad = slots[idx];
      if (!pad) throw new Error('No gamepad connected at index ' + idx);
      if (buttonIndex < 0 || buttonIndex >= pad.buttons.length) {
        throw new RangeError('Button index out of range: ' + buttonIndex);
      }
      var isPressed = !!pressed;
      var numVal = (value !== undefined && value !== null) ? Number(value) : (isPressed ? 1 : 0);
      pad.buttons[buttonIndex] = {
        pressed: isPressed,
        touched: isPressed || numVal > 0,
        value: numVal
      };
      pad.timestamp = nextTimestamp();
      return clonePad(pad);
    },
    setAxis: function (axisIndex, value, padIndex) {
      var idx = typeof padIndex === 'number' ? padIndex : 0;
      var pad = slots[idx];
      if (!pad) throw new Error('No gamepad connected at index ' + idx);
      if (axisIndex < 0 || axisIndex >= pad.axes.length) {
        throw new RangeError('Axis index out of range: ' + axisIndex);
      }
      pad.axes[axisIndex] = Number(value);
      pad.timestamp = nextTimestamp();
      return clonePad(pad);
    },
    resetInputs: function (padIndex) {
      var idx = typeof padIndex === 'number' ? padIndex : 0;
      var pad = slots[idx];
      if (!pad) throw new Error('No gamepad connected at index ' + idx);
      for (var i = 0; i < pad.buttons.length; i++) {
        pad.buttons[i] = { pressed: false, touched: false, value: 0 };
      }
      for (var j = 0; j < pad.axes.length; j++) {
        pad.axes[j] = 0;
      }
      pad.timestamp = nextTimestamp();
      return clonePad(pad);
    },
    getState: function (padIndex) {
      var idx = typeof padIndex === 'number' ? padIndex : 0;
      return clonePad(slots[idx]);
    }
  };
})();
"""


def make_lcg_init_script(seed: int) -> str:
    """Return an init script replacing ``Math.random`` with a deterministic 32-bit LCG."""
    seed_int = int(seed)
    return f"""
(function () {{
  var state = ({seed_int} >>> 0) || 1;
  Math.random = function () {{
    state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
    return state / 4294967296;
  }};
}})();
"""


def make_local_storage_fault_script(
    mode: str = "set_only",
    error_name: str = "QuotaExceededError",
) -> str:
    """Return an init script injecting ``localStorage`` failures.

    ``mode`` must be one of ``'set_only'``, ``'all_methods'``, or ``'getter'``.
    Includes an ``about:`` protocol guard so Playwright's initial ``about:blank``
    does not interfere with target-origin initialization.
    """
    if mode not in ("set_only", "all_methods", "getter"):
        raise ValueError(f"Unsupported localStorage fault mode: {mode!r}")
    return f"""
(function () {{
  if (location.protocol === 'about:') return;
  var mode = {json.dumps(mode)};
  var errName = {json.dumps(error_name)};
  function makeErr(op) {{
    return new DOMException('Simulated ' + errName + ' on ' + op, errName);
  }}
  if (mode === 'getter') {{
    Object.defineProperty(window, 'localStorage', {{
      configurable: true,
      get: function () {{ throw makeErr('localStorage'); }}
    }});
    return;
  }}
  var realLS = window.localStorage;
  var origGet = Storage.prototype.getItem;
  var origSet = Storage.prototype.setItem;
  var origRemove = Storage.prototype.removeItem;
  var origClear = Storage.prototype.clear;
  Storage.prototype.setItem = function (k, v) {{
    if (this === realLS) throw makeErr('setItem');
    return origSet.call(this, k, v);
  }};
  if (mode === 'all_methods') {{
    Storage.prototype.getItem = function (k) {{
      if (this === realLS) throw makeErr('getItem');
      return origGet.call(this, k);
    }};
    Storage.prototype.removeItem = function (k) {{
      if (this === realLS) throw makeErr('removeItem');
      return origRemove.call(this, k);
    }};
    Storage.prototype.clear = function () {{
      if (this === realLS) throw makeErr('clear');
      return origClear.call(this);
    }};
  }}
}})();
"""


def make_local_storage_seed_script(
    key: str,
    raw_value: str,
    *,
    seed_once: bool = True,
) -> str:
    """Return an init script seeding ``localStorage[key] = raw_value`` before app boot.

    Uses an ``about:`` guard plus ``sessionStorage`` (with ``window.name``
    fallback) so ``seed_once=True`` applies on the first real-origin load only
    and survives subsequent reloads to verify app recovery.
    """
    return f"""
(function () {{
  if (location.protocol === 'about:') return;
  var key = {json.dumps(key)};
  var val = {json.dumps(raw_value)};
  var seedOnce = {json.dumps(bool(seed_once))};
  if (seedOnce) {{
    var marker = '__e2e_seeded_' + key;
    var done = false;
    try {{ done = sessionStorage.getItem(marker) === '1'; }}
    catch (_) {{ done = (window.name || '').indexOf(marker) !== -1; }}
    if (done) return;
    try {{ sessionStorage.setItem(marker, '1'); }}
    catch (_) {{ window.name = (window.name ? window.name + '|' : '') + marker; }}
  }}
  localStorage.setItem(key, val);
}})();
"""


# ---------------------------------------------------------------------------
# Service Worker Offline & Diana Sudoku Sibling Isolation Helpers
# ---------------------------------------------------------------------------


def wait_for_service_worker_controlled(page: Page, timeout_ms: int = 10000) -> dict[str, Any]:
    """Wait until the active Service Worker finishes activating AND controls ``page``.

    Resolves the Chromium ``navigator.serviceWorker.ready`` vs ``'activating'`` /
    ``controller === null`` race:
    1. Waits for ``navigator.serviceWorker.ready`` and ``reg.active.state === 'activated'``.
    2. Waits briefly for ``controllerchange`` if ``clients.claim()`` is pending.
    3. If ``navigator.serviceWorker.controller`` is still ``null``, performs a single
       online ``page.reload(wait_until='load')`` and verifies ``controller !== null``.
    """
    deadline = time.monotonic() + (timeout_ms / 1000.0)

    def _remaining_ms() -> int:
        return max(100, int((deadline - time.monotonic()) * 1000))

    async_wait_js = """async (waitMs) => {
      if (!('serviceWorker' in navigator)) {
        throw new Error('navigator.serviceWorker is unavailable on this origin');
      }
      const timer = (ms) => new Promise((_, reject) =>
        setTimeout(() => reject(new Error('Timed out waiting for Service Worker activation')), ms)
      );
      const waitActivated = async () => {
        const reg = await navigator.serviceWorker.ready;
        const sw = reg.active || reg.waiting || reg.installing;
        if (!sw) {
          throw new Error('ServiceWorkerRegistration ready resolved without a worker');
        }
        if (sw.state !== 'activated') {
          await new Promise((resolve, reject) => {
            const onChange = () => {
              if (sw.state === 'activated') {
                sw.removeEventListener('statechange', onChange);
                resolve();
              } else if (sw.state === 'redundant') {
                sw.removeEventListener('statechange', onChange);
                reject(new Error('Service Worker became redundant before activating'));
              }
            };
            sw.addEventListener('statechange', onChange);
            if (sw.state === 'activated') {
              sw.removeEventListener('statechange', onChange);
              resolve();
            }
          });
        }
        if (!navigator.serviceWorker.controller) {
          await new Promise((resolve) => {
            const done = () => {
              navigator.serviceWorker.removeEventListener('controllerchange', done);
              resolve();
            };
            navigator.serviceWorker.addEventListener('controllerchange', done);
            setTimeout(done, 450);
          });
        }
        return {
          scope: reg.scope,
          state: (reg.active && reg.active.state) || sw.state,
          scriptURL: (reg.active && reg.active.scriptURL) || sw.scriptURL || '',
          controlled: Boolean(navigator.serviceWorker.controller)
        };
      };
      return await Promise.race([waitActivated(), timer(waitMs)]);
    }"""

    info = page.evaluate(async_wait_js, _remaining_ms())
    reloaded = False
    if not info["controlled"]:
        if time.monotonic() >= deadline:
            raise TimeoutError("Timed out before Service Worker controlled page.")
        page.reload(wait_until="load")
        reloaded = True
        info = page.evaluate(async_wait_js, _remaining_ms())
        if not info["controlled"]:
            raise RuntimeError(
                f"Service Worker activated ({info['scope']}) but navigator.serviceWorker.controller "
                "remained null after reload."
            )

    info["reloaded"] = reloaded
    return info


def _extract_origin(url_or_origin: str) -> str:
    parsed = urlsplit(url_or_origin)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return url_or_origin.rstrip("/")


def seed_diana_sudoku_sibling(
    context: BrowserContext,
    origin: str,
    *,
    diana_key: str = DIANA_STORAGE_KEY,
    diana_payload: dict[str, Any] | str | None = None,
    diana_cache_name: str = DIANA_CACHE_NAME,
    diana_cache_entries: dict[str, str] | None = None,
    stale_tetris_caches: Sequence[str] | None = None,
) -> None:
    """Seed same-origin *Diana Sudoku* ``localStorage`` and ``CacheStorage`` via a disposable page.

    Also optionally creates stale ``tetris-clasico-*`` caches so tests can assert
    that Tetris SW activation prunes old Tetris caches while leaving Diana Sudoku intact.
    Unroutes and closes the disposable page cleanly so main-page SW requests are unaffected.
    """
    base_origin = _extract_origin(origin)
    seed_url = f"{base_origin}/__e2e_diana_seed__.html"
    if diana_payload is None:
        raw_diana = json.dumps({"bestSeconds": 87, "completed": 12})
    elif isinstance(diana_payload, str):
        raw_diana = diana_payload
    else:
        raw_diana = json.dumps(diana_payload)

    if diana_cache_entries is None:
        diana_cache_entries = {
            "/diana-sudoku/index.html": "<!doctype html><title>Diana Sudoku</title>",
        }

    seed_page = context.new_page()

    def _fulfill(route: Any) -> None:
        route.fulfill(
            status=200,
            content_type="text/html; charset=utf-8",
            body="<!doctype html><title>Diana Seed</title>",
        )

    seed_page.route(seed_url, _fulfill)
    try:
        seed_page.goto(seed_url, wait_until="load")
        seed_page.evaluate(
            """async ({ dianaKey, rawDiana, cacheName, entries, staleCaches }) => {
              localStorage.setItem(dianaKey, rawDiana);
              if ('caches' in window) {
                const dianaCache = await caches.open(cacheName);
                for (const [path, body] of Object.entries(entries)) {
                  await dianaCache.put(
                    path,
                    new Response(body, { status: 200, headers: { 'Content-Type': 'text/html; charset=utf-8' } })
                  );
                }
                for (const staleName of (staleCaches || [])) {
                  const stale = await caches.open(staleName);
                  await stale.put('/__stale__.txt', new Response('stale', { status: 200 }));
                }
              }
            }""",
            {
                "dianaKey": diana_key,
                "rawDiana": raw_diana,
                "cacheName": diana_cache_name,
                "entries": diana_cache_entries,
                "staleCaches": list(stale_tetris_caches or []),
            },
        )
    finally:
        try:
            seed_page.unroute(seed_url, _fulfill)
        except Exception:
            pass
        seed_page.close()


def read_diana_sudoku_sibling(
    page: Page,
    *,
    diana_key: str = DIANA_STORAGE_KEY,
    diana_cache_name: str = DIANA_CACHE_NAME,
    diana_cache_url: str = "/diana-sudoku/index.html",
) -> dict[str, Any]:
    """Read *Diana Sudoku* sibling state from ``localStorage`` and ``CacheStorage``."""
    return page.evaluate(
        """async ({ dianaKey, cacheName, entryUrl }) => {
          const raw = localStorage.getItem(dianaKey);
          let parsed = null;
          if (raw !== null) {
            try { parsed = JSON.parse(raw); } catch (_) { parsed = null; }
          }
          let cacheNames = [];
          let hasCache = false;
          let entryText = null;
          if ('caches' in window) {
            cacheNames = await caches.keys();
            hasCache = await caches.has(cacheName);
            if (hasCache) {
              const cache = await caches.open(cacheName);
              const match = await cache.match(entryUrl);
              if (match) {
                entryText = await match.text();
              }
            }
          }
          return {
            storageRaw: raw,
            storageJson: parsed,
            cacheNames: cacheNames,
            hasDianaCache: hasCache,
            dianaCacheEntryText: entryText
          };
        }""",
        {
            "dianaKey": diana_key,
            "cacheName": diana_cache_name,
            "entryUrl": diana_cache_url,
        },
    )


# ---------------------------------------------------------------------------
# CDP Touch Gesture Driver (Calibrated for Chromium ~33.3 ms Dispatch Cadence)
# ---------------------------------------------------------------------------


class CDPTouchDriver:
    """Chromium CDP touch emitter dispatching trusted ``PointerEvent`` gestures.

    Calibrated around Chromium headless ``Input.dispatchTouchEvent``'s ~33.3 ms
    ``performance.now()`` cadence per ``touchMove`` so tap, proportional lateral
    drag, slow soft-drop, fast downward flick (+ post-flick lock), upward swipe
    hold, and ``touchCancel`` work deterministically across sensitivities 1..10.
    """

    def __init__(self, page: Page) -> None:
        self.page: Page = page
        self.cdp: CDPSession = page.context.new_cdp_session(page)
        self._detached: bool = False

    def _send(self, event_type: str, points: list[dict[str, float | int]]) -> None:
        if self._detached:
            raise RuntimeError("CDPTouchDriver has already been detached.")
        self.cdp.send("Input.dispatchTouchEvent", {"type": event_type, "touchPoints": points})

    @staticmethod
    def _sleep_ms(ms: float) -> None:
        if ms > 0:
            time.sleep(ms / 1000.0)

    def tap(self, x: float, y: float, hold_ms: float = 10.0) -> None:
        """Dispatch a short trusted touch tap at viewport coordinates ``(x, y)``."""
        self._send("touchStart", [{"x": x, "y": y, "id": 0}])
        self._sleep_ms(hold_ms)
        self._send("touchEnd", [])

    def drag_horizontal(
        self,
        x: float,
        y: float,
        dx: float,
        steps: int = 4,
        step_sleep_ms: float = 0.0,
    ) -> None:
        """Dispatch a proportional horizontal drag of ``dx`` CSS px."""
        if steps < 1:
            raise ValueError("steps must be >= 1")
        self._send("touchStart", [{"x": x, "y": y, "id": 0}])
        for i in range(1, steps + 1):
            self._sleep_ms(step_sleep_ms)
            self._send("touchMove", [{"x": x + (dx * i / steps), "y": y, "id": 0}])
        self._send("touchEnd", [])

    def soft_drop_drag(
        self,
        x: float,
        y: float,
        total_dy: float = 70.0,
        steps: int = 10,
        step_sleep_ms: float = 10.0,
    ) -> None:
        """Dispatch a slow downward drag that emits soft-drop steps without triggering flick."""
        if steps < 1:
            raise ValueError("steps must be >= 1")
        self._send("touchStart", [{"x": x, "y": y, "id": 0}])
        for i in range(1, steps + 1):
            self._sleep_ms(step_sleep_ms)
            self._send("touchMove", [{"x": x, "y": y + (total_dy * i / steps), "id": 0}])
        self._send("touchEnd", [])

    def flick_down(
        self,
        x: float,
        y: float,
        dy: float = 95.0,
        hold_after_flick: bool = False,
    ) -> None:
        """Dispatch a fast 2-step downward flick inside 90 ms to trigger hard drop."""
        pre_dy = min(10.0, dy * 0.12)
        self._send("touchStart", [{"x": x, "y": y, "id": 0}])
        self._send("touchMove", [{"x": x, "y": y + pre_dy, "id": 0}])
        self._send("touchMove", [{"x": x, "y": y + dy, "id": 0}])
        if hold_after_flick:
            for i in range(1, 4):
                self._sleep_ms(15.0)
                self._send(
                    "touchMove",
                    [{"x": x + 25.0 * i, "y": y + dy + 25.0 * i, "id": 0}],
                )
        self._send("touchEnd", [])

    def swipe_up_hold(self, x: float, y: float, total_dy: float = -72.0) -> None:
        """Dispatch a fast 2-step upward swipe (< 140 ms) to trigger Hold."""
        self._send("touchStart", [{"x": x, "y": y, "id": 0}])
        self._send("touchMove", [{"x": x, "y": y + (total_dy * 0.5), "id": 0}])
        self._send("touchMove", [{"x": x, "y": y + total_dy, "id": 0}])
        self._send("touchEnd", [])

    def cancel_touch(self, x: float, y: float, dx: float = 4.0, dy: float = 4.0) -> None:
        """Start a touch, move slightly, and cancel via ``touchCancel``."""
        self._send("touchStart", [{"x": x, "y": y, "id": 0}])
        self._send("touchMove", [{"x": x + dx, "y": y + dy, "id": 0}])
        self._send("touchCancel", [])

    def get_stage_points(self, selector: str = "#board-stage") -> dict[str, tuple[float, float]]:
        """Compute safe interior coordinates inside ``selector`` across desktop & small mobile viewports."""
        box = self.page.locator(selector).bounding_box()
        if not box or box["width"] <= 0 or box["height"] <= 0:
            raise AssertionError(f"Element {selector!r} has no visible bounding box: {box!r}")

        left = float(box["x"])
        top = float(box["y"])
        width = float(box["width"])
        height = float(box["height"])
        vp = self.page.viewport_size
        if vp:
            right = min(left + width, float(vp["width"]))
            bottom = min(top + height, float(vp["height"]))
            left = max(0.0, left)
            top = max(0.0, top)
            width = max(1.0, right - left)
            height = max(1.0, bottom - top)

        cx = left + width * 0.5
        cy = top + height * 0.5
        down_y = top + min(height * 0.25, max(20.0, height - 180.0))
        up_y = top + max(height * 0.72, min(height - 20.0, 96.0))
        return {
            "center": (cx, cy),
            "tap": (cx, cy),
            "drag_left": (left + width * 0.75, cy),
            "drag_right": (left + width * 0.25, cy),
            "down_start": (cx, down_y),
            "up_start": (cx, up_y),
        }

    def tap_element(self, selector: str = "#board-stage", hold_ms: float = 10.0) -> None:
        pts = self.get_stage_points(selector)
        self.tap(*pts["tap"], hold_ms=hold_ms)

    def drag_horizontal_on(
        self,
        selector: str = "#board-stage",
        *,
        dx: float = 90.0,
        steps: int = 4,
        step_sleep_ms: float = 0.0,
    ) -> None:
        pts = self.get_stage_points(selector)
        start = pts["drag_right"] if dx >= 0 else pts["drag_left"]
        self.drag_horizontal(*start, dx=dx, steps=steps, step_sleep_ms=step_sleep_ms)

    def soft_drop_on(
        self,
        selector: str = "#board-stage",
        *,
        total_dy: float = 70.0,
        steps: int = 10,
        step_sleep_ms: float = 10.0,
    ) -> None:
        pts = self.get_stage_points(selector)
        self.soft_drop_drag(*pts["down_start"], total_dy=total_dy, steps=steps, step_sleep_ms=step_sleep_ms)

    def flick_down_on(
        self,
        selector: str = "#board-stage",
        *,
        dy: float = 95.0,
        hold_after_flick: bool = False,
    ) -> None:
        pts = self.get_stage_points(selector)
        self.flick_down(*pts["down_start"], dy=dy, hold_after_flick=hold_after_flick)

    def swipe_up_hold_on(self, selector: str = "#board-stage", *, total_dy: float = -72.0) -> None:
        pts = self.get_stage_points(selector)
        self.swipe_up_hold(*pts["up_start"], total_dy=total_dy)

    def cancel_touch_on(
        self,
        selector: str = "#board-stage",
        *,
        dx: float = 4.0,
        dy: float = 4.0,
    ) -> None:
        pts = self.get_stage_points(selector)
        self.cancel_touch(*pts["center"], dx=dx, dy=dy)

    def detach(self) -> None:
        """Detach the underlying CDP session safely."""
        if not self._detached:
            self._detached = True
            try:
                self.cdp.detach()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Visual / Canvas / Layout / Visibility / Gameplay Helpers
# ---------------------------------------------------------------------------


def capture_element_image(page: Page, selector: str) -> Image.Image:
    """Capture a screenshot of ``selector`` as a Pillow RGB ``Image``."""
    png_bytes = page.locator(selector).screenshot()
    return Image.open(io.BytesIO(png_bytes)).convert("RGB")


def count_diff_pixels(img1: Image.Image, img2: Image.Image, channel_threshold: int = 8) -> int:
    """Count pixels whose max RGB channel difference exceeds ``channel_threshold``."""
    if img1.size != img2.size:
        raise ValueError(f"Image sizes differ: {img1.size} vs {img2.size}")
    diff = ImageChops.difference(img1, img2)
    r, g, b = diff.split()
    max_ch = ImageChops.lighter(r, ImageChops.lighter(g, b))
    hist = max_ch.histogram()
    return sum(hist[channel_threshold + 1 :])


def images_differ(
    img1: Image.Image,
    img2: Image.Image,
    channel_threshold: int = 8,
    min_diff_pixels: int = 1,
) -> bool:
    """Return ``True`` if two images differ in size or have >= ``min_diff_pixels`` changed."""
    if img1.size != img2.size:
        return True
    return count_diff_pixels(img1, img2, channel_threshold=channel_threshold) >= min_diff_pixels


def _crop_content_box(page: Page, selector: str, img: Image.Image) -> Image.Image:
    box = page.locator(selector).evaluate(
        """(el) => {
          const cs = getComputedStyle(el);
          const r = el.getBoundingClientRect();
          return {
            w: r.width, h: r.height,
            bl: parseFloat(cs.borderLeftWidth) || 0, br: parseFloat(cs.borderRightWidth) || 0,
            bt: parseFloat(cs.borderTopWidth) || 0, bb: parseFloat(cs.borderBottomWidth) || 0,
            pl: parseFloat(cs.paddingLeft) || 0, pr: parseFloat(cs.paddingRight) || 0,
            pt: parseFloat(cs.paddingTop) || 0, pb: parseFloat(cs.paddingBottom) || 0
          };
        }"""
    )
    if box["w"] <= 0 or box["h"] <= 0:
        return img
    sx = img.width / box["w"]
    sy = img.height / box["h"]
    left = round((box["bl"] + box["pl"]) * sx)
    top = round((box["bt"] + box["pt"]) * sy)
    right = round(img.width - (box["br"] + box["pr"]) * sx)
    bottom = round(img.height - (box["bb"] + box["pb"]) * sy)
    if right > left and bottom > top and (left > 0 or top > 0 or right < img.width or bottom < img.height):
        return img.crop((left, top, right, bottom))
    return img


def _classify_piece_color(rgb: tuple[int, int, int]) -> str:
    r, g, b = rgb
    return min(
        PIECE_PALETTE.keys(),
        key=lambda k: (r - PIECE_PALETTE[k][0]) ** 2
        + (g - PIECE_PALETTE[k][1]) ** 2
        + (b - PIECE_PALETTE[k][2]) ** 2,
    )


def sample_board_grid_state(
    page: Page,
    selector: str = "#board-canvas",
    cols: int = 10,
    rows: int = 20,
) -> dict[str, Any]:
    """Sample a ``rows x cols`` grid purely from rendered ``#board-canvas`` pixels.

    Uses a 5x5 inner-cell median patch to ignore grid lines, block bevels, and
    translucent ghost strokes, paired with adaptive dark-background estimation.
    """
    raw_img = capture_element_image(page, selector)
    img = _crop_content_box(page, selector, raw_img)
    w, h = img.size
    cell_w = w / cols
    cell_h = h / rows
    offsets = (0.32, 0.41, 0.50, 0.59, 0.68)

    cell_rgbs: list[list[tuple[int, int, int]]] = []
    all_samples: list[tuple[int, tuple[int, int, int]]] = []
    for row in range(rows):
        row_rgbs: list[tuple[int, int, int]] = []
        for col in range(cols):
            rs: list[int] = []
            gs: list[int] = []
            bs: list[int] = []
            for oy in offsets:
                py = min(h - 1, max(0, int((row + oy) * cell_h)))
                for ox in offsets:
                    px = min(w - 1, max(0, int((col + ox) * cell_w)))
                    r, g, b = img.getpixel((px, py))
                    rs.append(r)
                    gs.append(g)
                    bs.append(b)
            rs.sort()
            gs.sort()
            bs.sort()
            med = (rs[12], gs[12], bs[12])
            row_rgbs.append(med)
            all_samples.append((max(med), med))
        cell_rgbs.append(row_rgbs)

    all_samples.sort(key=lambda x: x[0])
    bg_slice = all_samples[: max(1, int(len(all_samples) * 0.4))]
    bg_rgb = tuple(sorted(x[1][i] for x in bg_slice)[len(bg_slice) // 2] for i in range(3))

    grid: list[list[dict[str, Any] | None]] = []
    for row in range(rows):
        row_state: list[dict[str, Any] | None] = []
        for col in range(cols):
            r, g, b = cell_rgbs[row][col]
            max_ch = max(r, g, b)
            lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
            dist_bg = math.sqrt((r - bg_rgb[0]) ** 2 + (g - bg_rgb[1]) ** 2 + (b - bg_rgb[2]) ** 2)
            if max_ch >= 115 and lum >= 85 and dist_bg >= 90:
                row_state.append(
                    {
                        "occupied": True,
                        "rgb": [r, g, b],
                        "piece": _classify_piece_color((r, g, b)),
                    }
                )
            else:
                row_state.append(None)
        grid.append(row_state)

    return {
        "raw_size": [raw_img.width, raw_img.height],
        "cropped_size": [w, h],
        "bg_rgb": list(bg_rgb),
        "grid": grid,
    }


def detect_top_spawn_piece(
    page: Page,
    selector: str = "#board-canvas",
    top_rows: int = 3,
) -> dict[str, Any] | None:
    """Detect the currently spawning piece type and cells from top board rows."""
    sampled = sample_board_grid_state(page, selector=selector)
    cells: list[list[int]] = []
    votes: dict[str, int] = {}
    for r in range(min(top_rows, len(sampled["grid"]))):
        for c, cell in enumerate(sampled["grid"][r]):
            if cell is not None:
                cells.append([r, c])
                piece = cell["piece"]
                votes[piece] = votes.get(piece, 0) + 1
    if not cells:
        return None
    best_piece = max(votes.items(), key=lambda kv: kv[1])[0]
    return {"piece": best_piece, "cells": cells}


_IS_VISIBLE_JS = """(el, opts) => {
  if (!el) return { visible: false, reason: 'missing' };
  const requireInteractive = opts && opts.requireInteractive;
  const rect = el.getBoundingClientRect();
  if (rect.width <= 0 || rect.height <= 0) {
    return { visible: false, reason: 'zero_bbox' };
  }
  const selfCs = getComputedStyle(el);
  if (selfCs.visibility === 'hidden' || selfCs.visibility === 'collapse') {
    return { visible: false, reason: 'visibility_' + selfCs.visibility };
  }
  let cur = el;
  let effectiveOpacity = 1;
  while (cur && cur.nodeType === 1) {
    const cs = getComputedStyle(cur);
    if (cs.display === 'none') {
      return { visible: false, reason: 'display_none' };
    }
    const op = parseFloat(cs.opacity);
    if (!Number.isNaN(op)) {
      effectiveOpacity *= op;
      if (op <= 0.01 || effectiveOpacity <= 0.01) {
        return { visible: false, reason: 'opacity_0' };
      }
    }
    cur = cur.parentElement;
  }
  if (requireInteractive && selfCs.pointerEvents === 'none') {
    return { visible: false, reason: 'pointer_events_none' };
  }
  if (selfCs.clipPath && /inset\\(\\s*50%/.test(selfCs.clipPath)) {
    return { visible: false, reason: 'clip_path_collapsed' };
  }
  if (rect.right <= 0 || (document.documentElement.scrollWidth <= window.innerWidth && rect.left >= window.innerWidth)) {
    return { visible: false, reason: 'offscreen_x' };
  }
  if (
    rect.bottom <= 0 ||
    (document.documentElement.scrollHeight <= window.innerHeight && rect.top >= window.innerHeight && !el.closest('[style*="overflow"]')) ||
    rect.top >= window.innerHeight * 2
  ) {
    return { visible: false, reason: 'offscreen_y' };
  }
  return { visible: true, reason: 'ok', pointerEvents: selfCs.pointerEvents };
}"""


def is_element_visible(page: Page, selector: str, require_interactive: bool = False) -> bool:
    """Return ``True`` iff ``selector`` is genuinely visible (opaque-box computed check).

    Unlike Playwright's built-in ``locator.is_visible()``, this traverses ancestors
    for ``opacity: 0`` and ``display: none``, rejects ``clip-path: inset(50%...)``
    and offscreen hiding, checks inherited ``visibility``, and supports
    ``require_interactive=True`` (checking ``pointer-events !== 'none'``).
    """
    loc = page.locator(selector)
    if loc.count() == 0:
        return False
    res = loc.first.evaluate(_IS_VISIBLE_JS, {"requireInteractive": require_interactive})
    return bool(res["visible"])


def get_layout_metrics(
    page: Page,
    canvas_selector: str = "#board-canvas",
    stage_selector: str = ".board-stage",
) -> dict[str, Any]:
    """Return viewport, overflow, stage ratio, HiDPI canvas sizing, and gesture-lock CSS metrics."""
    return page.evaluate(
        """({ canvasSelector, stageSelector }) => {
          const doc = document.documentElement;
          const body = document.body;
          const stage = document.querySelector(stageSelector);
          const canvas = document.querySelector(canvasSelector);
          const docCs = getComputedStyle(doc);
          const bodyCs = body ? getComputedStyle(body) : null;
          const stageCs = stage ? getComputedStyle(stage) : null;
          const canvasCs = canvas ? getComputedStyle(canvas) : null;
          const stageRect = stage ? stage.getBoundingClientRect() : null;
          const canvasRect = canvas ? canvas.getBoundingClientRect() : null;
          const dpr = window.devicePixelRatio || 1;
          const cappedDpr = Math.min(dpr, 2);
          const computedCssW = canvasCs ? parseFloat(canvasCs.width) || 0 : 0;
          const computedCssH = canvasCs ? parseFloat(canvasCs.height) || 0 : 0;
          return {
            innerWidth: window.innerWidth,
            innerHeight: window.innerHeight,
            scrollWidth: doc.scrollWidth,
            scrollHeight: doc.scrollHeight,
            noHorizontalOverflow: doc.scrollWidth <= window.innerWidth,
            noVerticalOverflow: doc.scrollHeight <= window.innerHeight,
            dpr: dpr,
            cappedDpr: cappedDpr,
            stageHeight: stageRect ? stageRect.height : 0,
            stageWidth: stageRect ? stageRect.width : 0,
            stageHeightRatio: (stageRect && window.innerHeight > 0) ? (stageRect.height / window.innerHeight) : 0,
            canvasCssW: computedCssW,
            canvasCssH: computedCssH,
            canvasClientW: canvas ? canvas.clientWidth : 0,
            canvasClientH: canvas ? canvas.clientHeight : 0,
            canvasRectW: canvasRect ? canvasRect.width : 0,
            canvasRectH: canvasRect ? canvasRect.height : 0,
            canvasBufferW: canvas ? canvas.width : 0,
            canvasBufferH: canvas ? canvas.height : 0,
            hidpiBufferExact: canvas
              ? (canvas.width === Math.round(computedCssW * cappedDpr) &&
                 canvas.height === Math.round(computedCssH * cappedDpr))
              : false,
            touchAction: {
              stage: stageCs ? stageCs.touchAction : null,
              canvas: canvasCs ? canvasCs.touchAction : null
            },
            userSelect: {
              body: bodyCs ? (bodyCs.userSelect || bodyCs.webkitUserSelect || null) : null,
              stage: stageCs ? (stageCs.userSelect || stageCs.webkitUserSelect || null) : null
            },
            overscrollBehavior: {
              html: { x: docCs.overscrollBehaviorX, y: docCs.overscrollBehaviorY },
              body: bodyCs ? { x: bodyCs.overscrollBehaviorX, y: bodyCs.overscrollBehaviorY } : null,
              stage: stageCs ? { x: stageCs.overscrollBehaviorX, y: stageCs.overscrollBehaviorY } : null
            }
          };
        }""",
        {"canvasSelector": canvas_selector, "stageSelector": stage_selector},
    )


def _parse_int_text(raw: str, label: str) -> int:
    cleaned = re.sub(r"[\s.,\u00a0]", "", raw.strip())
    if not cleaned or not re.fullmatch(r"-?\d+", cleaned):
        raise ValueError(f"Expected integer text for {label}, got {raw!r}")
    return int(cleaned)


def start_game(page: Page, level: int = 1, timeout_ms: int = 3000) -> None:
    """Start a game via the Start overlay UI at ``level`` (1..15)."""
    if not (1 <= level <= 15):
        raise ValueError(f"Start level must be between 1 and 15, got {level}")
    if not is_element_visible(page, SELECTORS["overlay_start"]):
        raise AssertionError("Start overlay (#overlay-start) is not visible before start_game().")

    for _ in range(20):
        cur_level = _parse_int_text(
            page.locator(SELECTORS["start_level_value"]).inner_text(),
            SELECTORS["start_level_value"],
        )
        if cur_level == level:
            break
        btn_sel = SELECTORS["btn_level_up"] if cur_level < level else SELECTORS["btn_level_down"]
        page.locator(btn_sel).click()
    else:
        final_level = page.locator(SELECTORS["start_level_value"]).inner_text()
        raise AssertionError(f"Failed to set start level to {level}; current text={final_level!r}")

    page.locator(SELECTORS["btn_play"]).click()
    page.wait_for_function(
        f"""({{ sel }}) => {{
          const el = document.querySelector(sel);
          if (!el) return true;
          return !({ _IS_VISIBLE_JS })(el, {{ requireInteractive: false }}).visible;
        }}""",
        arg={"sel": SELECTORS["overlay_start"]},
        timeout=timeout_ms,
    )
    # Give requestAnimationFrame at least one render tick after overlay closes.
    page.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")


def get_hud_stats(page: Page) -> dict[str, int]:
    """Read and parse live and best HUD counters from contracted DOM elements."""
    keys = (
        ("score", "score_value"),
        ("level", "level_value"),
        ("lines", "lines_value"),
        ("best_score", "best_score_value"),
        ("best_level", "best_level_value"),
        ("best_lines", "best_lines_value"),
    )
    stats: dict[str, int] = {}
    for out_key, sel_key in keys:
        sel = SELECTORS[sel_key]
        raw = page.locator(sel).inner_text()
        stats[out_key] = _parse_int_text(raw, sel)
    return stats


def get_raw_storage_item(page: Page, key: str = STORAGE_KEY) -> str | None:
    """Return raw ``window.localStorage.getItem(key)`` value (or ``None``)."""
    return page.evaluate("(k) => window.localStorage.getItem(k)", key)


def get_storage_data(page: Page, key: str = STORAGE_KEY) -> dict[str, Any] | None:
    """Return parsed JSON object stored at ``window.localStorage[key]`` (or ``None``)."""
    raw = get_raw_storage_item(page, key=key)
    if raw is None:
        return None
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in localStorage[{key!r}], got {type(data).__name__}")
    return data


def set_range_value(page: Page, selector: str, val: int | float) -> None:
    """Set ``<input type='range'>`` value and dispatch both ``input`` and ``change`` events."""
    page.locator(selector).fill(str(val))


# ---------------------------------------------------------------------------
# Diagnostics & Shared Base TestCase
# ---------------------------------------------------------------------------


def _is_external_url(url: str) -> bool:
    parsed = urlsplit(url)
    scheme = parsed.scheme.lower()
    if scheme not in _LOCAL_SCHEMES:
        return True
    if scheme in ("http", "https"):
        host = (parsed.hostname or "").lower()
        return host not in _LOCAL_HOSTS
    return False


@dataclass
class PageDiagnostics:
    """Per-page runtime diagnostics collected from Playwright page events."""

    console_errors: list[str] = field(default_factory=list)
    console_warnings: list[str] = field(default_factory=list)
    page_errors: list[str] = field(default_factory=list)
    request_failures: list[dict[str, str]] = field(default_factory=list)
    http_error_responses: list[dict[str, Any]] = field(default_factory=list)
    external_requests: list[dict[str, str]] = field(default_factory=list)
    all_requests: list[dict[str, str]] = field(default_factory=list)

    def clear(self) -> None:
        self.console_errors.clear()
        self.console_warnings.clear()
        self.page_errors.clear()
        self.request_failures.clear()
        self.http_error_responses.clear()
        self.external_requests.clear()
        self.all_requests.clear()

    def attach(self, page: Page) -> "PageDiagnostics":
        def _on_console(msg: Any) -> None:
            if msg.type == "error":
                self.console_errors.append(msg.text)
            elif msg.type == "warning":
                self.console_warnings.append(msg.text)

        def _on_pageerror(err: Any) -> None:
            self.page_errors.append(str(err))

        def _on_request(req: Any) -> None:
            entry = {
                "url": req.url,
                "method": req.method,
                "resource_type": req.resource_type,
            }
            self.all_requests.append(entry)
            if _is_external_url(req.url):
                self.external_requests.append(entry)

        def _on_requestfailed(req: Any) -> None:
            self.request_failures.append(
                {
                    "url": req.url,
                    "method": req.method,
                    "resource_type": req.resource_type,
                    "failure": req.failure or "unknown",
                }
            )

        def _on_response(resp: Any) -> None:
            if resp.status >= 400:
                self.http_error_responses.append(
                    {
                        "url": resp.url,
                        "status": resp.status,
                        "status_text": resp.status_text,
                    }
                )

        page.on("console", _on_console)
        page.on("pageerror", _on_pageerror)
        page.on("request", _on_request)
        page.on("requestfailed", _on_requestfailed)
        page.on("response", _on_response)
        return self

    def summary(self) -> str:
        return json.dumps(
            {
                "console_errors": self.console_errors,
                "page_errors": self.page_errors,
                "request_failures": self.request_failures,
                "http_error_responses": self.http_error_responses,
                "external_requests": self.external_requests,
            },
            indent=2,
        )


class TetrisE2EBaseCase(unittest.TestCase):
    """Shared class-scoped Playwright + StaticAppServer fixture with per-test context isolation.

    - Starts Playwright Chromium and optional ``StaticAppServer`` once per test class
      (with exception-safe partial rollback if ``setUpClass`` fails).
    - Every ``open_page()`` call creates a fresh ``browser.new_context(...)`` registered
      with ``addCleanup`` so ``localStorage``, ``CacheStorage``, and Service Workers
      never leak between tests.
    """

    APP_ROOT: Path = PROJECT_ROOT
    SERVER_BASE_PREFIX: str = "/"
    START_SERVER: bool = True
    CACHE_CONTROL: str | None = "no-store"
    HEADLESS: bool = True

    _playwright: Playwright | None = None
    _browser: Browser | None = None
    _server: StaticAppServer | None = None

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls._playwright = None
        cls._browser = None
        cls._server = None
        try:
            cls._playwright = sync_playwright().start()
            cls._browser = cls._playwright.chromium.launch(headless=cls.HEADLESS)
            if cls.START_SERVER:
                cls._server = StaticAppServer(
                    cls.APP_ROOT,
                    base_prefix=cls.SERVER_BASE_PREFIX,
                    cache_control=cls.CACHE_CONTROL,
                ).start()
        except Exception:
            cls._cleanup_class_resources()
            raise

    @classmethod
    def tearDownClass(cls) -> None:
        try:
            cls._cleanup_class_resources()
        finally:
            super().tearDownClass()

    @classmethod
    def _cleanup_class_resources(cls) -> None:
        server = cls._server
        browser = cls._browser
        playwright = cls._playwright
        cls._server = None
        cls._browser = None
        cls._playwright = None
        if server is not None:
            try:
                server.stop()
            except Exception:
                pass
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass
        if playwright is not None:
            try:
                playwright.stop()
            except Exception:
                pass

    @property
    def server(self) -> StaticAppServer:
        if self.__class__._server is None:
            raise RuntimeError("Class StaticAppServer was not started (START_SERVER is False).")
        return self.__class__._server

    @property
    def browser(self) -> Browser:
        if self.__class__._browser is None:
            raise RuntimeError("Class Playwright Browser is not initialized.")
        return self.__class__._browser

    def setUp(self) -> None:
        super().setUp()
        self._page_diagnostics: list[tuple[Page, PageDiagnostics]] = []
        self.last_diagnostics: PageDiagnostics | None = None

    @staticmethod
    def _safe_close_context(context: BrowserContext) -> None:
        try:
            context.close()
        except Exception:
            pass

    def start_server(
        self,
        root_dir: str | Path | None = None,
        *,
        base_prefix: str = "/",
        cache_control: str | None = "no-store",
    ) -> StaticAppServer:
        """Start an isolated ``StaticAppServer`` for the current test and stop via ``addCleanup``."""
        srv = StaticAppServer(
            self.APP_ROOT if root_dir is None else root_dir,
            base_prefix=base_prefix,
            cache_control=cache_control,
        ).start()
        self.addCleanup(srv.stop)
        return srv

    def attach_diagnostics(self, page: Page) -> PageDiagnostics:
        """Attach runtime error/request collectors to ``page`` and register it on ``self``."""
        diag = PageDiagnostics().attach(page)
        self._page_diagnostics.append((page, diag))
        self.last_diagnostics = diag
        return diag

    def diagnostics_for(self, page: Page) -> PageDiagnostics:
        """Return the ``PageDiagnostics`` instance bound to ``page``."""
        for tracked_page, diag in self._page_diagnostics:
            if tracked_page is page:
                return diag
        raise KeyError("No diagnostics registered for the given Page.")

    def new_context(
        self,
        *,
        viewport: tuple[int, int] = DESKTOP_VIEWPORT,
        has_touch: bool = False,
        is_mobile: bool = False,
        device_scale_factor: float = 1.0,
        offline: bool = False,
        ignore_https_errors: bool = False,
        init_scripts: Sequence[str] | None = None,
        gamepad: bool = False,
        rng_seed: int | None = None,
        local_storage_fault: str | tuple[str, str] | None = None,
        corrupt_storage: str | None = None,
        storage_seed: dict[str, Any] | str | None = None,
        storage_seed_key: str = STORAGE_KEY,
        storage_seed_once: bool = True,
    ) -> BrowserContext:
        """Create an isolated ``BrowserContext`` with optional init-script mocks & cleanup."""
        context = self.browser.new_context(
            viewport={"width": viewport[0], "height": viewport[1]},
            has_touch=has_touch,
            is_mobile=is_mobile,
            device_scale_factor=device_scale_factor,
            offline=offline,
            ignore_https_errors=ignore_https_errors,
        )
        self.addCleanup(self._safe_close_context, context)

        scripts: list[str] = []
        if rng_seed is not None:
            scripts.append(make_lcg_init_script(rng_seed))
        if gamepad:
            scripts.append(make_gamepad_init_script())
        if corrupt_storage is not None:
            scripts.append(
                make_local_storage_seed_script(
                    storage_seed_key,
                    corrupt_storage,
                    seed_once=storage_seed_once,
                )
            )
        if storage_seed is not None:
            raw_seed = storage_seed if isinstance(storage_seed, str) else json.dumps(storage_seed)
            scripts.append(
                make_local_storage_seed_script(
                    storage_seed_key,
                    raw_seed,
                    seed_once=storage_seed_once,
                )
            )
        if local_storage_fault is not None:
            if isinstance(local_storage_fault, tuple):
                fault_mode, fault_name = local_storage_fault
            else:
                fault_mode = local_storage_fault
                fault_name = "QuotaExceededError" if fault_mode == "set_only" else "SecurityError"
            scripts.append(make_local_storage_fault_script(mode=fault_mode, error_name=fault_name))
        if init_scripts:
            scripts.extend(init_scripts)

        for script in scripts:
            context.add_init_script(script)

        return context

    def open_page(
        self,
        url: str | None = None,
        *,
        viewport: tuple[int, int] = DESKTOP_VIEWPORT,
        has_touch: bool = False,
        is_mobile: bool = False,
        device_scale_factor: float = 1.0,
        offline: bool = False,
        ignore_https_errors: bool = False,
        init_scripts: Sequence[str] | None = None,
        gamepad: bool = False,
        rng_seed: int | None = None,
        local_storage_fault: str | tuple[str, str] | None = None,
        corrupt_storage: str | None = None,
        storage_seed: dict[str, Any] | str | None = None,
        storage_seed_key: str = STORAGE_KEY,
        storage_seed_once: bool = True,
        wait_until: str = "load",
    ) -> Page:
        """Open a fresh isolated context & page navigated to ``url`` (defaults to ``server.base_url``)."""
        target_url = self.server.base_url if url is None else url
        context = self.new_context(
            viewport=viewport,
            has_touch=has_touch,
            is_mobile=is_mobile,
            device_scale_factor=device_scale_factor,
            offline=offline,
            ignore_https_errors=ignore_https_errors,
            init_scripts=init_scripts,
            gamepad=gamepad,
            rng_seed=rng_seed,
            local_storage_fault=local_storage_fault,
            corrupt_storage=corrupt_storage,
            storage_seed=storage_seed,
            storage_seed_key=storage_seed_key,
            storage_seed_once=storage_seed_once,
        )
        page = context.new_page()
        self.attach_diagnostics(page)
        page.goto(target_url, wait_until=wait_until)
        return page

    def open_desktop_page(
        self,
        url: str | None = None,
        *,
        viewport: tuple[int, int] = DESKTOP_VIEWPORT,
        device_scale_factor: float = 1.0,
        **kwargs: Any,
    ) -> Page:
        """Open a desktop-configured isolated page (default 1440x900, non-touch)."""
        return self.open_page(
            url,
            viewport=viewport,
            has_touch=False,
            is_mobile=False,
            device_scale_factor=device_scale_factor,
            **kwargs,
        )

    def open_mobile_page(
        self,
        url: str | None = None,
        *,
        viewport: tuple[int, int] = MOBILE_VIEWPORT,
        device_scale_factor: float = 2.0,
        **kwargs: Any,
    ) -> Page:
        """Open a mobile-configured isolated page (default 390x844, touch, dpr=2)."""
        return self.open_page(
            url,
            viewport=viewport,
            has_touch=True,
            is_mobile=True,
            device_scale_factor=device_scale_factor,
            **kwargs,
        )

    def touch_driver(self, page: Page) -> CDPTouchDriver:
        """Create a ``CDPTouchDriver`` for ``page`` and register cleanup via ``addCleanup``."""
        driver = CDPTouchDriver(page)
        self.addCleanup(driver.detach)
        return driver

    def assertPageClean(
        self,
        page: Page,
        *,
        allow_request_failures: bool = False,
        allow_external_requests: bool = False,
        allow_http_errors: bool = False,
    ) -> None:
        """Assert zero console errors, uncaught page errors, failed requests, and external requests."""
        diag = self.diagnostics_for(page)
        self.assertEqual(diag.console_errors, [], f"Console errors observed:\n{diag.summary()}")
        self.assertEqual(diag.page_errors, [], f"Uncaught page errors observed:\n{diag.summary()}")
        if not allow_request_failures:
            self.assertEqual(diag.request_failures, [], f"Failed requests observed:\n{diag.summary()}")
        if not allow_external_requests:
            self.assertEqual(diag.external_requests, [], f"External requests observed:\n{diag.summary()}")
        if not allow_http_errors:
            self.assertEqual(diag.http_error_responses, [], f"HTTP >=400 responses observed:\n{diag.summary()}")

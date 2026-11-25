"""Area A E2E tests: Dual runtime (file:// & HTTP/subpath), PWA offline, and storage resilience.

Covers PROJECT.md features F1.1, F1.2, F1.3, and F2.8 via strictly opaque-box
Playwright checks against contracted DOM selectors, HTTP responses, Service Worker
lifecycle, and localStorage/CacheStorage isolation.
"""

from __future__ import annotations

import http.client
import json
import re
import unittest
from urllib.parse import urljoin, urlsplit

from tests.e2e.harness import (
    CACHE_NAME,
    DIANA_CACHE_NAME,
    DIANA_STORAGE_KEY,
    SELECTORS,
    TetrisE2EBaseCase,
    capture_element_image,
    file_uri,
    get_hud_stats,
    get_storage_data,
    images_differ,
    is_element_visible,
    read_diana_sudoku_sibling,
    seed_diana_sudoku_sibling,
    set_range_value,
    start_game,
    wait_for_service_worker_controlled,
)

_LOCAL_NETWORK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
_ALLOWED_LOCAL_SCHEMES = frozenset({"file", "http", "https", "data", "blob", "about"})


def _wait_raf(page, frames: int = 2) -> None:
    page.evaluate(
        """(count) => new Promise((resolve) => {
          let left = count;
          function step() {
            left -= 1;
            if (left <= 0) {
              resolve();
            } else {
              requestAnimationFrame(step);
            }
          }
          requestAnimationFrame(step);
        })""",
        frames,
    )


def _wait_until_hidden(page, selector: str, timeout_ms: int = 3000) -> None:
    deadline_steps = max(1, timeout_ms // 25)
    for _ in range(deadline_steps):
        if not is_element_visible(page, selector):
            return
        page.wait_for_timeout(25)
    raise AssertionError(f"Element {selector!r} remained visible after {timeout_ms} ms")


def _parse_first_int(raw: str, label: str) -> int:
    match = re.search(r"-?\d+", raw or "")
    if not match:
        raise AssertionError(f"Expected integer in {label}, got {raw!r}")
    return int(match.group(0))


def _is_strictly_relative_url(value: str) -> bool:
    if not value or not value.strip():
        return False
    if value.startswith("/") or value.startswith("//") or value.startswith(".."):
        return False
    if "://" in value:
        return False
    return True


class TestAreaAFileProtocol(TetrisE2EBaseCase):
    """Area A tests running directly from file:// without an HTTP server."""

    START_SERVER = False

    def test_tier1_file_protocol_boot_and_play(self) -> None:
        index_path = self.APP_ROOT / "index.html"
        page = self.open_desktop_page(file_uri(index_path))
        _wait_raf(page, 2)
        self.assertPageClean(page)

        self.assertTrue(
            is_element_visible(page, SELECTORS["overlay_start"], require_interactive=True),
            "Start overlay should be visible on file:// boot.",
        )
        canvas_box = page.locator(SELECTORS["board_canvas"]).bounding_box()
        self.assertIsNotNone(canvas_box)
        self.assertGreater(canvas_box["width"], 0)
        self.assertGreater(canvas_box["height"], 0)

        start_game(page, level=1)
        self.assertFalse(is_element_visible(page, SELECTORS["overlay_start"]))

        board_before = capture_element_image(page, SELECTORS["board_canvas"])
        page.keyboard.press("Space")
        _wait_raf(page, 2)
        board_after = capture_element_image(page, SELECTORS["board_canvas"])

        stats = get_hud_stats(page)
        self.assertGreater(stats["score"], 0, "Hard Drop on file:// must increase score.")
        self.assertTrue(
            images_differ(board_before, board_after, channel_threshold=8, min_diff_pixels=15),
            "Hard Drop on file:// must update #board-canvas pixels.",
        )

        # Verify localStorage interaction succeeds cleanly under file:// origin.
        page.locator(SELECTORS["btn_music"]).click()
        _wait_raf(page, 1)
        stored = get_storage_data(page)
        self.assertIsInstance(stored, dict)
        self.assertIn("musicEnabled", stored)
        self.assertPageClean(page)

    def test_tier2_file_protocol_gate_no_manifest_or_sw_register(self) -> None:
        sw_spy_script = """
(function () {
  window.__e2eSwRegisterCalls = 0;
  try {
    if (typeof ServiceWorkerContainer !== 'undefined' && ServiceWorkerContainer.prototype) {
      var protoOrig = ServiceWorkerContainer.prototype.register;
      if (typeof protoOrig === 'function') {
        ServiceWorkerContainer.prototype.register = function () {
          window.__e2eSwRegisterCalls += 1;
          return protoOrig.apply(this, arguments);
        };
      }
    }
  } catch (_) {}
  try {
    if ('serviceWorker' in navigator && navigator.serviceWorker && typeof navigator.serviceWorker.register === 'function') {
      var instOrig = navigator.serviceWorker.register.bind(navigator.serviceWorker);
      navigator.serviceWorker.register = function () {
        window.__e2eSwRegisterCalls += 1;
        return instOrig.apply(navigator.serviceWorker, arguments);
      };
    }
  } catch (_) {}
})();
"""
        index_path = self.APP_ROOT / "index.html"
        page = self.open_desktop_page(file_uri(index_path), init_scripts=[sw_spy_script])
        _wait_raf(page, 2)

        manifest_count = page.locator('link[rel="manifest"]').count()
        self.assertEqual(
            manifest_count,
            0,
            "file:// must NOT inject <link rel='manifest'>.",
        )
        sw_calls = page.evaluate("() => window.__e2eSwRegisterCalls")
        self.assertEqual(
            sw_calls,
            0,
            "file:// must NOT call navigator.serviceWorker.register().",
        )
        self.assertPageClean(page)


class TestAreaARootHttpAndStorage(TetrisE2EBaseCase):
    """Area A tests running at HTTP root / for manifest, asset paths, zero external network, and storage."""

    SERVER_BASE_PREFIX = "/"

    def test_tier1_http_root_dynamic_manifest_and_relative_assets(self) -> None:
        page = self.open_desktop_page(self.server.base_url)
        _wait_raf(page, 2)
        self.assertPageClean(page)

        self.assertEqual(page.locator("html").get_attribute("lang"), "es")
        self.assertIn("Tetris Clásico", page.title())

        manifest_links = page.evaluate(
            """() => Array.from(document.head.querySelectorAll('link[rel="manifest"]')).map((el) => ({
              attrHref: el.getAttribute('href'),
              resolvedHref: el.href
            }))"""
        )
        self.assertEqual(
            len(manifest_links),
            1,
            f"Expected exactly 1 manifest link in <head>, found {manifest_links!r}",
        )

        attr_href = manifest_links[0]["attrHref"] or ""
        self.assertTrue(
            _is_strictly_relative_url(attr_href),
            f"Manifest href attribute must be strictly relative, got {attr_href!r}",
        )
        self.assertIn(attr_href, ("./manifest.webmanifest", "manifest.webmanifest"))

        abs_manifest_url = manifest_links[0]["resolvedHref"]
        manifest_resp = page.request.get(abs_manifest_url)
        self.assertEqual(manifest_resp.status, 200)
        self.assertIn("json", (manifest_resp.headers.get("content-type") or "").lower())

        manifest = json.loads(manifest_resp.text())
        self.assertEqual(manifest.get("name"), "Tetris Clásico")
        self.assertEqual(manifest.get("display"), "standalone")
        self.assertEqual(manifest.get("lang"), "es")
        self.assertTrue(
            _is_strictly_relative_url(manifest.get("start_url", "")),
            f"Manifest start_url must be relative: {manifest.get('start_url')!r}",
        )
        self.assertTrue(
            _is_strictly_relative_url(manifest.get("scope", "")),
            f"Manifest scope must be relative: {manifest.get('scope')!r}",
        )

        icons = manifest.get("icons")
        self.assertIsInstance(icons, list)
        self.assertGreaterEqual(len(icons), 1)
        for icon in icons:
            src = icon.get("src", "")
            self.assertTrue(
                _is_strictly_relative_url(src),
                f"Manifest icon src must be relative, got {src!r}",
            )
            icon_url = urljoin(abs_manifest_url, src)
            icon_resp = page.request.get(icon_url)
            self.assertEqual(icon_resp.status, 200, f"Icon fetch failed for {icon_url}")
            icon_ct = (icon_resp.headers.get("content-type") or "").lower()
            self.assertTrue(
                icon_ct.startswith("image/"),
                f"Expected image/* Content-Type for {icon_url}, got {icon_ct!r}",
            )
            self.assertGreater(len(icon_resp.body()), 0, f"Icon body empty for {icon_url}")

        dom_asset_attrs = page.evaluate(
            """() => {
              const out = [];
              for (const s of document.querySelectorAll('script[src]')) {
                out.push({ tag: 'script', attr: s.getAttribute('src') });
              }
              for (const l of document.querySelectorAll('link[href]')) {
                out.push({ tag: 'link:' + (l.getAttribute('rel') || ''), attr: l.getAttribute('href') });
              }
              return out;
            }"""
        )
        self.assertGreater(len(dom_asset_attrs), 0)
        for entry in dom_asset_attrs:
            attr_val = entry["attr"] or ""
            self.assertTrue(
                _is_strictly_relative_url(attr_val),
                f"DOM asset attribute {entry!r} must be strictly relative.",
            )
        self.assertPageClean(page)

    def test_tier1_zero_external_network_dependencies_file_and_http(self) -> None:
        file_page = self.open_desktop_page(file_uri(self.APP_ROOT / "index.html"))
        _wait_raf(file_page, 2)
        file_diag = self.diagnostics_for(file_page)
        self.assertEqual(file_diag.external_requests, [])
        self.assertGreaterEqual(len(file_diag.all_requests), 1)
        for req in file_diag.all_requests:
            scheme = urlsplit(req["url"]).scheme.lower()
            self.assertIn(
                scheme,
                {"file", "data", "blob", "about"},
                f"Unexpected non-file scheme on file:// load: {req!r}",
            )
        self.assertPageClean(file_page)

        self.server.clear_requests()
        http_page = self.open_desktop_page(self.server.base_url)
        _wait_raf(http_page, 2)
        http_diag = self.diagnostics_for(http_page)
        self.assertEqual(http_diag.external_requests, [])
        self.assertGreaterEqual(len(http_diag.all_requests), 1)
        for req in http_diag.all_requests:
            parsed = urlsplit(req["url"])
            scheme = parsed.scheme.lower()
            self.assertIn(scheme, _ALLOWED_LOCAL_SCHEMES, f"Forbidden scheme: {req!r}")
            if scheme in ("http", "https"):
                self.assertIn(
                    (parsed.hostname or "").lower(),
                    _LOCAL_NETWORK_HOSTS,
                    f"External host detected: {req!r}",
                )

        srv_reqs = self.server.get_requests()
        self.assertGreaterEqual(len(srv_reqs), 1)
        for srv_req in srv_reqs:
            self.assertLess(srv_req["status"], 400, f"Unexpected HTTP error on local load: {srv_req!r}")
        self.assertPageClean(http_page)

    def test_tier2_corrupt_and_out_of_range_local_storage_recovery(self) -> None:
        cases = [
            ("malformed_json", "{bad-json"),
            ("wrong_root_type", "[1, 2, 3]"),
            (
                "out_of_range_and_bad_types",
                json.dumps(
                    {
                        "bestScore": -50,
                        "bestLevel": "bad",
                        "bestLines": -3,
                        "touchSensitivity": 99,
                        "startLevel": 99,
                        "musicEnabled": "yes",
                        "sfxEnabled": "invalid",
                    }
                ),
            ),
        ]

        for label, corrupt_payload in cases:
            with self.subTest(case=label):
                page = self.open_desktop_page(
                    self.server.base_url,
                    corrupt_storage=corrupt_payload,
                    storage_seed_once=True,
                )
                _wait_raf(page, 2)
                self.assertPageClean(page)

                self.assertTrue(is_element_visible(page, SELECTORS["overlay_start"], require_interactive=True))
                hud = get_hud_stats(page)
                self.assertGreaterEqual(hud["best_score"], 0)
                self.assertGreaterEqual(hud["best_level"], 0)
                self.assertGreaterEqual(hud["best_lines"], 0)

                start_lvl = _parse_first_int(
                    page.locator(SELECTORS["start_level_value"]).inner_text(),
                    SELECTORS["start_level_value"],
                )
                self.assertGreaterEqual(start_lvl, 1)
                self.assertLessEqual(start_lvl, 15)

                page.locator(SELECTORS["btn_start_settings"]).click()
                _wait_raf(page, 1)
                self.assertTrue(is_element_visible(page, SELECTORS["modal_settings"], require_interactive=True))
                sens_val = _parse_first_int(
                    page.locator(SELECTORS["sensitivity_value"]).inner_text(),
                    SELECTORS["sensitivity_value"],
                )
                self.assertGreaterEqual(sens_val, 1)
                self.assertLessEqual(sens_val, 10)
                slider_val = _parse_first_int(
                    page.locator(SELECTORS["sensitivity_slider"]).input_value(),
                    SELECTORS["sensitivity_slider"],
                )
                self.assertGreaterEqual(slider_val, 1)
                self.assertLessEqual(slider_val, 10)

                # Mutate settings & play so sanitized schema is persisted back to localStorage.
                set_range_value(page, SELECTORS["sensitivity_slider"], 7)
                page.locator(SELECTORS["toggle_music"]).click()
                page.locator(SELECTORS["btn_close_settings"]).click()
                _wait_raf(page, 1)

                start_game(page, level=1)
                page.keyboard.press("Space")
                _wait_raf(page, 2)

                recovered = get_storage_data(page)
                self.assertIsInstance(recovered, dict)
                self.assertIsInstance(recovered.get("bestScore"), int)
                self.assertGreaterEqual(recovered["bestScore"], 0)
                self.assertIsInstance(recovered.get("bestLevel"), int)
                self.assertGreaterEqual(recovered["bestLevel"], 0)
                self.assertIsInstance(recovered.get("bestLines"), int)
                self.assertGreaterEqual(recovered["bestLines"], 0)
                self.assertEqual(recovered.get("touchSensitivity"), 7)
                self.assertIsInstance(recovered.get("startLevel"), int)
                self.assertGreaterEqual(recovered["startLevel"], 1)
                self.assertLessEqual(recovered["startLevel"], 15)
                self.assertIsInstance(recovered.get("musicEnabled"), bool)
                self.assertIsInstance(recovered.get("sfxEnabled"), bool)

                page.reload(wait_until="load")
                _wait_raf(page, 2)
                self.assertPageClean(page)
                after_reload = get_storage_data(page)
                self.assertIsInstance(after_reload, dict)
                self.assertEqual(after_reload.get("touchSensitivity"), 7)
                page.locator(SELECTORS["btn_start_settings"]).click()
                _wait_raf(page, 1)
                self.assertEqual(
                    _parse_first_int(
                        page.locator(SELECTORS["sensitivity_value"]).inner_text(),
                        SELECTORS["sensitivity_value"],
                    ),
                    7,
                )

    def test_tier2_local_storage_fault_resilience(self) -> None:
        fault_modes = [
            ("set_only", "QuotaExceededError"),
            ("all_methods", "SecurityError"),
            ("getter", "SecurityError"),
        ]

        for mode, err_name in fault_modes:
            with self.subTest(mode=mode, error=err_name):
                page = self.open_desktop_page(
                    self.server.base_url,
                    local_storage_fault=(mode, err_name),
                )
                _wait_raf(page, 2)

                self.assertTrue(is_element_visible(page, SELECTORS["overlay_start"], require_interactive=True))
                page.locator(SELECTORS["btn_level_up"]).click()
                self.assertEqual(
                    _parse_first_int(
                        page.locator(SELECTORS["start_level_value"]).inner_text(),
                        SELECTORS["start_level_value"],
                    ),
                    2,
                )

                page.locator(SELECTORS["btn_start_settings"]).click()
                _wait_raf(page, 1)
                self.assertTrue(is_element_visible(page, SELECTORS["modal_settings"], require_interactive=True))
                set_range_value(page, SELECTORS["sensitivity_slider"], 8)
                self.assertEqual(
                    _parse_first_int(
                        page.locator(SELECTORS["sensitivity_value"]).inner_text(),
                        SELECTORS["sensitivity_value"],
                    ),
                    8,
                )
                page.locator(SELECTORS["toggle_music"]).click()
                page.locator(SELECTORS["toggle_sfx"]).click()
                page.locator(SELECTORS["btn_close_settings"]).click()
                _wait_raf(page, 1)

                start_game(page, level=2)
                page.keyboard.press("Space")
                _wait_raf(page, 2)
                hud1 = get_hud_stats(page)
                self.assertGreater(hud1["score"], 0)
                self.assertEqual(hud1["level"], 2)

                page.locator(SELECTORS["btn_pause"]).click()
                _wait_raf(page, 1)
                self.assertTrue(is_element_visible(page, SELECTORS["overlay_pause"], require_interactive=True))

                page.locator(SELECTORS["btn_pause_settings"]).click()
                _wait_raf(page, 1)
                self.assertTrue(is_element_visible(page, SELECTORS["modal_settings"], require_interactive=True))
                self.assertEqual(
                    _parse_first_int(
                        page.locator(SELECTORS["sensitivity_value"]).inner_text(),
                        SELECTORS["sensitivity_value"],
                    ),
                    8,
                    "In-memory sensitivity fallback must retain value 8 across pause/settings.",
                )
                page.locator(SELECTORS["btn_close_settings"]).click()
                _wait_raf(page, 1)

                if is_element_visible(page, SELECTORS["overlay_pause"]):
                    page.locator(SELECTORS["btn_resume"]).click()
                    _wait_raf(page, 1)
                self.assertFalse(is_element_visible(page, SELECTORS["overlay_pause"]))

                page.keyboard.press("Space")
                _wait_raf(page, 2)
                hud2 = get_hud_stats(page)
                self.assertGreater(hud2["score"], hud1["score"])
                self.assertPageClean(page)


class TestAreaASubpathPwaOffline(TetrisE2EBaseCase):
    """Area A tests running under GitHub Pages subpath /tetris-clasico/ with Service Worker offline checks."""

    SERVER_BASE_PREFIX = "/tetris-clasico/"

    def test_tier1_github_pages_subpath_assets_and_bare_prefix_301(self) -> None:
        # 1. Verify raw 301 redirect behavior on bare subpath (with and without query string).
        for req_path, expected_loc in (
            ("/tetris-clasico", "/tetris-clasico/"),
            ("/tetris-clasico?v=1", "/tetris-clasico/?v=1"),
        ):
            conn = http.client.HTTPConnection("127.0.0.1", self.server.port, timeout=5.0)
            try:
                conn.request("GET", req_path)
                resp = conn.getresponse()
                resp.read()
                self.assertEqual(resp.status, 301, f"Expected 301 for {req_path}, got {resp.status}")
                self.assertEqual(resp.getheader("Location"), expected_loc)
            finally:
                conn.close()

        # 2. Verify Playwright navigation to bare prefix redirects to trailing-slash subpath cleanly.
        self.server.clear_requests()
        redirected_page = self.open_desktop_page(self.server.bare_prefix_url)
        self.assertEqual(redirected_page.url, self.server.base_url)
        wait_for_service_worker_controlled(redirected_page)
        redirect_reqs = self.server.get_requests()
        self.assertGreaterEqual(len(redirect_reqs), 1)
        self.assertEqual(redirect_reqs[0], {"method": "GET", "path": "/tetris-clasico", "status": 301})
        self.assertPageClean(redirected_page)

        # 3. Verify fresh subpath index.html load + SW precache requests strictly stay within /tetris-clasico/ and return 200.
        self.server.clear_requests()
        page = self.open_desktop_page(self.server.url_for("index.html"))
        sw_info = wait_for_service_worker_controlled(page)
        self.assertTrue(sw_info["controlled"])
        self.assertEqual(sw_info["scope"], self.server.base_url)

        subpath_reqs = self.server.get_requests()
        self.assertGreater(len(subpath_reqs), 0)
        for req in subpath_reqs:
            self.assertTrue(
                req["path"].startswith("/tetris-clasico/"),
                f"Subpath asset/SW request leaked outside /tetris-clasico/: {req!r}",
            )
            self.assertEqual(
                req["status"],
                200,
                f"Expected status 200 on subpath request, got {req!r}",
            )

        self.assertPageClean(page)
        start_game(page, level=1)
        page.keyboard.press("Space")
        _wait_raf(page, 2)
        self.assertGreater(get_hud_stats(page)["score"], 0)
        self.assertPageClean(page)

    def test_tier1_service_worker_offline_reload_on_subpath(self) -> None:
        page = self.open_desktop_page(self.server.base_url)
        sw_info = wait_for_service_worker_controlled(page)
        self.assertTrue(sw_info["controlled"])
        self.assertEqual(sw_info["state"], "activated")
        self.assertEqual(sw_info["scope"], self.server.base_url)
        self.assertPageClean(page)

        diag = self.diagnostics_for(page)
        diag.clear()
        self.server.clear_requests()

        page.context.set_offline(True)
        page.reload(wait_until="load")
        _wait_raf(page, 2)

        self.assertEqual(
            self.server.get_requests(),
            [],
            "Offline reload must be served 100% from Service Worker cache with zero server hits.",
        )
        self.assertPageClean(page)
        self.assertTrue(is_element_visible(page, SELECTORS["overlay_start"], require_interactive=True))

        start_game(page, level=1)
        board_before = capture_element_image(page, SELECTORS["board_canvas"])
        page.keyboard.press("Space")
        _wait_raf(page, 2)
        board_after = capture_element_image(page, SELECTORS["board_canvas"])

        self.assertGreater(get_hud_stats(page)["score"], 0)
        self.assertTrue(images_differ(board_before, board_after, channel_threshold=8, min_diff_pixels=15))
        self.assertPageClean(page)

    def test_tier2_diana_sudoku_sibling_isolation(self) -> None:
        context = self.new_context()
        diana_payload = {"bestSeconds": 87, "completed": 12}
        diana_body = "<!doctype html><title>Diana Sudoku</title>"
        seed_diana_sudoku_sibling(
            context,
            self.server.origin,
            diana_key=DIANA_STORAGE_KEY,
            diana_payload=diana_payload,
            diana_cache_name=DIANA_CACHE_NAME,
            diana_cache_entries={"/diana-sudoku/index.html": diana_body},
            stale_tetris_caches=["tetris-clasico-v0", "tetris-clasico-old"],
        )

        page = context.new_page()
        self.attach_diagnostics(page)
        page.goto(self.server.base_url, wait_until="load")
        wait_for_service_worker_controlled(page)
        _wait_raf(page, 2)

        page.locator(SELECTORS["btn_start_settings"]).click()
        _wait_raf(page, 1)
        set_range_value(page, SELECTORS["sensitivity_slider"], 6)
        page.locator(SELECTORS["btn_close_settings"]).click()
        _wait_raf(page, 1)

        start_game(page, level=1)
        page.keyboard.press("Space")
        _wait_raf(page, 2)

        sib = read_diana_sudoku_sibling(page)
        self.assertNotIn("tetris-clasico-v0", sib["cacheNames"])
        self.assertNotIn("tetris-clasico-old", sib["cacheNames"])
        self.assertIn(CACHE_NAME, sib["cacheNames"])
        self.assertTrue(sib["hasDianaCache"])
        self.assertIn(DIANA_CACHE_NAME, sib["cacheNames"])
        self.assertEqual(sib["dianaCacheEntryText"], diana_body)
        self.assertEqual(sib["storageJson"], diana_payload)
        self.assertPageClean(page)

    def test_tier2_offline_multi_run_play_and_restart(self) -> None:
        page = self.open_desktop_page(self.server.base_url)
        wait_for_service_worker_controlled(page)
        diag = self.diagnostics_for(page)
        diag.clear()
        self.server.clear_requests()

        page.context.set_offline(True)
        page.reload(wait_until="load")
        _wait_raf(page, 2)

        # Run 1 offline
        start_game(page, level=1)
        page.keyboard.press("Space")
        _wait_raf(page, 2)
        page.keyboard.press("Space")
        _wait_raf(page, 2)
        score_r1 = get_hud_stats(page)["score"]
        self.assertGreater(score_r1, 0)

        page.locator(SELECTORS["btn_pause"]).click()
        _wait_raf(page, 1)
        self.assertTrue(is_element_visible(page, SELECTORS["overlay_pause"], require_interactive=True))
        page.locator(SELECTORS["btn_restart"]).click()
        _wait_until_hidden(page, SELECTORS["overlay_pause"])
        _wait_raf(page, 2)

        if is_element_visible(page, SELECTORS["overlay_start"]):
            start_game(page, level=1)
        else:
            self.assertEqual(get_hud_stats(page)["score"], 0)

        # Run 2 offline
        board_before = capture_element_image(page, SELECTORS["board_canvas"])
        page.keyboard.press("Space")
        _wait_raf(page, 2)
        board_after = capture_element_image(page, SELECTORS["board_canvas"])

        self.assertGreater(get_hud_stats(page)["score"], 0)
        self.assertTrue(images_differ(board_before, board_after, channel_threshold=8, min_diff_pixels=15))

        page.locator(SELECTORS["btn_pause"]).click()
        _wait_raf(page, 1)
        self.assertTrue(is_element_visible(page, SELECTORS["overlay_pause"], require_interactive=True))
        page.locator(SELECTORS["btn_resume"]).click()
        _wait_raf(page, 1)
        self.assertFalse(is_element_visible(page, SELECTORS["overlay_pause"]))

        self.assertEqual(self.server.get_requests(), [])
        self.assertPageClean(page)


if __name__ == "__main__":
    unittest.main()

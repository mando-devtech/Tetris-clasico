"""Area C E2E tests: Desktop keyboard controls, DAS/ARR, SOCD, focus safety, and guards.

Covers PROJECT.md feature F3.1 via strictly opaque-box Playwright checks using
keyboard events, DOM focus/scroll/visibility inspections, HUD/storage checks,
and Pillow pixel/grid sampling.
"""

from __future__ import annotations

import re
import unittest
from typing import Any

from tests.e2e.harness import (
    DEFAULT_STORAGE_STATE,
    PIECE_PALETTE,
    SELECTORS,
    TetrisE2EBaseCase,
    capture_element_image,
    detect_top_spawn_piece,
    get_hud_stats,
    get_storage_data,
    images_differ,
    is_element_visible,
    sample_board_grid_state,
    start_game,
)


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


def _parse_first_int(raw: str, label: str) -> int:
    match = re.search(r"-?\d+", raw or "")
    if not match:
        raise AssertionError(f"Expected integer in {label}, got {raw!r}")
    return int(match.group(0))


def _closest_piece_from_rgb(rgb: tuple[float, float, float], candidates: tuple[str, ...]) -> str:
    r, g, b = rgb
    return min(
        candidates,
        key=lambda k: (r - PIECE_PALETTE[k][0]) ** 2
        + (g - PIECE_PALETTE[k][1]) ** 2
        + (b - PIECE_PALETTE[k][2]) ** 2,
    )


class TestAreaCKeyboard(TetrisE2EBaseCase):
    """Area C tests covering desktop keyboard controls, DAS/ARR, SOCD, and focus/input guards."""

    def _occupied_cells(self, page, *, max_row: int = 19) -> list[tuple[int, int]]:
        grid = sample_board_grid_state(page, selector=SELECTORS["board_canvas"])["grid"]
        return [
            (r, c)
            for r in range(min(max_row + 1, len(grid)))
            for c, cell in enumerate(grid[r])
            if cell is not None
        ]

    @staticmethod
    def _active_cols(cells: list[tuple[int, int]]) -> list[int]:
        return sorted({c for _, c in cells})

    @staticmethod
    def _norm_shape(cells: list[tuple[int, int]]) -> frozenset[tuple[int, int]]:
        min_r = min(r for r, _ in cells)
        min_c = min(c for _, c in cells)
        return frozenset((r - min_r, c - min_c) for r, c in cells)

    def _identify_top_piece(self, page) -> str:
        sampled = sample_board_grid_state(page, selector=SELECTORS["board_canvas"])
        grid = sampled["grid"]
        cells: list[tuple[int, int]] = []
        rgbs: list[list[int]] = []
        for r in range(3):
            for c, cell in enumerate(grid[r]):
                if cell is not None:
                    cells.append((r, c))
                    rgbs.append(cell["rgb"])
        if not cells:
            detected = detect_top_spawn_piece(page, top_rows=4)
            if detected is None:
                raise AssertionError("No top spawn piece detected.")
            return detected["piece"]

        avg_rgb = (
            sum(rgb[0] for rgb in rgbs) / len(rgbs),
            sum(rgb[1] for rgb in rgbs) / len(rgbs),
            sum(rgb[2] for rgb in rgbs) / len(rgbs),
        )
        if len({r for r, _ in cells}) == 1:
            cols = tuple(sorted(c for _, c in cells))
            if cols == (3, 4, 5, 6):
                return "I"
            if cols == (3, 4):
                return "S"
            if cols == (4, 5):
                return _closest_piece_from_rgb(avg_rgb, ("O", "Z"))
            if cols == (3, 4, 5):
                return _closest_piece_from_rgb(avg_rgb, ("T", "J", "L"))

        return _closest_piece_from_rgb(avg_rgb, tuple(PIECE_PALETTE.keys()))

    def _descend_into_visible_grid(self, page, duration_ms: int = 100) -> list[tuple[int, int]]:
        page.keyboard.down("ArrowDown")
        page.wait_for_timeout(duration_ms)
        page.keyboard.up("ArrowDown")
        _wait_raf(page, 2)
        return self._occupied_cells(page, max_row=15)

    def _assert_not_focused(self, page, selector: str) -> None:
        focused = page.locator(selector).evaluate(
            "(el) => document.activeElement === el || el.matches(':focus')"
        )
        self.assertFalse(focused, f"Button {selector!r} must blur after click so Space will not re-trigger it.")

    # ------------------------------------------------------------------
    # Tier 1: Core Functional Sanity (5 tests)
    # ------------------------------------------------------------------

    def test_tier1_lateral_movement_arrow_left_right(self) -> None:
        page = self.open_desktop_page(self.server.base_url)
        start_game(page, level=1)
        self._descend_into_visible_grid(page, duration_ms=100)

        img0 = capture_element_image(page, SELECTORS["board_canvas"])
        cols0 = self._active_cols(self._occupied_cells(page))
        self.assertGreater(len(cols0), 0)

        page.keyboard.press("ArrowLeft")
        _wait_raf(page, 2)
        img_left = capture_element_image(page, SELECTORS["board_canvas"])
        cols_left = self._active_cols(self._occupied_cells(page))
        self.assertTrue(images_differ(img0, img_left, channel_threshold=8, min_diff_pixels=15))
        self.assertEqual(cols_left, [c - 1 for c in cols0])

        page.keyboard.press("ArrowRight")
        page.keyboard.press("ArrowRight")
        _wait_raf(page, 2)
        img_right = capture_element_image(page, SELECTORS["board_canvas"])
        cols_right = self._active_cols(self._occupied_cells(page))
        self.assertTrue(images_differ(img_left, img_right, channel_threshold=8, min_diff_pixels=15))
        self.assertEqual(cols_right, [c + 1 for c in cols0])
        self.assertPageClean(page)

    def test_tier1_rotation_arrow_up_key_x_cw_and_key_z_ccw(self) -> None:
        page = self.open_desktop_page(self.server.base_url)
        start_game(page, level=1)

        if self._identify_top_piece(page) == "O":
            page.keyboard.press("KeyC")
            _wait_raf(page, 2)

        cells_0 = self._descend_into_visible_grid(page)
        self.assertEqual(len(cells_0), 4)
        shape_0 = self._norm_shape(cells_0)
        img_0 = capture_element_image(page, SELECTORS["board_canvas"])

        page.keyboard.press("KeyX")
        _wait_raf(page, 2)
        cells_x = self._occupied_cells(page, max_row=15)
        self.assertEqual(len(cells_x), 4)
        shape_x = self._norm_shape(cells_x)
        img_x = capture_element_image(page, SELECTORS["board_canvas"])
        self.assertNotEqual(shape_x, shape_0)
        self.assertTrue(images_differ(img_0, img_x, channel_threshold=8, min_diff_pixels=15))

        page.keyboard.press("KeyZ")
        _wait_raf(page, 2)
        cells_z = self._occupied_cells(page, max_row=15)
        self.assertEqual(len(cells_z), 4)
        self.assertEqual(self._norm_shape(cells_z), shape_0)

        page.keyboard.press("ArrowUp")
        _wait_raf(page, 2)
        cells_up = self._occupied_cells(page, max_row=15)
        self.assertEqual(len(cells_up), 4)
        self.assertEqual(self._norm_shape(cells_up), shape_x)

        page.keyboard.press("KeyZ")
        _wait_raf(page, 2)
        cells_z2 = self._occupied_cells(page, max_row=15)
        self.assertEqual(len(cells_z2), 4)
        self.assertEqual(self._norm_shape(cells_z2), shape_0)
        self.assertPageClean(page)

    def test_tier1_soft_drop_and_hard_drop_scoring_and_lock(self) -> None:
        page = self.open_desktop_page(self.server.base_url)
        start_game(page, level=1)

        stats_0 = get_hud_stats(page)
        cells_0 = self._occupied_cells(page)
        max_r0 = max(r for r, _ in cells_0)

        page.keyboard.down("ArrowDown")
        page.wait_for_timeout(180)
        page.keyboard.up("ArrowDown")
        _wait_raf(page, 2)

        stats_soft = get_hud_stats(page)
        cells_soft = self._occupied_cells(page)
        max_r_soft = max(r for r, _ in cells_soft)
        self.assertGreaterEqual(max_r_soft, max_r0 + 2)
        soft_pts = stats_soft["score"] - stats_0["score"]
        self.assertGreaterEqual(soft_pts, 2)
        self.assertLessEqual(soft_pts, max_r_soft - max_r0)

        page.keyboard.press("Space")
        _wait_raf(page, 2)
        stats_hd = get_hud_stats(page)
        hd_pts = stats_hd["score"] - stats_soft["score"]
        self.assertEqual(hd_pts % 2, 0)
        self.assertGreaterEqual(hd_pts, 2 * max(1, 19 - max_r_soft - 1))
        self.assertLessEqual(hd_pts, 2 * (19 - max_r_soft))

        grid_hd = sample_board_grid_state(page)["grid"]
        self.assertTrue(any(cell is not None for cell in grid_hd[19]))
        self.assertIsNotNone(detect_top_spawn_piece(page))
        self.assertPageClean(page)

    def test_tier1_hold_keys_c_shift_left_shift_right(self) -> None:
        page = self.open_desktop_page(self.server.base_url)
        start_game(page, level=1)

        hold_empty = capture_element_image(page, SELECTORS["hold_canvas"])
        spawn_1 = self._identify_top_piece(page)

        page.keyboard.press("KeyC")
        _wait_raf(page, 2)
        hold_c = capture_element_image(page, SELECTORS["hold_canvas"])
        self.assertTrue(images_differ(hold_empty, hold_c, channel_threshold=10, min_diff_pixels=25))
        spawn_2 = self._identify_top_piece(page)
        self.assertNotEqual(spawn_2, spawn_1)

        # Second Hold before locking must be ignored (ShiftLeft check).
        page.keyboard.press("ShiftLeft")
        _wait_raf(page, 2)
        self.assertEqual(self._identify_top_piece(page), spawn_2)
        hold_blocked = capture_element_image(page, SELECTORS["hold_canvas"])
        self.assertFalse(images_differ(hold_c, hold_blocked, channel_threshold=8, min_diff_pixels=5))

        # Lock piece #2 -> ShiftLeft swaps spawn_1 back to active.
        page.keyboard.press("Space")
        _wait_raf(page, 2)
        spawn_3 = self._identify_top_piece(page)
        self.assertNotEqual(spawn_3, spawn_1)
        hold_before_sl = capture_element_image(page, SELECTORS["hold_canvas"])

        page.keyboard.press("ShiftLeft")
        _wait_raf(page, 2)
        self.assertEqual(self._identify_top_piece(page), spawn_1)
        hold_after_sl = capture_element_image(page, SELECTORS["hold_canvas"])
        self.assertTrue(images_differ(hold_before_sl, hold_after_sl, channel_threshold=10, min_diff_pixels=25))

        # Lock -> ShiftRight swaps spawn_3 back to active.
        page.keyboard.press("Space")
        _wait_raf(page, 2)
        spawn_4 = self._identify_top_piece(page)
        self.assertNotEqual(spawn_4, spawn_3)
        hold_before_sr = capture_element_image(page, SELECTORS["hold_canvas"])

        page.keyboard.press("ShiftRight")
        _wait_raf(page, 2)
        self.assertEqual(self._identify_top_piece(page), spawn_3)
        hold_after_sr = capture_element_image(page, SELECTORS["hold_canvas"])
        self.assertTrue(images_differ(hold_before_sr, hold_after_sr, channel_threshold=10, min_diff_pixels=25))
        self.assertPageClean(page)

    def test_tier1_pause_resume_key_p_and_escape_freeze_gravity_level_15(self) -> None:
        page = self.open_desktop_page(self.server.base_url)
        self.assertTrue(is_element_visible(page, SELECTORS["overlay_start"], require_interactive=True))
        for _ in range(14):
            page.locator(SELECTORS["btn_level_up"]).click()
        self.assertEqual(int(page.locator(SELECTORS["start_level_value"]).inner_text().strip()), 15)

        # Click Play and immediately pause before Level 15 gravity (~134 ms) reaches row 19.
        page.locator(SELECTORS["btn_play"]).click()
        page.keyboard.press("KeyP")
        _wait_raf(page, 2)
        self.assertTrue(is_element_visible(page, SELECTORS["overlay_pause"], require_interactive=True))

        g1 = sample_board_grid_state(page)
        img1 = capture_element_image(page, SELECTORS["board_canvas"])
        page.wait_for_timeout(1200)
        g2 = sample_board_grid_state(page)
        img2 = capture_element_image(page, SELECTORS["board_canvas"])
        self.assertEqual(g1["grid"], g2["grid"])
        self.assertFalse(images_differ(img1, img2, channel_threshold=16, min_diff_pixels=20))

        page.keyboard.press("KeyP")
        _wait_raf(page, 1)
        self.assertFalse(is_element_visible(page, SELECTORS["overlay_pause"]))
        cells_resumed_0 = self._occupied_cells(page)
        self.assertGreater(len(cells_resumed_0), 0)
        self.assertLessEqual(
            len(cells_resumed_0),
            4,
            f"Level 15 must stay frozen during 1200 ms pause without locking Piece 1 & spawning Piece 2 (got {len(cells_resumed_0)} cells).",
        )

        page.wait_for_timeout(700)
        _wait_raf(page, 2)
        cells_resumed_1 = self._occupied_cells(page)
        self.assertGreaterEqual(
            len(cells_resumed_1),
            6,
            f"Level 15 gravity & lock must resume after KeyP unpause (got {len(cells_resumed_1)} cells).",
        )
        self.assertEqual(max(r for r, _ in cells_resumed_1), 19)

        page.keyboard.press("Escape")
        _wait_raf(page, 2)
        self.assertTrue(is_element_visible(page, SELECTORS["overlay_pause"], require_interactive=True))
        g3 = sample_board_grid_state(page)
        img3 = capture_element_image(page, SELECTORS["board_canvas"])
        page.wait_for_timeout(1000)
        g4 = sample_board_grid_state(page)
        img4 = capture_element_image(page, SELECTORS["board_canvas"])
        self.assertEqual(g3["grid"], g4["grid"])
        self.assertFalse(images_differ(img3, img4, channel_threshold=16, min_diff_pixels=20))

        page.keyboard.press("Escape")
        _wait_raf(page, 2)
        self.assertFalse(is_element_visible(page, SELECTORS["overlay_pause"]))
        self.assertPageClean(page)

    # ------------------------------------------------------------------
    # Tier 2: Boundary & Edge Behavior (5 tests)
    # ------------------------------------------------------------------

    def test_tier2_das_arr_and_socd_last_input_priority(self) -> None:
        page = self.open_desktop_page(self.server.base_url)
        start_game(page, level=1)

        # Descend slightly so all 4 minos (including S/Z top row) are visible on the 10x20 grid.
        self._descend_into_visible_grid(page, duration_ms=90)
        cols_spawn = self._active_cols(self._occupied_cells(page))
        page.keyboard.press("ArrowLeft")
        _wait_raf(page, 2)
        cols_tap = self._active_cols(self._occupied_cells(page))
        self.assertEqual(cols_tap, [c - 1 for c in cols_spawn])
        self.assertGreaterEqual(cols_tap[0], 2)

        # Hold ArrowLeft 600 ms -> DAS+ARR drives piece flush to col 0.
        page.keyboard.down("ArrowLeft")
        page.wait_for_timeout(600)
        _wait_raf(page, 2)
        cols_left = self._active_cols(self._occupied_cells(page))
        self.assertEqual(cols_left[0], 0)

        # Keep ArrowLeft held while holding ArrowRight for 280 ms -> SOCD last-input priority moves right.
        page.keyboard.down("ArrowRight")
        page.wait_for_timeout(280)
        _wait_raf(page, 2)
        cols_mid = self._active_cols(self._occupied_cells(page))
        self.assertGreaterEqual(cols_mid[0], 2, f"Expected SOCD ArrowRight override to col >= 2, got {cols_mid}")

        # Release ArrowRight while ArrowLeft stays held -> returns leftward to col 0.
        page.keyboard.up("ArrowRight")
        page.wait_for_timeout(550)
        _wait_raf(page, 2)
        cols_back = self._active_cols(self._occupied_cells(page))
        self.assertLess(cols_back[0], cols_mid[0])
        self.assertEqual(cols_back[0], 0)

        page.keyboard.up("ArrowLeft")
        page.keyboard.press("Space")
        _wait_raf(page, 2)

        # Descend slightly on Piece 2 so S/Z top row is visible, then hold ArrowRight 600 ms -> hits col 9.
        self._descend_into_visible_grid(page, duration_ms=90)
        page.keyboard.down("ArrowRight")
        page.wait_for_timeout(600)
        page.keyboard.up("ArrowRight")
        _wait_raf(page, 2)
        cols_right_wall = self._active_cols(self._occupied_cells(page, max_row=15))
        self.assertEqual(max(cols_right_wall), 9)
        self.assertPageClean(page)

    def test_tier2_zero_page_scroll_and_prevent_default_at_1024x600(self) -> None:
        page = self.open_desktop_page(self.server.base_url, viewport=(1024, 600))
        start_game(page, level=1)

        page.evaluate(
            """() => {
              window.__e2eKeyEvents = [];
              window.addEventListener('keydown', (e) => {
                window.__e2eKeyEvents.push({
                  code: e.code,
                  key: e.key,
                  defaultPrevented: Boolean(e.defaultPrevented)
                });
              }, false);
            }"""
        )

        keys = ("ArrowDown", "ArrowUp", "ArrowLeft", "ArrowRight", "Space")
        for key in keys:
            page.keyboard.press(key)
        _wait_raf(page, 2)

        scroll_state = page.evaluate(
            """() => ({
              scrollX: window.scrollX,
              scrollY: window.scrollY,
              scrollW: document.documentElement.scrollWidth,
              scrollH: document.documentElement.scrollHeight,
              innerW: window.innerWidth,
              innerH: window.innerHeight,
              events: window.__e2eKeyEvents
            })"""
        )
        self.assertEqual(scroll_state["scrollX"], 0)
        self.assertEqual(scroll_state["scrollY"], 0)
        self.assertLessEqual(scroll_state["scrollW"], scroll_state["innerW"])
        self.assertLessEqual(scroll_state["scrollH"], scroll_state["innerH"])

        by_code = {ev["code"]: ev["defaultPrevented"] for ev in scroll_state["events"]}
        for key in keys:
            self.assertIn(key, by_code, f"Keydown spy missed {key}")
            self.assertTrue(by_code[key], f"Gameplay key {key} must call preventDefault().")
        self.assertPageClean(page)

    def test_tier2_hud_buttons_blur_and_space_hard_drops_safely(self) -> None:
        page = self.open_desktop_page(self.server.base_url)
        start_game(page, level=1)

        # Music toggle button blurs and is not re-triggered by Space.
        music_before = (get_storage_data(page) or {}).get(
            "musicEnabled", DEFAULT_STORAGE_STATE["musicEnabled"]
        )
        page.locator(SELECTORS["btn_music"]).click()
        _wait_raf(page, 2)
        self._assert_not_focused(page, SELECTORS["btn_music"])
        music_after = (get_storage_data(page) or {}).get("musicEnabled")
        self.assertEqual(music_after, not music_before)

        score_0 = get_hud_stats(page)["score"]
        page.keyboard.press("Space")
        _wait_raf(page, 2)
        self.assertGreater(get_hud_stats(page)["score"], score_0)
        self.assertEqual((get_storage_data(page) or {}).get("musicEnabled"), music_after)

        # SFX toggle button blurs and is not re-triggered by Space.
        sfx_before = (get_storage_data(page) or {}).get(
            "sfxEnabled", DEFAULT_STORAGE_STATE["sfxEnabled"]
        )
        page.locator(SELECTORS["btn_sfx"]).click()
        _wait_raf(page, 2)
        self._assert_not_focused(page, SELECTORS["btn_sfx"])
        sfx_after = (get_storage_data(page) or {}).get("sfxEnabled")
        self.assertEqual(sfx_after, not sfx_before)

        score_1 = get_hud_stats(page)["score"]
        page.keyboard.press("Space")
        _wait_raf(page, 2)
        self.assertGreater(get_hud_stats(page)["score"], score_1)
        self.assertEqual((get_storage_data(page) or {}).get("sfxEnabled"), sfx_after)

        # Pause & Resume buttons blur and Space behaves safely in both states.
        page.locator(SELECTORS["btn_pause"]).click()
        _wait_raf(page, 2)
        self.assertTrue(is_element_visible(page, SELECTORS["overlay_pause"], require_interactive=True))
        self._assert_not_focused(page, SELECTORS["btn_pause"])

        score_paused = get_hud_stats(page)["score"]
        page.keyboard.press("Space")
        _wait_raf(page, 2)
        self.assertTrue(
            is_element_visible(page, SELECTORS["overlay_pause"]),
            "Pressing Space while paused must NOT unpause or Hard Drop.",
        )
        self.assertEqual(get_hud_stats(page)["score"], score_paused)

        page.locator(SELECTORS["btn_resume"]).click()
        _wait_raf(page, 2)
        self.assertFalse(is_element_visible(page, SELECTORS["overlay_pause"]))
        self._assert_not_focused(page, SELECTORS["btn_resume"])

        page.keyboard.press("Space")
        _wait_raf(page, 2)
        self.assertGreater(get_hud_stats(page)["score"], score_paused)
        self.assertFalse(is_element_visible(page, SELECTORS["overlay_pause"]))
        self.assertPageClean(page)

    def test_tier2_blur_and_visibilitychange_auto_pause_no_stuck_keys(self) -> None:
        page = self.open_desktop_page(self.server.base_url)
        start_game(page, level=1)

        # Subcase A: window blur while ArrowLeft is actively held past DAS (180 ms).
        self._descend_into_visible_grid(page, duration_ms=100)
        for _ in range(4):
            page.keyboard.press("ArrowRight")
        _wait_raf(page, 2)

        page.keyboard.down("ArrowLeft")
        page.wait_for_timeout(180)
        page.evaluate("() => window.dispatchEvent(new Event('blur'))")
        _wait_raf(page, 2)

        self.assertTrue(
            is_element_visible(page, SELECTORS["overlay_pause"], require_interactive=True),
            "Window blur during active play must auto-pause.",
        )

        page.locator(SELECTORS["btn_resume"]).click()
        _wait_raf(page, 1)
        cols_on_resume = self._active_cols(self._occupied_cells(page, max_row=15))
        self.assertGreaterEqual(cols_on_resume[0], 2)

        page.wait_for_timeout(450)
        _wait_raf(page, 2)
        cols_after_blur = self._active_cols(self._occupied_cells(page, max_row=15))
        self.assertEqual(
            cols_after_blur,
            cols_on_resume,
            "Held ArrowLeft must be cleared on blur so no stuck-key drift occurs after Resume.",
        )
        page.keyboard.up("ArrowLeft")

        # Subcase B: document visibilitychange (hidden=true) while ArrowLeft is actively held.
        page.keyboard.press("Space")
        _wait_raf(page, 2)
        self._descend_into_visible_grid(page, duration_ms=100)
        for _ in range(4):
            page.keyboard.press("ArrowRight")
        _wait_raf(page, 2)

        page.keyboard.down("ArrowLeft")
        page.wait_for_timeout(180)
        page.evaluate(
            """() => {
              Object.defineProperty(document, 'hidden', { configurable: true, get: () => true });
              Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'hidden' });
              document.dispatchEvent(new Event('visibilitychange'));
            }"""
        )
        _wait_raf(page, 2)

        self.assertTrue(
            is_element_visible(page, SELECTORS["overlay_pause"], require_interactive=True),
            "visibilitychange (hidden) during active play must auto-pause.",
        )

        page.evaluate(
            """() => {
              delete document.hidden;
              delete document.visibilityState;
            }"""
        )
        page.locator(SELECTORS["btn_resume"]).click()
        _wait_raf(page, 1)
        cols_vis_resume = self._active_cols(self._occupied_cells(page, max_row=15))
        self.assertGreaterEqual(cols_vis_resume[0], 2)

        page.wait_for_timeout(450)
        _wait_raf(page, 2)
        cols_after_vis = self._active_cols(self._occupied_cells(page, max_row=15))
        self.assertEqual(
            cols_after_vis,
            cols_vis_resume,
            "Held ArrowLeft must be cleared on visibilitychange so no stuck-key drift occurs after Resume.",
        )
        page.keyboard.up("ArrowLeft")
        self.assertPageClean(page)

    def test_tier2_rising_edge_repeat_modifier_guard_and_settings_slider_isolation(self) -> None:
        page = self.open_desktop_page(self.server.base_url)
        start_game(page, level=1)

        # Skip 'O' via Space (never KeyC) so canHold remains True and #hold-canvas stays empty.
        if self._identify_top_piece(page) == "O":
            page.keyboard.press("Space")
            _wait_raf(page, 2)

        cells_0 = self._descend_into_visible_grid(page, duration_ms=100)
        self.assertEqual(len(cells_0), 4)
        score_0 = get_hud_stats(page)["score"]
        hold_0 = capture_element_image(page, SELECTORS["hold_canvas"])
        cols_0 = self._active_cols(cells_0)
        shape_0 = self._norm_shape(cells_0)

        # Synthetic repeat: true must be ignored on rising-edge actions.
        repeat_keys = [
            (" ", "Space"),
            ("ArrowUp", "ArrowUp"),
            ("x", "KeyX"),
            ("z", "KeyZ"),
            ("c", "KeyC"),
            ("Shift", "ShiftLeft"),
        ]
        for key, code in repeat_keys:
            page.evaluate(
                """({ key, code }) => {
                  const target = document.activeElement || document.body;
                  target.dispatchEvent(new KeyboardEvent('keydown', {
                    key, code, repeat: true, bubbles: true, cancelable: true
                  }));
                }""",
                {"key": key, "code": code},
            )
        _wait_raf(page, 2)

        cells_rep = self._occupied_cells(page, max_row=15)
        self.assertEqual(get_hud_stats(page)["score"], score_0)
        self.assertFalse(images_differ(hold_0, capture_element_image(page, SELECTORS["hold_canvas"]), min_diff_pixels=5))
        self.assertEqual(self._active_cols(cells_rep), cols_0)
        self.assertEqual(self._norm_shape(cells_rep), shape_0)

        # Modifier-held combinations must be ignored by game controls.
        for combo in ("Control+ArrowLeft", "Control+KeyC", "Meta+Space", "Alt+ArrowUp"):
            page.keyboard.press(combo)
        _wait_raf(page, 2)

        cells_mod = self._occupied_cells(page, max_row=15)
        self.assertEqual(get_hud_stats(page)["score"], score_0)
        self.assertFalse(images_differ(hold_0, capture_element_image(page, SELECTORS["hold_canvas"]), min_diff_pixels=5))
        self.assertEqual(self._active_cols(cells_mod), cols_0)
        self.assertEqual(self._norm_shape(cells_mod), shape_0)

        # Pause -> Settings slider keyboard interaction must adjust slider without moving board.
        page.locator(SELECTORS["btn_pause"]).click()
        _wait_raf(page, 1)
        self.assertTrue(is_element_visible(page, SELECTORS["overlay_pause"], require_interactive=True))
        page.locator(SELECTORS["btn_pause_settings"]).click()
        _wait_raf(page, 1)
        self.assertTrue(is_element_visible(page, SELECTORS["modal_settings"], require_interactive=True))

        slider = page.locator(SELECTORS["sensitivity_slider"])
        slider.focus()
        val_start = int(slider.input_value())
        self.assertEqual(
            _parse_first_int(
                page.locator(SELECTORS["sensitivity_value"]).inner_text(),
                SELECTORS["sensitivity_value"],
            ),
            val_start,
        )

        page.keyboard.press("ArrowRight")
        page.keyboard.press("ArrowRight")
        _wait_raf(page, 1)
        self.assertEqual(int(slider.input_value()), val_start + 2)
        self.assertEqual(
            _parse_first_int(
                page.locator(SELECTORS["sensitivity_value"]).inner_text(),
                SELECTORS["sensitivity_value"],
            ),
            val_start + 2,
        )

        page.keyboard.press("ArrowLeft")
        _wait_raf(page, 1)
        self.assertEqual(int(slider.input_value()), val_start + 1)
        self.assertEqual(
            _parse_first_int(
                page.locator(SELECTORS["sensitivity_value"]).inner_text(),
                SELECTORS["sensitivity_value"],
            ),
            val_start + 1,
        )

        page.keyboard.press("Escape")
        _wait_raf(page, 2)
        self.assertFalse(is_element_visible(page, SELECTORS["modal_settings"]))

        if is_element_visible(page, SELECTORS["overlay_pause"]):
            page.locator(SELECTORS["btn_resume"]).click()
            _wait_raf(page, 1)
        cells_after_pause_settings = self._occupied_cells(page, max_row=15)
        self.assertEqual(self._active_cols(cells_after_pause_settings), cols_0)
        self.assertEqual(self._norm_shape(cells_after_pause_settings), shape_0)

        # Verify HUD #btn-settings -> slider ArrowRight -> Escape isolation too.
        page.locator(SELECTORS["btn_settings"]).click()
        _wait_raf(page, 1)
        self.assertTrue(is_element_visible(page, SELECTORS["modal_settings"], require_interactive=True))

        slider.focus()
        page.keyboard.press("ArrowRight")
        _wait_raf(page, 1)
        self.assertEqual(int(slider.input_value()), val_start + 2)

        page.keyboard.press("Escape")
        _wait_raf(page, 2)
        self.assertFalse(is_element_visible(page, SELECTORS["modal_settings"]))
        if is_element_visible(page, SELECTORS["overlay_pause"]):
            page.locator(SELECTORS["btn_resume"]).click()
            _wait_raf(page, 1)
        cells_after_hud_settings = self._occupied_cells(page, max_row=15)
        self.assertEqual(self._active_cols(cells_after_hud_settings), cols_0)
        self.assertEqual(self._norm_shape(cells_after_hud_settings), shape_0)
        self.assertPageClean(page)


if __name__ == "__main__":
    unittest.main()

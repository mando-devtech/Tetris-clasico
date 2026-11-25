"""Area E E2E Tests: Xbox Gamepad API Integration, Deadzone & Hot-Plug.

Covers PROJECT.md feature F3.5 via strict opaque-box Playwright interactions
and the harness ``window.__e2eGamepad`` / ``navigator.getGamepads()`` driver.
"""

from __future__ import annotations

import unittest
from typing import Any

from playwright.sync_api import Page

from tests.e2e.harness import (
    SELECTORS,
    TetrisE2EBaseCase,
    capture_element_image,
    detect_top_spawn_piece,
    get_hud_stats,
    images_differ,
    is_element_visible,
    sample_board_grid_state,
    start_game,
)


def _occupied_cells(grid_state: dict[str, Any]) -> list[tuple[int, int, str]]:
    cells: list[tuple[int, int, str]] = []
    for r, row in enumerate(grid_state["grid"]):
        for c, cell in enumerate(row):
            if cell is not None:
                cells.append((r, c, str(cell["piece"])))
    return cells


def _cols_set(cells: list[tuple[int, int, str]]) -> set[int]:
    return {c for _, c, _ in cells}


def _normalize_shape(cells: list[tuple[int, int, str]]) -> frozenset[tuple[int, int]]:
    if not cells:
        return frozenset()
    min_r = min(r for r, _, _ in cells)
    min_c = min(c for _, c, _ in cells)
    return frozenset((r - min_r, c - min_c) for r, c, _ in cells)


def _min_row(cells: list[tuple[int, int, str]]) -> int:
    return min(r for r, _, _ in cells) if cells else -1


def _max_row(cells: list[tuple[int, int, str]]) -> int:
    return max(r for r, _, _ in cells) if cells else -1


def _count_bottom_cells(grid_state: dict[str, Any], start_row: int = 14) -> int:
    grid = grid_state["grid"]
    total = 0
    for r in range(start_row, len(grid)):
        for cell in grid[r]:
            if cell is not None:
                total += 1
    return total


def _wait_frames(page: Page, count: int = 2) -> None:
    page.evaluate(
        """(n) => new Promise((resolve) => {
          let i = 0;
          function tick() {
            i += 1;
            if (i >= n) resolve();
            else requestAnimationFrame(tick);
          }
          requestAnimationFrame(tick);
        })""",
        count,
    )


def _wait_visible(
    page: Page,
    selector: str,
    expected: bool = True,
    *,
    require_interactive: bool = False,
    timeout_ms: int = 2500,
) -> None:
    elapsed = 0
    step_ms = 30
    while elapsed <= timeout_ms:
        if is_element_visible(page, selector, require_interactive=require_interactive) is expected:
            return
        page.wait_for_timeout(step_ms)
        elapsed += step_ms
    actual = is_element_visible(page, selector, require_interactive=require_interactive)
    raise AssertionError(
        f"Timed out waiting for {selector!r} visibility={expected}; actual={actual}"
    )


def _gp_connect(page: Page, **opts: Any) -> dict[str, Any]:
    return page.evaluate("(o) => window.__e2eGamepad.connect(o)", opts)


def _gp_disconnect(page: Page, pad_index: int = 0) -> bool:
    return bool(page.evaluate("(i) => window.__e2eGamepad.disconnect(i)", pad_index))


def _gp_set_button(
    page: Page,
    button_index: int,
    pressed: bool,
    value: float | None = None,
    pad_index: int = 0,
) -> None:
    page.evaluate(
        "({ b, p, v, i }) => window.__e2eGamepad.setButton(b, p, v, i)",
        {"b": button_index, "p": pressed, "v": value, "i": pad_index},
    )


def _gp_set_axis(page: Page, axis_index: int, value: float, pad_index: int = 0) -> None:
    page.evaluate(
        "({ a, v, i }) => window.__e2eGamepad.setAxis(a, v, i)",
        {"a": axis_index, "v": value, "i": pad_index},
    )


def _gp_tap_button(
    page: Page,
    button_index: int,
    hold_frames: int = 2,
    settle_frames: int = 2,
    pad_index: int = 0,
) -> None:
    _gp_set_button(page, button_index, True, None, pad_index)
    _wait_frames(page, hold_frames)
    _gp_set_button(page, button_index, False, None, pad_index)
    _wait_frames(page, settle_frames)


def _nudge_piece_fully_visible(page: Page) -> list[tuple[int, int, str]]:
    """Soft-drop briefly via D-Pad Down so all 4 cells leave the hidden buffer row."""
    _gp_set_button(page, 13, True)
    page.wait_for_timeout(90)
    _gp_set_button(page, 13, False)
    _wait_frames(page, 2)
    cells = _occupied_cells(sample_board_grid_state(page))
    if len(cells) < 4:
        _gp_set_button(page, 13, True)
        page.wait_for_timeout(80)
        _gp_set_button(page, 13, False)
        _wait_frames(page, 2)
        cells = _occupied_cells(sample_board_grid_state(page))
    if len(cells) < 4:
        raise AssertionError(f"Expected 4 visible cells after soft-drop nudge, got {cells!r}")
    return cells


def _wait_for_gravity_tick(page: Page, initial_cells: list[tuple[int, int, str]], timeout_ms: int = 1250) -> list[tuple[int, int, str]]:
    """Wait for one natural level-1 gravity row drop to align a fresh ~950ms window."""
    base_min_r = _min_row(initial_cells)
    elapsed = 0
    step_ms = 25
    while elapsed <= timeout_ms:
        cur = _occupied_cells(sample_board_grid_state(page))
        if len(cur) == 4 and _min_row(cur) > base_min_r:
            return cur
        page.wait_for_timeout(step_ms)
        elapsed += step_ms
    raise AssertionError("Timed out waiting for level-1 gravity tick alignment.")


def _ensure_non_o_active_piece(page: Page) -> str:
    spawn = detect_top_spawn_piece(page)
    if spawn is None:
        raise AssertionError("No spawning piece detected at top of board.")
    if spawn["piece"] == "O":
        _gp_tap_button(page, 4)  # LB Hold
        spawn = detect_top_spawn_piece(page)
        if spawn is None or spawn["piece"] == "O":
            raise AssertionError(f"Expected non-O piece after LB Hold swap, got {spawn!r}")
    return str(spawn["piece"])


def _read_badge_state(page: Page) -> dict[str, Any]:
    loc = page.locator(SELECTORS["gamepad_badge"])
    text = loc.inner_text().strip() if loc.count() > 0 else ""
    return {
        "visible": is_element_visible(page, SELECTORS["gamepad_badge"]),
        "text": text,
    }


def _read_settings_gp_status(page: Page) -> str:
    return page.locator(SELECTORS["settings_gamepad_status"]).inner_text().strip()


class TestAreaEGamepad(TetrisE2EBaseCase):
    """Tier 1 & Tier 2 E2E coverage for Xbox / Generic Gamepad support (F3.5)."""

    def _assert_connected_text(self, text: str, *, expect_xbox: bool) -> None:
        norm = " ".join(text.lower().split())
        self.assertNotIn("desconectado", norm, f"Unexpected disconnected wording in {text!r}")
        self.assertNotIn("ningún", norm, f"Unexpected empty wording in {text!r}")
        self.assertNotIn("sin control", norm, f"Unexpected empty wording in {text!r}")
        if expect_xbox:
            self.assertIn("control xbox conectado", norm, f"Expected Xbox connected badge, got {text!r}")
        else:
            self.assertIn("control conectado", norm, f"Expected generic connected badge, got {text!r}")
            self.assertNotIn("xbox", norm, f"Generic HID controller must not claim Xbox: {text!r}")

    def _assert_disconnected_state(
        self,
        badge_state: dict[str, Any],
        baseline_badge: dict[str, Any],
        settings_text: str,
        baseline_settings: str,
    ) -> None:
        badge_norm = " ".join(str(badge_state["text"]).lower().split())
        self.assertNotIn("control xbox conectado", badge_norm)
        if badge_state["visible"]:
            self.assertTrue(
                badge_state["text"] == baseline_badge["text"]
                or any(tok in badge_norm for tok in ("desconectado", "sin", "ning", "no ")),
                f"Visible disconnected badge has unexpected connected text: {badge_state!r}",
            )

        settings_norm = " ".join(settings_text.lower().split())
        self.assertNotIn("control xbox conectado", settings_norm)
        self.assertTrue(
            settings_text == baseline_settings
            or any(tok in settings_norm for tok in ("desconectado", "sin", "ning", "no ")),
            f"Disconnected settings status should match baseline or disconnected text, got {settings_text!r}",
        )

    # ------------------------------------------------------------------
    # Tier 1: Core Functional Sanity (5 tests)
    # ------------------------------------------------------------------

    def test_tier1_01_gamepad_detection_and_spanish_badge(self) -> None:
        """F3.5: Hot-plug and pre-start Xbox connection update HUD badge and Settings status."""
        # Part A: Hot-plug mid-game.
        page = self.open_desktop_page(gamepad=True, rng_seed=42)
        baseline_badge = _read_badge_state(page)
        page.locator(SELECTORS["btn_start_settings"]).click()
        _wait_visible(page, SELECTORS["modal_settings"], True)
        baseline_settings = _read_settings_gp_status(page)
        page.locator(SELECTORS["btn_close_settings"]).click()
        _wait_visible(page, SELECTORS["modal_settings"], False)

        start_game(page, level=1)
        _gp_connect(page)
        _wait_frames(page, 3)

        badge_hot = _read_badge_state(page)
        self.assertTrue(badge_hot["visible"], "HUD #gamepad-badge must be visible after Xbox connect")
        self._assert_connected_text(badge_hot["text"], expect_xbox=True)

        page.locator(SELECTORS["btn_settings"]).click()
        _wait_visible(page, SELECTORS["modal_settings"], True)
        settings_hot = _read_settings_gp_status(page)
        self.assertNotEqual(settings_hot, baseline_settings)
        self._assert_connected_text(settings_hot, expect_xbox=True)
        self.assertPageClean(page)

        # Part B: Pre-connect while Start overlay is visible.
        page_pre = self.open_desktop_page(gamepad=True, rng_seed=42)
        page_pre.locator(SELECTORS["btn_start_settings"]).click()
        _wait_visible(page_pre, SELECTORS["modal_settings"], True)
        pre_baseline_settings = _read_settings_gp_status(page_pre)
        page_pre.locator(SELECTORS["btn_close_settings"]).click()
        _wait_visible(page_pre, SELECTORS["modal_settings"], False)

        _gp_connect(page_pre)
        _wait_frames(page_pre, 3)

        page_pre.locator(SELECTORS["btn_start_settings"]).click()
        _wait_visible(page_pre, SELECTORS["modal_settings"], True)
        pre_connected_settings = _read_settings_gp_status(page_pre)
        self.assertNotEqual(pre_connected_settings, pre_baseline_settings)
        self._assert_connected_text(pre_connected_settings, expect_xbox=True)
        page_pre.locator(SELECTORS["btn_close_settings"]).click()
        _wait_visible(page_pre, SELECTORS["modal_settings"], False)

        start_game(page_pre, level=1)
        badge_pre = _read_badge_state(page_pre)
        self.assertTrue(badge_pre["visible"])
        self._assert_connected_text(badge_pre["text"], expect_xbox=True)
        self.assertPageClean(page_pre)

    def test_tier1_02_dpad_and_left_stick_lateral_movement(self) -> None:
        """F3.5: D-Pad Left/Right and Left Stick X (±0.85) shift active piece horizontally."""
        page = self.open_desktop_page(gamepad=True, rng_seed=42)
        _gp_connect(page)
        start_game(page, level=1)

        cells_0 = _nudge_piece_fully_visible(page)
        cols_0 = _cols_set(cells_0)

        _gp_tap_button(page, 14)  # D-Pad Left
        cols_1 = _cols_set(_occupied_cells(sample_board_grid_state(page)))
        self.assertEqual(min(cols_1), min(cols_0) - 1)
        self.assertEqual(max(cols_1), max(cols_0) - 1)

        _gp_tap_button(page, 15)  # D-Pad Right
        cols_2 = _cols_set(_occupied_cells(sample_board_grid_state(page)))
        self.assertEqual(cols_2, cols_0)

        _gp_set_axis(page, 0, 0.85)
        _wait_frames(page, 2)
        _gp_set_axis(page, 0, 0.0)
        _wait_frames(page, 2)
        cols_3 = _cols_set(_occupied_cells(sample_board_grid_state(page)))
        self.assertGreater(min(cols_3), min(cols_2))

        _gp_set_axis(page, 0, -0.85)
        _wait_frames(page, 2)
        _gp_set_axis(page, 0, 0.0)
        _wait_frames(page, 2)
        cols_4 = _cols_set(_occupied_cells(sample_board_grid_state(page)))
        self.assertLess(min(cols_4), min(cols_3))
        self.assertPageClean(page)

    def test_tier1_03_face_buttons_rotate_cw_and_ccw(self) -> None:
        """F3.5: A and B rotate clockwise; X rotates counter-clockwise (reversing A without 180° confusion)."""
        page = self.open_desktop_page(gamepad=True, rng_seed=42)
        _gp_connect(page)
        start_game(page, level=1)

        _ensure_non_o_active_piece(page)
        nudged = _nudge_piece_fully_visible(page)
        cells_0 = _wait_for_gravity_tick(page, nudged)
        shape_0 = _normalize_shape(cells_0)
        cols_0 = _cols_set(cells_0)
        min_r_0 = _min_row(cells_0)

        # A: 0 -> 1 (CW)
        _gp_tap_button(page, 0)
        cells_1 = _occupied_cells(sample_board_grid_state(page))
        shape_1 = _normalize_shape(cells_1)
        cols_1 = _cols_set(cells_1)
        self.assertNotEqual(shape_1, shape_0)

        # X: 1 -> 0 (CCW; min_r_back == min_r_0 distinguishes State 0 from State 2 on I/S/Z)
        _gp_tap_button(page, 2)
        cells_back = _occupied_cells(sample_board_grid_state(page))
        self.assertEqual(_normalize_shape(cells_back), shape_0)
        self.assertEqual(_cols_set(cells_back), cols_0)
        self.assertEqual(_min_row(cells_back), min_r_0)

        # X: 0 -> 3 (CCW)
        _gp_tap_button(page, 2)
        cells_3 = _occupied_cells(sample_board_grid_state(page))
        shape_3 = _normalize_shape(cells_3)
        cols_3 = _cols_set(cells_3)
        self.assertNotEqual((shape_3, cols_3), (shape_1, cols_1))
        self.assertNotEqual((shape_3, cols_3), (shape_0, cols_0))

        # B: 3 -> 0 (CW) and 0 -> 1 (CW)
        _gp_tap_button(page, 1)
        cells_b0 = _occupied_cells(sample_board_grid_state(page))
        self.assertEqual(_normalize_shape(cells_b0), shape_0)
        self.assertEqual(_cols_set(cells_b0), cols_0)

        _gp_tap_button(page, 1)
        cells_b1 = _occupied_cells(sample_board_grid_state(page))
        self.assertEqual(_normalize_shape(cells_b1), shape_1)
        self.assertEqual(_cols_set(cells_b1), cols_1)
        self.assertPageClean(page)

    def test_tier1_04_hard_drop_and_soft_drop(self) -> None:
        """F3.5: D-Pad Up executes Hard Drop; D-Pad Down and Left Stick Y execute Soft Drop."""
        page = self.open_desktop_page(gamepad=True, rng_seed=42)
        _gp_connect(page)
        start_game(page, level=1)

        self.assertEqual(_count_bottom_cells(sample_board_grid_state(page), start_row=16), 0)

        _gp_tap_button(page, 12)  # D-Pad Up -> Hard Drop
        page.wait_for_timeout(130)

        score_after_hd = get_hud_stats(page)["score"]
        self.assertGreaterEqual(score_after_hd, 30)
        self.assertEqual(_count_bottom_cells(sample_board_grid_state(page), start_row=16), 4)
        self.assertIsNotNone(detect_top_spawn_piece(page))

        top_cells_0 = [c for c in _occupied_cells(sample_board_grid_state(page)) if c[0] <= 12]
        max_r_0 = _max_row(top_cells_0)

        _gp_set_button(page, 13, True)  # D-Pad Down -> Soft Drop
        page.wait_for_timeout(220)
        _gp_set_button(page, 13, False)
        _wait_frames(page, 2)

        score_after_dpad_sd = get_hud_stats(page)["score"]
        delta_1 = score_after_dpad_sd - score_after_hd
        self.assertGreater(delta_1, 0)
        self.assertLess(delta_1, 16)
        top_cells_1 = [c for c in _occupied_cells(sample_board_grid_state(page)) if c[0] <= 15]
        max_r_1 = _max_row(top_cells_1)
        self.assertGreaterEqual(max_r_1, max_r_0 + 3)

        _gp_set_axis(page, 1, 0.85)  # Left Stick Y down -> Soft Drop
        page.wait_for_timeout(220)
        _gp_set_axis(page, 1, 0.0)
        _wait_frames(page, 2)

        score_after_stick_sd = get_hud_stats(page)["score"]
        self.assertGreater(score_after_stick_sd, score_after_dpad_sd)
        top_cells_2 = [c for c in _occupied_cells(sample_board_grid_state(page)) if c[0] <= 16]
        self.assertGreaterEqual(_max_row(top_cells_2), max_r_1 + 3)
        self.assertPageClean(page)

    def test_tier1_05_hold_bumpers_and_menu_pause(self) -> None:
        """F3.5: LB/RB trigger Hold once per turn and Menu/Start toggles Pause overlay cleanly."""
        page = self.open_desktop_page(gamepad=True, rng_seed=42)
        _gp_connect(page)
        start_game(page, level=1)

        hold_0 = capture_element_image(page, SELECTORS["hold_canvas"])
        spawn_1 = detect_top_spawn_piece(page)
        self.assertIsNotNone(spawn_1)
        assert spawn_1 is not None

        _gp_tap_button(page, 4)  # LB
        hold_1 = capture_element_image(page, SELECTORS["hold_canvas"])
        spawn_2 = detect_top_spawn_piece(page)
        self.assertTrue(images_differ(hold_0, hold_1, min_diff_pixels=15))
        self.assertIsNotNone(spawn_2)
        assert spawn_2 is not None
        self.assertNotEqual(spawn_2["piece"], spawn_1["piece"])

        # RB on the same turn must not swap back.
        _gp_tap_button(page, 5)  # RB
        hold_guard = capture_element_image(page, SELECTORS["hold_canvas"])
        self.assertFalse(images_differ(hold_1, hold_guard, min_diff_pixels=10))

        # Hard Drop resets Hold availability.
        _gp_tap_button(page, 12)
        page.wait_for_timeout(140)
        hold_before_rb = capture_element_image(page, SELECTORS["hold_canvas"])
        score_before_pause = get_hud_stats(page)["score"]

        _gp_tap_button(page, 5)  # RB
        hold_after_rb = capture_element_image(page, SELECTORS["hold_canvas"])
        spawn_after_rb = detect_top_spawn_piece(page)
        self.assertTrue(images_differ(hold_before_rb, hold_after_rb, min_diff_pixels=15))
        self.assertIsNotNone(spawn_after_rb)
        assert spawn_after_rb is not None
        self.assertEqual(spawn_after_rb["piece"], spawn_1["piece"])

        _gp_tap_button(page, 9)  # Menu/Start -> Pause
        _wait_visible(page, SELECTORS["overlay_pause"], True)

        _gp_tap_button(page, 12)  # D-Pad Up ignored while paused
        self.assertEqual(get_hud_stats(page)["score"], score_before_pause)
        self.assertTrue(is_element_visible(page, SELECTORS["overlay_pause"]))

        _gp_tap_button(page, 9)  # Menu/Start -> Resume
        _wait_visible(page, SELECTORS["overlay_pause"], False)
        self.assertPageClean(page)

    # ------------------------------------------------------------------
    # Tier 2: Boundary & Edge Behavior (6 tests)
    # ------------------------------------------------------------------

    def test_tier2_01_left_stick_deadzone_030_and_das_arr(self) -> None:
        """F3.5: Left Stick X obeys 0.30 deadzone (±0.29 ignored; ±0.31 single step + DAS/ARR)."""
        page = self.open_desktop_page(gamepad=True, rng_seed=42)
        _gp_connect(page)
        start_game(page, level=1)

        cells_base = _nudge_piece_fully_visible(page)
        cols_base = _cols_set(cells_base)

        _gp_set_axis(page, 0, 0.29)
        page.wait_for_timeout(400)
        _gp_set_axis(page, 0, 0.0)
        _wait_frames(page, 2)
        self.assertEqual(_cols_set(_occupied_cells(sample_board_grid_state(page))), cols_base)

        _gp_set_axis(page, 0, -0.29)
        page.wait_for_timeout(400)
        _gp_set_axis(page, 0, 0.0)
        _wait_frames(page, 2)
        self.assertEqual(_cols_set(_occupied_cells(sample_board_grid_state(page))), cols_base)

        # Single step at +0.31 (< 160ms DAS)
        _gp_set_axis(page, 0, 0.31)
        _wait_frames(page, 2)
        _gp_set_axis(page, 0, 0.0)
        _wait_frames(page, 2)
        cols_step_r = _cols_set(_occupied_cells(sample_board_grid_state(page)))
        self.assertEqual(min(cols_step_r), min(cols_base) + 1)

        # Sustained +0.31 triggers DAS/ARR to right wall.
        _gp_set_axis(page, 0, 0.31)
        page.wait_for_timeout(420)
        _gp_set_axis(page, 0, 0.0)
        _wait_frames(page, 2)
        cols_wall_r = _cols_set(_occupied_cells(sample_board_grid_state(page)))
        self.assertEqual(max(cols_wall_r), 9)
        self.assertGreaterEqual(min(cols_wall_r), min(cols_step_r) + 2)

        # Single step at -0.31 (< 160ms DAS)
        _gp_set_axis(page, 0, -0.31)
        _wait_frames(page, 2)
        _gp_set_axis(page, 0, 0.0)
        _wait_frames(page, 2)
        cols_step_l = _cols_set(_occupied_cells(sample_board_grid_state(page)))
        self.assertEqual(min(cols_step_l), min(cols_wall_r) - 1)

        # Sustained -0.31 triggers DAS/ARR to left wall.
        _gp_set_axis(page, 0, -0.31)
        page.wait_for_timeout(480)
        _gp_set_axis(page, 0, 0.0)
        _wait_frames(page, 2)
        cols_wall_l = _cols_set(_occupied_cells(sample_board_grid_state(page)))
        self.assertEqual(min(cols_wall_l), 0)
        self.assertPageClean(page)

    def test_tier2_02_left_stick_y_up_strictly_ignored(self) -> None:
        """F3.5: Pushing Left Stick Y up (-0.95 / -1.0) never triggers Hard Drop."""
        page = self.open_desktop_page(gamepad=True, rng_seed=42)
        _gp_connect(page)
        start_game(page, level=1)

        for val in (-0.95, -1.0):
            _gp_set_axis(page, 1, val)
            page.wait_for_timeout(250)
            _gp_set_axis(page, 1, 0.0)
            _wait_frames(page, 2)
            grid_state = sample_board_grid_state(page)
            cells = _occupied_cells(grid_state)
            self.assertEqual(get_hud_stats(page)["score"], 0)
            self.assertEqual(_count_bottom_cells(grid_state, start_row=15), 0)
            self.assertLessEqual(_max_row(cells), 4)

        # Positive control: D-Pad Up Hard Drop works.
        _gp_tap_button(page, 12)
        page.wait_for_timeout(140)
        self.assertGreater(get_hud_stats(page)["score"], 0)
        self.assertEqual(_count_bottom_cells(sample_board_grid_state(page), start_row=16), 4)
        self.assertPageClean(page)

    def test_tier2_03_rising_edge_isolation_hard_drop_and_rotate(self) -> None:
        """F3.5: Holding D-Pad Up or A across 350ms+ fires strictly once until released and re-pressed."""
        page = self.open_desktop_page(gamepad=True, rng_seed=42)
        _gp_connect(page)
        start_game(page, level=1)

        _gp_set_button(page, 12, True)
        page.wait_for_timeout(350)
        grid_held = sample_board_grid_state(page)
        score_1 = get_hud_stats(page)["score"]
        self.assertEqual(_count_bottom_cells(grid_held, start_row=14), 4)
        self.assertGreater(score_1, 0)
        self.assertLessEqual(score_1, 42)
        self.assertFalse(is_element_visible(page, SELECTORS["overlay_gameover"]))

        _gp_set_button(page, 12, False)
        _wait_frames(page, 2)
        _gp_tap_button(page, 12)
        page.wait_for_timeout(140)
        self.assertEqual(_count_bottom_cells(sample_board_grid_state(page), start_row=14), 8)
        self.assertGreater(get_hud_stats(page)["score"], score_1)

        # Rotation rising-edge check (3 checkpoints defeat mod-4 coincidence).
        _ensure_non_o_active_piece(page)
        cells_0 = _nudge_piece_fully_visible(page)
        shape_0 = _normalize_shape(cells_0)

        _gp_set_button(page, 0, True)
        _wait_frames(page, 2)
        shape_t1 = _normalize_shape([c for c in _occupied_cells(sample_board_grid_state(page)) if c[0] <= 12])
        page.wait_for_timeout(180)
        shape_t2 = _normalize_shape([c for c in _occupied_cells(sample_board_grid_state(page)) if c[0] <= 12])
        page.wait_for_timeout(160)
        shape_t3 = _normalize_shape([c for c in _occupied_cells(sample_board_grid_state(page)) if c[0] <= 12])

        self.assertNotEqual(shape_t1, shape_0)
        self.assertEqual(shape_t1, shape_t2)
        self.assertEqual(shape_t2, shape_t3)

        _gp_set_button(page, 0, False)
        _wait_frames(page, 2)
        shape_rel = _normalize_shape([c for c in _occupied_cells(sample_board_grid_state(page)) if c[0] <= 12])
        self.assertEqual(shape_rel, shape_t1)

        _gp_tap_button(page, 0)
        shape_next = _normalize_shape([c for c in _occupied_cells(sample_board_grid_state(page)) if c[0] <= 12])
        self.assertNotEqual(shape_next, shape_t1)
        self.assertPageClean(page)

    def test_tier2_04_disconnect_and_non_standard_hid_fallback(self) -> None:
        """F3.5: Disconnect stops held stick and resets badges; non-standard HID shows generic badge safely."""
        page = self.open_desktop_page(gamepad=True, rng_seed=42)
        baseline_badge = _read_badge_state(page)
        page.locator(SELECTORS["btn_start_settings"]).click()
        _wait_visible(page, SELECTORS["modal_settings"], True)
        baseline_settings = _read_settings_gp_status(page)
        page.locator(SELECTORS["btn_close_settings"]).click()
        _wait_visible(page, SELECTORS["modal_settings"], False)

        start_game(page, level=1)
        _gp_connect(page)
        _wait_frames(page, 2)
        cols_before_stick = _cols_set(_nudge_piece_fully_visible(page))
        self.assertLessEqual(max(cols_before_stick), 7)

        # Hold stick right briefly (~32ms << 160ms DAS) then disconnect without releasing axes[0].
        _gp_set_axis(page, 0, 0.85)
        _wait_frames(page, 2)
        self.assertTrue(_gp_disconnect(page, 0))
        page.wait_for_timeout(350)

        cols_after_disc = _cols_set(_occupied_cells(sample_board_grid_state(page)))
        self.assertEqual(min(cols_after_disc), min(cols_before_stick) + 1)
        self.assertLess(max(cols_after_disc), 9)
        page.wait_for_timeout(200)
        self.assertEqual(_cols_set(_occupied_cells(sample_board_grid_state(page))), cols_after_disc)

        disc_badge = _read_badge_state(page)
        page.locator(SELECTORS["btn_settings"]).click()
        _wait_visible(page, SELECTORS["modal_settings"], True)
        disc_settings = _read_settings_gp_status(page)
        self._assert_disconnected_state(disc_badge, baseline_badge, disc_settings, baseline_settings)
        page.locator(SELECTORS["btn_close_settings"]).click()
        _wait_visible(page, SELECTORS["modal_settings"], False)
        if is_element_visible(page, SELECTORS["overlay_pause"]):
            page.locator(SELECTORS["btn_resume"]).click()
            _wait_visible(page, SELECTORS["overlay_pause"], False)

        score_before_hid = get_hud_stats(page)["score"]
        cols_before_hid = _cols_set(_occupied_cells(sample_board_grid_state(page)))

        # Atomically connect non-standard 10-axis HID gamepad with idle axes[9] = -1.0.
        page.evaluate(
            """() => {
              window.__e2eGamepad.connect({
                id: 'Generic USB Gamepad',
                mapping: '',
                buttonCount: 17,
                axisCount: 10
              });
              window.__e2eGamepad.setAxis(9, -1.0, 0);
            }"""
        )
        page.wait_for_timeout(350)

        hid_badge = _read_badge_state(page)
        self.assertTrue(hid_badge["visible"])
        self._assert_connected_text(hid_badge["text"], expect_xbox=False)
        self.assertEqual(get_hud_stats(page)["score"], score_before_hid)
        self.assertEqual(_count_bottom_cells(sample_board_grid_state(page), start_row=15), 0)
        self.assertEqual(_cols_set(_occupied_cells(sample_board_grid_state(page))), cols_before_hid)

        page.locator(SELECTORS["btn_settings"]).click()
        _wait_visible(page, SELECTORS["modal_settings"], True)
        self._assert_connected_text(_read_settings_gp_status(page), expect_xbox=False)
        self.assertPageClean(page)

    def test_tier2_05_overlay_start_and_resume_edge_isolation(self) -> None:
        """F3.5: A on Start and Menu/Start on Pause transition without frame-1 rotation, double-toggle, or Settings bypass."""
        chosen_seed = None
        grid_ref_spawn: Any = None
        page_ref: Page | None = None

        for candidate_seed in range(101, 115):
            probe_page = self.open_desktop_page(rng_seed=candidate_seed)
            start_game(probe_page, level=1)
            spawn = detect_top_spawn_piece(probe_page)
            if spawn is not None and spawn["piece"] != "O":
                chosen_seed = candidate_seed
                grid_ref_spawn = sample_board_grid_state(probe_page)["grid"]
                page_ref = probe_page
                break

        self.assertIsNotNone(chosen_seed)
        self.assertIsNotNone(page_ref)
        assert chosen_seed is not None and page_ref is not None

        page_gp = self.open_desktop_page(gamepad=True, rng_seed=chosen_seed)
        _gp_connect(page_gp)
        _wait_frames(page_gp, 2)

        # Settings modal over Start overlay must block gamepad A and Menu/Start.
        page_gp.locator(SELECTORS["btn_start_settings"]).click()
        _wait_visible(page_gp, SELECTORS["modal_settings"], True)
        _gp_set_button(page_gp, 0, True)
        page_gp.wait_for_timeout(80)
        _gp_set_button(page_gp, 0, False)
        _gp_set_button(page_gp, 9, True)
        page_gp.wait_for_timeout(80)
        _gp_set_button(page_gp, 9, False)
        _wait_frames(page_gp, 2)
        self.assertTrue(is_element_visible(page_gp, SELECTORS["modal_settings"]))
        self.assertTrue(is_element_visible(page_gp, SELECTORS["overlay_start"]))
        page_gp.locator(SELECTORS["btn_close_settings"]).click()
        _wait_visible(page_gp, SELECTORS["modal_settings"], False)

        # Hold A for 150ms on Start overlay -> starts cleanly in State 0 without rotating.
        _gp_set_button(page_gp, 0, True)
        page_gp.wait_for_timeout(150)
        _gp_set_button(page_gp, 0, False)
        _wait_frames(page_gp, 2)
        self.assertFalse(is_element_visible(page_gp, SELECTORS["overlay_start"]))
        self.assertEqual(sample_board_grid_state(page_gp)["grid"], grid_ref_spawn)

        cells_before_pause = _nudge_piece_fully_visible(page_gp)
        shape_before_pause = _normalize_shape(cells_before_pause)
        cols_before_pause = _cols_set(cells_before_pause)

        _gp_tap_button(page_gp, 9)  # Pause
        _wait_visible(page_gp, SELECTORS["overlay_pause"], True)
        page_gp.wait_for_timeout(200)
        self.assertTrue(is_element_visible(page_gp, SELECTORS["overlay_pause"]))

        # Settings modal over Pause overlay must block gamepad A and Menu/Start.
        page_gp.locator(SELECTORS["btn_pause_settings"]).click()
        _wait_visible(page_gp, SELECTORS["modal_settings"], True)
        _gp_set_button(page_gp, 0, True)
        page_gp.wait_for_timeout(80)
        _gp_set_button(page_gp, 0, False)
        _gp_set_button(page_gp, 9, True)
        page_gp.wait_for_timeout(80)
        _gp_set_button(page_gp, 9, False)
        _wait_frames(page_gp, 2)
        self.assertTrue(is_element_visible(page_gp, SELECTORS["modal_settings"]))
        self.assertTrue(is_element_visible(page_gp, SELECTORS["overlay_pause"]))
        page_gp.locator(SELECTORS["btn_close_settings"]).click()
        _wait_visible(page_gp, SELECTORS["modal_settings"], False)
        self.assertTrue(is_element_visible(page_gp, SELECTORS["overlay_pause"]))

        # A on Pause overlay must never rotate the paused piece.
        _gp_tap_button(page_gp, 0)
        if not is_element_visible(page_gp, SELECTORS["overlay_pause"]):
            _gp_tap_button(page_gp, 9)
            _wait_visible(page_gp, SELECTORS["overlay_pause"], True)

        # Hold Menu/Start for 150ms -> resumes cleanly once without toggling back to pause.
        _gp_set_button(page_gp, 9, True)
        page_gp.wait_for_timeout(150)
        _gp_set_button(page_gp, 9, False)
        _wait_frames(page_gp, 2)
        self.assertFalse(is_element_visible(page_gp, SELECTORS["overlay_pause"]))
        page_gp.wait_for_timeout(150)
        self.assertFalse(is_element_visible(page_gp, SELECTORS["overlay_pause"]))

        cells_after_resume = _occupied_cells(sample_board_grid_state(page_gp))
        self.assertEqual(_normalize_shape(cells_after_resume), shape_before_pause)
        self.assertEqual(_cols_set(cells_after_resume), cols_before_pause)

        _gp_tap_button(page_gp, 15)  # D-Pad Right works post-resume
        cols_post = _cols_set(_occupied_cells(sample_board_grid_state(page_gp)))
        self.assertGreater(min(cols_post), min(cols_before_pause))

        self.assertPageClean(page_ref)
        self.assertPageClean(page_gp)

    def test_tier2_06_soft_drop_y_threshold_045(self) -> None:
        """F3.5: Left Stick Y soft-drop threshold ignores 0.44 and activates at 0.46."""
        page = self.open_desktop_page(gamepad=True, rng_seed=42)
        _gp_connect(page)
        start_game(page, level=1)

        self.assertEqual(get_hud_stats(page)["score"], 0)

        _gp_set_axis(page, 1, 0.44)
        page.wait_for_timeout(280)
        _gp_set_axis(page, 1, 0.0)
        _wait_frames(page, 2)
        self.assertEqual(get_hud_stats(page)["score"], 0)
        max_r_before = _max_row(_occupied_cells(sample_board_grid_state(page)))

        _gp_set_axis(page, 1, 0.46)
        page.wait_for_timeout(280)
        _gp_set_axis(page, 1, 0.0)
        _wait_frames(page, 2)
        self.assertGreater(get_hud_stats(page)["score"], 0)
        max_r_after = _max_row(_occupied_cells(sample_board_grid_state(page)))
        self.assertGreaterEqual(max_r_after, max_r_before + 3)
        self.assertPageClean(page)


if __name__ == "__main__":
    unittest.main()

"""Area D E2E Tests: Mobile Touch Gestures, Sensitivity (1-10) & Viewport Locking.

Covers PROJECT.md features F2.8, F3.2, F3.3, F3.4, and F4.3 via strict
opaque-box Playwright browser interactions and Chromium CDP touch streams.
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
    get_layout_metrics,
    get_storage_data,
    images_differ,
    is_element_visible,
    sample_board_grid_state,
    set_range_value,
    start_game,
)


def _occupied_cells(grid_state: dict[str, Any]) -> list[tuple[int, int, str]]:
    cells: list[tuple[int, int, str]] = []
    for r, row in enumerate(grid_state["grid"]):
        for c, cell in enumerate(row):
            if cell is not None:
                cells.append((r, c, str(cell["piece"])))
    return cells


def _shape_signature(cells: list[tuple[int, int, str]]) -> frozenset[tuple[int, int]]:
    if not cells:
        return frozenset()
    min_r = min(r for r, _, _ in cells)
    min_c = min(c for _, c, _ in cells)
    return frozenset((r - min_r, c - min_c) for r, c, _ in cells)


def _bbox_dims(cells: list[tuple[int, int, str]]) -> tuple[int, int]:
    if not cells:
        return (0, 0)
    min_r = min(r for r, _, _ in cells)
    max_r = max(r for r, _, _ in cells)
    min_c = min(c for _, c, _ in cells)
    max_c = max(c for _, c, _ in cells)
    return (max_c - min_c + 1, max_r - min_r + 1)


def _cols_set(cells: list[tuple[int, int, str]]) -> set[int]:
    return {c for _, c, _ in cells}


def _bottom_rows_occupied(grid_state: dict[str, Any], start_row: int = 16) -> int:
    grid = grid_state["grid"]
    count = 0
    for r in range(start_row, len(grid)):
        for cell in grid[r]:
            if cell is not None:
                count += 1
    return count


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
        f"Timed out waiting for {selector!r} visibility={expected} "
        f"(require_interactive={require_interactive}); actual={actual}"
    )


def _wait_for_full_piece_visible(
    page: Page,
    *,
    min_cells: int = 4,
    timeout_ms: int = 1800,
) -> list[tuple[int, int, str]]:
    elapsed = 0
    step_ms = 35
    last_cells: list[tuple[int, int, str]] = []
    while elapsed <= timeout_ms:
        last_cells = _occupied_cells(sample_board_grid_state(page))
        if len(last_cells) >= min_cells:
            return last_cells
        page.wait_for_timeout(step_ms)
        elapsed += step_ms
    raise AssertionError(
        f"Timed out waiting for >= {min_cells} visible cells; last_cells={last_cells!r}"
    )


def _ensure_non_o_spawn(page: Page, driver: Any) -> str:
    spawn = detect_top_spawn_piece(page)
    if spawn is None:
        raise AssertionError("No active spawning piece detected at top of board.")
    if spawn["piece"] == "O":
        driver.tap_element(SELECTORS["hold_box"], hold_ms=10.0)
        _wait_frames(page, 2)
        spawn = detect_top_spawn_piece(page)
        if spawn is None or spawn["piece"] == "O":
            raise AssertionError(f"Expected non-O piece after Hold swap, got {spawn!r}")
    return str(spawn["piece"])


class TestAreaDMobileTouch(TetrisE2EBaseCase):
    """Tier 1 & Tier 2 E2E coverage for Mobile Touch, Sensitivity & Gesture Locking."""

    # ------------------------------------------------------------------
    # Tier 1: Core Functional Sanity (5 tests)
    # ------------------------------------------------------------------

    def test_tier1_01_mobile_viewports_layout_and_gesture_locking(self) -> None:
        """F3.4, F4.3: Mobile viewports keep >=80% board height, zero overflow, gesture lock, and reachable controls."""
        for viewport in ((390, 844), (360, 740)):
            with self.subTest(viewport=viewport):
                page = self.open_mobile_page(viewport=viewport, device_scale_factor=2.0, rng_seed=42)

                viewport_meta = page.evaluate(
                    "() => { const m = document.querySelector('meta[name=\"viewport\"]'); return m ? m.getAttribute('content') || '' : ''; }"
                )
                meta_lower = viewport_meta.lower()
                self.assertIn("width=device-width", meta_lower)
                self.assertIn("viewport-fit=cover", meta_lower)

                for phase in ("menu", "playing"):
                    if phase == "playing":
                        start_game(page, level=1)

                    metrics = get_layout_metrics(page)
                    self.assertTrue(
                        metrics["noHorizontalOverflow"],
                        f"Horizontal overflow at {viewport} ({phase}): {metrics}",
                    )
                    self.assertTrue(
                        metrics["noVerticalOverflow"],
                        f"Vertical overflow at {viewport} ({phase}): {metrics}",
                    )
                    self.assertGreaterEqual(
                        metrics["stageHeightRatio"],
                        0.80,
                        f"Expected .board-stage height >= 80% of innerHeight at {viewport} ({phase}): {metrics}",
                    )
                    self.assertEqual(metrics["touchAction"]["stage"], "none")
                    self.assertEqual(metrics["touchAction"]["canvas"], "none")

                    ob = metrics["overscrollBehavior"]
                    has_overscroll_lock = any(
                        entry is not None and entry["x"] == "none" and entry["y"] == "none"
                        for entry in (ob["html"], ob["body"], ob["stage"])
                    )
                    self.assertTrue(
                        has_overscroll_lock,
                        f"Expected overscroll-behavior: none on html/body/stage: {ob}",
                    )

                    us = metrics["userSelect"]
                    self.assertTrue(
                        us["stage"] == "none" or us["body"] == "none",
                        f"Expected user-select: none on stage or body: {us}",
                    )

                for key in ("hold_box", "btn_pause", "btn_settings", "btn_music", "btn_sfx"):
                    sel = SELECTORS[key]
                    self.assertTrue(
                        is_element_visible(page, sel, require_interactive=True),
                        f"Top bar control {sel} should be visible and interactive at {viewport}",
                    )
                    box = page.locator(sel).bounding_box()
                    self.assertIsNotNone(box, f"Missing bounding box for {sel}")
                    assert box is not None
                    self.assertGreater(box["width"], 0)
                    self.assertGreater(box["height"], 0)
                    self.assertGreaterEqual(box["x"], 0)
                    self.assertGreaterEqual(box["y"], 0)
                    self.assertLessEqual(box["x"] + box["width"], viewport[0] + 1)
                    self.assertLessEqual(box["y"] + box["height"], viewport[1] + 1)

                page.locator(SELECTORS["btn_music"]).click()
                page.locator(SELECTORS["btn_sfx"]).click()
                page.locator(SELECTORS["btn_pause"]).click()
                _wait_visible(page, SELECTORS["overlay_pause"], True)
                page.locator(SELECTORS["btn_resume"]).click()
                _wait_visible(page, SELECTORS["overlay_pause"], False)
                self.assertPageClean(page)

    def test_tier1_02_short_tap_rotates_active_piece_without_scoring(self) -> None:
        """F3.2: Short tap on #board-stage rotates active piece clockwise without awarding points."""
        page = self.open_mobile_page(rng_seed=42)
        driver = self.touch_driver(page)
        start_game(page, level=1)

        piece_type = _ensure_non_o_spawn(page, driver)
        before_cells = _wait_for_full_piece_visible(page)
        before_img = capture_element_image(page, SELECTORS["board_canvas"])
        before_w, before_h = _bbox_dims(before_cells)

        driver.tap_element(SELECTORS["board_stage"], hold_ms=10.0)
        _wait_frames(page, 2)

        after_img = capture_element_image(page, SELECTORS["board_canvas"])
        after_cells = _occupied_cells(sample_board_grid_state(page))
        after_w, after_h = _bbox_dims(after_cells)

        self.assertTrue(images_differ(before_img, after_img, min_diff_pixels=15))
        if piece_type == "I":
            self.assertEqual((before_w, before_h), (4, 1))
            self.assertEqual(after_w, 1)
            self.assertGreaterEqual(after_h, 3)
        else:
            self.assertTrue(
                before_w == 3 or before_h == 1,
                f"Unexpected state-0 dimensions {(before_w, before_h)} for {piece_type}",
            )
            self.assertLessEqual(after_w, 2)
            self.assertGreaterEqual(after_h, 2)

        self.assertEqual(get_hud_stats(page)["score"], 0)
        self.assertPageClean(page)

    def test_tier1_03_horizontal_drag_shifts_columns_without_rotation(self) -> None:
        """F3.2: Proportional lateral drag shifts piece right and left without triggering tap rotation."""
        page = self.open_mobile_page(rng_seed=42)
        driver = self.touch_driver(page)
        start_game(page, level=1)

        before_cells = _wait_for_full_piece_visible(page)
        before_cols = _cols_set(before_cells)
        before_shape = _shape_signature(before_cells)
        self.assertLessEqual(max(before_cols), 7)

        driver.drag_horizontal_on(SELECTORS["board_stage"], dx=80.0, steps=4)
        _wait_frames(page, 2)

        after_right_cells = _occupied_cells(sample_board_grid_state(page))
        after_right_cols = _cols_set(after_right_cells)
        self.assertGreater(min(after_right_cols), min(before_cols))
        self.assertGreater(max(after_right_cols), max(before_cols))
        self.assertEqual(_shape_signature(after_right_cells), before_shape)
        self.assertGreaterEqual(min(after_right_cols), 2)

        driver.drag_horizontal_on(SELECTORS["board_stage"], dx=-80.0, steps=4)
        _wait_frames(page, 2)

        after_left_cells = _occupied_cells(sample_board_grid_state(page))
        after_left_cols = _cols_set(after_left_cells)
        self.assertLess(min(after_left_cols), min(after_right_cols))
        self.assertLess(max(after_left_cols), max(after_right_cols))
        self.assertEqual(_shape_signature(after_left_cells), before_shape)

        self.assertEqual(get_hud_stats(page)["score"], 0)
        self.assertPageClean(page)

    def test_tier1_04_soft_drop_drag_vs_hard_drop_flick(self) -> None:
        """F3.2: Slow downward drag triggers Soft Drop without locking; fast flick triggers Hard Drop."""
        page = self.open_mobile_page(rng_seed=42)
        driver = self.touch_driver(page)
        start_game(page, level=1)

        driver.soft_drop_on(SELECTORS["board_stage"], total_dy=70.0, steps=10, step_sleep_ms=10.0)
        _wait_frames(page, 2)

        hud_soft = get_hud_stats(page)
        grid_soft = sample_board_grid_state(page)
        self.assertGreaterEqual(hud_soft["score"], 1)
        self.assertLessEqual(hud_soft["score"], 15)
        self.assertEqual(_bottom_rows_occupied(grid_soft, start_row=16), 0)

        driver.flick_down_on(SELECTORS["board_stage"], dy=95.0, hold_after_flick=False)
        page.wait_for_timeout(160)

        hud_hard = get_hud_stats(page)
        grid_hard = sample_board_grid_state(page)
        self.assertGreaterEqual(hud_hard["score"], hud_soft["score"] + 14)
        self.assertGreater(_bottom_rows_occupied(grid_hard, start_row=16), 0)
        self.assertIsNotNone(detect_top_spawn_piece(page))
        self.assertPageClean(page)

    def test_tier1_05_hold_via_hold_box_tap_and_upward_swipe(self) -> None:
        """F3.2, F2.5: Hold works via #hold-box tap and upward swipe with once-per-turn guard."""
        page = self.open_mobile_page(rng_seed=42)
        driver = self.touch_driver(page)
        start_game(page, level=1)

        spawn_1 = detect_top_spawn_piece(page)
        self.assertIsNotNone(spawn_1)
        assert spawn_1 is not None
        hold_img_0 = capture_element_image(page, SELECTORS["hold_canvas"])

        driver.tap_element(SELECTORS["hold_box"], hold_ms=10.0)
        page.wait_for_timeout(120)
        _wait_frames(page, 2)

        hold_img_1 = capture_element_image(page, SELECTORS["hold_canvas"])
        spawn_2 = detect_top_spawn_piece(page)
        self.assertIsNotNone(spawn_2)
        assert spawn_2 is not None
        self.assertTrue(images_differ(hold_img_0, hold_img_1, min_diff_pixels=15))
        self.assertNotEqual(spawn_2["piece"], spawn_1["piece"])

        # Second Hold before locking must be ignored (once-per-turn guard).
        driver.swipe_up_hold_on(SELECTORS["board_stage"], total_dy=-72.0)
        _wait_frames(page, 2)
        hold_img_guard = capture_element_image(page, SELECTORS["hold_canvas"])
        spawn_guard = detect_top_spawn_piece(page)
        self.assertFalse(images_differ(hold_img_1, hold_img_guard, min_diff_pixels=10))
        self.assertIsNotNone(spawn_guard)
        assert spawn_guard is not None
        self.assertEqual(spawn_guard["piece"], spawn_2["piece"])

        # Lock piece #2 via Hard Drop flick to reset Hold availability.
        driver.flick_down_on(SELECTORS["board_stage"], dy=95.0, hold_after_flick=False)
        page.wait_for_timeout(160)

        hold_before_swipe = capture_element_image(page, SELECTORS["hold_canvas"])
        spawn_3 = detect_top_spawn_piece(page)
        self.assertIsNotNone(spawn_3)
        assert spawn_3 is not None

        driver.swipe_up_hold_on(SELECTORS["board_stage"], total_dy=-72.0)
        _wait_frames(page, 2)

        hold_after_swipe = capture_element_image(page, SELECTORS["hold_canvas"])
        spawn_after_swipe = detect_top_spawn_piece(page)
        self.assertTrue(images_differ(hold_before_swipe, hold_after_swipe, min_diff_pixels=15))
        self.assertIsNotNone(spawn_after_swipe)
        assert spawn_after_swipe is not None
        self.assertEqual(spawn_after_swipe["piece"], spawn_1["piece"])
        self.assertPageClean(page)

    # ------------------------------------------------------------------
    # Tier 2: Boundary & Edge Behavior (7 tests)
    # ------------------------------------------------------------------

    def test_tier2_01_sensitivity_scaling_1_vs_10_and_reload_persistence(self) -> None:
        """F3.3, F2.8: Sensitivity slider 1 vs 10 scales lateral drag threshold and persists across reload."""
        page = self.open_mobile_page(rng_seed=17)

        page.locator(SELECTORS["btn_start_settings"]).click()
        _wait_visible(page, SELECTORS["modal_settings"], True)
        self.assertEqual(page.locator(SELECTORS["sensitivity_slider"]).input_value(), "5")
        self.assertEqual(page.locator(SELECTORS["sensitivity_value"]).inner_text().strip(), "5")

        set_range_value(page, SELECTORS["sensitivity_slider"], 1)
        self.assertEqual(page.locator(SELECTORS["sensitivity_value"]).inner_text().strip(), "1")
        storage_s1 = get_storage_data(page)
        self.assertIsNotNone(storage_s1)
        assert storage_s1 is not None
        self.assertEqual(storage_s1["touchSensitivity"], 1)

        page.locator(SELECTORS["btn_close_settings"]).click()
        _wait_visible(page, SELECTORS["modal_settings"], False)
        page.reload(wait_until="load")

        page.locator(SELECTORS["btn_start_settings"]).click()
        _wait_visible(page, SELECTORS["modal_settings"], True)
        self.assertEqual(page.locator(SELECTORS["sensitivity_slider"]).input_value(), "1")
        self.assertEqual(page.locator(SELECTORS["sensitivity_value"]).inner_text().strip(), "1")
        self.assertEqual(get_storage_data(page)["touchSensitivity"], 1)  # type: ignore[index]
        page.locator(SELECTORS["btn_close_settings"]).click()
        _wait_visible(page, SELECTORS["modal_settings"], False)

        driver = self.touch_driver(page)
        start_game(page, level=1)
        before_s1 = _wait_for_full_piece_visible(page)
        cols_before_s1 = _cols_set(before_s1)
        shape_s1 = _shape_signature(before_s1)

        driver.drag_horizontal_on(SELECTORS["board_stage"], dx=24.0, steps=4)
        _wait_frames(page, 2)
        after_s1 = _occupied_cells(sample_board_grid_state(page))
        self.assertEqual(_cols_set(after_s1), cols_before_s1)
        self.assertEqual(_shape_signature(after_s1), shape_s1)

        page.locator(SELECTORS["btn_settings"]).click()
        _wait_visible(page, SELECTORS["modal_settings"], True)
        set_range_value(page, SELECTORS["sensitivity_slider"], 10)
        self.assertEqual(page.locator(SELECTORS["sensitivity_value"]).inner_text().strip(), "10")
        self.assertEqual(get_storage_data(page)["touchSensitivity"], 10)  # type: ignore[index]
        page.locator(SELECTORS["btn_close_settings"]).click()
        _wait_visible(page, SELECTORS["modal_settings"], False)

        page.reload(wait_until="load")
        self.assertEqual(get_storage_data(page)["touchSensitivity"], 10)  # type: ignore[index]

        start_game(page, level=1)
        before_s10 = _wait_for_full_piece_visible(page)
        cols_before_s10 = _cols_set(before_s10)
        shape_s10 = _shape_signature(before_s10)
        self.assertLessEqual(max(cols_before_s10), 8)

        driver.drag_horizontal_on(SELECTORS["board_stage"], dx=24.0, steps=4)
        _wait_frames(page, 2)
        after_s10 = _occupied_cells(sample_board_grid_state(page))
        self.assertGreater(min(_cols_set(after_s10)), min(cols_before_s10))
        self.assertEqual(_shape_signature(after_s10), shape_s10)
        self.assertPageClean(page)

    def test_tier2_02_post_flick_pointer_lock_prevents_second_drop_or_drag(self) -> None:
        """F3.2: Continuation movement after a downward flick does not move or drop piece #2."""
        ctrl_page = self.open_mobile_page(rng_seed=101)
        ctrl_driver = self.touch_driver(ctrl_page)
        start_game(ctrl_page, level=1)
        ctrl_driver.flick_down_on(SELECTORS["board_stage"], dy=95.0, hold_after_flick=False)
        ctrl_page.wait_for_timeout(160)
        ctrl_score = get_hud_stats(ctrl_page)["score"]
        ctrl_piece2 = detect_top_spawn_piece(ctrl_page)
        self.assertIsNotNone(ctrl_piece2)
        assert ctrl_piece2 is not None
        self.assertGreater(ctrl_score, 0)

        test_page = self.open_mobile_page(rng_seed=101)
        test_driver = self.touch_driver(test_page)
        start_game(test_page, level=1)
        test_driver.flick_down_on(SELECTORS["board_stage"], dy=95.0, hold_after_flick=True)
        test_page.wait_for_timeout(160)
        test_score = get_hud_stats(test_page)["score"]
        test_piece2 = detect_top_spawn_piece(test_page)
        self.assertIsNotNone(test_piece2)
        assert test_piece2 is not None

        self.assertEqual(test_score, ctrl_score)
        self.assertEqual(
            {c for _, c in test_piece2["cells"]},
            {c for _, c in ctrl_piece2["cells"]},
        )

        # Fresh touch after touchEnd release must operate normally on piece #2.
        before_fresh = _wait_for_full_piece_visible(test_page, min_cells=4)
        before_cols = _cols_set(before_fresh)
        dx_fresh = 60.0 if max(before_cols) <= 7 else -60.0
        test_driver.drag_horizontal_on(SELECTORS["board_stage"], dx=dx_fresh, steps=4)
        _wait_frames(test_page, 2)
        after_fresh = _occupied_cells(sample_board_grid_state(test_page))
        # Filter to top half (rows 0..10) so locked bottom piece #1 does not interfere.
        after_top_cols = {c for r, c, _ in after_fresh if r <= 10}
        before_top_cols = {c for r, c, _ in before_fresh if r <= 10}
        self.assertNotEqual(after_top_cols, before_top_cols)

        self.assertPageClean(ctrl_page)
        self.assertPageClean(test_page)

    def test_tier2_03_soft_drop_vs_flick_discrimination_across_extremes(self) -> None:
        """F3.2, F3.3: Slow Soft Drop never misfires as Hard Drop, and Flick triggers Hard Drop at S=10 and S=1."""
        for sens in (10, 1):
            with self.subTest(touchSensitivity=sens):
                page = self.open_mobile_page(
                    rng_seed=42,
                    storage_seed={"touchSensitivity": sens},
                )
                driver = self.touch_driver(page)
                start_game(page, level=1)

                driver.soft_drop_on(
                    SELECTORS["board_stage"],
                    total_dy=70.0,
                    steps=10,
                    step_sleep_ms=10.0,
                )
                _wait_frames(page, 2)

                hud_soft = get_hud_stats(page)
                grid_soft = sample_board_grid_state(page)
                self.assertGreaterEqual(hud_soft["score"], 1)
                self.assertLessEqual(hud_soft["score"], 15)
                self.assertEqual(_bottom_rows_occupied(grid_soft, start_row=16), 0)

                driver.flick_down_on(SELECTORS["board_stage"], dy=95.0, hold_after_flick=False)
                page.wait_for_timeout(160)

                hud_hard = get_hud_stats(page)
                grid_hard = sample_board_grid_state(page)
                self.assertGreaterEqual(hud_hard["score"], hud_soft["score"] + 14)
                self.assertGreater(_bottom_rows_occupied(grid_hard, start_row=16), 0)
                self.assertIsNotNone(detect_top_spawn_piece(page))
                self.assertPageClean(page)

    def test_tier2_04_pointercancel_abort_safety_and_recovery(self) -> None:
        """F3.2: touchCancel / pointercancel aborts cleanly with zero phantom actions and full recovery."""
        page = self.open_mobile_page(rng_seed=42)
        driver = self.touch_driver(page)
        start_game(page, level=1)

        before_cells = _wait_for_full_piece_visible(page)
        before_cols = _cols_set(before_cells)
        before_shape = _shape_signature(before_cells)
        before_hold = capture_element_image(page, SELECTORS["hold_canvas"])

        # Short displacement cancel inside tap threshold.
        driver.cancel_touch_on(SELECTORS["board_stage"], dx=4.0, dy=4.0)
        _wait_frames(page, 2)

        after_short_cancel = _occupied_cells(sample_board_grid_state(page))
        self.assertEqual(_shape_signature(after_short_cancel), before_shape)
        self.assertEqual(_cols_set(after_short_cancel), before_cols)
        self.assertEqual(get_hud_stats(page)["score"], 0)
        self.assertEqual(_bottom_rows_occupied(sample_board_grid_state(page), start_row=16), 0)
        self.assertFalse(
            images_differ(
                before_hold,
                capture_element_image(page, SELECTORS["hold_canvas"]),
                min_diff_pixels=10,
            )
        )

        # Larger downward drag cancel (must pass empty touchPoints to touchCancel).
        # Note: live incremental softDropStep may run during pointermove before cancel,
        # so verify cancel aborts without Hard Drop/lock, rotation, column drift, or Hold.
        pts = driver.get_stage_points(SELECTORS["board_stage"])
        sx, sy = pts["down_start"]
        driver._send("touchStart", [{"x": sx, "y": sy, "id": 0}])
        driver._send("touchMove", [{"x": sx, "y": sy + 35.0, "id": 0}])
        driver._send("touchCancel", [])
        _wait_frames(page, 2)

        after_cells = _occupied_cells(sample_board_grid_state(page))
        self.assertEqual(_shape_signature(after_cells), before_shape)
        self.assertEqual(_cols_set(after_cells), before_cols)
        self.assertLessEqual(get_hud_stats(page)["score"], 6)
        self.assertEqual(_bottom_rows_occupied(sample_board_grid_state(page), start_row=16), 0)
        self.assertFalse(
            images_differ(
                before_hold,
                capture_element_image(page, SELECTORS["hold_canvas"]),
                min_diff_pixels=10,
            )
        )

        # Subsequent normal gestures recover cleanly.
        driver.drag_horizontal_on(SELECTORS["board_stage"], dx=60.0, steps=4)
        _wait_frames(page, 2)
        shifted_cells = _occupied_cells(sample_board_grid_state(page))
        self.assertGreater(min(_cols_set(shifted_cells)), min(before_cols))

        if shifted_cells[0][2] == "O":
            driver.tap_element(SELECTORS["hold_box"], hold_ms=10.0)
            page.wait_for_timeout(120)
            _wait_frames(page, 2)
            pre_tap_cells = _wait_for_full_piece_visible(page)
        else:
            pre_tap_cells = shifted_cells
        pre_tap_shape = _shape_signature(pre_tap_cells)
        driver.tap_element(SELECTORS["board_stage"], hold_ms=10.0)
        _wait_frames(page, 2)
        post_tap_cells = _occupied_cells(sample_board_grid_state(page))
        self.assertNotEqual(_shape_signature(post_tap_cells), pre_tap_shape)

        driver.flick_down_on(SELECTORS["board_stage"], dy=95.0, hold_after_flick=False)
        page.wait_for_timeout(160)
        self.assertGreater(get_hud_stats(page)["score"], 0)
        self.assertPageClean(page)

    def test_tier2_05_tiny_360x640_mobile_viewport_budget_and_touch(self) -> None:
        """F3.4, F4.3: Tiny 360x640 mobile screen preserves >=80% board budget, zero overflow, and playable touch."""
        viewport = (360, 640)
        page = self.open_mobile_page(viewport=viewport, device_scale_factor=2.0, rng_seed=42)
        driver = self.touch_driver(page)

        for phase in ("menu", "playing"):
            if phase == "playing":
                start_game(page, level=1)
            metrics = get_layout_metrics(page)
            self.assertGreaterEqual(metrics["stageHeightRatio"], 0.80)
            self.assertTrue(metrics["noHorizontalOverflow"])
            self.assertTrue(metrics["noVerticalOverflow"])
            self.assertEqual(metrics["touchAction"]["stage"], "none")
            self.assertEqual(metrics["touchAction"]["canvas"], "none")

        board_box = page.locator(SELECTORS["board_canvas"]).bounding_box()
        self.assertIsNotNone(board_box)
        assert board_box is not None

        for key in ("hold_box", "btn_pause", "btn_settings", "btn_music", "btn_sfx"):
            sel = SELECTORS[key]
            self.assertTrue(is_element_visible(page, sel, require_interactive=True))
            box = page.locator(sel).bounding_box()
            self.assertIsNotNone(box)
            assert box is not None
            self.assertGreaterEqual(box["x"], 0)
            self.assertGreaterEqual(box["y"], 0)
            self.assertLessEqual(box["x"] + box["width"], viewport[0] + 1)
            self.assertLessEqual(box["y"] + box["height"], viewport[1] + 1)
            self.assertLessEqual(box["y"] + box["height"], board_box["y"] + 2)

        driver.tap_element(SELECTORS["board_stage"], hold_ms=10.0)
        _wait_frames(page, 2)
        driver.flick_down_on(SELECTORS["board_stage"], dy=95.0, hold_after_flick=False)
        page.wait_for_timeout(160)
        self.assertGreaterEqual(get_hud_stats(page)["score"], 14)
        self.assertPageClean(page)

    def test_tier2_06_settings_from_playing_pauses_and_returns_to_pause_on_mobile(self) -> None:
        """F4.3, F3.3: Opening Settings from play pauses gravity, and closing returns strictly to #overlay-pause."""
        page = self.open_mobile_page(viewport=(360, 740), device_scale_factor=2.0, rng_seed=42)
        driver = self.touch_driver(page)
        start_game(page, level=5)

        self.assertTrue(is_element_visible(page, SELECTORS["btn_settings"], require_interactive=True))
        page.locator(SELECTORS["btn_settings"]).click()
        _wait_visible(page, SELECTORS["modal_settings"], True)

        img1 = capture_element_image(page, SELECTORS["board_canvas"])
        page.wait_for_timeout(650)
        img2 = capture_element_image(page, SELECTORS["board_canvas"])
        self.assertFalse(images_differ(img1, img2, min_diff_pixels=1))

        page.locator(SELECTORS["btn_close_settings"]).click()
        _wait_visible(page, SELECTORS["modal_settings"], False)
        _wait_visible(page, SELECTORS["overlay_pause"], True)

        page.wait_for_timeout(400)
        self.assertTrue(is_element_visible(page, SELECTORS["overlay_pause"]))

        page.locator(SELECTORS["btn_resume"]).click()
        _wait_visible(page, SELECTORS["overlay_pause"], False)

        driver.flick_down_on(SELECTORS["board_stage"], dy=95.0, hold_after_flick=False)
        page.wait_for_timeout(160)
        self.assertGreater(get_hud_stats(page)["score"], 0)
        self.assertPageClean(page)

    def test_tier2_07_multitouch_isolation_secondary_pointer_ignored(self) -> None:
        """F3.2: Secondary simultaneous touch neither aborts primary drag nor injects phantom drops."""
        page = self.open_mobile_page(rng_seed=42)
        driver = self.touch_driver(page)
        start_game(page, level=1)

        before_cells = _wait_for_full_piece_visible(page)
        before_cols = _cols_set(before_cells)
        before_shape = _shape_signature(before_cells)
        self.assertLessEqual(max(before_cols), 7)

        pts = driver.get_stage_points(SELECTORS["board_stage"])
        stage_box = page.locator(SELECTORS["board_stage"]).bounding_box()
        self.assertIsNotNone(stage_box)
        assert stage_box is not None

        x0, y0 = pts["drag_right"]
        x1, y1 = pts["drag_left"][0], pts["down_start"][1]
        dx_mid = min(40.0, float(stage_box["width"]) * 0.20)
        dx_end = min(90.0, float(stage_box["width"]) * 0.45)

        driver._send("touchStart", [{"x": x0, "y": y0, "id": 0}])
        driver._send("touchMove", [{"x": x0 + dx_mid, "y": y0, "id": 0}])
        driver._send("touchStart", [{"x": x1, "y": y1, "id": 1}])
        driver._send("touchMove", [{"x": x1, "y": y1 + 10.0, "id": 1}])
        driver._send("touchMove", [{"x": x1, "y": y1 + 95.0, "id": 1}])
        # Lift only secondary touch id=1 while keeping primary id=0 alive.
        driver._send("touchEnd", [{"x": x1, "y": y1 + 95.0, "id": 1}])
        driver._send("touchMove", [{"x": x0 + dx_end, "y": y0, "id": 0}])
        driver._send("touchEnd", [])
        _wait_frames(page, 2)

        after_cells = _occupied_cells(sample_board_grid_state(page))
        self.assertEqual(get_hud_stats(page)["score"], 0)
        self.assertEqual(_bottom_rows_occupied(sample_board_grid_state(page), start_row=16), 0)
        self.assertGreater(min(_cols_set(after_cells)), min(before_cols))
        self.assertEqual(_shape_signature(after_cells), before_shape)

        driver.flick_down_on(SELECTORS["board_stage"], dy=95.0, hold_after_flick=False)
        page.wait_for_timeout(160)
        self.assertGreater(get_hud_stats(page)["score"], 0)
        self.assertPageClean(page)


if __name__ == "__main__":
    unittest.main()

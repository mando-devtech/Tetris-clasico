"""Area B E2E tests: Core Tetris gameplay, SRS, lock delay, 7-bag, scoring, and persistence.

Covers PROJECT.md features F2.1 through F2.8 via strictly opaque-box Playwright
checks using DOM HUD stats, localStorage inspection, keyboard actions, and
Pillow pixel/grid sampling of #board-canvas, #hold-canvas, and #next-canvas.
"""

from __future__ import annotations

import math
import unittest
from typing import Any

from tests.e2e.harness import (
    PIECE_PALETTE,
    SELECTORS,
    TetrisE2EBaseCase,
    capture_element_image,
    count_diff_pixels,
    detect_top_spawn_piece,
    get_hud_stats,
    get_layout_metrics,
    get_storage_data,
    images_differ,
    is_element_visible,
    sample_board_grid_state,
    start_game,
)


def _rotate_cw(matrix: list[list[int]]) -> list[list[int]]:
    n = len(matrix)
    return [[matrix[n - 1 - c][r] for c in range(n)] for r in range(n)]


def _build_rotations(base: list[list[int]]) -> list[list[list[int]]]:
    s0 = base
    s1 = _rotate_cw(s0)
    s2 = _rotate_cw(s1)
    s3 = _rotate_cw(s2)
    return [s0, s1, s2, s3]


_SHAPES: dict[str, list[list[list[int]]]] = {
    "I": _build_rotations([[0, 0, 0, 0], [1, 1, 1, 1], [0, 0, 0, 0], [0, 0, 0, 0]]),
    "O": _build_rotations([[1, 1], [1, 1]]),
    "T": _build_rotations([[0, 1, 0], [1, 1, 1], [0, 0, 0]]),
    "S": _build_rotations([[0, 1, 1], [1, 1, 0], [0, 0, 0]]),
    "Z": _build_rotations([[1, 1, 0], [0, 1, 1], [0, 0, 0]]),
    "J": _build_rotations([[1, 0, 0], [1, 1, 1], [0, 0, 0]]),
    "L": _build_rotations([[0, 0, 1], [1, 1, 1], [0, 0, 0]]),
}

_SPAWN_COL: dict[str, int] = {
    "I": 3,
    "O": 4,
    "T": 3,
    "S": 3,
    "Z": 3,
    "J": 3,
    "L": 3,
}

_SPAWN_FOOTPRINTS: dict[frozenset[tuple[int, int]], str] = {}
for _ptype, _mats in _SHAPES.items():
    _mat0 = _mats[0]
    _coords = [
        (r, c)
        for r in range(len(_mat0))
        for c in range(len(_mat0[r]))
        if _mat0[r][c] == 1
    ]
    _min_r = min(r for r, _ in _coords)
    _min_c = min(c for _, c in _coords)
    _SPAWN_FOOTPRINTS[frozenset((r - _min_r, c - _min_c) for r, c in _coords)] = _ptype

_ROT_STATES: dict[str, list[dict[str, Any]]] = {}
for _ptype, _mats in _SHAPES.items():
    _states: list[dict[str, Any]] = []
    _seen_norms: set[frozenset[tuple[int, int]]] = set()
    for _rot_idx, _mat in enumerate(_mats):
        _coords = [
            (r, c)
            for r in range(len(_mat))
            for c in range(len(_mat[r]))
            if _mat[r][c] == 1
        ]
        _min_r = min(r for r, _ in _coords)
        _min_c = min(c for _, c in _coords)
        _norm = tuple(sorted((r - _min_r, c - _min_c) for r, c in _coords))
        _norm_set = frozenset(_norm)
        if _norm_set in _seen_norms:
            continue
        _seen_norms.add(_norm_set)
        _height = max(r for r, _ in _norm) + 1
        _width = max(c for _, c in _norm) + 1
        _states.append(
            {
                "rot_idx": _rot_idx,
                "cells": _norm,
                "height": _height,
                "width": _width,
                "spawn_left_col": _SPAWN_COL[_ptype] + _min_c,
            }
        )
    _ROT_STATES[_ptype] = _states


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


def _crop_canvas_content(page, selector: str, img):
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


def _estimate_bg_rgb(img) -> tuple[int, int, int]:
    pixels = list(img.getdata())
    if not pixels:
        return (0, 0, 0)
    stride = max(1, len(pixels) // 4000)
    sampled = pixels[::stride]
    sampled.sort(key=lambda rgb: max(rgb))
    dark_slice = sampled[: max(1, int(len(sampled) * 0.4))]
    mid = len(dark_slice) // 2
    return (
        sorted(p[0] for p in dark_slice)[mid],
        sorted(p[1] for p in dark_slice)[mid],
        sorted(p[2] for p in dark_slice)[mid],
    )


def _count_bright_pixels(
    img,
    *,
    bg_rgb: tuple[int, int, int] | None = None,
    channel_threshold: int = 115,
    lum_threshold: int = 85,
    dist_threshold: int = 75,
) -> int:
    if bg_rgb is None:
        bg_rgb = _estimate_bg_rgb(img)
    br, bg, bb = bg_rgb
    dist_sq_min = dist_threshold * dist_threshold
    count = 0
    for r, g, b in img.getdata():
        if max(r, g, b) < channel_threshold:
            continue
        lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
        if lum < lum_threshold:
            continue
        dist_sq = (r - br) ** 2 + (g - bg) ** 2 + (b - bb) ** 2
        if dist_sq >= dist_sq_min:
            count += 1
    return count


def _closest_piece_from_rgb(rgb: tuple[float, float, float], candidates: tuple[str, ...]) -> str:
    r, g, b = rgb
    return min(
        candidates,
        key=lambda k: (r - PIECE_PALETTE[k][0]) ** 2
        + (g - PIECE_PALETTE[k][1]) ** 2
        + (b - PIECE_PALETTE[k][2]) ** 2,
    )


def _evaluate_board_features(board: list[list[bool]]) -> dict[str, float]:
    rows = len(board)
    cols = len(board[0])
    row_trans = 0
    for r in range(rows):
        prev = True
        for c in range(cols):
            cur = board[r][c]
            if cur != prev:
                row_trans += 1
            prev = cur
        if not prev:
            row_trans += 1

    col_trans = 0
    holes = 0
    wells = 0
    for c in range(cols):
        prev = False
        seen_block = False
        well_depth = 0
        for r in range(rows):
            cur = board[r][c]
            if cur != prev:
                col_trans += 1
            prev = cur
            if cur:
                seen_block = True
                well_depth = 0
            else:
                if seen_block:
                    holes += 1
                left_filled = True if c == 0 else board[r][c - 1]
                right_filled = True if c == cols - 1 else board[r][c + 1]
                if left_filled and right_filled:
                    well_depth += 1
                    wells += well_depth
                else:
                    well_depth = 0
        if not prev:
            col_trans += 1

    return {
        "row_trans": float(row_trans),
        "col_trans": float(col_trans),
        "holes": float(holes),
        "wells": float(wells),
    }


def _best_opaque_placement(board: list[list[bool]], piece: str) -> dict[str, Any]:
    rows = len(board)
    cols = len(board[0])
    best: dict[str, Any] | None = None

    for state in _ROT_STATES[piece]:
        cells = state["cells"]
        height = state["height"]
        width = state["width"]
        for target_col in range(cols - width + 1):
            base_row = -1
            for candidate_row in range(rows - height + 1):
                if any(board[candidate_row + dr][target_col + dc] for dr, dc in cells):
                    break
                base_row = candidate_row
            if base_row < 0:
                continue

            next_board = [row[:] for row in board]
            for dr, dc in cells:
                next_board[base_row + dr][target_col + dc] = True

            cleared_rows = [r for r in range(rows) if all(next_board[r])]
            cleared = len(cleared_rows)
            if cleared:
                kept = [next_board[r] for r in range(rows) if r not in cleared_rows]
                next_board = [[False] * cols for _ in range(cleared)] + kept

            landing_height = float(rows) - (base_row + (height - 1) / 2.0)
            feats = _evaluate_board_features(next_board)
            score = (
                200.0 * cleared
                - 4.50 * landing_height
                - 3.22 * feats["row_trans"]
                - 9.35 * feats["col_trans"]
                - 7.90 * feats["holes"]
                - 3.39 * feats["wells"]
            )
            candidate = {
                "score": score,
                "cleared": cleared,
                "holes": int(feats["holes"]),
                "rot_idx": state["rot_idx"],
                "target_col": target_col,
                "spawn_left_col": state["spawn_left_col"],
            }
            if best is None or candidate["score"] > best["score"]:
                best = candidate

    if best is None:
        return {
            "score": -1e9,
            "cleared": 0,
            "holes": 999,
            "rot_idx": 0,
            "target_col": _SPAWN_COL[piece],
            "spawn_left_col": _SPAWN_COL[piece],
        }
    return best


class TestAreaBGameplay(TetrisE2EBaseCase):
    """Area B tests covering Marathon gameplay, SRS, lock delay, 7-bag, scoring, and persistence."""

    def _identify_spawn_piece(self, page, top_rows: int = 3) -> dict[str, Any]:
        sampled = sample_board_grid_state(page, selector=SELECTORS["board_canvas"])
        grid = sampled["grid"]
        cells: list[tuple[int, int]] = []
        rgbs: list[list[int]] = []
        for r in range(min(top_rows, len(grid))):
            for c, cell in enumerate(grid[r]):
                if cell is not None:
                    cells.append((r, c))
                    rgbs.append(cell["rgb"])

        if not cells:
            fallback = detect_top_spawn_piece(page, selector=SELECTORS["board_canvas"], top_rows=4)
            if fallback is None:
                raise AssertionError("No active spawn piece detected in top rows.")
            return fallback

        avg_rgb = (
            sum(rgb[0] for rgb in rgbs) / len(rgbs),
            sum(rgb[1] for rgb in rgbs) / len(rgbs),
            sum(rgb[2] for rgb in rgbs) / len(rgbs),
        )

        if len(cells) == 4:
            min_r = min(r for r, _ in cells)
            min_c = min(c for _, c in cells)
            norm = frozenset((r - min_r, c - min_c) for r, c in cells)
            if norm in _SPAWN_FOOTPRINTS:
                return {"piece": _SPAWN_FOOTPRINTS[norm], "cells": [[r, c] for r, c in cells]}

        distinct_rows = {r for r, _ in cells}
        if len(distinct_rows) == 1:
            cols = tuple(sorted(c for _, c in cells))
            if cols == (3, 4, 5, 6):
                return {"piece": "I", "cells": [[r, c] for r, c in cells]}
            if cols == (3, 4):
                return {"piece": "S", "cells": [[r, c] for r, c in cells]}
            if cols == (4, 5):
                return {
                    "piece": _closest_piece_from_rgb(avg_rgb, ("O", "Z")),
                    "cells": [[r, c] for r, c in cells],
                }
            if cols == (3, 4, 5):
                return {
                    "piece": _closest_piece_from_rgb(avg_rgb, ("T", "J", "L")),
                    "cells": [[r, c] for r, c in cells],
                }

        piece = _closest_piece_from_rgb(avg_rgb, tuple(PIECE_PALETTE.keys()))
        return {"piece": piece, "cells": [[r, c] for r, c in cells]}

    def _occupied_cells(self, page, *, max_row: int = 19) -> list[tuple[int, int]]:
        grid = sample_board_grid_state(page, selector=SELECTORS["board_canvas"])["grid"]
        return [
            (r, c)
            for r in range(min(max_row + 1, len(grid)))
            for c, cell in enumerate(grid[r])
            if cell is not None
        ]

    # ------------------------------------------------------------------
    # Tier 1: Core Functional Sanity (5 tests)
    # ------------------------------------------------------------------

    def test_tier1_initial_level_selection_transfers_to_hud(self) -> None:
        page = self.open_desktop_page(self.server.base_url)
        _wait_raf(page, 2)
        self.assertTrue(is_element_visible(page, SELECTORS["overlay_start"], require_interactive=True))
        self.assertEqual(int(page.locator(SELECTORS["start_level_value"]).inner_text().strip()), 1)

        for _ in range(8):
            page.locator(SELECTORS["btn_level_up"]).click()
        self.assertEqual(int(page.locator(SELECTORS["start_level_value"]).inner_text().strip()), 9)

        for _ in range(2):
            page.locator(SELECTORS["btn_level_down"]).click()
        self.assertEqual(int(page.locator(SELECTORS["start_level_value"]).inner_text().strip()), 7)

        page.locator(SELECTORS["btn_play"]).click()
        _wait_until_hidden(page, SELECTORS["overlay_start"])
        _wait_raf(page, 2)

        hud = get_hud_stats(page)
        self.assertEqual(hud["level"], 7)
        self.assertEqual(hud["score"], 0)
        self.assertEqual(hud["lines"], 0)
        self.assertPageClean(page)

    def test_tier1_playfield_aspect_active_ghost_and_next_queue(self) -> None:
        page = self.open_desktop_page(self.server.base_url)
        start_game(page, level=1)

        metrics = get_layout_metrics(page)
        self.assertGreater(metrics["canvasCssW"], 0)
        self.assertGreater(metrics["canvasCssH"], 0)
        self.assertLessEqual(abs(metrics["canvasCssW"] * 2 - metrics["canvasCssH"]), 1.0)
        self.assertLessEqual(abs(metrics["canvasBufferW"] * 2 - metrics["canvasBufferH"]), 2)
        self.assertTrue(metrics["hidpiBufferExact"], f"Unexpected HiDPI buffer sizing: {metrics!r}")
        self.assertEqual(metrics["canvasCssW"] % 10, 0)
        self.assertEqual(metrics["canvasCssH"] % 20, 0)
        self.assertGreaterEqual(metrics["canvasCssW"] / 10, 12)

        spawn = detect_top_spawn_piece(page)
        self.assertIsNotNone(spawn)
        self.assertIn(spawn["piece"], PIECE_PALETTE)
        self.assertGreaterEqual(len(spawn["cells"]), 2)
        self.assertLessEqual(len(spawn["cells"]), 4)

        # Ghost piece verification: bottom rows must be empty of solid blocks, yet shift pixels on ArrowLeft x3.
        grid_before = sample_board_grid_state(page)["grid"]
        self.assertEqual(
            sum(1 for r in range(16, 20) for cell in grid_before[r] if cell is not None),
            0,
            "Ghost piece must remain translucent and not read as solid occupied blocks.",
        )

        img_before = _crop_canvas_content(
            page, SELECTORS["board_canvas"], capture_element_image(page, SELECTORS["board_canvas"])
        )
        for _ in range(3):
            page.keyboard.press("ArrowLeft")
        _wait_raf(page, 2)

        grid_after = sample_board_grid_state(page)["grid"]
        self.assertEqual(
            sum(1 for r in range(16, 20) for cell in grid_after[r] if cell is not None),
            0,
        )
        img_after = _crop_canvas_content(
            page, SELECTORS["board_canvas"], capture_element_image(page, SELECTORS["board_canvas"])
        )
        w, h = img_before.size
        bottom_box = (0, int(0.85 * h), w, int(0.99 * h))
        mid_box = (0, int(0.40 * h), w, int(0.65 * h))
        bottom_diff = count_diff_pixels(
            img_before.crop(bottom_box), img_after.crop(bottom_box), channel_threshold=10
        )
        mid_diff = count_diff_pixels(
            img_before.crop(mid_box), img_after.crop(mid_box), channel_threshold=10
        )
        self.assertGreaterEqual(
            bottom_diff,
            30,
            f"Expected translucent Ghost pixels to shift at bottom on ArrowLeft x3 (got {bottom_diff}).",
        )
        self.assertGreater(
            bottom_diff,
            mid_diff * 2,
            f"Bottom Ghost diff ({bottom_diff}) should dominate empty mid-board diff ({mid_diff}).",
        )

        # 3-piece Next Queue verification along major axis.
        next_before = _crop_canvas_content(
            page, SELECTORS["next_canvas"], capture_element_image(page, SELECTORS["next_canvas"])
        )
        nw, nh = next_before.size
        next_bg = _estimate_bg_rgb(next_before)
        for slot_idx in range(3):
            if nh >= nw:
                y0 = (nh * slot_idx) // 3
                y1 = (nh * (slot_idx + 1)) // 3
                slot_img = next_before.crop((0, y0, nw, y1))
            else:
                x0 = (nw * slot_idx) // 3
                x1 = (nw * (slot_idx + 1)) // 3
                slot_img = next_before.crop((x0, 0, x1, nh))
            bright = _count_bright_pixels(slot_img, bg_rgb=next_bg)
            self.assertGreaterEqual(
                bright,
                15,
                f"Expected Next queue slot {slot_idx} to render a piece (>= 15 bright px, got {bright}).",
            )

        page.keyboard.press("Space")
        _wait_raf(page, 2)
        next_after = _crop_canvas_content(
            page, SELECTORS["next_canvas"], capture_element_image(page, SELECTORS["next_canvas"])
        )
        self.assertTrue(
            images_differ(next_before, next_after, channel_threshold=10, min_diff_pixels=20),
            "Locking active piece must advance #next-canvas.",
        )
        self.assertPageClean(page)

    def test_tier1_soft_drop_and_hard_drop_scoring_and_pixels(self) -> None:
        page = self.open_desktop_page(self.server.base_url)
        start_game(page, level=1)

        spawn1 = detect_top_spawn_piece(page)
        self.assertIsNotNone(spawn1)
        max_r1 = max(r for r, _ in spawn1["cells"])
        board_start = capture_element_image(page, SELECTORS["board_canvas"])

        for _ in range(4):
            page.keyboard.press("ArrowLeft")
        page.keyboard.press("Space")
        _wait_raf(page, 2)

        score_after_hard = get_hud_stats(page)["score"]
        self.assertEqual(score_after_hard, 2 * (19 - max_r1))
        board_after_hard = capture_element_image(page, SELECTORS["board_canvas"])
        self.assertTrue(images_differ(board_start, board_after_hard, channel_threshold=8, min_diff_pixels=15))
        grid_after_hard = sample_board_grid_state(page)["grid"]
        self.assertTrue(any(cell is not None for cell in grid_after_hard[19]))

        # Soft Drop Piece 2
        s_pre_soft = get_hud_stats(page)["score"]
        board_p2 = capture_element_image(page, SELECTORS["board_canvas"])
        page.keyboard.down("ArrowDown")
        page.wait_for_timeout(280)
        page.keyboard.up("ArrowDown")
        _wait_raf(page, 2)

        s_post_soft = get_hud_stats(page)["score"]
        soft_gain = s_post_soft - s_pre_soft
        self.assertGreaterEqual(soft_gain, 1)
        self.assertLessEqual(soft_gain, 12)
        board_post_soft = capture_element_image(page, SELECTORS["board_canvas"])
        self.assertTrue(images_differ(board_p2, board_post_soft, channel_threshold=8, min_diff_pixels=20))

        active_cells_p2 = self._occupied_cells(page, max_row=17)
        self.assertGreater(len(active_cells_p2), 0)
        max_r_soft = max(r for r, _ in active_cells_p2)
        self.assertGreaterEqual(max_r_soft, 1)
        self.assertLessEqual(max_r_soft, 15)

        page.keyboard.press("Space")
        _wait_raf(page, 2)
        hard_gain = get_hud_stats(page)["score"] - s_post_soft
        self.assertGreaterEqual(hard_gain, 10)
        self.assertEqual(hard_gain % 2, 0)
        self.assertLessEqual(hard_gain, 2 * (19 - max_r_soft))
        self.assertPageClean(page)

    def test_tier1_hold_piece_initial_populate_and_swap(self) -> None:
        page = self.open_desktop_page(self.server.base_url)
        start_game(page, level=1)

        hold_blank = _crop_canvas_content(
            page, SELECTORS["hold_canvas"], capture_element_image(page, SELECTORS["hold_canvas"])
        )
        self.assertEqual(
            _count_bright_pixels(hold_blank),
            0,
            "#hold-canvas should start empty before first Hold.",
        )

        piece1 = self._identify_spawn_piece(page)["piece"]
        page.keyboard.press("KeyC")
        _wait_raf(page, 2)

        hold_after_1 = _crop_canvas_content(
            page, SELECTORS["hold_canvas"], capture_element_image(page, SELECTORS["hold_canvas"])
        )
        self.assertTrue(
            images_differ(hold_blank, hold_after_1, channel_threshold=10, min_diff_pixels=25),
            "First Hold via KeyC must render held piece into #hold-canvas.",
        )
        piece2 = self._identify_spawn_piece(page)["piece"]
        self.assertNotEqual(piece2, piece1)

        # Lock piece2 so canHold resets, then test Hold swap via clicking #hold-box.
        page.keyboard.press("Space")
        _wait_raf(page, 2)
        piece3 = self._identify_spawn_piece(page)["piece"]
        self.assertNotEqual(piece3, piece1)
        hold_undimmed = _crop_canvas_content(
            page, SELECTORS["hold_canvas"], capture_element_image(page, SELECTORS["hold_canvas"])
        )

        self.assertTrue(is_element_visible(page, SELECTORS["hold_box"], require_interactive=True))
        page.locator(SELECTORS["hold_box"]).click()
        _wait_raf(page, 2)

        self.assertEqual(
            self._identify_spawn_piece(page)["piece"],
            piece1,
            "Clicking #hold-box must swap original piece1 back into active play.",
        )
        hold_after_2 = _crop_canvas_content(
            page, SELECTORS["hold_canvas"], capture_element_image(page, SELECTORS["hold_canvas"])
        )
        self.assertTrue(
            images_differ(hold_undimmed, hold_after_2, channel_threshold=10, min_diff_pixels=25),
            "#hold-canvas must update to show piece3 after second Hold.",
        )
        self.assertPageClean(page)

    def test_tier1_top_out_game_over_and_storage_persistence(self) -> None:
        page = self.open_desktop_page(self.server.base_url)
        start_game(page, level=2)

        for _ in range(35):
            if is_element_visible(page, SELECTORS["overlay_gameover"]):
                break
            page.keyboard.press("Space")
            page.wait_for_timeout(45)
        _wait_raf(page, 2)

        self.assertTrue(
            is_element_visible(page, SELECTORS["overlay_gameover"], require_interactive=True),
            "Stacking to top must trigger #overlay-gameover.",
        )
        hud = get_hud_stats(page)
        final_score = int(page.locator(SELECTORS["final_score_value"]).inner_text().strip())
        final_level = int(page.locator(SELECTORS["final_level_value"]).inner_text().strip())
        final_lines = int(page.locator(SELECTORS["final_lines_value"]).inner_text().strip())

        self.assertGreater(final_score, 0)
        self.assertEqual(final_score, hud["score"])
        self.assertEqual(final_level, 2)
        self.assertEqual(final_level, hud["level"])
        self.assertEqual(final_lines, 0)
        self.assertEqual(final_lines, hud["lines"])

        self.assertEqual(hud["best_score"], final_score)
        self.assertEqual(hud["best_level"], 2)
        self.assertEqual(hud["best_lines"], 0)

        stored = get_storage_data(page)
        self.assertIsInstance(stored, dict)
        self.assertEqual(stored.get("bestScore"), final_score)
        self.assertEqual(stored.get("bestLevel"), 2)
        self.assertEqual(stored.get("bestLines"), 0)

        page.reload(wait_until="load")
        _wait_raf(page, 2)
        reloaded_hud = get_hud_stats(page)
        self.assertEqual(reloaded_hud["best_score"], final_score)
        self.assertEqual(reloaded_hud["best_level"], 2)
        self.assertEqual(reloaded_hud["best_lines"], 0)
        reloaded_storage = get_storage_data(page)
        self.assertIsInstance(reloaded_storage, dict)
        self.assertEqual(reloaded_storage.get("bestScore"), final_score)
        self.assertPageClean(page)

    # ------------------------------------------------------------------
    # Tier 2: Boundary & Edge Behavior (7 tests)
    # ------------------------------------------------------------------

    def test_tier2_level_picker_clamping_boundaries(self) -> None:
        page = self.open_desktop_page(self.server.base_url)
        _wait_raf(page, 2)
        self.assertTrue(is_element_visible(page, SELECTORS["overlay_start"], require_interactive=True))
        self.assertEqual(int(page.locator(SELECTORS["start_level_value"]).inner_text().strip()), 1)

        btn_down = page.locator(SELECTORS["btn_level_down"])
        if btn_down.is_enabled():
            btn_down.click()
        self.assertEqual(int(page.locator(SELECTORS["start_level_value"]).inner_text().strip()), 1)

        btn_up = page.locator(SELECTORS["btn_level_up"])
        for _ in range(14):
            btn_up.click()
        self.assertEqual(int(page.locator(SELECTORS["start_level_value"]).inner_text().strip()), 15)

        if btn_up.is_enabled():
            btn_up.click()
        self.assertEqual(int(page.locator(SELECTORS["start_level_value"]).inner_text().strip()), 15)

        btn_down.click()
        self.assertEqual(int(page.locator(SELECTORS["start_level_value"]).inner_text().strip()), 14)
        btn_up.click()
        self.assertEqual(int(page.locator(SELECTORS["start_level_value"]).inner_text().strip()), 15)

        page.locator(SELECTORS["btn_play"]).click()
        _wait_until_hidden(page, SELECTORS["overlay_start"])
        _wait_raf(page, 2)
        self.assertEqual(get_hud_stats(page)["level"], 15)
        self.assertPageClean(page)

    def test_tier2_double_hold_blocked_within_single_drop(self) -> None:
        page = self.open_desktop_page(self.server.base_url)
        start_game(page, level=1)

        piece1 = self._identify_spawn_piece(page)["piece"]
        page.keyboard.press("KeyC")
        _wait_raf(page, 2)
        piece2 = self._identify_spawn_piece(page)["piece"]
        self.assertNotEqual(piece2, piece1)

        hold_1 = capture_element_image(page, SELECTORS["hold_canvas"])
        next_1 = capture_element_image(page, SELECTORS["next_canvas"])

        # Second Hold within the same turn must be ignored.
        page.keyboard.press("KeyC")
        _wait_raf(page, 2)
        hold_2 = capture_element_image(page, SELECTORS["hold_canvas"])
        next_2 = capture_element_image(page, SELECTORS["next_canvas"])

        self.assertEqual(self._identify_spawn_piece(page)["piece"], piece2)
        self.assertFalse(images_differ(hold_1, hold_2, channel_threshold=8, min_diff_pixels=5))
        self.assertFalse(images_differ(next_1, next_2, channel_threshold=8, min_diff_pixels=5))

        # After locking piece2, Hold must work again.
        page.keyboard.press("Space")
        _wait_raf(page, 2)
        page.keyboard.press("KeyC")
        _wait_raf(page, 2)
        self.assertEqual(self._identify_spawn_piece(page)["piece"], piece1)
        self.assertPageClean(page)

    def test_tier2_extended_placement_lock_delay(self) -> None:
        page = self.open_desktop_page(self.server.base_url)
        start_game(page, level=1)

        page.keyboard.down("ArrowDown")
        page.wait_for_timeout(560)
        page.keyboard.up("ArrowDown")
        _wait_raf(page, 2)

        cells = self._occupied_cells(page)
        max_r = max(r for r, _ in cells) if cells else -1
        for _ in range(10):
            if max_r >= 18:
                break
            page.keyboard.down("ArrowDown")
            page.wait_for_timeout(60)
            page.keyboard.up("ArrowDown")
            _wait_raf(page, 1)
            cells = self._occupied_cells(page)
            max_r = max(r for r, _ in cells) if cells else -1

        self.assertGreaterEqual(max_r, 18, f"Expected active piece near bottom, got max_r={max_r}")
        if max_r == 18:
            page.keyboard.down("ArrowDown")
            page.wait_for_timeout(70)
            page.keyboard.up("ArrowDown")

        # 4 lateral nudges spaced 180 ms apart (720 ms total > 500 ms lock delay).
        for key in ("ArrowRight", "ArrowLeft", "ArrowRight", "ArrowLeft"):
            page.keyboard.press(key)
            page.wait_for_timeout(180)

        self.assertIsNone(
            detect_top_spawn_piece(page),
            "Lateral moves during lock delay must reset lock timer and prevent premature lock.",
        )
        cells_grounded = self._occupied_cells(page)
        self.assertEqual(max(r for r, _ in cells_grounded), 19)

        # Wait idle > 500 ms so piece locks and next piece spawns at top.
        page.wait_for_timeout(750)
        _wait_raf(page, 2)
        self.assertIsNotNone(
            detect_top_spawn_piece(page),
            "Piece must lock after 500 ms idle and spawn the next piece at top.",
        )
        grid_final = sample_board_grid_state(page)["grid"]
        self.assertTrue(any(cell is not None for cell in grid_final[19]))
        self.assertPageClean(page)

    def test_tier2_gravity_level1_vs_level15_contrast(self) -> None:
        page_l1 = self.open_desktop_page(self.server.base_url)
        start_game(page_l1, level=1)
        page_l1.wait_for_timeout(500)
        cells_l1 = self._occupied_cells(page_l1)
        self.assertGreater(len(cells_l1), 0)
        max_row_l1 = max(r for r, _ in cells_l1)
        self.assertLessEqual(max_row_l1, 2, f"Level 1 fell unexpectedly far in 500 ms: max_row={max_row_l1}")

        page_l15 = self.open_desktop_page(self.server.base_url)
        start_game(page_l15, level=15)
        page_l15.wait_for_timeout(350)
        cells_l15 = self._occupied_cells(page_l15)
        self.assertGreater(len(cells_l15), 0)
        max_row_l15 = max(r for r, _ in cells_l15)
        self.assertGreaterEqual(max_row_l15, 15, f"Level 15 should reach bottom in 350 ms: max_row={max_row_l15}")

        self.assertGreaterEqual(max_row_l15 - max_row_l1, 12)
        self.assertPageClean(page_l1)
        self.assertPageClean(page_l15)

    def test_tier2_srs_wall_kicks_left_and_right_walls(self) -> None:
        page = self.open_desktop_page(self.server.base_url)
        start_game(page, level=1)

        # Left-wall CW kick (1 -> 2 at col 0)
        if self._identify_spawn_piece(page)["piece"] == "O":
            page.keyboard.press("KeyC")
            _wait_raf(page, 2)

        page.keyboard.down("ArrowDown")
        page.wait_for_timeout(140)
        page.keyboard.up("ArrowDown")
        _wait_raf(page, 2)

        page.keyboard.press("ArrowUp")
        for _ in range(6):
            page.keyboard.press("ArrowLeft")
        _wait_raf(page, 2)

        left_pre = self._occupied_cells(page, max_row=15)
        self.assertEqual(len(left_pre), 4)
        self.assertEqual(min(c for _, c in left_pre), 0)
        self.assertLessEqual(max(c for _, c in left_pre) - min(c for _, c in left_pre) + 1, 2)

        page.keyboard.press("ArrowUp")
        _wait_raf(page, 2)
        left_kicked = self._occupied_cells(page, max_row=15)
        self.assertEqual(len(left_kicked), 4)
        self.assertTrue(all(0 <= c <= 9 for _, c in left_kicked))
        self.assertEqual(min(c for _, c in left_kicked), 0)
        self.assertGreaterEqual(max(c for _, c in left_kicked) - min(c for _, c in left_kicked) + 1, 3)

        # Lock Piece 1, then test Right-wall CCW kick (3 -> 2 at col 9)
        page.keyboard.press("Space")
        _wait_raf(page, 2)

        if self._identify_spawn_piece(page)["piece"] == "O":
            page.keyboard.press("KeyC")
            _wait_raf(page, 2)

        page.keyboard.down("ArrowDown")
        page.wait_for_timeout(140)
        page.keyboard.up("ArrowDown")
        _wait_raf(page, 2)

        page.keyboard.press("KeyZ")
        for _ in range(6):
            page.keyboard.press("ArrowRight")
        _wait_raf(page, 2)

        right_pre = self._occupied_cells(page, max_row=15)
        self.assertEqual(len(right_pre), 4)
        self.assertEqual(max(c for _, c in right_pre), 9)
        self.assertLessEqual(max(c for _, c in right_pre) - min(c for _, c in right_pre) + 1, 2)

        page.keyboard.press("KeyZ")
        _wait_raf(page, 2)
        right_kicked = self._occupied_cells(page, max_row=15)
        self.assertEqual(len(right_kicked), 4)
        self.assertTrue(all(0 <= c <= 9 for _, c in right_kicked))
        self.assertEqual(max(c for _, c in right_kicked), 9)
        self.assertGreaterEqual(max(c for _, c in right_kicked) - min(c for _, c in right_kicked) + 1, 3)
        self.assertPageClean(page)

    def test_tier2_seven_bag_distribution_and_drought_bounds(self) -> None:
        page = self.open_desktop_page(self.server.base_url)
        start_game(page, level=1)

        lanes = (-4, -1, 2, 4)
        spawns: list[str] = []
        for idx in range(14):
            info = self._identify_spawn_piece(page)
            spawns.append(info["piece"])
            shift = lanes[idx % len(lanes)]
            key = "ArrowLeft" if shift < 0 else "ArrowRight"
            for _ in range(abs(shift)):
                page.keyboard.press(key)
            page.keyboard.press("Space")
            _wait_raf(page, 2)

        self.assertEqual(len(spawns), 14)
        self.assertEqual(set(spawns[:7]), set(PIECE_PALETTE.keys()), f"Bag 1 missing pieces: {spawns[:7]}")
        self.assertEqual(set(spawns[7:14]), set(PIECE_PALETTE.keys()), f"Bag 2 missing pieces: {spawns[7:14]}")

        max_run = 1
        cur_run = 1
        for i in range(1, len(spawns)):
            if spawns[i] == spawns[i - 1]:
                cur_run += 1
                max_run = max(max_run, cur_run)
            else:
                cur_run = 1
        self.assertLessEqual(max_run, 2, f"Consecutive identical piece run exceeded 2: {spawns}")
        self.assertPageClean(page)

    def test_tier2_opaque_line_clear_and_restart_boundary(self) -> None:
        page = self.open_desktop_page(self.server.base_url)
        start_game(page, level=1)

        hold_piece: str | None = None
        cleared_verified = False

        for _ in range(20):
            hud_before = get_hud_stats(page)
            if hud_before["lines"] >= 1:
                cleared_verified = True
                break

            grid = sample_board_grid_state(page)["grid"]
            board = [
                [(grid[r][c] is not None) if r >= 3 else False for c in range(10)]
                for r in range(20)
            ]
            active_piece = self._identify_spawn_piece(page)["piece"]
            best_active = _best_opaque_placement(board, active_piece)

            if hold_piece is None and best_active["cleared"] == 0 and best_active["holes"] > 0:
                page.keyboard.press("KeyC")
                _wait_raf(page, 2)
                hold_piece = active_piece
                active_piece = self._identify_spawn_piece(page)["piece"]
                best_active = _best_opaque_placement(board, active_piece)
            elif hold_piece is not None:
                best_hold = _best_opaque_placement(board, hold_piece)
                if (best_hold["cleared"] > 0 and best_active["cleared"] == 0) or (
                    best_hold["score"] > best_active["score"] + 15.0
                ):
                    page.keyboard.press("KeyC")
                    _wait_raf(page, 2)
                    active_piece, hold_piece = hold_piece, active_piece
                    best_active = best_hold

            for _ in range(best_active["rot_idx"]):
                page.keyboard.press("ArrowUp")
            dx = best_active["target_col"] - best_active["spawn_left_col"]
            move_key = "ArrowLeft" if dx < 0 else "ArrowRight"
            for _ in range(abs(dx)):
                page.keyboard.press(move_key)
            page.keyboard.press("Space")
            _wait_raf(page, 2)

            hud_after = get_hud_stats(page)
            if hud_after["lines"] >= 1:
                self.assertGreaterEqual(hud_after["score"] - hud_before["score"], 100)
                cleared_verified = True
                break

        self.assertTrue(cleared_verified, "Opaque placement solver expected to clear >= 1 line within 20 drops.")
        hud_cleared = get_hud_stats(page)
        self.assertGreaterEqual(hud_cleared["lines"], 1)
        self.assertGreaterEqual(hud_cleared["score"], 100)

        # Top out and verify #btn-play-again reset preserves best records.
        for _ in range(35):
            if is_element_visible(page, SELECTORS["overlay_gameover"]):
                break
            page.keyboard.press("Space")
            page.wait_for_timeout(45)
        _wait_raf(page, 2)

        self.assertTrue(is_element_visible(page, SELECTORS["overlay_gameover"], require_interactive=True))
        best_hud = get_hud_stats(page)
        best_score = best_hud["best_score"]
        best_lines = best_hud["best_lines"]
        self.assertGreaterEqual(best_score, 100)
        self.assertGreaterEqual(best_lines, 1)

        page.locator(SELECTORS["btn_play_again"]).click()
        _wait_until_hidden(page, SELECTORS["overlay_gameover"])
        _wait_raf(page, 2)

        hud_restarted = get_hud_stats(page)
        self.assertEqual(hud_restarted["score"], 0)
        self.assertEqual(hud_restarted["lines"], 0)
        self.assertEqual(hud_restarted["level"], 1)
        self.assertEqual(hud_restarted["best_score"], best_score)
        self.assertEqual(hud_restarted["best_lines"], best_lines)
        grid_clean = sample_board_grid_state(page)["grid"]
        self.assertEqual(
            sum(1 for r in range(3, 20) for cell in grid_clean[r] if cell is not None),
            0,
            "Rows 3..19 must be empty after Game Over restart.",
        )

        # Verify Pause -> #btn-restart clears active board & live counters while preserving bestScore.
        page.keyboard.press("Space")
        _wait_raf(page, 2)
        page.keyboard.press("Space")
        _wait_raf(page, 2)
        self.assertGreater(get_hud_stats(page)["score"], 0)

        page.locator(SELECTORS["btn_pause"]).click()
        _wait_raf(page, 1)
        self.assertTrue(is_element_visible(page, SELECTORS["overlay_pause"], require_interactive=True))
        page.locator(SELECTORS["btn_restart"]).click()
        _wait_until_hidden(page, SELECTORS["overlay_pause"])
        _wait_raf(page, 2)

        hud_pause_restart = get_hud_stats(page)
        self.assertEqual(hud_pause_restart["score"], 0)
        self.assertEqual(hud_pause_restart["lines"], 0)
        self.assertEqual(hud_pause_restart["best_score"], best_score)
        self.assertEqual(hud_pause_restart["best_lines"], best_lines)
        grid_pause_clean = sample_board_grid_state(page)["grid"]
        self.assertEqual(
            sum(1 for r in range(3, 20) for cell in grid_pause_clean[r] if cell is not None),
            0,
            "Rows 3..19 must be empty after Pause restart.",
        )
        self.assertPageClean(page)


if __name__ == "__main__":
    unittest.main()

"""Area F E2E Tests: HiDPI Visuals, FX, Modals, Web Audio, Spanish UI & README.

Covers PROJECT.md features F2.8, F4.1, F4.2, F4.3, F5.1, F5.2, and F6.1 via
strict opaque-box Playwright interactions, Pillow pixel inspection, and DOM/storage checks.
"""

from __future__ import annotations

import math
import re
import unittest
from pathlib import Path
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
    start_game,
)

_AUDIO_EXT_RE = re.compile(r"\.(mp3|wav|ogg|oga|opus|m4a|aac|flac|webm)(\?.*)?$", re.IGNORECASE)


def _parse_int_text(raw: str, label: str) -> int:
    cleaned = re.sub(r"[\s.,\u00a0]", "", raw.strip())
    if not cleaned or not re.fullmatch(r"-?\d+", cleaned):
        raise ValueError(f"Expected integer text for {label}, got {raw!r}")
    return int(cleaned)


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


def _max_occupied_row(grid_state: dict[str, Any]) -> int:
    max_r = -1
    for r, row in enumerate(grid_state["grid"]):
        if any(cell is not None for cell in row):
            max_r = r
    return max_r


def _bottom_rows_occupied(grid_state: dict[str, Any], start_row: int = 16) -> int:
    count = 0
    for r in range(start_row, len(grid_state["grid"])):
        for cell in grid_state["grid"][r]:
            if cell is not None:
                count += 1
    return count


def _hard_drop_until_gameover(page: Page, max_drops: int = 55) -> None:
    for _ in range(max_drops):
        if is_element_visible(page, SELECTORS["overlay_gameover"]):
            return
        page.keyboard.press("Space")
        page.wait_for_timeout(25)
    _wait_visible(page, SELECTORS["overlay_gameover"], True, timeout_ms=1500)


def _read_toggle_state(page: Page, selector: str) -> dict[str, Any]:
    state = page.evaluate(
        """(sel) => {
          const el = document.querySelector(sel);
          if (!el) return null;
          const tag = el.tagName.toLowerCase();
          const type = (el.getAttribute('type') || '').toLowerCase();
          const role = (el.getAttribute('role') || '').toLowerCase();
          const ariaPressed = el.getAttribute('aria-pressed');
          const ariaChecked = el.getAttribute('aria-checked');
          const checked = (tag === 'input' && type === 'checkbox') ? Boolean(el.checked) : null;
          let boolHint = null;
          if (checked !== null) boolHint = checked;
          else if (ariaChecked === 'true' || ariaChecked === 'false') boolHint = ariaChecked === 'true';
          else if (ariaPressed === 'true' || ariaPressed === 'false') boolHint = ariaPressed === 'true';
          return {
            tag,
            type,
            role,
            checked,
            ariaChecked,
            ariaPressed,
            boolHint,
            ariaLabel: el.getAttribute('aria-label') || '',
            title: el.getAttribute('title') || '',
            text: (el.innerText || el.textContent || '').trim(),
            markup: el.innerHTML || ''
          };
        }""",
        selector,
    )
    if state is None:
        raise AssertionError(f"Toggle selector {selector!r} not found in DOM.")
    return state


def _click_toggle(page: Page, selector: str) -> None:
    if is_element_visible(page, selector, require_interactive=True):
        page.locator(selector).click()
        return

    label_info = page.evaluate(
        """(sel) => {
          const el = document.querySelector(sel);
          if (!el) return null;
          const id = el.getAttribute('id');
          const parentLbl = el.closest('label');
          const forLbl = id ? document.querySelector('label[for="' + id + '"]') : null;
          const lbl = parentLbl || forLbl;
          if (!lbl) return { found: false };
          const r = lbl.getBoundingClientRect();
          return {
            found: true,
            visible: r.width > 0 && r.height > 0,
            useFor: !parentLbl && Boolean(forLbl),
            id: id || ''
          };
        }""",
        selector,
    )
    if label_info and label_info.get("found") and label_info.get("visible"):
        if label_info.get("useFor") and label_info.get("id"):
            page.locator(f'label[for="{label_info["id"]}"]').first.click()
            return
        page.locator(f"label:has({selector})").first.click()
        return
    raise AssertionError(
        f"Toggle {selector!r} is neither directly interactive nor backed by a visible <label>."
    )


class TestAreaFVisualAudioEs(TetrisE2EBaseCase):
    """Tier 1 & Tier 2 E2E coverage for HiDPI, Audio, Modals, Spanish UI & README."""

    # ------------------------------------------------------------------
    # Tier 1: Core Functional Sanity (5 tests)
    # ------------------------------------------------------------------

    def test_tier1_01_audio_toggles_independent_sync_and_persist(self) -> None:
        """F5.1, F5.2, F2.8: Music and SFX toggles work independently, stay synced, blur safely, and persist."""
        page = self.open_desktop_page(rng_seed=42)

        initial_storage = get_storage_data(page)
        if initial_storage is not None:
            self.assertIs(initial_storage["musicEnabled"], True)
            self.assertIs(initial_storage["sfxEnabled"], True)

        page.locator(SELECTORS["btn_start_settings"]).click()
        _wait_visible(page, SELECTORS["modal_settings"], True)
        tm0 = _read_toggle_state(page, SELECTORS["toggle_music"])
        ts0 = _read_toggle_state(page, SELECTORS["toggle_sfx"])
        if tm0["boolHint"] is not None:
            self.assertIs(tm0["boolHint"], True)
        if ts0["boolHint"] is not None:
            self.assertIs(ts0["boolHint"], True)
        page.locator(SELECTORS["btn_close_settings"]).click()
        _wait_visible(page, SELECTORS["modal_settings"], False)

        start_game(page, level=1)
        m0 = _read_toggle_state(page, SELECTORS["btn_music"])
        s0 = _read_toggle_state(page, SELECTORS["btn_sfx"])

        # 1. Disable Music via HUD #btn-music (SFX must remain untouched).
        _click_toggle(page, SELECTORS["btn_music"])
        self.assertTrue(
            page.evaluate(
                "(sel) => document.activeElement !== document.querySelector(sel)",
                SELECTORS["btn_music"],
            ),
            "#btn-music must blur after click so Space cannot re-toggle audio.",
        )
        data = get_storage_data(page)
        self.assertIsNotNone(data)
        assert data is not None
        self.assertIs(data["musicEnabled"], False)
        self.assertIs(data["sfxEnabled"], True)

        m1 = _read_toggle_state(page, SELECTORS["btn_music"])
        s1 = _read_toggle_state(page, SELECTORS["btn_sfx"])
        self.assertNotEqual(m1, m0)
        if m1["boolHint"] is not None:
            self.assertIs(m1["boolHint"], False)
        self.assertEqual(s1, s0)

        page.locator(SELECTORS["btn_settings"]).click()
        _wait_visible(page, SELECTORS["modal_settings"], True)
        tm1 = _read_toggle_state(page, SELECTORS["toggle_music"])
        ts1 = _read_toggle_state(page, SELECTORS["toggle_sfx"])
        self.assertNotEqual(tm1, tm0)
        if tm1["boolHint"] is not None:
            self.assertIs(tm1["boolHint"], False)
        self.assertEqual(ts1, ts0)
        page.locator(SELECTORS["btn_close_settings"]).click()
        _wait_visible(page, SELECTORS["modal_settings"], False)

        # 2. Reload persistence check (music=False, sfx=True).
        page.reload(wait_until="load")
        data_reload_1 = get_storage_data(page)
        self.assertIsNotNone(data_reload_1)
        assert data_reload_1 is not None
        self.assertIs(data_reload_1["musicEnabled"], False)
        self.assertIs(data_reload_1["sfxEnabled"], True)
        self.assertNotEqual(_read_toggle_state(page, SELECTORS["btn_music"]), m0)
        self.assertEqual(_read_toggle_state(page, SELECTORS["btn_sfx"]), s0)

        # 3. Re-enable Music via Settings (#toggle-music) and disable SFX via HUD (#btn-sfx).
        page.locator(SELECTORS["btn_start_settings"]).click()
        _wait_visible(page, SELECTORS["modal_settings"], True)
        self.assertNotEqual(_read_toggle_state(page, SELECTORS["toggle_music"]), tm0)
        self.assertEqual(_read_toggle_state(page, SELECTORS["toggle_sfx"]), ts0)
        _click_toggle(page, SELECTORS["toggle_music"])

        data_re_enabled = get_storage_data(page)
        self.assertIsNotNone(data_re_enabled)
        assert data_re_enabled is not None
        self.assertIs(data_re_enabled["musicEnabled"], True)
        self.assertIs(data_re_enabled["sfxEnabled"], True)
        self.assertEqual(_read_toggle_state(page, SELECTORS["toggle_music"]), tm0)
        page.locator(SELECTORS["btn_close_settings"]).click()
        _wait_visible(page, SELECTORS["modal_settings"], False)

        start_game(page, level=1)
        self.assertEqual(_read_toggle_state(page, SELECTORS["btn_music"]), m0)

        _click_toggle(page, SELECTORS["btn_sfx"])
        self.assertTrue(
            page.evaluate(
                "(sel) => document.activeElement !== document.querySelector(sel)",
                SELECTORS["btn_sfx"],
            ),
            "#btn-sfx must blur after click so Space cannot re-toggle audio.",
        )
        data_sfx_off = get_storage_data(page)
        self.assertIsNotNone(data_sfx_off)
        assert data_sfx_off is not None
        self.assertIs(data_sfx_off["musicEnabled"], True)
        self.assertIs(data_sfx_off["sfxEnabled"], False)
        self.assertNotEqual(_read_toggle_state(page, SELECTORS["btn_sfx"]), s0)
        self.assertEqual(_read_toggle_state(page, SELECTORS["btn_music"]), m0)

        page.locator(SELECTORS["btn_settings"]).click()
        _wait_visible(page, SELECTORS["modal_settings"], True)
        self.assertNotEqual(_read_toggle_state(page, SELECTORS["toggle_sfx"]), ts0)
        self.assertEqual(_read_toggle_state(page, SELECTORS["toggle_music"]), tm0)
        page.locator(SELECTORS["btn_close_settings"]).click()
        _wait_visible(page, SELECTORS["modal_settings"], False)

        page.reload(wait_until="load")
        data_reload_2 = get_storage_data(page)
        self.assertIsNotNone(data_reload_2)
        assert data_reload_2 is not None
        self.assertIs(data_reload_2["musicEnabled"], True)
        self.assertIs(data_reload_2["sfxEnabled"], False)
        self.assertEqual(_read_toggle_state(page, SELECTORS["btn_music"]), m0)
        self.assertNotEqual(_read_toggle_state(page, SELECTORS["btn_sfx"]), s0)
        self.assertPageClean(page)

    def test_tier1_02_zero_external_audio_fetches_and_clean_webaudio_lifecycle(self) -> None:
        """F5.1, F5.2: Web Audio synthesis issues zero audio file requests or media tags across full lifecycle."""
        page = self.open_desktop_page(rng_seed=7)
        start_game(page, level=1)

        page.wait_for_timeout(350)
        page.keyboard.press("ArrowLeft")
        page.keyboard.press("ArrowRight")
        page.keyboard.press("ArrowUp")
        page.keyboard.press("KeyZ")
        page.keyboard.press("KeyC")
        page.keyboard.down("ArrowDown")
        page.wait_for_timeout(120)
        page.keyboard.up("ArrowDown")
        page.keyboard.press("Space")

        page.keyboard.press("KeyP")
        _wait_visible(page, SELECTORS["overlay_pause"], True)
        page.wait_for_timeout(150)
        page.locator(SELECTORS["btn_resume"]).click()
        _wait_visible(page, SELECTORS["overlay_pause"], False)
        page.wait_for_timeout(200)

        _click_toggle(page, SELECTORS["btn_music"])
        _click_toggle(page, SELECTORS["btn_music"])
        _click_toggle(page, SELECTORS["btn_sfx"])
        _click_toggle(page, SELECTORS["btn_sfx"])

        _hard_drop_until_gameover(page)

        diag = self.diagnostics_for(page)
        media_requests = [
            req
            for req in diag.all_requests
            if req["resource_type"] == "media" or _AUDIO_EXT_RE.search(req["url"])
        ]
        self.assertEqual(media_requests, [], f"Unexpected audio/media network requests: {media_requests}")

        media_dom_count = page.evaluate(
            "() => document.querySelectorAll('audio[src], audio source[src], video[src], video source[src]').length"
        )
        self.assertEqual(media_dom_count, 0)
        self.assertPageClean(page)

    def test_tier1_03_hidpi_canvas_desktop_mobile_and_orientation_resize(self) -> None:
        """F4.1, F4.3: HiDPI canvases size accurately at dpr=2 on desktop, mobile, and orientation changes."""
        # Desktop 1440x900 @ dpr=2
        desk = self.open_desktop_page(device_scale_factor=2.0, rng_seed=42)
        start_game(desk, level=1)

        md = get_layout_metrics(desk)
        self.assertEqual(md["dpr"], 2)
        self.assertEqual(md["cappedDpr"], 2)
        self.assertTrue(md["hidpiBufferExact"], f"Desktop HiDPI buffer mismatch: {md}")
        self.assertTrue(md["noHorizontalOverflow"])
        self.assertTrue(md["noVerticalOverflow"])
        self.assertGreaterEqual(md["canvasCssW"], 120)
        self.assertLessEqual(abs(md["canvasCssH"] - 2 * md["canvasCssW"]), 1.0)
        self.assertLessEqual(abs(md["canvasBufferH"] - 2 * md["canvasBufferW"]), 2)

        for aux_key in ("hold_canvas", "next_canvas"):
            am = get_layout_metrics(desk, canvas_selector=SELECTORS[aux_key])
            self.assertGreater(am["canvasCssW"], 0)
            self.assertGreater(am["canvasCssH"], 0)
            self.assertTrue(am["hidpiBufferExact"], f"{aux_key} HiDPI mismatch: {am}")

        self.assertIsNotNone(detect_top_spawn_piece(desk))
        self.assertPageClean(desk)

        # Mobile 390x844 @ dpr=2 + Orientation switch 390x844 -> 844x390 -> 390x844
        mob = self.open_mobile_page(viewport=(390, 844), device_scale_factor=2.0, rng_seed=42)
        start_game(mob, level=1)

        m_port = get_layout_metrics(mob)
        self.assertEqual(m_port["dpr"], 2)
        self.assertEqual(m_port["cappedDpr"], 2)
        self.assertTrue(m_port["hidpiBufferExact"])
        self.assertTrue(m_port["noHorizontalOverflow"])
        self.assertTrue(m_port["noVerticalOverflow"])
        self.assertGreaterEqual(m_port["stageHeightRatio"], 0.80)
        self.assertGreaterEqual(m_port["canvasCssW"] / 10.0, 12.0)
        self.assertLessEqual(abs(m_port["canvasCssH"] - 2 * m_port["canvasCssW"]), 1.0)

        mob.set_viewport_size({"width": 844, "height": 390})
        mob.wait_for_function("() => window.innerWidth === 844 && window.innerHeight === 390")
        mob.wait_for_timeout(120)
        _wait_frames(mob, 2)

        m_land = get_layout_metrics(mob)
        self.assertEqual(m_land["dpr"], 2)
        self.assertTrue(m_land["hidpiBufferExact"])
        self.assertTrue(m_land["noHorizontalOverflow"])
        self.assertTrue(m_land["noVerticalOverflow"])
        self.assertGreaterEqual(m_land["canvasCssW"] / 10.0, 12.0)
        self.assertLessEqual(abs(m_land["canvasCssH"] - 2 * m_land["canvasCssW"]), 1.0)
        self.assertLess(m_land["canvasCssH"], m_port["canvasCssH"])
        grid_land = sample_board_grid_state(mob)["grid"]
        self.assertTrue(any(cell is not None for row in grid_land for cell in row))

        mob.set_viewport_size({"width": 390, "height": 844})
        mob.wait_for_function("() => window.innerWidth === 390 && window.innerHeight === 844")
        mob.wait_for_timeout(120)
        _wait_frames(mob, 2)

        m_restored = get_layout_metrics(mob)
        self.assertTrue(m_restored["hidpiBufferExact"])
        self.assertGreaterEqual(m_restored["stageHeightRatio"], 0.80)
        self.assertTrue(m_restored["noHorizontalOverflow"])
        self.assertTrue(m_restored["noVerticalOverflow"])
        self.assertPageClean(mob)

    def test_tier1_04_visual_feedback_drop_harddrop_hold_and_next_queue(self) -> None:
        """F4.1, F4.2, F2.5: Board, Hold, and 3-Next canvases visually update on gravity, Hold, and Hard Drop."""
        page = self.open_desktop_page(rng_seed=42)
        start_game(page, level=5)

        board_0 = capture_element_image(page, SELECTORS["board_canvas"])
        hold_empty = capture_element_image(page, SELECTORS["hold_canvas"])
        next_0 = capture_element_image(page, SELECTORS["next_canvas"])

        page.wait_for_timeout(550)
        board_1 = capture_element_image(page, SELECTORS["board_canvas"])
        self.assertTrue(images_differ(board_0, board_1, min_diff_pixels=20))

        # First Hold updates #hold-canvas and shifts #next-canvas.
        page.keyboard.press("KeyC")
        _wait_frames(page, 2)
        hold_1 = capture_element_image(page, SELECTORS["hold_canvas"])
        next_1 = capture_element_image(page, SELECTORS["next_canvas"])
        self.assertTrue(images_differ(hold_empty, hold_1, min_diff_pixels=20))
        self.assertTrue(images_differ(next_0, next_1, min_diff_pixels=20))

        # Hard Drop updates board, awards points, locks bottom cells, and shifts Next queue.
        board_before_hd = capture_element_image(page, SELECTORS["board_canvas"])
        page.keyboard.press("Space")
        page.wait_for_timeout(80)
        board_after_hd = capture_element_image(page, SELECTORS["board_canvas"])
        next_2 = capture_element_image(page, SELECTORS["next_canvas"])
        self.assertTrue(images_differ(board_before_hd, board_after_hd, min_diff_pixels=40))
        self.assertGreater(get_hud_stats(page)["score"], 0)
        self.assertGreater(_bottom_rows_occupied(sample_board_grid_state(page), start_row=16), 0)
        self.assertTrue(images_differ(next_1, next_2, min_diff_pixels=20))

        # Second Hold swaps a distinct piece into #hold-canvas.
        page.keyboard.press("KeyC")
        _wait_frames(page, 2)
        hold_2 = capture_element_image(page, SELECTORS["hold_canvas"])
        self.assertTrue(images_differ(hold_1, hold_2, min_diff_pixels=20))
        self.assertPageClean(page)

    def test_tier1_05_spanish_ui_aria_and_readme_verification(self) -> None:
        """F6.1, F4.3: 100% Spanish UI, accessible labels, controls guide, and README.md GitHub Pages docs."""
        page = self.open_desktop_page(rng_seed=42)

        lang = page.evaluate("() => document.documentElement.lang || ''")
        self.assertTrue(lang.lower().startswith("es"), f"Expected <html lang='es'>, got {lang!r}")
        self.assertEqual(page.title(), "Tetris Clásico")

        self.assertTrue(is_element_visible(page, SELECTORS["overlay_start"]))
        start_text = page.locator(SELECTORS["overlay_start"]).inner_text().lower()
        self.assertIn("nivel", start_text)
        self.assertTrue(any(w in start_text for w in ("jugar", "iniciar", "comenzar")))
        self.assertTrue(any(w in start_text for w in ("ajustes", "configuración")))

        # Check Settings modal Spanish text & controls guide (including optional guide tabs).
        page.locator(SELECTORS["btn_start_settings"]).click()
        _wait_visible(page, SELECTORS["modal_settings"], True)
        settings_texts = [page.locator(SELECTORS["modal_settings"]).inner_text().lower()]
        tab_count = page.locator(f"{SELECTORS['modal_settings']} [role='tab'], {SELECTORS['modal_settings']} button").count()
        if tab_count > 0:
            buttons = page.locator(f"{SELECTORS['modal_settings']} [role='tab'], {SELECTORS['modal_settings']} button")
            for idx in range(buttons.count()):
                btn = buttons.nth(idx)
                btn_id = btn.get_attribute("id") or ""
                if btn_id in ("btn-close-settings", "toggle-music", "toggle-sfx"):
                    continue
                txt = (btn.inner_text() or "").lower()
                if any(k in txt for k in ("teclado", "táctil", "tactil", "xbox", "control")):
                    btn.click()
                    settings_texts.append(page.locator(SELECTORS["modal_settings"]).inner_text().lower())
        combined_settings = "\n".join(settings_texts)
        self.assertIn("sensibilidad", combined_settings)
        self.assertIn("música", combined_settings)
        self.assertIn("efectos", combined_settings)
        self.assertTrue(any(w in combined_settings for w in ("cerrar", "listo", "volver", "guardar")))
        self.assertIn("teclado", combined_settings)
        self.assertTrue("táctil" in combined_settings or "tactil" in combined_settings)
        self.assertIn("control xbox", combined_settings)
        page.locator(SELECTORS["btn_close_settings"]).click()
        _wait_visible(page, SELECTORS["modal_settings"], False)

        # Start gameplay and verify HUD Spanish labels & ARIA attributes.
        start_game(page, level=1)
        body_text = page.evaluate("() => document.body.innerText || ''").lower()
        self.assertTrue(any(w in body_text for w in ("puntuación", "puntaje", "puntos")))
        self.assertIn("nivel", body_text)
        self.assertIn("líneas", body_text)
        self.assertTrue(any(w in body_text for w in ("mejor", "récord")))

        # Pause overlay Spanish copy.
        page.keyboard.press("KeyP")
        _wait_visible(page, SELECTORS["overlay_pause"], True)
        pause_text = page.locator(SELECTORS["overlay_pause"]).inner_text().lower()
        self.assertIn("pausa", pause_text)
        self.assertTrue(any(w in pause_text for w in ("reanudar", "continuar")))
        self.assertIn("reiniciar", pause_text)
        self.assertTrue(any(w in pause_text for w in ("ajustes", "configuración")))
        page.locator(SELECTORS["btn_resume"]).click()
        _wait_visible(page, SELECTORS["overlay_pause"], False)

        # Game Over overlay Spanish copy.
        _hard_drop_until_gameover(page)
        gameover_text = page.locator(SELECTORS["overlay_gameover"]).inner_text().lower()
        self.assertTrue(any(w in gameover_text for w in ("puntuación", "puntaje", "puntos")))
        self.assertIn("nivel", gameover_text)
        self.assertIn("líneas", gameover_text)
        self.assertTrue(any(w in gameover_text for w in ("jugar", "reiniciar", "reintentar", "otra")))

        # Accessible names & Spanish ARIA labels on contracted interactive controls.
        english_placeholders = {"play", "pause", "settings", "music", "sfx", "sound", "close", "hold", "restart", "resume"}
        for key in (
            "btn_pause",
            "btn_settings",
            "btn_music",
            "btn_sfx",
            "hold_box",
            "btn_level_down",
            "btn_level_up",
            "btn_close_settings",
        ):
            sel = SELECTORS[key]
            info = page.evaluate(
                """(s) => {
                  const el = document.querySelector(s);
                  if (!el) return null;
                  return {
                    ariaLabel: (el.getAttribute('aria-label') || '').trim(),
                    text: (el.innerText || el.textContent || '').trim(),
                    title: (el.getAttribute('title') || '').trim()
                  };
                }""",
                sel,
            )
            self.assertIsNotNone(info, f"Missing element {sel}")
            assert info is not None
            accessible_name = info["ariaLabel"] or info["text"] or info["title"]
            self.assertTrue(len(accessible_name) > 0, f"Control {sel} lacks accessible name")
            if info["ariaLabel"]:
                self.assertNotIn(
                    info["ariaLabel"].lower(),
                    english_placeholders,
                    f"English placeholder aria-label on {sel}: {info['ariaLabel']!r}",
                )

        # README.md verification (relative to self.APP_ROOT so isolated probes also validate cleanly).
        readme_path = Path(self.APP_ROOT) / "README.md"
        self.assertTrue(readme_path.is_file(), f"Expected README.md at {readme_path}")
        readme_text = readme_path.read_text(encoding="utf-8")
        self.assertGreaterEqual(len(readme_text.strip()), 400)
        readme_lower = readme_text.lower()
        self.assertIn("tetris", readme_lower)
        self.assertIn("index.html", readme_lower)
        self.assertIn("github pages", readme_lower)
        self.assertIn("teclado", readme_lower)
        self.assertTrue(any(w in readme_lower for w in ("táctil", "tactil", "celular", "móvil", "movil")))
        self.assertTrue(any(w in readme_lower for w in ("xbox", "gamepad")))
        self.assertTrue(any(w in readme_lower for w in ("pantalla de inicio", "instalar", "pwa")))
        self.assertGreaterEqual(
            sum(
                1
                for w in ("jugar", "controles", "despliegue", "navegador", "ajustes", "instalación", "instalacion")
                if w in readme_lower
            ),
            3,
            "README.md does not appear to contain expected Spanish documentation sections.",
        )

        self.assertPageClean(page)

    # ------------------------------------------------------------------
    # Tier 2: Boundary & Edge Behavior (6 tests)
    # ------------------------------------------------------------------

    def test_tier2_01_hidpi_dpr_capped_at_2_under_dpr3(self) -> None:
        """F4.1: Under devicePixelRatio === 3, canvas backing buffers cap DPR strictly at 2."""
        page = self.open_mobile_page(viewport=(390, 844), device_scale_factor=3.0, rng_seed=42)
        start_game(page, level=1)

        m = get_layout_metrics(page)
        self.assertEqual(m["dpr"], 3)
        self.assertEqual(m["cappedDpr"], 2)
        self.assertTrue(m["hidpiBufferExact"], f"Board canvas DPR cap mismatch under dpr=3: {m}")
        self.assertLess(m["canvasBufferW"], m["canvasCssW"] * 2.5)

        for aux_key in ("hold_canvas", "next_canvas"):
            am = get_layout_metrics(page, canvas_selector=SELECTORS[aux_key])
            self.assertGreater(am["canvasCssW"], 0)
            self.assertTrue(am["hidpiBufferExact"], f"{aux_key} DPR cap mismatch under dpr=3: {am}")
            self.assertLessEqual(am["canvasBufferW"], math.ceil(am["canvasCssW"] * 2) + 2)

        grid = sample_board_grid_state(page)["grid"]
        self.assertTrue(any(cell is not None for row in grid for cell in row))
        self.assertPageClean(page)

    def test_tier2_02_responsive_extremes_desktop_short_landscape_tiny_portrait(self) -> None:
        """F4.3, F4.1, F3.4: Desktop 1440x900, short landscape 740x360, and tiny portrait 360x640 fit cleanly."""
        configs = (
            ((1440, 900), False, False, 1.0, False),
            ((740, 360), True, True, 2.0, False),
            ((360, 640), True, True, 2.0, True),
        )
        for viewport, has_touch, is_mobile, dpr, expect_portrait_budget in configs:
            with self.subTest(viewport=viewport):
                page = self.open_page(
                    viewport=viewport,
                    has_touch=has_touch,
                    is_mobile=is_mobile,
                    device_scale_factor=dpr,
                    rng_seed=42,
                )

                m_start = get_layout_metrics(page)
                self.assertTrue(m_start["noHorizontalOverflow"])
                self.assertTrue(m_start["noVerticalOverflow"])
                self.assertTrue(is_element_visible(page, SELECTORS["btn_play"], require_interactive=True))

                start_game(page, level=1)
                m = get_layout_metrics(page)
                self.assertTrue(m["noHorizontalOverflow"], f"Horizontal overflow at {viewport}: {m}")
                self.assertTrue(m["noVerticalOverflow"], f"Vertical overflow at {viewport}: {m}")
                self.assertGreaterEqual(m["canvasCssW"] / 10.0, 12.0)
                self.assertGreaterEqual(m["canvasCssH"] / 20.0, 12.0)
                self.assertLessEqual(abs(m["canvasCssH"] - 2 * m["canvasCssW"]), 1.0)
                self.assertTrue(m["hidpiBufferExact"], f"HiDPI mismatch at {viewport}: {m}")

                if expect_portrait_budget:
                    self.assertGreaterEqual(m["stageHeightRatio"], 0.80)
                    self.assertEqual(m["touchAction"]["stage"], "none")

                for key in ("board_canvas", "hold_canvas", "next_canvas", "btn_pause", "btn_settings"):
                    self.assertTrue(is_element_visible(page, SELECTORS[key]))

                page.locator(SELECTORS["btn_settings"]).click()
                _wait_visible(page, SELECTORS["modal_settings"], True)
                m_modal = get_layout_metrics(page)
                self.assertTrue(m_modal["noHorizontalOverflow"])
                self.assertTrue(m_modal["noVerticalOverflow"])
                close_btn = page.locator(SELECTORS["btn_close_settings"])
                close_btn.scroll_into_view_if_needed()
                close_btn.click()
                _wait_visible(page, SELECTORS["modal_settings"], False)
                _wait_visible(page, SELECTORS["overlay_pause"], True)
                self.assertPageClean(page)

    def test_tier2_03_settings_modal_auto_pauses_and_returns_to_pause(self) -> None:
        """F4.3, F5.2: Opening Settings during play freezes level-8 gravity and closes to #overlay-pause."""
        page = self.open_desktop_page(rng_seed=99)
        start_game(page, level=8)

        grid_before = sample_board_grid_state(page)
        max_row_before = _max_occupied_row(grid_before)
        self.assertGreaterEqual(max_row_before, 0)
        self.assertLessEqual(max_row_before, 6)

        page.locator(SELECTORS["btn_settings"]).click()
        _wait_visible(page, SELECTORS["modal_settings"], True)
        page.wait_for_timeout(900)

        page.locator(SELECTORS["btn_close_settings"]).click()
        _wait_visible(page, SELECTORS["modal_settings"], False)
        _wait_visible(page, SELECTORS["overlay_pause"], True)

        page.wait_for_timeout(400)
        self.assertTrue(is_element_visible(page, SELECTORS["overlay_pause"]))
        self.assertEqual(get_hud_stats(page)["score"], 0)

        page.locator(SELECTORS["btn_resume"]).click()
        _wait_visible(page, SELECTORS["overlay_pause"], False)

        grid_resumed = sample_board_grid_state(page)
        max_row_resumed = _max_occupied_row(grid_resumed)
        self.assertLessEqual(max_row_resumed - max_row_before, 2)
        self.assertEqual(_bottom_rows_occupied(grid_resumed, start_row=16), 0)

        page.wait_for_timeout(550)
        grid_after = sample_board_grid_state(page)
        max_row_after = _max_occupied_row(grid_after)
        self.assertGreaterEqual(max_row_after - max_row_resumed, 2)
        self.assertPageClean(page)

    def test_tier2_04_hostile_webaudio_absence_plays_toggles_and_gameovers_cleanly(self) -> None:
        """F5.1, F5.2: Deleting AudioContext and webkitAudioContext yields zero errors across full lifecycle."""
        no_audio_script = """
        (function () {
          try { Object.defineProperty(window, 'AudioContext', { value: undefined, configurable: true, writable: true }); } catch (_) {}
          try { Object.defineProperty(window, 'webkitAudioContext', { value: undefined, configurable: true, writable: true }); } catch (_) {}
          try { delete window.AudioContext; } catch (_) {}
          try { delete window.webkitAudioContext; } catch (_) {}
        })();
        """
        page = self.open_desktop_page(init_scripts=[no_audio_script], rng_seed=17)
        types = page.evaluate("() => [typeof AudioContext, typeof webkitAudioContext]")
        self.assertEqual(types, ["undefined", "undefined"])

        start_game(page, level=1)
        page.keyboard.press("ArrowLeft")
        page.keyboard.press("ArrowRight")
        page.keyboard.press("ArrowUp")
        page.keyboard.press("KeyZ")
        page.keyboard.press("KeyC")
        page.keyboard.down("ArrowDown")
        page.wait_for_timeout(120)
        page.keyboard.up("ArrowDown")
        page.keyboard.press("Space")

        _click_toggle(page, SELECTORS["btn_music"])
        _click_toggle(page, SELECTORS["btn_sfx"])
        page.locator(SELECTORS["btn_settings"]).click()
        _wait_visible(page, SELECTORS["modal_settings"], True)
        _click_toggle(page, SELECTORS["toggle_music"])
        _click_toggle(page, SELECTORS["toggle_sfx"])
        page.locator(SELECTORS["btn_close_settings"]).click()
        _wait_visible(page, SELECTORS["modal_settings"], False)
        _wait_visible(page, SELECTORS["overlay_pause"], True)
        page.locator(SELECTORS["btn_resume"]).click()
        _wait_visible(page, SELECTORS["overlay_pause"], False)

        _hard_drop_until_gameover(page)
        self.assertGreater(get_hud_stats(page)["score"], 0)

        page.locator(SELECTORS["btn_play_again"]).click()
        _wait_visible(page, SELECTORS["overlay_gameover"], False)
        self.assertFalse(is_element_visible(page, SELECTORS["overlay_start"]))
        self.assertPageClean(page)

    def test_tier2_05_new_record_badge_boundary_and_lower_score_preservation(self) -> None:
        """F2.8, F4.3, F2.7: Record badge shows strictly on beating bestScore and stays hidden on lower score."""
        page = self.open_desktop_page(rng_seed=42)
        self.assertEqual(get_hud_stats(page)["best_score"], 0)

        # Run 1: Spread 3 pieces far left and 3 far right before center top-out to earn >= 280 points.
        start_game(page, level=1)
        for _ in range(3):
            for _ in range(4):
                page.keyboard.press("ArrowLeft")
            page.keyboard.press("Space")
            page.wait_for_timeout(35)
        for _ in range(3):
            for _ in range(4):
                page.keyboard.press("ArrowRight")
            page.keyboard.press("Space")
            page.wait_for_timeout(35)
        _hard_drop_until_gameover(page)

        score_run1 = _parse_int_text(
            page.locator(SELECTORS["final_score_value"]).inner_text(),
            SELECTORS["final_score_value"],
        )
        self.assertGreaterEqual(score_run1, 280)
        self.assertTrue(is_element_visible(page, SELECTORS["gameover_record_badge"]))
        self.assertEqual(get_hud_stats(page)["best_score"], score_run1)
        self.assertEqual(get_storage_data(page)["bestScore"], score_run1)  # type: ignore[index]

        # Run 2: Immediate Play Again with center-only Hard Drops yields lower score.
        page.locator(SELECTORS["btn_play_again"]).click()
        _wait_visible(page, SELECTORS["overlay_gameover"], False)
        _hard_drop_until_gameover(page)

        score_run2 = _parse_int_text(
            page.locator(SELECTORS["final_score_value"]).inner_text(),
            SELECTORS["final_score_value"],
        )
        self.assertGreater(score_run2, 0)
        self.assertLess(score_run2, score_run1)
        self.assertFalse(is_element_visible(page, SELECTORS["gameover_record_badge"]))
        self.assertEqual(get_hud_stats(page)["best_score"], score_run1)
        self.assertEqual(get_storage_data(page)["bestScore"], score_run1)  # type: ignore[index]

        page.reload(wait_until="load")
        self.assertEqual(get_hud_stats(page)["best_score"], score_run1)
        self.assertEqual(get_storage_data(page)["bestScore"], score_run1)  # type: ignore[index]
        self.assertPageClean(page)

    def test_tier2_06_settings_modal_origin_return_across_all_overlays(self) -> None:
        """F4.3: Closing Settings returns cleanly to Start, Pause, or Game Over depending on entry point."""
        page = self.open_desktop_page(rng_seed=42)

        # 1. Start -> Settings -> Close -> Start
        page.locator(SELECTORS["btn_start_settings"]).click()
        _wait_visible(page, SELECTORS["modal_settings"], True)
        page.locator(SELECTORS["btn_close_settings"]).click()
        _wait_visible(page, SELECTORS["modal_settings"], False)
        self.assertTrue(is_element_visible(page, SELECTORS["overlay_start"]))
        self.assertFalse(is_element_visible(page, SELECTORS["overlay_pause"]))

        # 2. Playing -> Settings -> Close -> Pause
        start_game(page, level=1)
        page.locator(SELECTORS["btn_settings"]).click()
        _wait_visible(page, SELECTORS["modal_settings"], True)
        page.locator(SELECTORS["btn_close_settings"]).click()
        _wait_visible(page, SELECTORS["modal_settings"], False)
        _wait_visible(page, SELECTORS["overlay_pause"], True)
        self.assertFalse(is_element_visible(page, SELECTORS["overlay_start"]))

        # 3. Pause -> Settings -> Close -> Pause
        page.locator(SELECTORS["btn_pause_settings"]).click()
        _wait_visible(page, SELECTORS["modal_settings"], True)
        page.locator(SELECTORS["btn_close_settings"]).click()
        _wait_visible(page, SELECTORS["modal_settings"], False)
        self.assertTrue(is_element_visible(page, SELECTORS["overlay_pause"]))

        page.locator(SELECTORS["btn_resume"]).click()
        _wait_visible(page, SELECTORS["overlay_pause"], False)

        # 4. Game Over -> Settings -> Close -> Game Over
        _hard_drop_until_gameover(page)
        page.locator(SELECTORS["btn_gameover_settings"]).click()
        _wait_visible(page, SELECTORS["modal_settings"], True)
        page.locator(SELECTORS["btn_close_settings"]).click()
        _wait_visible(page, SELECTORS["modal_settings"], False)
        self.assertTrue(is_element_visible(page, SELECTORS["overlay_gameover"]))
        self.assertFalse(is_element_visible(page, SELECTORS["overlay_pause"]))
        self.assertPageClean(page)


if __name__ == "__main__":
    unittest.main()

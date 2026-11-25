# E2E Testing Infrastructure Guide — Classic Tetris Web Application

Comprehensive reference for the opaque-box Playwright E2E test harness in [`tests/e2e/harness.py`](file:///home/antigravity/tests/e2e/harness.py) and the requirement-driven test suite under `tests/e2e/`.

---

## 1. Environment & Runtime Commands

### Verified Runtime Stack
- **Python**: `/opt/pyenv/shims/python3` (`Python 3.12.16`, on `PATH` as `python3`)
- **Browser Automation**: `playwright 1.65.2` (Chromium headless)
- **Image Inspection**: `Pillow 13.0.0` (`PIL.Image`, `PIL.ImageChops`)
- **Playwright Browsers**: `PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright`
- **Test Runner**: Python stdlib `unittest`

### Standard Commands
Run from `/home/antigravity`:

```bash
# Run the full E2E test suite
python3 -m unittest discover -s tests/e2e -v

# Run a single E2E test module
python3 -m unittest tests/e2e/<file>.py -v
```

> [!WARNING]
> **NEVER use `/opt/pipx/bin/pytest`** (or `pytest`). Its isolated pipx virtual environment lacks both `playwright` and `Pillow`, and `python3 -m pytest` is not installed. All E2E tests inherit from `unittest.TestCase` (via [`TetrisE2EBaseCase`](file:///home/antigravity/tests/e2e/harness.py)) and execute strictly via `python3 -m unittest`.

---

## 2. Opaque-Box Contract & Selector Reference

All E2E tests derive exclusively from `/home/antigravity/.agents/teamwork/ORIGINAL_REQUEST.md` and `/home/antigravity/PROJECT.md` (§ Feature Inventory, § Interface Contracts).

### Hard Opaque-Box Discipline
1. **Zero internal JS access**: Tests and harness helpers MUST NOT read, call, or mutate `window.Tetris.*` internals (`window.Tetris.Engine`, `window.Tetris.Main`, internal variables, etc.).
2. **Zero uncontracted CSS class assumptions**: Tests MUST NOT inspect `.hidden`, `.active`, `.open`, or other implementation-internal CSS classes to determine UI state. Always use [`is_element_visible(page, selector, require_interactive=...)`](file:///home/antigravity/tests/e2e/harness.py).
3. **Zero external network dependencies**: `PageDiagnostics` collects every outgoing request and flags any non-local request outside `127.0.0.1`, `localhost`, `::1`, `file://`, `data:`, `blob:`, and `about:`.

### Contracted DOM IDs (`SELECTORS`)

All 40 contracted DOM IDs from `PROJECT.md § 7` are exposed in `tests.e2e.harness.SELECTORS`:

| Surface / Group | Harness Key | DOM Selector | Purpose |
|---|---|---|---|
| **Board & Queues** | `board_stage` | `#board-stage` | Touch/pointer capture surface (`.board-stage`, `touch-action: none`) |
| | `board_canvas` | `#board-canvas` | 10×20 visible playfield `<canvas>` (`devicePixelRatio <= 2`) |
| | `hold_box` | `#hold-box` | Interactive `<button>` holding `#hold-canvas` (tap triggers Hold) |
| | `hold_canvas` | `#hold-canvas` | Held tetromino preview `<canvas>` |
| | `next_canvas` | `#next-canvas` | 3-piece upcoming queue `<canvas>` |
| **Live HUD & Best** | `score_value` | `#score-value` | Current game score text |
| | `level_value` | `#level-value` | Current level text |
| | `lines_value` | `#lines-value` | Total lines cleared text |
| | `best_score_value` | `#best-score-value` | Persisted best score text |
| | `best_level_value` | `#best-level-value` | Persisted best level text |
| | `best_lines_value` | `#best-lines-value` | Persisted best lines text |
| **Top / Action Bar** | `btn_pause` | `#btn-pause` | Pause/resume toggle button |
| | `btn_settings` | `#btn-settings` | Open Settings modal button |
| | `btn_music` | `#btn-music` | Quick Music mute/unmute button |
| | `btn_sfx` | `#btn-sfx` | Quick SFX mute/unmute button |
| | `gamepad_badge` | `#gamepad-badge` | HUD Xbox/Gamepad connection status indicator |
| **Start Overlay** | `overlay_start` | `#overlay-start` | Start screen overlay container |
| | `btn_level_down` | `#btn-level-down` | Decrement initial Marathon level (`1..15`) |
| | `start_level_value` | `#start-level-value` | Selected initial Marathon level text |
| | `btn_level_up` | `#btn-level-up` | Increment initial Marathon level (`1..15`) |
| | `btn_play` | `#btn-play` | Start game button |
| | `btn_start_settings` | `#btn-start-settings` | Open Settings from Start overlay |
| **Pause Overlay** | `overlay_pause` | `#overlay-pause` | Pause screen overlay container |
| | `btn_resume` | `#btn-resume` | Resume active game button |
| | `btn_pause_settings` | `#btn_pause_settings` | Open Settings from Pause overlay |
| | `btn_restart` | `#btn-restart` | Restart game button |
| **Game Over Overlay** | `overlay_gameover` | `#overlay-gameover` | Game Over overlay container |
| | `final_score_value` | `#final-score-value` | Final score summary text |
| | `final_level_value` | `#final-level-value` | Final level summary text |
| | `final_lines_value` | `#final-lines-value` | Final lines summary text |
| | `gameover_record_badge` | `#gameover-record-badge` | New record indicator badge |
| | `btn_play_again` | `#btn-play-again` | Start a new run from Game Over |
| | `btn_gameover_settings` | `#btn-gameover-settings` | Open Settings from Game Over |
| **Settings Modal** | `modal_settings` | `#modal-settings` | Settings modal container |
| | `sensitivity_slider` | `#sensitivity-slider` | `<input type="range" min="1" max="10">` touch sensitivity slider |
| | `sensitivity_value` | `#sensitivity-value` | Numeric touch sensitivity label |
| | `toggle_music` | `#toggle-music` | Settings modal Music toggle |
| | `toggle_sfx` | `#toggle-sfx` | Settings modal SFX toggle |
| | `settings_gamepad_status` | `#settings-gamepad-status` | Detailed Gamepad connection status in Settings |
| | `btn_close_settings` | `#btn-close-settings` | Close Settings modal button |

### Storage, PWA Cache & Sibling Isolation Contracts
- **Tetris `localStorage` Key** (`STORAGE_KEY`): `'tetris_clasico_v1'`
  - JSON schema (`DEFAULT_STORAGE_STATE`):
    `{ bestScore, bestLevel, bestLines, touchSensitivity, musicEnabled, sfxEnabled, startLevel }`
  - Defaults: `bestScore: 0`, `bestLevel: 0`, `bestLines: 0`, `touchSensitivity: 5`, `musicEnabled: true`, `sfxEnabled: true`, `startLevel: 1`.
- **Tetris Service Worker Cache** (`CACHE_NAME`, `CACHE_PREFIX`): `'tetris-clasico-v1'` (activation prunes only `key.startsWith('tetris-clasico-') && key !== 'tetris-clasico-v1'`).
- **Diana Sudoku Sibling Keys** (must remain untouched on shared `file://` and GitHub Pages origins):
  - `DIANA_STORAGE_KEY = 'diana_sudoku_v1'`
  - `DIANA_CACHE_NAME = 'diana-sudoku-v1'`

### Spanish Localization & Mobile Viewport Budget
- **Spanish UI**: `<html lang="es">`, `<title>Tetris Clásico</title>`, Spanish labels, ARIA attributes, and controls guide sections (`Teclado`, `Táctil`, `Control Xbox`).
- **Mobile Viewport Budget** (`<= 820px` width):
  - `.board-stage` height **>= 80%** of `window.innerHeight` (`stageHeightRatio >= 0.80`)
  - Zero horizontal or vertical page overflow (`scrollWidth <= innerWidth`, `scrollHeight <= innerHeight`)
  - Gesture locking: `touch-action: none` on `.board-stage`, `overscroll-behavior: none`, `user-select: none`.

---

## 3. Timing, Isolation & Harness API Reference

### `StaticAppServer`
Backed by Python stdlib `ThreadingHTTPServer` bound to `("127.0.0.1", 0)`:
- **Root & GitHub Pages Subpath Parity**: Serves `root_dir` (default `/home/antigravity`) at `/` or under a prefix such as `base_prefix="/tetris-clasico/"`. Requests to the bare subpath (`/tetris-clasico` or `/tetris-clasico?v=1`) respond with **`301 Location: /tetris-clasico/`** (preserving query string), while requests outside the prefix return `404`.
- **Security Hardening**: Rejects protocol-relative paths (`//evil.com` -> `404`), null bytes (`400`), backslashes / `..` traversal / symlink escapes outside `root_dir` (`403`), and directories lacking `index.html` (`404`).
- **Explicit `MIME_TYPES`**: `.html` (`text/html; charset=utf-8`), `.css` (`text/css; charset=utf-8`), `.js`/`.mjs` (`text/javascript; charset=utf-8`), `.webmanifest` (`application/manifest+json; charset=utf-8`), `.svg` (`image/svg+xml`), `.png` (`image/png`), `.json` (`application/json; charset=utf-8`), `.ico` (`image/x-icon`).
- **HTTP/1.1 + `Connection: close` + `Cache-Control: no-store`**:
  - `Cache-Control: no-store` prevents Chromium's HTTP disk/memory cache from masking broken Service Worker precaching while leaving SW `CacheStorage` (`cache.addAll` / `caches.match`) fully functional offline.
  - `Connection: close` ensures worker threads exit immediately rather than blocking in keep-alive `readline()`, keeping `stop()` teardown under ~50 ms with zero leaked threads, ports, or file descriptors.
- **API**: `start()`, `stop()`, `port` (cached even after `stop()`), `origin`, `base_url`, `bare_prefix_url`, `url_for(rel_path)`, `get_requests()`, `clear_requests()`, and context-manager (`with StaticAppServer(...) as srv:`). Supports `GET` and `HEAD` and suppresses broken-pipe noise.

### `TetrisE2EBaseCase` & `PageDiagnostics`
Subclass of `unittest.TestCase` in [`tests/e2e/harness.py`](file:///home/antigravity/tests/e2e/harness.py):
- **Class-Scoped Lifecycle (`setUpClass` / `tearDownClass`)**: Launches Playwright + Chromium (and optional `StaticAppServer` controlled by `APP_ROOT`, `SERVER_BASE_PREFIX`, `START_SERVER`, `CACHE_CONTROL`, `HEADLESS`) **once per test class** with exception-safe rollback if initialization fails.
- **Per-Test Context Isolation (`browser.new_context(...)`)**:
  - **Why `clear_cookies()` is insufficient**: Empirically verified in Chromium that `context.clear_cookies()` leaves `localStorage`, `CacheStorage`, and active Service Worker registrations intact on the origin. Every `open_page()` / `new_context()` call creates a fresh `BrowserContext` registered with `self.addCleanup(...)` so every test starts with zero storage/cache/SW bleed and tears down cleanly even on test failure.
- **Page Factories & Helpers**:
  - `open_page(url=None, *, viewport=(1440, 900), has_touch=False, is_mobile=False, device_scale_factor=1.0, offline=False, init_scripts=None, gamepad=False, rng_seed=None, local_storage_fault=None, corrupt_storage=None, storage_seed=None, storage_seed_key=STORAGE_KEY, storage_seed_once=True, wait_until="load")`
  - `open_desktop_page(...)`: `1440×900`, `has_touch=False`, `is_mobile=False`, `device_scale_factor=1.0`
  - `open_mobile_page(...)`: `390×844`, `has_touch=True`, `is_mobile=True`, `device_scale_factor=2.0`
  - `start_server(root_dir=None, *, base_prefix="/", cache_control="no-store")`: starts an isolated per-test server registered with `addCleanup(srv.stop)`.
  - `file_uri(path)`: builds canonical `file://` URIs for dual-runtime tests.
  - `touch_driver(page)`: constructs `CDPTouchDriver(page)` registered with `addCleanup(driver.detach)`.
- **Diagnostics (`PageDiagnostics`)**:
  - Attached automatically to every page created via `open_page()` (or manually via `attach_diagnostics(page)`), accessible via `self.diagnostics_for(page)` / `self.last_diagnostics`.
  - Records `console_errors`, `console_warnings`, `page_errors`, `request_failures`, `http_error_responses` (`>= 400`), `external_requests`, and `all_requests`.
  - `assertPageClean(page)` asserts zero console errors, uncaught page errors, failed requests, external requests, and HTTP error responses.

### Init-Script Mocks (`add_init_script`)
1. **Dynamic Xbox Gamepad Mock (`make_gamepad_init_script()`, `gamepad=True`)**:
   - Installs `window.__e2eGamepad` and overrides `navigator.getGamepads()` to return a 4-slot snapshot array (`[slot0, slot1, slot2, slot3]`).
   - API:
     - `connect(opts)` -> `{ index, id, mapping, buttonCount, axisCount }` (dispatches `gamepadconnected` with `GamepadEvent.prototype` + own `gamepad` property, avoiding Chromium's `new GamepadEvent()` conversion error on plain objects).
     - `disconnect(index=0)` -> marks disconnected, clears slot, dispatches `gamepaddisconnected`.
     - `setButton(buttonIndex, pressed, value=None, padIndex=0)`
     - `setAxis(axisIndex, value, padIndex=0)`
     - `resetInputs(padIndex=0)` -> clears all buttons/axes to neutral.
     - `getState(padIndex=0)` -> returns cloned snapshot or `null`.
   - Enforces strictly monotonic `timestamp` across rapid synchronous calls and supports non-standard `mapping` strings and arbitrary button/axis lengths.
2. **`localStorage` Fault Injection (`make_local_storage_fault_script(mode, error_name)`)**:
   - Modes: `'set_only'` (throws on `setItem` only, leaving `getItem` & `sessionStorage` working), `'all_methods'` (throws on `getItem`/`setItem`/`removeItem`/`clear`), `'getter'` (throws on bare `window.localStorage` access).
   - **Important `about:blank` guard**: Skips execution when `location.protocol === 'about:'` so Playwright's initial `about:blank` page does not interfere with real-origin behavior.
3. **`localStorage` Pre-Boot Seeding (`make_local_storage_seed_script(key, raw_value, seed_once=True)`)**:
   - Used by `corrupt_storage` and `storage_seed` options. Guards `location.protocol === 'about:'` and tracks `seed_once` via origin-scoped `sessionStorage` (with `window.name` fallback) so initial corrupt payloads trigger recovery on first load and recovered values persist across reloads.
4. **Deterministic PRNG (`make_lcg_init_script(seed)`, `rng_seed=...`)**:
   - Replaces `Math.random` with a 32-bit LCG (`(Math.imul(state, 1664525) + 1013904223) >>> 0`) producing identical `[0, 1)` sequences across contexts (handling `seed=0` safely).

### `CDPTouchDriver` & Chromium's ~33.3 ms Dispatch Cadence
Playwright's `page.touchscreen` exposes only `.tap()`, and synthetic `new PointerEvent(...)` fails `isTrusted` and breaks `setPointerCapture` (`NotFoundError`). `CDPTouchDriver` uses `page.context.new_cdp_session(page)` (`Input.dispatchTouchEvent`) to generate real `isTrusted === true`, `pointerType === 'touch'` pointer streams with proper `setPointerCapture` / `lostpointercapture` lifecycles.

**Critical Empirical Timing Fact (`~33.3 ms` per `touchMove`)**:
In headless Chromium, each sequential `cdp.send("Input.dispatchTouchEvent", ...)` round-trip advances JS `performance.now()` by **~33.3 ms (~30 Hz)** regardless of `time.sleep(0)` or CDP `timestamp` overrides. All `CDPTouchDriver` recipes are calibrated for this cadence across sensitivities `1..10` and cell sizes `24..48 px`:
- `tap(x, y, hold_ms=10.0)` / `tap_element(selector)`: Short tap (`<= 12 px`, `<= 260 ms`) -> clockwise rotate.
- `drag_horizontal(x, y, dx, steps=4, step_sleep_ms=0.0)` / `drag_horizontal_on(...)`: Proportional lateral movement.
- `soft_drop_drag(x, y, total_dy=70.0, steps=10, step_sleep_ms=10.0)` / `soft_drop_on(...)`: Small `7 px` steps per ~33.3 ms frame (`~0.21 px/ms`, strictly `< 0.60 px/ms` and `<= 21 px` per 90 ms window) so it triggers `softDropStep` without ever triggering accidental flick Hard Drop.
- `flick_down(x, y, dy=95.0, hold_after_flick=False)` / `flick_down_on(...)`: 2-step burst (`+10 px` sub-threshold pre-step then `+dy` burst within ~66 ms < 90 ms) guaranteeing `>= 1.44 px/ms` across `S=1..10`; `hold_after_flick=True` appends 3 post-flick continuation moves to verify post-flick pointer lock prevents extra drops/soft-drops.
- `swipe_up_hold(x, y, total_dy=-72.0)` / `swipe_up_hold_on(...)`: 2-step upward burst (`-36 px`, `-72 px` in ~66 ms << 140 ms) triggers Hold cleanly.
- `cancel_touch(x, y, dx=4.0, dy=4.0)` / `cancel_touch_on(...)`: Emits `touchStart -> touchMove -> touchCancel` so tests can verify `pointercancel` cleanup and zero phantom actions.
- `get_stage_points(selector="#board-stage")`: Computes safe interior coordinates inside `#board-stage` bounded by the active viewport for both desktop and tiny (`375×667`) mobile screens.

### SW Offline & Sibling Protection Helpers
- `wait_for_service_worker_controlled(page, timeout_ms=10000)`:
  - Resolves Chromium's `navigator.serviceWorker.ready` `'activating'`/`controller === null` race by waiting until `reg.active.state === 'activated'`, awaiting `controllerchange` if claiming, or performing one online `page.reload()` if `clients.claim()` is not used, before tests enter `context.set_offline(True)`.
  - **Note**: Do NOT attach `page.route()` or `context.route()` handlers to the active game page during SW tests, as Playwright interception can bypass Service Workers.
- `seed_diana_sudoku_sibling(context, origin, ...)` & `read_diana_sudoku_sibling(page, ...)`:
  - Opens a disposable `seed_page`, fulfills a temporary same-origin URL via `seed_page.route(...)`, writes `diana_sudoku_v1` + `diana-sudoku-v1` (plus optional stale `tetris-clasico-*` caches), then unroutes and closes `seed_page` cleanly before opening the game page.

### Canvas, Visibility, Layout & Gameplay Helpers
- **Pillow HiDPI Canvas Helpers**:
  - `capture_element_image(page, selector) -> PIL.Image.Image`
  - `count_diff_pixels(img1, img2, channel_threshold=8) -> int` (C-level `ImageChops`)
  - `images_differ(img1, img2, channel_threshold=8, min_diff_pixels=1) -> bool`
  - `sample_board_grid_state(page, selector="#board-canvas", cols=10, rows=20)` (content-box border/padding crop, 5×5 inner-cell median RGB, adaptive dark background thresholding avoiding translucent Ghost false positives)
  - `detect_top_spawn_piece(page, selector="#board-canvas", top_rows=3)` (identifies spawned piece color + cells purely from rendered top rows)
- **Computed Visibility & Layout**:
  - `is_element_visible(page, selector, require_interactive=False)`: Traverses ancestors for `display: none` and cumulative `opacity <= 0.01`, checks inherited `visibility`, `clip-path: inset(50%...)`, zero bbox, offscreen positions, and `pointer-events`.
  - `get_layout_metrics(page, canvas_selector="#board-canvas", stage_selector=".board-stage")`: Returns viewport dimensions, `scrollWidth`/`scrollHeight` overflow flags, `dpr` & `cappedDpr`, `stageHeightRatio`, CSS vs `clientWidth` vs backing buffer (`hidpiBufferExact`), `touchAction`, `userSelect`, and `overscrollBehavior`.
- **Opaque-Box Gameplay & Controls**:
  - `start_game(page, level=1, timeout_ms=3000)`: Adjusts `#btn-level-up`/`#btn-level-down` until `#start-level-value == level`, clicks `#btn-play`, waits for `#overlay-start` invisibility + render frame.
  - `get_hud_stats(page)`: Parses `{ score, level, lines, best_score, best_level, best_lines }` from DOM text.
  - `get_storage_data(page, key=STORAGE_KEY)` & `get_raw_storage_item(page, key=STORAGE_KEY)`
  - `set_range_value(page, selector, val)`: Uses `locator.fill(str(val))` (reliably fires both `input` and `change` events on `<input type="range">` in Chromium).

---

## 4. 4-Tier Testing Methodology & Areas A–F Matrix

### 4-Tier Structure (+ M7 Tier 5 Hardening)
1. **Tier 1 — Core Functional Sanity**: Baseline smoke checks per area (loads cleanly with zero errors, pieces render/move/drop/score, keyboard/touch/gamepad inputs trigger primary actions, Spanish UI visible).
2. **Tier 2 — Boundary & Edge Behavior**: Protocol gates (`file://` vs subpath `301`), SW offline + *Diana Sudoku* sibling survival, SRS wall-kicks, lock delay resets, 7-bag drought limits, DAS/ARR/SOCD, blur auto-pause, all sensitivity `1..10` extremes, post-flick pointer lock, `touchCancel`, Gamepad `0.30` deadzone, stick-up rejection, corrupt/`QuotaExceededError` storage recovery, HiDPI DPR capping (`<= 2`).
3. **Tier 3 — Cross-Feature Pairwise Combinations**: Interactions across Areas A–F (e.g., subpath + offline + `localStorage` persistence, LCG RNG + Hold + Ghost + Scoring + Level-Up, keyboard + touch sensitivity + settings modal pause/resume, Gamepad + keyboard coexistence + disconnect pause).
4. **Tier 4 — Full Real-World User Journeys**: End-to-end multi-minute player stories (Desktop keyboard marathon + pause/settings + reload record persistence; Mobile portrait touch session with sensitivity adjustment + tiny viewport; Xbox couch session connect/play/disconnect/reconnect; `file://` direct desktop play; GitHub Pages `/tetris-clasico/` PWA offline reload with *Diana Sudoku* sibling data; storage-fault / tiny-viewport resilience).
5. **Tier 5 (M7 Phase 2) — Adversarial Hardening**: Multi-input simultaneous contention, rapid restart/resize/blur stress, extreme boundary inputs after full app integration.

### Feature Inventory -> Area & Milestone Mapping

| Area | Domain | Covered `PROJECT.md` Features | Sub-Milestone (Tiers 1–2) | Tiers 3–4 |
|---|---|---|---|---|
| **Area A** | Runtime, Dual Protocol (`file://` & HTTP/Subpath) & PWA Offline | `F1.1`, `F1.2`, `F1.3`, `F2.8` | `E2E-2` | `E2E-4` |
| **Area B** | Core Tetris Gameplay, SRS, Lock Delay, 7-Bag, Scoring & Persistence | `F2.1`, `F2.2`, `F2.3`, `F2.4`, `F2.5`, `F2.6`, `F2.7`, `F2.8` | `E2E-2` | `E2E-4` |
| **Area C** | Desktop Keyboard Controls, DAS/ARR, SOCD & Focus Safety | `F3.1` | `E2E-2` | `E2E-4` |
| **Area D** | Mobile Touch Gestures, Sensitivity (`1–10`) & Gesture Locking | `F2.8`, `F3.2`, `F3.3`, `F3.4`, `F4.3` | `E2E-3` | `E2E-4` |
| **Area E** | Xbox Gamepad API Integration, Deadzone & Hot-Plug | `F3.5` | `E2E-3` | `E2E-4` |
| **Area F** | HiDPI Visuals, FX, Responsive Modals, Synthesized Audio & Spanish UI | `F4.1`, `F4.2`, `F4.3`, `F5.1`, `F5.2`, `F6.1`, `F2.8` | `E2E-3` | `E2E-4` |
| **All** | Shared Harness & End-to-End Verification | `F7.1` | `E2E-1`..`E2E-3` | `E2E-4`, `M7` |

### E2E File Inventory (Planned & Active)

| File | Milestone | Status | Contents / Purpose |
|---|---|---|---|
| `tests/e2e/__init__.py` | `E2E-1` | Active | Package exports for shared E2E harness symbols |
| `tests/e2e/harness.py` | `E2E-1` | Active | `StaticAppServer`, `TetrisE2EBaseCase`, `PageDiagnostics`, `CDPTouchDriver`, init-script mocks, SW/sibling helpers, Pillow HiDPI visual helpers, layout/visibility/HUD helpers |
| `tests/e2e/test_area_a_runtime_pwa.py` | `E2E-2` | Planned | Area A Tiers 1–2 (`F1.1`–`F1.3`, `F2.8`) |
| `tests/e2e/test_area_b_gameplay.py` | `E2E-2` | Planned | Area B Tiers 1–2 (`F2.1`–`F2.8`) |
| `tests/e2e/test_area_c_keyboard.py` | `E2E-2` | Planned | Area C Tiers 1–2 (`F3.1`) |
| `tests/e2e/test_area_d_mobile_touch.py` | `E2E-3` | Planned | Area D Tiers 1–2 (`F3.2`–`F3.4`, `F4.3`, `F2.8`) |
| `tests/e2e/test_area_e_gamepad.py` | `E2E-3` | Planned | Area E Tiers 1–2 (`F3.5`) |
| `tests/e2e/test_area_f_visual_audio_es.py` | `E2E-3` | Planned | Area F Tiers 1–2 (`F4.1`–`F4.3`, `F5.1`, `F5.2`, `F6.1`, `F2.8`) |
| `tests/e2e/test_tier3_combinations.py` | `E2E-4` | Planned | Pairwise cross-feature combination tests across Areas A–F |
| `tests/e2e/test_tier4_scenarios.py` | `E2E-4` | Planned | >= 6 end-to-end real-world user journey tests |
| `TEST_INFRA.md` | `E2E-1` / `E2E-4` | Active | Infrastructure guide (updated in `E2E-4` with final test counts & inventory) |

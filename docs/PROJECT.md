# Project: Tetris Web Clásico (PC + Móvil + Control Xbox + PWA)

## Architecture
- **Stack**: Vanilla HTML5, CSS3, and ES5/ES6-compatible JavaScript — **zero build step** and **zero external runtime dependencies** (no CDNs, no external audio/image assets, no frameworks).
- **Dual Execution Compatibility (`file://` and `https://` GitHub Pages)**:
  - All asset references, manifest paths, and Service Worker precache URLs MUST be strictly **relative** (`./...` or `js/...`, never leading `/`) to work on both `file:///.../index.html` and GitHub Pages project subpaths (`https://<user>.github.io/<repo>/`).
  - Scripts load sequentially via `<script defer src="js/..."></script>` (NOT `<script type="module">`, which fails under `file://` due to `null`-origin CORS blocks).
  - Every module uses an IIFE attaching to `window.Tetris.<Module>` plus a CommonJS guard (`if (typeof module !== 'undefined' && module.exports) { module.exports = api; }`) so Node.js (`node --test`) can import pure modules directly.
  - **Protocol-gated PWA**: `<link rel="manifest" href="./manifest.webmanifest">` is dynamically injected and `./service-worker.js` is registered **ONLY** when `window.location.protocol === 'http:' || window.location.protocol === 'https:'`, guaranteeing zero console errors on `file://`.
- **Origin Isolation (Sibling Protection for *Diana Sudoku*)**:
  - `localStorage` uses a single namespaced JSON key `'tetris_clasico_v1'` wrapped in `try/catch` with an in-memory fallback.
  - `service-worker.js` uses `CACHE_NAME = 'tetris-clasico-v1'` and during `activate` deletes ONLY caches where `key.startsWith('tetris-clasico-') && key !== CACHE_NAME`.
- **Testing Runtimes**:
  - Pure JS unit tests run with **Node v22 built-in test runner** (`node --test tests/unit/*.test.js`).
  - Browser E2E tests run with **Python 3.12** (`python3 -m unittest discover -s tests/e2e -v`) using Playwright (`playwright 1.65.2`) — NOTE: do NOT use `/opt/pipx/bin/pytest` because its isolated venv lacks `playwright` and `Pillow`.
- **Script Load Order & Dependency Graph**:
  1. `js/constants.js` (`Tetris.Constants`) — no internal deps
  2. `js/audio.js` (`Tetris.Audio`) — no required deps
  3. `js/engine.js` (`Tetris.Engine`) — depends on `Constants`
  4. `js/renderer.js` (`Tetris.Renderer`) — depends on `Constants`
  5. `js/input.js` (`Tetris.Input`) — optional `Constants`
  6. `js/main.js` (`Tetris.Main`) — orchestrates `Constants`, `Audio`, `Engine`, `Renderer`, `Input`, DOM, Storage, and conditional PWA/SW

---

## Feature Inventory

| # | ID | Feature | Description | Milestone | Source |
|---:|---|---|---|---|---|
| 1 | F1.1 | Zero-Build Vanilla Stack | Pure HTML5 + CSS3 + vanilla JS; zero external runtime deps or build tools | M1, M6 | ORIGINAL_REQUEST, Survey 1 |
| 2 | F1.2 | Dual Runtime (`file://` + `https://`) | Ordered `<script defer>` under `window.Tetris`, relative URLs, `.nojekyll`, `.gitignore` | M1, M6 | ORIGINAL_REQUEST, Survey 1 |
| 3 | F1.3 | PWA & Offline Support | `manifest.webmanifest`, vector + PNG icons (`192`, `512`, `512-maskable`, `180`), protocol-gated manifest & `service-worker.js` (`tetris-clasico-v1`) | M1, M6 | ORIGINAL_REQUEST, Survey 1, 2 |
| 4 | F2.1 | Playfield Grid (`10×24`) | 10 columns (`0..9`) × 20 visible rows (`4..23`) + 4 hidden top spawn buffer rows (`0..3`) | M1, M2 | ORIGINAL_REQUEST, Spec Miner |
| 5 | F2.2 | 7-Bag Randomizer | Unbiased Fisher-Yates permutation of `I, O, T, S, Z, J, L` with bag lookahead | M2 | ORIGINAL_REQUEST, Spec Miner |
| 6 | F2.3 | SRS Rotation & Wall-Kicks | Exact 4-state matrices (`0,1,2,3`), CW/CCW, 5-test official kick tables (`JLSTZ`, `I`; `O` invariant) with `+col=right, +row=down` | M1, M2 | ORIGINAL_REQUEST, Spec Miner |
| 7 | F2.4 | Extended Placement Lock Delay | `500 ms` grounded timer reset on successful move/rotate up to `15` resets; restores `15` only when `lowestRow` increases; `O` rotate does not stall | M2 | ORIGINAL_REQUEST, Spec Miner |
| 8 | F2.5 | Ghost, Hold & 3-Next Queue | Translucent Ghost landing projection; Hold swap once per turn (resets rot=0 & spawn pos); 3 upcoming Next pieces | M2, M4 | ORIGINAL_REQUEST, Spec Miner |
| 9 | F2.6 | Marathon Levels (1–15+) & Gravity | Selectable `startLevel` (`1..15`), level-up every 10 lines (`startLevel + Math.floor(lines / 10)`), Guideline gravity curve clamped at `effLevel <= 20` with multi-row `while` loop | M1, M2 | ORIGINAL_REQUEST, Spec Miner |
| 10 | F2.7 | Standard Marathon Scoring & Top-Out | Single `100×L`, Double `300×L`, Triple `500×L`, Tetris `800×L` (pre-clear level); Back-to-Back `×1.5` (Tetrises, preserved across 0-line drops); Combo `+50×combo×L`; Soft `+1/cell`; Hard `+2/cell`; Block Out & Lock Out | M2 | ORIGINAL_REQUEST, Spec Miner |
| 11 | F2.8 | Namespaced `localStorage` Persistence | Safe `try/catch` storage (`tetris_clasico_v1`) with in-memory fallback for `bestScore`, `bestLevel`, `bestLines`, `touchSensitivity`, `musicEnabled`, `sfxEnabled`, `startLevel` | M1, M6 | ORIGINAL_REQUEST, Survey 1, 2 |
| 12 | F3.1 | Desktop Keyboard Controls | `←/→` (`DAS 160ms`/`ARR 35ms`, SOCD last-dir priority), `↓` (`<=40ms` Soft Drop), `↑/X` (CW), `Z` (CCW), `Space` (Hard Drop), `C/Shift` (Hold), `P/Esc` (Pause); `preventDefault`, button `.blur()`, `blur`/`visibilitychange` auto-pause | M5, M6 | ORIGINAL_REQUEST, Survey 2 |
| 13 | F3.2 | Mobile Touch Gestures | Board-stage Pointer Events: proportional lateral drag, short tap rotate (`<=12px, <=260ms`), slow down drag Soft Drop, velocity/dist-calibrated down Flick Hard Drop (post-flick pointer lock), Hold box tap or upward swipe | M5, M6 | ORIGINAL_REQUEST, Survey 2 |
| 14 | F3.3 | Touch Sensitivity Slider (`1–10`) | Slider (`1..10`, default `5`) in Settings scaling lateral `pxPerCell`, soft-drop step, and flick thresholds, persisted immediately | M5, M6 | ORIGINAL_REQUEST, Survey 2 |
| 15 | F3.4 | Browser Gesture Locking | CSS `touch-action: none`, `overscroll-behavior: none`, `user-select: none`, `100dvh` + `viewport-fit=cover` | M6 | ORIGINAL_REQUEST, Survey 2 |
| 16 | F3.5 | Xbox Gamepad API Support | `gamepadconnected`/`gamepaddisconnected` + per-frame `getGamepads()` polling, `0.30` X deadzone + DAS/ARR, `0.45` Y Soft Drop, `D-Pad ↑` rising-edge Hard Drop (stick up ignored), `A/B` CW, `X` CCW, `LB/RB` Hold, `Menu/Start` Pause, HUD & Settings badge | M5, M6 | ORIGINAL_REQUEST, Survey 2 |
| 17 | F4.1 | Dark Glassmorphism & HiDPI Canvas | Dark neon/glass aesthetic, `devicePixelRatio` (`<=2`) HiDPI integer-cell canvas, shaded blocks, Ghost, Hold & 3-Next rendering | M4, M6 | ORIGINAL_REQUEST, Survey 2 |
| 18 | F4.2 | Visual FX & Callouts | Line-clear flash/sweep + particles, Hard Drop light trail/impact, floating callouts (`TETRIS!`, `BACK TO BACK`, `COMBO ×N`, `LEVEL UP!`) | M4 | ORIGINAL_REQUEST, Survey 2 |
| 19 | F4.3 | Responsive Layouts & Modals | Desktop 3-column layout; Mobile compact top bar + **80%+ viewport height/area** board stage; Start (level 1–15), Pause, Game Over, Settings modal (sensitivity, audio toggles, Xbox status, visual controls guide) | M6 | ORIGINAL_REQUEST, Survey 2 |
| 20 | F5.1 | Synthesized Web Audio SFX | 100% Web Audio synthesis (zero files): move, rotate, softDrop/land, hardDrop, lock, lineClear (1–3), tetris (4), hold, levelUp, gameOver | M3 | ORIGINAL_REQUEST, Spec Miner |
| 21 | F5.2 | Chiptune *Korobeiniki* Loop | 24-bar `A-A-B` `144 BPM` `4/4` lead + bass Web Audio lookahead scheduler (`25ms/120ms`), auto-pause on Pause/Game Over, independent Music/SFX switches | M3, M6 | ORIGINAL_REQUEST, Spec Miner |
| 22 | F6.1 | Spanish UI & GitHub Pages README | 100% Spanish UI, ARIA labels, PWA metadata, and `README.md` with local play + GitHub Pages + mobile install instructions | M1, M6 | ORIGINAL_REQUEST, Survey 1, 2 |
| 23 | F7.1 | Requirement-Driven E2E Suite | Opaque-box Playwright E2E suite (Tiers 1–4) + Tier 5 adversarial hardening covering `file://`, HTTP/PWA offline, keyboard, mobile touch+sensitivity, Xbox gamepad, gameplay, and visual budgets | E2E, M7 | ORIGINAL_REQUEST, Survey 1 |

---

## Code Layout

```text
/home/antigravity/
├── PROJECT.md
├── TEST_INFRA.md                     (created by E2E Testing Orchestrator)
├── TEST_READY.md                     (created by E2E Testing Orchestrator when ready)
├── index.html                        (M6)
├── styles.css                        (M6)
├── manifest.webmanifest              (M1)
├── service-worker.js                 (M1)
├── .nojekyll                         (M1)
├── .gitignore                        (M1)
├── README.md                         (M6)
├── icons/                            (M1)
│   ├── icon.svg
│   ├── icon-192.png
│   ├── icon-512.png
│   ├── icon-512-maskable.png
│   └── apple-touch-icon.png
├── js/
│   ├── constants.js                  (M1)
│   ├── engine.js                     (M2)
│   ├── audio.js                      (M3)
│   ├── renderer.js                   (M4)
│   ├── input.js                      (M5)
│   └── main.js                       (M6)
└── tests/
    ├── unit/
    │   ├── constants.test.js         (M1)
    │   ├── engine.test.js            (M2)
    │   ├── audio.test.js             (M3)
    │   ├── renderer.test.js          (M4)
    │   ├── input.test.js             (M5)
    │   └── main_storage.test.js      (M6)
    └── e2e/                          (E2E Testing Track + M7 Tier 5)
        └── ...
```

---

## Milestones

| # | Name | Scope | Dependencies | Status | Sub-orch Conv ID |
|---|---|---|---|---|---|
| M1 | Constants, PWA & Assets | `js/constants.js`, `manifest.webmanifest`, `service-worker.js`, `icons/*`, `.nojekyll`, `.gitignore`, `tests/unit/constants.test.js` | none | DONE (28/28 unit tests) | `f1722217f62d9e2724d9756c29f636ad` |
| M2 | Core Game Engine | `js/engine.js`, `tests/unit/engine.test.js` | M1 | DONE (7/7 unit tests) | `68d1c74ab1e6832f1d8fab9396b4255c` |
| M3 | Procedural Web Audio Engine | `js/audio.js`, `tests/unit/audio.test.js` | M1 | DONE (2/2 unit tests) | `1a3a95caeb012c7094213cecd6ec0a04` |
| M4 | HiDPI Canvas Renderer & FX | `js/renderer.js`, `tests/unit/renderer.test.js` | M1 | DONE (1/1 unit test) | `39aa43ac35dd69ace4e34611b8e694da` |
| M5 | Unified Input System | `js/input.js`, `tests/unit/input.test.js` | M1 | DONE (3/3 unit tests) | `6aca800b69381971811127d61b19b8e2` |
| M6 | App Shell, UI, Orchestration & Docs | `index.html`, `styles.css`, `js/main.js`, `README.md`, `tests/unit/main_storage.test.js` | M1, M2, M3, M4, M5 | DONE (2/2 unit tests) | — |
| M7 | Final Milestone: E2E Pass & Hardening | Areas A–F Tiers 1–2 E2E pass (`66/66`); Tiers 3–5 optional | M6 | DONE (Areas A–F 66/66 pass) | — |
| E2E | E2E Testing Track | `TEST_INFRA.md`, `tests/e2e/harness.py`, `tests/e2e/test_area_*.py` | none (runs in parallel) | DONE (Areas A–F 66/66 pass) | `938c8c056237cebec196dc8a6e606deb` |

---

## Interface Contracts

### 1. Module Pattern (`js/*.js`)
```js
(function (root) {
  'use strict';
  var Constants = (root.Tetris && root.Tetris.Constants) || (typeof require === 'function' ? require('./constants.js') : null);
  // ...
  root.Tetris = root.Tetris || {};
  root.Tetris.<ModuleName> = api;
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
})(typeof globalThis !== 'undefined' ? globalThis : this);
```

### 2. `Tetris.Constants` (`js/constants.js`)
- Grid: `COLS = 10`, `VISIBLE_ROWS = 20`, `BUFFER_ROWS = 4`, `TOTAL_ROWS = 24` (`rows 0..3` hidden buffer, `rows 4..23` visible).
- `PIECE_TYPES = ['I', 'O', 'T', 'S', 'Z', 'J', 'L']`
- `SHAPES`: `{ I: [4x4 x 4], O: [2x2 x 4], T: [3x3 x 4], S: [3x3 x 4], Z: [3x3 x 4], J: [3x3 x 4], L: [3x3 x 4] }` (states `0=spawn, 1=R, 2=2, 3=L`, CW rotation `rotCW[r][c] = m[N-1-c][r]`).
- `SPAWN_POS`: `{ I: { col: 3, row: 2 }, O: { col: 4, row: 2 }, T: { col: 3, row: 2 }, S: { col: 3, row: 2 }, Z: { col: 3, row: 2 }, J: { col: 3, row: 2 }, L: { col: 3, row: 2 } }`
- `COLORS`: `{ I, O, T, S, Z, J, L }` each `{ fill, light, dark, glow, ghostFill, ghostStroke }` (modern high-contrast neon/glass colors: `I:#22d3ee`, `O:#facc15`, `T:#c084fc`, `S:#4ade80`, `Z:#f87171`, `J:#60a5fa`, `L:#fb923c`).
- `WALL_KICKS`: `{ JLSTZ: { '0>1', '1>0', '1>2', '2>1', '2>3', '3>2', '3>0', '0>3' }, I: { same 8 keys }, O: { same 8 keys -> [[0,0]] } }` using `[dCol, dRow]` where **`+dCol = right`, `+dRow = DOWN`**.
- Timing & Gameplay Constants:
  - `LOCK_DELAY_MS = 500`, `MAX_LOCK_RESETS = 15`, `LINES_PER_LEVEL = 10`
  - `MIN_START_LEVEL = 1`, `MAX_START_LEVEL = 15`, `MAX_GRAVITY_LEVEL = 20`
  - `DAS_MS = 160`, `ARR_MS = 35`, `SOFT_DROP_REPEAT_MS = 40`
  - `GAMEPAD_DEADZONE_X = 0.30`, `GAMEPAD_SOFT_DROP_Y = 0.45`
  - `TOUCH_SENSITIVITY_MIN = 1`, `TOUCH_SENSITIVITY_MAX = 10`, `TOUCH_SENSITIVITY_DEFAULT = 5`
  - `NEXT_PREVIEW_COUNT = 3`
- Scoring: `LINE_SCORES = { 1: 100, 2: 300, 3: 500, 4: 800 }`, `B2B_MULTIPLIER = 1.5`, `COMBO_BASE = 50`, `SOFT_DROP_POINTS = 1`, `HARD_DROP_POINTS = 2`.
- Storage & Cache: `STORAGE_KEY = 'tetris_clasico_v1'`, `CACHE_NAME = 'tetris-clasico-v1'`, `DEFAULT_STATE = { bestScore: 0, bestLevel: 0, bestLines: 0, touchSensitivity: 5, musicEnabled: true, sfxEnabled: true, startLevel: 1 }`.
- Helpers:
  - `getGravityMs(level)`: `eff = Math.max(1, Math.min(MAX_GRAVITY_LEVEL, Math.floor(level || 1)))`, `Math.pow(0.8 - (eff - 1) * 0.007, eff - 1) * 1000`.
  - `getSoftDropMs(level)`: `Math.min(SOFT_DROP_REPEAT_MS, getGravityMs(level))` (ensures soft drop is never slower than native gravity).

### 3. `Tetris.Engine` (`js/engine.js`)
- `createEngine({ rng = Math.random, nextCount = 3 } = {})`:
  - `start(startLevel = 1)` -> initializes clean 10×24 board, bag, spawns first piece (with Guideline immediate 1-row spawn drop if clear), sets `status = 'playing'`, returns `{ events }`.
  - `pause()`, `resume()`, `togglePause()`, `reset()`
  - `step(dtMs)` -> clamps/accumulates gravity & soft drop (`while` loop for multi-row >1G drops!), advances lock timer when grounded, locks & scores & levels up & checks top-out. Returns `{ events }`.
  - `moveLeft()`, `moveRight()` -> returns `{ changed, events }` (updates lock delay via Extended Placement: only resets timer if `lockMovesRemaining > 0`, decrements remaining).
  - `rotateCW()`, `rotateCCW()` -> returns `{ changed, kicked, events }` (`O` is invariant no-op and does NOT reset lock delay; `I/J/L/S/T/Z` test 5 kicks and apply Extended Placement if moved/rotated).
  - `setSoftDrop(active)` -> enables/disables held soft drop.
  - `softDropStep()` -> single immediate 1-row downward step (awards `+1` pt if descended; used by mobile downward drag). Returns `{ changed, events }`.
  - `hardDrop()` -> drops immediately to `ghostY`, awards `+2 * dropRows`, locks immediately (`0ms`), clears/scores, spawns next. Returns `{ changed, events }`.
  - `hold()` -> swaps active piece with `holdPiece` (once per turn; resets rotation `0` & spawn pos + immediate 1-row drop; checks Block Out). Returns `{ changed, events }`.
  - `getGhostY()` -> integer row `>= active.row`.
  - `getSnapshot()` -> `{ status: 'menu'|'playing'|'paused'|'gameover', gameOverReason: null|'block_out'|'lock_out', board, activePiece: { type, rot, col, row, matrix } | null, ghostY, holdPiece, canHold, nextQueue, score, level, startLevel, lines, combo, backToBack, lockTimerMs, lockDelayMs, lockMovesRemaining, isGrounded }`.
- Emitted `EngineEvent` union:
  - `{ type: 'move', dir: -1|1 }`
  - `{ type: 'rotate', kicked: boolean }`
  - `{ type: 'hold', piece: string }`
  - `{ type: 'softDrop', cells: number }`
  - `{ type: 'hardDrop', piece: string, col: number, width: number, startY: number, endY: number, cells: number }`
  - `{ type: 'lock', piece: string, cells: Array<{col, row}> }`
  - `{ type: 'lineClear', count: 1|2|3|4, rows: number[], points: number, basePoints: number, comboBonus: number, isTetris: boolean, isBackToBack: boolean, combo: number, preClearLevel: number }`
  - `{ type: 'levelUp', level: number }`
  - `{ type: 'gameOver', reason: 'block_out'|'lock_out', score: number, level: number, lines: number }`

### 4. `Tetris.Audio` (`js/audio.js`)
- Pure exported constants (for Node verification): `KOROBEINIKI_BPM = 144`, `KOROBEINIKI_LEAD` (24 bars, each bar summing to `4.0` beats, total `96` beats), `KOROBEINIKI_BASS` (24 bars, `4.0` beats each), `NOTE_FREQS`.
- `createAudioController({ musicEnabled = true, sfxEnabled = true } = {})`:
  - `unlock()` -> safely creates/resumes `AudioContext` on user gesture; silent no-op if unavailable.
  - `setMusicEnabled(enabled)`, `setSfxEnabled(enabled)`, `isMusicEnabled()`, `isSfxEnabled()`.
  - `playSfx(name)` (`'move'|'rotate'|'softDrop'|'hardDrop'|'lock'|'lineClear'|'tetris'|'hold'|'levelUp'|'gameOver'`).
  - `handleEvents(events)` -> triggers corresponding SFX cleanly (avoids spamming `lock` when `tetris`/`lineClear` plays or layers cleanly; plays `levelUp` & `gameOver`).
  - `syncState(status)` -> starts/resumes *Korobeiniki* 25ms/120ms lookahead scheduler when `status === 'playing' && musicEnabled`; immediately stops active music oscillators & resets scheduler when paused/menu/gameover/muted.
  - `dispose()` -> clears scheduler interval & closes AudioContext safely.

### 5. `Tetris.Renderer` (`js/renderer.js`)
- `createRenderer({ boardCanvas, holdCanvas, nextCanvas, boardStage })`:
  - `resize()` -> measures `.board-stage` available W/H, picks integer `cellCssSize = Math.max(12, Math.floor(Math.min(availW / 10, availH / 20)))`, caps `dpr = Math.min(window.devicePixelRatio || 1, 2)`, updates canvas CSS & backing buffer sizes (`Math.round(css * dpr)`), resizes `#hold-canvas` & `#next-canvas` (adapts next layout vertically on desktop, horizontally in compact mobile portrait top bar!).
  - `triggerEffects(events)` -> spawns non-blocking line-clear row flashes + neon particles (capped `<= 120`), hard-drop vertical trail, and floating callouts (`¡TETRIS!`, `BACK TO BACK`, `COMBO ×N`, `¡NIVEL N!` / `LEVEL UP!`).
  - `render(snapshot, dtMs)` -> draws grid, locked blocks, ghost piece, active piece (subtle lock progress pulse), hold piece (dimmed when `!canHold`), 3-piece Next queue, and active particles/callouts.
  - `getBoardMetrics()` -> `{ cellSize, width, height, rect }`.
  - `resetEffects()` / `dispose()`.

### 6. `Tetris.Input` (`js/input.js`)
- Pure Node-testable exports:
  - `computeTouchThresholds(sensitivity = 5, cellSizePx = 32)` -> `{ sensitivity, pxPerCell, softDropStepPx, flickMinDistPx, flickMinVelPxPerMs, flickWindowMs: 90, holdSwipeMinPx, holdWindowMs: 140, tapMaxDistPx: 12, tapMaxDurationMs: 260 }`
  - `applyDeadzone(value, deadzone = 0.30)` -> `0` if `Math.abs(value) < deadzone`, else normalized/pass-through value.
  - `createDasArrState(dasMs = 160, arrMs = 35)` -> `{ press(dir), release(dir), reset(), update(dtMs) -> { steps, dir } }` (SOCD last-input priority).
- Runtime `createInputController({ boardElement, holdElement, getBoardMetrics, getGameStatus, isModalOpen, onAction, onUserGesture, onGamepadChange, sensitivity = 5 })`:
  - `onAction(action)` emits: `'moveLeft' | 'moveRight' | 'softDropStart' | 'softDropEnd' | 'softDropStep' | 'hardDrop' | 'rotateCW' | 'rotateCCW' | 'hold' | 'pauseToggle' | 'confirmStart'`
  - `onGamepadChange({ connected, isXbox, id, mapping, label })`
  - `setSensitivity(value)` (clamped `1..10`)
  - `update(dtMs)` (updates keyboard DAS/ARR + polls `navigator.getGamepads()` every frame + gamepad DAS/ARR + rising-edge buttons)
  - `clearAll()` (used on `blur`/`visibilitychange`/`pagehide`/pause transitions)
  - `destroy()`

### 7. App Shell, Storage & Spanish DOM Contracts (`index.html`, `styles.css`, `js/main.js`)
- `<html lang="es">`, `<title>Tetris Clásico</title>`
- Core DOM hooks (semantic, accessible, Spanish `aria-label`s):
  - `#board-stage` (`.board-stage` touch surface, `touch-action: none`) containing `#board-canvas`
  - `#hold-box` (`<button type="button" id="hold-box">`) containing `#hold-canvas`
  - `#next-canvas`
  - Live HUD: `#score-value`, `#level-value`, `#lines-value`, `#best-score-value`, `#best-level-value`, `#best-lines-value`
  - Top/Action buttons: `#btn-pause`, `#btn-settings`, `#btn-music`, `#btn-sfx` (all call `.blur()` on click)
  - Gamepad indicator: `#gamepad-badge` (HUD) & `#settings-gamepad-status` (Settings modal)
  - Overlays/Modals:
    - `#overlay-start` (`#btn-level-down`, `#start-level-value`, `#btn-level-up`, `#btn-play`, `#btn-start-settings`)
    - `#overlay-pause` (`#btn-resume`, `#btn-pause-settings`, `#btn-restart`)
    - `#overlay-gameover` (`#final-score-value`, `#final-level-value`, `#final-lines-value`, `#gameover-record-badge`, `#btn-play-again`, `#btn-gameover-settings`)
    - `#modal-settings` (`#sensitivity-slider` `min=1 max=10`, `#sensitivity-value`, `#toggle-music`, `#toggle-sfx`, `#settings-gamepad-status`, controls guide tabs/sections `Teclado`/`Táctil`/`Control Xbox`, `#btn-close-settings`)
- Mobile Viewport Budget (`<= 820px` portrait):
  - `100dvh` flex column; compact top bar `<= 88px` leaving **>= 80%** of `window.innerHeight` for `.board-stage` with zero overflow (`scrollWidth <= innerWidth`, `scrollHeight <= innerHeight`).

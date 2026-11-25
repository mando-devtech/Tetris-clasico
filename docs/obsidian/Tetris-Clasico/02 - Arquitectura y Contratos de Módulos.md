---
title: "Arquitectura y Contratos de Módulos"
tags:
  - proyecto/tetris-clasico
  - arquitectura
  - contratos
updated: 2026-11-25
---

# 02 — Arquitectura y Contratos de Módulos

Volver a [[00 - Tetris Clásico (Brain Maestro)]].

## 1. Estructura de Archivos del Proyecto

```text
tetris-clasico/
├── index.html                  # Shell HTML5 semántico en español + carga defer
├── styles.css                  # Tema oscuro Glassmorphism, responsivo PC/Móvil (>=80% tablero)
├── manifest.webmanifest        # Manifiesto PWA con rutas relativas
├── service-worker.js           # Caché offline aislado (tetris-clasico-v1)
├── .nojekyll                   # Evita procesamiento Jekyll en GitHub Pages
├── .gitignore
├── README.md                   # Guía local + publicación GitHub Pages
├── index_unico.html            # (Generado aparte) Bundle autocontenido de 118 KB en un solo archivo
├── icons/
│   ├── icon.svg
│   ├── icon-192.png
│   ├── icon-512.png
│   ├── icon-512-maskable.png
│   └── apple-touch-icon.png
├── js/
│   ├── constants.js            # Tetris.Constants
│   ├── audio.js                # Tetris.Audio
│   ├── engine.js               # Tetris.Engine
│   ├── renderer.js             # Tetris.Renderer
│   ├── input.js                # Tetris.Input
│   └── main.js                 # Tetris.Main
└── tests/
    ├── unit/                   # 6 archivos (43 tests con node --test)
    └── e2e/                    # Harness + 6 áreas (66 tests Playwright)
```

---

## 2. Patrón de Módulos y Compatibilidad Dual

Cada módulo JS utiliza una **IIFE** compatible simultáneamente con navegador (`file://` y `https://`) y Node.js (`node --test`):

```js
(function (root) {
  'use strict';
  // ...
  root.Tetris = root.Tetris || {};
  root.Tetris.<Modulo> = api;
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
})(typeof globalThis !== 'undefined' ? globalThis : this);
```

- **Orden estricto de carga en `index.html`:** `constants.js` → `audio.js` → `engine.js` → `renderer.js` → `input.js` → `main.js`.
- **PWA condicional (`registerPwaIfHttp`):** solo inyecta `manifest.webmanifest` y registra `service-worker.js` cuando `location.protocol` es `http:` o `https:`. En `file://` no genera errores de consola.

---

## 3. Contratos por Módulo

### `js/constants.js` (`Tetris.Constants`)
- **Tablero:** `COLS = 10`, `VISIBLE_ROWS = 20`, `BUFFER_ROWS = 4`, `TOTAL_ROWS = 24`.
- **Piezas:** `I, O, T, S, Z, J, L` con sus 4 estados SRS (`0..3`) y `SPAWN_POS` en filas de buffer `2..3`.
- **Wall-Kicks (`WALL_KICKS`):** tablas oficiales `JLSTZ`, `I` y `O` usando `[dCol, dRow]` con `+dCol = derecha` y `+dRow = abajo`.
- **Tiempos y constantes:**
  - `LOCK_DELAY_MS = 500`, `MAX_LOCK_RESETS = 15`, `LINES_PER_LEVEL = 10`
  - `DAS_MS = 160`, `ARR_MS = 35`, `SOFT_DROP_REPEAT_MS = 40`
  - `GAMEPAD_DEADZONE_X = 0.30`, `GAMEPAD_SOFT_DROP_Y = 0.45`
  - `TOUCH_SENSITIVITY_MIN = 1`, `MAX = 10`, `DEFAULT = 5`
- **Curva de gravedad (`getGravityMs(level)`):** fórmula Guideline `((0.8 - (eff - 1) * 0.007) ^ (eff - 1)) * 1000` con `eff` acotado a `1..20`.

### `js/engine.js` (`Tetris.Engine`)
- `createEngine({ rng, nextCount })` mantiene todo el estado de partida sin tocar el DOM.
- Implementa **7-Bag** (Fisher-Yates), caída por gravedad multi-fila (`while` para niveles >1G), *Extended Placement Lock Delay*, *Hold* (reinicia rotación a `0`), *Hard Drop* (`+2/celda`), *Soft Drop* (`+1/celda`), detección de `block_out` / `lock_out` y puntuación con `Combo` y `Back-to-Back`.
- Emite eventos estructurados (`move`, `rotate`, `hold`, `softDrop`, `hardDrop`, `lock`, `lineClear`, `levelUp`, `gameOver`) consumidos por `Audio` y `Renderer`.

### `js/audio.js` (`Tetris.Audio`)
- Sintetiza en tiempo real vía `AudioContext` (osciladores `square`, `triangle`, `sine`, `sawtooth` + envolventes `GainNode`).
- Scheduler con *lookahead* (`25 ms` / `120 ms`) para **Korobeiniki** a `144 BPM` (`24` compases `A-A-B`, `96` tiempos en total, voz principal + bajo).
- Pausa y limpia osciladores activos inmediatamente al pausar, silenciar o terminar la partida.

### `js/renderer.js` (`Tetris.Renderer`)
- Calcula tamaño entero de celda (`Math.max(12, Math.floor(Math.min(availW/10, availH/20)))`) y limita `devicePixelRatio` a `<= 2`.
- Adapta `#next-canvas` verticalmente en escritorio (`96×228`) y horizontalmente en móvil (`126×44`).
- Renderiza cuadrícula, bloques con bisel/brillo, pieza fantasma, pulso sutil de *lock delay*, partículas (`<= 120`), estela de *Hard Drop* y textos flotantes (`¡TETRIS!`, `BACK TO BACK`, `COMBO ×N`, `¡NIVEL N!`).

### `js/input.js` (`Tetris.Input`)
- **`computeTouchThresholds(sensitivity, cellSizePx)`:** escala `factor = 1.5 - (s - 1) * (0.9 / 9)` para adaptar `pxPerCell`, `softDropStepPx`, `flickMinDistPx`, `holdSwipeMinPx` y `flickMinVelPxPerMs` (`0.42` en S=1 a `0.28` en S=10, ventana `260 ms`).
- **Bloqueo post-flick:** tras disparar `hardDrop` o `hold` por deslizamiento, bloquea el puntero hasta `pointerup` para no mover ni soltar la siguiente pieza.
- **Gamepad API:** sondea `navigator.getGamepads()` cada frame y escucha `gamepadconnected`/`gamepaddisconnected`; aplica `deadzone 0.30`, *DAS/ARR* lateral y detección de flanco de subida (*rising edge*) en botones.

### `js/main.js` (`Tetris.Main`)
- Persistencia bajo `'tetris_clasico_v1'` con sanitización de rangos (`sanitizeState`) y respaldo en memoria si `localStorage` falla o está corrupto.
- Estructura JSON guardada:
  ```json
  {
    "bestScore": 0,
    "bestLevel": 0,
    "bestLines": 0,
    "touchSensitivity": 5,
    "musicEnabled": true,
    "sfxEnabled": true,
    "startLevel": 1
  }
  ```

Ver resultados de pruebas en [[03 - Historial de Pruebas y Calidad]].

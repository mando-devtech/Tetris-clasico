---
title: "Tetris Clásico — Brain Completo (Obsidian)"
aliases:
  - "Tetris Clásico"
  - "Tetris Brain"
tags:
  - proyecto/tetris-clasico
  - brain
  - documentacion
status: completado-listo-para-despliegue
repo: "https://github.com/mando-devtech/Tetris-clasico"
url_pages: "https://mando-devtech.github.io/Tetris-clasico/"
updated: 2026-11-25
---

# Tetris Clásico — Documentación Completa (Brain para Obsidian)

> [!info] Cómo usar este archivo
> Guarda este archivo `.md` dentro de tu vault de Obsidian (por ejemplo en `Proyectos/Tetris-Clasico/Tetris Clásico - Brain.md`). Contiene todo el historial, decisiones, contratos técnicos, resultados de pruebas y pasos de despliegue para retomar el proyecto al instante en cualquier sesión futura.

---

## 1. Resumen Ejecutivo (Contexto Rápido)

- **Qué es:** Aplicación web moderna del **Tetris clásico** en español (`<html lang="es">`), **cero dependencias externas** y **sin paso de compilación**.
- **Compatibilidad dual:** Funciona abriendo `index.html` directo con `file://` en PC y publicado en **GitHub Pages** (`https://mando-devtech.github.io/Tetris-clasico/`) como **PWA instalable** en celular.
- **Aislamiento con proyecto hermano (*Diana Sudoku*):**
  - `localStorage` bajo clave única: `'tetris_clasico_v1'`
  - Caché de Service Worker única: `'tetris-clasico-v1'` (solo limpia `tetris-clasico-*`, nunca toca `diana-sudoku-*`).
- **Estado actual:** Implementado y probado. Entregable único autocontenido (`index_unico.html`, 118 KB) + proyecto modular completo (`index.html`, `styles.css`, `js/*`, `icons/*`, `tests/*`).

---

## 2. Requisitos y Decisiones de Diseño

| Área | Decisión elegida | Detalle clave |
| :--- | :--- | :--- |
| **Alojamiento** | GitHub Pages + ejecución local directa | Compatible con `https://` en subruta (`/Tetris-clasico/`) y `file://`. |
| **Stack técnico** | HTML5 + CSS3 + JavaScript puro | Sin Node/Vite en runtime; `<script defer>` (no `type="module"`) para evitar CORS en `file://`. |
| **Reglas de juego** | Tetris moderno estándar (Guideline) | *7-Bag*, SRS con *wall-kicks*, *Lock Delay* 500 ms (15 reinicios), *Ghost*, *Hold* (1/turno) y 3 próximas piezas. |
| **Modo y progresión** | Modo Maratón (nivel inicial `1–15`) | Sube de nivel cada 10 líneas; récords (`bestScore`, `bestLevel`, `bestLines`) en `localStorage`. |
| **Controles PC** | Teclado estándar | `←/→` (`DAS 160 ms` / `ARR 35 ms`), `↓` soft drop, `↑/X` rotar der., `Z` rotar izq., `Espacio` hard drop, `C/Shift` hold, `P/Esc` pausa. |
| **Controles Celular** | **Solo gestos** sobre el tablero + Slider de sensibilidad (`1–10`) | Arrastrar `←/→` mueve por celda, tap corto rota, arrastrar `↓` soft drop, flick rápido `↓` hard drop (con bloqueo post-flick), tap en Hold o swipe `↑` guarda pieza. |
| **Control Xbox** | **Gamepad API** (USB/Bluetooth en PC y móvil) | `D-Pad/Stick ←→` mover, `D-Pad/Stick ↓` soft drop, `D-Pad ↑` hard drop (stick arriba ignorado), `A/B` rotar der., `X` rotar izq., `LB/RB` hold, `Menú/Start` pausa. |
| **Diseño visual** | Oscuro moderno (*Glassmorphism* + neón sutil) | Escritorio 3 columnas; móvil con barra superior compacta y **>= 80%** del alto de pantalla para `#board-stage`, `touch-action: none`. |
| **Audio** | Web Audio API (SFX + *Korobeiniki*) | 100% sintetizado por código (24 compases, 144 BPM); interruptores independientes para Música y Efectos. |
| **PWA Móvil** | Instalable en GitHub Pages | `manifest.webmanifest` + `service-worker.js` registrados únicamente en `http:`/`https:`. |

---

## 3. Arquitectura y Contratos Técnicos

```text
tetris-clasico/
├── index.html                  # Shell HTML5 semántico en español + carga defer
├── styles.css                  # Tema oscuro Glassmorphism, responsivo PC/Móvil
├── manifest.webmanifest        # Manifiesto PWA con rutas relativas
├── service-worker.js           # Caché offline aislado (tetris-clasico-v1)
├── .nojekyll                   # Evita procesamiento Jekyll en GitHub Pages
├── .gitignore
├── README.md
├── icons/                      # icon.svg, icon-192.png, icon-512.png, icon-512-maskable.png, apple-touch-icon.png
├── js/
│   ├── constants.js            # Tetris.Constants (10x24, SRS wall-kicks, gravedad, puntaje)
│   ├── audio.js                # Tetris.Audio (SFX + Korobeiniki Web Audio scheduler)
│   ├── engine.js               # Tetris.Engine (7-bag, SRS, lock delay, hold, combo, B2B)
│   ├── renderer.js             # Tetris.Renderer (Canvas HiDPI <=2x, partículas, callouts)
│   ├── input.js                # Tetris.Input (teclado DAS/ARR, gestos 1-10, Xbox Gamepad)
│   └── main.js                 # Tetris.Main (RAF loop, UI/modales, localStorage, PWA condicional)
└── tests/
    ├── unit/                   # 6 archivos (43 tests Node)
    └── e2e/                    # Harness + 6 áreas (66 tests Playwright)
```

### Esquema `localStorage` (`tetris_clasico_v1`)
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

### Parámetros clave de `Tetris.Input`
- `computeTouchThresholds(sensitivity, cellSizePx)` usa `factor = 1.5 - (s - 1) * (0.9 / 9)` para calcular `pxPerCell`, `softDropStepPx`, `flickMinDistPx`, `holdSwipeMinPx` y `flickMinVelPxPerMs` (`0.42` en S=1 a `0.28` en S=10, ventana `260 ms`).
- Tras disparar `hardDrop` o `hold` por deslizamiento, se bloquea el puntero hasta `pointerup` para evitar mover o soltar la pieza siguiente.
- Gamepad Xbox aplica `deadzone 0.30` en eje X, `0.45` en eje Y para soft drop, y detección de flanco de subida en botones.

---

## 4. Historial de Pruebas y Calidad

- **Pruebas unitarias (`node --test tests/unit/*.test.js`):** **43 / 43 aprobadas** (13 suites: `constants`, `engine`, `input`, `main_storage`, `audio`, `renderer`).
- **Pruebas E2E en navegador (`Playwright + Chromium`):** **66 / 66 aprobadas** en verificación local:
  - Área A (Runtime `file://`, PWA, GitHub Pages, aislamiento *Diana Sudoku*): **10 / 10**
  - Área B (Jugabilidad, 7-bag, SRS, Lock Delay, líneas): **12 / 12**
  - Área C (Teclado PC, DAS/ARR, SOCD, auto-pausa): **10 / 10**
  - Área D (Móvil, gestos táctiles, sensibilidad 1–10 y presupuesto >=80%): **12 / 12**
  - Área E (Control Xbox Gamepad API): **11 / 11**
  - Área F (Audio Web Audio, HiDPI, idioma español, récords): **11 / 11**
- **Bundle autocontenido (`index_unico.html`):** Probado en Playwright bajo `file://` con **0 errores de consola** y **0 errores de página**.

---

## 5. Despliegue en GitHub Pages y Próximos Pasos

- **Repositorio GitHub:** `https://github.com/mando-devtech/Tetris-clasico`
- **Publicación rápida con el HTML único:**
  1. Subir `index.html` en `Add file → Upload files` dentro de `mando-devtech/Tetris-clasico`.
  2. Activar **Settings → Pages → Deploy from a branch → `main` / `/ (root)`**.
  3. Jugar en PC o celular en `https://mando-devtech.github.io/Tetris-clasico/`.
- **Ideas futuras:**
  - Subir la carpeta modular completa (con `manifest.webmanifest`, `service-worker.js`, `icons/`, `.nojekyll`) para activar instalación PWA offline completa.
  - Modos **Sprint 40 líneas**, **Ultra 2 min** y **Modo Zen**.
  - Remapeo de botones de Xbox/teclado y T-Spins + vibración háptica en móvil.

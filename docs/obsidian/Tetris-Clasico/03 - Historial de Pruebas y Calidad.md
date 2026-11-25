---
title: "Historial de Pruebas y Calidad"
tags:
  - proyecto/tetris-clasico
  - testing
  - qa
updated: 2026-11-25
---

# 03 — Historial de Pruebas y Calidad

Volver a [[00 - Tetris Clásico (Brain Maestro)]].

## 1. Pruebas Unitarias (Node.js `node --test`)
Comando: `node --test tests/unit/*.test.js`

- **Resultado:** **43 / 43 aprobadas (13 suites, 0 fallos)**
  - `constants.test.js` (28 tests): inmutabilidad, dimensiones `10×24`, rotaciones SRS, simetría de *wall-kicks*, curvas de gravedad/soft drop, `manifest.webmanifest`, `service-worker.js` (incluyendo cancelación de streams `no-store` y aislamiento frente a `diana-sudoku-v1`), íconos PNG/SVG y `.nojekyll`/`.gitignore`.
  - `engine.test.js` (7 tests): inicio Maratón, permutaciones *7-bag*, *Hold* 1/turno, *wall-kicks*, *Lock Delay* 500 ms + límite de 15 reinicios, gravedad >1G multi-fila, pausa/reinicio.
  - `input.test.js` (3 tests): monotonicidad de umbrales táctiles `1..10`, *deadzone* analógica y temporización DAS/ARR + prioridad SOCD.
  - `main_storage.test.js` (2 tests): recuperación ante JSON corrupto, clamping de rangos y fallback en memoria cuando `localStorage` lanza excepciones.
  - `audio.test.js` (2 tests): validación de los 24 compases / 96 tiempos de *Korobeiniki* a 144 BPM y operación segura sin `AudioContext`.
  - `renderer.test.js` (1 test): redimensionado entero de celdas, renderizado completo y ciclo de efectos/partículas.

---

## 2. Pruebas E2E en Navegador (Playwright + Chromium)
Comando: `python3 -m unittest discover -s tests/e2e -v`

### Correcciones clave aplicadas durante la fase E2E
1. **Respuesta inmediata de teclado (`js/input.js`):** emitir el primer paso lateral en `keydown` (`kbDas.update(0)`) para que pulsaciones rápidas no esperen al siguiente frame `requestAnimationFrame`.
2. **Guardia de teclas modificadoras (`js/input.js`):** ignorar `Ctrl`/`Meta`/`Alt` para no activar controles del juego con atajos del sistema.
3. **Calibración de *flick* táctil (`js/input.js`):** ajuste de `flickMinDistPx`, `flickMinVelPxPerMs` (`0.42` a `0.28`) y ventana (`260 ms`) para lograr 100% de discriminación entre *Soft Drop* lento y *Hard Drop* rápido en sensibilidades `1..10`.
4. **Overlay de Pausa detrás de Ajustes (`js/main.js`):** mantener `#overlay-pause` visible detrás de `#modal-settings` cuando se abre desde pausa.
5. **Texto completo del badge Xbox (`js/main.js`):** mostrar `'Control Xbox conectado'` / `'Control conectado'` en `#gamepad-badge`.

### Resumen de resultados E2E tras verificación local en Windows (**66 / 66 aprobadas**)
| Área | Cobertura | Resultado |
| :--- | :--- | :--- |
| **Área A** (`test_area_a_runtime_pwa.py`) | `file://`, HTTP root, subruta GitHub Pages, offline SW, aislamiento *Diana Sudoku*, resiliencia `localStorage` | **10 / 10** |
| **Área B** (`test_area_b_gameplay.py`) | *7-Bag*, SRS *wall-kicks*, *Lock Delay* 15 resets, gravedad L1 vs L15, Hold, Soft/Hard drop, líneas, Top-Out | **12 / 12** |
| **Área C** (`test_area_c_keyboard.py`) | Flechas, DAS/ARR, SOCD, `Z`/`X`/`↑`/`Espacio`/`C`/`Shift`/`P`/`Esc`, auto-pausa `blur`/`visibilitychange` | **10 / 10** |
| **Área D** (`test_area_d_mobile_touch.py`) | Viewports móviles (`>=80%` alto tablero), tap, arrastre lateral, soft drop vs flick, hold swipe, slider `1–10`, multitouch, `pointercancel` | **12 / 12** |
| **Área E** (`test_area_e_gamepad.py`) | Detección Xbox, stick `deadzone 0.30`, `D-Pad`, botones `A/B/X/LB/RB/Start`, desconexión segura | **11 / 11** |
| **Área F** (`test_area_f_visual_audio_es.py`) | Audio Web Audio sin red, HiDPI `dpr<=2`, UI 100% español, récords, modales | **11 / 11** |

> [!note] Notas de mantenimiento y verificación
> - En la corrida original de la VM Linux habían quedado 5 casos pendientes (`61/66`); al ejecutar la suite en Windows (`D:\Armando\source\Personal\tetris-clasico\.venv`) ya solo fallaron 2 pruebas en `test_area_c_keyboard.py` por condiciones de carrera de gravedad/buffer y falta de reanudación tras `Escape` antes de muestrear el canvas. Tras ajustar esas aserciones y limpiar el bloque muerto `#mobile-hud-strip`, las **66 / 66 pruebas E2E** y **43 / 43 pruebas unitarias** pasan.
> - El bundle único `index_unico.html` fue verificado aparte en Playwright bajo `file://` con **0 errores de consola**, **0 errores de página** y flujo completo de partida + modal de Ajustes funcional.

Ver estado de despliegue en [[04 - Despliegue, GitHub Pages y Pendientes]].

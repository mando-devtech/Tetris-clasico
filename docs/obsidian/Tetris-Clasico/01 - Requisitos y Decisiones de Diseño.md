---
title: "Requisitos y Decisiones de Diseño"
tags:
  - proyecto/tetris-clasico
  - diseno
  - requisitos
updated: 2026-11-25
---

# 01 — Requisitos y Decisiones de Diseño

Volver a [[00 - Tetris Clásico (Brain Maestro)]].

## 1. Objetivo del Usuario
Construir una aplicación web clásica de **Tetris** con interfaz moderna, estable ("sin errores"), jugable en:
1. **Computadora (navegador web / archivo local)** usando las teclas de flecha.
2. **Teléfono celular** alojada en web (**GitHub Pages**, igual que *Diana Sudoku*).
3. **Control de Xbox** conectado por USB o Bluetooth.

---

## 2. Árbol de Decisiones Acordadas (Fase `/grill-me`)

| Área | Decisión elegida | Motivo / Detalle clave |
| :--- | :--- | :--- |
| **Alojamiento** | GitHub Pages + ejecución local directa | Compatible con `https://` en subruta (`/Tetris-clasico/`) y `file://`. |
| **Stack técnico** | HTML5 + CSS3 + JavaScript puro (sin build) | Cero Node/Vite requeridos para desplegar; scripts `<script defer>` sin `type="module"` para evitar errores CORS en `file://`. |
| **Reglas de juego** | Tetris moderno estándar (Guideline) | *7-Bag*, SRS con *wall-kicks*, *Lock Delay* 500 ms, pieza fantasma (*Ghost*), *Hold* (1 por turno) y vista de 3 próximas piezas. |
| **Modo y progresión** | Modo Maratón (nivel inicial `1–15`) | Sube de nivel cada 10 líneas; récords (`bestScore`, `bestLevel`, `bestLines`) guardados en `localStorage`. |
| **Controles PC** | Flechas + teclas estándar | `←/→` mover, `↓` soft drop, `↑/X` rotar der., `Z` rotar izq., `Espacio` hard drop, `C/Shift` hold, `P/Esc` pausa. |
| **Controles Celular** | **Solo gestos** sobre el tablero + Slider de sensibilidad (`1–10`) | Sin botones virtuales estorbando el tablero: arrastrar `←/→` mueve por celda, tap corta rota, arrastrar `↓` soft drop, flick rápido `↓` hard drop, tap en Hold o swipe `↑` guarda pieza. |
| **Control Xbox** | **Gamepad API** (estándar consola moderna) | `D-Pad/Stick ←→` mover, `D-Pad/Stick ↓` soft drop, `D-Pad ↑` hard drop (stick arriba ignorado), `A/B` rotar der., `X` rotar izq., `LB/RB` hold, `Menú/Start` pausa. |
| **Estilo visual** | Oscuro moderno (*Glassmorphism* + neón sutil) | Tablero centrado en escritorio; en móvil, barra superior compacta y **>= 80%** del alto de pantalla para `#board-stage`. |
| **Audio** | Web Audio API (SFX + *Korobeiniki*) | 100% generado por código (cero MP3 externos); interruptores independientes para Música y Efectos. |
| **PWA Móvil** | Instalable (`manifest` + `service-worker`) | Permite "Agregar a pantalla de inicio" en celular y jugar offline; bloquea scroll/zoom accidental (`touch-action: none`). |

---

## 3. Reglas UX Importantes
- **Botones de barra superior (`#btn-pause`, `#btn-settings`, `#btn-music`, `#btn-sfx`):** siempre ejecutan `.blur()` al hacer clic para que presionar `Espacio` después no reactive el botón por accidente.
- **Auto-pausa:** al abrir **Ajustes** o al perder el foco (`blur` / `visibilitychange`), el juego pausa la gravedad y limpia teclas/gestos retenidos para evitar movimientos fantasma al reanudar.
- **Idioma:** 100% en español (`<html lang="es">`, `<title>Tetris Clásico</title>`, guías de control y mensajes ARIA).

Ver arquitectura técnica en [[02 - Arquitectura y Contratos de Módulos]].

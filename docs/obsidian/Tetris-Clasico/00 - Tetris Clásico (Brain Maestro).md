---
title: "Tetris Clásico — Brain Maestro"
aliases:
  - "Tetris Clásico"
  - "Tetris Brain"
tags:
  - proyecto/tetris-clasico
  - indice
  - brain
status: publicado-en-github-pages
stack:
  - HTML5
  - CSS3
  - Vanilla-JS
  - Web-Audio-API
  - Gamepad-API
  - PWA
repo: "https://github.com/mando-devtech/Tetris-clasico"
url_pages: "https://mando-devtech.github.io/Tetris-clasico/"
updated: 2026-11-25
---

# Tetris Clásico — Brain Maestro

> [!info] Propósito de esta carpeta
> Esta carpeta funciona como **memoria persistente ("brain")** del proyecto **Tetris Clásico**. Si en el futuro retomamos este juego para agregar modos (Sprint, Ultra), temas visuales o mejoras, comparte o abre esta nota primero para recuperar el contexto completo en segundos.

## Mapa de Documentación (Vault)

1. [[01 - Requisitos y Decisiones de Diseño]] — Qué pidió el usuario, cómo se resolvió cada rama del diseño (controles PC, gestos móviles + sensibilidad, control Xbox, audio, PWA).
2. [[02 - Arquitectura y Contratos de Módulos]] — Estructura de archivos, orden de carga, contratos `window.Tetris.*`, modelo de datos en `localStorage`, aislamiento respecto a *Diana Sudoku* y parámetros exactos.
3. [[03 - Historial de Pruebas y Calidad]] — Suite unitaria en Node (`43/43`), suite E2E en Playwright (`66/66` aprobadas), correcciones aplicadas y cobertura.
4. [[04 - Despliegue, GitHub Pages y Pendientes]] — Repositorio Git (`mando-devtech/Tetris-clasico`), publicación en GitHub Pages (`https://mando-devtech.github.io/Tetris-clasico/`), entregable `index_unico.html` y roadmap futuro.

---

## Resumen Ejecutivo para Contexto Rápido (IA / Nuevo Chat)

- **Qué es:** Aplicación web clásica y moderna de **Tetris** en español (`<html lang="es">`), **cero dependencias externas** y **sin paso de compilación**.
- **Compatibilidad dual:** Funciona abriendo `index.html` directo con `file://` en PC y alojado en **GitHub Pages** (`https://`) como **PWA instalable** en celular.
- **Aislamiento con proyecto hermano (*Diana Sudoku*):**
  - `localStorage` bajo clave única: `'tetris_clasico_v1'`
  - Service Worker caché único: `'tetris-clasico-v1'` (solo limpia `tetris-clasico-*`, nunca toca `diana-sudoku-*`).
- **Módulos principales (`js/`):**
  - `constants.js` → tablero `10×24` (`20` visibles + `4` buffer), matrices SRS, wall-kicks, curvas de gravedad y puntaje.
  - `engine.js` → *7-bag*, rotación SRS, *Lock Delay* (`500 ms` / `15` reinicios), Ghost, Hold, 3-Next, Maratón `1–15+`, Combo y Back-to-Back.
  - `audio.js` → Web Audio API 100% sintetizado (SFX + melodía *Korobeiniki* 24 compases a 144 BPM con silencio independiente).
  - `renderer.js` → `<canvas>` HiDPI (`dpr <= 2`), bloques biselados neon/glass, partículas (`<= 120`), estela Hard Drop y callouts flotantes.
  - `input.js` → Teclado (`DAS 160 ms` / `ARR 35 ms`), gestos táctiles sobre `#board-stage` con **sensibilidad `1–10`** y **Control Xbox** vía Gamepad API.
  - `main.js` → Bucle `requestAnimationFrame`, UI/modales, persistencia segura en `localStorage` y registro condicional de PWA solo en `http:`/`https:`.
- **Estado actual:** Código completo, verificado (`43/43` unitarias y `66/66` E2E) y publicado en rama `main` (`mando-devtech/Tetris-clasico`), activo en vivo en `https://mando-devtech.github.io/Tetris-clasico/` con soporte PWA completo (además de `index_unico.html` como respaldo autocontenido).

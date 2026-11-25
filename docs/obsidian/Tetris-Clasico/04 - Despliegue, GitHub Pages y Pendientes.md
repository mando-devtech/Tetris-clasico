---
title: "Despliegue, GitHub Pages y Pendientes"
tags:
  - proyecto/tetris-clasico
  - despliegue
  - github-pages
  - roadmap
updated: 2026-11-25
---

# 04 — Despliegue, GitHub Pages y Pendientes

Volver a [[00 - Tetris Clásico (Brain Maestro)]].

## 1. Estado del Repositorio

- **Cuenta GitHub:** `mando-devtech` (`gonzalez.dev.tech@gmail.com`)
- **Repositorio remoto:** `https://github.com/mando-devtech/Tetris-clasico` (público)
- **Carpeta local:** `D:\Armando\source\Personal\tetris-clasico` (rama `main`)
- **Historial:** En la VM remota original hubo un bloqueo HTTP 403 al hacer push, por lo que inicialmente se subió manualmente `index_unico.html` como `index.html`. Posteriormente, desde la PC local con `gh` autenticado en `@mando-devtech`, se conectó el repo Git local sobre `origin/main` y se publicó el proyecto modular completo con soporte PWA.

---

## 2. Entregables

1. **Proyecto modular completo (despliegue GitHub Pages):** `index.html`, `styles.css`, `js/*`, `icons/*`, `manifest.webmanifest`, `service-worker.js`, `.nojekyll`, `README.md`, `tests/*` y `docs/*`.
2. **Archivo único autocontenido (`index_unico.html` de ~118 KB):** Contiene HTML, CSS, ícono SVG inline y los 6 módulos JS en un solo archivo portátil para abrir directo o compartir.

---

## 3. Ideas / Próximos Pasos si el Proyecto Crece

- [x] Subir la versión modular completa (`index.html`, `styles.css`, `js/`, `icons/`, `manifest.webmanifest`, `service-worker.js`, `.nojekyll`) para activar la instalación PWA completa en iOS y Android.
- [x] Resolver los casos E2E pendientes (`66/66` aprobados en local).
- [ ] Agregar pruebas E2E combinadas/end-to-end adicionales (`test_tier3_combinations.py`, `test_tier4_scenarios.py`, Tier 5) si se integra CI con GitHub Actions.
- [ ] Agregar modos extra opcionales (**Sprint 40 líneas**, **Ultra 2 min**, **Modo Zen**).
- [ ] Agregar remapeo personalizable de botones para control de Xbox y teclado en Ajustes.
- [ ] Agregar soporte de T-Spins y efectos hápticos (`navigator.vibrate`) opcionales en móvil al hacer Tetris / Hard Drop.

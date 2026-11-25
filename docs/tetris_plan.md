# Plan de Desarrollo: Tetris Web Clásico (PC + Móvil)

Este documento resume todas las decisiones acordadas para construir una aplicación web de Tetris moderna, fluida, sin errores y lista para ejecutarse tanto localmente en computadora como alojada en **GitHub Pages** para jugar desde el celular.

---

## 1. Arquitectura y Despliegue

- **Stack tecnológico:** HTML5, CSS3 y JavaScript puro (sin paso de compilación ni dependencias externas).
- **Compatibilidad dual:**
  - Rutas relativas y carga de scripts compatible con `file://` (abriendo `index.html` directamente en el navegador de tu computadora) y con `https://` en **GitHub Pages**.
  - Configuración **PWA** (`manifest.webmanifest`, íconos vectoriales/PNG y `service-worker.js` registrado únicamente bajo `http:` / `https:`) para instalar el juego en la pantalla de inicio del celular en modo pantalla completa y soporte offline.
- **Estructura propuesta de archivos:**
  - `index.html` — Estructura semántica, meta tags móviles y carga de scripts.
  - `styles.css` — Diseño responsivo, tema oscuro Glassmorphism/neón sutil, animaciones y bloqueo de gestos del navegador (`touch-action: none`, `overscroll-behavior: none`).
  - `manifest.webmanifest` & `service-worker.js` — Soporte PWA para GitHub Pages.
  - `js/constants.js` — Tablero (10×20 + buffer superior), tetrominós, colores, tablas SRS (wall-kicks) y curvas de velocidad/puntaje.
  - `js/audio.js` — Motor Web Audio API (efectos de sonido + melodía *Korobeiniki* chiptune opcional con controles independientes).
  - `js/engine.js` — Lógica pura del juego (7-bag, SRS, lock delay, detección de líneas, Combo, Back-to-Back, Ghost piece, Hold).
  - `js/input.js` — Manejador unificado de entrada: teclado (DAS/ARR para PC), gestos táctiles calibrados por sensibilidad y **control de Xbox vía Gamepad API**.
  - `js/renderer.js` — Renderizado nítido en `<canvas>` adaptado a `devicePixelRatio` (Retina/HiDPI), partículas/destellos al limpiar líneas.
  - `js/main.js` — Bucle principal (`requestAnimationFrame` con delta time), UI, pausa, modal de Ajustes, selección de nivel inicial y persistencia en `localStorage`.

---

## 2. Mecánicas de Juego (Estándar Moderno)

- **Tablero:** Cuadrícula oficial de **10 columnas × 20 filas visibles** (más 4 filas ocultas arriba para aparición segura de piezas).
- **Generador 7-Bag:** Garantiza que recibas las 7 piezas (`I, O, T, S, Z, J, L`) en orden aleatorio antes de repetir, evitando rachas injustas.
- **Rotación SRS con Wall-Kicks:** Tablas oficiales de desplazamiento para que las piezas roten limpiamente cerca de paredes, suelo u otras piezas.
- **Lock Delay:** Pequeño margen (~500 ms, con límite de reinicios) al tocar el suelo para poder deslizar o rotar la pieza antes de fijarse.
- **Ayudas estándar:**
  - **Ghost Piece (Sombra):** Muestra exactamente dónde aterrizará la pieza actual.
  - **Hold (Guardar):** Permite guardar o intercambiar la pieza activa (una vez por caída).
  - **Next Queue:** Vista previa de las **3 próximas piezas**.
- **Modo Maratón y Progresión:**
  - Selector de **nivel inicial (1 a 15)** antes de iniciar partida.
  - Subida automática de nivel y velocidad cada **10 líneas** completadas.
  - Puntuación estándar (Single, Double, Triple, Tetris, bonus Back-to-Back, Combo, Soft Drop y Hard Drop).
  - Guardado automático de récords (mejor puntaje, nivel y líneas) en `localStorage`.

---

## 3. Controles (PC, Celular y Control de Xbox)

### Computadora (Teclado)
| Tecla | Acción |
| :--- | :--- |
| `←` / `→` | Mover pieza (con auto-repetición calibrada DAS/ARR) |
| `↓` | Caída rápida (Soft Drop) |
| `↑` / `X` | Rotar en sentido horario |
| `Z` | Rotar en sentido antihorario |
| `Espacio` | Caída instantánea (Hard Drop) |
| `C` o `Shift` | Guardar / intercambiar pieza (Hold) |
| `P` o `Esc` | Pausar / Reanudar |

### Teléfono Celular (Solo Gestos sobre el Tablero + Control de Sensibilidad)
- **Arrastrar izquierda / derecha:** Desplaza la pieza celda por celda de forma proporcional y fluida.
- **Toque corto (Tap) en el tablero:** Rota la pieza.
- **Arrastrar hacia abajo:** Caída rápida (Soft Drop).
- **Deslizamiento rápido hacia abajo (Flick):** Caída instantánea (Hard Drop), calibrado por velocidad y umbral para evitar activaciones accidentales.
- **Tocar la caja de Hold o deslizar hacia arriba:** Guardar / intercambiar pieza (Hold).
- **Control de sensibilidad táctil (en Ajustes):** Slider ajustable (ej. `1` a `10`, guardado en `localStorage`) que regula cuántos píxeles requiere mover una celda lateral y el umbral del *flick* hacia abajo, para adaptarlo exactamente a tu dedo y tamaño de pantalla.
- **Barra superior accesible:** Botones compactos para Pausa, Ajustes, Música y Efectos.

### Control de Xbox (Gamepad API — USB / Bluetooth en PC y Celular)
- **Detección automática:** Reconoce el control al conectarlo o presionar cualquier botón, mostrando un indicador discreto de estado (*Control conectado*).
- **Calibración:** Zona muerta (*deadzone*) en el stick izquierdo para evitar movimientos involuntarios (*stick drift*) y repetición lateral fluida (DAS/ARR).
- **Mapeo estándar de consola moderna:**
  | Botón / Eje Xbox | Acción |
  | :--- | :--- |
  | `D-Pad ← / →` o `Stick Izq.` | Mover pieza |
  | `D-Pad ↓` o `Stick Izq. abajo` | Caída rápida (Soft Drop) |
  | `D-Pad ↑` | Caída instantánea (Hard Drop) |
  | `A` (o `B`) | Rotar en sentido horario |
  | `X` | Rotar en sentido antihorario |
  | `LB` / `RB` | Guardar / intercambiar pieza (Hold) |
  | `Menú / Start` | Pausar / Reanudar |

---

## 4. Diseño Visual e Interfaz Moderna

- **Estética:** Tema oscuro elegante con tarjetas tipo *glassmorphism* y acentos neón sutiles.
- **Piezas:** Bloques con sombreado y brillo sutil moderno (alto contraste y fácil lectura en pantallas pequeñas y grandes).
- **Feedback visual:** Destello suave al limpiar líneas, efecto sutil de impacto en Hard Drop y avisos flotantes limpios (`TETRIS!`, `COMBO x3`, `LEVEL UP`).
- **Modal de Ajustes:** Acceso rápido al slider de sensibilidad táctil, interruptores de Música y Efectos, indicador de control Xbox y guía visual de controles.
- **Diseño responsivo:**
  - **Escritorio:** Tablero centrado de gran tamaño con Hold a la izquierda y Next + Estadísticas a la derecha.
  - **Móvil:** Barra superior compacta (Hold, Puntuación/Nivel/Líneas, Próxima pieza y controles de Pausa/Ajustes/Audio) y el **80%+ de la pantalla** dedicado al tablero táctil.

---

## 5. Audio (Web Audio API)

- **100% sintetizado por código:** Cero archivos MP3/WAV externos (carga instantánea y funcionamiento garantizado offline).
- **Efectos de sonido:** Mover, rotar, fijar pieza, limpiar 1–3 líneas, Tetris (4 líneas), Hold, subir de nivel y Game Over.
- **Música clásica (*Korobeiniki*):** Versión chiptune suave en bucle sincronizado con el estado de juego (se pausa automáticamente al pausar o perder).
- **Controles independientes:** Interruptores separados para silenciar/activar **Música** y **Efectos**, recordando tu preferencia en `localStorage`.

---

## 6. Siguientes Pasos

1. Confirmar este plan actualizado (o ajustar cualquier detalle).
2. Construir todos los archivos de la aplicación en el espacio de trabajo y probarlos (lógica SRS, 7-bag, detección de líneas, teclado, Gamepad API, simulación táctil con sensibilidad, diseño móvil/PC y PWA).
3. Dejar el proyecto listo para publicarlo en GitHub Pages (con instrucciones paso a paso o directamente mediante GitHub si conectas tu repositorio).

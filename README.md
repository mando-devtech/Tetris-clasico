# Tetris Clásico (Web, Móvil y Control Xbox)

Aplicación web moderna del clásico **Tetris** en español, construida con **HTML5, CSS3 y JavaScript puro** (cero dependencias externas y sin paso de compilación). Funciona tanto abriendo `index.html` directamente en tu computadora como publicada en **GitHub Pages** para jugar desde tu teléfono celular o con un control de Xbox.

---

## Características principales

- **Reglas modernas estándar:** Generador *7-Bag*, rotación oficial **SRS** con *wall-kicks*, *Lock Delay* de 500 ms (hasta 15 reinicios), pieza fantasma (*Ghost*), guardar pieza (*Hold*) y vista previa de las **3 próximas piezas**.
- **Modo Maratón:** Selector de nivel inicial (`1–15`), subida de nivel cada 10 líneas, bonos *Back-to-Back* y *Combo*, con récords guardados localmente en el navegador.
- **Controles completos:**
  - **Computadora (Teclado):** `← / →` mover, `↓` caída rápida, `↑ / X` rotar derecha, `Z` rotar izquierda, `Espacio` caída instantánea (*Hard Drop*), `C / Shift` guardar (*Hold*), `P / Esc` pausa.
  - **Teléfono celular (Solo gestos):** Arrastrar `← / →` para mover, toque corto para rotar, arrastrar `↓` para caída rápida, deslizar rápido `↓` (*flick*) para caída instantánea y tocar la caja de *Hold* (o deslizar `↑`) para guardar pieza. Incluye **slider de sensibilidad táctil (`1–10`)** en Ajustes.
  - **Control de Xbox (USB / Bluetooth):** Detección automática vía *Gamepad API* (`D-Pad / Stick Izq.` mover/bajar, `D-Pad ↑` caída instantánea, `A / B` rotar derecha, `X` rotar izquierda, `LB / RB` guardar, `Menú / Start` pausa).
- **Audio sintetizado (Web Audio API):** Efectos de sonido y melodía chiptune *Korobeiniki* opcional con controles independientes para música y efectos.
- **PWA instalable:** Listo para agregar a la pantalla de inicio en celular desde GitHub Pages con soporte offline (aislado de otros proyectos en el mismo dominio como *Diana Sudoku*).

---

## Cómo jugar en tu computadora

1. Descarga o clona esta carpeta.
2. Abre el archivo `index.html` directamente con doble clic en tu navegador (Chrome, Edge, Firefox o Safari).

---

## Cómo publicar en GitHub Pages (para jugar en tu celular)

1. Crea un repositorio nuevo en GitHub (por ejemplo `tetris-clasico`).
2. Sube todo el contenido de este proyecto a la rama `main` (asegúrate de incluir el archivo oculto `.nojekyll`).
3. En GitHub, ve a **Settings → Pages**.
4. En **Source**, elige **Deploy from a branch**, selecciona la rama `main` y la carpeta `/ (root)`, y guarda.
5. Abre la URL `https://<tu-usuario>.github.io/<tu-repositorio>/` desde el navegador de tu celular.
6. *(Opcional)* En Safari (iOS) o Chrome (Android), toca **"Agregar a pantalla de inicio"** para instalarlo como app en pantalla completa.

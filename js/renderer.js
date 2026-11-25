(function (root) {
  'use strict';

  var Constants = (root.Tetris && root.Tetris.Constants) ||
    (typeof require === 'function' ? require('./constants.js') : null);

  if (!Constants) {
    throw new Error('Tetris.Constants is required before Tetris.Renderer');
  }

  var COLS = Constants.COLS;
  var VISIBLE_ROWS = Constants.VISIBLE_ROWS;
  var BUFFER_ROWS = Constants.BUFFER_ROWS;
  var SHAPES = Constants.SHAPES;
  var COLORS = Constants.COLORS;
  var MAX_PARTICLES = 120;

  function drawBeveledBlock(ctx, x, y, size, colorObj, alpha, pulseRatio) {
    if (size <= 0) {
      return;
    }
    var pad = Math.max(1, Math.floor(size * 0.05));
    var bx = x + pad;
    var by = y + pad;
    var bs = Math.max(2, size - pad * 2);
    var bevel = Math.max(2, Math.floor(bs * 0.16));

    ctx.save();
    ctx.globalAlpha = alpha !== undefined ? alpha : 1;

    // Base fill
    ctx.fillStyle = colorObj.fill;
    ctx.fillRect(bx, by, bs, bs);

    // Top & Left highlight
    ctx.fillStyle = colorObj.light;
    ctx.fillRect(bx, by, bs, bevel);
    ctx.fillRect(bx, by, bevel, bs);

    // Bottom & Right shadow
    ctx.fillStyle = colorObj.dark;
    ctx.fillRect(bx, by + bs - bevel, bs, bevel);
    ctx.fillRect(bx + bs - bevel, by, bevel, bs);

    // Inner glass sheen
    ctx.fillStyle = 'rgba(255, 255, 255, 0.16)';
    ctx.fillRect(bx + bevel, by + bevel, Math.max(1, bs - bevel * 2), Math.max(1, Math.floor((bs - bevel * 2) * 0.45)));

    // Subtle lock-delay pulse overlay when grounded
    if (pulseRatio && pulseRatio > 0) {
      ctx.fillStyle = 'rgba(255, 255, 255, ' + (0.28 * pulseRatio).toFixed(3) + ')';
      ctx.fillRect(bx, by, bs, bs);
    }

    ctx.restore();
  }

  function drawGhostBlock(ctx, x, y, size, colorObj) {
    var pad = Math.max(1, Math.floor(size * 0.08));
    var bx = x + pad;
    var by = y + pad;
    var bs = Math.max(2, size - pad * 2);

    ctx.save();
    ctx.fillStyle = colorObj.ghostFill;
    ctx.fillRect(bx, by, bs, bs);
    ctx.strokeStyle = colorObj.ghostStroke;
    ctx.lineWidth = Math.max(1, Math.floor(size * 0.07));
    ctx.strokeRect(bx + 0.5, by + 0.5, bs - 1, bs - 1);
    ctx.restore();
  }

  function drawMiniPiece(ctx, type, centerX, centerY, cellSize, alpha) {
    if (!type || !SHAPES[type] || !COLORS[type]) {
      return;
    }
    var matrix = SHAPES[type][0];
    var colorObj = COLORS[type];
    var minR = 4, maxR = -1, minC = 4, maxC = -1;
    var r, c;

    for (r = 0; r < matrix.length; r++) {
      for (c = 0; c < matrix[r].length; c++) {
        if (matrix[r][c]) {
          if (r < minR) minR = r;
          if (r > maxR) maxR = r;
          if (c < minC) minC = c;
          if (c > maxC) maxC = c;
        }
      }
    }
    if (maxR < minR) {
      return;
    }

    var pw = (maxC - minC + 1) * cellSize;
    var ph = (maxR - minR + 1) * cellSize;
    var startX = Math.round(centerX - pw / 2);
    var startY = Math.round(centerY - ph / 2);

    for (r = minR; r <= maxR; r++) {
      for (c = minC; c <= maxC; c++) {
        if (matrix[r][c]) {
          drawBeveledBlock(
            ctx,
            startX + (c - minC) * cellSize,
            startY + (r - minR) * cellSize,
            cellSize,
            colorObj,
            alpha,
            0
          );
        }
      }
    }
  }

  function createRenderer(options) {
    var opts = options || {};
    var boardCanvas = opts.boardCanvas || null;
    var holdCanvas = opts.holdCanvas || null;
    var nextCanvas = opts.nextCanvas || null;
    var boardStage = opts.boardStage || null;

    var cellSize = 28;
    var dpr = 1;
    var boardCssWidth = COLS * cellSize;
    var boardCssHeight = VISIBLE_ROWS * cellSize;
    var isCompactNext = false;

    var particles = [];
    var rowFlashes = [];
    var dropTrails = [];
    var callouts = [];

    function setupCanvas(canvas, cssW, cssH, scale) {
      if (!canvas) {
        return;
      }
      canvas.style.width = cssW + 'px';
      canvas.style.height = cssH + 'px';
      canvas.width = Math.max(1, Math.round(cssW * scale));
      canvas.height = Math.max(1, Math.round(cssH * scale));
    }

    function resize() {
      dpr = Math.min(
        typeof window !== 'undefined' && window.devicePixelRatio ? window.devicePixelRatio : 1,
        2
      );

      var availW = boardStage && boardStage.clientWidth ? boardStage.clientWidth - 8 : 300;
      var availH = boardStage && boardStage.clientHeight ? boardStage.clientHeight - 8 : 600;
      cellSize = Math.max(12, Math.floor(Math.min(availW / COLS, availH / VISIBLE_ROWS)));
      boardCssWidth = COLS * cellSize;
      boardCssHeight = VISIBLE_ROWS * cellSize;
      setupCanvas(boardCanvas, boardCssWidth, boardCssHeight, dpr);

      var vw = typeof window !== 'undefined' ? window.innerWidth : 1024;
      isCompactNext = vw <= 820;

      if (holdCanvas) {
        var holdSize = isCompactNext ? 48 : 88;
        setupCanvas(holdCanvas, holdSize, holdSize, dpr);
      }

      if (nextCanvas) {
        if (isCompactNext) {
          setupCanvas(nextCanvas, 126, 44, dpr);
        } else {
          setupCanvas(nextCanvas, 96, 228, dpr);
        }
      }
    }

    function spawnParticles(row, colorObj) {
      var visRow = row - BUFFER_ROWS;
      if (visRow < 0 || visRow >= VISIBLE_ROWS) {
        return;
      }
      var c, x, y;
      for (c = 0; c < COLS; c++) {
        if (particles.length >= MAX_PARTICLES) {
          break;
        }
        x = (c + 0.5) * cellSize;
        y = (visRow + 0.5) * cellSize;
        particles.push({
          x: x,
          y: y,
          vx: (Math.random() - 0.5) * 180,
          vy: (Math.random() - 0.7) * 160,
          size: Math.max(3, Math.floor(cellSize * 0.22)),
          color: colorObj ? colorObj.light : '#ffffff',
          life: 0,
          maxLife: 380
        });
      }
    }

    function addCallout(text, color) {
      callouts.push({
        text: text,
        color: color || '#e2e8f0',
        life: 0,
        maxLife: 950
      });
      if (callouts.length > 4) {
        callouts.shift();
      }
    }

    function triggerEffects(events) {
      if (!events || !events.length) {
        return;
      }
      var i, ev, r;
      for (i = 0; i < events.length; i++) {
        ev = events[i];
        if (ev.type === 'hardDrop' && ev.cells > 0) {
          dropTrails.push({
            col: ev.col,
            width: ev.width || 3,
            startY: Math.max(0, ev.startY - BUFFER_ROWS),
            endY: Math.max(0, ev.endY - BUFFER_ROWS),
            color: (COLORS[ev.piece] && COLORS[ev.piece].glow) || 'rgba(255,255,255,0.35)',
            life: 0,
            maxLife: 180
          });
        } else if (ev.type === 'lineClear') {
          for (r = 0; r < ev.rows.length; r++) {
            rowFlashes.push({
              visRow: ev.rows[r] - BUFFER_ROWS,
              life: 0,
              maxLife: 240
            });
            spawnParticles(ev.rows[r], COLORS.I);
          }
          if (ev.isTetris) {
            addCallout('¡TETRIS!', '#22d3ee');
          }
          if (ev.isBackToBack) {
            addCallout('BACK TO BACK', '#facc15');
          }
          if (ev.combo > 0) {
            addCallout('COMBO ×' + (ev.combo + 1), '#c084fc');
          }
        } else if (ev.type === 'levelUp') {
          addCallout('¡NIVEL ' + ev.level + '!', '#4ade80');
        }
      }
    }

    function updateEffects(dtMs) {
      var dtSec = (dtMs || 0) / 1000;
      var i, p;

      for (i = particles.length - 1; i >= 0; i--) {
        p = particles[i];
        p.life += dtMs;
        if (p.life >= p.maxLife) {
          particles.splice(i, 1);
          continue;
        }
        p.x += p.vx * dtSec;
        p.y += p.vy * dtSec;
        p.vy += 320 * dtSec;
      }

      for (i = rowFlashes.length - 1; i >= 0; i--) {
        rowFlashes[i].life += dtMs;
        if (rowFlashes[i].life >= rowFlashes[i].maxLife) {
          rowFlashes.splice(i, 1);
        }
      }

      for (i = dropTrails.length - 1; i >= 0; i--) {
        dropTrails[i].life += dtMs;
        if (dropTrails[i].life >= dropTrails[i].maxLife) {
          dropTrails.splice(i, 1);
        }
      }

      for (i = callouts.length - 1; i >= 0; i--) {
        callouts[i].life += dtMs;
        if (callouts[i].life >= callouts[i].maxLife) {
          callouts.splice(i, 1);
        }
      }
    }

    function renderBoard(snapshot) {
      if (!boardCanvas) {
        return;
      }
      var ctx = boardCanvas.getContext('2d');
      if (!ctx) {
        return;
      }

      ctx.save();
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

      // Deep dark glass backdrop
      ctx.fillStyle = '#090d1a';
      ctx.fillRect(0, 0, boardCssWidth, boardCssHeight);

      // Subtle playfield grid
      ctx.strokeStyle = 'rgba(148, 163, 184, 0.08)';
      ctx.lineWidth = 1;
      var c, r;
      ctx.beginPath();
      for (c = 1; c < COLS; c++) {
        ctx.moveTo(c * cellSize + 0.5, 0);
        ctx.lineTo(c * cellSize + 0.5, boardCssHeight);
      }
      for (r = 1; r < VISIBLE_ROWS; r++) {
        ctx.moveTo(0, r * cellSize + 0.5);
        ctx.lineTo(boardCssWidth, r * cellSize + 0.5);
      }
      ctx.stroke();

      // Hard drop trails
      var i, tr, alpha;
      for (i = 0; i < dropTrails.length; i++) {
        tr = dropTrails[i];
        alpha = 1 - tr.life / tr.maxLife;
        ctx.save();
        ctx.globalAlpha = alpha * 0.45;
        ctx.fillStyle = tr.color;
        ctx.fillRect(
          tr.col * cellSize,
          tr.startY * cellSize,
          tr.width * cellSize,
          Math.max(0, (tr.endY - tr.startY) * cellSize)
        );
        ctx.restore();
      }

      // Locked board cells
      if (snapshot && snapshot.board) {
        for (r = BUFFER_ROWS; r < BUFFER_ROWS + VISIBLE_ROWS; r++) {
          var visRow = r - BUFFER_ROWS;
          for (c = 0; c < COLS; c++) {
            var cellType = snapshot.board[r][c];
            if (cellType && COLORS[cellType]) {
              drawBeveledBlock(ctx, c * cellSize, visRow * cellSize, cellSize, COLORS[cellType], 1, 0);
            }
          }
        }
      }

      // Active & Ghost piece
      if (snapshot && snapshot.activePiece && snapshot.status !== 'menu') {
        var piece = snapshot.activePiece;
        var pColor = COLORS[piece.type];
        var matrix = piece.matrix;

        if (snapshot.ghostY !== undefined && snapshot.ghostY >= piece.row) {
          for (r = 0; r < matrix.length; r++) {
            for (c = 0; c < matrix[r].length; c++) {
              if (!matrix[r][c]) {
                continue;
              }
              var gVisRow = snapshot.ghostY + r - BUFFER_ROWS;
              if (gVisRow >= 0 && gVisRow < VISIBLE_ROWS) {
                drawGhostBlock(ctx, (piece.col + c) * cellSize, gVisRow * cellSize, cellSize, pColor);
              }
            }
          }
        }

        var pulseRatio = 0;
        if (snapshot.isGrounded && snapshot.lockDelayMs > 0) {
          pulseRatio = Math.min(1, snapshot.lockTimerMs / snapshot.lockDelayMs);
        }

        for (r = 0; r < matrix.length; r++) {
          for (c = 0; c < matrix[r].length; c++) {
            if (!matrix[r][c]) {
              continue;
            }
            var aVisRow = piece.row + r - BUFFER_ROWS;
            if (aVisRow >= 0 && aVisRow < VISIBLE_ROWS) {
              drawBeveledBlock(
                ctx,
                (piece.col + c) * cellSize,
                aVisRow * cellSize,
                cellSize,
                pColor,
                1,
                pulseRatio
              );
            }
          }
        }
      }

      // Line clear flashes
      var fl;
      for (i = 0; i < rowFlashes.length; i++) {
        fl = rowFlashes[i];
        if (fl.visRow >= 0 && fl.visRow < VISIBLE_ROWS) {
          alpha = 1 - fl.life / fl.maxLife;
          ctx.fillStyle = 'rgba(255, 255, 255, ' + (0.75 * alpha).toFixed(3) + ')';
          ctx.fillRect(0, fl.visRow * cellSize, boardCssWidth, cellSize);
        }
      }

      // Particles
      var p;
      for (i = 0; i < particles.length; i++) {
        p = particles[i];
        alpha = 1 - p.life / p.maxLife;
        ctx.save();
        ctx.globalAlpha = alpha;
        ctx.fillStyle = p.color;
        ctx.fillRect(p.x - p.size / 2, p.y - p.size / 2, p.size, p.size);
        ctx.restore();
      }

      // Floating callouts
      var co;
      for (i = 0; i < callouts.length; i++) {
        co = callouts[i];
        var prog = co.life / co.maxLife;
        alpha = prog < 0.2 ? prog / 0.2 : Math.max(0, 1 - (prog - 0.2) / 0.8);
        var cy = boardCssHeight * 0.34 - prog * 28 - i * 24;
        ctx.save();
        ctx.globalAlpha = alpha;
        ctx.font = '700 ' + Math.max(14, Math.round(cellSize * 0.72)) + 'px system-ui, -apple-system, sans-serif';
        ctx.textAlign = 'center';
        ctx.fillStyle = 'rgba(2, 6, 23, 0.85)';
        ctx.fillText(co.text, boardCssWidth / 2 + 1, cy + 2);
        ctx.fillStyle = co.color;
        ctx.fillText(co.text, boardCssWidth / 2, cy);
        ctx.restore();
      }

      ctx.restore();
    }

    function renderHold(snapshot) {
      if (!holdCanvas) {
        return;
      }
      var ctx = holdCanvas.getContext('2d');
      if (!ctx) {
        return;
      }
      var w = parseFloat(holdCanvas.style.width) || 88;
      var h = parseFloat(holdCanvas.style.height) || 88;
      ctx.save();
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);

      if (snapshot && snapshot.holdPiece) {
        var miniCell = Math.max(9, Math.floor(Math.min(w, h) * 0.21));
        var alpha = snapshot.canHold ? 1 : 0.4;
        drawMiniPiece(ctx, snapshot.holdPiece, w / 2, h / 2, miniCell, alpha);
      }
      ctx.restore();
    }

    function renderNext(snapshot) {
      if (!nextCanvas) {
        return;
      }
      var ctx = nextCanvas.getContext('2d');
      if (!ctx) {
        return;
      }
      var w = parseFloat(nextCanvas.style.width) || 96;
      var h = parseFloat(nextCanvas.style.height) || 228;
      ctx.save();
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);

      var queue = snapshot && snapshot.nextQueue ? snapshot.nextQueue : [];
      var count = Math.min(3, queue.length);
      var i;
      if (isCompactNext) {
        var slotW = w / 3;
        var miniCellH = Math.max(7, Math.floor(Math.min(slotW, h) * 0.20));
        for (i = 0; i < count; i++) {
          drawMiniPiece(ctx, queue[i], slotW * (i + 0.5), h / 2, miniCellH, i === 0 ? 1 : 0.78);
        }
      } else {
        var slotH = h / 3;
        var miniCellV = Math.max(10, Math.floor(Math.min(w, slotH) * 0.21));
        for (i = 0; i < count; i++) {
          drawMiniPiece(ctx, queue[i], w / 2, slotH * (i + 0.5), miniCellV, 1);
        }
      }
      ctx.restore();
    }

    function render(snapshot, dtMs) {
      updateEffects(dtMs || 0);
      renderBoard(snapshot);
      renderHold(snapshot);
      renderNext(snapshot);
    }

    function getBoardMetrics() {
      var rect = boardCanvas && typeof boardCanvas.getBoundingClientRect === 'function'
        ? boardCanvas.getBoundingClientRect()
        : { left: 0, top: 0, width: boardCssWidth, height: boardCssHeight };
      return {
        cellSize: cellSize,
        width: boardCssWidth,
        height: boardCssHeight,
        rect: rect
      };
    }

    function resetEffects() {
      particles = [];
      rowFlashes = [];
      dropTrails = [];
      callouts = [];
    }

    function dispose() {
      resetEffects();
    }

    return {
      resize: resize,
      triggerEffects: triggerEffects,
      render: render,
      getBoardMetrics: getBoardMetrics,
      resetEffects: resetEffects,
      dispose: dispose
    };
  }

  var api = {
    createRenderer: createRenderer
  };

  root.Tetris = root.Tetris || {};
  root.Tetris.Renderer = api;

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
})(typeof globalThis !== 'undefined' ? globalThis : this);

(function (root) {
  'use strict';

  var Constants = (root.Tetris && root.Tetris.Constants) ||
    (typeof require === 'function' ? require('./constants.js') : null);

  if (!Constants) {
    throw new Error('Tetris.Constants is required before Tetris.Engine');
  }

  var COLS = Constants.COLS;
  var BUFFER_ROWS = Constants.BUFFER_ROWS;
  var TOTAL_ROWS = Constants.TOTAL_ROWS;
  var PIECE_TYPES = Constants.PIECE_TYPES;
  var SHAPES = Constants.SHAPES;
  var SPAWN_POS = Constants.SPAWN_POS;
  var LOCK_DELAY_MS = Constants.LOCK_DELAY_MS;
  var MAX_LOCK_RESETS = Constants.MAX_LOCK_RESETS;
  var LINES_PER_LEVEL = Constants.LINES_PER_LEVEL;
  var MIN_START_LEVEL = Constants.MIN_START_LEVEL;
  var MAX_START_LEVEL = Constants.MAX_START_LEVEL;
  var NEXT_PREVIEW_COUNT = Constants.NEXT_PREVIEW_COUNT;
  var LINE_SCORES = Constants.LINE_SCORES;
  var B2B_MULTIPLIER = Constants.B2B_MULTIPLIER;
  var COMBO_BASE = Constants.COMBO_BASE;
  var SOFT_DROP_POINTS = Constants.SOFT_DROP_POINTS;
  var HARD_DROP_POINTS = Constants.HARD_DROP_POINTS;

  function createEmptyBoard() {
    var board = [];
    var r, c;
    for (r = 0; r < TOTAL_ROWS; r++) {
      var row = [];
      for (c = 0; c < COLS; c++) {
        row.push(null);
      }
      board.push(row);
    }
    return board;
  }

  function cloneBoard(board) {
    var copy = [];
    var r;
    for (r = 0; r < board.length; r++) {
      copy.push(board[r].slice());
    }
    return copy;
  }

  function clampStartLevel(level) {
    var n = Math.floor(Number(level));
    if (!isFinite(n)) {
      return MIN_START_LEVEL;
    }
    if (n < MIN_START_LEVEL) {
      return MIN_START_LEVEL;
    }
    if (n > MAX_START_LEVEL) {
      return MAX_START_LEVEL;
    }
    return n;
  }

  function createEngine(options) {
    var opts = options || {};
    var rng = typeof opts.rng === 'function' ? opts.rng : Math.random;
    var nextCount = typeof opts.nextCount === 'number' && opts.nextCount > 0
      ? Math.floor(opts.nextCount)
      : NEXT_PREVIEW_COUNT;

    var status = 'menu';
    var gameOverReason = null;
    var board = createEmptyBoard();
    var bag = [];
    var nextQueue = [];
    var activePiece = null;
    var holdPiece = null;
    var canHold = true;

    var score = 0;
    var startLevel = MIN_START_LEVEL;
    var level = MIN_START_LEVEL;
    var lines = 0;
    var combo = -1;
    var backToBack = false;

    var gravityTimerMs = 0;
    var lockTimerMs = 0;
    var lockMovesRemaining = MAX_LOCK_RESETS;
    var lowestRow = 0;
    var softDropActive = false;

    function refillBag() {
      var items = PIECE_TYPES.slice();
      var i, j, tmp;
      for (i = items.length - 1; i > 0; i--) {
        j = Math.floor(rng() * (i + 1));
        if (j < 0) j = 0;
        if (j > i) j = i;
        tmp = items[i];
        items[i] = items[j];
        items[j] = tmp;
      }
      for (i = 0; i < items.length; i++) {
        bag.push(items[i]);
      }
    }

    function pullFromBag() {
      if (bag.length === 0) {
        refillBag();
      }
      return bag.shift();
    }

    function fillNextQueue() {
      while (nextQueue.length < nextCount) {
        nextQueue.push(pullFromBag());
      }
    }

    function collides(type, rot, col, row) {
      var matrix = SHAPES[type][rot];
      var r, c, br, bc;
      for (r = 0; r < matrix.length; r++) {
        for (c = 0; c < matrix[r].length; c++) {
          if (!matrix[r][c]) {
            continue;
          }
          bc = col + c;
          br = row + r;
          if (bc < 0 || bc >= COLS || br >= TOTAL_ROWS) {
            return true;
          }
          if (br >= 0 && board[br][bc] !== null) {
            return true;
          }
        }
      }
      return false;
    }

    function isGrounded() {
      if (!activePiece) {
        return false;
      }
      return collides(activePiece.type, activePiece.rot, activePiece.col, activePiece.row + 1);
    }

    function triggerGameOver(reason, events) {
      status = 'gameover';
      gameOverReason = reason;
      softDropActive = false;
      events.push({
        type: 'gameOver',
        reason: reason,
        score: score,
        level: level,
        lines: lines
      });
    }

    function spawnPiece(type, events) {
      var spawn = SPAWN_POS[type];
      var rot = 0;
      var col = spawn.col;
      var row = spawn.row;

      if (collides(type, rot, col, row)) {
        activePiece = {
          type: type,
          rot: rot,
          col: col,
          row: row,
          matrix: SHAPES[type][rot]
        };
        triggerGameOver('block_out', events);
        return false;
      }

      if (!collides(type, rot, col, row + 1)) {
        row += 1;
      }

      activePiece = {
        type: type,
        rot: rot,
        col: col,
        row: row,
        matrix: SHAPES[type][rot]
      };
      lowestRow = row;
      gravityTimerMs = 0;
      lockTimerMs = 0;
      lockMovesRemaining = MAX_LOCK_RESETS;
      return true;
    }

    function spawnNextFromQueue(events) {
      fillNextQueue();
      var nextType = nextQueue.shift();
      fillNextQueue();
      return spawnPiece(nextType, events);
    }

    function registerExtendedPlacementAdjustment() {
      if (!activePiece) {
        return;
      }
      if (isGrounded() || lockTimerMs > 0) {
        if (lockMovesRemaining > 0) {
          lockTimerMs = 0;
          lockMovesRemaining -= 1;
        }
      }
    }

    function lockActivePiece(events) {
      if (!activePiece) {
        return;
      }
      var matrix = activePiece.matrix;
      var lockedCells = [];
      var allInBuffer = true;
      var r, c, br, bc;

      for (r = 0; r < matrix.length; r++) {
        for (c = 0; c < matrix[r].length; c++) {
          if (!matrix[r][c]) {
            continue;
          }
          bc = activePiece.col + c;
          br = activePiece.row + r;
          if (br >= 0 && br < TOTAL_ROWS && bc >= 0 && bc < COLS) {
            board[br][bc] = activePiece.type;
            lockedCells.push({ col: bc, row: br });
          }
          if (br >= BUFFER_ROWS) {
            allInBuffer = false;
          }
        }
      }

      events.push({
        type: 'lock',
        piece: activePiece.type,
        cells: lockedCells
      });

      if (allInBuffer) {
        activePiece = null;
        triggerGameOver('lock_out', events);
        return;
      }

      var clearedRows = [];
      var full;
      for (r = 0; r < TOTAL_ROWS; r++) {
        full = true;
        for (c = 0; c < COLS; c++) {
          if (board[r][c] === null) {
            full = false;
            break;
          }
        }
        if (full) {
          clearedRows.push(r);
        }
      }

      if (clearedRows.length > 0) {
        for (r = clearedRows.length - 1; r >= 0; r--) {
          board.splice(clearedRows[r], 1);
        }
        for (r = 0; r < clearedRows.length; r++) {
          var emptyRow = [];
          for (c = 0; c < COLS; c++) {
            emptyRow.push(null);
          }
          board.unshift(emptyRow);
        }

        var count = clearedRows.length;
        var preClearLevel = level;
        var isTetris = count === 4;
        var isBackToBack = isTetris && backToBack;
        var basePoints = (LINE_SCORES[count] || 0) * preClearLevel;
        if (isBackToBack) {
          basePoints = Math.round(basePoints * B2B_MULTIPLIER);
        }
        backToBack = isTetris;
        combo += 1;
        var comboBonus = combo > 0 ? COMBO_BASE * combo * preClearLevel : 0;
        var points = basePoints + comboBonus;

        score += points;
        lines += count;

        events.push({
          type: 'lineClear',
          count: count,
          rows: clearedRows,
          points: points,
          basePoints: basePoints,
          comboBonus: comboBonus,
          isTetris: isTetris,
          isBackToBack: isBackToBack,
          combo: combo,
          preClearLevel: preClearLevel
        });

        var newLevel = startLevel + Math.floor(lines / LINES_PER_LEVEL);
        if (newLevel > level) {
          level = newLevel;
          events.push({
            type: 'levelUp',
            level: level
          });
        }
      } else {
        combo = -1;
      }

      canHold = true;
      activePiece = null;
      spawnNextFromQueue(events);
    }

    function getGhostY() {
      if (!activePiece) {
        return 0;
      }
      var row = activePiece.row;
      while (!collides(activePiece.type, activePiece.rot, activePiece.col, row + 1)) {
        row += 1;
      }
      return row;
    }

    function start(initialLevel) {
      var events = [];
      startLevel = clampStartLevel(initialLevel !== undefined ? initialLevel : MIN_START_LEVEL);
      level = startLevel;
      score = 0;
      lines = 0;
      combo = -1;
      backToBack = false;
      holdPiece = null;
      canHold = true;
      gameOverReason = null;
      softDropActive = false;
      board = createEmptyBoard();
      bag = [];
      nextQueue = [];
      status = 'playing';

      fillNextQueue();
      spawnNextFromQueue(events);

      return { events: events };
    }

    function pause() {
      if (status === 'playing') {
        status = 'paused';
        softDropActive = false;
      }
    }

    function resume() {
      if (status === 'paused') {
        status = 'playing';
      }
    }

    function togglePause() {
      if (status === 'playing') {
        pause();
      } else if (status === 'paused') {
        resume();
      }
      return status;
    }

    function reset() {
      status = 'menu';
      gameOverReason = null;
      board = createEmptyBoard();
      bag = [];
      nextQueue = [];
      activePiece = null;
      holdPiece = null;
      canHold = true;
      score = 0;
      level = startLevel;
      lines = 0;
      combo = -1;
      backToBack = false;
      gravityTimerMs = 0;
      lockTimerMs = 0;
      lockMovesRemaining = MAX_LOCK_RESETS;
      lowestRow = 0;
      softDropActive = false;
    }

    function step(dtMs) {
      var events = [];
      if (status !== 'playing' || !activePiece || typeof dtMs !== 'number' || !isFinite(dtMs) || dtMs <= 0) {
        return { events: events };
      }

      var remaining = dtMs;
      var softDropCells = 0;

      while (remaining > 0 && status === 'playing' && activePiece) {
        if (!isGrounded()) {
          var interval = softDropActive ? Constants.getSoftDropMs(level) : Constants.getGravityMs(level);
          var needed = Math.max(0, interval - gravityTimerMs);
          if (remaining >= needed) {
            remaining -= needed;
            gravityTimerMs = 0;
            activePiece.row += 1;
            if (activePiece.row > lowestRow) {
              lowestRow = activePiece.row;
              lockMovesRemaining = MAX_LOCK_RESETS;
              lockTimerMs = 0;
            }
            if (softDropActive) {
              score += SOFT_DROP_POINTS;
              softDropCells += 1;
            }
          } else {
            gravityTimerMs += remaining;
            remaining = 0;
          }
        } else {
          gravityTimerMs = 0;
          var lockNeeded = Math.max(0, LOCK_DELAY_MS - lockTimerMs);
          if (remaining >= lockNeeded) {
            remaining -= lockNeeded;
            lockTimerMs = LOCK_DELAY_MS;
            if (softDropCells > 0) {
              events.push({ type: 'softDrop', cells: softDropCells });
              softDropCells = 0;
            }
            lockActivePiece(events);
          } else {
            lockTimerMs += remaining;
            remaining = 0;
          }
        }
      }

      if (softDropCells > 0) {
        events.push({ type: 'softDrop', cells: softDropCells });
      }

      return { events: events };
    }

    function moveHorizontal(dir) {
      if (status !== 'playing' || !activePiece) {
        return { changed: false, events: [] };
      }
      var nextCol = activePiece.col + dir;
      if (collides(activePiece.type, activePiece.rot, nextCol, activePiece.row)) {
        return { changed: false, events: [] };
      }
      activePiece.col = nextCol;
      registerExtendedPlacementAdjustment();
      return {
        changed: true,
        events: [{ type: 'move', dir: dir }]
      };
    }

    function moveLeft() {
      return moveHorizontal(-1);
    }

    function moveRight() {
      return moveHorizontal(1);
    }

    function rotate(delta) {
      if (status !== 'playing' || !activePiece) {
        return { changed: false, kicked: false, events: [] };
      }
      if (activePiece.type === 'O') {
        return { changed: false, kicked: false, events: [] };
      }
      var fromRot = activePiece.rot;
      var toRot = ((fromRot + delta) % 4 + 4) % 4;
      var kicks = Constants.getWallKicks(activePiece.type, fromRot, toRot);
      var i, dCol, dRow, nextCol, nextRow;

      for (i = 0; i < kicks.length; i++) {
        dCol = kicks[i][0];
        dRow = kicks[i][1];
        nextCol = activePiece.col + dCol;
        nextRow = activePiece.row + dRow;
        if (!collides(activePiece.type, toRot, nextCol, nextRow)) {
          activePiece.rot = toRot;
          activePiece.col = nextCol;
          activePiece.row = nextRow;
          activePiece.matrix = SHAPES[activePiece.type][toRot];
          if (activePiece.row > lowestRow) {
            lowestRow = activePiece.row;
            lockMovesRemaining = MAX_LOCK_RESETS;
            lockTimerMs = 0;
          } else {
            registerExtendedPlacementAdjustment();
          }
          var kicked = i > 0;
          return {
            changed: true,
            kicked: kicked,
            events: [{ type: 'rotate', kicked: kicked }]
          };
        }
      }

      return { changed: false, kicked: false, events: [] };
    }

    function rotateCW() {
      return rotate(1);
    }

    function rotateCCW() {
      return rotate(3);
    }

    function setSoftDrop(active) {
      softDropActive = Boolean(active);
    }

    function softDropStep() {
      if (status !== 'playing' || !activePiece) {
        return { changed: false, events: [] };
      }
      if (collides(activePiece.type, activePiece.rot, activePiece.col, activePiece.row + 1)) {
        return { changed: false, events: [] };
      }
      activePiece.row += 1;
      score += SOFT_DROP_POINTS;
      gravityTimerMs = 0;
      if (activePiece.row > lowestRow) {
        lowestRow = activePiece.row;
        lockMovesRemaining = MAX_LOCK_RESETS;
        lockTimerMs = 0;
      }
      return {
        changed: true,
        events: [{ type: 'softDrop', cells: 1 }]
      };
    }

    function hardDrop() {
      if (status !== 'playing' || !activePiece) {
        return { changed: false, events: [] };
      }
      var events = [];
      var startY = activePiece.row;
      var endY = getGhostY();
      var cells = endY - startY;

      activePiece.row = endY;
      score += cells * HARD_DROP_POINTS;

      events.push({
        type: 'hardDrop',
        piece: activePiece.type,
        col: activePiece.col,
        width: activePiece.matrix[0].length,
        startY: startY,
        endY: endY,
        cells: cells
      });

      lockActivePiece(events);
      return { changed: true, events: events };
    }

    function hold() {
      if (status !== 'playing' || !activePiece || !canHold) {
        return { changed: false, events: [] };
      }
      var events = [];
      var prevType = activePiece.type;
      canHold = false;
      events.push({ type: 'hold', piece: prevType });

      if (holdPiece === null) {
        holdPiece = prevType;
        spawnNextFromQueue(events);
      } else {
        var swapType = holdPiece;
        holdPiece = prevType;
        spawnPiece(swapType, events);
      }

      return { changed: true, events: events };
    }

    function getSnapshot() {
      return {
        status: status,
        gameOverReason: gameOverReason,
        board: cloneBoard(board),
        activePiece: activePiece ? {
          type: activePiece.type,
          rot: activePiece.rot,
          col: activePiece.col,
          row: activePiece.row,
          matrix: activePiece.matrix
        } : null,
        ghostY: getGhostY(),
        holdPiece: holdPiece,
        canHold: canHold,
        nextQueue: nextQueue.slice(),
        score: score,
        level: level,
        startLevel: startLevel,
        lines: lines,
        combo: combo,
        backToBack: backToBack,
        lockTimerMs: lockTimerMs,
        lockDelayMs: LOCK_DELAY_MS,
        lockMovesRemaining: lockMovesRemaining,
        isGrounded: isGrounded()
      };
    }

    return {
      start: start,
      pause: pause,
      resume: resume,
      togglePause: togglePause,
      reset: reset,
      step: step,
      moveLeft: moveLeft,
      moveRight: moveRight,
      rotateCW: rotateCW,
      rotateCCW: rotateCCW,
      setSoftDrop: setSoftDrop,
      softDropStep: softDropStep,
      hardDrop: hardDrop,
      hold: hold,
      getGhostY: getGhostY,
      getSnapshot: getSnapshot
    };
  }

  var api = {
    createEngine: createEngine
  };

  root.Tetris = root.Tetris || {};
  root.Tetris.Engine = api;

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
})(typeof globalThis !== 'undefined' ? globalThis : this);

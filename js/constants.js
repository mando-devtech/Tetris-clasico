(function (root) {
  'use strict';

  var COLS = 10;
  var VISIBLE_ROWS = 20;
  var BUFFER_ROWS = 4;
  var TOTAL_ROWS = VISIBLE_ROWS + BUFFER_ROWS;

  var PIECE_TYPES = ['I', 'O', 'T', 'S', 'Z', 'J', 'L'];

  function rotateMatrixCW(matrix) {
    var n = matrix.length;
    var rotated = [];
    var r, c;
    for (r = 0; r < n; r++) {
      var row = [];
      for (c = 0; c < n; c++) {
        row.push(matrix[n - 1 - c][r]);
      }
      rotated.push(row);
    }
    return rotated;
  }

  function buildRotationStates(baseMatrix) {
    var s0 = baseMatrix;
    var s1 = rotateMatrixCW(s0);
    var s2 = rotateMatrixCW(s1);
    var s3 = rotateMatrixCW(s2);
    return [s0, s1, s2, s3];
  }

  var SHAPES = {
    I: buildRotationStates([
      [0, 0, 0, 0],
      [1, 1, 1, 1],
      [0, 0, 0, 0],
      [0, 0, 0, 0]
    ]),
    O: buildRotationStates([
      [1, 1],
      [1, 1]
    ]),
    T: buildRotationStates([
      [0, 1, 0],
      [1, 1, 1],
      [0, 0, 0]
    ]),
    S: buildRotationStates([
      [0, 1, 1],
      [1, 1, 0],
      [0, 0, 0]
    ]),
    Z: buildRotationStates([
      [1, 1, 0],
      [0, 1, 1],
      [0, 0, 0]
    ]),
    J: buildRotationStates([
      [1, 0, 0],
      [1, 1, 1],
      [0, 0, 0]
    ]),
    L: buildRotationStates([
      [0, 0, 1],
      [1, 1, 1],
      [0, 0, 0]
    ])
  };

  var SPAWN_POS = {
    I: { col: 3, row: 2 },
    O: { col: 4, row: 2 },
    T: { col: 3, row: 2 },
    S: { col: 3, row: 2 },
    Z: { col: 3, row: 2 },
    J: { col: 3, row: 2 },
    L: { col: 3, row: 2 }
  };

  var COLORS = {
    I: {
      fill: '#22d3ee',
      light: '#a5f3fc',
      dark: '#0891b2',
      glow: 'rgba(34, 211, 238, 0.55)',
      ghostFill: 'rgba(34, 211, 238, 0.16)',
      ghostStroke: 'rgba(34, 211, 238, 0.65)'
    },
    O: {
      fill: '#facc15',
      light: '#fef08a',
      dark: '#ca8a04',
      glow: 'rgba(250, 204, 21, 0.55)',
      ghostFill: 'rgba(250, 204, 21, 0.16)',
      ghostStroke: 'rgba(250, 204, 21, 0.65)'
    },
    T: {
      fill: '#c084fc',
      light: '#e9d5ff',
      dark: '#9333ea',
      glow: 'rgba(192, 132, 252, 0.55)',
      ghostFill: 'rgba(192, 132, 252, 0.16)',
      ghostStroke: 'rgba(192, 132, 252, 0.65)'
    },
    S: {
      fill: '#4ade80',
      light: '#bbf7d0',
      dark: '#16a34a',
      glow: 'rgba(74, 222, 128, 0.55)',
      ghostFill: 'rgba(74, 222, 128, 0.16)',
      ghostStroke: 'rgba(74, 222, 128, 0.65)'
    },
    Z: {
      fill: '#f87171',
      light: '#fecaca',
      dark: '#dc2626',
      glow: 'rgba(248, 113, 113, 0.55)',
      ghostFill: 'rgba(248, 113, 113, 0.16)',
      ghostStroke: 'rgba(248, 113, 113, 0.65)'
    },
    J: {
      fill: '#60a5fa',
      light: '#bfdbfe',
      dark: '#2563eb',
      glow: 'rgba(96, 165, 250, 0.55)',
      ghostFill: 'rgba(96, 165, 250, 0.16)',
      ghostStroke: 'rgba(96, 165, 250, 0.65)'
    },
    L: {
      fill: '#fb923c',
      light: '#fed7aa',
      dark: '#ea580c',
      glow: 'rgba(251, 146, 60, 0.55)',
      ghostFill: 'rgba(251, 146, 60, 0.16)',
      ghostStroke: 'rgba(251, 146, 60, 0.65)'
    }
  };

  // Screen-space SRS wall-kick offsets: [dCol, dRow] where +dCol = right, +dRow = down.
  var WALL_KICKS = {
    JLSTZ: {
      '0>1': [[0, 0], [-1, 0], [-1, -1], [0, 2], [-1, 2]],
      '1>0': [[0, 0], [1, 0], [1, 1], [0, -2], [1, -2]],
      '1>2': [[0, 0], [1, 0], [1, 1], [0, -2], [1, -2]],
      '2>1': [[0, 0], [-1, 0], [-1, -1], [0, 2], [-1, 2]],
      '2>3': [[0, 0], [1, 0], [1, -1], [0, 2], [1, 2]],
      '3>2': [[0, 0], [-1, 0], [-1, 1], [0, -2], [-1, -2]],
      '3>0': [[0, 0], [-1, 0], [-1, 1], [0, -2], [-1, -2]],
      '0>3': [[0, 0], [1, 0], [1, -1], [0, 2], [1, 2]]
    },
    I: {
      '0>1': [[0, 0], [-2, 0], [1, 0], [-2, 1], [1, -2]],
      '1>0': [[0, 0], [2, 0], [-1, 0], [2, -1], [-1, 2]],
      '1>2': [[0, 0], [-1, 0], [2, 0], [-1, -2], [2, 1]],
      '2>1': [[0, 0], [1, 0], [-2, 0], [1, 2], [-2, -1]],
      '2>3': [[0, 0], [2, 0], [-1, 0], [2, -1], [-1, 2]],
      '3>2': [[0, 0], [-2, 0], [1, 0], [-2, 1], [1, -2]],
      '3>0': [[0, 0], [1, 0], [-2, 0], [1, 2], [-2, -1]],
      '0>3': [[0, 0], [-1, 0], [2, 0], [-1, -2], [2, 1]]
    },
    O: {
      '0>1': [[0, 0]],
      '1>0': [[0, 0]],
      '1>2': [[0, 0]],
      '2>1': [[0, 0]],
      '2>3': [[0, 0]],
      '3>2': [[0, 0]],
      '3>0': [[0, 0]],
      '0>3': [[0, 0]]
    }
  };

  var EMPTY_KICKS = Object.freeze([]);

  var LOCK_DELAY_MS = 500;
  var MAX_LOCK_RESETS = 15;
  var LINES_PER_LEVEL = 10;

  var MIN_START_LEVEL = 1;
  var MAX_START_LEVEL = 15;
  var MAX_GRAVITY_LEVEL = 20;

  var DAS_MS = 160;
  var ARR_MS = 35;
  var SOFT_DROP_REPEAT_MS = 40;

  var GAMEPAD_DEADZONE_X = 0.30;
  var GAMEPAD_SOFT_DROP_Y = 0.45;

  var TOUCH_SENSITIVITY_MIN = 1;
  var TOUCH_SENSITIVITY_MAX = 10;
  var TOUCH_SENSITIVITY_DEFAULT = 5;

  var NEXT_PREVIEW_COUNT = 3;

  var LINE_SCORES = {
    1: 100,
    2: 300,
    3: 500,
    4: 800
  };
  var B2B_MULTIPLIER = 1.5;
  var COMBO_BASE = 50;
  var SOFT_DROP_POINTS = 1;
  var HARD_DROP_POINTS = 2;

  var STORAGE_KEY = 'tetris_clasico_v1';
  var CACHE_NAME = 'tetris-clasico-v1';

  var DEFAULT_STATE = {
    bestScore: 0,
    bestLevel: 0,
    bestLines: 0,
    touchSensitivity: TOUCH_SENSITIVITY_DEFAULT,
    musicEnabled: true,
    sfxEnabled: true,
    startLevel: MIN_START_LEVEL
  };

  function isFiniteInteger(n) {
    return typeof n === 'number' && isFinite(n) && Math.floor(n) === n;
  }

  function normalizeRot(r) {
    return ((r % 4) + 4) % 4;
  }

  function getWallKicks(type, fromRot, toRot) {
    if (!isFiniteInteger(fromRot) || !isFiniteInteger(toRot)) {
      return EMPTY_KICKS;
    }
    var table;
    if (type === 'I') {
      table = WALL_KICKS.I;
    } else if (type === 'O') {
      table = WALL_KICKS.O;
    } else if (type === 'J' || type === 'L' || type === 'S' || type === 'T' || type === 'Z') {
      table = WALL_KICKS.JLSTZ;
    } else {
      return EMPTY_KICKS;
    }
    var key = normalizeRot(fromRot) + '>' + normalizeRot(toRot);
    return Object.prototype.hasOwnProperty.call(table, key) ? table[key] : EMPTY_KICKS;
  }

  function getGravityMs(level) {
    var num;
    if (typeof level === 'number') {
      num = level;
    } else if (typeof level === 'string' && level.trim() !== '') {
      num = Number(level);
    } else {
      num = 1;
    }
    if (!isFinite(num)) {
      num = num === Infinity ? MAX_GRAVITY_LEVEL : 1;
    }
    var eff = Math.max(1, Math.min(MAX_GRAVITY_LEVEL, Math.floor(num)));
    return Math.pow(0.8 - (eff - 1) * 0.007, eff - 1) * 1000;
  }

  function getSoftDropMs(level) {
    return Math.min(SOFT_DROP_REPEAT_MS, getGravityMs(level));
  }

  function deepFreeze(obj) {
    if (obj === null || (typeof obj !== 'object' && typeof obj !== 'function')) {
      return obj;
    }
    if (!Object.isFrozen(obj)) {
      Object.freeze(obj);
    }
    var keys = Object.keys(obj);
    var i;
    for (i = 0; i < keys.length; i++) {
      deepFreeze(obj[keys[i]]);
    }
    return obj;
  }

  var api = {
    COLS: COLS,
    VISIBLE_ROWS: VISIBLE_ROWS,
    BUFFER_ROWS: BUFFER_ROWS,
    TOTAL_ROWS: TOTAL_ROWS,
    PIECE_TYPES: PIECE_TYPES,
    SHAPES: SHAPES,
    SPAWN_POS: SPAWN_POS,
    COLORS: COLORS,
    WALL_KICKS: WALL_KICKS,
    LOCK_DELAY_MS: LOCK_DELAY_MS,
    MAX_LOCK_RESETS: MAX_LOCK_RESETS,
    LINES_PER_LEVEL: LINES_PER_LEVEL,
    MIN_START_LEVEL: MIN_START_LEVEL,
    MAX_START_LEVEL: MAX_START_LEVEL,
    MAX_GRAVITY_LEVEL: MAX_GRAVITY_LEVEL,
    DAS_MS: DAS_MS,
    ARR_MS: ARR_MS,
    SOFT_DROP_REPEAT_MS: SOFT_DROP_REPEAT_MS,
    GAMEPAD_DEADZONE_X: GAMEPAD_DEADZONE_X,
    GAMEPAD_SOFT_DROP_Y: GAMEPAD_SOFT_DROP_Y,
    TOUCH_SENSITIVITY_MIN: TOUCH_SENSITIVITY_MIN,
    TOUCH_SENSITIVITY_MAX: TOUCH_SENSITIVITY_MAX,
    TOUCH_SENSITIVITY_DEFAULT: TOUCH_SENSITIVITY_DEFAULT,
    NEXT_PREVIEW_COUNT: NEXT_PREVIEW_COUNT,
    LINE_SCORES: LINE_SCORES,
    B2B_MULTIPLIER: B2B_MULTIPLIER,
    COMBO_BASE: COMBO_BASE,
    SOFT_DROP_POINTS: SOFT_DROP_POINTS,
    HARD_DROP_POINTS: HARD_DROP_POINTS,
    STORAGE_KEY: STORAGE_KEY,
    CACHE_NAME: CACHE_NAME,
    DEFAULT_STATE: DEFAULT_STATE,
    getWallKicks: getWallKicks,
    getGravityMs: getGravityMs,
    getSoftDropMs: getSoftDropMs
  };

  deepFreeze(api);

  if (root && typeof root === 'object') {
    root.Tetris = root.Tetris || {};
    root.Tetris.Constants = api;
  }
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
})(typeof globalThis !== 'undefined' ? globalThis : (typeof self !== 'undefined' ? self : this));

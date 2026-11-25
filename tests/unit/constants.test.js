'use strict';

const { describe, it } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const zlib = require('node:zlib');

const ROOT_DIR = path.resolve(__dirname, '../..');
const Constants = require(path.join(ROOT_DIR, 'js/constants.js'));

function negZero(v) {
  return v === 0 ? 0 : -v;
}

function parsePng(filePath) {
  const buf = fs.readFileSync(filePath);
  const sig = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
  assert.ok(buf.length >= 33, `${path.basename(filePath)} too short`);
  assert.ok(buf.subarray(0, 8).equals(sig), `${path.basename(filePath)} missing PNG signature`);

  let offset = 8;
  let width = 0;
  let height = 0;
  let bitDepth = 0;
  let colorType = 0;
  let interlace = 0;
  const idatChunks = [];

  while (offset + 12 <= buf.length) {
    const length = buf.readUInt32BE(offset);
    const type = buf.subarray(offset + 4, offset + 8).toString('ascii');
    const dataStart = offset + 8;
    const dataEnd = dataStart + length;
    assert.ok(dataEnd + 4 <= buf.length, `Truncated PNG chunk ${type}`);
    const data = buf.subarray(dataStart, dataEnd);

    if (type === 'IHDR') {
      width = data.readUInt32BE(0);
      height = data.readUInt32BE(4);
      bitDepth = data.readUInt8(8);
      colorType = data.readUInt8(9);
      interlace = data.readUInt8(12);
    } else if (type === 'IDAT') {
      idatChunks.push(data);
    } else if (type === 'IEND') {
      break;
    }
    offset = dataEnd + 4;
  }

  assert.strictEqual(bitDepth, 8, `${path.basename(filePath)} bitDepth must be 8`);
  assert.ok(colorType === 2 || colorType === 6, `${path.basename(filePath)} colorType must be RGB (2) or RGBA (6)`);
  assert.strictEqual(interlace, 0, `${path.basename(filePath)} must be non-interlaced`);

  const bpp = colorType === 6 ? 4 : 3;
  const stride = width * bpp;
  const inflated = zlib.inflateSync(Buffer.concat(idatChunks));
  assert.strictEqual(inflated.length, height * (1 + stride), 'Unexpected PNG IDAT inflated size');

  const pixels = new Uint8Array(height * stride);

  function paeth(a, b, c) {
    const p = a + b - c;
    const pa = Math.abs(p - a);
    const pb = Math.abs(p - b);
    const pc = Math.abs(p - c);
    if (pa <= pb && pa <= pc) return a;
    if (pb <= pc) return b;
    return c;
  }

  for (let y = 0; y < height; y++) {
    const srcRowStart = y * (1 + stride);
    const filter = inflated[srcRowStart];
    const dstRowStart = y * stride;

    for (let x = 0; x < stride; x++) {
      const raw = inflated[srcRowStart + 1 + x];
      const a = x >= bpp ? pixels[dstRowStart + x - bpp] : 0;
      const b = y > 0 ? pixels[(y - 1) * stride + x] : 0;
      const c = y > 0 && x >= bpp ? pixels[(y - 1) * stride + x - bpp] : 0;
      let val;
      if (filter === 0) {
        val = raw;
      } else if (filter === 1) {
        val = (raw + a) & 0xff;
      } else if (filter === 2) {
        val = (raw + b) & 0xff;
      } else if (filter === 3) {
        val = (raw + ((a + b) >> 1)) & 0xff;
      } else if (filter === 4) {
        val = (raw + paeth(a, b, c)) & 0xff;
      } else {
        assert.fail(`Unsupported PNG filter ${filter}`);
      }
      pixels[dstRowStart + x] = val;
    }
  }

  function getPixel(x, y) {
    const idx = (y * width + x) * bpp;
    return {
      r: pixels[idx],
      g: pixels[idx + 1],
      b: pixels[idx + 2],
      a: bpp === 4 ? pixels[idx + 3] : 255
    };
  }

  return { width, height, bitDepth, colorType, getPixel };
}

function createSwSandbox({ existingPaths = new Set(), initialCaches = {}, origin = 'https://example.github.io', scopePath = '/tetris/' } = {}) {
  const store = new Map();
  for (const [cacheName, entries] of Object.entries(initialCaches)) {
    const map = new Map();
    for (const [k, v] of Object.entries(entries)) {
      map.set(k, v);
    }
    store.set(cacheName, map);
  }

  const baseHref = origin + scopePath;

  function normalizeKey(reqOrUrl) {
    const raw = typeof reqOrUrl === 'string' ? reqOrUrl : reqOrUrl.url;
    return new URL(raw, baseHref).href;
  }

  const cancelledResponses = [];
  const cacheMatchCalls = [];

  function makeResponseStub(
    bodyText,
    { ok = true, status = 200, type = 'basic', redirected = false, url = null, hasBody = true, cancelRejects = false } = {}
  ) {
    const headers = new Map([['content-type', 'text/plain']]);
    const stub = {
      ok,
      status,
      type,
      redirected,
      headers,
      body: hasBody
        ? {
            cancelCount: 0,
            async cancel() {
              stub.body.cancelCount += 1;
              cancelledResponses.push({ url, status, type, redirected, bodyText });
              if (cancelRejects) {
                throw new TypeError('Stream cancel failed');
              }
              return undefined;
            }
          }
        : null,
      clone() {
        return makeResponseStub(bodyText, { ok, status, type, redirected, url, hasBody, cancelRejects });
      },
      async text() {
        return bodyText;
      }
    };
    return stub;
  }

  function openCacheObj(cacheMap) {
    return {
      async put(reqOrUrl, response) {
        cacheMap.set(normalizeKey(reqOrUrl), response);
      },
      async match(reqOrUrl) {
        return cacheMap.get(normalizeKey(reqOrUrl));
      },
      async keys() {
        return Array.from(cacheMap.keys()).map((u) => ({ url: u }));
      }
    };
  }

  const caches = {
    async open(name) {
      if (!store.has(name)) {
        store.set(name, new Map());
      }
      return openCacheObj(store.get(name));
    },
    async keys() {
      return Array.from(store.keys());
    },
    async delete(name) {
      return store.delete(name);
    },
    async has(name) {
      return store.has(name);
    },
    async match(reqOrUrl, options) {
      const key = normalizeKey(reqOrUrl);
      const cacheName = options && typeof options.cacheName === 'string' ? options.cacheName : null;
      cacheMatchCalls.push({ key, cacheName });
      if (cacheName !== null) {
        const target = store.get(cacheName);
        return target ? target.get(key) : undefined;
      }
      for (const cacheMap of store.values()) {
        if (cacheMap.has(key)) {
          return cacheMap.get(key);
        }
      }
      return undefined;
    }
  };

  let online = true;
  let customFetchHandler = null;
  const fetchCalls = [];
  let skipWaitingCalled = false;
  let clientsClaimCalled = false;
  const listeners = {};

  class MockRequest {
    constructor(input, init = {}) {
      if (typeof input === 'string') {
        this.url = new URL(input, baseHref).href;
      } else {
        this.url = input.url;
      }
      this.method = init.method || 'GET';
      this.cache = init.cache || 'default';
      this.mode = init.mode || 'same-origin';
    }
  }

  const selfObj = {
    location: {
      origin,
      href: baseHref + 'service-worker.js'
    },
    registration: {
      scope: baseHref
    },
    addEventListener(type, fn) {
      listeners[type] = fn;
    },
    skipWaiting() {
      skipWaitingCalled = true;
      return Promise.resolve();
    },
    clients: {
      claim() {
        clientsClaimCalled = true;
        return Promise.resolve();
      }
    }
  };

  async function mockFetch(reqOrUrl) {
    const reqUrl = typeof reqOrUrl === 'string' ? new URL(reqOrUrl, baseHref).href : reqOrUrl.url;
    fetchCalls.push(reqUrl);
    if (!online) {
      throw new TypeError('Failed to fetch (offline)');
    }
    if (customFetchHandler) {
      return customFetchHandler(reqUrl, reqOrUrl);
    }
    const relPath = reqUrl.startsWith(baseHref) ? './' + reqUrl.slice(baseHref.length) : reqUrl;
    if (existingPaths.has(relPath)) {
      return makeResponseStub(`body:${relPath}`, { ok: true, status: 200, type: 'basic', url: reqUrl });
    }
    return makeResponseStub('Not Found', { ok: false, status: 404, type: 'basic', url: reqUrl });
  }

  const sandbox = {
    self: selfObj,
    caches,
    fetch: mockFetch,
    URL,
    Request: MockRequest,
    Response: {
      error() {
        return { type: 'error', status: 0, ok: false };
      }
    },
    Promise,
    console
  };
  sandbox.globalThis = sandbox;

  const swCode = fs.readFileSync(path.join(ROOT_DIR, 'service-worker.js'), 'utf8');
  vm.runInNewContext(swCode, sandbox, { filename: 'service-worker.js' });
  const exported = vm.runInContext(
    '({ CACHE_NAME: typeof CACHE_NAME !== "undefined" ? CACHE_NAME : self.CACHE_NAME, ' +
    'CACHE_PREFIX: typeof CACHE_PREFIX !== "undefined" ? CACHE_PREFIX : self.CACHE_PREFIX, ' +
    'PRECACHE_URLS: typeof PRECACHE_URLS !== "undefined" ? PRECACHE_URLS : self.PRECACHE_URLS })',
    sandbox
  );

  return {
    exported,
    listeners,
    store,
    caches,
    fetchCalls,
    cancelledResponses,
    cacheMatchCalls,
    makeResponseStub,
    setOnline(val) {
      online = val;
    },
    setFetchHandler(fn) {
      customFetchHandler = fn;
    },
    wasSkipWaitingCalled() {
      return skipWaitingCalled;
    },
    wasClientsClaimCalled() {
      return clientsClaimCalled;
    }
  };
}

describe('1. Tetris.Constants — Module Loading (CJS & Browser vm) & Immutability', () => {
  it('loads cleanly via CommonJS require without DOM globals', () => {
    assert.ok(Constants && typeof Constants === 'object');
    assert.strictEqual(typeof Constants.getGravityMs, 'function');
    assert.strictEqual(typeof Constants.getSoftDropMs, 'function');
    assert.strictEqual(typeof Constants.getWallKicks, 'function');
  });

  it('attaches Tetris.Constants in a zero-DOM browser-like vm context matching CJS export', () => {
    const code = fs.readFileSync(path.join(ROOT_DIR, 'js/constants.js'), 'utf8');
    const sandbox = {};
    sandbox.window = sandbox;
    sandbox.globalThis = sandbox;

    vm.runInNewContext(code, sandbox, { filename: 'js/constants.js' });
    assert.ok(sandbox.Tetris && sandbox.Tetris.Constants);
    assert.deepStrictEqual(
      Object.keys(sandbox.Tetris.Constants).sort(),
      Object.keys(Constants).sort()
    );
    const vmSnapshot = JSON.parse(JSON.stringify({
      SHAPES: sandbox.Tetris.Constants.SHAPES,
      WALL_KICKS: sandbox.Tetris.Constants.WALL_KICKS,
      COLORS: sandbox.Tetris.Constants.COLORS,
      DEFAULT_STATE: sandbox.Tetris.Constants.DEFAULT_STATE
    }));
    assert.deepStrictEqual(vmSnapshot.SHAPES, Constants.SHAPES);
    assert.deepStrictEqual(vmSnapshot.WALL_KICKS, Constants.WALL_KICKS);
    assert.deepStrictEqual(vmSnapshot.COLORS, Constants.COLORS);
    assert.deepStrictEqual(vmSnapshot.DEFAULT_STATE, Constants.DEFAULT_STATE);
    assert.strictEqual(sandbox.Tetris.Constants.getGravityMs(10), Constants.getGravityMs(10));
  });

  it('supports ES5 fallback without globalThis/self alongside module.exports', () => {
    const code = fs.readFileSync(path.join(ROOT_DIR, 'js/constants.js'), 'utf8');
    const mod = { exports: {} };
    const sandbox = {
      globalThis: undefined,
      self: undefined,
      module: mod,
      exports: mod.exports
    };
    vm.runInNewContext(code, sandbox, { filename: 'js/constants.js' });
    assert.ok(sandbox.Tetris && sandbox.Tetris.Constants);
    assert.strictEqual(mod.exports, sandbox.Tetris.Constants);
    assert.strictEqual(mod.exports.COLS, 10);
  });

  it('deep-freezes all exported structures and rejects strict-mode mutations', () => {
    assert.ok(Object.isFrozen(Constants));
    assert.ok(Object.isFrozen(Constants.PIECE_TYPES));
    assert.ok(Object.isFrozen(Constants.SHAPES));
    assert.ok(Object.isFrozen(Constants.SHAPES.T));
    assert.ok(Object.isFrozen(Constants.SHAPES.T[0]));
    assert.ok(Object.isFrozen(Constants.SHAPES.T[0][0]));
    assert.ok(Object.isFrozen(Constants.SPAWN_POS));
    assert.ok(Object.isFrozen(Constants.SPAWN_POS.I));
    assert.ok(Object.isFrozen(Constants.COLORS));
    assert.ok(Object.isFrozen(Constants.COLORS.I));
    assert.ok(Object.isFrozen(Constants.WALL_KICKS));
    assert.ok(Object.isFrozen(Constants.WALL_KICKS.I['0>1']));
    assert.ok(Object.isFrozen(Constants.WALL_KICKS.I['0>1'][0]));
    assert.ok(Object.isFrozen(Constants.LINE_SCORES));
    assert.ok(Object.isFrozen(Constants.DEFAULT_STATE));

    assert.throws(() => {
      Constants.COLS = 12;
    }, TypeError);
    assert.throws(() => {
      Constants.PIECE_TYPES.push('X');
    }, TypeError);
    assert.throws(() => {
      Constants.DEFAULT_STATE.bestScore = 999;
    }, TypeError);
    assert.throws(() => {
      Constants.SHAPES.T[0][0][0] = 9;
    }, TypeError);
  });
});

describe('2. Grid Dimensions & Piece Definitions', () => {
  it('defines exact 10x24 playfield grid constants', () => {
    assert.strictEqual(Constants.COLS, 10);
    assert.strictEqual(Constants.VISIBLE_ROWS, 20);
    assert.strictEqual(Constants.BUFFER_ROWS, 4);
    assert.strictEqual(Constants.TOTAL_ROWS, 24);
    assert.strictEqual(Constants.TOTAL_ROWS, Constants.VISIBLE_ROWS + Constants.BUFFER_ROWS);
  });

  it('defines exact 7 unique PIECE_TYPES', () => {
    assert.deepStrictEqual(Constants.PIECE_TYPES, ['I', 'O', 'T', 'S', 'Z', 'J', 'L']);
    assert.strictEqual(new Set(Constants.PIECE_TYPES).size, 7);
  });

  it('defines valid 4-state SRS matrices with exact CW rotation and 4 minos per state', () => {
    for (const type of Constants.PIECE_TYPES) {
      const states = Constants.SHAPES[type];
      assert.strictEqual(states.length, 4, `${type} must have 4 rotation states`);
      const N = type === 'I' ? 4 : (type === 'O' ? 2 : 3);

      for (let s = 0; s < 4; s++) {
        const mat = states[s];
        assert.strictEqual(mat.length, N, `${type}[${s}] must have ${N} rows`);
        let minos = 0;
        for (let r = 0; r < N; r++) {
          assert.strictEqual(mat[r].length, N, `${type}[${s}][${r}] must have ${N} cols`);
          for (let c = 0; c < N; c++) {
            const cell = mat[r][c];
            assert.ok(cell === 0 || cell === 1, `${type}[${s}] cell must be 0 or 1`);
            minos += cell;
          }
        }
        assert.strictEqual(minos, 4, `${type}[${s}] must have exactly 4 minos`);

        const next = states[(s + 1) % 4];
        for (let r = 0; r < N; r++) {
          for (let c = 0; c < N; c++) {
            assert.strictEqual(
              next[r][c],
              mat[N - 1 - c][r],
              `${type} CW rotation ${s}->${(s + 1) % 4} mismatch at (${r},${c})`
            );
          }
        }
      }
    }

    for (let s = 0; s < 4; s++) {
      assert.deepStrictEqual(Constants.SHAPES.O[s], [[1, 1], [1, 1]]);
    }
  });

  it('defines valid SPAWN_POS keeping all state-0 minos inside top buffer (rows 2..3)', () => {
    for (const type of Constants.PIECE_TYPES) {
      const pos = Constants.SPAWN_POS[type];
      assert.deepStrictEqual(pos, { col: type === 'O' ? 4 : 3, row: 2 });

      const mat = Constants.SHAPES[type][0];
      const occupied = [];
      for (let r = 0; r < mat.length; r++) {
        for (let c = 0; c < mat[r].length; c++) {
          if (mat[r][c] === 1) {
            const absCol = pos.col + c;
            const absRow = pos.row + r;
            assert.ok(absCol >= 0 && absCol < Constants.COLS, `${type} spawn col out of bounds: ${absCol}`);
            assert.ok(absRow >= 0 && absRow < Constants.BUFFER_ROWS, `${type} spawn row outside buffer: ${absRow}`);
            occupied.push([absCol, absRow]);
          }
        }
      }
      assert.strictEqual(occupied.length, 4);
    }
  });

  it('defines complete modern neon COLORS palette for all 7 pieces', () => {
    const expectedFills = {
      I: '#22d3ee',
      O: '#facc15',
      T: '#c084fc',
      S: '#4ade80',
      Z: '#f87171',
      J: '#60a5fa',
      L: '#fb923c'
    };
    const fields = ['fill', 'light', 'dark', 'glow', 'ghostFill', 'ghostStroke'];
    for (const type of Constants.PIECE_TYPES) {
      const entry = Constants.COLORS[type];
      assert.ok(entry && typeof entry === 'object', `Missing COLORS.${type}`);
      for (const f of fields) {
        assert.strictEqual(typeof entry[f], 'string', `COLORS.${type}.${f} must be string`);
        assert.ok(entry[f].trim().length > 0, `COLORS.${type}.${f} must be non-empty`);
      }
      assert.strictEqual(entry.fill.toLowerCase(), expectedFills[type]);
    }
  });
});

describe('3. SRS WALL_KICKS (JLSTZ, I, O) & getWallKicks', () => {
  const expectedKeys = ['0>1', '1>0', '1>2', '2>1', '2>3', '3>2', '3>0', '0>3'];

  const expectedJLSTZ = {
    '0>1': [[0, 0], [-1, 0], [-1, -1], [0, 2], [-1, 2]],
    '1>0': [[0, 0], [1, 0], [1, 1], [0, -2], [1, -2]],
    '1>2': [[0, 0], [1, 0], [1, 1], [0, -2], [1, -2]],
    '2>1': [[0, 0], [-1, 0], [-1, -1], [0, 2], [-1, 2]],
    '2>3': [[0, 0], [1, 0], [1, -1], [0, 2], [1, 2]],
    '3>2': [[0, 0], [-1, 0], [-1, 1], [0, -2], [-1, -2]],
    '3>0': [[0, 0], [-1, 0], [-1, 1], [0, -2], [-1, -2]],
    '0>3': [[0, 0], [1, 0], [1, -1], [0, 2], [1, 2]]
  };

  const expectedI = {
    '0>1': [[0, 0], [-2, 0], [1, 0], [-2, 1], [1, -2]],
    '1>0': [[0, 0], [2, 0], [-1, 0], [2, -1], [-1, 2]],
    '1>2': [[0, 0], [-1, 0], [2, 0], [-1, -2], [2, 1]],
    '2>1': [[0, 0], [1, 0], [-2, 0], [1, 2], [-2, -1]],
    '2>3': [[0, 0], [2, 0], [-1, 0], [2, -1], [-1, 2]],
    '3>2': [[0, 0], [-2, 0], [1, 0], [-2, 1], [1, -2]],
    '3>0': [[0, 0], [1, 0], [-2, 0], [1, 2], [-2, -1]],
    '0>3': [[0, 0], [-1, 0], [2, 0], [-1, -2], [2, 1]]
  };

  it('matches exact official screen-space SRS kick tables (+dRow = DOWN)', () => {
    assert.deepStrictEqual(Object.keys(Constants.WALL_KICKS).sort(), ['I', 'JLSTZ', 'O']);
    assert.deepStrictEqual(Object.keys(Constants.WALL_KICKS.JLSTZ).sort(), [...expectedKeys].sort());
    assert.deepStrictEqual(Object.keys(Constants.WALL_KICKS.I).sort(), [...expectedKeys].sort());
    assert.deepStrictEqual(Object.keys(Constants.WALL_KICKS.O).sort(), [...expectedKeys].sort());

    assert.deepStrictEqual(Constants.WALL_KICKS.JLSTZ, expectedJLSTZ);
    assert.deepStrictEqual(Constants.WALL_KICKS.I, expectedI);

    for (const key of expectedKeys) {
      assert.deepStrictEqual(Constants.WALL_KICKS.O[key], [[0, 0]]);
      assert.strictEqual(Constants.WALL_KICKS.JLSTZ[key].length, 5);
      assert.strictEqual(Constants.WALL_KICKS.I[key].length, 5);
      assert.deepStrictEqual(Constants.WALL_KICKS.JLSTZ[key][0], [0, 0]);
      assert.deepStrictEqual(Constants.WALL_KICKS.I[key][0], [0, 0]);
    }
  });

  it('satisfies exact reverse-transition negation symmetry (-0 safe) across all 24 transitions', () => {
    const pairs = [['0', '1'], ['1', '2'], ['2', '3'], ['3', '0']];
    for (const tableName of ['JLSTZ', 'I', 'O']) {
      const table = Constants.WALL_KICKS[tableName];
      for (const [a, b] of pairs) {
        const fwd = table[`${a}>${b}`];
        const rev = table[`${b}>${a}`];
        assert.strictEqual(fwd.length, rev.length);
        for (let i = 0; i < fwd.length; i++) {
          assert.deepStrictEqual(fwd[i], [negZero(rev[i][0]), negZero(rev[i][1])]);
        }
      }
    }
  });

  it('getWallKicks normalizes rotations and safely handles invalid inputs', () => {
    for (const t of ['J', 'L', 'S', 'T', 'Z']) {
      assert.deepStrictEqual(Constants.getWallKicks(t, 0, 1), expectedJLSTZ['0>1']);
    }
    assert.deepStrictEqual(Constants.getWallKicks('I', 0, 1), expectedI['0>1']);
    assert.deepStrictEqual(Constants.getWallKicks('O', 0, 1), [[0, 0]]);

    // Modulo wrapping on negative and >=4 integers
    assert.deepStrictEqual(Constants.getWallKicks('T', -1, 0), expectedJLSTZ['3>0']);
    assert.deepStrictEqual(Constants.getWallKicks('I', 3, 4), expectedI['3>0']);
    assert.deepStrictEqual(Constants.getWallKicks('L', -4, -3), expectedJLSTZ['0>1']);

    // Invalid types, 180-degree turns, floats, NaN, Infinity
    assert.deepStrictEqual(Constants.getWallKicks('T', 0, 2), []);
    assert.deepStrictEqual(Constants.getWallKicks('X', 0, 1), []);
    assert.deepStrictEqual(Constants.getWallKicks(null, 0, 1), []);
    assert.deepStrictEqual(Constants.getWallKicks('T', NaN, 1), []);
    assert.deepStrictEqual(Constants.getWallKicks('T', 1.5, 2), []);
    assert.deepStrictEqual(Constants.getWallKicks('T', Infinity, 1), []);
  });
});

describe('4. Gravity (getGravityMs) & Soft Drop (getSoftDropMs) Curves', () => {
  it('computes exact Guideline gravity intervals and strictly decreases from L1 to L20', () => {
    assert.strictEqual(Constants.getGravityMs(1), 1000);
    assert.strictEqual(Constants.getGravityMs(2), 793);
    assert.ok(Math.abs(Constants.getGravityMs(15) - 7.05861622) < 1e-6);
    assert.ok(Math.abs(Constants.getGravityMs(20) - 0.45539771) < 1e-6);

    for (let lvl = 2; lvl <= 20; lvl++) {
      assert.ok(
        Constants.getGravityMs(lvl) < Constants.getGravityMs(lvl - 1),
        `Level ${lvl} gravity must be strictly faster than level ${lvl - 1}`
      );
    }
  });

  it('clamps out-of-range levels (-5..150 including >115 zero-crossing) and handles invalid inputs cleanly', () => {
    const minG = Constants.getGravityMs(20);
    for (let lvl = -5; lvl <= 150; lvl++) {
      const g = Constants.getGravityMs(lvl);
      assert.ok(Number.isFinite(g) && g > 0, `Level ${lvl} gravity must be finite > 0, got ${g}`);
      if (lvl <= 1) {
        assert.strictEqual(g, 1000);
      } else if (lvl >= 20) {
        assert.strictEqual(g, minG);
      }
    }

    const fallbackLevel1Inputs = [NaN, undefined, null, 0, -5, -Infinity, '', '   ', 'abc', {}, [], true, false, Symbol('x'), 1.9];
    for (const input of fallbackLevel1Inputs) {
      assert.strictEqual(Constants.getGravityMs(input), 1000);
    }

    assert.strictEqual(Constants.getGravityMs('10'), Constants.getGravityMs(10));
    assert.strictEqual(Constants.getGravityMs(Infinity), minG);
    assert.strictEqual(Constants.getGravityMs('Infinity'), minG);
  });

  it('getSoftDropMs never exceeds SOFT_DROP_REPEAT_MS or native gravity across valid and edge inputs', () => {
    for (let lvl = -5; lvl <= 150; lvl++) {
      const g = Constants.getGravityMs(lvl);
      const sd = Constants.getSoftDropMs(lvl);
      assert.ok(Number.isFinite(sd) && sd > 0);
      assert.ok(sd <= Constants.SOFT_DROP_REPEAT_MS);
      assert.ok(sd <= g);
      if (lvl >= 1 && lvl <= 11) {
        assert.strictEqual(sd, 40);
      } else if (lvl >= 12) {
        assert.strictEqual(sd, g);
      }
    }

    for (const bad of [NaN, undefined, 'abc', {}, Symbol('y'), Infinity]) {
      const sd = Constants.getSoftDropMs(bad);
      assert.ok(Number.isFinite(sd) && sd > 0);
      assert.ok(sd <= Constants.SOFT_DROP_REPEAT_MS);
      assert.ok(sd <= Constants.getGravityMs(bad));
    }
  });
});

describe('5. Timing, Scoring, Storage & Cache Invariants', () => {
  it('exposes exact gameplay, input, scoring, storage, and cache constants', () => {
    assert.strictEqual(Constants.LOCK_DELAY_MS, 500);
    assert.strictEqual(Constants.MAX_LOCK_RESETS, 15);
    assert.strictEqual(Constants.LINES_PER_LEVEL, 10);
    assert.strictEqual(Constants.MIN_START_LEVEL, 1);
    assert.strictEqual(Constants.MAX_START_LEVEL, 15);
    assert.strictEqual(Constants.MAX_GRAVITY_LEVEL, 20);
    assert.strictEqual(Constants.DAS_MS, 160);
    assert.strictEqual(Constants.ARR_MS, 35);
    assert.strictEqual(Constants.SOFT_DROP_REPEAT_MS, 40);
    assert.strictEqual(Constants.GAMEPAD_DEADZONE_X, 0.30);
    assert.strictEqual(Constants.GAMEPAD_SOFT_DROP_Y, 0.45);
    assert.strictEqual(Constants.TOUCH_SENSITIVITY_MIN, 1);
    assert.strictEqual(Constants.TOUCH_SENSITIVITY_MAX, 10);
    assert.strictEqual(Constants.TOUCH_SENSITIVITY_DEFAULT, 5);
    assert.strictEqual(Constants.NEXT_PREVIEW_COUNT, 3);

    assert.deepStrictEqual(Constants.LINE_SCORES, { 1: 100, 2: 300, 3: 500, 4: 800 });
    assert.strictEqual(Constants.B2B_MULTIPLIER, 1.5);
    assert.strictEqual(Constants.COMBO_BASE, 50);
    assert.strictEqual(Constants.SOFT_DROP_POINTS, 1);
    assert.strictEqual(Constants.HARD_DROP_POINTS, 2);

    assert.strictEqual(Constants.STORAGE_KEY, 'tetris_clasico_v1');
    assert.strictEqual(Constants.CACHE_NAME, 'tetris-clasico-v1');
    assert.deepStrictEqual(Constants.DEFAULT_STATE, {
      bestScore: 0,
      bestLevel: 0,
      bestLines: 0,
      touchSensitivity: 5,
      musicEnabled: true,
      sfxEnabled: true,
      startLevel: 1
    });

    assert.ok(
      Constants.DEFAULT_STATE.touchSensitivity >= Constants.TOUCH_SENSITIVITY_MIN &&
      Constants.DEFAULT_STATE.touchSensitivity <= Constants.TOUCH_SENSITIVITY_MAX
    );
    assert.ok(
      Constants.DEFAULT_STATE.startLevel >= Constants.MIN_START_LEVEL &&
      Constants.DEFAULT_STATE.startLevel <= Constants.MAX_START_LEVEL
    );
  });
});

describe('6. manifest.webmanifest Validation', () => {
  it('parses as valid Spanish standalone PWA manifest with relative URLs and separated icon purposes', () => {
    const raw = fs.readFileSync(path.join(ROOT_DIR, 'manifest.webmanifest'), 'utf8');
    assert.ok(!raw.startsWith('\uFEFF'), 'manifest must not start with UTF-8 BOM');
    const manifest = JSON.parse(raw);

    // Omit "id" so W3C Web App Manifest defaults app ID to resolved start_url (preserving GitHub Pages <repo> subpath).
    assert.equal(Object.prototype.hasOwnProperty.call(manifest, 'id'), false);
    assert.equal(manifest.id, undefined);
    assert.strictEqual(manifest.lang, 'es');
    assert.strictEqual(manifest.dir, 'ltr');
    assert.strictEqual(manifest.name, 'Tetris Clásico');
    assert.strictEqual(manifest.short_name, 'Tetris');
    assert.ok(typeof manifest.description === 'string' && manifest.description.length > 10);
    assert.strictEqual(manifest.start_url, './index.html');
    assert.strictEqual(manifest.scope, './');
    assert.strictEqual(manifest.display, 'standalone');
    assert.strictEqual(manifest.background_color, '#070b14');
    assert.strictEqual(manifest.theme_color, '#0b1120');
    assert.ok(manifest.orientation === undefined || manifest.orientation === 'any');

    const urlFields = [manifest.start_url, manifest.scope, ...manifest.icons.map((i) => i.src)];
    for (const val of urlFields) {
      assert.ok(typeof val === 'string' && val.length > 0, `Manifest URL must be non-empty string: ${val}`);
      assert.ok(!val.startsWith('/'), `Manifest URL must not start with '/': ${val}`);
      assert.ok(!/^https?:\/\//i.test(val) && !val.startsWith('//') && !val.startsWith('..'), `Invalid relative URL: ${val}`);
    }
    const subpathManifestUrl = 'https://example.github.io/tetris-clasico/manifest.webmanifest';
    assert.strictEqual(
      new URL(manifest.start_url, subpathManifestUrl).href,
      'https://example.github.io/tetris-clasico/index.html'
    );
    assert.strictEqual(
      new URL(manifest.scope, subpathManifestUrl).href,
      'https://example.github.io/tetris-clasico/'
    );

    assert.ok(Array.isArray(manifest.icons) && manifest.icons.length >= 4);
    for (const icon of manifest.icons) {
      assert.notStrictEqual(icon.purpose, 'any maskable', 'Do not combine any and maskable in single icon entry');
      const resolved = path.resolve(ROOT_DIR, icon.src);
      assert.ok(fs.existsSync(resolved), `Missing manifest icon on disk: ${icon.src}`);
    }

    assert.ok(manifest.icons.some((i) => i.type === 'image/svg+xml' && i.purpose === 'any'));
    assert.ok(manifest.icons.some((i) => i.sizes === '192x192' && i.purpose === 'any'));
    assert.ok(manifest.icons.some((i) => i.sizes === '512x512' && i.purpose === 'any'));
    assert.ok(manifest.icons.some((i) => i.sizes === '512x512' && i.purpose === 'maskable'));
  });
});

describe('7. service-worker.js Syntax, Static Rules & Behavioral node:vm Sandbox', () => {
  const expectedPrecache = [
    './',
    './index.html',
    './styles.css',
    './manifest.webmanifest',
    './js/constants.js',
    './js/audio.js',
    './js/engine.js',
    './js/renderer.js',
    './js/input.js',
    './js/main.js',
    './icons/icon.svg',
    './icons/icon-192.png',
    './icons/icon-512.png',
    './icons/icon-512-maskable.png',
    './icons/apple-touch-icon.png'
  ];

  const m1ExistingUrls = new Set([
    './',
    './manifest.webmanifest',
    './js/constants.js',
    './icons/icon.svg',
    './icons/icon-192.png',
    './icons/icon-512.png',
    './icons/icon-512-maskable.png',
    './icons/apple-touch-icon.png'
  ]);

  it('parses cleanly and defines matching CACHE_NAME and strictly relative PRECACHE_URLS', () => {
    const swPath = path.join(ROOT_DIR, 'service-worker.js');
    const swCode = fs.readFileSync(swPath, 'utf8');
    new vm.Script(swCode, { filename: 'service-worker.js' });

    const env = createSwSandbox({ existingPaths: m1ExistingUrls });
    assert.strictEqual(env.exported.CACHE_NAME, Constants.CACHE_NAME);
    assert.strictEqual(env.exported.CACHE_PREFIX, 'tetris-clasico-');
    const precacheList = JSON.parse(JSON.stringify(env.exported.PRECACHE_URLS));
    assert.deepStrictEqual(precacheList, expectedPrecache);

    for (const url of precacheList) {
      assert.ok(url.startsWith('./'), `PRECACHE_URLS entry must start with './': ${url}`);
      assert.ok(!url.includes('..') && !/^\.\/\.[^/]/.test(url), `Unsafe precache entry: ${url}`);
    }

    for (const m1Url of m1ExistingUrls) {
      if (m1Url !== './') {
        assert.ok(fs.existsSync(path.resolve(ROOT_DIR, m1Url)), `Missing M1 precache file: ${m1Url}`);
      }
    }
  });

  it('installs cleanly with full precache AND tolerates M1 partial 404s without failing', async () => {
    // Full shell 200 OK
    const fullSet = new Set(expectedPrecache);
    const fullEnv = createSwSandbox({ existingPaths: fullSet });
    const fullPromises = [];
    fullEnv.listeners.install({ waitUntil: (p) => fullPromises.push(p) });
    await Promise.all(fullPromises);

    assert.strictEqual(fullEnv.wasSkipWaitingCalled(), true);
    assert.ok(fullEnv.store.has('tetris-clasico-v1'));
    assert.strictEqual(fullEnv.store.get('tetris-clasico-v1').size, expectedPrecache.length);
    assert.strictEqual(fullEnv.cancelledResponses.length, 0);

    // M1 incremental milestone (M2-M6 files return 404 and MUST have response.body.cancel() called)
    const partialEnv = createSwSandbox({ existingPaths: m1ExistingUrls });
    const partialPromises = [];
    partialEnv.listeners.install({ waitUntil: (p) => partialPromises.push(p) });
    await Promise.all(partialPromises);

    assert.strictEqual(partialEnv.wasSkipWaitingCalled(), true);
    const partialCache = partialEnv.store.get('tetris-clasico-v1');
    assert.strictEqual(partialCache.size, m1ExistingUrls.size);
    assert.ok(partialCache.has('https://example.github.io/tetris/js/constants.js'));
    assert.ok(!partialCache.has('https://example.github.io/tetris/js/engine.js'));

    const missingCount = expectedPrecache.length - m1ExistingUrls.size;
    assert.strictEqual(partialEnv.cancelledResponses.length, missingCount);
    for (const entry of partialEnv.cancelledResponses) {
      assert.strictEqual(entry.status, 404);
      const rel = './' + entry.url.slice('https://example.github.io/tetris/'.length);
      assert.ok(!m1ExistingUrls.has(rel), `Cached URL should not be cancelled: ${rel}`);
    }
  });

  it('install cancels body streams on skipped 404, 500, redirected, and opaque precache responses without hanging', async () => {
    const env = createSwSandbox();
    const responsesByRel = new Map();

    env.setFetchHandler(async (reqUrl) => {
      const rel = './' + reqUrl.slice('https://example.github.io/tetris/'.length);
      let stub;
      if (rel === './') {
        stub = env.makeResponseStub('ok-root', { ok: true, status: 200, type: 'basic', url: reqUrl });
      } else if (rel === './manifest.webmanifest') {
        stub = env.makeResponseStub('server-error', { ok: false, status: 500, type: 'basic', url: reqUrl });
      } else if (rel === './js/constants.js') {
        stub = env.makeResponseStub('redirected', { ok: true, status: 200, type: 'basic', redirected: true, url: reqUrl });
      } else if (rel === './js/audio.js') {
        stub = env.makeResponseStub('opaque', { ok: false, status: 0, type: 'opaque', url: reqUrl });
      } else if (rel === './js/engine.js') {
        stub = env.makeResponseStub('cancel-rejects', { ok: false, status: 404, type: 'basic', url: reqUrl, cancelRejects: true });
      } else if (rel === './js/renderer.js') {
        stub = env.makeResponseStub('no-body', { ok: false, status: 500, type: 'basic', url: reqUrl, hasBody: false });
      } else {
        stub = env.makeResponseStub('not-found', { ok: false, status: 404, type: 'basic', url: reqUrl });
      }
      responsesByRel.set(rel, stub);
      return stub;
    });

    const installPromises = [];
    env.listeners.install({ waitUntil: (p) => installPromises.push(p) });
    await Promise.all(installPromises);

    assert.strictEqual(env.wasSkipWaitingCalled(), true);
    const cache = env.store.get('tetris-clasico-v1');
    assert.strictEqual(cache.size, 1);
    assert.ok(cache.has('https://example.github.io/tetris/'));

    assert.strictEqual(responsesByRel.get('./').body.cancelCount, 0);
    assert.strictEqual(responsesByRel.get('./manifest.webmanifest').body.cancelCount, 1);
    assert.strictEqual(responsesByRel.get('./js/constants.js').body.cancelCount, 1);
    assert.strictEqual(responsesByRel.get('./js/audio.js').body.cancelCount, 1);
    assert.strictEqual(responsesByRel.get('./js/engine.js').body.cancelCount, 1);
    assert.strictEqual(responsesByRel.get('./js/renderer.js').body, null);

    for (const url of expectedPrecache) {
      if (url !== './' && url !== './js/renderer.js') {
        assert.strictEqual(responsesByRel.get(url).body.cancelCount, 1, `Expected cancel() on skipped ${url}`);
      }
    }
    assert.strictEqual(env.cancelledResponses.length, expectedPrecache.length - 2);
  });

  it('activate deletes ONLY stale tetris-clasico-* caches while preserving Diana Sudoku & sibling caches', async () => {
    const env = createSwSandbox({
      initialCaches: {
        'diana-sudoku-v1': { 'https://example.github.io/diana-sudoku/index.html': {} },
        'diana-sudoku-assets-v2': { 'https://example.github.io/diana-sudoku/app.js': {} },
        'other-site-v1': { 'https://example.github.io/other/index.html': {} },
        'tetris-clasico-v0': { 'https://example.github.io/tetris/index.html': {} },
        'tetris-clasico-v1': { 'https://example.github.io/tetris/js/constants.js': {} }
      }
    });

    const waitPromises = [];
    env.listeners.activate({ waitUntil: (p) => waitPromises.push(p) });
    await Promise.all(waitPromises);

    assert.strictEqual(env.wasClientsClaimCalled(), true);
    assert.strictEqual(env.store.has('diana-sudoku-v1'), true);
    assert.strictEqual(env.store.has('diana-sudoku-assets-v2'), true);
    assert.strictEqual(env.store.has('other-site-v1'), true);
    assert.strictEqual(env.store.has('tetris-clasico-v1'), true);
    assert.strictEqual(env.store.has('tetris-clasico-v0'), false);
  });

  it('fetch handler filters non-GET/cross-origin/out-of-scope, serves cache offline, updates online, and falls back for navigation', async () => {
    const env = createSwSandbox({ existingPaths: new Set(expectedPrecache) });
    const installPromises = [];
    env.listeners.install({ waitUntil: (p) => installPromises.push(p) });
    await Promise.all(installPromises);

    // 1. Non-GET ignored
    let respondCalled = false;
    env.listeners.fetch({
      request: { method: 'POST', url: 'https://example.github.io/tetris/api', cache: 'default', mode: 'cors' },
      respondWith: () => { respondCalled = true; }
    });
    assert.strictEqual(respondCalled, false);

    // 2. Cross-origin ignored
    respondCalled = false;
    env.listeners.fetch({
      request: { method: 'GET', url: 'https://other.example/evil.js', cache: 'default', mode: 'cors' },
      respondWith: () => { respondCalled = true; }
    });
    assert.strictEqual(respondCalled, false);

    // 3. Same-origin out-of-scope (e.g. Diana Sudoku sibling path) ignored
    respondCalled = false;
    env.listeners.fetch({
      request: { method: 'GET', url: 'https://example.github.io/diana-sudoku/index.html', cache: 'default', mode: 'same-origin' },
      respondWith: () => { respondCalled = true; }
    });
    assert.strictEqual(respondCalled, false);

    // 4. Same-origin cached GET served offline
    env.setOnline(false);
    let offlineRespPromise = null;
    env.listeners.fetch({
      request: { method: 'GET', url: 'https://example.github.io/tetris/js/constants.js', cache: 'default', mode: 'same-origin' },
      respondWith: (p) => { offlineRespPromise = p; }
    });
    assert.ok(offlineRespPromise);
    const offlineResp = await offlineRespPromise;
    assert.strictEqual(await offlineResp.text(), 'body:./js/constants.js');

    // 5. Offline navigation fallback with query param -> ./index.html
    let navFallbackPromise = null;
    env.listeners.fetch({
      request: { method: 'GET', url: 'https://example.github.io/tetris/index.html?source=pwa', cache: 'default', mode: 'navigate' },
      respondWith: (p) => { navFallbackPromise = p; }
    });
    const navResp = await navFallbackPromise;
    assert.strictEqual(await navResp.text(), 'body:./index.html');

    // 6. Online cache miss caches basic 200 response opportunistically
    env.setOnline(true);
    env.setFetchHandler(async () => env.makeResponseStub('dynamic-ok', { ok: true, status: 200, type: 'basic' }));
    let missPromise = null;
    env.listeners.fetch({
      request: { method: 'GET', url: 'https://example.github.io/tetris/extra.json', cache: 'default', mode: 'same-origin' },
      respondWith: (p) => { missPromise = p; }
    });
    const missResp = await missPromise;
    assert.strictEqual(await missResp.text(), 'dynamic-ok');
    assert.ok(env.store.get('tetris-clasico-v1').has('https://example.github.io/tetris/extra.json'));

    // 7. Partial/redirected responses are NOT cached
    env.setFetchHandler(async () => env.makeResponseStub('partial', { ok: true, status: 206, type: 'basic' }));
    let partialPromise = null;
    env.listeners.fetch({
      request: { method: 'GET', url: 'https://example.github.io/tetris/partial.bin', cache: 'default', mode: 'same-origin' },
      respondWith: (p) => { partialPromise = p; }
    });
    const partialResp = await partialPromise;
    assert.strictEqual(partialResp.status, 206);
    assert.ok(!env.store.get('tetris-clasico-v1').has('https://example.github.io/tetris/partial.bin'));
  });

  it('scopes all caches.match lookups to tetris-clasico-v1 and never serves stale entries from diana-sudoku-v1', async () => {
    const staleIndex = { ok: true, status: 200, async text() { return 'STALE DIANA INDEX'; } };
    const staleConstants = { ok: true, status: 200, async text() { return 'STALE DIANA CONSTANTS'; } };
    const staleRoot = { ok: true, status: 200, async text() { return 'STALE DIANA ROOT'; } };

    // 1. Verify sandbox faithfully models W3C CacheStorage.match (global scan when options.cacheName omitted)
    const env = createSwSandbox({
      initialCaches: {
        'diana-sudoku-v1': {
          'https://example.github.io/tetris/index.html': staleIndex,
          'https://example.github.io/tetris/js/constants.js': staleConstants,
          'https://example.github.io/tetris/': staleRoot
        }
      }
    });

    assert.strictEqual(
      await env.caches.match('https://example.github.io/tetris/index.html'),
      staleIndex
    );
    assert.strictEqual(
      await env.caches.match('https://example.github.io/tetris/index.html', { cacheName: 'tetris-clasico-v1' }),
      undefined
    );
    env.cacheMatchCalls.length = 0;

    // 2. Online request when tetris-clasico-v1 lacks js/constants.js: MUST fetch network, NEVER serve diana-sudoku-v1
    env.setFetchHandler(async () => env.makeResponseStub('FRESH TETRIS CONSTANTS', { ok: true, status: 200, type: 'basic' }));
    let constantsPromise = null;
    env.listeners.fetch({
      request: { method: 'GET', url: 'https://example.github.io/tetris/js/constants.js', cache: 'default', mode: 'same-origin' },
      respondWith: (p) => { constantsPromise = p; }
    });
    const constantsResp = await constantsPromise;
    assert.strictEqual(await constantsResp.text(), 'FRESH TETRIS CONSTANTS');
    assert.strictEqual(await env.store.get('diana-sudoku-v1').get('https://example.github.io/tetris/js/constants.js').text(), 'STALE DIANA CONSTANTS');

    // 3. Offline non-navigate miss when only diana-sudoku-v1 has the URL: MUST return Response.error()
    env.setOnline(false);
    let offlineMissPromise = null;
    env.listeners.fetch({
      request: { method: 'GET', url: 'https://example.github.io/tetris/index.html', cache: 'default', mode: 'same-origin' },
      respondWith: (p) => { offlineMissPromise = p; }
    });
    const offlineMissResp = await offlineMissPromise;
    assert.strictEqual(offlineMissResp.type, 'error');
    assert.strictEqual(offlineMissResp.status, 0);

    // 4. Offline navigate fallback when tetris-clasico-v1 has neither ./index.html nor ./: MUST NOT fall back to diana-sudoku-v1
    let offlineNavEmptyPromise = null;
    env.listeners.fetch({
      request: { method: 'GET', url: 'https://example.github.io/tetris/deep/route', cache: 'default', mode: 'navigate' },
      respondWith: (p) => { offlineNavEmptyPromise = p; }
    });
    const offlineNavEmptyResp = await offlineNavEmptyPromise;
    assert.strictEqual(offlineNavEmptyResp.type, 'error');
    assert.strictEqual(offlineNavEmptyResp.status, 0);

    // 5. Offline navigate fallback when tetris-clasico-v1 has ./ (M1 partial install) but lacks ./index.html
    const tetrisCache = await env.caches.open('tetris-clasico-v1');
    await tetrisCache.put('./', env.makeResponseStub('FRESH TETRIS ROOT', { ok: true, status: 200, type: 'basic' }));
    let offlineNavRootPromise = null;
    env.listeners.fetch({
      request: { method: 'GET', url: 'https://example.github.io/tetris/deep/route', cache: 'default', mode: 'navigate' },
      respondWith: (p) => { offlineNavRootPromise = p; }
    });
    const offlineNavRootResp = await offlineNavRootPromise;
    assert.strictEqual(await offlineNavRootResp.text(), 'FRESH TETRIS ROOT');

    // 6. Offline navigate fallback when BOTH caches have ./index.html (diana-sudoku-v1 inserted first)
    await tetrisCache.put('./index.html', env.makeResponseStub('FRESH TETRIS INDEX', { ok: true, status: 200, type: 'basic' }));
    let offlineNavIndexPromise = null;
    env.listeners.fetch({
      request: { method: 'GET', url: 'https://example.github.io/tetris/deep/route', cache: 'default', mode: 'navigate' },
      respondWith: (p) => { offlineNavIndexPromise = p; }
    });
    const offlineNavIndexResp = await offlineNavIndexPromise;
    assert.strictEqual(await offlineNavIndexResp.text(), 'FRESH TETRIS INDEX');

    assert.ok(env.cacheMatchCalls.length >= 6);
    for (const call of env.cacheMatchCalls) {
      assert.strictEqual(call.cacheName, 'tetris-clasico-v1', `Expected cacheName=tetris-clasico-v1 for ${call.key}`);
    }
  });
});

describe('8. Icons (icons/*) & Repo Setup (.nojekyll, .gitignore)', () => {
  it('validates icons/icon.svg structure, dark-neon palette, and absence of scripts', () => {
    const svgPath = path.join(ROOT_DIR, 'icons/icon.svg');
    assert.ok(fs.existsSync(svgPath));
    const svg = fs.readFileSync(svgPath, 'utf8');
    assert.ok(svg.length > 200);
    assert.ok(svg.includes('<svg'));
    assert.ok(svg.includes('xmlns="http://www.w3.org/2000/svg"'));
    assert.ok(svg.includes('viewBox="0 0 512 512"'));
    assert.ok(svg.includes('</svg>'));
    assert.ok(!/<script\b/i.test(svg), 'SVG must not contain <script> tags');
    assert.ok(svg.includes('#070b14') && svg.includes('#0b1120'));
    for (const hex of ['#c084fc', '#22d3ee', '#facc15', '#fb923c']) {
      assert.ok(svg.toLowerCase().includes(hex), `SVG missing accent color ${hex}`);
    }
  });

  it('validates icon-192.png and icon-512.png dimensions, RGBA mode, transparent corners, and neon center', () => {
    for (const [name, expectedSize] of [['icon-192.png', 192], ['icon-512.png', 512]]) {
      const png = parsePng(path.join(ROOT_DIR, 'icons', name));
      assert.strictEqual(png.width, expectedSize);
      assert.strictEqual(png.height, expectedSize);
      assert.strictEqual(png.colorType, 6);

      assert.strictEqual(png.getPixel(0, 0).a, 0);
      assert.strictEqual(png.getPixel(expectedSize - 1, 0).a, 0);
      assert.strictEqual(png.getPixel(0, expectedSize - 1).a, 0);
      assert.strictEqual(png.getPixel(expectedSize - 1, expectedSize - 1).a, 0);

      let brightOpaqueCount = 0;
      const start = Math.floor(expectedSize * 0.25);
      const end = Math.floor(expectedSize * 0.75);
      for (let y = start; y < end; y++) {
        for (let x = start; x < end; x++) {
          const p = png.getPixel(x, y);
          if (p.a === 255 && Math.max(p.r, p.g, p.b) >= 200) {
            brightOpaqueCount++;
          }
        }
      }
      assert.ok(brightOpaqueCount > 50, `${name} must contain crisp opaque neon pixels in center`);
    }
  });

  it('validates icon-512-maskable.png is 512x512 100% opaque with emblem strictly inside 80% safe circle', () => {
    const png = parsePng(path.join(ROOT_DIR, 'icons/icon-512-maskable.png'));
    assert.strictEqual(png.width, 512);
    assert.strictEqual(png.height, 512);

    const corners = [
      png.getPixel(0, 0),
      png.getPixel(511, 0),
      png.getPixel(0, 511),
      png.getPixel(511, 511),
      png.getPixel(256, 0),
      png.getPixel(0, 256)
    ];
    for (const c of corners) {
      assert.strictEqual(c.a, 255);
      assert.ok(Math.max(c.r, c.g, c.b) < 60, 'Maskable outer edge must be dark #070b14');
    }

    let brightInsideSafeZone = 0;
    for (let y = 0; y < 512; y++) {
      for (let x = 0; x < 512; x++) {
        const p = png.getPixel(x, y);
        assert.strictEqual(p.a, 255, `Pixel (${x},${y}) in maskable icon must have alpha=255`);
        const maxRgb = Math.max(p.r, p.g, p.b);
        const dist = Math.hypot(x + 0.5 - 256, y + 0.5 - 256);
        if (x < 51 || x >= 461 || y < 51 || y >= 461 || dist > 204.8) {
          assert.ok(maxRgb < 75, `Neon artwork leaked outside 80% safe zone at (${x},${y}): rgb(${p.r},${p.g},${p.b})`);
        } else if (maxRgb >= 200) {
          brightInsideSafeZone++;
        }
      }
    }
    assert.ok(brightInsideSafeZone > 500, 'Maskable icon must contain vivid neon artwork inside safe zone');
  });

  it('validates apple-touch-icon.png is 180x180 100% opaque with dark corners and neon artwork', () => {
    const png = parsePng(path.join(ROOT_DIR, 'icons/apple-touch-icon.png'));
    assert.strictEqual(png.width, 180);
    assert.strictEqual(png.height, 180);

    for (const [cx, cy] of [[0, 0], [179, 0], [0, 179], [179, 179]]) {
      const p = png.getPixel(cx, cy);
      assert.strictEqual(p.a, 255);
      assert.ok(Math.max(p.r, p.g, p.b) < 60);
    }

    let brightCenter = 0;
    for (let y = 0; y < 180; y++) {
      for (let x = 0; x < 180; x++) {
        const p = png.getPixel(x, y);
        assert.strictEqual(p.a, 255, `Pixel (${x},${y}) in apple-touch-icon must be 100% opaque`);
        if (x >= 35 && x < 145 && y >= 25 && y < 155 && Math.max(p.r, p.g, p.b) >= 200) {
          brightCenter++;
        }
      }
    }
    assert.ok(brightCenter > 200, 'apple-touch-icon must contain vivid neon artwork in center');
  });

  it('validates .nojekyll (0 bytes) and .gitignore hygiene rules', () => {
    const nojekyllPath = path.join(ROOT_DIR, '.nojekyll');
    assert.ok(fs.existsSync(nojekyllPath));
    assert.strictEqual(fs.statSync(nojekyllPath).size, 0);

    const gitignorePath = path.join(ROOT_DIR, '.gitignore');
    assert.ok(fs.existsSync(gitignorePath));
    const lines = fs
      .readFileSync(gitignorePath, 'utf8')
      .split(/\r?\n/)
      .map((l) => l.trim())
      .filter((l) => l.length > 0 && !l.startsWith('#'));

    const requiredEntries = [
      '.agents/',
      '.gemini/',
      '.cache/',
      '.config/',
      '.local/',
      '.npm/',
      '.android/',
      '.gradle/',
      'Downloads/',
      'node_modules/',
      '__pycache__/',
      '.bash*',
      '.profile'
    ];
    for (const req of requiredEntries) {
      assert.ok(lines.includes(req), `.gitignore missing required entry: ${req}`);
    }

    const forbiddenEntries = ['.*', '*.png', '*.svg', '*.js', 'icons/', 'js/', 'tests/', '.nojekyll', '.gitignore'];
    for (const bad of forbiddenEntries) {
      assert.ok(!lines.includes(bad), `.gitignore must not contain overly broad entry: ${bad}`);
    }
  });
});

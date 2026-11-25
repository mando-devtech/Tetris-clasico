'use strict';

const { describe, it } = require('node:test');
const assert = require('node:assert/strict');
const Main = require('../../js/main.js');

describe('Tetris.Main Storage Persistence', () => {
  it('recovers cleanly from corrupt JSON and clamps out-of-range fields', () => {
    const mockStorage = {
      data: { [Main.STORAGE_KEY]: '{broken json' },
      getItem(k) { return this.data[k] || null; },
      setItem(k, v) { this.data[k] = v; }
    };

    const recovered = Main.loadState(mockStorage);
    assert.deepEqual(recovered, Main.DEFAULT_STATE);

    const saved = Main.saveState({
      bestScore: 1200,
      touchSensitivity: 99,
      startLevel: -5,
      musicEnabled: false
    }, mockStorage);

    assert.equal(saved.bestScore, 1200);
    assert.equal(saved.touchSensitivity, 10);
    assert.equal(saved.startLevel, 1);
    assert.equal(saved.musicEnabled, false);
    assert.equal(saved.sfxEnabled, true);
  });

  it('falls back to in-memory state when localStorage throws', () => {
    const throwingStorage = {
      getItem() { throw new Error('SecurityError'); },
      setItem() { throw new Error('QuotaExceededError'); }
    };

    const s1 = Main.saveState({ bestScore: 4500, touchSensitivity: 8 }, throwingStorage);
    assert.equal(s1.bestScore, 4500);
    assert.equal(s1.touchSensitivity, 8);

    const s2 = Main.loadState(throwingStorage);
    assert.equal(s2.bestScore, 4500);
    assert.equal(s2.touchSensitivity, 8);
  });
});

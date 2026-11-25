'use strict';

const { describe, it } = require('node:test');
const assert = require('node:assert/strict');
const Input = require('../../js/input.js');

describe('Tetris.Input', () => {
  it('computes monotonically decreasing pxPerCell/thresholds as touch sensitivity increases 1..10', () => {
    const low = Input.computeTouchThresholds(1, 32);
    const mid = Input.computeTouchThresholds(5, 32);
    const high = Input.computeTouchThresholds(10, 32);

    assert.equal(low.sensitivity, 1);
    assert.equal(mid.sensitivity, 5);
    assert.equal(high.sensitivity, 10);

    assert.ok(low.pxPerCell > mid.pxPerCell);
    assert.ok(mid.pxPerCell > high.pxPerCell);
    assert.ok(low.flickMinDistPx > mid.flickMinDistPx);
    assert.ok(mid.flickMinDistPx > high.flickMinDistPx);
    assert.ok(low.flickMinVelPxPerMs > high.flickMinVelPxPerMs);
    assert.equal(mid.tapMaxDistPx, 12);
    assert.equal(mid.tapMaxDurationMs, 260);
  });

  it('applies analog stick deadzone cleanly', () => {
    assert.equal(Input.applyDeadzone(0.15, 0.30), 0);
    assert.equal(Input.applyDeadzone(-0.29, 0.30), 0);
    assert.equal(Input.applyDeadzone(0.30, 0.30), 0.30);
    assert.equal(Input.applyDeadzone(-0.85, 0.30), -0.85);
    assert.equal(Input.applyDeadzone(NaN, 0.30), 0);
  });

  it('handles DAS/ARR timing and SOCD last-input priority', () => {
    const das = Input.createDasArrState(160, 35);
    das.press(-1);
    // Initial step immediately
    let res = das.update(16);
    assert.equal(res.dir, -1);
    assert.equal(res.steps, 1);

    // Within DAS window -> 0 steps
    res = das.update(100);
    assert.equal(res.steps, 0);

    // Cross DAS (116 + 50 = 166 >= 160) -> 1 ARR step
    res = das.update(50);
    assert.equal(res.steps, 1);

    // SOCD: press right while left still held -> switches immediately to +1
    das.press(1);
    res = das.update(16);
    assert.equal(res.dir, 1);
    assert.equal(res.steps, 1);

    // Release right -> falls back to left
    das.release(1);
    res = das.update(16);
    assert.equal(res.dir, -1);
    assert.equal(res.steps, 1);

    das.reset();
    assert.equal(das.update(16).steps, 0);
  });
});

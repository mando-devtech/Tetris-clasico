'use strict';

const { describe, it } = require('node:test');
const assert = require('node:assert/strict');
const Constants = require('../../js/constants.js');
const Engine = require('../../js/engine.js');

function makeLcg(seed) {
  let state = seed >>> 0;
  return function () {
    state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
    return state / 4294967296;
  };
}

describe('Tetris.Engine', () => {
  it('initializes in menu state and starts clean Marathon at requested level', () => {
    const engine = Engine.createEngine({ rng: makeLcg(42) });
    assert.equal(engine.getSnapshot().status, 'menu');

    const res = engine.start(7);
    assert.ok(Array.isArray(res.events));
    const snap = engine.getSnapshot();
    assert.equal(snap.status, 'playing');
    assert.equal(snap.level, 7);
    assert.equal(snap.startLevel, 7);
    assert.equal(snap.score, 0);
    assert.equal(snap.lines, 0);
    assert.equal(snap.nextQueue.length, 3);
    assert.equal(snap.holdPiece, null);
    assert.equal(snap.canHold, true);
    assert.ok(snap.activePiece !== null);
    assert.equal(snap.board.length, Constants.TOTAL_ROWS);
    assert.equal(snap.board[0].length, Constants.COLS);
  });

  it('produces valid 7-bag permutations without duplicates per bag', () => {
    const engine = Engine.createEngine({ rng: makeLcg(123) });
    engine.start(1);
    const seen = [];
    for (let i = 0; i < 14; i++) {
      assert.equal(engine.getSnapshot().status, 'playing');
      seen.push(engine.getSnapshot().activePiece.type);
      const colShift = (i % 3) - 1;
      if (colShift < 0) {
        engine.moveLeft();
        engine.moveLeft();
        engine.moveLeft();
      } else if (colShift > 0) {
        engine.moveRight();
        engine.moveRight();
        engine.moveRight();
      }
      engine.hardDrop();
    }
    const bag1 = seen.slice(0, 7).sort();
    const bag2 = seen.slice(7, 14).sort();
    const expected = Constants.PIECE_TYPES.slice().sort();
    assert.deepEqual(bag1, expected);
    assert.deepEqual(bag2, expected);
  });

  it('handles Hold swap once per turn and resets rotation & spawn position', () => {
    const engine = Engine.createEngine({ rng: makeLcg(7) });
    engine.start(1);
    const first = engine.getSnapshot().activePiece.type;
    const second = engine.getSnapshot().nextQueue[0];

    const h1 = engine.hold();
    assert.equal(h1.changed, true);
    assert.equal(engine.getSnapshot().holdPiece, first);
    assert.equal(engine.getSnapshot().activePiece.type, second);
    assert.equal(engine.getSnapshot().canHold, false);

    // Second hold on same turn is rejected
    const h2 = engine.hold();
    assert.equal(h2.changed, false);

    // After hardDrop, canHold resets
    engine.hardDrop();
    assert.equal(engine.getSnapshot().canHold, true);
    const h3 = engine.hold();
    assert.equal(h3.changed, true);
    assert.equal(engine.getSnapshot().activePiece.type, first);
  });

  it('performs SRS wall-kicks near left/right walls and treats O as invariant', () => {
    // Use fixed rng where first piece is T or I or O
    const engine = Engine.createEngine({ rng: makeLcg(1) });
    engine.start(1);

    // Move all the way left and test rotation doesn't crash and stays in bounds
    for (let i = 0; i < 10; i++) engine.moveLeft();
    const before = engine.getSnapshot().activePiece;
    const rotRes = engine.rotateCW();
    const after = engine.getSnapshot().activePiece;
    if (before.type === 'O') {
      assert.equal(rotRes.changed, false);
    } else {
      assert.equal(rotRes.changed, true);
      assert.ok(after.col >= 0);
    }
  });

  it('enforces Extended Placement lock delay (500ms) and 15-reset cap', () => {
    const engine = Engine.createEngine({ rng: makeLcg(99) });
    engine.start(1);

    // Drop to floor using softDropStep until grounded
    for (let i = 0; i < 25; i++) {
      engine.softDropStep();
    }
    assert.equal(engine.getSnapshot().isGrounded, true);

    // Advance 400ms (not locked yet)
    engine.step(400);
    assert.equal(engine.getSnapshot().isGrounded, true);
    assert.equal(engine.getSnapshot().lockTimerMs, 400);

    // Move resets lock timer up to 15 times
    for (let m = 0; m < 15; m++) {
      const res = (m % 2 === 0) ? engine.moveLeft() : engine.moveRight();
      assert.equal(res.changed, true);
      assert.equal(engine.getSnapshot().lockTimerMs, 0);
    }
    assert.equal(engine.getSnapshot().lockMovesRemaining, 0);

    // Advance 450ms, move 16th time -> does NOT reset lockTimerMs
    engine.step(450);
    const res16 = engine.moveLeft();
    assert.equal(res16.changed, true);
    assert.equal(engine.getSnapshot().lockTimerMs, 450);

    // Advance 60ms -> locks!
    const lockStep = engine.step(60);
    assert.ok(lockStep.events.some(e => e.type === 'lock'));
  });

  it('handles >1G multi-row gravity in a single step', () => {
    const engine = Engine.createEngine({ rng: makeLcg(5) });
    engine.start(15); // Level 15 gravity is very fast (~9.6ms/row)
    const startRow = engine.getSnapshot().activePiece.row;
    engine.step(50);
    const afterSnap = engine.getSnapshot();
    assert.ok(afterSnap.activePiece.row > startRow + 1 || afterSnap.isGrounded);
  });

  it('pauses, resumes, and resets cleanly', () => {
    const engine = Engine.createEngine({ rng: makeLcg(11) });
    engine.start(3);
    assert.equal(engine.togglePause(), 'paused');
    assert.equal(engine.moveLeft().changed, false);
    assert.equal(engine.togglePause(), 'playing');
    assert.equal(engine.moveLeft().changed, true);
    engine.reset();
    assert.equal(engine.getSnapshot().status, 'menu');
    assert.equal(engine.getSnapshot().score, 0);
  });
});

'use strict';

const { describe, it } = require('node:test');
const assert = require('node:assert/strict');
const Renderer = require('../../js/renderer.js');

function makeMockCanvas() {
  const noop = () => {};
  const ctx = {
    save: noop,
    restore: noop,
    setTransform: noop,
    fillRect: noop,
    strokeRect: noop,
    clearRect: noop,
    beginPath: noop,
    moveTo: noop,
    lineTo: noop,
    stroke: noop,
    fillText: noop,
    fillStyle: '',
    strokeStyle: '',
    lineWidth: 1,
    globalAlpha: 1,
    font: '',
    textAlign: ''
  };
  return {
    style: {},
    width: 0,
    height: 0,
    getContext: () => ctx,
    getBoundingClientRect: () => ({ left: 0, top: 0, width: 280, height: 560 })
  };
}

describe('Tetris.Renderer', () => {
  it('resizes integer cell dimensions, renders snapshot and triggers effects without errors', () => {
    const boardCanvas = makeMockCanvas();
    const holdCanvas = makeMockCanvas();
    const nextCanvas = makeMockCanvas();
    const boardStage = { clientWidth: 320, clientHeight: 620 };

    const renderer = Renderer.createRenderer({ boardCanvas, holdCanvas, nextCanvas, boardStage });
    renderer.resize();

    const metrics = renderer.getBoardMetrics();
    assert.ok(metrics.cellSize >= 12);
    assert.equal(metrics.width, metrics.cellSize * 10);
    assert.equal(metrics.height, metrics.cellSize * 20);

    renderer.triggerEffects([
      { type: 'hardDrop', piece: 'I', col: 3, width: 4, startY: 2, endY: 18, cells: 16 },
      { type: 'lineClear', count: 4, rows: [20, 21, 22, 23], isTetris: true, isBackToBack: true, combo: 1 },
      { type: 'levelUp', level: 2 }
    ]);

    const board = Array.from({ length: 24 }, () => Array(10).fill(null));
    board[23][0] = 'T';
    renderer.render({
      status: 'playing',
      board,
      activePiece: {
        type: 'T',
        rot: 0,
        col: 3,
        row: 4,
        matrix: [[0, 1, 0], [1, 1, 1], [0, 0, 0]]
      },
      ghostY: 20,
      holdPiece: 'I',
      canHold: true,
      nextQueue: ['O', 'S', 'Z'],
      isGrounded: false,
      lockTimerMs: 0,
      lockDelayMs: 500
    }, 16);

    renderer.resetEffects();
    renderer.dispose();
  });
});

(function (root) {
  'use strict';

  var Constants = (root.Tetris && root.Tetris.Constants) ||
    (typeof require === 'function' ? require('./constants.js') : null);

  var DAS_MS = Constants ? Constants.DAS_MS : 160;
  var ARR_MS = Constants ? Constants.ARR_MS : 35;
  var GAMEPAD_DEADZONE_X = Constants ? Constants.GAMEPAD_DEADZONE_X : 0.30;
  var GAMEPAD_SOFT_DROP_Y = Constants ? Constants.GAMEPAD_SOFT_DROP_Y : 0.45;
  var SENS_MIN = Constants ? Constants.TOUCH_SENSITIVITY_MIN : 1;
  var SENS_MAX = Constants ? Constants.TOUCH_SENSITIVITY_MAX : 10;
  var SENS_DEFAULT = Constants ? Constants.TOUCH_SENSITIVITY_DEFAULT : 5;

  function clampSensitivity(value) {
    var n = Math.round(Number(value));
    if (!isFinite(n)) {
      return SENS_DEFAULT;
    }
    if (n < SENS_MIN) return SENS_MIN;
    if (n > SENS_MAX) return SENS_MAX;
    return n;
  }

  function computeTouchThresholds(sensitivity, cellSizePx) {
    var s = clampSensitivity(sensitivity !== undefined ? sensitivity : SENS_DEFAULT);
    var cell = (typeof cellSizePx === 'number' && isFinite(cellSizePx) && cellSizePx > 0) ? cellSizePx : 32;

    // Higher sensitivity => smaller factor => fewer px needed per cell/flick
    var factor = 1.5 - (s - 1) * (0.9 / 9);
    var pxPerCell = Math.max(12, Math.round(cell * factor));
    var softDropStepPx = Math.max(10, Math.round(cell * 0.65 * factor));
    var flickMinDistPx = Math.max(30, Math.round(44 * factor));
    var flickMinVelPxPerMs = Number((0.42 - (s - 1) * (0.14 / 9)).toFixed(3));
    var holdSwipeMinPx = Math.max(30, Math.round(40 * factor));

    return {
      sensitivity: s,
      pxPerCell: pxPerCell,
      softDropStepPx: softDropStepPx,
      flickMinDistPx: flickMinDistPx,
      flickMinVelPxPerMs: flickMinVelPxPerMs,
      flickWindowMs: 260,
      holdSwipeMinPx: holdSwipeMinPx,
      holdWindowMs: 260,
      tapMaxDistPx: 12,
      tapMaxDurationMs: 260
    };
  }

  function applyDeadzone(value, deadzone) {
    var dz = typeof deadzone === 'number' && isFinite(deadzone) ? deadzone : GAMEPAD_DEADZONE_X;
    if (typeof value !== 'number' || !isFinite(value)) {
      return 0;
    }
    return Math.abs(value) < dz ? 0 : value;
  }

  function createDasArrState(dasMs, arrMs) {
    var das = typeof dasMs === 'number' && isFinite(dasMs) ? dasMs : DAS_MS;
    var arr = typeof arrMs === 'number' && isFinite(arrMs) && arrMs > 0 ? arrMs : ARR_MS;

    var leftHeld = false;
    var rightHeld = false;
    var activeDir = 0; // -1, 0, 1
    var pendingInitial = false;
    var dasElapsed = 0;
    var arrElapsed = 0;
    var repeating = false;

    function setActiveDir(dir) {
      if (dir === activeDir) {
        return;
      }
      activeDir = dir;
      dasElapsed = 0;
      arrElapsed = 0;
      repeating = false;
      pendingInitial = dir !== 0;
    }

    function press(dir) {
      if (dir === -1) {
        if (leftHeld && activeDir === -1) return;
        leftHeld = true;
        setActiveDir(-1);
      } else if (dir === 1) {
        if (rightHeld && activeDir === 1) return;
        rightHeld = true;
        setActiveDir(1);
      }
    }

    function release(dir) {
      if (dir === -1) {
        leftHeld = false;
        if (activeDir === -1) {
          setActiveDir(rightHeld ? 1 : 0);
        }
      } else if (dir === 1) {
        rightHeld = false;
        if (activeDir === 1) {
          setActiveDir(leftHeld ? -1 : 0);
        }
      }
    }

    function reset() {
      leftHeld = false;
      rightHeld = false;
      activeDir = 0;
      pendingInitial = false;
      dasElapsed = 0;
      arrElapsed = 0;
      repeating = false;
    }

    function update(dtMs) {
      if (activeDir === 0) {
        return { steps: 0, dir: 0 };
      }
      var steps = 0;
      if (pendingInitial) {
        steps += 1;
        pendingInitial = false;
      }
      var dt = typeof dtMs === 'number' && isFinite(dtMs) && dtMs > 0 ? dtMs : 0;
      if (!repeating) {
        dasElapsed += dt;
        if (dasElapsed >= das) {
          repeating = true;
          var leftover = dasElapsed - das;
          steps += 1;
          arrElapsed = leftover;
          while (arrElapsed >= arr) {
            arrElapsed -= arr;
            steps += 1;
          }
        }
      } else {
        arrElapsed += dt;
        while (arrElapsed >= arr) {
          arrElapsed -= arr;
          steps += 1;
        }
      }
      return { steps: steps, dir: activeDir };
    }

    return {
      press: press,
      release: release,
      reset: reset,
      update: update
    };
  }

  function createInputController(options) {
    var opts = options || {};
    var boardElement = opts.boardElement || null;
    var holdElement = opts.holdElement || null;
    var getBoardMetrics = typeof opts.getBoardMetrics === 'function' ? opts.getBoardMetrics : function () { return { cellSize: 32 }; };
    var getGameStatus = typeof opts.getGameStatus === 'function' ? opts.getGameStatus : function () { return 'playing'; };
    var isModalOpen = typeof opts.isModalOpen === 'function' ? opts.isModalOpen : function () { return false; };
    var onAction = typeof opts.onAction === 'function' ? opts.onAction : function () {};
    var onUserGesture = typeof opts.onUserGesture === 'function' ? opts.onUserGesture : function () {};
    var onGamepadChange = typeof opts.onGamepadChange === 'function' ? opts.onGamepadChange : function () {};

    var sensitivity = clampSensitivity(opts.sensitivity);
    var kbDas = createDasArrState(DAS_MS, ARR_MS);
    var gpDas = createDasArrState(DAS_MS, ARR_MS);

    var kbSoftDrop = false;
    var gpSoftDrop = false;
    var gpPrevButtons = {};
    var gpConnectedState = false;
    var gpActiveId = '';

    // Touch state
    var touchState = null;

    function emit(action) {
      onAction(action);
    }

    function setSensitivity(val) {
      sensitivity = clampSensitivity(val);
    }

    function syncSoftDrop() {
      var active = kbSoftDrop || gpSoftDrop;
      emit(active ? 'softDropStart' : 'softDropEnd');
    }

    function clearAll() {
      kbDas.reset();
      gpDas.reset();
      if (kbSoftDrop || gpSoftDrop) {
        kbSoftDrop = false;
        gpSoftDrop = false;
        emit('softDropEnd');
      }
      touchState = null;
    }

    // --- Keyboard ---
    function onKeyDown(e) {
      if (e.ctrlKey || e.metaKey || e.altKey) {
        return;
      }
      var code = e.code || e.key;
      var status = getGameStatus();
      var modalOpen = isModalOpen();

      var gameCodes = {
        ArrowLeft: true,
        ArrowRight: true,
        ArrowDown: true,
        ArrowUp: true,
        Space: true,
        KeyZ: true,
        KeyX: true,
        KeyC: true,
        ShiftLeft: true,
        ShiftRight: true,
        KeyP: true,
        Escape: true
      };

      if (gameCodes[code] && !modalOpen) {
        e.preventDefault();
      }

      onUserGesture();

      if (modalOpen) {
        return;
      }

      if (code === 'KeyP' || code === 'Escape') {
        if (!e.repeat && (status === 'playing' || status === 'paused')) {
          emit('pauseToggle');
        }
        return;
      }

      if (status !== 'playing') {
        return;
      }

      if (code === 'ArrowLeft') {
        if (!e.repeat) {
          kbDas.press(-1);
          var resL = kbDas.update(0);
          for (var il = 0; il < resL.steps; il++) emit('moveLeft');
        }
      } else if (code === 'ArrowRight') {
        if (!e.repeat) {
          kbDas.press(1);
          var resR = kbDas.update(0);
          for (var ir = 0; ir < resR.steps; ir++) emit('moveRight');
        }
      } else if (code === 'ArrowDown') {
        if (!kbSoftDrop) {
          kbSoftDrop = true;
          syncSoftDrop();
        }
      } else if (code === 'ArrowUp' || code === 'KeyX') {
        if (!e.repeat) emit('rotateCW');
      } else if (code === 'KeyZ') {
        if (!e.repeat) emit('rotateCCW');
      } else if (code === 'Space') {
        if (!e.repeat) emit('hardDrop');
      } else if (code === 'KeyC' || code === 'ShiftLeft' || code === 'ShiftRight') {
        if (!e.repeat) emit('hold');
      }
    }

    function onKeyUp(e) {
      var code = e.code || e.key;
      if (code === 'ArrowLeft') {
        kbDas.release(-1);
      } else if (code === 'ArrowRight') {
        kbDas.release(1);
      } else if (code === 'ArrowDown') {
        if (kbSoftDrop) {
          kbSoftDrop = false;
          syncSoftDrop();
        }
      }
    }

    // --- Touch Pointer Events ---
    function getNow() {
      return typeof performance !== 'undefined' && performance.now ? performance.now() : Date.now();
    }

    function onPointerDown(e) {
      if (e.pointerType !== 'touch') {
        return;
      }
      onUserGesture();
      if (isModalOpen() || getGameStatus() !== 'playing') {
        return;
      }
      if (touchState !== null) {
        return;
      }
      e.preventDefault();
      if (boardElement && typeof boardElement.setPointerCapture === 'function') {
        try {
          boardElement.setPointerCapture(e.pointerId);
        } catch (err) {
          // Ignore capture errors
        }
      }
      var now = getNow();
      touchState = {
        pointerId: e.pointerId,
        startX: e.clientX,
        startY: e.clientY,
        startTime: now,
        lastX: e.clientX,
        lastY: e.clientY,
        accumX: 0,
        accumY: 0,
        movedBeyondTap: false,
        locked: false,
        samples: [{ x: e.clientX, y: e.clientY, t: now }]
      };
    }

    function onPointerMove(e) {
      if (!touchState || e.pointerId !== touchState.pointerId) {
        return;
      }
      if (e.pointerType !== 'touch') {
        return;
      }
      e.preventDefault();
      if (touchState.locked || isModalOpen() || getGameStatus() !== 'playing') {
        return;
      }

      var now = getNow();
      var metrics = getBoardMetrics();
      var th = computeTouchThresholds(sensitivity, metrics ? metrics.cellSize : 32);

      var totalDx = e.clientX - touchState.startX;
      var totalDy = e.clientY - touchState.startY;
      if (Math.hypot(totalDx, totalDy) > th.tapMaxDistPx) {
        touchState.movedBeyondTap = true;
      }

      var dx = e.clientX - touchState.lastX;
      var dy = e.clientY - touchState.lastY;
      touchState.lastX = e.clientX;
      touchState.lastY = e.clientY;
      touchState.samples.push({ x: e.clientX, y: e.clientY, t: now });

      // Prune samples older than holdWindowMs
      var maxWin = Math.max(th.flickWindowMs, th.holdWindowMs);
      while (touchState.samples.length > 1 && now - touchState.samples[0].t > maxWin) {
        touchState.samples.shift();
      }

      // Check downward flick (Hard Drop)
      var i, s, dt, sdy, sdx;
      for (i = 0; i < touchState.samples.length - 1; i++) {
        s = touchState.samples[i];
        dt = now - s.t;
        if (dt > 0 && dt <= th.flickWindowMs) {
          sdy = e.clientY - s.y;
          sdx = Math.abs(e.clientX - s.x);
          if (sdy >= th.flickMinDistPx && sdy > sdx * 1.4 && (sdy / dt) >= th.flickMinVelPxPerMs) {
            emit('hardDrop');
            touchState.locked = true;
            return;
          }
        }
        if (dt > 0 && dt <= th.holdWindowMs) {
          sdy = s.y - e.clientY; // upward
          sdx = Math.abs(e.clientX - s.x);
          if (sdy >= th.holdSwipeMinPx && sdy > sdx * 1.4) {
            emit('hold');
            touchState.locked = true;
            return;
          }
        }
      }

      // Proportional lateral drag
      touchState.accumX += dx;
      while (touchState.accumX >= th.pxPerCell) {
        touchState.accumX -= th.pxPerCell;
        emit('moveRight');
      }
      while (touchState.accumX <= -th.pxPerCell) {
        touchState.accumX += th.pxPerCell;
        emit('moveLeft');
      }

      // Proportional downward soft drop drag
      if (dy > 0) {
        touchState.accumY += dy;
        while (touchState.accumY >= th.softDropStepPx) {
          touchState.accumY -= th.softDropStepPx;
          emit('softDropStep');
        }
      } else {
        touchState.accumY = 0;
      }
    }

    function onPointerUp(e) {
      if (!touchState || e.pointerId !== touchState.pointerId) {
        return;
      }
      var state = touchState;
      touchState = null;

      if (state.locked || isModalOpen() || getGameStatus() !== 'playing') {
        return;
      }

      var now = getNow();
      var metrics = getBoardMetrics();
      var th = computeTouchThresholds(sensitivity, metrics ? metrics.cellSize : 32);
      var dist = Math.hypot(e.clientX - state.startX, e.clientY - state.startY);
      if (!state.movedBeyondTap && dist <= th.tapMaxDistPx && (now - state.startTime) <= th.tapMaxDurationMs) {
        emit('rotateCW');
      }
    }

    function onPointerCancel(e) {
      if (touchState && e.pointerId === touchState.pointerId) {
        touchState = null;
      }
    }

    function onHoldClick(e) {
      onUserGesture();
      if (holdElement && typeof holdElement.blur === 'function') {
        holdElement.blur();
      }
      if (!isModalOpen() && getGameStatus() === 'playing') {
        emit('hold');
      }
    }

    // --- Gamepad API ---
    function isButtonPressed(pad, idx) {
      var btn = pad && pad.buttons && pad.buttons[idx];
      return Boolean(btn && (btn.pressed || btn.value > 0.5));
    }

    function findActiveGamepad() {
      if (typeof navigator === 'undefined' || typeof navigator.getGamepads !== 'function') {
        return null;
      }
      var pads = navigator.getGamepads();
      if (!pads) return null;
      var i, p;
      for (i = 0; i < pads.length; i++) {
        p = pads[i];
        if (p && p.connected) {
          return p;
        }
      }
      return null;
    }

    function notifyGamepad(pad) {
      var connected = Boolean(pad);
      var id = pad ? (pad.id || '') : '';
      if (connected !== gpConnectedState || id !== gpActiveId) {
        gpConnectedState = connected;
        gpActiveId = id;
        var isXbox = connected && (/xbox|xinput|045e/i.test(id) || pad.mapping === 'standard');
        onGamepadChange({
          connected: connected,
          isXbox: isXbox,
          id: id,
          mapping: pad ? (pad.mapping || '') : '',
          label: connected ? (isXbox ? 'Control Xbox conectado' : 'Control conectado') : 'Sin control conectado'
        });
      }
    }

    function pollGamepad() {
      var pad = findActiveGamepad();
      notifyGamepad(pad);

      if (!pad) {
        gpDas.reset();
        gpPrevButtons = {};
        if (gpSoftDrop) {
          gpSoftDrop = false;
          syncSoftDrop();
        }
        return;
      }

      var status = getGameStatus();
      var modalOpen = isModalOpen();

      var bA = isButtonPressed(pad, 0);
      var bB = isButtonPressed(pad, 1);
      var bX = isButtonPressed(pad, 2);
      var bLB = isButtonPressed(pad, 4);
      var bRB = isButtonPressed(pad, 5);
      var bStart = isButtonPressed(pad, 9);
      var bUp = isButtonPressed(pad, 12);
      var bDown = isButtonPressed(pad, 13);
      var bLeft = isButtonPressed(pad, 14);
      var bRight = isButtonPressed(pad, 15);

      var risingA = bA && !gpPrevButtons.A;
      var risingB = bB && !gpPrevButtons.B;
      var risingX = bX && !gpPrevButtons.X;
      var risingLB = bLB && !gpPrevButtons.LB;
      var risingRB = bRB && !gpPrevButtons.RB;
      var risingStart = bStart && !gpPrevButtons.Start;
      var risingUp = bUp && !gpPrevButtons.Up;

      gpPrevButtons = {
        A: bA, B: bB, X: bX, LB: bLB, RB: bRB, Start: bStart, Up: bUp
      };

      if (bA || bB || bX || bLB || bRB || bStart || bUp || bDown || bLeft || bRight) {
        onUserGesture();
      }

      if (modalOpen) {
        return;
      }

      if (risingStart && (status === 'playing' || status === 'paused')) {
        emit('pauseToggle');
        return;
      }

      if (status !== 'playing') {
        if (risingA && (status === 'menu' || status === 'gameover')) {
          emit('confirmStart');
        }
        gpDas.reset();
        if (gpSoftDrop) {
          gpSoftDrop = false;
          syncSoftDrop();
        }
        return;
      }

      var axisX = pad.axes && pad.axes.length > 0 ? applyDeadzone(pad.axes[0], GAMEPAD_DEADZONE_X) : 0;
      var axisY = pad.axes && pad.axes.length > 1 ? pad.axes[1] : 0;

      var moveLeftActive = bLeft || axisX < 0;
      var moveRightActive = bRight || axisX > 0;

      if (moveLeftActive && !moveRightActive) {
        gpDas.press(-1);
        gpDas.release(1);
      } else if (moveRightActive && !moveLeftActive) {
        gpDas.press(1);
        gpDas.release(-1);
      } else {
        gpDas.release(-1);
        gpDas.release(1);
      }

      var nextSoftDrop = bDown || axisY >= GAMEPAD_SOFT_DROP_Y;
      if (nextSoftDrop !== gpSoftDrop) {
        gpSoftDrop = nextSoftDrop;
        syncSoftDrop();
      }

      if (risingUp) {
        emit('hardDrop');
      }
      if (risingA || risingB) {
        emit('rotateCW');
      }
      if (risingX) {
        emit('rotateCCW');
      }
      if (risingLB || risingRB) {
        emit('hold');
      }
    }

    function onGamepadEvent() {
      pollGamepad();
    }

    function update(dtMs) {
      if (getGameStatus() === 'playing' && !isModalOpen()) {
        var kbRes = kbDas.update(dtMs);
        var i;
        for (i = 0; i < kbRes.steps; i++) {
          emit(kbRes.dir < 0 ? 'moveLeft' : 'moveRight');
        }
      }

      pollGamepad();

      if (getGameStatus() === 'playing' && !isModalOpen()) {
        var gpRes = gpDas.update(dtMs);
        var j;
        for (j = 0; j < gpRes.steps; j++) {
          emit(gpRes.dir < 0 ? 'moveLeft' : 'moveRight');
        }
      }
    }

    if (typeof window !== 'undefined') {
      window.addEventListener('keydown', onKeyDown);
      window.addEventListener('keyup', onKeyUp);
      window.addEventListener('gamepadconnected', onGamepadEvent);
      window.addEventListener('gamepaddisconnected', onGamepadEvent);
    }
    if (boardElement) {
      boardElement.addEventListener('pointerdown', onPointerDown);
      boardElement.addEventListener('pointermove', onPointerMove);
      boardElement.addEventListener('pointerup', onPointerUp);
      boardElement.addEventListener('pointercancel', onPointerCancel);
      boardElement.addEventListener('lostpointercapture', onPointerCancel);
    }
    if (holdElement) {
      holdElement.addEventListener('click', onHoldClick);
    }

    function destroy() {
      clearAll();
      if (typeof window !== 'undefined') {
        window.removeEventListener('keydown', onKeyDown);
        window.removeEventListener('keyup', onKeyUp);
        window.removeEventListener('gamepadconnected', onGamepadEvent);
        window.removeEventListener('gamepaddisconnected', onGamepadEvent);
      }
      if (boardElement) {
        boardElement.removeEventListener('pointerdown', onPointerDown);
        boardElement.removeEventListener('pointermove', onPointerMove);
        boardElement.removeEventListener('pointerup', onPointerUp);
        boardElement.removeEventListener('pointercancel', onPointerCancel);
        boardElement.removeEventListener('lostpointercapture', onPointerCancel);
      }
      if (holdElement) {
        holdElement.removeEventListener('click', onHoldClick);
      }
    }

    return {
      setSensitivity: setSensitivity,
      update: update,
      clearAll: clearAll,
      destroy: destroy
    };
  }

  var api = {
    computeTouchThresholds: computeTouchThresholds,
    applyDeadzone: applyDeadzone,
    createDasArrState: createDasArrState,
    createInputController: createInputController
  };

  root.Tetris = root.Tetris || {};
  root.Tetris.Input = api;

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
})(typeof globalThis !== 'undefined' ? globalThis : this);

(function (root) {
  'use strict';

  var Constants = (root.Tetris && root.Tetris.Constants) ||
    (typeof require === 'function' ? require('./constants.js') : null);
  var AudioMod = (root.Tetris && root.Tetris.Audio) ||
    (typeof require === 'function' ? require('./audio.js') : null);
  var EngineMod = (root.Tetris && root.Tetris.Engine) ||
    (typeof require === 'function' ? require('./engine.js') : null);
  var RendererMod = (root.Tetris && root.Tetris.Renderer) ||
    (typeof require === 'function' ? require('./renderer.js') : null);
  var InputMod = (root.Tetris && root.Tetris.Input) ||
    (typeof require === 'function' ? require('./input.js') : null);

  var STORAGE_KEY = Constants ? Constants.STORAGE_KEY : 'tetris_clasico_v1';
  var DEFAULT_STATE = Constants ? Constants.DEFAULT_STATE : {
    bestScore: 0,
    bestLevel: 0,
    bestLines: 0,
    touchSensitivity: 5,
    musicEnabled: true,
    sfxEnabled: true,
    startLevel: 1
  };

  var memoryFallbackState = null;

  function cloneDefaultState() {
    return {
      bestScore: DEFAULT_STATE.bestScore,
      bestLevel: DEFAULT_STATE.bestLevel,
      bestLines: DEFAULT_STATE.bestLines,
      touchSensitivity: DEFAULT_STATE.touchSensitivity,
      musicEnabled: DEFAULT_STATE.musicEnabled,
      sfxEnabled: DEFAULT_STATE.sfxEnabled,
      startLevel: DEFAULT_STATE.startLevel
    };
  }

  function sanitizeInt(val, min, max, fallback) {
    var n = Math.floor(Number(val));
    if (!isFinite(n)) {
      return fallback;
    }
    if (min !== null && n < min) return min;
    if (max !== null && n > max) return max;
    return n;
  }

  function sanitizeState(raw) {
    var base = cloneDefaultState();
    if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
      return base;
    }
    base.bestScore = sanitizeInt(raw.bestScore, 0, null, base.bestScore);
    base.bestLevel = sanitizeInt(raw.bestLevel, 0, null, base.bestLevel);
    base.bestLines = sanitizeInt(raw.bestLines, 0, null, base.bestLines);
    base.touchSensitivity = sanitizeInt(raw.touchSensitivity, 1, 10, base.touchSensitivity);
    base.startLevel = sanitizeInt(raw.startLevel, 1, 15, base.startLevel);
    if (typeof raw.musicEnabled === 'boolean') {
      base.musicEnabled = raw.musicEnabled;
    }
    if (typeof raw.sfxEnabled === 'boolean') {
      base.sfxEnabled = raw.sfxEnabled;
    }
    return base;
  }

  function loadState(storageObj) {
    try {
      var store = storageObj !== undefined ? storageObj : (typeof window !== 'undefined' ? window.localStorage : null);
      if (!store || typeof store.getItem !== 'function') {
        return memoryFallbackState ? sanitizeState(memoryFallbackState) : cloneDefaultState();
      }
      var rawText = store.getItem(STORAGE_KEY);
      if (!rawText) {
        return memoryFallbackState ? sanitizeState(memoryFallbackState) : cloneDefaultState();
      }
      var parsed = JSON.parse(rawText);
      var clean = sanitizeState(parsed);
      memoryFallbackState = clean;
      return clean;
    } catch (err) {
      return memoryFallbackState ? sanitizeState(memoryFallbackState) : cloneDefaultState();
    }
  }

  function saveState(partialState, storageObj) {
    var current = loadState(storageObj);
    var merged = sanitizeState({
      bestScore: partialState && partialState.bestScore !== undefined ? partialState.bestScore : current.bestScore,
      bestLevel: partialState && partialState.bestLevel !== undefined ? partialState.bestLevel : current.bestLevel,
      bestLines: partialState && partialState.bestLines !== undefined ? partialState.bestLines : current.bestLines,
      touchSensitivity: partialState && partialState.touchSensitivity !== undefined ? partialState.touchSensitivity : current.touchSensitivity,
      musicEnabled: partialState && partialState.musicEnabled !== undefined ? partialState.musicEnabled : current.musicEnabled,
      sfxEnabled: partialState && partialState.sfxEnabled !== undefined ? partialState.sfxEnabled : current.sfxEnabled,
      startLevel: partialState && partialState.startLevel !== undefined ? partialState.startLevel : current.startLevel
    });
    memoryFallbackState = merged;
    try {
      var store = storageObj !== undefined ? storageObj : (typeof window !== 'undefined' ? window.localStorage : null);
      if (store && typeof store.setItem === 'function') {
        store.setItem(STORAGE_KEY, JSON.stringify(merged));
      }
    } catch (err) {
      // Fallback safely to in-memory state
    }
    return merged;
  }

  function registerPwaIfHttp() {
    if (typeof window === 'undefined' || typeof document === 'undefined') {
      return;
    }
    var proto = window.location && window.location.protocol;
    if (proto !== 'http:' && proto !== 'https:') {
      return;
    }
    try {
      if (!document.querySelector('link[rel="manifest"]')) {
        var link = document.createElement('link');
        link.rel = 'manifest';
        link.href = './manifest.webmanifest';
        document.head.appendChild(link);
      }
    } catch (err) {
      // Ignore DOM errors
    }
    if (typeof navigator !== 'undefined' && 'serviceWorker' in navigator) {
      try {
        navigator.serviceWorker.register('./service-worker.js').catch(function () {});
      } catch (err2) {
        // Ignore SW registration errors
      }
    }
  }

  function bootApp() {
    if (typeof document === 'undefined' || !EngineMod || !AudioMod || !RendererMod || !InputMod) {
      return null;
    }

    registerPwaIfHttp();

    var state = loadState();
    var settingsOpen = false;
    var lastStatus = 'menu';

    // DOM Elements
    var el = {
      boardStage: document.getElementById('board-stage'),
      boardCanvas: document.getElementById('board-canvas'),
      holdBox: document.getElementById('hold-box'),
      holdCanvas: document.getElementById('hold-canvas'),
      nextCanvas: document.getElementById('next-canvas'),
      scoreValue: document.getElementById('score-value'),
      levelValue: document.getElementById('level-value'),
      linesValue: document.getElementById('lines-value'),
      bestScoreValue: document.getElementById('best-score-value'),
      bestLevelValue: document.getElementById('best-level-value'),
      bestLinesValue: document.getElementById('best-lines-value'),
      btnPause: document.getElementById('btn-pause'),
      btnSettings: document.getElementById('btn-settings'),
      btnMusic: document.getElementById('btn-music'),
      btnSfx: document.getElementById('btn-sfx'),
      gamepadBadge: document.getElementById('gamepad-badge'),
      overlayStart: document.getElementById('overlay-start'),
      btnLevelDown: document.getElementById('btn-level-down'),
      startLevelValue: document.getElementById('start-level-value'),
      btnLevelUp: document.getElementById('btn-level-up'),
      btnPlay: document.getElementById('btn-play'),
      btnStartSettings: document.getElementById('btn-start-settings'),
      overlayPause: document.getElementById('overlay-pause'),
      btnResume: document.getElementById('btn-resume'),
      btnPauseSettings: document.getElementById('btn-pause-settings'),
      btnRestart: document.getElementById('btn-restart'),
      overlayGameover: document.getElementById('overlay-gameover'),
      finalScoreValue: document.getElementById('final-score-value'),
      finalLevelValue: document.getElementById('final-level-value'),
      finalLinesValue: document.getElementById('final-lines-value'),
      gameoverRecordBadge: document.getElementById('gameover-record-badge'),
      btnPlayAgain: document.getElementById('btn-play-again'),
      btnGameoverSettings: document.getElementById('btn-gameover-settings'),
      modalSettings: document.getElementById('modal-settings'),
      sensitivitySlider: document.getElementById('sensitivity-slider'),
      sensitivityValue: document.getElementById('sensitivity-value'),
      toggleMusic: document.getElementById('toggle-music'),
      toggleSfx: document.getElementById('toggle-sfx'),
      settingsGamepadStatus: document.getElementById('settings-gamepad-status'),
      btnCloseSettings: document.getElementById('btn-close-settings')
    };

    var engine = EngineMod.createEngine();
    var audio = AudioMod.createAudioController({
      musicEnabled: state.musicEnabled,
      sfxEnabled: state.sfxEnabled
    });
    var renderer = RendererMod.createRenderer({
      boardCanvas: el.boardCanvas,
      holdCanvas: el.holdCanvas,
      nextCanvas: el.nextCanvas,
      boardStage: el.boardStage
    });

    function syncAudioButtons() {
      var m = audio.isMusicEnabled();
      var s = audio.isSfxEnabled();
      if (el.btnMusic) {
        el.btnMusic.setAttribute('aria-pressed', String(m));
        el.btnMusic.classList.toggle('muted', !m);
      }
      if (el.btnSfx) {
        el.btnSfx.setAttribute('aria-pressed', String(s));
        el.btnSfx.classList.toggle('muted', !s);
      }
      if (el.toggleMusic) {
        el.toggleMusic.setAttribute('aria-pressed', String(m));
        el.toggleMusic.textContent = m ? 'Activada' : 'Silenciada';
      }
      if (el.toggleSfx) {
        el.toggleSfx.setAttribute('aria-pressed', String(s));
        el.toggleSfx.textContent = s ? 'Activados' : 'Silenciados';
      }
    }

    function syncSensitivityUI() {
      if (el.sensitivitySlider) {
        el.sensitivitySlider.value = String(state.touchSensitivity);
      }
      if (el.sensitivityValue) {
        el.sensitivityValue.textContent = String(state.touchSensitivity);
      }
    }

    function syncStartLevelUI() {
      if (el.startLevelValue) {
        el.startLevelValue.textContent = String(state.startLevel);
      }
    }

    function syncRecordsUI() {
      if (el.bestScoreValue) el.bestScoreValue.textContent = String(state.bestScore);
      if (el.bestLevelValue) el.bestLevelValue.textContent = String(state.bestLevel);
      if (el.bestLinesValue) el.bestLinesValue.textContent = String(state.bestLines);
    }

    function syncOverlays(status) {
      if (el.overlayStart) el.overlayStart.hidden = status !== 'menu';
      if (el.overlayPause) el.overlayPause.hidden = status !== 'paused';
      if (el.overlayGameover) el.overlayGameover.hidden = status !== 'gameover';
      if (el.modalSettings) el.modalSettings.hidden = !settingsOpen;
    }

    function updateHud(snap) {
      if (el.scoreValue) el.scoreValue.textContent = String(snap.score);
      if (el.levelValue) el.levelValue.textContent = String(snap.level);
      if (el.linesValue) el.linesValue.textContent = String(snap.lines);
    }

    function processEvents(events) {
      if (!events || !events.length) {
        return;
      }
      audio.handleEvents(events);
      renderer.triggerEffects(events);

      var i, ev;
      for (i = 0; i < events.length; i++) {
        ev = events[i];
        if (ev.type === 'gameOver') {
          var isNewRecord = ev.score > state.bestScore && ev.score > 0;
          state = saveState({
            bestScore: Math.max(state.bestScore, ev.score),
            bestLevel: Math.max(state.bestLevel, ev.level),
            bestLines: Math.max(state.bestLines, ev.lines)
          });
          syncRecordsUI();
          if (el.finalScoreValue) el.finalScoreValue.textContent = String(ev.score);
          if (el.finalLevelValue) el.finalLevelValue.textContent = String(ev.level);
          if (el.finalLinesValue) el.finalLinesValue.textContent = String(ev.lines);
          if (el.gameoverRecordBadge) el.gameoverRecordBadge.hidden = !isNewRecord;
        }
      }
    }

    function startNewGame() {
      audio.unlock();
      renderer.resetEffects();
      input.clearAll();
      var res = engine.start(state.startLevel);
      processEvents(res.events);
      var snap = engine.getSnapshot();
      lastStatus = snap.status;
      audio.syncState(snap.status);
      syncOverlays(snap.status);
      updateHud(snap);
    }

    function pauseGame() {
      var snap = engine.getSnapshot();
      if (snap.status === 'playing') {
        engine.pause();
        input.clearAll();
        audio.syncState('paused');
        lastStatus = 'paused';
        syncOverlays('paused');
      }
    }

    function resumeGame() {
      audio.unlock();
      var snap = engine.getSnapshot();
      if (snap.status === 'paused') {
        engine.resume();
        input.clearAll();
        audio.syncState('playing');
        lastStatus = 'playing';
        syncOverlays('playing');
      }
    }

    function togglePauseGame() {
      var snap = engine.getSnapshot();
      if (snap.status === 'playing') {
        pauseGame();
      } else if (snap.status === 'paused') {
        resumeGame();
      }
    }

    function openSettings() {
      audio.unlock();
      var snap = engine.getSnapshot();
      if (snap.status === 'playing') {
        pauseGame();
      }
      settingsOpen = true;
      syncOverlays(engine.getSnapshot().status);
    }

    function closeSettings() {
      settingsOpen = false;
      syncOverlays(engine.getSnapshot().status);
    }

    var input = InputMod.createInputController({
      boardElement: el.boardStage,
      holdElement: el.holdBox,
      getBoardMetrics: renderer.getBoardMetrics,
      getGameStatus: function () {
        return engine.getSnapshot().status;
      },
      isModalOpen: function () {
        return settingsOpen;
      },
      onUserGesture: function () {
        audio.unlock();
      },
      onGamepadChange: function (info) {
        if (el.gamepadBadge) {
          el.gamepadBadge.classList.toggle('connected', info.connected);
          var txt = el.gamepadBadge.querySelector('.gamepad-text');
          if (txt) txt.textContent = info.label;
        }
        if (el.settingsGamepadStatus) {
          el.settingsGamepadStatus.classList.toggle('connected', info.connected);
          el.settingsGamepadStatus.textContent = info.label;
        }
      },
      onAction: function (action) {
        var res = null;
        if (action === 'moveLeft') {
          res = engine.moveLeft();
        } else if (action === 'moveRight') {
          res = engine.moveRight();
        } else if (action === 'softDropStart') {
          engine.setSoftDrop(true);
        } else if (action === 'softDropEnd') {
          engine.setSoftDrop(false);
        } else if (action === 'softDropStep') {
          res = engine.softDropStep();
        } else if (action === 'hardDrop') {
          res = engine.hardDrop();
        } else if (action === 'rotateCW') {
          res = engine.rotateCW();
        } else if (action === 'rotateCCW') {
          res = engine.rotateCCW();
        } else if (action === 'hold') {
          res = engine.hold();
        } else if (action === 'pauseToggle') {
          togglePauseGame();
        } else if (action === 'confirmStart') {
          startNewGame();
        }
        if (res && res.events && res.events.length) {
          processEvents(res.events);
        }
      },
      sensitivity: state.touchSensitivity
    });

    function bindButton(btn, handler) {
      if (!btn) return;
      btn.addEventListener('click', function () {
        btn.blur();
        audio.unlock();
        handler();
      });
    }

    bindButton(el.btnPlay, startNewGame);
    bindButton(el.btnPlayAgain, startNewGame);
    bindButton(el.btnRestart, startNewGame);
    bindButton(el.btnPause, togglePauseGame);
    bindButton(el.btnResume, resumeGame);
    bindButton(el.btnSettings, openSettings);
    bindButton(el.btnStartSettings, openSettings);
    bindButton(el.btnPauseSettings, openSettings);
    bindButton(el.btnGameoverSettings, openSettings);
    bindButton(el.btnCloseSettings, closeSettings);

    bindButton(el.btnLevelDown, function () {
      state = saveState({ startLevel: Math.max(1, state.startLevel - 1) });
      syncStartLevelUI();
    });

    bindButton(el.btnLevelUp, function () {
      state = saveState({ startLevel: Math.min(15, state.startLevel + 1) });
      syncStartLevelUI();
    });

    function toggleMusic() {
      var next = !audio.isMusicEnabled();
      audio.setMusicEnabled(next);
      state = saveState({ musicEnabled: next });
      syncAudioButtons();
    }

    function toggleSfx() {
      var next = !audio.isSfxEnabled();
      audio.setSfxEnabled(next);
      state = saveState({ sfxEnabled: next });
      syncAudioButtons();
    }

    bindButton(el.btnMusic, toggleMusic);
    bindButton(el.toggleMusic, toggleMusic);
    bindButton(el.btnSfx, toggleSfx);
    bindButton(el.toggleSfx, toggleSfx);

    if (el.sensitivitySlider) {
      var onSensChange = function () {
        var val = sanitizeInt(el.sensitivitySlider.value, 1, 10, 5);
        state = saveState({ touchSensitivity: val });
        input.setSensitivity(val);
        syncSensitivityUI();
      };
      el.sensitivitySlider.addEventListener('input', onSensChange);
      el.sensitivitySlider.addEventListener('change', onSensChange);
    }

    if (el.modalSettings) {
      el.modalSettings.addEventListener('click', function (e) {
        if (e.target === el.modalSettings) {
          closeSettings();
        }
      });
    }

    window.addEventListener('keydown', function (e) {
      if ((e.code === 'Escape' || e.key === 'Escape') && settingsOpen) {
        e.preventDefault();
        closeSettings();
      }
    });

    window.addEventListener('blur', function () {
      input.clearAll();
      if (engine.getSnapshot().status === 'playing') {
        pauseGame();
      }
    });

    document.addEventListener('visibilitychange', function () {
      if (document.hidden) {
        input.clearAll();
        if (engine.getSnapshot().status === 'playing') {
          pauseGame();
        }
      }
    });

    window.addEventListener('resize', function () {
      renderer.resize();
    });

    // Initial UI sync
    renderer.resize();
    syncAudioButtons();
    syncSensitivityUI();
    syncStartLevelUI();
    syncRecordsUI();
    syncOverlays('menu');

    var lastTime = typeof performance !== 'undefined' && performance.now ? performance.now() : Date.now();
    function frame(now) {
      var dtMs = Math.min(100, Math.max(0, now - lastTime));
      lastTime = now;

      input.update(dtMs);

      var snap = engine.getSnapshot();
      if (snap.status === 'playing' && !settingsOpen) {
        var stepRes = engine.step(dtMs);
        processEvents(stepRes.events);
        snap = engine.getSnapshot();
      }

      if (snap.status !== lastStatus) {
        lastStatus = snap.status;
        audio.syncState(snap.status);
        syncOverlays(snap.status);
      }

      updateHud(snap);
      renderer.render(snap, dtMs);
      requestAnimationFrame(frame);
    }

    requestAnimationFrame(frame);

    return {
      engine: engine,
      audio: audio,
      renderer: renderer,
      input: input
    };
  }

  if (typeof document !== 'undefined') {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', bootApp);
    } else {
      bootApp();
    }
  }

  var api = {
    STORAGE_KEY: STORAGE_KEY,
    DEFAULT_STATE: DEFAULT_STATE,
    sanitizeState: sanitizeState,
    loadState: loadState,
    saveState: saveState,
    bootApp: bootApp
  };

  root.Tetris = root.Tetris || {};
  root.Tetris.Main = api;

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
})(typeof globalThis !== 'undefined' ? globalThis : this);

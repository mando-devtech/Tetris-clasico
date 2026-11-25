(function (root) {
  'use strict';

  var KOROBEINIKI_BPM = 144;
  var BEAT_SEC = 60 / KOROBEINIKI_BPM;

  var NOTE_FREQS = Object.freeze({
    REST: 0,
    E2: 82.41,
    A2: 110.00,
    B2: 123.47,
    C3: 130.81,
    D3: 146.83,
    E3: 164.81,
    'G#3': 207.65,
    A3: 220.00,
    B3: 246.94,
    C4: 261.63,
    D4: 293.66,
    E4: 329.63,
    F4: 349.23,
    G4: 392.00,
    'G#4': 415.30,
    A4: 440.00,
    B4: 493.88,
    C5: 523.25,
    D5: 587.33,
    E5: 659.25,
    F5: 698.46,
    G5: 783.99,
    'G#5': 830.61,
    A5: 880.00
  });

  // 24-bar A-A-B Korobeiniki arrangement (each bar sums to 4.0 beats)
  var SECTION_A_LEAD = [
    [['E5', 1], ['B4', 0.5], ['C5', 0.5], ['D5', 1], ['C5', 0.5], ['B4', 0.5]],
    [['A4', 1], ['A4', 0.5], ['C5', 0.5], ['E5', 1], ['D5', 0.5], ['C5', 0.5]],
    [['B4', 1.5], ['C5', 0.5], ['D5', 1], ['E5', 1]],
    [['C5', 1], ['A4', 1], ['A4', 2]],
    [['REST', 0.5], ['D5', 1], ['F5', 0.5], ['A5', 1], ['G5', 0.5], ['F5', 0.5]],
    [['E5', 1.5], ['C5', 0.5], ['E5', 1], ['D5', 0.5], ['C5', 0.5]],
    [['B4', 1], ['B4', 0.5], ['C5', 0.5], ['D5', 1], ['E5', 1]],
    [['C5', 1], ['A4', 1], ['A4', 2]]
  ];

  var SECTION_B_LEAD = [
    [['E4', 2], ['C4', 2]],
    [['D4', 2], ['B3', 2]],
    [['C4', 2], ['A3', 2]],
    [['G#3', 2], ['B3', 2]],
    [['E4', 2], ['C4', 2]],
    [['D4', 2], ['B3', 2]],
    [['C4', 1], ['E4', 1], ['A4', 2]],
    [['G#4', 3], ['REST', 1]]
  ];

  var SECTION_A_BASS = [
    [['E2', 1], ['E3', 1], ['E2', 1], ['E3', 1]],
    [['A2', 1], ['A3', 1], ['A2', 1], ['A3', 1]],
    [['E2', 1], ['G#3', 1], ['E2', 1], ['G#3', 1]],
    [['A2', 1], ['E3', 1], ['A2', 2]],
    [['D3', 1], ['A3', 1], ['D3', 1], ['A3', 1]],
    [['C3', 1], ['G4', 1], ['C3', 1], ['G4', 1]],
    [['E2', 1], ['G#3', 1], ['E2', 1], ['G#3', 1]],
    [['A2', 1], ['E3', 1], ['A2', 2]]
  ];

  var SECTION_B_BASS = [
    [['A2', 1], ['E3', 1], ['A2', 1], ['E3', 1]],
    [['E2', 1], ['G#3', 1], ['E2', 1], ['G#3', 1]],
    [['A2', 1], ['E3', 1], ['A2', 1], ['E3', 1]],
    [['E2', 1], ['G#3', 1], ['E2', 1], ['E3', 1]],
    [['A2', 1], ['E3', 1], ['A2', 1], ['E3', 1]],
    [['E2', 1], ['G#3', 1], ['E2', 1], ['G#3', 1]],
    [['A2', 1], ['E3', 1], ['A2', 1], ['E3', 1]],
    [['E2', 1], ['G#3', 1], ['E2', 2]]
  ];

  var KOROBEINIKI_LEAD = Object.freeze(SECTION_A_LEAD.concat(SECTION_A_LEAD, SECTION_B_LEAD));
  var KOROBEINIKI_BASS = Object.freeze(SECTION_A_BASS.concat(SECTION_A_BASS, SECTION_B_BASS));

  function flattenBars(bars) {
    var events = [];
    var beatOffset = 0;
    var b, i, item;
    for (b = 0; b < bars.length; b++) {
      for (i = 0; i < bars[b].length; i++) {
        item = bars[b][i];
        events.push({
          note: item[0],
          startBeat: beatOffset,
          durationBeats: item[1]
        });
        beatOffset += item[1];
      }
    }
    return { events: events, totalBeats: beatOffset };
  }

  var LEAD_FLAT = flattenBars(KOROBEINIKI_LEAD);
  var BASS_FLAT = flattenBars(KOROBEINIKI_BASS);
  var TOTAL_LOOP_BEATS = LEAD_FLAT.totalBeats;

  function getAudioContextClass() {
    if (typeof window === 'undefined') {
      return null;
    }
    return window.AudioContext || window.webkitAudioContext || null;
  }

  function createAudioController(options) {
    var opts = options || {};
    var musicEnabled = opts.musicEnabled !== undefined ? Boolean(opts.musicEnabled) : true;
    var sfxEnabled = opts.sfxEnabled !== undefined ? Boolean(opts.sfxEnabled) : true;
    var currentStatus = 'menu';

    var ctx = null;
    var masterGain = null;
    var musicGain = null;
    var sfxGain = null;

    var schedulerTimer = null;
    var nextLoopStartTime = 0;
    var leadIndex = 0;
    var bassIndex = 0;
    var loopNumber = 0;
    var activeMusicNodes = [];

    function ensureContext() {
      if (ctx) {
        return ctx;
      }
      var AudioCtx = getAudioContextClass();
      if (!AudioCtx) {
        return null;
      }
      try {
        ctx = new AudioCtx();
        masterGain = ctx.createGain();
        masterGain.gain.value = 0.7;
        masterGain.connect(ctx.destination);

        musicGain = ctx.createGain();
        musicGain.gain.value = musicEnabled ? 0.22 : 0;
        musicGain.connect(masterGain);

        sfxGain = ctx.createGain();
        sfxGain.gain.value = sfxEnabled ? 0.45 : 0;
        sfxGain.connect(masterGain);
      } catch (err) {
        ctx = null;
      }
      return ctx;
    }

    function unlock() {
      var audioCtx = ensureContext();
      if (!audioCtx) {
        return false;
      }
      if (audioCtx.state === 'suspended' && typeof audioCtx.resume === 'function') {
        try {
          audioCtx.resume();
        } catch (err) {
          // Ignore resume errors outside gesture
        }
      }
      if (currentStatus === 'playing' && musicEnabled && !schedulerTimer) {
        startMusicScheduler();
      }
      return true;
    }

    function stopActiveMusicNodes() {
      var i, osc;
      for (i = 0; i < activeMusicNodes.length; i++) {
        osc = activeMusicNodes[i];
        try {
          osc.stop();
        } catch (err) {
          // Already stopped
        }
        try {
          osc.disconnect();
        } catch (err2) {
          // Ignore
        }
      }
      activeMusicNodes = [];
    }

    function stopMusicScheduler() {
      if (schedulerTimer !== null) {
        clearInterval(schedulerTimer);
        schedulerTimer = null;
      }
      stopActiveMusicNodes();
    }

    function scheduleNote(freq, startTime, durationSec, type, volume) {
      if (!ctx || !musicGain || freq <= 0) {
        return;
      }
      var osc = ctx.createOscillator();
      var env = ctx.createGain();
      osc.type = type;
      osc.frequency.setValueAtTime(freq, startTime);

      var attack = 0.01;
      var release = Math.min(0.04, durationSec * 0.25);
      var sustainEnd = Math.max(startTime + attack, startTime + durationSec - release);

      env.gain.setValueAtTime(0.0001, startTime);
      env.gain.linearRampToValueAtTime(volume, startTime + attack);
      env.gain.setValueAtTime(volume, sustainEnd);
      env.gain.exponentialRampToValueAtTime(0.0001, startTime + durationSec);

      osc.connect(env);
      env.connect(musicGain);

      osc.start(startTime);
      osc.stop(startTime + durationSec + 0.01);

      activeMusicNodes.push(osc);
      osc.onended = function () {
        var idx = activeMusicNodes.indexOf(osc);
        if (idx !== -1) {
          activeMusicNodes.splice(idx, 1);
        }
      };
    }

    function schedulerTick() {
      if (!ctx || currentStatus !== 'playing' || !musicEnabled) {
        return;
      }
      var lookaheadSec = 0.12;
      var horizon = ctx.currentTime + lookaheadSec;
      var loopDurSec = TOTAL_LOOP_BEATS * BEAT_SEC;

      while (true) {
        var leadItem = LEAD_FLAT.events[leadIndex];
        var leadTime = nextLoopStartTime + loopNumber * loopDurSec + leadItem.startBeat * BEAT_SEC;
        var bassItem = BASS_FLAT.events[bassIndex];
        var bassTime = nextLoopStartTime + loopNumber * loopDurSec + bassItem.startBeat * BEAT_SEC;

        var didSchedule = false;

        if (leadTime < horizon) {
          var leadFreq = NOTE_FREQS[leadItem.note] || 0;
          if (leadFreq > 0) {
            scheduleNote(leadFreq, leadTime, leadItem.durationBeats * BEAT_SEC * 0.9, 'square', 0.35);
          }
          leadIndex += 1;
          didSchedule = true;
        }

        if (bassTime < horizon) {
          var bassFreq = NOTE_FREQS[bassItem.note] || 0;
          if (bassFreq > 0) {
            scheduleNote(bassFreq, bassTime, bassItem.durationBeats * BEAT_SEC * 0.85, 'triangle', 0.45);
          }
          bassIndex += 1;
          didSchedule = true;
        }

        if (leadIndex >= LEAD_FLAT.events.length && bassIndex >= BASS_FLAT.events.length) {
          leadIndex = 0;
          bassIndex = 0;
          loopNumber += 1;
        }

        if (!didSchedule) {
          break;
        }
      }
    }

    function startMusicScheduler() {
      if (!ctx || schedulerTimer !== null || !musicEnabled || currentStatus !== 'playing') {
        return;
      }
      nextLoopStartTime = ctx.currentTime + 0.04;
      leadIndex = 0;
      bassIndex = 0;
      loopNumber = 0;
      schedulerTick();
      schedulerTimer = setInterval(schedulerTick, 25);
    }

    function playTone(freqStart, freqEnd, durationSec, type, gainPeak, delaySec) {
      if (!sfxEnabled) {
        return;
      }
      var audioCtx = ensureContext();
      if (!audioCtx || !sfxGain) {
        return;
      }
      var t0 = audioCtx.currentTime + (delaySec || 0);
      var osc = audioCtx.createOscillator();
      var env = audioCtx.createGain();
      osc.type = type || 'triangle';
      osc.frequency.setValueAtTime(freqStart, t0);
      if (freqEnd !== freqStart) {
        osc.frequency.exponentialRampToValueAtTime(Math.max(20, freqEnd), t0 + durationSec);
      }

      env.gain.setValueAtTime(0.0001, t0);
      env.gain.linearRampToValueAtTime(gainPeak || 0.3, t0 + 0.008);
      env.gain.exponentialRampToValueAtTime(0.0001, t0 + durationSec);

      osc.connect(env);
      env.connect(sfxGain);
      osc.start(t0);
      osc.stop(t0 + durationSec + 0.015);
    }

    function playSfx(name) {
      if (!sfxEnabled) {
        return;
      }
      if (name === 'move') {
        playTone(320, 360, 0.04, 'triangle', 0.16);
      } else if (name === 'rotate') {
        playTone(440, 620, 0.06, 'sine', 0.22);
      } else if (name === 'softDrop') {
        playTone(220, 180, 0.035, 'sine', 0.12);
      } else if (name === 'hardDrop') {
        playTone(260, 90, 0.11, 'sawtooth', 0.28);
        playTone(150, 65, 0.09, 'triangle', 0.32, 0.01);
      } else if (name === 'lock') {
        playTone(190, 120, 0.07, 'triangle', 0.22);
      } else if (name === 'hold') {
        playTone(392, 523.25, 0.08, 'sine', 0.22);
      } else if (name === 'lineClear') {
        playTone(523.25, 659.25, 0.12, 'square', 0.22, 0);
        playTone(659.25, 783.99, 0.15, 'square', 0.22, 0.07);
      } else if (name === 'tetris') {
        playTone(523.25, 523.25, 0.09, 'square', 0.25, 0);
        playTone(659.25, 659.25, 0.09, 'square', 0.25, 0.07);
        playTone(783.99, 783.99, 0.09, 'square', 0.25, 0.14);
        playTone(1046.5, 1046.5, 0.22, 'square', 0.28, 0.21);
      } else if (name === 'levelUp') {
        playTone(440, 554.37, 0.09, 'triangle', 0.25, 0);
        playTone(554.37, 659.25, 0.09, 'triangle', 0.25, 0.08);
        playTone(659.25, 880, 0.18, 'triangle', 0.28, 0.16);
      } else if (name === 'gameOver') {
        playTone(392, 349.23, 0.16, 'sawtooth', 0.24, 0);
        playTone(349.23, 293.66, 0.16, 'sawtooth', 0.24, 0.15);
        playTone(293.66, 196, 0.32, 'sawtooth', 0.26, 0.30);
      }
    }

    function handleEvents(events) {
      if (!events || !events.length || !sfxEnabled) {
        return;
      }
      var hasLineClear = false;
      var hasHardDrop = false;
      var i, ev;
      for (i = 0; i < events.length; i++) {
        ev = events[i];
        if (ev.type === 'lineClear') {
          hasLineClear = true;
          playSfx(ev.count === 4 ? 'tetris' : 'lineClear');
        } else if (ev.type === 'hardDrop') {
          hasHardDrop = true;
          playSfx('hardDrop');
        }
      }
      for (i = 0; i < events.length; i++) {
        ev = events[i];
        if (ev.type === 'move') {
          playSfx('move');
        } else if (ev.type === 'rotate') {
          playSfx('rotate');
        } else if (ev.type === 'hold') {
          playSfx('hold');
        } else if (ev.type === 'softDrop') {
          playSfx('softDrop');
        } else if (ev.type === 'lock' && !hasLineClear && !hasHardDrop) {
          playSfx('lock');
        } else if (ev.type === 'levelUp') {
          playSfx('levelUp');
        } else if (ev.type === 'gameOver') {
          playSfx('gameOver');
        }
      }
    }

    function syncState(status) {
      currentStatus = status;
      if (currentStatus === 'playing' && musicEnabled) {
        if (ctx) {
          startMusicScheduler();
        }
      } else {
        stopMusicScheduler();
      }
    }

    function setMusicEnabled(enabled) {
      musicEnabled = Boolean(enabled);
      if (musicGain && ctx) {
        musicGain.gain.setValueAtTime(musicEnabled ? 0.22 : 0, ctx.currentTime);
      }
      if (musicEnabled && currentStatus === 'playing') {
        if (ctx) {
          startMusicScheduler();
        }
      } else {
        stopMusicScheduler();
      }
    }

    function setSfxEnabled(enabled) {
      sfxEnabled = Boolean(enabled);
      if (sfxGain && ctx) {
        sfxGain.gain.setValueAtTime(sfxEnabled ? 0.45 : 0, ctx.currentTime);
      }
    }

    function isMusicEnabled() {
      return musicEnabled;
    }

    function isSfxEnabled() {
      return sfxEnabled;
    }

    function dispose() {
      stopMusicScheduler();
      if (ctx && typeof ctx.close === 'function') {
        try {
          ctx.close();
        } catch (err) {
          // Ignore close errors
        }
      }
      ctx = null;
      masterGain = null;
      musicGain = null;
      sfxGain = null;
    }

    return {
      unlock: unlock,
      setMusicEnabled: setMusicEnabled,
      setSfxEnabled: setSfxEnabled,
      isMusicEnabled: isMusicEnabled,
      isSfxEnabled: isSfxEnabled,
      playSfx: playSfx,
      handleEvents: handleEvents,
      syncState: syncState,
      dispose: dispose
    };
  }

  var api = {
    KOROBEINIKI_BPM: KOROBEINIKI_BPM,
    NOTE_FREQS: NOTE_FREQS,
    KOROBEINIKI_LEAD: KOROBEINIKI_LEAD,
    KOROBEINIKI_BASS: KOROBEINIKI_BASS,
    createAudioController: createAudioController
  };

  root.Tetris = root.Tetris || {};
  root.Tetris.Audio = api;

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
})(typeof globalThis !== 'undefined' ? globalThis : this);

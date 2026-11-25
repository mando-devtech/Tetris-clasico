'use strict';

const { describe, it } = require('node:test');
const assert = require('node:assert/strict');
const AudioMod = require('../../js/audio.js');

describe('Tetris.Audio', () => {
  it('exports valid 24-bar 144 BPM Korobeiniki lead and bass scores', () => {
    assert.equal(AudioMod.KOROBEINIKI_BPM, 144);
    assert.equal(AudioMod.KOROBEINIKI_LEAD.length, 24);
    assert.equal(AudioMod.KOROBEINIKI_BASS.length, 24);

    for (const track of [AudioMod.KOROBEINIKI_LEAD, AudioMod.KOROBEINIKI_BASS]) {
      let total = 0;
      for (const bar of track) {
        let barBeats = 0;
        for (const [note, dur] of bar) {
          assert.ok(Object.prototype.hasOwnProperty.call(AudioMod.NOTE_FREQS, note), `Missing note ${note}`);
          assert.ok(dur > 0);
          barBeats += dur;
        }
        assert.equal(barBeats, 4.0);
        total += barBeats;
      }
      assert.equal(total, 96);
    }
  });

  it('safely operates in headless Node without AudioContext', () => {
    const audio = AudioMod.createAudioController({ musicEnabled: true, sfxEnabled: true });
    assert.equal(audio.isMusicEnabled(), true);
    assert.equal(audio.isSfxEnabled(), true);
    assert.equal(audio.unlock(), false);
    audio.playSfx('rotate');
    audio.handleEvents([{ type: 'lineClear', count: 4 }]);
    audio.syncState('playing');
    audio.setMusicEnabled(false);
    assert.equal(audio.isMusicEnabled(), false);
    audio.setSfxEnabled(false);
    assert.equal(audio.isSfxEnabled(), false);
    audio.syncState('paused');
    audio.dispose();
  });
});

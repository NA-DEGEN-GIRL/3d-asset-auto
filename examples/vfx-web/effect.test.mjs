import assert from 'node:assert/strict';
import { test } from 'node:test';
import { Group, DataTexture } from 'three';
import { createArcanePulse, pulseState, PULSE } from './effect.js';
import { createSoulFlame, flipbookFrame } from './soul-effect.js';

test('seeking backwards reproduces geometry and seeded variants remain independent', () => {
  const a = createArcanePulse({ seed: 17 });
  const b = createArcanePulse({ seed: 17 });
  const c = createArcanePulse({ seed: 91 });
  a.update(0.82); b.update(0.82); c.update(0.82);
  const position = (fx) => Array.from(fx.group.getObjectByName('sparks').geometry.attributes.position.array);
  const expected = position(a);
  assert.deepEqual(position(b), expected);
  assert.notDeepEqual(position(c), expected);
  a.update(1.9); a.update(0.1); a.update(0.82);
  assert.deepEqual(position(a), expected);
  a.setLayer('ring', false);
  a.update(0.82);
  assert.equal(a.group.getObjectByName('ring').visible, false);
  assert.equal(b.group.getObjectByName('ring').visible, true);
  a.group.getObjectByName('ring').material.uniforms.uColor.value.set('#ff0000');
  assert.notEqual(a.group.getObjectByName('ring').material.uniforms.uColor.value.getHex(),
    b.group.getObjectByName('ring').material.uniforms.uColor.value.getHex());
  a.dispose(); b.dispose(); c.dispose();
});

test('one-shot endpoints, cancellation, replay and finite particles', () => {
  const effect = createArcanePulse();
  for (const t of [-1, 0, PULSE.duration, 10]) {
    effect.update(t); assert.equal(effect.group.visible, false);
  }
  for (let i = 1; i < 240; i++) {
    effect.update(i / 100);
    const spark = effect.group.getObjectByName('sparks');
    assert.ok(Array.from(spark.geometry.attributes.position.array).every(Number.isFinite));
    assert.ok(Array.from(spark.geometry.attributes.strength.array).every((x) => x >= 0 && x <= 1));
  }
  effect.update(0); effect.update(0.56); assert.equal(effect.group.visible, true);
  assert.equal(pulseState(PULSE.impact).phase, 'impact');
  assert.throws(() => effect.update(NaN), /finite/);
  assert.throws(() => effect.setLayer('missing', true), /Unknown/);
  effect.dispose();
});

test('dispose releases every owned geometry/material exactly once and detaches the effect', () => {
  const scene = new Group();
  for (let i = 0; i < 30; i++) {
    const effect = createArcanePulse(); scene.add(effect.group); effect.update(0.6);
    let geometries = 0, materials = 0;
    effect.group.children.forEach((object) => {
      object.geometry.addEventListener('dispose', () => geometries++);
      object.material.addEventListener('dispose', () => materials++);
    });
    effect.dispose(); effect.dispose();
    assert.equal(geometries, 4); assert.equal(materials, 4);
    assert.equal(scene.children.length, 0);
    assert.throws(() => effect.update(0.6), /disposed/);
  }
});

test('flipbook clamps rather than wrapping and supports reverse seek with subframe blending', () => {
  const timing = { frames: 96, fps: 16 };
  assert.deepEqual(flipbookFrame(-1, timing), { first: 0, next: 1, mix: 0 });
  assert.deepEqual(flipbookFrame(0.03125, timing), { first: 0, next: 1, mix: 0.5 });
  assert.deepEqual(flipbookFrame(6, timing), { first: 95, next: 95, mix: 0 });
  assert.throws(() => flipbookFrame(1, { frames: 0, fps: 16 }), /positive/);
  assert.throws(() => flipbookFrame(Infinity, timing), /finite/);
});

test('soul instances share caller-owned media but preserve independent timing and cleanup', () => {
  const texture = new DataTexture(new Uint8Array(8 * 12 * 4), 8, 12);
  let textureDisposals = 0; texture.addEventListener('dispose', () => textureDisposals++);
  const a = createSoulFlame({ texture }), b = createSoulFlame({ texture });
  a.update(1); b.update(2);
  const frame = (effect) => effect.group.getObjectByName('body').material.uniforms.uFrames.value.toArray();
  assert.notDeepEqual(frame(a), frame(b));
  const previous = frame(a); a.update(4); a.update(1); assert.deepEqual(frame(a), previous);
  a.update(6); assert.equal(a.group.visible, false);
  a.update(0.5); assert.equal(a.group.visible, true);
  a.setLayer('body', false); a.update(1); assert.equal(a.group.getObjectByName('body').visible, false);
  a.dispose(); a.dispose(); assert.equal(textureDisposals, 0);
  b.update(1); b.dispose(); texture.dispose(); assert.equal(textureDisposals, 1);
  assert.throws(() => createSoulFlame({ texture, frames: 97 }), /atlas/);
});

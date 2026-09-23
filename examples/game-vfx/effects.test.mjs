import assert from 'node:assert/strict';
import { test } from 'node:test';
import * as THREE from 'three';
import { EFFECTS, createEffect } from './effects.js';

function glacier() {
  const scene = new THREE.Group(), texture = new THREE.DataTexture(new Uint8Array([128, 210, 255, 255]), 1, 1);
  const geometry = new THREE.BoxGeometry(), material = new THREE.MeshStandardMaterial({ map: texture });
  material.name = 'ice_interior';
  const mesh = new THREE.Mesh(geometry, material); mesh.name = 'fragment'; scene.add(mesh);
  return { scene, texture, geometry, material, animations: [new THREE.AnimationClip('ice_fall_break', 6, [
    new THREE.VectorKeyframeTrack('fragment.position', [0, 2, 6], [0, 5, 0, 0, 0.5, 0, 2, 0.5, 0]),
  ])] };
}

function snapshot(effect) {
  const objects = [];
  effect.group.traverse((object) => {
    objects.push({ name: object.name, visible: object.visible, position: object.position.toArray(),
      quaternion: object.quaternion.toArray(), scale: object.scale.toArray(),
      instances: object.instanceMatrix ? Array.from(object.instanceMatrix.array) : null,
      drawRange: object.geometry ? { ...object.geometry.drawRange } : null,
      particles: object.isPoints ? Object.fromEntries(Object.entries(object.geometry.attributes).map(([name, attribute]) => [name, Array.from(attribute.array)])) : null,
      opacity: object.material?.opacity ?? object.material?.uniforms?.uOpacity?.value ?? null,
    });
  });
  return objects;
}

test('all effects clean endpoints, replay and preserve absolute-time seeks', () => {
  const iceGltf = glacier();
  for (const definition of EFFECTS) {
    const effect = createEffect(definition.id, { iceGltf });
    const sample = definition.impact + .2;
    effect.update(sample); const expected = snapshot(effect);
    assert.equal(effect.group.visible, true);
    for (const time of [-1, 0, effect.duration, effect.duration + 4]) {
      effect.update(time); assert.equal(effect.group.visible, false);
    }
    effect.update(sample); assert.deepEqual(snapshot(effect), expected);
    effect.update(.1); effect.update(sample); assert.deepEqual(snapshot(effect), expected);
    assert.throws(() => effect.update(NaN), /finite/);
    assert.throws(() => effect.update(Infinity), /finite/);
    effect.dispose();
  }
});

test('each effect has finite spatial geometry and transforms throughout its life', () => {
  const iceGltf = glacier();
  for (const definition of EFFECTS) {
    const effect = createEffect(definition.id, { iceGltf });
    for (let i = 0; i <= 60; i++) {
      effect.update(effect.duration * i / 60);
      effect.group.updateMatrixWorld(true);
      effect.group.traverse((object) => {
        assert.ok(object.matrixWorld.elements.every(Number.isFinite), `${definition.id}/${object.name}`);
        if (object.instanceMatrix) assert.ok(Array.from(object.instanceMatrix.array).every(Number.isFinite));
        if (object.geometry?.attributes.position) assert.ok(Array.from(object.geometry.attributes.position.array).every(Number.isFinite));
      });
    }
    effect.dispose();
  }
});

test('seeds and instance state are independent, with layers affecting only their instance', () => {
  const iceGltf = glacier();
  for (const definition of EFFECTS) {
    const a = createEffect(definition.id, { iceGltf, seed: 7 });
    const b = createEffect(definition.id, { iceGltf, seed: 7 });
    const c = createEffect(definition.id, { iceGltf, seed: 19 });
    const time = definition.impact + .5;
    a.update(time); b.update(time); c.update(time);
    assert.deepEqual(snapshot(a), snapshot(b)); assert.notDeepEqual(snapshot(a), snapshot(c));
    const before = snapshot(b);
    a.setLayer('secondary', false); a.update(.4);
    assert.equal(a.group.getObjectByName('secondary').visible, false);
    assert.deepEqual(snapshot(b), before);
    a.setLayer('main', false); assert.equal(a.group.getObjectByName('main').visible, false);
    assert.throws(() => a.setLayer('wrong', true), /Unknown layer/);
    a.dispose(); b.update(time); b.dispose(); c.dispose();
  }
});

test('speed and scale change playback contract without changing canonical poses', () => {
  const a = createEffect('fire'), b = createEffect('fire', { scale: 2, speed: 2 });
  assert.equal(b.duration, a.duration / 2); assert.equal(b.impact, a.impact / 2);
  assert.deepEqual(b.group.scale.toArray(), [2, 2, 2]);
  a.update(1.7); b.update(.85);
  assert.deepEqual(snapshot(a).slice(1), snapshot(b).slice(1));
  a.dispose(); b.dispose();
  for (const options of [{ scale: 0 }, { speed: -1 }, { seed: NaN }]) assert.throws(() => createEffect('fire', options), /finite/);
});

test('all owned resources dispose once, caller geometry/materials/textures remain usable', () => {
  const iceGltf = glacier(), noiseTexture = new THREE.DataTexture(new Uint8Array(4), 1, 1);
  let sharedDisposals = 0;
  [iceGltf.geometry, iceGltf.material, iceGltf.texture, noiseTexture].forEach((r) => r.addEventListener('dispose', () => sharedDisposals++));
  const scene = new THREE.Group();
  for (const definition of EFFECTS) {
    const effect = createEffect(definition.id, { iceGltf, noiseTexture }); scene.add(effect.group);
    const ownedResources = new Set();
    const instanceMeshes = [];
    effect.group.traverse((object) => {
      if (object.isInstancedMesh) { ownedResources.add(object); instanceMeshes.push(object); }
      if (object.geometry && object.geometry !== iceGltf.geometry) ownedResources.add(object.geometry);
      (Array.isArray(object.material) ? object.material : [object.material]).filter(Boolean).forEach((r) => ownedResources.add(r));
    });
    assert.ok(instanceMeshes.length >= 1, `${definition.id} exposes owned particle instance buffers`);
    const counts = new Map();
    ownedResources.forEach((r) => { counts.set(r, 0); r.addEventListener('dispose', () => counts.set(r, counts.get(r) + 1)); });
    effect.dispose(); effect.dispose();
    counts.forEach((count, resource) => assert.equal(count, 1, `${definition.id}/${resource.name || resource.type} disposal`));
    assert.equal(scene.children.length, 0); assert.equal(sharedDisposals, 0);
    assert.throws(() => effect.update(1), /disposed/);
  }
  const again = createEffect('ice', { iceGltf }); again.update(2.2);
  assert.deepEqual(iceGltf.scene.children[0].position.toArray(), [0, 0, 0]); again.dispose();
});

test('opaque scene depth binding is optional, resizeable and remains caller owned', () => {
  const effect = createEffect('fire'), texture = new THREE.DepthTexture(800, 600);
  const uniforms = effect.group.getObjectByName('fire-volume').material.uniforms;
  assert.equal(uniforms.uHasSceneDepth.value, false);
  effect.setSceneDepth(texture, 800, 600);
  assert.equal(uniforms.uSceneDepth.value, texture); assert.equal(uniforms.uHasSceneDepth.value, true);
  assert.deepEqual(uniforms.uViewport.value.toArray(), [800, 600]);
  effect.setSceneDepth(texture, 1200, 800); assert.deepEqual(uniforms.uViewport.value.toArray(), [1200, 800]);
  assert.throws(() => effect.setSceneDepth(texture, 0, 600), /positive finite/);
  effect.setSceneDepth(null); assert.equal(uniforms.uHasSceneDepth.value, false);
  effect.setSceneDepth(texture, 800, 600);
  let disposals = 0; texture.addEventListener('dispose', () => disposals++);
  effect.dispose(); assert.equal(disposals, 0);
  assert.throws(() => effect.setSceneDepth(texture, 800, 600), /disposed/);
  texture.dispose(); assert.equal(disposals, 1);
});

test('Blender supplied paths are used verbatim and malformed paths are rejected', () => {
  const paths = [[[0, 8, 0], [1, 4, .8], [0, .2, 0]], [[1, 4, .8], [2, 2, -1]]];
  const effect = createEffect('lightning', { recipes: { lightning: { paths } } });
  assert.equal(effect.stats.blenderPaths, true); assert.equal(effect.stats.paths, 2);
  const bolt = effect.group.getObjectByName('lightning-core-0'); bolt.geometry.computeBoundingBox();
  assert.ok(bolt.geometry.boundingBox.max.y > 7.99);
  assert.ok(bolt.geometry.boundingBox.max.x > .9);
  effect.dispose();
  for (const malformed of [[], [[1, 2]], [[[0, 0, 0], [0, Infinity, 0]]]]) {
    assert.throws(() => createEffect('lightning', { recipes: { lightning: { paths: malformed } } }), /Invalid lightning/);
  }
  const withRoles = createEffect('lightning', { recipes: { lightning: { paths, roles: ['trunk', 'ground'] } } });
  const groundPaths = [];
  withRoles.group.traverse((o) => { if (o.name.startsWith('lightning-ground-')) groundPaths.push(o); });
  assert.equal(groundPaths.length, 1); assert.equal(groundPaths[0].parent.name, 'secondary');
  withRoles.dispose();
  assert.throws(() => createEffect('lightning', { recipes: { lightning: { paths, roles: ['trunk'] } } }), /Invalid lightning roles/);
  assert.throws(() => createEffect('ice'), /generated glacier/);
  assert.throws(() => createEffect('unknown'), /Unknown effect/);
});

test('each ice contact drives its own response at the source collision pose', () => {
  const input = glacier(), effect = createEffect('ice', { iceGltf: input });
  const events = effect.stats.events;
  assert.equal(events.length, 3);
  assert.equal(new Set(events.map((e) => e.time)).size, 3);
  for (const event of events) {
    const group = effect.group.getObjectByName(event.id);
    assert.deepEqual(group.position.toArray(), event.position);
    effect.update(event.time - .001); assert.equal(group.visible, false);
    effect.update(event.time + .06); assert.equal(group.visible, true);
  }
  effect.update(events[0].time + .06);
  assert.equal(effect.group.getObjectByName(events[0].id).visible, true);
  assert.equal(effect.group.getObjectByName(events[1].id).visible, false);
  assert.equal(effect.group.getObjectByName(events[2].id).visible, false);
  for (const [i, event] of events.entries()) {
    effect.update(event.time);
    const sourcePose = effect.group.getObjectByName(`ice-body-${i}`).children[0].position;
    assert.ok(Math.abs(sourcePose.x - (event.sourceImpact - 2) * .5) < 1e-5);
  }
  effect.update(events[0].cleanupEnd + .03);
  assert.equal(effect.group.getObjectByName('ice-mass-0').scale.x, 0);
  assert.ok(effect.group.getObjectByName('ice-mass-2').scale.x > 0);
  effect.update(2.55); const expected = snapshot(effect);
  effect.update(4.8); effect.update(2.55); assert.deepEqual(snapshot(effect), expected);
  effect.dispose();
});

test('ice event seconds follow playback speed while source time and local positions are preserved', () => {
  const input = glacier();
  const normal = createEffect('ice', { iceGltf: input });
  const fast = createEffect('ice', { iceGltf: input, speed: 2, scale: 3 });
  const original = structuredClone(normal.stats.events);
  const fastEvents = structuredClone(fast.stats.events);
  for (const [i, event] of fast.stats.events.entries()) {
    assert.equal(event.time, original[i].time / 2);
    assert.equal(event.cleanupEnd, original[i].cleanupEnd / 2);
    assert.equal(event.sourceImpact, original[i].sourceImpact);
    assert.deepEqual(event.position, original[i].position);
    const response = fast.group.getObjectByName(event.id);
    assert.deepEqual(response.position.toArray(), event.position);
    fast.update(event.time - .001); assert.equal(response.visible, false);
    fast.update(event.time + .025); assert.equal(response.visible, true);
    fast.update(event.time);
    const sourcePose = fast.group.getObjectByName(`ice-body-${i}`).children[0].position;
    assert.ok(Math.abs(sourcePose.x - (event.sourceImpact - 2) * .5) < 1e-5);
  }
  fast.update(fastEvents[0].cleanupEnd + .015);
  assert.equal(fast.group.getObjectByName('ice-mass-0').scale.x, 0);
  assert.ok(fast.group.getObjectByName('ice-mass-2').scale.x > 0);
  // Consumers may annotate their instance's metadata without changing another
  // effect or the animation's independently authored contact coordinates.
  fast.stats.events[1].time = 99;
  fast.stats.events[1].sourceImpact = 99;
  fast.stats.events[1].position[0] = 99;
  assert.deepEqual(normal.stats.events, original);
  assert.deepEqual(fast.group.getObjectByName(fastEvents[1].id).position.toArray(), fastEvents[1].position);
  fast.update(fastEvents[1].time + .025);
  assert.equal(fast.group.getObjectByName(fastEvents[1].id).visible, true);
  const again = createEffect('ice', { iceGltf: input, speed: 2 });
  assert.deepEqual(again.stats.events, fastEvents);
  normal.dispose(); fast.dispose(); again.dispose();
});

test('lightning events stay synchronized with leader, contact and restrike at double speed', () => {
  const normal = createEffect('lightning'), fast = createEffect('lightning', { speed: 2 });
  for (const event of fast.stats.events) {
    const canonical = normal.stats.events.find((e) => e.id === event.id);
    assert.equal(event.time, canonical.time / 2);
    normal.update(canonical.time + .06); fast.update(event.time + .03);
    assert.deepEqual(snapshot(fast), snapshot(normal));
  }
  const contact = fast.stats.events.find((e) => e.id === 'contact');
  const roots = [];
  fast.group.traverse((o) => { if (o.name.startsWith('lightning-ground-')) roots.push(o); });
  fast.update(contact.time - .03); assert.ok(roots.every((r) => !r.visible));
  fast.update(contact.time + .03); assert.ok(roots.some((r) => r.visible && r.geometry.drawRange.count > 0));
  assert.ok(fast.group.getObjectByName('lightning-core-0').visible);
  fast.stats.events[0].time = 99;
  assert.equal(normal.stats.events[0].time, 1.6);
  normal.dispose(); fast.dispose();
});

test('lightning reaches its contact before ground branches and separates late current', () => {
  const effect = createEffect('lightning');
  const core = effect.group.getObjectByName('lightning-core-0');
  const roots = [];
  effect.group.traverse((o) => { if (o.name.startsWith('lightning-ground-')) roots.push(o); });
  effect.update(1.65);
  assert.ok(core.geometry.drawRange.count > 0 && core.geometry.drawRange.count < core.geometry.index.count);
  assert.ok(roots.every((r) => !r.visible));
  effect.update(1.78);
  assert.equal(core.geometry.drawRange.count, core.geometry.index.count);
  assert.ok(roots.some((r) => r.visible && r.geometry.drawRange.count > 0));
  effect.update(2.9);
  assert.equal(core.visible, false);
  const lingering = [];
  effect.group.traverse((o) => { if (o.name.startsWith('lightning-residual-') && o.visible) lingering.push(o); });
  assert.ok(lingering.length > 0);
  effect.dispose();
});

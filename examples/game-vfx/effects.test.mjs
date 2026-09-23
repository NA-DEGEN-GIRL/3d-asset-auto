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
    assert.equal(instanceMeshes.length, 1, `${definition.id} has one owned particle instance buffer`);
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

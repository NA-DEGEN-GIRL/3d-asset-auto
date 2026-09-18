import * as THREE from 'three';

// The caller owns the loaded GLB geometry/textures. Each instance owns its mixer,
// materials and supporting particles; seeking uses absolute time, never integration.
export function createIceFall({ gltf, events, seed = 17 }) {
  const group = new THREE.Group();
  const body = gltf.scene.clone(true);
  const ownedMaterials = new Map();
  body.traverse((object) => {
    if (!object.isMesh) return;
    object.castShadow = true; object.receiveShadow = true;
    const clone = (source) => {
      if (!ownedMaterials.has(source)) {
        const material = source.name === 'ice_interior'
          ? new THREE.MeshPhysicalMaterial({ name: 'ice_interior_web', color: '#b6e2f5', map: source.map,
            roughness: 0.2, metalness: 0.02, clearcoat: 0.65, clearcoatRoughness: 0.14,
            transmission: 0.18, thickness: 0.35, ior: 1.31,
            attenuationColor: new THREE.Color('#68b7d8'), attenuationDistance: 0.7 })
          : source.clone();
        material.roughness = Math.min(material.roughness ?? 0.4, 0.42);
        material.envMapIntensity = 0.8;
        ownedMaterials.set(source, material);
      }
      return ownedMaterials.get(source);
    };
    object.material = Array.isArray(object.material) ? object.material.map(clone) : clone(object.material);
  });
  group.add(body);
  const clip = gltf.animations.find((item) => item.name === events.clip);
  if (!clip) throw new Error(`Missing ice animation: ${events.clip}`);
  const mixer = new THREE.AnimationMixer(body);
  const action = mixer.clipAction(clip);
  action.setLoop(THREE.LoopOnce, 1); action.clampWhenFinished = true; action.play();
  const duration = events.duration;
  const impact = events.impact;
  const count = 480;
  const positions = new Float32Array(count * 3);
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  const random = (index) => {
    const value = Math.sin((index + seed * 7.13) * 127.1) * 43758.5453;
    return value - Math.floor(value);
  };
  const particles = Array.from({ length: count }, (_, i) => ({
    angle: random(i * 5) * Math.PI * 2, speed: 1.6 + random(i * 5 + 1) * 3.6,
    rise: 0.5 + random(i * 5 + 2) * 2.0, delay: random(i * 5 + 3) * 0.09,
    height: random(i * 5 + 4) * 0.24,
  }));
  const dustMaterial = new THREE.PointsMaterial({ color: '#dbf7ff', size: 0.045,
    transparent: true, opacity: 0, depthWrite: false, sizeAttenuation: true });
  dustMaterial.onBeforeCompile = (shader) => {
    shader.fragmentShader = shader.fragmentShader.replace('void main() {',
      'void main() { if (length(gl_PointCoord - vec2(0.5)) > 0.5) discard;');
  };
  const dust = new THREE.Points(geometry, dustMaterial);
  dust.frustumCulled = false;
  group.add(dust);
  const ring = new THREE.Mesh(new THREE.RingGeometry(0.88, 1, 80),
    new THREE.MeshBasicMaterial({ color: '#b5e5ef', transparent: true, opacity: 0,
      depthWrite: false, side: THREE.DoubleSide }));
  ring.rotation.x = -Math.PI / 2; ring.position.y = 0.018;
  group.add(ring);
  const layers = { body: true, dust: true, ring: true };
  let disposed = false;
  function update(seconds) {
    if (disposed) throw new Error('Ice effect is disposed');
    if (!Number.isFinite(seconds)) throw new Error('Time must be finite');
    const t = Math.max(0, Math.min(duration, seconds));
    group.visible = seconds > 0;
    action.paused = false; action.enabled = true;
    mixer.setTime(t + (events.start_offset ?? 0));
    body.visible = layers.body;
    const elapsed = t - impact;
    const dustAlpha = elapsed > 0 ? Math.min(1, elapsed * 25) * Math.exp(-elapsed * 2.2) : 0;
    dustMaterial.opacity = 0.65 * dustAlpha;
    dust.visible = layers.dust && dustAlpha > 0.005;
    particles.forEach((p, i) => {
      const age = Math.max(0, elapsed - p.delay);
      const travel = p.speed * (1 - Math.exp(-age * 1.8)) / 1.8;
      positions[i * 3] = Math.cos(p.angle) * travel;
      positions[i * 3 + 1] = Math.max(0.025, p.height + p.rise * age - 2.8 * age * age);
      positions[i * 3 + 2] = Math.sin(p.angle) * travel;
    });
    geometry.attributes.position.needsUpdate = true;
    ring.visible = layers.ring && elapsed >= 0 && elapsed < 0.55;
    ring.scale.setScalar(0.5 + Math.max(0, elapsed) * 4.5);
    ring.material.opacity = Math.max(0, 0.32 * (1 - elapsed / 0.55));
    return { phase: t < 0.35 ? 'ready' : t < impact ? 'fall' : t < impact + 0.2 ? 'impact'
      : t < impact + 1.6 ? 'scatter' : 'settle' };
  }
  update(0);
  return { group, duration, impact, update,
    setLayer(name, visible) { if (name in layers) layers[name] = Boolean(visible); },
    dispose() {
      if (disposed) return;
      disposed = true;
      group.removeFromParent(); mixer.stopAllAction(); mixer.uncacheRoot(body);
      for (const material of ownedMaterials.values()) material.dispose();
      geometry.dispose(); dustMaterial.dispose(); ring.geometry.dispose(); ring.material.dispose();
    },
  };
}

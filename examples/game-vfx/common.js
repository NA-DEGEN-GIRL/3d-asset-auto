import * as THREE from 'three';

const clamp = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x));
const smooth = (a, b, x) => { const t = clamp((x - a) / (b - a)); return t * t * (3 - 2 * t); };
const random = (seed, i) => { const n = Math.sin((i + seed * 13.719) * 127.1) * 43758.5453; return n - Math.floor(n); };
const TAU = Math.PI * 2;

function resources() {
  const geometry = new Set(), material = new Set(), objects = new Set();
  return {
    geometry(g) { geometry.add(g); return g; }, material(m) { material.add(m); return m; },
    object(o) { objects.add(o); return o; },
    dispose() {
      // InstancedMesh owns GPU instance buffers independently of its geometry.
      objects.forEach((o) => o.dispose()); geometry.forEach((g) => g.dispose()); material.forEach((m) => m.dispose());
      objects.clear(); geometry.clear(); material.clear();
    },
  };
}

function emitted(color, energy = 1) { return new THREE.Color(color).multiplyScalar(energy); }
function glowMaterial(owned, color, energy = 1, opacity = 1) {
  return owned.material(new THREE.MeshBasicMaterial({ color: emitted(color, energy),
    transparent: true, opacity, blending: THREE.AdditiveBlending, depthWrite: false,
    toneMapped: false, side: THREE.DoubleSide }));
}

// Broken bands read as energy rather than a uniformly filled disk. Noise in
// angular space keeps them coherent from every camera angle.
function makeRing(owned, color, energy, radius = 1, width = 0.075) {
  const material = owned.material(new THREE.ShaderMaterial({
    uniforms: { uColor: { value: emitted(color, energy) }, uOpacity: { value: 0 }, uTime: { value: 0 } },
    vertexShader: 'varying vec2 vUv; void main(){vUv=uv;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.);}',
    fragmentShader: `varying vec2 vUv; uniform vec3 uColor; uniform float uOpacity; uniform float uTime;
      void main(){ vec2 p=vUv-.5; float a=atan(p.y,p.x); float n=.55+.45*sin(a*11.+sin(a*7.-uTime*2.));
      float r=length(p)*2.; float edge=smoothstep(.82,.9,r)*(1.-smoothstep(.96,1.,r));
      gl_FragColor=vec4(uColor,edge*n*uOpacity); }`,
    transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide,
    toneMapped: false,
  }));
  const ring = new THREE.Mesh(owned.geometry(new THREE.RingGeometry(radius * (1 - width), radius, 96)), material);
  // RingGeometry UV follows XY position (the shader sees actual radius).
  ring.rotation.x = -Math.PI / 2; ring.position.y = 0.025;
  return ring;
}

function createSparks(owned, { count = 180, color = '#ffbd6b', seed, mode = 'fire', energy = 3.5 }) {
  const geometry = owned.geometry(new THREE.OctahedronGeometry(1, 0));
  const material = glowMaterial(owned, color, energy);
  const mesh = owned.object(new THREE.InstancedMesh(geometry, material, count));
  mesh.name = `${mode}-sparks`; mesh.frustumCulled = false;
  const data = Array.from({ length: count }, (_, i) => ({
    a: random(seed, i * 6) * TAU, radius: random(seed, i * 6 + 1),
    v: random(seed, i * 6 + 2), delay: random(seed, i * 6 + 3),
    life: 0.6 + random(seed, i * 6 + 4) * 1.2, size: 0.012 + random(seed, i * 6 + 5) * 0.024,
  }));
  const dummy = new THREE.Object3D();
  function update(time, impact) {
    data.forEach((p, i) => {
      const age = time - impact - p.delay * (mode === 'fire' ? 1.0 : 0.23);
      const alive = age > 0 && age < p.life;
      const t = Math.max(0, age);
      if (mode === 'fire') {
        const r = 0.4 + p.radius * 0.7 + t * (0.45 + p.v);
        dummy.position.set(Math.cos(p.a + t * 0.7) * r, 0.3 + (2.4 + p.v * 3) * t - 1.25 * t * t,
          Math.sin(p.a + t * 0.7) * r);
      } else {
        const r = (1.8 + p.radius * 3.3) * t / (1 + t * 0.9);
        dummy.position.set(Math.cos(p.a) * r, Math.max(0.035, 0.08 + (1.4 + p.v * 2.2) * t - 3.2 * t * t), Math.sin(p.a) * r);
      }
      const size = alive ? p.size * Math.sin(Math.PI * clamp(age / p.life)) : 0;
      dummy.scale.set(size, size * (mode === 'fire' ? 2.6 : 1.7), size);
      dummy.rotation.set(p.a + t, p.a, t * 2); dummy.updateMatrix(); mesh.setMatrixAt(i, dummy.matrix);
    });
    mesh.instanceMatrix.needsUpdate = true;
  }
  return { mesh, update };
}


export { clamp, smooth, random, TAU, resources, emitted, glowMaterial, makeRing, createSparks };

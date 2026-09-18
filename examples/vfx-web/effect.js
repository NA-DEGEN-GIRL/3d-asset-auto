import * as THREE from 'three';

// Absolute local seconds: no accumulated simulation state, so seeking is repeatable.
export const PULSE = Object.freeze({ duration: 2.4, impact: 0.46, radius: 3.5 });
const clamp = (v) => Math.max(0, Math.min(1, v));
const smooth = (a, b, t) => { const x = clamp((t - a) / (b - a)); return x * x * (3 - 2 * x); };

export function pulseState(time) {
  if (!Number.isFinite(time)) throw new TypeError('Time must be finite seconds');
  const age = Math.max(0, time - PULSE.impact);
  const active = time > 0 && time < PULSE.duration;
  return {
    active, age,
    phase: time <= 0 ? 'ready' : time < PULSE.impact ? 'charge' : time < 0.78 ? 'impact'
      : time < 1.65 ? 'expand' : time < PULSE.duration ? 'fade' : 'finished',
    charge: smooth(0, 0.12, time) * (1 - smooth(PULSE.impact, 0.68, time)),
    burst: smooth(PULSE.impact, PULSE.impact + 0.035, time) * (1 - smooth(0.52, 1.3, time)),
    radius: 0.45 + (PULSE.radius - 0.45) * (1 - Math.exp(-2.5 * age)),
    opacity: active ? smooth(0, 0.12, time) * (1 - smooth(1.25, PULSE.duration, time)) : 0,
  };
}

const vertex = `varying vec2 vUv;
void main() { vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`;
const ringFragment = `
uniform float uTime, uRadius, uOpacity, uCharge;
uniform vec3 uColor;
varying vec2 vUv;
float band(float r, float target, float width) { return exp(-pow((r-target)/width, 2.0)); }
void main() {
  vec2 p = (vUv - 0.5) * 8.0;
  float r = length(p), a = atan(p.y, p.x);
  float ripple = sin(a*15.0 + uTime*7.0)*0.022 + sin(a*29.0-uTime*9.0)*0.012;
  float release = smoothstep(0.46, 0.51, uTime);
  float outer = band(r+ripple, uRadius, 0.038);
  float glow = band(r, uRadius, 0.19)*0.24;
  float echo = band(r-ripple, uRadius*0.80, 0.019)*0.55;
  float dash = smoothstep(0.6, 0.8, sin(a*32.0+uTime*1.4));
  float glyph = band(r, 0.90, 0.05)*dash + band(r, 0.72, 0.018);
  float charge = (glyph + band(r, 1.08, 0.018)*0.65)*uCharge;
  float body = (outer + glow + echo)*release + charge;
  float alpha = min(0.97, body*uOpacity);
  if (alpha < 0.002) discard;
  gl_FragColor = vec4(mix(uColor, vec3(0.8,1.0,1.0), min(0.6, outer*0.5)), alpha);
  #include <colorspace_fragment>
}`;
const crownFragment = `
uniform float uTime, uOpacity;
uniform vec3 uColor;
varying vec2 vUv;
void main() {
  float strands = pow(max(0.0, sin(vUv.x*150.796 + vUv.y*4.0 + uTime*5.0)), 12.0);
  float edges = exp(-vUv.y*9.0);
  float a = (edges*0.42 + strands*0.60*pow(1.0-vUv.y, 2.0))*uOpacity;
  if (a < 0.002) discard;
  gl_FragColor = vec4(uColor, a);
  #include <colorspace_fragment>
}`;
const orbVertex = `varying vec3 vNormal, vView;
void main(){ vec4 p = modelViewMatrix * vec4(position,1.0);
vNormal = normalize(normalMatrix*normal); vView = normalize(-p.xyz);
gl_Position = projectionMatrix*p; }`;
const orbFragment = `uniform vec3 uColor; uniform float uOpacity;
varying vec3 vNormal, vView;
void main(){ float rim=pow(1.0-abs(dot(normalize(vNormal),normalize(vView))),2.2);
gl_FragColor=vec4(mix(uColor,vec3(0.85,1.0,1.0),rim),uOpacity*(0.18+rim*0.8));
#include <colorspace_fragment>
}`;
const sparkVertex = `attribute float strength; varying float vStrength;
void main(){ vStrength=strength; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0); }`;
const sparkFragment = `uniform vec3 uColor; varying float vStrength;
void main(){ if(vStrength<0.002)discard; gl_FragColor=vec4(uColor,vStrength);
#include <colorspace_fragment>
}`;

function seeded(seed) {
  let state = seed >>> 0;
  return () => { state = (Math.imul(state, 1664525) + 1013904223) >>> 0; return state / 4294967296; };
}

export function createArcanePulse({ seed = 17, color = '#57eadb' } = {}) {
  const group = new THREE.Group();
  group.name = 'ArcanePulse';
  const tint = new THREE.Color(color);
  const materials = [];
  const geometries = [];
  const uniform = () => ({ uTime: { value: 0 }, uRadius: { value: 0 },
    uOpacity: { value: 0 }, uCharge: { value: 0 }, uColor: { value: tint.clone() } });
  function shader(fragmentShader, vertexShader = vertex) {
    const material = new THREE.ShaderMaterial({ uniforms: uniform(), vertexShader, fragmentShader,
      transparent: true, depthWrite: false, side: THREE.DoubleSide, toneMapped: false });
    materials.push(material);
    return material;
  }
  function mesh(name, geometry, material) {
    geometries.push(geometry);
    const object = new THREE.Mesh(geometry, material);
    object.name = name;
    group.add(object);
    return object;
  }
  const ring = mesh('ring', new THREE.PlaneGeometry(8, 8), shader(ringFragment));
  ring.rotation.x = -Math.PI / 2;
  ring.position.y = 0.035;
  const crown = mesh('crown', new THREE.CylinderGeometry(1, 1, 1, 96, 1, true), shader(crownFragment));
  const core = mesh('core', new THREE.SphereGeometry(1, 32, 24), shader(orbFragment, orbVertex));
  core.position.y = 0.65;

  const random = seeded(seed);
  const particles = Array.from({ length: 80 }, () => ({
    angle: random() * Math.PI * 2, speed: 1.0 + random() * 2.8,
    lift: 0.6 + random() * 3.8, delay: random() * 0.13, life: 0.65 + random() * 0.9,
  }));
  const segments = 5;
  const positions = new Float32Array(particles.length * segments * 2 * 3);
  const strengths = new Float32Array(particles.length * segments * 2);
  const sparksGeometry = new THREE.BufferGeometry();
  sparksGeometry.setAttribute('position', new THREE.BufferAttribute(positions, 3).setUsage(THREE.DynamicDrawUsage));
  sparksGeometry.setAttribute('strength', new THREE.BufferAttribute(strengths, 1).setUsage(THREE.DynamicDrawUsage));
  geometries.push(sparksGeometry);
  const sparks = new THREE.LineSegments(sparksGeometry, shader(sparkFragment, sparkVertex));
  sparks.name = 'sparks';
  // Positions change on seek; do not use a stale geometry bounding sphere.
  sparks.frustumCulled = false;
  group.add(sparks);
  const layers = { ring: true, crown: true, core: true, sparks: true };
  let disposed = false;

  function update(time) {
    if (disposed) throw new Error('Effect has been disposed');
    const state = pulseState(time);
    group.visible = state.active;
    if (!state.active) return state;
    for (const material of materials) {
      const u = material.uniforms;
      u.uTime.value = time; u.uRadius.value = state.radius;
      u.uOpacity.value = state.opacity; u.uCharge.value = state.charge;
    }
    core.scale.setScalar(0.08 + state.charge * 0.24 + state.burst * 0.55);
    core.material.uniforms.uOpacity.value = Math.max(state.charge * 0.8, state.burst) * state.opacity;
    crown.scale.set(state.radius, 0.05 + state.burst * 0.8, state.radius);
    crown.position.y = crown.scale.y / 2 + 0.04;
    crown.material.uniforms.uOpacity.value = time > PULSE.impact ? state.opacity * 0.75 : 0;
    for (let i = 0; i < particles.length; i++) {
      const p = particles[i];
      const age = time - PULSE.impact - p.delay;
      for (let j = 0; j < segments * 2; j++) {
        const step = Math.floor(j / 2) + j % 2;
        const t = Math.max(0, age - step * 0.018);
        const radius = 0.16 + p.speed * t * Math.exp(-0.28 * t);
        const idx = i * segments * 2 + j;
        positions[idx * 3] = Math.cos(p.angle) * radius;
        positions[idx * 3 + 1] = Math.max(0.055, 0.18 + p.lift * t - 2.4 * t * t);
        positions[idx * 3 + 2] = Math.sin(p.angle) * radius;
        strengths[idx] = age > 0 && age < p.life && age >= step * 0.018
          ? (1 - step / segments) * (1 - smooth(p.life * 0.4, p.life, age)) * state.opacity : 0;
      }
    }
    sparksGeometry.attributes.position.needsUpdate = true;
    sparksGeometry.attributes.strength.needsUpdate = true;
    for (const child of group.children) child.visible = layers[child.name];
    return state;
  }
  function setLayer(name, visible) {
    if (!Object.hasOwn(layers, name)) throw new Error(`Unknown effect layer: ${name}`);
    layers[name] = Boolean(visible);
    group.getObjectByName(name).visible = layers[name];
  }
  function dispose() {
    if (disposed) return;
    group.removeFromParent();
    geometries.forEach((geometry) => geometry.dispose());
    materials.forEach((material) => material.dispose());
    group.clear();
    disposed = true;
  }
  update(0);
  return { group, update, setLayer, dispose, duration: PULSE.duration, impact: PULSE.impact };
}

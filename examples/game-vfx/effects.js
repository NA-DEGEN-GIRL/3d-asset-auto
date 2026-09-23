import * as THREE from 'three';

// The main effects occupy world space. Textures provide density/detail; none of
// the main effects is a camera-facing video. Time is absolute and seekable.
export const EFFECTS = [
  { id: 'fire', name: 'Cinder Bloom', subtitle: '화염 분출', duration: 4.8, impact: 1.25,
    color: '#ff8647', description: '응축된 열기가 지면에서 솟아오르고, 입체 화염과 불티가 퍼집니다.',
    moments: [{ label: '응축', time: 0.7 }, { label: '분출', time: 1.65 }, { label: '불기둥', time: 2.45 }, { label: '잔열', time: 3.65 }] },
  { id: 'ice', name: 'Glacier Barrage', subtitle: '빙하 연쇄 낙하', duration: 5.4, impact: 1.9,
    color: '#8adfff', description: '생성한 얼음 모델이 시간차로 떨어져 실제 입체 파편으로 부서집니다.',
    moments: [{ label: '낙하', time: 1.1 }, { label: '충돌', time: 2.05 }, { label: '연쇄', time: 2.5 }, { label: '서리', time: 3.55 }] },
  { id: 'lightning', name: 'Storm Verdict', subtitle: '분기 낙뢰', duration: 4.4, impact: 1.6,
    color: '#ada7ff', description: '상공에서 내려오는 분기 전류가 지면에 닿아 여러 방향으로 흩어집니다.',
    moments: [{ label: '예고', time: 1 }, { label: '낙뢰', time: 1.7 }, { label: '분기', time: 2.15 }, { label: '잔류', time: 2.9 }] },
];

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

const FIRE_VERTEX = `varying vec3 vLocal; void main(){ vLocal=position; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.); }`;
const FIRE_FRAGMENT = `
  precision highp float;
  varying vec3 vLocal;
  uniform sampler2D uNoise;
  uniform bool uHasNoise;
  uniform vec3 uCamera;
  uniform vec3 uOrthoDirection;
  uniform bool uOrthographic;
  uniform sampler2D uSceneDepth;
  uniform bool uHasSceneDepth;
  uniform vec2 uViewport;
  uniform mat4 uLocalToClip;
  uniform float uTime;
  uniform float uOpacity;
  uniform float uSeed;
  float hash(vec3 p){return fract(sin(dot(p,vec3(127.1,311.7,74.7)))*43758.5453);}
  float fallbackNoise(vec3 p){
    vec3 i=floor(p),f=fract(p); f=f*f*(3.-2.*f);
    return mix(mix(mix(hash(i),hash(i+vec3(1,0,0)),f.x),mix(hash(i+vec3(0,1,0)),hash(i+vec3(1,1,0)),f.x),f.y),
      mix(mix(hash(i+vec3(0,0,1)),hash(i+vec3(1,0,1)),f.x),mix(hash(i+vec3(0,1,1)),hash(i+vec3(1,1,1)),f.x),f.y),f.z);
  }
  vec3 slice(vec2 p,float z){
    vec2 tile=vec2(mod(z,8.),floor(z/8.));
    vec2 q=fract(p)*64.-.5;
    // Interior samples use hardware bilinear filtering. Only boundary samples
    // wrap their four texels inside this slice rather than bleeding into a tile.
    if(all(greaterThanEqual(q,vec2(0.)))&&all(lessThan(q,vec2(63.))))
      return texture2D(uNoise,(tile*64.+q+.5)/512.).rgb;
    vec2 b=floor(q),f=fract(q);
    vec3 a=texture2D(uNoise,(tile*64.+mod(b,64.)+.5)/512.).rgb;
    vec3 c=texture2D(uNoise,(tile*64.+mod(b+vec2(1.,0.),64.)+.5)/512.).rgb;
    vec3 d=texture2D(uNoise,(tile*64.+mod(b+vec2(0.,1.),64.)+.5)/512.).rgb;
    vec3 e=texture2D(uNoise,(tile*64.+mod(b+vec2(1.),64.)+.5)/512.).rgb;
    return mix(mix(a,c,f.x),mix(d,e,f.x),f.y);
  }
  vec3 densityNoise(vec3 p){
    if(!uHasNoise)return vec3(fallbackNoise(p*6.),fallbackNoise(p*15.),fallbackNoise(p*30.));
    vec3 q=fract(p); float z=q.z*64.;
    return mix(slice(q.xy,floor(z)),slice(q.xy,mod(floor(z)+1.,64.)),fract(z));
  }
  vec2 field(vec3 p){
    float h=clamp((p.y+.96)/1.92,0.,1.);
    // Advected, stretched noise tears holes through a broad plume; the previous
    // single analytic helix produced a smooth noodle even with surface noise.
    float turn=h*5.5-uTime*.55;
    mat2 rotation=mat2(cos(turn),-sin(turn),sin(turn),cos(turn));
    vec2 xy=rotation*p.xz;
    vec3 n=densityNoise(vec3(xy.x*.95+uSeed,p.y*.19-uTime*.22,xy.y*.95));
    vec3 detail=densityNoise(vec3(xy.x*1.55+uSeed+.19,p.y*.30-uTime*.39,xy.y*1.55+.27));
    vec2 sway=vec2(sin(h*9.-uTime*.9),cos(h*8.-uTime*.6))*.20*h;
    vec2 q=p.xz+sway+vec2(n.r-.5,n.g-.5)*.38;
    float radius=.78*pow(max(0.,1.-h),.60)+.025;
    float lobes=sin(atan(q.y,q.x)*3.+h*12.-uTime*1.3)*.12*(1.-h);
    float body=(radius+lobes-length(q))*2.5+(n.g-.49)*2.5+(detail.g-.5)*1.05;
    float tears=smoothstep(.35,.63,detail.r)*smoothstep(.31,.61,n.g);
    float vertical=smoothstep(0.,.055,h)*(1.-smoothstep(.88,1.,h));
    float density=max(0.,body)*tears*vertical*2.1;
    float heat=clamp(body*.72+(detail.b-.5)*.95-h*.16,0.,1.);
    return vec2(density,heat);
  }
  vec3 fireColor(float heat){
    vec3 red=vec3(1.15,.018,.002),orange=vec3(2.6,.29,.008),yellow=vec3(3.3,1.65,.24);
    return mix(mix(red,orange,smoothstep(.02,.48,heat)),yellow,smoothstep(.53,.98,heat));
  }
  void main(){
    vec3 dir=uOrthographic?normalize(uOrthoDirection):normalize(vLocal-uCamera);
    vec3 pos=vLocal+dir*.002;
    vec3 inv=1./(dir+vec3(.000001));
    vec3 toFar=max((-vec3(1.)-pos)*inv,(vec3(1.)-pos)*inv);
    float distance=min(toFar.x,min(toFar.y,toFar.z));
    float ds=max(0.,distance)/64.;
    float opaqueDepth=uHasSceneDepth?texture2D(uSceneDepth,gl_FragCoord.xy/uViewport).x:1.;
    vec3 sum=vec3(0.); float alpha=0.;
    for(int i=0;i<64;i++){
      vec4 clipPosition=uLocalToClip*vec4(pos,1.);
      float sampleDepth=clipPosition.z/clipPosition.w*.5+.5;
      if(uHasSceneDepth&&sampleDepth>opaqueDepth+.000002)break;
      vec2 sampleValue=field(pos); float a=1.-exp(-sampleValue.x*ds*3.3);
      sum+=(1.-alpha)*a*fireColor(sampleValue.y); alpha+=(1.-alpha)*a;
      pos+=dir*ds; if(alpha>.985)break;
    }
    if(alpha<.005)discard;
    gl_FragColor=vec4(sum/max(alpha,.0001),alpha*uOpacity);
  }
`;

function createFire(owned, { noiseTexture, seed }) {
  const main = new THREE.Group(), secondary = new THREE.Group();
  const material = owned.material(new THREE.ShaderMaterial({
    uniforms: { uNoise: { value: noiseTexture ?? null }, uHasNoise: { value: Boolean(noiseTexture) },
      uCamera: { value: new THREE.Vector3() }, uOrthoDirection: { value: new THREE.Vector3() },
      uSceneDepth: { value: null }, uHasSceneDepth: { value: false }, uViewport: { value: new THREE.Vector2(1, 1) },
      uLocalToClip: { value: new THREE.Matrix4() },
      uOrthographic: { value: false }, uTime: { value: 0 }, uOpacity: { value: 0 }, uSeed: { value: seed * .037 } },
    vertexShader: FIRE_VERTEX, fragmentShader: FIRE_FRAGMENT,
    transparent: true, depthWrite: false, side: THREE.FrontSide, toneMapped: false,
  }));
  const plume = new THREE.Mesh(owned.geometry(new THREE.BoxGeometry(2, 2, 2)), material);
  plume.name = 'fire-volume'; plume.renderOrder = 2; main.add(plume);
  const inverse = new THREE.Matrix4(), worldDirection = new THREE.Vector3();
  plume.onBeforeRender = (_renderer, _scene, camera) => {
    inverse.copy(plume.matrixWorld).invert();
    camera.getWorldPosition(material.uniforms.uCamera.value).applyMatrix4(inverse);
    camera.getWorldDirection(worldDirection);
    material.uniforms.uOrthoDirection.value.copy(worldDirection).transformDirection(inverse);
    material.uniforms.uOrthographic.value = Boolean(camera.isOrthographicCamera);
    material.uniforms.uLocalToClip.value.multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse).multiply(plume.matrixWorld);
  };
  const ring = makeRing(owned, '#ff7130', 2.8); ring.name = 'fire-shockwave'; secondary.add(ring);
  const charge = makeRing(owned, '#ff993a', 1.8); charge.name = 'fire-charge'; secondary.add(charge);
  const sparks = createSparks(owned, { count: 210, seed, mode: 'fire' }); secondary.add(sparks.mesh);
  const light = new THREE.PointLight('#ff7135', 0, 13, 2); light.position.y = 1.7; secondary.add(light);
  return { main, secondary,
    update(t) {
      const age = t - 1.25;
      const rise = smooth(-.18, .42, age);
      const fade = 1 - smooth(1.7, 3.35, age);
      const height = .65 + 5.4 * rise * (1 - smooth(2.1, 3.5, age) * .45);
      const width = .25 + 1.85 * rise * (1 - smooth(1.9, 3.4, age) * .55);
      plume.scale.set(width, height / 2, width); plume.position.y = height / 2 + .025;
      plume.visible = age > -.18 && fade > .001;
      material.uniforms.uTime.value = t; material.uniforms.uOpacity.value = rise * fade * .9;
      const ringAge = Math.max(0, age);
      ring.scale.setScalar(.35 + ringAge * 3.7); ring.visible = age > 0 && age < .95;
      ring.material.uniforms.uOpacity.value = .8 * (1 - smooth(.12, .95, ringAge)); ring.material.uniforms.uTime.value = t;
      charge.scale.setScalar(1.8 - smooth(.05, 1.15, t) * 1.25); charge.rotation.z = t * .6;
      charge.material.uniforms.uOpacity.value = smooth(.05, .45, t) * (1 - smooth(1.1, 1.42, t)) * .7;
      charge.material.uniforms.uTime.value = t;
      sparks.update(t, 1.3); light.intensity = 32 * rise * fade;
    }, setSceneDepth(texture, width, height) {
      if (texture == null) { material.uniforms.uHasSceneDepth.value = false; material.uniforms.uSceneDepth.value = null; return; }
      if (!texture.isTexture || ![width, height].every(Number.isFinite) || width <= 0 || height <= 0) {
        throw new Error('Scene depth requires a texture and positive finite viewport dimensions');
      }
      material.uniforms.uSceneDepth.value = texture; material.uniforms.uHasSceneDepth.value = true;
      material.uniforms.uViewport.value.set(width, height);
    }, stats: { representation: '3D raymarched density + spatial embers', volumeSteps: 64, sparks: 210,
      blenderDensityAtlas: Boolean(noiseTexture) } };
}

function polyline(points) {
  const curve = new THREE.CurvePath();
  for (let i = 1; i < points.length; i++) curve.add(new THREE.LineCurve3(new THREE.Vector3(...points[i - 1]), new THREE.Vector3(...points[i])));
  return curve;
}

function fallbackLightning(seed) {
  const main = Array.from({ length: 18 }, (_, i) => [i === 0 || i === 17 ? 0 : (random(seed, i) - .5) * .95,
    8 - i * 7.82 / 17, i === 0 || i === 17 ? 0 : (random(seed, i + 31) - .5) * .8]);
  const paths = [main];
  for (let b = 0; b < 7; b++) {
    const index = 4 + b, start = main[index], a = b * 2.4;
    paths.push(Array.from({ length: 6 }, (_, i) => {
      const t = i / 5;
      return [start[0] + Math.cos(a) * t * (1.2 + b * .14) + Math.sin(i * 9) * t * .13,
        start[1] - t * (1.3 + b * .08), start[2] + Math.sin(a) * t * 1.6];
    }));
  }
  return paths;
}

function bolt(owned, points, radius, color, energy) {
  const curve = polyline(points);
  return new THREE.Mesh(owned.geometry(new THREE.TubeGeometry(curve, Math.max(16, points.length * 2), radius, 5, false)),
    glowMaterial(owned, color, energy));
}

function createLightning(owned, { recipes, seed }) {
  const main = new THREE.Group(), secondary = new THREE.Group();
  const supplied = recipes?.lightning?.paths;
  if (supplied && (!Array.isArray(supplied) || supplied.length === 0 || supplied.some((p) => !Array.isArray(p) || p.length < 2
    || p.some((v) => !Array.isArray(v) || v.length !== 3 || !v.every(Number.isFinite))))) {
    throw new Error('Invalid lightning paths: finite 3D polylines required');
  }
  const paths = supplied ?? fallbackLightning(seed);
  const roles = recipes?.lightning?.roles;
  if (roles && (!Array.isArray(roles) || roles.length !== paths.length || roles.some((r) => !['trunk', 'branch', 'ground'].includes(r)))) {
    throw new Error('Invalid lightning roles: one trunk/branch/ground role per path required');
  }
  const roots = [];
  const bolts = paths.map((points, i) => {
    if (roles?.[i] === 'ground') {
      const root = bolt(owned, points, .022, '#9384ff', 3.2); root.name = `lightning-ground-${i}`;
      secondary.add(root); roots.push(root); return null;
    }
    const trunk = roles ? roles[i] === 'trunk' : i === 0;
    const core = bolt(owned, points, trunk ? .029 : .012, trunk ? '#e8ebff' : '#acb3ff', trunk ? 4 : 1.8);
    const halo = bolt(owned, points, trunk ? .085 : .042, '#8272ff', 1.6);
    core.name = `lightning-core-${i}`; halo.name = `lightning-halo-${i}`;
    main.add(core, halo); return { core, halo, index: i };
  }).filter(Boolean);
  const needsGroundPaths = roots.length === 0;
  for (let b = 0; b < (needsGroundPaths ? 10 : 0); b++) {
    const a = b * TAU / 10 + random(seed, b + 100) * .35;
    const length = 2.2 + random(seed, b + 120) * 2;
    const points = Array.from({ length: 9 }, (_, i) => {
      const t = i / 8, side = Math.sin(i * 3.1 + b) * .19 * t;
      return [Math.cos(a) * t * length - Math.sin(a) * side,
        .045 + Math.sin(t * Math.PI) * .12, Math.sin(a) * t * length + Math.cos(a) * side];
    });
    const root = bolt(owned, points, .022, '#9384ff', 3.2); root.name = `lightning-ground-${b}`;
    secondary.add(root); roots.push(root);
  }
  const charge = makeRing(owned, '#8f83ff', 2.1); charge.name = 'lightning-charge'; secondary.add(charge);
  const pulse = makeRing(owned, '#b1aaff', 2.3); pulse.name = 'lightning-shockwave'; secondary.add(pulse);
  const sparks = createSparks(owned, { count: 150, color: '#c9ceff', seed, mode: 'lightning' }); secondary.add(sparks.mesh);
  const light = new THREE.PointLight('#9185ff', 0, 12, 2); light.position.y = 1.7; secondary.add(light);
  return { main, secondary,
    update(t) {
      const age = t - 1.6;
      // Broad, staggered surges; no rapid whole-screen strobing.
      const surge = (x) => smooth(0, .045, x) * (1 - smooth(.20, .55, x));
      const power = Math.max(surge(age), surge(age - .51) * .65);
      bolts.forEach(({ core, halo, index }) => {
        const branchPower = index ? smooth(index * .012, index * .012 + .08, age) * power : power;
        core.visible = halo.visible = branchPower > .005;
        core.material.opacity = branchPower; halo.material.opacity = branchPower * .12;
      });
      roots.forEach((root, i) => { const p = smooth(.01 + i * .013, .16 + i * .013, age) * (1 - smooth(.55, 1.3, age));
        root.visible = p > .005; root.material.opacity = p * .75; });
      charge.scale.setScalar(1.65 - smooth(.2, 1.55, t) * .95); charge.rotation.z = -t * .4;
      charge.material.uniforms.uOpacity.value = smooth(.1, .6, t) * (1 - smooth(1.5, 1.73, t)) * .75;
      charge.material.uniforms.uTime.value = t;
      pulse.scale.setScalar(.4 + Math.max(0, age) * 4);
      pulse.material.uniforms.uOpacity.value = smooth(0, .06, age) * (1 - smooth(.08, .7, age)) * .6;
      pulse.visible = age > 0 && age < .7; pulse.material.uniforms.uTime.value = t;
      sparks.update(t, 1.65); light.intensity = power * 90;
    }, stats: { representation: 'branching 3D tubes + spatial arcs', paths: paths.length, sparks: 150,
      blenderPaths: Boolean(supplied) } };
}

function createIce(owned, { iceGltf, seed }) {
  if (!iceGltf?.scene || !Array.isArray(iceGltf.animations)) throw new Error('Ice requires the generated glacier GLB');
  const clip = iceGltf.animations.find((c) => c.name === 'ice_fall_break');
  if (!clip) throw new Error('Ice requires clip ice_fall_break');
  let sourceMeshes = 0; iceGltf.scene.traverse((object) => { if (object.isMesh) sourceMeshes++; });
  const main = new THREE.Group(), secondary = new THREE.Group();
  const setups = [{ x: 0, z: 0, size: 1, delay: 0, turn: .1 },
    { x: -2.25, z: -.85, size: .63, delay: .26, turn: -1.1 },
    { x: 1.95, z: .75, size: .53, delay: .56, turn: 1.5 }];
  const bodies = setups.map((setup, index) => {
    const anchor = new THREE.Group(); anchor.position.set(setup.x, 0, setup.z); anchor.rotation.y = setup.turn;
    anchor.scale.setScalar(setup.size); main.add(anchor);
    const body = iceGltf.scene.clone(true); body.name = `ice-body-${index}`; anchor.add(body);
    const materialMap = new Map();
    body.traverse((object) => {
      if (!object.isMesh) return;
      object.castShadow = true; object.receiveShadow = true;
      const clone = (source) => {
        if (!materialMap.has(source)) {
          const mat = source.name === 'ice_interior'
            ? new THREE.MeshPhysicalMaterial({ name: 'game-vfx-ice-interior', color: '#72c5f0', map: source.map,
              roughness: .21, metalness: .02, clearcoat: .75, transmission: .11, thickness: .32, ior: 1.31,
              attenuationColor: new THREE.Color('#419ed2'), attenuationDistance: .6 })
            : source.clone();
          mat.roughness = Math.min(mat.roughness ?? .36, .38); mat.envMapIntensity = 1.2;
          materialMap.set(source, owned.material(mat));
        }
        return materialMap.get(source);
      };
      object.material = Array.isArray(object.material) ? object.material.map(clone) : clone(object.material);
    });
    const mixer = new THREE.AnimationMixer(body), action = mixer.clipAction(clip);
    action.setLoop(THREE.LoopOnce, 1); action.clampWhenFinished = true; action.play();
    const ring = makeRing(owned, '#9edbff', 1.5); ring.position.set(setup.x, .025, setup.z); secondary.add(ring);
    return { setup, anchor, body, mixer, action, ring };
  });
  const sparks = createSparks(owned, { count: 110, color: '#91c3df', seed, mode: 'ice', energy: 1.15 }); secondary.add(sparks.mesh);
  // Frost is supporting spatial particles with soft edges, not bright rigid
  // torus hoops or one opaque plane that hides the actual ice fragments.
  const puffCount = 100, puffPositions = new Float32Array(puffCount * 3);
  const puffSizes = new Float32Array(puffCount), puffAlpha = new Float32Array(puffCount);
  const puffGeometry = owned.geometry(new THREE.BufferGeometry());
  puffGeometry.setAttribute('position', new THREE.BufferAttribute(puffPositions, 3));
  puffGeometry.setAttribute('puffSize', new THREE.BufferAttribute(puffSizes, 1));
  puffGeometry.setAttribute('puffAlpha', new THREE.BufferAttribute(puffAlpha, 1));
  const puffMaterial = owned.material(new THREE.ShaderMaterial({
    uniforms: { uViewport: { value: 600 }, uOrthographic: { value: false } },
    vertexShader: `attribute float puffSize; attribute float puffAlpha; varying float vAlpha;
      uniform float uViewport; uniform bool uOrthographic;
      void main(){ vec4 p=modelViewMatrix*vec4(position,1.); gl_Position=projectionMatrix*p;
        float distanceScale=uOrthographic?1.:max(1.,-p.z);
        float modelScale=length(modelMatrix[0].xyz);
        gl_PointSize=clamp(puffSize*modelScale*uViewport*.5*abs(projectionMatrix[1][1])/distanceScale,1.,100.); vAlpha=puffAlpha; }`,
    fragmentShader: `varying float vAlpha; void main(){ float r=length(gl_PointCoord-.5)*2.;
      float alpha=pow(max(0.,1.-r*r),2.)*vAlpha; if(alpha<.002)discard;
      gl_FragColor=vec4(.32,.48,.58,alpha); }`,
    transparent: true, depthWrite: false, toneMapped: false,
  }));
  const mist = new THREE.Points(puffGeometry, puffMaterial); mist.name = 'ice-mist'; mist.frustumCulled = false; secondary.add(mist);
  const viewport = new THREE.Vector2();
  mist.onBeforeRender = (renderer, _scene, camera) => {
    renderer.getDrawingBufferSize(viewport); puffMaterial.uniforms.uViewport.value = viewport.y;
    puffMaterial.uniforms.uOrthographic.value = Boolean(camera.isOrthographicCamera);
  };
  return { main, secondary,
    update(t) {
      bodies.forEach(({ setup, anchor, mixer, action, ring }) => {
        const age = t - setup.delay;
        // Piece motion is a Blender rigid-body bake; support visuals are runtime.
        action.paused = false; action.enabled = true;
        mixer.setTime(clamp(age / 1.9 * 2, 0, 6) + 1 / 24);
        anchor.visible = age > .04;
        // Shrink only after the pieces have settled, avoiding abrupt cleanup.
        anchor.scale.setScalar(setup.size * (1 - smooth(4.0, 5.35, t)));
        const shockAge = age - 1.9;
        ring.visible = shockAge > 0 && shockAge < .75;
        ring.scale.setScalar(setup.size * (.35 + Math.max(0, shockAge) * 4.1));
        ring.material.uniforms.uOpacity.value = .45 * (1 - smooth(.12, .75, shockAge));
        ring.material.uniforms.uTime.value = t;
      });
      sparks.update(t, 1.92);
      const age = t - 1.9;
      mist.visible = age > 0 && age < 2.25;
      for (let i = 0; i < puffCount; i++) {
        const a = random(seed, i * 5 + 3000) * TAU;
        const delay = random(seed, i * 5 + 3001) * .28;
        const dt = Math.max(0, age - delay);
        const v = .4 + random(seed, i * 5 + 3002) * 1.6;
        const r = .3 + v * dt / (1 + dt * .6);
        puffPositions[i * 3] = Math.cos(a) * r;
        puffPositions[i * 3 + 1] = .08 + random(seed, i * 5 + 3003) * .22 + dt * .18;
        puffPositions[i * 3 + 2] = Math.sin(a) * r;
        puffSizes[i] = (.25 + random(seed, i * 5 + 3004) * .45) * (1 + dt * .9);
        puffAlpha[i] = smooth(0, .13, age - delay) * (1 - smooth(.25, 2.0, dt)) * .11;
      }
      puffGeometry.attributes.position.needsUpdate = true;
      puffGeometry.attributes.puffSize.needsUpdate = true; puffGeometry.attributes.puffAlpha.needsUpdate = true;
    }, cleanup() { bodies.forEach(({ mixer, body }) => { mixer.stopAllAction(); mixer.uncacheRoot(body); }); },
    stats: { representation: 'generated mesh + Blender baked fracture', sourceMeshes, instances: 3, sparks: 110, frostPuffs: puffCount } };
}

export function createEffect(id, { iceGltf, noiseTexture, recipes, seed = 17, scale = 1, speed = 1 } = {}) {
  const definition = EFFECTS.find((e) => e.id === id);
  if (!definition) throw new Error(`Unknown effect: ${id}`);
  if (![seed, scale, speed].every(Number.isFinite) || scale <= 0 || speed <= 0) throw new Error('Seed must be finite; scale and speed must be positive finite values');
  const owned = resources();
  let effect;
  try {
    effect = ({ fire: createFire, ice: createIce, lightning: createLightning })[id](owned, { iceGltf, noiseTexture, recipes, seed });
  } catch (error) { owned.dispose(); throw error; }
  const group = new THREE.Group(); group.name = `game-vfx-${id}`; group.scale.setScalar(scale);
  effect.main.name = 'main'; effect.secondary.name = 'secondary'; group.add(effect.main, effect.secondary);
  const layers = { main: true, secondary: true };
  let disposed = false;
  const duration = definition.duration / speed, impact = definition.impact / speed;
  function update(seconds) {
    if (disposed) throw new Error('Effect is disposed');
    if (!Number.isFinite(seconds)) throw new Error('Time must be finite');
    const t = clamp(seconds * speed, 0, definition.duration);
    group.visible = seconds > 0 && seconds < duration;
    effect.update(t); effect.main.visible = layers.main; effect.secondary.visible = layers.secondary;
    return { time: seconds, phase: t < definition.impact ? 'anticipation' : t < definition.impact + .35 ? 'impact'
      : t < definition.duration - 1 ? 'release' : 'dissipation', active: group.visible };
  }
  update(0);
  return { group, duration, impact, update, stats: effect.stats,
    setSceneDepth(texture, width, height) { if (disposed) throw new Error('Effect is disposed'); effect.setSceneDepth?.(texture, width, height); },
    setLayer(name, visible) { if (!(name in layers)) throw new Error(`Unknown layer: ${name}`);
      layers[name] = Boolean(visible); effect[name].visible = layers[name]; },
    dispose() { if (disposed) return; disposed = true; group.removeFromParent(); effect.cleanup?.(); owned.dispose(); },
  };
}

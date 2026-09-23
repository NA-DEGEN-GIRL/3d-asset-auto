import * as THREE from 'three';
import { clamp, smooth, random, TAU } from './common.js';

const IMPACT = 1.9;
const SOURCE_IMPACT = 2;
const SOURCE_OFFSET = 1 / 24;

function makeMist(owned, count, seed, color) {
  const positions = new Float32Array(count * 3), sizes = new Float32Array(count), alpha = new Float32Array(count);
  const phases = Float32Array.from({ length: count }, (_, i) => random(seed, i + 6200));
  const geometry = owned.geometry(new THREE.BufferGeometry());
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geometry.setAttribute('puffSize', new THREE.BufferAttribute(sizes, 1));
  geometry.setAttribute('puffAlpha', new THREE.BufferAttribute(alpha, 1));
  geometry.setAttribute('puffPhase', new THREE.BufferAttribute(phases, 1));
  const material = owned.material(new THREE.ShaderMaterial({
    uniforms: { uViewport: { value: 600 }, uOrthographic: { value: false }, uColor: { value: new THREE.Color(color) } },
    vertexShader: `attribute float puffSize; attribute float puffAlpha; attribute float puffPhase;
      varying float vAlpha; varying float vPhase; uniform float uViewport; uniform bool uOrthographic;
      void main(){ vec4 p=modelViewMatrix*vec4(position,1.); gl_Position=projectionMatrix*p;
        float distanceScale=uOrthographic?1.:max(1.,-p.z);
        float modelScale=length(modelMatrix[0].xyz);
        gl_PointSize=clamp(puffSize*modelScale*uViewport*.5*abs(projectionMatrix[1][1])/distanceScale,1.,140.);
        vAlpha=puffAlpha; vPhase=puffPhase; }`,
    fragmentShader: `varying float vAlpha; varying float vPhase; uniform vec3 uColor;
      float hash(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}
      float noise(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);
        return mix(mix(hash(i),hash(i+vec2(1,0)),f.x),mix(hash(i+vec2(0,1)),hash(i+1.),f.x),f.y);}
      void main(){ vec2 p=gl_PointCoord-.5; float r=length(p)*2.;
        float detail=.55+.3*noise(p*7.+vPhase*43.)+.15*noise(p*16.-vPhase*18.);
        float alpha=pow(max(0.,1.-r*r),1.65)*detail*vAlpha;if(alpha<.002)discard;
        gl_FragColor=vec4(uColor,alpha); }`,
    transparent: true, depthWrite: false, toneMapped: false,
  }));
  const mesh = new THREE.Points(geometry, material); mesh.frustumCulled = false;
  const viewport = new THREE.Vector2();
  mesh.onBeforeRender = (renderer, _scene, camera) => {
    renderer.getDrawingBufferSize(viewport); material.uniforms.uViewport.value = viewport.y;
    material.uniforms.uOrthographic.value = Boolean(camera.isOrthographicCamera);
  };
  return { mesh, positions, sizes, alpha,
    commit() { geometry.attributes.position.needsUpdate = true; geometry.attributes.puffSize.needsUpdate = true; geometry.attributes.puffAlpha.needsUpdate = true; } };
}

function makeGroundFrost(owned, seed) {
  const material = owned.material(new THREE.ShaderMaterial({
    uniforms: { uGrowth: { value: 0 }, uFade: { value: 0 }, uSeed: { value: seed * .07 } },
    vertexShader: 'varying vec2 vUv;void main(){vUv=uv;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.);}',
    fragmentShader: `varying vec2 vUv;uniform float uGrowth;uniform float uFade;uniform float uSeed;
      float hash(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}
      float noise(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);
        return mix(mix(hash(i),hash(i+vec2(1,0)),f.x),mix(hash(i+vec2(0,1)),hash(i+1.),f.x),f.y);}
      void main(){vec2 p=(vUv-.5)*2.;
        p+=vec2(noise(p*3.+uSeed),noise(p*3.-uSeed+17.))*.28-.14;
        float coarse=noise(p*3.2+uSeed), grain=noise(p*31.-uSeed);
        float frostPattern=.55*coarse+.3*noise(p*6.3-uSeed)+.15*noise(p*13.+uSeed);
        float edge=length(p*vec2(.92,1.1))+.25*noise(p*5.-uSeed);
        float growth=1.-smoothstep(uGrowth-.14,uGrowth+.03,edge);
        float flakes=smoothstep(.42,.72,grain)*smoothstep(.3,.62,frostPattern);
        float cracks=(1.-smoothstep(.015,.045,abs(noise(p*8.+uSeed)-.55)))*frostPattern;
        float alpha=growth*(flakes*.22+cracks*.10+frostPattern*.06)*uFade;
        if(alpha<.008)discard;gl_FragColor=vec4(mix(vec3(.16,.30,.40),vec3(.36,.52,.63),grain),alpha);}`,
    transparent: true, depthWrite: false, side: THREE.DoubleSide, toneMapped: false,
  }));
  const mesh = new THREE.Mesh(owned.geometry(new THREE.PlaneGeometry(5.7, 5.7)), material);
  mesh.rotation.x = -Math.PI / 2; mesh.position.y = .015;
  return { mesh, update(age) {
    mesh.visible = age > 0 && age < 2.85;
    material.uniforms.uGrowth.value = smooth(0, .65, age);
    material.uniforms.uFade.value = 1 - smooth(1.8, 2.85, age);
  } };
}

function makeImpact(owned, seed, geometry, material) {
  const group = new THREE.Group();
  const count = 38;
  const shards = owned.object(new THREE.InstancedMesh(geometry, material, count));
  shards.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  shards.name = 'ice-secondary-shards'; shards.frustumCulled = false;
  shards.castShadow = true; shards.receiveShadow = true; group.add(shards);
  const mist = makeMist(owned, 68, seed, '#86b7cc'); mist.mesh.name = 'ice-impact-mist'; group.add(mist.mesh);
  // Short velocity-aligned micro-fractures make the initial impulse legible.
  // They are slender world-space geometry, not additive squares or long-lived sparks.
  const streakCount = 18;
  const streakMaterial = owned.material(new THREE.MeshBasicMaterial({ color: '#a8cbdc',
    transparent: true, opacity: 0, depthWrite: false, toneMapped: true }));
  const streaks = owned.object(new THREE.InstancedMesh(
    owned.geometry(new THREE.CylinderGeometry(.18, 1, 1, 5, 1)), streakMaterial, streakCount));
  streaks.name = 'ice-powder-streaks'; streaks.frustumCulled = false;
  streaks.instanceMatrix.setUsage(THREE.DynamicDrawUsage); group.add(streaks);
  const frost = makeGroundFrost(owned, seed); frost.mesh.name = 'ice-ground-frost'; group.add(frost.mesh);
  const dummy = new THREE.Object3D();
  const velocity = new THREE.Vector3(), up = new THREE.Vector3(0, 1, 0);
  const data = Array.from({ length: count }, (_, i) => ({
    angle: random(seed, i * 8 + 2000) * TAU,
    speed: 1.4 + random(seed, i * 8 + 2001) * 3.1,
    lift: 1.5 + random(seed, i * 8 + 2002) * 3.3,
    delay: random(seed, i * 8 + 2003) * .045,
    size: i < 8 ? .13 + random(seed, i * 8 + 2004) * .12 : .035 + random(seed, i * 8 + 2004) * .085,
    spin: 2.5 + random(seed, i * 8 + 2005) * 5,
    length: .8 + random(seed, i * 8 + 2006) * 1.9,
    finish: 1.9 + random(seed, i * 8 + 2007) * .65,
  }));
  return { group, update(age) {
    group.visible = age > 0 && age < 2.85;
    data.forEach((p, i) => {
      const t = Math.max(0, age - p.delay), flight = p.lift * .2;
      const grounded = Math.max(0, t - flight);
      const travel = p.speed * (Math.min(t, flight) + .27 * (1 - Math.exp(-grounded * 4)));
      const y = t <= flight ? .065 + p.lift * t - 5 * t * t
        : .065 + Math.max(0, p.lift * .24 * grounded - 5 * grounded * grounded);
      // Uneven, directional jets support the large fracture pieces rather than
      // replacing them with identical glowing confetti.
      dummy.position.set(Math.cos(p.angle) * travel, y, Math.sin(p.angle) * travel * .74);
      const turn = Math.min(t, flight) * p.spin + Math.min(grounded, .3);
      dummy.rotation.set(p.angle + turn, p.angle * .7 + turn * .6, turn * .8);
      const size = age > p.delay ? p.size * (1 - smooth(p.finish, p.finish + .25, age)) : 0;
      dummy.scale.set(size * .5, size * p.length, size * .7); dummy.updateMatrix(); shards.setMatrixAt(i, dummy.matrix);
    });
    shards.instanceMatrix.needsUpdate = true;
    streaks.visible = age > 0 && age < .78;
    streakMaterial.opacity = smooth(0, .035, age) * (1 - smooth(.17, .78, age)) * .38;
    for (let i = 0; i < streakCount; i++) {
      const t = Math.max(0, age - random(seed, i * 4 + 9000) * .035);
      const a = (i % 5) / 5 * TAU + random(seed, i * 4 + 9001) * .36 + seed * .015;
      const v = 3.8 + random(seed, i * 4 + 9002) * 4.4;
      const vy = 1.2 + random(seed, i * 4 + 9003) * 2.8;
      const y = .13 + vy * t - 6 * t * t;
      dummy.position.set(Math.cos(a) * v * t, Math.max(.045, y), Math.sin(a) * v * t * .85);
      velocity.set(Math.cos(a) * v, vy - 12 * t, Math.sin(a) * v * .85).normalize();
      dummy.quaternion.setFromUnitVectors(up, velocity);
      const width = age > 0 && y > .045 ? .012 + .008 * random(seed, i + 9600) : 0;
      dummy.scale.set(width, width ? .16 + Math.min(.38, v * t * .28) : 0, width);
      dummy.updateMatrix(); streaks.setMatrixAt(i, dummy.matrix);
    }
    streaks.instanceMatrix.needsUpdate = true;
    for (let i = 0; i < mist.sizes.length; i++) {
      const powder = i < 36;
      const delay = random(seed, i * 6 + 4001) * (powder ? .025 : .09);
      const t = Math.max(0, age - delay);
      if (powder) {
        const lobe = i % 6, along = .48 + Math.floor(i / 6) * .13;
        const a = lobe / 6 * TAU + seed * .015 + (random(seed, i * 6 + 4000) - .5) * .24;
        const travel = (.18 + t * (6.5 + random(seed, lobe + 4700) * 2.5) / (1 + t * 2.6)) * along;
        mist.positions[i * 3] = Math.cos(a) * travel;
        mist.positions[i * 3 + 1] = .13 + t * (1.7 + random(seed, lobe + 4800) * 1.8) / (1 + t * 2) * along;
        mist.positions[i * 3 + 2] = Math.sin(a) * travel * .83;
        mist.sizes[i] = (.36 + random(seed, i * 6 + 4004) * .27) * (1 + t * 2.6);
        mist.alpha[i] = smooth(0, .03, age - delay) * (1 - smooth(.15, .78, t)) * .28;
      } else {
        const a = random(seed, i * 6 + 4000) * TAU;
        const travel = .28 + (1.4 + random(seed, i * 6 + 4002) * 2.5) * t / (1 + t * .72);
        mist.positions[i * 3] = Math.cos(a) * travel;
        mist.positions[i * 3 + 1] = .10 + (1 - Math.exp(-t * 2)) * .14 + random(seed, i * 6 + 4003) * .13;
        mist.positions[i * 3 + 2] = Math.sin(a) * travel * .82;
        mist.sizes[i] = (.64 + random(seed, i * 6 + 4004) * .55) * (1 + t * .55);
        mist.alpha[i] = smooth(0, .07, age - delay) * (1 - smooth(.38, 1.85 + random(seed, i * 6 + 4005) * .25, t)) * .19;
      }
    }
    mist.commit(); frost.update(age);
  }, shardCount: count, streakCount, puffCount: mist.sizes.length };
}

export function createIce(owned, { iceGltf, seed }) {
  if (!iceGltf?.scene || !Array.isArray(iceGltf.animations)) throw new Error('Ice requires the generated glacier GLB');
  const clip = iceGltf.animations.find((c) => c.name === 'ice_fall_break');
  if (!clip) throw new Error('Ice requires clip ice_fall_break');
  let sourceMeshes = 0; iceGltf.scene.traverse((object) => { if (object.isMesh) sourceMeshes++; });
  const main = new THREE.Group(), secondary = new THREE.Group();
  const setups = [{ x: 0, z: 0, size: 1, delay: 0, turn: .1 },
    { x: -2.25, z: -.85, size: .63, delay: .26, turn: -1.1 },
    { x: 1.95, z: .75, size: .53, delay: .56, turn: 1.5 }];
  const shardGeometry = owned.geometry(new THREE.IcosahedronGeometry(1, 0));
  const shardMaterial = owned.material(new THREE.MeshPhysicalMaterial({ color: '#72b7d7',
    roughness: .3, metalness: .025, clearcoat: .7, transmission: .055, thickness: .12, ior: 1.31,
    attenuationColor: new THREE.Color('#4386ae'), attenuationDistance: .4, envMapIntensity: 1.1 }));
  const bodies = setups.map((setup, index) => {
    const anchor = new THREE.Group(); anchor.name = `ice-mass-${index}`;
    anchor.position.set(setup.x, 0, setup.z); anchor.rotation.y = setup.turn;
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
          // Preserve the exterior's packed roughness texture multiplier instead
          // of forcing it to .38 and washing its frozen surface in reflections.
          mat.envMapIntensity = source.name === 'ice_interior' ? 1.0 : .85;
          materialMap.set(source, owned.material(mat));
        }
        return materialMap.get(source);
      };
      object.material = Array.isArray(object.material) ? object.material.map(clone) : clone(object.material);
    });
    const mixer = new THREE.AnimationMixer(body), action = mixer.clipAction(clip);
    action.setLoop(THREE.LoopOnce, 1); action.clampWhenFinished = true; action.play();
    const impact = makeImpact(owned, seed + index * 101, shardGeometry, shardMaterial);
    impact.group.name = `ice-impact-${index}`;
    impact.group.position.set(setup.x, 0, setup.z); impact.group.rotation.y = setup.turn;
    impact.group.scale.setScalar(setup.size); secondary.add(impact.group);
    impact.group.userData.impactTime = IMPACT + setup.delay;
    const trail = makeMist(owned, 30, seed + index * 151, '#83bbd8');
    trail.mesh.name = `ice-fall-trail-${index}`;
    const trailAnchor = new THREE.Group(); trailAnchor.position.copy(impact.group.position);
    trailAnchor.rotation.copy(impact.group.rotation); trailAnchor.scale.setScalar(setup.size);
    trailAnchor.add(trail.mesh); secondary.add(trailAnchor);
    return { setup, anchor, body, mixer, action, impact, trail, trailAnchor, index,
      bounds: new THREE.Box3(), center: new THREE.Vector3() };
  });
  return { main, secondary,
    update(t) {
      bodies.forEach(({ setup, anchor, body, mixer, action, impact, trail, trailAnchor, index, bounds, center }) => {
        const age = t - setup.delay;
        // Preserve the source collision event exactly while accelerating the
        // approach and compressing the post-impact bake independently.
        const sourceTime = age <= IMPACT ? SOURCE_IMPACT * Math.pow(clamp(age / IMPACT), 1.65)
          : SOURCE_IMPACT + (age - IMPACT) * 1.3;
        action.paused = false; action.enabled = true;
        mixer.setTime(clamp(sourceTime, 0, 6) + SOURCE_OFFSET);
        anchor.visible = age > .04;
        anchor.scale.setScalar(setup.size * (1 - smooth(4.0, 4.78, age)));
        impact.update(age - IMPACT);
        trailAnchor.visible = age > .2 && age < IMPACT;
        if (trailAnchor.visible) {
          anchor.updateWorldMatrix(true, true);
          bounds.setFromObject(body); bounds.getCenter(center); anchor.worldToLocal(center);
          const intensity = smooth(.2, 1.35, age) * (1 - smooth(1.82, IMPACT, age));
          for (let i = 0; i < trail.sizes.length; i++) {
            const f = i / (trail.sizes.length - 1), a = random(seed + index * 151, i * 3 + 8100) * TAU;
            const radius = (.18 + f * .17) * Math.sin(a * 3 + age * 4);
            trail.positions[i * 3] = center.x + Math.cos(a) * radius;
            trail.positions[i * 3 + 1] = center.y + .55 + f * (1.1 + intensity * 1.05);
            trail.positions[i * 3 + 2] = center.z + Math.sin(a) * radius;
            trail.sizes[i] = .27 + (1 - f) * .42;
            trail.alpha[i] = intensity * (1 - f) * .14;
          }
          trail.commit();
        } else {
          trail.positions.fill(0); trail.sizes.fill(0); trail.alpha.fill(0); trail.commit();
        }
      });
    }, cleanup() { bodies.forEach(({ mixer, body }) => { mixer.stopAllAction(); mixer.uncacheRoot(body); }); },
    stats: { representation: 'generated mesh + Blender baked fracture + per-impact secondary shards, cold mist and frost',
      sourceMeshes, instances: 3, secondaryShards: 114, powderStreaks: 54, frostPuffs: 204,
      powderPuffs: 108, rollingMistPuffs: 96, trailPuffs: 90,
      events: setups.map((setup, index) => ({ id: `ice-impact-${index}`, time: IMPACT + setup.delay,
        position: [setup.x, 0, setup.z], sourceImpact: SOURCE_IMPACT + SOURCE_OFFSET,
        cleanupEnd: 4.78 + setup.delay })) } };
}

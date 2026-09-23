import * as THREE from 'three';
import { clamp, smooth, random, TAU, glowMaterial, createSparks } from './common.js';

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

function bolt(owned, points, radius, color, energy, taper = .78) {
  const curve = polyline(points);
  const segments = Math.max(16, points.length * 2);
  const geometry = owned.geometry(new THREE.TubeGeometry(curve, segments, radius, 5, false));
  const positions = geometry.attributes.position, point = new THREE.Vector3();
  for (let i = 0; i <= segments; i++) {
    const u = i / segments, center = curve.getPointAt(u), width = 1 - taper * Math.pow(u, .8);
    for (let j = 0; j <= 5; j++) {
      const index = i * 6 + j;
      point.fromBufferAttribute(positions, index).sub(center).multiplyScalar(width).add(center);
      positions.setXYZ(index, point.x, point.y, point.z);
    }
  }
  geometry.computeBoundingSphere();
  return new THREE.Mesh(geometry, glowMaterial(owned, color, energy));
}

function reveal(mesh, head, tail = 0) {
  const count = mesh.geometry.index.count;
  const stride = 30; // One TubeGeometry segment, five radial faces.
  const start = Math.floor(clamp(tail) * count / stride) * stride;
  const end = Math.floor(clamp(head) * count / stride) * stride;
  mesh.geometry.setDrawRange(start, Math.max(0, end - start));
}

function makeContact(owned) {
  const material = owned.material(new THREE.ShaderMaterial({
    uniforms: { uTime: { value: 0 }, uCharge: { value: 0 }, uAfter: { value: 0 } },
    vertexShader: 'varying vec2 vUv;void main(){vUv=uv;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.);}',
    fragmentShader: `varying vec2 vUv;uniform float uTime,uCharge,uAfter;
      void main(){vec2 p=(vUv-.5)*2.;float r=length(p),a=atan(p.y,p.x);
        float wobble=sin(a*7.+sin(a*3.)*1.6)*.06+sin(a*19.)*.025;
        float bed=(1.-smoothstep(.16,.9,r+wobble))*(.55+.2*sin(a*11.+r*33.));
        float veins=pow(max(0.,cos(a*13.+sin(r*18.+a*3.)*.65)),28.);
        float advancing=1.-smoothstep(max(0.,uTime)*1.8,max(0.,uTime)*1.8+.13,r);
        float detail=veins*(1.-smoothstep(.45,.95,r))*advancing;
        float halo=pow(max(0.,1.-r),3.);
        vec3 cold=vec3(.07,.035,.16),charged=vec3(.24,.17,.62);
        vec3 color=mix(cold,charged,clamp(detail+uCharge,0.,1.));
        float alpha=bed*uAfter*.24+detail*uAfter*.40+halo*uCharge*.40;
        if(alpha<.002)discard;gl_FragColor=vec4(color,alpha);}`,
    transparent: true, depthWrite: false, toneMapped: false,
  }));
  const mesh = new THREE.Mesh(owned.geometry(new THREE.PlaneGeometry(8, 8)), material);
  mesh.rotation.x = -Math.PI / 2; mesh.position.y = .015; mesh.name = 'lightning-contact';
  return mesh;
}

export function createLightning(owned, { recipes, seed }) {
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
      const major = roots.length < 7;
      const root = bolt(owned, points, major ? .039 : .016, major ? '#c0ceff' : '#748cff', major ? 2.6 : 1.7);
      root.name = `lightning-ground-${i}`;
      secondary.add(root); roots.push(root); return null;
    }
    const trunk = roles ? roles[i] === 'trunk' : i === 0;
    const major = !trunk && i <= 8;
    const core = bolt(owned, points, trunk ? .043 : major ? .028 : .010,
      trunk ? '#dbe9ff' : major ? '#b2c7ff' : '#7e9aff', trunk ? 2.9 : major ? 2.1 : 1.4, trunk ? .08 : .83);
    const halo = bolt(owned, points, trunk ? .088 : major ? .06 : .027, '#4868e9', 1.05, trunk ? .10 : .83);
    core.name = `lightning-core-${i}`; halo.name = `lightning-halo-${i}`;
    main.add(core, halo);
    // Branch reveal starts only when the leader reaches the branch's height.
    const begin = trunk ? 0 : clamp((8 - points[0][1]) / 7.84) * .095;
    return { core, halo, index: i, trunk, begin };
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
  const contact = makeContact(owned); secondary.add(contact);
  const streamers = [];
  for (let b = 0; b < 7; b++) {
    const angle = b * 2.399 + random(seed, b + 140) * .3;
    const radius = 1.0 + random(seed, b + 151) * 1.2;
    const points = Array.from({ length: 11 }, (_, i) => {
      const u = i / 10, r = radius * (1 - u * .72), bend = Math.sin(i * 6.1 + b) * .10 * Math.sin(u * Math.PI);
      return [Math.cos(angle) * r + bend, .03 + u * (1.1 + b * .13), Math.sin(angle) * r - bend];
    });
    const arc = bolt(owned, points, .010, '#697fff', 1.45);
    arc.name = `lightning-streamer-${b}`; secondary.add(arc); streamers.push(arc);
  }
  // Delayed oblique arcs carry residual charge through space after the trunk.
  const residuals = [];
  for (let b = 0; b < 6; b++) {
    const a = b * 1.77 + .3, extent = 1.7 + random(seed, b + 231) * 1.5;
    const points = Array.from({ length: 16 }, (_, i) => {
      const u = i / 15, r = u * extent;
      return [Math.cos(a) * r + Math.sin(i * 4.2 + b) * .07 * Math.sin(u * Math.PI),
        .07 + Math.sin(u * Math.PI) * (.45 + random(seed, b + 235) * .6),
        Math.sin(a) * r + Math.cos(i * 3.7) * .09 * Math.sin(u * Math.PI)];
    });
    const arc = bolt(owned, points, .014, '#688dff', 2.1);
    arc.name = `lightning-residual-${b}`; secondary.add(arc); residuals.push(arc);
  }
  const sparks = createSparks(owned, { count: 120, color: '#b1ceff', seed, mode: 'lightning', energy: 2.2 }); secondary.add(sparks.mesh);
  const light = new THREE.PointLight('#768fff', 0, 11, 2); light.position.y = .8; secondary.add(light);
  return { main, secondary,
    update(t) {
      const age = t - 1.6;
      // A descending leader, a return stroke, then a weaker re-strike. Local
      // channel changes retain cadence without flashing the whole frame.
      const surge = (x) => smooth(.085, .12, x) * (1 - smooth(.22, .46, x));
      const primary = surge(age), reprise = surge(age - .46) * .62;
      const leader = smooth(0, .05, age) * (1 - smooth(.08, .16, age)) * .33;
      const power = Math.max(primary, reprise);
      bolts.forEach(({ core, halo, index, trunk, begin }) => {
        const activeAge = age < .46 ? age : age - .46;
        const reach = smooth(begin, begin + (trunk ? .095 : .08), activeAge);
        const branchFactor = trunk ? 1 : (.38 + random(seed, index + 410) * .55)
          * (age < .46 || index % 3 !== 0 ? 1 : .16);
        const branchPower = Math.max(leader, power) * branchFactor * smooth(begin, begin + .018, activeAge);
        reveal(core, reach); reveal(halo, reach);
        core.visible = halo.visible = branchPower > .005;
        core.material.opacity = branchPower; halo.material.opacity = branchPower * .16;
      });
      roots.forEach((root, i) => {
        const start = .095 + i % 7 * .002 + (i >= 7 ? .035 : 0);
        const p = smooth(start, start + .028, age) * (1 - smooth(.46, 1.22, age));
        reveal(root, smooth(start, start + .055, age), smooth(.7, 1.3, age));
        root.visible = p > .005; root.material.opacity = p * .78;
      });
      streamers.forEach((arc, i) => {
        const start = .55 + i * .09;
        const p = smooth(start, start + .16, t) * (1 - smooth(1.59, 1.77, t));
        reveal(arc, smooth(start, start + .28, t));
        arc.visible = p > .005; arc.material.opacity = p * (.23 + smooth(1.3, 1.59, t) * .48);
      });
      residuals.forEach((arc, i) => {
        const dt = age - .44 - i * .055;
        reveal(arc, smooth(0, .2, dt), smooth(.3, .8, dt));
        arc.material.opacity = smooth(0, .055, dt) * (1 - smooth(.22, .8, dt)) * .55;
        arc.visible = dt > 0 && dt < .8;
      });
      contact.material.uniforms.uTime.value = age;
      contact.material.uniforms.uCharge.value = smooth(.1, 1.48, t) * (1 - smooth(1.58, 1.8, t));
      contact.material.uniforms.uAfter.value = smooth(.1, .22, age) * (1 - smooth(1.15, 2.65, age));
      sparks.update(t, 1.73); light.intensity = power * 48;
    }, stats: { representation: 'descending leader, branching return strokes and spatial residual arcs', paths: paths.length, sparks: 120,
      events: [{ id: 'leader', time: 1.6 }, { id: 'contact', time: 1.7 }, { id: 'restrike', time: 2.16 }],
      blenderPaths: Boolean(supplied) } };
}

import * as THREE from 'three';
import { clamp, smooth, random, TAU, glowMaterial, makeRing, createSparks } from './common.js';

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
  uniform float uAge;
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
    float h=clamp((p.y+.97)/1.94,0.,1.);
    if(h<=0.||h>=1.||length(p.xz)>.96||h>uAge*2.15+.15)return vec2(0.);
    // Follow the reference's broad, asymmetric S rather than scaling a conical
    // flame. This is an authored flow field, not a fluid-simulation claim.
    float turn=h*8.9-uTime*.73+.24*sin(h*6.+uTime*.4);
    mat2 rotation=mat2(cos(turn),-sin(turn),sin(turn),cos(turn));
    vec2 radial=vec2(cos(turn),sin(turn));
    vec2 tangent=vec2(-radial.y,radial.x);
    vec2 xy=rotation*p.xz;
    // Only the large sheet follows the vortex. Coarse eddies advect through
    // world space and fine turbulence crosses the flow, so the hot material
    // breaks into flame lobes instead of tracing unbroken helical hairs.
    vec2 worldFlow=p.xz+vec2(sin(p.y*2.4-uTime)*.045,cos(p.y*2.8-uTime*.8)*.045);
    vec3 n=densityNoise(vec3(worldFlow.x*1.10+uSeed,h*1.10-uTime*.33,worldFlow.y*1.10));
    vec3 detail=densityNoise(vec3(mix(p.x,xy.x,.28)*1.48+uSeed+.19,h*1.85-uTime*.57,mix(p.z,xy.y,.28)*1.48+.27));
    float sweep=(.08+.34*sin(h*2.65))*(.89+.11*sin(h*10.-uTime));
    vec2 center=radial*sweep+vec2(.12*h*h,-.045*h);
    vec2 q=p.xz-center+vec2(n.r-.5,n.g-.5)*.32;
    float width=(.305*pow(max(0.,1.-h),.24)+.038)*(.62+n.r*.85);
    // A wide ribbon with a narrow radial thickness leaves real negative space.
    // Different-height tongues overlap imperfectly: they do not become a smooth
    // glowing tube or a single cylindrical shell when viewed from the side.
    float ribbon=1.-length(vec2(dot(q,radial)/(width*.90),dot(q,tangent)/(width*1.65)));
    vec2 outerCenter=vec2(cos(turn+.92),sin(turn+.92))*(sweep+.20);
    vec2 outerQ=p.xz-outerCenter+vec2(detail.r-.5,detail.g-.5)*.23;
    float outer=1.-length(vec2(dot(outerQ,radial)/(width*.55+.018),dot(outerQ,tangent)/(width*.90+.018)));
    outer=mix(-2.,outer,smoothstep(.05,.20,h)*(1.-smoothstep(.73,.98,h)));
    vec2 innerCenter=vec2(cos(turn-.70),sin(turn-.70))*(sweep+.08);
    vec2 innerQ=p.xz-innerCenter+vec2(n.b-.5,detail.r-.5)*.18;
    float inner=1.-length(vec2(dot(innerQ,radial)/(width*.45+.01),dot(innerQ,tangent)/(width*.62+.01)));
    inner=mix(-2.,inner,smoothstep(.18,.34,h)*(1.-smoothstep(.62,.95,h)));
    float root=1.-length(p.xz)/(.22+.035*sin(atan(p.z,p.x)*5.+uTime*3.));
    root=mix(-2.,root,1.-smoothstep(.03,.20,h));
    float body=max(ribbon,max(inner*.78,max(outer*.86,root*.85)));
    // Strong erosion and anisotropic detail carve open cavities through the
    // sheets. Merely adding surface noise left the entire hot core continuous.
    float turbulence=(n.g-.52)*2.4+(detail.g-.51)*2.5;
    float torn=smoothstep(.34,.63,detail.r)*smoothstep(.24,.58,n.g);
    float density=max(0.,body+turbulence)*torn*1.95;
    // The eruption travels up the body. The base burns out first; late fire
    // lifts into a cooling crown instead of shrinking like an inflatable cone.
    float front=smoothstep(h-.14,h+.08,uAge*2.15);
    float burnout=1.-smoothstep(1.62+h*.72,2.63+h*.50,uAge);
    float vertical=smoothstep(0.,.027,h)*(1.-smoothstep(.87,1.,h));
    density*=front*burnout*vertical;
    float heat=clamp(body*.62+(detail.b-.5)*1.8+(n.g-.5)*.8+.12-.14*h,0.,1.);
    heat*=1.-smoothstep(1.80+h*.60,3.3,uAge)*.74;
    return vec2(density,heat);
  }
  vec3 fireColor(float heat){
    vec3 red=vec3(.76,.015,.002),orange=vec3(2.5,.24,.006),yellow=vec3(3.4,1.85,.38);
    return mix(mix(red,orange,smoothstep(.015,.37,heat)),yellow,smoothstep(.46,.94,heat));
  }
  void main(){
    vec3 dir=uOrthographic?normalize(uOrthoDirection):normalize(vLocal-uCamera);
    vec3 pos=vLocal+dir*.002;
    vec3 inv=1./(dir+vec3(.000001));
    vec3 toFar=max((-vec3(1.)-pos)*inv,(vec3(1.)-pos)*inv);
    float distance=min(toFar.x,min(toFar.y,toFar.z));
    float ds=max(0.,distance)/80.;
    float opaqueDepth=uHasSceneDepth?texture2D(uSceneDepth,gl_FragCoord.xy/uViewport).x:1.;
    vec3 sum=vec3(0.); float alpha=0.;
    for(int i=0;i<80;i++){
      vec4 clipPosition=uLocalToClip*vec4(pos,1.);
      float sampleDepth=clipPosition.z/clipPosition.w*.5+.5;
      if(uHasSceneDepth&&sampleDepth>opaqueDepth+.000002)break;
      vec2 sampleValue=field(pos); float a=1.-exp(-sampleValue.x*ds*4.2);
      sum+=(1.-alpha)*a*fireColor(sampleValue.y); alpha+=(1.-alpha)*a;
      pos+=dir*ds; if(alpha>.985)break;
    }
    if(alpha<.005)discard;
    gl_FragColor=vec4(sum/max(alpha,.0001),alpha*uOpacity);
  }
`;

function createCinders(owned, seed) {
  const geometry = owned.geometry(new THREE.OctahedronGeometry(1, 0));
  const material = glowMaterial(owned, '#ff943e', 3.3);
  const mesh = owned.object(new THREE.InstancedMesh(geometry, material, 260));
  mesh.name = 'fire-cooling-cinders'; mesh.frustumCulled = false;
  const data = Array.from({ length: 260 }, (_, i) => ({
    angle: random(seed, i * 8 + 2000) * TAU,
    h: random(seed, i * 8 + 2001), delay: random(seed, i * 8 + 2002) * 1.9,
    life: .45 + random(seed, i * 8 + 2003) * 1.20,
    speed: random(seed, i * 8 + 2004), radius: random(seed, i * 8 + 2005),
    size: .012 + Math.pow(random(seed, i * 8 + 2006), 2) * .027,
  }));
  const dummy = new THREE.Object3D(), velocity = new THREE.Vector3(), up = new THREE.Vector3(0, 1, 0);
  return { mesh, update(t) {
    data.forEach((p, i) => {
      const age = t - 1.34 - p.delay, life = clamp(age / p.life);
      const alive = age > 0 && age < p.life;
      const h = .12 + p.h * .82;
      const theta = h * 8.9 - (1.34 + p.delay) * .73;
      const a = theta + age * (1.6 + p.speed) + (p.angle - Math.PI) * .18;
      const r = .4 + Math.sin(h * 2.65) * 1.30 + age * (.35 + p.radius * .9);
      dummy.position.set(Math.cos(a) * r, h * 6.1 + age * (1.0 + p.speed * 1.7), Math.sin(a) * r);
      velocity.set(-Math.sin(a) * r * 2, 1.2 + p.speed, Math.cos(a) * r * 2).normalize();
      dummy.quaternion.setFromUnitVectors(up, velocity);
      const size = alive ? p.size * Math.sin(Math.PI * life) * (1 - smooth(4.35, 4.79, t)) : 0;
      dummy.scale.set(size, size * (2.0 + p.speed * 4), size);
      dummy.updateMatrix(); mesh.setMatrixAt(i, dummy.matrix);
    });
    mesh.instanceMatrix.needsUpdate = true;
  } };
}

function createScorch(owned) {
  const material = owned.material(new THREE.ShaderMaterial({
    uniforms: { uTime: { value: 0 }, uOpacity: { value: 0 }, uHeat: { value: 0 } },
    vertexShader: 'varying vec2 vUv; void main(){vUv=uv;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.);}',
    fragmentShader: `varying vec2 vUv; uniform float uTime; uniform float uOpacity; uniform float uHeat;
      float hash(vec2 p){ return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453); }
      float n(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);
        return mix(mix(hash(i),hash(i+vec2(1,0)),f.x),mix(hash(i+vec2(0,1)),hash(i+vec2(1,1)),f.x),f.y);}
      void main(){vec2 p=(vUv-.5)*2.;float r=length(p);
        float coarse=n(p*3.7+vec2(1.3,-2.1));
        float grain=n(p*13.)*.6+n(p*37.)*.4;
        float islands=smoothstep(.25,.63,coarse)*smoothstep(.22,.58,grain);
        float mask=(1.-smoothstep(.28,.92,r+(.5-coarse)*.75))*islands*uOpacity;
        vec2 warp=p+vec2(n(p*4.),n(p*4.+7.))*.35;
        float veins=1.-smoothstep(.008,.045,abs(n(warp*11.)-.51));
        float ember=veins*smoothstep(.52,.78,n(p*21.))*uHeat;
        vec3 color=vec3(.035,.020,.012)+vec3(1.6,.14,.005)*ember;
        gl_FragColor=vec4(color,mask*.50); }`,
    transparent: true, depthWrite: false, toneMapped: false,
  }));
  const mesh = new THREE.Mesh(owned.geometry(new THREE.PlaneGeometry(7.8, 7.8)), material);
  mesh.name = 'fire-scorched-impact'; mesh.rotation.x = -Math.PI / 2; mesh.position.y = .012;
  return { mesh, update(t) {
    const age = t - 1.25;
    material.uniforms.uTime.value = t;
    material.uniforms.uOpacity.value = smooth(0, .28, age) * (1 - smooth(2.8, 3.52, age));
    material.uniforms.uHeat.value = (1 - smooth(.55, 2.3, age)) * .75;
  } };
}

export function createFire(owned, { noiseTexture, seed }) {
  const main = new THREE.Group(), secondary = new THREE.Group();
  const material = owned.material(new THREE.ShaderMaterial({
    uniforms: { uNoise: { value: noiseTexture ?? null }, uHasNoise: { value: Boolean(noiseTexture) },
      uCamera: { value: new THREE.Vector3() }, uOrthoDirection: { value: new THREE.Vector3() },
      uSceneDepth: { value: null }, uHasSceneDepth: { value: false }, uViewport: { value: new THREE.Vector2(1, 1) },
      uLocalToClip: { value: new THREE.Matrix4() },
      uOrthographic: { value: false }, uTime: { value: 0 }, uAge: { value: 0 }, uOpacity: { value: 0 }, uSeed: { value: seed * .037 } },
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
  const sparks = createSparks(owned, { count: 100, seed, mode: 'fire', energy: 2.6 }); secondary.add(sparks.mesh);
  const cinders = createCinders(owned, seed); secondary.add(cinders.mesh);
  const scorch = createScorch(owned); secondary.add(scorch.mesh);
  const light = new THREE.PointLight('#ff7135', 0, 15, 2); light.position.y = 2.2; secondary.add(light);
  return { main, secondary,
    update(t) {
      const age = t - 1.25;
      const rise = smooth(0, .20, age);
      const fade = 1 - smooth(2.5, 3.35, age);
      // Fixed bounds: front propagation/cooling occurs inside the field. The
      // silhouette does not simply expand and contract as one scaled object.
      const height = 6.8, width = 3.05;
      plume.scale.set(width, height / 2, width); plume.position.y = height / 2 + .025;
      plume.visible = age > 0 && fade > .001;
      material.uniforms.uTime.value = t; material.uniforms.uAge.value = age;
      material.uniforms.uOpacity.value = rise * fade * .97;
      const ringAge = Math.max(0, age);
      ring.scale.setScalar(.35 + ringAge * 3.7); ring.visible = age > 0 && age < .95;
      ring.material.uniforms.uOpacity.value = .48 * (1 - smooth(.12, .70, ringAge)); ring.material.uniforms.uTime.value = t;
      charge.scale.setScalar(1.8 - smooth(.05, 1.15, t) * 1.25); charge.rotation.z = t * .6;
      charge.material.uniforms.uOpacity.value = smooth(.05, .45, t) * (1 - smooth(1.1, 1.42, t)) * .7;
      charge.material.uniforms.uTime.value = t;
      sparks.update(t, 1.3); cinders.update(t); scorch.update(t);
      light.intensity = (22 + 20 * (1 - smooth(.05, .40, age))) * rise * (1 - smooth(1.6, 3.2, age));
    }, setSceneDepth(texture, width, height) {
      if (texture == null) { material.uniforms.uHasSceneDepth.value = false; material.uniforms.uSceneDepth.value = null; return; }
      if (!texture.isTexture || ![width, height].every(Number.isFinite) || width <= 0 || height <= 0) {
        throw new Error('Scene depth requires a texture and positive finite viewport dimensions');
      }
      material.uniforms.uSceneDepth.value = texture; material.uniforms.uHasSceneDepth.value = true;
      material.uniforms.uViewport.value.set(width, height);
    }, stats: { representation: '3D helical flame sheets + rising cinders + cooling scorched impact', volumeSteps: 80, sparks: 360,
      blenderDensityAtlas: Boolean(noiseTexture) } };
}

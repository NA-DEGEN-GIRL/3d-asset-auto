import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { EFFECTS, createEffect } from './effects.js';

const $ = (id) => document.getElementById(id);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
const korean = { fire: '불 마법', ice: '얼음 마법', lightning: '번개 마법' };
const phaseNames = { anticipation: '응축 · 예고', impact: '방출 · 충돌', release: '확산', dissipation: '소멸', active: '전개', finished: '종료' };
let stop = () => {};

function fail(message) {
  $('error').textContent = `미리보기를 시작하지 못했습니다.\n${message}`;
  $('error').hidden = false; $('loading').hidden = true;
  $('controls').disabled = true;
  for (const node of [...$$('[data-effect]'), $('play'), $('restart'), $('scrub')]) node.disabled = true;
  stop();
}

async function readJson(url) {
  const response = await fetch(url, { cache: 'no-store' });
  if (!response.ok) throw new Error(`${url} 파일을 불러올 수 없습니다 (${response.status}).`);
  return response.json();
}

// A neutral, owned floor material helps judging contact without hiding the VFX.
function makeFloorTexture() {
  const canvas = document.createElement('canvas'); canvas.width = canvas.height = 256;
  const context = canvas.getContext('2d');
  const pixels = context.createImageData(256, 256);
  for (let i = 0; i < 256 * 256; i++) {
    const hash = Math.sin(i * 12.9898) * 43758.5453;
    const shade = 170 + Math.round((hash - Math.floor(hash)) * 42);
    pixels.data.set([shade, shade, shade, 255], i * 4);
  }
  context.putImageData(pixels, 0, 0);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.wrapS = texture.wrapT = THREE.RepeatWrapping; texture.repeat.set(70, 70);
  return texture;
}

async function start() {
  const config = await readJson('./config.json');
  if (config.version !== 1 || !config.available || !config.resources) {
    throw new Error('필요한 제작 자료가 없습니다. 준비된 media 폴더를 지정하여 미리보기를 빌드해 주세요.');
  }
  const viewport = $('viewport');
  const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 1.7));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 0.85;
  renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFShadowMap;
  renderer.domElement.setAttribute('aria-label', '입체 마법 효과: 드래그하여 회전');
  viewport.append(renderer.domElement);
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(42, 1, 0.05, 100);
  const orbit = new OrbitControls(camera, renderer.domElement);
  orbit.enableDamping = true; orbit.minDistance = 6; orbit.maxDistance = 35;
  orbit.maxPolarAngle = Math.PI * 0.49; orbit.target.set(0, 2, 0);
  const pmrem = new THREE.PMREMGenerator(renderer);
  const environmentScene = new RoomEnvironment();
  const environment = pmrem.fromScene(environmentScene, 0.05);
  scene.environment = environment.texture; scene.environmentIntensity = 0.65;
  environmentScene.dispose(); pmrem.dispose();
  const floorTexture = makeFloorTexture();
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(120, 120), new THREE.MeshStandardMaterial({
    map: floorTexture, roughness: 0.9, metalness: 0.04,
  }));
  floor.rotation.x = -Math.PI / 2; floor.position.y = -0.025; floor.receiveShadow = true; scene.add(floor);
  const grid = new THREE.GridHelper(40, 40, '#617489', '#455a6d');
  grid.material.transparent = true; grid.material.opacity = 0.12; grid.position.y = -0.022; scene.add(grid);
  const hemisphere = new THREE.HemisphereLight('#eaf6ff', '#19212e', 0.9); scene.add(hemisphere);
  const key = new THREE.DirectionalLight('#edf6ff', 2.2); key.position.set(5, 9, 6);
  key.castShadow = true; key.shadow.mapSize.set(2048, 2048);
  Object.assign(key.shadow.camera, { left: -11, right: 11, top: 12, bottom: -11, near: 0.1, far: 35 });
  key.shadow.bias = -0.00015; key.shadow.normalBias = 0.02; scene.add(key);
  const fill = new THREE.DirectionalLight('#8ebee8', 0.45); fill.position.set(-6, 5, -7); scene.add(fill);
  const blocker = new THREE.Mesh(new THREE.BoxGeometry(1.4, 2.3, 1.4),
    new THREE.MeshStandardMaterial({ color: '#748798', roughness: 0.65, metalness: 0.12 }));
  blocker.position.set(1.3, 1.15, 1.8); blocker.castShadow = true; blocker.receiveShadow = true;
  blocker.visible = false; scene.add(blocker);
  const composer = new EffectComposer(renderer);
  const renderPass = new RenderPass(scene, camera);
  const bloom = new UnrealBloomPass(new THREE.Vector2(1, 1), 0.55, 0.55, 1.25);
  const output = new OutputPass(); composer.addPass(renderPass); composer.addPass(bloom); composer.addPass(output);
  // The flame is a volume inside a box; box-surface depth alone cannot stop its
  // ray at a solid object inside that box. Supply opaque scene depth separately.
  const depthTarget = new THREE.WebGLRenderTarget(1, 1, {
    minFilter: THREE.NearestFilter, magFilter: THREE.NearestFilter,
    depthBuffer: true, stencilBuffer: false,
  });
  depthTarget.texture.generateMipmaps = false;
  depthTarget.depthTexture = new THREE.DepthTexture(1, 1, THREE.UnsignedIntType);
  const drawingBufferSize = new THREE.Vector2();

  let iceGltf = null, noiseTexture = null, recipes = null;
  let primary = null, duplicate = null, definition = null;
  let seconds = 0, speed = 1, scale = 1, overlap = false;
  let playing = !reducedMotion, running = true, raf = 0, last = performance.now(), disposed = false;
  let sizeObserver = null;
  const cleanup = () => {
    if (disposed) return; disposed = true; running = false; cancelAnimationFrame(raf);
    sizeObserver?.disconnect(); orbit.dispose(); primary?.dispose(); duplicate?.dispose();
    noiseTexture?.dispose(); floorTexture.dispose(); environment.dispose();
    const geometries = new Set(), materials = new Set(), textures = new Set();
    iceGltf?.scene.traverse((node) => {
      if (node.geometry) geometries.add(node.geometry);
      for (const material of Array.isArray(node.material) ? node.material : node.material ? [node.material] : []) {
        materials.add(material); Object.values(material).forEach((value) => { if (value?.isTexture) textures.add(value); });
      }
    });
    geometries.forEach((item) => item.dispose()); materials.forEach((item) => item.dispose()); textures.forEach((item) => item.dispose());
    floor.geometry.dispose(); floor.material.dispose(); grid.geometry.dispose(); grid.material.dispose();
    blocker.geometry.dispose(); blocker.material.dispose(); key.shadow.dispose();
    depthTarget.dispose(); bloom.dispose(); output.dispose(); composer.dispose(); renderer.dispose();
  };
  stop = cleanup;
  window.addEventListener('pagehide', cleanup, { once: true });
  renderer.domElement.addEventListener('webglcontextlost', (event) => {
    event.preventDefault(); fail('그래픽 연결이 중단되었습니다. 페이지를 새로고침해 주세요.');
  });
  // Surface shader failures in the page instead of pretending the effect worked.
  renderer.debug.onShaderError = (gl, program, vertex, fragment) => {
    const error = [gl.getProgramInfoLog(program), gl.getShaderInfoLog(vertex), gl.getShaderInfoLog(fragment)].filter(Boolean).join('\n');
    queueMicrotask(() => fail(`효과 셰이더 오류: ${error}`));
  };
  function setPlaying(value) {
    playing = value; $('play').textContent = value ? '일시정지' : '재생';
    $('play').setAttribute('aria-label', value ? '일시정지' : '재생');
  }
  function setCamera(id) {
    const positions = { perspective: [11, 8.5, 13], side: [17, 4, 0], rear: [-11, 8.5, -13], top: [0, 20, 0.001] };
    const ice = definition?.id === 'ice';
    const distance = ice ? 0.78 : 1, targetY = ice ? 1.7 : 2;
    const [x, y, z] = positions[id];
    camera.position.set(x * distance, targetY + (y - 2) * distance, z * distance);
    orbit.target.set(0, targetY, 0); orbit.update();
    $$('[data-camera]').forEach((button) => button.setAttribute('aria-pressed', String(button.dataset.camera === id)));
  }
  orbit.addEventListener('start', () => $$('[data-camera]').forEach((button) => button.setAttribute('aria-pressed', 'false')));
  function setBackground(id) {
    const light = id === 'light';
    const background = light ? '#b4c1ce' : '#101a27';
    scene.background = new THREE.Color(background); scene.fog = new THREE.Fog(background, 26, 60);
    floor.material.color.set(light ? '#aabac8' : '#283948');
    grid.material.opacity = light ? 0.20 : 0.12; $('stage').classList.toggle('light', light);
    $$('[data-background]').forEach((button) => button.setAttribute('aria-pressed', String(button.dataset.background === id)));
  }
  setBackground('dark'); setCamera('perspective');
  $$('[data-background]').forEach((button) => button.addEventListener('click', () => setBackground(button.dataset.background)));
  $$('[data-camera]').forEach((button) => button.addEventListener('click', () => setCamera(button.dataset.camera)));
  function bindSceneDepth() {
    primary?.setSceneDepth?.(depthTarget.depthTexture, drawingBufferSize.x, drawingBufferSize.y);
    duplicate?.setSceneDepth?.(depthTarget.depthTexture, drawingBufferSize.x, drawingBufferSize.y);
  }
  const resize = () => {
    const { width, height } = viewport.getBoundingClientRect(); if (!width || !height || disposed) return;
    camera.aspect = width / height; camera.updateProjectionMatrix();
    renderer.setSize(width, height, false); composer.setSize(width, height);
    renderer.getDrawingBufferSize(drawingBufferSize);
    depthTarget.setSize(drawingBufferSize.x, drawingBufferSize.y); bindSceneDepth();
  };
  sizeObserver = new ResizeObserver(resize); sizeObserver.observe(viewport); resize();
  const loaded = await Promise.allSettled([
    new GLTFLoader().loadAsync(config.resources.ice),
    new THREE.TextureLoader().loadAsync(config.resources.noise), readJson(config.resources.recipes),
  ]);
  // Keep successfully loaded resources available to cleanup when a sibling fails.
  iceGltf = loaded[0].status === 'fulfilled' ? loaded[0].value : null;
  noiseTexture = loaded[1].status === 'fulfilled' ? loaded[1].value : null;
  recipes = loaded[2].status === 'fulfilled' ? loaded[2].value : null;
  const failure = loaded.find((item) => item.status === 'rejected');
  if (failure) throw new Error(`제작 자료를 불러오지 못했습니다. ${failure.reason?.message ?? '파일 경로와 로컬 서버를 확인해 주세요.'}`);
  if (disposed) return;
  if (noiseTexture.image.width !== 512 || noiseTexture.image.height !== 512) {
    throw new Error('화염 밀도 아틀라스는 512 × 512 크기여야 합니다.');
  }
  noiseTexture.colorSpace = THREE.NoColorSpace;
  noiseTexture.wrapS = noiseTexture.wrapT = THREE.ClampToEdgeWrapping;
  noiseTexture.minFilter = noiseTexture.magFilter = THREE.LinearFilter; noiseTexture.generateMipmaps = false;

  function updateReference(id) {
    const reference = config.references[id];
    if (!reference?.image) throw new Error(`${id} 참고 이미지가 지정되지 않았습니다.`);
    $('reference-title').textContent = `${korean[id]}의 표현`;
    $('reference-image').src = reference.image; $('reference-image').alt = `${korean[id]}의 형태와 색감 참고 이미지`;
    const video = $('reference-video'); video.pause(); video.removeAttribute('src');
    if (reference.video) {
      video.src = reference.video; $('video-figure').hidden = false;
      $('video-note').textContent = '영상은 아래에서 별도로 재생할 수 있습니다. 참고의 흐름과 입체 결과를 비교해 보세요.';
    } else {
      $('video-figure').hidden = true; $('video-note').textContent = '이 예시에는 이미지 참고가 준비되어 있습니다.';
    }
    video.load();
  }
  function applySettings() {
    primary.group.scale.setScalar(scale); duplicate.group.scale.setScalar(scale * 0.76);
    primary.group.position.set(overlap ? 1.25 : 0, 0, 0);
    duplicate.group.position.set(-3.1, 0, -1.6);
    primary.setLayer('secondary', $('secondary').checked); duplicate.setLayer('secondary', $('secondary').checked);
  }
  function selectEffect(id) {
    const next = EFFECTS.find((effect) => effect.id === id);
    if (!next) throw new Error(`알 수 없는 효과: ${id}`);
    primary?.dispose(); duplicate?.dispose(); definition = next;
    primary = createEffect(id, { iceGltf, noiseTexture, recipes, seed: 17, scale: 1, speed: 1 });
    duplicate = createEffect(id, { iceGltf, noiseTexture, recipes, seed: 93, scale: 1, speed: 1 });
    scene.add(primary.group, duplicate.group); applySettings(); bindSceneDepth();
    seconds = playing ? 0 : next.moments[1].time;
    document.documentElement.style.setProperty('--accent', next.color);
    $('effect-eyebrow').textContent = `0${EFFECTS.indexOf(next) + 1} / ${id.toUpperCase()} STUDY`;
    $('effect-name').textContent = next.name; $('effect-subtitle').textContent = next.subtitle;
    $('effect-description').textContent = next.description;
    document.querySelector('.lab-tag').lastChild.textContent = ` 0${EFFECTS.indexOf(next) + 1} / 03`;
    $('scrub').max = String(primary.duration); $('duration').textContent = `${primary.duration.toFixed(2)} s`;
    $$('[data-effect]').forEach((button) => button.setAttribute('aria-pressed', String(button.dataset.effect === id)));
    $('moments').replaceChildren(...next.moments.map((moment) => {
      const button = document.createElement('button'); button.textContent = moment.label;
      button.dataset.time = String(moment.time); button.setAttribute('aria-pressed', 'false');
      const stamp = document.createElement('span'); stamp.textContent = `${moment.time.toFixed(2)}s`; button.append(stamp);
      button.addEventListener('click', () => { seconds = moment.time; setPlaying(false); }); return button;
    }));
    updateReference(id); setCamera('perspective');
  }
  $$('[data-effect]').forEach((button) => button.addEventListener('click', () => {
    try { selectEffect(button.dataset.effect); } catch (error) { fail(error.message); }
  }));
  $('play').addEventListener('click', () => {
    if (seconds >= primary.duration) seconds = 0; setPlaying(!playing);
  });
  $('restart').addEventListener('click', () => { seconds = 0; setPlaying(true); });
  $('scrub').addEventListener('input', (event) => { seconds = Number(event.target.value); setPlaying(false); });
  $('speed').addEventListener('change', (event) => { speed = Number(event.target.value); });
  $('scale').addEventListener('input', (event) => {
    scale = Number(event.target.value); $('scale-value').textContent = `${scale.toFixed(2)}×`; applySettings();
  });
  $('secondary').addEventListener('change', applySettings);
  $('overlap').addEventListener('change', (event) => { overlap = event.target.checked; applySettings(); });
  $('occluder').addEventListener('change', (event) => { blocker.visible = event.target.checked; });
  $('references').addEventListener('toggle', () => { if (!$('references').open) $('reference-video').pause(); });
  document.addEventListener('visibilitychange', () => { last = performance.now(); });
  selectEffect('fire'); setPlaying(playing);
  $('loading').hidden = true; $('controls').disabled = false;
  for (const node of [...$$('[data-effect]'), $('play'), $('restart'), $('scrub')]) node.disabled = false;
  function frame(now) {
    if (!running) return;
    try {
      const delta = Math.min((now - last) / 1000, 0.08); last = now;
      if (playing && !document.hidden) {
        seconds += delta * speed;
        if ($('repeat').checked) { if (seconds > primary.duration + 0.35) seconds %= primary.duration + 0.35; }
        else if (seconds >= primary.duration) { seconds = primary.duration; setPlaying(false); }
      }
      const time = Math.min(seconds, primary.duration);
      const state = primary.update(time);
      duplicate.update(overlap ? time >= primary.duration ? duplicate.duration : Math.max(0, time - 0.22) : 0);
      $('scrub').value = String(time); $('elapsed').textContent = `${time.toFixed(2)} s`;
      $('stage-phase').textContent = time >= primary.duration ? '종료' : phaseNames[state?.phase] ?? '전개';
      $$('[data-time]').forEach((button) => button.setAttribute('aria-pressed', String(!playing && Math.abs(Number(button.dataset.time) - time) < 0.015)));
      orbit.update();
      if (definition.id === 'fire') {
        const primaryVisible = primary.group.visible, duplicateVisible = duplicate.group.visible;
        const gridVisible = grid.visible, previousTarget = renderer.getRenderTarget();
        primary.group.visible = duplicate.group.visible = grid.visible = false;
        try {
          renderer.setRenderTarget(depthTarget); renderer.clear(); renderer.render(scene, camera);
        } finally {
          renderer.setRenderTarget(previousTarget);
          primary.group.visible = primaryVisible; duplicate.group.visible = duplicateVisible; grid.visible = gridVisible;
        }
      }
      composer.render(); raf = requestAnimationFrame(frame);
    } catch (error) { fail(error.message); }
  }
  raf = requestAnimationFrame(frame);
}

start().catch((error) => fail(error.message));

import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

const ui = Object.fromEntries(['status', 'stage', 'canvas', 'error', 'effects', 'effect-name', 'effect-subtitle', 'description', 'background', 'occluder', 'multiple', 'play', 'restart', 'loop', 'speed', 'seed', 'time', 'timeline', 'events', 'instances', 'fps', 'download'].map(id => [id, document.getElementById(id)]));
const INSTANCE_LIMIT = 12000;
let context, renderer, scene, camera, controls, ground, grid, occluder, manifest;
let active = null, handles = [], elapsed = 0, running = true, ready = false, last = 0, accumulator = 0;
let frames = 0, fpsTime = 0, raf = 0;
const resources = new Map();
const projection = new Float32Array(16), view = new Float32Array(16);

function failure(error) {
  running = false;
  ready = false;
  cancelAnimationFrame(raf);
  ui.error.hidden = false;
  ui.error.textContent = `미리보기를 시작하지 못했습니다.\n${error.message || error}\n\n런타임·효과 파일 경로와 브라우저 WebGL 지원을 확인하세요.`;
  ui.status.textContent = '불러오기 실패';
  ui.status.style.color = '#ee969e';
  console.error(error);
}

function setupScene() {
  renderer = new THREE.WebGLRenderer({ canvas: ui.canvas, antialias: true, alpha: false, powerPreference: 'low-power' });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  scene = new THREE.Scene();
  camera = new THREE.PerspectiveCamera(42, 1, 0.1, 300);
  camera.position.set(11, 8, 15);
  controls = new OrbitControls(camera, ui.canvas);
  controls.target.set(0, 1.5, 0);
  controls.enableDamping = true;
  controls.minDistance = 3;
  controls.maxDistance = 65;
  controls.maxPolarAngle = Math.PI * 0.49;
  controls.addEventListener('start', () => document.querySelectorAll('[data-view]').forEach(button => button.classList.remove('selected')));
  scene.add(new THREE.HemisphereLight(0xd9e5ff, 0x373645, 2.0));
  const sun = new THREE.DirectionalLight(0xfff3e5, 2.2);
  sun.position.set(4, 10, 6);
  scene.add(sun);
  ground = new THREE.Mesh(new THREE.PlaneGeometry(200, 200), new THREE.MeshStandardMaterial({ color: 0x151921, roughness: 0.88 }));
  ground.rotation.x = -Math.PI / 2;
  ground.position.y = -0.035;
  scene.add(ground);
  grid = new THREE.GridHelper(40, 40, 0x434857, 0x262d3a);
  grid.position.y = -0.025;
  grid.material.transparent = true;
  grid.material.opacity = 0.6;
  scene.add(grid);
  occluder = new THREE.Mesh(new THREE.BoxGeometry(1.7, 3.2, 1.2), new THREE.MeshStandardMaterial({ color: 0x555c6f, roughness: 0.72, metalness: 0.15 }));
  occluder.position.set(0, 1.6, 2.5);
  occluder.visible = false;
  scene.add(occluder);
  applyBackground();
  const resize = () => {
    const { width, height } = ui.stage.getBoundingClientRect();
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
  };
  new ResizeObserver(resize).observe(ui.stage);
  resize();
}

function applyBackground() {
  const light = ui.background.value === 'light';
  scene.background = new THREE.Color(light ? 0xd5d6cf : 0x151820);
  scene.fog = new THREE.Fog(scene.background, 24, 95);
  ground.material.color.setHex(light ? 0xb9bcb4 : 0x151921);
  grid.material.opacity = light ? 0.28 : 0.6;
  ui.stage.parentElement.classList.toggle('light-stage', light);
}

function makeHandles() {
  context.stopAll();
  handles = [];
  const origin = active.position || [0, 0, 0];
  const seed = Math.max(1, Math.min(2147483647, Number(ui.seed.value) || 42));
  ui.seed.value = seed;
  const offsets = ui.multiple.checked ? [-4, 0, 4] : [0];
  for (const [i, offset] of offsets.entries()) {
    const handle = context.play(resources.get(active.id), origin[0] + offset, origin[1], origin[2]);
    if (!handle) throw new Error('효과 인스턴스를 만들 수 없습니다.');
    handle.setRandomSeed(seed + i);
    const scale = active.scale ?? 1;
    handle.setScale(scale, scale, scale);
    handle.setRotation(...(active.rotation || [0, 0, 0]));
    handles.push(handle);
  }
}

function restart() {
  if (!ready) return;
  makeHandles();
  elapsed = 0;
  accumulator = 0;
  context.update(0);
  updateTimeline();
}

function seek(seconds) {
  if (!ready) return;
  running = false;
  makeHandles();
  elapsed = Math.min(active.duration, Math.max(0, seconds));
  for (const handle of handles) handle.setFrame(elapsed * 60);
  accumulator = 0;
  updateTimeline();
}

function updateTimeline() {
  ui.timeline.value = elapsed;
  ui.time.textContent = `${elapsed.toFixed(2)} / ${active.duration.toFixed(2)} s`;
  ui.play.textContent = running ? '일시정지' : '재생';
}

function selectEffect(effect) {
  active = effect;
  document.documentElement.style.setProperty('--accent', effect.color || '#ffa769');
  for (const card of ui.effects.children) {
    card.classList.toggle('active', card.dataset.id === effect.id);
    card.setAttribute('aria-pressed', String(card.dataset.id === effect.id));
  }
  ui['effect-name'].textContent = effect.name;
  ui['effect-subtitle'].textContent = effect.subtitle || effect.id.toUpperCase();
  ui.description.textContent = effect.description || '';
  ui.seed.value = effect.seed || 42;
  ui.timeline.max = effect.duration;
  ui.events.replaceChildren();
  for (const event of effect.events || []) {
    const button = document.createElement('button');
    button.textContent = `${event.time.toFixed(2)}s · ${event.label}`;
    button.addEventListener('click', () => seek(event.time));
    ui.events.append(button);
  }
  ui.download.href = effect.url;
  ui.download.download = effect.url.split('/').pop();
  ui.download.hidden = false;
  running = true;
  restart();
  setView('perspective');
}

function setView(name) {
  const target = new THREE.Vector3(...(active?.cameraTarget || [0, 1.5, 0]));
  const distance = active?.cameraDistance || 18;
  const directions = { perspective: [0.65, 0.43, 0.88], front: [0, 0.1, 1], side: [1, 0.1, 0], back: [0, 0.1, -1], top: [0, 1, 0.001] };
  camera.position.copy(target).add(new THREE.Vector3(...directions[name]).normalize().multiplyScalar(distance));
  controls.target.copy(target);
  controls.update();
  for (const button of document.querySelectorAll('[data-view]')) button.classList.toggle('selected', button.dataset.view === name);
}

function frame(now) {
  raf = requestAnimationFrame(frame);
  try {
    const delta = last ? Math.min((now - last) / 1000, 0.1) : 0;
    last = now;
    if (ready && running && !document.hidden) {
      accumulator += delta * Number(ui.speed.value);
      while (accumulator >= 1 / 60) {
        context.update(1);
        elapsed += 1 / 60;
        accumulator -= 1 / 60;
        if (elapsed >= active.duration) {
          if (ui.loop.checked) restart();
          else { elapsed = active.duration; running = false; accumulator = 0; }
          break;
        }
      }
      updateTimeline();
    }
    controls.update();
    renderer.render(scene, camera);
    projection.set(camera.projectionMatrix.elements);
    view.set(camera.matrixWorldInverse.elements);
    context.setProjectionMatrix(projection);
    context.setCameraMatrix(view);
    context.draw();
    renderer.resetState();
    frames++;
    fpsTime += delta;
    if (fpsTime >= 0.5) {
      ui.fps.textContent = `${Math.round(frames / fpsTime)} FPS`;
      ui.instances.textContent = `활성 인스턴스 ${(INSTANCE_LIMIT - context.getRestInstancesCount()).toLocaleString()}`;
      frames = 0;
      fpsTime = 0;
    }
  } catch (error) { failure(error); }
}

async function main() {
  const response = await fetch('./effects.json');
  if (!response.ok) throw new Error(`effects.json HTTP ${response.status}`);
  manifest = await response.json();
  if (manifest.version !== 1 || !manifest.effects?.length) throw new Error('효과 목록이 비어 있습니다.');
  if (!window.effekseer?.initRuntime) throw new Error('Effekseer JavaScript 런타임이 없습니다.');
  setupScene();
  ui.canvas.addEventListener('webglcontextlost', event => { event.preventDefault(); failure(new Error('WebGL 컨텍스트가 중단되었습니다. 다른 그래픽 작업을 확인하고 페이지를 새로 고치세요.')); });
  await new Promise((resolve, reject) => window.effekseer.initRuntime('./runtime/effekseer.wasm', resolve, () => reject(new Error('Effekseer WASM 초기화 실패'))));
  context = window.effekseer.createContext();
  context.init(renderer.getContext(), { instanceMaxCount: INSTANCE_LIMIT, squareMaxCount: 16000, enableExtensionsByDefault: true });
  context.setRestorationOfStatesFlag(false);
  for (const effect of manifest.effects) {
    ui.status.textContent = `${effect.name} 불러오는 중`;
    await new Promise((resolve, reject) => {
      const resource = context.loadEffect(effect.url, 1, () => { resources.set(effect.id, resource); resolve(); }, (reason, resourcePath) => reject(new Error(`${effect.name}: ${reason} (${resourcePath})`)));
    });
    const button = document.createElement('button');
    button.className = 'effect-card';
    button.dataset.id = effect.id;
    button.style.setProperty('--card-color', effect.color || '#ffa769');
    const icon = document.createElement('span'); icon.className = 'effect-icon'; icon.textContent = effect.icon || ['✦', '❖', 'ϟ', '◈'][ui.effects.children.length % 4];
    const labels = document.createElement('span');
    const name = document.createElement('span'); name.className = 'effect-title'; name.textContent = effect.name;
    const code = document.createElement('span'); code.className = 'effect-code'; code.textContent = effect.subtitle || effect.id.toUpperCase();
    labels.append(name, code);
    const ordinal = document.createElement('span'); ordinal.className = 'ordinal'; ordinal.textContent = String(ui.effects.children.length + 1).padStart(2, '0');
    button.append(icon, labels, ordinal);
    button.addEventListener('click', () => selectEffect(effect));
    ui.effects.append(button);
  }
  ready = true;
  renderer.resetState();
  ui.play.disabled = ui.restart.disabled = ui.timeline.disabled = false;
  selectEffect(manifest.effects[0]);
  ui.status.textContent = `Effekseer 1.80.7 · ${manifest.effects.length}개 효과 준비됨`;
  ui.play.addEventListener('click', () => { if (elapsed >= active.duration) restart(); running = !running; updateTimeline(); });
  ui.restart.addEventListener('click', () => { running = true; restart(); });
  ui.timeline.addEventListener('input', () => seek(Number(ui.timeline.value)));
  ui.background.addEventListener('change', applyBackground);
  ui.occluder.addEventListener('change', () => { occluder.visible = ui.occluder.checked; });
  ui.multiple.addEventListener('change', restart);
  ui.seed.addEventListener('change', restart);
  document.querySelectorAll('[data-view]').forEach(button => button.addEventListener('click', () => setView(button.dataset.view)));
  document.addEventListener('visibilitychange', () => { last = 0; });
  window.addEventListener('pagehide', () => { cancelAnimationFrame(raf); context.stopAll(); for (const resource of resources.values()) context.releaseEffect(resource); window.effekseer.releaseContext(context); renderer.dispose(); });
  raf = requestAnimationFrame(frame);
}

main().catch(failure);

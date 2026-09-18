import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { createArcanePulse } from './effect.js';
import { createSoulFlame } from './soul-effect.js';

const $ = (selector) => document.querySelector(selector);
const viewport = $('#viewport');
const error = $('#error');
function reportError(message) { error.hidden = false; error.textContent = message; }
start().catch((e) => reportError(`미리보기를 시작하지 못했습니다: ${e.message}`));

async function start() {
  const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.domElement.setAttribute('aria-label', '비전 충격파 3D 렌더');
  viewport.append(renderer.domElement);
  renderer.domElement.addEventListener('webglcontextlost', (event) => {
    event.preventDefault(); playing = false;
    reportError('그래픽 컨텍스트가 중단되었습니다. 페이지를 새로고침해 주세요.');
  });
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(40, 1, 0.05, 100);
  camera.position.set(8, 6.7, 9);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.target.set(0, 0.45, 0);
  controls.enableDamping = true;
  controls.minDistance = 4; controls.maxDistance = 24;
  controls.maxPolarAngle = Math.PI * 0.485;
  controls.update();
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(200, 200), new THREE.MeshBasicMaterial());
  floor.rotation.x = -Math.PI / 2;
  floor.position.y = -0.015;
  scene.add(floor);
  const grid = new THREE.GridHelper(40, 40, '#2c4352', '#223643');
  grid.material.transparent = true; grid.material.opacity = 0.44;
  scene.add(grid);
  const blocker = new THREE.Mesh(new THREE.BoxGeometry(1.2, 1.55, 1.2),
    new THREE.MeshStandardMaterial({ color: '#647c8c', roughness: 0.8 }));
  blocker.position.set(0.75, 0.775, 1.25); blocker.visible = false; scene.add(blocker);
  scene.add(new THREE.HemisphereLight('#e9f9ff', '#293444', 2));
  const key = new THREE.DirectionalLight('#d2fcf2', 2); key.position.set(4, 7, 5); scene.add(key);
  const effect = createArcanePulse(); scene.add(effect.group);
  const secondary = createArcanePulse({ seed: 91, color: '#a9a1ff' });
  secondary.group.position.set(-1.9, 0, -0.7); secondary.group.scale.setScalar(0.7);
  scene.add(secondary.group);
  const modes = { pulse: { effect, secondary, title: 'Arcane Pulse', subtitle: '비전 충격파',
    method: 'PROCEDURAL STUDY', description: '응축된 빛이 퍼지는 순간.', target: 0.45,
    moments: [0.30, 0.56, 1.05, 1.90], labels: ['응축', '방출', '확산', '소멸'],
    layers: { ring: '파동 · Ring', crown: '잔광 · Crown', core: '광원핵 · Core', sparks: '불티 · Sparks' } } };
  let active = modes.pulse;
  let atlas = null;
  let overlapping = false;
  let time = 0;
  let playing = !matchMedia('(prefers-reduced-motion: reduce)').matches;
  let previous = performance.now();
  let frame = 0;
  const phases = { ready: '준비', charge: '응축', impact: '방출', expand: '확산', sustain: '흐름', fade: '소멸', finished: '종료' };
  const setPlaying = (value) => { playing = value; $('#play').textContent = playing ? '일시정지' : '재생'; };
  setPlaying(playing);
  if (!playing) time = 0.56;
  function setBackground(value) {
    const light = value === 'light';
    const color = light ? '#c9d9dd' : '#101d28';
    scene.background = new THREE.Color(color);
    scene.fog = new THREE.Fog(color, 14, 32);
    floor.material.color.set(color);
    grid.material.color.set(light ? '#637e8a' : '#8cb6c6');
    $('.stage').classList.toggle('light', light);
    document.querySelectorAll('[data-background]').forEach((button) => {
      button.setAttribute('aria-pressed', String(button.dataset.background === value));
    });
  }
  setBackground('dark');
  $('#play').onclick = () => { if (time >= active.effect.duration) time = 0; setPlaying(!playing); };
  $('#replay').onclick = () => { time = 0; setPlaying(true); };
  $('#scrub').oninput = (event) => { time = Number(event.target.value); setPlaying(false); };
  $('#overlap').onchange = (event) => { overlapping = event.target.checked; };
  $('#occluder').onchange = (event) => { blocker.visible = event.target.checked; };
  document.querySelectorAll('[data-time]').forEach((button) => {
    button.onclick = () => { time = Number(button.dataset.time); setPlaying(false); };
  });
  document.querySelectorAll('[data-background]').forEach((button) => {
    button.onclick = () => setBackground(button.dataset.background);
  });
  function selectEffect(name) {
    active.effect.update(0); active.secondary.update(0);
    active = modes[name];
    $('#effect').value = name;
    time = playing ? 0 : active.moments[1];
    $('#scrub').max = String(active.effect.duration);
    $('#effect-title').innerHTML = `${active.title}<span>${active.subtitle}</span>`;
    $('#effect-description').textContent = active.description;
    $('#effect-method').textContent = active.method;
    renderer.domElement.setAttribute('aria-label', `${active.subtitle} 3D 렌더`);
    document.querySelectorAll('[data-time]').forEach((button, index) => {
      button.dataset.time = String(active.moments[index]);
      button.innerHTML = `0${index + 1} <span>${active.labels[index]}</span>`;
    });
    $('#layers').replaceChildren();
    for (const [layer, label] of Object.entries(active.layers)) {
      active.effect.setLayer(layer, true); active.secondary.setLayer(layer, true);
      const row = document.createElement('label'); row.className = 'row';
      const text = document.createElement('span'); text.textContent = label;
      const input = document.createElement('input'); input.type = 'checkbox'; input.checked = true;
      input.onchange = () => { active.effect.setLayer(layer, input.checked); active.secondary.setLayer(layer, input.checked); };
      row.append(text, input); $('#layers').append(row);
    }
    controls.target.set(0, active.target, 0); controls.update();
  }
  $('#effect').onchange = () => selectEffect($('#effect').value);
  selectEffect('pulse');
  document.querySelectorAll('[data-camera]').forEach((button) => {
    button.onclick = () => {
      const position = { perspective: [8, 6.7, 9], side: [0, 2.1, 12], top: [0, 12, 0.01] }[button.dataset.camera];
      camera.position.set(...position); controls.target.set(0, active.target, 0); controls.update();
      document.querySelectorAll('[data-camera]').forEach((b) => b.setAttribute('aria-pressed', String(b === button)));
    };
  });
  renderer.domElement.addEventListener('pointerdown', () => {
    document.querySelectorAll('[data-camera]').forEach((button) => button.setAttribute('aria-pressed', 'false'));
  });
  const resize = new ResizeObserver(() => {
    const { width, height } = viewport.getBoundingClientRect();
    renderer.setSize(width, height, false); camera.aspect = width / Math.max(height, 1); camera.updateProjectionMatrix();
  });
  resize.observe(viewport);
  document.addEventListener('visibilitychange', () => { previous = performance.now(); });
  renderer.setAnimationLoop((now) => {
    const dt = Math.min(0.1, (now - previous) / 1000); previous = now;
    if (playing && !document.hidden) {
      time += dt * Number($('#speed').value);
      if (time >= active.effect.duration) {
        if ($('#loop').checked) time %= active.effect.duration;
        else { time = active.effect.duration; setPlaying(false); }
      }
    }
    const state = active.effect.update(time);
    active.secondary.update(overlapping ? time - 0.14 : 0);
    controls.update(); renderer.render(scene, camera);
    $('#scrub').value = String(time);
    $('#time').innerHTML = `${time.toFixed(2)} <span>/ ${active.effect.duration.toFixed(2)} s</span>`;
    $('#phase').textContent = phases[state.phase];
    if (frame++ % 20 === 0) $('#render-status').textContent = `${renderer.info.render.calls} draw calls · ${overlapping ? 2 : 1} effect`;
  });
  window.addEventListener('pagehide', (event) => {
    if (event.persisted) return;
    renderer.setAnimationLoop(null); resize.disconnect(); controls.dispose();
    for (const mode of Object.values(modes)) { mode.effect.dispose(); mode.secondary.dispose(); }
    atlas?.dispose();
    for (const object of [floor, blocker, grid]) { object.geometry.dispose(); object.material.dispose(); }
    renderer.dispose();
  });
  const response = await fetch('config.json');
  if (!response.ok) throw new Error('효과 설정 파일을 불러오지 못했습니다. 예제를 다시 빌드해 주세요.');
  const config = await response.json();
  if (config.soul) {
    atlas = await new THREE.TextureLoader().loadAsync(config.soul.atlas);
    atlas.colorSpace = THREE.SRGBColorSpace;
    atlas.generateMipmaps = false;
    atlas.minFilter = THREE.LinearFilter; atlas.magFilter = THREE.LinearFilter;
    const soul = createSoulFlame({ texture: atlas, ...config.soul });
    const secondSoul = createSoulFlame({ texture: atlas, ...config.soul });
    secondSoul.group.position.set(-2.1, 0, -0.6); secondSoul.group.scale.setScalar(0.68);
    scene.add(soul.group, secondSoul.group);
    modes.soul = { effect: soul, secondary: secondSoul, title: 'Soul Fire', subtitle: '영혼 불꽃',
      method: 'IMAGEGEN → GROK → FLIPBOOK', description: '갈라지는 청록의 불길, 보랏빛 잔영.', target: 1.6,
      moments: [0.6, 1.8, 3.3, 5.65], labels: ['현현', '상승', '흐름', '잔광'],
      layers: { body: '불길 · Generated flipbook', halo: '바닥 잔광 · Halo' } };
    $('#effect option[value="soul"]').disabled = false;
    $('#reference-image').src = config.soul.image;
    $('#reference-video').src = config.soul.video;
    $('#references').hidden = false;
    selectEffect('soul');
  }
}

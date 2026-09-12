import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import './style.css';

const $ = (id) => document.getElementById(id);
const viewport = $('viewport');
const scene = new THREE.Scene();
scene.background = new THREE.Color('#202733');
const camera = new THREE.PerspectiveCamera(38, 1, 0.001, 10000);
const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: false });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.2;
viewport.appendChild(renderer.domElement);
renderer.domElement.setAttribute('aria-label', '3D 에셋 미리보기');
const pmrem = new THREE.PMREMGenerator(renderer);
const room = new RoomEnvironment();
scene.environment = pmrem.fromScene(room, 0.04).texture;
room.dispose(); pmrem.dispose();
scene.add(new THREE.HemisphereLight(0xd9efff, 0x566075, 2));
const key = new THREE.DirectionalLight(0xfff0d6, 3); key.position.set(4, 7, 5); scene.add(key);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.autoRotateSpeed = 1.3;
let grid = new THREE.GridHelper(4, 20, 0x536579, 0x354252); scene.add(grid);
let model, current, entries = [], serial = 0, fit = 1;
const loader = new GLTFLoader();
const fileURL = (item, name) => `/assets/${encodeURIComponent(item.asset_id)}/${encodeURIComponent(item.revision)}/${name}`;
const text = (id, value) => { $(id).textContent = value; };
const errorMessage = (error) => error instanceof TypeError && /failed to fetch|networkerror|load failed/i.test(error.message)
  ? '로컬 서버에 연결할 수 없습니다. 프로젝트 폴더의 start-viewer.cmd를 실행한 뒤 목록 새로고침을 눌러 주세요.'
  : String(error.message);

new ResizeObserver(() => {
  const { width, height } = viewport.getBoundingClientRect();
  renderer.setSize(width, height); camera.aspect = width / height; camera.updateProjectionMatrix();
}).observe(viewport);
renderer.setAnimationLoop(() => { controls.update(); renderer.render(scene, camera); });

function resetView() {
  if (!model) return;
  const box = new THREE.Box3().setFromObject(model);
  const center = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3());
  fit = Math.max(size.x, size.y, size.z);
  controls.target.copy(center);
  camera.position.copy(center).add(new THREE.Vector3(1.1, .6, 1.9).multiplyScalar(fit));
  camera.near = Math.max(fit / 1000, .0001); camera.far = fit * 100;
  camera.updateProjectionMatrix();
  controls.minDistance = fit * .1; controls.maxDistance = fit * 15;
  scene.remove(grid); grid.geometry.dispose(); grid.material.dispose();
  grid = new THREE.GridHelper(fit * 3, 20, 0x536579, 0x354252);
  grid.position.set(center.x, box.min.y - fit * .003, center.z);
  grid.visible = $('grid').checked; scene.add(grid);
  controls.update();
}
function dispose(object) {
  object.traverse(n => { if (n.isMesh) { n.geometry.dispose();
    for (const m of (Array.isArray(n.material) ? n.material : [n.material])) {
      for (const v of Object.values(m)) if (v?.isTexture) v.dispose(); m.dispose();
    }
  }});
}
function wireframe() {
  model?.traverse(n => { if(n.isMesh) for(const m of (Array.isArray(n.material)?n.material:[n.material])) m.wireframe=$('wireframe').checked; });
}
function badge(label, state, value) {
  const row = document.createElement('div'); row.className = 'check';
  const title = document.createElement('span'); title.textContent = label;
  const tag = document.createElement('span'); tag.className = `badge ${state}`; tag.textContent = value;
  row.append(title, tag); return row;
}
function metadata(item) {
  text('asset-name', item.asset_id); text('provider', `${item.provider.toUpperCase()} / STATIC MESH`);
  text('triangles', item.inspection.triangles.toLocaleString());
  // Stored Blender dimensions are Z-up; display the exported glTF Y-up ordering.
  const d = item.inspection.dimensions;
  text('dimensions', [d[0], d[2], d[1]].map(n => n.toFixed(3)).join(' · ') + ' m');
  text('parts-count', item.inspection.parts.length);
  $('download').href=fileURL(item,'asset.glb'); $('download').download=`${item.asset_id}.glb`; $('download').classList.remove('disabled');
  $('part-list').replaceChildren(...item.inspection.parts.map(p => {
    const el=document.createElement('div'); el.className='part';
    const name=document.createElement('span'); name.textContent=p.name;
    const count=document.createElement('small'); count.textContent=p.triangles.toLocaleString(); el.append(name,count); return el;
  }));
  const notes=[...item.inspection.errors,...item.inspection.warnings];
  if(item.review?.notes) notes.push(`시각 검토: ${item.review.notes}`);
  $('warnings').replaceChildren(...(notes.length?notes:['수치 검사에서 발견된 문제가 없습니다.']).map(n=>{
    const p=document.createElement('p');p.textContent=n;return p;
  }));
  $('checks').replaceChildren(
    badge('메시 수치 검사',item.inspection.passed?'good':'pending',item.inspection.passed?'통과':'수정 필요'),
    badge('Godot 가져오기',item.godot?.passed?'good':'pending',item.godot?.passed?'통과':'미검증'),
    badge('시각 검토',item.review?.passed?'good':'pending',item.review?item.review.passed?'통과':'수정 필요':'미검토')
  );
  text('edit-note',item.edits?.description || item.prompt);
  $('renders').replaceChildren(...item.renders.map(name=>{
    const a=document.createElement('a');a.href=fileURL(item,name);a.target='_blank';a.rel='noopener';
    const img=document.createElement('img');img.src=a.href;img.alt=name.replace('.png','')+' 렌더';
    const span=document.createElement('span');span.textContent=name.replace('.png','');a.append(img,span);return a;
  }));
}
async function selectRevision(item) {
  current=item; const ticket=++serial;
  $('loading').classList.remove('hidden');text('loading','3D 모델을 불러오고 있습니다.');text('web-status','불러오는 중');
  viewport.dataset.loaded='false'; metadata(item);
  try {
    const gltf=await loader.loadAsync(fileURL(item,'asset.glb'));
    if(ticket!==serial){dispose(gltf.scene);return;}
    if(model){scene.remove(model);dispose(model);}
    model=gltf.scene;scene.add(model);wireframe();resetView();
    let meshes=0, triangles=0;
    model.traverse(n=>{if(n.isMesh){meshes++;triangles+=(n.geometry.index?.count ?? n.geometry.attributes.position.count)/3;}});
    if(!meshes||!triangles) throw Error('표시 가능한 메시가 없습니다.');
    renderer.render(scene,camera);
    const drawCalls=renderer.info.render.calls;
    if(!drawCalls||renderer.getContext().isContextLost()) throw Error('WebGL 렌더링에 실패했습니다.');
    viewport.dataset.loaded='true';viewport.dataset.meshes=String(meshes);viewport.dataset.triangles=String(triangles);
    viewport.dataset.asset=item.asset_id;viewport.dataset.revision=item.revision;
    text('web-status','로드 · 렌더 통과');$('loading').classList.add('hidden');
    // Saving a report must not turn a successful model render into a load failure.
    try {
      const report=await fetch(`/api/assets/${item.asset_id}/${item.revision}/browser-report`,{method:'POST',
        headers:{'Content-Type':'application/json'},body:JSON.stringify({meshes,triangles,draw_calls:drawCalls,three_version:THREE.REVISION})});
      if(ticket===serial&&!report.ok) text('web-status','렌더 통과 · 기록 실패');
    } catch(error) {
      if(ticket===serial) text('web-status','렌더 통과 · 기록 연결 끊김');
      console.warn('Browser report could not be saved',error);
    }
  } catch(error) {
    if(ticket!==serial)return;
    text('web-status','로드 실패');text('loading',errorMessage(error));$('loading').classList.remove('hidden');
    console.error(error);
  }
}
function selectAsset(id) {
  const versions=entries.filter(x=>x.asset_id===id);
  $('revision').replaceChildren(...versions.map((v,i)=>{const option=document.createElement('option');option.value=v.revision;
    option.textContent=`${i===0?'최신 · ':''}${new Date(v.created_at).toLocaleString('ko-KR')}`;return option;}));
  document.querySelectorAll('.asset-card').forEach(card=>card.classList.toggle('selected',card.dataset.id===id));
  if(versions.length) selectRevision(versions[0]);
}
async function refresh() {
  try {
    const response=await fetch('/api/assets');if(!response.ok)throw Error('에셋 목록을 불러올 수 없습니다.');entries=await response.json();
    const ids=[...new Set(entries.map(x=>x.asset_id))];text('asset-count',ids.length);
    $('library').replaceChildren(...ids.map(id=>{const item=entries.find(x=>x.asset_id===id);const card=document.createElement('button');
      card.className='asset-card';card.dataset.id=id;const image=document.createElement('img');image.src=fileURL(item,'perspective.png');image.alt='';
      const name=document.createElement('strong');name.textContent=id;const info=document.createElement('small');
      info.textContent=`${entries.filter(x=>x.asset_id===id).length}개 버전 · ${item.provider}`;card.append(image,name,info);card.onclick=()=>selectAsset(id);return card;}));
    if(ids.length)selectAsset(current&&ids.includes(current.asset_id)?current.asset_id:ids[0]);
    else text('loading','아직 생성된 에셋이 없습니다. 에셋을 생성한 뒤 목록을 새로고침하세요.');
  }catch(error){text('loading',errorMessage(error));$('loading').classList.remove('hidden');}
}
$('refresh').onclick=refresh;$('reset').onclick=resetView;$('wireframe').onchange=wireframe;
$('rotate').onchange=()=>{controls.autoRotate=$('rotate').checked;};$('grid').onchange=()=>{grid.visible=$('grid').checked;};
$('revision').onchange=()=>selectRevision(entries.find(x=>x.asset_id===current.asset_id&&x.revision===$('revision').value));
refresh();

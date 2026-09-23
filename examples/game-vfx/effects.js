import * as THREE from 'three';

// The main effects occupy world space. Textures provide density/detail; none of
// the main effects is a camera-facing video. Time is absolute and seekable.
export const EFFECTS = [
  { id: 'fire', name: 'Cinder Vortex', subtitle: '회오리 화염', duration: 4.8, impact: 1.25,
    color: '#ff8647', description: '분출한 불길이 크게 감겨 올라가며, 갈라지는 화염과 냉각되는 불티를 남깁니다.',
    moments: [{ label: '분출', time: 1.55 }, { label: '회오리', time: 2.10 }, { label: '상승', time: 2.75 }, { label: '잔열', time: 3.70 }] },
  { id: 'ice', name: 'Glacier Barrage', subtitle: '빙하 연쇄 낙하', duration: 5.4, impact: 1.9,
    color: '#8adfff', description: '생성한 얼음 모델이 시간차로 떨어져 실제 입체 파편으로 부서집니다.',
    moments: [{ label: '낙하', time: 1.1 }, { label: '충돌', time: 2.05 }, { label: '연쇄', time: 2.5 }, { label: '서리', time: 3.55 }] },
  { id: 'lightning', name: 'Storm Verdict', subtitle: '분기 낙뢰', duration: 4.4, impact: 1.7,
    color: '#ada7ff', description: '상공에서 내려오는 분기 전류가 지면에 닿아 여러 방향으로 흩어집니다.',
    moments: [{ label: '집전', time: 1.45 }, { label: '낙뢰', time: 1.78 }, { label: '재방전', time: 2.23 }, { label: '잔류', time: 2.85 }] },
];

import { resources, clamp } from './common.js';
import { createFire } from './fire.js';
import { createIce } from './ice.js';
import { createLightning } from './lightning.js';

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
  // Public event times use the same seconds as update(). Source-file times
  // and effect-local positions retain their original units and coordinate frame.
  const stats = structuredClone(effect.stats);
  stats.events?.forEach((event) => {
    event.time /= speed;
    if (event.cleanupEnd !== undefined) event.cleanupEnd /= speed;
  });
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
  return { group, duration, impact, update, stats,
    setSceneDepth(texture, width, height) { if (disposed) throw new Error('Effect is disposed'); effect.setSceneDepth?.(texture, width, height); },
    setLayer(name, visible) { if (!(name in layers)) throw new Error(`Unknown layer: ${name}`);
      layers[name] = Boolean(visible); effect[name].visible = layers[name]; },
    dispose() { if (disposed) return; disposed = true; group.removeFromParent(); effect.cleanup?.(); owned.dispose(); },
  };
}

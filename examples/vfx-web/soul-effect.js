import * as THREE from 'three';

export function flipbookFrame(time, { frames, fps }) {
  if (!Number.isFinite(time) || !Number.isInteger(frames) || frames < 1 || !(fps > 0) || !Number.isFinite(fps)) {
    throw new TypeError('Expected finite seconds, a positive frame count and finite positive FPS');
  }
  const position = Math.max(0, Math.min(frames - 1, time * fps));
  return { first: Math.floor(position), next: Math.min(frames - 1, Math.floor(position) + 1), mix: position % 1 };
}

// The caller owns the supplied texture; instances own only their geometry/materials.
export function createSoulFlame({ texture, columns = 8, rows = 12, frames = 96, fps = 16 } = {}) {
  if (!texture?.isTexture || !Number.isInteger(columns) || !Number.isInteger(rows) || columns < 1 || rows < 1
    || !Number.isInteger(frames) || frames < 1 || frames > columns * rows || !Number.isFinite(fps) || fps <= 0) {
    throw new TypeError('A texture and valid atlas dimensions/timing are required');
  }
  const duration = frames / fps;
  const group = new THREE.Group(); group.name = 'SoulFlame';
  const bodyMaterial = new THREE.ShaderMaterial({
    transparent: true, depthWrite: false, toneMapped: false, side: THREE.DoubleSide,
    uniforms: { uMap: { value: texture }, uGrid: { value: new THREE.Vector2(columns, rows) },
      uFrames: { value: new THREE.Vector3(0, 1, 0) }, uAlpha: { value: 0 },
      uTexel: { value: new THREE.Vector2(1 / texture.image.width, 1 / texture.image.height) } },
    vertexShader: `varying vec2 vUv;
      void main(){ vUv=uv;
        vec4 center=modelViewMatrix*vec4(0.0,0.0,0.0,1.0);
        vec2 scale=vec2(length(modelMatrix[0].xyz),length(modelMatrix[1].xyz));
        center.xy+=position.xy*scale;
        gl_Position=projectionMatrix*center;
      }`,
    fragmentShader: `uniform sampler2D uMap; uniform vec2 uGrid,uTexel;
      uniform vec3 uFrames; uniform float uAlpha; varying vec2 vUv;
      vec4 readFrame(float frame){
        vec2 cell=vec2(mod(frame,uGrid.x),uGrid.y-1.0-floor(frame/uGrid.x));
        vec2 uv=(cell+vUv)/uGrid;
        vec2 low=cell/uGrid+uTexel*0.5, high=(cell+1.0)/uGrid-uTexel*0.5;
        return texture2D(uMap,clamp(uv,low,high));
      }
      void main(){
        vec3 rgb=mix(readFrame(uFrames.x).rgb,readFrame(uFrames.y).rgb,uFrames.z);
        float brightness=max(rgb.r,max(rgb.g,rgb.b));
        float alpha=smoothstep(0.003,0.065,brightness)*sqrt(max(brightness,0.0));
        float border=smoothstep(0.0,0.025,min(min(vUv.x,1.0-vUv.x),min(vUv.y,1.0-vUv.y)));
        if(alpha<0.002)discard;
        // Approximate black-matte removal for this luminous source, not general matting.
        gl_FragColor=vec4(min(rgb/max(alpha,0.002),vec3(1.0)),alpha*uAlpha*border);
        #include <colorspace_fragment>
      }`,
  });
  const body = new THREE.Mesh(new THREE.PlaneGeometry(4.4, 4.4), bodyMaterial);
  body.name = 'body'; body.position.y = 2.0; body.frustumCulled = false; group.add(body);
  const haloMaterial = new THREE.ShaderMaterial({
    transparent: true, depthWrite: false, side: THREE.DoubleSide, toneMapped: false,
    uniforms: { uAlpha: { value: 0 } },
    vertexShader: `varying vec2 vUv;void main(){vUv=uv;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);}`,
    fragmentShader: `uniform float uAlpha;varying vec2 vUv;
      void main(){float r=length((vUv-0.5)*2.0);float a=exp(-r*r*6.0)*(1.0-smoothstep(0.7,1.0,r));
      gl_FragColor=vec4(0.10,0.66,0.57,a*uAlpha*0.40);
      #include <colorspace_fragment>
      }`,
  });
  const halo = new THREE.Mesh(new THREE.PlaneGeometry(3.3, 3.3), haloMaterial);
  halo.name = 'halo'; halo.rotation.x = -Math.PI / 2; halo.position.y = 0.04; group.add(halo);
  let disposed = false;
  function update(time) {
    if (disposed) throw new Error('Effect has been disposed');
    const sample = flipbookFrame(time, { frames, fps });
    group.visible = time > 0 && time < duration;
    const fadeIn = Math.min(1, Math.max(0, time / 0.28));
    const fadeOut = Math.min(1, Math.max(0, (duration - time) / 0.65));
    bodyMaterial.uniforms.uFrames.value.set(sample.first, sample.next, sample.mix);
    bodyMaterial.uniforms.uAlpha.value = fadeIn * fadeOut;
    haloMaterial.uniforms.uAlpha.value = fadeIn * fadeOut;
    return { active: group.visible, phase: time <= 0 ? 'ready' : time < 0.5 ? 'charge'
      : time < duration - 0.65 ? 'sustain' : time < duration ? 'fade' : 'finished' };
  }
  function setLayer(name, visible) {
    if (disposed) throw new Error('Effect has been disposed');
    if (!['body', 'halo'].includes(name)) throw new Error(`Unknown effect layer: ${name}`);
    group.getObjectByName(name).visible = Boolean(visible);
  }
  function dispose() {
    if (disposed) return;
    group.removeFromParent();
    for (const mesh of [body, halo]) { mesh.geometry.dispose(); mesh.material.dispose(); }
    group.clear(); disposed = true;
  }
  update(0);
  return { group, update, setLayer, dispose, duration };
}

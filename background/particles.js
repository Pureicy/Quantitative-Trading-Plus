/**
 * Particle background — Three.js scene used as an ambient background layer.
 *
 * Design notes
 * ------------
 * * BufferGeometry + PointsMaterial + THREE.Points (no per-particle objects).
 * * Default particle count 4000.
 * * Particles are seeded once in a 20x20x20 volume (x/y/z in [-10, 10]).
 * * Motion is a whole-group rotation plus a pre-computed sinusoidal offset
 *   written into a reused Float32Array — no allocation inside the frame loop.
 * * Cold palette: indigo -> violet -> cyan, with random lightness.
 * * setPixelRatio is capped at 2 and dropped to 1 in power-saver mode.
 * * Mouse parallax: NDC -> clamped target offset -> lerp, so it never jitters.
 * * Raycaster picks the "core" icosahedron; picking highlights it in gold and
 *   notifies the host (Flet app / page) through a callback.
 *
 * Public API (exposed on window.ParticleBackground):
 *   initParticles(count), disposeParticles(), animate(),
 *   setCount(count), setQuality('performance' | 'power'), onSelect(cb)
 */

import * as THREE from './vendor/three.module.js';

const DEFAULTS = {
  particleCount: 4000,
  spread: 10, // particles live in [-spread, spread] on every axis
  size: 0.062,
  colorCore: new THREE.Color('#6c7cff'), // indigo
  colorMid: new THREE.Color('#8a5cff'), // violet
  colorEdge: new THREE.Color('#35e0ff'), // cyan
  highlight: new THREE.Color('#ffc857'), // gold, used when the core is picked
  background: new THREE.Color('#05070f'), // deep blue-black
  parallaxRange: 0.5, // camera offset is clamped to +/- this value
  parallaxEase: 0.055, // lerp factor per frame
  driftSpeed: 0.09, // radians per second for the whole-particle rotation
};

const FRAME_INTERVAL = {
  performance: 1000 / 60,
  power: 1000 / 4,
};

const state = {
  renderer: null,
  scene: null,
  camera: null,
  group: null,
  points: null,
  core: null,
  coreMaterial: null,
  geometry: null,
  material: null,
  raycaster: null,
  clock: null,
  running: false,
  frameId: 0,
  quality: 'performance',
  count: DEFAULTS.particleCount,
  pointer: { x: 0, y: 0 },
  target: { x: 0, y: 0 },
  parallaxEnabled: true,
  hovered: false,
  selectCallback: null,
  // pre-allocated scratch objects (never re-created inside the loop)
  scratchVector: new THREE.Vector3(),
  scratchColor: new THREE.Color(),
  phases: null,
  basePositions: null,
  configTimer: 0,
  lastRenderAt: 0,
};

const isCoarsePointer =
  typeof window.matchMedia === 'function' &&
  window.matchMedia('(pointer: coarse)').matches;

function isMobileLike() {
  return isCoarsePointer || (window.innerWidth || 0) < 768;
}

/* ------------------------------------------------------------------ */
/* Renderer / scene bootstrap                                          */
/* ------------------------------------------------------------------ */

function createRenderer() {
  const renderer = new THREE.WebGLRenderer({
    antialias: true,
    alpha: true,
    powerPreference: 'high-performance',
  });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderer.setClearColor(DEFAULTS.background, 0); // transparent canvas
  renderer.domElement.id = 'particle-canvas';
  document.body.appendChild(renderer.domElement);
  return renderer;
}

function createScene() {
  const scene = new THREE.Scene();
  scene.fog = new THREE.FogExp2(DEFAULTS.background.getHex(), 0.035);

  const camera = new THREE.PerspectiveCamera(
    55,
    window.innerWidth / Math.max(window.innerHeight, 1),
    0.1,
    200,
  );
  camera.position.set(0, 0, 26);

  const group = new THREE.Group();
  scene.add(group);

  return { scene, camera, group };
}

/* ------------------------------------------------------------------ */
/* Particles                                                           */
/* ------------------------------------------------------------------ */

/**
 * (Re)build the particle system.
 * @param {number} count number of points
 */
export function initParticles(count = DEFAULTS.particleCount) {
  disposeParticles();

  const total = Math.max(1, Math.floor(count));
  state.count = total;
  state.phases = new Float32Array(total);
  state.basePositions = new Float32Array(total * 3);

  const positions = new Float32Array(total * 3);
  const colors = new Float32Array(total * 3);

  for (let i = 0; i < total; i += 1) {
    const i3 = i * 3;
    const spread = DEFAULTS.spread;

    positions[i3] = (Math.random() * 2 - 1) * spread;
    positions[i3 + 1] = (Math.random() * 2 - 1) * spread;
    positions[i3 + 2] = (Math.random() * 2 - 1) * spread;
    state.basePositions[i3] = positions[i3];
    state.basePositions[i3 + 1] = positions[i3 + 1];
    state.basePositions[i3 + 2] = positions[i3 + 2];

    // random phase so the drift never looks synchronised
    state.phases[i] = Math.random() * Math.PI * 2;

    // cold gradient with random lightness
    const t = Math.random();
    if (t < 0.5) {
      state.scratchColor.copy(DEFAULTS.colorCore).lerp(DEFAULTS.colorMid, t * 2);
    } else {
      state.scratchColor
        .copy(DEFAULTS.colorMid)
        .lerp(DEFAULTS.colorEdge, (t - 0.5) * 2);
    }
    const lightness = 0.55 + Math.random() * 0.65;
    state.scratchColor.multiplyScalar(lightness);
    colors[i3] = state.scratchColor.r;
    colors[i3 + 1] = state.scratchColor.g;
    colors[i3 + 2] = state.scratchColor.b;
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));

  const material = new THREE.PointsMaterial({
    size: DEFAULTS.size,
    vertexColors: true,
    transparent: true,
    opacity: 0.92,
    sizeAttenuation: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
  });

  const points = new THREE.Points(geometry, material);
  state.geometry = geometry;
  state.material = material;
  state.points = points;
  state.group.add(points);

  createCore();
  return points;
}

/** The pickable "3D core component" in the middle of the cloud. */
function createCore() {
  const geometry = new THREE.IcosahedronGeometry(1.55, 1);
  const material = new THREE.MeshBasicMaterial({
    color: DEFAULTS.colorCore,
    wireframe: true,
    transparent: true,
    opacity: 0.65,
  });
  const core = new THREE.Mesh(geometry, material);
  core.name = 'core';
  state.core = core;
  state.coreMaterial = material;
  state.group.add(core);

  const halo = new THREE.Mesh(
    new THREE.IcosahedronGeometry(2.15, 2),
    new THREE.MeshBasicMaterial({
      color: DEFAULTS.colorMid,
      wireframe: true,
      transparent: true,
      opacity: 0.18,
    }),
  );
  halo.name = 'core-halo';
  state.group.add(halo);
  state.halo = halo;
}

/**
 * Tear the particle system down (geometry, materials, core).
 */
export function disposeParticles() {
  if (state.points) {
    state.group.remove(state.points);
    state.points = null;
  }
  if (state.core) {
    state.group.remove(state.core);
    state.core.geometry.dispose();
    state.coreMaterial.dispose();
    state.core = null;
    state.coreMaterial = null;
  }
  if (state.halo) {
    state.group.remove(state.halo);
    state.halo.geometry.dispose();
    state.halo.material.dispose();
    state.halo = null;
  }
  if (state.geometry) {
    state.geometry.dispose();
    state.geometry = null;
  }
  if (state.material) {
    state.material.dispose();
    state.material = null;
  }
  state.phases = null;
  state.basePositions = null;
}

/* ------------------------------------------------------------------ */
/* Interaction                                                          */
/* ------------------------------------------------------------------ */

function ndcFromEvent(event) {
  const rect = state.renderer.domElement.getBoundingClientRect();
  const x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
  const y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
  return { x, y };
}

export function onMouseMove(event) {
  if (!state.parallaxEnabled || isMobileLike()) {
    return;
  }
  const ndc = ndcFromEvent(event);
  const limit = DEFAULTS.parallaxRange;
  state.target.x = THREE.MathUtils.clamp(ndc.x * limit, -limit, limit);
  state.target.y = THREE.MathUtils.clamp(ndc.y * limit * 0.6, -limit, limit);
}

export function onMouseLeave() {
  state.target.x = 0;
  state.target.y = 0;
}

function pickCore(event) {
  if (!state.camera || !state.core) {
    return null;
  }
  const ndc = ndcFromEvent(event);
  state.scratchVector.set(ndc.x, ndc.y, 0.5);
  state.raycaster.setFromCamera(state.scratchVector, state.camera);
  const hits = state.raycaster.intersectObject(state.core, false);
  return hits.length ? hits[0] : null;
}

export function onClick(event) {
  const hit = pickCore(event);
  if (!hit) {
    return;
  }
  state.coreMaterial.color.copy(DEFAULTS.highlight);
  state.coreMaterial.opacity = 0.95;
  state.renderer.render(state.scene, state.camera);
  if (state.selectCallback) {
    state.selectCallback({
      object: 'core',
      name: '3D 核心组件',
      point: { x: hit.point.x, y: hit.point.y, z: hit.point.z },
      at: new Date().toISOString(),
    });
  }
  reportSelection();
}

export function onPointerMove(event) {
  if (!state.core) {
    return;
  }
  const hit = pickCore(event);
  const hovering = Boolean(hit);
  if (hovering !== state.hovered) {
    state.hovered = hovering;
    state.renderer.domElement.style.cursor = hovering ? 'pointer' : 'default';
  }
}

/* ------------------------------------------------------------------ */
/* Quality / configuration                                              */
/* ------------------------------------------------------------------ */

export function setQuality(mode) {
  const next = mode === 'power' ? 'power' : 'performance';
  state.quality = next;
  if (!state.renderer) {
    return;
  }
  if (next === 'power') {
    state.renderer.setPixelRatio(1);
    state.pointer.x = 0;
    state.pointer.y = 0;
    state.target.x = 0;
    state.target.y = 0;
    state.camera.position.x = 0;
    state.camera.position.y = 0;
    state.camera.lookAt(0, 0, 0);
    if (state.material) {
      state.material.size = DEFAULTS.size * 1.15;
    }
  } else {
    state.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    if (state.material) {
      state.material.size = DEFAULTS.size;
    }
  }
  state.renderer.setSize(window.innerWidth, window.innerHeight);
}

export function setCount(count) {
  const total = Math.max(1, Math.floor(Number(count) || DEFAULTS.particleCount));
  if (total === state.count && state.points) {
    return;
  }
  initParticles(total);
}

/* ------------------------------------------------------------------ */
/* Frame loop                                                           */
/* ------------------------------------------------------------------ */

export function animate() {
  if (!state.running) {
    return;
  }
  state.frameId = window.requestAnimationFrame(animate);

  const now = performance.now();
  const targetInterval = FRAME_INTERVAL[state.quality] || FRAME_INTERVAL.performance;
  if (now - state.lastRenderAt < targetInterval) {
    return;
  }
  state.lastRenderAt = now;

  const delta = state.clock.getDelta();
  const elapsed = state.clock.getElapsedTime();

  if (state.quality === 'performance') {
    // whole-group rotation + lightweight per-point drift
    state.group.rotation.y += DEFAULTS.driftSpeed * delta;
    state.group.rotation.x = Math.sin(elapsed * 0.08) * 0.12;

    if (state.points && state.phases) {
      const position = state.geometry.attributes.position;
      const array = position.array;
      const base = state.basePositions;
      const phases = state.phases;
      const total = state.count;
      for (let i = 0; i < total; i += 1) {
        const i3 = i * 3;
        const phase = phases[i];
        array[i3] = base[i3] + Math.sin(elapsed * 0.7 + phase) * 0.16;
        array[i3 + 1] = base[i3 + 1] + Math.cos(elapsed * 0.56 + phase) * 0.16;
        array[i3 + 2] = base[i3 + 2] + Math.sin(elapsed * 0.44 + phase * 0.5) * 0.12;
      }
      position.needsUpdate = true;
    }
    if (state.core) {
      state.core.rotation.y += 0.35 * delta;
      state.core.rotation.x += 0.18 * delta;
      state.halo.rotation.y -= 0.22 * delta;
    }
  }

  if (state.quality === 'performance') {
    // smooth camera parallax (lerp) — never snaps, never jitters
    if (state.parallaxEnabled && !isMobileLike()) {
      state.pointer.x += (state.target.x - state.pointer.x) * DEFAULTS.parallaxEase;
      state.pointer.y += (state.target.y - state.pointer.y) * DEFAULTS.parallaxEase;
    } else {
      state.pointer.x += (0 - state.pointer.x) * DEFAULTS.parallaxEase;
      state.pointer.y += (0 - state.pointer.y) * DEFAULTS.parallaxEase;
    }
    state.camera.position.x = state.pointer.x;
    state.camera.position.y = state.pointer.y;
    state.camera.lookAt(0, 0, 0);
  }

  state.renderer.render(state.scene, state.camera);
}

/* ------------------------------------------------------------------ */
/* Host bridge                                                          */
/* ------------------------------------------------------------------ */

async function reportSelection() {
  try {
    await fetch('/api/event', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type: 'core-selected', at: new Date().toISOString() }),
    });
  } catch (err) {
    /* the page may be opened without the overlay server — ignore */
  }
}

async function pollConfig() {
  try {
    const response = await fetch('/api/config', { cache: 'no-store' });
    if (!response.ok) {
      return;
    }
    const config = await response.json();
    if (config.count && config.count !== state.count) {
      setCount(config.count);
    }
    if (config.quality && config.quality !== state.quality) {
      setQuality(config.quality);
    }
  } catch (err) {
    /* standalone page without a config endpoint */
  }
}

export function onSelect(callback) {
  state.selectCallback = callback;
}

export function start() {
  if (state.running) {
    return;
  }
  state.renderer = createRenderer();
  const { scene, camera, group } = createScene();
  state.scene = scene;
  state.camera = camera;
  state.group = group;
  state.raycaster = new THREE.Raycaster();
  state.clock = new THREE.Clock();
  state.lastRenderAt = 0;
  state.parallaxEnabled = !isMobileLike();

  initParticles(state.count);
  setQuality(state.quality);

  window.addEventListener('resize', onResize);
  window.addEventListener('mousemove', onMouseMove, { passive: true });
  window.addEventListener('mouseleave', onMouseLeave);
  window.addEventListener('pointermove', onPointerMove, { passive: true });
  window.addEventListener('click', onClick);

  state.running = true;
  state.configTimer = window.setInterval(pollConfig, 2000);
  pollConfig();
  animate();
}

export function stop() {
  state.running = false;
  if (state.frameId) {
    window.cancelAnimationFrame(state.frameId);
    state.frameId = 0;
  }
  if (state.configTimer) {
    window.clearInterval(state.configTimer);
    state.configTimer = 0;
  }
  window.removeEventListener('resize', onResize);
  window.removeEventListener('mousemove', onMouseMove);
  window.removeEventListener('mouseleave', onMouseLeave);
  window.removeEventListener('pointermove', onPointerMove);
  window.removeEventListener('click', onClick);
  disposeParticles();
  if (state.renderer) {
    const canvas = state.renderer.domElement;
    state.renderer.dispose();
    state.renderer.forceContextLoss?.();
    canvas.remove();
    state.renderer = null;
  }
  state.scene = null;
  state.camera = null;
  state.group = null;
  state.raycaster = null;
  state.clock = null;
  state.hovered = false;
}

export function onResize() {
  if (!state.renderer || !state.camera) {
    return;
  }
  state.camera.aspect = window.innerWidth / Math.max(window.innerHeight, 1);
  state.camera.updateProjectionMatrix();
  state.renderer.setSize(window.innerWidth, window.innerHeight);
}

export function setParallaxEnabled(enabled) {
  state.parallaxEnabled = Boolean(enabled);
}

export function getState() {
  return {
    running: state.running,
    count: state.count,
    quality: state.quality,
    parallaxEnabled: state.parallaxEnabled,
    hovered: state.hovered,
  };
}

window.ParticleBackground = {
  initParticles,
  disposeParticles,
  animate,
  start,
  stop,
  setCount,
  setQuality,
  setParallaxEnabled,
  onSelect,
  getState,
  onMouseMove,
  onClick,
  onPointerMove,
  DEFAULTS,
};

window.addEventListener('DOMContentLoaded', () => {
  start();
  window.addEventListener('message', (event) => {
    const data = event.data || {};
    if (data.type === 'setCount') {
      setCount(data.value);
    } else if (data.type === 'setQuality') {
      setQuality(data.value);
    } else if (data.type === 'select') {
      if (state.selectCallback) {
        state.selectCallback(data.payload || {});
      }
    }
  });
});

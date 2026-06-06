import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

const container = document.getElementById("viewer");
const statusEl = document.getElementById("viewer-status");
const hudTitle = document.querySelector("#hud strong");

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x12100e);

const camera = new THREE.PerspectiveCamera(45, 1, 0.01, 100);
camera.position.set(2.4, 1.6, 3.2);
camera.up.set(0, 1, 0);

const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
renderer.outputColorSpace = THREE.SRGBColorSpace;
container.appendChild(renderer.domElement);

const controls = new OrbitControls(camera, renderer.domElement);
controls.target.set(0, 0, 0);
controls.enablePan = false;
controls.enableDamping = true;
controls.dampingFactor = 0.08;
controls.minPolarAngle = 0.08;
controls.maxPolarAngle = Math.PI / 2;
controls.minDistance = 0.6;
controls.maxDistance = 8.0;
controls.update();

let currentViewMode = "3d";
let currentRadius = 1.1;
const HEAD_CENTER_Y = 1.33;

function applyCameraMode(mode, resetCamera = false) {
  if (mode === "2d") {
    camera.up.set(0, 0, -1);
    controls.target.set(0, 0, 0);
    controls.enableRotate = false;
    controls.enableZoom = true;
    controls.enablePan = false;
    controls.minPolarAngle = 0;
    controls.maxPolarAngle = 0;
    if (resetCamera) {
      camera.position.set(0, Math.max(2.4, currentRadius * 3.2), 0);
    }
  } else {
    camera.up.set(0, 1, 0);
    controls.target.set(0, 0, 0);
    controls.enableRotate = true;
    controls.enableZoom = true;
    controls.enablePan = false;
    controls.minPolarAngle = 0.08;
    controls.maxPolarAngle = Math.PI / 2;
    if (resetCamera) {
      camera.position.set(2.4, 1.6, 3.2);
    }
  }
  camera.lookAt(controls.target);
  controls.update();
}

scene.add(new THREE.HemisphereLight(0xf7ead8, 0x332820, 1.8));
const keyLight = new THREE.DirectionalLight(0xffffff, 2.0);
keyLight.position.set(2.5, 4.0, 3.0);
scene.add(keyLight);

const floor = new THREE.GridHelper(6, 24, 0x3a3028, 0x2b241e);
floor.position.y = -HEAD_CENTER_Y - 0.01;
scene.add(floor);

const avatarGroup = new THREE.Group();
scene.add(avatarGroup);

const dynamicGroup = new THREE.Group();
scene.add(dynamicGroup);

function appToThree(point, flattenHeight = false) {
  return new THREE.Vector3(point.x_m, flattenHeight ? 0 : point.z_m, -point.y_m);
}

function addAvatar() {
  const bodyMat = new THREE.MeshStandardMaterial({ color: 0xd8c2aa, roughness: 0.82, metalness: 0.0 });
  const accentMat = new THREE.MeshStandardMaterial({ color: 0x8f7b67, roughness: 0.9, metalness: 0.0 });

  const pelvis = new THREE.Mesh(new THREE.SphereGeometry(0.18, 24, 16), accentMat);
  pelvis.scale.set(0.9, 0.55, 0.65);
  pelvis.position.y = 0.55;
  avatarGroup.add(pelvis);

  const torso = new THREE.Mesh(new THREE.CylinderGeometry(0.19, 0.24, 0.52, 24), bodyMat);
  torso.position.y = 0.92;
  avatarGroup.add(torso);

  const head = new THREE.Mesh(new THREE.SphereGeometry(0.16, 24, 16), bodyMat);
  head.position.y = 1.33;
  avatarGroup.add(head);

  for (const x of [-0.29, 0.29]) {
    const arm = new THREE.Mesh(new THREE.CylinderGeometry(0.035, 0.04, 0.58, 16), accentMat);
    arm.position.set(x, 0.88, 0);
    arm.rotation.z = x > 0 ? 0.18 : -0.18;
    avatarGroup.add(arm);
  }

  for (const x of [-0.1, 0.1]) {
    const leg = new THREE.Mesh(new THREE.CylinderGeometry(0.045, 0.055, 0.58, 16), accentMat);
    leg.position.set(x, 0.25, 0);
    avatarGroup.add(leg);
  }

  avatarGroup.position.y = -HEAD_CENTER_Y;
}

function makeLabel(text, position) {
  const canvas = document.createElement("canvas");
  canvas.width = 256;
  canvas.height = 64;
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.font = "28px Arial, Helvetica, sans-serif";
  ctx.fillStyle = "#f2e7d8";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(text, canvas.width / 2, canvas.height / 2);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: texture, transparent: true }));
  sprite.position.copy(position);
  sprite.scale.set(0.42, 0.105, 1);
  return sprite;
}

function addCylinderBetween(start, end, radius, material) {
  const direction = new THREE.Vector3().subVectors(end, start);
  const length = direction.length();
  if (length <= 0.0001) {
    return null;
  }
  const geometry = new THREE.CylinderGeometry(radius, radius, length, 18);
  const mesh = new THREE.Mesh(geometry, material);
  mesh.position.copy(start).add(end).multiplyScalar(0.5);
  mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), direction.clone().normalize());
  return mesh;
}

function addArrowHead(start, end, material) {
  const direction = new THREE.Vector3().subVectors(end, start);
  if (direction.length() <= 0.0001) {
    return null;
  }
  const cone = new THREE.Mesh(new THREE.ConeGeometry(0.06, 0.16, 24), material);
  cone.position.copy(end);
  cone.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), direction.normalize());
  return cone;
}

function drawScene(payload) {
  dynamicGroup.clear();

  const mode = payload.preview_mode === "2d" ? "2d" : "3d";
  const is2D = mode === "2d";
  const radius = Math.max(0.1, payload.radius_m || 1.1);
  const modeChanged = currentViewMode !== mode;
  currentViewMode = mode;
  currentRadius = radius;
  applyCameraMode(mode, modeChanged);

  if (is2D) {
    const disk = new THREE.Mesh(
      new THREE.CircleGeometry(radius, 96),
      new THREE.MeshBasicMaterial({ color: 0x4fb3d8, transparent: true, opacity: 0.09, side: THREE.DoubleSide })
    );
    disk.rotation.x = -Math.PI / 2;
    dynamicGroup.add(disk);
  } else {
    const sphereMat = new THREE.MeshBasicMaterial({
      color: 0x4fb3d8,
      transparent: true,
      opacity: 0.16,
      wireframe: true
    });
    const sphere = new THREE.Mesh(new THREE.SphereGeometry(radius, 40, 20), sphereMat);
    sphere.position.y = 0;
    dynamicGroup.add(sphere);
  }

  const ring = new THREE.Mesh(
    new THREE.RingGeometry(radius * 0.992, radius, 96),
    new THREE.MeshBasicMaterial({ color: 0x4fb3a6, transparent: true, opacity: 0.62, side: THREE.DoubleSide })
  );
  ring.rotation.x = -Math.PI / 2;
  dynamicGroup.add(ring);

  const start = appToThree(payload.start, is2D);
  const end = appToThree(payload.end, is2D);
  const pathMat = new THREE.MeshStandardMaterial({ color: 0xf08b4f, roughness: 0.45, metalness: 0.0 });
  const path = addCylinderBetween(start, end, Math.max(0.012, radius * 0.016), pathMat);
  if (path) dynamicGroup.add(path);
  const arrow = addArrowHead(start, end, pathMat);
  if (arrow) dynamicGroup.add(arrow);

  const startMarker = new THREE.Mesh(new THREE.SphereGeometry(Math.max(0.045, radius * 0.045), 24, 16), new THREE.MeshStandardMaterial({ color: 0xa8d672 }));
  startMarker.position.copy(start);
  dynamicGroup.add(startMarker);
  const endMarker = new THREE.Mesh(new THREE.SphereGeometry(Math.max(0.045, radius * 0.045), 24, 16), new THREE.MeshStandardMaterial({ color: 0xdf7c52 }));
  endMarker.position.copy(end);
  dynamicGroup.add(endMarker);

  const labelLift = is2D ? 0.02 : 0.08;
  dynamicGroup.add(makeLabel("Start", start.clone().add(new THREE.Vector3(0.08, labelLift, 0))));
  dynamicGroup.add(makeLabel("End", end.clone().add(new THREE.Vector3(0.08, labelLift, 0))));
  dynamicGroup.add(makeLabel("+X right", new THREE.Vector3(radius * 1.18, 0.05, 0)));
  dynamicGroup.add(makeLabel("+Y front", new THREE.Vector3(0, 0.05, -radius * 1.18)));
  if (!is2D) {
    dynamicGroup.add(makeLabel("+Z up", new THREE.Vector3(0, radius * 1.05, 0)));
  }

  const axisMat = new THREE.LineBasicMaterial({ color: 0x6f6257 });
  const axisPoints = [
    [new THREE.Vector3(-radius, 0, 0), new THREE.Vector3(radius, 0, 0)],
    [new THREE.Vector3(0, 0, radius), new THREE.Vector3(0, 0, -radius)]
  ];
  if (!is2D) {
    axisPoints.push([new THREE.Vector3(0, 0, 0), new THREE.Vector3(0, radius, 0)]);
  }
  for (const pair of axisPoints) {
    dynamicGroup.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pair), axisMat));
  }

  if (hudTitle) {
    hudTitle.textContent = is2D ? "2D Sound Path" : "3D Sound Path";
  }
  statusEl.textContent = `${payload.path_length_m.toFixed(2)} m path, ${payload.movement_duration_s.toFixed(2)} s movement`;
  window.__trajectoryViewerState = {
    ready: true,
    view_mode: mode,
    height_visible: !is2D,
    camera_locked_top_down: is2D,
    path_length_m: payload.path_length_m.toFixed(3),
    camera_max_polar_angle: controls.maxPolarAngle.toFixed(6)
  };
  container.dataset.viewerReady = "true";
  container.dataset.viewMode = mode;
  container.dataset.heightVisible = String(!is2D);
  container.dataset.cameraLockedTopDown = String(is2D);
  container.dataset.pathLengthM = window.__trajectoryViewerState.path_length_m;
  container.dataset.cameraMaxPolarAngle = window.__trajectoryViewerState.camera_max_polar_angle;
}

function resize() {
  const width = Math.max(1, container.clientWidth);
  const height = Math.max(1, container.clientHeight);
  renderer.setSize(width, height, false);
  camera.aspect = width / height;
  camera.updateProjectionMatrix();
}

function animate() {
  resize();
  controls.update();
  renderer.render(scene, camera);
  window.requestAnimationFrame(animate);
}

addAvatar();
drawScene({
  preview_mode: "2d",
  radius_m: 1.1,
  path_length_m: 1.0,
  movement_duration_s: 3.0,
  start: { x_m: 0, y_m: 1.1, z_m: 0 },
  end: { x_m: 0, y_m: 0.1, z_m: 0 }
});
resize();
animate();

window.updateTrajectory = function updateTrajectory(payload) {
  drawScene(payload);
};

window.resetTrajectoryCamera = function resetTrajectoryCamera() {
  applyCameraMode(currentViewMode, true);
};

container.dataset.viewerReady = "true";

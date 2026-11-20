// Loads the character GLBs with three's GLTFLoader (in node) and checks that every clip in anims.glb binds
// by bone name to lean / mid / big, and that the poses land where anims.json says they should.
//
//   node web/tools/verify_three.mjs
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import * as THREE from '../node_modules/three/build/three.module.js';
import { GLTFLoader } from '../node_modules/three/examples/jsm/loaders/GLTFLoader.js';

const here = dirname(fileURLToPath(import.meta.url));
const assets = join(here, '..', 'public', 'assets');
const loader = new GLTFLoader();
const load = (rel) => {
  const buf = readFileSync(join(assets, rel));
  const ab = buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength);
  return new Promise((ok, fail) => loader.parse(ab, '', ok, fail));
};
const manifest = JSON.parse(readFileSync(join(assets, 'characters', 'anims.json'), 'utf8'));
const fmt = (v) => `(${v.x.toFixed(3)}, ${v.y.toFixed(3)}, ${v.z.toFixed(3)})`;
let failures = 0;
const check = (ok, msg) => { console.log(`${ok ? 'ok  ' : 'FAIL'} ${msg}`); if (!ok) failures++; };

const anims = await load('characters/anims.glb');
check(anims.animations.length === manifest.clips.length, `anims.glb has ${anims.animations.length} clips (manifest ${manifest.clips.length})`);
for (const c of manifest.clips) {
  const clip = THREE.AnimationClip.findByName(anims.animations, c.name);
  check(!!clip && Math.abs(clip.duration - c.frames / 30) < 1e-3, `clip ${c.name} duration ${clip?.duration.toFixed(4)} = ${c.frames}/30`);
}

for (const build of ['lean', 'mid', 'big']) {
  const gltf = await load(`characters/${build}.glb`);
  const root = gltf.scene;
  const skins = [];
  root.traverse((o) => { if (o.isSkinnedMesh) skins.push(o); });
  const skinned = skins[0];
  const mats = new Set();
  root.traverse((o) => { if (o.isMesh) (Array.isArray(o.material) ? o.material : [o.material]).forEach((m) => mats.add(m.name)); });
  const geo = skinned.geometry;
  check(skins.every((m) => m.geometry.attributes.uv && m.geometry.attributes.uv1 && m.skeleton === skinned.skeleton), `${build}: ${skins.length} skinned primitives share one skeleton, all have uv (UVMap) + uv1 (NumberUV); ${mats.size} materials, ${skinned.skeleton.bones.length} bones`);

  // Every track of every clip must resolve to a node in this character.
  let unbound = 0;
  for (const clip of anims.animations) {
    for (const track of clip.tracks) {
      const nodeName = THREE.PropertyBinding.parseTrackName(track.name).nodeName;
      if (!THREE.PropertyBinding.findNode(root, nodeName)) unbound++;
    }
  }
  check(unbound === 0, `${build}: all ${anims.animations.reduce((n, c) => n + c.tracks.length, 0)} tracks bind by bone name`);

  const mixer = new THREE.AnimationMixer(root);
  const bone = (n) => root.getObjectByName(n);
  const pose = (name, frame) => {
    mixer.stopAllAction();
    const action = mixer.clipAction(THREE.AnimationClip.findByName(anims.animations, name));
    action.reset().play();
    mixer.setTime(frame / 30);
    root.updateMatrixWorld(true);
  };
  // Throw: at `release` ball_hand_r must be where A_Throw.fbx puts it on frame 10 (Blender (-0.050, -0.555, 1.882)).
  // anims.json's release_point (-0.03, -0.69, 1.84) is measured on the control rig before baking and is ~14 cm off;
  // the game never reads it (it takes the bone's position at the event).
  const throwInfo = manifest.clips.find((c) => c.name === 'Throw');
  pose('Throw', throwInfo.events.release);
  const expected = new THREE.Vector3(-0.050, 1.882, 0.555);
  const got = bone('ball_hand_r').getWorldPosition(new THREE.Vector3());
  check(got.distanceTo(expected) < 0.003, `${build}: Throw release ball_hand_r ${fmt(got)} vs A_Throw.fbx ${fmt(expected)}`);
  const y = new THREE.Vector3(0, 1, 0).applyQuaternion(bone('ball_hand_r').getWorldQuaternion(new THREE.Quaternion()));
  check(y.z > 0.5, `${build}: ball_hand_r +Y at release points downfield (+Z): ${fmt(y)}`);

  // Skinned bounds in two poses: standing (Idle) and lying (DownBack).
  for (const [clip, frame] of [['Idle', 0], ['Run', 4], ['DownBack', 0]]) {
    pose(clip, frame);
    const box = new THREE.Box3();
    const v = new THREE.Vector3();
    for (const sm of skins) {
      sm.skeleton.update();
      const pos = sm.geometry.attributes.position;
      for (let i = 0; i < pos.count; i += 3) { sm.getVertexPosition(i, v); box.expandByPoint(v.applyMatrix4(sm.matrixWorld)); }
    }
    console.log(`     ${build} ${clip}@${frame}: skinned bounds min ${fmt(box.min)} max ${fmt(box.max)}`);
    if (clip === 'Idle') check(box.max.y > 1.8 && box.max.y < 2.05 && Math.abs(box.min.y) < 0.05, `${build}: Idle stands on y=0, height ${box.max.y.toFixed(2)} m`);
    if (clip === 'DownBack') check(box.max.y < 0.8, `${build}: DownBack lies down (top ${box.max.y.toFixed(2)} m)`);
  }
  // Facing: in Idle the face (head joint forward of the neck) is toward +Z.
  pose('Run', 0);
  const head = bone('head').getWorldPosition(new THREE.Vector3());
  const pelvis = bone('pelvis').getWorldPosition(new THREE.Vector3());
  check(head.z > pelvis.z, `${build}: Run leans forward toward +Z (head z ${head.z.toFixed(3)} > pelvis z ${pelvis.z.toFixed(3)})`);
}
console.log(failures ? `${failures} FAILED` : 'all checks passed');
process.exit(failures ? 1 : 0);

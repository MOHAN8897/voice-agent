import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs/promises';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { AnimationMixer, LoopOnce, Vector3 } from 'three';
import { createVoxlyController } from '../src/three/BotController.js';

async function load() {
 const bytes=await fs.readFile(new URL('../public/models/VoxlyBot_AIEmployee_Interactive.glb',import.meta.url));
 const gltf=await new GLTFLoader().parseAsync(bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength),'');
 return {gltf,c:createVoxlyController(gltf)};
}

test('Blender arm chains are symmetric and every exported gesture keeps each wrist on its own side',async()=>{
 const {gltf,c}=await load();
 for(const part of ['Forearm','Hand']) assert.ok(Math.abs(c.bones.get('Left'+part).position.length()-c.bones.get('Right'+part).position.length())<1e-5);
 const p=new Vector3();
 for(const name of ['RIGHT_HAND_WAVE','LEFT_HAND_WAVE','DOUBLE_WAVE','CELEBRATE','ROLL_DOUBLE_WAVE','DOUBLE_ROLL_DOUBLE_WAVE','THINKING','DANCE']) {
  c.playGesture(name);
  for(let i=0;i<270;i++){
   c.update(1/60);gltf.scene.updateMatrixWorld(true);
   for(const [side,sign] of [['Left',1],['Right',-1]]) {
    c.bones.get(side+'Hand').getWorldPosition(p);c.bones.get('Body').worldToLocal(p);
    assert.ok(p.x*sign>1.05,`${name} ${side} crossed torso at frame ${i}: ${p.x}`);
    for(const part of ['UpperArm','Forearm','Hand'])assert.ok(Math.abs(c.bones.get(side+part).quaternion.length()-1)<1e-5);
   }
  }
 }
 c.dispose();
});

test('left and right skin weights actually follow their own hand bones',async()=>{
 const {gltf,c}=await load();
 for(const side of ['Left','Right']) {
  let mesh;c.nodes.get(side+'PalmGlow').traverse(o=>{if(o.isSkinnedMesh)mesh=o});
  assert.ok(mesh,side+' palm mesh');
  const joints=mesh.geometry.getAttribute('skinIndex'), weights=mesh.geometry.getAttribute('skinWeight');
  for(let i=0;i<joints.count;i++)for(let k=0;k<4;k++)if(weights.getComponent(i,k)>.001)assert.equal(mesh.skeleton.bones[joints.getComponent(i,k)].userData.controlName,side+'Hand');
 }
 c.dispose();
});

test('facial expressions blend, speech updates mouth, and reduced motion cancels spins',async()=>{
 const {c}=await load();let mouth;c.nodes.get('Mouth').traverse(o=>{if(o.morphTargetDictionary)mouth=o});
 assert.ok(mouth);
 c.setExpression('SURPRISED');c.update(1/60);
 const index=mouth.morphTargetDictionary.MouthSurprised;
 assert.ok(mouth.morphTargetInfluences[index]>0 && mouth.morphTargetInfluences[index]<1);
 c.setState('SPEAKING');assert.equal(c.isSpeaking,true);
 c.update(1/60);assert.ok(mouth.morphTargetInfluences[mouth.morphTargetDictionary.MouthOpen]>0);
 c.playGesture('DOUBLE_ROLL_DOUBLE_WAVE');c.update(.1);assert.ok(c.rollProgress>0);
 c.setReducedMotion(true);c.update(.1);assert.equal(c.rollProgress,0);
 c.playGesture('DANCE');assert.notEqual(c.state,'DANCE');
 c.dispose();
});

test('rapid gesture changes remain finite and settle back to speaking',async()=>{
 const {c}=await load();c.setState('SPEAKING');
 for(const gesture of ['DOUBLE_WAVE','THINKING','LEFT_HAND_WAVE','DANCE','RIGHT_HAND_WAVE']){
  c.playGesture(gesture);for(let i=0;i<10;i++)c.update(1/60);
 }
 for(let i=0;i<260;i++)c.update(1/60);
 assert.equal(c.state,'TALKING');
 for(const b of c.bones.values())assert.ok(b.quaternion.toArray().every(Number.isFinite));
 c.dispose();
});

test('all baked clips have seamless endpoints and single waves raise only the selected hand',async()=>{
 const {gltf,c}=await load();c.dispose();
 const mixer=new AnimationMixer(gltf.scene);
 for(const clip of gltf.animations) {
  mixer.stopAllAction();
  const action=mixer.clipAction(clip).setLoop(LoopOnce,1);
  action.clampWhenFinished=true;action.reset().play();mixer.update(0);
  const start=[...c.bones.values()].map(b=>({p:b.position.clone(),q:b.quaternion.clone()}));
  mixer.update(clip.duration);
  [...c.bones.values()].forEach((b,i)=>{
   assert.ok(b.position.distanceTo(start[i].p)<1e-4,clip.name+' position seam');
   assert.ok(b.quaternion.angleTo(start[i].q)<.002,clip.name+' rotation seam');
  });
 }
 for(const side of ['Left','Right']) {
  mixer.stopAllAction();
  const action=mixer.clipAction(gltf.animations.find(a=>a.name===side.toUpperCase()+'_HAND_WAVE'));
  action.reset().play();mixer.update(1.4);gltf.scene.updateMatrixWorld(true);
  const raised=c.bones.get(side+'Hand').getWorldPosition(new Vector3());
  const resting=c.bones.get((side==='Left'?'Right':'Left')+'Hand').getWorldPosition(new Vector3());
  assert.ok(raised.y-resting.y>.7,side+' wave must not lift the opposite hand');
 }
 mixer.stopAllAction();mixer.uncacheRoot(gltf.scene);
});

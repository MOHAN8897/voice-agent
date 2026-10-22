import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { Vector3 } from 'three';
import { createVoxlyController } from '../src/three/BotController.js';

const bytes=await fs.readFile(new URL('../public/models/VoxlyBot_AIEmployee_Interactive.glb',import.meta.url));
const gltf=await new GLTFLoader().parseAsync(bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength),'');
const c=createVoxlyController(gltf);
const handMeshes=[];
gltf.scene.traverse(o=>{
 if(o.isSkinnedMesh && /^(Left|Right)(Hand|Finger)/.test(o.name))handMeshes.push(o);
});
const v=new Vector3();
for(const gesture of ['RIGHT_HAND_WAVE','LEFT_HAND_WAVE','DOUBLE_WAVE','THINKING','DANCE']){
 c.playGesture(gesture);let clearance=Infinity;
 for(let frame=0;frame<240;frame++){
  c.update(1/60);gltf.scene.updateMatrixWorld(true);
  if(frame%6)continue;
  for(const mesh of handMeshes){
   mesh.skeleton.update();
   for(let i=0;i<mesh.geometry.attributes.position.count;i++){
    mesh.getVertexPosition(i,v);mesh.localToWorld(v);
    if(v.y>2.15)clearance=Math.min(clearance,Math.abs(v.x)-1.9);
   }
  }
 }
 console.log(gesture,'minimum clearance above cheek:',clearance.toFixed(3));
 assert.ok(clearance>.05,`${gesture}: hand vertices must clear the headphone silhouette`);
}
c.dispose();

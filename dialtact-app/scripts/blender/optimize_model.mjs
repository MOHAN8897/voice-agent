// Shrink the mascot GLB for low-end devices without touching its animation.
//
//   node scripts/blender/optimize_model.mjs <in.glb> <out.glb>
//
// Only mesh attributes are quantized (KHR_mesh_quantization: positions, normals and
// UVs as small integers, decoded natively by three.js). Full meshopt compression was
// rejected: it also rounds animation rotations, which broke clip seams in the rig tests.
import { NodeIO } from '@gltf-transform/core';
import { ALL_EXTENSIONS } from '@gltf-transform/extensions';
import { quantize } from '@gltf-transform/functions';

const [input, output] = process.argv.slice(2);
const io = new NodeIO().registerExtensions(ALL_EXTENSIONS);
const doc = await io.read(input);
await doc.transform(quantize({ quantizePosition: 14, quantizeNormal: 10 }));
await io.write(output, doc);
console.log('wrote', output);

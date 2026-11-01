// Copy the Blender-authored scroll clips into the original mascot GLB.
//
//   node scripts/blender/merge_scroll_clips.mjs <original.glb> <blender-export.glb> <out.glb>
//
// Re-exporting the whole model from Blender resamples the hand-tuned clips that ship
// today (DANCE stopped looping seamlessly), so only animations the original does not
// have are copied, retargeted to the original's nodes by name. That is valid because
// the rig's rest transforms are identical in both files; this script checks it.
import { NodeIO } from '@gltf-transform/core';
import { ALL_EXTENSIONS } from '@gltf-transform/extensions';

const [originalPath, authoredPath, outPath] = process.argv.slice(2);
if (!outPath) {
  console.error('usage: merge_scroll_clips.mjs <original.glb> <blender-export.glb> <out.glb>');
  process.exit(1);
}

// Register every extension so materials (clearcoat, emissive strength) survive the write.
const io = new NodeIO().registerExtensions(ALL_EXTENSIONS);
const original = await io.read(originalPath);
const authored = await io.read(authoredPath);
const root = original.getRoot();
// Bones are matched through the skin: object nodes can share a bone's name ("Body").
const joints = (doc) => new Map(doc.getRoot().listSkins()[0].listJoints().map((node) => [node.getName(), node]));
const nodesByName = joints(original);
const buffer = root.listBuffers()[0];
const existing = new Set(root.listAnimations().map((animation) => animation.getName()));

for (const [name, node] of joints(authored)) {
  const target = nodesByName.get(name);
  if (!target) throw new Error(`Bone "${name}" is missing from the original rig.`);
  const same = (a, b) => a.every((value, i) => Math.abs(value - b[i]) < 1e-4 || (a.length === 4 && Math.abs(value + b[i]) < 1e-4));
  if (!same(node.getTranslation(), target.getTranslation()) || !same(node.getRotation(), target.getRotation())) {
    throw new Error(`Rest transform of "${node.getName()}" differs; clips would be misaligned.`);
  }
}

const copyAccessor = (accessor) => original.createAccessor(accessor.getName())
  .setType(accessor.getType())
  .setArray(accessor.getArray().slice())
  .setBuffer(buffer);

let added = 0;
for (const clip of authored.getRoot().listAnimations()) {
  if (existing.has(clip.getName())) continue;
  const animation = original.createAnimation(clip.getName());
  for (const channel of clip.listChannels()) {
    const node = nodesByName.get(channel.getTargetNode()?.getName());
    if (!node) throw new Error(`${clip.getName()}: no node "${channel.getTargetNode()?.getName()}" in the original`);
    const source = channel.getSampler();
    const sampler = original.createAnimationSampler()
      .setInterpolation(source.getInterpolation())
      .setInput(copyAccessor(source.getInput()))
      .setOutput(copyAccessor(source.getOutput()));
    animation.addSampler(sampler).addChannel(
      original.createAnimationChannel().setTargetNode(node).setTargetPath(channel.getTargetPath()).setSampler(sampler)
    );
  }
  added += 1;
  console.log(`added ${clip.getName()} (${clip.listChannels().length} channels)`);
}

await io.write(outPath, original);
console.log(`wrote ${outPath} with ${added} new clip(s)`);

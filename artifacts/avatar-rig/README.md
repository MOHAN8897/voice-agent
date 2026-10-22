# Avatar rig repair

The frontend GLB was rebuilt with Blender 5.2.2. `VoxlyBot-repaired.blend`
is the editable source; `original.glb` preserves the input used for the repair.

The repair mirrors the right arm geometry, skin weights and bone rest frames
onto the left. It bakes 19 clips using fixed arm lengths and outward elbow
poles. Both wrists stay outside the torso. Single waves, double waves,
thinking, dancing and speaking share the same rig and neutral endpoints.

Run from the repository root (PowerShell):

```powershell
& 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe' --background --python voxly-ai/scripts/repair_bot_rig.py -- --input artifacts/avatar-rig/original.glb --output voxly-ai/public/models/VoxlyBot_AIEmployee_Interactive.glb --blend artifacts/avatar-rig/VoxlyBot-repaired.blend
```

Run `npm run test:rig` and `npm run build` inside `voxly-ai`.
The tests load the actual GLB in Three.js and cover arm symmetry, side
separation, skin weights, expressions, speech, reduced motion, interrupted
gestures, loop seams and single-hand selection. Desktop and mobile screenshots
record the frontend check; Blender's viewport was also checked at idle and
double-wave poses.

The 3.1 refinement lengthens the upper-arm/forearm segments while preserving
the idle wrist targets and hand size. Raised waves and the thinking gesture
now clear the headphone silhouette. Dedicated amber microphone and violet
headphone/palm materials provide contrast without recoloring the face/body.
`check-hand-clearance.mjs` samples the actual skinned hand/finger vertices
through each gesture to catch renewed overlap above the cheek line.

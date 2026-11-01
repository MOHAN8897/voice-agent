"""
Author the home page's scroll-reaction clips on the Dialtact mascot and export a new GLB.

Run headless (Blender 4.4+ / 5.x):
  blender -b --factory-startup --python scripts/blender/add_scroll_clips.py -- <in.glb> <out.glb>

The mascot is a skeletal rig ("Rig": Root > Body > Head, Shoulder > UpperArm > Forearm >
Hand per side) facing the camera along -Y, Z up, so screen-left is -X (its right arm).
Poses are written as world-space intents ("aim this arm at that direction", "pitch
the head") and converted to each bone's local rest frame, so they stay correct if the
rig's rest pose changes. Every clip keys every bone at both ends, so a clip never
leaves a bone where the previous clip put it.
"""
import math
import sys

import bpy
from mathutils import Quaternion, Vector

src, dst = sys.argv[sys.argv.index('--') + 1:][:2]
FPS = 24

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
rig = bpy.data.objects['Rig']
bones = rig.data.bones
BONES = [b.name for b in bones]


def rest_q(name):
    return (rig.matrix_world @ bones[name].matrix_local).to_quaternion()


def to_local(name, world_delta, parent_delta=Quaternion()):
    """World-space rotation delta -> pose rotation in the bone's rest frame."""
    b = rest_q(name)
    return b.inverted() @ (parent_delta.inverted() @ world_delta) @ b


def rest_dir(name):
    bone = bones[name]
    return (rig.matrix_world.to_3x3() @ (bone.tail_local - bone.head_local)).normalized()


def aim(name, target, parent_delta=Quaternion()):
    """Rotation (world delta, local) that points bone `name` along `target`."""
    world = (parent_delta @ rest_dir(name)).rotation_difference(Vector(target).normalized()) @ parent_delta
    return world, to_local(name, world, parent_delta)


def axis_angle(axis, degrees):
    return Quaternion(Vector(axis), math.radians(degrees))


def arm_pose(side, upper_target, fore_target, body_delta=Quaternion()):
    """Aim one arm: upper arm, then forearm relative to the posed upper arm."""
    pose = {}
    upper_world, pose[f'{side}UpperArm'] = aim(f'{side}UpperArm', upper_target, body_delta)
    _, pose[f'{side}Forearm'] = aim(f'{side}Forearm', fore_target, upper_world)
    return pose


def root_lift(z):
    """Root translation of `z` metres straight up, in Root's local frame."""
    return rest_q('Root').inverted() @ Vector((0, 0, z))


def make_clip(name, keys):
    """keys: [(frame, {bone: Quaternion | ('loc', Vector)})]. Unlisted bones rest."""
    action = bpy.data.actions.new(name)
    rig.animation_data_create()
    rig.animation_data.action = action
    for frame, pose in keys:
        for bone_name in BONES:
            pb = rig.pose.bones[bone_name]
            pb.rotation_mode = 'QUATERNION'
            value = pose.get(bone_name, Quaternion())
            pb.rotation_quaternion = value
            pb.location = pose.get(f'{bone_name}.loc', Vector())
            pb.scale = pose.get(f'{bone_name}.scale', Vector((1, 1, 1)))
            pb.keyframe_insert('rotation_quaternion', frame=frame)
            pb.keyframe_insert('location', frame=frame)
            pb.keyframe_insert('scale', frame=frame)
    track = rig.animation_data.nla_tracks.new()
    track.name = name
    track.strips.new(name, int(keys[0][0]), action)
    rig.animation_data.action = None
    print('CLIP', name, keys[-1][0] / FPS, 's')


REST = {}


def merge(*poses):
    out = {}
    for pose in poses:
        out.update(pose)
    return out


def lean(degrees_y, yaw_z=0.0, pitch_x=0.0):
    """Body lean sideways (about Y), head yaw (about Z) and pitch (about X)."""
    body_world = axis_angle((0, 1, 0), degrees_y)
    head_world = axis_angle((0, 0, 1), yaw_z) @ axis_angle((1, 0, 0), pitch_x)
    return {
        'Body': to_local('Body', body_world),
        'Head': to_local('Head', head_world @ body_world, body_world),
    }, body_world


# --- POINT_LEFT / POINT_RIGHT: "look over here" at the content beside it -------------
for clip, side, sx in (('POINT_LEFT', 'Right', -1), ('POINT_RIGHT', 'Left', 1)):
    # Lean and look toward the side it points to (positive Z yaw turns the face to +X).
    body, body_world = lean(6 * sx, yaw_z=22 * sx, pitch_x=4)
    # Straight out to the side at shoulder height, only slightly toward the camera, so
    # the arm reads as pointing rather than waving; the "tap" flicks the forearm.
    point = arm_pose(side, (sx, -0.18, 0.08), (sx, -0.22, 0.12), body_world)
    tap = arm_pose(side, (sx, -0.18, 0.12), (sx, -0.3, 0.32), body_world)
    make_clip(clip, [
        (1, REST),
        (9, merge(body, point)),
        (20, merge(body, tap)),
        (28, merge(body, point)),
        (40, merge(body, point)),
        (52, REST),
    ])

# --- NOD: agreement ------------------------------------------------------------------
make_clip('NOD', [
    (1, REST),
    (7, {'Head': to_local('Head', axis_angle((1, 0, 0), 14))}),
    (13, {'Head': to_local('Head', axis_angle((1, 0, 0), -3))}),
    (19, {'Head': to_local('Head', axis_angle((1, 0, 0), 11))}),
    (28, REST),
])

# --- SCAN: looks across the section, as if reading it --------------------------------
def scan(deg):
    body_world = axis_angle((0, 0, 1), deg * 0.3)
    return {'Body': to_local('Body', body_world),
            'Head': to_local('Head', axis_angle((0, 0, 1), deg) @ axis_angle((1, 0, 0), 6), body_world)}

make_clip('SCAN', [(1, REST), (12, scan(-28)), (26, scan(-28)), (40, scan(26)), (54, scan(26)), (66, REST)])

# --- HOP: anticipation squash, jump, land, settle --------------------------------------
def hop(z, squash=1.0):
    return {'Root.loc': root_lift(z), 'Root.scale': Vector((1 / math.sqrt(squash), squash, 1 / math.sqrt(squash)))}

arms_up = merge(arm_pose('Right', (-0.8, -0.3, 0.55), (-0.6, -0.3, 0.75)), arm_pose('Left', (0.8, -0.3, 0.55), (0.6, -0.3, 0.75)))
make_clip('HOP', [
    (1, REST),
    (6, hop(-0.06, 0.9)),
    (12, merge(hop(0.55, 1.06), arms_up)),
    (18, merge(hop(0.62, 1.0), arms_up)),
    (24, hop(-0.05, 0.92)),
    (32, REST),
])

# --- ARRIVE: lands in a new section with a spin ---------------------------------------
def spin(deg, z=0.0):
    return {'Root': to_local('Root', axis_angle((0, 0, 1), deg)), 'Root.loc': root_lift(z)}

make_clip('ARRIVE', [
    (1, REST),
    (5, spin(0, 0.38)),
    (10, merge(spin(90, 0.45), arms_up)),
    (15, merge(spin(180, 0.38), arms_up)),
    (20, spin(270, 0.2)),
    (25, spin(360, -0.04)),
    (34, REST),
])

# --- PRESENT: open arms, "here it is" --------------------------------------------------
open_arms = merge(
    arm_pose('Right', (-1, -0.7, 0.3), (-0.55, -0.95, 0.45)),
    arm_pose('Left', (1, -0.7, 0.3), (0.55, -0.95, 0.45)),
    {'Head': to_local('Head', axis_angle((1, 0, 0), -6))},
)
make_clip('PRESENT', [
    (1, REST),
    (10, merge(open_arms, {'Root.loc': root_lift(0.12)})),
    (30, merge(open_arms, {'Root.loc': root_lift(0.06)})),
    (44, REST),
])

bpy.ops.object.select_all(action='SELECT')
bpy.ops.export_scene.gltf(
    filepath=dst,
    export_format='GLB',
    export_animations=True,
    export_animation_mode='ACTIONS',
    export_morph=True,
    export_morph_animation=True,
    export_yup=True,
    export_apply=False,
    export_extras=True,
)
print('EXPORTED', dst)

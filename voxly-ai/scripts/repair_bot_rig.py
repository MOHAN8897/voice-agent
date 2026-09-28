"""Rebuild Voxly's arm symmetry and bake gestures with Blender 5.2.
blender --background --python scripts/repair_bot_rig.py -- --input source.glb --output repaired.glb --blend repaired.blend
Coordinates: X=left, -Y=front, Z=up. No runtime quaternion corrections required.
"""
import argparse, math, sys
from pathlib import Path
import bpy, bmesh
from mathutils import Matrix, Vector, Quaternion

parser=argparse.ArgumentParser()
parser.add_argument('--input',required=True)
parser.add_argument('--output',required=True)
parser.add_argument('--blend',required=True)
args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(Path(args.input).resolve()))
rig=next(o for o in bpy.data.objects if o.type=='ARMATURE')
# Preserve shape keys/materials but replace all old animation ownership.
for o in bpy.data.objects:
 o.animation_data_clear()
 if o.type=='MESH' and o.data.shape_keys: o.data.shape_keys.animation_data_clear()
for action in list(bpy.data.actions): bpy.data.actions.remove(action)
for p in rig.pose.bones: p.matrix_basis=Matrix.Identity(4)
bpy.context.view_layer.update()

# Give raised palms room outside the headphone cups. Extend only the two
# arm segments, keeping hand size and the existing idle wrist targets intact.
stretch=1.40
old_rest={b.name:b.matrix_local.copy() for b in rig.data.bones}
upper=rig.data.bones['RightUpperArm']
fore=rig.data.bones['RightForearm']
elbow_shift=(upper.tail_local-upper.head_local)*(stretch-1)
wrist_shift=elbow_shift+(fore.tail_local-fore.head_local)*(stretch-1)
bpy.context.view_layer.objects.active=rig;rig.select_set(True)
bpy.ops.object.mode_set(mode='EDIT')
for bone in rig.data.edit_bones:
 if bone.name=='RightUpperArm':bone.tail+=elbow_shift
 elif bone.name=='RightForearm':
  bone.head+=elbow_shift;bone.tail+=wrist_shift
 elif bone.name=='RightHand' or bone.name.startswith('RightFinger'):
  bone.head+=wrist_shift;bone.tail+=wrist_shift
bpy.ops.object.mode_set(mode='OBJECT')
deforms={}
for bone in rig.data.bones:
 if bone.name in ['RightUpperArm','RightForearm','RightHand'] or bone.name.startswith('RightFinger'):
  scale=Matrix.Diagonal((1,stretch if bone.name in ['RightUpperArm','RightForearm'] else 1,1,1))
  deforms[bone.name]=bone.matrix_local @ scale @ old_rest[bone.name].inverted()
for obj in bpy.data.objects:
 if obj.type!='MESH' or not obj.name.startswith('Right'):continue
 to_rig=rig.matrix_world.inverted() @ obj.matrix_world
 from_rig=to_rig.inverted()
 for vertex in obj.data.vertices:
  pos=to_rig @ vertex.co;delta=Vector((0,0,0))
  for group in vertex.groups:
   transform=deforms.get(obj.vertex_groups[group.group].name)
   if transform is not None:delta+=(transform @ pos-pos)*group.weight
  vertex.co=from_rig @ (pos+delta)
 obj.data.update()

mirror=Matrix.Diagonal((-1,1,1,1))
arm_names=['Shoulder','ShoulderJoint','UpperArm','Elbow','Forearm','Wrist','Hand','PalmGlow','PalmInset']
arm_names += [f'Finger{i:02d}{part}' for i in range(1,5) for part in ['', 'Joint','Tip']]
for suffix in arm_names:
 right=bpy.data.objects.get('Right'+suffix)
 old=bpy.data.objects.get('Left'+suffix)
 if not right or right.type!='MESH': continue
 if old: bpy.data.objects.remove(old,do_unlink=True)
 obj=right.copy();obj.data=right.data.copy();obj.name='Left'+suffix
 bpy.context.collection.objects.link(obj)
 obj.data.transform(obj.matrix_world.inverted() @ mirror @ obj.matrix_world)
 bm=bmesh.new();bm.from_mesh(obj.data);bmesh.ops.reverse_faces(bm,faces=list(bm.faces));bm.to_mesh(obj.data);bm.free()
 for group in obj.vertex_groups:
  if group.name.startswith('Right'): group.name='MirrorTmp'+group.name[5:]
 for group in obj.vertex_groups:
  if group.name.startswith('Left'): group.name='Right'+group.name[4:]
 for group in obj.vertex_groups:
  if group.name.startswith('MirrorTmp'): group.name='Left'+group.name[9:]
 for key in ['controlName','rig_bone']:
  if key in obj and str(obj[key]).startswith('Right'):obj[key]='Left'+str(obj[key])[5:]
 obj.data.update()

bpy.context.view_layer.objects.active=rig;rig.select_set(True)
bpy.ops.object.mode_set(mode='EDIT')
for bone in list(rig.data.edit_bones):
 if bone.name.startswith('Right') and any(bone.name[5:].startswith(n) for n in ['Shoulder','UpperArm','Forearm','Hand','Finger']):
  left=rig.data.edit_bones.get('Left'+bone.name[5:])
  left.head=mirror @ bone.head;left.tail=mirror @ bone.tail
  left.align_roll(mirror.to_3x3() @ bone.z_axis)
bpy.ops.object.mode_set(mode='OBJECT')
rig['rig_version']='3.1-head-clearance'
rig['arm_solver']='Two-bone analytic IK; side-constrained elbow poles; fixed segment lengths; palm front calibration'
rig['gesture_blend_seconds']=0.28
scene=bpy.context.scene;scene.render.fps=30
front=Vector((0,-1,0))
def frame(direction):
 y=direction.normalized();x=y.cross(front).normalized();z=x.cross(y).normalized()
 return Matrix((x,y,z)).transposed().to_4x4()

def smooth(x):
 x=max(0,min(1,x));return x*x*(3-2*x)
def envelope(t,d):return smooth(t/.65)*smooth((d-t)/.65)
arm_info={}
for side,sign in [('Left',1),('Right',-1)]:
 names=[side+n for n in ['UpperArm','Forearm','Hand']]
 correction=[]
 for name in names:
  bone=rig.data.bones[name]
  reference=Vector((0,0,-1)) if name.endswith('Hand') else bone.tail_local-bone.head_local
  correction.append(frame(reference).inverted() @ bone.matrix_local.to_quaternion().to_matrix().to_4x4())
 arm_info[side]=(sign,names,correction)

def pose_arm(side,t,kind,weight,duration):
 sign,names,correction=arm_info[side]
 upper,fore,hand=[rig.pose.bones[n] for n in names]
 shoulder=rig.data.bones[names[0]].head_local.copy()
 a=(rig.data.bones[names[1]].head_local-shoulder).length
 b=(rig.data.bones[names[2]].head_local-rig.data.bones[names[1]].head_local).length
 # Idle hands hang naturally outside the body, palms front, thumbs mirrored.
 wrist=Vector((sign*1.94,-.24,1.16))
 breath=math.sin(t*math.tau/duration)*.018
 wrist.x+=sign*breath
 lift=0.;think=0.;dance=0.
 if kind in ['GREETING','WAVE','RIGHT_HAND_WAVE'] and side=='Right':lift=weight
 elif kind=='LEFT_HAND_WAVE' and side=='Left':lift=weight
 elif kind in ['DOUBLE_WAVE','CELEBRATE','ROLL_DOUBLE_WAVE','DOUBLE_ROLL_DOUBLE_WAVE']:lift=weight
 elif kind=='THINKING' and side=='Right':think=weight
 elif kind=='DANCE':dance=weight
 if lift:
  wrist=wrist.lerp(Vector((sign*(2.72+.045*math.sin(t*8+sign*.35)),-.32,2.25)),lift)
 if think:wrist=wrist.lerp(Vector((-2.72,-.42,1.88)),think)
 if dance:wrist=wrist.lerp(Vector((sign*(2.04+.06*math.sin(t*5)),-.40,1.80+.22*math.sin(t*5+sign*1.5))),dance)
 if kind in ['SPEAKING','TALKING']:
  beat=.5+.5*math.sin(t*math.tau/2+sign*.7)
  wrist+=Vector((sign*.04*beat,-.10*beat,.12*beat))
 direction=wrist-shoulder;distance=max(abs(a-b)+.035,min(direction.length,a+b-.025));direction.normalize()
 wrist=shoulder+direction*distance
 pole=Vector((sign,.25,-.2));pole=(pole-direction*pole.dot(direction)).normalized()
 along=(a*a-b*b+distance*distance)/(2*distance)
 elbow=shoulder+direction*along+pole*math.sqrt(max(0,a*a-along*along))
 finger=Vector((sign*.08,-.02,-1))
 angle=math.pi*lift
 if lift:finger=Vector((sign*(.08+.17*lift+.6*math.sin(angle)+.10*math.sin(t*8)*lift),-.02-.01*lift,-math.cos(angle)))
 if think:finger=finger.lerp(Vector((-.12,-.15,1)),think)
 if dance:finger=finger.lerp(Vector((sign*.55,-.15,-.7)),dance)
 for p,start,end,corr in [(upper,shoulder,elbow,correction[0]),(fore,elbow,wrist,correction[1]),(hand,wrist,wrist+finger,correction[2])]:
  mat=frame(end-start)@corr;mat.translation=start
  # Body transform is shared by both shoulders and every arm target.
  body=rig.pose.bones['Body'].matrix @ rig.data.bones['Body'].matrix_local.inverted()
  p.matrix=body @ mat
  bpy.context.view_layer.update()

clips={'IDLE':4,'FLOAT':4,'HAPPY':4,'LISTENING':4,'SAD':4,'SURPRISED':4,'EXCITED':4,'SPEAKING':4,'TALKING':4,
 'GREETING':3.2,'WAVE':3.2,'RIGHT_HAND_WAVE':3.2,'LEFT_HAND_WAVE':3.2,'DOUBLE_WAVE':2.8,'CELEBRATE':2.8,
 'ROLL_DOUBLE_WAVE':2.8,'DOUBLE_ROLL_DOUBLE_WAVE':4,'THINKING':3,'DANCE':3}
for kind,duration in clips.items():
 action=bpy.data.actions.new(kind);action.use_fake_user=True
 rig.animation_data_create();rig.animation_data.action=action
 total=round(duration*30)
 for index in range(total+1):
  scene.frame_set(index+1)
  for p in rig.pose.bones:p.matrix_basis=Matrix.Identity(4);p.rotation_mode='QUATERNION'
  t=index/30;w=envelope(t,duration)
  # Looping breathing starts and ends in the same pose; gestures settle to idle.
  rig.pose.bones['Body'].rotation_quaternion=Quaternion((0,0,1),math.sin(t*math.tau/(duration))*.018)
  if kind=='DANCE':rig.pose.bones['Body'].rotation_quaternion=Quaternion((0,0,1),math.sin(t*5)*.065*w)
  if kind=='THINKING':rig.pose.bones['Head'].rotation_quaternion=Quaternion((0,0,1),-.10*w)
  elif kind in ['LISTENING','TALKING','SPEAKING']:rig.pose.bones['Head'].rotation_quaternion=Quaternion((1,0,0),math.sin(t*math.tau/duration)*.025)
  bpy.context.view_layer.update()
  for side in arm_info:pose_arm(side,t,kind,w,duration)
  for p in rig.pose.bones:
   p.rotation_quaternion.normalize()
   p.keyframe_insert('location',frame=index+1,group=p.name)
   p.keyframe_insert('rotation_quaternion',frame=index+1,group=p.name)
   p.keyframe_insert('scale',frame=index+1,group=p.name)
 action['gesture']=kind;action['duration_seconds']=duration
# Separate accent materials keep the face/body palette unchanged.
def accent(name,base,emission,strength,metallic=.25):
 mat=bpy.data.materials.new(name);mat.use_nodes=True
 shader=next(n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
 shader.inputs['Base Color'].default_value=(*base,1)
 shader.inputs['Metallic'].default_value=metallic
 shader.inputs['Roughness'].default_value=.32
 shader.inputs['Emission Color'].default_value=(*emission,1)
 shader.inputs['Emission Strength'].default_value=strength
 return mat
mic=accent('MAT_MicrophoneAmber',(.62,.22,.035),(.8,.23,.025),.45,.45)
mic_glow=accent('MAT_MicrophoneGlow',(.9,.44,.08),(1,.38,.045),2)
headphone_glow=accent('MAT_HeadphoneAccent',(.24,.075,.65),(.35,.12,1),2.4)
palm_glow=accent('MAT_PalmGlow',(.16,.07,.6),(.3,.12,1),2.2)
for obj in bpy.data.objects:
 material=None
 if obj.name in ['MicArm','MicHead','MicHinge']:material=mic
 elif obj.name=='MicGlow':material=mic_glow
 elif obj.name in ['LeftEarGlow','RightEarGlow','HeadbandGlow']:material=headphone_glow
 elif obj.name in ['LeftPalmGlow','RightPalmGlow']:material=palm_glow
 if material and obj.type=='MESH':
  obj.data.materials.clear();obj.data.materials.append(material)
# Export sampled actions, keeping every morph target.
rig.animation_data.action=bpy.data.actions['IDLE'];scene.frame_start=1;scene.frame_end=121;scene.frame_set(1)
for o in bpy.data.objects:
 if o.type=='MESH' and o.data.shape_keys:
  for key in o.data.shape_keys.key_blocks:
   if key.name in ['HappyEyes','MouthSmile']:key.value=.65
bpy.ops.wm.save_as_mainfile(filepath=str(Path(args.blend).resolve()))
bpy.ops.export_scene.gltf(filepath=str(Path(args.output).resolve()),export_format='GLB',export_animations=True,
 export_animation_mode='ACTIONS',export_force_sampling=True,export_rest_position_armature=True,
 export_extras=True,export_morph=True,export_skins=True,export_yup=True)
print('REPAIRED',args.output,'CLIPS',len(clips))

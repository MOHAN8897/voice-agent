import { AnimationMixer, Euler, Quaternion, LoopOnce, LoopRepeat, MathUtils, Color } from 'three';

export const EXPRESSIONS = {
  NEUTRAL: {
    HappyEyes: 0,
    SquintEyes: 0,
    WideEyes: 0,
    SadEyes: 0,
    MouthSmile: 0,
    MouthSad: 0,
    MouthOpen: 0,
    MouthWide: 0,
    MouthSurprised: 0,
  },
  HAPPY: {
    HappyEyes: 1.0,
    MouthSmile: 1.0,
    WideEyes: 0.1,
    SquintEyes: 0,
    SadEyes: 0,
    MouthSad: 0,
    MouthSurprised: 0,
  },
  THINKING: {
    SquintEyes: 0.9,
    MouthSmile: 0.35,
    HappyEyes: 0,
    WideEyes: 0,
    SadEyes: 0,
    MouthSad: 0,
    MouthSurprised: 0,
  },
  SURPRISED: {
    WideEyes: 1.0,
    MouthSurprised: 1.0,
    HappyEyes: 0,
    SquintEyes: 0,
    SadEyes: 0,
    MouthSmile: 0,
    MouthSad: 0,
  },
  EXCITED: {
    HappyEyes: 1.0,
    WideEyes: 0.6,
    MouthSmile: 1.0,
    MouthWide: 0.85,
    SquintEyes: 0,
    SadEyes: 0,
    MouthSad: 0,
  },
  ANGRY: {
    SquintEyes: 1.0,
    SadEyes: 0.85,
    MouthSad: 1.0,
    HappyEyes: 0,
    WideEyes: 0,
    MouthSmile: 0,
    MouthSurprised: 0,
  },
  SAD: {
    SadEyes: 1.0,
    MouthSad: 1.0,
    HappyEyes: 0,
    WideEyes: 0,
    SquintEyes: 0,
    MouthSmile: 0,
  },
  LISTENING: {
    WideEyes: 0.5,
    HappyEyes: 0.3,
    MouthSmile: 0.4,
    SquintEyes: 0,
    SadEyes: 0,
  },
  CURIOUS: {
    WideEyes: 0.42,
    HappyEyes: 0.48,
    MouthSmile: 0.55,
    MouthSurprised: 0.12,
    SquintEyes: 0,
    SadEyes: 0,
    MouthSad: 0,
  },
  CONFIDENT: {
    HappyEyes: 0.72,
    MouthSmile: 0.82,
    WideEyes: 0.08,
    SquintEyes: 0.08,
    SadEyes: 0,
    MouthSad: 0,
    MouthSurprised: 0,
  },
  SPEAKING: {
    MouthOpen: 0.65,
    MouthSmile: 0.4,
    HappyEyes: 0.3,
  },
};

export const ALL_MORPH_NAMES = [
  'Blink',
  'BlinkLeft',
  'BlinkRight',
  'HappyEyes',
  'SadEyes',
  'WideEyes',
  'SquintEyes',
  'MouthSmile',
  'MouthSad',
  'MouthOpen',
  'MouthWide',
  'MouthSurprised',
];

export function createVoxlyController(gltf, { onExpressionChange } = {}) {
  const nodes = new Map(), bones = new Map(), materials = new Map();
  const clonedMaterials = new Map();

  gltf.scene.traverse((o) => {
    const name = o.userData.controlName || o.name;
    (o.isBone ? bones : nodes).set(name, o);
    if (o.material) {
      const clone = (m) => {
        if (!clonedMaterials.has(m)) clonedMaterials.set(m, m.clone());
        const result = clonedMaterials.get(m);
        materials.set(result.name, result);
        return result;
      };
      o.material = Array.isArray(o.material) ? o.material.map(clone) : clone(o.material);
    }
  });

  // Blender exports skinned geometry beside its original control empty.
  // Resolve facial controls to the morph mesh rather than the detached empty.
  gltf.scene.traverse((o) => {
    if (o.morphTargetDictionary) {
      const control = (o.userData.controlName || o.name).replace(/_Geometry.*$/, '');
      if (['LeftEye', 'RightEye', 'Mouth'].includes(control)) nodes.set(control, o);
    }
  });

  const face = ['LeftEye', 'RightEye', 'Mouth'].flatMap((name) => {
    const meshes = [];
    nodes.get(name)?.traverse((node) => {
      if (node.morphTargetDictionary) meshes.push({ node, name });
    });
    return meshes;
  });
  const mixer = new AnimationMixer(gltf.scene);
  const clips = new Map(gltf.animations.map((c) => [c.name, c]));
  const rest = new Map([...bones].map(([n, b]) => [n, { q: b.quaternion.clone(), p: b.position.clone(), s: b.scale.clone() }]));
  const animated = new Map([...bones].map(([n, b]) => [n, { q: b.quaternion.clone(), p: b.position.clone(), s: b.scale.clone() }]));
  const transitionFrom = new Map([...bones].map(([n, b]) => [n, { q: b.quaternion.clone(), p: b.position.clone(), s: b.scale.clone() }]));
  let transitionTime = 0.28;

  const ring = nodes.get('HoverRing');
  const ringScale = ring ? ring.scale.clone() : null;
  const ringRotation = ring ? ring.quaternion.clone() : null;
  const head = bones.get('Head');
  const body = bones.get('Body');
  const rotation = new Quaternion();
  const euler = new Euler();

  const weights = Object.fromEntries(ALL_MORPH_NAMES.map((k) => [k, 0]));

  let state = 'IDLE';
  let expression = 'HAPPY';
  let action = null;
  let gesture = false;
  let time = 0;
  let amplitude = 0;
  let mouth = 0;
  let pointerX = 0;
  let pointerY = 0;
  let yaw = 0;
  let pitch = 0;
  let blinkStart = -10;
  let nextBlink = 3.0;
  let analyser = null;
  let samples = null;
  let talkingPreview = true;
  let isSpeaking = false;
  const overrides = new Map();

  const audioBars = [];
  for (let i = 0; i <= 4; i++) {
    const lBar = nodes.get(`LeftAudioBar${i}`);
    const rBar = nodes.get(`RightAudioBar${i}`);
    if (lBar) audioBars.push({ node: lBar, index: i });
    if (rBar) audioBars.push({ node: rBar, index: i });
  }

  // Arm motion belongs to the Blender clips; only the whole-avatar spin is procedural.
  let reducedMotion = false;
  let rollTimer = 0;
  let currentRollDuration = 1.6;
  let rollProgress = 0;

  // Autonomous random idle expressions tracking (cycles between vivid expressions)
  let nextRandomExprTime = 3.0;
  let userExpressionLockUntil = 0;
  const RANDOM_IDLE_EXPRS = ['HAPPY', 'THINKING', 'CURIOUS', 'SURPRISED', 'EXCITED', 'CONFIDENT', 'HAPPY', 'THINKING'];
  let randomExprIndex = 0;

  // Autonomous idle gesture loop: cycles body gestures when idle (wave, think, dance, celebrate)
  let nextIdleGestureTime = 6.0;
  let idleGestureIndex = 0;
  const IDLE_GESTURES = ['RIGHT_HAND_WAVE', 'THINKING', 'DANCE', 'DOUBLE_WAVE', 'CELEBRATE', 'LEFT_HAND_WAVE'];

  const defaultGlowColor = new Color('#6344E7');
  const angryGlowColor = new Color('#FF3366');

  const clamp = (v) => (Number.isFinite(v) ? MathUtils.clamp(v, 0, 1) : 0);

  function play(name, once = false) {
    if (reducedMotion && name !== 'IDLE') return;
    const clip = clips.get(name);
    if (!clip) {
      return;
    }
    const next = mixer.clipAction(clip);
    if (next === action && !once) return;
    // Snapshot the visible pose so interrupted/repeated gestures do not snap
    // back to frame zero or accumulate several partially weighted actions.
    for (const [name, pose] of animated) {
      const from = transitionFrom.get(name);
      from.q.copy(pose.q); from.p.copy(pose.p); from.s.copy(pose.s);
    }
    transitionTime = action && !reducedMotion ? 0 : 0.28;
    mixer.stopAllAction();
    next.reset().setLoop(once ? LoopOnce : LoopRepeat, once ? 1 : Infinity);
    next.clampWhenFinished = once;
    next.enabled = true;
    next.setEffectiveWeight(1).setEffectiveTimeScale(1).play();
    action = next;
  }

  function finished(e) {
    if (gesture && e.action === action) {
      gesture = false;
      play(clips.has(state) ? state : 'IDLE');
    }
  }

  function setExpression(name, userInitiated = true) {
    const upper = String(name).toUpperCase();
    if (EXPRESSIONS[upper]) {
      expression = upper;
      if (userInitiated) {
        // Lock user-selected expression for 10 seconds before resuming gentle random idle expressions
        userExpressionLockUntil = time + 10.0;
      }
      if (!gesture && (state === 'IDLE' || state === 'HAPPY')) {
        const clipName = clips.has(upper) ? upper : 'IDLE';
        play(clipName);
      }
      if (onExpressionChange) {
        onExpressionChange(upper);
      }
    }
  }

  function startGesture(name = 'RIGHT_HAND_WAVE', userInitiated = true) {
    if (reducedMotion) return;
    const aliases = { THINK: 'THINKING', TWO_HANDS_HI: 'DOUBLE_WAVE' };
    const upper = String(name).toUpperCase();
    const clipName = aliases[upper] || upper;
    if (!clips.has(clipName)) return;
    gesture = clipName;
    rollTimer = 0;
    rollProgress = 0;
    if (clipName.includes('ROLL')) {
      currentRollDuration = clipName.includes('DOUBLE_ROLL') ? 3.2 : 1.6;
      rollTimer = currentRollDuration;
    }
    setExpression(clipName === 'THINKING' ? 'THINKING' :
      /DOUBLE|CELEBRATE/.test(clipName) ? 'EXCITED' : 'HAPPY', userInitiated);
    play(clipName, true);
  }

  mixer.addEventListener('finished', finished);
  play('IDLE');

  return {
    nodes,
    bones,
    materials,
    mixer,
    get state() {
      return gesture || state;
    },
    get expression() {
      return expression;
    },
    get rollProgress() {
      return rollProgress;
    },
    get currentRollDuration() {
      return currentRollDuration;
    },
    setState(name) {
      const upper = String(name).toUpperCase();
      if (['GREETING', 'WAVE', 'LEFT_HAND_WAVE', 'RIGHT_HAND_WAVE', 'DOUBLE_WAVE', 'ROLL_DOUBLE_WAVE', 'DOUBLE_ROLL_DOUBLE_WAVE', 'CELEBRATE', 'DANCE', 'THINK', 'TWO_HANDS_HI'].includes(upper)) {
        startGesture(upper);
        return;
      }
      if (upper === 'TALKING' || upper === 'SPEAKING') {
        state = 'TALKING';
        isSpeaking = true;
        talkingPreview = true;
        const isGestureActive = gesture;
        if (!isGestureActive) {
          play('TALKING');
        }
        return;
      }
      if (EXPRESSIONS[upper]) {
        state = upper;
        isSpeaking = false;
        setExpression(upper, true);
        if (!gesture) play(clips.has(upper) ? upper : 'IDLE');
        return;
      }
      if (upper === 'IDLE') {
        isSpeaking = false;
        state = 'IDLE';
        const isGestureActive = gesture;
        if (!isGestureActive) {
          gesture = false;
          play('IDLE');
        }
        return;
      }
      state = clips.has(upper) ? upper : 'IDLE';
      const isGestureActive = gesture;
      if (!isGestureActive) {
        gesture = false;
        play(state);
      }
    },
    setExpression(name, userInitiated = true) {
      setExpression(name, userInitiated);
    },
    setReducedMotion(value) {
      reducedMotion = Boolean(value);
      if (reducedMotion) {
        gesture = false;
        rollTimer = 0;
        rollProgress = 0;
        mixer.stopAllAction();
        action = null;
        play('IDLE');
        mixer.update(0);
      } else if (!gesture) play(clips.has(state) ? state : 'IDLE');
    },
    setPointer(x, y) {
      // User-driven look-at stays active under reduced-motion (not decorative).
      const scale = reducedMotion ? 0.55 : 1;
      pointerX = scale * MathUtils.clamp(x, -1, 1);
      pointerY = scale * MathUtils.clamp(y, -1, 1);
    },
    setAudioAmplitude(value) {
      amplitude = clamp(value);
    },
    setSpeaking(val) {
      isSpeaking = Boolean(val);
      if (isSpeaking) {
        talkingPreview = true;
      }
    },
    get isSpeaking() {
      return isSpeaking;
    },
    setTalkingPreview(enabled) {
      talkingPreview = Boolean(enabled);
    },
    attachAnalyser(node) {
      analyser = node;
      samples = node ? new Float32Array(node.fftSize) : null;
    },
    blink() {
      blinkStart = time;
      nextBlink = time + 3 + Math.random() * 3;
    },
    setMorph(name, value) {
      overrides.set(name, clamp(value));
    },
    clearMorph(name) {
      overrides.delete(name);
    },
    playGesture(name = 'RIGHT_HAND_WAVE') {
      startGesture(String(name).toUpperCase(), true);
    },
    update(delta) {
      const dt = MathUtils.clamp(Number.isFinite(delta) ? delta : 0, 0, 0.1);
      time += dt;

      // Restore bone rest states before mixer update
      for (const [name, b] of bones) {
        const r = animated.get(name);
        if (r) {
          b.quaternion.copy(r.q);
          b.position.copy(r.p);
          b.scale.copy(r.s);
        }
      }

      mixer.update(reducedMotion ? 0 : dt);

      transitionTime = Math.min(0.28, transitionTime + dt);
      const progress = transitionTime / 0.28;
      const blend = progress * progress * (3 - 2 * progress);
      if (blend < 1) {
        for (const [name, bone] of bones) {
          const from = transitionFrom.get(name);
          bone.quaternion.slerpQuaternions(from.q, bone.quaternion, blend);
          bone.position.lerpVectors(from.p, bone.position, blend);
          bone.scale.lerpVectors(from.s, bone.scale, blend);
        }
      }

      for (const [name, b] of bones) {
        const r = animated.get(name);
        if (r) {
          r.q.copy(b.quaternion);
          r.p.copy(b.position);
          r.s.copy(b.scale);
        }
      }

      // ROLL PROGRESS UPDATE:
      if (rollTimer > 0) {
        rollTimer -= dt;
        rollProgress = Math.max(0, Math.min(1, 1 - (rollTimer / currentRollDuration)));
      } else {
        rollProgress = 0;
      }

      // AUTONOMOUS RANDOM EXPRESSIONS WHEN IDLE (Every 3.5 to 5.5s):
      const isAnyGestureActive = Boolean(gesture);
      if (time > nextRandomExprTime && time > userExpressionLockUntil && !isAnyGestureActive && (state === 'IDLE' || state === 'HAPPY')) {
        randomExprIndex = (randomExprIndex + 1) % RANDOM_IDLE_EXPRS.length;
        const nextExpr = RANDOM_IDLE_EXPRS[randomExprIndex];
        setExpression(nextExpr, false);
        nextRandomExprTime = time + 3.5 + Math.random() * 2.0; // Every 3.5 - 5.5s
      }

      // AUTONOMOUS IDLE GESTURE LOOP (Every 5 to 8s when idle, no user interaction):
      if (!reducedMotion && time > nextIdleGestureTime && time > userExpressionLockUntil && !isAnyGestureActive && !isSpeaking && (state === 'IDLE' || state === 'HAPPY')) {
        idleGestureIndex = (idleGestureIndex + 1) % IDLE_GESTURES.length;
        const nextGesture = IDLE_GESTURES[idleGestureIndex];
        startGesture(nextGesture, false);
        nextIdleGestureTime = time + 5.0 + Math.random() * 3.0; // Every 5.0 - 8.0s
      }

      // Audio analysis if available
      if (analyser && samples) {
        if (samples.length !== analyser.fftSize) samples = new Float32Array(analyser.fftSize);
        analyser.getFloatTimeDomainData(samples);
        let sum = 0;
        for (let i = 0; i < samples.length; i++) {
          sum += samples[i] * samples[i];
        }
        amplitude = clamp((Math.sqrt(sum / samples.length) - 0.012) * 8);
      }

      const speaking = isSpeaking || state === 'SPEAKING' || state === 'TALKING';
      const liveSpeechCadence = 0.22 + 0.65 * Math.pow(Math.sin(time * 11), 2) * (0.65 + 0.35 * Math.sin(time * 5.5));
      const audioLevel = speaking 
        ? (amplitude > 0.02 ? amplitude : liveSpeechCadence) 
        : 0;
      mouth = MathUtils.damp(mouth, audioLevel, 20, dt);

      // HEADPHONE EQUALIZER AUDIO BARS ANIMATION:
      if (audioBars.length > 0) {
        for (const { node, index } of audioBars) {
          const barOsc = speaking 
            ? Math.max(0.12, mouth * (0.35 + 0.65 * Math.sin(time * 18 + index * 1.3)))
            : 0.08;
          node.scale.y = MathUtils.damp(node.scale.y, 0.25 + barOsc * 1.6, 22, dt);
        }
      }

      // EXPRESSIONS: Smooth morph target blending
      const targetExpr = EXPRESSIONS[expression] || EXPRESSIONS.HAPPY;

      for (const name of ALL_MORPH_NAMES) {
        const targetVal = targetExpr[name] !== undefined ? targetExpr[name] : 0;
        weights[name] = MathUtils.damp(weights[name], targetVal, 16, dt);
      }

      // Natural eye blinking
      if (time >= nextBlink) {
        blinkStart = time;
        nextBlink = time + 2.8 + Math.random() * 2.5;
      }
      const phase = (time - blinkStart) / 0.15;
      const blink = phase >= 0 && phase < 1 ? Math.pow(Math.sin(phase * Math.PI), 2) : 0;

      // Apply morph targets to face meshes
      for (const { node: o, name: faceName } of face) {
        if (!o || !o.morphTargetDictionary) continue;
        const isEye = faceName !== 'Mouth';
        const sideBlink = overrides.get(faceName === 'LeftEye' ? 'BlinkLeft' : 'BlinkRight') || 0;
        const close = isEye ? Math.max(blink, overrides.get('Blink') || 0, sideBlink) : 0;

        for (const [name, index] of Object.entries(o.morphTargetDictionary)) {
          let value = overrides.has(name) ? overrides.get(name) : (weights[name] || 0);
          if (name === 'MouthOpen' && !overrides.has(name) && speaking) {
            value = Math.max(value, mouth);
          }
          if (isEye) {
            value = name === 'Blink' ? close : name.startsWith('Blink') ? 0 : value * (1 - close);
          }
          o.morphTargetInfluences[index] = clamp(value);
        }
      }

      // HEAD LOOK-AT & EXPRESSIVE TILT
      const tiltAngle = expression === 'THINKING' ? MathUtils.degToRad(8) : 0;
      const pitchOffset = expression === 'ANGRY' ? MathUtils.degToRad(5) : 0;

      // Reduced by 20% for smoother, less aggressive mouse following
      yaw = MathUtils.damp(yaw, pointerX * MathUtils.degToRad(12.8), 14, dt);
      pitch = MathUtils.damp(pitch, -pointerY * MathUtils.degToRad(8), 14, dt);

      if (head && rest.has('Head')) {
        rotation.copy(rest.get('Head').q).invert().multiply(head.quaternion);
        euler.setFromQuaternion(rotation);
        euler.x = MathUtils.clamp(euler.x + pitch + pitchOffset, -MathUtils.degToRad(11.2), MathUtils.degToRad(11.2));
        euler.y = MathUtils.clamp(euler.y + yaw, -MathUtils.degToRad(14.4), MathUtils.degToRad(14.4));
        euler.z = MathUtils.clamp(euler.z + tiltAngle - pointerX * MathUtils.degToRad(3.2), -MathUtils.degToRad(8), MathUtils.degToRad(8));
        rotation.setFromEuler(euler);
        head.quaternion.copy(rest.get('Head').q).multiply(rotation);
      }

      // Body subtle playful jiggle
      if (!reducedMotion && body && rest.has('Body')) {
        const jiggleZ = Math.sin(time * 3.0) * MathUtils.degToRad(1.2);
        const jiggleX = Math.cos(time * 2.5) * MathUtils.degToRad(0.8);
        
        euler.set(jiggleX, 0, jiggleZ);
        rotation.setFromEuler(euler);
        body.quaternion.multiply(rotation);
      }

      // Emissive lighting pulses & Angry red glow
      const isAngry = expression === 'ANGRY';
      const targetColor = isAngry ? angryGlowColor : defaultGlowColor;
      const pulse = 0.5 + 0.5 * Math.sin(time * 2.5);
      const glow = isAngry
        ? 5.0 + pulse * 2.0
        : speaking 
        ? 2.5 + mouth * 3.8 
        : state === 'LISTENING' 
        ? 4.0 
        : state === 'THINKING' 
        ? 1.4 + pulse * 2.4 
        : 1.4;

      if (materials.has('MAT_HeadphoneGlow')) {
        const mat = materials.get('MAT_HeadphoneGlow');
        mat.emissiveIntensity = glow;
        if (mat.emissive) mat.emissive.lerp(targetColor, 0.2);
      }
      if (materials.has('MAT_EyeGlow')) {
        const mat = materials.get('MAT_EyeGlow');
        if (mat.emissive) mat.emissive.lerp(targetColor, 0.2);
      }
      if (materials.has('MAT_MouthGlow')) {
        const mat = materials.get('MAT_MouthGlow');
        if (mat.emissive) mat.emissive.lerp(targetColor, 0.2);
      }
      if (materials.has('MAT_MicrophoneGlow')) {
        materials.get('MAT_MicrophoneGlow').emissiveIntensity = state === 'LISTENING' ? 4.5 : 1.5 + mouth * 2.8;
      }
      if (materials.has('MAT_AccentGlow')) {
        materials.get('MAT_AccentGlow').emissiveIntensity = 1.2 + (speaking ? mouth * 2.2 : pulse * 0.4);
      }
      if (materials.has('MAT_RingGlow')) {
        materials.get('MAT_RingGlow').emissiveIntensity = 1.6 + (state === 'IDLE' ? pulse * 0.4 : glow * 0.4);
      }
      if (materials.has('MAT_BaseGlow')) {
        materials.get('MAT_BaseGlow').emissiveIntensity = 0.9 + (speaking ? mouth * 1.6 : state === 'THINKING' ? pulse * 0.8 : 0.3 * pulse);
      }

      // Microphone subtle nod when speaking
      if (speaking && bones.has('Mic')) {
        bones.get('Mic').rotation.x += mouth * 0.018;
      }

      // Hover ring breathing
      if (ring && ringScale && ringRotation) {
        ring.scale.copy(ringScale).multiplyScalar(1 + (reducedMotion ? 0 : 0.018 * Math.sin(time * 2)));
        ring.quaternion.copy(ringRotation);
      }
    },
    dispose() {
      mixer.removeEventListener('finished', finished);
      mixer.stopAllAction();
      mixer.uncacheRoot(gltf.scene);
      for (const material of clonedMaterials.values()) {
        material.dispose();
      }
    },
  };
}

import { AnimationMixer, Euler, Quaternion, LoopOnce, LoopRepeat, MathUtils, Color, Vector3 } from 'three';

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

// Left arm resting down & raised high wave targets (matching right hand resting pose symmetrically, palm showing to user, clear of head/body)
const TARGET_LEFT_UPPER_DOWN = new Quaternion(-0.735285, -0.45258, -0.45258, 0.22293);
const TARGET_LEFT_FORE_DOWN = new Quaternion(-0.19226, 0.52302, -0.12444, 0.82098);
const TARGET_LEFT_HAND_DOWN = new Quaternion(-0.24555, 0.80967, -0.11110, 0.52135);
const TARGET_LEFT_UPPER_UP = new Quaternion(-0.10690, -0.16083, -0.50364, 0.84206);
const TARGET_LEFT_FORE_UP = new Quaternion(0.08716, 0.00000, 0.00000, 0.99619);
const TARGET_LEFT_HAND_UP = new Quaternion(0.24612, 0.77715, 0.49227, 0.30517);

// Right arm resting down & raised high wave targets (right hand resting position confirmed correct, waving palm showing round glow circles to user, clear of head/body)
const TARGET_RIGHT_UPPER_DOWN = new Quaternion(-0.735285, 0.45258, 0.45258, 0.22293);
const TARGET_RIGHT_FORE_DOWN = new Quaternion(-0.222388, 0.239328, -0.054709, 0.943542);
const TARGET_RIGHT_HAND_DOWN = new Quaternion(-0.00017, -0.2029, 0.04603, 0.97812);
const TARGET_RIGHT_UPPER_UP = new Quaternion(-0.10690, 0.16083, 0.50364, 0.84206);
const TARGET_RIGHT_FORE_UP = new Quaternion(0.08716, 0.00000, 0.00000, 0.99619);
const TARGET_RIGHT_HAND_UP = new Quaternion(-0.13628, 0.45083, -0.55815, 0.68311);

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

  const face = ['LeftEye', 'RightEye', 'Mouth'].map((n) => nodes.get(n));
  const mixer = new AnimationMixer(gltf.scene);
  const clips = new Map(gltf.animations.map((c) => [c.name, c]));
  const rest = new Map([...bones].map(([n, b]) => [n, { q: b.quaternion.clone(), p: b.position.clone(), s: b.scale.clone() }]));
  const animated = new Map([...bones].map(([n, b]) => [n, { q: b.quaternion.clone(), p: b.position.clone(), s: b.scale.clone() }]));

  const ring = nodes.get('HoverRing');
  const ringScale = ring ? ring.scale.clone() : null;
  const ringRotation = ring ? ring.quaternion.clone() : null;
  const head = bones.get('Head');
  const body = bones.get('Body');
  const leftUpper = bones.get('LeftUpperArm');
  const leftFore = bones.get('LeftForearm');
  const leftHand = bones.get('LeftHand');
  const rightUpper = bones.get('RightUpperArm');
  const rightFore = bones.get('RightForearm');
  const rightHand = bones.get('RightHand');

  const rotation = new Quaternion();
  const euler = new Euler();
  const waveXAxis = new Vector3(1, 0, 0);
  const waveZAxis = new Vector3(0, 0, 1);
  const waveYAxis = new Vector3(0, 1, 0);

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

  // Procedural wave duration tracking (matches greeting speech duration ~3.2s)
  let waveTimer = 0;
  const WAVE_DURATION = 3.2;

  // Multiple clicks special movements: two hands wave & 360 roll
  let twoHandsWaveTimer = 0;
  let twoHandsWaveDuration = 2.8;
  const TWO_HANDS_DURATION = 2.8;
  let rollTimer = 0;
  let currentRollDuration = 1.6;
  const ROLL_DURATION = 1.6;
  let rollProgress = 0;
  let activeWaveSide = 'RIGHT';

  // New procedural interaction gestures: Think & Dance
  let thinkTimer = 0;
  const THINK_DURATION = 2.6;
  let danceTimer = 0;
  const DANCE_DURATION = 2.8;

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
    const clip = clips.get(name);
    if (!clip) {
      return;
    }
    const next = mixer.clipAction(clip);
    if (next === action && !once) return;
    next.reset().setLoop(once ? LoopOnce : LoopRepeat, once ? 1 : Infinity);
    next.clampWhenFinished = once;
    next.enabled = true;
    next.setEffectiveWeight(1).setEffectiveTimeScale(1).play();
    if (action && action !== next) next.crossFadeFrom(action, 0.25, false);
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
      const target = EXPRESSIONS[upper];
      for (const k of ALL_MORPH_NAMES) {
        weights[k] = target[k] !== undefined ? target[k] : 0;
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
    gesture = name;
    const upper = String(name).toUpperCase();
    if (upper === 'DOUBLE_WAVE' || upper === 'ROLL_DOUBLE_WAVE' || upper === 'TWO_HANDS_HI' || upper === 'CELEBRATE' || upper.includes('DOUBLE_ROLL')) {
      twoHandsWaveDuration = upper.includes('DOUBLE_ROLL') ? TWO_HANDS_DURATION * 1.4 : TWO_HANDS_DURATION;
      twoHandsWaveTimer = twoHandsWaveDuration;
      waveTimer = 0;
      thinkTimer = 0;
      danceTimer = 0;
      if (upper.includes('ROLL')) {
        currentRollDuration = upper.includes('DOUBLE_ROLL') ? ROLL_DURATION * 2 : ROLL_DURATION;
        rollTimer = currentRollDuration;
      }
      setExpression('EXCITED', userInitiated);
      play(clips.has('EXCITED') ? 'EXCITED' : 'IDLE', true);
      return;
    }

    if (upper === 'THINK' || upper === 'THINKING') {
      thinkTimer = THINK_DURATION;
      waveTimer = 0;
      twoHandsWaveTimer = 0;
      rollTimer = 0;
      danceTimer = 0;
      setExpression('THINKING', userInitiated);
      play(clips.has('THINKING') ? 'THINKING' : 'IDLE', true);
      return;
    }

    if (upper === 'DANCE') {
      danceTimer = DANCE_DURATION;
      waveTimer = 0;
      twoHandsWaveTimer = 0;
      rollTimer = 0;
      thinkTimer = 0;
      setExpression('HAPPY', userInitiated);
      play(clips.has('HAPPY') ? 'HAPPY' : 'IDLE', true);
      return;
    }

    activeWaveSide = upper === 'LEFT_HAND_WAVE' ? 'LEFT' : 'RIGHT';
    waveTimer = WAVE_DURATION;
    twoHandsWaveTimer = 0;
    rollTimer = 0;
    thinkTimer = 0;
    danceTimer = 0;
    setExpression('HAPPY', userInitiated);
    const clipName = clips.has('RIGHT_HAND_WAVE') ? 'RIGHT_HAND_WAVE' : (clips.has(name) ? name : 'WAVE');
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
      if (upper === 'GREETING' || upper === 'WAVE' || upper === 'LEFT_HAND_WAVE' || upper === 'RIGHT_HAND_WAVE' || upper === 'DOUBLE_WAVE' || upper === 'ROLL_DOUBLE_WAVE') {
        startGesture(upper);
        return;
      }
      if (EXPRESSIONS[upper]) {
        setExpression(upper, true);
        return;
      }
      if (upper === 'TALKING' || upper === 'SPEAKING') {
        state = 'TALKING';
        isSpeaking = true;
        talkingPreview = true;
        const isGestureActive = gesture || waveTimer > 0 || twoHandsWaveTimer > 0 || rollTimer > 0 || thinkTimer > 0 || danceTimer > 0;
        if (!isGestureActive) {
          play('TALKING');
        }
        return;
      }
      if (upper === 'IDLE') {
        isSpeaking = false;
        state = 'IDLE';
        const isGestureActive = gesture || waveTimer > 0 || twoHandsWaveTimer > 0 || rollTimer > 0 || thinkTimer > 0 || danceTimer > 0;
        if (!isGestureActive) {
          gesture = false;
          play('IDLE');
        }
        return;
      }
      state = clips.has(upper) ? upper : 'IDLE';
      const isGestureActive = gesture || waveTimer > 0 || twoHandsWaveTimer > 0 || rollTimer > 0 || thinkTimer > 0 || danceTimer > 0;
      if (!isGestureActive) {
        gesture = false;
        play(state);
      }
    },
    setExpression(name, userInitiated = true) {
      setExpression(name, userInitiated);
    },
    setPointer(x, y) {
      pointerX = MathUtils.clamp(x, -1, 1);
      pointerY = MathUtils.clamp(y, -1, 1);
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

      mixer.update(dt);

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

      // TWO HANDS HI MOVEMENT (BOTH ARMS WAVE EXCITEDLY):
      if (twoHandsWaveTimer > 0) {
        twoHandsWaveTimer -= dt;
        // The timer can be extended for a double roll. Always use the matching
        // duration and clamp the envelope: negative slerp weights were the source
        // of the occasional inside-out hands at the end of those gestures.
        const progress = MathUtils.clamp(1 - (twoHandsWaveTimer / twoHandsWaveDuration), 0, 1);
        const armWeight = MathUtils.clamp(Math.min(progress / 0.2, (1 - progress) / 0.2, 1), 0, 1);

        const waveOsc = Math.sin(time * 12) * 0.28 * armWeight;
        const handOsc = Math.sin(time * 12) * 0.18 * armWeight;

        // Left arm raises up and waves with palm showing round glowing circles to user, clear of head & body
        if (leftUpper) {
          leftUpper.quaternion.copy(TARGET_LEFT_UPPER_DOWN).slerp(TARGET_LEFT_UPPER_UP, armWeight);
          const rUpper = animated.get('LeftUpperArm');
          if (rUpper) rUpper.q.copy(leftUpper.quaternion);
        }
        if (leftFore) {
          const waveOscL = (-0.08 - Math.sin(time * 12) * 0.08) * armWeight;
          leftFore.quaternion.copy(TARGET_LEFT_FORE_DOWN).slerp(TARGET_LEFT_FORE_UP, armWeight);
          leftFore.quaternion.multiply(new Quaternion().setFromAxisAngle(waveZAxis, waveOscL));
          const rFore = animated.get('LeftForearm');
          if (rFore) rFore.q.copy(leftFore.quaternion);
        }
        if (leftHand) {
          const handOscL = (-0.06 - Math.sin(time * 12) * 0.06) * armWeight;
          leftHand.quaternion.copy(TARGET_LEFT_HAND_DOWN).slerp(TARGET_LEFT_HAND_UP, armWeight);
          leftHand.quaternion.multiply(new Quaternion().setFromAxisAngle(waveZAxis, handOscL));
          const rHand = animated.get('LeftHand');
          if (rHand) rHand.q.copy(leftHand.quaternion);
        }

        // Right arm raises up and waves with palm showing round glowing circles to user, clear of head & body
        if (rightUpper) {
          rightUpper.quaternion.copy(TARGET_RIGHT_UPPER_DOWN).slerp(TARGET_RIGHT_UPPER_UP, armWeight);
          const rUpper = animated.get('RightUpperArm');
          if (rUpper) rUpper.q.copy(rightUpper.quaternion);
        }
        if (rightFore) {
          const waveOscR = (0.08 + Math.sin(time * 12) * 0.08) * armWeight;
          rightFore.quaternion.copy(TARGET_RIGHT_FORE_DOWN).slerp(TARGET_RIGHT_FORE_UP, armWeight);
          rightFore.quaternion.multiply(new Quaternion().setFromAxisAngle(waveZAxis, waveOscR));
          const rFore = animated.get('RightForearm');
          if (rFore) rFore.q.copy(rightFore.quaternion);
        }
        if (rightHand) {
          const handOscR = (0.06 + Math.sin(time * 12) * 0.06) * armWeight;
          rightHand.quaternion.copy(TARGET_RIGHT_HAND_DOWN).slerp(TARGET_RIGHT_HAND_UP, armWeight);
          rightHand.quaternion.multiply(new Quaternion().setFromAxisAngle(waveZAxis, handOscR));
          const rHand = animated.get('RightHand');
          if (rHand) rHand.q.copy(rightHand.quaternion);
        }

        if (twoHandsWaveTimer <= 0) {
          gesture = false;
          play(isSpeaking ? 'TALKING' : (clips.has(state) ? state : 'IDLE'));
        }
      } else if (waveTimer > 0) {
        // PROCEDURAL SINGLE-HAND WAVE. The raised hand is selected explicitly so
        // LEFT_HAND_WAVE no longer gets silently rendered as a right-hand wave.
        waveTimer -= dt;
        const progress = 1 - (waveTimer / WAVE_DURATION); // 0 to 1
        const waveArmWeight = MathUtils.clamp(Math.min(progress / 0.22, (1 - progress) / 0.22, 1), 0, 1);

        const isLeftWave = activeWaveSide === 'LEFT';
        const raised = isLeftWave
          ? { upper: leftUpper, fore: leftFore, hand: leftHand, upperDown: TARGET_LEFT_UPPER_DOWN, upperUp: TARGET_LEFT_UPPER_UP, foreDown: TARGET_LEFT_FORE_DOWN, foreUp: TARGET_LEFT_FORE_UP, handDown: TARGET_LEFT_HAND_DOWN, handUp: TARGET_LEFT_HAND_UP, names: ['LeftUpperArm', 'LeftForearm', 'LeftHand'], direction: -1 }
          : { upper: rightUpper, fore: rightFore, hand: rightHand, upperDown: TARGET_RIGHT_UPPER_DOWN, upperUp: TARGET_RIGHT_UPPER_UP, foreDown: TARGET_RIGHT_FORE_DOWN, foreUp: TARGET_RIGHT_FORE_UP, handDown: TARGET_RIGHT_HAND_DOWN, handUp: TARGET_RIGHT_HAND_UP, names: ['RightUpperArm', 'RightForearm', 'RightHand'], direction: 1 };
        const resting = isLeftWave
          ? { upper: rightUpper, fore: rightFore, hand: rightHand, upperDown: TARGET_RIGHT_UPPER_DOWN, foreDown: TARGET_RIGHT_FORE_DOWN, handDown: TARGET_RIGHT_HAND_DOWN, names: ['RightUpperArm', 'RightForearm', 'RightHand'] }
          : { upper: leftUpper, fore: leftFore, hand: leftHand, upperDown: TARGET_LEFT_UPPER_DOWN, foreDown: TARGET_LEFT_FORE_DOWN, handDown: TARGET_LEFT_HAND_DOWN, names: ['LeftUpperArm', 'LeftForearm', 'LeftHand'] };

        // Lock the non-waving arm to its known-good rest pose, while the other
        // arm follows a short, palm-forward wave with a clamped local rotation.
        [[resting.upper, resting.upperDown, resting.names[0]], [resting.fore, resting.foreDown, resting.names[1]], [resting.hand, resting.handDown, resting.names[2]]].forEach(([bone, target, boneName]) => {
          if (!bone) return;
          bone.quaternion.copy(target);
          const saved = animated.get(boneName);
          if (saved) saved.q.copy(bone.quaternion);
        });
        if (raised.upper) {
          raised.upper.quaternion.copy(raised.upperDown).slerp(raised.upperUp, waveArmWeight);
          const saved = animated.get(raised.names[0]);
          if (saved) saved.q.copy(raised.upper.quaternion);
        }
        const wristWave = raised.direction * (0.07 + Math.sin(time * 10.5) * 0.10) * waveArmWeight;
        if (raised.fore) {
          raised.fore.quaternion.copy(raised.foreDown).slerp(raised.foreUp, waveArmWeight);
          raised.fore.quaternion.multiply(new Quaternion().setFromAxisAngle(waveZAxis, wristWave * 0.72));
          const saved = animated.get(raised.names[1]);
          if (saved) saved.q.copy(raised.fore.quaternion);
        }
        if (raised.hand) {
          raised.hand.quaternion.copy(raised.handDown).slerp(raised.handUp, waveArmWeight);
          raised.hand.quaternion.multiply(new Quaternion().setFromAxisAngle(waveZAxis, wristWave));
          const saved = animated.get(raised.names[2]);
          if (saved) saved.q.copy(raised.hand.quaternion);
        }

        if (waveTimer <= 0) {
          gesture = false;
          play(isSpeaking ? 'TALKING' : (clips.has(state) ? state : 'IDLE'));
        }
      } else if (thinkTimer > 0) {
        // PROCEDURAL THOUGHTFUL CHIN TOUCH GESTURE:
        thinkTimer -= dt;
        const progress = 1 - (thinkTimer / THINK_DURATION);
        let armWeight = 1;
        if (progress < 0.22) {
          armWeight = progress / 0.22;
        } else if (progress > 0.78) {
          armWeight = (1 - progress) / 0.22;
        }

        // Left arm strictly at rest
        if (leftUpper) {
          leftUpper.quaternion.copy(TARGET_LEFT_UPPER_DOWN);
          const rUpper = animated.get('LeftUpperArm');
          if (rUpper) rUpper.q.copy(TARGET_LEFT_UPPER_DOWN);
        }
        if (leftFore) {
          leftFore.quaternion.copy(TARGET_LEFT_FORE_DOWN);
          const rFore = animated.get('LeftForearm');
          if (rFore) rFore.q.copy(TARGET_LEFT_FORE_DOWN);
        }
        if (leftHand) {
          leftHand.quaternion.copy(TARGET_LEFT_HAND_DOWN);
          const rHand = animated.get('LeftHand');
          if (rHand) rHand.q.copy(TARGET_LEFT_HAND_DOWN);
        }

        // Right arm raises thoughtfully toward chin / cheek
        if (rightUpper) {
          rightUpper.quaternion.copy(TARGET_RIGHT_UPPER_DOWN).slerp(TARGET_RIGHT_UPPER_UP, armWeight * 0.75);
          const rUpper = animated.get('RightUpperArm');
          if (rUpper) rUpper.q.copy(rightUpper.quaternion);
        }
        if (rightFore) {
          rightFore.quaternion.copy(TARGET_RIGHT_FORE_DOWN).slerp(TARGET_RIGHT_FORE_UP, armWeight * 0.95);
          const rFore = animated.get('RightForearm');
          if (rFore) rFore.q.copy(rightFore.quaternion);
        }
        if (rightHand) {
          rightHand.quaternion.copy(TARGET_RIGHT_HAND_DOWN).slerp(TARGET_RIGHT_HAND_UP, armWeight * 0.85);
          const rHand = animated.get('RightHand');
          if (rHand) rHand.q.copy(rightHand.quaternion);
        }

        if (thinkTimer <= 0) {
          gesture = false;
          play(isSpeaking ? 'TALKING' : (clips.has(state) ? state : 'IDLE'));
        }
      } else if (danceTimer > 0) {
        // PROCEDURAL RHYTHMIC GROOVE DANCE:
        danceTimer -= dt;
        const progress = 1 - (danceTimer / DANCE_DURATION);
        let armWeight = 1;
        if (progress < 0.2) {
          armWeight = progress / 0.2;
        } else if (progress > 0.8) {
          armWeight = (1 - progress) / 0.2;
        }

        const danceOscL = Math.sin(time * 11) * 0.45 * armWeight;
        const danceOscR = Math.sin(time * 11 + Math.PI) * 0.45 * armWeight;

        if (leftUpper) {
          leftUpper.quaternion.copy(TARGET_LEFT_UPPER_DOWN).slerp(TARGET_LEFT_UPPER_UP, armWeight * 0.65);
          leftUpper.quaternion.multiply(new Quaternion().setFromAxisAngle(waveYAxis, danceOscL * 0.3));
          const rUpper = animated.get('LeftUpperArm');
          if (rUpper) rUpper.q.copy(leftUpper.quaternion);
        }
        if (leftFore) {
          leftFore.quaternion.copy(TARGET_LEFT_FORE_DOWN).slerp(TARGET_LEFT_FORE_UP, armWeight * 0.7);
          const rFore = animated.get('LeftForearm');
          if (rFore) rFore.q.copy(leftFore.quaternion);
        }

        if (rightUpper) {
          rightUpper.quaternion.copy(TARGET_RIGHT_UPPER_DOWN).slerp(TARGET_RIGHT_UPPER_UP, armWeight * 0.65);
          rightUpper.quaternion.multiply(new Quaternion().setFromAxisAngle(waveYAxis, danceOscR * 0.3));
          const rUpper = animated.get('RightUpperArm');
          if (rUpper) rUpper.q.copy(rightUpper.quaternion);
        }
        if (rightFore) {
          rightFore.quaternion.copy(TARGET_RIGHT_FORE_DOWN).slerp(TARGET_RIGHT_FORE_UP, armWeight * 0.7);
          const rFore = animated.get('RightForearm');
          if (rFore) rFore.q.copy(rightFore.quaternion);
        }
        if (leftHand) {
          leftHand.quaternion.copy(TARGET_LEFT_HAND_DOWN).slerp(TARGET_LEFT_HAND_UP, armWeight * 0.4);
          const rHand = animated.get('LeftHand');
          if (rHand) rHand.q.copy(leftHand.quaternion);
        }
        if (rightHand) {
          rightHand.quaternion.copy(TARGET_RIGHT_HAND_DOWN).slerp(TARGET_RIGHT_HAND_UP, armWeight * 0.4);
          const rHand = animated.get('RightHand');
          if (rHand) rHand.q.copy(rightHand.quaternion);
        }

        if (danceTimer <= 0) {
          gesture = false;
          play(isSpeaking ? 'TALKING' : (clips.has(state) ? state : 'IDLE'));
        }
      } else {
        // BOTH ARMS STRICTLY LOCKED DOWN AT REST
        if (leftUpper) {
          leftUpper.quaternion.copy(TARGET_LEFT_UPPER_DOWN);
          const rUpper = animated.get('LeftUpperArm');
          if (rUpper) rUpper.q.copy(TARGET_LEFT_UPPER_DOWN);
        }
        if (leftFore) {
          leftFore.quaternion.copy(TARGET_LEFT_FORE_DOWN);
          const rFore = animated.get('LeftForearm');
          if (rFore) rFore.q.copy(TARGET_LEFT_FORE_DOWN);
        }
        if (leftHand) {
          leftHand.quaternion.copy(TARGET_LEFT_HAND_DOWN);
          const rHand = animated.get('LeftHand');
          if (rHand) rHand.q.copy(TARGET_LEFT_HAND_DOWN);
        }

        if (rightUpper) {
          rightUpper.quaternion.copy(TARGET_RIGHT_UPPER_DOWN);
          const rUpper = animated.get('RightUpperArm');
          if (rUpper) rUpper.q.copy(TARGET_RIGHT_UPPER_DOWN);
        }
        if (rightFore) {
          rightFore.quaternion.copy(TARGET_RIGHT_FORE_DOWN);
          const rFore = animated.get('RightForearm');
          if (rFore) rFore.q.copy(TARGET_RIGHT_FORE_DOWN);
        }
        if (rightHand) {
          rightHand.quaternion.copy(TARGET_RIGHT_HAND_DOWN);
          const rHand = animated.get('RightHand');
          if (rHand) rHand.q.copy(TARGET_RIGHT_HAND_DOWN);
        }
      }

      // AUTONOMOUS RANDOM EXPRESSIONS WHEN IDLE (Every 3.5 to 5.5s):
      const isAnyGestureActive = waveTimer > 0 || twoHandsWaveTimer > 0 || rollTimer > 0 || thinkTimer > 0 || danceTimer > 0;
      if (time > nextRandomExprTime && time > userExpressionLockUntil && !isAnyGestureActive && (state === 'IDLE' || state === 'HAPPY')) {
        randomExprIndex = (randomExprIndex + 1) % RANDOM_IDLE_EXPRS.length;
        const nextExpr = RANDOM_IDLE_EXPRS[randomExprIndex];
        setExpression(nextExpr, false);
        nextRandomExprTime = time + 3.5 + Math.random() * 2.0; // Every 3.5 - 5.5s
      }

      // AUTONOMOUS IDLE GESTURE LOOP (Every 5 to 8s when idle, no user interaction):
      if (time > nextIdleGestureTime && time > userExpressionLockUntil && !isAnyGestureActive && !isSpeaking && (state === 'IDLE' || state === 'HAPPY')) {
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
      for (const o of face) {
        if (!o || !o.morphTargetDictionary) continue;
        const isEye = o !== face[2];
        const sideBlink = overrides.get(o === face[0] ? 'BlinkLeft' : 'BlinkRight') || 0;
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
      if (body && rest.has('Body')) {
        const jiggleZ = Math.sin(time * 3.0) * MathUtils.degToRad(1.2);
        const jiggleX = Math.cos(time * 2.5) * MathUtils.degToRad(0.8);
        
        euler.set(jiggleX, 0, jiggleZ);
        rotation.setFromEuler(euler);
        body.quaternion.copy(rest.get('Body').q).multiply(rotation);
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
        ring.scale.copy(ringScale).multiplyScalar(1 + 0.018 * Math.sin(time * 2));
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

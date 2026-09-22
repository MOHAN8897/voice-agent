import React, { useState, useRef, useEffect } from 'react';
import { VoxlyScene } from '../three/VoxlyScene';
import { HERO_CONTENT } from '../data/siteContent';
import { voiceAgent } from '../services/voiceAgent';
import { Check, Mic, X } from 'lucide-react';


// CLICK_INTERACTIONS: Each click on the robot triggers the next interaction in sequence.
// First click is always a friendly wave greeting. Subsequent clicks cycle through varied responses.
const CLICK_INTERACTIONS = [
  {
    title: "Voxly",
    message: "Hello! Hiii! 👋 I'm Voxly! Nice to meet you!",
    speech: "Hello! Hiii! I'm Voxly! Nice to meet you!",
    audioSrc: "/audio/voxly/hero_step1.mp3",
    expression: "HAPPY",
    gesture: "RIGHT_HAND_WAVE",
    mood: "friendly",
  },
  {
    title: "Voxly",
    message: "Hiii! Excited to scale your voice workflows! ✨ Ready for 500+ calls.",
    speech: "Hiii! Excited to scale your voice workflows! Ready for 500 plus calls.",
    audioSrc: "/audio/voxly/hero_step2.mp3",
    expression: "EXCITED",
    gesture: "DOUBLE_WAVE",
    mood: "excited",
  },
  {
    title: "Voxly (Acrobatic)",
    message: "Whoaaa! Watch this barrel roll! 🎉 360° celebratory spin & wave!",
    speech: "Whoaaa! Watch this barrel roll! 360 degree celebratory spin and wave!",
    audioSrc: "/audio/voxly/hero_step3.mp3",
    expression: "EXCITED",
    gesture: "ROLL_DOUBLE_WAVE",
    mood: "celebration",
  },
  {
    title: "Voxly • RAG Intelligence",
    message: "Analyzing your knowledge base... 💡 I can resolve 85% of tier-one questions instantly!",
    speech: "Analyzing your knowledge base... I can resolve 85 percent of tier-one questions instantly!",
    audioSrc: "/audio/voxly/hero_think.mp3",
    expression: "THINKING",
    gesture: "THINKING",
    mood: "smart",
  },
  {
    title: "Voxly",
    message: "Don't tickle me! Haha! Double hi to you! 👋😄👋",
    speech: "Don't tickle me! Haha! Double high five to you!",
    audioSrc: "/audio/voxly/hero_step4.mp3",
    expression: "EXCITED",
    gesture: "DOUBLE_WAVE",
    mood: "playful",
  },
  {
    title: "Voxly • Pipeline Qualified",
    message: "Woohoo! 🎉 Another qualified lead booked straight into your calendar!",
    speech: "Woohoo! Another qualified lead booked straight into your calendar!",
    audioSrc: "/audio/voxly/hero_celebrate.mp3",
    expression: "EXCITED",
    gesture: "CELEBRATE",
    mood: "celebration",
  },
  {
    title: "Voxly • High-Speed Groove",
    message: "Look at these moves! 💃 Grooving through phone queues with zero hold times!",
    speech: "Look at these moves! Grooving through phone queues with zero hold times!",
    audioSrc: "/audio/voxly/hero_dance.mp3",
    expression: "HAPPY",
    gesture: "DANCE",
    mood: "playful",
  },
  {
    title: "Voxly",
    message: "Double barrel roll & high five! 🚀✨ Let's conquer customer calls!",
    speech: "Double barrel roll and high five! Let's conquer customer calls!",
    audioSrc: "/audio/voxly/hero_step5.mp3",
    expression: "EXCITED",
    gesture: "DOUBLE_ROLL_DOUBLE_WAVE",
    mood: "celebration",
  },
  {
    title: "Voxly • Double High-Five",
    message: "Double high-five! 🚀✨ Ready to handle 500 simultaneous calls!",
    speech: "Double high-five! Ready to handle 500 simultaneous calls!",
    audioSrc: "/audio/voxly/hero_double_wave.mp3",
    expression: "EXCITED",
    gesture: "DOUBLE_WAVE",
    mood: "celebration",
  },
  {
    title: "Voxly • Sub-400ms Speed",
    message: "Did you know? ⚡ Sub-400ms latency creates natural, fluid human conversations!",
    speech: "Did you know? Sub-400 millisecond response time means natural, human conversation!",
    audioSrc: "/audio/voxly/hero_surprise.mp3",
    expression: "SURPRISED",
    gesture: "RIGHT_HAND_WAVE",
    mood: "fast",
  },
  {
    title: "Voxly • Smart Routing",
    message: "I route calls to the right team instantly! 🧠 No more phone tag!",
    speech: "I route calls to the right team instantly! No more phone tag!",
    audioSrc: "/audio/voxly/hero_think.mp3",
    expression: "THINKING",
    gesture: "THINKING",
    mood: "smart",
  },
  {
    title: "Voxly • Celebration Mode",
    message: "Another happy customer! 🎊 That's what I live for!",
    speech: "Another happy customer! That's what I live for!",
    audioSrc: "/audio/voxly/hero_celebrate.mp3",
    expression: "EXCITED",
    gesture: "CELEBRATE",
    mood: "celebration",
  },
  {
    title: "Voxly • Dance Break",
    message: "Time for a victory dance! 💃🕺 Zero hold times, maximum groove!",
    speech: "Time for a victory dance! Zero hold times, maximum groove!",
    audioSrc: "/audio/voxly/hero_dance.mp3",
    expression: "HAPPY",
    gesture: "DANCE",
    mood: "playful",
  },
  {
    title: "Voxly • Wave Hello",
    message: "Hey there! 👋 Still exploring? Ask me anything about voice AI!",
    speech: "Hey there! Still exploring? Ask me anything about voice AI!",
    audioSrc: "/audio/voxly/hero_wave.mp3",
    expression: "HAPPY",
    gesture: "RIGHT_HAND_WAVE",
    mood: "friendly",
  },
  {
    title: "Voxly • Always Listening",
    message: "I’m all ears. 🎧 Tell me what a great customer conversation sounds like, and I’ll help make it repeatable.",
    speech: "I'm all ears. Tell me what a great customer conversation sounds like, and I'll help make it repeatable.",
    audioSrc: "/audio/voxly/hero_wave.mp3",
    expression: "LISTENING",
    gesture: "LEFT_HAND_WAVE",
    mood: "curious",
  },
  {
    title: "Voxly • Confident Follow-up",
    message: "A warm follow-up, exactly on time. ✨ I keep every promising conversation moving forward.",
    speech: "A warm follow-up, exactly on time. I keep every promising conversation moving forward.",
    audioSrc: "/audio/voxly/hero_step2.mp3",
    expression: "CONFIDENT",
    gesture: "RIGHT_HAND_WAVE",
    mood: "confident",
  },
  {
    title: "Voxly • Curious Mode",
    message: "Ooh, a new challenge! 💫 I can learn your playbook, tone, and handoff rules in one place.",
    speech: "Ooh, a new challenge. I can learn your playbook, tone, and handoff rules in one place.",
    audioSrc: "/audio/voxly/hero_surprise.mp3",
    expression: "CURIOUS",
    gesture: "THINKING",
    mood: "curious",
  },
  {
    title: "Voxly • Team Win",
    message: "That’s a win for your team! 🌟 I’ll celebrate the booked meeting and tee up the next best action.",
    speech: "That's a win for your team. I'll celebrate the booked meeting and tee up the next best action.",
    audioSrc: "/audio/voxly/hero_celebrate.mp3",
    expression: "EXCITED",
    gesture: "CELEBRATE",
    mood: "celebration",
  },
];

export function Hero({
  botState: initialBotState = 'IDLE',
  setBotState: externalSetBotState = null,
  onTalkToMe,
  onWatchDemo,
  onGetStarted,
  botControllerRef,
  isModalOpen = false,
}) {
  const heroRef = useRef(null);
  const sceneContainerRef = useRef(null);
  const heroPointerRef = useRef({ x: 0, y: 0 });
  const botRectRef = useRef(null);
  const [localBotState, setLocalBotState] = useState(initialBotState);
  const setBotState = externalSetBotState || setLocalBotState;
  const botState = externalSetBotState ? initialBotState : localBotState;
  const [activePopup, setActivePopup] = useState(null);
  const [isHeroInView, setIsHeroInView] = useState(true);

  const clickCountRef = useRef(0);
  const lastClickTimeRef = useRef(0);
  const popupAutoDismissTimerRef = useRef(null);
  const loopIndexRef = useRef(0);
  const isHoveredRef = useRef(false);
  const isInteractingRef = useRef(false);

  // Preload all robot voice audio clips for zero-delay instant playback
  useEffect(() => {
    const audioUrls = [
      ...CLICK_INTERACTIONS.map((s) => s.audioSrc).filter(Boolean),
      '/audio/voxly/hero_pouty.mp3',
      '/audio/voxly/hero_wave.mp3',
      '/audio/voxly/hero_roll.mp3',
      '/audio/voxly/hero_think.mp3',
      '/audio/voxly/hero_celebrate.mp3',
      '/audio/voxly/hero_dance.mp3',
      '/audio/voxly/hero_surprise.mp3',
    ];
    audioUrls.forEach((url) => {
      try {
        const audio = new Audio();
        audio.src = url;
        audio.preload = 'auto';
      } catch (e) {}
    });
  }, []);

  // Clean up all timers on unmount
  useEffect(() => {
    return () => {
      if (popupAutoDismissTimerRef.current) clearTimeout(popupAutoDismissTimerRef.current);
    };
  }, []);

  // Subscribe to voiceAgent state to keep botState, lip-sync, and speaking in continuous sync
  useEffect(() => {
    const unsubscribe = voiceAgent.subscribe((event, data) => {
      if (event === 'stateChange') {
        if (data.state === 'TALKING' || data.state === 'SPEAKING') {
          if (setBotState) setBotState('TALKING');
          if (botControllerRef.current) {
            botControllerRef.current.setSpeaking(true);
            botControllerRef.current.setState('TALKING');
          }
        } else if (data.state === 'IDLE') {
          if (setBotState) setBotState('IDLE');
          if (botControllerRef.current) {
            botControllerRef.current.setSpeaking(false);
            botControllerRef.current.setState('IDLE');
          }
        }
      }
    });
    return () => unsubscribe();
  }, [setBotState, botControllerRef]);

  // Helper to manage dialogue auto-dismiss timer
  const resetDismissTimer = (durationMs = 3000) => {
    if (popupAutoDismissTimerRef.current) {
      clearTimeout(popupAutoDismissTimerRef.current);
    }
    popupAutoDismissTimerRef.current = setTimeout(() => {
      if (!isHoveredRef.current && !voiceAgent.isSpeaking) {
        setActivePopup(null);
        isInteractingRef.current = false;
      } else if (voiceAgent.isSpeaking) {
        resetDismissTimer(1000);
      }
    }, durationMs);
  };

  // Centralized step execution for user-initiated interactions
  const executeStep = (stepData) => {
    isInteractingRef.current = true;

    // 1. Immediately halt any active voice to ensure zero overlapping or duplicate audio
    voiceAgent.stopTTS();

    setActivePopup(stepData);

    // Cancel dismiss timer while audio is speaking
    if (popupAutoDismissTimerRef.current) {
      clearTimeout(popupAutoDismissTimerRef.current);
    }

    // Trigger 3D robot speaking state, expression & physical animation
    if (botControllerRef?.current) {
      botControllerRef.current.setSpeaking(true);
      botControllerRef.current.setState('TALKING');
      botControllerRef.current.setExpression(stepData.expression, true);
      if (stepData.gesture) {
        botControllerRef.current.playGesture(stepData.gesture);
      }
    }
    if (setBotState) setBotState('TALKING');

    const soundType = stepData.mood === 'angry'
      ? 'tickle'
      : stepData.gesture?.includes('ROLL')
      ? 'roll'
      : stepData.gesture?.includes('THINK')
      ? 'think'
      : stepData.gesture?.includes('CELEBRATE')
      ? 'celebrate'
      : stepData.gesture?.includes('DANCE')
      ? 'dance'
      : stepData.gesture?.includes('WAVE')
      ? 'wave'
      : 'happy';

    const onAudioEnd = () => {
      if (botControllerRef?.current) {
        botControllerRef.current.setSpeaking(false);
        botControllerRef.current.setState('IDLE');
      }
      if (setBotState) setBotState('IDLE');
      // Speech finished: dismiss dialogue box after 3 seconds
      resetDismissTimer(3000);
      isInteractingRef.current = false;
    };

    const onAudioStart = () => {
      if (botControllerRef?.current) {
        botControllerRef.current.setSpeaking(true);
        botControllerRef.current.setState('TALKING');
      }
      if (setBotState) setBotState('TALKING');
    };

    // Play high-clarity voice clip with lip-sync and robotic SFX, with automatic TTS fallback
    if (stepData.audioSrc) {
      voiceAgent.playAudioClip(stepData.audioSrc, onAudioEnd, onAudioStart, {
        soundType,
        fallbackText: stepData.speech,
      });
    } else {
      voiceAgent.playTTS(stepData.speech, onAudioEnd, onAudioStart, { soundType });
    }
  };

  // Section observer: Detect when user is in Hero section vs other sections
  useEffect(() => {
    if (!heroRef.current) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        setIsHeroInView(entry.isIntersecting);
      },
      { threshold: 0.2 }
    );

    observer.observe(heroRef.current);
    return () => observer.disconnect();
  }, []);

  // When user scrolls away or modal opens, dismiss dialogue cleanly
  useEffect(() => {
    if (!isHeroInView || isModalOpen) {
      if (popupAutoDismissTimerRef.current) clearTimeout(popupAutoDismissTimerRef.current);
      setActivePopup(null);
      isInteractingRef.current = false;
      clickCountRef.current = 0;
      loopIndexRef.current = 0;
      if (botControllerRef?.current) {
        botControllerRef.current.setExpression('HAPPY', false);
      }
    }
  }, [isHeroInView, isModalOpen]);

  const handleMouseEnterPopup = () => {
    isHoveredRef.current = true;
    if (popupAutoDismissTimerRef.current) {
      clearTimeout(popupAutoDismissTimerRef.current);
    }
  };

  const handleMouseLeavePopup = () => {
    isHoveredRef.current = false;
    // Auto-dismiss after 3 seconds when mouse leaves
    resetDismissTimer(3000);
  };

  // HIGH-PERFORMANCE ZERO-RERENDER MOUSE TRACKING:
  // Updates heroPointerRef directly at 60/120fps without triggering React component re-renders.
  // Caches container bounding rect on scroll/resize to eliminate layout thrashing.
  useEffect(() => {
    const updateBotRect = () => {
      if (sceneContainerRef.current) {
        botRectRef.current = sceneContainerRef.current.getBoundingClientRect();
      }
    };

    updateBotRect();
    window.addEventListener('resize', updateBotRect, { passive: true });
    window.addEventListener('scroll', updateBotRect, { passive: true });

    const handleMouseMove = (e) => {
      if (!botRectRef.current && sceneContainerRef.current) {
        botRectRef.current = sceneContainerRef.current.getBoundingClientRect();
      }
      const rect = botRectRef.current;
      if (!rect) return;

      const isDesktop = window.innerWidth >= 960;
      // On desktop, the 3D robot is shifted left (-0.22 in Three.js ≈ -55px on screen)
      const botOffsetX = isDesktop ? -55 : 0;
      const botCenterX = rect.left + rect.width * 0.5 + botOffsetX;
      const botCenterY = rect.top + rect.height * 0.45;

      const diffX = e.clientX - botCenterX;
      const diffY = e.clientY - botCenterY;

      // Natural, responsive distance normalization across viewport
      const maxDistX = Math.max(window.innerWidth * 0.45, 380);
      const maxDistY = Math.max(window.innerHeight * 0.40, 280);

      const normX = Math.max(-1, Math.min(1, diffX / maxDistX));
      const normY = -Math.max(-1, Math.min(1, diffY / maxDistY));

      heroPointerRef.current.x = normX;
      heroPointerRef.current.y = normY;
    };

    const handleMouseLeave = () => {
      heroPointerRef.current.x = 0;
      heroPointerRef.current.y = 0;
    };

    window.addEventListener('mousemove', handleMouseMove, { passive: true });
    document.addEventListener('mouseleave', handleMouseLeave);

    return () => {
      window.removeEventListener('resize', updateBotRect);
      window.removeEventListener('scroll', updateBotRect);
      window.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseleave', handleMouseLeave);
    };
  }, []);

  // MANUAL CLICKS:
  // First click is always "Hi!" with right hand raised high waving palm front.
  // Subsequent clicks cycle through dialogue responses, voices, and body interaction states.
  // Protection: when clicking initiates an interaction, until that interaction is completed
  // the 3D model does NOT jump to a different interaction (prevents manhandling/click-spam).
  const handleBotClick = () => {
    if (voiceAgent.isSpeaking || isInteractingRef.current) {
      return;
    }

    const now = Date.now();
    if (now - lastClickTimeRef.current < 400) {
      return; // Ignore duplicate synthetic/bubbling events
    }
    lastClickTimeRef.current = now;

    clickCountRef.current += 1;
    const count = clickCountRef.current;

    let stepData = null;
    if (count <= CLICK_INTERACTIONS.length) {
      stepData = CLICK_INTERACTIONS[count - 1];
      loopIndexRef.current = count % CLICK_INTERACTIONS.length;
    } else {
      // Excess clicks: Pouty / angry expression
      stepData = {
        title: "Voxly (Pouty)",
        message: "Hey! Don't poke me, I have calls to make! 😤 Click 'Live Mic Chat' instead!",
        speech: "Hey! Don't poke me, I have calls to make! Click live mic chat instead!",
        audioSrc: "/audio/voxly/hero_pouty.mp3",
        expression: "ANGRY",
        gesture: null,
        mood: "angry",
      };
      // Reset counter after angry poke so next clicks restart fresh from Step 1
      clickCountRef.current = 0;
      loopIndexRef.current = 0;
    }

    executeStep(stepData);
  };

  return (
    <section
      ref={heroRef}
      className="relative min-h-[90vh] pt-28 pb-16 overflow-hidden flex items-center bg-[#FAF9FD]"
    >
      <div className="max-w-7xl mx-auto px-6 sm:px-8 w-full">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 lg:gap-8 items-center">
          
          {/* LEFT COLUMN: Solid typography & tactile CTAs */}
          <div className="lg:col-span-6 flex flex-col items-start z-10">
            {/* Eyebrow badge: Clean restrained label */}
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-lg bg-white border border-[#E4E2EB] text-[#6344E7] text-xs font-bold tracking-wider uppercase mb-5 shadow-craft-xs">
              <span className="w-1.5 h-1.5 rounded-full bg-[#10B981]" />
              <span>{HERO_CONTENT.eyebrow}</span>
            </div>

            {/* Main Headline: Solid high-contrast text */}
            <h1 className="text-4xl sm:text-5xl lg:text-[56px] font-extrabold text-[#0F0E17] leading-[1.08] tracking-tight mb-5">
              {HERO_CONTENT.titleLine1}{' '}
              <span className="block text-[#0F0E17]">
                {HERO_CONTENT.titleHighlight}
              </span>
            </h1>

            {/* Supporting Copy */}
            <p className="text-sm sm:text-base text-[#524E5E] leading-relaxed max-w-xl mb-7">
              {HERO_CONTENT.subtitle}
            </p>

            {/* CTA Buttons: Emil Kowalski tactile buttons */}
            <div className="flex flex-wrap items-center gap-3.5 sm:gap-4 mb-8 w-full sm:w-auto">
              {/* Primary CTA */}
              <button
                onClick={onGetStarted}
                className="inline-flex items-center justify-center gap-2 px-7 py-3.5 rounded-xl text-sm font-semibold text-white bg-[#0F0E17] hover:bg-[#232130] active:scale-[0.98] shadow-sm transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#6344E7]"
              >
                <span>{HERO_CONTENT.ctaPrimary}</span>
              </button>

              {/* Secondary CTA: Talk to AI */}
              <button
                onClick={onTalkToMe}
                className="inline-flex items-center justify-center gap-2.5 px-6 py-3.5 rounded-xl text-sm font-semibold text-[#0F0E17] bg-white hover:bg-[#F9F8FD] border border-[#E4E2EB] active:scale-[0.98] shadow-xs transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#6344E7]"
              >
                <div className="w-6 h-6 rounded-lg bg-[#FAF9FD] border border-[#E4E2EB] flex items-center justify-center text-[#6344E7]">
                  <Mic className="w-3.5 h-3.5" />
                </div>
                <span>{HERO_CONTENT.ctaSecondary}</span>
              </button>
            </div>

            {/* Value Props / Checkmarks */}
            <div className="flex flex-wrap items-center gap-y-2 gap-x-5 text-xs font-semibold text-[#524E5E]">
              {HERO_CONTENT.perks.map((perk) => (
                <div key={perk} className="flex items-center gap-2">
                  <div className="w-4 h-4 rounded-full bg-[#EFECE6] flex items-center justify-center text-[#0F0E17] text-[9px]">
                    <Check className="w-2.5 h-2.5 stroke-[3]" />
                  </div>
                  <span>{perk}</span>
                </div>
              ))}
            </div>
          </div>

          {/* RIGHT COLUMN: 3D Three.js WebGL Scene */}
          <div className="lg:col-span-6 relative flex flex-col items-center justify-center">
            
            {/* 3D WebGL Canvas Container */}
            <div
              ref={sceneContainerRef}
              className="relative w-full h-[380px] sm:h-[440px] lg:h-[500px] flex items-center justify-center cursor-pointer select-none"
            >
              <VoxlyScene
                state={botState}
                onBotClick={handleBotClick}
                pointerRef={heroPointerRef}
                audioAnalyser={voiceAgent.getAnalyser()}
                isInView={isHeroInView}
                onControllerReady={(ctrl) => {
                  botControllerRef.current = ctrl;
                }}
              />

              {/* A lightweight, persistent invitation makes the character's rich
                  click flow discoverable without competing with its dialogue. */}
              {!activePopup && (
                <div className="absolute top-3 left-1/2 -translate-x-1/2 rounded-full border border-[#DCD5FF] bg-white/85 px-3 py-1.5 text-[10px] font-bold tracking-wide text-[#6344E7] shadow-sm backdrop-blur-sm pointer-events-none animate-pulse">
                  Tap Voxly for a surprise ✨
                </div>
              )}

              {/* Dynamic Interactive Dialogue Box on Interaction:
                  Positioned at top-right corner near the robot without touching it.
                  Displays messages only without interaction buttons, ensuring zero visual clutter. */}
              {activePopup && (
                <div
                  onClick={(e) => e.stopPropagation()}
                  onMouseEnter={handleMouseEnterPopup}
                  onMouseLeave={handleMouseLeavePopup}
                  className={`absolute top-1 right-1 sm:top-2 sm:right-2 md:top-2 md:right-3 lg:top-2 lg:right-0 xl:top-2 xl:right-1 w-[calc(100%-20px)] max-w-[245px] sm:max-w-[265px] p-3.5 rounded-2xl shadow-xl border z-30 transition-all ${
                    activePopup.mood === 'angry'
                      ? 'bg-[#111019] text-white border-red-500/40 shadow-xl'
                      : activePopup.mood === 'curious'
                      ? 'bg-[#F7F3FF] text-[#0F0E17] border-[#DCD5FF] shadow-craft-md'
                      : 'bg-white text-[#0F0E17] border-[#E4E2EB] shadow-craft-md'
                  }`}
                >
                  {/* Subtle directional pointer pointing towards the 3D robot */}
                  <div
                    className={`absolute top-6 -left-1.5 w-3 h-3 rotate-45 border-l border-b hidden sm:block ${
                      activePopup.mood === 'angry'
                        ? 'bg-[#111019] border-red-500/40'
                        : 'bg-white border-[#E4E2EB]'
                    }`}
                  />

                  <div className="flex items-center justify-between gap-2 mb-2">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="relative flex h-2 w-2 shrink-0">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#10B981] opacity-75"></span>
                        <span className="relative inline-flex rounded-full h-2 w-2 bg-[#10B981]"></span>
                      </span>
                      <span
                        className={`text-[10.5px] sm:text-[11px] font-bold uppercase tracking-wider truncate ${
                          activePopup.mood === 'angry' ? 'text-red-400' : 'text-[#6344E7]'
                        }`}
                      >
                        {activePopup.title}
                      </span>
                    </div>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setActivePopup(null);
                        isInteractingRef.current = false;
                        voiceAgent.stopTTS();
                      }}
                      className="text-xs font-bold opacity-60 hover:opacity-100 p-0.5 rounded transition-opacity shrink-0"
                      title="Dismiss"
                      aria-label="Dismiss dialogue"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </div>

                  <p
                    className={`text-xs sm:text-[13px] font-medium leading-relaxed ${
                      activePopup.mood === 'angry' ? 'text-[#D1CFDC]' : 'text-[#524E5E]'
                    }`}
                  >
                    {activePopup.message}
                  </p>
                </div>
              )}

              {/* Status badge: Always On Fleet Indicator */}
              <div className="absolute bottom-4 right-2 sm:right-6 pointer-events-none select-none z-10 flex flex-col items-end">
                <div className="bg-white/95 backdrop-blur-xs border border-[#E4E2EB] shadow-craft-xs px-3 py-1.5 rounded-xl flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-[#10B981] animate-pulse" />
                  <span className="text-[11px] font-mono font-semibold text-[#0F0E17] uppercase tracking-wider">
                    Always On • 24/7 Fleet
                  </span>
                </div>
              </div>
            </div>

          </div>

        </div>
      </div>
    </section>
  );
}

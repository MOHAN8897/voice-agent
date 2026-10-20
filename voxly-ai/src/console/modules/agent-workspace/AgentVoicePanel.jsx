import React, { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import {
  Volume2,
  VolumeX,
  Play,
  Square,
  Check,
  CheckCircle2,
  Radio,
  Sliders,
  Sparkles,
  Info,
  RotateCcw,
  Languages,
  Mic,
  Activity,
  Layers,
  ChevronDown,
} from 'lucide-react';
import { voiceAgent } from '../../../services/voiceAgent';
import { api } from '../../../services/api';
import { showToast } from '../../ui/ToastHost';

/**
 * Curated 10 neural voice profiles with realistic pre-recorded conversational WAV samples.
 */
export const VOICE_CATALOG = [
  {
    id: 'marin',
    name: 'Marin',
    gender: 'female',
    tone: 'Warm & conversational',
    category: 'support',
    useCase: 'Customer Care, Hospitality & Appointments',
    sampleText: 'Thank you for calling City Concierge. I can assist with reservations, guest services, and appointment scheduling. How may I help you today?',
    sampleUrl: '/audio/voxly/samples/marin.wav',
    duration: '8.3s',
  },
  {
    id: 'cedar',
    name: 'Cedar',
    gender: 'male',
    tone: 'Calm & steady',
    category: 'operations',
    useCase: 'Field Operations, Home Services & Dispatch',
    sampleText: 'You have reached CoolAir Service Dispatch. I can schedule emergency maintenance, technician visits, or system inspections. What can I do for you?',
    sampleUrl: '/audio/voxly/samples/cedar.wav',
    duration: '8.9s',
  },
  {
    id: 'alloy',
    name: 'Alloy',
    gender: 'neutral',
    tone: 'Balanced & empathetic',
    category: 'support',
    useCase: 'Healthcare Clinics, Patient Triage & Intake',
    sampleText: 'Thank you for calling Sunshine Health Clinic. I can help you book, reschedule, or check doctor availability. What appointment do you need?',
    sampleUrl: '/audio/voxly/samples/alloy.wav',
    duration: '8.0s',
  },
  {
    id: 'ash',
    name: 'Ash',
    gender: 'male',
    tone: 'Grounded & thoughtful',
    category: 'operations',
    useCase: 'Technical Operations, Diagnostics & Advisory',
    sampleText: 'Hello, this is Northbridge Technical Operations. I can help resolve systems access, diagnostic alerts, or service tickets. Please tell me your issue.',
    sampleUrl: '/audio/voxly/samples/ash.wav',
    duration: '9.1s',
  },
  {
    id: 'ballad',
    name: 'Ballad',
    gender: 'male',
    tone: 'Proactive & direct',
    category: 'sales',
    useCase: 'Automotive Sales, Direct Outreach & Inquiries',
    sampleText: 'Hello, this is Metro Automotive Sales. We have exciting offers and test drive slots open this week. Which vehicle would you like to explore?',
    sampleUrl: '/audio/voxly/samples/ballad.wav',
    duration: '8.7s',
  },
  {
    id: 'coral',
    name: 'Coral',
    gender: 'female',
    tone: 'Friendly & trustworthy',
    category: 'support',
    useCase: 'Banking Verification, Fintech & Onboarding',
    sampleText: 'Thank you for calling Meridian Financial Services. I can assist with account verification, card security, and onboarding. How may I assist?',
    sampleUrl: '/audio/voxly/samples/coral.wav',
    duration: '8.5s',
  },
  {
    id: 'echo',
    name: 'Echo',
    gender: 'male',
    tone: 'Bright & confident',
    category: 'sales',
    useCase: 'Sales Inquiries, Real Estate & Outbound',
    sampleText: 'Thanks for calling Harbour Point Real Estate. We have exclusive property viewings and investment tours scheduled this weekend. What area interests you?',
    sampleUrl: '/audio/voxly/samples/echo.wav',
    duration: '9.4s',
  },
  {
    id: 'sage',
    name: 'Sage',
    gender: 'female',
    tone: 'Crisp & professional',
    category: 'operations',
    useCase: 'Enterprise IT, B2B SaaS & Tech Helpdesk',
    sampleText: 'Welcome to Enterprise IT Systems Helpdesk. I can verify your credentials, unlock single sign-on, and resolve workstation requests immediately.',
    sampleUrl: '/audio/voxly/samples/sage.wav',
    duration: '8.7s',
  },
  {
    id: 'shimmer',
    name: 'Shimmer',
    gender: 'female',
    tone: 'Encouraging & pleasant',
    category: 'support',
    useCase: 'Academic Admissions, Travel & Concierge',
    sampleText: 'Welcome to Northbridge Academic Advisory. I can guide you through admissions deadlines, degree requirements, and enrolment. How can I guide you?',
    sampleUrl: '/audio/voxly/samples/shimmer.wav',
    duration: '8.9s',
  },
  {
    id: 'verse',
    name: 'Verse',
    gender: 'male',
    tone: 'Dynamic & adaptable',
    category: 'sales',
    useCase: 'Retail Ordering, Commercial Outreach & Reservations',
    sampleText: 'Good evening! Thank you for calling Bella Vista Dining. I can confirm your table reservations or take your specialty order. How many in your party?',
    sampleUrl: '/audio/voxly/samples/verse.wav',
    duration: '8.8s',
  },
];

/**
 * Regional Indian and International spoken languages.
 */
export const EXTENDED_LANGUAGES = [
  {
    code: 'te-IN',
    name: 'Telugu',
    nativeName: 'తెలుగు',
    flag: '🇮🇳',
    badge: 'Native Neural',
    sampleText: 'నమస్కారం. మీకు ఎలా సహాయం చేయగలను?',
  },
  {
    code: 'en-IN',
    name: 'English (India)',
    nativeName: 'Indian English',
    flag: '🇮🇳',
    badge: 'Localized Accent',
    sampleText: 'Hello. How can I help you today?',
  },
  {
    code: 'hi-IN',
    name: 'Hindi',
    nativeName: 'हिन्दी',
    flag: '🇮🇳',
    badge: 'Regional Voices',
    sampleText: 'नमस्ते। मैं आपकी कैसे मदद कर सकता हूँ?',
  },
  {
    code: 'ta-IN',
    name: 'Tamil',
    nativeName: 'தமிழ்',
    flag: '🇮🇳',
    badge: 'Regional Dravidian',
    sampleText: 'வணக்கம். உங்களுக்கு எப்படி உதவலாம்?',
  },
  {
    code: 'kn-IN',
    name: 'Kannada',
    nativeName: 'ಕನ್ನಡ',
    flag: '🇮🇳',
    badge: 'Multilingual Voice',
    sampleText: 'ನಮಸ್ಕಾರ. ನಾನು ನಿಮಗೆ ಹೇಗೆ ಸಹಾಯ ಮಾಡಬಹುದು?',
  },
  {
    code: 'en-GB',
    name: 'English (UK)',
    nativeName: 'British English',
    flag: '🇬🇧',
    badge: 'RP Accent',
  },
  {
    code: 'en-US',
    name: 'English (US)',
    nativeName: 'American English',
    flag: '🇺🇸',
    badge: 'General American',
  },
];

/**
 * Streamlined, high-density Voice & Language Studio.
 * Eliminates bulky cards in favor of a sleek, compact roster where all voices are visible simultaneously.
 */
export function AgentVoicePanel({
  formData,
  setFormData,
  phoneVoices = [],
  activeVoiceProvider = 'openai',
  defaultVoiceId = 'te-in-csagent-5',
  voiceCatalogError = null,
  stackLabel = 'Enterprise Voice Network',
  onOpenTestCall,
}) {
  const storedVoiceId = String(
    formData?.voice?.realtimeVoice || formData?.voice?.voiceId || 'marin'
  ).toLowerCase();
  const currentVoiceId =
    activeVoiceProvider === 'gemini'
      ? String(
          phoneVoices.find(
            (voice) => voice.provider === 'gemini' && voice.id?.toLowerCase() === storedVoiceId
          )?.id || defaultVoiceId || 'te-in-csagent-5'
        ).toLowerCase()
      : storedVoiceId;
  const currentLanguage =
    formData?.language ||
    (Array.isArray(formData?.languages) && formData.languages[0]) ||
    'te-IN';
  const currentSpeed = formData?.voice?.speed ?? 1.0;
  const currentPitch = formData?.voice?.pitch ?? 0.0;
  const currentStability = formData?.voice?.stability ?? 0.75;

  const [playingVoiceId, setPlayingVoiceId] = useState(null);
  const [playingType, setPlayingType] = useState(null); // 'sample' | 'greeting'
  const [audioError, setAudioError] = useState(null);
  const [isBufferingGreeting, setIsBufferingGreeting] = useState(false);
  const [activeCategory, setActiveCategory] = useState('all');
  const [genderFilter, setGenderFilter] = useState('all');
  const [showAcousticControls, setShowAcousticControls] = useState(false);

  // Merge server phone voices with catalog
  const displayVoices = useMemo(() => {
    if (activeVoiceProvider === 'gemini') {
      const liveVoices = phoneVoices
        .filter((voice) => voice.provider === 'gemini')
        .map((voice) => ({
          ...voice,
          name: voice.label || voice.geminiVoice || voice.id,
          sampleText:
            voice.sampleText ||
            EXTENDED_LANGUAGES.find((language) => language.code === currentLanguage)?.sampleText ||
            'Hello. Thank you for calling. How can I help you today?',
        }));
      const localeVoices = liveVoices.filter((voice) => voice.languageCode === currentLanguage);
      if (localeVoices.length) {
        const selectedMultilingualVoice = liveVoices.find(
          (voice) => voice.id?.toLowerCase() === currentVoiceId && !voice.languageCode
        );
        return selectedMultilingualVoice
          ? [...localeVoices, selectedMultilingualVoice]
          : localeVoices;
      }
      const multilingualVoices = liveVoices.filter((voice) => !voice.languageCode);
      if (multilingualVoices.length) return multilingualVoices;
      if (liveVoices.length) return liveVoices;
    }
    return VOICE_CATALOG.map((catVoice) => {
      const match = phoneVoices.find(
        (pv) =>
          pv.id?.toLowerCase() === catVoice.id.toLowerCase() ||
          pv.name?.toLowerCase() === catVoice.name.toLowerCase()
      );
      if (match) {
        return {
          ...catVoice,
          name: match.name || match.label || catVoice.name,
          label: match.label || match.name || catVoice.name,
          category: match.category || catVoice.category,
          useCase: match.useCase || catVoice.useCase,
          tone: match.tone || catVoice.tone,
        };
      }
      return catVoice;
    });
  }, [phoneVoices, activeVoiceProvider, currentLanguage, currentVoiceId]);

  const voiceCategoryCounts = useMemo(() => {
    const countCategory = (categories) =>
      displayVoices.filter((voice) => categories.includes(voice.category)).length;
    return {
      all: displayVoices.length,
      support: countCategory(['support', 'care']),
      operations: countCategory(['operations', 'formal']),
      sales: countCategory(['sales', 'energetic']),
    };
  }, [displayVoices]);

  // Filtered voice list
  const filteredVoices = useMemo(() => {
    return displayVoices.filter((v) => {
      if (activeCategory !== 'all') {
        const cat = v.category;
        if (activeCategory === 'care' || activeCategory === 'support') {
          if (cat !== 'support' && cat !== 'care') return false;
        } else if (activeCategory === 'formal' || activeCategory === 'operations') {
          if (cat !== 'operations' && cat !== 'formal') return false;
        } else if (activeCategory === 'energetic' || activeCategory === 'sales') {
          if (cat !== 'sales' && cat !== 'energetic') return false;
        } else if (cat !== activeCategory) {
          return false;
        }
      }
      if (genderFilter !== 'all' && v.gender !== genderFilter) return false;
      return true;
    });
  }, [displayVoices, activeCategory, genderFilter]);

  // Active voice metadata
  const activeVoice = useMemo(() => {
    return (
      displayVoices.find((v) => v.id === currentVoiceId) ||
      displayVoices[0] ||
      VOICE_CATALOG[0]
    );
  }, [displayVoices, currentVoiceId]);

  // Active language metadata
  const activeLanguage = useMemo(() => {
    return (
      EXTENDED_LANGUAGES.find((l) => l.code === currentLanguage) ||
      EXTENDED_LANGUAGES[0]
    );
  }, [currentLanguage]);

  // Audio sample playback
  const handlePlayVoiceSample = useCallback(
    async (voice) => {
      setAudioError(null);

      // Toggle off if currently playing
      if (playingVoiceId === voice.id && playingType === 'sample') {
        voiceAgent.stopTTS();
        setPlayingVoiceId(null);
        setPlayingType(null);
        return;
      }

      voiceAgent.stopTTS();
      setPlayingVoiceId(voice.id);
      setPlayingType('sample');

      let previewUrl = null;
      try {
        if (voice.provider === 'gemini') {
          const preview = await api.telephony.previewVoice({
            voiceId: voice.id,
            text: voice.sampleText || `Hello. This is ${voice.name}. How can I help you today?`,
            language: currentLanguage,
            speed: currentSpeed,
          });
          previewUrl = preview?.url || null;
          if (preview?.blob) {
            const played = await voiceAgent.playAudioBuffer(
              preview.blob,
              () => {
                setPlayingVoiceId((curr) => (curr === voice.id ? null : curr));
                setPlayingType((curr) => (curr === 'sample' ? null : curr));
              },
              () => {
                setPlayingVoiceId(voice.id);
                setPlayingType('sample');
              }
            );
            if (played) {
              if (previewUrl) URL.revokeObjectURL(previewUrl);
              return;
            }
          }
          if (preview?.url) {
            voiceAgent.playAudioClip(
              preview.url,
              () => {
                if (previewUrl) URL.revokeObjectURL(previewUrl);
                setPlayingVoiceId((curr) => (curr === voice.id ? null : curr));
                setPlayingType((curr) => (curr === 'sample' ? null : curr));
              },
              () => {
                setPlayingVoiceId(voice.id);
                setPlayingType('sample');
              }
            );
            return;
          }
          throw new Error('No synthesized audio returned');
        }
        const audioUrl = voice.sampleUrl;
        voiceAgent.playAudioClip(
          audioUrl,
          () => {
            // onEnd callback
            setPlayingVoiceId((curr) => (curr === voice.id ? null : curr));
            setPlayingType((curr) => (curr === 'sample' ? null : curr));
          },
          () => {
            // onStart callback
            setPlayingVoiceId(voice.id);
            setPlayingType('sample');
          },
          {
            fallbackText: voice.sampleText || voice.useCase || `Hello, this is ${voice.name}.`,
          }
        );
      } catch (e) {
        if (previewUrl) URL.revokeObjectURL(previewUrl);
        setPlayingVoiceId(null);
        setPlayingType(null);
        setAudioError(
          String(e?.message || '').trim() ||
            'Could not reach the voice service. Check the voice configuration and audio output.'
        );
      }
    },
    [playingVoiceId, playingType, currentLanguage, currentSpeed]
  );

  const handleStopAudio = useCallback(() => {
    voiceAgent.stopTTS();
    setPlayingVoiceId(null);
    setPlayingType(null);
    setIsBufferingGreeting(false);
  }, []);

  // Voice selection
  const handleSelectVoice = useCallback(
    (voice) => {
      setFormData((prev) => ({
        ...prev,
        voice: {
          ...prev.voice,
          provider: 'phone_ai',
          realtimeVoice: voice.id,
          voiceId: voice.id,
          voiceName: voice.name || voice.id,
        },
      }));
      showToast(`Speaking voice set to ${voice.name} (${voice.tone})`, 'info');
    },
    [setFormData]
  );

  // Language selection
  const handleSelectLanguage = useCallback(
    (langCode) => {
      const currentGeminiVoice = phoneVoices.find(
        (voice) => voice.provider === 'gemini' && voice.id?.toLowerCase() === currentVoiceId
      );
      const nativeDefault = phoneVoices.find(
        (voice) =>
          voice.provider === 'gemini' &&
          voice.languageCode === langCode &&
          voice.defaultForLanguage === true
      );
      const multilingualDefault = phoneVoices.find(
        (voice) => voice.provider === 'gemini' && voice.id?.toLowerCase() === 'puck'
      );
      const voiceAlreadyMatches = currentGeminiVoice?.languageCode === langCode;
      const nextGeminiVoice =
        activeVoiceProvider === 'gemini' && !voiceAlreadyMatches
          ? nativeDefault || (currentGeminiVoice?.languageCode ? multilingualDefault : null)
          : null;

      setFormData((prev) => ({
        ...prev,
        language: langCode,
        languages: [langCode],
        voice: {
          ...prev.voice,
          language: langCode,
          ...(nextGeminiVoice
            ? {
                realtimeVoice: nextGeminiVoice.id,
                voiceId: nextGeminiVoice.id,
                voiceName: nextGeminiVoice.label || nextGeminiVoice.id,
              }
            : {}),
        },
      }));
      const lMeta = EXTENDED_LANGUAGES.find((l) => l.code === langCode);
      showToast(`Language updated to ${lMeta?.name || langCode}`, 'info');
    },
    [activeVoiceProvider, currentVoiceId, phoneVoices, setFormData]
  );

  // Test greeting in selected voice
  const handlePlayGreetingPreview = useCallback(async () => {
    if (playingType === 'greeting') {
      handleStopAudio();
      return;
    }

    handleStopAudio();
    setAudioError(null);
    setIsBufferingGreeting(true);

    const greetingText =
      formData?.greeting?.trim() ||
      "Hello! Thank you for calling. How can I assist you today?";

    let previewUrl = null;
    try {
      const resp = await api.telephony.previewVoice({
        voiceId: currentVoiceId,
        text: greetingText,
        language: currentLanguage,
        speed: currentSpeed,
      });
      previewUrl = resp?.url || null;

      if (resp?.url || resp?.blob) {
        setPlayingType('greeting');
        setPlayingVoiceId(currentVoiceId);
        setIsBufferingGreeting(false);

        const played = resp.blob
          ? await voiceAgent.playAudioBuffer(
              resp.blob,
              () => {
                if (previewUrl) URL.revokeObjectURL(previewUrl);
                previewUrl = null;
                handleStopAudio();
              },
              () => {
                setPlayingType('greeting');
                setPlayingVoiceId(currentVoiceId);
              }
            )
          : false;
        if (played) {
          if (previewUrl) URL.revokeObjectURL(previewUrl);
          return;
        }
        if (previewUrl) {
          voiceAgent.playAudioClip(
            previewUrl,
            () => {
              if (previewUrl) URL.revokeObjectURL(previewUrl);
              previewUrl = null;
              handleStopAudio();
            },
            () => {
              setPlayingType('greeting');
              setPlayingVoiceId(currentVoiceId);
            }
          );
        } else {
          throw new Error('Preview audio could not be decoded.');
        }
      } else {
        throw new Error('No audio returned');
      }
    } catch (error) {
      if (typeof previewUrl === 'string') URL.revokeObjectURL(previewUrl);
      setIsBufferingGreeting(false);
      setAudioError(error?.message || 'Live greeting synthesis preview unavailable.');
    }
  }, [
    playingType,
    handleStopAudio,
    formData?.greeting,
    currentVoiceId,
    currentLanguage,
    currentSpeed,
  ]);

  // Clean up audio on unmount
  useEffect(() => {
    return () => {
      voiceAgent.stopTTS();
    };
  }, []);

  return (
    <div className="space-y-4" data-testid="agent-voice-panel">
      {/* 1. Header Bar: Compact Active Summary */}
      <div className="flex flex-wrap items-center justify-between gap-3 p-3.5 rounded-xl bg-white border border-[#E4E2EB] shadow-xs">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-[#6344E7]/10 flex items-center justify-center text-[#6344E7]">
            <Volume2 className="w-4 h-4" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold text-[#0F0E17]">
                Voice &amp; Language Configuration
              </span>
              <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-[#FAF9FD] text-[#6344E7] border border-[#6344E7]/20">
                {stackLabel}
              </span>
            </div>
            <p className="text-[11px] text-[#524E5E]">
              Selected: <strong className="text-[#0F0E17]">{activeVoice.name}</strong> ({activeVoice.tone}) · <strong className="text-[#0F0E17]">{activeLanguage.name}</strong> ({activeLanguage.code})
            </p>
          </div>
        </div>

        {/* Action Controls & Floating Playing Status */}
        <div className="flex items-center gap-2">
          {playingVoiceId && (
            <div
              className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[#6344E7]/10 text-[#6344E7] text-xs font-semibold animate-pulse border border-[#6344E7]/25"
              data-testid="voice-playing-indicator"
            >
              <div className="flex items-center gap-0.5 h-3">
                <span className="w-0.5 h-3 bg-[#6344E7] rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="w-0.5 h-2 bg-[#6344E7] rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="w-0.5 h-3.5 bg-[#6344E7] rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
              <span>
                Playing sample: {displayVoices.find((v) => v.id === playingVoiceId)?.name || playingVoiceId}
              </span>
              <button
                type="button"
                onClick={handleStopAudio}
                data-testid="stop-voice-audio-btn"
                className="ml-1 p-0.5 rounded hover:bg-[#6344E7]/20 text-[#6344E7]"
                title="Stop audio"
              >
                <Square className="w-3.5 h-3.5 fill-current" />
              </button>
            </div>
          )}

          {onOpenTestCall && (
            <button
              type="button"
              onClick={onOpenTestCall}
              data-testid="voice-open-test-call-btn"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-[#6344E7] hover:bg-[#5233D6] text-white shadow-xs transition-all cursor-pointer"
            >
              <Radio className="w-3.5 h-3.5 animate-pulse" />
              <span>Test Live Agent</span>
            </button>
          )}
        </div>
      </div>

      {audioError && (
        <div
          className="flex items-center gap-2 p-2.5 rounded-lg bg-amber-50 text-amber-800 text-xs border border-amber-200"
          data-testid="voice-preview-error"
          role="alert"
        >
          <Info className="w-4 h-4 shrink-0 text-amber-600" />
          <span>{audioError}</span>
        </div>
      )}

      {/* 2. Compact Language Palette */}
      <div
        className="p-3.5 rounded-xl bg-white border border-[#E4E2EB] shadow-xs space-y-2.5"
        data-testid="language-selection-card"
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Languages className="w-4 h-4 text-[#6344E7]" />
            <span className="text-xs font-bold text-[#0F0E17]">
              Primary Spoken Language &amp; Accent
            </span>
          </div>
          <span className="text-[11px] font-medium text-[#6344E7]">
            Active: {activeLanguage.name} ({activeLanguage.code})
          </span>
        </div>

        {/* Compact Horizontal Pill Grid */}
        <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-7 gap-2">
          {EXTENDED_LANGUAGES.map((lang) => {
            const isSelected = currentLanguage === lang.code;
            return (
              <button
                key={lang.code}
                type="button"
                data-testid={`language-card-${lang.code}`}
                aria-pressed={isSelected}
                onClick={() => handleSelectLanguage(lang.code)}
                className={`flex flex-col items-center justify-center p-2 rounded-lg text-center transition-all ${
                  isSelected
                    ? 'bg-[#6344E7]/10 border-2 border-[#6344E7] text-[#0F0E17] shadow-xs'
                    : 'bg-[#FAF9FD] border border-[#E4E2EB] text-[#524E5E] hover:border-[#6344E7]/40 hover:bg-white'
                }`}
              >
                <div className="flex items-center gap-1">
                  <span className="text-sm">{lang.flag}</span>
                  <span className="text-[11px] font-bold text-[#0F0E17]">
                    {lang.nativeName}
                  </span>
                </div>
                <span className="text-[10px] text-[#524E5E] truncate max-w-full">
                  {lang.name}
                </span>
                <span className="text-[9px] text-[#8C879A] mt-0.5 uppercase tracking-wider">
                  {lang.code}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* 3. Speaking Voices Showcase: Dense Roster List Format */}
      <div
        className="p-3.5 rounded-xl bg-white border border-[#E4E2EB] shadow-xs space-y-3"
        data-testid="speaking-voice-showcase"
      >
        {voiceCatalogError && (
          <p className="text-[11px] text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2" role="alert">
            {voiceCatalogError}
          </p>
        )}
        {activeVoiceProvider === 'gemini' && ['hi-IN', 'te-IN'].includes(currentLanguage) && (
          <p
            className="text-[11px] text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2"
            data-testid="voice-localization-note"
          >
            {currentLanguage === 'te-IN' ? 'Telugu (India) choices include regional support, concierge, and technical voices.' : 'Hindi-specific choices are regional voices.'} Each voice is labeled with its accent; preview it before selecting.
          </p>
        )}
        {activeVoiceProvider === 'gemini' &&
          currentLanguage !== 'hi-IN' &&
          !phoneVoices.some(
            (voice) => voice.provider === 'gemini' && voice.languageCode === currentLanguage
          ) && (
            <p
              className="text-[11px] text-[#716C7F] bg-[#FAF9FD] border border-[#E4E2EB] rounded-lg px-3 py-2"
              data-testid="voice-localization-note"
            >
              This language has no dedicated regional voice in the current Gemini Live catalog. The multilingual voice follows the selected language instruction.
            </p>
          )}
        <div className="flex flex-wrap items-center justify-between gap-2 pb-2 border-b border-[#F0EEF6]">
          <div className="flex items-center gap-2">
            <Mic className="w-4 h-4 text-[#6344E7]" />
            <span className="text-xs font-bold text-[#0F0E17]">
              Available Speaking Voices ({filteredVoices.length})
            </span>
            <span className="text-[11px] text-[#8C879A]">
              Click Play to listen · Click row to choose
            </span>
          </div>

          {/* Compact Category & Gender Filters */}
          <div className="flex items-center gap-1.5 text-xs">
            <div className="flex rounded-lg bg-[#FAF9FD] border border-[#E4E2EB] p-0.5">
              {[
                { id: 'all', label: `All Roles (${voiceCategoryCounts.all})`, testId: 'voice-filter-all' },
                { id: 'support', aliases: ['care'], label: `Customer Care (${voiceCategoryCounts.support})`, testId: 'voice-filter-care' },
                { id: 'operations', aliases: ['formal'], label: `Operations & Technical (${voiceCategoryCounts.operations})`, testId: 'voice-filter-formal' },
                { id: 'sales', aliases: ['energetic'], label: `Sales & Outreach (${voiceCategoryCounts.sales})`, testId: 'voice-filter-energetic' },
              ].map((c) => {
                const isActive = activeCategory === c.id || (c.aliases && c.aliases.includes(activeCategory));
                return (
                  <button
                    key={c.id}
                    type="button"
                    data-testid={c.testId}
                    onClick={() => setActiveCategory(c.id)}
                    className={`px-2 py-0.5 text-[11px] font-medium rounded-md transition-all ${
                      isActive
                        ? 'bg-[#0F0E17] text-white shadow-2xs'
                        : 'text-[#524E5E] hover:text-[#0F0E17]'
                    }`}
                  >
                    {c.label}
                  </button>
                );
              })}
            </div>

            <div className="flex rounded-lg bg-[#FAF9FD] border border-[#E4E2EB] p-0.5">
              {[
                { id: 'all', label: 'All' },
                { id: 'female', label: 'Female' },
                { id: 'male', label: 'Male' },
                { id: 'neutral', label: 'Neutral' },
              ].map((g) => (
                <button
                  key={g.id}
                  type="button"
                  onClick={() => setGenderFilter(g.id)}
                  className={`px-2 py-0.5 text-[11px] font-medium rounded-md transition-all ${
                    genderFilter === g.id
                      ? 'bg-[#6344E7] text-white shadow-2xs'
                      : 'text-[#524E5E] hover:text-[#0F0E17]'
                  }`}
                >
                  {g.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Dense Voice List / Table */}
        <div className="divide-y divide-[#F0EEF6] border border-[#E4E2EB] rounded-lg overflow-hidden">
          {filteredVoices.map((voice) => {
            const isSelected = currentVoiceId === voice.id;
            const isPlayingThis = playingVoiceId === voice.id;

            return (
              <div
                key={voice.id}
                data-testid={`voice-card-${voice.id}`}
                onClick={() => handleSelectVoice(voice)}
                className={`group flex items-center justify-between gap-3 px-3 py-2.5 transition-colors cursor-pointer select-none ${
                  isSelected
                    ? 'bg-[#6344E7]/8 border-l-4 border-l-[#6344E7]'
                    : 'bg-white hover:bg-[#FAF9FD]'
                }`}
              >
                {/* Left: Play/Stop Button + Avatar + Name + Tone */}
                <div className="flex items-center gap-3 min-w-0">
                  {/* Play Sample Button */}
                  <button
                    type="button"
                    data-testid={`voice-play-btn-${voice.id}`}
                    aria-label={`Play sample for ${voice.name}`}
                    onClick={(e) => {
                      e.stopPropagation();
                      handlePlayVoiceSample(voice);
                    }}
                    className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 transition-transform active:scale-95 ${
                      isPlayingThis
                        ? 'bg-rose-600 text-white shadow-xs'
                        : 'bg-[#6344E7]/10 text-[#6344E7] hover:bg-[#6344E7] hover:text-white'
                    }`}
                  >
                    {isPlayingThis ? (
                      <Square className="w-3.5 h-3.5 fill-current" />
                    ) : (
                      <Play className="w-3.5 h-3.5 fill-current ml-0.5" />
                    )}
                  </button>

                  {/* Equalizer animation when playing */}
                  {isPlayingThis && (
                    <div className="flex items-center gap-0.5 h-3.5 shrink-0">
                      <span className="w-0.5 h-3 bg-[#6344E7] rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                      <span className="w-0.5 h-2 bg-[#6344E7] rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                      <span className="w-0.5 h-3.5 bg-[#6344E7] rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                    </div>
                  )}

                  {/* Name & Tone */}
                  <div className="min-w-0">
                    <div className="flex items-center gap-1.5">
                      <span className="text-xs font-bold text-[#0F0E17]">
                        {voice.name}
                      </span>
                      <span className="px-1.5 py-0.2 rounded text-[10px] font-medium bg-[#F0EEF6] text-[#524E5E] capitalize">
                        {voice.gender}
                      </span>
                      <span className="px-1.5 py-0.2 rounded text-[10px] font-semibold bg-[#6344E7]/10 text-[#6344E7] border border-[#6344E7]/20">
                        {voice.category === 'support' || voice.category === 'care'
                          ? 'Customer Care'
                          : voice.category === 'sales' || voice.category === 'energetic'
                          ? 'Sales & Outreach'
                          : 'Operations & Tech'}
                      </span>
                      <span className="hidden sm:inline-block text-[11px] font-medium text-[#716C7F]">
                        · {voice.tone}
                      </span>
                    </div>
                    <p className="text-[11px] text-[#716C7F] truncate max-w-xs md:max-w-md">
                      {voice.accent
                        ? `${voice.accent}${voice.languageCode ? ` · ${voice.languageCode}` : ''}`
                        : voice.useCase}
                    </p>
                  </div>
                </div>

                {/* Right: Duration + Selection Action */}
                <div className="flex items-center gap-3 shrink-0">
                  <span className="hidden sm:inline-block text-[11px] text-[#8C879A] font-mono">
                    {voice.duration}
                  </span>

                  <button
                    type="button"
                    data-testid={`voice-select-btn-${voice.id}`}
                    onClick={(e) => {
                      e.stopPropagation();
                      handleSelectVoice(voice);
                    }}
                    className={`flex items-center gap-1 px-3 py-1 text-xs font-semibold rounded-lg transition-all ${
                      isSelected
                        ? 'bg-[#6344E7] text-white shadow-xs'
                        : 'bg-[#FAF9FD] text-[#524E5E] hover:bg-[#6344E7]/10 hover:text-[#6344E7] border border-[#E4E2EB]'
                    }`}
                  >
                    {isSelected ? (
                      <>
                        <Check className="w-3.5 h-3.5 stroke-[3]" />
                        <span>Selected</span>
                      </>
                    ) : (
                      <span>Choose</span>
                    )}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* 4. Acoustic Calibration & Greeting Toolbar (Collapsible / Compact) */}
      <div
        className="p-3.5 rounded-xl bg-white border border-[#E4E2EB] shadow-xs space-y-3"
        data-testid="acoustic-calibration-card"
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Sliders className="w-4 h-4 text-[#6344E7]" />
            <span className="text-xs font-bold text-[#0F0E17]">
              Acoustic Calibration &amp; Speech Dynamics
            </span>
          </div>

          <button
            type="button"
            onClick={() => setShowAcousticControls((v) => !v)}
            className="flex items-center gap-1 text-[11px] font-semibold text-[#6344E7] hover:underline"
          >
            <span>{showAcousticControls ? 'Hide Sliders' : 'Fine-Tune Speed & Pitch'}</span>
            <ChevronDown className={`w-3.5 h-3.5 transition-transform ${showAcousticControls ? 'rotate-180' : ''}`} />
          </button>
        </div>

        {/* Speed Slider always available or expanded */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-1">
          {/* Speaking Pace */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between text-xs">
              <span className="font-semibold text-[#0F0E17]">Speaking Pace</span>
              <span className="font-mono font-bold text-[#6344E7] text-[11px]">
                {currentSpeed.toFixed(2)}x
              </span>
            </div>
            <input
              type="range"
              min="0.8"
              max="1.3"
              step="0.05"
              value={currentSpeed}
              data-testid="speed-slider"
              onChange={(e) => {
                const val = parseFloat(e.target.value);
                setFormData((prev) => ({
                  ...prev,
                  voice: {
                    ...prev.voice,
                    speed: val,
                  },
                }));
              }}
              className="w-full h-1.5 bg-[#E4E2EB] rounded-lg appearance-none cursor-pointer accent-[#6344E7]"
            />
            <div className="flex justify-between text-[10px] text-[#8C879A]">
              <span>0.8x (Deliberate)</span>
              <span>1.0x (Standard)</span>
              <span>1.3x (Fast)</span>
            </div>
          </div>

          {/* Quick Presets */}
          <div className="space-y-1.5">
            <span className="text-xs font-semibold text-[#0F0E17] block">
              Pacing Presets
            </span>
            <div className="flex items-center gap-1.5">
              {[
                { label: 'Standard (1.0x)', speed: 1.0, pitch: 0.0 },
                { label: 'Patient Support (0.9x)', speed: 0.9, pitch: -0.05 },
                { label: 'High-Energy Sales (1.1x)', speed: 1.1, pitch: 0.05 },
              ].map((p) => (
                <button
                  key={p.label}
                  type="button"
                  onClick={() => {
                    setFormData((prev) => ({
                      ...prev,
                      voice: {
                        ...prev.voice,
                        speed: p.speed,
                        pitch: p.pitch,
                      },
                    }));
                  }}
                  className={`px-2.5 py-1 rounded text-[11px] font-medium border transition-all ${
                    Math.abs(currentSpeed - p.speed) < 0.01
                      ? 'bg-[#6344E7] text-white border-[#6344E7]'
                      : 'bg-[#FAF9FD] text-[#524E5E] border-[#E4E2EB] hover:bg-white'
                  }`}
                >
                  {p.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Detailed sliders if expanded */}
        {showAcousticControls && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2 border-t border-[#F0EEF6]">
            {/* Pitch Offset */}
            <div className="space-y-1">
              <div className="flex items-center justify-between text-xs">
                <span className="font-semibold text-[#0F0E17]">Pitch Offset</span>
                <span className="font-mono text-[#6344E7] text-[11px]">
                  {currentPitch > 0 ? `+${currentPitch.toFixed(2)}` : currentPitch.toFixed(2)}
                </span>
              </div>
              <input
                type="range"
                min="-0.15"
                max="0.15"
                step="0.05"
                value={currentPitch}
                onChange={(e) => {
                  const val = parseFloat(e.target.value);
                  setFormData((prev) => ({
                    ...prev,
                    voice: {
                      ...prev.voice,
                      pitch: val,
                    },
                  }));
                }}
                className="w-full h-1.5 bg-[#E4E2EB] rounded-lg appearance-none cursor-pointer accent-[#6344E7]"
              />
            </div>

            {/* Stability */}
            <div className="space-y-1">
              <div className="flex items-center justify-between text-xs">
                <span className="font-semibold text-[#0F0E17]">Tone Stability</span>
                <span className="font-mono text-[#6344E7] text-[11px]">
                  {currentStability.toFixed(2)}
                </span>
              </div>
              <input
                type="range"
                min="0.3"
                max="1.0"
                step="0.05"
                value={currentStability}
                onChange={(e) => {
                  const val = parseFloat(e.target.value);
                  setFormData((prev) => ({
                    ...prev,
                    voice: {
                      ...prev.voice,
                      stability: val,
                    },
                  }));
                }}
                className="w-full h-1.5 bg-[#E4E2EB] rounded-lg appearance-none cursor-pointer accent-[#6344E7]"
              />
            </div>
          </div>
        )}
      </div>

      {/* 5. Bespoke Greeting Quick Test */}
      <div
        className="flex flex-wrap items-center justify-between gap-3 p-3 rounded-xl bg-white border border-[#E4E2EB] shadow-xs"
        data-testid="greeting-preview-card"
      >
        <div className="flex items-center gap-2 min-w-0">
          <Activity className="w-4 h-4 text-[#6344E7] shrink-0" />
          <div className="min-w-0">
            <span className="text-xs font-bold text-[#0F0E17] block">
              Test Agent's Opening Greeting
            </span>
            <p className="text-[11px] text-[#524E5E] truncate max-w-sm sm:max-w-md">
              "{formData?.greeting || 'Hello! Thank you for calling...'}"
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handlePlayGreetingPreview}
            disabled={isBufferingGreeting}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              playingType === 'greeting'
                ? 'bg-rose-600 text-white'
                : 'bg-[#0F0E17] hover:bg-[#232130] text-white shadow-2xs'
            }`}
          >
            {isBufferingGreeting ? (
              <span>Synthesizing...</span>
            ) : playingType === 'greeting' ? (
              <>
                <Square className="w-3.5 h-3.5 fill-current" />
                <span>Stop Greeting</span>
              </>
            ) : (
              <>
                <Volume2 className="w-3.5 h-3.5" />
                <span>Hear Greeting with {activeVoice.name}</span>
              </>
            )}
          </button>

          {onOpenTestCall && (
            <button
              type="button"
              onClick={onOpenTestCall}
              data-testid="voice-greeting-test-call-btn"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-[#6344E7]/10 hover:bg-[#6344E7]/20 text-[#6344E7] border border-[#6344E7]/30 transition-all cursor-pointer"
            >
              <Radio className="w-3.5 h-3.5" />
              <span>Start Browser Call</span>
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

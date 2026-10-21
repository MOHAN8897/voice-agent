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
    id: 'zephyr',
    name: 'Zephyr',
    gender: 'female',
    tone: 'Bright & clear',
    category: 'sales',
    useCase: 'Advertising, Direct Outreach & Sales Inquiries',
    sampleText: 'Hello, this is Zephyr. I can assist you with bookings, orders, and inquiries. How can I help you today?',
    sampleUrl: '/audio/voxly/samples/zephyr.wav',
    duration: '8.5s',
  },
  {
    id: 'aoede',
    name: 'Aoede',
    gender: 'female',
    tone: 'Breezy & engaging',
    category: 'sales',
    useCase: 'Video Voiceover, Commercial Outreach & Hosting',
    sampleText: 'Welcome! I am Aoede, your virtual assistant. How can I assist you today?',
    sampleUrl: '/audio/voxly/samples/aoede.wav',
    duration: '8.3s',
  },
  {
    id: 'kore',
    name: 'Kore',
    gender: 'female',
    tone: 'Firm & authoritative',
    category: 'operations',
    useCase: 'Healthcare Clinics, Patient Triage & Intake',
    sampleText: 'Thank you for calling. I can help you schedule appointments, verify records, and answer questions. What can I do for you today?',
    sampleUrl: '/audio/voxly/samples/kore.wav',
    duration: '8.4s',
  },
  {
    id: 'leda',
    name: 'Leda',
    gender: 'female',
    tone: 'Youthful & pleasant',
    category: 'support',
    useCase: 'Customer Care, Hospitality & Concierge',
    sampleText: 'Thank you for calling. I am here to assist with your bookings, questions, and customer care. How may I help you?',
    sampleUrl: '/audio/voxly/samples/leda.wav',
    duration: '8.2s',
  },
  {
    id: 'puck',
    name: 'Puck',
    gender: 'male',
    tone: 'Upbeat & proactive',
    category: 'sales',
    useCase: 'Automotive Sales, Direct Outreach & Inquiries',
    sampleText: 'Hello! I am Puck. I can help explore our latest inventory, book appointments, or answer questions. What can I get started for you?',
    sampleUrl: '/audio/voxly/samples/puck.wav',
    duration: '8.6s',
  },
  {
    id: 'charon',
    name: 'Charon',
    gender: 'male',
    tone: 'Informative & calm',
    category: 'operations',
    useCase: 'Field Operations, Home Services & Dispatch',
    sampleText: 'You have reached Dispatch Services. I can schedule emergency maintenance, technician visits, or system inspections. What can I do for you?',
    sampleUrl: '/audio/voxly/samples/charon.wav',
    duration: '8.9s',
  },
  {
    id: 'fenrir',
    name: 'Fenrir',
    gender: 'male',
    tone: 'Confident & excitable',
    category: 'sales',
    useCase: 'Sales Inquiries, Real Estate & Outbound',
    sampleText: 'Thanks for calling! We have exclusive viewings and consultations available this week. What area interests you?',
    sampleUrl: '/audio/voxly/samples/fenrir.wav',
    duration: '8.8s',
  },
  {
    id: 'orus',
    name: 'Orus',
    gender: 'male',
    tone: 'Grounded & thoughtful',
    category: 'operations',
    useCase: 'Technical Operations, Diagnostics & Advisory',
    sampleText: 'Hello, this is Technical Operations. I can help resolve systems access, diagnostic alerts, or service tickets. Please describe your issue.',
    sampleUrl: '/audio/voxly/samples/orus.wav',
    duration: '9.0s',
  },
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
    gender: 'female',
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

const STACK_TIER_LABELS = {
  low: 'Economical Tier',
  medium: 'Standard Regional Tier',
  premium: 'Flagship Live Tier',
};
const BLOCKED_TENANT_TERMS = /\b(vobiz|telnyx|nango|exotel|plivo|composio|sarvam|gemini|openai|elevenlabs|deepgram|playht|murf|azure)\b/i;

function publicChoice(value) {
  return typeof value === 'string' && value.trim() && !BLOCKED_TENANT_TERMS.test(value);
}

function hasApprovedRetailRate(rate) {
  return Boolean(
    rate &&
      Number.isFinite(Number(rate.amount)) &&
      Number(rate.amount) >= 0 &&
      typeof rate.currency === 'string' &&
      /^[A-Z]{3}$/.test(rate.currency)
  );
}

function formatRetailRate(rate) {
  if (!hasApprovedRetailRate(rate)) return null;
  try {
    return new Intl.NumberFormat(undefined, {
      style: 'currency',
      currency: rate.currency,
      maximumFractionDigits: 2,
    }).format(Number(rate.amount));
  } catch {
    return `${rate.currency} ${Number(rate.amount).toFixed(2)}`;
  }
}

function publicEngines(profile, language) {
  if (!Array.isArray(profile?.engines)) return [];
  return profile.engines
    .filter((engine) => publicChoice(engine?.id) && publicChoice(engine?.label))
    .map((engine) => ({
      ...engine,
      models: (Array.isArray(engine.models) ? engine.models : [])
        .filter((model) => publicChoice(model?.id) && publicChoice(model?.label))
        .map((model) => ({
          ...model,
          voices: (Array.isArray(model.voices) ? model.voices : []).filter(
            (voice) =>
              publicChoice(voice?.id) &&
              publicChoice(voice?.label) &&
              Array.isArray(voice.languages) &&
              voice.languages.includes(language)
          ),
        }))
        .filter((model) => model.voices.length > 0),
    }))
    .filter((engine) => engine.models.length > 0);
}

function isSelectableProfile(profile, language) {
  if (
    !profile ||
    profile.ready !== true ||
    !['low', 'medium', 'premium'].includes(profile.tier) ||
    !Number.isSafeInteger(profile.profileRevision) ||
    profile.profileRevision < 0 ||
    !hasApprovedRetailRate(profile.retailRate)
  ) {
    return false;
  }
  return profile.tier === 'premium' || publicEngines(profile, language).length > 0;
}

function selectionFromAgent(agent) {
  const settings = agent?.voiceSettings;
  if (settings?.stackSelectionVersion !== 1 || !STACK_TIER_LABELS[agent?.defaultTier]) {
    return { tier: '', engineId: '', modelId: '', voiceId: '' };
  }
  return {
    tier: agent.defaultTier,
    engineId: settings.engineId || '',
    modelId: settings.modelId || '',
    voiceId: settings.voiceId || '',
  };
}

function selectionKey(selection) {
  return [selection.tier, selection.engineId, selection.modelId, selection.voiceId].join('|');
}

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
  agent = null,
  voiceStackProfiles = [],
  voiceStackCatalogLoading = false,
  voiceStackCatalogError = null,
  voiceCatalogLoading = false,
  onRetryVoiceStackCatalog,
  onRetryVoiceCatalog,
  onSaveVoiceStackSelection,
  onReloadVoiceStackSettings,
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
  const [draftSelection, setDraftSelection] = useState(() => selectionFromAgent(agent));
  const [isSavingStackSelection, setIsSavingStackSelection] = useState(false);
  const [stackSelectionError, setStackSelectionError] = useState(null);
  const [stackSelectionNotice, setStackSelectionNotice] = useState(null);
  const [stackSelectionConflict, setStackSelectionConflict] = useState(false);
  const [previewRetry, setPreviewRetry] = useState(0);
  const [previewError, setPreviewError] = useState(false);
  const agentIdRef = useRef(agent?.id);
  const savedSelection = useMemo(() => selectionFromAgent(agent), [
    agent?.id,
    agent?.defaultTier,
    agent?.voiceSettings?.stackSelectionVersion,
    agent?.voiceSettings?.engineId,
    agent?.voiceSettings?.modelId,
    agent?.voiceSettings?.voiceId,
  ]);
  const savedSelectionRevision = Number.isSafeInteger(agent?.voiceRevision) ? agent.voiceRevision : 0;
  const savedSelectionStateKey = `${selectionKey(savedSelection)}|${savedSelectionRevision}`;
  const isStackOptedIn = agent?.voiceSettings?.stackSelectionVersion === 1;
  const selectableStackProfiles = useMemo(
    () =>
      voiceStackProfiles
        .filter((profile) => isSelectableProfile(profile, currentLanguage))
        .filter((profile) => profile.tier === 'low' || profile.tier === 'medium'),
    [voiceStackProfiles, currentLanguage]
  );
  const currentStackProfile = selectableStackProfiles.find(
    (profile) => profile.tier === draftSelection?.tier
  );
  const currentStackEngines = useMemo(
    () => publicEngines(currentStackProfile, currentLanguage),
    [currentStackProfile, currentLanguage]
  );
  const currentStackEngine = currentStackEngines.find(
    (engine) => engine.id === draftSelection?.engineId
  );
  const currentStackModel = currentStackEngine?.models.find(
    (model) => model.id === draftSelection?.modelId
  );
  const currentStackVoice = currentStackModel?.voices.find(
    (voice) => voice.id === draftSelection?.voiceId
  );
  const savedProfile = selectableStackProfiles.find((profile) => profile.tier === savedSelection.tier);
  const savedEngine = publicEngines(savedProfile, currentLanguage)
    .find((engine) => engine.id === savedSelection.engineId);
  const savedModel = savedEngine?.models.find((model) => model.id === savedSelection.modelId);
  const savedVoice = savedModel?.voices.find((voice) => voice.id === savedSelection.voiceId);
  const hasUnsavedStackSelection = selectionKey(savedSelection) !== selectionKey(draftSelection || {});
  const persistedLanguage =
    (Array.isArray(agent?.languages) ? agent.languages[0] : null) ||
    agent?.language ||
    currentLanguage;
  const stackLanguageNeedsSave = currentLanguage !== persistedLanguage;
  const canSaveStackSelection = Boolean(
    onSaveVoiceStackSelection &&
      hasUnsavedStackSelection &&
      currentStackProfile &&
      formatRetailRate(currentStackProfile.retailRate) &&
      currentStackVoice &&
      !stackLanguageNeedsSave &&
      !voiceStackCatalogLoading
  );
  const showExistingLiveVoiceControls =
    draftSelection?.tier === 'premium' ||
    (!isStackOptedIn && !draftSelection?.tier);

  useEffect(() => {
    setDraftSelection(savedSelection);
    if (agentIdRef.current !== agent?.id) {
      setStackSelectionError(null);
      setStackSelectionNotice(null);
      setStackSelectionConflict(false);
      setPreviewError(false);
      agentIdRef.current = agent?.id;
    }
  }, [agent?.id, savedSelectionStateKey]);

  const handleStackTierChange = (tier) => {
    setStackSelectionError(null);
    setStackSelectionNotice(null);
    setDraftSelection(
      tier === savedSelection.tier
        ? savedSelection
        : { tier, engineId: '', modelId: '', voiceId: '' }
    );
  };

  const handleStackEngineChange = (engineId) => {
    setStackSelectionError(null);
    setStackSelectionNotice(null);
    setDraftSelection((current) => ({ ...current, engineId, modelId: '', voiceId: '' }));
  };

  const handleStackModelChange = (modelId) => {
    setStackSelectionError(null);
    setStackSelectionNotice(null);
    setDraftSelection((current) => ({ ...current, modelId, voiceId: '' }));
  };

  const handleStackLanguageChange = (language) => {
    if (language === currentLanguage) return;
    setFormData((current) => ({
      ...current,
      language,
      languages: [language],
      voice: { ...current.voice, language },
    }));
    setDraftSelection((current) => ({ ...current, engineId: '', modelId: '', voiceId: '' }));
    setStackSelectionError(null);
    setStackSelectionNotice(null);
  };

  const handleSaveStackSelection = async () => {
    if (!canSaveStackSelection || isSavingStackSelection) return;
    setIsSavingStackSelection(true);
    setStackSelectionError(null);
    setStackSelectionNotice(null);
    try {
      const result = await onSaveVoiceStackSelection({
        tier: draftSelection.tier,
        ...(draftSelection.tier === 'premium'
          ? {}
          : {
              profileRevision: currentStackProfile?.profileRevision,
              engineId: draftSelection.engineId,
              modelId: draftSelection.modelId,
              voiceId: draftSelection.voiceId,
            }),
      });
      if (result?.conflict) {
        if (result.agent) setDraftSelection(selectionFromAgent(result.agent));
        setStackSelectionConflict(true);
        setStackSelectionError(
          result.agent
            ? 'Another editor saved newer voice settings. The current saved settings have been loaded.'
            : 'Another editor saved newer voice settings. Reload the saved settings before continuing.'
        );
        return;
      }
      if (result?.languageNeedsSave) {
        setStackSelectionError('Save the language change before applying this voice setup.');
        return;
      }
      if (result?.savedButUnconfirmed) {
        setStackSelectionConflict(true);
        setStackSelectionError('The save could not be confirmed. Reload the saved settings before trying again.');
        return;
      }
      if (result?.error || !result?.agent) {
        setStackSelectionError('Voice setup could not be saved. Your saved choice is unchanged. Try again.');
        return;
      }
      setDraftSelection(selectionFromAgent(result.agent));
      setStackSelectionNotice('Voice setup saved. New calls will use this setting.');
    } catch {
      setStackSelectionError('Voice setup could not be saved. Your saved choice is unchanged. Try again.');
    } finally {
      setIsSavingStackSelection(false);
    }
  };

  const handleReloadStackSettings = async () => {
    if (!onReloadVoiceStackSettings) return;
    setIsSavingStackSelection(true);
    const latest = await onReloadVoiceStackSettings();
    setIsSavingStackSelection(false);
    if (!latest) {
      setStackSelectionError('Saved settings could not be reloaded. Try again.');
      return;
    }
    setDraftSelection(selectionFromAgent(latest));
    setStackSelectionError(null);
    setStackSelectionConflict(false);
    setStackSelectionNotice('Saved voice settings reloaded.');
  };
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
    const langPrefix = String(currentLanguage || 'te-IN').split('-')[0].toLowerCase();

    const localizeVoice = (v) => {
      const vid = String(v.id || '').toLowerCase();
      const localizedSampleUrl = `/audio/voxly/samples/${vid}_${langPrefix}.wav`;
      const baseSampleUrl = v.sampleUrl || `/audio/voxly/samples/${vid}.wav`;
      const localizedSampleText =
        v.sampleText ||
        EXTENDED_LANGUAGES.find((language) => language.code === currentLanguage)?.sampleText ||
        'Hello. Thank you for calling. How can I help you today?';
      const cleanGender = v.gender === 'neutral' ? 'female' : (v.gender || 'female');
      return {
        ...v,
        gender: cleanGender,
        sampleUrl: localizedSampleUrl,
        fallbackUrl: baseSampleUrl,
        sampleText: localizedSampleText,
      };
    };

    if (activeVoiceProvider === 'gemini') {
      const liveVoices = phoneVoices
        .filter((voice) => voice.provider === 'gemini')
        .map((voice) => ({
          ...voice,
          name: voice.label || voice.geminiVoice || voice.id,
          gender: voice.gender === 'neutral' ? 'female' : (voice.gender || 'female'),
          sampleUrl: voice.sampleUrl || `/audio/voxly/samples/${voice.id?.toLowerCase()}.wav`,
          sampleText:
            voice.sampleText ||
            EXTENDED_LANGUAGES.find((language) => language.code === currentLanguage)?.sampleText ||
            'Hello. Thank you for calling. How can I help you today?',
        }));

      // Multilingual Gemini Live voices (Zephyr, Aoede, Kore, Leda, Puck, Charon, Fenrir, Orus, etc.)
      const multilingualVoices = liveVoices.filter((voice) => !voice.languageCode);
      // Regional dialect voices matching current language (e.g. te-in-csagent-5 for te-IN)
      const localeVoices = liveVoices.filter((voice) => voice.languageCode === currentLanguage);

      if (multilingualVoices.length || localeVoices.length) {
        // Core Gemini 3.8 Live voices: Zephyr first, followed by the rest of the core roster
        const CORE_ORDER = ['zephyr', 'aoede', 'kore', 'leda', 'puck', 'charon', 'fenrir', 'orus'];
        const combined = [...multilingualVoices, ...localeVoices];
        const seen = new Set();
        const deduped = [];
        // First add core voices in order
        for (const cid of CORE_ORDER) {
          const match = combined.find((v) => String(v.id).toLowerCase() === cid);
          if (match && !seen.has(String(match.id).toLowerCase())) {
            seen.add(String(match.id).toLowerCase());
            deduped.push(match);
          }
        }
        // Then add locale-specific presets for current language
        for (const v of localeVoices) {
          const idKey = String(v.id).toLowerCase();
          if (!seen.has(idKey)) {
            seen.add(idKey);
            deduped.push(v);
          }
        }
        // Then add any remaining voices
        for (const v of combined) {
          const idKey = String(v.id).toLowerCase();
          if (!seen.has(idKey)) {
            seen.add(idKey);
            deduped.push(v);
          }
        }
        return deduped.map(localizeVoice);
      }
      if (liveVoices.length) return liveVoices.map(localizeVoice);
    }
    return VOICE_CATALOG.map((catVoice) => {
      const match = phoneVoices.find(
        (pv) =>
          pv.id?.toLowerCase() === catVoice.id.toLowerCase() ||
          pv.name?.toLowerCase() === catVoice.name.toLowerCase()
      );
      if (match) {
        return localizeVoice({
          ...catVoice,
          name: match.name || match.label || catVoice.name,
          label: match.label || match.name || catVoice.name,
          category: match.category || catVoice.category,
          useCase: match.useCase || catVoice.useCase,
          tone: match.tone || catVoice.tone,
          gender: match.gender && match.gender !== 'neutral' ? match.gender : catVoice.gender,
        });
      }
      return localizeVoice(catVoice);
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

      const langPrefix = String(currentLanguage || 'te-IN').split('-')[0].toLowerCase();
      const vid = String(voice.id || '').toLowerCase();
      const audioUrl = voice.sampleUrl || `/audio/voxly/samples/${vid}_${langPrefix}.wav`;
      const fallbackUrl = voice.fallbackUrl || `/audio/voxly/samples/${vid}.wav`;
      const previewText =
        voice.sampleText ||
        EXTENDED_LANGUAGES.find((language) => language.code === currentLanguage)?.sampleText ||
        'Hello. Thank you for calling. How can I help you today?';

      if (activeVoiceProvider === 'gemini') {
        try {
          const result = await api.telephony.previewVoice({
            text: previewText,
            voiceId: voice.id,
            language: currentLanguage,
            speed: currentSpeed,
          });
          if (result?.blob) {
            const played = await voiceAgent.playAudioBuffer(
              result.blob,
              () => {
                setPlayingVoiceId((curr) => (curr === voice.id ? null : curr));
                setPlayingType((curr) => (curr === 'sample' ? null : curr));
              },
              () => {
                setPlayingVoiceId(voice.id);
                setPlayingType('sample');
              }
            );
            if (played) return;
          }
        } catch (e) {
          const msg = String(e?.message || '').trim();
          if (msg && !msg.includes('Failed to fetch')) {
            setPlayingVoiceId(null);
            setPlayingType(null);
            setAudioError(msg);
            return;
          }
        }
      }

      try {
        voiceAgent.playAudioClip(
          audioUrl,
          () => {
            setPlayingVoiceId((curr) => (curr === voice.id ? null : curr));
            setPlayingType((curr) => (curr === 'sample' ? null : curr));
          },
          () => {
            setPlayingVoiceId(voice.id);
            setPlayingType('sample');
          },
          {
            fallbackUrl,
            fallbackText: previewText,
          }
        );
      } catch (e) {
        setPlayingVoiceId(null);
        setPlayingType(null);
        setAudioError(
          String(e?.message || '').trim() ||
            'Could not play the voice sample. Check the audio output device.'
        );
      }
    },
    [playingVoiceId, playingType, currentLanguage, currentSpeed, activeVoiceProvider]
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
      const multilingualDefault =
        phoneVoices.find(
          (voice) => voice.provider === 'gemini' && voice.id?.toLowerCase() === 'zephyr'
        ) ||
        phoneVoices.find(
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
      const langPrefix = String(currentLanguage || 'te-IN').split('-')[0].toLowerCase();
      const localizedGreetingUrl = `/audio/voxly/samples/${currentVoiceId?.toLowerCase()}_${langPrefix}.wav`;
      const fallbackUrl = `/audio/voxly/samples/${currentVoiceId?.toLowerCase()}.wav`;
      voiceAgent.playAudioClip(
        localizedGreetingUrl,
        () => handleStopAudio(),
        () => {
          setPlayingType('greeting');
          setPlayingVoiceId(currentVoiceId);
        },
        { fallbackUrl, fallbackText: greetingText }
      );
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
      <section
        className="rounded-xl border border-[#E4E2EB] bg-white p-4 shadow-xs space-y-4"
        data-testid="voice-stack-selector"
        aria-busy={voiceStackCatalogLoading}
      >
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="text-sm font-bold text-[#0F0E17]">Voice setup</h2>
            <p className="mt-1 text-xs text-[#524E5E]">
              Saved setup:{' '}
              <strong className="text-[#0F0E17]">
                {isStackOptedIn && STACK_TIER_LABELS[agent?.defaultTier]
                  ? STACK_TIER_LABELS[agent.defaultTier]
                  : 'Current voice configuration'}
              </strong>
              {isStackOptedIn && savedVoice ? ` · ${savedVoice.label}` : ''}
            </p>
            <p className="mt-1 text-[11px] text-[#716C7F]">
              Saved changes apply to new calls. Calls already in progress keep their current setup.
            </p>
          </div>
          {isStackOptedIn && agent?.defaultTier === 'premium' && (
            <span className="rounded-full border border-[#6344E7]/20 bg-[#6344E7]/5 px-2.5 py-1 text-[11px] font-semibold text-[#5233D6]">
              Live voice controls below
            </span>
          )}
        </div>

        {draftSelection?.tier && ['low', 'medium'].includes(draftSelection.tier) && (
          <div className="max-w-sm space-y-1.5">
            <label htmlFor="voice-stack-language" className="block text-xs font-semibold text-[#0F0E17]">
              Voice language
            </label>
            <select
              id="voice-stack-language"
              value={currentLanguage}
              onChange={(event) => handleStackLanguageChange(event.target.value)}
              disabled={isSavingStackSelection}
              className="w-full rounded-lg border border-[#D8D5E1] bg-white px-3 py-2 text-sm text-[#0F0E17] focus:border-[#6344E7] focus:outline-none focus:ring-2 focus:ring-[#6344E7]/20"
              data-testid="voice-stack-language"
            >
              {!EXTENDED_LANGUAGES.some((language) => language.code === currentLanguage) && (
                <option value={currentLanguage}>{currentLanguage}</option>
              )}
              {EXTENDED_LANGUAGES.map((language) => (
                <option key={language.code} value={language.code}>
                  {language.nativeName} · {language.code}
                </option>
              ))}
            </select>
            {stackLanguageNeedsSave && (
              <p className="text-[11px] text-amber-800" data-testid="voice-stack-language-unsaved">
                Save the language change with the agent before applying this voice setup.
              </p>
            )}
          </div>
        )}

        {voiceStackCatalogLoading && (
          <p className="text-xs text-[#716C7F]" role="status" data-testid="voice-stack-loading">
            Loading approved voice options…
          </p>
        )}
        {voiceStackCatalogError && (
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-800" role="alert">
            <span>{voiceStackCatalogError}</span>
            <button
              type="button"
              onClick={onRetryVoiceStackCatalog}
              disabled={voiceStackCatalogLoading}
              className="rounded-md border border-red-300 px-2.5 py-1 font-semibold hover:bg-red-100 focus:outline-none focus:ring-2 focus:ring-red-400 disabled:opacity-50"
              data-testid="voice-stack-catalog-retry"
            >
              Retry
            </button>
          </div>
        )}
        {!voiceStackCatalogLoading && !voiceStackCatalogError && !voiceCatalogLoading && selectableStackProfiles.length === 0 && (
          <p className="rounded-lg border border-[#E4E2EB] bg-[#FAF9FD] px-3 py-2.5 text-xs text-[#524E5E]" data-testid="voice-stack-empty">
            No approved voice setup is available for this language yet. Your current saved setup is unchanged.
          </p>
        )}

        {selectableStackProfiles.length > 0 && (
          <fieldset className="space-y-2" disabled={isSavingStackSelection || voiceStackCatalogLoading}>
            <legend className="mb-2 text-xs font-semibold text-[#0F0E17]">Choose a ready voice tier</legend>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
              {selectableStackProfiles.map((profile) => {
                const selected = draftSelection?.tier === profile.tier;
                return (
                  <label
                    key={profile.tier}
                    className={`flex min-h-14 cursor-pointer items-start gap-2.5 rounded-lg border px-3 py-2.5 transition-colors focus-within:ring-2 focus-within:ring-[#6344E7]/30 ${
                      selected
                        ? 'border-[#6344E7] bg-[#6344E7]/5'
                        : 'border-[#E4E2EB] bg-white hover:border-[#B9B4C8]'
                    }`}
                  >
                    <input
                      type="radio"
                      name={`voice-stack-tier-${agent?.id || 'agent'}`}
                      value={profile.tier}
                      checked={selected}
                      onChange={() => handleStackTierChange(profile.tier)}
                      className="mt-0.5 accent-[#6344E7]"
                      data-testid={`voice-stack-tier-${profile.tier}`}
                    />
                    <span className="min-w-0 flex-1">
                      <span className="block text-xs font-bold text-[#0F0E17]">
                        {STACK_TIER_LABELS[profile.tier]}
                      </span>
                      <span className="mt-0.5 block text-[11px] text-[#716C7F]">
                        Approved retail rate: {formatRetailRate(profile.retailRate)}
                      </span>
                    </span>
                  </label>
                );
              })}
            </div>
          </fieldset>
        )}

        {draftSelection?.tier && ['low', 'medium'].includes(draftSelection.tier) && currentStackProfile && (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3" data-testid="voice-stack-options">
            <label className="space-y-1.5 text-xs font-semibold text-[#0F0E17]">
              <span>Engine</span>
              <select
                value={draftSelection.engineId}
                onChange={(event) => handleStackEngineChange(event.target.value)}
                disabled={isSavingStackSelection || currentStackEngines.length === 0}
                className="w-full rounded-lg border border-[#D8D5E1] bg-white px-3 py-2 text-sm font-normal focus:border-[#6344E7] focus:outline-none focus:ring-2 focus:ring-[#6344E7]/20"
                data-testid="voice-stack-engine"
              >
                <option value="">Select an engine</option>
                {currentStackEngines.map((engine) => (
                  <option key={engine.id} value={engine.id}>{engine.label}</option>
                ))}
              </select>
            </label>
            <label className="space-y-1.5 text-xs font-semibold text-[#0F0E17]">
              <span>Model</span>
              <select
                value={draftSelection.modelId}
                onChange={(event) => handleStackModelChange(event.target.value)}
                disabled={isSavingStackSelection || !currentStackEngine}
                className="w-full rounded-lg border border-[#D8D5E1] bg-white px-3 py-2 text-sm font-normal focus:border-[#6344E7] focus:outline-none focus:ring-2 focus:ring-[#6344E7]/20"
                data-testid="voice-stack-model"
              >
                <option value="">Select a model</option>
                {(currentStackEngine?.models || []).map((model) => (
                  <option key={model.id} value={model.id}>{model.label}</option>
                ))}
              </select>
            </label>
            <label className="space-y-1.5 text-xs font-semibold text-[#0F0E17]">
              <span>Voice</span>
              <select
                value={draftSelection.voiceId}
                onChange={(event) => {
                  setDraftSelection((current) => ({ ...current, voiceId: event.target.value }));
                  setPreviewError(false);
                  setStackSelectionError(null);
                  setStackSelectionNotice(null);
                }}
                disabled={isSavingStackSelection || !currentStackModel}
                className="w-full rounded-lg border border-[#D8D5E1] bg-white px-3 py-2 text-sm font-normal focus:border-[#6344E7] focus:outline-none focus:ring-2 focus:ring-[#6344E7]/20"
                data-testid="voice-stack-voice"
              >
                <option value="">Select a voice</option>
                {(currentStackModel?.voices || []).map((voice) => (
                  <option key={voice.id} value={voice.id}>{voice.label}</option>
                ))}
              </select>
            </label>
          </div>
        )}

        {draftSelection?.tier && ['low', 'medium'].includes(draftSelection.tier) && currentStackVoice && (
          <div className="rounded-lg border border-[#E4E2EB] bg-[#FAF9FD] p-3" data-testid="voice-stack-preview">
            <p className="text-xs font-semibold text-[#0F0E17]">{currentStackVoice.label}</p>
            {typeof currentStackVoice.previewUrl === 'string' && currentStackVoice.previewUrl.trim() ? (
              <div className="mt-2 space-y-1.5">
                <audio
                  key={`${currentStackVoice.id}-${previewRetry}`}
                  controls
                  preload="none"
                  src={currentStackVoice.previewUrl}
                  onError={() => setPreviewError(true)}
                  aria-label={`Approved voice sample for ${currentStackVoice.label}`}
                  className="w-full"
                  data-testid="voice-stack-audio-preview"
                />
                {previewError && (
                  <div className="flex items-center justify-between gap-2 text-[11px] text-red-700" role="alert">
                    <span>That approved sample could not be played.</span>
                    <button
                      type="button"
                      onClick={() => {
                        setPreviewError(false);
                        setPreviewRetry((current) => current + 1);
                      }}
                      className="rounded-md border border-red-300 px-2 py-1 font-semibold hover:bg-red-50 focus:outline-none focus:ring-2 focus:ring-red-400"
                      data-testid="voice-stack-preview-retry"
                    >
                      Retry sample
                    </button>
                  </div>
                )}
              </div>
            ) : (
              <p className="mt-1 text-[11px] text-[#716C7F]">No approved audio sample is available for this voice.</p>
            )}
          </div>
        )}

        {draftSelection?.tier === 'premium' && (
          <p className="rounded-lg border border-[#E4E2EB] bg-[#FAF9FD] px-3 py-2.5 text-xs text-[#524E5E]">
            This tier keeps the existing Live voice path. Choose or review its voice in the controls below.
          </p>
        )}

        {stackSelectionError && (
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-800" role="alert" data-testid="voice-stack-save-error">
            <span>{stackSelectionError}</span>
            {stackSelectionConflict && onReloadVoiceStackSettings && (
              <button
                type="button"
                onClick={handleReloadStackSettings}
                disabled={isSavingStackSelection}
                className="rounded-md border border-red-300 px-2.5 py-1 font-semibold hover:bg-red-100 focus:outline-none focus:ring-2 focus:ring-red-400 disabled:opacity-50"
                data-testid="voice-stack-conflict-reload"
              >
                Reload saved settings
              </button>
            )}
          </div>
        )}
        {stackSelectionNotice && (
          <p className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-800" role="status" data-testid="voice-stack-save-status">
            {stackSelectionNotice}
          </p>
        )}

        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-[#F0EEF6] pt-3">
          <p className="text-[11px] text-[#716C7F]">
            {isStackOptedIn && savedSelection.tier && STACK_TIER_LABELS[savedSelection.tier]
              ? `Saved configuration: ${STACK_TIER_LABELS[savedSelection.tier]}${savedVoice ? ` · ${savedVoice.label}` : ''}`
              : 'Your current voice configuration remains active until a ready tier is saved.'}
          </p>
          <div className="flex items-center gap-2">
            {hasUnsavedStackSelection && (
              <button
                type="button"
                onClick={() => {
                  setDraftSelection(savedSelection);
                  setStackSelectionError(null);
                  setStackSelectionNotice(null);
                  setStackSelectionConflict(false);
                }}
                disabled={isSavingStackSelection}
                className="rounded-lg px-3 py-2 text-xs font-semibold text-[#524E5E] hover:bg-[#FAF9FD] focus:outline-none focus:ring-2 focus:ring-[#6344E7]/30 disabled:opacity-50"
                data-testid="voice-stack-reset"
              >
                Restore saved choice
              </button>
            )}
            <button
              type="button"
              onClick={handleSaveStackSelection}
              disabled={!canSaveStackSelection || isSavingStackSelection || stackSelectionConflict}
              className="rounded-lg bg-[#0F0E17] px-4 py-2 text-xs font-semibold text-white shadow-xs hover:bg-[#232130] focus:outline-none focus:ring-2 focus:ring-[#6344E7]/40 disabled:cursor-not-allowed disabled:opacity-45"
              data-testid="voice-stack-save"
            >
              {isSavingStackSelection ? 'Saving…' : 'Save voice setup'}
            </button>
          </div>
        </div>
      </section>

      {showExistingLiveVoiceControls && (
        <>
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
                {draftSelection?.tier === 'premium' ? STACK_TIER_LABELS.premium : 'Current voice setup'}
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
        </>
      )}
    </div>
  );
}

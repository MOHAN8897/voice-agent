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
  RefreshCw,
} from 'lucide-react';
import { voiceAgent } from '../../../services/voiceAgent';
import { api } from '../../../services/api';
import { showToast } from '../../ui/ToastHost';
import { BLOCKED_TENANT_TERMS, publicLabel } from '../../../lib/internalLabels';
import { Badge } from '../../ui/StatusBadge';

// Voice inventories come from the authenticated catalog; never invent offline choices.
export const VOICE_CATALOG = [];

const STACK_TIER_LABELS = {
  low: 'Basic voice',
  medium: 'Standard voice',
  premium: 'Premium live voice',
};
// The admin-configured tier name wins so the console matches billing and pricing.
function tierName(tier, profile) {
  return publicText(profile?.label) || STACK_TIER_LABELS[tier] || tier;
}

function publicChoice(value) {
  return typeof value === 'string' && value.trim() && !BLOCKED_TENANT_TERMS.test(value);
}

// Provider metadata is display-only, but a misconfigured profile must never be
// able to surface an internal stack or vendor name in the tenant UI.
function publicText(value) {
  return publicLabel(value);
}

function publicPreviewUrl(value) {
  const url = typeof value === 'string' ? value.trim() : '';
  return /^\/api\/telephony\/voice-preview\/(catalog|live)\?[A-Za-z0-9_.~%&=+-]+$/.test(url) ? url : '';
}

function formatCategory(value) {
  const text = publicText(value);
  if (!text) return '';
  const normalized = text.replace(/[_-]+/g, ' ').trim().toLowerCase();
  const known = {
    conversation: 'Conversation',
    conversational: 'Conversational',
    support: 'Customer care',
    care: 'Customer care',
    sales: 'Sales and outreach',
    promotional: 'Promotional',
    operations: 'Operations',
    narration: 'Narration',
    normal: 'General',
  };
  return known[normalized] || normalized.replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function voiceMetaLine(voice) {
  return [publicText(voice?.tone), publicText(voice?.useCase)].filter(Boolean).join(' · ');
}

function voiceGender(value) {
  const gender = String(value || '').trim().toLowerCase();
  if (gender === 'female' || gender === 'feminine') return 'female';
  if (gender === 'male' || gender === 'masculine') return 'male';
  if (gender === 'neutral' || gender === 'gender_neutral') return 'neutral';
  return '';
}

function matchesGender(voice, filter) {
  if (!filter || filter === 'all') return true;
  // Voices without published gender stay in All rather than being guessed into
  // a category they do not belong to.
  return voiceGender(voice?.gender) === filter;
}

const voicePreviewBlobs = new Map();
const voicePreviewRequests = new Map();

async function loadVoicePreview(url) {
  if (voicePreviewBlobs.has(url)) return voicePreviewBlobs.get(url);
  if (!voicePreviewRequests.has(url)) {
    const request = api.telephony.fetchVoicePreview(url)
      .then((blob) => {
        if (blob) voicePreviewBlobs.set(url, blob);
        return blob;
      })
      .finally(() => voicePreviewRequests.delete(url));
    voicePreviewRequests.set(url, request);
  }
  return voicePreviewRequests.get(url);
}

function hasApprovedRetailRate(rate) {
  if (rate?.complete === true) {
    return [rate.usdMicrosPerMin, rate.inrPaisePerMin, rate.version].every(
      (value) => Number.isSafeInteger(value) && value > 0
    );
  }
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
  if (rate.complete === true) {
    return `${new Intl.NumberFormat(undefined, { style: 'currency', currency: 'USD', maximumFractionDigits: 4 }).format(rate.usdMicrosPerMin / 1_000_000)} / ${new Intl.NumberFormat(undefined, { style: 'currency', currency: 'INR', maximumFractionDigits: 2 }).format(rate.inrPaisePerMin / 100)} per min`;
  }
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
    typeof profile.tier !== 'string' ||
    !profile.tier.trim() ||
    !Number.isSafeInteger(profile.profileRevision) ||
    profile.profileRevision < 0 ||
    !hasApprovedRetailRate(profile.retailRate)
  ) {
    return false;
  }
  return publicEngines(profile, language).length > 0;
}

function selectionFromAgent(agent) {
  const settings = agent?.voiceSettings;
  if (settings?.stackSelectionVersion !== 1 || !agent?.defaultTier) {
    return { tier: '', engineId: '', modelId: '', voiceId: '' };
  }
  return {
    tier: agent.defaultTier,
    profileRevision: settings.profileRevision,
    engineId: settings.engineId || '',
    modelId: settings.modelId || '',
    voiceId: settings.voiceId || settings.realtimeVoice || '',
  };
}

function selectionKey(selection) {
  return [selection.tier, selection.profileRevision, selection.engineId, selection.modelId, selection.voiceId].join('|');
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
    badge: 'Regional voices',
  },
  {
    code: 'en-IN',
    name: 'English (India)',
    nativeName: 'Indian English',
    flag: '🇮🇳',
    badge: 'Indian accent',
  },
  {
    code: 'hi-IN',
    name: 'Hindi',
    nativeName: 'हिन्दी',
    flag: '🇮🇳',
    badge: 'Regional voices',
  },
  {
    code: 'ta-IN',
    name: 'Tamil',
    nativeName: 'தமிழ்',
    flag: '🇮🇳',
    badge: 'Regional voices',
  },
  {
    code: 'kn-IN',
    name: 'Kannada',
    nativeName: 'ಕನ್ನಡ',
    flag: '🇮🇳',
    badge: 'Multilingual voice',
  },
  {
    code: 'gu-IN',
    name: 'Gujarati',
    nativeName: 'ગુજરાતી',
    flag: '🇮🇳',
    badge: 'Regional voices',
  },
  {
    code: 'ml-IN',
    name: 'Malayalam',
    nativeName: 'മലയാളം',
    flag: '🇮🇳',
    badge: 'Regional voices',
  },
  {
    code: 'en-US',
    name: 'English (US)',
    nativeName: 'American English',
    flag: '🇺🇸',
    badge: 'American accent',
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
  onVoiceStackReadyChange,
  onSavedVoiceApplied,
  phoneVoices = [],
  activeVoiceProvider = 'openai',
  defaultVoiceId = 'te-in-csagent-5',
  voiceCatalogError = null,
  stackLabel = 'Enterprise Voice Network',
  onOpenTestCall,
  isAdmin = false,
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
  const [tierVoiceCategories, setTierVoiceCategories] = useState({});
  const [tierVoiceGenders, setTierVoiceGenders] = useState({});
  const [previewRetry, setPreviewRetry] = useState(0);
  const [previewError, setPreviewError] = useState(false);
  const agentIdRef = useRef(agent?.id);
  const savedSelection = useMemo(() => selectionFromAgent(agent), [
    agent?.id,
    agent?.defaultTier,
    agent?.voiceSettings?.stackSelectionVersion,
    agent?.voiceSettings?.profileRevision,
    agent?.voiceSettings?.engineId,
    agent?.voiceSettings?.modelId,
    agent?.voiceSettings?.voiceId,
    agent?.voiceSettings?.realtimeVoice,
  ]);
  const savedSelectionRevision = Number.isSafeInteger(agent?.voiceRevision) ? agent.voiceRevision : 0;
  const savedSelectionStateKey = `${selectionKey(savedSelection)}|${savedSelectionRevision}`;
  const isStackOptedIn = agent?.voiceSettings?.stackSelectionVersion === 1;
  const catalogStackProfiles = Array.isArray(voiceStackProfiles)
    ? voiceStackProfiles.filter((profile) => profile?.tier && profile?.enabled !== false && !profile?.blockers?.some(b => b.code === 'profile_not_available'))
    : [];
  const [isRefreshingVoiceData, setIsRefreshingVoiceData] = useState(false);

  const handleRefreshAllVoiceData = useCallback(async () => {
    if (isRefreshingVoiceData) return;
    setIsRefreshingVoiceData(true);
    try {
      const results = await Promise.allSettled([
        onRetryVoiceStackCatalog ? onRetryVoiceStackCatalog() : Promise.resolve(),
        onRetryVoiceCatalog ? onRetryVoiceCatalog() : Promise.resolve(),
        onReloadVoiceStackSettings ? onReloadVoiceStackSettings() : Promise.resolve(),
      ]);
      if (results.some((result) => result.status === 'rejected' || result.value === null || result.value?.error)) {
        showToast('Some voice options could not be refreshed. Check the messages below and try again.', 'error');
      } else {
        showToast('Voice options refreshed.', 'success');
      }
    } catch {
      showToast('Voice options could not be refreshed. Try again.', 'error');
    } finally {
      setIsRefreshingVoiceData(false);
    }
  }, [isRefreshingVoiceData, onRetryVoiceStackCatalog, onRetryVoiceCatalog, onReloadVoiceStackSettings]);
  const selectableStackProfiles = useMemo(
    () =>
      voiceStackProfiles
        .filter((profile) => isSelectableProfile(profile, currentLanguage)),
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
  const userChangedChoice = Boolean(
    savedSelection.tier && (
      draftSelection.tier !== savedSelection.tier ||
      draftSelection.voiceId !== savedSelection.voiceId ||
      (Boolean(draftSelection.engineId) && (
        draftSelection.engineId !== savedSelection.engineId ||
        draftSelection.modelId !== savedSelection.modelId
      ))
    )
  );
  const hasUnsavedStackSelection = userChangedChoice;
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
      (currentStackProfile.tier === 'premium' || currentStackVoice) &&
      !stackLanguageNeedsSave &&
      !voiceStackCatalogLoading
  );
  const showExistingLiveVoiceControls =
    (draftSelection?.tier === 'premium' && !currentStackProfile?.engines?.length) ||
    (!isStackOptedIn && !draftSelection?.tier);

  // Admin edits (labels, prices, knobs) bump a profile's revision on every save.
  // The server keeps a saved choice valid while its engine/model/voice still
  // resolve in the current catalog (resolve_agent_selection), so the console
  // must too: comparing revisions here made a still-saved voice look lost.
  const savedSelectionValid = Boolean(savedProfile && savedVoice);
  const voiceStackReady = savedSelectionValid && !voiceStackCatalogLoading && !isSavingStackSelection && !hasUnsavedStackSelection &&
    !stackLanguageNeedsSave && !stackSelectionError && !stackSelectionConflict;
  useEffect(() => {
    onVoiceStackReadyChange?.(Boolean(voiceStackReady));
  }, [onVoiceStackReadyChange, voiceStackReady]);

  useEffect(() => {
    if (!stackSelectionConflict || agentIdRef.current !== agent?.id) setDraftSelection(savedSelection);
    if (agentIdRef.current !== agent?.id) {
      setStackSelectionError(null);
      setStackSelectionNotice(null);
      setStackSelectionConflict(false);
      setPreviewError(false);
      agentIdRef.current = agent?.id;
    }
  }, [agent?.id, savedSelectionStateKey]);

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

  const confirmStackSave = useCallback((result) => {
    if (result?.conflict) {
      setStackSelectionConflict(true);
      setStackSelectionError(
        'Another editor saved newer voice settings. Your choice was not applied. Reload the saved settings before continuing.'
      );
      return false;
    }
    if (result?.languageNeedsSave) {
      setStackSelectionError('Save the language change before applying this voice setup.');
      return false;
    }
    if (result?.savedButUnconfirmed) {
      setStackSelectionConflict(true);
      setStackSelectionError('The save could not be confirmed. Reload the saved settings before trying again.');
      return false;
    }
    if (result?.error || !result?.agent) {
      setStackSelectionError(typeof result?.error === 'string'
        ? result.error
        : 'Voice setup could not be saved. Your saved choice is unchanged. Try again.');
      return false;
    }
    setDraftSelection(selectionFromAgent(result.agent));
    setStackSelectionConflict(false);
    setStackSelectionNotice('Voice setup saved. New calls will use this setting.');
    return true;
  }, []);

  const handleSaveStackSelection = async () => {
    if (!canSaveStackSelection || isSavingStackSelection) return;
    setIsSavingStackSelection(true);
    setStackSelectionError(null);
    setStackSelectionNotice(null);
    try {
      confirmStackSave(await onSaveVoiceStackSelection({
        tier: draftSelection.tier,
        ...(draftSelection.tier === 'premium'
          ? { realtimeVoice: draftSelection.voiceId }
          : {
              profileRevision: currentStackProfile?.profileRevision,
              engineId: draftSelection.engineId,
              modelId: draftSelection.modelId,
              voiceId: draftSelection.voiceId,
            }),
      }));
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
  const [playingType, setPlayingType] = useState(null); // 'sample'
  const [audioError, setAudioError] = useState(null);
  const [activeCategory, setActiveCategory] = useState('all');
  const [genderFilter, setGenderFilter] = useState('all');
  const [showAcousticControls, setShowAcousticControls] = useState(false);

  // Display-only projection of server catalog rows. Playback URLs and sample
  // text are server-owned; nothing is synthesized or located by the browser.
  const displayVoices = useMemo(() => {
    const sanitizeVoice = (voice) => ({
      ...voice,
      name: '',
      label: '',
      gender: voiceGender(voice?.gender),
      category: publicText(voice?.category),
      tone: publicText(voice?.tone),
      useCase: publicText(voice?.useCase),
      accent: publicText(voice?.accent),
      tag: publicText(voice?.tag),
      duration: publicText(voice?.duration),
      previewUrl: publicPreviewUrl(voice?.previewUrl),
    });

    if (activeVoiceProvider === 'gemini') {
      const liveVoices = phoneVoices
        .filter((voice) => voice.provider === 'gemini')
        .filter(
          (voice) =>
            !Array.isArray(voice.languages) ||
            voice.languages.length === 0 ||
            voice.languages.includes(currentLanguage)
        )
        .map(sanitizeVoice);
      const multilingualVoices = liveVoices.filter((voice) => !voice.languageCode);
      const localeVoices = liveVoices.filter((voice) => voice.languageCode === currentLanguage);
      const combined = [...multilingualVoices, ...localeVoices];
      const seen = new Set();
      const deduped = [];
      const CORE_ORDER = ['zephyr', 'aoede', 'kore', 'leda', 'puck', 'charon', 'fenrir', 'orus'];
      for (const id of CORE_ORDER) {
        const match = combined.find((voice) => String(voice.id).toLowerCase() === id);
        if (match && !seen.has(String(match.id).toLowerCase())) {
          seen.add(String(match.id).toLowerCase());
          deduped.push(match);
        }
      }
      for (const voice of localeVoices) {
        const key = String(voice.id).toLowerCase();
        if (!seen.has(key)) {
          seen.add(key);
          deduped.push(voice);
        }
      }
      for (const voice of combined) {
        const key = String(voice.id).toLowerCase();
        if (!seen.has(key)) {
          seen.add(key);
          deduped.push(voice);
        }
      }
      return deduped.map((voice, index) => ({
        ...voice,
        name: `Voice ${index + 1}`,
        label: `Voice ${index + 1}`,
      }));
    }

    return VOICE_CATALOG.map((catVoice, index) => {
      const match = phoneVoices.find(
        (pv) =>
          pv.id?.toLowerCase() === catVoice.id.toLowerCase() ||
          pv.name?.toLowerCase() === catVoice.name.toLowerCase()
      );
      const merged = sanitizeVoice({ ...catVoice, ...(match || {}) });
      return { ...merged, name: `Voice ${index + 1}`, label: `Voice ${index + 1}` };
    });
  }, [phoneVoices, activeVoiceProvider, currentLanguage, currentVoiceId]);

  const voiceCategoryCounts = useMemo(() => {
    const isConv = (v) => v.category === 'conversational' || v.category === 'support' || v.category === 'care';
    const isPromo = (v) => v.category === 'promotional' || v.category === 'sales' || v.category === 'operations';
    return {
      all: displayVoices.length,
      conversational: displayVoices.filter(isConv).length,
      promotional: displayVoices.filter(isPromo).length,
    };
  }, [displayVoices]);

  // Gender splits are counted inside the active category so the buttons always
  // add up to the row count the tenant is currently looking at.
  const showcaseGenderCounts = useMemo(() => {
    const inCategory = displayVoices.filter((v) => {
      if (activeCategory === 'all') return true;
      if (activeCategory === 'conversational') {
        return v.category === 'conversational' || v.category === 'support' || v.category === 'care';
      }
      if (activeCategory === 'promotional') {
        return v.category === 'promotional' || v.category === 'sales' || v.category === 'operations';
      }
      return v.category === activeCategory;
    });
    const count = (gender) => inCategory.filter((v) => voiceGender(v.gender) === gender).length;
    return {
      all: inCategory.length,
      female: count('female'),
      male: count('male'),
      neutral: count('neutral'),
    };
  }, [displayVoices, activeCategory]);

  // Filtered voice list
  const filteredVoices = useMemo(() => {
    return displayVoices.filter((v) => {
      if (activeCategory !== 'all') {
        const cat = v.category;
        if (activeCategory === 'conversational') {
          if (cat !== 'conversational' && cat !== 'support' && cat !== 'care') return false;
        } else if (activeCategory === 'promotional') {
          if (cat !== 'promotional' && cat !== 'sales' && cat !== 'operations') return false;
        } else if (cat !== activeCategory) {
          return false;
        }
      }
      if (!matchesGender(v, genderFilter)) return false;
      return true;
    });
  }, [displayVoices, activeCategory, genderFilter]);

  // Active voice metadata
  const activeVoice = useMemo(() => {
    return (
      displayVoices.find((v) => v.id === currentVoiceId) ||
      displayVoices[0] ||
      { name: "Choose a voice", tone: "" }
    );
  }, [displayVoices, currentVoiceId]);

  // Active language metadata
  const activeLanguage = useMemo(() => {
    return (
      EXTENDED_LANGUAGES.find((l) => l.code === currentLanguage) ||
      EXTENDED_LANGUAGES[0]
    );
  }, [currentLanguage]);

  // Computed voices for each tier for the active language
  const tierVoicesMap = useMemo(() => {
    const map = {};
    for (const profile of catalogStackProfiles) {
      if (!profile?.tier) continue;
      if (profile.tier === 'premium' && !profile.engines?.length) {
        map.premium = displayVoices.map((v, idx) => ({
          ...v,
          name: `Voice ${idx + 1}`,
          label: `Voice ${idx + 1}`,
        }));
      } else {
        const engines = publicEngines(profile, currentLanguage);
        const voices = [];
        for (const engine of engines) {
          for (const model of engine.models || []) {
            for (const v of model.voices || []) {
              const voiceNumber = voices.length + 1;
              voices.push({
                ...v,
                tier: profile.tier,
                profileRevision: profile.profileRevision,
                engineId: engine.id,
                modelId: model.id,
                audioStreaming: model.audioStreaming,
                gender: voiceGender(v.gender),
                category: publicText(v.category),
                tone: publicText(v.tone),
                useCase: publicText(v.useCase),
                accent: publicText(v.accent),
                tag: publicText(v.tag),
                previewUrl: publicPreviewUrl(v.previewUrl),
                name: `Voice ${voiceNumber}`,
                label: `Voice ${voiceNumber}`,
              });
            }
          }
        }
        map[profile.tier] = voices;
      }
    }
    return map;
  }, [catalogStackProfiles, currentLanguage, displayVoices]);

  // Every catalog voice plays the server's stored sample for its own URL.
  const handlePlayVoiceSample = useCallback(
    async (voice) => {
      setAudioError(null);

      if (playingVoiceId === voice.id && playingType === 'sample') {
        voiceAgent.stopTTS();
        setPlayingVoiceId(null);
        setPlayingType(null);
        return;
      }

      const previewUrl = publicPreviewUrl(voice?.previewUrl);
      if (!previewUrl) {
        setAudioError('There is no sample for this voice yet. Refresh the voice list and try again.');
        return;
      }

      voiceAgent.stopTTS();
      setPlayingVoiceId(voice.id);
      setPlayingType('sample');

      const finish = () => {
        setPlayingVoiceId((curr) => (curr === voice.id ? null : curr));
        setPlayingType((curr) => (curr === 'sample' ? null : curr));
      };
      try {
        const blob = await loadVoicePreview(previewUrl);
        if (blob && await voiceAgent.playAudioBuffer(blob, finish, () => {
          setPlayingVoiceId(voice.id);
          setPlayingType('sample');
        })) {
          return;
        }
        setAudioError('The voice sample could not be played. Check the audio output device.');
      } catch (e) {
        setAudioError(
          String(e?.message || '').trim() ||
            'The voice sample could not be loaded. Try again in a moment.'
        );
      }
      setPlayingVoiceId(null);
      setPlayingType(null);
    },
    [playingVoiceId, playingType]
  );

  const handleStopAudio = useCallback(() => {
    voiceAgent.stopTTS();
    setPlayingVoiceId(null);
    setPlayingType(null);
  }, []);

  // A live (Flagship) voice that the server has just saved. The saved value is
  // also written into the script form's baseline so it never shows up as an
  // "unsaved change" that Discard would roll back to the previous voice.
  const handleSelectVoice = useCallback(
    (voice) => {
      const voicePatch = {
        provider: 'phone_ai',
        realtimeVoice: voice.id,
        voiceId: voice.id,
        voiceName: voice.name || voice.id,
        language: currentLanguage,
      };
      if (onSavedVoiceApplied) {
        onSavedVoiceApplied({ voice: voicePatch });
      } else {
        setFormData((prev) => ({ ...prev, voice: { ...prev.voice, ...voicePatch } }));
      }
      const tone = publicText(voice.tone);
      showToast(`Speaking voice set to ${voice.name}${tone ? ` (${tone})` : ''}`, 'info');
    },
    [currentLanguage, setFormData, onSavedVoiceApplied]
  );

  // Every voice pick is saved straight away through the revision-checked PATCH.
  // A pick made while an earlier one is still saving is queued (latest wins)
  // instead of being dropped, which used to leave the screen showing a voice the
  // server never received.
  const savingPickRef = useRef(false);
  const pendingPickRef = useRef(null);
  const selectTierVoiceRef = useRef(null);
  const savedSelectionRef = useRef(savedSelection);
  savedSelectionRef.current = savedSelection;

  const handleSelectTierVoice = useCallback(
    async (profile, voice) => {
      if (stackSelectionConflict) return;
      setStackSelectionError(null);
      setStackSelectionNotice(null);
      const isPremium = profile.tier === 'premium' && !profile.engines?.length;
      const newSelection = {
        tier: profile.tier,
        profileRevision: isPremium ? undefined : profile.profileRevision,
        engineId: isPremium ? '' : voice.engineId,
        modelId: isPremium ? '' : voice.modelId,
        voiceId: voice.id,
      };
      setDraftSelection(newSelection);
      if (savingPickRef.current) {
        pendingPickRef.current = { profile, voice };
        return;
      }
      savingPickRef.current = true;
      setIsSavingStackSelection(true);
      try {
        const result = await onSaveVoiceStackSelection?.(isPremium
          ? { tier: 'premium', realtimeVoice: voice.id }
          : newSelection);
        if (!confirmStackSave(result)) {
          // Rejected: show what is actually saved, not the choice that failed.
          if (!result?.conflict && !result?.savedButUnconfirmed) setDraftSelection(savedSelectionRef.current);
          pendingPickRef.current = null;
          return;
        }
        if (isPremium) handleSelectVoice(voice);
        // A composed selection was persisted by the dedicated voice save and
        // stays out of the unpublished script form and its dirty guard.
      } catch {
        setDraftSelection(savedSelectionRef.current);
        pendingPickRef.current = null;
        setStackSelectionError('Voice setup could not be saved. Your saved choice is unchanged. Try again.');
      } finally {
        savingPickRef.current = false;
        setIsSavingStackSelection(false);
        const next = pendingPickRef.current;
        pendingPickRef.current = null;
        // Run the newest handler: it carries the revision the first save returned.
        if (next) setTimeout(() => selectTierVoiceRef.current?.(next.profile, next.voice), 0);
      }
    },
    [handleSelectVoice, onSaveVoiceStackSelection, stackSelectionConflict, confirmStackSave]
  );
  selectTierVoiceRef.current = handleSelectTierVoice;

  const handleStackTierChange = useCallback(
    (tier) => {
      const profile = selectableStackProfiles.find((item) => item.tier === tier);
      const voice = tierVoicesMap[tier]?.[0];
      if (!profile || !voice) return;
      // Selecting a tier applies its first catalog voice through the same
      // revision-checked save as choosing a voice card.
      return handleSelectTierVoice(profile, voice);
    },
    [selectableStackProfiles, tierVoicesMap, handleSelectTierVoice]
  );

  // Language selection
  const handleSelectLanguage = useCallback(
    (langCode) => {
      // Re-clicking the current language changes nothing (it used to reset the
      // composed voice to the tier's first voice).
      if (langCode === currentLanguage) return;
      setStackSelectionError(null);
      setStackSelectionNotice(null);

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

      // Composed tier: a language switch keeps the chosen voice when the tier
      // offers it in the new language. Only a voice the new language cannot use
      // is replaced, and that replacement is a draft the tenant still saves. It
      // is never written into the script form, so the main Save cannot publish
      // a voice the tenant did not pick.
      if (draftSelection?.tier && draftSelection.tier !== 'premium') {
        const prof = selectableStackProfiles.find((p) => p.tier === draftSelection.tier);
        const engines = publicEngines(prof, langCode);
        const keepsVoice = engines.some((engine) => engine.id === draftSelection.engineId &&
          engine.models.some((model) => model.id === draftSelection.modelId &&
            model.voices.some((voice) => voice.id === draftSelection.voiceId)));
        const firstVoice = engines[0]?.models?.[0]?.voices?.[0];
        if (!keepsVoice && firstVoice) {
          setDraftSelection((curr) => ({
            ...curr,
            engineId: engines[0].id,
            modelId: engines[0].models[0].id,
            voiceId: firstVoice.id,
          }));
          setStackSelectionNotice(null);
          setStackSelectionError('Your saved voice does not speak this language. Choose a voice below to save it.');
        } else if (!keepsVoice) {
          setDraftSelection((curr) => ({ ...curr, engineId: '', modelId: '', voiceId: '' }));
        }
      }

      const lMeta = EXTENDED_LANGUAGES.find((l) => l.code === langCode);
      showToast(`Language updated to ${lMeta?.name || langCode}`, 'info');
    },
    [phoneVoices, currentVoiceId, currentLanguage, activeVoiceProvider, draftSelection, selectableStackProfiles, setFormData]
  );



  // Clean up audio on unmount
  useEffect(() => {
    return () => {
      voiceAgent.stopTTS();
    };
  }, []);

  return (
    <div className="space-y-4" data-testid="agent-voice-panel">
      {/* 1. Primary Spoken Language & Accent Card */}
      <div
        className="p-4 sm:p-5 rounded-card bg-surface border border-line shadow-craft-xs space-y-3"
        data-testid="language-selection-card"
      >
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Languages className="w-4 h-4 text-accent" aria-hidden="true" />
            <h2 className="text-title text-ink">
              Spoken language and accent
            </h2>
          </div>
          <span className="text-ui font-medium text-accent-fg">
            Active: {activeLanguage.name} ({activeLanguage.code})
          </span>
        </div>

        {/* Compact Horizontal Pill Grid */}
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2">
          {EXTENDED_LANGUAGES.map((lang) => {
            const isSelected = currentLanguage === lang.code;
            return (
              <button
                key={lang.code}
                type="button"
                data-testid={`language-card-${lang.code}`}
                disabled={isSavingStackSelection || stackSelectionConflict}
                aria-pressed={isSelected}
                onClick={() => handleSelectLanguage(lang.code)}
                title={`${lang.name} (${lang.code})`}
                className={`flex min-w-0 flex-col items-center justify-center p-2 min-h-[64px] rounded-control text-center border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent ${
                  isSelected
                    ? 'bg-accent-soft border-accent text-ink ring-1 ring-accent'
                    : 'bg-canvas border-line text-fg-body hover:border-line-strong hover:bg-surface'
                }`}
              >
                <div className="flex items-center gap-1">
                  <span className="text-copy">{lang.flag}</span>
                  <span className="text-meta font-medium text-ink">
                    {lang.nativeName}
                  </span>
                </div>
                <span className="text-meta text-fg-body truncate max-w-full">
                  {lang.name}
                </span>
                <span className="text-meta font-mono text-fg-muted mt-0.5">
                  {lang.code}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      <section
        className="rounded-card border border-line bg-surface p-4 sm:p-5 shadow-craft-xs space-y-4"
        data-testid="voice-stack-selector"
        aria-busy={voiceStackCatalogLoading}
      >
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="text-title text-ink">Voice setup</h2>
            <p className="mt-1 text-ui text-fg-body">
              Saved setup:{' '}
              <strong className="text-ink">
                {isStackOptedIn && agent?.defaultTier
                  ? tierName(agent.defaultTier, savedProfile)
                  : 'Current voice'}
              </strong>
              {isStackOptedIn && savedVoice ? ` · ${savedVoice.label}` : ''}
            </p>
            <p className="mt-1 text-meta text-fg-muted">
              Saved changes apply to new calls. Calls already in progress keep their current setup.
            </p>
          </div>
          <div className="flex items-center gap-2">
            {isStackOptedIn && agent?.defaultTier === 'premium' && (
              <Badge tone="accent">Live voice controls below</Badge>
            )}
          </div>
        </div>

        {voiceStackCatalogLoading && (
          <p className="text-ui text-fg-muted" role="status" data-testid="voice-stack-loading">
            Loading voice options…
          </p>
        )}
        {voiceStackCatalogError && (
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-control border border-danger-line bg-danger-soft px-3 py-2 text-ui text-danger-fg" role="alert">
            <span>{voiceStackCatalogError}</span>
            <button
              type="button"
              onClick={onRetryVoiceStackCatalog}
              disabled={voiceStackCatalogLoading}
              className="rounded-control border border-danger-line px-2.5 py-1 font-semibold hover:bg-danger-soft focus:outline-none focus:ring-2 focus:ring-danger disabled:opacity-50"
              data-testid="voice-stack-catalog-retry"
            >
              Retry
            </button>
          </div>
        )}
        {!voiceStackCatalogLoading && !voiceStackCatalogError && !voiceCatalogLoading && selectableStackProfiles.length === 0 && (
          <p className="rounded-control border border-line bg-canvas px-3 py-2.5 text-ui text-fg-body" data-testid="voice-stack-empty">
            No voice setup is ready for this language yet. Your saved setup has not changed.
          </p>
        )}

        {/* 3 Columns for the Stacks with Scrollable Voices */}
        {catalogStackProfiles.length > 0 && (
          <fieldset className="space-y-3" disabled={isSavingStackSelection || voiceStackCatalogLoading}>
            <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
              <legend className="text-ui font-semibold text-ink">
                Choose a voice setup
              </legend>
              <button
                type="button"
                onClick={handleRefreshAllVoiceData}
                disabled={isRefreshingVoiceData || voiceStackCatalogLoading}
                className="flex items-center gap-1.5 px-2.5 py-1 min-h-[32px] text-ui font-medium text-fg-body hover:text-ink bg-surface hover:bg-canvas rounded-control border border-line transition-colors cursor-pointer disabled:opacity-50"
                title="Refresh voice options"
                data-testid="refresh-voice-stacks-btn"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${isRefreshingVoiceData || voiceStackCatalogLoading ? 'animate-spin' : ''}`} />
                <span>{isRefreshingVoiceData || voiceStackCatalogLoading ? 'Refreshing…' : 'Refresh options'}</span>
              </button>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3.5">
              {catalogStackProfiles.map((profile) => {
                const isSelectedTier = draftSelection?.tier === profile.tier;
                const ready = isSelectableProfile(profile, currentLanguage);
                const voices = tierVoicesMap[profile.tier] || [];
                const categories = [...new Set(voices.map((voice) => voice.category).filter(Boolean))].sort();
                const category = categories.includes(tierVoiceCategories[profile.tier]) ? tierVoiceCategories[profile.tier] : '';
                const gender = ['female', 'male', 'neutral'].includes(tierVoiceGenders[profile.tier])
                  ? tierVoiceGenders[profile.tier]
                  : 'all';
                const categoryVoices = voices.filter((voice) => !category || voice.category === category);
                const visibleVoices = categoryVoices.filter((voice) => matchesGender(voice, gender));
                const genderCounts = {
                  all: categoryVoices.length,
                  female: categoryVoices.filter((voice) => matchesGender(voice, 'female')).length,
                  male: categoryVoices.filter((voice) => matchesGender(voice, 'male')).length,
                  neutral: categoryVoices.filter((voice) => matchesGender(voice, 'neutral')).length,
                };

                return (
                  <div
                    key={profile.tier}
                    className={`flex min-w-0 flex-col rounded-card border transition-colors ${
                      isSelectedTier
                        ? 'border-accent bg-surface ring-2 ring-accent/20 shadow-craft-xs'
                        : 'border-line bg-surface hover:border-line-strong'
                    } ${!ready ? 'opacity-70' : ''}`}
                  >
                    {/* Column Header */}
                    <div className="p-3.5 border-b border-line bg-canvas/50 rounded-t-card">
                      <div className="flex items-start justify-between gap-2">
                        <label className="flex items-center gap-2 cursor-pointer select-none">
                          <input
                            type="radio"
                            name={`voice-stack-tier-${agent?.id || 'agent'}`}
                            value={profile.tier}
                            checked={isSelectedTier}
                            disabled={!ready || isSavingStackSelection || stackSelectionConflict}
                            aria-describedby={`voice-stack-tier-status-${profile.tier}`}
                            onChange={() => handleStackTierChange(profile.tier)}
                            className="mt-0.5 accent-accent"
                            data-testid={`voice-stack-tier-${profile.tier}`}
                          />
                          <div>
                            <span className="block text-ui font-semibold text-ink">
                              {tierName(profile.tier, profile)}
                            </span>
                            <span className="text-meta text-fg-muted">
                              {profile.tier === 'low'
                                ? 'Lowest price per minute'
                                : profile.tier === 'medium'
                                ? 'Regional voices with more expression'
                                : profile.tier === 'premium'
                                ? 'The most natural, real-time conversation'
                                : (publicText(profile.description) || `${profile.label || 'Custom'} voice`)}
                            </span>
                          </div>
                        </label>
                        <span
                          className="shrink-0 rounded-pill px-2 py-0.5 text-meta font-medium border bg-neutral-soft text-neutral-fg border-neutral-line"
                        >
                          {profile.tier === 'low'
                            ? 'Basic'
                            : profile.tier === 'medium'
                            ? 'Standard'
                            : profile.tier === 'premium'
                            ? 'Premium'
                            : (profile.label || 'Custom')}
                        </span>
                      </div>
                      <div
                        id={`voice-stack-tier-status-${profile.tier}`}
                        className="mt-2 text-meta text-fg-body font-medium"
                      >
                        {ready
                          ? `Phone calls: ${formatRetailRate(profile.retailRate)}`
                          : 'Not available for this language yet.'}
                        {ready && profile.webRetailRate?.complete && <span className="mt-1 block">Web calls: {formatRetailRate(profile.webRetailRate)}</span>}
                      </div>
                    </div>

                    {/* Column Body: Scrollable Voice Section */}
                    <div className="p-3 flex-1 flex flex-col min-h-0">
                      <div className="flex items-center justify-between text-meta font-semibold text-fg-body mb-2">
                        <span>Voices for {activeLanguage.name}</span>
                        <span className="text-meta text-fg-muted font-normal">
                          {visibleVoices.length} {visibleVoices.length === 1 ? 'voice' : 'voices'} available
                        </span>
                      </div>
                      <p className="mb-3 text-meta leading-relaxed text-fg-muted" data-testid={`voice-inventory-summary-${profile.tier}`}>
                        {visibleVoices.length} {activeLanguage.name} {visibleVoices.length === 1 ? 'voice matches' : 'voices match'} your filters
                        {category ? ` · ${formatCategory(category)}` : ' · All styles'}.
                      </p>

                      {categories.length > 0 && <label className="mb-2 text-meta text-fg-body">Voice style
                        <select aria-label={`Voice style for ${profile.label || profile.tier}`} value={category}
                          onChange={(event) => setTierVoiceCategories((previous) => ({ ...previous, [profile.tier]: event.target.value }))}
                          className="mt-1 w-full rounded-control border border-line bg-surface p-2 text-base sm:text-ui">
                          <option value="">All styles ({voices.filter((voice) => matchesGender(voice, gender)).length})</option>
                          {categories.map((style) => <option key={style} value={style}>{formatCategory(style)} ({voices.filter((voice) => voice.category === style && matchesGender(voice, gender)).length})</option>)}
                        </select>
                      </label>}
                      <div className="mb-2 flex items-center gap-0.5 rounded-control border border-line bg-canvas p-0.5" role="group" aria-label={`Voice gender for ${profile.label || profile.tier}`}>
                        {[
                          { id: 'all', label: `All (${genderCounts.all})` },
                          { id: 'female', label: `Female (${genderCounts.female})` },
                          { id: 'male', label: `Male (${genderCounts.male})` },
                          { id: 'neutral', label: `Neutral (${genderCounts.neutral})` },
                        ].map((option) => (
                          <button
                            key={option.id}
                            type="button"
                            aria-pressed={gender === option.id}
                            onClick={() => setTierVoiceGenders((previous) => ({ ...previous, [profile.tier]: option.id }))}
                            className={`flex-1 rounded-[8px] px-1 py-1 min-h-[32px] text-meta font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent ${
                              gender === option.id
                                ? 'bg-surface text-ink shadow-craft-xs'
                                : 'text-fg-body hover:text-ink'
                            }`}
                          >
                            {option.label}
                          </button>
                        ))}
                      </div>
                      <div role="region" aria-label={`Voices for ${profile.label || profile.tier}`} tabIndex={0} className="max-h-60 overflow-y-auto space-y-1.5 pr-1 divide-y divide-line">
                        {voices.length === 0 ? (
                          <div className="py-6 text-center text-ui text-fg-muted italic">
                            No voices for {activeLanguage.name} at this level yet.
                          </div>
                        ) : visibleVoices.length === 0 ? (
                          <div className="py-6 text-center text-ui text-fg-muted italic">
                            No voices match the selected style and gender.
                            <button type="button" className="mt-2 block w-full font-semibold not-italic text-accent"
                              onClick={() => {
                                setTierVoiceCategories((previous) => ({ ...previous, [profile.tier]: '' }));
                                setTierVoiceGenders((previous) => ({ ...previous, [profile.tier]: 'all' }));
                              }}>Clear voice filters</button>
                          </div>
                        ) : (
                          visibleVoices.map((v) => {
                            const isVoiceSelected =
                              profile.tier === 'premium'
                                ? (isSelectedTier || (!isStackOptedIn && !draftSelection?.tier)) &&
                                  (currentVoiceId === v.id || draftSelection?.voiceId === v.id)
                                : isSelectedTier &&
                                  draftSelection?.voiceId === v.id &&
                                  (v.engineId ? draftSelection?.engineId === v.engineId : true);
                            const isPlayingThis = playingVoiceId === v.id && playingType === 'sample';

                            return (
                              <div
                                key={`${profile.tier}-${v.engineId || ''}-${v.id}`}
                                onClick={() => ready && handleSelectTierVoice(profile, v)}
                                className={`flex items-center justify-between gap-2 p-2 rounded-control transition-colors cursor-pointer select-none ${
                                  isVoiceSelected
                                    ? 'bg-accent-soft border border-accent/30'
                                    : 'hover:bg-canvas'
                                }`}
                              >
                                <div className="flex items-center gap-2 min-w-0">
                                  {/* Play/Stop Button */}
                                  <button
                                    type="button"
                                    data-testid={profile.tier === 'premium' && showExistingLiveVoiceControls ? `voice-tier-play-btn-${v.id}` : `voice-play-btn-${v.id}`}
                                    aria-label={`Play preview for ${v.label || v.name}`}
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      handlePlayVoiceSample(v);
                                    }}
                                    className={`w-7 h-7 rounded-full flex items-center justify-center shrink-0 transition-all ${
                                      isPlayingThis
                                        ? 'bg-danger text-white shadow-craft-xs'
                                        : 'bg-accent-soft text-accent hover:bg-accent hover:text-white'
                                    }`}
                                  >
                                    {isPlayingThis ? (
                                      <Square className="w-3 h-3 fill-current" />
                                    ) : (
                                      <Play className="w-3 h-3 fill-current ml-0.5" />
                                    )}
                                  </button>

                                  {/* Voice Name & Details */}
                                  <div className="min-w-0">
                                    <div className="flex items-center gap-1.5 flex-wrap">
                                      <span className="text-ui font-semibold text-ink truncate" title={v.label || v.name}>
                                        {v.label || v.name}
                                      </span>
                                      {v.gender && (
                                        <span className="text-meta px-1.5 rounded-pill bg-surface-subtle text-fg-body font-medium capitalize">
                                          {v.gender}
                                        </span>
                                      )}
                                      {(v.tag === 'Indian' || v.accent?.includes('Indian') || v.useCase?.includes('Indian')) && (
                                        <span className="text-meta px-1.5 rounded-pill font-medium bg-neutral-soft text-neutral-fg border border-neutral-line">
                                          🇮🇳 Indian
                                        </span>
                                      )}
                                      {formatCategory(v.category) && (
                                        <span className="text-meta px-1.5 rounded-pill font-medium bg-info-soft text-info-fg border border-info-line">
                                          {formatCategory(v.category)}
                                        </span>
                                      )}
                                    </div>
                                    <p className="text-meta text-fg-muted truncate">
                                      {voiceMetaLine(v) || (profile.tier === 'premium' ? 'Live voice' : 'Regional voice')}
                                    </p>
                                  </div>
                                </div>

                                {/* Choose / Selected Action */}
                                <button
                                  type="button"
                                  data-testid={profile.tier === 'premium' && showExistingLiveVoiceControls ? `voice-tier-select-btn-${v.id}` : `voice-select-btn-${v.id}`}
                                  disabled={isSavingStackSelection || stackSelectionConflict}
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    handleSelectTierVoice(profile, v);
                                  }}
                                  className={`shrink-0 flex items-center gap-1 px-2.5 py-1 min-h-[32px] rounded-control text-meta font-medium border transition-colors ${
                                    isVoiceSelected
                                      ? 'bg-ink text-white border-ink'
                                      : 'bg-surface text-fg-body hover:text-ink hover:border-line-strong border-line'
                                  }`}
                                >
                                  {isSavingStackSelection && isVoiceSelected ? (
                                    <span>Saving…</span>
                                  ) : isVoiceSelected ? (
                                    <>
                                      <Check className="w-3 h-3 stroke-[3]" />
                                      <span>Selected</span>
                                    </>
                                  ) : (
                                    <span>Choose</span>
                                  )}
                                </button>
                              </div>
                            );
                          })
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </fieldset>
        )}

        {/* Saved configuration indicator & status messages */}
        {!voiceStackCatalogLoading && !savedSelectionValid && !stackSelectionError && (
          <p role="status" data-testid="voice-setup-needs-selection" className="rounded-control border border-warning-line bg-warning-soft px-3 py-2 text-ui text-warning-fg">
            Choose a voice below before testing this employee. If the options have changed, refresh them and choose your voice again.
          </p>
        )}
        {isStackOptedIn && savedSelection.tier && (
          <div className="mt-3 flex items-center justify-between border-t border-line pt-2.5">
            <p className="text-ui text-fg-muted">
              Saved configuration: <span className="font-semibold text-ink">{tierName(savedSelection.tier, savedProfile)}</span>
              {savedVoice ? ` · ${savedVoice.label}` : ''}
            </p>
          </div>
        )}

        {stackSelectionError && (
          <div className="mt-2.5 flex flex-wrap items-center justify-between gap-2 rounded-control border border-danger-line bg-danger-soft px-3 py-2 text-ui text-danger-fg" role="alert" data-testid="voice-stack-save-error">
            <span>{stackSelectionError}</span>
            {stackSelectionConflict && onReloadVoiceStackSettings && (
              <button
                type="button"
                onClick={handleReloadStackSettings}
                disabled={isSavingStackSelection}
                className="rounded-control border border-danger-line px-2.5 py-1 font-semibold hover:bg-danger-soft focus:outline-none focus:ring-2 focus:ring-danger disabled:opacity-50"
                data-testid="voice-stack-conflict-reload"
              >
                Reload saved settings
              </button>
            )}
          </div>
        )}
        {stackSelectionNotice && (
          <p className="mt-2.5 rounded-control border border-success-line bg-success-soft px-3 py-2 text-ui text-success-fg" role="status" data-testid="voice-stack-save-status">
            {stackSelectionNotice}
          </p>
        )}
      </section>

      {showExistingLiveVoiceControls && (
        <>
      {/* 1. Header Bar: Compact Active Summary */}
      <div className="flex flex-wrap items-center justify-between gap-3 p-4 rounded-card bg-surface border border-line shadow-craft-xs">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-control bg-accent-soft flex items-center justify-center text-accent">
            <Volume2 className="w-4 h-4" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-title text-ink">
                Voice and language
              </span>
              <span className="px-2 py-0.5 rounded-pill text-meta font-medium bg-accent-soft text-accent-fg border border-accent/20">
                {draftSelection?.tier === 'premium' ? tierName('premium', currentStackProfile) : 'Current voice setup'}
              </span>
            </div>
            <p className="text-ui text-fg-body">
              Selected: <strong className="text-ink">{activeVoice.name}</strong>
              {publicText(activeVoice.tone) ? ` (${publicText(activeVoice.tone)})` : ''} · <strong className="text-ink">{activeLanguage.name}</strong> ({activeLanguage.code})
            </p>
          </div>
        </div>

        {/* Action Controls & Floating Playing Status */}
        <div className="flex items-center gap-2">
          {playingVoiceId && (
            <div
              className="flex items-center gap-2 px-3 py-1.5 rounded-control bg-accent-soft text-accent-fg text-ui font-medium border border-accent/25"
              data-testid="voice-playing-indicator"
            >
              <div className="flex items-center gap-0.5 h-3">
                <span className="w-0.5 h-3 bg-accent rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="w-0.5 h-2 bg-accent rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="w-0.5 h-3.5 bg-accent rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
              <span>
                Playing sample: {displayVoices.find((v) => v.id === playingVoiceId)?.name || 'Voice'}
              </span>
              <button
                type="button"
                onClick={handleStopAudio}
                data-testid="stop-voice-audio-btn"
                className="ml-1 p-0.5 rounded-control hover:bg-accent/20 text-accent"
                title="Stop audio"
              >
                <Square className="w-3.5 h-3.5 fill-current" />
              </button>
            </div>
          )}

        </div>
      </div>

      {audioError && (
        <div
          className="flex items-center gap-2 p-2.5 rounded-control bg-warning-soft text-warning-fg text-ui border border-warning-line"
          data-testid="voice-preview-error"
          role="alert"
        >
          <Info className="w-4 h-4 shrink-0 text-warning" />
          <span>{audioError}</span>
        </div>
      )}

      {/* 2. Speaking Voices Showcase: Dense Roster List Format */}
      <div
        className="p-4 rounded-card bg-surface border border-line shadow-craft-xs space-y-3"
        data-testid="speaking-voice-showcase"
      >
        {voiceCatalogError && (
          <p className="text-meta text-danger-fg bg-danger-soft border border-danger-line rounded-control px-3 py-2" role="alert">
            {voiceCatalogError}
          </p>
        )}
        {activeVoiceProvider === 'gemini' && ['hi-IN', 'te-IN'].includes(currentLanguage) && (
          <p
            className="text-meta text-warning-fg bg-warning-soft border border-warning-line rounded-control px-3 py-2"
            data-testid="voice-localization-note"
          >
            {currentLanguage === 'te-IN' ? 'Telugu voices include support, front-desk and technical styles.' : 'These Hindi voices are regional.'} Each voice shows its accent; play a sample before choosing.
          </p>
        )}
        {activeVoiceProvider === 'gemini' &&
          currentLanguage !== 'hi-IN' &&
          !phoneVoices.some(
            (voice) => voice.provider === 'gemini' && voice.languageCode === currentLanguage
          ) && (
            <p
              className="text-meta text-fg-muted bg-canvas border border-line rounded-control px-3 py-2"
              data-testid="voice-localization-note"
            >
              There is no regional voice for this language yet. The multilingual voice speaks the language you chose.
            </p>
          )}
        <div className="flex flex-wrap items-center justify-between gap-2 pb-2 border-b border-line">
          <div className="flex items-center gap-2">
            <Mic className="w-4 h-4 text-accent" />
            <span className="text-title text-ink">
              Speaking voices ({filteredVoices.length})
            </span>
            <button
              type="button"
              onClick={handleRefreshAllVoiceData}
              disabled={isRefreshingVoiceData || voiceCatalogLoading}
              className="flex items-center gap-1 px-2 py-0.5 min-h-[28px] text-meta font-medium text-fg-body hover:text-ink bg-surface hover:bg-canvas rounded-control border border-line transition-colors cursor-pointer ml-1 disabled:opacity-50"
              title="Refresh voices and samples"
              data-testid="refresh-speaking-voices-btn"
            >
              <RefreshCw className={`w-3 h-3 ${isRefreshingVoiceData || voiceCatalogLoading ? 'animate-spin' : ''}`} />
              <span>{isRefreshingVoiceData || voiceCatalogLoading ? 'Refreshing…' : 'Refresh'}</span>
            </button>
            <span className="text-meta text-fg-muted">
              Play to listen, then choose a voice
            </span>
          </div>

          {/* Compact Category & Gender Filters */}
          <div className="flex items-center gap-1.5 text-ui">
            <div className="flex rounded-control bg-canvas border border-line p-0.5">
              {[
                { id: 'all', label: `All (${voiceCategoryCounts.all})`, testId: 'voice-filter-all' },
                { id: 'conversational', aliases: ['support', 'care'], label: `Conversational (${voiceCategoryCounts.conversational})`, testId: 'voice-filter-conversational' },
                { id: 'promotional', aliases: ['sales', 'operations'], label: `Sales and promotions (${voiceCategoryCounts.promotional})`, testId: 'voice-filter-promotional' },
              ].map((c) => {
                const isActive = activeCategory === c.id || (c.aliases && c.aliases.includes(activeCategory));
                return (
                  <button
                    key={c.id}
                    type="button"
                    data-testid={c.testId}
                    onClick={() => setActiveCategory(c.id)}
                    className={`px-2 py-0.5 text-meta font-medium rounded-control transition-all ${
                      isActive
                        ? 'bg-ink text-white shadow-craft-xs'
                        : 'text-fg-body hover:text-ink'
                    }`}
                  >
                    {c.label}
                  </button>
                );
              })}
            </div>

            <div className="flex rounded-control bg-canvas border border-line p-0.5">
              {[
                { id: 'all', label: `All (${showcaseGenderCounts.all})` },
                { id: 'female', label: `Female (${showcaseGenderCounts.female})` },
                { id: 'male', label: `Male (${showcaseGenderCounts.male})` },
                { id: 'neutral', label: `Neutral (${showcaseGenderCounts.neutral})` },
              ].map((g) => (
                <button
                  key={g.id}
                  type="button"
                  data-testid={`voice-gender-${g.id}`}
                  onClick={() => setGenderFilter(g.id)}
                  className={`px-2 py-0.5 text-meta font-medium rounded-control transition-all ${
                    genderFilter === g.id
                      ? 'bg-accent text-white shadow-craft-xs'
                      : 'text-fg-body hover:text-ink'
                  }`}
                >
                  {g.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Dense Voice List / Table */}
        <div className="divide-y divide-line border border-line rounded-control overflow-hidden">
          {filteredVoices.map((voice) => {
            const isSelected = currentVoiceId === voice.id;
            const isPlayingThis = playingVoiceId === voice.id;

            return (
              <div
                key={voice.id}
                data-testid={`voice-card-${voice.id}`}
                onClick={() => handleSelectTierVoice({ tier: 'premium' }, voice)}
                className={`group flex items-center justify-between gap-3 px-3 py-2.5 transition-colors cursor-pointer select-none ${
                  isSelected
                    ? 'bg-accent-soft border-l-4 border-l-accent'
                    : 'bg-surface hover:bg-canvas'
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
                        ? 'bg-danger text-white shadow-craft-xs'
                        : 'bg-accent-soft text-accent hover:bg-accent hover:text-white'
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
                      <span className="w-0.5 h-3 bg-accent rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                      <span className="w-0.5 h-2 bg-accent rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                      <span className="w-0.5 h-3.5 bg-accent rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                    </div>
                  )}

                  {/* Name & Tone */}
                  <div className="min-w-0">
                    <div className="flex items-center gap-1.5">
                      <span className="text-ui font-semibold text-ink truncate" title={voice.name}>
                        {voice.name}
                      </span>
                      {voice.gender && (
                        <span className="px-1.5 rounded-pill text-meta font-medium bg-surface-subtle text-fg-body capitalize">
                          {voice.gender}
                        </span>
                      )}
                      {(voice.tag === 'Indian' || voice.accent?.includes('Indian') || voice.useCase?.includes('Indian') || voice.tone?.includes('Telugu') || voice.tone?.includes('Hindi')) && (
                        <span className="px-1.5 rounded-pill text-meta font-medium bg-neutral-soft text-neutral-fg border border-neutral-line">
                          🇮🇳 Indian
                        </span>
                      )}
                      <span className="px-1.5 rounded-pill text-meta font-medium bg-info-soft text-info-fg border border-info-line">
                        {formatCategory(voice.category) || 'General'}
                      </span>
                      {publicText(voice.tone) && (
                        <span className="hidden sm:inline-block text-meta font-medium text-fg-muted">
                          · {publicText(voice.tone)}
                        </span>
                      )}
                    </div>
                    <p className="text-meta text-fg-muted truncate max-w-xs md:max-w-md">
                      {voice.accent
                        ? `${voice.accent}${voice.languageCode ? ` · ${voice.languageCode}` : ''}`
                        : publicText(voice.useCase)}
                    </p>
                  </div>
                </div>

                {/* Right: Selection Action */}
                <div className="flex items-center gap-3 shrink-0">
                  <button
                    type="button"
                    data-testid={`voice-select-btn-${voice.id}`}
                    disabled={isSavingStackSelection || stackSelectionConflict}
                    onClick={(e) => {
                      e.stopPropagation();
                      handleSelectTierVoice({ tier: 'premium' }, voice);
                    }}
                    className={`flex items-center gap-1 px-3 py-1 min-h-[32px] text-ui font-medium rounded-control border transition-colors ${
                      isSelected
                        ? 'bg-ink text-white border-ink'
                        : 'bg-surface text-fg-body hover:text-ink hover:border-line-strong border-line'
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
        </>
      )}

      {/* 3. Acoustic Calibration & Speech Dynamics (Admin Only - Hidden for Tenants) */}
      {isAdmin && (
        <div
          className="p-4 rounded-card bg-surface border border-line shadow-craft-xs space-y-3"
          data-testid="acoustic-calibration-card"
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Sliders className="w-4 h-4 text-accent" />
              <span className="text-title text-ink">
                Speed and pitch
              </span>
            </div>

            <button
              type="button"
              onClick={() => setShowAcousticControls((v) => !v)}
              className="flex items-center gap-1 text-meta font-semibold text-accent hover:underline"
            >
              <span>{showAcousticControls ? 'Hide controls' : 'Adjust speed and pitch'}</span>
              <ChevronDown className={`w-3.5 h-3.5 transition-transform ${showAcousticControls ? 'rotate-180' : ''}`} />
            </button>
          </div>

          {/* Speed Slider always available or expanded */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-1">
            {/* Speaking Pace */}
            <div className="space-y-1.5">
              <div className="flex items-center justify-between text-ui">
                <span className="font-semibold text-ink">Speaking speed</span>
                <span className="font-mono font-medium text-accent text-meta">
                  {Number(currentSpeed || 1.0).toFixed(2)}x
                </span>
              </div>
              <input
                type="range"
                min="0.5"
                max="2.0"
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
                className="w-full h-1.5 bg-line rounded-control appearance-none cursor-pointer accent-accent"
              />
              <div className="flex justify-between text-meta text-fg-muted">
                <span>0.5x (Slow)</span>
                <span className="font-semibold text-accent">1.0x (Industry Standard)</span>
                <span>2.0x (Fast)</span>
              </div>
            </div>

            {/* Quick Presets */}
            <div className="space-y-1.5">
              <span className="text-ui font-semibold text-ink block">
                Quick settings
              </span>
              <div className="flex items-center gap-1.5">
                {[
                  { label: 'Standard (1.0x)', speed: 1.0 },
                  { label: 'Slower, for support (0.9x)', speed: 0.9 },
                  { label: 'Faster, for sales (1.1x)', speed: 1.1 },
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
                        },
                      }));
                    }}
                    className={`px-2.5 py-1 rounded-control text-meta font-medium border transition-all ${
                      Math.abs(currentSpeed - p.speed) < 0.01
                        ? 'bg-accent text-white border-accent'
                        : 'bg-canvas text-fg-body border-line hover:bg-surface'
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
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2 border-t border-line">
              {/* Pitch Offset - Disabled because providers manage pitch natively */}
              <div className="space-y-1.5 opacity-80">
                <div className="flex items-center justify-between text-ui">
                  <span className="font-semibold text-ink">Pitch</span>
                  <span className="font-mono text-fg-muted text-meta">
                    0.00 (Neutral)
                  </span>
                </div>
                <input
                  type="range"
                  min="-0.15"
                  max="0.15"
                  step="0.05"
                  value={0}
                  disabled
                  className="w-full h-1.5 bg-line rounded-control appearance-none cursor-not-allowed opacity-50"
                />
                <p className="text-meta text-fg-muted italic">
                  Managed natively by provider voice persona (Not supported by provider API).
                </p>
              </div>

              {/* Stability - Disabled because providers manage prosody natively */}
              <div className="space-y-1.5 opacity-80">
                <div className="flex items-center justify-between text-ui">
                  <span className="font-semibold text-ink">Steadiness</span>
                  <span className="font-mono text-fg-muted text-meta">
                    0.75 (Balanced Natural)
                  </span>
                </div>
                <input
                  type="range"
                  min="0.3"
                  max="1.0"
                  step="0.05"
                  value={0.75}
                  disabled
                  className="w-full h-1.5 bg-line rounded-control appearance-none cursor-not-allowed opacity-50"
                />
                <p className="text-meta text-fg-muted italic">
                  Native acoustic model control (Not supported by provider API).
                </p>
              </div>
            </div>
          )}
        </div>
      )}


    </div>
  );
}

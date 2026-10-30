import React, { useCallback, useMemo, useState, useEffect, useRef } from 'react';
import {
  FileCode2,
  Volume2,
  Play,
  Square,
  Plus,
  Trash2,
  CheckCircle2,
  Radio,
  ArrowLeft,
  LayoutDashboard,
  History,
  Settings,
  Eye,
  EyeOff,
  Sparkles,
  ChevronDown,
} from 'lucide-react';
import { AgentTestCallPanel } from './agent-workspace/AgentTestCallPanel';
import { SolidCard } from '../ui/SolidCard';
import { StatusBadge } from '../ui/StatusBadge';
import { TactileButton } from '../ui/TactileButton';
import { Modal } from '../ui/Modal';
import { AgentStudioHeaderSkeleton, AgentStudioEditorSkeleton, WaveformSkeleton } from '../ui/Skeleton';
import { useWorkspace } from '../context/WorkspaceContext';
import { voiceAgent } from '../../services/voiceAgent';
import { LANGUAGE_OPTIONS } from '../../lib/voicePresets';
import { PHONE_STACK_LABEL } from '../../lib/phoneLabels';
import {
  fetchPhoneVoiceOptions,
  parseStudioFieldsFromSections,
  parseVoiceConfigFromSections,
} from '../../lib/voiceStack';
import {
  OBJECTION_PRESETS,
  SAMPLE_LEADS,
  filterScriptVariables,
  findScriptVariableTrigger,
  getScriptVariableGroups,
  replaceScriptVariableTrigger,
  renderScriptPreview,
} from '../../lib/studioScriptHelpers';
import { formatPhoneVoiceLabel, groupVoicesByTier } from '../../lib/voiceDisplay';
import { loadAgentBrain, reviewAgentBrain } from '../../services/agentBrain';
import { api } from '../../services/api';
import { normalizeAgent } from '../../services/apiNormalize';
import { AgentOverview } from './agent-workspace/AgentOverview';
import { AgentCallsPanel } from './agent-workspace/AgentCallsPanel';
import { AgentSettingsPanel } from './agent-workspace/AgentSettingsPanel';
import { AgentVoicePanel } from './agent-workspace/AgentVoicePanel';
import { AgentSaveDock } from './agent-workspace/AgentSaveDock';
import { ErrorBoundary } from '../ui/ErrorBoundary';
import { resolveEmployeeStep } from '../employeeFlowHash';

/**
 * Canonical text for the dirty check, and the payload "Discard" restores.
 *
 * These are the same thing on purpose. They used to be a hand-picked subset,
 * which meant Discard restored a form with `objectionRules`, `boundaries`,
 * `dynamicVariables` and `inboundRouting` missing — the editor then crashed on
 * the next `.map`, and a rejected edit silently erased the caller's rules.
 *
 * Snapshot and form are therefore built from one field list, so they cannot
 * drift apart again: adding an editor field to `formFromAgent` without adding it
 * here is the only way to reintroduce the bug, and it now fails visibly.
 */
/** Extract the greeting / opening phrase from a script text if present. */
export function extractGreetingFromScript(scriptText) {
  if (!scriptText || !scriptText.trim()) return null;

  // 1. Matches "--- CANONICAL OPENING ---" section
  const canonicalMatch = scriptText.match(
    /(?:^|\n)(?:---|##)\s*CANONICAL OPENING\s*(?:---|##)?\s*\n+([\s\S]*?)(?=(?:\n+---|(?:\n+##)|$))/i
  );
  if (canonicalMatch && canonicalMatch[1]) {
    const body = canonicalMatch[1].trim();
    const leadMatch = body.match(
      /^(?:After the callee speaks, say once:|When you answer, say once:|Say once:|Say:|Example opening:)\s*\n*([\s\S]+)/i
    );
    if (leadMatch && leadMatch[1]) {
      return leadMatch[1].trim();
    }
    return body;
  }

  // 2. Matches "--- OPENING ---" or "--- OPENING HINT ---"
  const openingHintMatch = scriptText.match(
    /(?:^|\n)(?:---|##)\s*OPENING(?: HINT)?\s*(?:---|##)?\s*\n+([\s\S]*?)(?=(?:\n+---|(?:\n+##)|$))/i
  );
  if (openingHintMatch && openingHintMatch[1]) {
    const body = openingHintMatch[1].trim();
    const leadMatch = body.match(
      /^(?:After the callee speaks, say once:|When you answer, say once:|Say once:|Say:|Example opening:)\s*\n*([\s\S]+)/i
    );
    if (leadMatch && leadMatch[1]) {
      return leadMatch[1].trim();
    }
    return body;
  }

  return null;
}

/** Synchronize greeting into calling script text so both stay connected without clashes. */
export function syncGreetingToScript(currentScript, newGreeting) {
  const gTrim = (newGreeting || '').trim();
  const rawClean = (currentScript || '').replace(/^OPENING LINE\s*\n[^\n]*\n*/im, '').trim();
  if (!rawClean) {
    return gTrim ? `--- CANONICAL OPENING ---\nAfter the callee speaks, say once:\n${gTrim}` : '';
  }

  // 1. If "--- CANONICAL OPENING ---" exists, replace its body while preserving or inserting lead instruction
  const canonicalRegex = /((?:^|\n)(?:---|##)\s*CANONICAL OPENING\s*(?:---|##)?\s*\n+)([\s\S]*?)(?=(?:\n+---|\n+##|$))/i;
  if (canonicalRegex.test(rawClean)) {
    return rawClean.replace(canonicalRegex, (_match, header, body) => {
      const leadMatch = body.match(
        /^(After the callee speaks, say once:|When you answer, say once:|Say once:|Say:|Example opening:)/im
      );
      const lead = leadMatch ? leadMatch[1] : 'After the callee speaks, say once:';
      return `${header}${lead}\n${gTrim}`;
    });
  }

  // 2. If "--- OPENING ---" or "--- OPENING HINT ---" exists, upgrade it to CANONICAL OPENING
  const openingHintRegex = /((?:^|\n)(?:---|##)\s*OPENING(?: HINT)?\s*(?:---|##)?\s*\n+)([\s\S]*?)(?=(?:\n+---|\n+##|$))/i;
  if (openingHintRegex.test(rawClean)) {
    return rawClean.replace(openingHintRegex, (_match, _header, body) => {
      const leadMatch = body.match(
        /^(After the callee speaks, say once:|When you answer, say once:|Say once:|Say:|Example opening:)/im
      );
      const lead = leadMatch ? leadMatch[1] : 'After the callee speaks, say once:';
      return `\n--- CANONICAL OPENING ---\n${lead}\n${gTrim}`;
    });
  }

  // 3. Prepend CANONICAL OPENING to script cleanly
  if (gTrim) {
    return `--- CANONICAL OPENING ---\nAfter the callee speaks, say once:\n${gTrim}\n\n${rawClean}`;
  }
  return rawClean;
}

const EDITABLE_FIELDS = [
  'name',
  'role',
  'greeting',
  'farewell',
  'script',
  'language',
  'dynamicVariables',
  'objectionRules',
  'boundaries',
  'variableDefinitions',
  'voice',
  'inboundRouting',
];

/**
 * Reduce a form to just the editable fields, with every collection normalised to
 * an array. The normalisation is not cosmetic: a restored snapshot that lacks a
 * key would leave `undefined` in place of a list, and the first `.map` over it
 * would throw and take the whole workspace down.
 */
function editableSubset(form) {
  const out = {};
  for (const key of EDITABLE_FIELDS) {
    const value = form?.[key];
    if (Array.isArray(value)) {
      out[key] = value;
    } else if (value && typeof value === 'object') {
      out[key] = value;
    } else {
      out[key] = value ?? '';
    }
  }
  return out;
}

function snapForm(form) {
  if (!form) return JSON.stringify(editableSubset(EMPTY_FORM));
  return JSON.stringify(editableSubset(form));
}

/** Turn a stored snapshot back into a complete, renderable form. */
function formFromSnapshot(snapshot) {
  const parsed = JSON.parse(snapshot || '{}');
  return {
    ...editableSubset(parsed),
    // Never inherit a malformed list from an older or hand-edited snapshot.
    dynamicVariables: Array.isArray(parsed.dynamicVariables) ? parsed.dynamicVariables : [],
    objectionRules: Array.isArray(parsed.objectionRules) ? parsed.objectionRules : [],
    boundaries: Array.isArray(parsed.boundaries) ? parsed.boundaries : [],
    variableDefinitions: Array.isArray(parsed.variableDefinitions)
      ? parsed.variableDefinitions
      : [],
  };
}

/** The five workspace tabs. Test call is a header button, not a tab. */
const FLOW_TABS = [
  { id: 'overview', label: 'Overview', icon: LayoutDashboard },
  { id: 'script', label: 'Script', icon: FileCode2 },
  { id: 'calls', label: 'Calls', icon: History },
  { id: 'voice', label: 'Voice', icon: Volume2 },
  { id: 'settings', label: 'Settings', icon: Settings },
];

const EMPTY_FORM = {
  name: '',
  role: 'Sales',
  greeting: '',
  script: '',
  dynamicVariables: [],
  objectionRules: [],
  boundaries: [],
  variableDefinitions: [],
  voice: { speed: 1, pitch: 0, voiceName: 'Puck', voiceId: 'Puck', realtimeVoice: 'Puck', provider: 'gemini' },
  language: 'en-IN',
  inboundRouting: {
    businessHours: '',
    afterHoursAction: 'voicemail',
    greetingPhrase: '',
  },
};

const VOICE_STACK_SAVE_ERRORS = {
  profile_revision_conflict: 'Voice options changed. Choose a voice from the refreshed catalog and try again.',
  voice_selection_invalid: 'That voice is no longer available for this language. Choose from the refreshed catalog.',
  unsupported_language: 'This tier does not support the selected language. Choose a supported language or another tier.',
  profile_unavailable: 'This voice tier is currently unavailable. Choose another ready tier or try again later.',
  invalid_composed_tier: 'This voice tier could not be applied. Reload voice options and try again.',
  premium_composed_settings_forbidden: 'This live voice setup is out of date. Reload this page and choose the voice again.',
  voice_selection_incomplete: 'Choose a complete voice option from the current catalog before saving.',
  voice_revision_required: 'Reload the saved voice settings before choosing another voice.',
  durable_store_unavailable: 'Voice settings cannot be saved right now. Your saved choice is unchanged. Try again later.',
};

function formFromAgent(agent) {
  if (!agent) return { ...EMPTY_FORM };
  const rawVoice = agent.voice || agent.voice_settings || agent.voiceSettings || {};
  const voiceId = rawVoice.voiceId || rawVoice.realtimeVoice || 'Puck';
  const realtimeVoice = rawVoice.realtimeVoice || rawVoice.voiceId || 'Puck';
  const lang = (agent.languages && agent.languages[0]) || agent.language || rawVoice.language || 'en-IN';
  return {
    ...editableSubset({
      name: agent.name || '',
      role: agent.role || 'Sales',
      greeting: agent.greeting || '',
      farewell: agent.farewell || '',
      script: agent.script || '',
      dynamicVariables: agent.dynamicVariables || [],
      objectionRules: agent.objectionRules || [],
      boundaries: agent.boundaries || [],
      variableDefinitions: agent.variableDefinitions || [],
      voice: {
        ...EMPTY_FORM.voice,
        ...rawVoice,
        voiceId,
        realtimeVoice,
        voiceName: rawVoice.voiceName || 'Puck',
        speed: rawVoice.speed ?? 1,
      },
      language: lang,
      inboundRouting: agent.inboundRouting || {
        businessHours: '',
        afterHoursAction: 'voicemail',
        greetingPhrase: agent.greeting || '',
      },
    }),
  };
}

export { OBJECTION_PRESETS, SAMPLE_LEADS, renderScriptPreview };

export function AgentStudioModule({
  onNavigate,
  onOpenBuyNumber,
  flowStep,
  onFlowStepChange,
  onBackToFleet,
}) {
  const {
    agents,
    isLoading,
    selectedAgentId,
    setSelectedAgentId,
    selectedAgent,
    updateAgent,
    updateAgentInWorkspace,
  } = useWorkspace();
  const voiceLanguage =
    (Array.isArray(selectedAgent?.languages) ? selectedAgent.languages[0] : null) ||
    selectedAgent?.language ||
    'te-IN';

  const [activeTab, setActiveTab] = useState(() => resolveEmployeeStep(flowStep).step);
  const [callPanel, setCallPanel] = useState(() => resolveEmployeeStep(flowStep).callPanel || 'history');
  const [testCallOpen, setTestCallOpen] = useState(() => Boolean(resolveEmployeeStep(flowStep).openTestCall));
  const [voiceStackReady, setVoiceStackReady] = useState(true);
  // Reset before the voice panel's passive validation effect. Resetting here
  // with useEffect used to overwrite the child's initial "not ready" verdict.
  React.useLayoutEffect(() => { setVoiceStackReady(true); }, [selectedAgentId]);
  // The Test call modal is a header action, so closing it must return focus to the
  // button that opened it rather than dropping the user back at the top of the page.
  const testCallButtonRef = useRef(null);
  const [phoneVoices, setPhoneVoices] = useState([]);
  const [activeVoiceProvider, setActiveVoiceProvider] = useState('gemini');
  const [defaultVoiceId, setDefaultVoiceId] = useState('Puck');
  const [voiceCatalogError, setVoiceCatalogError] = useState(null);
  const [voiceCatalogLoading, setVoiceCatalogLoading] = useState(true);
  const [stackLabel, setStackLabel] = useState(PHONE_STACK_LABEL);
  const voiceCatalogRefreshRef = useRef(null);
  const [voiceStackProfiles, setVoiceStackProfiles] = useState([]);
  const [voiceStackCatalogLoading, setVoiceStackCatalogLoading] = useState(false);
  const [voiceStackCatalogError, setVoiceStackCatalogError] = useState(null);
  const [voiceStackSavedAgents, setVoiceStackSavedAgents] = useState({});
  const voiceStackCatalogRequestRef = useRef(0);
  const voiceStackCatalogFlightRef = useRef(null);

  useEffect(() => {
    let mounted = true;
    let requestId = 0;
    const refreshVoiceCatalog = () => {
      const currentRequest = ++requestId;
      setVoiceCatalogLoading(true);
      return fetchPhoneVoiceOptions(voiceLanguage)
        .then((o) => {
          if (!mounted || currentRequest !== requestId) return;
          setPhoneVoices(o.voices || []);
          setActiveVoiceProvider(o.activeVoiceProvider || 'gemini');
          setDefaultVoiceId(o.defaultVoiceId || 'te-in-csagent-5');
          setStackLabel(o.stackLabel || PHONE_STACK_LABEL);
          setVoiceCatalogError(null);
          return { error: false };
        })
        .catch((error) => {
          if (!mounted || currentRequest !== requestId) return;
          setVoiceCatalogError('Current voice options could not be loaded. Try again.');
          return { error: true };
        })
        .finally(() => {
          if (mounted && currentRequest === requestId) setVoiceCatalogLoading(false);
        });
    };
    voiceCatalogRefreshRef.current = refreshVoiceCatalog;
    refreshVoiceCatalog();
    // Voice options change rarely and depend only on the language: refresh in the
    // background every 5 minutes while visible, and when the user comes back.
    const refreshIfVisible = () => {
      if (document.visibilityState === 'visible') refreshVoiceCatalog();
    };
    const interval = window.setInterval(refreshIfVisible, 300_000);
    window.addEventListener('focus', refreshIfVisible);
    document.addEventListener('visibilitychange', refreshIfVisible);
    return () => {
      mounted = false;
      if (voiceCatalogRefreshRef.current === refreshVoiceCatalog) {
        voiceCatalogRefreshRef.current = null;
      }
      window.clearInterval(interval);
      window.removeEventListener('focus', refreshIfVisible);
      document.removeEventListener('visibilitychange', refreshIfVisible);
    };
  }, [voiceLanguage]);

  const retryVoiceCatalog = useCallback(() => {
    return voiceCatalogRefreshRef.current?.();
  }, []);

  // A legacy ?step=telephony or ?step=test link resolves here on first mount and on
  // every later hash change, so old bookmarks still land somewhere useful.
  useEffect(() => {
    if (!flowStep) return;
    const next = resolveEmployeeStep(flowStep);
    setActiveTab(next.step);
    if (next.callPanel) setCallPanel(next.callPanel);
    if (next.openTestCall) setTestCallOpen(true);
  }, [flowStep]);

  const [isSaved, setIsSaved] = useState(false);
  const [isPlayingVoice, setIsPlayingVoice] = useState(false);
  const [isBufferingVoice, setIsBufferingVoice] = useState(false);
  const [voicePreviewError, setVoicePreviewError] = useState(null);
  // Which voice actually spoke, so the operator knows this is the real one.
  const [voiceSpoken, setVoiceSpoken] = useState({ voice: null, model: null });
  const [brainLoadError, setBrainLoadError] = useState(null);
  const [brainLoading, setBrainLoading] = useState(false);
  const [brainLoadAttempt, setBrainLoadAttempt] = useState(0);
  const [publishedVersion, setPublishedVersion] = useState(null);
  const [generationReport, setGenerationReport] = useState(null);
  const [variablePickerOpen, setVariablePickerOpen] = useState(false);
  const [useFallbackSyntax, setUseFallbackSyntax] = useState(true);
  const [variableSuggestionTrigger, setVariableSuggestionTrigger] = useState(null);
  const [variableSuggestionTop, setVariableSuggestionTop] = useState(0);
  const [selectedVariableSuggestion, setSelectedVariableSuggestion] = useState(0);
  const [scriptPreviewMode, setScriptPreviewMode] = useState(false);
  const [sampleLeadIdx, setSampleLeadIdx] = useState(0);
  const scriptTextareaRef = useRef(null);
  const workspaceContainerRef = useRef(null);
  const scriptVariableGroups = useMemo(() => getScriptVariableGroups(useFallbackSyntax), [useFallbackSyntax]);
  const variableSuggestions = useMemo(
    () => variableSuggestionTrigger
      ? filterScriptVariables(scriptVariableGroups, variableSuggestionTrigger.query)
      : [],
    [scriptVariableGroups, variableSuggestionTrigger],
  );

  const [formData, setFormData] = useState(() => formFromAgent(selectedAgent));
  // Size to the complete document, including wrapped lines after a sidebar/viewport resize.
  React.useLayoutEffect(() => {
    const editor = scriptTextareaRef.current;
    if (!editor) return;
    let lastWidth = 0;
    const fit = () => {
      if (!editor.clientWidth) return;
      editor.style.height = 'auto';
      editor.style.height = `${editor.scrollHeight + 2}px`;
    };
    fit();
    const observer = new ResizeObserver(() => {
      if (editor.clientWidth !== lastWidth) { lastWidth = editor.clientWidth; fit(); }
    });
    observer.observe(editor);
    return () => observer.disconnect();
  }, [formData.script, activeTab, scriptPreviewMode, brainLoading]);

  const savedVoiceStackAgent = selectedAgent?.id ? voiceStackSavedAgents[selectedAgent.id] : null;
  const voiceStackAgent = savedVoiceStackAgent &&
    (savedVoiceStackAgent.voiceRevision ?? 0) >= (selectedAgent?.voiceRevision ?? 0)
    ? {
        ...selectedAgent,
        defaultTier: savedVoiceStackAgent.defaultTier,
        voiceSettings: savedVoiceStackAgent.voiceSettings,
        voiceRevision: savedVoiceStackAgent.voiceRevision,
        languages: savedVoiceStackAgent.languages || selectedAgent.languages,
      }
    : selectedAgent;

  const voiceStackLanguage =
    formData?.language ||
    (Array.isArray(formData?.languages) ? formData.languages[0] : null) ||
    voiceLanguage;

  const refreshVoiceStackCatalog = useCallback(({ background = false } = {}) => {
    const flight = voiceStackCatalogFlightRef.current;
    if (flight?.language === voiceStackLanguage) return flight.promise;
    const requestId = ++voiceStackCatalogRequestRef.current;
    if (!background) setVoiceStackCatalogLoading(true);
    const promise = (async () => { try {
      const result = await api.request(
        'GET',
        `/api/voice-stacks/catalog?language=${encodeURIComponent(voiceStackLanguage)}`,
        null, {}, { timeoutMs: 15_000 }
      );
      if (requestId !== voiceStackCatalogRequestRef.current) return;
      setVoiceStackProfiles(Array.isArray(result?.profiles) ? result.profiles : []);
      setVoiceStackCatalogError(null);
      return { error: false };
    } catch {
      if (requestId === voiceStackCatalogRequestRef.current) {
        setVoiceStackCatalogError('Approved voice options could not be loaded. Try again.');
      }
      return { error: true };
    } finally {
      if (requestId === voiceStackCatalogRequestRef.current) {
        setVoiceStackCatalogLoading(false);
        voiceStackCatalogFlightRef.current = null;
      }
    } })();
    voiceStackCatalogFlightRef.current = { language: voiceStackLanguage, promise };
    return promise;
  }, [voiceStackLanguage]);

  useEffect(() => {
    setVoiceStackProfiles([]);
    refreshVoiceStackCatalog();
    const refresh = () => {
      if (document.visibilityState === 'visible') refreshVoiceStackCatalog({ background: true });
    };
    // The catalog depends only on the language (refreshVoiceStackCatalog's dep).
    const interval = window.setInterval(refresh, 300_000);
    window.addEventListener('focus', refresh);
    document.addEventListener('visibilitychange', refresh);
    return () => {
      window.clearInterval(interval);
      window.removeEventListener('focus', refresh);
      document.removeEventListener('visibilitychange', refresh);
      ++voiceStackCatalogRequestRef.current;
      voiceStackCatalogFlightRef.current = null;
    };
  }, [refreshVoiceStackCatalog]);

  const saveVoiceStackSelection = useCallback(async (selection) => {
    if (!voiceStackAgent?.id) return { error: true };

    const persistedLanguage =
      (Array.isArray(voiceStackAgent.languages) ? voiceStackAgent.languages[0] : null) ||
      voiceStackAgent.language ||
      'en-IN';

    const expectedVoiceRevision = Number.isSafeInteger(voiceStackAgent.voiceRevision)
      ? voiceStackAgent.voiceRevision
      : Number.isSafeInteger(voiceStackAgent.voice_revision)
        ? voiceStackAgent.voice_revision
        : 0;
    const voiceSettings = { stackSelectionVersion: 1 };
    if (selection.tier === 'premium' && !selection.engineId) {
      if (selection.realtimeVoice) voiceSettings.realtimeVoice = selection.realtimeVoice;
    } else {
      voiceSettings.profileRevision = selection.profileRevision;
      voiceSettings.engineId = selection.engineId;
      voiceSettings.modelId = selection.modelId;
      voiceSettings.voiceId = selection.voiceId;
    }

    try {
      const patchPayload = {
        defaultTier: selection.tier,
        expectedVoiceRevision,
        voiceSettings,
      };
      if (voiceStackLanguage && voiceStackLanguage !== persistedLanguage) {
        patchPayload.languages = [voiceStackLanguage];
      }
      const response = await api.request('PATCH', `/api/agents/${voiceStackAgent.id}`, patchPayload);
      const responseAgent = response?.agent || response;
      const normalizedResponse = normalizeAgent(responseAgent);
      const isPremium = selection.tier === 'premium' && !selection.engineId;
      const responseIsComplete =
        normalizedResponse?.defaultTier === selection.tier &&
        normalizedResponse?.voiceSettings?.stackSelectionVersion === 1 &&
        normalizedResponse.languages?.[0] === voiceStackLanguage &&
        (isPremium ? (
          !selection.realtimeVoice || normalizedResponse.voiceSettings.realtimeVoice === selection.realtimeVoice
        ) : (
          normalizedResponse?.voiceSettings?.engineId === selection.engineId &&
          normalizedResponse?.voiceSettings?.modelId === selection.modelId &&
          normalizedResponse?.voiceSettings?.voiceId === selection.voiceId &&
          normalizedResponse?.voiceSettings?.profileRevision === selection.profileRevision
        )) &&
        Number.isSafeInteger(normalizedResponse?.voiceRevision) &&
        normalizedResponse.voiceRevision > expectedVoiceRevision;
      const savedAgent = responseIsComplete
        ? {
            ...voiceStackAgent,
            ...(Array.isArray(responseAgent?.languages)
              ? { languages: normalizedResponse.languages }
              : {}),
            defaultTier: normalizedResponse.defaultTier,
            voiceSettings: normalizedResponse.voiceSettings,
            voiceRevision: normalizedResponse.voiceRevision,
          }
        : await api.agents.get(voiceStackAgent.id);
      if (
        !savedAgent ||
        savedAgent.defaultTier !== selection.tier ||
        savedAgent.voiceSettings?.stackSelectionVersion !== 1 ||
        savedAgent.languages?.[0] !== voiceStackLanguage ||
        (isPremium ? (
          selection.realtimeVoice && savedAgent.voiceSettings?.realtimeVoice !== selection.realtimeVoice
        ) : (
          savedAgent.voiceSettings?.engineId !== selection.engineId ||
          savedAgent.voiceSettings?.modelId !== selection.modelId ||
          savedAgent.voiceSettings?.voiceId !== selection.voiceId ||
          savedAgent.voiceSettings?.profileRevision !== selection.profileRevision
        )) ||
        !Number.isSafeInteger(savedAgent.voiceRevision) ||
        savedAgent.voiceRevision <= expectedVoiceRevision
      ) {
        return { savedButUnconfirmed: true };
      }
      setVoiceStackSavedAgents((current) => ({ ...current, [voiceStackAgent.id]: savedAgent }));
      updateAgentInWorkspace?.(savedAgent);
      return { agent: savedAgent };
    } catch (error) {
      if (error?.code === 'voice_revision_conflict') {
        try {
          const latest = await api.agents.get(voiceStackAgent.id);
          setVoiceStackSavedAgents((current) => ({ ...current, [voiceStackAgent.id]: latest }));
          updateAgentInWorkspace?.(latest);

          // If the server voice selection itself hasn't changed (counter bumped due to script/meta updates),
          // auto-retry once with the latest revision so the user's choice applies cleanly.
          const currentVoiceId = voiceStackAgent.defaultTier === 'premium'
            ? voiceStackAgent.voiceSettings?.realtimeVoice
            : voiceStackAgent.voiceSettings?.voiceId;
          const serverVoiceId = latest.defaultTier === 'premium'
            ? latest.voiceSettings?.realtimeVoice
            : latest.voiceSettings?.voiceId;
          const voiceUnchangedByOther =
            latest.defaultTier === voiceStackAgent.defaultTier &&
            currentVoiceId === serverVoiceId;

          if (voiceUnchangedByOther && Number.isSafeInteger(latest.voiceRevision)) {
            try {
              const retryPayload = {
                defaultTier: selection.tier,
                expectedVoiceRevision: latest.voiceRevision,
                voiceSettings,
              };
              if (voiceStackLanguage && voiceStackLanguage !== persistedLanguage) {
                retryPayload.languages = [voiceStackLanguage];
              }
              const retryRes = await api.request('PATCH', `/api/agents/${voiceStackAgent.id}`, retryPayload);
              const retryAgent = normalizeAgent(retryRes?.agent || retryRes);
              setVoiceStackSavedAgents((current) => ({ ...current, [voiceStackAgent.id]: retryAgent }));
              updateAgentInWorkspace?.(retryAgent);
              return { agent: retryAgent };
            } catch {
              // Retry failed; fall through to conflict
            }
          }
          return { conflict: true, agent: latest };
        } catch {
          return { conflict: true };
        }
      }
      if (['profile_revision_conflict', 'voice_selection_invalid', 'unsupported_language', 'profile_unavailable'].includes(error?.code)) {
        await refreshVoiceStackCatalog();
      }
      return {
        error: VOICE_STACK_SAVE_ERRORS[error?.code] || 'Voice setup could not be saved. Your saved choice is unchanged. Try again.',
        code: error?.code,
      };
    }
  }, [voiceStackAgent, voiceStackLanguage, refreshVoiceStackCatalog, updateAgentInWorkspace]);

  const reloadVoiceStackSettings = useCallback(async () => {
    if (!selectedAgent?.id) return null;
    try {
      const latest = await api.agents.get(selectedAgent.id);
      setVoiceStackSavedAgents((current) => ({ ...current, [selectedAgent.id]: latest }));
      updateAgentInWorkspace?.(latest);
      return latest;
    } catch {
      return null;
    }
  }, [selectedAgent?.id, updateAgentInWorkspace]);

  // Settings panel dirty state & save/discard ref callbacks
  const [settingsDirty, setSettingsDirty] = useState(false);
  const settingsSaveRef = useRef(null);
  const settingsDiscardRef = useRef(null);

  const insertVariable = (token) => {
    setVariableSuggestionTrigger(null);
    const el = scriptTextareaRef.current;
    if (el) {
      const start = el.selectionStart ?? el.value.length;
      const end = el.selectionEnd ?? el.value.length;
      const current = el.value || '';
      const nextScript = current.substring(0, start) + token + current.substring(end);
      handleScriptChange(nextScript);
      requestAnimationFrame(() => {
        if (el) {
          el.focus();
          const newPos = start + token.length;
          el.setSelectionRange(newPos, newPos);
        }
      });
    } else {
      setFormData((prev) => {
        const next = prev.script ? `${prev.script} ${token}` : token;
        handleScriptChange(next);
        return { ...prev, script: next };
      });
    }
  };

  const updateVariableSuggestion = (element) => {
    if (!element) return;
    const trigger = findScriptVariableTrigger(element.value, element.selectionStart);
    if (trigger) {
      // A paper-height editor can extend well beyond the viewport. Anchor its
      // autocomplete near the caret instead of below the entire document.
      const mirror = document.createElement('div');
      const style = getComputedStyle(element);
      for (const property of ['font', 'lineHeight', 'letterSpacing', 'wordSpacing', 'padding', 'textIndent', 'tabSize', 'direction']) {
        mirror.style[property] = style[property];
      }
      Object.assign(mirror.style, { position: 'fixed', left: '-100000px', top: '0', visibility: 'hidden',
        width: `${element.clientWidth}px`, boxSizing: 'border-box', whiteSpace: 'pre-wrap', overflowWrap: 'break-word' });
      mirror.textContent = element.value.slice(0, element.selectionStart);
      const caret = document.createElement('span');
      caret.textContent = '\u200b';
      mirror.append(caret);
      document.body.append(mirror);
      const caretTop = caret.offsetTop + (parseFloat(style.lineHeight) || 28);
      const dockHeight = parseFloat(workspaceContainerRef.current?.style.getPropertyValue('--agent-save-dock-height')) || 90;
      const visibleTop = window.innerHeight - element.getBoundingClientRect().top - 240 - dockHeight;
      setVariableSuggestionTop(Math.max(0, Math.min(caretTop, visibleTop)));
      mirror.remove();
    }
    setVariableSuggestionTrigger(trigger);
    setSelectedVariableSuggestion(0);
  };

  const selectVariableSuggestion = (variable) => {
    const element = scriptTextareaRef.current;
    const trigger = variableSuggestionTrigger;
    if (!element || !trigger || !variable) return;
    const next = replaceScriptVariableTrigger(element.value, trigger, variable);
    handleScriptChange(next.text);
    setVariableSuggestionTrigger(null);
    requestAnimationFrame(() => {
      element.focus();
      element.setSelectionRange(next.cursor, next.cursor);
    });
  };

  const handleScriptEditorKeyDown = (event) => {
    if (!variableSuggestionTrigger) return;
    if (event.key === 'Escape') {
      event.preventDefault();
      setVariableSuggestionTrigger(null);
      return;
    }
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      if (!variableSuggestions.length) return;
      event.preventDefault();
      const direction = event.key === 'ArrowDown' ? 1 : -1;
      setSelectedVariableSuggestion((index) =>
        (index + direction + variableSuggestions.length) % variableSuggestions.length,
      );
      return;
    }
    if ((event.key === 'Enter' || event.key === 'Tab') && variableSuggestions.length) {
      event.preventDefault();
      selectVariableSuggestion(variableSuggestions[selectedVariableSuggestion]);
    }
  };

  // Universal synchronization between "Greeting the caller hears" and Calling script & telephony routing
  const handleGreetingChange = (newGreeting) => {
    setFormData((prev) => ({
      ...prev,
      greeting: newGreeting,
      script: syncGreetingToScript(prev.script, newGreeting),
      inboundRouting: {
        ...(prev.inboundRouting || {}),
        greetingPhrase: newGreeting,
      },
    }));
  };

  const handleScriptChange = (newScript) => {
    const extracted = extractGreetingFromScript(newScript);
    setFormData((prev) => {
      const resolvedGreeting = extracted !== null ? extracted : prev.greeting;
      return {
        ...prev,
        script: newScript,
        greeting: resolvedGreeting,
        inboundRouting: {
          ...(prev.inboundRouting || {}),
          greetingPhrase: resolvedGreeting,
        },
      };
    });
  };

  // The last-loaded (saved) state. Dirty = formData differs from this, or settings tab has unsaved changes.
  const [savedSnapshot, setSavedSnapshot] = useState(() => snapForm(formData));
  const [pendingLeave, setPendingLeave] = useState(null);
  const scriptDirty = snapForm(formData) !== savedSnapshot;
  const dirty = scriptDirty || settingsDirty;

  const confirmLeave = useCallback(
    () => (dirty ? new Promise((resolve) => setPendingLeave(() => resolve)) : Promise.resolve(true)),
    [dirty]
  );

  const settleLeave = useCallback((ok) => {
    setPendingLeave((prev) => {
      if (typeof prev === 'function') prev(ok);
      return null;
    });
  }, []);

  const discardChanges = useCallback(() => {
    setSaveError(null);
    if (scriptDirty) {
      setFormData(formFromSnapshot(savedSnapshot));
      setSaveError(null);
      setIsSaved(false);
    }
    if (settingsDirty && settingsDiscardRef.current) {
      settingsDiscardRef.current();
    }
  }, [scriptDirty, savedSnapshot, settingsDirty]);

  const handleSettingsSaved = useCallback((savedData) => {
    setFormData((prev) => {
      const incomingGreeting =
        savedData.greeting ??
        savedData.greetingPhrase ??
        savedData.telephonyProfile?.greetingPhrase;
      const nextGreeting =
        incomingGreeting !== undefined && incomingGreeting !== ''
          ? incomingGreeting
          : prev.greeting;
      const nextLang = savedData.language || prev.language;
      const nextName = savedData.name || prev.name;
      const nextScript =
        nextGreeting !== prev.greeting
          ? syncGreetingToScript(prev.script, nextGreeting)
          : prev.script;
      const updated = {
        ...prev,
        name: nextName,
        language: nextLang,
        greeting: nextGreeting,
        script: nextScript,
        voice: {
          ...prev.voice,
          language: nextLang,
        },
      };
      setSavedSnapshot(snapForm(updated));
      return updated;
    });
    setSettingsDirty(false);
  }, []);

  const guardedAction = useCallback(
    (run) => async (...args) => {
      if (!(await confirmLeave())) return undefined;
      return run(...args);
    },
    [confirmLeave]
  );

  // Never let a refresh or a hard navigation silently discard an edited script.
  useEffect(() => {
    const onBeforeUnload = (event) => {
      if (!dirty) return;
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', onBeforeUnload);
    return () => window.removeEventListener('beforeunload', onBeforeUnload);
  }, [dirty]);

  const selectAgent = useMemo(
    () => guardedAction((agentId, step) => {
      setSelectedAgentId(agentId);
      onFlowStepChange?.(step, agentId);
    }),
    [guardedAction, setSelectedAgentId, onFlowStepChange]
  );

  const selectTab = useMemo(
    () => guardedAction((id, panel) => {
      setActiveTab(id);
      if (id === 'calls' && ['inbound', 'outbound', 'history', 'leads'].includes(panel)) setCallPanel(panel);
      onFlowStepChange?.(id);
    }),
    [guardedAction, onFlowStepChange]
  );

  // Agent list rows do not include script — load draft brain once per selection (not on every list refresh).
  useEffect(() => {
    const agentId = selectedAgentId || selectedAgent?.id;
    if (!agentId) return;

    let cancelled = false;
    setBrainLoading(true);
    setBrainLoadError(null);
    setPublishedVersion(null);
    setGenerationReport(null);
    setVariablePickerOpen(false);
    setVariableSuggestionTrigger(null);

    const agent =
      selectedAgent?.id === agentId
        ? selectedAgent
        : agents.find((a) => a.id === agentId) || selectedAgent;
    const base = formFromAgent(agent);

    loadAgentBrain(agentId)
      .then((data) => {
        if (cancelled) return;
        setPublishedVersion(data?.published?.version_id || null);
        setGenerationReport(data?.published?.optimizer_report || null);
        const studio = parseStudioFieldsFromSections(data?.draft?.sections);
        const cfg = parseVoiceConfigFromSections(data?.draft?.sections);
        const chosenVoice = agent?.voiceSettings?.realtimeVoice || agent?.voice?.realtimeVoice ||
          agent?.voice?.voiceId || cfg.realtimeVoice || base.voice?.realtimeVoice || 'Puck';
        const voiceMeta = (phoneVoices.length ? phoneVoices : []).find(
          (v) => v.id === chosenVoice
        );
        let initialGreeting = studio.greeting || base.greeting || '';
        let initialScript = studio.script || '';
        const extracted = extractGreetingFromScript(initialScript);
        if (extracted) {
          initialGreeting = extracted;
        } else if (initialGreeting && initialScript && !extractGreetingFromScript(initialScript)) {
          initialScript = syncGreetingToScript(initialScript, initialGreeting);
        }
        const loaded = {
          ...base,
          brainRevision: data?.draft?.revision,
          script: initialScript,
          greeting: initialGreeting,
          farewell: studio.farewell || '',
          boundaries: studio.boundaries ?? base.boundaries,
          objectionRules: studio.objectionRules ?? base.objectionRules,
          variableDefinitions: studio.variableDefinitions?.length
            ? studio.variableDefinitions
            : base.variableDefinitions,
          language: base.language || cfg.language,
          voice: {
            ...base.voice,
            realtimeVoice: chosenVoice,
            voiceId: chosenVoice,
            voiceName: voiceMeta?.label || chosenVoice,
            speed: cfg.speed ?? base.voice?.speed ?? 1,
            pitch: cfg.pitch ?? base.voice?.pitch ?? 0,
            stability: cfg.stability ?? base.voice?.stability ?? 0.75,
          },
        };
        setFormData(loaded);
        // What the server just sent IS the saved baseline, so switching agents
        // never reports a phantom "unsaved changes".
        setSavedSnapshot(snapForm(loaded));
      })
      .catch((err) => {
        if (!cancelled) {
          setBrainLoadError(err?.message || 'Could not load calling script');
          setFormData(base);
          setSavedSnapshot(snapForm(base));
        }
      })
      .finally(() => {
        if (!cancelled) setBrainLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [selectedAgentId, brainLoadAttempt]);


  useEffect(() => {
    if (!selectedAgent) return;
    setFormData((prev) => ({
      ...prev,
      name: selectedAgent.name || prev.name,
      role: selectedAgent.role || prev.role,
    }));
  }, [selectedAgent?.id, selectedAgent?.name, selectedAgent?.role]);

  // Handle Save
  const [saveError, setSaveError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [scriptReview, setScriptReview] = useState(null);

  const handleSave = async () => {
    if (!selectedAgent?.id || saving || brainLoading || brainLoadError) return false;
    setSaveError(null);
    setSaving(true);
    let success = true;
    try {
      if (scriptDirty) {
        const review = await reviewAgentBrain(selectedAgent.id, formData);
        setScriptReview({ snapshot: snapForm(formData), agentId: selectedAgent.id, ...review });
        if (!review.ok) {
          setSaveError('Review the blocking issues below before publishing. Your edits have been kept.');
          return false;
        }
        const updated = await updateAgent(selectedAgent.id, formData);
        setPublishedVersion(updated?.publication?.compiled_version || null);
        setGenerationReport(null);
        const publishedForm = { ...formData, brainRevision: updated?.publication?.draft_revision || formData.brainRevision };
        setFormData(publishedForm);
        try {
          await api.agents.saveTelephonyProfile(selectedAgent.id, {
            greetingPhrase: formData.greeting || '',
          });
        } catch {
          throw new Error('The script was published, but the opening greeting could not be confirmed. Your edits have been kept; retry Save.');
        }
        // Re-baseline: after a successful publish there is nothing left to guard.
        setSavedSnapshot(snapForm(publishedForm));
      }
      if (settingsDirty && settingsSaveRef.current) {
        const ok = await settingsSaveRef.current();
        if (!ok) {
          success = false;
          setSaveError('Agent settings could not be fully saved. Your edits are kept; review Settings and retry.');
        }
      }
      if (success) {
        setIsSaved(true);
        setTimeout(() => setIsSaved(false), 2500);
      }
      return success;
    } catch (e) {
      setSaveError(e.message || 'Could not save agent');
      return false;
    } finally {
      setSaving(false);
    }
  };

  // Variable chip insertion into script cursor
  const handleInsertVariable = (varName) => {
    setFormData((prev) => ({
      ...prev,
      script: prev.script ? `${prev.script}\n{{${varName}}}` : `{{${varName}}}`,
    }));
  };

  const handleAddObjection = (preset = null) => {
    const newRule = preset
      ? {
          category: preset.category || 'custom',
          kind: preset.kind || 'objection',
          enabled: preset.enabled !== false,
          trigger: preset.trigger || '',
          response: preset.response || '',
          action: preset.action || 'continue_script',
        }
      : {
          category: 'custom',
          kind: 'objection',
          enabled: true,
          trigger: '',
          response: '',
          action: 'continue_script',
        };
    setFormData((prev) => ({
      ...prev,
      objectionRules: [...(prev.objectionRules || []), newRule],
    }));
  };

  const handleRemoveObjection = (index) => {
    setFormData((prev) => ({
      ...prev,
      objectionRules: prev.objectionRules.filter((_, i) => i !== index)
    }));
  };

  // Cleanup audio preview on unmount
  useEffect(() => {
    return () => {
      voiceAgent.stopTTS();
      setIsPlayingVoice(false);
    };
  }, []);

  const handlePlayVoicePreview = async () => {
    if (isPlayingVoice || isBufferingVoice) {
      voiceAgent.stopTTS();
      setIsPlayingVoice(false);
      setIsBufferingVoice(false);
      return;
    }

    const previewLanguage = formData.language || formData.languages?.[0] || 'te-IN';
    const storedVoice = String(formData.voice?.voiceId || formData.voice?.realtimeVoice || 'marin').toLowerCase();
    const targetVoice = activeVoiceProvider === 'gemini'
      ? phoneVoices.find((voice) => voice.provider === 'gemini' && voice.id?.toLowerCase() === storedVoice)?.id || defaultVoiceId
      : storedVoice;
    const selectedVoice = phoneVoices.find((voice) => voice.id?.toLowerCase() === String(targetVoice).toLowerCase());
    const isEnglishGreeting = formData.greeting && /^[A-Za-z0-9\s.,!?'"()-]+$/.test(formData.greeting.trim());
    const previewText = selectedVoice?.sampleText ||
      (isEnglishGreeting ? formData.greeting.trim() : null) ||
      `Hi there! This is ${formData.name || 'Priya'}. Do you have two minutes to speak?`;
    setVoicePreviewError(null);
    setVoiceSpoken({ voice: null, model: null });
    setIsBufferingVoice(true);

    // Use the selected provider and the active voice for the agent's language.
    let previewUrl = null;
    try {
      const targetSpeed = formData.voice?.speed ?? 1;
      const { blob, url, voice, model } = await api.telephony.previewVoice({
        text: previewText,
        voiceId: targetVoice,
        language: previewLanguage,
        speed: targetSpeed,
        tier: voiceStackAgent?.defaultTier || null,
      });
      previewUrl = url || null;
      setVoiceSpoken({ voice: voice || targetVoice, model: model || null, language: previewLanguage });
      setIsBufferingVoice(false);
      setIsPlayingVoice(true);
      let played = false;
      if (blob) {
        played = await voiceAgent.playAudioBuffer(
          blob,
          () => {
            if (previewUrl) URL.revokeObjectURL(previewUrl);
            previewUrl = null;
            setIsPlayingVoice(false);
          },
          () => setIsPlayingVoice(true)
        );
        if (played && previewUrl) {
          URL.revokeObjectURL(previewUrl);
          previewUrl = null;
        }
      }
      if (!played && url) {
        voiceAgent.playAudioClip(
          url,
          () => {
            if (previewUrl) URL.revokeObjectURL(previewUrl);
            previewUrl = null;
            setIsPlayingVoice(false);
          },
          () => setIsPlayingVoice(true)
        );
        played = true;
      }
      if (!played) {
        if (previewUrl) URL.revokeObjectURL(previewUrl);
        previewUrl = null;
        setIsPlayingVoice(false);
        setVoicePreviewError('The preview audio could not be played. Check your sound output.');
      }
    } catch (e) {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
      setIsBufferingVoice(false);
      setIsPlayingVoice(false);
      setVoicePreviewError(
        e?.message || 'Could not reach the voice service to preview this voice.'
      );
    }
  };

  if (!isLoading && agents.length === 0) {
    return (
      <SolidCard className="p-10 text-center space-y-4 max-w-lg mx-auto">
        <FileCode2 className="w-10 h-10 text-[#6344E7] mx-auto" />
        <h2 className="text-lg font-bold text-[#0F0E17]">No agents yet</h2>
        <p className="text-sm text-[#524E5E]">
          Create an AI employee first, then edit scripts, voice, and telephony routing here in Script Studio.
        </p>
        <TactileButton onClick={() => onNavigate?.('employees', { openCreate: true })}>
          Create your first AI employee
        </TactileButton>
      </SolidCard>
    );
  }

  if (!selectedAgent) {
    if (isLoading) {
      return (
        <div className="space-y-6" data-testid="agent-studio-loading" aria-busy="true">
          <AgentStudioHeaderSkeleton />
          <AgentStudioEditorSkeleton />
        </div>
      );
    }
    return (
      <SolidCard className="p-10 text-center space-y-3 max-w-lg mx-auto">
        <p className="text-sm text-[#524E5E]">Select an agent to edit.</p>
      </SolidCard>
    );
  }

  return (
    <div ref={workspaceContainerRef} className="space-y-6"
      style={{ paddingBottom: dirty ? 'calc(var(--agent-save-dock-height, 9rem) + 2rem)' : undefined }}>
      {saveError && (
        <div role="alert" data-testid="agent-save-error" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-900">{saveError}</div>
      )}
      {/* Unsaved-changes guard. Every leave path (tab, agent switch, back, unload)
          funnels through confirmLeave, so nothing silently discards a script. */}


      <Modal
        isOpen={Boolean(pendingLeave)}
        onClose={() => settleLeave(false)}
        title="Unsaved changes"
        subtitle="Your configurations have not been saved yet."
        maxWidth="max-w-md"
      >
        <div className="space-y-4" data-testid="agent-studio-leave-dialog">
          <p className="text-xs text-[#524E5E]">
            Leaving now discards the unsaved changes you have made to this agent.
          </p>
          <div className="flex flex-wrap items-center justify-end gap-2">
            <button
              type="button"
              onClick={() => {
                discardChanges();
                settleLeave(true);
              }}
              data-testid="leave-discard"
              className="mr-auto rounded-xl px-3 py-2 text-xs font-semibold text-[#B42318] hover:bg-[#FEF2F2]"
            >
              Discard changes
            </button>
            <button
              type="button"
              onClick={() => settleLeave(false)}
              data-testid="leave-cancel"
              className="rounded-xl px-3 py-2 text-xs font-semibold text-[#524E5E] hover:bg-[#FAF9FD]"
            >
              Keep editing
            </button>
            <button
              type="button"
              disabled={saving}
              data-testid="leave-save"
              onClick={async () => {
                const ok = await handleSave();
                if (ok) settleLeave(true);
              }}
              className="rounded-xl bg-[#6344E7] px-3 py-2 text-xs font-bold text-white disabled:opacity-50"
            >
              {saving ? 'Saving…' : 'Save & continue'}
            </button>
          </div>
        </div>
      </Modal>
      {/* Workbench Header: Agent Switcher, Status & Save */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-5 rounded-2xl bg-white border border-[#E4E2EB] shadow-craft-xs">
        {/* Left: Agent Avatar & Selector */}
        <div className="flex items-center gap-3.5">
          {onBackToFleet && (
            <button
              type="button"
              onClick={() => void (async () => {
                  if (await confirmLeave()) onBackToFleet?.();
                })()}
              data-testid="agent-studio-back"
              className="p-2 rounded-xl border border-[#E4E2EB] text-[#524E5E] hover:text-[#0F0E17] hover:bg-[#FAF9FD]"
              title="Back to fleet"
            >
              <ArrowLeft className="w-4 h-4" />
            </button>
          )}
          <div className="w-12 h-12 rounded-2xl bg-[#F0EEF6] border border-[#E4E2EB] flex items-center justify-center text-[#0F0E17] font-bold text-lg shadow-2xs">
            {selectedAgent.name.charAt(0)}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <select
                value={selectedAgentId}
                onChange={(e) => void selectAgent(e.target.value)}
                data-testid="agent-studio-switcher"
                className="bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl px-2.5 py-1.5 min-h-[40px] sm:min-h-[34px] text-base sm:text-sm font-bold text-[#0F0E17] focus:outline-none focus:border-[#6344E7] transition-colors"
              >
                {agents.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name} ({a.role})
                  </option>
                ))}
              </select>
              <StatusBadge status={selectedAgent.status} size="xs" />
            </div>
            <div className="text-xs text-[#524E5E] mt-1">
              Assigned: <span className="font-mono font-semibold text-[#0F0E17]">{selectedAgent.assignedNumber || 'None (Pool)'}</span>
            </div>
          </div>
        </div>

        {/* Right Action Buttons */}
        <div className="flex items-center gap-2.5">
          <TactileButton
            variant="secondary"
            size="sm"
            icon={Radio}
            disabled={!voiceStackReady || dirty || saving || brainLoading || !!brainLoadError}
            title={dirty ? 'Save your changes before testing the agent.' : 'Test the published script'}
            onClick={(e) => {
              testCallButtonRef.current = e.currentTarget;
              setTestCallOpen(true);
            }}
            data-testid="agent-test-call"
            className="min-h-[38px]"
          >
            Test call
          </TactileButton>

          <span className="hidden sm:inline text-xs text-[#716C7F]" role="status">
            {dirty ? 'Changes pending' : isSaved ? 'Changes saved' : 'All changes saved'}
          </span>
        </div>
      </div>

      {/* Tabs Navigation Bar */}
      <div
        className="sticky top-0 z-20 flex items-center gap-1 p-1.5 rounded-2xl bg-white border border-[#E4E2EB] overflow-x-auto scrollbar-none touch-pan-x shadow-craft-xs"
        role="tablist"
        aria-label="Agent workspace"
      >
        {FLOW_TABS.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              role="tab"
              id={`agent-tab-${tab.id}`}
              aria-selected={isActive}
              aria-controls={`agent-panel-${tab.id}`}
              data-testid={`agent-tab-${tab.id}`}
              onClick={() => selectTab(tab.id)}
              className={`flex items-center gap-2 px-4 py-2 min-h-[40px] rounded-xl text-xs font-semibold whitespace-nowrap transition-all ${
                isActive
                  ? 'bg-[#0F0E17] text-white shadow-xs font-bold'
                  : 'text-[#524E5E] hover:text-[#0F0E17] hover:bg-[#FAF9FD]'
              }`}
            >
              <Icon className="w-3.5 h-3.5" />
              <span>{tab.label}</span>
            </button>
          );
        })}
      </div>

      {/* TAB: OVERVIEW */}
      {activeTab === 'overview' && (
        <div
          role="tabpanel"
          id="agent-panel-overview"
          aria-labelledby="agent-tab-overview"
          className="animate-in fade-in duration-150"
        >
          <ErrorBoundary title="Unable to load agent overview">
            <AgentOverview agent={selectedAgent} onOpenTab={selectTab} />
          </ErrorBoundary>
        </div>
      )}

      {/* TAB: SCRIPT & CONVERSATION FLOW */}
      {activeTab === 'script' && (
        <div
          role="tabpanel"
          id="agent-panel-script"
          aria-labelledby="agent-tab-script"
          className="flex flex-col gap-4 animate-in fade-in duration-150"
        >
          {generationReport?.status && generationReport.status !== 'ready' ? (
            <div data-testid="agent-script-generation-status" className="rounded-xl border border-[#E4E2EB] bg-[#FAF9FD] px-4 py-3 text-xs text-[#524E5E]" aria-live="polite">
              <p className="font-semibold text-[#0F0E17]">
                Review the business details before calling
              </p>
              <p className="mt-1">
                Check the names, offer, and next step in this script, then make a test call.
              </p>
              {scriptDirty ? <p className="mt-1">This report describes the published script. The current draft has edits.</p> : null}
            </div>
          ) : null}
          <div className="console-categories script-categories grid gap-4 items-start" data-category="all">
          {/* Greeting mechanics stay unchanged; only the surrounding layout changes. */}
          <div data-section="writing" className="flex flex-col gap-4">

          <SolidCard>
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-3">
              <div>
                <h3 className="text-xs font-bold text-[#0F0E17]">Calling script</h3>
                <p className="text-[11px] text-[#524E5E]">
                  Your agent’s conversation guide. Save to use your changes on calls.
                </p>
                {brainLoading && (
                  <p className="text-[11px] text-[#6344E7] mt-1">Loading your script…</p>
                )}
                {brainLoadError && (
                  <div role="alert" className="text-[11px] text-red-600 mt-1">
                    {brainLoadError}
                    <button type="button" onClick={() => setBrainLoadAttempt((n) => n + 1)} className="ml-2 underline" data-testid="retry-script-load">Retry loading</button>
                  </div>
                )}
                {!brainLoading && !brainLoadError && (
                  <div className="flex items-center gap-1.5 mt-1">
                    <span className={`inline-block size-1.5 rounded-full ${publishedVersion ? 'bg-emerald-500' : 'bg-amber-500'}`} />
                    <p data-testid="script-save-status" className="text-[11px] text-[#524E5E]" role="status">
                      {scriptDirty ? 'Unsaved changes' : publishedVersion ? 'Saved for calls' : 'Save your script to use it on calls'}
                    </p>
                  </div>
                )}
              </div>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setScriptPreviewMode(!scriptPreviewMode)}
                  className={`px-2.5 py-1.5 rounded-lg border text-xs font-semibold flex items-center gap-1.5 shadow-2xs transition-colors ${
                    scriptPreviewMode
                      ? 'border-[#6344E7] bg-[#EEF2FF] text-[#4338CA]'
                      : 'border-[#E4E2EB] bg-[#FAF9FD] hover:bg-[#F0EEF6] text-[#524E5E]'
                  }`}
                  data-testid="preview-script-toggle"
                >
                  <Eye className="w-3.5 h-3.5" />
                  <span>{scriptPreviewMode ? 'Edit Script' : 'Preview with Lead'}</span>
                </button>

                {!scriptPreviewMode && (
                  <div className="relative">
                    <button
                      type="button"
                      onClick={() => setVariablePickerOpen(!variablePickerOpen)}
                      disabled={brainLoading || !!brainLoadError || saving}
                      className="px-2.5 py-1.5 rounded-lg border border-[#E4E2EB] bg-[#FAF9FD] hover:bg-[#F0EEF6] text-xs font-semibold text-[#6344E7] flex items-center gap-1.5 shadow-2xs transition-colors"
                      data-testid="insert-variable-btn"
                    >
                      <Plus className="w-3.5 h-3.5" />
                      <span>Insert variable +</span>
                    </button>

                    {variablePickerOpen && (
                      <div className="absolute right-0 top-full mt-1.5 w-72 bg-white border border-[#E4E2EB] rounded-xl shadow-xl z-30 p-2.5 text-xs space-y-2.5">
                        {/* Fallback Syntax Toggle */}
                        <label className="flex items-center justify-between p-2 bg-[#F5F3FF] rounded-lg border border-[#DDD6FE] cursor-pointer select-none">
                          <div className="flex flex-col">
                            <span className="text-[10px] font-bold text-[#5B21B6]">Include Fallback Defaults</span>
                            <span className="text-[9px] text-[#6B7280]">e.g. {'{{contact.first_name | there}}'}</span>
                          </div>
                          <input
                            type="checkbox"
                            checked={useFallbackSyntax}
                            onChange={(e) => setUseFallbackSyntax(e.target.checked)}
                            className="rounded text-[#6344E7] focus:ring-[#6344E7] cursor-pointer"
                            data-testid="toggle-fallback-syntax"
                          />
                        </label>

                        {scriptVariableGroups.map((group, groupIndex) => (
                          <div key={group.id} className={groupIndex > 0 ? 'border-t border-[#E4E2EB] pt-1.5' : ''}>
                            <span className="text-[10px] font-bold uppercase text-[#8C879A] px-1 block mb-1">
                              {group.title}
                            </span>
                            <div className="space-y-0.5 max-h-40 overflow-y-auto pr-1">
                              {group.variables.map((variable) => {
                                const slug = variable.label.toLowerCase().replace(/\s+/g, '-');
                                const testId = group.id === 'system' ? `insert-token-system-${slug}` : `insert-token-${slug}`;
                                return (
                                  <button
                                    key={variable.key}
                                    type="button"
                                    onClick={() => {
                                      insertVariable(variable.token);
                                      setVariablePickerOpen(false);
                                    }}
                                    className="w-full text-left px-2 py-1 rounded hover:bg-[#FAF9FD] flex items-center justify-between text-[#0F0E17] group"
                                    data-testid={testId}
                                  >
                                    <span className="text-[11px]">{variable.label}</span>
                                    <span className="text-[9px] font-mono text-[#6344E7] group-hover:underline truncate max-w-[140px] text-right">
                                      {variable.token}
                                    </span>
                                  </button>
                                );
                              })}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>

            {scriptReview?.agentId === selectedAgent?.id && scriptReview?.snapshot === snapForm(formData) && (scriptReview.error || !scriptReview.ok || scriptReview.issues?.length > 0) && (
              <div role="alert" data-testid="script-review-result" className="mb-3 rounded-xl border border-amber-300 bg-amber-50/70 p-3 text-xs text-amber-900 space-y-1.5">
                <p className="font-semibold">{scriptReview.error || 'Check these details before saving'}</p>
                {!!scriptReview.issues?.length && <ul className="list-disc pl-4 space-y-1">{scriptReview.issues.map((issue, index) => <li key={`${issue.code}-${index}`}>{issue.message}</li>)}</ul>}
              </div>
            )}
            {scriptPreviewMode ? (
              <div className="space-y-3" data-testid="script-preview-panel">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 p-2.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB]">
                  <div className="flex items-center gap-2">
                    <span className="text-[11px] font-bold text-[#0F0E17]">Sample Lead:</span>
                    <div className="flex gap-1.5">
                      {SAMPLE_LEADS.map((lead, idx) => (
                        <button
                          key={lead.id}
                          type="button"
                          onClick={() => setSampleLeadIdx(idx)}
                          className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition-all ${
                            sampleLeadIdx === idx
                              ? 'bg-[#6344E7] text-white shadow-xs'
                              : 'bg-white text-[#524E5E] border border-[#E4E2EB] hover:bg-[#F5F3FF]'
                          }`}
                          data-testid={`select-sample-lead-${idx}`}
                        >
                          <span>{lead.name}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200 self-start sm:self-auto">
                    {SAMPLE_LEADS[sampleLeadIdx].badge}
                  </span>
                </div>

                <div className="relative">
                  <div className="absolute top-2 right-2 px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider bg-[#EDE9FE] text-[#6344E7]">
                    Sample lead preview
                  </div>
                  <div className="w-full min-h-[180px] bg-[#0F0E17] text-[#F3F4F6] border border-[#2E2B36] rounded-xl p-4 text-xs font-mono leading-relaxed whitespace-pre-wrap select-text">
                    {renderScriptPreview(formData.script, SAMPLE_LEADS[sampleLeadIdx].contact) || (
                      <span className="text-[#6B7280] italic">No script text to preview. Switch back to edit and enter your script.</span>
                    )}
                  </div>
                </div>

                <div className="flex items-center justify-between text-[11px] text-[#524E5E] bg-[#F8FAFC] p-2.5 rounded-lg border border-[#E2E8F0]">
                  <span className="flex items-center gap-1 text-[#059669] font-medium">
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    <span>Dynamic lead variable tokens &amp; fallback defaults evaluated in real time</span>
                  </span>
                  <button
                    type="button"
                    onClick={() => setScriptPreviewMode(false)}
                    className="font-semibold text-[#6344E7] hover:underline"
                  >
                    Back to script editor
                  </button>
                </div>
              </div>
            ) : (
              <div className="relative">
                <textarea
                  ref={scriptTextareaRef}
                  disabled={brainLoading || !!brainLoadError || saving}
                  rows={12}
                  value={formData.script}
                  onChange={(event) => {
                    handleScriptChange(event.target.value);
                    updateVariableSuggestion(event.target);
                  }}
                  onClick={(event) => updateVariableSuggestion(event.currentTarget)}
                  onKeyUp={(event) => {
                    if (!['ArrowDown', 'ArrowUp', 'Enter', 'Tab', 'Escape'].includes(event.key)) {
                      updateVariableSuggestion(event.currentTarget);
                    }
                  }}
                  onKeyDown={handleScriptEditorKeyDown}
                  role="combobox"
                  aria-label="Calling script"
                  aria-autocomplete="list"
                  aria-expanded={variableSuggestionTrigger !== null}
                  aria-controls="script-variable-suggestions"
                  aria-activedescendant={variableSuggestions.length
                    ? `script-variable-option-${selectedVariableSuggestion}`
                    : undefined}
                  className="script-paper w-full text-[13px] text-[#0F0E17] leading-6 focus:outline-none focus:ring-2 focus:ring-[#6344E7]/30"
                  data-testid="script-textarea"
                />
                {variableSuggestionTrigger && (
                  <div
                    id="script-variable-suggestions"
                    role="listbox"
                    aria-label="Available script variables"
                    className="absolute left-0 right-0 z-40 mt-1 max-h-56 overflow-y-auto rounded-xl border border-[#E4E2EB] bg-white p-2 shadow-xl"
                    style={{ top: variableSuggestionTop }}
                    data-testid="script-variable-suggestions"
                  >
                    <p className="px-2 py-1 text-[10px] text-[#8C879A]">
                      Insert a variable · use ↑/↓ and Enter
                    </p>
                    {variableSuggestions.length ? variableSuggestions.map((variable, index) => (
                      <button
                        key={variable.key}
                        id={`script-variable-option-${index}`}
                        type="button"
                        role="option"
                        aria-selected={selectedVariableSuggestion === index}
                        onMouseDown={(event) => event.preventDefault()}
                        onMouseEnter={() => setSelectedVariableSuggestion(index)}
                        onClick={() => selectVariableSuggestion(variable)}
                        className={`flex w-full items-center justify-between gap-3 rounded-lg px-2.5 py-2 text-left ${
                          selectedVariableSuggestion === index ? 'bg-[#F5F3FF]' : 'hover:bg-[#FAF9FD]'
                        }`}
                      >
                        <span className="min-w-0">
                          <span className="block text-[11px] font-semibold text-[#0F0E17]">{variable.label}</span>
                          <span className="block text-[9px] text-[#8C879A]">{variable.groupTitle}</span>
                        </span>
                        <span className="shrink-0 truncate font-mono text-[10px] text-[#6344E7]">{variable.token}</span>
                      </button>
                    )) : (
                      <p className="px-2.5 py-2 text-[11px] text-[#524E5E]">No matching variables.</p>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* Only show what is real. Token counts and latency are internal
                engineering metrics; the server does not report them here, so
                guessing would be worse than saying nothing. */}
            <div className="flex items-center justify-between text-[11px] text-[#8C879A] mt-2">
              <span>
                {formData.script.trim()
                  ? `${formData.script.trim().split(/\s+/).length} words`
                  : 'Script is empty'}
              </span>
              <button
                type="button"
                onClick={() => setTestCallOpen(true)}
                disabled={!voiceStackReady || dirty || saving || brainLoading || !!brainLoadError}
                title={dirty ? 'Publish your changes before testing the agent.' : 'Test the published script'}
                className="font-semibold text-[#5034CE] hover:underline"
              >
                Test published script
              </button>
            </div>
          </SolidCard></div>

          <div className="script-support flex flex-col gap-4" data-section="support">
          <div data-section="greeting"><SolidCard>
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-2">
              <div>
                <h3 className="text-xs font-bold text-[#0F0E17] flex items-center gap-2">
                  <Volume2 className="w-3.5 h-3.5 text-[#6344E7]" />
                  <span>Greeting the caller hears</span>
                </h3>
                <p className="text-[11px] text-[#524E5E]">
                  The opening phrase the caller hears when they connect. Connected to the calling script and the acoustic voice preview.
                </p>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="text-[10px] font-mono px-2 py-0.5 rounded-md border bg-[#F0EEF6] text-[#524E5E] border-[#E4E2EB]">
                  {LANGUAGE_OPTIONS.find((l) => l.code === formData.language)?.label || formData.language}
                </span>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded-md border bg-[#F0EEF6] text-[#524E5E] border-[#E4E2EB]">
                  {/^Voice \d+$/.test(String(formData.voice?.voiceName || '').trim())
                    ? formData.voice.voiceName
                    : 'Selected voice'}
                </span>
              </div>
            </div>

            <textarea
              rows={2}
              aria-label="Opening greeting"
              disabled={brainLoading || !!brainLoadError || saving}
              value={formData.greeting}
              onChange={(e) => handleGreetingChange(e.target.value)}
              placeholder="Hi there! Thanks for calling. How can I help you today?"
              data-testid="agent-studio-greeting"
              className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-xl p-3 text-xs text-[#0F0E17] font-medium leading-relaxed focus:outline-none focus:border-[#6344E7] transition-colors resize-none"
            />
          </SolidCard></div>
          <div data-section="closing"><SolidCard>
            <label htmlFor="agent-farewell" className="block text-sm font-semibold text-[#0F0E17]">
              Farewell the caller hears
            </label>
            <p id="agent-farewell-help" className="mt-1 mb-3 text-xs text-[#524E5E]">
              Write the closing words in the agent’s language. They are spoken live after an approved ending.
              A saved callback request gets a confirmation before this farewell. Leave blank to use the language default.
            </p>
            <textarea
              id="agent-farewell"
              name="farewell"
              rows={3}
              maxLength={240}
              value={formData.farewell || ''}
              onChange={(event) => setFormData((previous) => ({ ...previous, farewell: event.target.value }))}
              disabled={brainLoading || !!brainLoadError || saving}
              aria-describedby="agent-farewell-help"
              data-testid="agent-studio-farewell"
              className="w-full rounded-xl border border-[#E4E2EB] bg-[#FAF9FD] p-4 text-sm leading-relaxed text-[#0F0E17] focus-visible:outline-2 focus-visible:-outline-offset-1 focus-visible:outline-[#6344E7] max-sm:text-base"
            />
            <p className="mt-2 text-right text-xs text-[#524E5E]">{(formData.farewell || '').length}/240 characters</p>
          </SolidCard></div>

          {/* Objection Handling Rules */}
          <div data-section="objections"><SolidCard>
            <fieldset disabled={brainLoading || !!brainLoadError || saving} className="contents" aria-label="Objection and objective rules">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-3">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-xs font-bold text-[#0F0E17]">Objection &amp; Objective Handling</h3>
                  <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-[#FAF5FF] text-[#7E22CE] border border-[#F3E8FF]">
                    Concerns and conversation goals
                  </span>
                </div>
                <p className="text-[11px] text-[#524E5E] mt-0.5">
                  Configure responses and goals in any language. Save changes to recompile the brain for future calls. Rules respect caller intent and available actions.
                </p>
              </div>
              <div className="flex flex-wrap gap-3"><button type="button" onClick={() => handleAddObjection({ kind: 'objective' })} className="text-xs font-semibold text-[#6344E7]" data-testid="add-objective-btn">+ Add objective</button><button
                type="button"
                onClick={() => handleAddObjection()}
                className="text-xs font-semibold text-[#6344E7] hover:text-[#5034CE] flex items-center gap-1 self-start sm:self-auto shrink-0"
                data-testid="add-objection-btn"
              >
                <Plus className="w-3 h-3" />
                <span>Add objection</span>
              </button>
              </div>
            </div>

            {/* Quick-add industry standard templates bar */}
            <div className="mb-4 p-2.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB]">
              <span className="text-[10px] font-bold uppercase text-[#8C879A] block mb-1.5">
                Quick-add templates to review:
              </span>
              <div className="flex flex-wrap gap-1.5">
                {OBJECTION_PRESETS.map((preset) => (
                  <button
                    key={preset.id}
                    type="button"
                    onClick={() => handleAddObjection(preset)}
                    className="px-2.5 py-1 rounded-lg text-xs font-medium border border-[#E4E2EB] bg-white hover:bg-[#F5F3FF] hover:border-[#DDD6FE] text-[#2E2B36] hover:text-[#6344E7] transition-all flex items-center gap-1 shadow-2xs"
                    data-testid={`preset-objection-${preset.id}`}
                  >
                    <Plus className="w-3 h-3 text-[#6344E7]" />
                    <span>{preset.label}</span>
                  </button>
                ))}
              </div>
            </div>

            {/* Rules list */}
            <div className="space-y-3">
              {(formData.objectionRules || []).length === 0 ? (
                <div className="p-4 rounded-xl border border-dashed border-[#D2CEE0] text-center bg-[#FAF9FD]">
                  <p className="text-xs text-[#524E5E]">No handling rules configured yet.</p>
                  <p className="text-[11px] text-[#8C879A] mt-1">
                    Add a concern or a conversation goal, then configure how the agent should handle it.
                  </p>
                </div>
              ) : (
                (formData.objectionRules || []).map((rule, idx) => (
                  <div
                    key={idx}
                    className="p-3.5 rounded-xl bg-white border border-[#E4E2EB] shadow-2xs relative group transition-all hover:border-[#D2CEE0]"
                    data-testid={`objection-rule-${idx}`}
                  >
                    <div className="flex items-center justify-between mb-2.5">
                      <div className="flex items-center gap-2">
                        <select aria-label={`Rule ${idx + 1} type`} value={rule.kind || 'objection'} onChange={(event) => setFormData(previous => ({ ...previous, objectionRules: previous.objectionRules.map((item, index) => index === idx ? { ...item, kind: event.target.value } : item) }))} className="rounded-lg border border-[#E4E2EB] p-1 text-xs">
                          <option value="objection">Objection</option><option value="objective">Objective</option>
                        </select>
                        <label className="flex items-center gap-1 text-xs"><input type="checkbox" aria-label={`Enable rule ${idx + 1}`} checked={rule.enabled !== false} onChange={(event) => setFormData(previous => ({ ...previous, objectionRules: previous.objectionRules.map((item, index) => index === idx ? { ...item, enabled: event.target.checked } : item) }))} />Enabled</label>
                        <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-md bg-[#FAF5FF] text-[#6344E7] border border-[#F3E8FF]">
                          Rule #{idx + 1}
                        </span>
                        {rule.category && rule.category !== 'custom' && (
                          <span className="text-[10px] font-medium px-2 py-0.5 rounded-md bg-[#F3F4F6] text-[#374151]">
                            {rule.category.toUpperCase()}
                          </span>
                        )}
                      </div>
                      <button
                        type="button"
                        onClick={() => handleRemoveObjection(idx)}
                        className="p-1 text-[#DC2626] hover:bg-red-50 rounded transition-colors"
                        title="Remove rule"
                        data-testid={`remove-objection-${idx}`}
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-12 gap-3">
                      {/* Trigger */}
                      <div className="md:col-span-5">
                        <span className="text-[10px] text-[#8C879A] uppercase font-bold block mb-1">
                          {rule.kind === 'objective' ? 'Situation / goal:' : 'Caller concern:'}
                        </span>
                        <input
                          type="text"
                          aria-label={`Rule ${idx + 1} situation`}
                          value={rule.trigger || ''}
                          placeholder="e.g. Too expensive / Not interested"
                          onChange={(e) => {
                            const next = [...formData.objectionRules];
                            next[idx] = { ...next[idx], trigger: e.target.value };
                            setFormData({ ...formData, objectionRules: next });
                          }}
                          className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-lg px-2.5 py-1.5 text-xs text-[#0F0E17] focus:outline-none focus:border-[#6344E7] transition-colors"
                          data-testid={`objection-trigger-${idx}`}
                        />
                      </div>

                      {/* Response */}
                      <div className="md:col-span-5">
                        <span className="text-[10px] text-[#8C879A] uppercase font-bold block mb-1">
                          {rule.kind === 'objective' ? 'Guidance to achieve the goal:' : 'Response guidance:'}
                        </span>
                        <textarea
                          aria-label={`Rule ${idx + 1} guidance`}
                          rows={2}
                          value={rule.response || ''}
                          placeholder="e.g. I understand budget is important... Could I share..."
                          onChange={(e) => {
                            const next = [...formData.objectionRules];
                            next[idx] = { ...next[idx], response: e.target.value };
                            setFormData({ ...formData, objectionRules: next });
                          }}
                          className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-lg px-2.5 py-1.5 text-xs text-[#0F0E17] focus:outline-none focus:border-[#6344E7] transition-colors resize-none"
                          data-testid={`objection-response-${idx}`}
                        />
                      </div>

                      {/* Action outcome */}
                      <div className="md:col-span-2">
                        <span className="text-[10px] text-[#8C879A] uppercase font-bold block mb-1">
                          Action Outcome:
                        </span>
                        <select
                          value={rule.action || 'continue_script'}
                          onChange={(e) => {
                            const next = [...formData.objectionRules];
                            next[idx] = { ...next[idx], action: e.target.value };
                            setFormData({ ...formData, objectionRules: next });
                          }}
                          className="w-full bg-[#FAF9FD] border border-[#E4E2EB] rounded-lg px-2 py-1.5 text-xs text-[#0F0E17] focus:outline-none focus:border-[#6344E7] transition-colors"
                          data-testid={`objection-action-${idx}`}
                        >
                          <option value="continue_script">Continue Script</option>
                          <option value="offer_callback">Offer Callback</option>
                          <option value="end_call">Request Call Ending</option>
                          <option value="transfer_human">Transfer Human</option>
                        </select>
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
            </fieldset>
          </SolidCard></div>
          </div>
          </div>
        </div>
      )}

      {/* TAB: VOICE & LANGUAGE STUDIO */}
      {activeTab === 'voice' && (
        <div
          role="tabpanel"
          id="agent-panel-voice"
          aria-labelledby="agent-tab-voice"
          data-testid="agent-panel-voice"
          className="space-y-6 animate-in fade-in duration-150"
        >
          <ErrorBoundary title="Unable to load voice studio">
            <AgentVoicePanel
              formData={formData}
              setFormData={setFormData}
              phoneVoices={phoneVoices}
              activeVoiceProvider={activeVoiceProvider}
              defaultVoiceId={defaultVoiceId}
              voiceCatalogError={voiceCatalogError}
              voiceCatalogLoading={voiceCatalogLoading}
              onRetryVoiceCatalog={retryVoiceCatalog}
              agent={voiceStackAgent}
              voiceStackProfiles={voiceStackProfiles}
              voiceStackCatalogLoading={voiceStackCatalogLoading}
              voiceStackCatalogError={voiceStackCatalogError}
              onRetryVoiceStackCatalog={refreshVoiceStackCatalog}
              onSaveVoiceStackSelection={saveVoiceStackSelection}
              onReloadVoiceStackSettings={reloadVoiceStackSettings}
              onVoiceStackReadyChange={setVoiceStackReady}
              onOpenTestCall={() => setTestCallOpen(true)}
            />
          </ErrorBoundary>
        </div>
      )}

      {/* TAB: CALLS (history | leads | call settings) */}
      {activeTab === 'calls' && (
        <div
          role="tabpanel"
          id="agent-panel-calls"
          aria-labelledby="agent-tab-calls"
          className="space-y-4 animate-in fade-in duration-150"
        >
          <div className="rounded-xl border border-[#E4E2EB] bg-[#F0EEF6]/70 px-3.5 py-2.5 text-xs font-semibold text-[#1F1D2B]">
            Phone calls use your published script and wallet credits. Your saved voice setup applies to
            incoming and outgoing calls.
          </div>
          <ErrorBoundary title="Unable to load agent calls panel">
            <AgentCallsPanel
              agentId={selectedAgent.id}
              agentName={selectedAgent.name}
              initialPanel={callPanel}
              onNavigateToSettings={() => selectTab('settings')}
            />
          </ErrorBoundary>
        </div>
      )}

      {/* TAB: SETTINGS */}
      {activeTab === 'settings' && (
        <div
          role="tabpanel"
          id="agent-panel-settings"
          aria-labelledby="agent-tab-settings"
          className="animate-in fade-in duration-150"
        >
          <ErrorBoundary title="Unable to load agent settings">
            <AgentSettingsPanel
              agent={selectedAgent}
              savingChanges={saving}
              agentGreeting={formData.greeting}
              onGreetingChange={handleGreetingChange}
              onOpenBuyNumber={onOpenBuyNumber}
              onDirtyChange={setSettingsDirty}
              registerSaveHandler={(saveFn, discardFn) => {
                settingsSaveRef.current = saveFn;
                settingsDiscardRef.current = discardFn;
              }}
              onSettingsSaved={handleSettingsSaved}
            />
          </ErrorBoundary>
        </div>
      )}

      {dirty && <AgentSaveDock containerRef={workspaceContainerRef} scriptDirty={scriptDirty}
        settingsDirty={settingsDirty} saving={saving} error={saveError} disabled={brainLoading || !!brainLoadError}
        onSave={handleSave} onDiscard={discardChanges} />}

      {/* Test call is a header action, not a tab. Focus returns to the button on close. */}
      {testCallOpen && (
        <Modal
          isOpen={testCallOpen}
          onClose={() => {
            setTestCallOpen(false);
            requestAnimationFrame(() => testCallButtonRef.current?.focus());
          }}
          title={`Test call — ${selectedAgent?.name || 'Agent'}`}
          subtitle="Talk to your agent in this browser or receive a phone call. Usage is billed from your wallet."
          maxWidth="max-w-lg"
        >
          <div data-testid="agent-test-call-panel">
            <ErrorBoundary title="Unable to initialize test call">
                <AgentTestCallPanel
                  agent={voiceStackAgent}
                  pricingProfile={voiceStackProfiles.find((profile) => profile.tier === (voiceStackAgent?.defaultTier || voiceStackAgent?.default_tier))}
                  language={formData.language || formData.languages?.[0] || selectedAgent?.languages?.[0] || selectedAgent?.language || 'en-IN'}
                />
            </ErrorBoundary>
          </div>
        </Modal>
      )}
    </div>
  );
}

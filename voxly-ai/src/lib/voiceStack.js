import { api } from '../services/api';

let cachedOptions = null;

export async function fetchPhoneVoiceOptions() {
  if (cachedOptions) return cachedOptions;
  const data = await api.request('GET', '/api/telephony/voice-options');
  cachedOptions = {
    stackLabel: data.stackLabel || 'Live phone AI',
    stackDescription: data.stackDescription || '',
    defaultVoiceId: data.defaultVoiceId || 'marin',
    voices: Array.isArray(data.voices) ? data.voices : [],
    languages: Array.isArray(data.languages) ? data.languages : [],
  };
  return cachedOptions;
}

export function parseVoiceConfigFromSections(sections) {
  if (!Array.isArray(sections)) return {};
  const row = sections.find((s) => s.title === 'saas_voice_config');
  if (!row?.raw_text) return {};
  try {
    const parsed = JSON.parse(row.raw_text);
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
}

export const SAAS_SCRIPT_VARIABLES_TITLE = 'saas_script_variables';
export const SAAS_CALLING_SCRIPT_TITLE = 'Calling script';

export function parseStudioFieldsFromSections(sections) {
  if (!Array.isArray(sections)) return { script: '', greeting: '', variableDefinitions: [] };
  const scriptRow = sections.find(
    (s) =>
      s.enabled !== false &&
      s.type === 'facts' &&
      (s.title === SAAS_CALLING_SCRIPT_TITLE ||
        s.title === 'Agent script' ||
        s.title === 'Business Facts')
  );
  const script = String(scriptRow?.raw_text || '').trim();
  const identity = sections.find((s) => s.type === 'identity_purpose');
  let greeting = '';
  const idText = String(identity?.raw_text || '');
  const gm = idText.match(/Opening greeting:\s*(.+)/i);
  if (gm) greeting = gm[1].split('\n')[0].trim();
  return {
    script,
    greeting,
    variableDefinitions: parseScriptVariablesFromSections(sections),
  };
}

export function scriptVariablesSection(variables) {
  if (!variables?.length) return null;
  return {
    type: 'custom',
    title: SAAS_SCRIPT_VARIABLES_TITLE,
    order: 8,
    raw_text: JSON.stringify({ version: 1, variables }, null, 2),
    enabled: true,
  };
}

export function parseScriptVariablesFromSections(sections) {
  if (!Array.isArray(sections)) return [];
  const row = sections.find((s) => s.title === SAAS_SCRIPT_VARIABLES_TITLE);
  if (!row?.raw_text) return [];
  try {
    const parsed = JSON.parse(row.raw_text);
    return Array.isArray(parsed?.variables) ? parsed.variables : [];
  } catch {
    return [];
  }
}

export function voiceConfigSection(voice, languageCode) {
  const realtimeVoice = voice?.realtimeVoice || voice?.voiceId || 'marin';
  return {
    type: 'custom',
    title: 'saas_voice_config',
    order: 5,
    raw_text: JSON.stringify(
      {
        realtimeVoice,
        voiceId: realtimeVoice,
        speed: voice?.speed ?? 1,
        language: languageCode || voice?.language || 'te-IN',
        turnDetection: 'semantic_vad',
        noiseReduction: 'far_field',
      },
      null,
      0
    ),
    enabled: true,
  };
}

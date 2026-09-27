/**
 * Map Voxly Agent Studio fields → Business Brain API (draft + publish).
 */
import { api } from './api';
import {
  SAAS_CALLING_SCRIPT_TITLE,
  scriptVariablesSection,
  voiceConfigSection,
} from '../lib/voiceStack';

function voiceSection(voice, language) {
  if (!voice && !language) return null;
  const lines = [];
  if (language) lines.push(`Language: ${language}`);
  if (voice) {
    lines.push(`Voice style: ${voice.voiceName || voice.voiceId || 'default'}`);
    if (voice.speed != null) lines.push(`Speed: ${voice.speed}`);
    if (voice.pitch != null) lines.push(`Pitch: ${voice.pitch}`);
    if (voice.stability != null) lines.push(`Stability: ${voice.stability}`);
  }
  return {
    type: 'custom',
    title: 'Voice profile (console)',
    order: 15,
    raw_text: lines.join('\n'),
    enabled: true,
  };
}

function routingSection(inboundRouting) {
  if (!inboundRouting) return null;
  return {
    type: 'custom',
    title: 'Inbound routing prefs (console)',
    order: 55,
    raw_text: JSON.stringify(inboundRouting, null, 2),
    enabled: true,
  };
}

function sectionsFromStudio({
  script,
  greeting,
  boundaries,
  objectionRules,
  role,
  voice,
  language,
  inboundRouting,
  variableDefinitions,
}) {
  const guardrails = (boundaries || []).map((b) => `- ${b}`).join('\n');
  const faq = (objectionRules || [])
    .map((o) => `When: ${o.trigger}\nReply: ${o.response}`)
    .join('\n\n');
  const callingScript = [greeting ? `OPENING LINE\n${greeting.trim()}` : '', (script || '').trim()]
    .filter(Boolean)
    .join('\n\n');
  const langCode =
    typeof language === 'string' && language.includes('-')
      ? language
      : language || 'en-IN';
  const varSection = scriptVariablesSection(variableDefinitions);
  const voiceSec = voiceConfigSection(voice, langCode);
  const sections = [
    ...(voiceSec ? [{ ...voiceSec, enabled: false }] : []),
    ...(varSection ? [{ ...varSection, enabled: false }] : []),
    {
      type: 'identity_purpose',
      title: 'Identity & Purpose',
      order: 10,
      raw_text:
        'You are a live phone agent for this business. Follow the Calling script section exclusively.',
      enabled: true,
    },
    {
      type: 'facts',
      title: SAAS_CALLING_SCRIPT_TITLE,
      order: 20,
      raw_text: callingScript || script || '',
      enabled: true,
    },
    {
      type: 'guardrails',
      title: 'Guardrails',
      order: 30,
      raw_text: guardrails || 'Do not invent prices or policies not in the script.',
      enabled: true,
    },
    { type: 'faq', title: 'FAQ & Objections', order: 40, raw_text: faq || '', enabled: !!faq },
  ];
  const v = voiceSection(voice, language);
  if (v) sections.push(v);
  const r = routingSection(inboundRouting);
  if (r) sections.push(r);
  return sections;
}

export async function loadAgentBrain(agentId) {
  const data = await api.request('GET', `/api/agents/${agentId}/business-brain`);
  return data;
}

export async function saveAndPublishAgentBrain(agentId, studioFields) {
  const existing = await loadAgentBrain(agentId).catch(() => null);
  const base = existing?.draft?.sections?.length
    ? existing.draft.sections
    : sectionsFromStudio(studioFields);
  const byType = {};
  for (const s of base) {
    byType[s.type] = s;
  }
  const seeds = sectionsFromStudio(studioFields);
  const merged = seeds.map((seed) => {
    const prev = existing?.draft?.sections?.find(
      (s) => s.type === seed.type && s.title === seed.title
    );
    return prev
      ? { ...prev, raw_text: seed.raw_text, enabled: seed.enabled }
      : { ...seed, section_id: seed.section_id || crypto.randomUUID() };
  });
  await api.request('PUT', `/api/agents/${agentId}/business-brain/draft`, { sections: merged });
  return await api.request('POST', `/api/agents/${agentId}/business-brain/publish`);
}

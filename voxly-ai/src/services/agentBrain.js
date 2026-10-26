/**
 * Map Voxly Agent Studio fields → Business Brain API (draft + publish).
 */
import { api } from './api';
import {
  SAAS_CALLING_SCRIPT_TITLE,
  scriptVariablesSection,
  voiceConfigSection,
} from '../lib/voiceStack';

const reviewedDrafts = new Map();

function studioFingerprint(fields) {
  return JSON.stringify(fields);
}

function assertCurrentRevision(existing, fields) {
  const revision = existing?.draft?.revision;
  if (!revision) throw new Error('Reload the agent before reviewing or publishing its script.');
  if (fields.brainRevision && fields.brainRevision !== revision) {
    throw new Error('This draft changed in another editor. Reload it before publishing; your edits have been kept.');
  }
  return revision;
}

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
    enabled: false,
  };
}

function routingSection(inboundRouting) {
  if (!inboundRouting) return null;
  return {
    type: 'custom',
    title: 'Inbound routing prefs (console)',
    order: 55,
    raw_text: JSON.stringify(inboundRouting, null, 2),
    enabled: false,
  };
}

function sectionsFromStudio({
  script,
  greeting,
  farewell,
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
    .map((o, index) => {
      if (!String(o.trigger || '').trim() || !String(o.response || '').trim()) {
        throw new Error(`Complete the concern and response in objection rule ${index + 1}, or remove that rule.`);
      }
      const intentPart = o.category && o.category !== 'custom' ? `[Intent: ${o.category}]\n` : '';
      const actionPart = o.action && o.action !== 'continue_script' ? `\nAction: ${o.action}` : '';
      return `${intentPart}When: ${o.trigger}\nReply: ${o.response}${actionPart}`;
    })
    .join('\n\n');
  // Strip any legacy OPENING LINE artifact so it never clashes with CANONICAL OPENING
  let cleanScript = (script || '')
    .replace(/^OPENING LINE\s*\n[^\n]*\n*/i, '')
    .trim();

  // If greeting is present and script lacks CANONICAL OPENING, add CANONICAL OPENING cleanly once
  const hasCanonical = /(?:^|\n)(?:---|##)\s*CANONICAL OPENING\s*(?:---|##)?/i.test(cleanScript);
  if (!hasCanonical && greeting && greeting.trim()) {
    cleanScript = `--- CANONICAL OPENING ---\nAfter the callee speaks, say once:\n${greeting.trim()}\n\n${cleanScript}`.trim();
  }
  const callingScript = cleanScript;
  const langCode =
    typeof language === 'string' && language.includes('-')
      ? language
      : language || 'en-IN';
  const varSection = scriptVariablesSection(variableDefinitions);
  const voiceSec = voiceConfigSection(voice, langCode);
  const sections = [
    {
      type: 'custom', title: 'saas_call_end_policy', order: 25,
      raw_text: JSON.stringify({ farewell: String(farewell || '').trim() }), enabled: false,
    },
    ...(voiceSec ? [{ ...voiceSec, enabled: false }] : []),
    ...(varSection ? [{ ...varSection, enabled: false }] : []),
    {
      type: 'identity_purpose',
      title: 'Identity & Purpose',
      order: 10,
      // The greeting lives here as well as being pinned into the script section.
      // Writing it in only one place meant the editor could never read it back:
      // the loader looks for this exact line, and without it the greeting was
      // absorbed into the script body and duplicated on every save.
      raw_text: [
        'You are a professional live phone agent for this business. Follow the calling script and supplied business facts within platform safety and tool permissions.',
        greeting ? `Opening greeting: ${String(greeting).split('\n')[0].trim()}` : '',
      ]
        .filter(Boolean)
        .join('\n'),
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
    { type: 'faq', title: 'FAQ & Objections', order: 40, raw_text: faq ? `Adapt these replies naturally to the selected call language with everyday English mixing. Respect refusals; these suggestions do not override safety or tool permissions. Actions need an available tool and successful result; never claim a transfer or callback booking without confirmation.\n\n${faq}` : '', enabled: !!faq },
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

export function mergeStudioSections(existingSections, studioFields) {
  const base = Array.isArray(existingSections) ? existingSections : [];
  const seeds = sectionsFromStudio(studioFields);
  const metadataTitles = new Set(['saas_voice_config', 'saas_script_variables', 'saas_call_end_policy', 'Voice profile (console)', 'Inbound routing prefs (console)']);
  const replaced = new Set();
  const merged = seeds.map((seed) => {
    let prev = base.find((s) => s.type === seed.type && s.title === seed.title);
    if (!prev && seed.title === SAAS_CALLING_SCRIPT_TITLE) {
      prev = base.find((s) => s.enabled !== false && s.type === 'facts' && ['Agent script', 'Business Facts'].includes(s.title));
    }
    if (prev) replaced.add(prev);
    // Identity notes are not exposed in this editor. Only replace its greeting.
    if (prev?.raw_text && seed.type === 'identity_purpose') {
      const body = String(prev.raw_text).replace(/^Opening greeting:.*(?:\n|$)/gim, '').trim()
        .replace('You are a live phone agent for this business. Follow the Calling script section exclusively.', 'You are a professional live phone agent for this business. Follow the calling script and supplied business facts within platform safety and tool permissions.');
      seed.raw_text = [body, studioFields.greeting ? `Opening greeting: ${String(studioFields.greeting).split('\n')[0].trim()}` : ''].filter(Boolean).join('\n');
    }
    if (prev?.raw_text && seed.type === 'faq') {
      // Preserve free-form FAQ notes which the concern/response controls cannot edit.
      const reference = String(prev.raw_text).split(/\n\s*\n/).filter((block) =>
        !/(?:^|\n)(?:When(?: caller says)?|Reply|Response):/i.test(block) &&
        !block.startsWith('Adapt these replies naturally to the selected call language')).join('\n\n');
      if (reference.trim()) {
        seed.raw_text = [reference.trim(), seed.raw_text].filter(Boolean).join('\n\n');
        seed.enabled = true;
      }
    }
    return prev
      ? { ...prev, title: seed.title, raw_text: seed.raw_text, enabled: seed.enabled }
      : { ...seed, section_id: seed.section_id || crypto.randomUUID() };
  });
  return [...merged, ...base.filter((section) => !replaced.has(section) && !metadataTitles.has(section.title))];
}

export async function reviewAgentBrain(agentId, studioFields) {
  const existing = await loadAgentBrain(agentId);
  const revision = assertCurrentRevision(existing, studioFields);
  const sections = mergeStudioSections(existing?.draft?.sections, studioFields);
  const review = await api.request('POST', `/api/agents/${agentId}/business-brain/preview`, { sections });
  reviewedDrafts.set(agentId, { fingerprint: studioFingerprint(studioFields), revision, sections, review });
  return review;
}

export async function saveAndPublishAgentBrain(agentId, studioFields) {
  let reviewed = reviewedDrafts.get(agentId);
  if (!reviewed || reviewed.fingerprint !== studioFingerprint(studioFields)) {
    await reviewAgentBrain(agentId, studioFields);
    reviewed = reviewedDrafts.get(agentId);
  }
  if (!reviewed.review.ok) throw new Error('Resolve the blocking script issues before publishing.');
  const saved = await api.request('PUT', `/api/agents/${agentId}/business-brain/draft`, {
    sections: reviewed.sections, expected_revision: reviewed.revision,
  });
  const publication = await api.request('POST', `/api/agents/${agentId}/business-brain/publish`, {
    expected_revision: saved.revision,
  });
  reviewedDrafts.delete(agentId);
  return { ...publication, draft_revision: saved.revision };
}

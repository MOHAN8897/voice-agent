/**
 * Studio Script Helpers — Variable interpolation with fallback syntax,
 * dynamic system tokens, sample leads catalog, and objection presets.
 */

const SCRIPT_VARIABLE_GROUPS = [
  {
    id: 'contact',
    title: 'Contact Personalization',
    variables: [
      { label: 'First Name', key: 'contact.first_name', token: '{{contact.first_name}}', fallbackToken: '{{contact.first_name | there}}' },
      { label: 'Last Name', key: 'contact.last_name', token: '{{contact.last_name}}' },
      { label: 'Full Name', key: 'contact.full_name', token: '{{contact.full_name}}', fallbackToken: '{{contact.full_name | customer}}' },
      { label: 'Company', key: 'contact.company', token: '{{contact.company}}', fallbackToken: '{{contact.company | your company}}' },
      { label: 'Job Title', key: 'contact.job_title', token: '{{contact.job_title}}' },
      { label: 'City', key: 'contact.city', token: '{{contact.city}}', fallbackToken: '{{contact.city | your area}}' },
      { label: 'State', key: 'contact.state', token: '{{contact.state}}' },
      { label: 'Country', key: 'contact.country', token: '{{contact.country}}' },
      { label: 'Phone', key: 'contact.phone', token: '{{contact.phone}}' },
      { label: 'Email', key: 'contact.email', token: '{{contact.email}}' },
      { label: 'Notes', key: 'contact.notes', token: '{{contact.notes}}' },
    ],
  },
  {
    id: 'system',
    title: 'Dynamic Time & System Context',
    variables: [
      { label: 'Time of Day', key: 'system.time_of_day', token: '{{system.time_of_day}}' },
      { label: 'Day of Week', key: 'system.day_of_week', token: '{{system.day_of_week}}' },
      { label: 'Current Date', key: 'system.date', token: '{{system.date}}' },
    ],
  },
  {
    id: 'custom',
    title: 'Custom Fields',
    variables: [
      { label: 'Product', key: 'contact.custom_fields.product', token: '{{contact.custom_fields.product}}', fallbackToken: '{{contact.custom_fields.product | our service}}' },
      { label: 'Appointment Date', key: 'contact.custom_fields.appointment_date', token: '{{contact.custom_fields.appointment_date}}', fallbackToken: '{{contact.custom_fields.appointment_date | scheduled time}}' },
      { label: 'Balance', key: 'contact.custom_fields.balance', token: '{{contact.custom_fields.balance}}' },
      { label: 'Lead Type', key: 'contact.custom_fields.lead_type', token: '{{contact.custom_fields.lead_type}}', fallbackToken: '{{contact.custom_fields.lead_type | general}}' },
    ],
  },
];

export function getScriptVariableGroups(useFallbackSyntax = true) {
  return SCRIPT_VARIABLE_GROUPS.map((group) => ({
    ...group,
    variables: group.variables.map((variable) => ({
      ...variable,
      token: useFallbackSyntax && variable.fallbackToken ? variable.fallbackToken : variable.token,
    })),
  }));
}

export function findScriptVariableTrigger(value, cursor) {
  const text = String(value || '');
  const position = Math.max(0, Math.min(Number(cursor) || 0, text.length));
  const beforeCursor = text.slice(0, position);
  const atIndex = beforeCursor.lastIndexOf('@');
  if (atIndex < 0) return null;

  const previous = atIndex > 0 ? beforeCursor[atIndex - 1] : '';
  const query = beforeCursor.slice(atIndex + 1);
  if ((previous && !/[\s([{"'`]/.test(previous)) || !/^[a-zA-Z0-9_.-]*$/.test(query)) return null;

  return { start: atIndex, end: position, query };
}

export function filterScriptVariables(groups, query = '') {
  const needle = String(query).trim().toLowerCase();
  return (groups || []).flatMap((group) => (group.variables || []).map((variable) => ({
    ...variable,
    groupTitle: group.title,
  }))).filter((variable) => !needle ||
    variable.label.toLowerCase().includes(needle) ||
    variable.key.toLowerCase().includes(needle) ||
    variable.token.toLowerCase().includes(needle));
}

export function replaceScriptVariableTrigger(text, trigger, variable) {
  const current = String(text || '');
  const start = Math.max(0, Math.min(trigger?.start ?? current.length, current.length));
  const end = Math.max(start, Math.min(trigger?.end ?? start, current.length));
  const token = String(variable?.token || '');
  const nextText = current.slice(0, start) + token + current.slice(end);
  const cursor = start + token.length;
  return { text: nextText, cursor };
}

export const OBJECTION_PRESETS = [
  {
    id: 'price',
    label: '💰 Price / Budget',
    category: 'price',
    trigger: 'Too expensive / We do not have the budget right now',
    response: 'I understand. I can explain the approved pricing and what it covers. Which part would you like to clarify?',
    action: 'continue_script',
  },
  {
    id: 'busy',
    label: '⏰ Busy / Bad Time',
    category: 'timing',
    trigger: 'I am busy right now / In a meeting / Call me later',
    response: 'No problem. What time would suit you for a callback?',
    action: 'offer_callback',
  },
  {
    id: 'trust',
    label: '🤝 Trust / AI Query',
    category: 'trust',
    trigger: 'Are you an AI?',
    response: 'Yes, I am an AI assistant representing this business. What would you like to know?',
    action: 'continue_script',
  },
  {
    id: 'competitor',
    label: '🏢 Competitor / Vendor',
    category: 'competitor',
    trigger: 'We are already using another vendor / Happy with current provider',
    response: 'Understood. If you are happy with your current provider, I respect that.',
    action: 'continue_script',
  },
  {
    id: 'not_interested',
    label: '🛑 Not Interested',
    category: 'not_interested',
    trigger: 'Not interested / Please remove me from your list',
    response: 'Understood. Thank you for your time. Goodbye.',
    action: 'end_call',
  },
];

export const SAMPLE_LEADS = [
  {
    id: 'lead-1',
    name: 'Priya Sharma (Complete Lead)',
    badge: 'Complete Data',
    contact: {
      first_name: 'Priya',
      last_name: 'Sharma',
      full_name: 'Priya Sharma',
      phone: '+91 98765 43210',
      email: 'priya.sharma@example.com',
      company: 'Apex Technologies',
      city: 'Hyderabad',
      state: 'Telangana',
      country: 'India',
      notes: 'Interested in voice agent automation',
      custom_fields: {
        product: 'Voice Agent AI Pro',
        appointment_date: 'tomorrow at 3:00 PM',
        balance: '₹12,500',
        lead_type: 'High Priority',
      },
    },
  },
  {
    id: 'lead-2',
    name: 'Anonymous Lead (Missing Name & Company)',
    badge: 'Tests Fallbacks',
    contact: {
      first_name: '',
      last_name: '',
      full_name: '',
      phone: '+91 91234 56789',
      email: 'lead@domain.com',
      company: '',
      city: 'Bengaluru',
      state: 'Karnataka',
      country: 'India',
      notes: '',
      custom_fields: {},
    },
  },
];

export function renderScriptPreview(template, contact) {
  if (!template) return '';
  const now = new Date();
  const hour = now.getHours();
  const timeOfDay = hour < 12 ? 'morning' : hour < 17 ? 'afternoon' : 'evening';
  const dayOfWeek = now.toLocaleDateString('en-US', { weekday: 'long' });
  const dateStr = now.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });

  const systemVars = {
    'system.time_of_day': timeOfDay,
    'system.day_of_week': dayOfWeek,
    'system.date': dateStr,
  };

  return template.replace(/\{\{\s*([a-zA-Z0-9_.]+)(?:\s*(?:\||\|\|)\s*([^}]+?))?\s*\}\}/g, (_match, path, fallback) => {
    const cleanFallback = fallback !== undefined ? fallback.trim().replace(/^['"]|['"]$/g, '') : '';
    if (path in systemVars) {
      return systemVars[path];
    }
    let val = undefined;
    if (path.startsWith('contact.')) {
      const sub = path.substring(8);
      if (sub.startsWith('custom_fields.')) {
        const cfKey = sub.substring(14);
        val = contact?.custom_fields?.[cfKey];
      } else {
        val = contact?.[sub];
      }
    } else if (contact && path in contact) {
      val = contact[path];
    }
    if (val !== undefined && val !== null && String(val).trim() !== '') {
      return String(val).trim();
    }
    if (cleanFallback !== '') {
      return cleanFallback;
    }
    return `[Missing: ${path}]`;
  });
}

export function parseObjectionRulesFromSections(sections) {
  if (!Array.isArray(sections)) return [];
  const faqRow = sections.find(
    (s) => s.enabled !== false && (s.type === 'faq' || s.title === 'FAQ & Objections')
  );
  if (!faqRow?.raw_text) return [];
  const blocks = String(faqRow.raw_text).split(/\n\s*\n/);
  const rules = [];
  for (const block of blocks) {
    const text = block.trim();
    if (!text) continue;
    const catMatch = text.match(/(?:\[Intent:\s*([^\]]+)\]|^Category:\s*(.+))/im);
    const category = catMatch ? (catMatch[1] || catMatch[2] || '').trim() : 'custom';
    const trigMatch = text.match(/(?:When(?: caller says)?:\s*)([^\n]+)/i);
    const trigger = trigMatch ? trigMatch[1].trim() : '';
    const respMatch = text.match(/(?:(?:Reply|Response):\s*)([^\n]+(?:\n(?!(?:When|Action|Follow-up|Category|\[Intent))[^\n]+)*)/i);
    const response = respMatch ? respMatch[1].trim() : '';
    const actMatch = text.match(/(?:(?:Follow-up Action|Action):\s*)([a-zA-Z0-9_]+)/i);
    const action = actMatch ? actMatch[1].trim() : 'continue_script';
    if (trigger || response) {
      rules.push({
        category,
        trigger: trigger || 'Customer concern...',
        response: response || '',
        action,
      });
    }
  }
  return rules;
}


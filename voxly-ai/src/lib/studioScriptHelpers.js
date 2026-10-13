/**
 * Studio Script Helpers — Variable interpolation with fallback syntax,
 * dynamic system tokens, sample leads catalog, and objection presets.
 */

export const OBJECTION_PRESETS = [
  {
    id: 'price',
    label: '💰 Price / Budget',
    category: 'price',
    trigger: 'Too expensive / We do not have the budget right now',
    response: 'I completely understand that budget is critical. Many clients felt the same initially until seeing a significant ROI within the first month. Could I share a quick 1-minute case study?',
    action: 'continue_script',
  },
  {
    id: 'busy',
    label: '⏰ Busy / Bad Time',
    category: 'timing',
    trigger: 'I am busy right now / In a meeting / Call me later',
    response: 'No problem at all, I caught you in the middle of your day. Would tomorrow morning or later in the afternoon work better for a brief 2-minute catch-up?',
    action: 'offer_callback',
  },
  {
    id: 'trust',
    label: '🤝 Trust / AI Query',
    category: 'trust',
    trigger: 'Are you an AI? / How did you get my contact information?',
    response: "Yes, I am Voxly's AI assistant calling on behalf of our team to quickly connect without keeping you on hold. You recently engaged with our platform. Do you have a brief moment?",
    action: 'continue_script',
  },
  {
    id: 'competitor',
    label: '🏢 Competitor / Vendor',
    category: 'competitor',
    trigger: 'We are already using another vendor / Happy with current provider',
    response: 'That is great to hear—most of our enterprise clients previously used legacy systems before moving to our zero-latency stack. What feature do you like most about your current setup?',
    action: 'continue_script',
  },
  {
    id: 'not_interested',
    label: '🛑 Not Interested',
    category: 'not_interested',
    trigger: 'Not interested / Please remove me from your list',
    response: 'Understood, thank you for letting me know. I will mark your number as do-not-contact right away. Have a wonderful rest of your day!',
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


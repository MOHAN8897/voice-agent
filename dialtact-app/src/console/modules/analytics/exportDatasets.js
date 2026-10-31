/**
 * What each export holds and which filters it takes. Filter `key`s are the query
 * names `GET /api/app/exports/{dataset}` reads; option values are the server's
 * tokens, labels are what the owner reads.
 */
export const EXPORT_ROW_LIMIT = 50000;

const CALL_OUTCOMES = [
  { value: 'answered', label: 'Answered' },
  { value: 'no_answer', label: 'No answer' },
  { value: 'busy', label: 'Busy' },
  { value: 'declined', label: 'Declined' },
  { value: 'unreachable', label: 'Unreachable' },
  { value: 'failed', label: 'Failed' },
  { value: 'voicemail', label: 'Voicemail' },
];

export const EXPORT_DATASETS = [
  {
    id: 'calls',
    label: 'Calls',
    description: 'Call history, including calls nobody answered.',
    filters: [
      { key: 'outcome', label: 'Outcome', options: CALL_OUTCOMES },
      { key: 'direction', label: 'Direction', options: [{ value: 'inbound', label: 'Incoming' }, { value: 'outbound', label: 'Outgoing' }] },
      { key: 'tags', type: 'tags' },
    ],
    agent: true,
  },
  {
    id: 'leads',
    label: 'Leads',
    description: 'Every lead with its stage, source and tags.',
    filters: [
      {
        key: 'stage',
        label: 'Stage',
        options: ['new', 'contacted', 'qualified', 'meeting_booked', 'converted', 'unqualified'].map((v) => ({
          value: v,
          label: { meeting_booked: 'Meeting booked' }[v] || v[0].toUpperCase() + v.slice(1),
        })),
      },
      { key: 'tags', type: 'tags' },
    ],
    agent: true,
  },
  {
    id: 'dnc',
    label: 'Do-not-call list',
    description: 'Numbers your agents will never call, with when and why they were added.',
    filters: [
      { key: 'status', label: 'Status', options: [{ value: 'active', label: 'On the list' }, { value: 'inactive', label: 'Removed' }, { value: 'all', label: 'All' }] },
      { key: 'source', label: 'Added by', options: [
        { value: 'operator_ui', label: 'Added by hand' }, { value: 'manual', label: 'Added by hand (older)' },
        { value: 'live_call_opt_out', label: 'Caller asked on a call' }, { value: 'bulk_upload', label: 'Upload' },
        { value: 'subscriber', label: 'Workspace API' },
      ] },
    ],
    agent: false,
  },
  {
    id: 'callbacks',
    label: 'Callback requests',
    description: 'Callers who asked to be called back.',
    filters: [
      { key: 'status', label: 'Status', options: [{ value: 'requested', label: 'Pending' }, { value: 'completed', label: 'Completed' }, { value: 'converted', label: 'Converted' }, { value: 'dismissed', label: 'Dismissed' }] },
    ],
    agent: true,
  },
  {
    id: 'language_callbacks',
    label: 'Language callbacks',
    description: 'Callers who asked to talk in another language.',
    filters: [
      { key: 'status', label: 'Status', options: [{ value: 'pending', label: 'Pending' }, { value: 'calling', label: 'Calling' }, { value: 'done', label: 'Done' }, { value: 'dismissed', label: 'Dismissed' }] },
      {
        key: 'language',
        label: 'Language',
        options: [
          ['te', 'Telugu'], ['hi', 'Hindi'], ['ta', 'Tamil'], ['kn', 'Kannada'], ['ml', 'Malayalam'],
          ['mr', 'Marathi'], ['bn', 'Bengali'], ['gu', 'Gujarati'], ['pa', 'Punjabi'], ['en-IN', 'English'],
        ].map(([value, label]) => ({ value, label })),
      },
    ],
    agent: true,
  },
  {
    id: 'followups',
    label: 'Follow-ups',
    description: 'Callbacks and recalls your agents planned.',
    filters: [
      { key: 'status', label: 'Result', options: [{ value: 'scheduled', label: 'Scheduled' }, { value: 'done', label: 'Done' }, { value: 'failed', label: 'Failed' }, { value: 'cancelled', label: 'Cancelled' }] },
      { key: 'kind', label: 'Kind', options: [{ value: 'callback', label: 'Callback' }, { value: 'missed', label: 'Missed call' }, { value: 'recall', label: 'Recall' }] },
    ],
    agent: true,
  },
  {
    id: 'wallet',
    label: 'Wallet transactions',
    description: 'Top-ups and charges on your wallet.',
    filters: [],
    agent: true,
  },
];

export function datasetById(id) {
  return EXPORT_DATASETS.find((d) => d.id === id) || EXPORT_DATASETS[0];
}

/** Turn dialog state into server query keys. Dates are IST calendar days. */
export function exportQuery({ range, since, until, agentId, values = {}, tags = [], tagMatch = 'any' }, dataset) {
  const q = {};
  if (range === 'custom') {
    q.range = 'custom';
    q.since = since;
    q.until = until;
  } else if (range && range !== 'all') {
    q.range = range;
  }
  if (dataset.agent && agentId) q.agentId = agentId;
  for (const f of dataset.filters) {
    if (f.type === 'tags') {
      if (tags.length) {
        q.tags = tags.join(',');
        q.tagMatch = tagMatch;
      }
    } else if (values[f.key]) {
      q[f.key] = values[f.key];
    }
  }
  return q;
}

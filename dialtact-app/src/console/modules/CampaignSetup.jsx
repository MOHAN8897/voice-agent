import React, { useEffect, useRef, useState } from 'react';
import { AlertCircle, CheckCircle2, FileSpreadsheet, Loader2, ShieldCheck, UploadCloud } from 'lucide-react';
import { api } from '../../services/api';
import { useWorkspace } from '../context/WorkspaceContext';
import { TactileButton } from '../ui/TactileButton';
import { showToast } from '../ui/ToastHost';
import { CallIntegrationPicker, IntegrationSelectionSummary, useCallIntegrationOptions } from '../ui/CallIntegrationPicker';
import { humanizeToken } from '../../lib/internalLabels';
import { relativeTime } from '../../lib/money';
import { useSessionDraft } from '../lib/sessionDraft';

const input = 'mt-1 w-full min-h-11 min-w-0 rounded-control border border-line-strong bg-surface px-3 py-2 text-base sm:text-ui text-ink placeholder:text-fg-subtle focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/15 disabled:opacity-50';
const fields = ['phone', 'full_name', 'first_name', 'last_name', 'email', 'company', 'job_title', 'country', 'city', 'state', 'timezone', 'notes', 'ignore'];
const countries = ['IN', 'US', 'GB', 'CA', 'AU', 'SG', 'AE', 'DE', 'FR', 'ZA', 'PH', 'NZ'];
const fileLimit = 5 * 1024 * 1024;
const pretty = (value) => value === 'ignore' ? 'Skip column' : `${humanizeToken(value)} · {{contact.${value}}}`;

function fileData(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error('Could not read this file. Choose it again.'));
    reader.readAsDataURL(file);
  });
}

export function CampaignSetup({ initialAgentId = '', initialContacts = [], initialSource = '', draftKey = null, onComplete, onBusyChange }) {
  const { agents, phoneNumbers, outboundFromE164, createCampaign } = useWorkspace();
  // With a draftKey, the options typed so far survive switching tabs or pages (this
  // browser tab only) and are cleared on launch or save. A chosen file and the
  // contact check are not kept: the file must be picked again, then re-checked.
  const fromLeads = initialContacts.length > 0;
  const [draft, patchDraft, resetDraft] = useSessionDraft(draftKey && !fromLeads ? 'campaign-setup' : null, draftKey, {
    config: { name: '', description: '', agentId: initialAgentId || '', fromE164: '', defaultCountry: 'IN' },
    source: initialSource || 'upload',
    text: '',
    listId: '',
    dateRangeEnabled: false,
    dateRange: { startsAt: '', expiresAt: '' },
    duplicateStrategy: 'keep_first',
    pacing: { concurrency: 3, maxAttempts: 2, retryDelayMinutes: 30 },
    windowEnabled: true,
    callingWindow: { start: '09:00', end: '18:00', timezone: 'Asia/Kolkata' },
    integrations: null,
    integrationsAgentId: '',
  });
  const draftSetter = (field) => (value) =>
    patchDraft((prev) => ({ [field]: typeof value === 'function' ? value(prev[field]) : value }));
  const config = {
    ...draft.config,
    agentId: draft.config.agentId || initialAgentId || agents[0]?.id || '',
    fromE164: draft.config.fromE164 || outboundFromE164 || '',
  };
  const setConfig = (fn) => patchDraft((prev) => ({ config: typeof fn === 'function' ? fn(prev.config) : fn }));
  const source = fromLeads ? 'leads' : draft.source;
  const setSource = draftSetter('source');
  const [audience, setAudience] = useState({ jobs: [], total: 0 });
  const [audienceSelected, setAudienceSelected] = useState([]);
  const [audienceLoading, setAudienceLoading] = useState(false);
  const [audienceError, setAudienceError] = useState('');
  const [audienceReload, setAudienceReload] = useState(0);
  const { dateRangeEnabled, dateRange, text, listId, duplicateStrategy, pacing, windowEnabled, callingWindow } = draft;
  const setDateRangeEnabled = draftSetter('dateRangeEnabled');
  const setDateRange = draftSetter('dateRange');
  const [file, setFile] = useState(null);
  const setText = draftSetter('text');
  const [lists, setLists] = useState([]);
  const setListId = draftSetter('listId');
  const [listError, setListError] = useState('');
  const [parsed, setParsed] = useState(null);
  const [mapping, setMapping] = useState({});
  const [validation, setValidation] = useState(null);
  const [variables, setVariables] = useState(null);
  const setDuplicateStrategy = draftSetter('duplicateStrategy');
  const [variablePolicy, setVariablePolicy] = useState('review');
  const [consent, setConsent] = useState(false);
  const setPacing = draftSetter('pacing');
  const setWindowEnabled = draftSetter('windowEnabled');
  const setCallingWindow = draftSetter('callingWindow');
  const [previewIndex, setPreviewIndex] = useState(0);
  // Integrations every campaign call may use; null keeps the agent's saved settings.
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('');
  const lock = useRef(false);
  const creationId = useRef(crypto.randomUUID());
  const lastValidated = useRef(null);
  const errorRef = useRef(null);
  const currentAgent = config.agentId || initialAgentId || agents[0]?.id || '';
  const outbound = phoneNumbers.filter((n) => n.outboundEnabled !== false && !['released', 'pending', 'failed'].includes(n.status));
  const agent = agents.find((a) => a.id === currentAgent);
  const followupSource = source === 'callbacks' || source === 'missed';
  const integrationOptions = useCallIntegrationOptions(currentAgent);
  // Integrations belong to the agent they were picked for.
  const integrations = draft.integrationsAgentId === currentAgent ? draft.integrations : null;
  const setIntegrations = (value) => patchDraft({ integrations: value, integrationsAgentId: currentAgent });

  useEffect(() => {
    if (!followupSource || !currentAgent) return;
    let active = true;
    setAudienceLoading(true); setAudienceError(''); setAudience({ jobs: [], total: 0 });
    setAudienceSelected([]); setParsed(null); setValidation(null); setVariables(null); setConsent(false);
    api.campaigns.followupAudience(currentAgent, source === 'missed' ? 'missed' : 'callback')
      .then((data) => { if (active) { setAudience(data); setAudienceError(data.unavailableReason || ''); } })
      .catch((err) => { if (active) setAudienceError(err.message || 'Could not load follow-ups. Retry to refresh the audience.'); })
      .finally(() => { if (active) setAudienceLoading(false); });
    return () => { active = false; };
  }, [followupSource, currentAgent, source, audienceReload]);

  useEffect(() => {
    let active = true;
    api.contacts.getLists().then((res) => { if (active) setLists(res.lists || []); })
      .catch(() => { if (active) setListError('Saved lists could not be loaded. You can upload or paste contacts.'); });
    return () => { active = false; };
  }, []);
  useEffect(() => { onBusyChange?.(Boolean(busy)); }, [busy, onBusyChange]);
  useEffect(() => { if (error) errorRef.current?.focus(); }, [error]);

  function invalidate() {
    setValidation(null); setVariables(null); setConsent(false); lastValidated.current = null;
    setVariablePolicy('review'); setPreviewIndex(0);
  }
  function changeSource(value) {
    setSource(value); setParsed(null); setMapping({}); setError(''); invalidate();
  }
  function changeConfig(key, value) {
    setConfig((prev) => ({ ...prev, [key]: value }));
    if (key === 'agentId' || key === 'defaultCountry') invalidate();
  }
  async function guarded(label, operation) {
    if (lock.current) return;
    lock.current = true; setBusy(label); setError('');
    try { await operation(); }
    catch (err) { setError(err.message || 'This action could not be completed. Please try again.'); }
    finally { lock.current = false; setBusy(''); }
  }

  async function normalize(data, selectedMapping) {
    if (!Object.values(selectedMapping).includes('phone')) throw new Error('Map one column to phone before validating.');
    const result = await api.contacts.normalizePreview({ rows: data.rows, mapping: selectedMapping,
      defaultCountry: config.defaultCountry, duplicateStrategy, sourceFileName: data.fileName });
    if (!Array.isArray(result.validContacts) || !Number.isSafeInteger(result.validCount) || !Number.isSafeInteger(result.totalRows)) {
      throw new Error('The contact check returned incomplete results. No campaign was created. Retry after refreshing.');
    }
    const variableResult = await api.campaigns.validateVariables(currentAgent, result.validContacts || []);
    setValidation(result); setVariables(variableResult); setConsent(false);
    lastValidated.current = { agentId: currentAgent, country: config.defaultCountry };
  }
  async function prepare() {
    await guarded('Checking contacts', async () => {
      if (!currentAgent) throw new Error('Choose an agent first.');
      invalidate();
      let data = parsed;
      let selectedMapping = mapping;
      if (!data) {
        if (followupSource) {
          const chosen = audience.jobs.filter((job) => audienceSelected.includes(job.jobId));
          if (!chosen.length) throw new Error('Select scheduled follow-ups for this campaign first.');
          const headers = ['phone', 'full_name', 'email', 'notes', 'timezone', 'custom_field:followup_job_id', 'custom_field:followup_kind'];
          const rows = chosen.map((job) => ({ ...job, 'custom_field:followup_job_id': job.jobId, 'custom_field:followup_kind': job.kind }));
          data = { rows, headers, totalRows: rows.length, fileName: 'scheduled-follow-ups' };
          selectedMapping = Object.fromEntries(headers.map((key) => [key, key]));
        } else if (source === 'leads') {
          const headers = ['phone', 'full_name', 'email', 'notes', 'custom_field:lead_id', 'custom_field:lead_stage'];
          data = { rows: initialContacts, headers, totalRows: initialContacts.length, fileName: 'selected-leads' };
          selectedMapping = Object.fromEntries(headers.map((key) => [key, key]));
        } else if (source === 'list') {
          if (!listId) throw new Error('Choose a saved list.');
          const response = await api.contacts.getListContacts(listId);
          const rows = (response.contacts || []).map((c) => ({ ...c, first_name: c.first_name || c.firstName || '',
            last_name: c.last_name || c.lastName || '', full_name: c.full_name || c.fullName || '',
            ...Object.fromEntries(Object.entries(c.custom_fields || c.customFields || {}).map(([key, value]) => [`custom_field:${key}`, value])) }));
          if (response.truncated || (response.totalContacts && response.totalContacts > rows.length)) throw new Error('This list exceeds the import limit. Split it into smaller lists.');
          const headers = [...fields.filter((f) => f !== 'ignore'), ...new Set(rows.flatMap((row) => Object.keys(row).filter((key) => key.startsWith('custom_field:'))))];
          data = { rows, headers, totalRows: rows.length, fileName: 'saved-list', previewRows: rows.slice(0, 5) };
          selectedMapping = Object.fromEntries(headers.map((f) => [f, f]));
        } else {
          if (source === 'upload' && !file) throw new Error('Choose a CSV or .xlsx file.');
          if (source === 'upload' && file && file.size > fileLimit) throw new Error('Choose a file smaller than 5 MB.');
          if (source === 'paste' && !text.trim()) throw new Error('Paste a CSV with a phone column and at least one contact.');
          data = await api.contacts.parse(source === 'upload' ? { fileName: file.name, contentBase64: await fileData(file) } : { fileName: 'pasted.csv', rawText: text });
          if (!data.rows || data.rows.length !== data.totalRows) throw new Error('The server returned an incomplete import. No campaign was created. Refresh after updating the server.');
          selectedMapping = Object.fromEntries(Object.entries(data.detectedMappings || {}).map(([key, value]) => [key, (value.field || value.targetField || 'ignore').replace(/^custom_fields\./, 'custom_field:')]));
        }
        if (!data.rows?.length) throw new Error('No contact rows were found. Include column headers in your file.');
        if (data.rows.length > 10000) throw new Error('Split this import into batches of 10,000 contacts or fewer.');
        setParsed(data); setMapping(selectedMapping);
      }
      await normalize(data, selectedMapping);
    });
  }

  async function submit(autoStart) {
    await guarded(autoStart ? 'Launching campaign' : 'Saving draft', async () => {
      if (!config.name.trim()) throw new Error('Enter a campaign name.');
      if (!validation?.validCount || !consent || !lastValidated.current || lastValidated.current.agentId !== currentAgent) throw new Error('Validate contacts and confirm calling authorization first.');
      if (windowEnabled && callingWindow.start === callingWindow.end) throw new Error('Calling window start and end must differ.');
      let contacts = validation.validContacts.map((c) => ({ ...c, custom_fields: { ...(c.custom_fields || {}) } }));
      const missing = Object.keys(variables?.missing_breakdown || {});
      if (missing.length && variablePolicy === 'review') throw new Error('Choose how to handle contacts with missing script variables.');
      if (missing.length && variablePolicy === 'skip') {
        const excluded = new Set(variables?.missing_contact_indices || []);
        contacts = contacts.filter((_contact, index) => !excluded.has(index));
      }
      if (!contacts.length) throw new Error('No contacts remain after applying the variable policy.');
      let dates = {};
      if (dateRangeEnabled) {
        if (!dateRange.startsAt || !dateRange.expiresAt) throw new Error('Choose the campaign start and expiry.');
        const start = new Date(dateRange.startsAt), end = new Date(dateRange.expiresAt);
        if (!Number.isFinite(start.getTime()) || !Number.isFinite(end.getTime()) || end <= start || end <= new Date()) throw new Error('Choose an expiry after the start and the current time.');
        dates = { startsAt: start.toISOString(), expiresAt: end.toISOString() };
      }
      const followupJobIds = followupSource ? contacts.map((contact) => contact.custom_fields?.followup_job_id).filter(Boolean) : undefined;
      if (followupSource && followupJobIds.length !== contacts.length) throw new Error('Follow-up references were lost during validation. Refresh the audience and try again.');
      const created = await createCampaign({ clientRequestId: creationId.current, ...config, agentId: currentAgent, expectedScriptVersion: variables?.scriptVersion, ...pacing, ...dates,
        contacts: followupSource ? [] : contacts, followupJobIds, autoStart,
        callingWindow: windowEnabled ? callingWindow : undefined, consentConfirmed: consent, dndScrubEnabled: true,
        integrations: integrations || undefined });
      const excluded = created.dndExcludedCount || 0;
      showToast(created.status === 'running' ? `Campaign queued: ${Math.max(0, created.totalContacts - excluded)} eligible contacts.` : 'Campaign saved as a draft.', 'success');
      resetDraft();
      onComplete?.(created);
    });
  }

  const missing = Object.keys(variables?.missing_breakdown || {});
  const contactsReady = Math.max(0, (validation?.validCount || 0) - (variablePolicy === 'skip' ? variables?.missing_contact_indices?.length || 0 : 0));
  const ready = Boolean(config.name.trim() && currentAgent && contactsReady && consent && !variables?.invalid_placeholders?.length && (!missing.length || variablePolicy !== 'review'));
  const preview = variables?.previews?.[previewIndex] || variables?.previews?.[0];
  return (
    <div className="grid min-w-0 gap-6 lg:grid-cols-[minmax(0,1fr)_19rem]" data-testid="campaign-setup">
      <fieldset disabled={Boolean(busy)} className="min-w-0 space-y-6">
        <section className="space-y-4" aria-labelledby="campaign-details-heading">
          <div><h3 id="campaign-details-heading" className="text-title text-ink">Campaign details</h3><p className="mt-1 text-copy text-fg-body">Choose who calls and which number your contacts see.</p></div>
          <label className="block text-ui font-medium text-ink">Campaign name<input className={input} maxLength={255} value={config.name} onChange={(e) => changeConfig('name', e.target.value)} placeholder="October customer follow-up" /></label>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block text-ui font-medium text-ink">Agent<select className={input} value={currentAgent} disabled={Boolean(initialAgentId)} onChange={(e) => changeConfig('agentId', e.target.value)}><option value="">Choose an agent</option>{agents.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</select></label>
            <label className="block text-ui font-medium text-ink">Calling number<select className={input} value={config.fromE164} onChange={(e) => changeConfig('fromE164', e.target.value)}><option value="">Agent’s own line</option>{outbound.map((n) => <option key={n.id} value={n.number || n.e164}>{n.number || n.e164}</option>)}</select></label>
          </div>
        </section>
        <div className="border-t border-line pt-5">
          <CallIntegrationPicker scope="campaign" agentId={currentAgent} value={integrations} onChange={setIntegrations}
            disabled={Boolean(busy)} options={integrationOptions} />
        </div>
        <section className="space-y-4 border-t border-line pt-5" aria-labelledby="campaign-contacts-heading">
          <div className="flex flex-wrap items-center justify-between gap-2"><h3 id="campaign-contacts-heading" className="text-title">Contacts</h3><span className="text-meta text-fg-muted">Up to 10,000 contacts · 5 MB</span></div>
          <div className="flex flex-wrap gap-2" role="group" aria-label="Contact source">{[...(initialContacts.length ? [['leads', 'Selected leads']] : []), ['upload', 'Upload file'], ['paste', 'Paste CSV'], ['list', 'Saved list'], ['callbacks', 'Callback requests'], ['missed', 'Missed calls']].map(([key, label]) => <button key={key} type="button" aria-pressed={source === key} onClick={() => changeSource(key)} className={`min-h-11 rounded-pill border px-4 text-ui font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent ${source === key ? 'border-accent bg-accent-soft text-accent-fg' : 'border-line bg-surface text-fg-body hover:border-line-strong hover:text-ink'}`}>{label}</button>)}</div>
          {followupSource && <div className="space-y-3 rounded-control border border-line bg-canvas p-4" data-testid="campaign-followup-audience">
            <p className="text-copy">Use this agent’s scheduled follow-ups. Check unclear times in Leads first. The caller’s requested time, the agent’s permission, the do-not-call list and your wallet are still checked, and nobody is called twice for the same follow-up.</p>
            <div className="flex flex-wrap items-center justify-between gap-2"><span className="text-meta text-fg-muted">{audienceSelected.length} selected · showing {audience.jobs.length} of {audience.total} available</span><TactileButton variant="secondary" size="sm" disabled={audienceLoading} onClick={() => setAudienceReload((value) => value + 1)}>Refresh audience</TactileButton></div>
            {audienceLoading && <p role="status" className="text-copy">Loading scheduled follow-ups…</p>}
            {audienceError && <p role="alert" className="text-copy text-warning-fg">{audienceError}</p>}
            {!audienceLoading && !audienceError && !audience.jobs.length && <p className="text-copy text-fg-muted">No scheduled follow-ups yet. Turn on follow-ups in the agent’s settings, then check their times in Leads.</p>}
            {audience.jobs.length > 0 && <><label className="flex min-h-11 items-center gap-2 text-copy"><input type="checkbox" checked={audience.jobs.every((job) => audienceSelected.includes(job.jobId))} onChange={(event) => { setAudienceSelected(event.target.checked ? audience.jobs.map((job) => job.jobId) : []); setParsed(null); invalidate(); }} />Select all visible follow-ups</label><ul className="max-h-72 divide-y divide-line overflow-auto">{audience.jobs.map((job) => <li key={job.jobId}><label className="flex min-h-11 items-start gap-3 py-3 text-copy"><input type="checkbox" className="mt-1 shrink-0" aria-label={`Select follow-up ${job.phone}`} checked={audienceSelected.includes(job.jobId)} onChange={() => { setAudienceSelected((ids) => ids.includes(job.jobId) ? ids.filter((id) => id !== job.jobId) : [...ids, job.jobId]); setParsed(null); invalidate(); }} /><span className="min-w-0 break-words"><span className="font-medium">{job.full_name || job.phone}</span><span className="mt-1 block text-meta text-fg-muted"><span title={new Date(job.dueAt).toLocaleString('en-IN')}>Not before {relativeTime(job.dueAt)}</span> · {job.timezone || 'saved timezone'}</span></span></label></li>)}</ul></>}
          </div>}
          {source === 'leads' && <div className="rounded-control border border-line bg-canvas p-4 text-copy" data-testid="campaign-selected-leads">
            <p className="font-semibold">{initialContacts.length} selected {initialContacts.length === 1 ? 'lead' : 'leads'}</p>
            <p className="mt-1 text-fg-body">Names, numbers, email and notes come with them. Validate the contacts before saving or launching.</p>
            <ul className="mt-3 space-y-1">{initialContacts.slice(0, 5).map((contact) => <li key={contact['custom_field:lead_id']}>{contact.full_name} · <span className="font-mono tabular-nums">{contact.phone}</span></li>)}</ul>
          </div>}
          {source === 'upload' && <label className="flex cursor-pointer flex-col items-center gap-2 rounded-control border border-dashed border-line-strong bg-canvas p-6 text-center"><UploadCloud className="h-6 w-6 text-accent" /><span className="text-copy font-semibold">{file?.name || 'Choose a contact spreadsheet'}</span><span className="text-meta text-fg-muted">CSV or Excel (.xlsx), with a header row</span><input type="file" accept=".csv,.xlsx" aria-label="Contact spreadsheet" className="max-w-full text-copy" onChange={(e) => { setFile(e.target.files?.[0] || null); setParsed(null); invalidate(); }} /></label>}
          {source === 'paste' && <label className="block text-ui font-medium text-ink">CSV contacts<textarea className={`${input} min-h-36 font-mono`} value={text} maxLength={5 * 1024 * 1024} placeholder={'phone,full_name\n+12025550101,Example Contact'} onChange={(e) => { setText(e.target.value); setParsed(null); invalidate(); }} /></label>}
          {source === 'list' && <label className="block text-ui font-medium text-ink">Contact list<select className={input} value={listId} onChange={(e) => { setListId(e.target.value); setParsed(null); invalidate(); }}><option value="">Choose a list</option>{lists.map((list) => <option key={list.id} value={list.id}>{list.name} ({list.totalContacts ?? list.total_contacts ?? 0})</option>)}</select>{listError && <span role="status" className="mt-2 block text-meta text-warning-fg">{listError}</span>}</label>}
          <div className="grid gap-4 sm:grid-cols-2"><label className="block text-ui font-medium text-ink">Country for local numbers<select className={input} value={config.defaultCountry} onChange={(e) => changeConfig('defaultCountry', e.target.value)}>{countries.map((code) => <option key={code} value={code}>{new Intl.DisplayNames(['en'], { type: 'region' }).of(code)}</option>)}</select></label><label className="block text-ui font-medium text-ink">Duplicate numbers<select className={input} value={duplicateStrategy} onChange={(e) => { setDuplicateStrategy(e.target.value); invalidate(); }}><option value="keep_first">Keep first contact</option><option value="keep_last">Keep last contact</option><option value="remove">Skip all duplicates</option><option value="merge">Merge duplicate contact fields</option></select></label></div>
          {parsed && <details className="rounded-control border border-line p-3"><summary className="min-h-8 cursor-pointer text-copy font-semibold">Column mapping · {parsed.totalRows.toLocaleString()} {parsed.totalRows === 1 ? 'row' : 'rows'} loaded</summary><div className="mt-3 space-y-3">{parsed.warnings?.map((warning, i) => <p key={i} className="break-words text-meta text-warning-fg">{warning}</p>)}{parsed.headers.map((header) => <label key={header} className="grid min-w-0 items-center gap-1 text-copy sm:grid-cols-2"><span className="break-words">{header}</span><select className={input} aria-label={`Map ${header}`} value={mapping[header] || 'ignore'} onChange={(e) => { setMapping((prev) => ({ ...prev, [header]: e.target.value })); invalidate(); }}>{fields.map((key) => <option key={key} value={key}>{pretty(key)}</option>)}<option value={`custom_field:${header.toLowerCase().replace(/[^a-z0-9_]/g, '_')}`}>Custom field: {header}</option>{mapping[header]?.startsWith('custom_field:') && <option value={mapping[header]}>Custom field: {humanizeToken(mapping[header].slice(13))}</option>}</select></label>)}</div></details>}
          <TactileButton variant="secondary" onClick={prepare} disabled={Boolean(busy)} icon={FileSpreadsheet}>{busy === 'Checking contacts' ? 'Checking contacts…' : validation ? 'Recheck contacts' : 'Validate contacts'}</TactileButton>
          {validation && <div role="status" className="space-y-3 rounded-control border border-success-line bg-success-soft p-4"><p className="flex items-center gap-2 text-copy font-semibold text-success-fg"><CheckCircle2 className="h-4 w-4" />{validation.validCount.toLocaleString('en-IN')} ready · {validation.invalidCount} invalid · {validation.duplicateCount} duplicates</p><p className="text-meta text-success-fg">Checked {validation.totalRows.toLocaleString()} contact {validation.totalRows === 1 ? 'row' : 'rows'}. Numbers on the do-not-call list are checked again just before each call.</p><details className="text-copy"><summary className="cursor-pointer">Contact preview and excluded rows</summary><div className="mt-2 overflow-x-auto"><table className="w-full min-w-[18rem] text-left text-meta"><caption className="sr-only">First five validated contacts</caption><thead><tr><th className="p-2">Name</th><th className="p-2">Phone</th></tr></thead><tbody>{validation.validContacts?.slice(0, 5).map((c, i) => <tr key={i}><td className="p-2">{c.full_name || c.first_name || '—'}</td><td className="p-2 font-mono">{c.phone}</td></tr>)}</tbody></table></div>{validation.invalidContacts?.slice(0, 10).map((c, i) => <p key={i} className="mt-1 break-words">Row {c.source_row ?? c.row_index ?? i + 1}: {c.error || c.reason || 'Invalid phone number'}</p>)}</details></div>}
          {Boolean(variables?.invalid_placeholders?.length) && <p role="alert" className="rounded-control border border-danger-line bg-danger-soft p-3 text-copy text-danger-fg">The published script has a variable we cannot fill. Insert variables from the script editor, publish the script, then recheck these contacts.</p>}
          {missing.length > 0 && <div className="space-y-2 rounded-control border border-warning-line bg-warning-soft p-3 text-copy"><p className="break-words">Required script fields are missing: {missing.map((key) => `${key} (${variables.missing_breakdown[key]} contacts)`).join(', ')}. Fields with script fallbacks are already handled.</p><label className="block font-medium">Handle missing fields<select className={input} value={variablePolicy} onChange={(e) => setVariablePolicy(e.target.value)}><option value="review">Fix the mapping or script first</option><option value="skip">Skip contacts missing required fields</option></select></label></div>}
        </section>
        <details className="rounded-control border border-line p-4"><summary className="cursor-pointer text-copy font-semibold">More settings · pace, calling hours and import options</summary><div className="mt-4 space-y-4">
          <label className="block text-ui font-medium text-ink">Description<textarea className={input} maxLength={4000} value={config.description} onChange={(e) => changeConfig('description', e.target.value)} /></label>
          <div className="grid gap-3 sm:grid-cols-3">{[['concurrency', 'Calls at once', 1, 20], ['maxAttempts', 'Maximum attempts', 1, 5], ...(followupSource ? [] : [['retryDelayMinutes', 'Retry delay (minutes)', 5, 1440]])].map(([key, label, min, max]) => <label key={key} className="block text-ui font-medium text-ink">{label}<input type="number" className={input} min={min} max={max} value={pacing[key]} onChange={(e) => setPacing((prev) => ({ ...prev, [key]: Math.max(min, Math.min(max, Number(e.target.value) || min)) }))} /></label>)}</div>
          <p className="text-meta text-fg-muted">Your plan’s limit also applies. We only retry when we know a call did not connect; unclear attempts go to review.</p>
          {followupSource && <p className="text-meta text-fg-muted">For follow-up campaigns, the stricter agent attempt limit and campaign attempt limit apply. Retry delay and daily limits come from the agent’s follow-up policy.</p>}
          <label className="flex min-h-11 items-center gap-2 text-copy"><input type="checkbox" checked={dateRangeEnabled} onChange={(e) => setDateRangeEnabled(e.target.checked)} />Set campaign start and expiry</label>
          {dateRangeEnabled && <div className="grid gap-3 sm:grid-cols-2">{[['startsAt', 'Campaign starts'], ['expiresAt', 'Campaign expires']].map(([key, title]) => <label key={key} className="text-ui font-medium text-ink">{title}<input type="datetime-local" aria-label={title} className={input} value={dateRange[key]} onChange={(event) => setDateRange((value) => ({ ...value, [key]: event.target.value }))} /></label>)}<p className="text-meta text-fg-muted sm:col-span-2">Times use your browser timezone ({Intl.DateTimeFormat().resolvedOptions().timeZone}). A campaign never advances a caller’s requested callback time. Expiry stops new attempts.</p></div>}
          <label className="flex min-h-11 items-center gap-2 text-copy"><input type="checkbox" checked={windowEnabled} onChange={(e) => setWindowEnabled(e.target.checked)} className="h-4 w-4" />Limit calls to a daily calling window</label>
          {windowEnabled && <div className="grid gap-3 sm:grid-cols-2"><label className="text-ui font-medium text-ink">Start time<input type="time" className={input} value={callingWindow.start} onChange={(e) => setCallingWindow((prev) => ({ ...prev, start: e.target.value }))} /></label><label className="text-ui font-medium text-ink">End time<input type="time" className={input} value={callingWindow.end} onChange={(e) => setCallingWindow((prev) => ({ ...prev, end: e.target.value }))} /></label><label className="text-ui font-medium text-ink sm:col-span-2">Fallback timezone<input className={input} value={callingWindow.timezone} onChange={(e) => setCallingWindow((prev) => ({ ...prev, timezone: e.target.value }))} /><span className="mt-1 block text-meta font-normal text-fg-muted">Uses each contact’s timezone when supplied; otherwise this timezone (for example, Asia/Kolkata).</span></label></div>}
        </div></details>
      </fieldset>
      <aside className="min-w-0 self-start rounded-card border border-line bg-canvas p-5 shadow-craft-xs lg:sticky lg:top-0" aria-label="Campaign review">
        <h3 className="text-title text-ink">Review campaign</h3><p className="mt-1 text-copy text-fg-muted">Everything in one place before you launch.</p>
        {preview && <section className="mt-4 space-y-3 border-b border-line pb-4" aria-label="Script personalization">
          <label className="block text-ui font-medium text-ink">Preview contact<select className={input} value={previewIndex} onChange={(event) => setPreviewIndex(Number(event.target.value))}>{variables.previews.map((item, index) => <option key={index} value={index}>{item.name || `Contact ${index + 1}`}</option>)}</select></label>
          <dl className="space-y-2 text-meta">{Object.entries(preview.values || {}).map(([key, value]) => <div key={key} className="min-w-0"><dt className="break-all font-mono text-fg-muted">{`{{${key}}}`}</dt><dd className="break-words font-semibold">{value || (preview.missingVariables?.includes(key) ? 'Missing — action required' : 'Using script fallback')}</dd></div>)}</dl>
          <details><summary className="cursor-pointer text-copy font-semibold">Preview personalized script</summary><pre className="mt-2 max-h-72 overflow-y-auto whitespace-pre-wrap break-words rounded-control bg-surface p-3 font-sans text-meta leading-relaxed" data-testid="campaign-personalized-preview">{preview.renderedText}</pre></details>
          <p className="text-meta text-fg-muted">Each call uses its own contact values and this published script version.</p>
        </section>}
        <dl className="my-5 space-y-3 text-copy"><div><dt className="text-fg-muted">Agent</dt><dd className="break-words font-semibold">{agent?.name || 'Choose an agent'}</dd></div><div><dt className="text-fg-muted">Contacts ready</dt><dd className="font-mono text-heading tabular-nums text-ink">{validation ? contactsReady.toLocaleString() : '—'}</dd></div><div><dt className="text-fg-muted">Calls at once</dt><dd className="font-semibold">Up to {pacing.concurrency}, within your plan</dd></div><div><dt className="text-fg-muted">Calling window</dt><dd className="break-words font-semibold">{windowEnabled ? `${callingWindow.start}–${callingWindow.end} · ${callingWindow.timezone}` : 'No daily time restriction'}</dd></div><div><dt className="text-fg-muted">Integrations each call may use</dt><dd className="mt-1"><IntegrationSelectionSummary selection={integrations} options={integrationOptions.items} emptyText="None chosen: the agent’s saved integration settings apply." /></dd></div></dl>
        <div className="flex gap-2 rounded-control border border-line bg-surface p-3 text-meta text-fg-body"><ShieldCheck className="h-4 w-4 shrink-0 text-success" aria-hidden="true" /><p>Do-not-call checks stay on. Pausing stops new calls; calls already in progress may finish.</p></div>
        <label className="mt-4 flex cursor-pointer items-start gap-3 text-copy leading-relaxed"><input type="checkbox" checked={consent} disabled={!validation?.validCount || Boolean(busy)} onChange={(e) => setConsent(e.target.checked)} className="mt-1 h-4 w-4 shrink-0" /><span>I confirm I have authorization and required consent to call these contacts, approve wallet charges, and accept responsibility for the campaign’s purpose, content and legality.</span></label>
        {error && <div ref={errorRef} tabIndex={-1} role="alert" className="mt-4 flex gap-2 rounded-control border border-danger-line bg-danger-soft p-3 text-copy text-danger-fg"><AlertCircle className="h-4 w-4 shrink-0" /><p className="break-words">{error}</p></div>}
        {busy && <p role="status" className="mt-3 flex items-center gap-2 text-copy"><Loader2 className="h-4 w-4 animate-spin" />{busy}…</p>}
        <div className="mt-5 flex flex-col gap-2"><TactileButton onClick={() => submit(true)} disabled={!ready || Boolean(busy)} variant="primary" className="w-full min-h-11 justify-center" data-testid="campaign-launch">Launch campaign</TactileButton><TactileButton onClick={() => submit(false)} disabled={!ready || Boolean(busy)} variant="secondary" className="w-full min-h-11 justify-center">Save as draft</TactileButton></div>
        {!validation && <p className="mt-3 text-meta text-fg-muted">Validate your contacts to enable launch.</p>}
      </aside>
    </div>
  );
}

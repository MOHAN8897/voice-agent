import React, { useEffect, useRef, useState } from 'react';
import { AlertCircle, CheckCircle2, FileSpreadsheet, Loader2, ShieldCheck, UploadCloud } from 'lucide-react';
import { api } from '../../services/api';
import { useWorkspace } from '../context/WorkspaceContext';
import { TactileButton } from '../ui/TactileButton';
import { showToast } from '../ui/ToastHost';

const input = 'mt-1 w-full min-h-11 min-w-0 rounded-xl border border-[#D1CFDB] bg-white px-3 py-2 text-base sm:text-sm text-[#0F0E17] focus:outline-none focus:ring-2 focus:ring-[#6344E7]';
const fields = ['phone', 'full_name', 'first_name', 'last_name', 'email', 'company', 'job_title', 'country', 'city', 'state', 'timezone', 'notes', 'ignore'];
const countries = ['IN', 'US', 'GB', 'CA', 'AU', 'SG', 'AE', 'DE', 'FR', 'ZA', 'PH', 'NZ'];
const fileLimit = 5 * 1024 * 1024;
const pretty = (value) => value === 'ignore' ? 'Skip column' : `${value.replaceAll('_', ' ')} · {{contact.${value}}}`;

function fileData(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error('Could not read this file. Choose it again.'));
    reader.readAsDataURL(file);
  });
}

export function CampaignSetup({ initialAgentId = '', onComplete, onBusyChange }) {
  const { agents, phoneNumbers, outboundFromE164, createCampaign } = useWorkspace();
  const [config, setConfig] = useState({ name: '', description: '', agentId: initialAgentId || agents[0]?.id || '', fromE164: outboundFromE164 || '', defaultCountry: 'IN' });
  const [source, setSource] = useState('upload');
  const [file, setFile] = useState(null);
  const [text, setText] = useState('');
  const [lists, setLists] = useState([]);
  const [listId, setListId] = useState('');
  const [listError, setListError] = useState('');
  const [parsed, setParsed] = useState(null);
  const [mapping, setMapping] = useState({});
  const [validation, setValidation] = useState(null);
  const [variables, setVariables] = useState(null);
  const [duplicateStrategy, setDuplicateStrategy] = useState('keep_first');
  const [variablePolicy, setVariablePolicy] = useState('review');
  const [consent, setConsent] = useState(false);
  const [pacing, setPacing] = useState({ concurrency: 3, maxAttempts: 2, retryDelayMinutes: 30 });
  const [windowEnabled, setWindowEnabled] = useState(true);
  const [callingWindow, setCallingWindow] = useState({ start: '09:00', end: '18:00', timezone: 'Asia/Kolkata' });
  const [previewIndex, setPreviewIndex] = useState(0);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('');
  const lock = useRef(false);
  const creationId = useRef(crypto.randomUUID());
  const lastValidated = useRef(null);
  const errorRef = useRef(null);
  const currentAgent = config.agentId || initialAgentId || agents[0]?.id || '';
  const outbound = phoneNumbers.filter((n) => n.outboundEnabled !== false && !['released', 'pending', 'failed'].includes(n.status));
  const agent = agents.find((a) => a.id === currentAgent);

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
        if (source === 'list') {
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
      const created = await createCampaign({ clientRequestId: creationId.current, ...config, agentId: currentAgent, expectedScriptVersion: variables?.scriptVersion, ...pacing, contacts, autoStart,
        callingWindow: windowEnabled ? callingWindow : undefined, consentConfirmed: consent, dndScrubEnabled: true });
      const excluded = created.dndExcludedCount || 0;
      showToast(created.status === 'running' ? `Campaign queued: ${Math.max(0, created.totalContacts - excluded)} eligible contacts.` : 'Campaign saved as a draft.', 'success');
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
          <div><h3 id="campaign-details-heading" className="text-base font-bold">Campaign details</h3><p className="mt-1 text-sm text-[#524E5E]">Choose who calls and which line recipients see.</p></div>
          <label className="block text-sm font-medium">Campaign name<input className={input} maxLength={255} value={config.name} onChange={(e) => changeConfig('name', e.target.value)} placeholder="October customer follow-up" /></label>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block text-sm font-medium">Agent<select className={input} value={currentAgent} disabled={Boolean(initialAgentId)} onChange={(e) => changeConfig('agentId', e.target.value)}><option value="">Choose an agent</option>{agents.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</select></label>
            <label className="block text-sm font-medium">Outbound number<select className={input} value={config.fromE164} onChange={(e) => changeConfig('fromE164', e.target.value)}><option value="">Agent’s configured line</option>{outbound.map((n) => <option key={n.id} value={n.number || n.e164}>{n.number || n.e164}</option>)}</select></label>
          </div>
        </section>
        <section className="space-y-4 border-t border-[#E4E2EB] pt-5" aria-labelledby="campaign-contacts-heading">
          <div className="flex flex-wrap items-center justify-between gap-2"><h3 id="campaign-contacts-heading" className="text-base font-bold">Contacts</h3><span className="text-xs text-[#645D73]">Up to 10,000 contacts · 5 MB</span></div>
          <div className="flex flex-wrap gap-2" role="group" aria-label="Contact source">{[['upload', 'Upload file'], ['paste', 'Paste CSV'], ['list', 'Saved list']].map(([key, label]) => <button key={key} type="button" aria-pressed={source === key} onClick={() => changeSource(key)} className={`min-h-11 rounded-xl border px-4 text-sm font-semibold ${source === key ? 'border-[#6344E7] bg-[#F0EEF6] text-[#5033C6]' : 'border-[#E4E2EB] text-[#524E5E]'}`}>{label}</button>)}</div>
          {source === 'upload' && <label className="flex cursor-pointer flex-col items-center gap-2 rounded-xl border border-dashed border-[#B9B3CF] bg-[#FAF9FD] p-6 text-center"><UploadCloud className="h-6 w-6 text-[#6344E7]" /><span className="text-sm font-semibold">{file?.name || 'Choose a contact spreadsheet'}</span><span className="text-xs text-[#645D73]">CSV or Excel (.xlsx), with a header row</span><input type="file" accept=".csv,.xlsx" aria-label="Contact spreadsheet" className="max-w-full text-sm" onChange={(e) => { setFile(e.target.files?.[0] || null); setParsed(null); invalidate(); }} /></label>}
          {source === 'paste' && <label className="block text-sm font-medium">CSV contacts<textarea className={`${input} min-h-36 font-mono`} value={text} maxLength={5 * 1024 * 1024} placeholder={'phone,full_name\n+12025550101,Example Contact'} onChange={(e) => { setText(e.target.value); setParsed(null); invalidate(); }} /></label>}
          {source === 'list' && <label className="block text-sm font-medium">Contact list<select className={input} value={listId} onChange={(e) => { setListId(e.target.value); setParsed(null); invalidate(); }}><option value="">Choose a list</option>{lists.map((list) => <option key={list.id} value={list.id}>{list.name} ({list.totalContacts ?? list.total_contacts ?? 0})</option>)}</select>{listError && <span role="status" className="mt-2 block text-xs text-amber-800">{listError}</span>}</label>}
          <div className="grid gap-4 sm:grid-cols-2"><label className="block text-sm font-medium">Country for local numbers<select className={input} value={config.defaultCountry} onChange={(e) => changeConfig('defaultCountry', e.target.value)}>{countries.map((code) => <option key={code} value={code}>{new Intl.DisplayNames(['en'], { type: 'region' }).of(code)}</option>)}</select></label><label className="block text-sm font-medium">Duplicate numbers<select className={input} value={duplicateStrategy} onChange={(e) => { setDuplicateStrategy(e.target.value); invalidate(); }}><option value="keep_first">Keep first contact</option><option value="keep_last">Keep last contact</option><option value="remove">Skip all duplicates</option><option value="merge">Merge duplicate contact fields</option></select></label></div>
          {parsed && <details className="rounded-xl border border-[#E4E2EB] p-3"><summary className="min-h-8 cursor-pointer text-sm font-semibold">Column mapping · {parsed.totalRows.toLocaleString()} {parsed.totalRows === 1 ? 'row' : 'rows'} loaded</summary><div className="mt-3 space-y-3">{parsed.warnings?.map((warning, i) => <p key={i} className="break-words text-xs text-amber-800">{warning}</p>)}{parsed.headers.map((header) => <label key={header} className="grid min-w-0 items-center gap-1 text-sm sm:grid-cols-2"><span className="break-words">{header}</span><select className={input} aria-label={`Map ${header}`} value={mapping[header] || 'ignore'} onChange={(e) => { setMapping((prev) => ({ ...prev, [header]: e.target.value })); invalidate(); }}>{fields.map((key) => <option key={key} value={key}>{pretty(key)}</option>)}<option value={`custom_field:${header.toLowerCase().replace(/[^a-z0-9_]/g, '_')}`}>Custom field: {header}</option>{mapping[header]?.startsWith('custom_field:') && <option value={mapping[header]}>{mapping[header]}</option>}</select></label>)}</div></details>}
          <TactileButton variant="secondary" onClick={prepare} disabled={Boolean(busy)} icon={FileSpreadsheet}>{busy === 'Checking contacts' ? 'Checking contacts…' : validation ? 'Recheck contacts' : 'Validate contacts'}</TactileButton>
          {validation && <div role="status" className="space-y-3 rounded-xl border border-[#C5E7D7] bg-[#F1FBF5] p-4"><p className="flex items-center gap-2 text-sm font-semibold text-[#166534]"><CheckCircle2 className="h-4 w-4" />{validation.validCount.toLocaleString()} ready · {validation.invalidCount} invalid · {validation.duplicateCount} duplicates</p><p className="text-xs text-[#365A45]">Checked {validation.totalRows.toLocaleString()} contact {validation.totalRows === 1 ? 'row' : 'rows'}. Do Not Call exclusions are checked again before dialing.</p><details className="text-sm"><summary className="cursor-pointer">Contact preview and excluded rows</summary><div className="mt-2 overflow-x-auto"><table className="w-full min-w-[18rem] text-left text-xs"><caption className="sr-only">First five validated contacts</caption><thead><tr><th className="p-2">Name</th><th className="p-2">Phone</th></tr></thead><tbody>{validation.validContacts?.slice(0, 5).map((c, i) => <tr key={i}><td className="p-2">{c.full_name || c.first_name || '—'}</td><td className="p-2 font-mono">{c.phone}</td></tr>)}</tbody></table></div>{validation.invalidContacts?.slice(0, 10).map((c, i) => <p key={i} className="mt-1 break-words">Row {c.source_row ?? c.row_index ?? i + 1}: {c.error || c.reason || 'Invalid phone number'}</p>)}</details></div>}
          {Boolean(variables?.invalid_placeholders?.length) && <p role="alert" className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-800">The published script has an unsupported or unclosed placeholder. Insert variables from the script editor, publish the script, and recheck these contacts.</p>}
          {missing.length > 0 && <div className="space-y-2 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm"><p className="break-words">Required script fields are missing: {missing.map((key) => `${key} (${variables.missing_breakdown[key]} contacts)`).join(', ')}. Fields with script fallbacks are already handled.</p><label className="block font-medium">Handle missing fields<select className={input} value={variablePolicy} onChange={(e) => setVariablePolicy(e.target.value)}><option value="review">Fix the mapping or script first</option><option value="skip">Skip contacts missing required fields</option></select></label></div>}
        </section>
        <details className="rounded-xl border border-[#E4E2EB] p-4"><summary className="cursor-pointer text-sm font-semibold">Advanced settings · pacing, calling hours and import options</summary><div className="mt-4 space-y-4">
          <label className="block text-sm font-medium">Description<textarea className={input} maxLength={4000} value={config.description} onChange={(e) => changeConfig('description', e.target.value)} /></label>
          <div className="grid gap-3 sm:grid-cols-3">{[['concurrency', 'Concurrent calls', 1, 20], ['maxAttempts', 'Maximum attempts', 1, 5], ['retryDelayMinutes', 'Retry delay (minutes)', 5, 1440]].map(([key, label, min, max]) => <label key={key} className="block text-sm font-medium">{label}<input type="number" className={input} min={min} max={max} value={pacing[key]} onChange={(e) => setPacing((prev) => ({ ...prev, [key]: Math.max(min, Math.min(max, Number(e.target.value) || min)) }))} /></label>)}</div>
          <p className="text-xs text-[#645D73]">Your plan limit also applies. Retries wait for a confirmed non-connection; uncertain requests need review.</p>
          <label className="flex min-h-11 items-center gap-2 text-sm"><input type="checkbox" checked={windowEnabled} onChange={(e) => setWindowEnabled(e.target.checked)} className="h-4 w-4" />Limit calls to a daily calling window</label>
          {windowEnabled && <div className="grid gap-3 sm:grid-cols-2"><label className="text-sm font-medium">Start time<input type="time" className={input} value={callingWindow.start} onChange={(e) => setCallingWindow((prev) => ({ ...prev, start: e.target.value }))} /></label><label className="text-sm font-medium">End time<input type="time" className={input} value={callingWindow.end} onChange={(e) => setCallingWindow((prev) => ({ ...prev, end: e.target.value }))} /></label><label className="text-sm font-medium sm:col-span-2">Fallback timezone<input className={input} value={callingWindow.timezone} onChange={(e) => setCallingWindow((prev) => ({ ...prev, timezone: e.target.value }))} /><span className="mt-1 block text-xs font-normal text-[#645D73]">Uses each contact’s timezone when supplied; otherwise this IANA timezone (for example, Asia/Kolkata).</span></label></div>}
        </div></details>
      </fieldset>
      <aside className="min-w-0 self-start rounded-2xl border border-[#DCD7EE] bg-[#FAF9FD] p-5 lg:sticky lg:top-0" aria-label="Campaign review">
        <h3 className="text-base font-bold">Review campaign</h3><p className="mt-1 text-sm text-[#645D73]">Everything in one place before you launch.</p>
        {preview && <section className="mt-4 space-y-3 border-b border-[#DCD7EE] pb-4" aria-label="Script personalization">
          <label className="block text-sm font-medium">Preview contact<select className={input} value={previewIndex} onChange={(event) => setPreviewIndex(Number(event.target.value))}>{variables.previews.map((item, index) => <option key={index} value={index}>{item.name || `Contact ${index + 1}`}</option>)}</select></label>
          <dl className="space-y-2 text-xs">{Object.entries(preview.values || {}).map(([key, value]) => <div key={key} className="min-w-0"><dt className="break-all font-mono text-[#645D73]">{`{{${key}}}`}</dt><dd className="break-words font-semibold">{value || (preview.missingVariables?.includes(key) ? 'Missing — action required' : 'Using script fallback')}</dd></div>)}</dl>
          <details><summary className="cursor-pointer text-sm font-semibold">Preview personalized script</summary><pre className="mt-2 max-h-72 overflow-y-auto whitespace-pre-wrap break-words rounded-lg bg-white p-3 font-sans text-xs leading-relaxed" data-testid="campaign-personalized-preview">{preview.renderedText}</pre></details>
          <p className="text-xs text-[#645D73]">Each call uses its own contact values and this published script version.</p>
        </section>}
        <dl className="my-5 space-y-3 text-sm"><div><dt className="text-[#645D73]">Agent</dt><dd className="break-words font-semibold">{agent?.name || 'Choose an agent'}</dd></div><div><dt className="text-[#645D73]">Contacts ready</dt><dd className="text-2xl font-bold tabular-nums">{validation ? contactsReady.toLocaleString() : '—'}</dd></div><div><dt className="text-[#645D73]">Concurrent calls</dt><dd className="font-semibold">Up to {pacing.concurrency}, within your plan</dd></div><div><dt className="text-[#645D73]">Calling window</dt><dd className="break-words font-semibold">{windowEnabled ? `${callingWindow.start}–${callingWindow.end} · ${callingWindow.timezone}` : 'No daily time restriction'}</dd></div></dl>
        <div className="flex gap-2 rounded-xl bg-white p-3 text-xs text-[#365A45]"><ShieldCheck className="h-4 w-4 shrink-0" /><p>Do Not Call checks stay enabled. Pausing stops new work; calls already in progress may continue.</p></div>
        <label className="mt-4 flex cursor-pointer items-start gap-3 text-sm leading-relaxed"><input type="checkbox" checked={consent} disabled={!validation?.validCount || Boolean(busy)} onChange={(e) => setConsent(e.target.checked)} className="mt-1 h-4 w-4 shrink-0" /><span>I confirm I have authorization and required consent to call these contacts, and accept responsibility for the campaign’s purpose, content and legality.</span></label>
        {error && <div ref={errorRef} tabIndex={-1} role="alert" className="mt-4 flex gap-2 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-800"><AlertCircle className="h-4 w-4 shrink-0" /><p className="break-words">{error}</p></div>}
        {busy && <p role="status" className="mt-3 flex items-center gap-2 text-sm"><Loader2 className="h-4 w-4 animate-spin" />{busy}…</p>}
        <div className="mt-5 flex flex-col gap-2"><TactileButton onClick={() => submit(true)} disabled={!ready || Boolean(busy)} variant="primary" className="w-full min-h-11 justify-center" data-testid="campaign-launch">Launch campaign</TactileButton><TactileButton onClick={() => submit(false)} disabled={!ready || Boolean(busy)} variant="secondary" className="w-full min-h-11 justify-center">Save as draft</TactileButton></div>
        {!validation && <p className="mt-3 text-xs text-[#645D73]">Validate your contacts to enable launch.</p>}
      </aside>
    </div>
  );
}

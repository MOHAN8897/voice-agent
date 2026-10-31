import React, { useEffect, useMemo, useState } from 'react';
import { Download } from 'lucide-react';
import { Modal } from '../../ui/Modal';
import { TactileButton } from '../../ui/TactileButton';
import { Tabs } from '../../ui/Tabs';
import { showToast } from '../../ui/ToastHost';
import { useWorkspace } from '../../context/WorkspaceContext';
import { api } from '../../../services/api';
import { tagLabel } from '../../../lib/internalLabels';
import { EXPORT_DATASETS, EXPORT_ROW_LIMIT, datasetById, exportQuery } from './exportDatasets';

const RANGES = [
  { id: 'all', label: 'All time' },
  { id: 'today', label: 'Today' },
  { id: '7d', label: '7 days' },
  { id: '30d', label: '30 days' },
  { id: 'custom', label: 'Custom' },
];

function istToday() {
  return new Date(Date.now() + 330 * 60 * 1000).toISOString().slice(0, 10);
}

function FilterSelect({ label, value, onChange, options }) {
  return (
    <label className="block min-w-0">
      <span className="mb-1 block text-meta text-fg-muted">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-9 w-full min-w-0 rounded-control border border-line bg-surface px-3 text-base sm:text-ui text-ink focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/15"
      >
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </label>
  );
}

/**
 * Pick a dataset, narrow it with filters, see how many rows it holds, and download
 * it as CSV or Excel. `preset` pre-fills the dialog from the page that opened it:
 * `{ dataset, agentId, values: { stage: 'qualified' }, tags: [...] }`.
 */
export function ExportDialog({ isOpen, onClose, preset = null }) {
  const { agents = [] } = useWorkspace();
  const [datasetId, setDatasetId] = useState(preset?.dataset || 'calls');
  const [range, setRange] = useState(preset?.range || 'all');
  const [since, setSince] = useState(preset?.since || istToday());
  const [until, setUntil] = useState(preset?.until || istToday());
  const [agentId, setAgentId] = useState(preset?.agentId || '');
  const [values, setValues] = useState(preset?.values || {});
  const [tags, setTags] = useState(preset?.tags || []);
  const [tagMatch, setTagMatch] = useState(preset?.tagMatch || 'any');
  const [knownTags, setKnownTags] = useState([]);
  const [count, setCount] = useState(null);
  const [counting, setCounting] = useState(false);
  const [countError, setCountError] = useState('');
  const [busy, setBusy] = useState('');

  // Re-seed from the preset each time the dialog opens.
  useEffect(() => {
    if (!isOpen) return;
    setDatasetId(preset?.dataset || 'calls');
    setRange(preset?.range || 'all');
    setAgentId(preset?.agentId || '');
    setValues(preset?.values || {});
    setTags(preset?.tags || []);
    setTagMatch(preset?.tagMatch || 'any');
  }, [isOpen, preset]);

  const dataset = datasetById(datasetId);
  const hasTags = dataset.filters.some((f) => f.type === 'tags');
  const query = useMemo(
    () => exportQuery({ range, since, until, agentId, values, tags, tagMatch }, dataset),
    [range, since, until, agentId, values, tags, tagMatch, dataset],
  );
  const queryKey = JSON.stringify([datasetId, query]);

  useEffect(() => {
    if (!isOpen || !hasTags) return;
    let alive = true;
    api.calls.tags({}).then((rows) => {
      if (alive) setKnownTags(rows.map((r) => (typeof r === 'string' ? r : r.tag)).filter(Boolean));
    }).catch(() => {});
    return () => { alive = false; };
  }, [isOpen, hasTags]);

  useEffect(() => {
    if (!isOpen) return;
    let alive = true;
    setCounting(true);
    setCountError('');
    const timer = setTimeout(() => {
      api.exports.count(datasetId, query)
        .then((data) => { if (alive) setCount(data); })
        .catch((err) => { if (alive) { setCount(null); setCountError(err.message || 'Could not count rows'); } })
        .finally(() => { if (alive) setCounting(false); });
    }, 250);
    return () => { alive = false; clearTimeout(timer); };
    // queryKey captures every input of the count.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, queryKey]);

  const changeDataset = (id) => {
    setDatasetId(id);
    setValues({});
    setTags([]);
  };

  const download = async (format) => {
    setBusy(format);
    try {
      await api.exports.download(datasetId, format, query);
      showToast(`${dataset.label} downloaded as ${format === 'xlsx' ? 'Excel' : 'CSV'}.`, 'success');
    } catch (err) {
      showToast(err.message || 'Could not export. Try again in a moment.', 'error');
    } finally {
      setBusy('');
    }
  };

  const agentOptions = [{ value: '', label: 'All agents' }, ...agents.map((a) => ({ value: a.id, label: a.name }))];
  const rows = count?.count ?? null;

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Export data" subtitle="Download a spreadsheet of your workspace data." maxWidth="max-w-xl">
      <div className="space-y-5" data-testid="export-dialog">
        <label className="block">
          <span className="mb-1.5 block text-ui font-medium text-ink">What to export</span>
          <select
            data-testid="export-dataset"
            value={datasetId}
            onChange={(e) => changeDataset(e.target.value)}
            className="h-10 w-full rounded-control border border-line bg-surface px-3 text-base sm:text-ui text-ink focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/15"
          >
            {EXPORT_DATASETS.map((d) => <option key={d.id} value={d.id}>{d.label}</option>)}
          </select>
          <span className="mt-1 block text-meta text-fg-muted">{dataset.description}</span>
        </label>

        <div>
          <span className="mb-1.5 block text-ui font-medium text-ink">Period</span>
          <Tabs variant="pills" size="sm" label="Export period" value={range} onChange={setRange} items={RANGES} />
          {range === 'custom' && (
            <div className="mt-2 grid grid-cols-2 gap-2">
              <label className="text-meta text-fg-muted">From
                <input type="date" value={since} max={until} onChange={(e) => setSince(e.target.value)} data-testid="export-since"
                  className="mt-1 h-9 w-full rounded-control border border-line bg-surface px-2 text-base sm:text-ui text-ink" />
              </label>
              <label className="text-meta text-fg-muted">To
                <input type="date" value={until} min={since} onChange={(e) => setUntil(e.target.value)} data-testid="export-until"
                  className="mt-1 h-9 w-full rounded-control border border-line bg-surface px-2 text-base sm:text-ui text-ink" />
              </label>
            </div>
          )}
          <span className="mt-1 block text-meta text-fg-muted">Dates are India time.</span>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          {dataset.agent && agents.length > 0 && (
            <FilterSelect label="Agent" value={agentId} onChange={setAgentId} options={agentOptions} />
          )}
          {dataset.filters.filter((f) => f.options).map((f) => (
            <FilterSelect
              key={f.key}
              label={f.label}
              value={values[f.key] || ''}
              onChange={(v) => setValues((prev) => ({ ...prev, [f.key]: v }))}
              options={[{ value: '', label: 'Any' }, ...f.options]}
            />
          ))}
        </div>

        {hasTags && (
          <fieldset>
            <legend className="mb-1.5 text-ui font-medium text-ink">Tags</legend>
            {knownTags.length === 0 && tags.length === 0 ? (
              <p className="text-meta text-fg-muted">No tags yet. Tags appear after calls are summarised.</p>
            ) : (
              <div className="flex flex-wrap gap-1.5" data-testid="export-tags">
                {[...new Set([...tags, ...knownTags])].slice(0, 40).map((tag) => {
                  const on = tags.includes(tag);
                  return (
                    <button
                      key={tag}
                      type="button"
                      aria-pressed={on}
                      onClick={() => setTags((prev) => (on ? prev.filter((t) => t !== tag) : [...prev, tag]))}
                      className={`rounded-pill border px-2.5 py-1 text-meta font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent ${
                        on ? 'border-ink bg-ink text-white' : 'border-line bg-surface text-fg-body hover:border-line-strong'
                      }`}
                    >
                      {tagLabel(tag)}
                    </button>
                  );
                })}
              </div>
            )}
            {tags.length > 1 && (
              <Tabs
                className="mt-2"
                size="sm"
                label="Tag match"
                value={tagMatch}
                onChange={setTagMatch}
                items={[{ id: 'any', label: 'Any of these tags' }, { id: 'all', label: 'All of these tags' }]}
              />
            )}
          </fieldset>
        )}

        <div className="rounded-control bg-surface-subtle px-3 py-2 text-ui text-fg-body" role="status" aria-live="polite" data-testid="export-count">
          {countError ? (
            <span className="text-danger-fg">{countError}</span>
          ) : counting && rows == null ? (
            'Counting rows…'
          ) : rows === 0 ? (
            'No rows match these filters.'
          ) : (
            <>
              <span className="font-mono tabular-nums text-ink">{(rows ?? 0).toLocaleString('en-IN')}</span> rows match.
              {count?.capped && ` Only the newest ${EXPORT_ROW_LIMIT.toLocaleString('en-IN')} will be downloaded.`}
            </>
          )}
          <span className="block text-meta text-fg-muted">
            Exports hold up to {EXPORT_ROW_LIMIT.toLocaleString('en-IN')} rows. Phone numbers are formatted; times are India time.
          </span>
        </div>

        <div className="flex flex-wrap justify-end gap-2">
          <TactileButton variant="secondary" onClick={onClose}>Close</TactileButton>
          <TactileButton variant="secondary" icon={Download} loading={busy === 'csv'} disabled={Boolean(busy) || rows === 0 || Boolean(countError)} onClick={() => download('csv')} data-testid="export-csv">
            Download CSV
          </TactileButton>
          <TactileButton variant="primary" icon={Download} loading={busy === 'xlsx'} disabled={Boolean(busy) || rows === 0 || Boolean(countError)} onClick={() => download('xlsx')} data-testid="export-xlsx">
            Download Excel
          </TactileButton>
        </div>
      </div>
    </Modal>
  );
}

/** A small "Export" button that opens the dialog pre-filtered for the page it sits on. */
export function ExportButton({ preset, label = 'Export', size = 'sm', className = '' }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <TactileButton variant="secondary" size={size} icon={Download} onClick={() => setOpen(true)} className={className} data-testid={`export-open-${preset?.dataset || 'data'}`}>
        {label}
      </TactileButton>
      {open && <ExportDialog isOpen={open} onClose={() => setOpen(false)} preset={preset} />}
    </>
  );
}

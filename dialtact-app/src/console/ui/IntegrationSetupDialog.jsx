import React, { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import { TactileButton } from './TactileButton';
import { api } from '../../services/api';

const overlayClass = 'fixed inset-0 z-50 flex items-center justify-center bg-ink/60 backdrop-blur-sm p-4 animate-in fade-in duration-200';
const dialogClass = 'bg-surface border border-line rounded-card w-full shadow-craft-lg animate-in zoom-in-95 duration-200';
const closeButtonClass = 'shrink-0 -mr-2 -mt-1 min-w-[40px] min-h-[40px] flex items-center justify-center rounded-control text-fg-muted hover:text-ink hover:bg-canvas focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent transition-colors';
const inputClass = 'w-full px-3.5 py-2 min-h-[44px] sm:min-h-[38px] text-base sm:text-ui bg-surface border border-line rounded-control focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/20 text-ink placeholder:text-fg-subtle';

/**
 * Choose the resource an app's actions use (a Slack channel, a Notion page, a
 * Cal.com event type ...). Until the required ones are saved the app is never
 * offered to a call, so the agent cannot promise something that would fail.
 */
export function IntegrationSetupDialog({ app, onClose, onSaved }) {
  const [fields, setFields] = useState([]);
  const [values, setValues] = useState({});
  const [options, setOptions] = useState({});
  const [loadingField, setLoadingField] = useState(null);
  const [fieldError, setFieldError] = useState({});
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [loaded, setLoaded] = useState(false);

  const loadOptions = async (key, current = values) => {
    setLoadingField(key);
    setFieldError((prev) => ({ ...prev, [key]: null }));
    try {
      const others = Object.fromEntries(Object.entries(current || {}).filter(([k, v]) => k !== key && v));
      const data = await api.integrations.options(app.id, key, others);
      setOptions((prev) => ({ ...prev, [key]: data?.options || [] }));
    } catch (err) {
      setFieldError((prev) => ({ ...prev, [key]: err?.message || 'Could not load choices. Enter the value instead.' }));
    } finally {
      setLoadingField(null);
    }
  };

  useEffect(() => {
    let live = true;
    api.integrations.settings(app.id)
      .then((data) => {
        if (!live) return;
        setFields(data?.fields || []);
        setValues(data?.values || {});
        setLoaded(true);
        // Offer the account's own choices right away for the first pickable field.
        const first = (data?.fields || []).find((f) => f.has_options);
        if (first) loadOptions(first.key, data?.values || {});
      })
      .catch((err) => live && setError(err?.message || 'Could not load the setup for this app.'));
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [app.id]);

  const save = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const data = await api.integrations.saveSettings(app.id, values);
      onSaved?.(data);
    } catch (err) {
      setError(err?.message || 'Could not save. Check the values and try again.');
    } finally {
      setSaving(false);
    }
  };

  const missing = fields.filter((f) => f.required && !String(values[f.key] || '').trim());

  return (
    <div className={overlayClass}>
      <div role="dialog" aria-modal="true" aria-labelledby="integration-setup-title" className={`${dialogClass} p-5 sm:p-6 max-w-md space-y-4`} data-testid="integration-setup-dialog">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h3 id="integration-setup-title" className="text-title text-ink break-words">Set up {app.name}</h3>
            <p className="mt-1 text-ui text-fg-muted">Choose what your agents use in {app.name}. They never guess these during a call.</p>
          </div>
          <button type="button" onClick={onClose} aria-label="Close" className={closeButtonClass}>
            <X className="w-4 h-4" />
          </button>
        </div>

        {error && <p role="alert" className="rounded-control border border-danger-line bg-danger-soft px-3 py-2 text-ui text-danger-fg">{error}</p>}
        {!loaded && !error && <p role="status" className="text-ui text-fg-muted">Loading…</p>}

        {loaded && (
          <form onSubmit={save} className="space-y-4">
            {fields.map((f) => {
              // Fixed choices from the app's setup, or the account's own (loaded on demand).
              const choices = f.choices && f.choices.length ? f.choices : options[f.key];
              const id = `setup-${app.id}-${f.key}`;
              const current = values[f.key] || '';
              return (
                <div key={f.key}>
                  <label htmlFor={id} className="block text-ui font-medium text-ink mb-1.5">
                    {f.label}{f.required ? '' : ' (optional)'}
                  </label>
                  {choices && choices.length > 0 ? (
                    <select id={id} value={current} onChange={(e) => setValues({ ...values, [f.key]: e.target.value })}
                      className={inputClass} data-testid={`setup-field-${f.key}`}>
                      <option value="">Choose…</option>
                      {current && !choices.some((c) => c.value === current) && <option value={current}>{current}</option>}
                      {choices.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
                    </select>
                  ) : f.multiline ? (
                    <textarea id={id} rows={4} value={current} maxLength={f.max_length || undefined}
                      onChange={(e) => setValues({ ...values, [f.key]: e.target.value })}
                      className={`${inputClass} py-2.5 leading-relaxed`} data-testid={`setup-field-${f.key}`} />
                  ) : (
                    <input id={id} type="text" value={current} maxLength={f.max_length || undefined}
                      onChange={(e) => setValues({ ...values, [f.key]: e.target.value })}
                      className={inputClass} data-testid={`setup-field-${f.key}`} autoComplete="off" />
                  )}
                  {f.help && <p className="mt-1 text-meta text-fg-muted">{f.help}</p>}
                  {f.has_options && (
                    <button type="button" onClick={() => loadOptions(f.key)} disabled={loadingField === f.key}
                      className="mt-1 min-h-[32px] text-meta font-medium text-accent-fg hover:underline disabled:opacity-60">
                      {loadingField === f.key ? 'Loading choices…' : choices ? 'Refresh choices' : `Load choices from ${app.name}`}
                    </button>
                  )}
                  {choices && choices.length === 0 && <p className="mt-1 text-meta text-fg-muted">Nothing found in the connected account. Enter the value instead.</p>}
                  {fieldError[f.key] && <p role="alert" className="mt-1 text-meta text-warning-fg">{fieldError[f.key]}</p>}
                </div>
              );
            })}
            <div className="flex items-center justify-between gap-2 pt-3 border-t border-line">
              <p className="text-meta text-fg-muted">{missing.length ? `Still needed: ${missing.map((f) => f.label).join(', ')}` : 'Ready for calls once saved.'}</p>
              <div className="flex gap-2">
                <TactileButton type="button" variant="ghost" size="sm" onClick={onClose}>Cancel</TactileButton>
                <TactileButton type="submit" variant="primary" size="sm" loading={saving} disabled={saving} data-testid="integration-setup-save">Save</TactileButton>
              </div>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}

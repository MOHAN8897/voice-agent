import React, { useEffect, useState } from 'react';
import { Blocks, Clock, ExternalLink, Loader2, PhoneCall, RefreshCw } from 'lucide-react';
import { api } from '../../services/api';
import { FULL_INTEGRATIONS_CATALOG } from '../modules/integrationsCatalog';

/**
 * "Integrations for this call": which connected apps this call (or every call
 * in a campaign) may use. Only connected and verified apps are selectable;
 * the rest are shown disabled with the reason and a link to connect them.
 *
 * value: null (agent defaults) or [{ app, mode }]. onChange receives the same.
 */

const MODE_LABEL = { in_call: 'During the call', post_call: 'After the call' };
const MODE_TONE = {
  in_call: 'bg-info-soft text-info-fg border-info-line',
  post_call: 'bg-neutral-soft text-neutral-fg border-neutral-line',
};

export function ModeBadge({ mode }) {
  const Icon = mode === 'in_call' ? PhoneCall : Clock;
  return (
    <span className={`inline-flex items-center gap-1 whitespace-nowrap rounded-pill border px-2 py-0.5 text-meta font-medium ${MODE_TONE[mode] || MODE_TONE.in_call}`}>
      <Icon className="h-3 w-3" aria-hidden="true" />
      {MODE_LABEL[mode] || mode}
    </span>
  );
}

export function useCallIntegrationOptions(agentId) {
  const [state, setState] = useState({ items: [], loading: false, error: '' });
  const [reload, setReload] = useState(0);
  useEffect(() => {
    if (!agentId) { setState({ items: [], loading: false, error: '' }); return undefined; }
    let active = true;
    setState((prev) => ({ ...prev, loading: true, error: '' }));
    api.integrations.callOptions(agentId)
      .then((data) => { if (active) setState({ items: data.items || [], loading: false, error: '' }); })
      .catch((err) => { if (active) setState({ items: [], loading: false, error: err.message || 'Apps could not be loaded.' }); });
    return () => { active = false; };
  }, [agentId, reload]);
  return { ...state, refresh: () => setReload((n) => n + 1) };
}

/** Compact read-only list used in confirmation steps and detail pages. */
export function IntegrationSelectionSummary({ selection, options = [], emptyText, inherited = false, className = '' }) {
  const names = Object.fromEntries((options || []).map((item) => [item.app, item.name]));
  if (!selection?.length) {
    return (
      <p className={`text-ui text-fg-body ${className}`} data-testid="integration-summary-default">
        {emptyText || 'The employee’s saved app settings (none chosen for this call).'}
      </p>
    );
  }
  return (
    <ul className={`space-y-1.5 ${className}`} data-testid="integration-summary">
      {selection.map((item) => {
        const mode = (options.find((o) => o.app === item.app)?.modes || []).find((m) => m.mode === item.mode);
        return (
          <li key={`${item.app}-${item.mode}`} className="min-w-0 text-ui">
            <span className="flex flex-wrap items-center gap-1.5">
              <span className="font-semibold text-ink">{names[item.app] || prettyApp(item.app)}</span>
              <ModeBadge mode={item.mode} />
            </span>
            {mode?.description && <span className="mt-0.5 block break-words text-fg-body">{mode.description}</span>}
          </li>
        );
      })}
      {inherited && <li className="text-meta text-fg-muted">Set by the campaign.</li>}
    </ul>
  );
}

/**
 * One app-label map for the console: the integrations catalog's names, keyed by
 * the app id with separators removed ("google_calendar" and "GOOGLECALENDAR" both
 * become "Google Calendar"). Anything not in the catalog is title-cased.
 */
const APP_LABELS = Object.fromEntries(
  FULL_INTEGRATIONS_CATALOG.map((entry) => [String(entry.id).replace(/[^a-z0-9]/gi, '').toUpperCase(), entry.name])
);

export function prettyApp(app) {
  const key = String(app || '').replace(/[^a-z0-9]/gi, '').toUpperCase();
  if (APP_LABELS[key]) return APP_LABELS[key];
  return String(app || '').replaceAll('_', ' ').toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase());
}

export function CallIntegrationPicker({ agentId, value, onChange, scope = 'call', disabled = false, options }) {
  const { items, loading, error, refresh } = options;
  const selected = Object.fromEntries((value || []).map((item) => [item.app, item.mode]));

  const update = (next) => {
    const list = Object.entries(next).map(([app, mode]) => ({ app, mode }));
    onChange(list.length ? list : null);
  };
  const toggle = (item) => {
    const next = { ...selected };
    if (next[item.app]) delete next[item.app];
    else next[item.app] = item.defaultMode || item.modes[0]?.mode;
    update(next);
  };
  const setMode = (item, mode) => update({ ...selected, [item.app]: mode });

  const available = items.filter((item) => item.selectable);
  const unavailable = items.filter((item) => !item.selectable && item.state !== 'setup_required');
  const needsSetup = items.filter((item) => item.state === 'setup_required');
  const subject = scope === 'campaign' ? 'every call in this campaign' : 'this call';

  return (
    <section className="space-y-3" aria-labelledby={`integrations-${scope}-heading`} data-testid="call-integration-picker">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 id={`integrations-${scope}-heading`} className="flex items-center gap-2 text-title text-ink">
            <Blocks className="h-4 w-4 text-accent" aria-hidden="true" />
            Integrations for {scope === 'campaign' ? 'this campaign' : 'this call'}
          </h3>
          <p className="mt-1 text-ui text-fg-body">
            Choose which connected apps the employee may use for {subject}. They use only these. If you choose none,
            the employee uses their saved app settings.
          </p>
        </div>
        <button type="button" onClick={refresh} disabled={loading || !agentId}
          className="inline-flex min-h-9 items-center gap-1 rounded-control px-2 text-ui font-medium text-accent-fg hover:bg-surface-subtle disabled:opacity-50">
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} aria-hidden="true" /> Refresh
        </button>
      </div>

      {!agentId && <p className="text-ui text-fg-body">Choose an employee to see their apps.</p>}
      {loading && <p role="status" className="flex items-center gap-2 text-ui text-fg-body"><Loader2 className="h-3.5 w-3.5 animate-spin" />Loading apps…</p>}
      {error && <p role="alert" className="rounded-control border border-warning-line bg-warning-soft p-2 text-ui text-warning-fg">{error} The employee’s saved app settings will be used.</p>}

      {!loading && agentId && !error && !available.length && (
        <div className="rounded-control border border-dashed border-line-strong p-3 text-ui text-fg-body">
          None of your connected apps can be used on calls yet.{' '}
          <a href="#dashboard/integrations" className="font-semibold text-accent-fg underline">Connect one on the Integrations page</a>.
        </div>
      )}

      {available.length > 0 && (
        <ul className="grid gap-2 sm:grid-cols-2">
          {available.map((item) => {
            const on = Boolean(selected[item.app]);
            const mode = selected[item.app] || item.defaultMode;
            const modeInfo = item.modes.find((m) => m.mode === mode) || item.modes[0];
            return (
              <li key={item.app} className={`min-w-0 rounded-control border p-3 transition-colors ${on ? 'border-accent bg-accent-soft' : 'border-line bg-surface'}`}>
                <label className="flex cursor-pointer items-start gap-2.5">
                  <input type="checkbox" className="mt-0.5 h-4 w-4 shrink-0 accent-accent" checked={on} disabled={disabled}
                    onChange={() => toggle(item)} aria-describedby={`ci-desc-${scope}-${item.app}`} data-testid={`ci-toggle-${item.app}`} />
                  <span className="min-w-0">
                    <span className="flex flex-wrap items-center gap-1.5">
                      <span className="text-copy font-semibold text-ink">{item.name || prettyApp(item.app)}</span>
                      <ModeBadge mode={mode} />
                    </span>
                    <span id={`ci-desc-${scope}-${item.app}`} className="mt-1 block break-words text-ui text-fg-body">{modeInfo?.description}</span>
                  </span>
                </label>
                {item.modes.length > 1 && (
                  <div className="mt-2 flex flex-wrap gap-1.5 pl-6" role="radiogroup" aria-label={`When ${item.name} runs`}>
                    {item.modes.map((m) => (
                      <button key={m.mode} type="button" role="radio" aria-checked={mode === m.mode} disabled={disabled}
                        onClick={() => (on ? setMode(item, m.mode) : update({ ...selected, [item.app]: m.mode }))}
                        className={`min-h-8 rounded-control border px-2.5 text-meta font-medium ${mode === m.mode && on ? 'border-accent bg-surface text-accent-fg' : 'border-line bg-surface text-fg-body hover:border-line-strong'}`}>
                        {m.label}
                      </button>
                    ))}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {(unavailable.length > 0 || needsSetup.length > 0) && (
        <details className="rounded-control border border-line p-3">
          <summary className="cursor-pointer text-ui font-medium text-fg-body">
            Not available for calls ({unavailable.length + needsSetup.length})
          </summary>
          <ul className="mt-2 grid gap-2 sm:grid-cols-2">
            {[...unavailable, ...needsSetup].map((item) => (
              <li key={item.app} aria-disabled="true" className="min-w-0 rounded-control border border-line bg-canvas p-2.5 opacity-70">
                <span className="text-ui font-semibold text-fg-body">{item.name || prettyApp(item.app)}</span>
                <span className="mt-0.5 block break-words text-meta text-fg-body">{item.reason}</span>
                {(item.state === 'not_connected' || item.state === 'needs_reauth') && (
                  <a href="#dashboard/integrations" className="mt-1 inline-flex items-center gap-1 text-meta font-medium text-accent-fg underline">
                    Connect on Integrations page <ExternalLink className="h-3 w-3" aria-hidden="true" />
                  </a>
                )}
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}

import React, { useEffect, useState } from 'react';
import { Blocks, Clock, ExternalLink, Loader2, PhoneCall, RefreshCw } from 'lucide-react';
import { api } from '../../services/api';

/**
 * "Integrations for this call": which connected apps this call (or every call
 * in a campaign) may use. Only connected and verified apps are selectable;
 * the rest are shown disabled with the reason and a link to connect them.
 *
 * value: null (agent defaults) or [{ app, mode }]. onChange receives the same.
 */

const MODE_LABEL = { in_call: 'During the call', post_call: 'After the call' };
const MODE_TONE = {
  in_call: 'bg-[#EEF2FF] text-[#4338CA] border-[#C7D2FE]',
  post_call: 'bg-[#ECFDF5] text-[#047857] border-[#A7F3D0]',
};

export function ModeBadge({ mode }) {
  const Icon = mode === 'in_call' ? PhoneCall : Clock;
  return (
    <span className={`inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide ${MODE_TONE[mode] || MODE_TONE.in_call}`}>
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
      .catch((err) => { if (active) setState({ items: [], loading: false, error: err.message || 'Integrations could not be loaded.' }); });
    return () => { active = false; };
  }, [agentId, reload]);
  return { ...state, refresh: () => setReload((n) => n + 1) };
}

/** Compact read-only list used in confirmation steps and detail pages. */
export function IntegrationSelectionSummary({ selection, options = [], emptyText, inherited = false, className = '' }) {
  const names = Object.fromEntries((options || []).map((item) => [item.app, item.name]));
  if (!selection?.length) {
    return (
      <p className={`text-xs text-[#645D73] ${className}`} data-testid="integration-summary-default">
        {emptyText || 'Agent’s saved integration settings (none chosen for this call).'}
      </p>
    );
  }
  return (
    <ul className={`space-y-1.5 ${className}`} data-testid="integration-summary">
      {selection.map((item) => {
        const mode = (options.find((o) => o.app === item.app)?.modes || []).find((m) => m.mode === item.mode);
        return (
          <li key={`${item.app}-${item.mode}`} className="min-w-0 text-xs">
            <span className="flex flex-wrap items-center gap-1.5">
              <span className="font-semibold text-[#0F0E17]">{names[item.app] || prettyApp(item.app)}</span>
              <ModeBadge mode={item.mode} />
            </span>
            {mode?.description && <span className="mt-0.5 block break-words text-[#645D73]">{mode.description}</span>}
          </li>
        );
      })}
      {inherited && <li className="text-[11px] text-[#645D73]">Inherited from the campaign.</li>}
    </ul>
  );
}

export function prettyApp(app) {
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
          <h3 id={`integrations-${scope}-heading`} className="flex items-center gap-2 text-sm font-bold text-[#0F0E17]">
            <Blocks className="h-4 w-4 text-[#6344E7]" aria-hidden="true" />
            Integrations for {scope === 'campaign' ? 'this campaign' : 'this call'}
          </h3>
          <p className="mt-1 text-xs text-[#524E5E]">
            Choose which connected apps the agent may use for {subject}. It uses exactly these and will not offer anything
            else. If you choose none, the agent uses its saved integration settings.
          </p>
        </div>
        <button type="button" onClick={refresh} disabled={loading || !agentId}
          className="inline-flex min-h-9 items-center gap-1 rounded-lg px-2 text-xs font-semibold text-[#5033C6] hover:bg-[#F0EEF6] disabled:opacity-50">
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} aria-hidden="true" /> Refresh
        </button>
      </div>

      {!agentId && <p className="text-xs text-[#645D73]">Choose an agent to see its integrations.</p>}
      {loading && <p role="status" className="flex items-center gap-2 text-xs text-[#524E5E]"><Loader2 className="h-3.5 w-3.5 animate-spin" />Loading integrations…</p>}
      {error && <p role="alert" className="rounded-lg border border-amber-200 bg-amber-50 p-2 text-xs text-amber-900">{error} The agent’s saved integration settings will apply.</p>}

      {!loading && agentId && !error && !available.length && (
        <div className="rounded-xl border border-dashed border-[#D1CFDB] p-3 text-xs text-[#524E5E]">
          No connected integrations can be used from calls yet.{' '}
          <a href="#dashboard/integrations" className="font-semibold text-[#5033C6] underline">Connect one on the Integrations page</a>.
        </div>
      )}

      {available.length > 0 && (
        <ul className="grid gap-2 sm:grid-cols-2">
          {available.map((item) => {
            const on = Boolean(selected[item.app]);
            const mode = selected[item.app] || item.defaultMode;
            const modeInfo = item.modes.find((m) => m.mode === mode) || item.modes[0];
            return (
              <li key={item.app} className={`min-w-0 rounded-xl border p-3 transition-colors ${on ? 'border-[#6344E7] bg-[#F7F5FF]' : 'border-[#E4E2EB] bg-white'}`}>
                <label className="flex cursor-pointer items-start gap-2.5">
                  <input type="checkbox" className="mt-0.5 h-4 w-4 shrink-0" checked={on} disabled={disabled}
                    onChange={() => toggle(item)} aria-describedby={`ci-desc-${scope}-${item.app}`} data-testid={`ci-toggle-${item.app}`} />
                  <span className="min-w-0">
                    <span className="flex flex-wrap items-center gap-1.5">
                      <span className="text-sm font-semibold text-[#0F0E17]">{item.name}</span>
                      <ModeBadge mode={mode} />
                    </span>
                    <span id={`ci-desc-${scope}-${item.app}`} className="mt-1 block break-words text-xs text-[#524E5E]">{modeInfo?.description}</span>
                  </span>
                </label>
                {item.modes.length > 1 && (
                  <div className="mt-2 flex flex-wrap gap-1.5 pl-6" role="radiogroup" aria-label={`When ${item.name} runs`}>
                    {item.modes.map((m) => (
                      <button key={m.mode} type="button" role="radio" aria-checked={mode === m.mode} disabled={disabled}
                        onClick={() => (on ? setMode(item, m.mode) : update({ ...selected, [item.app]: m.mode }))}
                        className={`min-h-8 rounded-lg border px-2.5 text-[11px] font-semibold ${mode === m.mode && on ? 'border-[#6344E7] bg-white text-[#5033C6]' : 'border-[#E4E2EB] text-[#524E5E]'}`}>
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
        <details className="rounded-xl border border-[#E4E2EB] p-3">
          <summary className="cursor-pointer text-xs font-semibold text-[#524E5E]">
            Not available for calls ({unavailable.length + needsSetup.length})
          </summary>
          <ul className="mt-2 grid gap-2 sm:grid-cols-2">
            {[...unavailable, ...needsSetup].map((item) => (
              <li key={item.app} aria-disabled="true" className="min-w-0 rounded-lg border border-[#EEEDF3] bg-[#FAF9FD] p-2.5 opacity-70">
                <span className="text-xs font-semibold text-[#524E5E]">{item.name}</span>
                <span className="mt-0.5 block break-words text-[11px] text-[#645D73]">{item.reason}</span>
                {(item.state === 'not_connected' || item.state === 'needs_reauth') && (
                  <a href="#dashboard/integrations" className="mt-1 inline-flex items-center gap-1 text-[11px] font-semibold text-[#5033C6] underline">
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

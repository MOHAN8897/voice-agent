import React, { useEffect, useMemo, useState } from 'react';
import { Plug } from 'lucide-react';
import { SolidCard } from '../../ui/SolidCard';
import { TactileButton } from '../../ui/TactileButton';
import { Badge } from '../../ui/StatusBadge';
import { showToast } from '../../ui/ToastHost';
import { api } from '../../../services/api';

const field = 'min-h-10 rounded-control border border-line bg-surface px-3 py-2 text-base text-ink sm:text-copy focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/15';

/** A rule as the server stores it, or the behaviour the agent gets with none. */
function effective(item) {
  if (item.rule) return { enabled: item.rule.enabled, timing: item.rule.timing, actions: item.rule.actions || [] };
  const timing = item.modes.some((m) => m.mode === item.default.timing) ? item.default.timing : item.modes[0]?.mode || 'in_call';
  return { enabled: item.default.enabled, timing, actions: [] };
}

/**
 * Which connected apps this employee uses, during or after its calls, and which
 * actions it may take. Inbound calls and calls launched without a per-call pick
 * follow these settings.
 */
export function AgentIntegrationsCard({ agentId, readOnly = false }) {
  const [items, setItems] = useState(null);
  const [draft, setDraft] = useState({});
  const [toolLimit, setToolLimit] = useState(29);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [initial, setInitial] = useState('{}');

  const load = async () => {
    setError(null);
    try {
      const data = await api.integrations.agentRules(agentId);
      const list = data?.items || [];
      const next = Object.fromEntries(list.map((i) => [i.app, effective(i)]));
      setItems(list);
      setDraft(next);
      setInitial(JSON.stringify(next));
      setToolLimit(data?.toolLimit || 29);
    } catch (err) {
      setError(err?.message || 'Could not load this employee’s integrations.');
    }
  };

  useEffect(() => { if (agentId) load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [agentId]);

  const dirty = JSON.stringify(draft) !== initial;
  const set = (app, patch) => setDraft((d) => ({ ...d, [app]: { ...d[app], ...patch } }));
  const inCallTools = useMemo(() => (items || []).reduce((n, i) => {
    const r = draft[i.app];
    if (!r?.enabled || r.timing !== 'in_call' || !i.configured) return n;
    return n + (r.actions.length || i.actions.length);
  }, 0), [items, draft]);

  const save = async () => {
    setSaving(true);
    try {
      // Apps left at their default keep following it; only real choices become rules.
      const rules = (items || [])
        .filter((i) => i.rule || JSON.stringify(draft[i.app]) !== JSON.stringify(effective({ ...i, rule: null })))
        .map((i) => ({ app: i.app, enabled: draft[i.app].enabled, timing: draft[i.app].timing, actions: draft[i.app].actions }));
      await api.integrations.saveAgentRules(agentId, rules);
      showToast('Integration settings saved. New calls use them.', 'success');
      await load();
    } catch (err) {
      showToast(err?.message || 'Could not save integration settings.', 'error');
    } finally {
      setSaving(false);
    }
  };

  return (
    <SolidCard className="space-y-4" data-testid="agent-integrations">
      <div className="flex gap-3">
        <Plug className="h-5 w-5 shrink-0 text-accent" aria-hidden="true" />
        <div>
          <h3 className="text-title text-ink">Apps this employee uses</h3>
          <p className="mt-1 text-ui leading-relaxed text-fg-muted">
            Choose which connected apps this employee may use, and when. Inbound calls, and outbound calls started without choosing apps, follow these settings. After-call actions only run when you turn them on here.
          </p>
        </div>
      </div>
      {error ? <p role="alert" className="rounded-control bg-warning-soft p-3 text-copy text-warning-fg">{error}</p>
        : !items ? <p role="status" className="text-copy">Loading integrations…</p>
        : items.length === 0 ? <p className="text-copy text-fg-muted">No apps are connected yet. Connect them on the Integrations page.</p>
        : <>
          <ul className="space-y-3">
            {items.map((item) => {
              const r = draft[item.app];
              const limited = r.actions.length > 0;
              return (
                <li key={item.app} className="rounded-control border border-line p-3 space-y-2" data-testid={`agent-integration-${item.app.toLowerCase()}`}>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <label className="flex items-center gap-3 text-copy font-medium text-ink">
                      <input type="checkbox" className="h-4 w-4 accent-accent" checked={r.enabled} disabled={readOnly || !item.configured}
                        aria-label={`Use ${item.name}`} onChange={(e) => set(item.app, { enabled: e.target.checked })} />
                      {item.name}
                    </label>
                    {!item.configured ? <Badge tone="warning">Set up needed</Badge>
                      : item.modes.length > 1 ? (
                        <select className={field} value={r.timing} disabled={readOnly || !r.enabled} aria-label={`When ${item.name} is used`}
                          onChange={(e) => set(item.app, { timing: e.target.value, actions: [] })}>
                          {item.modes.map((m) => <option key={m.mode} value={m.mode}>{m.mode === 'in_call' ? 'During the call' : 'After the call'}</option>)}
                        </select>)
                      : <Badge tone="neutral">{item.modes[0]?.mode === 'post_call' ? 'After the call' : 'During the call'}</Badge>}
                  </div>
                  {!item.configured
                    ? <p className="text-meta text-fg-muted">{item.setupNote} Finish it on the Integrations page.</p>
                    : <p className="text-meta text-fg-muted">{item.modes.find((m) => m.mode === r.timing)?.description}</p>}
                  {item.scriptNote && r.enabled && <p className="text-meta text-warning-fg">{item.scriptNote}</p>}
                  {item.configured && r.enabled && r.timing === 'in_call' && item.actions.length > 1 && (
                    <details className="text-ui" open={limited}>
                      <summary className="cursor-pointer text-meta font-medium text-fg-body">
                        {limited ? `Limited to ${r.actions.length} of ${item.actions.length} actions` : `All ${item.actions.length} actions allowed`}
                      </summary>
                      <div className="mt-2 grid gap-1.5 sm:grid-cols-2">
                        {item.actions.map((a) => (
                          <label key={a.name} className="flex items-start gap-2 text-meta text-fg-body">
                            <input type="checkbox" className="mt-0.5 h-4 w-4 accent-accent" disabled={readOnly}
                              checked={!limited || r.actions.includes(a.name)}
                              onChange={(e) => {
                                const all = item.actions.map((x) => x.name);
                                const current = limited ? r.actions : all;
                                const next = e.target.checked ? [...new Set([...current, a.name])] : current.filter((n) => n !== a.name);
                                set(item.app, { actions: next.length === all.length ? [] : next });
                              }} />
                            {a.description}
                          </label>
                        ))}
                      </div>
                    </details>
                  )}
                  {item.configured && r.enabled && r.timing === 'post_call' && item.postCallAction && (
                    <p className="text-meta text-fg-muted">Runs once after each call, built from the call summary. Skipped when the call did not capture the details it needs.</p>
                  )}
                </li>
              );
            })}
          </ul>
          {inCallTools > toolLimit && (
            <p role="alert" className="rounded-control bg-warning-soft p-3 text-ui text-warning-fg">
              {inCallTools} actions are on during calls; only {toolLimit} fit. Apps at the end of the list will be left out. Turn some off or limit their actions.
            </p>
          )}
          <div className="flex justify-end">
            <TactileButton variant="primary" size="sm" onClick={save} disabled={readOnly || !dirty || saving} loading={saving} data-testid="agent-integrations-save">
              Save integrations
            </TactileButton>
          </div>
        </>}
    </SolidCard>
  );
}

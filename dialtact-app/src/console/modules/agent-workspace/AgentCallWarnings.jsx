import React, { useEffect, useState } from 'react';
import { AlertTriangle, ArrowRight, X } from 'lucide-react';
import { SolidCard } from '../../ui/SolidCard';
import { api } from '../../../services/api';
import { humanizeToken } from '../../../lib/internalLabels';

/** "GMAIL_CREATE_DRAFT" -> "Gmail create draft", without inventing a product name. */
function actionLabel(action) {
  return humanizeToken(String(action || '').toLowerCase());
}

function LinkButton({ onClick, children }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="mt-1 text-ui font-medium text-accent-fg hover:underline inline-flex items-center gap-1"
    >
      {children} <ArrowRight className="w-3 h-3" />
    </button>
  );
}

const DISMISS_KEY = 'dialtact.agentCallWarnings.dismissed.';

/**
 * Warnings the owner closed, per agent. Each warning has a stable key, so closing
 * hides what is on screen now and a new warning still appears. A key whose warning
 * went away is forgotten, so the same problem coming back shows again.
 */
function readDismissed(agentId) {
  try {
    const raw = window.localStorage.getItem(DISMISS_KEY + agentId);
    const parsed = raw ? JSON.parse(raw) : [];
    return new Set(Array.isArray(parsed) ? parsed : []);
  } catch {
    return new Set();
  }
}

function writeDismissed(agentId, keys) {
  try {
    window.localStorage.setItem(DISMISS_KEY + agentId, JSON.stringify([...keys]));
  } catch {
    // Private mode or blocked storage: the card simply reappears next visit.
  }
}

const skippedKey = (item) => `skip:${item.action}:${[...(item.missing || [])].sort().join(',')}`;
const questionKey = (q) => `q:${String(q.question || '').trim().toLowerCase()}`;

/**
 * Settings this employee's recent calls show need attention.
 *
 * Every item comes from `/api/app/agents/:id/call-warnings`, which reads the agent row
 * and finished call outcomes. Renders nothing when there is nothing to fix.
 */
export function AgentCallWarnings({ agent, onOpenTab }) {
  const agentId = agent?.id;
  const [data, setData] = useState(null);
  const [dismissed, setDismissed] = useState(() => (agentId ? readDismissed(agentId) : new Set()));

  useEffect(() => {
    setDismissed(agentId ? readDismissed(agentId) : new Set());
  }, [agentId]);

  useEffect(() => {
    if (!agentId) return undefined;
    let live = true;
    setData(null);
    api.agents.callWarnings(agentId)
      .then((res) => { if (live) setData(res); })
      .catch(() => { if (live) setData(null); });
    return () => { live = false; };
  }, [agentId]);

  const disclosureOff = data ? Boolean(data.recordingDisclosureOff) : agent ? !agent.recordingDisclosureEnabled : false;
  const allSkipped = data?.skippedActions || [];
  const allQuestions = data?.unansweredQuestions || [];
  const currentKeys = new Set([
    ...(disclosureOff ? ['disclosure'] : []),
    ...allSkipped.map(skippedKey),
    ...allQuestions.map(questionKey),
  ]);

  // Forget closed warnings that are no longer current, so a repeat shows again.
  useEffect(() => {
    if (!agentId || !data) return;
    const kept = new Set([...dismissed].filter((key) => currentKeys.has(key)));
    if (kept.size !== dismissed.size) {
      writeDismissed(agentId, kept);
      setDismissed(kept);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentId, data]);

  const showDisclosure = disclosureOff && !dismissed.has('disclosure');
  const skipped = allSkipped.filter((item) => !dismissed.has(skippedKey(item)));
  const questions = allQuestions.filter((q) => !dismissed.has(questionKey(q)));
  if (!showDisclosure && !skipped.length && !questions.length) return null;

  const close = () => {
    const next = new Set([...dismissed, ...currentKeys]);
    writeDismissed(agentId, next);
    setDismissed(next);
  };

  return (
    <SolidCard data-testid="agent-call-warnings" className="border-warning-line bg-warning-soft space-y-3">
      <div className="flex items-start justify-between gap-3">
        <h4 className="text-title text-warning-fg inline-flex items-center gap-2">
          <AlertTriangle className="w-4 h-4" aria-hidden="true" /> Needs your attention
        </h4>
        <button
          type="button"
          onClick={close}
          aria-label="Close. It shows again only if something new needs attention."
          title="Close. It shows again only if something new needs attention."
          data-testid="agent-call-warnings-close"
          className="-mr-1 -mt-1 inline-flex h-11 w-11 sm:h-8 sm:w-8 shrink-0 items-center justify-center rounded-control text-warning-fg hover:bg-warning-line focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
        >
          <X className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>
      <ul className="space-y-3 text-copy text-fg-body">
        {showDisclosure && (
          <li data-testid="warning-recording-disclosure">
            <p><span className="font-medium text-ink">Recording disclosure is off.</span> Callers are not told the call may be recorded.</p>
            <LinkButton onClick={() => onOpenTab?.('settings')}>Turn it on in Settings</LinkButton>
          </li>
        )}
        {skipped.map((item) => (
          <li key={item.action} data-testid="warning-skipped-action">
            <p>
              <span className="font-medium text-ink">{actionLabel(item.action)} was skipped after{' '}
                <span className="font-mono tabular-nums">{item.count}</span> call{item.count === 1 ? '' : 's'}.</span>{' '}
              The calls did not capture what it needs{item.missing?.length ? `: ${item.missing.join(', ')}` : ''}.
              Ask for these in the script, or turn the action off.
            </p>
          </li>
        ))}
        {questions.length > 0 && (
          <li data-testid="warning-unanswered-questions">
            <p><span className="font-medium text-ink">Callers asked questions this employee could not answer.</span> Add these facts to the script:</p>
            <ul className="mt-1 list-disc pl-5 space-y-0.5">
              {questions.map((q) => (
                <li key={q.question} className="break-words">
                  {q.question}{q.count > 1 ? <span className="text-fg-muted"> · asked on {q.count} calls</span> : null}
                </li>
              ))}
            </ul>
            <LinkButton onClick={() => onOpenTab?.('script')}>Open the script</LinkButton>
          </li>
        )}
      </ul>
    </SolidCard>
  );
}

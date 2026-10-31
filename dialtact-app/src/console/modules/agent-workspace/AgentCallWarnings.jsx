import React, { useEffect, useState } from 'react';
import { AlertTriangle, ArrowRight } from 'lucide-react';
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

/**
 * Settings this employee's recent calls show need attention.
 *
 * Every item comes from `/api/app/agents/:id/call-warnings`, which reads the agent row
 * and finished call outcomes. Renders nothing when there is nothing to fix.
 */
export function AgentCallWarnings({ agent, onOpenTab }) {
  const agentId = agent?.id;
  const [data, setData] = useState(null);

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
  const skipped = data?.skippedActions || [];
  const questions = data?.unansweredQuestions || [];
  if (!disclosureOff && !skipped.length && !questions.length) return null;

  return (
    <SolidCard data-testid="agent-call-warnings" className="border-warning-line bg-warning-soft space-y-3">
      <h4 className="text-title text-warning-fg inline-flex items-center gap-2">
        <AlertTriangle className="w-4 h-4" aria-hidden="true" /> Needs your attention
      </h4>
      <ul className="space-y-3 text-copy text-fg-body">
        {disclosureOff && (
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

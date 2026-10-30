import React from 'react';
import { ShieldOff } from 'lucide-react';
import { Badge } from '../ui/StatusBadge';
import { dispositionLabel, humanizeToken } from '../../lib/internalLabels';
import { relativeTime } from '../../lib/money';

export function LeadPriority({ lead, detailed = false }) {
  const a = lead.assessment;
  const scored = a?.score != null;
  return <div className="mt-2 space-y-2" data-testid="lead-priority">
    <div className="flex flex-wrap gap-1.5">
      <Badge tone={scored ? 'accent' : 'neutral'} size="xs" title={scored ? 'Priority score from this lead’s calls' : undefined}>
        {scored ? `${a.score}/100 · ${a.band} priority` : 'Priority not scored'}
      </Badge>
      {lead.doNotCall && (
        <Badge tone="warning" size="xs" title="This number is on your do-not-call list">
          <ShieldOff className="h-3 w-3" aria-hidden="true" />DND · calling blocked
        </Badge>
      )}
    </div>
    {detailed && <>
      <p className="text-meta leading-relaxed text-fg-muted">{a?.note || 'Scored from what happened on this lead’s calls. The score is separate from a confirmed sale and from permission to call.'}</p>
      {a?.components?.length > 0 && <ul className="grid gap-2 sm:grid-cols-2">{a.components.map((c) => (
        <li key={c.signal} className="min-w-0 rounded-control border border-line p-3 text-meta">
          <span className="font-medium text-ink">{humanizeToken(c.signal)}: <span className="font-mono tabular-nums">{c.points}/{c.max}</span></span>
          <span className="mt-1 block break-words text-fg-muted">{c.evidence}</span>
        </li>
      ))}</ul>}
      {a?.assessedAt && <p className="text-meta text-fg-muted">
        Scored <time dateTime={a.assessedAt} title={new Date(a.assessedAt).toLocaleString('en-IN')}>{relativeTime(a.assessedAt)}</time>
        {a.disposition ? ` · ${dispositionLabel(a.disposition)}` : ''}
      </p>}
    </>}
  </div>;
}

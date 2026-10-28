import React from 'react';

export function LeadPriority({ lead, detailed = false }) {
  const a = lead.assessment;
  return <div className="mt-2 space-y-2" data-testid="lead-priority">
    <div className="flex flex-wrap gap-2 text-xs"><span className="rounded-md bg-[#F0ECFF] px-2 py-1 font-medium text-[#5034CE]">{a?.score != null ? `${a.score}/100 · ${a.band} priority` : 'Priority not scored'}</span>{lead.doNotCall && <span className="rounded-md bg-red-50 px-2 py-1 font-medium text-red-800">DND · calling blocked</span>}</div>
    {detailed && <><p className="text-xs leading-relaxed text-[#716C7F]">{a?.note || 'Future call outcomes are scored from recorded business signals. Score is separate from tenant-confirmed conversion and permission to call.'}</p>{a?.components?.length > 0 && <ul className="grid gap-2 sm:grid-cols-2">{a.components.map((c) => <li key={c.signal} className="rounded-lg border border-[#E4E2EB] p-3 text-xs"><span className="font-medium capitalize">{c.signal}: {c.points}/{c.max}</span><span className="mt-1 block text-[#716C7F]">{c.evidence}</span></li>)}</ul>}{a?.assessedAt && <p className="text-xs text-[#716C7F]">Assessed {new Date(a.assessedAt).toLocaleString()} · {a.disposition?.replace(/_/g, ' ')}</p>}</>}
  </div>;
}

import React, { useState } from 'react';
import { FileCode2, RefreshCw, Sparkles } from 'lucide-react';
import { StepFooter } from './StepBrief';

/**
 * Step 2 — Review script.
 *
 * The compiler has already run and published the brain. This step shows the brief
 * the agent was built from and the full calling script it will follow, and lets the
 * user edit the script before it is saved back.
 */
export function StepScript({ draft, onChange, onNext, onBack, onRegenerate, busy, error }) {
  const [editing, setEditing] = useState(false);
  const script = draft.generatedScript || '';
  const variables = draft.variables || [];

  const set = (patch) => onChange({ ...draft, ...patch });

  const saveEdit = async () => {
    set({ scriptDirty: true });
    setEditing(false);
  };

  return (
    <div className="space-y-5">
      <div>
        <h3 className="text-sm font-bold text-[#0F0E17] flex items-center gap-1.5">
          <FileCode2 className="w-4 h-4 text-[#6344E7]" />
          Your agent's script
        </h3>
        <p className="text-[11px] text-[#524E5E] mt-0.5">
          Written from your description. The agent follows this on every call — read it and change
          anything that does not sound like your business.
        </p>
      </div>

      {/* The brief the agent was built from, so the user can see the source of truth. */}
      <div className="p-3.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] space-y-2">
        <div className="text-[10px] font-bold uppercase tracking-wider text-[#8C879A]">
          Built from your description
        </div>
        <p className="text-xs text-[#0F0E17] leading-relaxed whitespace-pre-line">
          {draft.brief.trim()}
        </p>
        <div className="flex flex-wrap gap-1.5 pt-1">
          <span className="text-[10px] font-mono px-2 py-0.5 rounded-lg bg-white border border-[#E4E2EB] text-[#524E5E]">
            {draft.language}
          </span>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded-lg bg-white border border-[#E4E2EB] text-[#524E5E]">
            {draft.role.replace(/_/g, ' ')}
          </span>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded-lg bg-white border border-[#E4E2EB] text-[#524E5E]">
            {draft.mode === 'bulk' ? 'Bulk caller' : 'Instant lead caller'}
          </span>
          {draft.agentName && (
            <span className="text-[10px] font-mono px-2 py-0.5 rounded-lg bg-[#F0EEF6] border border-[#6344E7]/30 text-[#5034CE]">
              {draft.agentName}
            </span>
          )}
        </div>
      </div>

      <div className="flex items-center justify-between gap-3">
        <p className="text-[10px] font-bold uppercase tracking-wider text-[#8C879A]">
          Calling script
        </p>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setEditing((v) => !v)}
            data-testid="script-toggle-edit"
            className="text-[11px] font-semibold text-[#5034CE] hover:underline"
          >
            {editing ? 'Done editing' : 'Edit script'}
          </button>
          {onRegenerate && (
            <button
              type="button"
              onClick={onRegenerate}
              disabled={busy}
              data-testid="script-regenerate"
              className="inline-flex items-center gap-1 text-[11px] font-semibold text-[#524E5E] hover:text-[#0F0E17] disabled:opacity-50"
            >
              <RefreshCw className={`w-3 h-3 ${busy ? 'animate-spin' : ''}`} />
              Regenerate
            </button>
          )}
        </div>
      </div>

      {editing ? (
        <textarea
          value={script}
          onChange={(e) => set({ generatedScript: e.target.value, scriptDirty: true })}
          onBlur={saveEdit}
          rows={16}
          data-testid="script-editor"
          className="w-full rounded-xl bg-[#FAF9FD] border border-[#6344E7] px-3.5 py-3 text-xs text-[#0F0E17] focus:outline-none resize-y leading-relaxed font-mono"
        />
      ) : (
        <pre
          data-testid="script-preview"
          className="w-full max-h-96 overflow-y-auto rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] px-3.5 py-3 text-xs text-[#0F0E17] leading-relaxed whitespace-pre-wrap font-sans"
        >
          {script || 'No script was generated. Try regenerating.'}
        </pre>
      )}

      {variables.length > 0 && (
        <div className="p-3.5 rounded-xl bg-[#FAF9FD] border border-[#E4E2EB] space-y-2">
          <div className="flex items-center gap-1.5 text-xs font-bold text-[#0F0E17]">
            <Sparkles className="w-3.5 h-3.5 text-[#6344E7]" />
            <span>Details the agent fills in during a call</span>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {variables.map((v) => (
              <span
                key={v.key}
                title={v.description || v.label}
                className="text-[10px] font-mono px-2 py-0.5 rounded-lg bg-white border border-[#E4E2EB] text-[#524E5E]"
              >
                {`{{${v.key}}}`}
              </span>
            ))}
          </div>
        </div>
      )}

      {error && (
        <div
          data-testid="employee-create-error"
          className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-900"
          role="alert"
        >
          {error}
        </div>
      )}

      <StepFooter
        onBack={onBack}
        onNext={onNext}
        nextLabel="Looks right — set up the phone"
        nextDisabled={!script.trim()}
        busy={busy}
        busyLabel="Saving…"
      />
    </div>
  );
}

import React from 'react';
import { Check } from 'lucide-react';
import { AGENT_CREATION_STEPS } from './index';

/**
 * Progress indicator for the agent creation flow.
 * `current` is a 0-based index; steps up to it are marked complete.
 */
export function Stepper({ current, maxReached, onJumpTo }) {
  return (
    <ol className="flex items-center gap-1.5" aria-label="Agent creation progress">
      {AGENT_CREATION_STEPS.map((step, index) => {
        const isDone = index < current;
        const isCurrent = index === current;
        const canJump = onJumpTo && index <= (maxReached ?? current) && !isCurrent;
        return (
          <li key={step.id} className="flex items-center gap-1.5">
            <button
              type="button"
              data-testid={`create-step-${step.id}`}
              disabled={!canJump}
              aria-current={isCurrent ? 'step' : undefined}
              onClick={() => canJump && onJumpTo(index)}
              className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[11px] font-bold transition-colors ${
                isCurrent
                  ? 'bg-[#0F0E17] text-white'
                  : canJump
                    ? 'bg-[#F0EEF6] text-[#524E5E] hover:text-[#0F0E17]'
                    : 'bg-[#FAF9FD] text-[#A9A5B4] border border-[#E4E2EB]'
              }`}
            >
              <span
                className={`flex items-center justify-center w-4 h-4 rounded-full text-[9px] ${
                  isCurrent
                    ? 'bg-white text-[#0F0E17]'
                    : isDone
                      ? 'bg-[#047857] text-white'
                      : 'bg-[#E4E2EB] text-[#8C879A]'
                }`}
              >
                {isDone ? <Check className="w-2.5 h-2.5" /> : index + 1}
              </span>
              {step.label}
            </button>
            {index < AGENT_CREATION_STEPS.length - 1 && (
              <span className="w-3 h-px bg-[#E4E2EB]" aria-hidden />
            )}
          </li>
        );
      })}
    </ol>
  );
}

import React from 'react';
import { ArrowRight, LayoutDashboard, Shield } from 'lucide-react';

/**
 * Shown when user opens #dashboard/* without a session (console is sign-in gated).
 */
export function ConsoleSignInRequired({ onSignIn, onBackToMarketing }) {
  return (
    <div className="min-h-screen flex flex-col bg-[#FAF9FD] text-[#0F0E17]">
      <header className="border-b border-[#E4E2EB] bg-white/90 backdrop-blur px-6 py-4">
        <div className="max-w-3xl mx-auto flex items-center justify-between gap-4">
          <button
            type="button"
            onClick={onBackToMarketing}
            className="text-xs font-semibold text-[#524E5E] hover:text-[#0F0E17]"
          >
            ← Back to voxly.ai
          </button>
          <span className="text-xs font-mono text-[#524E5E]">Subscriber console</span>
        </div>
      </header>

      <main className="flex-1 flex items-center justify-center px-6 py-16">
        <div className="max-w-md w-full text-center space-y-6">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-[#0F0E17] text-white mx-auto">
            <LayoutDashboard className="w-7 h-7" />
          </div>
          <div>
            <h1 className="text-2xl font-extrabold tracking-tight">Sign in to build your agent</h1>
            <p className="mt-2 text-sm text-[#524E5E] leading-relaxed">
              The user console is only available after sign-in. Create agents, assign numbers, and manage billing
              from one workspace.
            </p>
          </div>
          <ul className="text-left text-xs text-[#524E5E] space-y-2 bg-white border border-[#E4E2EB] rounded-2xl p-4">
            <li className="flex gap-2">
              <Shield className="w-4 h-4 text-[#6344E7] shrink-0 mt-0.5" />
              <span>Google or work email — same account for marketing site and console.</span>
            </li>
            <li className="flex gap-2">
              <Shield className="w-4 h-4 text-[#6344E7] shrink-0 mt-0.5" />
              <span>&ldquo;Build your agent&rdquo; on the website opens this console after you sign in.</span>
            </li>
          </ul>
          <button
            type="button"
            onClick={onSignIn}
            className="w-full inline-flex items-center justify-center gap-2 py-3.5 px-5 rounded-xl text-sm font-semibold text-white bg-[#0F0E17] hover:bg-[#232130] active:scale-[0.98] transition-all"
          >
            Continue — sign in
            <ArrowRight className="w-4 h-4" />
          </button>
        </div>
      </main>
    </div>
  );
}

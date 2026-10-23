import React from 'react';

/**
 * Rich loading skeleton for the console workspace.
 * Renders immediately when user accesses or refreshes any #dashboard route
 * while auth state or workspace data is settling, preventing view flicker,
 * unneeded auth modals, and sudden layout jumps.
 */
export function ConsoleSkeleton() {
  return (
    <div
      role="status"
      aria-label="Loading workspace"
      className="min-h-screen flex bg-[#FAF9FD] text-[#0F0E17] font-sans antialiased overflow-hidden select-none"
    >
      {/* Sidebar Skeleton */}
      <aside className="hidden md:flex w-64 border-r border-[#E9E6F2] bg-white flex-col shrink-0 justify-between">
        <div>
          {/* Logo & Workspace header */}
          <div className="h-16 px-5 border-b border-[#E9E6F2] flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-[#6344E7]/20 to-[#6344E7]/5 animate-pulse shrink-0" />
            <div className="space-y-1.5 flex-1 min-w-0">
              <div className="h-3.5 w-24 bg-[#E9E6F2] rounded-md animate-pulse" />
              <div className="h-2.5 w-16 bg-[#F0EEF6] rounded-md animate-pulse" />
            </div>
          </div>

          {/* Nav Items */}
          <div className="p-3 space-y-1.5">
            {[
              { w: 'w-24', active: true },
              { w: 'w-20' },
              { w: 'w-28' },
              { w: 'w-16' },
              { w: 'w-24' },
              { w: 'w-20' },
              { w: 'w-22' },
            ].map((item, idx) => (
              <div
                key={idx}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-xl ${
                  item.active ? 'bg-[#F0EEF6]/80' : ''
                }`}
              >
                <div className="w-5 h-5 rounded-lg bg-[#E9E6F2] animate-pulse shrink-0" />
                <div className={`h-3 ${item.w} bg-[#E9E6F2] rounded-md animate-pulse`} />
              </div>
            ))}
          </div>
        </div>

        {/* User Pill Footer */}
        <div className="p-4 border-t border-[#E9E6F2]">
          <div className="flex items-center gap-3 p-2 rounded-xl bg-[#FAF9FD]">
            <div className="w-8 h-8 rounded-full bg-[#E9E6F2] animate-pulse shrink-0" />
            <div className="flex-1 min-w-0 space-y-1">
              <div className="h-3 w-20 bg-[#E9E6F2] rounded-md animate-pulse" />
              <div className="h-2 w-28 bg-[#F0EEF6] rounded-md animate-pulse" />
            </div>
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Topbar Skeleton */}
        <header className="h-16 border-b border-[#E9E6F2] bg-white flex items-center justify-between px-6 shrink-0">
          <div className="flex items-center gap-3">
            <div className="h-4 w-28 bg-[#E9E6F2] rounded-md animate-pulse" />
            <div className="h-3 w-3 bg-[#F0EEF6] rounded-full" />
            <div className="h-4 w-36 bg-[#F0EEF6] rounded-md animate-pulse" />
          </div>

          <div className="flex items-center gap-3">
            <div className="h-9 w-28 rounded-xl bg-[#F0EEF6] animate-pulse" />
            <div className="h-9 w-24 rounded-xl bg-[#6344E7]/10 animate-pulse" />
            <div className="w-9 h-9 rounded-full bg-[#E9E6F2] animate-pulse" />
          </div>
        </header>

        {/* Dashboard Content Skeleton */}
        <main className="flex-1 overflow-y-auto p-6 lg:p-8 space-y-6">
          {/* Welcome / Header Banner */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-6 rounded-2xl bg-white border border-[#E9E6F2]">
            <div className="space-y-2">
              <div className="h-6 w-48 bg-[#E9E6F2] rounded-lg animate-pulse" />
              <div className="h-3.5 w-72 bg-[#F0EEF6] rounded-md animate-pulse" />
            </div>
            <div className="flex items-center gap-3">
              <div className="h-10 w-32 rounded-xl bg-[#6344E7]/15 animate-pulse" />
            </div>
          </div>

          {/* Metric Cards Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {[1, 2, 3, 4].map((i) => (
              <div
                key={i}
                className="p-5 rounded-2xl bg-white border border-[#E9E6F2] space-y-3"
              >
                <div className="flex items-center justify-between">
                  <div className="h-3 w-20 bg-[#F0EEF6] rounded-md animate-pulse" />
                  <div className="w-7 h-7 rounded-lg bg-[#F0EEF6] animate-pulse" />
                </div>
                <div className="h-7 w-28 bg-[#E9E6F2] rounded-lg animate-pulse" />
                <div className="h-2.5 w-16 bg-[#F0EEF6] rounded-md animate-pulse" />
              </div>
            ))}
          </div>

          {/* Main Card / Table Preview Skeleton */}
          <div className="rounded-2xl bg-white border border-[#E9E6F2] p-6 space-y-5">
            <div className="flex items-center justify-between pb-4 border-b border-[#E9E6F2]">
              <div className="space-y-1.5">
                <div className="h-4 w-32 bg-[#E9E6F2] rounded-md animate-pulse" />
                <div className="h-3 w-48 bg-[#F0EEF6] rounded-md animate-pulse" />
              </div>
              <div className="h-8 w-24 rounded-lg bg-[#F0EEF6] animate-pulse" />
            </div>

            {/* Simulated Table Rows */}
            <div className="space-y-3">
              {[1, 2, 3, 4, 5].map((row) => (
                <div
                  key={row}
                  className="flex items-center justify-between p-3.5 rounded-xl bg-[#FAF9FD] border border-[#F0EEF6]"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-lg bg-[#E9E6F2] animate-pulse" />
                    <div className="space-y-1">
                      <div className="h-3.5 w-36 bg-[#E9E6F2] rounded-md animate-pulse" />
                      <div className="h-2.5 w-20 bg-[#F0EEF6] rounded-md animate-pulse" />
                    </div>
                  </div>
                  <div className="hidden sm:flex items-center gap-6">
                    <div className="h-3 w-16 bg-[#F0EEF6] rounded-md animate-pulse" />
                    <div className="h-6 w-20 rounded-full bg-[#E9E6F2]/80 animate-pulse" />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}

export default ConsoleSkeleton;

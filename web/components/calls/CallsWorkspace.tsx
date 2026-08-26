"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ensureArray } from "@/lib/ensure-array";
import { ConsolePage } from "@/components/console/ConsolePage";
import { PageHeader } from "@/components/console/PageHeader";
import { CallsFilterBar, type CallsFilters } from "@/components/calls/CallsFilterBar";
import { CallsListPanel } from "@/components/calls/CallsListPanel";
import { CallDetailInspector } from "@/components/calls/CallDetailInspector";
import type { CallListItem } from "@/lib/call-list-utils";

const EMPTY_FILTERS: CallsFilters = {
  search: "",
  channel: "",
  disposition: "",
  since: "",
  until: "",
};

function toSinceIso(date: string): string | undefined {
  if (!date) return undefined;
  return new Date(`${date}T00:00:00`).toISOString();
}

function toUntilIso(date: string): string | undefined {
  if (!date) return undefined;
  return new Date(`${date}T23:59:59`).toISOString();
}

export function CallsWorkspace() {
  const [filters, setFilters] = useState<CallsFilters>(EMPTY_FILTERS);
  const [calls, setCalls] = useState<CallListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const loadCalls = useCallback(async (active: CallsFilters) => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ limit: "50" });
      if (active.disposition) params.set("disposition", active.disposition);
      const since = toSinceIso(active.since);
      const until = toUntilIso(active.until);
      if (since) params.set("since", since);
      if (until) params.set("until", until);

      const r = await fetch(`/api/calls?${params}`, { credentials: "include" });
      if (!r.ok) throw new Error("list failed");
      const j = await r.json();
      let list = ensureArray<CallListItem>(j.calls);
      if (active.channel) {
        list = list.filter((c) => (c.channel || "").toLowerCase() === active.channel.toLowerCase());
      }
      if (active.search.trim()) {
        const q = active.search.trim().toLowerCase();
        list = list.filter((c) => c.call_id.toLowerCase().includes(q));
      }
      setCalls(list);
      setTotal(typeof j.total === "number" ? j.total : list.length);
      setSelectedId((prev) => {
        if (prev && list.some((c) => c.call_id === prev)) return prev;
        return list[0]?.call_id ?? null;
      });
    } catch {
      setCalls([]);
      setTotal(0);
      setSelectedId(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadCalls(EMPTY_FILTERS);
  }, [loadCalls]);

  const selectedCall = useMemo(
    () => calls.find((c) => c.call_id === selectedId) ?? null,
    [calls, selectedId]
  );

  function applyFilters() {
    loadCalls(filters);
  }

  function resetFilters() {
    setFilters(EMPTY_FILTERS);
    loadCalls(EMPTY_FILTERS);
  }

  return (
    <ConsolePage className="space-y-6">
      <PageHeader
        eyebrow="Recording archive"
        title="Calls"
        description="Transcript, memory, audio, and disposition — filter the archive and inspect each call."
      />

      <CallsFilterBar
        filters={filters}
        onChange={(patch) => setFilters((prev) => ({ ...prev, ...patch }))}
        onApply={applyFilters}
        onReset={resetFilters}
        total={total}
        loading={loading}
      />

      <div className="grid gap-6 xl:grid-cols-[minmax(0,380px)_minmax(0,1fr)]">
        <CallsListPanel
          calls={calls}
          selectedId={selectedId}
          onSelect={setSelectedId}
          loading={loading}
        />
        <CallDetailInspector call={selectedCall} />
      </div>
    </ConsolePage>
  );
}

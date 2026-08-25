"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { DevCard } from "@/components/dev/DevCard";
import { ensureArray } from "@/lib/ensure-array";
import { portalFetch, refreshPortalSession } from "@/lib/auth-client";

type PlivoStatus = {
  enabled?: boolean;
  configured?: boolean;
  ready?: boolean;
  webhook_base?: string | null;
  answer_url?: string | null;
  default_number?: string | null;
  assignments?: Record<string, string>;
};

type PhoneRow = {
  e164: string;
  status?: string;
  assigned_agent_id?: string | null;
  source?: string;
};

export function PstnTestPanel({ agentId, tier }: { agentId: string; tier: string }) {
  const [status, setStatus] = useState<PlivoStatus | null>(null);
  const [numbers, setNumbers] = useState<PhoneRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [registerE164, setRegisterE164] = useState("");
  const [fromE164, setFromE164] = useState("");
  const [toE164, setToE164] = useState("");
  const [assignE164, setAssignE164] = useState("");

  const load = useCallback(async () => {
    await refreshPortalSession("dev");
    const [stR, numR] = await Promise.all([
      portalFetch("dev", "/api/dev/plivo/status"),
      portalFetch("dev", "/api/dev/plivo/numbers"),
    ]);
    if (stR.ok) setStatus(await stR.json());
    if (numR.ok) {
      const j = await numR.json();
      const list = ensureArray<PhoneRow>(j.numbers);
      setNumbers(list);
      if (list[0]?.e164) {
        setFromE164(j.numbers[0].e164);
        setAssignE164(j.numbers[0].e164);
      }
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function registerNumber() {
    if (!registerE164.trim()) return;
    setMessage("Registering number…");
    const r = await portalFetch("dev", "/api/dev/plivo/numbers", {
      method: "POST",
      body: JSON.stringify({ e164: registerE164.trim() }),
    });
    setMessage(r.ok ? "Number registered" : "Register failed");
    if (r.ok) {
      setRegisterE164("");
      await load();
    }
  }

  async function assignNumber() {
    if (!assignE164.trim()) return;
    setMessage("Assigning number to agent…");
    const r = await portalFetch("dev", "/api/dev/plivo/numbers/assign", {
      method: "PUT",
      body: JSON.stringify({ e164: assignE164.trim(), agentId }),
    });
    setMessage(r.ok ? `Assigned ${assignE164} → this agent` : "Assign failed");
    if (r.ok) await load();
  }

  async function outboundDial() {
    if (!toE164.trim()) {
      setMessage("Enter destination number");
      return;
    }
    setMessage("Placing outbound test call…");
    const r = await portalFetch("dev", "/api/dev/plivo/outbound", {
      method: "POST",
      body: JSON.stringify({
        toE164: toE164.trim(),
        fromE164: fromE164.trim() || undefined,
        agentId,
        tier,
      }),
    });
    const j = await r.json();
    setMessage(
      r.ok
        ? `Outbound queued · request ${j.request_uuid || "ok"}`
        : j.error?.message || "Outbound failed"
    );
  }

  if (loading) return <p className="text-sm text-text-muted">Loading Plivo status…</p>;

  const notReady = !status?.enabled || !status?.configured;

  if (notReady) {
    return (
      <DevCard title="PSTN · Plivo" description="Phone channel not ready">
        <div className="rounded-xl border border-dashed border-warning/40 bg-warning/5 p-5">
          <p className="font-medium text-warning">Plivo not connected</p>
          <p className="mt-2 text-sm text-text-muted">
            Enable <span className="font-mono">ENABLE_PLIVO</span>, add auth credentials, and set{" "}
            <span className="font-mono">PLIVO_WEBHOOK_BASE_URL</span> so inbound/outbound can reach your API.
          </p>
          <ul className="mt-4 space-y-2 text-sm text-text-muted">
            <li className="flex gap-2">
              <span className={status?.enabled ? "text-success" : "text-text-subtle"}>
                {status?.enabled ? "✓" : "○"}
              </span>
              ENABLE_PLIVO toggle on
            </li>
            <li className="flex gap-2">
              <span className={status?.configured ? "text-success" : "text-text-subtle"}>
                {status?.configured ? "✓" : "○"}
              </span>
              PLIVO_AUTH_ID and PLIVO_AUTH_TOKEN set
            </li>
            <li className="flex gap-2">
              <span className={status?.answer_url ? "text-success" : "text-text-subtle"}>
                {status?.answer_url ? "✓" : "○"}
              </span>
              Public webhook URL configured
            </li>
          </ul>
          <Link href="/dev/environment" className="mt-4 inline-block text-sm font-medium text-accent hover:underline">
            Open Environment →
          </Link>
        </div>
        <p className="mt-4 text-xs text-text-subtle">
          Browser Test Studio still works without Plivo. PSTN shares the same call ledger once connected.
        </p>
      </DevCard>
    );
  }

  return (
    <div className="space-y-6">
      <DevCard title="PSTN readiness" description="Plivo credentials and webhook routing">
        <dl className="grid gap-3 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-text-muted">Answer URL</dt>
            <dd className="mt-1 font-mono text-xs text-text break-all">{status?.answer_url || "—"}</dd>
          </div>
          <div>
            <dt className="text-text-muted">Webhook base</dt>
            <dd className="mt-1 font-mono text-xs text-text">{status?.webhook_base || "—"}</dd>
          </div>
          <div>
            <dt className="text-text-muted">Default number</dt>
            <dd className="mt-1 font-mono text-text">{status?.default_number || "—"}</dd>
          </div>
          <div>
            <dt className="text-text-muted">Assigned to this agent</dt>
            <dd className="mt-1 font-mono text-text">
              {numbers.filter((n) => n.assigned_agent_id === agentId).map((n) => n.e164).join(", ") || "—"}
            </dd>
          </div>
        </dl>
      </DevCard>

      <DevCard title="Phone numbers" description="Register, assign inbound routing, sync from Plivo account">
        <div className="space-y-4">
          <div className="flex flex-wrap gap-2">
            <input
              type="text"
              placeholder="+91XXXXXXXXXX"
              value={registerE164}
              onChange={(e) => setRegisterE164(e.target.value)}
              className="rounded-xl border border-surface-border bg-surface-raised px-3 py-2 text-sm font-mono"
            />
            <Button type="button" variant="secondary" onClick={registerNumber}>Register in DB</Button>
          </div>

          <div className="overflow-x-auto rounded-xl border border-surface-border-subtle">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-surface-border-subtle bg-surface-raised text-xs text-text-muted">
                <tr>
                  <th className="px-3 py-2">Number</th>
                  <th className="px-3 py-2">Source</th>
                  <th className="px-3 py-2">Assigned agent</th>
                </tr>
              </thead>
              <tbody>
                {numbers.length === 0 ? (
                  <tr>
                    <td colSpan={3} className="px-3 py-4 text-text-muted">No numbers — register or sync from Plivo.</td>
                  </tr>
                ) : (
                  numbers.map((n) => (
                    <tr key={n.e164} className="border-b border-surface-border-subtle/50">
                      <td className="px-3 py-2 font-mono">{n.e164}</td>
                      <td className="px-3 py-2 text-text-muted">{n.source || "—"}</td>
                      <td className="px-3 py-2 font-mono text-xs">
                        {n.assigned_agent_id || "—"}
                        {n.assigned_agent_id === agentId && (
                          <span className="ml-2 text-success">(this agent)</span>
                        )}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          <div className="flex flex-wrap items-end gap-2">
            <label className="block text-sm">
              <span className="text-text-muted">Assign to this agent</span>
              <select
                className="mt-1 rounded-xl border border-surface-border bg-surface-raised px-3 py-2 text-sm font-mono"
                value={assignE164}
                onChange={(e) => setAssignE164(e.target.value)}
              >
                <option value="">Select number</option>
                {numbers.map((n) => (
                  <option key={n.e164} value={n.e164}>{n.e164}</option>
                ))}
              </select>
            </label>
            <Button type="button" variant="secondary" onClick={assignNumber}>Assign inbound</Button>
          </div>
        </div>
      </DevCard>

      <DevCard title="Outbound test call" description="Plivo REST originate → same answer URL → PSTN stream">
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="block text-sm">
            <span className="text-text-muted">From (CLI)</span>
            <select
              className="mt-2 w-full rounded-xl border border-surface-border bg-surface-raised px-3 py-2 text-sm font-mono"
              value={fromE164}
              onChange={(e) => setFromE164(e.target.value)}
            >
              {numbers.map((n) => (
                <option key={n.e164} value={n.e164}>{n.e164}</option>
              ))}
              {status?.default_number && !numbers.some((n) => n.e164 === status.default_number) && (
                <option value={status.default_number}>{status.default_number}</option>
              )}
            </select>
          </label>
          <label className="block text-sm">
            <span className="text-text-muted">To (test handset)</span>
            <input
              type="text"
              value={toE164}
              onChange={(e) => setToE164(e.target.value)}
              placeholder="+91XXXXXXXXXX"
              className="mt-2 w-full rounded-xl border border-surface-border bg-surface-raised px-3 py-2 text-sm font-mono"
            />
          </label>
        </div>
        <Button type="button" className="mt-4" onClick={outboundDial}>Place outbound test call</Button>
        <p className="mt-3 text-xs text-text-muted">
          Uses tier <span className="font-mono">{tier}</span> metadata on originate. Call appears in Calls when stream connects.
        </p>
      </DevCard>

      {message && <p className="text-sm text-text-muted">{message}</p>}
    </div>
  );
}

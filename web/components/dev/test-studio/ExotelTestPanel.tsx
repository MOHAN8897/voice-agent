"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { DevCard } from "@/components/dev/DevCard";
import { ensureArray } from "@/lib/ensure-array";
import { portalFetch, refreshPortalSession } from "@/lib/auth-client";

type ExotelStatus = {
  ok?: boolean;
  enabled?: boolean;
  configured?: boolean;
  handshake_ok?: boolean;
  handshake_error?: string | null;
  balance?: string | null;
  ready?: boolean;
  webhook_base?: string | null;
  passthru_url?: string | null;
  status_callback_url?: string | null;
  exophone?: string | null;
  account_sid?: string | null;
  subdomain?: string | null;
  stream_url_resolver?: string | null;
  recent_calls?: ExotelCallRow[];
};

type ExotelCallRow = {
  call_sid: string;
  status?: string;
  from?: string;
  to?: string;
  direction?: string;
  duration?: string;
  last_event?: string;
  updated_at?: number;
};

type PhoneRow = {
  e164: string;
  status?: string;
  assigned_agent_id?: string | null;
  source?: string;
};

function CheckItem({ ok, label }: { ok: boolean; label: string }) {
  return (
    <li className="flex gap-2">
      <span className={ok ? "text-success" : "text-text-subtle"}>{ok ? "✓" : "○"}</span>
      {label}
    </li>
  );
}

function CopyField({ label, value }: { label: string; value: string | null | undefined }) {
  const [copied, setCopied] = useState(false);
  if (!value) return null;
  return (
    <div>
      <dt className="text-text-muted">{label}</dt>
      <dd className="mt-1 flex items-start gap-2">
        <span className="font-mono text-xs text-text break-all">{value}</span>
        <button
          type="button"
          className="shrink-0 text-xs text-accent hover:underline"
          onClick={async () => {
            await navigator.clipboard.writeText(value);
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
          }}
        >
          {copied ? "Copied" : "Copy"}
        </button>
      </dd>
    </div>
  );
}

export function ExotelTestPanel({ agentId, tier }: { agentId: string; tier: string }) {
  const [status, setStatus] = useState<ExotelStatus | null>(null);
  const [numbers, setNumbers] = useState<PhoneRow[]>([]);
  const [calls, setCalls] = useState<ExotelCallRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [registerE164, setRegisterE164] = useState("");
  const [fromE164, setFromE164] = useState("");
  const [toE164, setToE164] = useState("");
  const [callerId, setCallerId] = useState("");
  const [assignE164, setAssignE164] = useState("");
  const [outboundMode, setOutboundMode] = useState<"voice_ai" | "bridge">("voice_ai");
  const [selectedCall, setSelectedCall] = useState<string | null>(null);
  const [callDetail, setCallDetail] = useState<Record<string, unknown> | null>(null);
  const dialingRef = useRef(false);

  const load = useCallback(async () => {
    await refreshPortalSession("dev");
    const [stR, numR, callsR] = await Promise.all([
      portalFetch("dev", "/api/dev/exotel/status"),
      portalFetch("dev", "/api/dev/exotel/numbers"),
      portalFetch("dev", "/api/dev/exotel/calls"),
    ]);
    if (stR.ok) {
      const j = await stR.json();
      setStatus(j);
      if (j.exophone) setCallerId(j.exophone);
    }
    if (numR.ok) {
      const j = await numR.json();
      const list = ensureArray<PhoneRow>(j.numbers);
      setNumbers(list);
      if (list[0]?.e164 && !fromE164) setFromE164(list[0].e164);
      if (list[0]?.e164 && !assignE164) setAssignE164(list[0].e164);
      if (j.exophone && !callerId) setCallerId(j.exophone);
    }
    if (callsR.ok) {
      const j = await callsR.json();
      setCalls(ensureArray<ExotelCallRow>(j.calls));
    }
    setLoading(false);
  }, [assignE164, callerId, fromE164]);

  useEffect(() => {
    load();
  }, [load]);

  async function runHandshake() {
    setBusy(true);
    setMessage("Running Exotel handshake (Balance API)…");
    const r = await portalFetch("dev", "/api/dev/exotel/handshake", { method: "POST" });
    const j = await r.json();
    if (r.ok && j.ok) {
      setMessage(`Handshake OK · balance ${j.handshake?.balance ?? "—"} ${j.handshake?.currency ?? ""}`.trim());
    } else {
      const err = j.error;
      setMessage(
        `Handshake failed: ${err?.message || "unknown"}${err?.status_code ? ` (HTTP ${err.status_code})` : ""}`
      );
    }
    setBusy(false);
    await load();
  }

  async function registerNumber() {
    if (!registerE164.trim()) return;
    setMessage("Registering number…");
    const r = await portalFetch("dev", "/api/dev/exotel/numbers", {
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
    const r = await portalFetch("dev", "/api/dev/exotel/numbers/assign", {
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
    if (outboundMode === "bridge" && !fromE164.trim()) {
      setMessage("Bridge mode requires agent handset (From) number");
      return;
    }
    if (dialingRef.current || busy) {
      return;
    }
    dialingRef.current = true;
    setBusy(true);
    setMessage(
      outboundMode === "voice_ai"
        ? "Placing Voice AI outbound call (AgentStream)…"
        : "Placing bridge call via Exotel connect…"
    );
    const r = await portalFetch("dev", "/api/dev/exotel/outbound", {
      method: "POST",
      body: JSON.stringify({
        toE164: toE164.trim(),
        fromE164: fromE164.trim() || undefined,
        callerId: callerId.trim() || undefined,
        agentId,
        tier,
        mode: outboundMode,
      }),
    });
    const j = await r.json();
    setMessage(
      r.ok
        ? `Call queued · SID ${j.call_sid || "ok"} · status ${j.status || "—"}`
        : j.error?.message || "Outbound failed"
    );
    setBusy(false);
    dialingRef.current = false;
    if (r.ok) await load();
  }

  async function refreshCall(callSid: string) {
    setSelectedCall(callSid);
    setMessage(`Refreshing call ${callSid.slice(0, 12)}…`);
    const r = await portalFetch("dev", `/api/dev/exotel/calls/${encodeURIComponent(callSid)}`);
    if (r.ok) {
      const j = await r.json();
      setCallDetail(j);
      setMessage(j.remote_error ? `Remote: ${j.remote_error}` : "Call status refreshed");
    } else {
      setMessage("Failed to refresh call");
    }
    await load();
  }

  if (loading) return <p className="text-sm text-text-muted">Loading Exotel status…</p>;

  const checklist = {
    enabled: Boolean(status?.enabled),
    configured: Boolean(status?.configured),
    handshake: Boolean(status?.handshake_ok),
    webhook: Boolean(status?.status_callback_url),
  };
  const notReady = !checklist.enabled || !checklist.configured || !checklist.handshake;

  if (notReady) {
    return (
      <DevCard title="PSTN · Exotel" description="Programmable Voice — connect two numbers">
        <div className="rounded-xl border border-dashed border-warning/40 bg-warning/5 p-5">
          <p className="font-medium text-warning">Exotel not ready</p>
          <p className="mt-2 text-sm text-text-muted">
            Enable <span className="font-mono">ENABLE_EXOTEL</span>, set API key/token and{" "}
            <span className="font-mono">EXOTEL_ACCOUNT_SID</span>, then run handshake. For outbound status
            callbacks, set <span className="font-mono">EXOTEL_WEBHOOK_BASE_URL</span> to your public tunnel URL.
          </p>
          {status?.handshake_error && (
            <p className="mt-3 rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger">{status.handshake_error}</p>
          )}
          <ul className="mt-4 space-y-2 text-sm text-text-muted">
            <CheckItem ok={checklist.enabled} label="ENABLE_EXOTEL toggle on" />
            <CheckItem ok={checklist.configured} label="EXOTEL_API_KEY, EXOTEL_API_TOKEN, EXOTEL_ACCOUNT_SID set" />
            <CheckItem ok={checklist.handshake} label="Balance API handshake succeeds" />
            <CheckItem ok={checklist.webhook} label="Public webhook URL configured (for outbound)" />
          </ul>
          <div className="mt-4 flex flex-wrap gap-2">
            <Button type="button" onClick={runHandshake} disabled={busy}>
              {busy ? "Testing…" : "Test handshake"}
            </Button>
            <Link href="/dev/environment" className="inline-flex items-center text-sm font-medium text-accent hover:underline">
              Open Environment →
            </Link>
          </div>
        </div>
        <p className="mt-4 text-xs text-text-subtle">
          Browser Test Studio works without PSTN. See{" "}
          <a
            href="https://developer.exotel.com/docs/voice"
            target="_blank"
            rel="noreferrer"
            className="text-accent hover:underline"
          >
            Exotel Programmable Voice docs
          </a>
          .
        </p>
        {message && <p className="mt-3 text-sm text-text-muted">{message}</p>}
      </DevCard>
    );
  }

  const terminal = new Set(["completed", "failed", "busy", "no-answer", "canceled"]);

  return (
    <div className="space-y-6">
      <DevCard title="Exotel handshake" description="Credentials verified via Balance API">
        <dl className="grid gap-3 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-text-muted">Account SID</dt>
            <dd className="mt-1 font-mono text-xs">{status?.account_sid || "—"}</dd>
          </div>
          <div>
            <dt className="text-text-muted">Balance</dt>
            <dd className="mt-1 font-mono text-text">{status?.balance ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-text-muted">Subdomain</dt>
            <dd className="mt-1 font-mono text-xs">{status?.subdomain || "—"}</dd>
          </div>
          <div>
            <dt className="text-text-muted">ExoPhone (CallerId)</dt>
            <dd className="mt-1 font-mono text-text">{status?.exophone || "—"}</dd>
          </div>
          <CopyField label="Passthru URL (inbound flow)" value={status?.passthru_url} />
          <CopyField label="Status callback URL (outbound)" value={status?.status_callback_url} />
          <CopyField label="Stream URL resolver (Voicebot)" value={status?.stream_url_resolver} />
        </dl>
        <Button type="button" variant="secondary" className="mt-4" onClick={runHandshake} disabled={busy}>
          Re-test handshake
        </Button>
      </DevCard>

      <DevCard title="Phone numbers" description="Register ExoPhone, assign inbound routing to this agent">
        <div className="space-y-4">
          <div className="flex flex-wrap gap-2">
            <input
              type="text"
              placeholder="+91XXXXXXXXXX"
              value={registerE164}
              onChange={(e) => setRegisterE164(e.target.value)}
              className="rounded-xl border border-surface-border bg-surface-raised px-3 py-2 text-sm font-mono"
            />
            <Button type="button" variant="secondary" onClick={registerNumber}>
              Register in DB
            </Button>
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
                    <td colSpan={3} className="px-3 py-4 text-text-muted">
                      No numbers — set EXOTEL_EXOPHONE or register one.
                    </td>
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
                  <option key={n.e164} value={n.e164}>
                    {n.e164}
                  </option>
                ))}
              </select>
            </label>
            <Button type="button" variant="secondary" onClick={assignNumber}>
              Assign inbound
            </Button>
          </div>
        </div>
      </DevCard>

      <DevCard
        title="Outbound test call"
        description="Voice AI dials customer and streams to agent (default). Bridge rings two handsets."
      >
        <div className="mb-4 flex flex-wrap gap-2 text-sm">
          <label className="flex items-center gap-2">
            <input
              type="radio"
              name="exotel-mode"
              checked={outboundMode === "voice_ai"}
              onChange={() => setOutboundMode("voice_ai")}
            />
            Voice AI (AgentStream)
          </label>
          <label className="flex items-center gap-2">
            <input
              type="radio"
              name="exotel-mode"
              checked={outboundMode === "bridge"}
              onChange={() => setOutboundMode("bridge")}
            />
            Bridge two phones
          </label>
        </div>
        <div className="grid gap-4 sm:grid-cols-3">
          {outboundMode === "bridge" && (
            <label className="block text-sm">
              <span className="text-text-muted">From (agent handset)</span>
              <input
                type="text"
                value={fromE164}
                onChange={(e) => setFromE164(e.target.value)}
                placeholder="+91XXXXXXXXXX"
                className="mt-2 w-full rounded-xl border border-surface-border bg-surface-raised px-3 py-2 text-sm font-mono"
              />
            </label>
          )}
          <label className="block text-sm">
            <span className="text-text-muted">To (customer)</span>
            <input
              type="text"
              value={toE164}
              onChange={(e) => setToE164(e.target.value)}
              placeholder="08897908470"
              className="mt-2 w-full rounded-xl border border-surface-border bg-surface-raised px-3 py-2 text-sm font-mono"
            />
          </label>
          <label className="block text-sm">
            <span className="text-text-muted">CallerId (ExoPhone)</span>
            <input
              type="text"
              value={callerId}
              onChange={(e) => setCallerId(e.target.value)}
              placeholder="+91XXXXXXXXXX"
              className="mt-2 w-full rounded-xl border border-surface-border bg-surface-raised px-3 py-2 text-sm font-mono"
            />
          </label>
        </div>
        {!status?.exophone && (
          <p className="mt-3 rounded-lg bg-warning/10 px-3 py-2 text-xs text-warning">
            No ExoPhone on account — set <span className="font-mono">EXOTEL_EXOPHONE</span> in Environment from your
            Exotel dashboard (CoPilot → ExoPhones).
          </p>
        )}
        <Button type="button" className="mt-4" onClick={outboundDial} disabled={busy}>
          {busy ? "Dialing…" : outboundMode === "voice_ai" ? "Place Voice AI call" : "Place bridge call"}
        </Button>
        <p className="mt-3 text-xs text-text-muted">
          Voice AI uses tier <span className="font-mono">{tier}</span> and streams audio to{" "}
          <span className="font-mono">/ws/exotel-stream</span> via your public tunnel.
        </p>
      </DevCard>

      <DevCard title="Active & recent calls" description="Local registry + Exotel call details">
        <div className="overflow-x-auto rounded-xl border border-surface-border-subtle">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-surface-border-subtle bg-surface-raised text-xs text-text-muted">
              <tr>
                <th className="px-3 py-2">Call SID</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">From → To</th>
                <th className="px-3 py-2">Actions</th>
              </tr>
            </thead>
            <tbody>
              {calls.length === 0 ? (
                <tr>
                  <td colSpan={4} className="px-3 py-4 text-text-muted">
                    No calls yet — place an outbound test or receive inbound via Passthru flow.
                  </td>
                </tr>
              ) : (
                calls.map((c) => {
                  const st = (c.status || "").toLowerCase();
                  const isLive = st && !terminal.has(st);
                  return (
                    <tr key={c.call_sid} className="border-b border-surface-border-subtle/50">
                      <td className="px-3 py-2 font-mono text-xs">{c.call_sid?.slice(0, 20)}…</td>
                      <td className="px-3 py-2">
                        <span className={isLive ? "text-success" : "text-text-muted"}>{c.status || "—"}</span>
                      </td>
                      <td className="px-3 py-2 font-mono text-xs">
                        {c.from || "—"} → {c.to || "—"}
                      </td>
                      <td className="px-3 py-2">
                        <Button type="button" variant="ghost" onClick={() => refreshCall(c.call_sid)}>
                          Refresh
                        </Button>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
        {selectedCall && callDetail && (
          <pre className="mt-4 max-h-48 overflow-auto rounded-xl border border-surface-border-subtle bg-surface-raised p-3 text-xs">
            {JSON.stringify(callDetail, null, 2)}
          </pre>
        )}
      </DevCard>

      {message && <p className="text-sm text-text-muted">{message}</p>}
    </div>
  );
}

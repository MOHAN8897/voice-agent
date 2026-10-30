"use client";

import { useEffect, useMemo, useState } from "react";
import { SkeuoButton } from "@/components/ui/skeuo";
import { adminAction, devFetch, useAdminResource } from "@/lib/useAdminResource";
import { cn } from "@/lib/cn";
import { PLANS, ROLE_LABEL, USER_ROLES, money, runBulk, type ListPage, type Workspace } from "./model";
import { ActionDialog, Field, Modal, Notice, TextInput, selectClass, useDebounced } from "./ui";

/* ------------------------------------------------------------------ pickers */

/** Searchable workspace picker backed by the server list (never the whole table). */
export function WorkspacePicker({
  value,
  onChange,
  label = "Workspace",
  hint,
  excludeId,
}: {
  value: string;
  onChange: (tenantId: string, ws: Workspace | null) => void;
  label?: string;
  hint?: string;
  excludeId?: string | null;
}) {
  const [q, setQ] = useState("");
  const dq = useDebounced(q, 250);
  const res = useAdminResource<ListPage<Workspace>>(
    `/api/dev/admin/accounts/workspaces?sort=name&dir=asc&limit=50${dq ? `&q=${encodeURIComponent(dq)}` : ""}`,
    [dq]
  );
  const options = (res.data?.items ?? []).filter((w) => w.tenantId !== excludeId);
  const selected = options.find((w) => w.tenantId === value) ?? null;
  return (
    <Field label={label} hint={hint}>
      <div className="space-y-1.5">
        <TextInput value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search workspaces by name or ID…" aria-label={`Search ${label}`} />
        <select
          value={value}
          onChange={(e) => onChange(e.target.value, options.find((w) => w.tenantId === e.target.value) ?? null)}
          className={selectClass}
          aria-label={label}
          size={Math.min(6, Math.max(3, options.length + 1))}
        >
          <option value="">{res.loading ? "Loading…" : options.length ? "Choose a workspace…" : "No workspaces match"}</option>
          {options.map((w) => (
            <option key={w.tenantId} value={w.tenantId} disabled={w.status !== "active"}>
              {w.name} · {w.status}
              {w.status !== "active" ? " (not active)" : ""} · {money(w.walletBalanceUsd)}
            </option>
          ))}
        </select>
        {selected && selected.kyc !== "approved" && (
          <p className="text-[11px] text-status-warning">This workspace has not passed voice KYC; carrier numbers may be refused.</p>
        )}
      </div>
    </Field>
  );
}

type AgentOption = { agentId: string; name: string; status?: string; numberCount: number };

export function AgentPicker({ tenantId, value, onChange }: { tenantId: string; value: string; onChange: (id: string) => void }) {
  const res = useAdminResource<{ agents: AgentOption[] }>(
    tenantId ? `/api/dev/admin/accounts/workspaces/${tenantId}/agents` : null,
    [tenantId]
  );
  const agents = res.data?.agents ?? [];
  return (
    <Field label="Agent" hint="Calls to this number are answered by the chosen agent.">
      <select value={value} onChange={(e) => onChange(e.target.value)} className={selectClass} disabled={!tenantId} aria-label="Agent">
        <option value="">{!tenantId ? "Choose a workspace first" : res.loading ? "Loading agents…" : agents.length ? "Choose an agent…" : "This workspace has no agents"}</option>
        {agents.map((a) => (
          <option key={a.agentId} value={a.agentId}>
            {a.name}
            {a.status && a.status !== "active" ? ` · ${a.status}` : ""} · {a.numberCount} number{a.numberCount === 1 ? "" : "s"}
          </option>
        ))}
      </select>
      {res.error && <span className="mt-1 block text-[11px] text-status-error">{res.error}</span>}
    </Field>
  );
}

export function RolePicker({ value, onChange }: { value: string; onChange: (r: string) => void }) {
  return (
    <Field label="Role" hint="Admin can manage the workspace; viewer is read-only.">
      <select value={value} onChange={(e) => onChange(e.target.value)} className={selectClass} aria-label="Role">
        {USER_ROLES.map((r) => (
          <option key={r} value={r}>
            {ROLE_LABEL[r] ?? r}
          </option>
        ))}
      </select>
    </Field>
  );
}

/* ------------------------------------------------------------------ create workspace */

export function CreateWorkspaceDialog({ open, onClose }: { open: boolean; onClose: (createdId?: string) => void }) {
  const [name, setName] = useState("");
  const [plan, setPlan] = useState("starter");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (open) {
      setName("");
      setPlan("starter");
      setError(null);
    }
  }, [open]);
  async function create() {
    setBusy(true);
    setError(null);
    try {
      const res = await adminAction<{ tenantId?: string }>("/api/dev/admin/tenants", {
        method: "POST",
        body: { name: name.trim(), status: "active", plan },
      });
      onClose(res.tenantId);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create the workspace");
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal open={open} title="New workspace" onClose={() => onClose()}>
      <p className="text-sm text-text-muted">Creates an empty customer workspace with a zero wallet. Invite its first admin afterwards.</p>
      <Field label="Workspace name">
        <TextInput value={name} onChange={(e) => setName(e.target.value)} placeholder="Acme Voice Corp" autoFocus />
      </Field>
      <Field label="Plan">
        <select value={plan} onChange={(e) => setPlan(e.target.value)} className={selectClass}>
          {PLANS.filter((p) => p !== "platform").map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
      </Field>
      {error && <Notice tone="error">{error}</Notice>}
      <div className="flex justify-end gap-2">
        <SkeuoButton variant="ghost" onClick={() => onClose()}>
          Cancel
        </SkeuoButton>
        <SkeuoButton variant="primary" disabled={!name.trim()} loading={busy} onClick={() => void create()}>
          Create workspace
        </SkeuoButton>
      </div>
    </Modal>
  );
}

/* ------------------------------------------------------------------ invite user */

export function InviteUserDialog({
  open,
  tenantId: presetTenant,
  onClose,
}: {
  open: boolean;
  tenantId?: string | null;
  onClose: (changed: boolean) => void;
}) {
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [tenantId, setTenantId] = useState(presetTenant ?? "");
  const [role, setRole] = useState("customer_admin");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<{ email: string; temp: string } | null>(null);
  useEffect(() => {
    if (open) {
      setEmail("");
      setFullName("");
      setTenantId(presetTenant ?? "");
      setRole("customer_admin");
      setError(null);
      setCreated(null);
    }
  }, [open, presetTenant]);
  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const res = await adminAction<{ devTempPassword?: string; tempPassword?: string }>("/api/dev/admin/users", {
        method: "POST",
        body: { email: email.trim(), fullName: fullName.trim(), tenantId, role },
      });
      setCreated({ email: email.trim(), temp: res.devTempPassword ?? res.tempPassword ?? "" });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create the user");
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal open={open} title="Invite user" onClose={() => onClose(Boolean(created))}>
      {created ? (
        <>
          <Notice tone="success">
            Created <strong>{created.email}</strong> as {ROLE_LABEL[role] ?? role}. The account is pending until they sign in.
          </Notice>
          {created.temp && (
            <Field label="One-time password (shown once — share it securely)">
              <code className="block break-all rounded-skeuo-sm bg-surface-panel-inset px-3 py-2 font-mono text-sm text-text">{created.temp}</code>
            </Field>
          )}
          <div className="flex justify-end">
            <SkeuoButton variant="primary" onClick={() => onClose(true)}>
              Done
            </SkeuoButton>
          </div>
        </>
      ) : (
        <>
          <Field label="Email">
            <TextInput type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="name@company.com" autoFocus />
          </Field>
          <Field label="Full name (optional)">
            <TextInput value={fullName} onChange={(e) => setFullName(e.target.value)} />
          </Field>
          <WorkspacePicker value={tenantId} onChange={(id) => setTenantId(id)} />
          <RolePicker value={role} onChange={setRole} />
          {error && <Notice tone="error">{error}</Notice>}
          <div className="flex justify-end gap-2">
            <SkeuoButton variant="ghost" onClick={() => onClose(false)}>
              Cancel
            </SkeuoButton>
            <SkeuoButton variant="primary" disabled={!email.includes("@") || !tenantId} loading={busy} onClick={() => void submit()}>
              Create user
            </SkeuoButton>
          </div>
        </>
      )}
    </Modal>
  );
}

/* ------------------------------------------------------------------ wallet */

export function WalletDialog({
  open,
  workspace,
  onClose,
}: {
  open: boolean;
  workspace: { tenantId: string; name: string; walletBalanceUsd: number } | null;
  onClose: (changed: boolean) => void;
}) {
  const [mode, setMode] = useState<"credit" | "debit">("credit");
  const [amount, setAmount] = useState("10");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (open) {
      setMode("credit");
      setAmount("10");
      setNote("");
      setError(null);
    }
  }, [open]);
  const dollars = Number(amount);
  const valid = Number.isFinite(dollars) && dollars > 0 && note.trim().length >= 8;
  async function submit() {
    if (!workspace || !valid) return;
    setBusy(true);
    setError(null);
    try {
      await adminAction("/api/dev/admin/wallets/adjust", {
        method: "POST",
        body: {
          tenantId: workspace.tenantId,
          amountUsdCents: Math.round(dollars * 100) * (mode === "credit" ? 1 : -1),
          reason: mode === "credit" ? "admin_credit" : "admin_debit",
          note: note.trim(),
        },
      });
      onClose(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Wallet adjustment failed");
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal open={open} title={`Adjust wallet · ${workspace?.name ?? ""}`} onClose={() => onClose(false)}>
      <p className="text-sm text-text-muted">
        Current balance <strong className="font-mono text-text">{money(workspace?.walletBalanceUsd)}</strong>. For INR adjustments and the
        full ledger, use the workspace page.
      </p>
      <div className="grid grid-cols-2 gap-2">
        {(["credit", "debit"] as const).map((m) => (
          <button
            key={m}
            type="button"
            onClick={() => setMode(m)}
            className={cn(
              "rounded-skeuo-sm border py-2 text-xs font-semibold",
              mode === m
                ? m === "credit"
                  ? "border-status-success bg-status-success/15 text-status-success"
                  : "border-status-error bg-status-error/15 text-status-error"
                : "border-surface-border-subtle text-text-muted"
            )}
          >
            {m === "credit" ? "+ Credit (add funds)" : "− Debit (deduct)"}
          </button>
        ))}
      </div>
      <Field label="Amount (USD)">
        <TextInput type="number" min="0.01" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} />
      </Field>
      <div className="flex gap-1.5">
        {["5", "10", "25", "50", "100"].map((a) => (
          <button key={a} type="button" onClick={() => setAmount(a)} className="rounded border border-surface-border-subtle px-2 py-0.5 text-xs text-text hover:bg-surface-panel-raised">
            ${a}
          </button>
        ))}
      </div>
      <Field label="Reason (saved to the audit log)" hint="At least 8 characters.">
        <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} className={selectClass} />
      </Field>
      {error && <Notice tone="error">{error}</Notice>}
      <div className="flex justify-end gap-2">
        <SkeuoButton variant="ghost" onClick={() => onClose(false)}>
          Cancel
        </SkeuoButton>
        <SkeuoButton variant="primary" disabled={!valid} loading={busy} onClick={() => void submit()}>
          Confirm {mode}
        </SkeuoButton>
      </div>
    </Modal>
  );
}

/* ------------------------------------------------------------------ impersonate */

export function ImpersonateDialog({
  open,
  workspace,
  onClose,
}: {
  open: boolean;
  workspace: { tenantId: string; name: string } | null;
  onClose: () => void;
}) {
  return (
    <ActionDialog
      open={open}
      title={`Open the console as ${workspace?.name ?? "customer"}`}
      description="Starts a 30-minute support session in the customer console as a workspace admin. The customer sees a support banner and the session is audited."
      action="impersonate"
      count={1}
      confirmLabel="Start support session"
      onClose={() => onClose()}
      onRun={async (reason) => {
        if (!workspace) return;
        const res = await adminAction<{ url?: string }>(`/api/dev/admin/tenants/${workspace.tenantId}/impersonate`, {
          method: "POST",
          body: { note: reason, ttlMinutes: 30 },
        });
        if (res.url) window.open(res.url, "_blank", "noopener,noreferrer");
      }}
    />
  );
}

/* ------------------------------------------------------------------ add number */

type PoolNumber = {
  e164: string;
  numberId: string | null;
  telnyxNumberId: string | null;
  carrierNumberId?: string | null;
  provider?: string | null;
  status: string;
  source: string;
  available: boolean;
  inInventory?: boolean;
};

type CarrierCandidate = { e164: string; provider: string; country: string; monthlyUsd: number; monthlyInr: number };

/**
 * Put a number into a workspace: from the platform pool (existing allocate flow,
 * with its KYC and carrier-ownership checks) or by ordering one from the active
 * carrier. Optionally pin it to an agent in the same step.
 */
export function AddNumberDialog({
  open,
  tenantId: presetTenant,
  onClose,
}: {
  open: boolean;
  tenantId?: string | null;
  onClose: (changed: boolean) => void;
}) {
  const [mode, setMode] = useState<"pool" | "carrier">("pool");
  const [tenantId, setTenantId] = useState(presetTenant ?? "");
  const [agentId, setAgentId] = useState("");
  const [e164, setE164] = useState("");
  const [poolQ, setPoolQ] = useState("");
  const [country, setCountry] = useState("IN");
  const [reason, setReason] = useState("");
  const [candidates, setCandidates] = useState<CarrierCandidate[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [changed, setChanged] = useState(false);

  const pool = useAdminResource<{ numbers: PoolNumber[]; activeProvider?: string }>(open ? "/api/dev/admin/numbers/pool" : null, [open]);
  const active = pool.data?.activeProvider ?? "vobiz";

  useEffect(() => {
    if (open) {
      setMode("pool");
      setTenantId(presetTenant ?? "");
      setAgentId("");
      setE164("");
      setPoolQ("");
      setReason("");
      setCandidates([]);
      setError(null);
      setNotice(null);
      setChanged(false);
    }
  }, [open, presetTenant]);
  useEffect(() => setCountry(active === "vobiz" ? "IN" : "US"), [active]);

  const available = useMemo(
    () =>
      (pool.data?.numbers ?? [])
        .filter((n) => n.available)
        .filter((n) => !poolQ.trim() || `${n.e164} ${n.source}`.toLowerCase().includes(poolQ.trim().toLowerCase())),
    [pool.data, poolQ]
  );
  const picked = (pool.data?.numbers ?? []).find((n) => n.e164 === e164) ?? null;

  async function pinAgent(numberId: string | undefined) {
    if (!agentId || !numberId) return;
    const res = await runBulk("numbers", [numberId], { action: "assign_agent", agentId, reason: "Pinned while assigning the number" });
    if (res.failed.length) throw new Error(`Number assigned, but pinning to the agent failed: ${res.failed[0].error}`);
  }

  async function assignFromPool() {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const res = await adminAction<{ numberId?: string }>("/api/dev/admin/numbers/allocate", {
        method: "POST",
        body: { e164, tenantId, telnyxNumberId: picked?.telnyxNumberId || null },
      });
      setChanged(true);
      await pinAgent(res.numberId);
      setNotice(`${e164} is now assigned${agentId ? " and pinned to the agent" : ""}.`);
      setE164("");
      await pool.reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Assignment failed");
    } finally {
      setBusy(false);
    }
  }

  async function searchCarrier() {
    setBusy(true);
    setError(null);
    try {
      const q = new URLSearchParams({ provider: active, country: country.trim().toUpperCase() });
      const res = (await devFetch(`/api/dev/admin/numbers/carrier-search?${q}`)) as { numbers: CarrierCandidate[] };
      setCandidates(res.numbers ?? []);
      if (!(res.numbers ?? []).length) setNotice("No unassigned carrier inventory in that country right now.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Carrier search failed");
      setCandidates([]);
    } finally {
      setBusy(false);
    }
  }

  async function order(c: CarrierCandidate) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const res = await adminAction<{ provisioning?: boolean }>("/api/dev/admin/numbers/carrier-purchase", {
        method: "POST",
        body: { e164: c.e164, provider: c.provider, country: c.country, tenantId, reason: reason.trim() },
      });
      setChanged(true);
      setCandidates((cur) => cur.filter((x) => x.e164 !== c.e164));
      setNotice(
        res.provisioning
          ? `${c.e164}: the carrier accepted the order and it is pending until the carrier confirms the line. Do not order it again.`
          : `${c.e164} is active and assigned. Pin it to an agent from the number's details.`
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Carrier order failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open={open} title="Add a phone number to a workspace" onClose={() => onClose(changed)} wide>
      <div className="flex gap-1 rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-inset p-1 text-xs" role="tablist">
        {(
          [
            ["pool", "From platform pool"],
            ["carrier", `Order from ${active.toUpperCase()}`],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={mode === id}
            onClick={() => setMode(id)}
            className={cn("flex-1 rounded-skeuo-sm px-3 py-1.5 font-medium", mode === id ? "bg-accent-primary text-white" : "text-text-muted hover:text-text")}
          >
            {label}
          </button>
        ))}
      </div>

      <WorkspacePicker value={tenantId} onChange={(id) => { setTenantId(id); setAgentId(""); }} label="1. Workspace" />

      {mode === "pool" ? (
        <>
          <Field label="2. Number" hint={`Unassigned numbers on ${active.toUpperCase()} and in platform inventory. Assignment runs the same KYC and carrier-ownership checks as before.`}>
            <TextInput value={poolQ} onChange={(e) => setPoolQ(e.target.value)} placeholder="Search numbers…" />
            <select value={e164} onChange={(e) => setE164(e.target.value)} className={cn(selectClass, "mt-1.5 font-mono")} size={6} aria-label="Available number">
              <option value="">{pool.loading ? "Loading pool…" : available.length ? "Choose a number…" : "No available numbers"}</option>
              {available.map((n) => (
                <option key={n.e164} value={n.e164}>
                  {n.e164} · {n.inInventory || n.source.includes("inventory") ? "inventory" : n.source} · {(n.provider || active).toUpperCase()}
                </option>
              ))}
            </select>
          </Field>
          <AgentPicker tenantId={tenantId} value={agentId} onChange={setAgentId} />
          <p className="-mt-1 text-[11px] text-text-subtle">3. Agent is optional — you can pin it later.</p>
        </>
      ) : (
        <>
          <div className="grid grid-cols-[1fr_2fr] gap-2">
            <Field label="Country (ISO)">
              <TextInput value={country} maxLength={2} onChange={(e) => setCountry(e.target.value.toUpperCase())} className="font-mono" />
            </Field>
            <Field label="Order reason (8+ characters)" hint="Recorded in the admin activity log. Carrier charges apply.">
              <TextInput value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} placeholder="e.g. Dedicated sales DID" />
            </Field>
          </div>
          <SkeuoButton variant="secondary" disabled={busy || !country.trim()} onClick={() => void searchCarrier()}>
            Search {active.toUpperCase()} inventory
          </SkeuoButton>
          {candidates.length > 0 && (
            <ul className="max-h-56 divide-y divide-surface-border-subtle overflow-y-auto rounded-skeuo-sm border border-surface-border-subtle">
              {candidates.map((c) => (
                <li key={c.e164} className="flex items-center justify-between gap-2 px-3 py-2 text-sm">
                  <span className="font-mono">{c.e164}</span>
                  <span className="text-xs text-text-muted">
                    ${c.monthlyUsd.toFixed(2)} / ₹{c.monthlyInr.toFixed(2)} per month
                  </span>
                  <SkeuoButton size="sm" variant="primary" disabled={busy || !tenantId || reason.trim().length < 8} onClick={() => void order(c)}>
                    Order
                  </SkeuoButton>
                </li>
              ))}
            </ul>
          )}
        </>
      )}

      {notice && <Notice tone="success">{notice}</Notice>}
      {error && <Notice tone="error">{error}</Notice>}
      <div className="flex justify-end gap-2">
        <SkeuoButton variant="ghost" onClick={() => onClose(changed)}>
          {changed ? "Done" : "Cancel"}
        </SkeuoButton>
        {mode === "pool" && (
          <SkeuoButton variant="primary" disabled={!e164 || !tenantId} loading={busy} onClick={() => void assignFromPool()}>
            Assign number
          </SkeuoButton>
        )}
      </div>
    </Modal>
  );
}

/* ------------------------------------------------------------------ carrier switch */

export function CarrierSwitchDialog({ open, active, onClose }: { open: boolean; active: string; onClose: (changed: boolean) => void }) {
  const next = active === "vobiz" ? "telnyx" : "vobiz";
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (open) setError(null);
  }, [open]);
  return (
    <Modal open={open} title={`Switch the calling network to ${next.toUpperCase()}?`} onClose={() => onClose(false)}>
      <Notice tone="warning">
        This is platform-wide: new calls in every workspace route through {next.toUpperCase()}, and number lists show {next.toUpperCase()}
        lines. Existing numbers stay where they are.
      </Notice>
      {error && <Notice tone="error">{error}</Notice>}
      <div className="flex justify-end gap-2">
        <SkeuoButton variant="ghost" onClick={() => onClose(false)}>
          Cancel
        </SkeuoButton>
        <SkeuoButton
          variant="primary"
          loading={busy}
          onClick={async () => {
            setBusy(true);
            try {
              await adminAction("/api/dev/telephony/provider", { method: "PATCH", body: { provider: next } });
              onClose(true);
            } catch (e) {
              setError(e instanceof Error ? e.message : "Could not switch the calling network");
            } finally {
              setBusy(false);
            }
          }}
        >
          Switch to {next.toUpperCase()}
        </SkeuoButton>
      </div>
    </Modal>
  );
}

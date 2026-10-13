"use client";

import { useEffect, useMemo, useState, type FormEvent } from "react";
import {
  AdminError,
  AdminLoading,
  AdminPageHeader,
} from "@/components/admin/AdminNav";
import { DevCard } from "@/components/dev/DevCard";
import { SkeuoButton } from "@/components/ui/skeuo";
import { adminAction, formatWhen, useAdminResource } from "@/lib/useAdminResource";

type SupportConfig = {
  supportEmail: string;
  businessHours: string;
  slaResponseTime: string;
  autoReplyMessage: string;
  isActive: boolean;
  twitterUrl: string;
  linkedinUrl: string;
  githubUrl: string;
  youtubeUrl: string;
  discordUrl: string;
  smtpHost: string;
  smtpPort: number;
  smtpUsername: string;
  smtpHasPassword: boolean;
  smtpUseTls: boolean;
  senderEmail: string;
  senderName: string;
  notifyCustomerOnTicket: boolean;
  notifyAdminOnTicket: boolean;
  adminAlertEmail: string;
};

type Inquiry = {
  id: string;
  ticketNumber: string;
  fullName: string;
  email: string;
  company?: string | null;
  category: string;
  priority: string;
  subject: string;
  message: string;
  status: string;
  assignedTo?: string | null;
  adminNotes?: string | null;
  resolutionNotes?: string | null;
  customerReplies?: Array<{ id: string; author: string; message: string; sentAt: string; isStaff: boolean }>;
  createdAt: string | null;
};

type ConfigResponse = { config: SupportConfig };
type InquiryResponse = { inquiries: Inquiry[] };

const EMPTY_CONFIG: SupportConfig = {
  supportEmail: "",
  businessHours: "",
  slaResponseTime: "",
  autoReplyMessage: "",
  isActive: true,
  twitterUrl: "",
  linkedinUrl: "",
  githubUrl: "",
  youtubeUrl: "",
  discordUrl: "",
  smtpHost: "",
  smtpPort: 587,
  smtpUsername: "",
  smtpHasPassword: false,
  smtpUseTls: true,
  senderEmail: "",
  senderName: "",
  notifyCustomerOnTicket: true,
  notifyAdminOnTicket: true,
  adminAlertEmail: "",
};

const TABS = [
  { id: "tickets", label: "Support tickets" },
  { id: "channels", label: "Public channels" },
  { id: "mail", label: "Mail delivery" },
] as const;
const PAGE_SIZE = 50;

function Field({
  label,
  value,
  onChange,
  type = "text",
  placeholder,
  autoComplete,
}: {
  label: string;
  value: string | number;
  onChange: (value: string) => void;
  type?: string;
  placeholder?: string;
  autoComplete?: string;
}) {
  return (
    <label className="block space-y-1.5 text-sm">
      <span className="text-text-muted">{label}</span>
      <input
        type={type}
        value={value ?? ""}
        placeholder={placeholder}
        autoComplete={autoComplete}
        onChange={(event) => onChange(event.target.value)}
        className="w-full rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised px-3 py-2 text-sm text-text outline-none focus:border-accent-primary"
      />
    </label>
  );
}

export default function AdminSupportPage() {
  const [tab, setTab] = useState<(typeof TABS)[number]["id"]>("tickets");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("open");
  const [priorityFilter, setPriorityFilter] = useState("all");
  const [categoryFilter, setCategoryFilter] = useState("all");
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<Inquiry | null>(null);
  const [reply, setReply] = useState("");
  const [saveState, setSaveState] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [config, setConfig] = useState<SupportConfig>(EMPTY_CONFIG);
  const [smtpPassword, setSmtpPassword] = useState("");
  const [smtpResult, setSmtpResult] = useState("");

  const configResource = useAdminResource<ConfigResponse>("/api/dev/admin/support/config");
  const inquiriesPath = useMemo(() => {
    const params = new URLSearchParams();
    if (statusFilter !== "all") params.set("status", statusFilter);
    if (priorityFilter !== "all") params.set("priority", priorityFilter);
    if (categoryFilter !== "all") params.set("category", categoryFilter);
    if (search.trim()) params.set("search", search.trim());
    params.set("limit", String(PAGE_SIZE + 1));
    params.set("offset", String(offset));
    const query = params.toString();
    return `/api/dev/admin/support/inquiries${query ? `?${query}` : ""}`;
  }, [search, statusFilter, priorityFilter, categoryFilter, offset]);
  const inquiryResource = useAdminResource<InquiryResponse>(tab === "tickets" ? inquiriesPath : null, [tab]);

  useEffect(() => {
    if (configResource.data?.config) setConfig({ ...EMPTY_CONFIG, ...configResource.data.config });
  }, [configResource.data]);

  const inquiries = inquiryResource.data?.inquiries ?? [];
  const visibleInquiries = inquiries.slice(0, PAGE_SIZE);
  const hasNextPage = inquiries.length > PAGE_SIZE;
  const pageNumber = Math.floor(offset / PAGE_SIZE) + 1;

  function updateConfig<K extends keyof SupportConfig>(key: K, value: SupportConfig[K]) {
    setConfig((current) => ({ ...current, [key]: value }));
  }

  async function saveConfig(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setSaveState("");
    try {
      const payload: Record<string, unknown> = {
        ...config,
        smtpHasPassword: undefined,
      };
      delete payload.smtpHasPassword;
      if (smtpPassword) payload.smtpPassword = smtpPassword;
      await adminAction("/api/dev/admin/support/config", { method: "PUT", body: payload });
      setSmtpPassword("");
      await configResource.reload();
      setSaveState("Saved");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save support settings");
    } finally {
      setBusy(false);
    }
  }

  async function testSmtp() {
    setBusy(true);
    setError(null);
    setSmtpResult("");
    try {
      const result = await adminAction<{ message?: string }>("/api/dev/admin/support/smtp/test", {
        body: {
          smtpHost: config.smtpHost,
          smtpPort: Number(config.smtpPort) || 587,
          smtpUsername: config.smtpUsername,
          smtpPassword: smtpPassword || undefined,
          smtpUseTls: config.smtpUseTls,
        },
      });
      setSmtpResult(result.message || "SMTP connection verified.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "SMTP test failed");
    } finally {
      setBusy(false);
    }
  }

  async function updateInquiry(patch: Partial<Inquiry> & { replyMessage?: string }) {
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      const response = await adminAction<{ inquiry: Partial<Inquiry> }>(
        `/api/dev/admin/support/inquiries/${selected.id}`,
        { method: "PATCH", body: patch }
      );
      setSelected((current) => current ? { ...current, ...response.inquiry } : current);
      setReply("");
      await inquiryResource.reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not update ticket");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6 p-6" data-testid="platform-support-page">
      <AdminPageHeader
        title="Support desk & delivery"
        description="Manage customer inquiries, public contact channels, and the platform mail gateway. Access and changes are checked and audited by the server."
      />

      <AdminError error={error || configResource.error || inquiryResource.error} />
      <div className="flex flex-wrap gap-2" role="tablist" aria-label="Support administration">
        {TABS.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={tab === item.id}
            onClick={() => setTab(item.id)}
            className={`rounded-full border px-4 py-2 text-sm ${tab === item.id ? "border-accent-primary bg-accent-primary text-white" : "border-surface-border-subtle bg-surface-panel text-text-muted hover:text-text"}`}
          >
            {item.label}
          </button>
        ))}
      </div>

      {tab === "tickets" && (
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(320px,0.8fr)]">
          <DevCard title="Customer inquiries" description="Search recent tickets and track their status.">
            <div className="mb-4 flex flex-wrap gap-2">
              <input
                value={search}
                onChange={(event) => { setSearch(event.target.value); setOffset(0); }}
                placeholder="Search ticket, name, email, or subject"
                aria-label="Search support tickets"
                className="min-w-[220px] flex-1 rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised px-3 py-2 text-sm"
              />
              <select
                value={statusFilter}
                onChange={(event) => { setStatusFilter(event.target.value); setOffset(0); }}
                aria-label="Filter support tickets"
                className="rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised px-3 py-2 text-sm"
              >
                <option value="open">Open</option>
                <option value="all">All tickets</option>
                <option value="new">New</option>
                <option value="triaged">Triaged</option>
                <option value="in_progress">In progress</option>
                <option value="waiting_on_customer">Waiting on customer</option>
                <option value="resolved">Resolved</option>
                <option value="closed">Closed</option>
              </select>
              <select
                value={priorityFilter}
                onChange={(event) => { setPriorityFilter(event.target.value); setOffset(0); }}
                aria-label="Filter by priority"
                className="rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised px-3 py-2 text-sm"
              >
                <option value="all">All priorities</option>
                <option value="urgent">Urgent</option>
                <option value="high">High</option>
                <option value="normal">Normal</option>
                <option value="low">Low</option>
              </select>
              <select
                value={categoryFilter}
                onChange={(event) => { setCategoryFilter(event.target.value); setOffset(0); }}
                aria-label="Filter by category"
                className="rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised px-3 py-2 text-sm"
              >
                <option value="all">All categories</option>
                <option value="technical_support">Technical support</option>
                <option value="enterprise_fleet">Enterprise fleet</option>
                <option value="telephony_trunk">Voice network</option>
                <option value="billing_pricing">Billing</option>
                <option value="general_inquiry">General</option>
              </select>
            </div>
            <AdminLoading loading={inquiryResource.loading} />
            <div className="max-h-[60vh] overflow-auto">
              <table className="w-full min-w-[620px] text-left text-sm">
                <thead className="sticky top-0 bg-surface-panel text-xs uppercase text-text-subtle">
                  <tr><th className="p-2">Ticket</th><th className="p-2">Customer</th><th className="p-2">Subject</th><th className="p-2">Status</th></tr>
                </thead>
                <tbody>
                  {visibleInquiries.map((inquiry) => (
                    <tr key={inquiry.id} className={`border-t border-surface-border-subtle hover:bg-surface-panel-raised ${selected?.id === inquiry.id ? "bg-surface-panel-raised" : ""}`}>
                      <td className="p-2 font-mono text-xs"><button type="button" onClick={() => { setSelected(inquiry); setReply(""); }} aria-label={`Open ticket ${inquiry.ticketNumber}`} className="underline-offset-2 hover:underline">{inquiry.ticketNumber}</button></td>
                      <td className="p-2"><span className="block">{inquiry.fullName}</span><span className="text-xs text-text-muted">{inquiry.email}</span></td>
                      <td className="max-w-[240px] truncate p-2">{inquiry.subject}</td>
                      <td className="p-2 capitalize">{inquiry.status.replaceAll("_", " ")}</td>
                    </tr>
                  ))}
                  {!inquiryResource.loading && visibleInquiries.length === 0 && (
                    <tr><td className="p-5 text-center text-text-muted" colSpan={4}>No matching inquiries.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
            <div className="mt-3 flex items-center justify-between gap-3 text-sm">
              <span className="text-text-muted" aria-live="polite">Page {pageNumber} of support tickets</span>
              <div className="flex gap-2">
                <SkeuoButton
                  variant="secondary"
                  disabled={inquiryResource.loading || offset === 0}
                  onClick={() => setOffset((current) => Math.max(0, current - PAGE_SIZE))}
                >
                  Previous page
                </SkeuoButton>
                <SkeuoButton
                  variant="secondary"
                  disabled={inquiryResource.loading || !hasNextPage}
                  onClick={() => setOffset((current) => current + PAGE_SIZE)}
                >
                  Next page
                </SkeuoButton>
              </div>
            </div>
          </DevCard>

          <DevCard title={selected ? `${selected.ticketNumber} · ${selected.subject}` : "Ticket details"}>
            {selected ? (
              <div className="space-y-4 text-sm">
                <div className="text-text-muted">{selected.fullName} · {selected.email}{selected.company ? ` · ${selected.company}` : ""}<br />Received {formatWhen(selected.createdAt)}</div>
                <p className="whitespace-pre-wrap rounded-skeuo-sm bg-surface-panel-raised p-3">{selected.message}</p>
                <div className="grid grid-cols-2 gap-3 rounded-skeuo-sm bg-surface-panel-raised p-3">
                  <p><span className="block text-xs text-text-muted">Category</span><span className="capitalize">{selected.category.replaceAll("_", " ")}</span></p>
                  <p><span className="block text-xs text-text-muted">Priority</span><span className="capitalize">{selected.priority}</span></p>
                </div>
                {(selected.customerReplies ?? []).length > 0 && (
                  <div className="max-h-40 space-y-2 overflow-auto">
                    {selected.customerReplies?.map((entry) => (
                      <p key={entry.id} className="rounded-skeuo-sm border border-surface-border-subtle p-2">
                        <span className="font-medium">{entry.author}{entry.isStaff ? " · Staff" : ""}</span>
                        <span className="ml-2 text-xs text-text-muted">{formatWhen(entry.sentAt)}</span>
                        <br />{entry.message}
                      </p>
                    ))}
                  </div>
                )}
                <label className="block space-y-1.5 text-sm"><span className="text-text-muted">Status</span>
                  <select value={selected.status} onChange={(event) => setSelected({ ...selected, status: event.target.value })} className="w-full rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised px-3 py-2">
                    <option value="new">New</option><option value="triaged">Triaged</option><option value="in_progress">In progress</option><option value="waiting_on_customer">Waiting on customer</option><option value="resolved">Resolved</option><option value="closed">Closed</option>
                  </select>
                </label>
                <Field label="Assigned to" value={selected.assignedTo || ""} onChange={(value) => setSelected({ ...selected, assignedTo: value })} />
                <label className="block space-y-1.5 text-sm"><span className="text-text-muted">Internal notes</span><textarea value={selected.adminNotes || ""} onChange={(event) => setSelected({ ...selected, adminNotes: event.target.value })} rows={3} className="w-full rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised px-3 py-2" /></label>
                <label className="block space-y-1.5 text-sm"><span className="text-text-muted">Reply to customer</span><textarea value={reply} onChange={(event) => setReply(event.target.value)} rows={3} className="w-full rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised px-3 py-2" /></label>
                <div className="flex flex-wrap items-center gap-2"><SkeuoButton disabled={busy} onClick={() => void updateInquiry({ status: selected.status, assignedTo: selected.assignedTo || "", adminNotes: selected.adminNotes || "" })}>Save ticket</SkeuoButton><SkeuoButton disabled={busy || !reply.trim()} onClick={() => void updateInquiry({ status: selected.status === "new" ? "in_progress" : selected.status, assignedTo: selected.assignedTo || "", adminNotes: selected.adminNotes || "", replyMessage: reply.trim() })}>Send reply</SkeuoButton></div>
              </div>
            ) : <p className="text-sm text-text-muted">Select a ticket to view its message and respond.</p>}
          </DevCard>
        </div>
      )}

      {tab === "channels" && (
        <DevCard title="Public channels" description="These details appear on the public support page and site footer.">
          {configResource.loading ? <AdminLoading loading /> : (
            <form onSubmit={saveConfig} className="space-y-5" data-testid="support-channels-form">
              <div className="grid gap-4 md:grid-cols-2">
                <Field label="Support email" type="email" value={config.supportEmail} onChange={(value) => updateConfig("supportEmail", value)} />
                <Field label="Business hours" value={config.businessHours} onChange={(value) => updateConfig("businessHours", value)} />
                <Field label="Response SLA" value={config.slaResponseTime} onChange={(value) => updateConfig("slaResponseTime", value)} />
                <Field label="X / Twitter URL" type="url" value={config.twitterUrl} onChange={(value) => updateConfig("twitterUrl", value)} />
                <Field label="LinkedIn URL" type="url" value={config.linkedinUrl} onChange={(value) => updateConfig("linkedinUrl", value)} />
                <Field label="GitHub URL" type="url" value={config.githubUrl} onChange={(value) => updateConfig("githubUrl", value)} />
                <Field label="YouTube URL" type="url" value={config.youtubeUrl} onChange={(value) => updateConfig("youtubeUrl", value)} />
                <Field label="Discord URL" type="url" value={config.discordUrl} onChange={(value) => updateConfig("discordUrl", value)} />
              </div>
              <label className="block space-y-1.5 text-sm"><span className="text-text-muted">Automatic ticket acknowledgment</span><textarea value={config.autoReplyMessage} onChange={(event) => updateConfig("autoReplyMessage", event.target.value)} rows={3} className="w-full rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised px-3 py-2" /></label>
              <div className="flex flex-wrap gap-5 text-sm"><label className="flex items-center gap-2"><input type="checkbox" checked={config.isActive} onChange={(event) => updateConfig("isActive", event.target.checked)} />Support is active</label><label className="flex items-center gap-2"><input type="checkbox" checked={config.notifyCustomerOnTicket} onChange={(event) => updateConfig("notifyCustomerOnTicket", event.target.checked)} />Notify customer</label><label className="flex items-center gap-2"><input type="checkbox" checked={config.notifyAdminOnTicket} onChange={(event) => updateConfig("notifyAdminOnTicket", event.target.checked)} />Notify admin</label></div>
              <Field label="Admin notification email" type="email" value={config.adminAlertEmail} onChange={(value) => updateConfig("adminAlertEmail", value)} />
              <div className="flex items-center gap-3"><SkeuoButton disabled={busy}>{busy ? "Saving…" : "Save public channels"}</SkeuoButton><span role="status" className="text-sm text-status-success">{saveState}</span></div>
            </form>
          )}
        </DevCard>
      )}

      {tab === "mail" && (
        <DevCard title="Mail gateway" description="SMTP credentials are write-only here. The server reports whether a password is stored; it never sends the password back to this page.">
          {configResource.loading ? <AdminLoading loading /> : (
            <form onSubmit={saveConfig} className="space-y-5" data-testid="support-mail-form">
              <div className="grid gap-4 md:grid-cols-2">
                <Field label="SMTP host" value={config.smtpHost} onChange={(value) => updateConfig("smtpHost", value)} autoComplete="off" />
                <Field label="SMTP port" type="number" value={config.smtpPort} onChange={(value) => updateConfig("smtpPort", Number(value))} />
                <Field label="SMTP username" value={config.smtpUsername} onChange={(value) => updateConfig("smtpUsername", value)} autoComplete="off" />
                <Field label="SMTP password" type="password" value={smtpPassword} onChange={setSmtpPassword} placeholder={config.smtpHasPassword ? "Stored password is set; enter only to replace" : "Enter password"} autoComplete="new-password" />
                <Field label="Sender email" type="email" value={config.senderEmail} onChange={(value) => updateConfig("senderEmail", value)} />
                <Field label="Sender display name" value={config.senderName} onChange={(value) => updateConfig("senderName", value)} />
              </div>
              <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={config.smtpUseTls} onChange={(event) => updateConfig("smtpUseTls", event.target.checked)} />Use STARTTLS</label>
              <p className="text-xs text-text-muted">Password stored: {config.smtpHasPassword ? "yes" : "no"}</p>
              {smtpResult && <p role="status" className="text-sm text-status-success">{smtpResult}</p>}
              <div className="flex flex-wrap gap-2"><SkeuoButton disabled={busy}>{busy ? "Saving…" : "Save mail settings"}</SkeuoButton><SkeuoButton type="button" variant="secondary" disabled={busy} onClick={() => void testSmtp()}>Test connection</SkeuoButton><span role="status" className="self-center text-sm text-status-success">{saveState}</span></div>
            </form>
          )}
        </DevCard>
      )}
    </div>
  );
}

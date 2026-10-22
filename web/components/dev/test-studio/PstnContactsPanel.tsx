"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/Button";
import { DevCard } from "@/components/dev/DevCard";
import { portalFetch } from "@/lib/auth-client";
import { ensureArray } from "@/lib/ensure-array";
import type { DevTelephonyContact } from "@/lib/dev-telephony-types";

export function PstnContactsPanel({
  seedPhone = "",
  onPickPhone,
  onCallPhone,
  compact = false,
}: {
  seedPhone?: string;
  onPickPhone: (phone: string, name?: string) => void;
  onCallPhone?: (phone: string, name?: string) => void;
  compact?: boolean;
}) {
  const [contacts, setContacts] = useState<DevTelephonyContact[]>([]);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [notes, setNotes] = useState("");
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const load = useCallback(async () => {
    const r = await portalFetch("dev", "/api/dev/telephony/contacts");
    if (!r.ok) return;
    const j = await r.json();
    setContacts(ensureArray<DevTelephonyContact>(j.contacts));
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (seedPhone.trim() && !phone.trim()) {
      setPhone(seedPhone.trim());
    }
  }, [seedPhone, phone]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return contacts;
    return contacts.filter((c) => {
      const hay = `${c.name || ""} ${c.phone || ""} ${c.notes || ""}`.toLowerCase();
      return hay.includes(q);
    });
  }, [contacts, query]);

  async function saveContact(overridePhone?: string) {
    const nextPhone = (overridePhone ?? phone).trim() || seedPhone.trim();
    if (!nextPhone) {
      setMessage("Phone number required");
      return;
    }
    setBusy(true);
    const r = await portalFetch("dev", "/api/dev/telephony/contacts", {
      method: "POST",
      body: JSON.stringify({ name: name.trim() || nextPhone, phone: nextPhone, notes }),
    });
    setBusy(false);
    if (!r.ok) {
      setMessage("Could not save contact");
      return;
    }
    setName("");
    setPhone("");
    setNotes("");
    setMessage("Contact saved");
    await load();
  }

  async function removeContact(contactId: string) {
    setBusy(true);
    await portalFetch("dev", `/api/dev/telephony/contacts/${contactId}`, { method: "DELETE" });
    setBusy(false);
    await load();
  }

  return (
    <DevCard
      title="Saved contacts"
      description="Persist test numbers, search the list, then dial without retyping"
    >
      <div className="grid gap-3 sm:grid-cols-3">
        <label className="block text-sm">
          <span className="text-text-muted">Name</span>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="mt-2 w-full rounded-xl border border-surface-border bg-surface-raised px-3 py-2 text-sm"
            placeholder="Subhash"
          />
        </label>
        <label className="block text-sm">
          <span className="text-text-muted">Phone (E.164)</span>
          <input
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            className="mt-2 w-full rounded-xl border border-surface-border bg-surface-raised px-3 py-2 text-sm font-mono"
            placeholder={seedPhone || "+919876543210"}
          />
        </label>
        <label className="block text-sm">
          <span className="text-text-muted">Notes</span>
          <input
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            className="mt-2 w-full rounded-xl border border-surface-border bg-surface-raised px-3 py-2 text-sm"
            placeholder="Callback test"
          />
        </label>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button type="button" onClick={() => void saveContact()} disabled={busy}>
          Save contact
        </Button>
        {seedPhone.trim() ? (
          <Button
            type="button"
            variant="secondary"
            disabled={busy}
            onClick={() => void saveContact(seedPhone.trim())}
          >
            Save current To
          </Button>
        ) : null}
        {message ? <span className="self-center text-xs text-text-muted">{message}</span> : null}
      </div>

      {contacts.length > 0 ? (
        <label className="mt-4 block text-sm">
          <span className="text-text-muted">Search contacts</span>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="mt-2 w-full rounded-xl border border-surface-border bg-surface-raised px-3 py-2 text-sm"
            placeholder="Name, number, or note"
            data-testid="pstn-contact-search"
          />
        </label>
      ) : null}

      <ul className={`mt-4 space-y-2 ${compact ? "max-h-64 overflow-y-auto pr-1" : ""}`}>
        {contacts.length === 0 ? (
          <li className="text-sm text-text-muted">No saved contacts yet. Save a number above, then Call to dial it.</li>
        ) : filtered.length === 0 ? (
          <li className="text-sm text-text-muted">No contacts match “{query}”.</li>
        ) : (
          filtered.map((c) => (
            <li
              key={c.contact_id}
              className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-surface-border-subtle px-3 py-2"
            >
              <div>
                <p className="text-sm font-medium text-text">{c.name || c.phone}</p>
                <p className="font-mono text-xs text-text-muted">{c.phone}</p>
                {c.notes ? <p className="text-[11px] text-text-subtle">{c.notes}</p> : null}
              </div>
              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  onClick={() => {
                    if (onCallPhone) onCallPhone(c.phone, c.name);
                    else onPickPhone(c.phone, c.name);
                  }}
                >
                  Call
                </Button>
                <Button type="button" variant="secondary" onClick={() => onPickPhone(c.phone, c.name)}>
                  Fill To
                </Button>
                <Button type="button" variant="secondary" onClick={() => void removeContact(c.contact_id)} disabled={busy}>
                  Delete
                </Button>
              </div>
            </li>
          ))
        )}
      </ul>
    </DevCard>
  );
}

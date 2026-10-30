"use client";

import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { DevCard } from "@/components/dev/DevCard";
import { portalFetch } from "@/lib/auth-client";
import type { TelephonyStatus } from "@/components/dev/voice-stack/profileModel";

/** Carrier trunk selection and handshake checks (platform infrastructure). */
export function TelephonyTrunkPanel() {
  const [telephony, setTelephony] = useState<TelephonyStatus | null>(null);
  const [telephonyBusy, setTelephonyBusy] = useState(false);
  const [telephonyMsg, setTelephonyMsg] = useState("");
  const [telephonyError, setTelephonyError] = useState("");

  const loadTelephony = useCallback(async () => {
    try {
      const res = await portalFetch("dev", "/api/dev/telephony/status");
      if (!res.ok) return;
      setTelephony(await res.json());
    } catch {
      // Non-blocking telephony fetch
    }
  }, []);

  useEffect(() => {
    void loadTelephony();
  }, [loadTelephony]);

  const switchTelephony = async (providerId: string) => {
    if (telephonyBusy || telephony?.active_provider === providerId) return;
    setTelephonyBusy(true);
    setTelephonyMsg("");
    setTelephonyError("");
    try {
      const r = await portalFetch("dev", "/api/dev/telephony/provider", {
        method: "PATCH",
        body: JSON.stringify({ provider: providerId }),
      });
      if (!r.ok) {
        setTelephonyError(`Failed to switch provider (${r.status})`);
        return;
      }
      await loadTelephony();
      setTelephonyMsg(`Active telephony trunk switched to ${providerId.toUpperCase()}. Direct routing updated.`);
    } catch (e) {
      setTelephonyError(e instanceof Error ? e.message : "Failed to switch provider");
    } finally {
      setTelephonyBusy(false);
    }
  };

  const testHandshake = async () => {
    setTelephonyBusy(true);
    setTelephonyMsg("Testing carrier handshake…");
    setTelephonyError("");
    try {
      const r = await portalFetch("dev", "/api/dev/telephony/handshake", { method: "POST" });
      const j = await r.json();
      if (j.ok) {
        setTelephonyMsg(`Handshake OK (${telephony?.active_provider?.toUpperCase()}): connected to the carrier trunk.`);
      } else {
        setTelephonyError(`Handshake warning: ${j.error || JSON.stringify(j)}`);
      }
    } catch (e) {
      setTelephonyError(e instanceof Error ? e.message : "Handshake failed");
    } finally {
      setTelephonyBusy(false);
    }
  };

  return (
    <DevCard
      title="Telephony Infrastructure & PSTN Calling Trunk"
      description="Select and manage wholesale carrier trunks for inbound and outbound calls, DID provisioning, and bidirectional audio streaming."
    >
      {telephonyError && (
        <div className="mb-4 rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-200">
          {telephonyError}
        </div>
      )}
      {telephonyMsg && (
        <div className="mb-4 rounded-xl border border-accent/30 bg-accent/10 p-3 text-xs font-mono text-accent">
          {telephonyMsg}
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        {/* Telnyx Trunk Card */}
        {(() => {
          const telnyxSt = telephony?.providers?.find((p) => p.id === "telnyx");
          const isTelnyxActive = (telephony?.active_provider || "vobiz") === "telnyx";
          const isReady = Boolean(telnyxSt?.ready);
          return (
            <div
              className={`rounded-xl border p-4 text-left transition-all ${
                isTelnyxActive
                  ? "border-accent bg-accent/5 ring-1 ring-accent/30"
                  : "border-border bg-surface-card hover:border-accent/40"
              }`}
            >
              <div className="flex items-center justify-between">
                <p className="text-sm font-semibold text-text">Telnyx PSTN Trunk</p>
                <span
                  className={`text-[10px] font-mono px-2 py-0.5 rounded font-semibold ${
                    isReady ? "bg-emerald-500/10 text-emerald-400" : "bg-amber-500/10 text-amber-400"
                  }`}
                >
                  {isReady ? "Ready" : "Setup incomplete"}
                </span>
              </div>
              <p className="text-xs text-text-muted mt-1">
                Call Control v2 · 8 kHz µ-law · WebSocket media streaming
              </p>
              <div className="mt-3 space-y-1 font-mono text-[11px] text-text-subtle">
                <div>Caller ID: {telnyxSt?.phone_number || "Auto"}</div>
                <div>Connection ID: {telnyxSt?.connection_id || "Configured"}</div>
                <div>Webhook: /api/telnyx/webhook</div>
                <div>Stream: /ws/telnyx-stream</div>
              </div>
              <div className="mt-4">
                <Button
                  type="button"
                  variant={isTelnyxActive ? "primary" : "secondary"}
                  disabled={isTelnyxActive || telephonyBusy}
                  onClick={() => void switchTelephony("telnyx")}
                  className="w-full text-xs"
                >
                  {isTelnyxActive ? "Active Trunk" : "Switch to Telnyx"}
                </Button>
              </div>
            </div>
          );
        })()}

        {/* Vobiz Trunk Card */}
        {(() => {
          const vobizSt = telephony?.providers?.find((p) => p.id === "vobiz");
          const isVobizActive = (telephony?.active_provider || "vobiz") === "vobiz";
          const isReady = Boolean(vobizSt?.ready);
          return (
            <div
              className={`rounded-xl border p-4 text-left transition-all ${
                isVobizActive
                  ? "border-accent bg-accent/5 ring-1 ring-accent/30"
                  : "border-border bg-surface-card hover:border-accent/40"
              }`}
            >
              <div className="flex items-center justify-between">
                <p className="text-sm font-semibold text-text">Vobiz Telephony (Primary Trunk)</p>
                <span
                  className={`text-[10px] font-mono px-2 py-0.5 rounded font-semibold ${
                    isReady ? "bg-emerald-500/10 text-emerald-400" : "bg-amber-500/10 text-amber-400"
                  }`}
                >
                  {isReady ? "Ready" : "Setup incomplete"}
                </span>
              </div>
              <p className="text-xs text-text-muted mt-1">
                Voice XML + Bidirectional L16/µ-law WebSocket stream
              </p>
              <div className="mt-3 space-y-1 font-mono text-[11px] text-text-subtle">
                <div>Auth ID: {vobizSt?.account_info?.auth_id || "MA_LX2CKOU1"}</div>
                <div>App ID: {vobizSt?.account_info?.app_id || "551682"}</div>
                <div>Answer URL: /api/vobiz/answer</div>
                <div>Stream: /ws/vobiz-stream</div>
              </div>
              <div className="mt-4">
                <Button
                  type="button"
                  variant={isVobizActive ? "primary" : "secondary"}
                  disabled={isVobizActive || telephonyBusy}
                  onClick={() => void switchTelephony("vobiz")}
                  className="w-full text-xs"
                >
                  {isVobizActive ? "Active Trunk" : "Switch to Vobiz"}
                </Button>
              </div>
            </div>
          );
        })()}
      </div>

      <div className="mt-6 pt-4 border-t border-border flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Button
            type="button"
            variant="secondary"
            disabled={telephonyBusy}
            onClick={() => void testHandshake()}
            className="text-xs"
          >
            Test Live Handshake
          </Button>
          <Button
            type="button"
            variant="secondary"
            disabled={telephonyBusy}
            onClick={() => void loadTelephony()}
            className="text-xs"
          >
            Refresh Trunk Status
          </Button>
        </div>
        <span className="font-mono text-xs text-text-subtle">
          Trunk controls are isolated to platform infrastructure.
        </span>
      </div>
    </DevCard>
  );
}

"use client";

import { useEffect, useMemo, useState } from "react";
import { DevCard } from "@/components/dev/DevCard";
import { SkeuoButton, SkeuoInput } from "@/components/ui/skeuo";
import { adminAction, formatWhen, useAdminResource } from "@/lib/useAdminResource";

type Tone = "neutral" | "accent" | "success" | "warning";

type TierTag = { label: string; tone: Tone };

type FeaturedStyle = "graphite" | "ivory" | "forest" | "midnight";

type MerchandisedTier = {
  id: string;
  label: string;
  active: boolean;
  tags: TierTag[];
  featured: boolean;
  visible: boolean;
  pstnInrPerMin: number | null;
  webInrPerMin: number | null;
};

type MerchandisingPayload = {
  version: number;
  updatedAt: string | null;
  updatedBy: string | null;
  featuredStyle: FeaturedStyle;
  featuredStyles: string[];
  tiers: MerchandisedTier[];
};

type StylePalette = {
  background: string;
  border: string;
  ring: string;
  text: string;
  muted: string;
  strong: string;
  accent: string;
  buttonBg: string;
  buttonText: string;
  buttonHover: string;
};

type FeaturedStyleOption = {
  id: FeaturedStyle;
  label: string;
  description: string;
  palette: StylePalette;
};

const TONES: { value: Tone; label: string }[] = [
  { value: "neutral", label: "Neutral" },
  { value: "accent", label: "Accent" },
  { value: "success", label: "Success" },
  { value: "warning", label: "Warning" },
];

const TONE_CHIP: Record<Tone, string> = {
  neutral: "border-surface-border-subtle bg-surface-panel text-text-muted",
  accent: "border-indigo-200 bg-indigo-50 text-indigo-700",
  success: "border-emerald-200 bg-emerald-50 text-emerald-700",
  warning: "border-amber-200 bg-amber-50 text-amber-800",
};

const MAX_TAGS = 3;
const MAX_TAG_LENGTH = 32;

// Palette values mirror .landing-price-card.is-featured presets in voxly-ai/src/styles/landing.css.
const FEATURED_STYLE_OPTIONS: FeaturedStyleOption[] = [
  {
    id: "graphite",
    label: "Graphite",
    description: "Charcoal card, champagne accents, hairline tags.",
    palette: {
      background: "linear-gradient(168deg, #2d2f35 0%, #22242a 52%, #191a1f 100%)",
      border: "rgba(255, 255, 255, .16)",
      ring: "rgba(255, 255, 255, .2)",
      text: "#ffffff",
      muted: "#b8b3aa",
      strong: "#ffffff",
      accent: "#e7d0a1",
      buttonBg: "#e7d0a1",
      buttonText: "#1f1b14",
      buttonHover: "#f1e0bb",
    },
  },
  {
    id: "ivory",
    label: "Ivory",
    description: "Warm light card with a gold hairline.",
    palette: {
      background: "linear-gradient(160deg, #fdfaf2 0%, #f5ecdb 100%)",
      border: "rgba(158, 124, 55, .42)",
      ring: "rgba(158, 124, 55, .26)",
      text: "#2c2216",
      muted: "#7c6b52",
      strong: "#2c2216",
      accent: "#8a6621",
      buttonBg: "#2c2216",
      buttonText: "#fdf7ea",
      buttonHover: "#46372a",
    },
  },
  {
    id: "forest",
    label: "Forest",
    description: "Deep green card with champagne accents.",
    palette: {
      background: "linear-gradient(165deg, #152e23 0%, #0f231a 58%, #0b1b14 100%)",
      border: "rgba(190, 209, 174, .28)",
      ring: "rgba(206, 224, 190, .24)",
      text: "#f6f3e9",
      muted: "#b6c1ad",
      strong: "#ffffff",
      accent: "#dfcb9a",
      buttonBg: "#dfcb9a",
      buttonText: "#152017",
      buttonHover: "#ecdcb5",
    },
  },
  {
    id: "midnight",
    label: "Midnight",
    description: "Deep violet gradient with a soft glow.",
    palette: {
      background: "radial-gradient(120% 100% at 15% 0%, #322a52 0%, #221c36 55%, #1b1628 100%)",
      border: "rgba(165, 137, 255, .45)",
      ring: "rgba(196, 177, 255, .35)",
      text: "#ffffff",
      muted: "#c9bedc",
      strong: "#ffffff",
      accent: "#c9b8ff",
      buttonBg: "#ffffff",
      buttonText: "#1b132d",
      buttonHover: "#ece5fb",
    },
  },
];

function toDrafts(payload: MerchandisingPayload | null): MerchandisedTier[] {
  if (!payload) return [];
  return payload.tiers.map((tier) => ({
    ...tier,
    active: tier.active === true,
    tags: tier.tags.map((tag) => ({ label: tag.label, tone: tag.tone })),
    pstnInrPerMin: typeof tier.pstnInrPerMin === "number" ? tier.pstnInrPerMin : null,
    webInrPerMin: typeof tier.webInrPerMin === "number" ? tier.webInrPerMin : null,
  }));
}

function inr(value: number | null): string | null {
  return typeof value === "number" && Number.isFinite(value) ? `₹${value.toFixed(2)}` : null;
}

function FeaturedCardPreview({
  style,
  label,
  tags,
  pstnInrPerMin,
  webInrPerMin,
  note,
}: {
  style: FeaturedStyle;
  label: string;
  tags: TierTag[];
  pstnInrPerMin: number | null;
  webInrPerMin: number | null;
  note: string | null;
}) {
  const option =
    FEATURED_STYLE_OPTIONS.find((item) => item.id === style) ?? FEATURED_STYLE_OPTIONS[0];
  const palette = option.palette;
  const rate = inr(pstnInrPerMin);
  const webRate = inr(webInrPerMin);

  return (
    <div aria-label="Featured card preview" className="min-w-0">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-text-subtle">
          Live preview
        </p>
        {note ? <p className="text-[11px] text-text-subtle">{note}</p> : null}
      </div>
      <div
        className="mt-2 rounded-2xl border p-5"
        style={{
          background: palette.background,
          borderColor: palette.border,
          boxShadow: `inset 0 0 0 1px ${palette.ring}`,
          color: palette.text,
        }}
      >
        <div className="flex flex-wrap items-start justify-between gap-2">
          <span
            className="text-[11px] font-semibold uppercase tracking-[0.12em]"
            style={{ color: palette.text }}
          >
            {label}
          </span>
          {tags.length > 0 ? (
            <ul className="flex flex-wrap items-center gap-x-3 gap-y-1">
              {tags.map((tag, index) => (
                <li
                  key={`${tag.label}-${index}`}
                  className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.09em]"
                  style={{ color: palette.accent }}
                >
                  <span
                    aria-hidden="true"
                    className="inline-block h-px w-4"
                    style={{ backgroundColor: palette.accent, opacity: 0.75 }}
                  />
                  {tag.label}
                </li>
              ))}
            </ul>
          ) : null}
        </div>

        <div className="mt-4 flex flex-wrap items-baseline gap-1.5">
          <span className="text-3xl font-semibold tracking-tight" style={{ color: palette.text }}>
            {rate ?? "Rate in workspace"}
          </span>
          <span className="text-xs" style={{ color: palette.muted }}>
            /phone min
          </span>
        </div>

        <div
          className="mt-3 grid gap-1 border-t pt-3 text-xs"
          style={{ borderColor: palette.ring, color: palette.muted }}
        >
          <span>
            Browser agent{" "}
            <strong className="font-semibold" style={{ color: palette.strong }}>
              {webRate ?? "in workspace"}
            </strong>
            {webRate ? "/min" : null}
          </span>
          <span>Phone number rental billed monthly</span>
        </div>

        <div
          className="mt-4 rounded-full px-4 py-2 text-center text-xs font-semibold"
          style={{ background: palette.buttonBg, color: palette.buttonText }}
        >
          Choose {label}
        </div>
      </div>
    </div>
  );
}

export function PricingMerchandisingEditor() {
  const resource = useAdminResource<MerchandisingPayload>(
    "/api/dev/admin/pricing-merchandising"
  );
  const [drafts, setDrafts] = useState<MerchandisedTier[]>([]);
  const [featuredStyle, setFeaturedStyle] = useState<FeaturedStyle>("graphite");
  const [tagInputs, setTagInputs] = useState<Record<string, { label: string; tone: Tone }>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<string | null>(null);

  useEffect(() => {
    if (resource.data) {
      setDrafts(toDrafts(resource.data));
      setFeaturedStyle(resource.data.featuredStyle ?? "graphite");
      setTagInputs({});
      setError(null);
    }
  }, [resource.data]);

  const serverDrafts = useMemo(() => toDrafts(resource.data), [resource.data]);
  const serverStyle = resource.data?.featuredStyle ?? "graphite";
  const dirty = useMemo(
    () => serverStyle !== featuredStyle || JSON.stringify(serverDrafts) !== JSON.stringify(drafts),
    [serverStyle, featuredStyle, serverDrafts, drafts]
  );

  function updateTier(id: string, patch: Partial<MerchandisedTier>) {
    setDrafts((current) =>
      current.map((tier) => {
        if (tier.id !== id) return tier;
        const next = { ...tier, ...patch };
        // The server rejects a hidden featured tier; keep the form honest.
        if (!next.visible && next.featured) next.featured = false;
        if (next.featured && !next.visible) next.visible = true;
        return next;
      })
    );
    setSavedAt(null);
  }

  function setFeatured(id: string) {
    setDrafts((current) =>
      current.map((tier) => ({
        ...tier,
        featured: tier.id === id,
        visible: tier.id === id ? true : tier.visible,
      }))
    );
    setSavedAt(null);
  }

  function inputFor(id: string) {
    return tagInputs[id] ?? { label: "", tone: "neutral" as Tone };
  }

  function updateTagInput(id: string, patch: Partial<{ label: string; tone: Tone }>) {
    setTagInputs((current) => ({ ...current, [id]: { ...inputFor(id), ...patch } }));
  }

  function addTag(id: string) {
    const tier = drafts.find((item) => item.id === id);
    const input = inputFor(id);
    const label = input.label.trim().replace(/\s+/g, " ");
    if (!tier) return;
    if (!label) {
      setError("Enter a tag label before adding it.");
      return;
    }
    if (label.length > MAX_TAG_LENGTH) {
      setError(`Tag labels are limited to ${MAX_TAG_LENGTH} characters.`);
      return;
    }
    if (tier.tags.length >= MAX_TAGS) {
      setError(`Each tier shows at most ${MAX_TAGS} tags.`);
      return;
    }
    if (tier.tags.some((tag) => tag.label.toLowerCase() === label.toLowerCase())) {
      setError(`"${label}" is already on the ${tier.label} tier.`);
      return;
    }
    setError(null);
    updateTier(id, { tags: [...tier.tags, { label, tone: input.tone }] });
    setTagInputs((current) => ({ ...current, [id]: { label: "", tone: input.tone } }));
  }

  function removeTag(id: string, index: number) {
    const tier = drafts.find((item) => item.id === id);
    if (!tier) return;
    updateTier(id, { tags: tier.tags.filter((_, position) => position !== index) });
  }

  function setTagTone(id: string, index: number, tone: Tone) {
    const tier = drafts.find((item) => item.id === id);
    if (!tier) return;
    updateTier(id, {
      tags: tier.tags.map((tag, position) =>
        position === index ? { ...tag, tone } : tag
      ),
    });
  }

  function save() {
    if (!resource.data) return;
    setBusy(true);
    setError(null);
    setSavedAt(null);
    const tiers: Record<string, { tags: TierTag[]; featured: boolean; visible: boolean }> = {};
    for (const tier of drafts) {
      tiers[tier.id] = { tags: tier.tags, featured: tier.featured, visible: tier.visible };
    }
    void adminAction<MerchandisingPayload>("/api/dev/admin/pricing-merchandising", {
      method: "PUT",
      body: { expectedVersion: resource.data.version, featuredStyle, tiers },
    })
      .then(async (result) => {
        setSavedAt(new Date().toISOString());
        setDrafts(toDrafts(result));
        setFeaturedStyle(result.featuredStyle ?? "graphite");
        await resource.reload();
      })
      .catch(async (e: unknown) => {
        setError(e instanceof Error ? e.message : "Could not save pricing tags.");
        if (e instanceof Error && /another session/i.test(e.message)) {
          await resource.reload();
        }
      })
      .finally(() => setBusy(false));
  }

  const featuredTier = drafts.find((tier) => tier.featured) ?? null;
  const previewTags = featuredTier
    ? featuredTier.tags
    : [{ label: "Most chosen", tone: "neutral" as Tone }];
  const previewNote = featuredTier
    ? featuredTier.active
      ? null
      : "Not active — this card stays hidden until the tier is ready."
    : "Feature a tier to publish this card.";

  return (
    <DevCard
      title="Pricing tags, featured tier & card style"
      description="Badges shown beside each tier on the marketing pricing cards and the workspace calculator, plus the treatment of the highlighted card with a live preview. Prices themselves come from the rate tables above, so editing a rate updates the public page without touching this card."
      actions={
        <div className="flex flex-wrap items-center justify-end gap-2 text-[11px] text-text-subtle">
          <span className="rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel px-2.5 py-1 font-mono">
            v{resource.data?.version ?? 0}
          </span>
          <span>
            {savedAt ? "Saved just now" : `Updated ${formatWhen(resource.data?.updatedAt)}`}
            {resource.data?.updatedBy ? ` by ${resource.data.updatedBy}` : ""}
          </span>
        </div>
      }
    >
      {resource.loading && !resource.data ? (
        <div className="grid gap-3 sm:grid-cols-3" aria-busy="true" aria-label="Loading pricing tags">
          {[0, 1, 2].map((key) => (
            <div
              key={key}
              className="h-48 animate-pulse rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel"
            />
          ))}
        </div>
      ) : resource.error ? (
        <div className="space-y-3">
          <p className="rounded-skeuo-sm border border-red-200 bg-red-50 p-3 text-xs text-red-700">
            {resource.error}
          </p>
          <SkeuoButton type="button" onClick={() => void resource.reload()}>
            Retry
          </SkeuoButton>
        </div>
      ) : (
        <fieldset disabled={busy} className="min-w-0 space-y-4 pt-1">
          <p className="rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised p-3 text-xs text-text-muted">
            Every stack configured in the voice stack appears here, including custom stacks. Up to{" "}
            {MAX_TAGS} tags per tier, {MAX_TAG_LENGTH} characters each. One tier can be featured. Tags are
            plain text — vendor names, carrier names and links are rejected, and the public API publishes a
            tier only while it is enabled and ready for tenants; inactive tiers keep their saved tags until
            then.
          </p>

          <div className="grid gap-4 rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-raised p-4 lg:grid-cols-[1.15fr_0.85fr]">
            <div className="min-w-0" role="group" aria-labelledby="featured-style-heading">
              <h3 id="featured-style-heading" className="text-sm font-semibold text-text">
                Highlight card style
              </h3>
              <p className="mt-1 text-xs text-text-muted">
                Pick how the featured tier card looks on the marketing pricing page. The preview
                uses the featured tier&apos;s saved tags and published shelf price.
              </p>
              <div className="mt-3 grid gap-2 sm:grid-cols-2">
                {FEATURED_STYLE_OPTIONS.map((option) => {
                  const selected = featuredStyle === option.id;
                  return (
                    <button
                      key={option.id}
                      type="button"
                      aria-pressed={selected}
                      onClick={() => {
                        setFeaturedStyle(option.id);
                        setSavedAt(null);
                      }}
                      className={`rounded-skeuo-sm border p-2.5 text-left transition ${
                        selected
                          ? "border-indigo-300 bg-indigo-50/60 ring-1 ring-indigo-200"
                          : "border-surface-border-subtle bg-surface-panel hover:border-surface-border-strong"
                      }`}
                    >
                      <span
                        className="flex h-10 items-center justify-center rounded-md border text-[11px] font-semibold uppercase tracking-[0.14em]"
                        style={{
                          background: option.palette.background,
                          borderColor: option.palette.border,
                          color: option.palette.accent,
                        }}
                      >
                        Aa
                      </span>
                      <span className="mt-2 block text-xs font-semibold text-text">
                        {selected ? `${option.label} · selected` : option.label}
                      </span>
                      <span className="mt-0.5 block text-[11px] leading-snug text-text-subtle">
                        {option.description}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>

            <FeaturedCardPreview
              style={featuredStyle}
              label={featuredTier?.label ?? "Your featured tier"}
              tags={previewTags}
              pstnInrPerMin={featuredTier?.pstnInrPerMin ?? null}
              webInrPerMin={featuredTier?.webInrPerMin ?? null}
              note={previewNote}
            />
          </div>

          <div className="grid gap-3 lg:grid-cols-3">
            {drafts.map((tier) => {
              const input = inputFor(tier.id);
              return (
                <section
                  key={tier.id}
                  aria-label={`${tier.label} pricing tags`}
                  className={`rounded-skeuo-sm border p-4 ${
                    tier.featured
                      ? "border-indigo-300 bg-indigo-50/40"
                      : "border-surface-border-subtle bg-surface-panel"
                  }`}
                >
                  <header className="flex items-start justify-between gap-2">
                    <div>
                      <h3 className="text-sm font-semibold text-text">{tier.label}</h3>
                      <p className="font-mono text-[11px] text-text-subtle">{tier.id}</p>
                      {tier.active ? (
                        <span className="mt-1 inline-flex rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[10px] font-semibold text-emerald-700">
                          Active · published
                        </span>
                      ) : (
                        <span className="mt-1 inline-flex rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[10px] font-semibold text-amber-800">
                          Not active · hidden from marketing
                        </span>
                      )}
                    </div>
                    <div className="space-y-1 text-right text-[11px]">
                      <label className="flex items-center justify-end gap-1.5">
                        <input
                          type="checkbox"
                          checked={tier.visible}
                          onChange={(event) =>
                            updateTier(tier.id, { visible: event.target.checked })
                          }
                          aria-label={`Show ${tier.label} on public pricing`}
                        />
                        Visible
                      </label>
                      <label className="flex items-center justify-end gap-1.5">
                        <input
                          type="radio"
                          name="featured-tier"
                          checked={tier.featured}
                          onChange={() => setFeatured(tier.id)}
                          aria-label={`Feature ${tier.label}`}
                        />
                        Featured
                      </label>
                    </div>
                  </header>

                  <ul className="mt-3 flex flex-wrap gap-1.5" aria-label={`${tier.label} tags`}>
                    {tier.tags.length === 0 ? (
                      <li className="text-[11px] text-text-subtle">No tags yet.</li>
                    ) : (
                      tier.tags.map((tag, index) => (
                        <li
                          key={`${tag.label}-${index}`}
                          className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold ${TONE_CHIP[tag.tone]}`}
                        >
                          <span>{tag.label}</span>
                          <select
                            value={tag.tone}
                            onChange={(event) =>
                              setTagTone(tier.id, index, event.target.value as Tone)
                            }
                            aria-label={`Style for ${tag.label}`}
                            className="rounded bg-transparent text-[10px] text-inherit"
                          >
                            {TONES.map((tone) => (
                              <option key={tone.value} value={tone.value}>
                                {tone.label}
                              </option>
                            ))}
                          </select>
                          <button
                            type="button"
                            onClick={() => removeTag(tier.id, index)}
                            aria-label={`Remove ${tag.label}`}
                            className="rounded-full px-1 text-inherit hover:bg-black/5"
                          >
                            ×
                          </button>
                        </li>
                      ))
                    )}
                  </ul>

                  <div className="mt-3 space-y-2">
                    <SkeuoInput
                      value={input.label}
                      onChange={(event) => updateTagInput(tier.id, { label: event.target.value })}
                      onKeyDown={(event) => {
                        if (event.key === "Enter") {
                          event.preventDefault();
                          addTag(tier.id);
                        }
                      }}
                      maxLength={MAX_TAG_LENGTH}
                      placeholder="Most chosen"
                      aria-label={`New tag for ${tier.label}`}
                    />
                    <div className="flex items-center gap-2">
                      <select
                        value={input.tone}
                        onChange={(event) =>
                          updateTagInput(tier.id, { tone: event.target.value as Tone })
                        }
                        aria-label={`New tag style for ${tier.label}`}
                        className="w-full rounded-skeuo-sm border border-surface-border-subtle bg-surface-panel-inset px-2 py-1.5 text-xs text-text shadow-inset"
                      >
                        {TONES.map((tone) => (
                          <option key={tone.value} value={tone.value}>
                            {tone.label}
                          </option>
                        ))}
                      </select>
                      <SkeuoButton
                        type="button"
                        onClick={() => addTag(tier.id)}
                        disabled={tier.tags.length >= MAX_TAGS}
                      >
                        Add
                      </SkeuoButton>
                    </div>
                  </div>
                </section>
              );
            })}
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-surface-border-subtle pt-4">
            <p className="max-w-xl text-[11px] text-text-subtle">
              Hidden tiers stay out of the public pricing cards but keep their saved rates.
              Feature at most one tier so the landing page highlights a single choice.
            </p>
            <div className="flex items-center gap-3">
              {error ? (
                <span className="max-w-xs text-xs font-medium text-status-error">{error}</span>
              ) : null}
              {!error && savedAt ? (
                <span className="text-xs font-medium text-emerald-700">Saved.</span>
              ) : null}
              <SkeuoButton
                type="button"
                onClick={() => {
                  setDrafts(serverDrafts);
                  setFeaturedStyle(serverStyle);
                  setTagInputs({});
                  setError(null);
                  setSavedAt(null);
                }}
                disabled={!dirty || busy}
              >
                Discard
              </SkeuoButton>
              <SkeuoButton type="button" onClick={save} disabled={busy || !dirty}>
                {busy ? "Saving…" : "Save tags"}
              </SkeuoButton>
            </div>
          </div>
        </fieldset>
      )}
    </DevCard>
  );
}

# Stitch exports drop folder

Put screens from [Stitch project 17901155908568771114](https://stitch.withgoogle.com/projects/17901155908568771114) here.

## Naming

```text
01-home-hero.png
01-home-hero.html
02-pricing.png
03-signin-business.png
04-console-overview.png
05-test-studio.png
06-calls-detail.png
07-billing-checkout.png
08-dev-overview.png
```

Device suffix if needed: `01-home-hero.desktop.png`, `01-home-hero.mobile.png`.

## After drop-in

1. Update the inventory table in [`../01-stitch-source-and-alignment.md`](../01-stitch-source-and-alignment.md).
2. Implement with tokens from [`../02-ui-style-system.md`](../02-ui-style-system.md) — do not commit Stitch’s default Material CSS into `web/`.
3. PNGs used on the site go through `next/image` (copy into `web/public/marketing/` if needed). This folder stays documentation-only.

## Git

Binary PNGs can be large. Prefer HTML + a few key PNGs; don’t dump every variant.

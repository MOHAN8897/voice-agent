---
name: design-md
description: Author, lint, and export Google DESIGN.md token spec files for this project. Use when creating or updating DESIGN.md, exporting Tailwind/DTCG tokens, or validating WCAG contrast.
---

# DESIGN.md Skill

This project uses Google's DESIGN.md spec (`@google/design.md`) as the visual source of truth.

Canonical file: `DESIGN.md` at the repository root.

## Commands (Windows)

Use the dot-free alias so PowerShell does not open the markdown file:

```bash
npx -y -p @google/design.md designmd lint DESIGN.md
npx -y -p @google/design.md designmd export --format css-tailwind DESIGN.md
npx -y -p @google/design.md designmd export --format json-tailwind DESIGN.md
```

## Rules

1. Read `DESIGN.md` before generating any UI.
2. Do not invent colors, fonts, radii, or spacing outside the token file.
3. Component YAML keys must use `backgroundColor`, `textColor`, `rounded`, `padding` — never `background` / `color` / `borderRadius`.
4. Hover variants are sibling keys (`button-primary-hover`), not nested objects.
5. After editing tokens, lint, then sync `web/tailwind.config.js` and `web/app/globals.css`.
6. Marketing and consoles share the same palette; density changes, not brand.

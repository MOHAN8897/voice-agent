---
name: emil-kowalski-craft
description: >-
  Provides guidelines, component recipes, design tokens, and anti-pattern checklists for building
  editorial, high-craft user interfaces inspired by Emil Kowalski. Use when designing, reviewing,
  or refactoring landing pages, components, and design systems for enterprise SaaS.
---

# Emil Kowalski Craft Skill

This skill provides practical recipes, tokens, and checklists for executing high-craft product design.

## Core Philosophy
1. **Restraint over decoration**: Remove unnecessary gradients, blurred background orbs, and generic glassmorphism. Use clean negative space.
2. **Tactile feedback**: Interactive elements should feel physical. Use subtle active scaling (`active:scale-[0.98]`), distinct focus rings, and crisp borders.
3. **Typographic hierarchy**: Solid `#0F0E17` display typography with tight tracking (`tracking-tight`), paired with high-contrast `#524E5E` body copy.
4. **Editorial asymmetry**: Replace monotonous repetitive card grids with structured data tables, asymmetric workbench layouts, and narrative process flows.

## Quick Component Recipes

### Primary Button
```jsx
<button
  className="inline-flex items-center justify-center gap-2 px-6 py-3 rounded-xl text-sm font-semibold text-white bg-[#0F0E17] hover:bg-[#232130] active:scale-[0.98] transition-all duration-150 shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#6344E7]"
>
  Build Your Agent
</button>
```

### Secondary Button
```jsx
<button
  className="inline-flex items-center justify-center gap-2 px-6 py-3 rounded-xl text-sm font-semibold text-[#0F0E17] bg-white hover:bg-[#F9F8FD] border border-[#E4E2EB] active:scale-[0.98] transition-all duration-150 shadow-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#6344E7]"
>
  Talk to AI
</button>
```

### High-Craft Solid Card
```jsx
<div className="bg-white rounded-2xl border border-[#E4E2EB] p-6 sm:p-8 shadow-[0_1px_3px_rgba(0,0,0,0.04)] hover:border-[#D1CFDB] transition-all">
  {/* Card Content */}
</div>
```

### Dark Workbench Panel
```jsx
<div className="bg-[#111019] rounded-2xl border border-white/10 p-6 sm:p-8 text-white shadow-xl">
  {/* High contrast dark module */}
</div>
```

### Segmented Tab Control
```jsx
<div className="inline-flex p-1 rounded-xl bg-[#F0EEF6] border border-[#E4E2EB]">
  {tabs.map((tab) => (
    <button
      key={tab.id}
      onClick={() => setActiveTab(tab.id)}
      className={`px-4 py-2 rounded-lg text-xs font-semibold transition-all ${
        activeTab === tab.id
          ? 'bg-white text-[#0F0E17] shadow-xs'
          : 'text-[#524E5E] hover:text-[#0F0E17]'
      }`}
    >
      {tab.label}
    </button>
  ))}
</div>
```

# 05 · Design System

**Direction:** Vercel's precision + ChatGPT's chat ergonomics, built on **shadcn/ui (zinc)** with **prompt-kit** for everything conversational. **Strictly black / white / neutral greys.** No brand color. Functional amber/red only for flags.

## 1. Principles
1. **Data first, chrome last.** Hairline borders (1px), no shadows except overlays, no gradients, no decorative color.
2. **Numbers are the hero.** Large tabular numerals for KPIs; units always adjacent in muted text.
3. **Color never carries meaning alone.** Severity = icon + label; deltas = ▲/▼ + sign; chart series = shade + dash + direct label.
4. **One black mark per view.** The recommended price is the only solid-black data mark; everything else is outlined or grey.
5. **Calm density.** 14px body, 32–36px controls, 44px table rows, generous 24px gutters.

## 2. Tokens (CSS variables, shadcn naming)

Light (`:root`) · Dark (`.dark`). Neutral = zinc.

| Token | Light | Dark |
|---|---|---|
| `--background` | `#FFFFFF` | `#09090B` |
| `--foreground` | `#09090B` | `#FAFAFA` |
| `--card` | `#FFFFFF` | `#09090B` |
| `--muted` | `#F4F4F5` | `#18181B` |
| `--muted-foreground` | `#71717A` | `#A1A1AA` |
| `--border` / `--input` | `#E4E4E7` | `#27272A` |
| `--accent` (hover/selected) | `#F4F4F5` | `#27272A` |
| `--primary` | `#18181B` | `#FAFAFA` |
| `--primary-foreground` | `#FAFAFA` | `#18181B` |
| `--secondary` | `#F4F4F5` | `#27272A` |
| `--ring` | `#A1A1AA` | `#52525B` |
| `--sidebar` | `#FAFAFA` | `#0C0C0E` |
| **Functional** `--warning` | `#B45309` text · `#FEF3C7` bg · `#F59E0B` dot | `#FBBF24` text · `#2A1F05` bg |
| **Functional** `--destructive` | `#B91C1C` text · `#FEE2E2` bg · `#EF4444` dot | `#F87171` text · `#2A0A0A` bg |

Greyscale chart ramp (series order): `#09090B` · `#52525B` · `#A1A1AA` · `#D4D4D8` (dark mode reversed: `#FAFAFA` · `#A1A1AA` · `#71717A` · `#3F3F46`).

Radius: `--radius: 8px` (controls 6, cards 12, sheets 12, pills 999). Border: 1px `--border`. Focus ring: 2px `--ring` offset 2.

## 3. Typography
- **UI:** Geist Sans (fallback Inter, system-ui). **Numerals/code/units:** Geist Mono with `font-variant-numeric: tabular-nums`.
- Scale (px / line / weight): Display 28/34/600 (page titles) · H2 20/28/600 · H3 16/24/600 · Body 14/22/400 · Small 13/20/400 · Micro 12/16/500 (labels, badges) · KPI 32/36/600 mono-tabular.
- Letter-spacing −0.01em on ≥20px. Sentence case everywhere.

## 4. Spacing & layout
4px base. Page gutter 24 (mobile 16). Section gap 24. Card padding 20. Table row 44, header 40. Sidebar 260/56. Ask AI 380. Max content width 1200 for tabs; chat column max 720 centered (ChatGPT).

## 5. Components

### 5.1 From shadcn/ui
`Sidebar`, `Button` (default = solid primary, outline, ghost), `Input`, `Select`, `Combobox`/`Command` (⌘K and multiselect), `Tabs` (underline variant, Vercel), `ToggleGroup` (segmented), `Table`, `Badge`, `Card`, `Dialog`, `Sheet`, `Tooltip`, `Popover`, `DropdownMenu`, `Separator`, `Skeleton`, `Switch`, `Checkbox`, `Slider`, `Sonner` toast, `Chart` (Recharts wrapper), `Collapsible`, `ScrollArea`, `Breadcrumb`.

### 5.2 From prompt-kit (installed via registry)
| Need | Component |
|---|---|
| Thread layout & autoscroll | `ChatContainer`, `ScrollButton` |
| Messages | `Message` (avatar, content), `Markdown`, `CodeBlock` (formulas) |
| Composer | `PromptInput` (+ actions: attach `FileUpload`, Configure run, send) |
| Suggestions | `PromptSuggestion` |
| Agent progress | `Steps`, `ChainOfThought`, `Reasoning`, `ThinkingBar`, `TextShimmer`, `Loader` |
| Engine call | `Tool` |
| Citations | `Source` |
| Warnings in thread | `SystemMessage` |
| Memo feedback | `FeedbackBar` |
| Upload dropzone | `FileUpload` |
| Memo/inline images | `Image` (optional) |

### 5.3 Custom (built from shadcn primitives)
| Component | Spec |
|---|---|
| **PriceLadder** | Horizontal bar in USD/t. Floor (cost-plus) → ceiling (value) as a 2px track with 8px end caps; corridor band `bg-muted`; **anchor = solid black 14px circle + value label**; market = outlined diamond tick (or dashed "Add benchmark" chip); reference price = thin vertical line labelled "TSP 640". Below-floor segment: amber hatched fill + icon. Labels above/below, mono numerals. Mini variant (height 56) for ResultCard. |
| **KpiCard** | Label 13 muted · value 32 mono · unit muted · delta `▲ 3.02 vs TSP` · optional 24px sparkline (greyscale). Variants: default, pinned (1.5px black border). |
| **PivotBar** | Three `ToggleGroup`-style chips *Product ▾ · Strategy ▾ · Metric ▾*; pinned chip has a pin glyph and solid-black border; others dashed hint. Click pin to move. |
| **VersionChip** | `v2 ▾` popover: list of runs with time, author (You/Agent), change summary; "Compare with v1". |
| **ProvenanceBadge** | 12px mono pill: `Prices · 21 Apr` · `Standard cost · 2026` · `You edited ●` · `Agent assumption`. Hover = source detail. |
| **FlagRow / FlagBanner** | Icon (triangle/octagon/info/check) + title + detail + action link. Amber/red hairline-tinted background (`warning`/`destructive` bg tokens). |
| **ResultCard** | Card: title, run chip, mini PriceLadder, 3 KPIs, up to 2 flags, buttons *Open simulation*, *Memo*. |
| **ChangeCard** | Diff row (`before → after`, strikethrough/bold), reason, buttons *Apply & re-run (vN)* (primary) · *Dismiss*. |
| **DerivedBanner** | Full-width muted strip: "Viewing under 2025 conditions · Back to Today". |
| **FreshnessChip** | Ghost pill: `Latest upload · 02 Oct 2026 · Data through 24 Sep`; amber dot when warning. |
| **MethodCard** | Method name, price (mono 24), formula in words, inputs used (ProvenanceBadges), status (Ready / Needs input). |
| **RecipeTable** | Editable table w/ "+ Add ingredient" row; live unit cost footer. |

## 6. Charts (Recharts via shadcn `Chart`, greyscale)
- Axes: 12px muted ticks, no axis lines, horizontal gridlines `--border` dashed 2 2.
- **Direct labels** at series ends instead of legends. Tooltips: black card, white text, mono values (Vercel style).
- **C1 Price by method** (grouped horizontal bars): cost-plus `#A1A1AA`, market outlined, value `#52525B`, reference-minus `#09090B` (anchor), reference price as dashed vertical line.
- **C2 Volume ramp-up** (area + line): line solid black, area `#F4F4F5`; label "Illustrative ramp-up".
- **C3 CGM waterfall**: totals solid black/dark-grey; increases filled `#52525B`; decreases hatched pattern (SVG `pattern` 45° 1px); connector lines dashed.
- **C4 Carbon scenarios** (bars + baseline line): bars `#D4D4D8` with value labels; empty state when no carbon price.
- **Across-years strip**: tiny table + sparkline of anchor price; current column outlined.
- Sparklines: 1.5px solid, no dots, last-point 4px dot.

## 7. Motion
150ms ease-out for hovers/popovers, 200ms for sheets/dialogs (translate 8px + opacity). `TextShimmer` on in-flight steps; `Steps` complete with a check that fades in. Respect `prefers-reduced-motion` (disable shimmer/translate).

## 8. Iconography
Lucide, 16px (20 in sidebar), stroke 1.5. Severity icons: `AlertTriangle` (warning), `OctagonAlert` (error), `Info`, `CircleCheck` (resolved).

## 9. Responsive rules
| Breakpoint | Rules |
|---|---|
| ≥1280 | 3 panes (Sidebar 260 · Main · Ask AI 380). KPI row 3–4 across. Dashboard charts 2×2. |
| 1024–1279 | Sidebar rail 56; Ask AI overlay (⌘/). KPI 3 across; charts 2×2 compact. |
| 768–1023 | Sidebar drawer; tables scroll-x; KPI 2 across; charts 1 col. |
| <768 (mobile, second target) | Bottom-anchored composer; ☰ drawer for history; pivot bar & tabs become scroll-snap strips; tables → stacked cards (key figure first); Run form & sheets = full-height bottom sheets; Ask AI = full-screen view via floating "Ask AI" pill; PriceLadder keeps horizontal with labels beneath; touch targets ≥ 44px. |

## 10. Accessibility
WCAG AA contrast both modes; visible focus; all charts have a data table alternative (toggle "View as table"); `aria-live="polite"` for streaming steps; dialogs trap focus; keyboard map in doc 02 §7; no color-only meaning.

## 11. Empty-state & voice
Short, lowercase-friendly sentences: "Nothing here yet." / "No benchmark added." with one clear action. No illustrations; a single 16px icon at most.

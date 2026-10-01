# Interface design system

The application, the published exhibits and the landing page share one visual system. Tokens and shared components are defined once, in `src/pe_value_os/api/presentation.py` (`CSS`). The hand-written landing page, `docs/index.html`, carries its own stylesheet built on the same token values.

## Direction

- **Primary reference: Attio.** Light, neutral surfaces, compact tables, subtle dividers and tidy record layouts.
- **Financial figures: Mercury.** Tabular numerals, right-aligned amounts and restrained colour.
- **Typography, controls, colour scales and states: Vercel Geist.**

These are style references only. No branding, assets or layouts are copied.

## Rules

- **One accent.** Blue is used for links, focus, selection and the first chart series. Primary buttons are near-black.
- **Colour means state.** Green, amber, red and blue appear only on status badges, alerts and chart directions. Category tags such as *Quick win* or *In plan* stay neutral grey. A status is always shown as text, never as colour alone.
- **Hierarchy comes from type, spacing and alignment.** No gradients, decorative borders, uppercase letter-spaced labels or heavy shadows.
- **Flat by default.** Surfaces are separated by 1 px borders. The single elevation (`--shadow-raised`) is reserved for surfaces that float over content: the detail panel, the skip link and the landing-page product preview.
- **Tables come before cards** for anything with rows: companies, initiatives and value cases. Figures are tabular; amounts are right-aligned with `.num`, and totals sit in a `tfoot` row.
- **A list with a detail panel** shows one record at a time. Selecting a row opens its panel through a link fragment (`:target`), so it needs no script.

## Tokens

| Token | Value |
|---|---|
| Typeface | Inter (SIL Open Font License), self-hosted: `src/pe_value_os/api/assets/`, `docs/assets/fonts/`. Falls back to system UI fonts. Feature `ss01` (open digits) everywhere; tabular numerals (`tnum`) in tables, metrics and badges |
| Type scale (size/line height, px) | 12/18 captions, table headers, notes · 13/20 table body, secondary text, controls · 14/22 body · 16/24 section titles · 24/32 page titles · 28/35 headline figures. Weights 400, 500 and 600 only |
| Tracking | Negative only at display sizes: −0.006em at 14, −0.011em at 16, −0.02em at 24, −0.022em at 28 (figures). Body and small text 0 |
| Spacing | 4 px base: 4, 8, 12, 16, 20, 24, 32, 40, 48. Table cells 8 × 12; panels 20 (16 under 420 px) |
| Surfaces | `--bg #ffffff` content · `--bg-subtle #fafafa` sidebar, table header, totals · `--bg-muted #f4f4f5` fills, hover · `--bg-active #ececee` selected |
| Text | `--text #171717` primary · `--text-2 #4d4d55` secondary · `--text-3 #66666e` tertiary (notes, captions, labels) |
| Borders | `--border #ebebed` dividers · `--border-strong #dcdce0` controls, tags · `--border-input #8a8a92` form fields (3:1 boundary) |
| Radii | `--r-sm 4` badges · `--r-md 6` buttons, inputs · `--r-lg 8` panels, tables, disclosures · 12 landing-page cards |
| Accent | `--accent #2f5bea` (hover `#2349c9`, soft `#eef2fe`, line `#c9d5fa`) |
| Primary button | `--primary #18181b` (hover `#323238`) |
| Status (text on fill, border) | ok `#16653a` on `#effaf3`, `#bfe3cc` · warning `#8a5300` on `#fff8eb`, `#efd9a7` (alert body `#5f3c05`) · error `#b42318` on `#fef4f3`, `#f2c6c0` · info `#2349c9` on `#eef2fe`, `#c9d5fa` |
| Elevation | `--shadow-raised: 0 1px 2px rgb(0 0 0/4%), 0 4px 16px rgb(0 0 0/5%)`; everything else `none` |
| Focus | 2 px `--accent` outline, 2 px offset. Text fields add `--ring` (3 px accent at 20%) and keep a transparent outline so forced-colors mode still shows focus |
| Motion | 150 ms `cubic-bezier(.2,0,0,1)` on colour and chevron rotation only; removed under `prefers-reduced-motion` |
| Charts | increase `#3c9a6b` · decrease `#d4604f` · total `#18181b` (each ≥ 3:1 on white) |

## Contrast

Every text token meets WCAG 2.x AA (4.5:1) on every surface it is used on. Lowest ratios: `--text-3` 4.82:1 on `--bg-active`, 5.09:1 on the accent and info fills, 5.18:1 on `--bg-muted`, 5.69:1 on white; `--accent` 4.68:1 on `--bg-active`, 5.52:1 on white; status text 5.99–6.64:1 on its own fill. White on `--primary` is 17.7:1. The previous tertiary grey (`#8e8e93`, 3.3:1) is retired.

## Components

- **Buttons** (`.button`, `button`): primary (near-black), `.secondary` (white, strong border), `.danger` (white, red text and border). Sizes `.small` 28 px, default 32 px, `.large` 40 px; every button is at least 40 px tall under 760 px. Disabled (`:disabled`, `[aria-disabled=true]`) uses a muted fill and tertiary text instead of opacity.
- **Form fields**: 36 px (40 px and 16 px text on touch screens), `--border-input` boundary, accent border and ring on focus, `aria-invalid` turns the border red. Checkboxes and radios use the primary colour. `fieldset`/`legend` group related notes.
- **Badges** (`.badge`): a status badge (`status_badge()`, `.state-*`) has a tinted fill, a tinted border, a dot and a text label; a tag (`.badge` without a state) is neutral grey.
- **Tables**: `--bg-subtle` header row with 12 px medium labels, 13/20 body, hover on rows, `tfoot` totals with a strong top border. Column labels and descriptive notes use proportional figures; data cells use tabular figures. `.num` right-aligns an amount.
- **Panels and metric cards**: 1 px border, 8 px radius, no shadow. A metric card is a 13 px label, a 28 px figure and a 12 px note.
- **Alerts** (`.alert`, `.warning`, `.alert.bad`, `.alert.info`) and **empty states** (`.empty-state`, dashed border).
- **Disclosures** (`details`, `.disclosure`): bordered container with a border-drawn chevron that points right when closed and down when open; 40 px summary (44 px on touch screens).

## Accessibility and output

- **Forced colours**: status dots and progress bars switch to `CanvasText`, tracks gain a border, and `[aria-current=page]` gains an outline, so no state depends on a background fill alone.
- **Print**: navigation and forms are hidden, table headers repeat on each page, rows and cards avoid page breaks, status fills print, and disclosure content prints where the browser supports `::details-content`.
- **Contrast check**: any token change should be re-run through a WCAG relative-luminance check of each text token against each surface listed above.

## Layout

- **Application pages** (`page()`): a 232 px sidebar holds the brand, workspace navigation and data-provenance note, beside a content column of at most 1,200 px. Under 900 px the sidebar becomes a top bar.
- **Sign-in** has no workspace navigation.
- **Exhibits** (generated reports) use a slim top bar with section links, because they are documents rather than application screens.
- **Landing page**: a centred hero with one primary and one secondary action, a product preview of the current decision, then full-width sections separated by hairlines. Content width 1,200 px.
- **Responsiveness:** every page must render without horizontal overflow at 375, 768 and 1440 px with all disclosures open. `scripts/check_portfolio_browser.py` and `scripts/check_private_review_browser.py` enforce this in CI.

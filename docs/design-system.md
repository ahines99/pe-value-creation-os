# Interface design system

The application, the published exhibits and the landing page share one visual system. It is defined once, in `src/pe_value_os/api/presentation.py` (`CSS`). The landing page in `docs/index.html` carries a matching override block.

## Direction

- **Primary reference: Attio.** Light, neutral surfaces, compact tables, subtle dividers and tidy record layouts.
- **Financial figures: Mercury.** Tabular numerals, right-aligned amounts and restrained colour.
- **Controls and colour scales: Vercel Geist.**

These are style references only. No branding, assets or layouts are copied.

## Rules

- **One accent.** Blue is used for links, focus, selection and the first chart series. Primary buttons are near-black.
- **Colour means state.** Green, amber, red and blue appear only on status badges and chart directions. Category tags such as *Quick win* or *In plan* stay neutral grey. A status is always shown as text, never as colour alone.
- **Hierarchy comes from type, spacing and alignment.** No gradients, decorative borders, uppercase letter-spaced labels or heavy shadows. Shadows are reserved for the floating detail panel.
- **Tables come before cards** for anything with rows: companies, initiatives and value cases. Figures are tabular and right-aligned, and totals sit in a `tfoot` row.
- **A list with a detail panel** shows one record at a time. Selecting a row opens its panel through a link fragment (`:target`), so it needs no script.

## Tokens

| Token | Value |
|---|---|
| Typeface | Inter (SIL Open Font License), self-hosted: `src/pe_value_os/api/assets/`, `docs/assets/fonts/`. Falls back to system UI fonts |
| Type scale | 12 captions, table headers · 13 table body, secondary text, controls · 14 body · 16 section titles · 24 page titles · 28 headline figures. Weights 400, 500 and 600 only |
| Spacing | 4 px base: 4, 8, 12, 16, 20, 24, 32, 48. Table cells 8 × 12 |
| Surfaces | Content `#ffffff`; sidebar and table header `#fafafa`; muted fill `#f4f4f5` |
| Text | `#171717` primary · `#52525b` secondary · `#8e8e93` tertiary |
| Borders | 1 px `#ebebeb` default, `#dfdfe2` strong |
| Radii | 4 badges · 6 buttons and inputs · 8 panels and tables |
| Accent | `#2f5bea` (hover `#2349c9`, soft `#eef2fe`) |
| Primary button | `#18181b` (hover `#2c2c30`) |
| Status | ok `#16653a` on `#effaf3` · warning `#8a5300` on `#fff8eb` · error `#b42318` on `#fef4f3` · info `#2349c9` on `#eef2fe` |
| Charts | increase `#3c9a6b` · decrease `#d4604f` · total `#18181b` |

## Layout

- **Application pages** (`page()`): a 232 px sidebar holds the brand, workspace navigation and data-provenance note, beside a content column of at most 1,200 px. Under 900 px the sidebar becomes a top bar.
- **Sign-in** has no workspace navigation.
- **Exhibits** (generated reports) use a slim top bar with section links, because they are documents rather than application screens.
- **Responsiveness:** every page must render without horizontal overflow at 375, 768 and 1440 px with all disclosures open. `scripts/check_portfolio_browser.py` and `scripts/check_private_review_browser.py` enforce this in CI.

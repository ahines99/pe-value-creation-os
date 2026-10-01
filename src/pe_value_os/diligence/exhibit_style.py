"""Document shell and exhibit-only styles for the published report pages.

The shared tokens and components live in ``api.presentation.CSS``. ``EXHIBIT_CSS`` is appended after it
and only changes how generated reports read as documents: a slim report header, an on-page contents
list, section rhythm, right-aligned figures and quieter disclosures. It adds no script and no external
request. Any new token uses the ``--x-`` prefix so it cannot collide with the shared stylesheet.
"""

from __future__ import annotations

import re
from html import escape

from ..api.presentation import BRAND_MARK, CSS

EXHIBIT_CSS = """
:root{--x-quiet:#6b6b73;--x-prose:72ch;--x-toc:216px;--x-head:57px;--x-figure:30px}
html{scroll-padding-top:calc(var(--x-head) + 16px)}
.exhibit{background:var(--bg)}
.exhibit table{font-variant-numeric:normal}
.exhibit .num,.exhibit td.num,.exhibit th.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.exhibit th.num{font-variant-numeric:normal;white-space:normal}

/* Report header */
.exhibit .topbar{position:sticky;top:0;z-index:20;background:rgb(255 255 255 / 94%);backdrop-filter:saturate(1.4) blur(8px)}
.exhibit .topbar-inner{max-width:1296px;min-height:56px;padding:8px 32px;gap:16px}
.exhibit .brand .brand-subtitle{font-size:12px}
.x-kind{display:inline-flex;align-items:center;min-width:0;gap:8px;font-size:13px;color:var(--text-2)}
.x-provenance{display:inline-flex;align-items:center;min-height:22px;padding:0 8px;border:1px solid var(--border-strong);border-radius:var(--r-sm);background:var(--bg-subtle);font-size:12px;font-weight:500;color:var(--text-2);white-space:nowrap}
.exhibit .primary-nav{margin-left:auto}
.exhibit .x-provenance+.primary-nav{margin-left:8px}
.exhibit .topbar-inner>.x-provenance{margin-left:auto}

/* Frame: contents list beside a document column */
.x-frame{max-width:1296px;margin:0 auto}
.x-toc{display:none}
.exhibit .x-frame>.app-shell{max-width:1120px;padding:32px 32px 64px}
@media(min-width:1280px){
  .x-frame{display:grid;grid-template-columns:var(--x-toc) minmax(0,1fr);gap:48px;padding:0 32px}
  .exhibit .x-frame>.app-shell{max-width:none;padding:32px 0 72px;margin:0}
  .x-toc{display:block;position:sticky;top:var(--x-head);align-self:start;max-height:calc(100vh - var(--x-head));overflow-y:auto;padding:32px 0 24px}
  .exhibit .topbar .primary-nav{display:none}
}
.x-toc p{font-size:12px;font-weight:500;color:var(--x-quiet);margin:0 0 8px 12px}
.x-toc ol{list-style:none;margin:0;padding:0;border-left:1px solid var(--border)}
.x-toc li+li{margin-top:0}
.x-toc a{display:block;padding:5px 12px;margin-left:-1px;border-left:1px solid transparent;color:var(--text-2);font-size:13px;line-height:1.4;text-decoration:none}
.x-toc a:hover{color:var(--text);border-left-color:var(--text-3)}
.x-toc .x-toc-meta{display:block;margin-top:16px;padding-top:12px;border-top:1px solid var(--border);font-size:12px;color:var(--x-quiet);line-height:1.5;margin-left:0}

/* Title block */
.exhibit .hero{background:transparent;border:0;border-radius:0;padding:0;margin:0 0 32px;grid-template-columns:minmax(0,1fr) minmax(260px,340px);gap:48px;align-items:start}
.exhibit .hero .eyebrow{font-size:12px;color:var(--x-quiet);margin-bottom:10px}
.exhibit .hero h1{font-size:30px;line-height:1.18;letter-spacing:-.022em;max-width:28ch}
.exhibit .hero .page-subtitle{font-size:16px;line-height:1.5;color:var(--text-2);margin-top:10px;max-width:60ch}
.exhibit .hero>div>p:not(.eyebrow):not(.page-subtitle){font-size:14px;color:var(--text-2);margin-top:14px;max-width:68ch}
.exhibit .hero-aside,.exhibit .hero-aside.panel{border:1px solid var(--border);border-radius:var(--r-lg);background:var(--bg-subtle);padding:16px 20px;gap:8px;justify-content:flex-start;margin:0}
.exhibit .hero-aside .metric-label{font-size:12px;color:var(--x-quiet);margin:0}
.exhibit .hero-aside p{font-size:14px;line-height:1.55;color:var(--text);max-width:none}
.exhibit .hero-aside p+p{font-size:12px;color:var(--text-2);margin-top:4px}
.exhibit .hero-aside .metric-value{font-size:24px}
.exhibit .hero-aside .metric-note{margin-top:0}

/* Headline figures */
.exhibit .metrics-grid{gap:12px;margin:0 0 8px}
.exhibit .metric-card{padding:16px 18px 18px;display:flex;flex-direction:column}
.exhibit .metric-label{font-size:13px;color:var(--text-2);margin-bottom:10px}
.exhibit .metric-value{font-size:var(--x-figure);font-weight:600;letter-spacing:-.025em;line-height:1.1;font-variant-numeric:normal}
.exhibit .metric-note{margin-top:auto;padding-top:10px;font-size:12px;color:var(--x-quiet)}
.x-unit{font-size:13px;font-weight:500;letter-spacing:0;color:var(--x-quiet);margin-left:2px;white-space:nowrap}

/* Sections */
.exhibit .x-doc>.panel,.exhibit .x-doc>section.panel{background:transparent;border:0;border-top:1px solid var(--border);border-radius:0;padding:28px 0 4px;margin:36px 0 0}
.exhibit .x-doc>.hero+.panel,.exhibit .x-doc>.hero+.layer-banner+.panel{margin-top:0}
.exhibit .x-doc>.panel>.eyebrow{font-size:12px;color:var(--x-quiet);margin-bottom:6px}
.exhibit .x-doc>.panel>h2{font-size:20px;line-height:1.3;letter-spacing:-.015em;max-width:40ch}
.exhibit .x-doc>.panel>h2+p{font-size:15px;line-height:1.6;color:var(--text);margin-top:10px}
.exhibit .x-doc h3{font-size:15px;line-height:1.4;margin:28px 0 8px}
.exhibit .x-doc .panel>p,.exhibit .x-doc .panel>ul,.exhibit .x-doc .panel>ol,.exhibit .x-doc details p,.exhibit .x-doc article p{max-width:var(--x-prose)}
.exhibit .x-doc .panel>p{margin:12px 0;line-height:1.65}
.exhibit .x-doc .panel>p.muted{font-size:13px;color:var(--text-2)}
.exhibit .x-doc .panel>p.muted+.table-wrap{margin-top:8px}
.exhibit .x-doc .panel>p>strong:first-child{color:var(--text)}
.exhibit .x-doc ul,.exhibit .x-doc ol{padding-left:20px}
.exhibit .x-doc li{line-height:1.6}
.exhibit .x-doc>p{max-width:var(--x-prose);margin:16px 0}
.exhibit .x-doc>p.layer-banner{max-width:none;margin:0 0 32px}
.exhibit .x-doc article{padding:20px 0 4px;border-top:1px solid var(--border);margin-top:20px}
.exhibit .x-doc .panel>h2+article,.exhibit .x-doc .panel>h2+p+article{margin-top:16px}
.exhibit .x-doc article>h3{margin:0 0 8px}
.exhibit .x-doc article+article{margin-top:0}
.exhibit .x-doc .memo-grid>article{padding:16px 18px;margin:0;border:1px solid var(--border)}

.exhibit .x-doc .definition-list{margin:16px 0;border-top:1px solid var(--border);border-bottom:1px solid var(--border)}
.exhibit .x-doc .definition-list>div{grid-template-columns:minmax(140px,220px) minmax(0,1fr);gap:24px;padding:10px 0}
.exhibit .x-doc .definition-list dt{color:var(--text);font-weight:500}
.exhibit .x-doc .definition-list dd{color:var(--text-2);line-height:1.6;max-width:var(--x-prose);overflow-wrap:break-word}

/* Tables */
.exhibit .table-wrap{margin:16px 0;border-radius:var(--r-lg)}
.exhibit caption{font-size:12px;line-height:1.5;color:var(--text-2);padding:10px 12px;background:var(--bg);text-align:left}
.exhibit th{font-size:12px;font-weight:500;color:var(--text-2);padding:8px 12px;white-space:normal}
.exhibit td{padding:8px 12px;font-size:13px;line-height:1.5}
.exhibit td.num,.exhibit th.num{padding-left:16px}
.exhibit tbody tr.x-total>td,.exhibit tbody tr.x-total>th{font-weight:600;color:var(--text);background:var(--bg-subtle);border-top:1px solid var(--border-strong)}
.exhibit tbody tr.x-total:hover>td{background:var(--bg-subtle)}
.exhibit td.x-date{white-space:nowrap}
.exhibit td small,.exhibit td .muted{color:var(--x-quiet)}
.exhibit td code{font-size:11px;word-break:break-all}
.exhibit td>p{margin:2px 0 0;font-size:12px;color:var(--x-quiet)}

/* Callouts */
.exhibit .layer-banner,.x-callout{position:relative;padding:12px 16px 12px 40px;border:1px solid var(--border);border-radius:var(--r-lg);background:var(--bg-subtle);color:var(--text-2);font-size:13px;line-height:1.6;margin:0 0 32px}
.exhibit .layer-banner:before,.x-callout:before{content:"i";position:absolute;left:14px;top:13px;width:16px;height:16px;border-radius:50%;border:1px solid var(--text-3);color:var(--text-2);font:600 11px/14px var(--font);text-align:center}
.x-callout.x-limit{background:var(--warn-bg);border-color:var(--warn-line);color:#5f3c05}
.x-callout.x-limit:before{content:"!";border-color:var(--warn);color:var(--warn)}
.x-callout strong{color:inherit}
.exhibit .memo-choice{background:var(--bg-subtle);border:1px solid var(--border);border-radius:var(--r-lg);padding:16px 20px;margin:20px 0}
.exhibit .memo-choice h3{margin:0 0 8px;font-size:15px}
.exhibit .memo-choice p,.exhibit .memo-choice li{max-width:var(--x-prose)}

/* Disclosures */
.exhibit .x-doc details{border:1px solid var(--border);border-radius:var(--r-lg);margin:16px 0;background:var(--bg)}
.exhibit summary{list-style:none;display:flex;align-items:center;gap:10px;padding:10px 14px;min-height:44px;font-size:13px;font-weight:500;color:var(--text);line-height:1.45}
.exhibit summary::-webkit-details-marker{display:none}
.exhibit summary:before{content:"";flex-shrink:0;width:6px;height:6px;border-right:1.5px solid var(--text-3);border-bottom:1.5px solid var(--text-3);transform:rotate(-45deg);margin:0 2px 0 2px;transition:transform .12s}
.exhibit details[open]>summary:before{transform:rotate(45deg);margin-top:-3px}
.exhibit details[open]>summary{border-bottom:1px solid var(--border)}
.exhibit .x-doc details>p,.exhibit .x-doc details>h3,.exhibit .x-doc details>ul,.exhibit .x-doc details>ol,.exhibit .x-doc details>pre{margin:14px 16px}
.exhibit .x-doc details>.table-wrap{margin:14px 16px}
.exhibit .x-doc details>.table-wrap:last-child,.exhibit .x-doc details>p:last-child{margin-bottom:16px}
.exhibit .detail-body,.exhibit .memo-body,.exhibit .details-content{padding:16px;overflow-wrap:anywhere}
.exhibit .detail-body>:first-child,.exhibit .memo-body>:first-child{margin-top:0}
.exhibit .detail-body>:last-child,.exhibit .memo-body>:last-child{margin-bottom:0}
.exhibit .memo-body>p,.exhibit .detail-body>p{margin:10px 0}
.exhibit pre{margin:0;padding:12px 14px;max-height:440px;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere;background:var(--bg-subtle);border:1px solid var(--border);border-radius:var(--r-md);font:12px/1.6 var(--mono);color:var(--text-2)}
.exhibit .x-doc p code,.exhibit .x-doc li code{font-size:11px;word-break:break-all}

/* Links that continue the route */
.exhibit .x-doc a[download]{font-weight:500}
.exhibit .memo-sources{display:flex;flex-wrap:wrap;gap:8px}
.exhibit .memo-sources a{margin:0;display:inline-flex;align-items:center;min-height:32px;padding:4px 10px;border:1px solid var(--border-strong);border-radius:var(--r-md);color:var(--text);font-size:13px;font-weight:500;text-decoration:none}
.exhibit .memo-sources a:hover{background:var(--bg-hover)}

/* Waterfall */
.x-chart{margin:16px 0 4px;padding:16px 20px 12px;border:1px solid var(--border);border-radius:var(--r-lg)}
.x-chart-head{display:flex;justify-content:space-between;align-items:baseline;gap:16px;flex-wrap:wrap;margin-bottom:8px}
.x-chart-title{font-size:13px;font-weight:600;color:var(--text)}
.x-legend{display:flex;gap:14px;flex-wrap:wrap;font-size:12px;color:var(--text-2)}
.x-legend span{display:inline-flex;align-items:center;gap:6px}
.x-legend span:before{content:"";width:10px;height:10px;border-radius:2px;background:var(--x-swatch)}
.exhibit .earnings-waterfall .waterfall-row{grid-template-columns:150px minmax(0,1fr) 72px;gap:16px;margin:0;padding:6px 0;font-size:13px;color:var(--text-2)}
.exhibit .earnings-waterfall .waterfall-row:last-child{border-top:1px solid var(--border);margin-top:6px;padding-top:10px;color:var(--text)}
.exhibit .waterfall-track{height:16px;background:transparent;border-radius:0}
.exhibit .waterfall-bar{height:16px;border-radius:2px}
.exhibit .waterfall-zero{height:24px;top:-4px;border-left:1px solid var(--border-strong)}
.exhibit .waterfall-value{font-variant-numeric:tabular-nums;color:var(--text);white-space:nowrap}

/* Footer */
.exhibit .x-footer{max-width:1296px;padding:20px 32px 32px}
.exhibit .x-footer a{color:var(--text-2)}

@media(max-width:1100px){.exhibit .hero{grid-template-columns:minmax(0,1fr) minmax(240px,300px);gap:32px}}
@media(max-width:900px){
  .exhibit .topbar{position:static;backdrop-filter:none;background:var(--bg)}
  html{scroll-padding-top:16px}
  .exhibit .topbar-inner{padding:8px 20px}
  .exhibit .x-frame>.app-shell{padding:24px 20px 48px}
  .exhibit .x-footer{padding:16px 20px 24px}
}
@media(max-width:760px){
  .exhibit .hero{grid-template-columns:minmax(0,1fr);gap:20px;padding-bottom:24px;margin-bottom:24px}
  .exhibit .hero h1{font-size:26px}
  .exhibit .hero-aside{border-top:1px solid var(--border);padding:14px 16px}
  .exhibit .topbar-inner>.x-provenance{display:none}
  .exhibit .primary-nav{flex-wrap:nowrap;overflow-x:auto;scrollbar-width:none;margin-left:-10px}
  .exhibit .x-provenance+.primary-nav{margin-left:-10px}
  .exhibit td:first-child{min-width:132px}
  .exhibit .x-doc>.panel,.exhibit .x-doc>section.panel{margin-top:32px;padding-top:24px}
  .exhibit .x-doc>.panel>h2{font-size:18px}
  :root{--x-figure:26px}
  .exhibit .table-wrap>table:has(thead th:nth-child(3)){min-width:480px}
  .exhibit .table-wrap>table:has(thead th:nth-child(4)){min-width:560px}
  .exhibit .table-wrap>table:has(thead th:nth-child(6)){min-width:720px}
  .exhibit .table-wrap>table:has(thead th:nth-child(8)){min-width:880px}
  .exhibit .metrics-grid,.exhibit .memo-facts{gap:0;border:1px solid var(--border);border-radius:var(--r-lg);overflow:hidden}
  .exhibit .metrics-grid>.metric-card,.exhibit .memo-facts>div{border:0;border-radius:0;border-bottom:1px solid var(--border)}
  .exhibit .metrics-grid>.metric-card:last-child,.exhibit .memo-facts>div:last-child{border-bottom:0}
  .exhibit .metric-label{margin-bottom:6px}
  .exhibit .metric-note{padding-top:6px}
}
@media(max-width:600px){
  .exhibit .earnings-waterfall .waterfall-row{grid-template-columns:96px minmax(0,1fr) 56px;gap:8px;font-size:12px}
  .x-chart{padding:12px}
}
@media(max-width:420px){
  .exhibit .x-frame>.app-shell{padding:20px 16px 40px}
  .exhibit .topbar-inner{padding-left:16px;padding-right:16px}
  .exhibit .x-footer{padding:16px}
  .exhibit .hero h1{font-size:24px}
  .exhibit .x-doc details>p,.exhibit .x-doc details>h3,.exhibit .x-doc details>ul,.exhibit .x-doc details>ol,.exhibit .x-doc details>pre,.exhibit .x-doc details>.table-wrap{margin-left:12px;margin-right:12px}
  .exhibit .detail-body,.exhibit .memo-body{padding:12px}
}
@media print{
  .x-toc,.exhibit .topbar .primary-nav{display:none!important}
  .exhibit .topbar{position:static}
  .x-frame{display:block}
  .exhibit pre{max-height:none;overflow:visible}
  .exhibit .x-doc>.panel{break-inside:auto}
}
"""

_SECTION = re.compile(
    r"<section class='panel'(?: id='(?P<id>[^']+)')?>(?P<eyebrow><p class='eyebrow'>.*?</p>)?<h2>(?P<title>.*?)</h2>"
)
_TAGS = re.compile(r"<[^>]+>")


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:48] or "section"


def _contents(body: str) -> tuple[str, list[tuple[str, str]]]:
    """Give every top-level section an anchor and return the on-page contents list."""
    entries: list[tuple[str, str]] = []
    used = set(re.findall(r" id='([^']+)'", body))

    def visit(match: re.Match[str]) -> str:
        title = _TAGS.sub("", match["title"]).strip()
        anchor = match["id"]
        if anchor is None:
            anchor, n = "s-" + _slug(title), 2
            while anchor in used:
                anchor, n = f"s-{_slug(title)}-{n}", n + 1
            used.add(anchor)
        entries.append((anchor, title))
        return f"<section class='panel' id='{anchor}'>{match['eyebrow'] or ''}<h2>{match['title']}</h2>"

    return _SECTION.sub(visit, body), entries


def exhibit_page(
    *,
    title: str,
    kind: str,
    nav: list[tuple[str, str]],
    body: str,
    provenance: str | None = None,
    nav_label: str = "Sections",
    home: str = "../index.html",
    extra_css: str = "",
    main_id: str = "main",
    footer: str | None = None,
) -> str:
    """Wrap trusted exhibit markup in the shared report header, contents list and footer.

    ``title``, ``kind``, ``provenance`` and navigation labels are escaped here; ``body`` and ``footer``
    are trusted markup assembled by the renderer from escaped values.
    """
    body, entries = _contents(body)
    links = "".join(f"<a class='nav-link' href='{escape(href, quote=True)}'>{escape(text)}</a>" for href, text in nav)
    badge = f"<span class='x-provenance'>{escape(provenance)}</span>" if provenance else ""
    toc = ""
    if entries:
        toc = (
            "<nav class='x-toc' aria-label='On this page'><p>On this page</p><ol>"
            + "".join(f"<li><a href='#{escape(a, quote=True)}'>{escape(t)}</a></li>" for a, t in entries)
            + "</ol>"
            + (f"<p class='x-toc-meta'>{escape(provenance)}</p>" if provenance else "")
            + "</nav>"
        )
    if footer is None:
        footer = (
            "<div class='footer-line'><p><strong>Value Creation OS</strong> · "
            f"{escape(kind)}</p><p><a href='{escape(home, quote=True)}'>All exhibits</a></p></div>"
        )
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>{escape(title)}</title><style>{CSS}{EXHIBIT_CSS}{extra_css}</style></head><body class='exhibit'>"
        f"<a class='skip-link' href='#{main_id}'>Skip to content</a>"
        "<header class='topbar'><div class='topbar-inner'>"
        f"<a class='brand' href='{escape(home, quote=True)}'>{BRAND_MARK}"
        f"<span class='brand-name'>Value Creation OS<span class='brand-subtitle'>{escape(kind)}</span></span></a>"
        f"{badge}<nav class='primary-nav' aria-label='{escape(nav_label, quote=True)}'>{links}</nav></div></header>"
        f"<div class='x-frame'>{toc}<main id='{main_id}' tabindex='-1' class='app-shell x-doc'>{body}</main></div>"
        f"<footer class='page-footer x-footer'>{footer}</footer></body></html>"
    )

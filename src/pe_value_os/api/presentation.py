"""Shared, dependency-free presentation for the operating partner workspace.

The body passed to :func:`page` is trusted application markup. All helpers escape
their text arguments; callers must escape dynamic content used to build a body.
"""

from __future__ import annotations

import os
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from html import escape
from typing import Any, Literal

CSS = """
@font-face{font-family:"Inter";font-style:normal;font-weight:100 900;font-display:swap;src:url("../assets/fonts/InterVariable-latin.woff2") format("woff2")}
:root{
  color-scheme:light;
  --font:"Inter",ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  --mono:ui-monospace,SFMono-Regular,"Cascadia Mono",Consolas,monospace;
  --bg:#ffffff; --bg-subtle:#fafafa; --bg-muted:#f4f4f5; --bg-hover:#f4f4f5; --bg-active:#ececee;
  --border:#ebebeb; --border-strong:#dfdfe2;
  --text:#171717; --text-2:#52525b; --text-3:#8e8e93;
  --primary:#18181b; --primary-hover:#2c2c30;
  --accent:#2f5bea; --accent-hover:#2349c9; --accent-soft:#eef2fe; --accent-line:#d5defb;
  --ok:#16653a; --ok-bg:#effaf3; --ok-line:#cdebd8;
  --warn:#8a5300; --warn-bg:#fff8eb; --warn-line:#f1dfb6;
  --bad:#b42318; --bad-bg:#fef4f3; --bad-line:#f5d0cb;
  --info:#2349c9; --info-bg:#eef2fe; --info-line:#d5defb;
  --chart-up:#3c9a6b; --chart-down:#d4604f; --chart-total:var(--primary);
  --r-sm:4px; --r-md:6px; --r-lg:8px;
  /* Names kept for renderers that predate the token set. */
  --ink:var(--text); --navy:var(--text); --navy-deep:var(--text); --teal:var(--accent); --teal-light:var(--accent-soft);
  --copper:var(--text-3); --paper:var(--bg); --white:#fff; --muted:var(--text-2); --line:var(--border); --soft:var(--bg-muted);
  --fg:var(--text); --card:var(--bg); --radius:var(--r-lg); --shadow:none;
}
/* app tokens */
:root{
  --side-w:240px; --capture-h:0px; --tabs-h:41px;
  --bar-bg:#18181b; --bar-text:#fafafa; --bar-text-2:#c4c4ca; --bar-line:rgb(255 255 255 / 16%);
  --shadow-sm:0 1px 2px rgb(16 16 20 / 5%); --shadow-panel:0 1px 2px rgb(16 16 20 / 4%),0 6px 20px rgb(16 16 20 / 5%);
}
*{box-sizing:border-box}
html{scroll-behavior:smooth;scroll-padding-top:24px}
body{margin:0;background:var(--bg);color:var(--text);font:14px/1.55 var(--font);font-feature-settings:"cv11","ss01";-webkit-font-smoothing:antialiased}
a{color:var(--accent);text-decoration:underline;text-decoration-color:var(--accent-line);text-underline-offset:3px}
a:hover{color:var(--accent-hover);text-decoration-color:currentColor}
button,input,textarea,select{font:inherit;color:inherit}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:var(--r-sm)}
[tabindex='-1']:focus{outline:none}
::selection{background:var(--accent-soft);color:var(--text)}
h1,h2,h3,h4,p{margin:0}
h1,h2,h3,h4{line-height:1.3;overflow-wrap:break-word;color:var(--text)}
h1{font-size:24px;font-weight:600;letter-spacing:-.015em}
h2{font-size:16px;font-weight:600;letter-spacing:-.005em}
h3{font-size:14px;font-weight:600}
h4{font-size:13px;font-weight:600}
p+p{margin-top:8px}
ul,ol{padding-left:20px;margin:8px 0}li+li{margin-top:4px}
code{font:12px/1.5 var(--mono);overflow-wrap:anywhere;background:var(--bg-muted);padding:1px 4px;border-radius:var(--r-sm);color:var(--text-2)}
small{font-size:12px}
strong{font-weight:600}
svg{display:block;max-width:100%}
.skip-link{position:fixed;top:8px;left:8px;transform:translateY(-200%);z-index:30;background:var(--bg);color:var(--text);padding:8px 12px;border:1px solid var(--border-strong);border-radius:var(--r-md);text-decoration:none}
.skip-link:focus{transform:translateY(0)}

/* Document header used by exhibit pages */
.topbar{background:var(--bg);border-bottom:1px solid var(--border);color:var(--text)}
.topbar-inner{max-width:1200px;margin:auto;min-height:52px;display:flex;align-items:center;gap:24px;padding:8px 32px}
.brand{display:inline-flex;align-items:center;gap:10px;color:var(--text);text-decoration:none;flex-shrink:0;font-weight:600;font-size:14px;min-height:32px}
.brand-mark{width:24px;height:24px;border-radius:var(--r-md);display:grid;place-items:center;background:var(--primary);color:#fff;flex-shrink:0}
.brand-mark svg{width:14px;height:14px}
.brand-name{font-size:14px;font-weight:600;line-height:1.2;letter-spacing:-.01em}
.brand-subtitle{display:block;font-size:12px;color:var(--text-3);font-weight:400;margin-top:1px}
.primary-nav{display:flex;align-items:center;gap:4px;margin-left:auto;flex-wrap:wrap}
.nav-link{color:var(--text-2);text-decoration:none;padding:6px 10px;border-radius:var(--r-md);font-size:13px;font-weight:500;white-space:nowrap}
.nav-link:hover{background:var(--bg-hover);color:var(--text)}
.nav-link[aria-current=page],.nav-link.active{background:var(--bg-active);color:var(--text)}
.workspace-tag{font-size:12px;color:var(--text-3);white-space:nowrap}
.app-shell{width:100%;max-width:1200px;margin:0 auto;padding:24px 32px 48px;min-height:60vh}

/* Page structure */
.eyebrow,.section-kicker{display:block;font-size:12px;font-weight:500;color:var(--text-3);margin-bottom:4px}
.page-title{max-width:900px}
.page-subtitle{color:var(--text-2);font-size:14px;max-width:680px;margin-top:4px}
.section-heading{display:flex;align-items:flex-end;justify-content:space-between;gap:16px;margin:32px 0 12px}
.section-heading p{font-size:13px;color:var(--text-2);margin-top:2px}
.hero{background:var(--bg-subtle);border:1px solid var(--border);border-radius:var(--r-lg);padding:24px;display:grid;grid-template-columns:minmax(0,1.5fr) minmax(240px,.8fr);gap:32px;margin-bottom:24px}
.hero h1,.hero h2{color:var(--text)}.hero p{max-width:680px}
.hero .page-subtitle,.hero .muted{color:var(--text-2)}
.hero-aside{border-left:1px solid var(--border);padding-left:24px;display:flex;flex-direction:column;justify-content:center;gap:12px}
.hero-aside .metric-value{font-size:28px}
.hero-aside.panel{border:1px solid var(--border);padding:20px;margin:0;background:var(--bg)}
.hero .action-list>p{padding:12px 0;border-bottom:1px solid var(--border);color:var(--text-2);font-size:13px}.hero .action-list strong{color:var(--text)}

/* Surfaces */
.panel{background:var(--bg);border:1px solid var(--border);border-radius:var(--r-lg);padding:20px;margin-bottom:16px;min-width:0}
.panel-header{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;margin-bottom:16px;padding-bottom:12px;border-bottom:1px solid var(--border)}
.panel-header p{font-size:13px;color:var(--text-2);margin-top:2px}
.panel>:last-child{margin-bottom:0}
.panel>.section-heading:first-child{margin-top:0}
.two-column{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;align-items:stretch}
.three-column{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;align-items:start}
.stack{display:flex;flex-direction:column;gap:16px}.stack>.panel{margin-bottom:0}
.divider{border:0;border-top:1px solid var(--border);margin:20px 0}

/* Figures */
.metrics-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:0 0 12px}
.metrics-grid+.form-help,.metrics-grid+p{margin:0 0 16px}
.metric-card{background:var(--bg);padding:16px;border:1px solid var(--border);border-radius:var(--r-lg);min-width:0}
.metric-card.highlight{border-color:var(--border)}
.metric-label{display:block;color:var(--text-2);font-size:13px;font-weight:500;line-height:1.4;margin-bottom:6px}
.metric-value{display:block;font-size:28px;font-weight:600;line-height:1.2;letter-spacing:-.02em;font-variant-numeric:tabular-nums;overflow-wrap:anywhere;color:var(--text)}
.metric-value small{display:inline;font-size:13px;font-weight:500;color:var(--text-3);letter-spacing:0;margin-right:4px}
.metric-note{display:block;font-size:12px;color:var(--text-3);line-height:1.5;margin-top:6px}
.metric-comparison{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:16px 0}
.metric-comparison>div{padding-top:10px;border-top:1px solid var(--border)}
.metric-comparison span{display:block;font-size:12px;color:var(--text-3);margin-bottom:4px}
.metric-comparison strong,.metric-comparison .metric-value{font-size:16px;font-weight:600;font-variant-numeric:tabular-nums}
.num,.figure{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.positive{color:var(--ok)}.muted{color:var(--text-2)}.warn{color:var(--warn)}.bad{color:var(--bad)}

/* Badges and tags */
.badge,.pill{display:inline-flex;align-items:center;gap:6px;font-size:12px;line-height:18px;font-weight:500;border:1px solid var(--border-strong);border-radius:var(--r-sm);padding:0 6px;background:var(--bg-muted);color:var(--text-2);max-width:100%;vertical-align:middle;white-space:normal}
.badge[data-status]:before{content:"";width:6px;height:6px;border-radius:50%;background:currentColor;flex-shrink:0}
.state-complete,.state-approved,.state-active,.state-on_track,.state-approval_recorded{color:var(--ok);background:var(--ok-bg);border-color:var(--ok-line)}
.state-awaiting_approval,.state-changes_requested,.state-needs_evidence,.state-revisions_queued{color:var(--warn);background:var(--warn-bg);border-color:var(--warn-line)}
.state-failed,.state-rejected,.state-cancelled,.state-blocked,.state-off_track,.state-rejection_recorded{color:var(--bad);background:var(--bad-bg);border-color:var(--bad-line)}
.state-running,.state-queued,.state-pending{color:var(--info);background:var(--info-bg);border-color:var(--info-line)}

/* Controls */
.button,button{display:inline-flex;align-items:center;justify-content:center;gap:6px;background:var(--primary);border:1px solid var(--primary);color:#fff;text-decoration:none;border-radius:var(--r-md);padding:6px 12px;font-size:13px;line-height:20px;font-weight:500;cursor:pointer;min-height:34px;text-align:center;white-space:nowrap;transition:background .12s,border-color .12s}
.button:hover,button:hover{background:var(--primary-hover);border-color:var(--primary-hover);color:#fff;text-decoration:none}
.button.secondary,button.secondary{background:var(--bg);color:var(--text);border-color:var(--border-strong)}
.button.secondary:hover,button.secondary:hover{background:var(--bg-hover);color:var(--text)}
.button.danger,button.danger{background:var(--bg);color:var(--bad);border-color:var(--bad-line)}
.button.danger:hover,button.danger:hover{background:var(--bad-bg);color:var(--bad)}
button:disabled{opacity:.5;cursor:not-allowed}
.text-link{font-size:13px;font-weight:500;text-decoration:none}.text-link:after{content:" →"}
.text-link:hover{text-decoration:underline}
label{display:block;font-size:13px;font-weight:500;margin:12px 0 6px}
input:not([type=checkbox]):not([type=radio]):not([type=hidden]),textarea,select,.input-field{width:100%;background:var(--bg);color:var(--text);border:1px solid var(--border-strong);border-radius:var(--r-md);padding:7px 10px;min-height:36px;font-size:14px}
input:focus,textarea:focus,select:focus{outline:0;border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft)}
textarea{min-height:96px;resize:vertical;line-height:1.5}
input[type=checkbox],input[type=radio]{accent-color:var(--primary);width:16px;height:16px;vertical-align:middle;margin:0 8px 0 0;flex-shrink:0}
.checkbox-label{display:flex;align-items:flex-start;font-weight:400;gap:6px}
.checkbox-label input{margin-top:3px}.form-help{font-size:12px;color:var(--text-3);margin-top:6px}
.scope-option{display:flex;gap:10px;align-items:flex-start;padding:10px 0;border-bottom:1px solid var(--border);cursor:pointer;font-weight:400;margin:0}
.scope-option input{margin:2px 0}.scope-option small{display:block;color:var(--text-3)}
.decision-actions{display:flex;gap:8px;flex-wrap:wrap;margin:16px 0 8px}

/* Tables */
.table-wrap,.scroll{max-width:100%;overflow-x:auto;overscroll-behavior-x:contain;border:1px solid var(--border);border-radius:var(--r-lg);margin:12px 0;background:var(--bg)}
.data-table,table{width:100%;border-collapse:collapse;font-size:13px;font-variant-numeric:tabular-nums;text-align:left}
caption{caption-side:top;text-align:left;font-size:12px;color:var(--text-3);padding:8px 12px;border-bottom:1px solid var(--border)}
th{color:var(--text-2);font-size:12px;font-weight:500;line-height:1.4;background:var(--bg-subtle);vertical-align:bottom}
th,td{padding:8px 12px;border-bottom:1px solid var(--border);vertical-align:top}
td{line-height:1.5;overflow-wrap:break-word}
tbody th{background:transparent;color:var(--text);font-size:13px;font-weight:500;vertical-align:top}
tbody tr:last-child td,tbody tr:last-child th{border-bottom:0}
tbody tr:hover>td,tbody tr:hover>th{background:var(--bg-subtle)}
td .muted,td small,th small{display:block;font-weight:400;font-size:12px;color:var(--text-3);margin-top:2px;line-height:1.45}
td .badge,th .badge{white-space:nowrap}
tfoot td,tfoot th{background:var(--bg-subtle);border-top:1px solid var(--border);border-bottom:0;font-weight:600;color:var(--text)}
.table-caption{font-size:12px;color:var(--text-3);margin-top:8px}

/* Disclosure */
.disclosure,details{background:var(--bg);border:1px solid var(--border);border-radius:var(--r-lg);margin:12px 0;min-width:0}
summary{font-size:13px;font-weight:500;padding:8px 12px;cursor:pointer;min-height:40px;display:list-item;color:var(--text);line-height:24px}
summary:hover{background:var(--bg-subtle)}
summary::marker{color:var(--text-3)}details[open]>summary{border-bottom:1px solid var(--border)}
.disclosure-body,details>.details-content{padding:16px}
details>.table-wrap{margin:12px}
.disclosure>p,.disclosure>dl,.disclosure>h4,.disclosure>ul,.disclosure>.table-wrap,.disclosure>.scenario-grid,.disclosure>.evidence-links,.disclosure>.timeline-grid{margin:12px 16px}
.technical{font-size:12px;line-height:1.6;color:var(--text-2)}
.technical code{font-size:11px}.technical h3{font-size:13px;color:var(--text);margin-bottom:6px}

/* Bars and scenario figures */
.value-bar,.value-track,.progress-track,.bar-track{height:6px;background:var(--bg-muted);border-radius:3px;overflow:hidden;margin-top:8px}
.value-bar>span,.value-track>span,.progress-fill,.bar-fill{display:block;height:100%;width:var(--value,0%);max-width:100%;background:var(--accent);border-radius:3px}
.bar-fill.negative{background:var(--bad)}
.contribution-row{padding:10px 0;border-bottom:1px solid var(--border);font-size:13px}
.contribution-row:last-of-type{border-bottom:0}.contribution-row .bar-track{margin-top:6px}
.contribution-row>div:first-child{display:flex;justify-content:space-between;gap:16px}
.contribution-row strong{white-space:nowrap;font-variant-numeric:tabular-nums}
.scenario-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}
.scenario,.scenario-card{background:var(--bg);padding:12px;border-radius:var(--r-md);border:1px solid var(--border);min-width:0}
.scenario.base,.scenario-card.base{background:var(--accent-soft);border-color:var(--accent-line)}
.scenario-card .metric-label,.scenario .metric-label{font-size:12px;margin-bottom:2px}
.scenario-card .metric-value,.scenario .metric-value{font-size:16px}
.scenario-card.negative{background:var(--bad-bg);border-color:var(--bad-line)}.scenario-card.negative .metric-value{color:var(--bad)}
.timeline-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:1px;background:var(--border);border:1px solid var(--border);border-radius:var(--r-lg);overflow:hidden;margin:12px 0}
.timeline-stage{background:var(--bg);padding:12px 16px}.timeline-stage h3,.timeline-stage h4{font-size:13px;margin-bottom:4px}.timeline-stage p,.timeline-stage li{font-size:13px;color:var(--text-2)}

/* Lists and key-value data */
.definition-list{margin:12px 0;font-size:13px}
.definition-list>div{display:grid;grid-template-columns:minmax(140px,.6fr) minmax(0,1fr);gap:16px;padding:8px 0;border-bottom:1px solid var(--border)}
.definition-list>div:last-child{border-bottom:0}
.definition-list dt{color:var(--text-2)}.definition-list dd{margin:0;overflow-wrap:anywhere}
.meta-list{margin:0;display:grid;grid-template-columns:minmax(120px,.35fr) minmax(0,1fr);gap:8px 20px;font-size:13px}
.meta-list dt{color:var(--text-2)}.meta-list dd{margin:0;overflow-wrap:anywhere}
.inline-meta,.status-line{display:flex;align-items:center;gap:8px;flex-wrap:wrap;font-size:12px;color:var(--text-3)}
.action-list{list-style:none;padding:0;margin:0}.action-list li{padding:10px 0;border-bottom:1px solid var(--border)}
.action-list li:last-child{border-bottom:0}
.initiative-list{list-style:none;padding:0;margin:0}
.initiative-row{padding:12px 0;display:flex;gap:16px;align-items:center;justify-content:space-between;border-bottom:1px solid var(--border)}
.initiative-row:last-child{border-bottom:0}.initiative-row p{font-size:12px;color:var(--text-3);margin-top:2px}
.initiative-row .metric-value{font-size:16px}.initiative-row .metric-note{margin-top:2px}
.evidence-links{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px}
.evidence-links a,.evidence-link{display:inline-flex;align-items:center;gap:6px;min-height:28px;padding:3px 8px;border:1px solid var(--border-strong);border-radius:var(--r-md);background:var(--bg);color:var(--text-2);font-size:12px;font-weight:500;text-decoration:none;overflow-wrap:anywhere}
.evidence-links a:hover,.evidence-link:hover{background:var(--bg-hover);color:var(--text)}

/* Cards used on overview pages */
.company-card{background:var(--bg);border:1px solid var(--border);border-radius:var(--r-lg);padding:16px;min-width:0;display:flex;flex-direction:column;gap:12px;height:100%}
.card-top{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}
.company-monogram{width:28px;height:28px;display:inline-grid;place-items:center;background:var(--bg-muted);color:var(--text-2);border:1px solid var(--border);border-radius:var(--r-md);font-size:12px;font-weight:600;flex-shrink:0}
.company-card .metric-value{font-size:20px}
.company-card .card-actions{margin-top:auto;border-top:1px solid var(--border);padding-top:12px}
.card-actions{display:flex;gap:12px;align-items:center;flex-wrap:wrap}
.workstream,.workstream-card{border-top:1px solid var(--border)}
.initiative-card{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;border:1px solid var(--border);border-radius:var(--r-lg);padding:12px 16px;margin:8px 0;background:var(--bg)}
.initiative-card h3,.initiative-card h4{font-size:13px;margin-top:4px}.initiative-card>p{font-size:13px;color:var(--text-2);margin-top:4px}
.initiative-values{min-width:150px;text-align:right;flex-shrink:0}.initiative-values strong{display:block;font-size:16px;font-variant-numeric:tabular-nums}.initiative-values span{font-size:12px;color:var(--text-3)}

/* Detail body, shared by exhibits and the application's record panels */
.detail-body{padding:16px}.detail-body>*+*{margin-top:12px}
.detail-body h4{margin-top:16px}

/* Notices and states */
.alert,.warning{padding:12px 16px;border:1px solid var(--warn-line);border-radius:var(--r-lg);background:var(--warn-bg);font-size:13px;line-height:1.55;margin-bottom:16px;color:#5f3c05}
.alert h2,.alert h3,.warning h2,.warning h3{font-size:14px;margin-bottom:4px;color:inherit}
.alert.bad{background:var(--bad-bg);border-color:var(--bad-line);color:var(--bad)}
.notice{padding:10px 14px;border:1px solid var(--border);border-radius:var(--r-lg);background:var(--bg-subtle);font-size:13px;color:var(--text-2);margin-bottom:16px}
.empty-state{padding:32px 24px;border:1px dashed var(--border-strong);border-radius:var(--r-lg);background:var(--bg-subtle);text-align:center;color:var(--text-2)}
.empty-state h2,.empty-state h3{color:var(--text);margin-bottom:8px}.empty-state p{max-width:560px;margin:0 auto}.empty-state>*+*{margin-top:8px}.empty-state>p+p{margin-top:12px}
.decision-grid{display:grid;grid-template-columns:minmax(0,1.5fr) minmax(240px,1fr);gap:24px}
.source-preview{max-width:100%;max-height:620px;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere;padding:16px;background:var(--bg-subtle);border:1px solid var(--border);border-radius:var(--r-lg);font:12px/1.7 var(--mono)}

/* Footer */
.page-footer{border-top:1px solid var(--border);color:var(--text-3);width:100%;max-width:1200px;margin:0 auto;padding:16px 32px 24px;font-size:12px}
.footer-line{display:flex;justify-content:space-between;align-items:flex-start;gap:24px}.footer-line strong{font-weight:600;color:var(--text-2)}
.page-footer details{max-width:820px;background:transparent;border:0;margin:8px 0 0}.page-footer summary{padding:4px 0;font-size:12px;min-height:28px;color:var(--text-2)}.page-footer summary:hover{background:transparent}
.page-footer details[open]>summary{border:0}.page-footer details p{max-width:780px;padding:4px 0}
.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}

@media(max-width:1100px){.metrics-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.three-column{grid-template-columns:repeat(2,minmax(0,1fr))}.hero{gap:24px}}
@media(max-width:900px){
  .topbar-inner{padding:8px 20px;gap:12px}.workspace-tag{display:none}
  .app-shell{padding:20px 20px 40px}.page-footer{padding:16px 20px 24px}
}
@media(max-width:760px){
  .topbar-inner{flex-wrap:wrap;gap:4px 12px;padding-top:8px;padding-bottom:8px}.primary-nav{width:100%;margin-left:-10px;gap:2px}
  .two-column,.three-column,.decision-grid{grid-template-columns:minmax(0,1fr)}
  .hero{grid-template-columns:minmax(0,1fr);padding:20px}.hero-aside{border-left:0;border-top:1px solid var(--border);padding:16px 0 0}
  .metric-comparison{grid-template-columns:repeat(2,minmax(0,1fr))}
  .initiative-card{display:block}.initiative-values{text-align:left;margin-top:8px}
  .footer-line{flex-direction:column;gap:6px}
  .data-table{min-width:560px}
  .button,button,.side-link,.nav-link{min-height:40px}
}
@media(max-width:600px){
  .timeline-grid,.scenario-grid{grid-template-columns:minmax(0,1fr)}
  .definition-list>div,.meta-list{grid-template-columns:minmax(0,1fr);gap:2px}
}
@media(max-width:420px){
  .app-shell{padding:16px 16px 32px}.topbar-inner{padding-left:16px;padding-right:16px}.page-footer{padding:16px}
  .metrics-grid{grid-template-columns:minmax(0,1fr)}.metric-value{font-size:24px}
  .panel{padding:16px}.card-top,.panel-header{flex-wrap:wrap}
  .decision-actions>.button,.decision-actions>button,.card-actions .button{flex-grow:1}
}
/* ------------------------------------------------------------------
   Application screens (workspace shell, record views and forms).
   These classes are used only by server-rendered application pages.
   ------------------------------------------------------------------ */
.app-layout{display:grid;grid-template-columns:var(--side-w) minmax(0,1fr);min-height:calc(100vh - var(--capture-h));background:linear-gradient(90deg,var(--bg-subtle) 0 calc(var(--side-w) - 1px),var(--border) calc(var(--side-w) - 1px) var(--side-w),var(--bg) var(--side-w))}
.sidebar{position:sticky;top:0;align-self:start;height:calc(100vh - var(--capture-h));overflow-y:auto;display:flex;flex-direction:column;min-width:0}
.side-workspace{display:flex;align-items:center;gap:10px;min-height:56px;padding:10px 16px;border-bottom:1px solid var(--border);color:var(--text);text-decoration:none}
.side-workspace:hover{background:var(--bg-hover)}
.side-workspace .brand-mark{width:28px;height:28px;border-radius:7px;box-shadow:inset 0 0 0 1px rgb(255 255 255 / 10%)}
.side-workspace .brand-name{font-size:14px;min-width:0}
.side-workspace .brand-subtitle{font-size:12px;margin-top:0}
.side-nav{display:flex;flex-direction:column;gap:2px;padding:12px 8px}
.side-label{font-size:12px;font-weight:500;color:var(--text-3);padding:0 8px;margin:4px 0 6px}
.side-link{display:flex;align-items:center;gap:10px;min-height:32px;padding:6px 8px;border-radius:var(--r-md);color:var(--text-2);text-decoration:none;font-size:13px;font-weight:500;white-space:nowrap}
.side-link svg{width:16px;height:16px;flex-shrink:0;color:var(--text-3)}
.side-link:hover{background:var(--bg-active);color:var(--text)}
.side-link[aria-current=page]{background:var(--bg);color:var(--text);box-shadow:0 0 0 1px var(--border),var(--shadow-sm)}
.side-link[aria-current=page] svg{color:var(--text)}
.side-foot{margin-top:auto;padding:14px 8px 16px;border-top:1px solid var(--border)}
.side-foot .side-label{margin-top:0}
.side-facts{list-style:none;margin:0;padding:0}
.side-facts li{display:flex;align-items:flex-start;gap:10px;margin:0;padding:4px 8px;font-size:12px;line-height:1.45;color:var(--text-2)}
.side-facts svg{width:14px;height:14px;flex-shrink:0;margin-top:1px;color:var(--text-3)}
.app-main{min-width:0;display:flex;flex-direction:column}
.app-main>.app-shell{flex:1;max-width:1240px;padding:28px 40px 56px}
.app-main>.page-footer{max-width:1240px;padding:16px 40px 24px}
.app-layout.bare{display:flex;flex-direction:column;background:var(--bg-subtle)}
.bare-header{display:flex;align-items:center;min-height:56px;padding:10px 32px;border-bottom:1px solid var(--border);background:var(--bg)}
.bare .app-main{flex:1}
.bare .app-main>.app-shell{max-width:1120px;padding-top:56px}

/* Capture provenance bar (static captures only) */
body:has(.capture-bar){--capture-h:40px}
.capture-bar{display:flex;align-items:center;justify-content:space-between;gap:6px 24px;flex-wrap:wrap;min-height:40px;padding:7px 24px;background:var(--bar-bg);color:var(--bar-text-2);font-size:12px;line-height:1.5}
.capture-facts{display:flex;flex-wrap:wrap;align-items:center;margin:0;min-width:0}
.capture-facts>span{display:inline-flex;align-items:center}
.capture-facts>span+span:before{content:"";width:3px;height:3px;border-radius:50%;background:var(--bar-text-2);margin:0 10px;opacity:.7}
.capture-facts strong{color:var(--bar-text);font-weight:600}
.capture-facts svg{width:14px;height:14px;margin-right:8px;color:var(--bar-text)}
.capture-links{display:flex;gap:6px;flex-shrink:0}
.capture-links a{display:inline-flex;align-items:center;min-height:26px;padding:2px 10px;border:1px solid var(--bar-line);border-radius:var(--r-md);color:var(--bar-text);font-weight:500;text-decoration:none}
.capture-links a:hover{background:rgb(255 255 255 / 8%);color:var(--bar-text)}
.capture-bar a:focus-visible{outline-color:var(--bar-text)}

/* Page header: breadcrumb, title, status and right-aligned actions */
.breadcrumb{display:flex;gap:6px;align-items:center;flex-wrap:wrap;font-size:13px;color:var(--text-3);margin:0 0 14px}
.breadcrumb a{color:var(--text-2);text-decoration:none;border-radius:var(--r-sm)}.breadcrumb a:hover{color:var(--text)}
.breadcrumb [aria-current]{color:var(--text)}
.breadcrumb .sep{color:var(--border-strong)}
.page-header{margin:0 0 28px;padding:0 0 20px;border-bottom:1px solid var(--border)}
.page-header.has-tabs{border-bottom:0;margin-bottom:0;padding-bottom:16px}
.page-header-row{display:flex;align-items:flex-start;justify-content:space-between;gap:16px 24px}
.page-heading{display:flex;align-items:flex-start;gap:14px;min-width:0}
.page-heading>div{min-width:0}
.page-icon{width:40px;height:40px;display:grid;place-items:center;flex-shrink:0;border:1px solid var(--border);border-radius:10px;background:var(--bg-subtle);color:var(--text-2);box-shadow:var(--shadow-sm)}
.page-icon svg{width:20px;height:20px}
.page-title-row{display:flex;align-items:center;flex-wrap:wrap;gap:6px 12px}
.page-header .page-title{font-size:24px;line-height:1.25}
.page-header .page-subtitle{margin-top:4px}
.page-actions{display:flex;align-items:center;gap:8px;flex-wrap:wrap;flex-shrink:0}
.page-meta{display:flex;flex-wrap:wrap;gap:6px 20px;margin-top:14px;font-size:12px;color:var(--text-3)}
.page-meta>span{display:inline-flex;align-items:center;white-space:pre-wrap}
.page-meta svg{width:14px;height:14px;flex-shrink:0;margin-right:6px}
.page-meta strong{font-weight:500;color:var(--text-2)}
.count{display:inline-flex;align-items:center;justify-content:center;min-width:22px;height:20px;padding:0 7px;border-radius:10px;background:var(--bg-muted);border:1px solid var(--border);color:var(--text-2);font-size:12px;font-weight:500;font-variant-numeric:tabular-nums;line-height:1}
.button .count{background:var(--bg-muted);border-color:var(--border);height:18px;min-width:20px}

/* Section tabs (sticky on long records) */
.section-nav{position:sticky;top:0;z-index:6;display:flex;gap:24px;margin:0 0 28px;background:var(--bg);border-bottom:1px solid var(--border);overflow-x:auto;scrollbar-width:none}
.section-nav::-webkit-scrollbar{display:none}
.section-nav a{display:inline-flex;align-items:center;gap:6px;min-height:40px;padding:0 1px;border-bottom:2px solid transparent;color:var(--text-2);font-size:13px;font-weight:500;text-decoration:none;white-space:nowrap}
.section-nav a svg{width:15px;height:15px;color:var(--text-3)}
.section-nav a:hover{color:var(--text);border-bottom-color:var(--border-strong)}
.section-nav a:focus-visible{outline-offset:-2px}
.app-shell:not(:has(:target)) .section-nav a[href='#executive'],.app-shell:has(#executive:target) .section-nav a[href='#executive'],
.app-shell:has(#workstreams:target) .section-nav a[href='#workstreams'],.app-shell:has(#evidence:target,.detail-panel:target) .section-nav a[href='#evidence'],
.app-shell:has(#decision:target) .section-nav a[href='#decision']{color:var(--text);border-bottom-color:var(--text)}
html:has(.section-nav){scroll-padding-top:calc(var(--tabs-h) + 24px)}

/* Section titles inside application screens */
.block-head{display:flex;align-items:flex-end;justify-content:space-between;gap:12px 16px;flex-wrap:wrap;margin:40px 0 14px}
.block-head>div{min-width:0}
.block-head h2{font-size:16px}
.block-head p{font-size:13px;color:var(--text-2);margin-top:2px}
.block-head .eyebrow{margin-bottom:2px}
.page-header+section>.block-head:first-child,.section-nav+section>.block-head:first-child{margin-top:0}

/* Headline figures (Mercury-style summary strip) */
.summary-strip{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:1px;background:var(--border);border:1px solid var(--border);border-radius:var(--r-lg);overflow:hidden;margin:0 0 10px}
.summary-strip:has(.lead){grid-template-columns:minmax(0,1.4fr) repeat(3,minmax(0,1fr))}
.summary-strip.cols-3{grid-template-columns:repeat(3,minmax(0,1fr))}
.summary-item{background:var(--bg);padding:20px 24px 22px;min-width:0}
.summary-item .metric-label{display:flex;align-items:center;gap:8px;font-size:13px;font-weight:500;color:var(--text-2);margin:0 0 12px}
.summary-item .metric-label svg{width:15px;height:15px;color:var(--text-3);flex-shrink:0}
.summary-item .metric-value{font-size:32px;line-height:1.1;font-weight:600;letter-spacing:-.025em}
.summary-item .metric-value small{font-size:14px;font-weight:500;color:var(--text-3);letter-spacing:0;margin-right:6px;vertical-align:4px}
.summary-item .metric-value .unit{font-size:20px;font-weight:500;color:var(--text-2);letter-spacing:-.01em;margin-left:1px}
.summary-item .metric-value+.metric-value{margin-top:10px}
.summary-item .metric-note{margin-top:10px;color:var(--text-3)}
.summary-item p:not([class]){font-size:13px;color:var(--text-2);margin-top:6px}
.summary-foot{font-size:12px;color:var(--text-3);margin:0 0 8px;max-width:920px}

/* Table card: toolbar above a flush table (Attio-style) */
.table-card{border:1px solid var(--border);border-radius:var(--r-lg);background:var(--bg);overflow:hidden;min-width:0}
.table-card>.table-wrap{border:0;border-radius:0;margin:0}
.table-toolbar{display:flex;align-items:center;justify-content:space-between;gap:8px 16px;flex-wrap:wrap;min-height:48px;padding:8px 16px;border-bottom:1px solid var(--border)}
.toolbar-title{display:flex;align-items:center;gap:8px;min-width:0}
.toolbar-title h2,.toolbar-title h3{font-size:14px;font-weight:600}
.toolbar-title svg{width:16px;height:16px;color:var(--text-3)}
.toolbar-meta{display:flex;align-items:center;gap:6px 12px;flex-wrap:wrap;font-size:12px;color:var(--text-3)}
.th-label{display:inline-flex;align-items:center;gap:6px;white-space:nowrap}
.th-label svg{width:14px;height:14px;flex-shrink:0;color:var(--text-3)}
.app-shell svg,.sidebar svg,.capture-bar svg{flex-shrink:0}
.portfolio-block{margin-top:28px}
.company-table thead th{padding:9px 14px;vertical-align:middle}
.company-table tbody th,.company-table tbody td{padding:14px}
.company-table>thead>tr>*+*,.company-table>tbody>tr>*+*{border-left:1px solid var(--border)}
.company-table th[scope=row]{min-width:250px;max-width:380px}
.company-table td.num small{white-space:normal}
.company-table .col-lever{min-width:150px}
.company-table td .badge{margin-top:1px}
.entity{display:flex;align-items:flex-start;gap:12px;min-width:0}
.entity>div{min-width:0}
.entity-name{display:block;font-size:14px;font-weight:600;color:var(--text);line-height:1.35}
.entity .company-monogram{width:32px;height:32px;border-radius:8px;background:var(--bg);box-shadow:var(--shadow-sm);color:var(--text);font-size:12px}
.figure-lg{display:block;font-size:15px;font-weight:600;color:var(--text);font-variant-numeric:tabular-nums}
.figure-lg .ccy{font-size:12px;font-weight:500;color:var(--text-3);margin-right:4px}
.row-actions{display:flex;flex-direction:column;align-items:flex-start;gap:8px;white-space:nowrap}
.row-actions .row-link{display:inline-flex;align-items:center;gap:6px;min-height:30px;padding:4px 10px;border:1px solid var(--border-strong);border-radius:var(--r-md);background:var(--bg);box-shadow:var(--shadow-sm);color:var(--text);font-size:12px;font-weight:500;text-decoration:none}
.row-actions .row-link:hover{background:var(--bg-hover)}
.row-actions .row-link svg{width:14px;height:14px;color:var(--text-3)}
.row-actions .text-link{font-size:12px}

/* Decision desk */
.desk{padding:0;overflow:hidden;margin-top:32px}
.desk-list{list-style:none;margin:0;padding:0}
.desk-row{display:flex;align-items:center;gap:12px 14px;margin:0;padding:14px 16px;border-bottom:1px solid var(--border)}
.desk-row:last-child{border-bottom:0}
.desk-main{flex:1;min-width:0}
.desk-main strong{display:block;font-size:14px}
.desk-main .inline-meta{margin-top:4px}
.desk-row .button{flex-shrink:0}
.desk-empty{display:flex;align-items:center;gap:12px;padding:20px 16px;color:var(--text-2);font-size:13px}
.desk-empty svg{width:18px;height:18px;color:var(--ok);flex-shrink:0}

/* Record cards (workstreams, KPIs): header, flush table, flush disclosures */
.record-card.panel{padding:0;overflow:hidden;margin:0}
.record-head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px 16px;padding:16px 20px}
.record-head>div{min-width:0}
.record-head h3{font-size:15px;margin-top:2px}
.record-title{display:flex;align-items:flex-start;gap:12px;min-width:0}
.record-num{width:28px;height:28px;display:grid;place-items:center;flex-shrink:0;border-radius:7px;background:var(--bg-muted);border:1px solid var(--border);font-size:12px;font-weight:600;color:var(--text-2);font-variant-numeric:tabular-nums}
.record-sub{display:flex;align-items:center;flex-wrap:wrap;gap:4px 12px;font-size:12px;color:var(--text-3);margin-top:3px}
.record-sub>span{display:inline-flex;align-items:center;white-space:pre-wrap}
.record-sub svg{width:13px;height:13px;margin-right:5px}
.record-card>.table-wrap{margin:0;border:0;border-top:1px solid var(--border);border-radius:0}
.record-card>.alert{margin:0;border-radius:0;border-width:1px 0 0}
.record-card>.alert ul{margin-bottom:0}
.record-card>details{margin:0;border:0;border-top:1px solid var(--border);border-radius:0}
.record-card>details>summary{padding:10px 20px}
.record-card>details>.timeline-grid{margin:16px 20px}
.record-card>details>.table-wrap{margin:16px 20px}
.record-card>details>ul,.record-card>details>p,.record-card>details>.evidence-links{margin:14px 20px}
.record-card tfoot th,.record-card tfoot td{background:var(--bg-subtle)}
.record-card>.table-wrap :is(th,td):first-child{padding-left:20px}
.record-card>.table-wrap :is(th,td):last-child{padding-right:20px}
.record-card>p,.record-card>.form-help{margin:12px 20px;font-size:13px}
.record-card>.record-head+p{margin-top:0}
.record-card>p:last-child{margin-bottom:16px}
.record-card>ul{margin:0;padding:14px 20px 16px 40px;border-top:1px solid var(--border);font-size:13px;color:var(--text-2)}
.record-card>ul li+li{margin-top:8px}
.record-head h2{font-size:15px}
.record-head>div>.record-sub{display:block;font-size:13px;color:var(--text-2)}
.record-num svg{width:15px;height:15px}
.record-num.warn{background:var(--warn-bg);border-color:var(--warn-line);color:var(--warn)}
.empty-state>.page-icon{margin:0 auto 12px;background:var(--bg)}
.private-review p,.private-review td{overflow-wrap:anywhere}
.app-shell>section.alert,.app-shell>.gap-card{margin-top:24px}
.app-shell>.gap-card h2{font-size:15px}
.stack.records{gap:16px}

/* Two-panel brief */
.brief-grid{display:grid;grid-template-columns:minmax(0,1.1fr) minmax(0,1fr);gap:16px;margin-top:16px}
.brief-grid>.panel{margin:0;padding:0}
.brief-grid .brief-head{padding:16px 20px;border-bottom:1px solid var(--border)}
.brief-grid .brief-head h3{font-size:14px}
.brief-grid .brief-head .eyebrow{margin-bottom:2px}
.brief-grid .brief-body{padding:8px 20px 18px}
.brief-body>ul{padding-left:18px;font-size:13px}.brief-body>ul li+li{margin-top:8px}
.brief-body>p{margin-top:10px}.brief-body>p:not([class]){font-size:13px;color:var(--text-2)}
.brief-body .contribution-row{padding:12px 0}

/* Master-detail: value case list with one selected record panel */
.split{display:grid;grid-template-columns:minmax(0,1fr) minmax(340px,420px);gap:20px;align-items:start}
.split>.table-card{position:relative}
.detail-stack{position:sticky;top:calc(var(--tabs-h) + 16px);min-width:0}
.detail-panel{display:none;background:var(--bg);border:1px solid var(--border);border-radius:var(--r-lg);min-width:0;box-shadow:var(--shadow-panel)}
.detail-panel:target,.detail-stack:not(:has(.detail-panel:target))>.detail-panel:first-child{display:block}
.detail-head{padding:18px 20px 16px;border-bottom:1px solid var(--border)}
.detail-kicker{display:flex;align-items:center;gap:8px;font-size:12px;font-weight:500;color:var(--text-3)}
.record-icon{width:24px;height:24px;display:grid;place-items:center;flex-shrink:0;border-radius:6px;background:var(--accent-soft);color:var(--accent)}
.record-icon svg{width:14px;height:14px}
.detail-head h3{font-size:16px;line-height:1.35;margin-top:10px}
.detail-tags{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}
.detail-panel .detail-body{padding:0}
.detail-panel .detail-body>*+*{margin-top:0}
.detail-lede{padding:16px 20px 0;font-size:13px;color:var(--text-2)}
.detail-section{padding:16px 20px}
.detail-section+.detail-section{border-top:1px solid var(--border)}
.detail-lede+.detail-section{padding-top:14px}
.detail-section>h4{font-size:12px;font-weight:500;color:var(--text-3);margin:0 0 10px}
.detail-section>*+*:not(h4+*){margin-top:10px}
.detail-section .table-wrap{margin:10px 0 0}
.detail-section>ul{font-size:13px;color:var(--text-2)}
.detail-panel .definition-list{margin:0}
.detail-panel .definition-list>div{grid-template-columns:minmax(0,1fr) auto;padding:7px 0}
.detail-panel .definition-list dd{text-align:right;font-variant-numeric:tabular-nums;font-weight:500;color:var(--text)}
.detail-foot{padding:12px 20px;border-top:1px solid var(--border);background:var(--bg-subtle);font-size:12px;color:var(--text-3);border-radius:0 0 var(--r-lg) var(--r-lg)}
.case-table tbody tr{position:relative}
.case-table tbody th,.case-table tbody td{padding:12px 14px;vertical-align:middle}
.case-table thead th{padding:9px 14px;vertical-align:middle}
.case-table .row-link{color:var(--text);font-weight:500;text-decoration:none}
.case-table .row-link:after{content:"";position:absolute;inset:0}
.case-table .row-link:focus-visible{outline:0}
.case-table tr:has(.row-link:focus-visible){outline:2px solid var(--accent);outline-offset:-2px}
.case-table tbody tr:hover>*{background:var(--bg-subtle)}
.case-table tbody tr:hover .row-link{color:var(--accent-hover)}
.case-table .row-chevron{width:36px;padding-left:0;padding-right:12px;color:var(--text-3)}
.case-table .row-chevron svg{width:16px;height:16px}
tr.is-outside>td,tr.is-outside>th,tr.is-outside .row-link{color:var(--text-3)}
.case-table tr.is-selected>*{background:var(--accent-soft)}

/* Decision panel: an enterprise form with header, body and action bar */
.decision-panel{padding:0;margin-top:40px;border:1px solid var(--border-strong);border-radius:var(--r-lg);background:var(--bg);box-shadow:var(--shadow-sm);overflow:hidden}
.decision-head{display:flex;gap:14px;align-items:flex-start;padding:20px 24px;border-bottom:1px solid var(--border)}
.decision-head>div{min-width:0}
.decision-head h2{font-size:16px;margin:0}
.decision-head p:not(.eyebrow){font-size:13px;color:var(--text-2);margin-top:4px;max-width:720px}
.decision-panel>.alert{margin:16px 24px 0}
.decision-panel>.decision-record{padding:18px 24px 22px}
.decision-record>*+*{margin-top:8px}
.decision-record .inline-meta{font-size:13px;color:var(--text-2)}
.decision-panel form,.decision-panel fieldset{margin:0;padding:0;border:0;min-width:0}
.decision-panel fieldset[disabled]>legend{float:left;margin:16px 24px 0;padding:2px 8px;border:1px solid var(--border-strong);border-radius:var(--r-sm);background:var(--bg-muted);font-size:12px;font-weight:500;color:var(--text-2)}
.decision-panel fieldset[disabled]>legend+*{clear:both}
.decision-body{padding:4px 24px 20px}
.decision-body>details{margin:16px 0 0}
.decision-body>details>p{margin:12px 16px 4px;font-size:13px;color:var(--text-2)}
.decision-body .scope-option{display:flex;align-items:center;gap:12px;margin:0;padding:10px 16px;border-top:1px solid var(--border);border-bottom:0}
.decision-body .scope-option>span{flex:1;display:flex;justify-content:space-between;align-items:baseline;gap:4px 16px;flex-wrap:wrap}
.decision-body .scope-option small{display:inline;color:var(--text-3);font-variant-numeric:tabular-nums;white-space:nowrap}
.decision-body .scope-option:hover{background:var(--bg-subtle)}
.field{margin-top:18px}
.field>label{margin:0 0 4px;font-size:13px;font-weight:500}
.field>.form-help{margin:0 0 8px}
.field textarea{min-height:112px}
.decision-actions{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin:0;padding:14px 24px;border-top:1px solid var(--border);background:var(--bg-subtle)}
.decision-actions .form-help{margin:0 0 0 auto;max-width:440px}
.decision-panel fieldset[disabled] button{opacity:.55}

/* Operating scorecard */
.kpi-card .metric-comparison{grid-template-columns:repeat(4,minmax(0,1fr));gap:1px;margin:0;background:var(--border);border-top:1px solid var(--border);border-bottom:1px solid var(--border)}
.kpi-card .metric-comparison>div{background:var(--bg);padding:14px 20px;border-top:0}
.kpi-card .metric-comparison .metric-label{font-size:12px;color:var(--text-3);margin-bottom:6px}
.kpi-card .metric-comparison .metric-value{font-size:18px;letter-spacing:-.01em}
.kpi-progress{padding:14px 20px 16px}
.kpi-progress>*+*{margin-top:8px}
.kpi-progress .progress-track{height:8px;border-radius:4px;margin-top:0}
.kpi-progress .metric-note{margin-top:8px}
.kpi-progress>.empty-state{text-align:left;padding:14px 16px;border-style:solid;font-size:13px}

/* Evidence viewer */
.file-card{border:1px solid var(--border);border-radius:var(--r-lg);overflow:hidden;background:var(--bg)}
.file-card>.form-help{margin:0;padding:10px 16px;border-bottom:1px solid var(--border);background:var(--bg-subtle)}
.file-card>.table-wrap{margin:0;border:0;border-radius:0}
.file-card>.source-preview{margin:0;border:0;border-radius:0;background:var(--bg);max-height:640px}
.file-card caption{background:var(--bg)}

/* Private review workspace */
.status-card{min-width:240px;max-width:340px;padding:14px 16px;border:1px solid var(--border);border-radius:var(--r-lg);background:var(--bg-subtle)}
.status-card .metric-label{font-size:12px;color:var(--text-3);margin:0}
.status-card h2{font-size:15px;margin-top:4px}
.status-card p{font-size:12px;color:var(--text-2);margin-top:6px}
.review-list{list-style:none;margin:0;padding:0}
.review-row{display:grid;grid-template-columns:minmax(0,1.4fr) minmax(0,1fr) minmax(0,1fr) auto;align-items:center;gap:8px 20px;margin:0;padding:14px 16px;border-top:1px solid var(--border)}
.review-row:first-child{border-top:0}
.review-row p{font-size:13px;color:var(--text-2);margin:0}
.review-row .entity-name{font-size:14px}
.private-review .decision-body>fieldset{margin-top:20px;padding:4px 16px 16px;border:1px solid var(--border);border-radius:var(--r-lg)}
.private-review .decision-body>fieldset>legend{padding:0 6px;font-size:13px;font-weight:600}
.private-review .decision-body label{margin:14px 0 6px}
.private-review .decision-body>label:first-child{margin-top:16px}

/* Sign-in */
.login-layout{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(320px,420px);gap:64px;align-items:start}
.login-intro .page-title{font-size:32px;line-height:1.2;letter-spacing:-.02em;margin-top:4px}
.login-intro .page-subtitle{font-size:15px;margin-top:12px;max-width:560px}
.login-steps{list-style:none;padding:0;margin:32px 0 0;border-top:1px solid var(--border)}
.login-steps li{display:flex;gap:14px;margin:0;padding:16px 0;border-bottom:1px solid var(--border)}
.login-steps strong{display:block;font-size:14px}
.login-steps p{font-size:13px;color:var(--text-2);margin-top:2px}
.step-num{width:28px;height:28px;display:grid;place-items:center;flex-shrink:0;border-radius:7px;border:1px solid var(--border);background:var(--bg);font-size:12px;font-weight:600;color:var(--text-2);font-variant-numeric:tabular-nums}
.login-card{background:var(--bg);border:1px solid var(--border);border-radius:12px;box-shadow:var(--shadow-panel);overflow:hidden}
.login-card-head{padding:24px 24px 0}
.login-card-head .page-icon{margin-bottom:16px}
.login-card-head h2{font-size:18px;margin-top:2px}
.login-card-head .muted{font-size:13px;margin-top:6px}
.login-card form{padding:4px 24px 24px;gap:0}
.login-card form label{margin:20px 0 6px}
.login-card form .button{width:100%;margin-top:16px;min-height:40px}
.login-card .alert{margin:16px 24px 0}
.login-note{padding:14px 24px;border-top:1px solid var(--border);background:var(--bg-subtle);font-size:12px;color:var(--text-3);margin:0}

/* Error and status pages */
.status-page{max-width:520px;margin:48px auto;padding:40px 32px;text-align:center;border:1px solid var(--border);border-radius:12px;background:var(--bg);box-shadow:var(--shadow-sm)}
.status-page .page-icon{margin:0 auto 18px}
.status-page h1{font-size:22px;margin-top:4px}
.status-page p:not(.eyebrow){color:var(--text-2);margin-top:8px}
.status-page .page-actions{justify-content:center;margin-top:24px}

@media(max-width:1100px){
  .split{grid-template-columns:minmax(0,1fr)}.detail-stack{position:static}
  .summary-strip,.summary-strip:has(.lead){grid-template-columns:repeat(2,minmax(0,1fr))}
  .summary-strip.cols-3{grid-template-columns:repeat(3,minmax(0,1fr))}
  .review-row{grid-template-columns:minmax(0,1fr) minmax(0,1fr);}
}
@media(max-width:900px){
  .app-layout{display:block;background:var(--bg)}
  .sidebar{position:static;height:auto;overflow:visible;background:var(--bg-subtle);border-bottom:1px solid var(--border)}
  .side-workspace{min-height:52px;padding:8px 16px}
  .side-nav{flex-direction:row;gap:4px;padding:6px 12px 8px;overflow-x:auto;scrollbar-width:none}
  .side-nav::-webkit-scrollbar{display:none}
  .side-label,.side-foot{display:none}
  .app-main>.app-shell{padding:20px 20px 40px}.app-main>.page-footer{padding:16px 20px 24px}
  .bare .app-main>.app-shell{padding-top:32px}
  .bare-header{padding:8px 20px}
  .brief-grid,.login-layout{grid-template-columns:minmax(0,1fr)}
  .login-layout{gap:32px}.login-card{order:-1}
  .kpi-card .metric-comparison{grid-template-columns:repeat(2,minmax(0,1fr))}
  .capture-bar{padding:8px 20px}
}
@media(max-width:760px){
  .page-header-row{flex-direction:column}
  .page-actions{width:100%}
  .summary-strip.cols-3{grid-template-columns:minmax(0,1fr)}
  .status-card{max-width:none;width:100%}
  .review-row{grid-template-columns:minmax(0,1fr)}
  .decision-head,.decision-body,.decision-actions{padding-left:16px;padding-right:16px}
  .decision-panel>.alert{margin-left:16px;margin-right:16px}
  .decision-actions .form-help{margin:4px 0 0;max-width:none;flex-basis:100%}
  .desk-row{flex-wrap:wrap}.desk-row .button{margin-left:44px}
  .login-intro .page-title{font-size:26px}
  .side-link{min-height:36px}
}
@media(max-width:600px){
  .page-heading>.page-icon{display:none}
  .stack-table.data-table{min-width:0}
  .stack-table thead{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}
  .stack-table,.stack-table tbody,.stack-table tfoot,.stack-table tr,.stack-table tbody th,.stack-table tfoot th,.stack-table td{display:block}
  .stack-table tbody tr,.stack-table tfoot tr{padding:12px 16px;border-bottom:1px solid var(--border)}
  .stack-table tbody tr:last-child{border-bottom:0}
  .stack-table tfoot tr{border-top:1px solid var(--border);border-bottom:0;background:var(--bg-subtle)}
  .stack-table tbody th,.stack-table tfoot th,.stack-table td{padding:0;border:0!important;min-width:0;max-width:none;background:transparent!important}
  .stack-table tbody th,.stack-table tfoot th{padding-bottom:8px}
  .stack-table td{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;padding:6px 0;border-top:1px solid var(--border)!important;text-align:right;white-space:normal}
  .stack-table td:before{content:attr(data-label);flex-shrink:0;font-size:12px;font-weight:400;color:var(--text-3);text-align:left}
  .company-table tbody tr{padding:14px 16px}
  .company-table .row-actions{align-items:flex-end}
  .case-table.data-table{min-width:0}
  .case-table .row-chevron{display:none}
  .case-table thead{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}
  .case-table,.case-table tbody{display:block}
  .case-table tbody tr{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;border-bottom:1px solid var(--border)}
  .case-table tbody tr:last-child{border-bottom:0}
  .case-table tbody th{grid-column:1/-1;padding:12px 16px 6px;border:0}
  .case-table tbody td{padding:0 16px 12px;border:0}
  .case-table tbody td.num{padding-left:0}
  .detail-panel .scenario-grid{grid-template-columns:repeat(3,minmax(0,1fr))}
  .detail-panel .scenario-card{padding:10px}
  .detail-panel .definition-list>div{grid-template-columns:minmax(0,1fr) auto}
  .record-head{flex-wrap:wrap;padding:14px 16px}
  .record-card>details>summary{padding:10px 16px}
  .detail-section,.detail-head,.detail-foot{padding-left:16px;padding-right:16px}.detail-lede{padding:14px 16px 0}
}
@media(max-width:420px){
  .app-main>.app-shell{padding:16px 16px 32px}.app-main>.page-footer{padding:16px}
  .summary-strip,.summary-strip:has(.lead){grid-template-columns:minmax(0,1fr)}
  .summary-item{padding:16px 18px}
  .summary-item .metric-value{font-size:28px}
  .page-header .page-title{font-size:22px}
  .page-icon{width:36px;height:36px}
  .capture-bar{padding:8px 16px}
  .status-page{padding:32px 20px;margin-top:24px}
  .decision-actions>button,.decision-actions>.button{flex-grow:1}
}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}*,*:before,*:after{transition:none!important;animation:none!important}}
@media print{
  body{font-size:10pt}.sidebar,.primary-nav,.workspace-tag,.skip-link,form,.card-actions,.section-nav,.decision-panel button{display:none!important}
  .app-layout{display:block}.app-shell{max-width:none;padding:16px 0}.topbar{border-bottom:1px solid #999}
  .panel,.metric-card,.decision-panel,.detail-panel{break-inside:avoid;border-color:#bbb;box-shadow:none}.detail-panel{display:block!important}
  .table-wrap{overflow:visible}table,.data-table{min-width:0;font-size:9pt}th,td{padding:5px}a{color:#111}details{break-inside:avoid}
  .badge{border-color:#999;color:#111;background:#fff}h1{font-size:18pt}.metric-value{font-size:16pt}
}
"""


def money(value: Any, *, compact: bool = False) -> str:
    """Format financial units without asserting an unspecified currency.

    Full amounts of 1,000 or more display in whole units; smaller amounts keep two decimal places
    unless they are whole. Compact amounts always carry one decimal place, are deliberately
    approximate, and should be paired with a full figure for decision making.
    """
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return escape(str(value))
    if not amount.is_finite():
        return "Not available"
    if compact and abs(amount) >= 1000:
        for scale, suffix in ((Decimal("1e9"), "bn"), (Decimal("1e6"), "m"), (Decimal("1e3"), "k")):
            scaled = (amount / scale).quantize(Decimal("0.1"), ROUND_HALF_UP)
            if abs(scaled) >= 1:  # choose the scale after rounding, so 999,950 reads 1.0m, not 1,000.0k
                return f"{scaled:,.1f}{suffix}"
    cents = amount.quantize(Decimal("0.01"), ROUND_HALF_UP)
    if abs(cents) >= 1000 or cents == cents.to_integral_value():
        whole = amount.quantize(Decimal(1), ROUND_HALF_UP)
        return f"{abs(whole) if whole == 0 else whole:,.0f}"
    return f"{abs(cents) if cents == 0 else cents:,.2f}"


def label(value: str) -> str:
    """Render readable, escaped enum or identifier text."""
    replacements = {
        "awaiting_approval": "Awaiting decision",
        "needs_evidence": "Evidence required",
        "changes_requested": "Changes requested",
        "complete": "Complete",
        "quick_win": "Quick win",
        "in_progress": "In progress",
        "ai_and_automation": "AI and automation",
        "gtm_efficiency": "Go-to-market efficiency",
    }
    if value in replacements:
        return escape(replacements[value])
    words = f" {value.replace('_', ' ').replace('-', ' ').replace(':', ': ')} ".replace(" s and m ", " S&M ").split()
    readable = " ".join(_WORDS.get(w.lower(), w.lower()) for w in words)
    return escape(readable[:1].upper() + readable[1:])


# Abbreviations that stay upper case (or take their usual form) when an identifier is shown as text.
_WORDS = {
    **{w: w.upper() for w in ("ai", "arr", "mrr", "nrr", "grr", "acv", "arpa", "cac", "ltv", "ebitda", "kpi", "sla")},
    **{w: w.upper() for w in ("csat", "nps", "gtm", "mfn", "sku")},
    "s&m": "S&M",
    **{w: w.upper() for w in ("cogs", "fte", "api", "g&a", "r&d")},
    "saas": "SaaS",
    "pct": "%",
    "tier1": "tier-1",
    "tier2": "tier-2",
}


def status_badge(value: str) -> str:
    """Return an escaped status badge; arbitrary status text cannot affect CSS."""
    states = {
        "complete",
        "approved",
        "active",
        "awaiting_approval",
        "changes_requested",
        "needs_evidence",
        "failed",
        "rejected",
        "cancelled",
        "blocked",
        "running",
        "queued",
        "pending",
        "on_track",
        "off_track",
    }
    state = value if value in states else "neutral"
    return f"<span class='badge state-{state}' data-status='{escape(value)}'>{label(value)}</span>"


ERROR_PAGES = {
    401: ("Sign in required", "Sign in to open this page."),
    403: ("Access not allowed", "Your account cannot view or change this record."),
    404: ("Not found", "This record does not exist, or it belongs to a company your account cannot access."),
}


def error_page(status_code: int) -> str:
    """Browser page for 401/403/404; API clients keep JSON errors."""
    title, message = ERROR_PAGES.get(status_code, ("Something went wrong", "The request could not be completed."))
    action = "Sign in" if status_code == 401 else "Back to portfolio"
    symbol = {401: "private", 403: "private", 404: "search"}.get(status_code, "alert")
    body = (
        f"<section class='status-page'><span class='page-icon'>{icon(symbol)}</span>"
        f"<p class='eyebrow'>Error {status_code}</p><h1>{escape(title)}</h1>"
        f"<p>{escape(message)}</p><div class='page-actions'><a class='button' href='/'>{action}</a></div></section>"
    )
    return page(title, body, active="login" if status_code == 401 else "portfolio")


# The stylesheet's relative font path suits published exhibits; the application serves the font itself.
APP_FONT = (
    '@font-face{font-family:"Inter";font-style:normal;font-weight:100 900;font-display:swap;'
    'src:url("/assets/fonts/InterVariable-latin.woff2") format("woff2")}'
)
BRAND_MARK = (
    "<span class='brand-mark' aria-hidden='true'><svg viewBox='0 0 24 24' fill='none'>"
    "<path d='M5 19V12M10 19V7M15 19V10M20 19V4' stroke='currentColor' stroke-width='2.6' stroke-linecap='round'/></svg></span>"
)
# Outline icons drawn on a 24-unit grid; decorative only (aria-hidden), always paired with text.
_ICONS = {
    "portfolio": "<rect x='3' y='3' width='7' height='7' rx='1.5'/><rect x='14' y='3' width='7' height='7' rx='1.5'/><rect x='3' y='14' width='7' height='7' rx='1.5'/><rect x='14' y='14' width='7' height='7' rx='1.5'/>",
    "decisions": "<path d='M9 11l3 3 8-8'/><path d='M20 12v6a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h9'/>",
    "private": "<rect x='4' y='10' width='16' height='11' rx='2'/><path d='M8 10V7a4 4 0 0 1 8 0v3'/>",
    "methodology": "<path d='M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2z'/><path d='M4 19V5'/>",
    "company": "<rect x='4' y='3' width='16' height='18' rx='2'/><path d='M9 7h1M14 7h1M9 11h1M14 11h1M9 15h1M14 15h1'/>",
    "status": "<circle cx='12' cy='12' r='8'/><circle cx='12' cy='12' r='3'/>",
    "value": "<path d='M3 17l6-6 4 4 8-8'/><path d='M15 7h6v6'/>",
    "lever": "<circle cx='12' cy='12' r='8'/><circle cx='12' cy='12' r='4'/><path d='M12 12h.01'/>",
    "alert": "<path d='M10.3 4.2L2.6 18a2 2 0 0 0 1.7 3h15.4a2 2 0 0 0 1.7-3L13.7 4.2a2 2 0 0 0-3.4 0z'/><path d='M12 9v4M12 17h.01'/>",
    "next": "<path d='M5 12h14M13 6l6 6-6 6'/>",
    "chevron": "<path d='M9 6l6 6-6 6'/>",
    "file": "<path d='M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z'/><path d='M14 3v5h5M9 13h6M9 17h4'/>",
    "shield": "<path d='M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6z'/><path d='M9 12l2 2 4-4'/>",
    "data": "<ellipse cx='12' cy='6' rx='7' ry='3'/><path d='M5 6v12c0 1.7 3.1 3 7 3s7-1.3 7-3V6M5 12c0 1.7 3.1 3 7 3s7-1.3 7-3'/>",
    "chart": "<path d='M4 20h16M7 16v-5M12 16V6M17 16v-8'/>",
    "calendar": "<rect x='4' y='5' width='16' height='16' rx='2'/><path d='M4 10h16M9 3v4M15 3v4'/>",
    "user": "<circle cx='12' cy='8' r='4'/><path d='M4 21c1.5-4 4.5-6 8-6s6.5 2 8 6'/>",
    "layers": "<path d='M12 3l9 5-9 5-9-5z'/><path d='M3 13l9 5 9-5'/>",
    "tag": "<path d='M3 12V4a1 1 0 0 1 1-1h8l9 9-9 9z'/><circle cx='8' cy='8' r='1.5'/>",
    "hash": "<path d='M5 9h14M5 15h14M10 4L8 20M16 4l-2 16'/>",
    "external": "<path d='M14 4h6v6M20 4l-9 9'/><path d='M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5'/>",
    "activity": "<path d='M3 12h4l3-8 4 16 3-8h4'/>",
    "eye": "<path d='M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z'/><circle cx='12' cy='12' r='3'/>",
    "search": "<circle cx='11' cy='11' r='7'/><path d='M20 20l-4-4'/>",
    "check": "<circle cx='12' cy='12' r='9'/><path d='M8 12l3 3 5-6'/>",
    "scale": "<path d='M12 4v16M5 20h14M5 8h14M7 8l-3 7h6zM17 8l-3 7h6z'/>",
}


def icon(name: str) -> str:
    """Return a decorative outline icon; the surrounding text carries the meaning."""
    return (
        "<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='1.8' stroke-linecap='round' "
        f"stroke-linejoin='round' aria-hidden='true' focusable='false'>{_ICONS[name]}</svg>"
    )


_icon = icon


def page_header(
    title: str,
    *,
    crumbs: list[tuple[str, str | None]] | None = None,
    subtitle: str = "",
    badge: str = "",
    actions: str = "",
    meta: str = "",
    symbol: str | None = None,
    eyebrow: str = "",
    tabs: bool = False,
    aside: str = "",
) -> str:
    """Shared page header: breadcrumb, title with status, subtitle and right-aligned actions.

    ``title`` and ``crumbs`` text are escaped; ``subtitle``, ``badge``, ``actions``, ``meta``, ``eyebrow`` and
    ``aside`` are trusted markup built by callers from escaped values.
    """
    trail = ""
    if crumbs:
        parts = []
        for index, (text, href) in enumerate(crumbs):
            if index:
                parts.append("<span class='sep' aria-hidden='true'>/</span>")
            if href is None:
                parts.append(f"<span aria-current='page'>{escape(text)}</span>")
            else:
                parts.append(f"<a href='{escape(href)}'>{escape(text)}</a>")
        trail = f"<nav class='breadcrumb' aria-label='Breadcrumb'>{''.join(parts)}</nav>"
    heading = f"<span class='page-icon'>{icon(symbol)}</span>" if symbol else ""
    right = ""
    if actions:
        right += f"<div class='page-actions'>{actions}</div>"
    right += aside
    return (
        f"<header class='page-header{' has-tabs' if tabs else ''}'>{trail}<div class='page-header-row'>"
        f"<div class='page-heading'>{heading}<div>{eyebrow}"
        f"<div class='page-title-row'><h1 class='page-title'>{escape(title)}</h1>{badge}</div>"
        + (f"<p class='page-subtitle'>{subtitle}</p>" if subtitle else "")
        + (f"<div class='page-meta'>{meta}</div>" if meta else "")
        + f"</div></div>{right}</div></header>"
    )


def page(
    title: str,
    body: str,
    *,
    active: str = "portfolio",
    eyebrow: str | None = None,
    private_origin: Literal["synthetic_test_fixture", "company_export", "mixed"] | None = None,
) -> str:
    """Wrap trusted application markup in the shared, accessible workspace shell."""
    links = (("portfolio", "/", "Portfolio"), ("decisions", "/#decisions", "Decision desk"))
    if active == "private":
        links = (("private", "/private-reviews", "Private reviews"), ("portfolio", "/", "Portfolio"))
    navigation = "".join(
        f"<a class='side-link' href='{href}'"
        + (" aria-current='page'" if active == key else "")
        + f">{icon(key)}<span>{text}</span></a>"
        for key, href, text in links
    )
    navigation += f"<a class='side-link' href='#methodology'>{icon('methodology')}<span>Methodology</span></a>"
    if active == "login":
        navigation = ""
    kicker = f"<p class='eyebrow'>{escape(eyebrow)}</p>" if eyebrow else ""
    synthetic = os.environ.get("PVC_SOURCE_ADAPTER", "fixtures") == "fixtures"
    data_note = "Synthetic company data" if synthetic else "Company-scoped operating evidence"
    source_note = (
        "The showcase uses fictional companies and seeded observations."
        if synthetic
        else "Recorded observations inherit the scope and limitations of their source data."
    )
    methodology = (
        "Evidence supports the diagnostic. Deterministic calculations size the value cases. "
        "A human decides which initiatives enter the execution plan. Financial figures are modeled "
        "in source units; they are not realized returns. " + source_note
    )
    outcome_note = "Modeled outcomes"
    if private_origin is not None:
        outcome_note = "Recorded observations and claims"
        data_note = (
            "Fictional private-workflow rehearsal"
            if private_origin == "synthetic_test_fixture"
            else "Permissioned private company data"
        )
        if private_origin == "mixed":
            data_note = "Private review records; source origin shown per case"
        methodology = (
            "This private review separates frozen forecasts, accounting observations and initiative claims. "
            "A finance decision records the reviewer's assessment; it does not establish causation or operating permission. "
            "Current source and delivery support is checked separately from historical receipts."
        )
    brand = (
        f"{BRAND_MARK}<span class='brand-name'>Value Creation OS"
        "<span class='brand-subtitle'>Operating partner workspace</span></span>"
    )
    if active == "login":
        chrome = (
            "<div class='app-layout bare'><header class='bare-header'>"
            f"<a class='brand' href='/' aria-label='Value Creation OS portfolio'>{brand}</a></header>"
        )
    else:
        facts = "".join(
            f"<li>{icon(symbol)}<span>{text}</span></li>"
            for symbol, text in (("data", data_note), ("chart", outcome_note), ("shield", "Human decision control"))
        )
        chrome = (
            "<div class='app-layout'><aside class='sidebar'>"
            f"<a class='brand side-workspace' href='/' aria-label='Value Creation OS portfolio'>{brand}</a>"
            f"<nav class='side-nav' aria-label='Main'><p class='side-label'>Workspace</p>{navigation}</nav>"
            f"<div class='side-foot'><p class='side-label'>Data provenance</p><ul class='side-facts'>{facts}</ul></div>"
            "</aside>"
        )
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<meta name='theme-color' content='#ffffff'>"
        f"<title>{escape(title)} | Value Creation OS</title><style>{CSS}{APP_FONT}</style></head><body>"
        "<a class='skip-link' href='#main-content'>Skip to content</a>"
        + chrome
        + f"<div class='app-main'><main class='app-shell' id='main-content' tabindex='-1'>{kicker}{body}</main>"
        "<footer class='page-footer'><div class='footer-line'>"
        "<p><strong>Value Creation OS</strong> · Evidence. Value. Execution.</p>"
        f"<p>{data_note} · {outcome_note} · Human decision control</p></div>"
        "<details id='methodology'><summary>Methodology &amp; technical boundaries</summary>"
        f"<p>{methodology}</p></details></footer></div></div></body></html>"
    )

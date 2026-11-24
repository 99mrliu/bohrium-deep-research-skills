#!/usr/bin/env python3
"""build_atlas.py -- evidence-atlas-forge render gate.

Renders result.json + pages.jsonl into a self-contained HTML evidence
atlas. Rendering re-verifies every finding quote verbatim against the
claimed page: failures are badged VERIFICATION FAILED on the card and
cause exit code 1 -- the render must never silently ship stale evidence.

Writes: <outdir>/report.html, <outdir>/atlas_manifest.json
"""
import argparse
import hashlib
import html
import json
import re
import sys
from pathlib import Path

SEV_COLOR = {"critical": "#b00020", "major": "#d35400",
             "minor": "#b7950b", "advisory": "#1e8449"}
SEVS = list(SEV_COLOR)


def collapse(s):
    return re.sub(r"\s+", " ", s or "").strip()


def esc(s):
    return html.escape(str(s), quote=True)


def sha256_of(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def card_html(f, ok):
    sev = f.get("severity", "advisory")
    color = SEV_COLOR.get(sev, "#555")
    badge = ('<span class="vf">VERIFICATION FAILED</span>' if not ok
             else '<span class="vo">quote verified</span>')
    loc = f.get("location", {})
    return f"""
<div class="card" style="border-left:6px solid {color}">
  <div class="cardhead">
    <b>{esc(f.get('id','?'))}</b>
    <span class="sev" style="background:{color}">{esc(sev)}</span>
    <span class="cat">{esc(f.get('category',''))}</span>
    <span class="itype">{esc(f.get('issue_type',''))}</span>
    {badge}
  </div>
  <div class="loc">&#128205; {esc(loc.get('locator',''))} (page
    {esc(loc.get('page','?'))})</div>
  <blockquote>{esc(loc.get('quote',''))}</blockquote>
  <table>
    <tr><th>claim</th><td>{esc(f.get('claim',''))}</td></tr>
    <tr><th>verdict</th><td>{esc(f.get('verdict',''))}</td></tr>
    <tr><th>basis</th><td>{esc(f.get('basis',''))}</td></tr>
    <tr><th>suggestion</th><td>{esc(f.get('suggestion',''))}</td></tr>
    <tr><th>confidence</th><td>{esc(f.get('confidence',''))}
      &nbsp;|&nbsp;recheck: {esc(f.get('recheck',''))}</td></tr>
  </table>
</div>"""


CSS = """
body{font-family:-apple-system,'Helvetica Neue',Arial,'PingFang SC',
'Microsoft YaHei',sans-serif;max-width:960px;margin:2em auto;padding:0 1em;
color:#222;line-height:1.55}
h1{font-size:1.5em} h2{font-size:1.15em;border-bottom:2px solid #ddd;
padding-bottom:.2em;margin-top:1.6em}
.card{border:1px solid #ddd;border-radius:6px;padding:.9em 1.1em;
margin:1em 0;background:#fff}
.cardhead{display:flex;gap:.6em;align-items:center;flex-wrap:wrap}
.sev{color:#fff;border-radius:4px;padding:.05em .5em;font-size:.85em}
.cat,.itype{background:#eef;border-radius:4px;padding:.05em .5em;
font-size:.85em}
.vo{color:#1e8449;font-size:.85em}
.vf{color:#fff;background:#b00020;border-radius:4px;padding:.05em .5em;
font-size:.85em;font-weight:bold}
.loc{color:#666;font-size:.9em;margin:.4em 0}
blockquote{background:#f7f7f9;border-left:3px solid #999;margin:.5em 0;
padding:.4em .8em;font-style:italic;color:#444}
table{border-collapse:collapse;width:100%;margin-top:.4em}
th,td{text-align:left;vertical-align:top;padding:.2em .5em;
border-top:1px solid #eee;font-size:.92em}
th{width:7.5em;color:#555}
.cov td{border:1px solid #ddd}
.meta{color:#777;font-size:.85em}
ul{line-height:1.5}
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--result", required=True)
    ap.add_argument("--pages", required=True)
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args()

    result = json.load(open(args.result, encoding="utf-8"))
    pages = {}
    for line in open(args.pages, encoding="utf-8"):
        if line.strip():
            pg = json.loads(line)
            pages[pg["page"]] = collapse(pg["text"])

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    findings = result.get("findings", [])
    manifest = {"case_id": result.get("case_id"),
                "result_sha256": sha256_of(args.result),
                "pages_sha256": sha256_of(args.pages), "cards": []}
    failed = 0
    cards = []
    for f in findings:
        loc = f.get("location", {})
        page, quote = loc.get("page"), collapse(loc.get("quote", ""))
        ok = bool(quote) and page in pages and quote in pages[page]
        if not ok:
            failed += 1
        manifest["cards"].append({"id": f.get("id"), "page": page,
                                  "quote_verified": ok})
        cards.append(card_html(f, ok))

    cov = result.get("coverage", {})
    cov_rows = "".join(
        f"<tr><td>{esc(k)}</td><td>{esc(v)}</td></tr>"
        for k, v in cov.items())
    sev_counts = {s: sum(1 for f in findings if f.get("severity") == s)
                  for s in SEVS}
    sev_summary = " · ".join(f"{s}: {n}" for s, n in sev_counts.items())
    unchecked = "".join(f"<li>{esc(x)}</li>"
                        for x in result.get("unchecked_items", []))
    uncertainties = "".join(f"<li>{esc(x)}</li>"
                            for x in result.get("uncertainties", []))

    report = f"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<title>Evidence Atlas - {esc(result.get('case_id','?'))}</title>
<style>{CSS}</style></head><body>
<h1>Evidence Atlas &#8212; {esc(result.get('case_id','?'))}</h1>
<p class="meta">skill: {esc(result.get('skill','?'))} | status:
<b>{esc(result.get('status','?'))}</b> | findings: {len(findings)}
({sev_summary}) | verification failed cards: <b>{failed}</b></p>
<p class="meta">result sha256: {manifest['result_sha256'][:16]}&hellip;
| pages sha256: {manifest['pages_sha256'][:16]}&hellip;</p>
<h2>六类覆盖状态</h2>
<table class="cov">{cov_rows}</table>
<h2>待复核与不确定性</h2>
<ul>{unchecked or '<li>无</li>'}</ul>
<ul>{uncertainties or '<li>无</li>'}</ul>
<h2>证据卡片</h2>
{''.join(cards) if cards else '<p>无 finding。</p>'}
</body></html>"""

    (outdir / "report.html").write_text(report, encoding="utf-8")
    with open(outdir / "atlas_manifest.json", "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)
    print(json.dumps({"cards": len(findings),
                      "verification_failed": failed}, ensure_ascii=False))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()

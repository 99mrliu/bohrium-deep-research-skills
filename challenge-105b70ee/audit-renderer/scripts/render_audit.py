#!/usr/bin/env python3
"""Render the audit pack (audit-renderer skill).

Reads result.json (+ verify_report.json when present) and writes a
self-contained HTML audit report: coverage matrix, per-field evidence
cards with the scalar highlighted in its quote, claims grouped by kind,
uncertainty table, verification verdict. With --pdf and pdftoppm present,
referenced pages are also rendered as PNG previews (--pages-dir); previews
are runtime artifacts and their absence never blocks the HTML.
"""
import argparse
import html
import json
import os
import shutil
import subprocess
import sys
import time

STATUS_COLOR = {"reported": "#1a7f37", "not_reported": "#6e7781",
                "source_conflict": "#bf4b00", "extraction_failed": "#b02a37"}


def esc(t):
    return html.escape(str(t if t is not None else "—"))


def hi(quote, scalar):
    q = esc(quote)
    if scalar and scalar in (quote or ""):
        q = q.replace(esc(scalar), "<mark>%s</mark>" % esc(scalar), 1)
    return q


def render_pages(pdf, pages_dir, wanted):
    if not pdf or not shutil.which("pdftoppm"):
        return []
    os.makedirs(pages_dir, exist_ok=True)
    made = []
    for pg in sorted(set(wanted)):
        prefix = os.path.join(pages_dir, "page-%d" % pg)
        try:
            p = subprocess.run(["pdftoppm", "-f", str(pg), "-l", str(pg),
                                "-r", "110", "-png", pdf, prefix],
                               capture_output=True, timeout=120)
            for f in os.listdir(pages_dir):
                if f.startswith("page-%d" % pg) and f.endswith(".png"):
                    made.append(os.path.join(pages_dir, f))
                    break
            if p.returncode != 0:
                break
        except (OSError, subprocess.TimeoutExpired):
            break
    return made


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--result", required=True)
    ap.add_argument("--work-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--pdf")
    ap.add_argument("--pages-dir")
    a = ap.parse_args()
    d = json.load(open(a.result, encoding="utf-8"))
    vr = {}
    vrp = os.path.join(a.work_dir, "verify_report.json")
    if os.path.isfile(vrp):
        vr = json.load(open(vrp, encoding="utf-8"))
    frs = (d.get("result") or {}).get("field_results") or []

    wanted_pages = [r.get("page") for r in frs if r.get("page")] + \
        [(c.get("evidence") or {}).get("page") for c in d.get("claims", [])
         if (c.get("evidence") or {}).get("page")]
    previews = render_pages(a.pdf, a.pages_dir, wanted_pages) \
        if a.pdf and a.pages_dir else []

    rows = "".join(
        "<tr><td>%s</td><td style='color:%s'>%s</td><td>%s</td><td>%s</td></tr>"
        % (esc(r.get("field_id")), STATUS_COLOR.get(r.get("status"), "#000"),
           esc(r.get("status")), esc(r.get("scalar")), esc(r.get("units")))
        for r in frs)
    cards = []
    for r in frs:
        cards.append(
            "<div class='card'><h3>%s <span style='color:%s'>[%s]</span></h3>"
            "<p class='q'>%s</p>"
            "<table><tr><td>value</td><td>%s %s %s</td></tr>"
            "<tr><td>condition</td><td>%s</td></tr>"
            "<tr><td>comparator</td><td>%s</td></tr>"
            "<tr><td>location</td><td>page %s %s %s</td></tr>"
            "<tr><td>notes</td><td>%s</td></tr></table></div>" % (
                esc(r.get("field_id")), STATUS_COLOR.get(r.get("status"), "#000"),
                esc(r.get("status")), hi(r.get("quote"), r.get("scalar")),
                esc(r.get("scalar")), esc(r.get("units")), esc(r.get("statistic")),
                esc(r.get("condition")), esc(r.get("comparator")),
                esc(r.get("page")), esc(r.get("paragraph_id")),
                esc(r.get("bank_id")), esc(r.get("notes"))))
    claims = "".join(
        "<tr><td>%s</td><td>%s</td><td class='q'>%s</td><td>%s</td></tr>" % (
            esc(c.get("kind")), esc(c.get("text")),
            esc((c.get("evidence") or {}).get("quote")),
            esc(c.get("location")))
        for c in d.get("claims", []))
    unc = "".join(
        "<tr><td>%s</td><td>%s</td><td>%s</td></tr>" % (
            esc(u.get("field_id") or u.get("item")), esc(u.get("status")),
            esc(u.get("notes")))
        for u in d.get("uncertainties", []))
    verdict = vr.get("verdict", "not run")
    vchecks = "".join(
        "<tr class='%s'><td>%s</td><td>%s</td><td>%s</td></tr>" % (
            "fail" if not c["pass"] else "pass",
            "✗" if not c["pass"] else "✓", esc(c["check"]), esc(c["detail"]))
        for c in vr.get("checks", []))
    prev = "".join("<li>%s</li>" % esc(p) for p in previews)

    doc = """<!doctype html><html><head><meta charset="utf-8"><title>audit</title>
<style>body{font-family:system-ui,sans-serif;max-width:960px;margin:2em auto}
table{border-collapse:collapse;margin:1em 0}td,th{border:1px solid #ccc;
padding:4px 8px;text-align:left;vertical-align:top}
.card{border:1px solid #ddd;border-radius:8px;padding:1em;margin:1em 0}
.q{color:#444;font-style:italic}mark{background:#ffe58f;padding:0 2px}
tr.fail td{color:#b02a37}h1,h2{border-bottom:2px solid #eee;padding-bottom:.2em}
</style></head><body>
<h1>Extraction audit — %(case_id)s</h1>
<p>status: <b>%(status)s</b> · verification verdict: <b>%(verdict)s</b>
(%(nchecks)d checks, %(nerrors)d errors) · rendered %(ts)s</p>
<h2>Coverage matrix</h2>
<table><tr><th>field_id</th><th>status</th><th>scalar</th><th>units</th></tr>
%(rows)s</table>
<h2>Evidence cards</h2>%(cards)s
<h2>Claims</h2>
<table><tr><th>kind</th><th>claim</th><th>evidence quote</th><th>location</th></tr>
%(claims)s</table>
<h2>Uncertainties</h2>
<table><tr><th>field</th><th>status</th><th>notes</th></tr>%(unc)s</table>
<h2>Verification join-checks</h2>
<table><tr><th></th><th>check</th><th>detail</th></tr>%(vchecks)s</table>
<h2>Page previews</h2><ul>%(prev)s</ul>
</body></html>""" % {
        "case_id": esc(d.get("case_id")), "status": esc(d.get("status")),
        "verdict": esc(verdict), "nchecks": len(vr.get("checks", [])),
        "nerrors": vr.get("errors", 0),
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "rows": rows, "cards": "".join(cards), "claims": claims,
        "unc": unc, "vchecks": vchecks, "prev": prev or "<li>not rendered</li>",
    }
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(doc)
    print("audit -> %s (%d fields, %d previews)" % (a.out, len(frs), len(previews)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""render_deliverables.py -- render inspectable deliverables and retain
human-edit diffs.

Render mode (needs --notes and --claims-report):
  notebook.md    Markdown notebook grouped by note_type, each note shows the
                 claim, quote blocks with source locators
                 `file - p.N - annotation_id`, tags and verification status;
                 header block carries provenance (source hashes from
                 sources/<filekey>/source.json when present, tool version,
                 and a synthetic-example banner when --example is passed).
  index.html     fully standalone HTML index (inline CSS, clickable anchors
                 per note, verification summary table; no external resources).
  manifest.json  deliverable file list with sha256 and byte counts.

Human-edit retention (no --notes needed):
  --snapshot LABEL        copy current notebook.md / index.html of --out-dir
                          into change_records/<LABEL>/
  --diff LABEL1 LABEL2    write unified diffs (difflib.unified_diff) between
                          two snapshots into
                          change_records/diff-<LABEL1>-to-<LABEL2>.diff

Deterministic: no wall-clock anywhere; ordering follows input order.

Exit codes: 0 success; 2 usage / IO error; 3 not used by this script.
"""
import argparse
import difflib
import hashlib
import html
import json
import re
import shutil
import sys
from pathlib import Path

TOOL_VERSION = "deliverable-forge 1.0.0"
NOTE_TYPE_ORDER = ["problem", "method", "result", "reusable_point", "doubt"]
NOTE_TYPE_TITLE = {
    "problem": "Problems / research questions",
    "method": "Methods",
    "result": "Results",
    "reusable_point": "Reusable points",
    "doubt": "Doubts / open questions",
}
SNAPSHOT_FILES = ["notebook.md", "index.html"]
LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def die(msg, code=2):
    print(f"render_deliverables: ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def check_label(label):
    if not LABEL_RE.match(label or ""):
        die(f"invalid snapshot label '{label}' "
            f"(allowed: [A-Za-z0-9._-], max 64 chars)")


def load_jsonl(path, what):
    p = Path(path)
    if not p.is_file():
        die(f"{what} not found: {path}")
    records = []
    with p.open(encoding="utf-8") as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as e:
                die(f"{what}:{lineno}: invalid JSON: {e}")
    return records


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_claims_report(path):
    p = Path(path)
    if not p.is_file():
        die(f"claims report not found: {path}")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        die(f"claims report: invalid JSON: {e}")


def build_provenance(notes, sources_dir):
    """Collect source file hashes from sources/<filekey>/source.json when
    present. Deterministic: files sorted."""
    files = sorted({ev["file"] for n in notes for ev in n.get("evidence", [])})
    prov = []
    for fk in files:
        entry = {"file": fk, "source_json": False, "tool": None, "pages": []}
        sj = Path(sources_dir) / fk / "source.json"
        if sj.is_file():
            try:
                meta = json.loads(sj.read_text(encoding="utf-8"))
                entry["source_json"] = True
                entry["tool"] = meta.get("tool")
                for pg in meta.get("pages", []):
                    entry["pages"].append({
                        "page": pg.get("page"),
                        "file": pg.get("file"),
                        "sha256": pg.get("sha256"),
                    })
            except json.JSONDecodeError:
                entry["tool"] = "(source.json unreadable)"
        prov.append(entry)
    return prov


def status_map(report):
    return {r["note_id"]: r["status"] for r in report.get("results", [])}


def group_notes(notes):
    grouped = {t: [] for t in NOTE_TYPE_ORDER}
    for n in notes:
        grouped.setdefault(n.get("note_type"), []).append(n)
    ordered = [(t, grouped[t]) for t in NOTE_TYPE_ORDER if grouped.get(t)]
    extra = [(t, ns) for t, ns in grouped.items()
             if t not in NOTE_TYPE_ORDER and ns]
    return ordered + sorted(extra)


def locator_str(ev):
    ann = ev.get("annotation_id") or "direct"
    return f"{ev['file']} — p.{ev['page']} — {ann}"


def render_notebook(notes, report, prov, example):
    sm = status_map(report)
    L = []
    L.append("# Reading Notebook — deliverable-forge")
    L.append("")
    if example:
        L.append("> **SYNTHETIC EXAMPLE** — rendered with `--example`; all "
                 "content is fixture data, not real research.")
        L.append("")
    L.append("## Provenance")
    L.append("")
    L.append(f"- tool: {TOOL_VERSION} (render_deliverables.py)")
    L.append(f"- verification: {report.get('verified')}/"
             f"{report.get('total_claims')} claims verified "
             f"(verified_rate {report.get('verified_rate')}) — "
             f"from claims_report.json")
    L.append(f"- deterministic output: no timestamps; note order follows "
             f"input order")
    L.append("- sources:")
    for p in prov:
        if p["source_json"]:
            L.append(f"  - `{p['file']}` (text extraction tool: {p['tool']})")
            for pg in p["pages"]:
                L.append(f"    - {pg['file']}: sha256={pg['sha256']}")
        else:
            L.append(f"  - `{p['file']}` (no source.json provided)")
    L.append("")
    for ntype, ns in group_notes(notes):
        L.append(f"## {NOTE_TYPE_TITLE.get(ntype, ntype)}")
        L.append("")
        for n in ns:
            L.append(f"### {n['note_id']} ({n['note_type']})")
            L.append("")
            L.append(f"- **claim**: {n['claim']}")
            tags = ", ".join(n.get("tags", [])) or "(none)"
            L.append(f"- tags: {tags}")
            L.append(f"- status: {sm.get(n['note_id'], 'unknown')}")
            for w in n.get("warnings", []):
                L.append(f"- warning: {w}")
            L.append("")
            for ev in n.get("evidence", []):
                L.append(f"> {ev['quote']}")
                L.append(">")
                L.append(f"> — {locator_str(ev)}")
                L.append("")
    return "\n".join(L).rstrip("\n") + "\n"


def render_index(notes, report, prov, example):
    sm = status_map(report)
    esc = html.escape
    banner = ('<p class="banner">SYNTHETIC EXAMPLE — rendered with '
              '<code>--example</code>; fixture data, not real research.</p>'
              if example else "")
    nav = "".join(
        f'<li><a href="#note-{esc(n["note_id"])}">{esc(n["note_id"])}</a> '
        f'<span class="st-{esc(sm.get(n["note_id"], "unknown"))}">'
        f'{esc(sm.get(n["note_id"], "unknown"))}</span></li>'
        for n in notes)
    rows = "".join(
        f'<tr><td><a href="#note-{esc(r["note_id"])}">{esc(r["note_id"])}'
        f'</a></td><td class="st-{esc(r["status"])}">{esc(r["status"])}</td>'
        f"<td>{len(r.get('evidence', []))}</td></tr>"
        for r in report.get("results", []))
    prov_items = ""
    for p in prov:
        if p["source_json"]:
            pages = "; ".join(f"{esc(str(pg['file']))} sha256="
                              f"{esc(str(pg['sha256']))[:16]}…"
                              for pg in p["pages"])
            prov_items += (f"<li><code>{esc(p['file'])}</code> "
                           f"(tool: {esc(str(p['tool']))}) — {pages}</li>")
        else:
            prov_items += (f"<li><code>{esc(p['file'])}</code> "
                           f"(no source.json provided)</li>")
    sections = []
    for ntype, ns in group_notes(notes):
        cards = []
        for n in ns:
            quotes = "".join(
                f"<blockquote>{esc(ev['quote'])}<footer>— "
                f"{esc(locator_str(ev))}</footer></blockquote>"
                for ev in n.get("evidence", []))
            warns = "".join(f'<p class="warn">warning: {esc(w)}</p>'
                            for w in n.get("warnings", []))
            tags = ", ".join(esc(t) for t in n.get("tags", [])) or "(none)"
            st = sm.get(n["note_id"], "unknown")
            cards.append(
                f'<article class="card" id="note-{esc(n["note_id"])}">'
                f'<h3>{esc(n["note_id"])} '
                f'<span class="type">{esc(n["note_type"])}</span></h3>'
                f'<p class="claim">{esc(n["claim"])}</p>'
                f'{quotes}'
                f'<p class="meta">tags: {tags} · status: '
                f'<span class="st-{esc(st)}">{esc(st)}</span></p>'
                f'{warns}</article>')
        sections.append(f"<h2>{esc(NOTE_TYPE_TITLE.get(ntype, ntype))}</h2>"
                        + "".join(cards))
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Deliverable-Forge Index</title>
<style>
body {{ font-family: -apple-system, "Segoe UI", Helvetica, Arial, sans-serif;
       max-width: 900px; margin: 2em auto; padding: 0 1em; color: #222; }}
h1 {{ border-bottom: 3px solid #444; padding-bottom: .2em; }}
.banner {{ background: #fff3cd; border: 1px solid #e0a800; padding: .6em;
          border-radius: 6px; font-weight: bold; }}
.card {{ border: 1px solid #ccc; border-radius: 8px; padding: .8em 1em;
        margin: 1em 0; }}
.card h3 {{ margin-top: 0; }}
.type {{ font-size: .7em; color: #fff; background: #555; border-radius: 4px;
        padding: .1em .5em; vertical-align: middle; }}
.claim {{ font-size: 1.05em; }}
blockquote {{ border-left: 4px solid #7aa5d2; margin: .6em 0;
             padding: .3em .9em; background: #f4f8fc; }}
blockquote footer {{ color: #666; font-size: .85em; margin-top: .3em; }}
.meta {{ color: #666; font-size: .85em; }}
.warn {{ color: #8a5a00; }}
table {{ border-collapse: collapse; }}
th, td {{ border: 1px solid #bbb; padding: .3em .7em; text-align: left; }}
th {{ background: #eee; }}
.st-verified {{ color: #1a7f37; font-weight: bold; }}
.st-quote_not_found, .st-page_missing, .st-file_missing
{{ color: #b02a2a; font-weight: bold; }}
code {{ background: #f0f0f0; padding: 0 .2em; border-radius: 3px; }}
</style>
</head>
<body>
<h1>Deliverable-Forge Index</h1>
{banner}
<p>tool: {esc(TOOL_VERSION)} · claims verified:
{report.get('verified')}/{report.get('total_claims')}
(verified_rate {report.get('verified_rate')})</p>
<h2>Provenance</h2>
<ul>{prov_items}</ul>
<h2>Verification summary</h2>
<table>
<tr><th>note</th><th>status</th><th>evidence items</th></tr>
{rows}
<tr><th>total</th><th>{report.get('verified')}/{report.get('total_claims')}
verified</th><th>{report.get('total_claims')}</th></tr>
</table>
<h2>Notes</h2>
<ul>{nav}</ul>
{''.join(sections)}
</body>
</html>
"""


def cmd_render(args):
    notes = load_jsonl(args.notes, "notes file")
    report = load_claims_report(args.claims_report)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    prov = build_provenance(notes, args.sources_dir)

    notebook = render_notebook(notes, report, prov, args.example)
    index = render_index(notes, report, prov, args.example)
    (out_dir / "notebook.md").write_text(notebook, encoding="utf-8")
    (out_dir / "index.html").write_text(index, encoding="utf-8")

    files = []
    for name in sorted(["index.html", "notebook.md"]):
        p = out_dir / name
        files.append({"path": name, "bytes": p.stat().st_size,
                      "sha256": sha256_file(p)})
    manifest = {"tool": TOOL_VERSION, "files": files}
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print(f"render_deliverables {TOOL_VERSION}")
    print(f"notes rendered: {len(notes)}")
    for fentry in files:
        print(f"  {fentry['path']}: {fentry['bytes']} bytes "
              f"sha256={fentry['sha256'][:16]}…")
    print(f"  manifest.json written")
    print(f"out dir: {out_dir}")
    return 0


def cmd_snapshot(args):
    check_label(args.snapshot)
    out_dir = Path(args.out_dir)
    if not out_dir.is_dir():
        die(f"out dir not found: {out_dir} (render first)")
    dest = out_dir / "change_records" / args.snapshot
    dest.mkdir(parents=True, exist_ok=True)
    copied = []
    for name in SNAPSHOT_FILES:
        src = out_dir / name
        if src.is_file():
            shutil.copyfile(src, dest / name)
            copied.append(name)
    if not copied:
        die(f"nothing to snapshot in {out_dir} (render first)")
    print(f"snapshot '{args.snapshot}' saved: {', '.join(copied)} "
          f"-> {dest}")
    return 0


def cmd_diff(args):
    l1, l2 = args.diff
    check_label(l1)
    check_label(l2)
    out_dir = Path(args.out_dir)
    d1 = out_dir / "change_records" / l1
    d2 = out_dir / "change_records" / l2
    for d, lab in ((d1, l1), (d2, l2)):
        if not d.is_dir():
            die(f"snapshot '{lab}' not found at {d}")
    names = sorted({p.name for p in d1.iterdir() if p.is_file()}
                   | {p.name for p in d2.iterdir() if p.is_file()})
    chunks = []
    for name in names:
        a = (d1 / name).read_text(encoding="utf-8").splitlines() \
            if (d1 / name).is_file() else []
        b = (d2 / name).read_text(encoding="utf-8").splitlines() \
            if (d2 / name).is_file() else []
        diff = list(difflib.unified_diff(
            a, b, fromfile=f"{l1}/{name}", tofile=f"{l2}/{name}",
            lineterm=""))
        if diff:
            chunks.append("\n".join(diff))
    out_path = out_dir / "change_records" / f"diff-{l1}-to-{l2}.diff"
    if chunks:
        out_path.write_text("\n".join(chunks) + "\n", encoding="utf-8")
        print(f"diff written: {out_path} "
              f"({sum(len(c.splitlines()) for c in chunks)} lines)")
    else:
        out_path.write_text(f"# no differences between snapshots "
                            f"'{l1}' and '{l2}'\n", encoding="utf-8")
        print(f"no differences; wrote marker: {out_path}")
    return 0


def main():
    ap = argparse.ArgumentParser(
        description="Render notebook.md / index.html / manifest.json, or "
                    "snapshot and diff human edits.")
    ap.add_argument("--notes", help="notes.jsonl (render mode)")
    ap.add_argument("--claims-report", help="claims_report.json (render mode)")
    ap.add_argument("--sources-dir", default="sources",
                    help="directory with sources/<filekey>/ (default: "
                    "'sources'; used for provenance hashes)")
    ap.add_argument("--out-dir", required=True,
                    help="output directory for deliverables")
    ap.add_argument("--example", action="store_true",
                    help="mark outputs as a synthetic example")
    ap.add_argument("--snapshot", metavar="LABEL",
                    help="snapshot current notebook.md/index.html into "
                    "change_records/LABEL/")
    ap.add_argument("--diff", nargs=2, metavar=("LABEL1", "LABEL2"),
                    help="write unified diff between two snapshots")
    args = ap.parse_args()

    if args.snapshot and args.diff:
        die("use either --snapshot or --diff, not both")
    if args.snapshot:
        sys.exit(cmd_snapshot(args))
    if args.diff:
        sys.exit(cmd_diff(args))
    if not args.notes or not args.claims_report:
        die("render mode requires --notes and --claims-report")
    sys.exit(cmd_render(args))


if __name__ == "__main__":
    main()

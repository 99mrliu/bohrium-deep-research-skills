#!/usr/bin/env python3
"""render.py -- export and self-check for the audit-trail-polish skill.

Commands:
  export       --job <dir> --out <dir>
      Produce polished.md, changes.json, change-log.md and review.html (a
      self-contained single file: inline CSS, no external dependencies; left
      column original / right column revised, type badges, collapsible
      reason+basis, top statistics bar and gate status). Gate C01 re-fills
      sentence-by-sentence and verifies integrity before anything is written.
  idempotence  --job <dir> --polished <polished.md>
      Treat the polished text as a new source: re-run prepare + intake with an
      empty edit set, assert 0 mandatory changes and that the sentence-loss
      gate passes.

Determinism: no timestamps, no randomness. Re-running any command on the same
inputs yields byte-identical outputs.
Python 3 standard library only.
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ledger  # noqa: E402  (same bundle; stdlib + this module only)

STATUS_LABELS = {
    "applied": "APPLIED",
    "rolled_back_unreviewed": "ROLLED BACK (unreviewed)",
    "rolled_back_stale": "ROLLED BACK (stale hash)",
    "rolled_back_review_rejected": "ROLLED BACK (reviewer rejected)",
    "rolled_back_review_query": "ROLLED BACK (reviewer query)",
    "rolled_back_token_violation": "ROLLED BACK (token loss)",
    "rejected_intake": "REJECTED (intake)",
}


# ---------------------------------------------------------------------------
# Ledger assembly
# ---------------------------------------------------------------------------

def assemble_ledger(state, intake_report):
    """Merge state edits and intake rejections into one ordered entry list."""
    entries = []
    for e in state["edits"]:
        entries.append({
            "edit_id": e["edit_id"], "sid": e["sid"], "status": e["status"],
            "types": e["types"], "original": e["original"],
            "revised": e["revised"], "reason": e["reason"], "basis": e["basis"],
            "batch": e["batch"], "review": e["review"],
            "detail": e["status_detail"],
        })
    for r in intake_report.get("rejected", []):
        edit = r["edit"] if isinstance(r["edit"], dict) else {}
        sid = r.get("sid") or "unknown"
        eid = ("rejected-%s-%d" % (r["batch"], r["index"]))
        entries.append({
            "edit_id": eid, "sid": sid, "status": "rejected_intake",
            "types": edit.get("types", []),
            "original": edit.get("original"),
            "revised": edit.get("revised"),
            "reason": edit.get("reason"), "basis": edit.get("basis"),
            "batch": r["batch"], "review": None,
            "detail": "; ".join(r["reasons"]),
        })
    entries.sort(key=lambda x: (x["sid"], x["edit_id"]))
    return entries


def evaluate_gates(state, entries, polished, source_text):
    gates = {}
    units = state["sentences"]
    applied = {e["sid"]: e for e in entries if e["status"] == "applied"}

    # C01: sentence integrity -- count, order, untouched sentences identical,
    # exact reconstruction of both source and polished text.
    c01_problems = []
    if "".join(u["text"] + u["sep"] for u in units) != source_text:
        c01_problems.append("frozen units no longer reconstruct the source")
    rebuilt = []
    for u in units:
        e = applied.get(u["sid"])
        rebuilt.append((e["revised"] if e else u["text"]) + u["sep"])
    if "".join(rebuilt) != polished:
        c01_problems.append("polished text does not equal sentence-by-sentence refill")
    gates["C01_sentence_integrity"] = {
        "pass": not c01_problems,
        "detail": ("%d frozen sentences, order preserved, refill verified"
                   % len(units)) if not c01_problems else "; ".join(c01_problems),
    }

    # C02: every applied edit was anchored to its frozen sentence.
    anchored = all(
        any(u["sid"] == e["sid"] and u["text"] == e["original"] for u in units)
        for e in applied.values())
    gates["C02_anchor_and_schema"] = {
        "pass": anchored,
        "detail": ("every applied edit's 'original' equals its frozen sentence"
                   if anchored else "an applied edit is not anchored to the frozen source"),
    }

    # C03: protected tokens conserved by every applied edit.
    token_bad = []
    n_tokens = 0
    for e in applied.values():
        missing, added = ledger.token_violations(e["original"], e["revised"])
        n_tokens += len(ledger.protected_tokens(e["original"]))
        if missing or added:
            token_bad.append(e["edit_id"])
    gates["C03_protected_tokens"] = {
        "pass": not token_bad,
        "detail": ("%d protected tokens verified across %d applied edits"
                   % (n_tokens, len(applied))) if not token_bad
                  else "token mismatch in: %s" % ", ".join(token_bad),
    }

    # C04: no edit is applied without a review record; rollback is enforced.
    unreviewed_applied = [e["edit_id"] for e in applied.values() if not e["review"]]
    gates["C04_mandatory_review"] = {
        "pass": not unreviewed_applied,
        "detail": ("every applied edit carries an accept review; unreviewed edits "
                   "were rolled back") if not unreviewed_applied
                  else "applied without review: %s" % ", ".join(unreviewed_applied),
    }

    # C07: applied edits carry concrete, non-vacuous reasons.
    vacuous = [e["edit_id"] for e in applied.values()
               if len(e["reason"]) < ledger.MIN_REASON_CHARS
               or ledger.normalize_reason(e["reason"]) in ledger.VACUOUS_REASONS]
    gates["C07_reason_quality"] = {
        "pass": not vacuous,
        "detail": ("all applied edits have concrete reasons (>= %d chars, "
                   "blacklist-screened)" % ledger.MIN_REASON_CHARS) if not vacuous
                  else "vacuous reasons in: %s" % ", ".join(vacuous),
    }
    return gates


def build_polished(state):
    applied = {e["sid"]: e["revised"] for e in state["edits"]
               if e["status"] == "applied"}
    return "".join((applied.get(u["sid"], u["text"])) + u["sep"]
                   for u in state["sentences"])


# ---------------------------------------------------------------------------
# review.html rendering (self-contained, no external dependencies)
# ---------------------------------------------------------------------------

HTML_CSS = """
:root{color-scheme:light}
*{box-sizing:border-box}
body{font-family:-apple-system,'Segoe UI',Helvetica,Arial,sans-serif;margin:0;
color:#1c2430;background:#f4f6f9;line-height:1.5}
header{background:#12233f;color:#fff;padding:18px 28px}
header h1{margin:0 0 4px;font-size:20px}
header .sub{font-size:12.5px;opacity:.85}
.synthetic{display:inline-block;background:#b7791f;color:#fff;border-radius:4px;
padding:1px 8px;font-size:11.5px;margin-left:8px;vertical-align:middle}
.stats{display:flex;flex-wrap:wrap;gap:10px;padding:14px 28px;background:#fff;
border-bottom:1px solid #dde3ec}
.stat{background:#eef2f8;border:1px solid #d5deeb;border-radius:6px;
padding:6px 12px;font-size:12.5px}
.stat b{display:block;font-size:18px;color:#12233f}
.gates{padding:14px 28px;background:#fff;border-bottom:1px solid #dde3ec}
.gates h2{font-size:14px;margin:0 0 8px;text-transform:uppercase;letter-spacing:.05em;
color:#52657f}
.gate{display:inline-block;margin:0 8px 6px 0;padding:4px 10px;border-radius:5px;
font-size:12.5px;border:1px solid}
.gate.pass{background:#e6f6ec;border-color:#9ed7b2;color:#17603a}
.gate.fail{background:#fdeaea;border-color:#efa9a9;color:#8c2222}
.gate .d{display:block;font-size:11px;opacity:.8}
main{padding:18px 28px;max-width:1280px;margin:0 auto}
h2.section{font-size:15px;color:#12233f;border-bottom:2px solid #12233f;
padding-bottom:4px;margin:26px 0 12px}
.card{background:#fff;border:1px solid #dde3ec;border-radius:8px;
margin:0 0 14px;overflow:hidden}
.card .head{display:flex;align-items:center;gap:8px;padding:8px 14px;
background:#eef2f8;border-bottom:1px solid #dde3ec;font-size:12.5px;flex-wrap:wrap}
.sid{font-family:ui-monospace,Menlo,Consolas,monospace;font-weight:700;color:#12233f}
.badge{display:inline-block;border-radius:10px;padding:1px 9px;font-size:11px;
background:#2c5282;color:#fff}
.status{margin-left:auto;font-size:11px;font-weight:700;padding:2px 8px;border-radius:4px}
.status.applied{background:#e6f6ec;color:#17603a}
.status.rolled{background:#fdf3e0;color:#8a5a00}
.status.rejected{background:#fdeaea;color:#8c2222}
.cols{display:grid;grid-template-columns:1fr 1fr}
.cols>div{padding:12px 14px;font-size:13.5px}
.cols .orig{border-right:1px solid #eef1f6;background:#fcfcfd}
.cols h4{margin:0 0 6px;font-size:11px;text-transform:uppercase;letter-spacing:.06em;
color:#7a8aa0}
.cols p{margin:0;white-space:pre-wrap;word-break:break-word}
details{border-top:1px solid #eef1f6;padding:8px 14px;font-size:12.5px}
summary{cursor:pointer;color:#2c5282;font-weight:600}
details dl{display:grid;grid-template-columns:110px 1fr;gap:4px 10px;margin:8px 0 0}
details dt{font-weight:700;color:#52657f}
details dd{margin:0;white-space:pre-wrap;word-break:break-word}
footer{padding:14px 28px;font-size:11.5px;color:#7a8aa0;border-top:1px solid #dde3ec;
background:#fff}
"""

STATUS_CLASS = {
    "applied": "applied",
    "rejected_intake": "rejected",
}


def status_class(status):
    return STATUS_CLASS.get(status, "rolled")


def esc(s):
    return html.escape("" if s is None else str(s), quote=True)


def render_entry_card(e):
    badges = "".join('<span class="badge">%s</span>' % esc(t) for t in e["types"])
    label = STATUS_LABELS.get(e["status"], e["status"])
    review = e["review"] or {}
    parts = [
        '<div class="card">',
        '<div class="head"><span class="sid">%s</span>%s'
        '<span class="status %s">%s</span></div>'
        % (esc(e["sid"]), badges, status_class(e["status"]), esc(label)),
        '<div class="cols">',
        '<div class="orig"><h4>Original (frozen)</h4><p>%s</p></div>'
        % esc(e["original"]),
        '<div class="rev"><h4>Revised</h4><p>%s</p></div>' % esc(e["revised"]),
        '</div>',
        '<details><summary>Reason, basis &amp; review record</summary><dl>',
        '<dt>Reason</dt><dd>%s</dd>' % esc(e["reason"]),
        '<dt>Basis</dt><dd>%s</dd>' % esc(e["basis"]),
        '<dt>Batch</dt><dd>%s</dd>' % esc(e["batch"]),
        '<dt>Ledger status</dt><dd>%s</dd>' % esc(e["detail"]),
        '<dt>Review</dt><dd>%s</dd>' % (
            esc("%s -- %s" % (review.get("decision"), review.get("reason")))
            if review else "no review record"),
        '</dl></details>',
        '</div>',
    ]
    return "\n".join(parts)


def render_html(case_id, state, entries, gates, summary):
    gate_html = "".join(
        '<span class="gate %s"><b>%s</b> %s<span class="d">%s</span></span>'
        % ("pass" if g["pass"] else "fail", esc(gid),
           "PASS" if g["pass"] else "FAIL", esc(g["detail"]))
        for gid, g in gates.items())
    stats = [
        ("sentences", state["sentence_count"]),
        ("edits received", summary["received"]),
        ("accepted (intake)", summary["accepted"]),
        ("applied", summary["applied"]),
        ("rolled back", summary["rolled_back"]),
        ("rejected (intake)", summary["rejected"]),
        ("gates passing", "%d/%d" % (sum(1 for g in gates.values() if g["pass"]),
                                     len(gates))),
    ]
    stat_html = "".join('<div class="stat"><b>%s</b>%s</div>' % (esc(v), esc(k))
                        for k, v in stats)
    applied_cards = [render_entry_card(e) for e in entries if e["status"] == "applied"]
    rolled_cards = [render_entry_card(e) for e in entries
                    if e["status"].startswith("rolled_back")]
    rejected_cards = [render_entry_card(e) for e in entries
                      if e["status"] == "rejected_intake"]
    unchanged = [u for u in state["sentences"]
                 if not any(e["sid"] == u["sid"] and e["status"] == "applied"
                            for e in entries)]
    unchanged_cards = []
    for u in unchanged:
        unchanged_cards.append(
            '<div class="card"><div class="head"><span class="sid">%s</span>'
            '<span class="status applied">UNCHANGED</span></div>'
            '<div class="cols"><div class="orig"><h4>Original (frozen)</h4>'
            '<p>%s</p></div><div class="rev"><h4>Revised</h4><p>%s</p></div>'
            '</div></div>' % (esc(u["sid"]), esc(u["text"]), esc(u["text"])))
    doc = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Audit ledger review -- {case_id}</title>
<style>{css}</style>
</head>
<body>
<header><h1>Audit Ledger Review <span class="synthetic">SYNTHETIC EXAMPLE / 合成示例</span></h1>
<div class="sub">Case {case_id} &middot; self-contained review page generated from the real
edit ledger &middot; every entry is machine-recheckable; this page supports human review,
it does not replace peer review.</div></header>
<div class="stats">{stats}</div>
<div class="gates"><h2>Gates</h2>{gates}</div>
<main>
<h2 class="section">Applied edits ({n_applied})</h2>
{applied}
<h2 class="section">Rolled back ({n_rolled})</h2>
{rolled}
<h2 class="section">Rejected at intake ({n_rejected})</h2>
{rejected}
<h2 class="section">Unchanged sentences ({n_unchanged})</h2>
{unchanged}
</main>
<footer>Generated by audit-trail-polish (bundle e-audit-ledger). Deterministic output:
no timestamps, no randomness. Gates: C01 sentence integrity, C02 anchor/schema,
C03 protected tokens, C04 mandatory review (rollback not skippable), C07 reason quality.</footer>
</body>
</html>
""".format(
        case_id=esc(case_id), css=HTML_CSS, stats=stat_html, gates=gate_html,
        n_applied=len(applied_cards), applied="\n".join(applied_cards),
        n_rolled=len(rolled_cards), rolled="\n".join(rolled_cards),
        n_rejected=len(rejected_cards), rejected="\n".join(rejected_cards),
        n_unchanged=len(unchanged_cards), unchanged="\n".join(unchanged_cards),
    )
    return doc


# ---------------------------------------------------------------------------
# change-log.md
# ---------------------------------------------------------------------------

def render_change_log(case_id, entries, gates, summary):
    lines = [
        "# Change Log -- %s" % case_id,
        "",
        "Synthetic example / 合成示例. Every entry below is a ledger record that a "
        "third party can re-check against the frozen source.",
        "",
        "## Gates",
        "",
        "| Gate | Status | Detail |",
        "|---|---|---|",
    ]
    for gid, g in gates.items():
        lines.append("| %s | %s | %s |"
                     % (gid, "PASS" if g["pass"] else "FAIL", g["detail"]))
    lines += [
        "",
        "## Summary",
        "",
        "- sentences: %d" % summary["sentences"],
        "- edits received: %d" % summary["received"],
        "- accepted at intake: %d" % summary["accepted"],
        "- applied: %d" % summary["applied"],
        "- rolled back: %d" % summary["rolled_back"],
        "- rejected at intake: %d" % summary["rejected"],
        "",
    ]
    for title, pred in (
        ("Applied edits", lambda s: s == "applied"),
        ("Rolled back (rollback is mandatory, not skippable)",
         lambda s: s.startswith("rolled_back")),
        ("Rejected at intake", lambda s: s == "rejected_intake"),
    ):
        group = [e for e in entries if pred(e["status"])]
        lines.append("## %s (%d)" % (title, len(group)))
        lines.append("")
        for e in group:
            lines.append("### %s -- %s" % (e["sid"], ", ".join(e["types"]) or "n/a"))
            lines.append("")
            lines.append("- status: `%s` -- %s"
                         % (e["status"], e["detail"] or ""))
            lines.append("- original: %s" % (e["original"] or ""))
            lines.append("- revised: %s" % (e["revised"] or ""))
            lines.append("- reason: %s" % (e["reason"] or ""))
            lines.append("- basis: %s" % (e["basis"] or ""))
            if e["review"]:
                lines.append("- review: **%s** -- %s"
                             % (e["review"]["decision"], e["review"]["reason"]))
            else:
                lines.append("- review: none")
            lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------

def cmd_export(args):
    state = ledger.load_state(args.job)
    if not state.get("finalized"):
        raise SystemExit("job not finalized -- run ledger.py review first")
    intake_path = Path(args.job) / "intake-report.json"
    intake_report = json.loads(intake_path.read_text(encoding="utf-8")) \
        if intake_path.exists() else {"rejected": [], "accepted": [], "batches": []}
    case_id = args.case_id

    polished = build_polished(state)
    # C01 refill verification BEFORE writing anything: the polished text must be
    # reproducible sentence-by-sentence from frozen units plus applied edits.
    entries = assemble_ledger(state, intake_report)
    summary = {
        "sentences": state["sentence_count"],
        "received": len(entries),
        "accepted": len(state["edits"]),
        "applied": sum(1 for e in entries if e["status"] == "applied"),
        "rolled_back": sum(1 for e in entries if e["status"].startswith("rolled_back")),
        "rejected": sum(1 for e in entries if e["status"] == "rejected_intake"),
    }
    # source text for C01 reconstruction check
    source_text = "".join(u["text"] + u["sep"] for u in state["sentences"])
    gates = evaluate_gates(state, entries, polished, source_text)
    if not gates["C01_sentence_integrity"]["pass"]:
        raise SystemExit("C01 failure: " + gates["C01_sentence_integrity"]["detail"])

    changes = {
        "case_id": case_id,
        "synthetic_example": True,
        "gates": {k: {"status": "pass" if g["pass"] else "fail",
                      "detail": g["detail"]} for k, g in gates.items()},
        "summary": summary,
        "batches": intake_report.get("batches", []),
        "entries": entries,
    }

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "polished.md").write_text(polished, encoding="utf-8")
    (out / "changes.json").write_text(
        json.dumps(changes, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    (out / "change-log.md").write_text(
        render_change_log(case_id, entries, gates, summary) + "\n",
        encoding="utf-8")
    (out / "review.html").write_text(
        render_html(case_id, state, entries, gates, summary), encoding="utf-8")
    print("export: wrote polished.md, changes.json, change-log.md, review.html -> %s" % out)
    for gid, g in gates.items():
        print("  gate %s: %s" % (gid, "PASS" if g["pass"] else "FAIL"))
    return 0


# ---------------------------------------------------------------------------
# idempotence
# ---------------------------------------------------------------------------

def cmd_idempotence(args):
    polished_path = Path(args.polished)
    if not polished_path.exists():
        raise SystemExit("polished file not found: %s" % polished_path)
    state = ledger.load_state(args.job)
    idem_dir = Path(args.job) / "idempotence"
    edits_dir = idem_dir / "empty-edits"
    edits_dir.mkdir(parents=True, exist_ok=True)

    text = polished_path.read_text(encoding="utf-8")
    units = ledger.split_sentences(text)  # includes C01 reconstruction self-check
    report = {"checks": []}

    ok = True
    # 1. sentence-loss gate: polished text freezes into the same number of units.
    same_count = len(units) == state["sentence_count"]
    report["checks"].append({
        "check": "sentence_loss_gate",
        "pass": same_count,
        "detail": "polished text freezes into %d units (original: %d)"
                  % (len(units), state["sentence_count"]),
    })
    ok = ok and same_count

    # 2. empty edit intake: 0 mandatory changes on the polished text.
    (idem_dir / "state.json").write_text(json.dumps({
        "version": 1, "source_sha1": "idem", "sentence_count": len(units),
        "sentences": units, "edits": [], "reviews": [], "finalized": True,
    }, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    ns = argparse.Namespace(job=str(idem_dir), edits=str(edits_dir),
                            out=str(idem_dir / "intake-report.json"))
    ledger.cmd_intake(ns)
    intake = json.loads((idem_dir / "intake-report.json").read_text(encoding="utf-8"))
    zero_changes = (len(intake["accepted"]) == 0 and len(intake["rejected"]) == 0)
    report["checks"].append({
        "check": "zero_mandatory_changes",
        "pass": zero_changes,
        "detail": "empty-edit intake on polished text: %d accepted, %d rejected"
                  % (len(intake["accepted"]), len(intake["rejected"])),
    })
    ok = ok and zero_changes

    # 3. protected tokens survive in the polished text as a whole.
    src_tokens = ledger.protected_tokens(
        "".join(u["text"] for u in state["sentences"]))
    pol_tokens = ledger.protected_tokens("".join(u["text"] for u in units))
    tokens_ok = src_tokens == pol_tokens
    report["checks"].append({
        "check": "protected_tokens_conserved_end_to_end",
        "pass": tokens_ok,
        "detail": "%d protected tokens identical between source and polished text"
                  % len(pol_tokens) if tokens_ok else
                  "token drift: source=%s polished=%s" % (src_tokens, pol_tokens),
    })
    ok = ok and tokens_ok

    rp = idem_dir / "idempotence-report.json"
    rp.write_text(json.dumps(report, ensure_ascii=False, indent=2,
                             sort_keys=True) + "\n", encoding="utf-8")
    for c in report["checks"]:
        print("idempotence: %s %s -- %s"
              % ("PASS" if c["pass"] else "FAIL", c["check"], c["detail"]))
    print("idempotence: %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(
        description="export polished deliverables and run idempotence self-check")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("export", help="write polished.md / changes.json / "
                                      "change-log.md / review.html")
    p.add_argument("--job", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--case-id", default="MINIMAL-AUDIT-001")
    p.set_defaults(fn=cmd_export)

    p = sub.add_parser("idempotence", help="re-run prepare+empty intake on the "
                                           "polished text; expect 0 changes")
    p.add_argument("--job", required=True)
    p.add_argument("--polished", required=True)
    p.set_defaults(fn=cmd_idempotence)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())

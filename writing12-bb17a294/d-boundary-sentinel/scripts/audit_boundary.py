#!/usr/bin/env python3
"""audit_boundary.py — audit a Chinese translation against a boundary ledger
produced by extract_markers.py, and emit boundary_audit.json.

Alignment: ledger records carry `sent_index`/`sent_total`; each record is
matched to the PROPORTIONALLY corresponding Chinese segment (split on 。！？),
center = (sent_index-1) * n_segments / sent_total, with a tolerance window of
+/- --tol segments around that center (default 1) to absorb marker-free
sentences and 1-to-n sentence re-mappings. If the ledger lacks the fields,
alignment falls back to a running pointer.

Checks per ledger sentence (window = matched segment +/- tol, joined):
  (a) source negation count > 0  -> a Chinese negation
      (不/无/没有/未/并非/不能/缺乏/而非/毫无/绝不) must appear in the window,
      else ERROR `negation_at_risk`.
  (b) every hedge class in the source must map to an accepted Chinese
      rendering from the built-in table (see HEDGE_MAP; may/might/could ->
      可能/或/或许; suggest -> 提示/表明/可能; approximately/about/around ->
      约/大约; up to -> 至多/高达(保留上限); at least -> 至少; likely ->
      很可能; unlikely -> 不太可能; ...), else ERROR `hedge_dropped`.
  (c) strong causal verbs rendered only with weak renderings, or weak causal
      verbs strengthened (证明/证实) -> WARNING `strength_shift`.
  (d) quantifier `only` -> 仅/只/唯 required, else ERROR `quantifier_at_risk`.
  (e) every citation marker of the sentence must survive (numeric verbatim;
      author-year keeps author + year, et al. -> 等 allowed), else ERROR
      `citation_lost`.
Additionally the whole window is scanned for Chinese absolute-strength words
(证明/证实/首次/突破性) whose SOURCE sentence contains no matching strong
marker -> WARNING `claim_added` (possible translator-added claim).

Every finding carries: sentence id, source sentence, kind, severity, verdict,
the translation window inspected, and a suggested human action. The agent
MUST resolve every ERROR (fix the translation) or queue it as a [待确认]
item in the deliverable and change_log.md.

Exit code: 0 when there are no ERROR findings (warnings allowed),
           1 when at least one ERROR exists, 2 on usage/IO failure.

Usage:
    python3 audit_boundary.py boundary_ledger.jsonl translation_zh.md
                              [-o boundary_audit.json] [--tol 1]
"""

import argparse
import json
import re
import sys

from cite_patterns import citation_preserved

ZH_NEGATION_RE = re.compile(r"不|无|没有|未|并非|不能|缺乏|而非|毫无|绝不")

# Accepted Chinese renderings per hedge class. Deviations are allowed only
# when recorded in change_log.md (see references/method.md).
HEDGE_MAP = {
    "possibility": ["可能", "或", "或许", "也许", "有望"],
    "suggestion": ["提示", "表明", "可能", "暗示"],
    "appearance": ["似乎", "看来", "貌似", "显得"],
    "approximation": ["约", "大约", "左右", "近"],
    "up_to": ["至多", "高达", "不超过", "最高", "上限"],
    "at_least": ["至少", "不少于", "不低于"],
    "at_most": ["至多", "最多", "不超过"],
    "potentially": ["潜在", "可能", "有望"],
    "likely": ["很可能", "可能", "有望", "大概率"],
    "unlikely": ["不太可能", "不大可能", "未必"],
}

STRONG_ZH = ["证明", "证实", "表明", "显示", "揭示", "明确", "确定", "确立"]
WEAK_ZH = ["相关", "关联", "一致", "符合", "提示"]
ONLY_ZH = ["仅", "只", "唯"]

# (zh pattern, source regex that licenses it, label)
ABSOLUTE_ZH = [
    (re.compile(r"证明|证实"),
     re.compile(r"\b(prove|proves|proved|proven|demonstrate|demonstrates|"
                r"demonstrated|confirm|confirms|confirmed|establish|"
                r"establishes|established)\b", re.I),
     "证明/证实 (absolute causal strength)"),
    (re.compile(r"首次"), re.compile(r"\bfirst\b", re.I),
     "首次 (first/novelty claim)"),
    (re.compile(r"突破性"), re.compile(r"\bbreakthrough\b", re.I),
     "突破性 (breakthrough claim)"),
]

_REF_HEADING_RE = re.compile(
    r"^\s*#{0,6}\s*(参考文献|参考资料|references)\b", re.I | re.M)


def zh_segments(text):
    """Split a Chinese (markdown) translation into segments: drop heading
    lines, stop at the reference-list heading, split on 。！？."""
    body_lines = []
    for ln in text.splitlines():
        if _REF_HEADING_RE.match(ln):
            break
        if ln.strip().startswith("#"):
            continue
        body_lines.append(ln)
    joined = "\n".join(body_lines)
    parts = re.split(r"(?<=[。！？!?])\s*", joined)
    return [p.strip() for p in parts if p.strip()]


def audit(ledger_path, translation_path, tol=1):
    with open(ledger_path, "r", encoding="utf-8") as f:
        records = [json.loads(line) for line in f if line.strip()]
    with open(translation_path, "r", encoding="utf-8") as f:
        zh_text = f.read()
    segs = zh_segments(zh_text)

    # body-only text for citation fallback (never match the reference list)
    m_ref = _REF_HEADING_RE.search(zh_text)
    zh_body = zh_text[:m_ref.start()] if m_ref else zh_text

    findings = []
    ptr = 0  # fallback running pointer when sent_index/sent_total are absent
    for rec in records:
        if rec.get("sent_index") and rec.get("sent_total") and segs:
            center = int((rec["sent_index"] - 1) * len(segs)
                         / max(1, rec["sent_total"]))
            center = min(center, len(segs) - 1)
        else:
            center = min(ptr, max(0, len(segs) - 1))
        ptr += 1
        lo = max(0, center - tol)
        hi = min(len(segs), center + tol + 1)
        window = "".join(segs[lo:hi])
        sid = rec["id"]
        src = rec["text"]
        mk = rec["markers"]

        def add(kind, severity, verdict, action, win=None):
            findings.append({
                "sentence_id": sid,
                "kind": kind,
                "severity": severity,
                "source_text": src,
                "translation_window": window if win is None else win,
                "verdict": verdict,
                "suggested_action": action,
            })

        # (a) negation preservation
        if len(mk["negation"]) > 0 and not ZH_NEGATION_RE.search(window):
            add("negation_at_risk", "error",
                "source has %d negation marker(s) %s but no Chinese negation "
                "(不/无/没有/未/并非/不能/缺乏/而非) found in the matched window"
                % (len(mk["negation"]), mk["negation"]),
                "Re-check the corresponding Chinese sentence; restore the "
                "negation (e.g. 不/没有/并非) or queue as [待确认].")

        # (b) hedge mapping
        for h in mk["hedge"]:
            accepted = HEDGE_MAP.get(h["class"], [])
            if accepted and not any(a in window for a in accepted):
                add("hedge_dropped", "error",
                    "hedge '%s' (class %s) has no accepted Chinese rendering "
                    "(%s) in the matched window"
                    % (h["term"], h["class"], "/".join(accepted)),
                    "Add the appropriate hedge rendering (see references/"
                    "method.md table) or record a justified deviation in "
                    "change_log.md; otherwise queue as [待确认].")

        # (c) causal strength drift
        for c in mk["causal_strength"]:
            strong_hits = [w for w in STRONG_ZH if w in window]
            weak_hits = [w for w in WEAK_ZH if w in window]
            absolute = [w for w in ("证明", "证实") if w in window]
            if c["class"] == "strong" and not strong_hits:
                add("strength_shift", "warning",
                    "strong causal verb '%s' not rendered with a strong "
                    "Chinese verb (证明/证实/表明/显示/...)%s"
                    % (c["term"],
                       "; weak-only rendering found: %s" % weak_hits
                       if weak_hits else ""),
                    "Confirm the rendering keeps strong causal force; fix or "
                    "queue as [待确认].")
            elif c["class"] == "weak":
                if absolute:
                    add("strength_shift", "warning",
                        "weak causal claim '%s' appears strengthened to %s"
                        % (c["term"], absolute),
                        "Downgrade to a weak rendering (与…相关/一致/符合); "
                        "never strengthen a claim.")
                elif not weak_hits:
                    add("strength_shift", "warning",
                        "weak causal marker '%s' has no weak Chinese "
                        "rendering (相关/关联/一致/符合/提示) in the window"
                        % c["term"],
                        "Add a weak rendering (e.g. 与……相关) or queue as "
                        "[待确认].")
            elif c["class"] == "moderate" and absolute:
                add("strength_shift", "warning",
                    "moderate causal verb '%s' appears strengthened to %s"
                    % (c["term"], absolute),
                    "Use 表明/显示/提示 instead of 证明/证实, or queue as "
                    "[待确认].")

        # (d) only-quantifier
        for q in mk["quantifier"]:
            if q.lower() == "only" and not any(w in window for w in ONLY_ZH):
                add("quantifier_at_risk", "error",
                    "quantifier 'only' not rendered with 仅/只/唯 in the "
                    "matched window",
                    "Restrict the scope with 仅/只 (e.g. 仅限…) or queue as "
                    "[待确认].")

        # (e) citation preservation
        for cit in mk["citation"]:
            if not (citation_preserved(cit, window)
                    or citation_preserved(cit, zh_body)):
                add("citation_lost", "error",
                    "citation marker %s (%s) not preserved in the translation"
                    % (cit["raw"], cit["kind"]),
                    "Restore the citation verbatim (numeric) or with author + "
                    "year (author-year; et al. -> 等 allowed); never drop or "
                    "invent citations.")

        # (extra) claim_added: absolute-strength words without source license.
        # Checked against the CENTER segment only (not the tolerance window),
        # so a neighbor sentence's legitimate 证明/证实 does not false-fire.
        focus = segs[center] if segs else ""
        for zh_rx, en_rx, label in ABSOLUTE_ZH:
            m = zh_rx.search(focus)
            if m and not en_rx.search(src):
                add("claim_added", "warning",
                    "translation window contains '%s' (%s) but the source "
                    "sentence has no matching strong wording"
                    % (m.group(0), label),
                    "Verify against the source; soften or delete the added "
                    "claim, or justify in change_log.md / queue as [待确认].",
                    win=focus)

    errors = sum(1 for f in findings if f["severity"] == "error")
    warnings = sum(1 for f in findings if f["severity"] == "warning")
    return {
        "summary": {
            "sentences_checked": len(records),
            "zh_segments": len(segs),
            "tolerance": tol,
            "errors": errors,
            "warnings": warnings,
            "status": "pass" if errors == 0 else "fail",
        },
        "findings": findings,
        "note": "Heuristic, recall-oriented audit; a human resolves all "
                "findings. Errors must be fixed or queued as [待确认].",
    }, errors


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("ledger", help="boundary_ledger.jsonl from extract_markers.py")
    ap.add_argument("translation", help="Chinese translation file (UTF-8, md/txt)")
    ap.add_argument("-o", "--output", default="boundary_audit.json")
    ap.add_argument("--tol", type=int, default=1,
                    help="alignment tolerance in segments (default 1)")
    args = ap.parse_args(argv)

    try:
        report, errors = audit(args.ledger, args.translation, args.tol)
    except (OSError, json.JSONDecodeError) as e:
        print("audit failed: %s" % e, file=sys.stderr)
        return 2
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    s = report["summary"]
    print("checked=%d errors=%d warnings=%d status=%s -> %s"
          % (s["sentences_checked"], s["errors"], s["warnings"],
             s["status"], args.output))
    for f in report["findings"]:
        print("  [%s] %s %s: %s" % (f["severity"], f["sentence_id"],
                                    f["kind"], f["verdict"]))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())

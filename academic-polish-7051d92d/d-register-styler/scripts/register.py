#!/usr/bin/env python3
"""register.py -- genre detection, register lint, and before/after scorecard.

Part of the genre-register-polish skill (direction D: register-styler).

Subcommands:
  detect    --task <task.md> --text <f> --out genre.json
      Identify the target genre (journal-abstract / thesis / grant-proposal /
      review-response / en-abstract / unknown). An explicit declaration in the
      task file wins; otherwise text signals decide. When evidence is weak the
      tool reports "unknown" with needs_confirmation=true instead of guessing.
  lint      --text <f> --genre <g> --out register-report.json
      Register check with four violation classes: colloquial, promotional,
      absolute, person-misuse. Refuses to run on genre "unknown".
  scorecard --before <report1> --after <report2> --out scorecard.json [--md f]
      Before/after comparison. Exit code 1 if total violations increased
      (the "polishing must not get more colloquial" gate).

Python 3 standard library only. Deterministic: no randomness, no timestamps,
stable ordering of all output lists.
"""
import argparse
import json
import os
import re
import sys
from collections import Counter

GENRES = ["journal-abstract", "thesis", "grant-proposal",
          "review-response", "en-abstract"]

# --------------------------------------------------------------------------
# genre detection
# --------------------------------------------------------------------------

TASK_GENRE_KEYWORDS = [
    ("grant-proposal", ["grant-proposal", "grant proposal", "基金", "申请书",
                        "项目申请", "基金申请"]),
    ("review-response", ["review-response", "reviewer response", "审稿回复",
                         "审稿意见", "response to reviewer", "rebuttal"]),
    ("journal-abstract", ["journal-abstract", "journal abstract", "期刊摘要",
                          "期刊论文摘要"]),
    ("en-abstract", ["en-abstract", "english abstract", "英文摘要"]),
    ("thesis", ["thesis", "dissertation", "学位论文"]),
]

# (genre, pattern, weight, human label)
TEXT_SIGNALS = [
    ("review-response", r"response to (the )?reviewer", 3, "'Response to Reviewer' heading"),
    ("review-response", r"reviewer\s*(#|no\.?)?\s*\d", 2, "reviewer numbering"),
    ("review-response", r"we thank the (reviewer|referee|editor)", 3, "courtesy formula"),
    ("review-response", r"\bcomment\s*[:：]", 1, "'Comment:' marker"),
    ("review-response", r"\bresponse\s*[:：]", 1, "'Response:' marker"),
    ("review-response", r"point-by-point", 2, "'point-by-point'"),
    ("grant-proposal", r"本项目", 3, "本项目"),
    ("grant-proposal", r"拟解决", 3, "拟解决"),
    ("grant-proposal", r"拟(开展|研究|采用|构建|建立|提出)", 2, "拟+verb"),
    ("grant-proposal", r"立项依据|研究内容|技术路线|创新点|关键科学问题", 2, "grant section term"),
    ("grant-proposal", r"自然科学基金|基金委|申请代码|申请书", 3, "funding-agency term"),
    ("thesis", r"学位论文|硕士学位|博士学位|攻读(硕士|博士)", 3, "degree term"),
    ("thesis", r"第\s*[0-9一二三四五六七八九十]+\s*章", 2, "chapter marker"),
    ("thesis", r"绪论|文献综述|致谢", 1, "thesis section term"),
    ("journal-abstract", r"摘\s*要\s*[:：]", 2, "摘要:"),
    ("journal-abstract", r"关键词\s*[:：]", 2, "关键词:"),
    ("journal-abstract", r"\bkeywords?\s*[:：]", 2, "Keywords:"),
    ("journal-abstract", r"\babstract\b", 1, "Abstract"),
    ("journal-abstract", r"\bdoi\b", 1, "DOI"),
    ("en-abstract", r"\bthis (paper|thesis|dissertation|study|work)\b", 2, "'this paper/study'"),
    ("en-abstract", r"\bwe (propose|present|develop|introduce|report)\b", 2, "'we propose/present'"),
    ("en-abstract", r"\b(dissertation|doctoral|master'?s thesis|degree of)\b", 3, "degree term (EN)"),
]


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _write_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def cmd_detect(args):
    text = _read(args.text)
    task = _read(args.task) if args.task else ""
    base = os.path.basename(args.text)

    declared, evidence = None, None
    if task:
        # 1) a task line naming this exact file wins
        for line in task.splitlines():
            if base in line:
                for g, kws in TASK_GENRE_KEYWORDS:
                    if any(k.lower() in line.lower() for k in kws):
                        declared, evidence = g, "task line: " + line.strip()
                        break
            if declared:
                break
        # 2) otherwise, if the whole task names exactly one genre, use it
        if not declared:
            hits = [g for g, kws in TASK_GENRE_KEYWORDS
                    if any(k.lower() in task.lower() for k in kws)]
            hits = list(dict.fromkeys(hits))
            if len(hits) == 1:
                declared = hits[0]
                evidence = "only genre mentioned in the task file"

    scores = {g: 0 for g in GENRES}
    signals = []
    for g, pat, w, label in TEXT_SIGNALS:
        n = len(re.findall(pat, text, flags=re.IGNORECASE))
        if n:
            scores[g] += w
            signals.append({"genre": g, "signal": label, "matches": n, "weight": w})
    # ASCII-dominant short text weakly suggests an English abstract
    if text:
        ascii_ratio = sum(1 for c in text if ord(c) < 128) / max(1, len(text))
        if ascii_ratio > 0.95:
            scores["en-abstract"] += 1
            signals.append({"genre": "en-abstract", "signal": "ASCII-dominant text",
                            "matches": 1, "weight": 1})

    best = max(scores.values()) if scores else 0
    winners = [g for g in GENRES if scores[g] == best and best > 0]
    if declared:
        genre, confidence, needs = declared, 0.95, False
    elif best >= 4 and len(winners) == 1:
        genre, confidence, needs = winners[0], 0.8, False
    elif best >= 3 and len(winners) == 1:
        genre, confidence, needs = winners[0], 0.6, False
    elif best >= 2 and len(winners) == 1:
        genre, confidence, needs = winners[0], 0.5, True
    else:
        genre, confidence, needs = "unknown", 0.0, True

    note = ""
    if needs and genre == "unknown":
        note = ("Genre could not be determined from the task file or text "
                "signals. Ask the user / confirm the target genre before "
                "running lint; do NOT force a guessed genre.")
    elif needs:
        note = ("Weak evidence for genre '%s'. Confirm with the user before "
                "applying genre rules." % genre)
    else:
        note = "Genre determined by %s." % ("task declaration" if declared
                                             else "text signals")

    out = {
        "text_file": args.text,
        "genre": genre,
        "confidence": confidence,
        "declared_in_task": bool(declared),
        "task_evidence": evidence,
        "text_signals": signals,
        "signal_scores": {g: scores[g] for g in GENRES if scores[g] > 0},
        "needs_confirmation": needs,
        "note": note,
    }
    _write_json(args.out, out)
    print("detect: genre=%s confidence=%.2f needs_confirmation=%s"
          % (genre, confidence, needs))
    return 0


# --------------------------------------------------------------------------
# register lint
# --------------------------------------------------------------------------

# category policy per genre: violation | warning
POLICY = {
    "journal-abstract": {"colloquial": "violation", "promotional": "violation",
                         "absolute": "violation", "person": "violation"},
    "en-abstract": {"colloquial": "violation", "promotional": "violation",
                    "absolute": "violation", "person": "violation"},
    "thesis": {"colloquial": "violation", "promotional": "violation",
               "absolute": "violation", "person": "violation"},
    # grant proposals tolerate promotion only with evidence -> warning
    "grant-proposal": {"colloquial": "violation", "promotional": "warning",
                       "absolute": "violation", "person": "violation"},
    "review-response": {"colloquial": "violation", "promotional": "warning",
                        "absolute": "violation", "person": "violation"},
}

CATEGORY_NORM = {
    "colloquial": "Academic register requires formal verbs and quantified degree adverbs.",
    "promotional": "Hype words need verifiable evidence (metric/benchmark/citation) or removal.",
    "absolute": "Unbounded claims must be qualified to what the evidence supports.",
    "person": "Person/address forms must match the genre convention.",
}

# (category, rule id, pattern, suggestion, flags, genre restriction, severity override)
RULES = [
    # ---- colloquial, English ----
    ("colloquial", "contraction-nt", r"\b\w+n't\b",
     "Expand the contraction (e.g. 'do not', 'does not').", None, "violation"),
    ("colloquial", "contraction-pron",
     r"\b(?:it|that|there|here|what|who|he|she|we|they|this|these|those|let)'(?:s|re|ve|ll|d|m)\b",
     "Expand the contraction (e.g. 'it is', 'we have').", None, "violation"),
    ("colloquial", "a-lot-of", r"\ba\s+lot\s+of\b",
     "Use 'many', 'numerous' or a quantified statement.", None, "violation"),
    ("colloquial", "lots-of", r"\blots\s+of\b",
     "Use 'many' / 'a large number of'.", None, "violation"),
    ("colloquial", "kind-sort-of", r"\b(?:kind|sort)\s+of\b",
     "Remove the hedge or quantify it.", None, "violation"),
    ("colloquial", "a-bit", r"\ba\s+bit\b",
     "Remove or quantify.", None, "violation"),
    ("colloquial", "just", r"\bjust\b",
     "Remove, or use 'only'/'merely' when a real limit is meant.", None, "violation"),
    ("colloquial", "really", r"\breally\b",
     "Remove the intensifier; state the fact.", None, "violation"),
    ("colloquial", "pretty-adv",
     r"\bpretty\s+(?:good|well|much|high|large|close|fast|accurate|stable)\b",
     "Replace the informal intensifier with a measured statement.", None, "violation"),
    ("colloquial", "get-pp",
     r"\b(?:get|gets|got|getting|gotten)\s+(?!ten\b|seven\b|often\b|even\b|eleven\b)[a-z]+(?:ed|en)\b",
     "Use a precise verb ('obtain', 'become', 'be + participle').", None, "violation"),
    ("colloquial", "stuff", r"\bstuff\b",
     "Name the material or items precisely.", None, "violation"),
    # ---- colloquial, Chinese ----
    ("colloquial", "gao", r"搞(?!笑)",
     "口语词；改为正式动词：建立/开展/制备/提出。", None, "violation"),
    ("colloquial", "nong", r"弄(?!虚作假)",
     "口语词；改为正式动词：获得/处理/完成。", None, "violation"),
    ("colloquial", "ting", r"挺(?!拔|进|立|住|身)",
     "口语程度词；改为‘较/相当/十分’或量化表述。", None, "violation"),
    ("colloquial", "tebie", r"特别(?!是|地|注明|强调)",
     "口语程度词；改为‘尤其/十分/显著’或删除。", None, "violation"),
    ("colloquial", "dongxi", r"东西|事儿",
     "口语泛指；给出具体名称。", None, "violation"),
    # ---- promotional ----
    ("promotional", "hype-en",
     r"\b(?:revolutionary|breakthrough|cutting-edge|game-changing|world-leading|world-class|unprecedented|first-ever|state-of-the-art)\b",
     "Remove the hype or attach verifiable evidence (metric, benchmark, citation).",
     None, None),
    ("promotional", "hype-zh",
     r"国际领先|国际一流|世界一流|国内首创|填补(国内|国际|该领域的)?空白|颠覆性|重大突破|遥遥领先|远超",
     "删除宣传语，或补充可验证证据（指标、对比、文献）。", None, None),
    # ---- absolute ----
    ("absolute", "always-never", r"\b(?:always|never)\b",
     "Qualify the claim or provide a proof/measurement.", None, "violation"),
    ("absolute", "completely-prove",
     r"\b(?:completely|totally|entirely|fully)\s+(?:prove[sd]?|demonstrate[sd]?|eliminate[sd]?|solve[sd]?|show[ns]?)\b",
     "Absolute claim; weaken to what the evidence shows.", None, "violation"),
    ("absolute", "guarantee", r"\bguarantee[sd]?\b",
     "Replace with a bounded statement unless a formal guarantee exists.", None, "violation"),
    ("absolute", "absolute-zh",
     r"彻底(解决|消除|避免|根绝|杜绝)?|完全(解决|消除|避免)|从根本上(解决|消除|杜绝)|绝对不?会|绝不(再)?|必将|百分之百|百分百",
     "无证据时改为有限定表述：‘显著缓解/有望/在……条件下’。", None, "violation"),
    # ---- person misuse ----
    ("person", "first-person-I", r"\bI\b",
     "Abstracts use 'we' or 'this paper/study'; avoid 'I'.", None, "violation"),
    ("person", "second-person", r"\b(?:you|your)\b",
     "Avoid addressing the reader; use impersonal phrasing.", None, "violation"),
    ("person", "wo", r"我(?!们)",
     "学术文体用‘本文/本项目/本研究’，不用‘我’。", None, "violation"),
    ("person", "women", r"我们",
     "期刊摘要/学位论文建议改用‘本文/本研究’（基金与审稿回复中‘我们’可接受）。",
     ["journal-abstract", "thesis"], "warning"),
]


def _snippet(text, start, end, width=22):
    s = max(0, start - width)
    e = min(len(text), end + width)
    return re.sub(r"\s+", " ", text[s:e]).strip()


def cmd_lint(args):
    genre = args.genre
    if genre == "unknown" or genre not in POLICY:
        print("lint: genre '%s' is unknown or unsupported; confirm the genre "
              "first (see register.py detect). Refusing to guess." % genre,
              file=sys.stderr)
        return 2
    text = _read(args.text)
    policy = POLICY[genre]
    violations = []

    for cat, rid, pat, sug, genres, sev_override in RULES:
        if genres and genre not in genres:
            continue
        severity = sev_override or policy[cat]
        for m in re.finditer(pat, text, flags=re.IGNORECASE):
            line = text.count("\n", 0, m.start()) + 1
            violations.append({
                "category": cat,
                "rule": rid,
                "severity": severity,
                "line": line,
                "offset": m.start(),
                "matched": m.group(0),
                "snippet": _snippet(text, m.start(), m.end()),
                "suggestion": sug,
                "genre_norm": CATEGORY_NORM[cat],
            })

    # genre-specific whole-text checks
    if genre == "review-response":
        if not re.search(r"we thank|thank (the )?(reviewer|referee|editor)",
                         text, flags=re.IGNORECASE):
            violations.append({
                "category": "person", "rule": "courtesy-missing",
                "severity": "violation", "line": 1, "offset": 0,
                "matched": "(whole text)",
                "snippet": _snippet(text, 0, min(len(text), 60)),
                "suggestion": ("Open with courteous framing, e.g. 'We thank "
                               "the reviewer for ...' and state 'We have "
                               "revised ...' for each point."),
                "genre_norm": CATEGORY_NORM["person"],
            })
        for m in re.finditer(
                r"\byou (are|were) (wrong|mistaken)\b|\bthe reviewer (is|was) wrong\b|\bobviously\b",
                text, flags=re.IGNORECASE):
            violations.append({
                "category": "person", "rule": "combative-tone",
                "severity": "violation",
                "line": text.count("\n", 0, m.start()) + 1,
                "offset": m.start(), "matched": m.group(0),
                "snippet": _snippet(text, m.start(), m.end()),
                "suggestion": ("Never state the reviewer is wrong; thank the "
                               "comment and show the revision or evidence."),
                "genre_norm": CATEGORY_NORM["person"],
            })

    violations.sort(key=lambda v: (v["line"], v["offset"], v["rule"]))
    counts = Counter()
    warnings = 0
    for v in violations:
        if v["severity"] == "warning":
            warnings += 1
        else:
            counts[v["category"]] += 1
    cat_counts = {c: counts.get(c, 0)
                  for c in ("colloquial", "promotional", "absolute", "person")}

    out = {
        "text_file": args.text,
        "genre": genre,
        "counts": cat_counts,
        "warning_count": warnings,
        "total_violations": sum(cat_counts.values()),
        "violations": violations,
        "notes": [
            "Heuristic rules: every hit needs agent adjudication in context; "
            "see references/register-taxonomy.md for decision boundaries.",
            "Warnings (e.g. promotional words in a grant proposal) are listed "
            "but not counted in total_violations.",
        ],
    }
    _write_json(args.out, out)
    print("lint: genre=%s total_violations=%d warnings=%d %s"
          % (genre, out["total_violations"], warnings, dict(cat_counts)))
    return 0


# --------------------------------------------------------------------------
# scorecard
# --------------------------------------------------------------------------

def cmd_scorecard(args):
    before = json.loads(_read(args.before))
    after = json.loads(_read(args.after))
    cats = ("colloquial", "promotional", "absolute", "person")
    b_counts = before.get("counts", {})
    a_counts = after.get("counts", {})
    delta_cat = {c: a_counts.get(c, 0) - b_counts.get(c, 0) for c in cats}
    b_total = before.get("total_violations", sum(b_counts.values()))
    a_total = after.get("total_violations", sum(a_counts.values()))
    gate = "pass" if a_total <= b_total else "fail"
    out = {
        "before": {"file": before.get("text_file"), "genre": before.get("genre"),
                   "counts": b_counts, "total_violations": b_total,
                   "warnings": before.get("warning_count", 0)},
        "after": {"file": after.get("text_file"), "genre": after.get("genre"),
                  "counts": a_counts, "total_violations": a_total,
                  "warnings": after.get("warning_count", 0)},
        "delta_per_category": delta_cat,
        "delta_total": a_total - b_total,
        "gate": gate,
        "rule": "after.total_violations must not exceed before.total_violations",
    }
    _write_json(args.out, out)
    if args.md:
        lines = [
            "## Register scorecard — %s" % (before.get("text_file") or "text"),
            "",
            "| category | before | after | Δ |",
            "|---|---|---|---|",
        ]
        for c in cats:
            lines.append("| %s | %d | %d | %+d |"
                         % (c, b_counts.get(c, 0), a_counts.get(c, 0),
                            delta_cat[c]))
        lines.append("| **total** | **%d** | **%d** | **%+d** |"
                     % (b_total, a_total, a_total - b_total))
        lines.append("| warnings (not counted) | %d | %d | %+d |"
                     % (before.get("warning_count", 0),
                        after.get("warning_count", 0),
                        after.get("warning_count", 0)
                        - before.get("warning_count", 0)))
        lines.append("")
        lines.append("Gate: **%s** — %s." % (gate.upper(), out["rule"]))
        lines.append("")
        with open(args.md, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
    print("scorecard: before=%d after=%d delta=%+d gate=%s"
          % (b_total, a_total, a_total - b_total, gate))
    return 0 if gate == "pass" else 1


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Genre detection, register lint, and before/after scorecard.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("detect", help="identify the target genre")
    p.add_argument("--task", help="task file (optional)")
    p.add_argument("--text", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_detect)

    p = sub.add_parser("lint", help="register check for a known genre")
    p.add_argument("--text", required=True)
    p.add_argument("--genre", required=True,
                   help="one of: %s, unknown" % ", ".join(GENRES))
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_lint)

    p = sub.add_parser("scorecard", help="before/after register comparison gate")
    p.add_argument("--before", required=True)
    p.add_argument("--after", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--md", help="optional markdown table output")
    p.set_defaults(func=cmd_scorecard)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""strength.py - hedging-strength profiling and drift comparison.

Part of the `strength-conserving-polish` skill (bundle B: strength-conservator).

What it does:
  * profile  : assign each sentence a five-level strength profile plus four
               guardrail dimensions (quantifier scope, negation scope,
               causality vs correlation, conditionals / scope adverbials).
  * compare  : given original and revised text (or an edits JSON), emit a
               per-sentence drift verdict:
               none | strengthened | weakened | scope-narrowed |
               scope-broadened | negation-changed | causality-changed

Honesty boundary: the cue lexicons are HEURISTICS. A "none" verdict does not
prove semantic equivalence, and a drift verdict is a trigger for human/agent
review, not a proof of semantic change. English cues are matched on word
boundaries (case-insensitive); Chinese cues are matched as substrings.

Python 3 standard library only. Deterministic: same input -> same bytes.
"""

import argparse
import difflib
import json
import re
import sys

# ---------------------------------------------------------------------------
# Cue lexicons (English + Chinese)
# ---------------------------------------------------------------------------

LEVEL_NAMES = {
    0: "speculative",
    1: "tentative",
    2: "reporting",
    3: "strong",
    4: "absolute",
}

# Five-level strength ladder. Level of a sentence = max level of its hits;
# a sentence with no cue defaults to level 2 (plain declarative reporting).
LADDER = {
    0: ["may", "might", "could", "suggest", "suggests", "suggested",
        "possibly", "perhaps", "potentially", "conceivably", "speculate",
        "speculates", "speculated",
        "可能", "或许", "也许", "推测", "疑似"],
    1: ["appears", "appear", "appeared", "seems", "seem", "seemed",
        "tend", "tends", "tended", "likely", "unlikely", "plausibly",
        "似乎", "看来", "倾向于"],
    2: ["indicates", "indicate", "indicated", "shows", "show", "showed",
        "demonstrates", "demonstrate", "demonstrated", "found", "observe",
        "observed", "report", "reported", "supports", "support",
        "implicates", "implicate",
        "表明", "显示", "发现", "提示", "观察到"],
    3: ["establishes", "establish", "established", "confirms", "confirm",
        "confirmed", "conclusively", "robustly",
        "证实", "确证", "确认"],
    4: ["proves", "prove", "proven", "proved", "always", "never", "must",
        "certainly", "definitely", "undoubtedly", "impossible", "inevitably",
        "证明", "必然", "总是", "绝对", "毫无疑问"],
}

# Quantifier scope, ranked narrow -> broad.
QUANTIFIERS = {
    "none": 0, "no": 0, "few": 1, "little": 1, "rare": 1,
    "several": 2, "some": 2, "certain": 2, "a subset of": 2,
    "many": 3, "numerous": 3,
    "most": 4, "majority": 4,
    "all": 5, "every": 5, "each": 5,
    "无": 0, "没有": 0, "少数": 1,
    "一些": 2, "部分": 2, "某些": 2, "若干": 2,
    "许多": 3, "多数": 4, "大多数": 4,
    "所有": 5, "全部": 5, "每个": 5,
}

NEGATIONS = ["not", "n't", "no", "never", "rarely", "seldom", "hardly",
             "scarcely", "without", "fail", "fails", "failed", "none",
             "不", "没", "没有", "未", "无", "很少", "罕见"]

CAUSAL = ["causes", "cause", "caused", "causing", "leads to", "lead to",
          "led to", "results in", "resulted in", "drives", "drove",
          "induces", "induced", "triggers", "triggered", "produces",
          "generates",
          "导致", "引起", "造成", "促使"]

CORRELATIONAL = ["is associated with", "associated with", "correlates with",
                 "correlated with", "correlate", "is linked to", "linked to",
                 "relates to", "related to", "tied to", "co-occurs",
                 "相关", "关联", "有关", "伴随"]

SCOPERS = ["in vitro", "in vivo", "ex vivo", "in silico", "in situ",
           "in this cohort", "in this study", "in this subset",
           "in this population", "in this sample",
           "under these conditions", "under these circumstances",
           "in mice", "in mouse", "in rats", "in humans", "in human",
           "in patients", "in animals", "preliminary", "pilot",
           "体外", "体内", "离体", "本研究", "本队列", "在该条件下", "初步"]

# Verdict priority when several drift kinds fire on one sentence.
DRIFT_PRIORITY = ["negation-changed", "causality-changed", "strengthened",
                  "weakened", "scope-broadened", "scope-narrowed"]


# ---------------------------------------------------------------------------
# Core machinery
# ---------------------------------------------------------------------------

def _is_cjk(text):
    return any("一" <= ch <= "鿿" for ch in text)


def find_cues(text, cues):
    """Return canonical (lower-cased) cues found in text, order-stable."""
    hits = []
    for cue in cues:
        if _is_cjk(cue):
            if cue in text:
                hits.append(cue)
        else:
            if re.search(r"\b" + re.escape(cue) + r"\b", text, re.IGNORECASE):
                hits.append(cue.lower())
    # de-duplicate, keep first occurrence order
    seen, out = set(), []
    for h in hits:
        if h not in seen:
            seen.add(h)
            out.append(h)
    return out


def normalize(text):
    return re.sub(r"\s+", " ", text.strip())


def split_sentences(text):
    """Naive sentence split; good enough for machine comparison of drafts."""
    text = normalize(text)
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [p.strip() for p in parts if p.strip()]


def profile_sentence(text):
    """Strength profile of one sentence."""
    level_hits = {}
    for level in sorted(LADDER):
        for cue in find_cues(text, LADDER[level]):
            level_hits[cue] = level
    level = max(level_hits.values()) if level_hits else 2
    quant_hits = {}
    for cue in find_cues(text, list(QUANTIFIERS)):
        quant_hits[cue] = QUANTIFIERS[cue]
    neg_hits = find_cues(text, NEGATIONS)
    causal_hits = find_cues(text, CAUSAL)
    corr_hits = find_cues(text, CORRELATIONAL)
    classes = []
    if causal_hits:
        classes.append("causal")
    if corr_hits:
        classes.append("correlational")
    scoper_hits = find_cues(text, SCOPERS)
    return {
        "level": level,
        "level_name": LEVEL_NAMES[level],
        "level_hits": level_hits,
        "quantifiers": quant_hits,
        "negations": neg_hits,
        "causality": {
            "classes": classes,
            "causal_hits": causal_hits,
            "correlational_hits": corr_hits,
        },
        "scopers": scoper_hits,
    }


def compare_sentences(orig, rev):
    """Compare one original sentence with its revision.

    Returns {"verdict": <primary>, "drifts": [{kind, direction, evidence}]}.
    """
    po, pr = profile_sentence(orig), profile_sentence(rev)
    drifts = []

    # 1. negation scope
    if set(po["negations"]) != set(pr["negations"]):
        drifts.append({
            "kind": "negation-changed",
            "direction": "negation-set-changed",
            "evidence": {"orig": po["negations"], "rev": pr["negations"]},
        })

    # 2. causality vs correlation
    if set(po["causality"]["classes"]) != set(pr["causality"]["classes"]):
        co, cr = set(po["causality"]["classes"]), set(pr["causality"]["classes"])
        if "causal" in cr and "causal" not in co:
            direction = "correlational-to-causal"
        elif "correlational" in cr and "correlational" not in co:
            direction = "causal-to-correlational"
        else:
            direction = "causality-class-changed"
        drifts.append({
            "kind": "causality-changed",
            "direction": direction,
            "evidence": {"orig": po["causality"], "rev": pr["causality"]},
        })

    # 3. ladder strength
    if pr["level"] > po["level"]:
        drifts.append({
            "kind": "strengthened",
            "direction": "level-%d-to-%d" % (po["level"], pr["level"]),
            "evidence": {"orig": po["level_hits"], "rev": pr["level_hits"]},
        })
    elif pr["level"] < po["level"]:
        drifts.append({
            "kind": "weakened",
            "direction": "level-%d-to-%d" % (po["level"], pr["level"]),
            "evidence": {"orig": po["level_hits"], "rev": pr["level_hits"]},
        })

    # 4. quantifier scope
    qo, qr = po["quantifiers"], pr["quantifiers"]
    if qo != qr:
        ro = max(qo.values()) if qo else None
        rr = max(qr.values()) if qr else None
        kind = None
        if ro is not None and (rr is None or rr > ro):
            kind = "scope-broadened"   # e.g. some -> all, some -> (bare noun)
        elif rr is not None and (ro is None or rr < ro):
            kind = "scope-narrowed"    # e.g. most -> some
        elif ro is not None and rr is not None and rr == ro and set(qo) != set(qr):
            kind = None                # same rank, different word (some->several): no drift
        if kind:
            drifts.append({
                "kind": kind,
                "direction": "quantifier-rank-%s-to-%s" % (ro, rr),
                "evidence": {"orig": qo, "rev": qr},
            })

    # 5. scope adverbials / conditionals
    so, sr = set(po["scopers"]), set(pr["scopers"])
    removed, added = sorted(so - sr), sorted(sr - so)
    if removed:
        drifts.append({
            "kind": "scope-broadened",
            "direction": "scope-condition-removed",
            "evidence": {"orig": sorted(so), "rev": sorted(sr),
                         "removed": removed},
        })
    if added:
        drifts.append({
            "kind": "scope-narrowed",
            "direction": "scope-condition-added",
            "evidence": {"orig": sorted(so), "rev": sorted(sr),
                         "added": added},
        })

    verdict = "none"
    for kind in DRIFT_PRIORITY:
        if any(d["kind"] == kind for d in drifts):
            verdict = kind
            break
    return {"verdict": verdict, "drifts": drifts,
            "orig_profile": po, "rev_profile": pr}


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def _dump(obj, out_path=None):
    text = json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if out_path:
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(text)
    else:
        sys.stdout.write(text)


def cmd_profile(args):
    with open(args.text, "r", encoding="utf-8") as fh:
        raw = fh.read()
    sentences = []
    for i, sent in enumerate(split_sentences(raw), start=1):
        sentences.append({
            "id": "s%04d" % i,
            "text": sent,
            "profile": profile_sentence(sent),
        })
    levels = {}
    for s in sentences:
        key = str(s["profile"]["level"])
        levels[key] = levels.get(key, 0) + 1
    _dump({"file": args.text, "sentences": sentences,
           "summary": {"n_sentences": len(sentences), "level_counts": levels}},
          args.out)
    return 0


def _align(orig_sents, rev_sents):
    """Align sentence lists; yields (orig_or_None, rev_or_None) pairs."""
    matcher = difflib.SequenceMatcher(a=[s.lower() for s in orig_sents],
                                      b=[s.lower() for s in rev_sents],
                                      autojunk=False)
    pairs = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                pairs.append((orig_sents[i1 + k], rev_sents[j1 + k]))
        elif tag == "replace":
            n = max(i2 - i1, j2 - j1)
            for k in range(n):
                o = orig_sents[i1 + k] if i1 + k < i2 else None
                r = rev_sents[j1 + k] if j1 + k < j2 else None
                pairs.append((o, r))
        elif tag == "delete":
            for k in range(i1, i2):
                pairs.append((orig_sents[k], None))
        elif tag == "insert":
            for k in range(j1, j2):
                pairs.append((None, rev_sents[k]))
    return pairs


def cmd_compare(args):
    pairs_in = []
    if args.edits:
        with open(args.edits, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        items = payload if isinstance(payload, list) else payload.get("pairs", [])
        for i, item in enumerate(items, start=1):
            pairs_in.append({"id": item.get("id", "p%04d" % i),
                             "orig": item.get("orig", ""),
                             "rev": item.get("rev", "")})
    else:
        with open(args.orig, "r", encoding="utf-8") as fh:
            orig_sents = split_sentences(fh.read())
        with open(args.rev, "r", encoding="utf-8") as fh:
            rev_sents = split_sentences(fh.read())
        for i, (o, r) in enumerate(_align(orig_sents, rev_sents), start=1):
            pairs_in.append({"id": "p%04d" % i, "orig": o, "rev": r})

    pairs_out = []
    counts = {}
    for pair in pairs_in:
        o, r = pair["orig"], pair["rev"]
        if o is None:
            entry = {"id": pair["id"], "orig": None, "rev": r,
                     "verdict": "added", "drifts": []}
        elif r is None:
            entry = {"id": pair["id"], "orig": o, "rev": None,
                     "verdict": "removed", "drifts": []}
        else:
            cmp_res = compare_sentences(o, r)
            entry = {"id": pair["id"], "orig": o, "rev": r,
                     "verdict": cmp_res["verdict"], "drifts": cmp_res["drifts"]}
        counts[entry["verdict"]] = counts.get(entry["verdict"], 0) + 1
        pairs_out.append(entry)
    _dump({"pairs": pairs_out,
           "summary": {"n_pairs": len(pairs_out), "verdict_counts": counts}},
          args.out)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Hedging-strength profiler and drift comparator "
                    "(strength-conserving-polish skill).")
    sub = parser.add_subparsers(dest="command", required=True)

    p_prof = sub.add_parser("profile",
                            help="Profile every sentence of a text file.")
    p_prof.add_argument("--text", required=True, help="UTF-8 text file.")
    p_prof.add_argument("--out", default=None, help="Write JSON here instead of stdout.")
    p_prof.set_defaults(func=cmd_profile)

    p_cmp = sub.add_parser("compare",
                           help="Compare original vs revised text, or an edits JSON.")
    src = p_cmp.add_mutually_exclusive_group(required=True)
    src.add_argument("--orig", help="Original text file (use with --rev).")
    src.add_argument("--edits", help='JSON file: [{"id","orig","rev"}, ...] '
                                     'or {"pairs": [...]}.')
    p_cmp.add_argument("--rev", help="Revised text file (required with --orig).")
    p_cmp.add_argument("--out", default=None, help="Write JSON here instead of stdout.")
    p_cmp.set_defaults(func=cmd_compare)

    args = parser.parse_args(argv)
    if args.command == "compare" and args.orig and not args.rev:
        parser.error("--rev is required when using --orig")
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""candidates.py — deterministic candidate alias-pair generation.

The script, not the model, does the scanning. It reads <work>/corpus.json
(produced by discover.py) and emits <work>/candidates.json with every candidate
alias pair the model must adjudicate:

  1. abbr-definition     "Full Name (ABBR)" at first mention, intra-paper
  2. abbr-cross-paper    abbreviation defined in paper A, used in paper B
  3. same-key-cross-paper identical normalization key across papers
  4. same-key-variant    same key, different surface form, same paper

Same-key pairs pass through the same-key-different-context trap detector:
when both sides carry non-empty, differing discriminator-token sets (compact /
mesoporous / anatase / ... within +/-5 tokens of the mention), the pair is
flagged trap=true so the adjudicator must justify any merge. Blocking by
guessed entity type (material/metric/method/unknown) buckets standalone
mentions before pairing; abbreviation-derived pairs bypass blocking because the
link is definitional.

Usage: python3 candidates.py --work /app/work
"""
import argparse
import re
import sys
from collections import defaultdict

import kgcommon as K

ABBR_RE = re.compile(r"\(([A-Za-z][A-Za-z0-9\-]{1,19})\)")
TOKEN_RE = re.compile(r"\S+")

# Trailing words that may never lead a full name (deterministic trim list).
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "based", "by", "certified", "for",
    "from", "in", "into", "is", "material", "of", "on", "or", "our", "reach",
    "reaching", "report", "show", "that", "the", "their", "these", "this",
    "to", "under", "use", "used", "using", "via", "was", "we", "were", "with",
}
MAX_FULLNAME_TOKENS = 6
WINDOW = 5  # tokens either side of a mention scanned for discriminators


def _looks_like_abbr(token):
    return any(ch.isupper() for ch in token) or any(ch.isdigit() for ch in token)


def _collect_full_name(prefix_text):
    """Collect the full name immediately preceding an '(ABBR)' parenthesis.

    Deterministic heuristic: walk whitespace tokens backwards; stop at a
    sentence-initial capitalized token, a stopword, a numeric-only token, or
    after MAX_FULLNAME_TOKENS tokens; then trim leading stopwords.
    """
    tokens = prefix_text.split()
    collected = []
    for tok in reversed(tokens):
        clean = tok.strip(".,;:")
        if not clean:
            continue
        if collected and len(collected) >= MAX_FULLNAME_TOKENS:
            break
        first = clean[0]
        if first.isupper() and not re.match(r"^[A-Z]-", clean):
            break  # sentence boundary (allow name-like "X-ray")
        if clean.casefold() in STOPWORDS:
            break
        if first.isdigit() and not re.search(r"[A-Za-z(]", clean):
            break  # pure number/unit such as "85%"
        if first == "(":
            break
        collected.append(clean)
    collected.reverse()
    while collected and collected[0].casefold() in STOPWORDS:
        collected.pop(0)
    return " ".join(collected)


def _classify_standalone(token):
    """Return mention kind for a standalone token, or None."""
    if len(token) < 2 or len(token) > 20:
        return None
    has_digit = any(ch.isdigit() for ch in token)
    n_upper = sum(1 for ch in token if ch.isupper())
    n_lower = sum(1 for ch in token if ch.islower())
    if token[0].isupper() and has_digit and n_upper >= 1:
        return "formula"
    if n_upper >= 2 and n_lower <= 1 and not has_digit:
        return "acronym"
    if "-" in token and any(seg[:1].isupper() for seg in token.split("-")[1:]):
        return "hyphenated"  # spiro-OMeTAD, Li-TFSI (not "UV-curable")
    return None


def _mention(source_id, paragraph_id, surface, kind, context):
    return {
        "surface": surface,
        "norm_key": K.norm_key(surface),
        "source_id": source_id,
        "paragraph_id": paragraph_id,
        "kind": kind,
        "context": context,
    }


def extract_mentions(corpus):
    """Scan all paragraphs; return (mentions, abbr_definitions)."""
    mentions = []
    definitions = []  # (full_mention, abbr_mention)
    seen = set()

    def add(m, priority):
        key = (m["norm_key"], m["surface"], m["source_id"], m["paragraph_id"])
        if key in seen:
            return None
        seen.add(key)
        mentions.append(m)
        return m

    for src in corpus["sources"]:
        sid = src["source_id"]
        for para in src["paragraphs"]:
            pid, text = para["paragraph_id"], para["text"]
            # --- rule: first-mention abbreviation definitions "Full (ABBR)" --
            for match in ABBR_RE.finditer(text):
                abbr = match.group(1)
                if not _looks_like_abbr(abbr):
                    continue
                full = _collect_full_name(text[:match.start()])
                if not full or full == abbr:
                    continue
                ctx = K.sentence_with(text, match.group(0))
                fm = add(_mention(sid, pid, full, "abbr-definition-full", ctx), 2)
                am = add(_mention(sid, pid, abbr, "abbr-definition-abbr", ctx), 2)
                if fm and am:
                    definitions.append((fm, am))
            # --- rule: standalone formula / acronym / hyphenated tokens ------
            tokens = text.split()
            for raw in tokens:
                tok = raw.strip(".,;:()[]\"'")
                if not tok:
                    continue
                kind = _classify_standalone(tok)
                if not kind:
                    continue
                ctx = K.sentence_with(text, tok)
                add(_mention(sid, pid, tok, "standalone-" + kind, ctx), 1)
    return mentions, definitions


def _discriminators(mention, paragraph_text):
    """Discriminator tokens within +/-WINDOW tokens of the mention."""
    sent = mention["context"]
    toks = sent.split()
    idxs = [i for i, t in enumerate(toks)
            if mention["surface"] in t.strip(".,;:()[]\"'")]
    found = set()
    for i in idxs:
        lo, hi = max(0, i - WINDOW), min(len(toks), i + WINDOW + 1)
        for t in toks[lo:hi]:
            clean = t.strip(".,;:()[]\"'").casefold()
            if clean in K.DISCRIMINATORS:
                found.add(clean)
    return found


def build_candidates(corpus):
    mentions, definitions = extract_mentions(corpus)
    para_text = {}
    para_sids = []
    for src in corpus["sources"]:
        para_sids.append(src["source_id"])
        for para in src["paragraphs"]:
            para_text[(src["source_id"], para["paragraph_id"])] = para["text"]

    for m in mentions:
        m["block"] = K.guess_type(m["surface"])

    by_key = defaultdict(list)
    for m in mentions:
        by_key[(m["block"], m["norm_key"])].append(m)
    for key in by_key:
        by_key[key].sort(key=lambda m: (m["source_id"], m["paragraph_id"], m["surface"]))

    pairs = []
    seen_pairs = set()

    def add_pair(kind, a, b, bypass_block=False):
        if not bypass_block and not K.block_compatible(a["block"], b["block"]):
            return
        sig = tuple(sorted([(a["norm_key"], a["source_id"]),
                            (b["norm_key"], b["source_id"])]))
        if sig in seen_pairs:
            return
        seen_pairs.add(sig)
        trap, trap_reason = False, None
        if kind.startswith("same-key"):
            da = _discriminators(a, para_text[(a["source_id"], a["paragraph_id"])])
            db = _discriminators(b, para_text[(b["source_id"], b["paragraph_id"])])
            if da and db and da != db:
                trap = True
                trap_reason = (
                    "same key but differing context discriminators: %s side {%s} vs %s side {%s}"
                    % (a["source_id"], ",".join(sorted(da)),
                       b["source_id"], ",".join(sorted(db))))
        pairs.append({
            "kind": kind,
            "block": a["block"] if a["block"] == b["block"] else "mixed",
            "a": a, "b": b,
            "trap": trap,
            "trap_reason": trap_reason,
            "priority_hint": "likely-merge" if kind == "abbr-definition" and not trap
                             else ("needs-careful-review" if trap else "review"),
        })

    # 1. intra-paper abbreviation definitions (definitional: bypass blocking)
    for fm, am in definitions:
        add_pair("abbr-definition", fm, am, bypass_block=True)

    def first_mention(key, source_id):
        cands = [m for (blk, k), ms in by_key.items() if k == key
                 for m in ms if m["source_id"] == source_id]
        cands.sort(key=lambda m: (m["paragraph_id"], m["surface"]))
        return cands[0] if cands else None

    # 2. abbreviation defined in one paper, used in another (definitional)
    for fm, am in definitions:
        for src in corpus["sources"]:
            if src["source_id"] == am["source_id"]:
                continue
            other = first_mention(am["norm_key"], src["source_id"])
            if other:
                add_pair("abbr-cross-paper", fm, other, bypass_block=True)

    # 3./4. same normalization key across papers, or variant forms intra-paper
    for (block, key), ms in sorted(by_key.items()):
        sids = sorted({m["source_id"] for m in ms})
        for i, sid_a in enumerate(sids):
            for sid_b in sids[i + 1:]:
                ma = first_mention(key, sid_a)
                mb = first_mention(key, sid_b)
                if ma and mb:
                    add_pair("same-key-cross-paper", ma, mb)
        forms = sorted({m["surface"] for m in ms})
        if len(forms) > 1:
            for sid in sids:
                local = [m for m in ms if m["source_id"] == sid]
                local_forms = sorted({m["surface"] for m in local})
                if len(local_forms) > 1:
                    reps = [next(m for m in local if m["surface"] == f)
                            for f in local_forms[:2]]
                    add_pair("same-key-variant", reps[0], reps[1])

    kind_order = {"abbr-definition": 0, "abbr-cross-paper": 1,
                  "same-key-cross-paper": 2, "same-key-variant": 3}
    pairs.sort(key=lambda p: (kind_order[p["kind"]], p["a"]["norm_key"],
                              p["a"]["source_id"], p["b"]["norm_key"],
                              p["b"]["source_id"]))
    for idx, pair in enumerate(pairs, 1):
        pair_sorted = {"pair_id": "P%02d" % idx}
        pair_sorted.update(pair)
        pairs[idx - 1] = pair_sorted

    paired = set()
    for p in pairs:
        paired.add((p["a"]["norm_key"], p["a"]["source_id"]))
        paired.add((p["b"]["norm_key"], p["b"]["source_id"]))
    unpaired = sorted(
        [{"surface": m["surface"], "norm_key": m["norm_key"],
          "source_id": m["source_id"], "paragraph_id": m["paragraph_id"],
          "block": m["block"]}
         for m in mentions if (m["norm_key"], m["source_id"]) not in paired],
        key=lambda d: (d["norm_key"], d["source_id"]))

    return {
        "notice": K.NOTICE,
        "pair_count": len(pairs),
        "pairs": pairs,
        "unpaired_mentions": unpaired,
        "stats": {
            "mentions": len(mentions),
            "abbr_definitions": len(definitions),
            "trap_flagged": sum(1 for p in pairs if p["trap"]),
        },
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--work", required=True, help="work directory")
    args = ap.parse_args(argv)
    try:
        corpus = K.load_json(args.work + "/corpus.json")
    except Exception as exc:
        print("ERROR: cannot read corpus.json (%s); run discover.py first" % exc,
              file=sys.stderr)
        return 2
    result = build_candidates(corpus)
    out = args.work + "/candidates.json"
    K.dump_json(result, out)
    print("candidates: %d pair(s) (%d trap-flagged) from %d mention(s) -> %s" % (
        result["pair_count"], result["stats"]["trap_flagged"],
        result["stats"]["mentions"], out))
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""align_bilingual.py — anchor-based alignment of source paragraphs to
translated paragraph blocks.

Source: paragraphs.jsonl (from segment_text.py).
Target: either a .txt with blank-line-separated blocks (optional leading
[[PXXXX]] tag per block; blocks are soft-unwrapped the same way as
segment_text.py merges lines), or a paragraphs.jsonl (--tgt-paras).

Anchors per paragraph:
  * numeric tokens      (regex \\d+(?:\\.\\d+)?)          -> token "n:<num>"
  * citation markers    ([n], [n, m], [n-m])               -> tokens "n:<num>"
    (citation numbers survive translation, so they double as anchors)
  * figure/table refs   Fig\\.?\\s*\\d+|Table\\s*\\d+|图\\s*\\d+|表\\s*\\d+
                                                        -> token "ft:<ref>"

Alignment algorithm (deterministic greedy walk over source paragraphs):
  * a [[PXXXX]] tag on a target block is honored unconditionally
    (two blocks carrying the same tag -> split-in-target)
  * otherwise, for source i, consider unused targets in window i +/- 3
    and pick the one maximizing anchor Jaccard overlap
  * overlap 0.0 with non-empty anchor sets on both sides -> anchor-mismatch
    (the pair is still formed, but flagged for human review)
  * consecutive source paragraphs folding into one target block ->
    merged-in-target (only when the UNION of their anchor sets fits the
    target strictly better than the next source paragraph fits it alone)
  * one source paragraph spread over consecutive target blocks ->
    split-in-target
  * leftover source paragraphs -> missing-translation (BLOCKER, exit 1)
  * leftover target blocks     -> extra-translation   (warning)
  * a target index lower than any previously used index -> order-swap
    (warning)

Output: alignment.json + align_report.json; exit code 1 iff any
missing-translation exists, else 0. See references/alignment_format.md.
"""
import argparse
import json
import os
import re
import sys

NUM_RE = re.compile(r"\d+(?:\.\d+)?")
CITE_RE = re.compile(r"\[(\d+(?:\s*[-,]\s*\d+)*)\]")
FIGTAB_RE = re.compile(
    r"Fig\.?\s*\d+|Table\s*\d+|图\s*\d+|表\s*\d+", re.IGNORECASE)
TAG_RE = re.compile(r"^\s*\[\[(P\d{4})\]\]")
WINDOW = 3


def anchors(text):
    """Extract the anchor token set of a paragraph."""
    found = set()
    for m in NUM_RE.finditer(text):
        found.add("n:" + m.group(0))
    for m in CITE_RE.finditer(text):
        inner = re.sub(r"\s+", "", m.group(1))
        for part in re.split(r"[-,]", inner):
            if part:
                found.add("n:" + part)
    for m in FIGTAB_RE.finditer(text):
        found.add("ft:" + re.sub(r"\s+", "", m.group(0)))
    return found


def jaccard(a, b):
    if not a and not b:
        return 1.0
    union = a | b
    if not union:
        return 1.0
    return len(a & b) / float(len(union))


def parse_txt_blocks(path):
    """Blank-line separated blocks with optional leading [[PXXXX]] tag."""
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        raw = fh.read()
    blocks = []
    for chunk in re.split(r"\n\s*\n", raw):
        lines = [ln.strip() for ln in chunk.split("\n") if ln.strip()]
        if not lines:
            continue
        tag = None
        m = TAG_RE.match(lines[0])
        if m:
            tag = m.group(1)
            lines = lines[1:]
        blocks.append({"tag": tag, "text": " ".join(lines)})
    return blocks


def load_jsonl(path):
    rows = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def best_unused(j_from, j_to, used, score_fn, skip=()):
    """Return (best_index, best_score) over unused targets in [j_from, j_to),
    excluding indices in skip. Returns (-1, -1.0) when nothing available."""
    best_j, best_s = -1, -1.0
    for j in range(max(0, j_from), min(j_to, len(used))):
        if used[j] or j in skip:
            continue
        s = score_fn(j)
        if s > best_s:
            best_j, best_s = j, s
    return best_j, best_s


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", required=True, help="source paragraphs.jsonl")
    ap.add_argument("--tgt", help="target .txt (blank-line blocks)")
    ap.add_argument("--tgt-paras", help="target paragraphs.jsonl")
    ap.add_argument("--out", required=True, help="alignment.json output")
    ap.add_argument("--report", required=True, help="align_report.json output")
    args = ap.parse_args()

    if bool(args.tgt) == bool(args.tgt_paras):
        sys.stderr.write("ERROR: pass exactly one of --tgt / --tgt-paras\n")
        sys.exit(2)

    src = load_jsonl(args.src)
    if args.tgt_paras:
        tgts = [{"tag": p.get("seg_id"), "text": p["text"]}
                for p in load_jsonl(args.tgt_paras)]
    else:
        tgts = parse_txt_blocks(args.tgt)

    n_src, n_tgt = len(src), len(tgts)
    src_anchors = [anchors(p["text"]) for p in src]
    tgt_anchors = [anchors(t["text"]) for t in tgts]

    used = [False] * n_tgt
    pairs = []
    missing, extra = [], []
    anchor_mismatch, order_swaps = [], []
    merged, split = [], []

    max_used = -1

    def note_swap(sid, j):
        nonlocal max_used
        if j < max_used:
            order_swaps.append(sid)
        max_used = max(max_used, j)

    i = 0
    while i < n_src:
        sid = src[i]["seg_id"]

        # -- 1) honor explicit [[PXXXX]] tags ------------------------------
        tagged = [j for j, t in enumerate(tgts)
                  if t["tag"] == sid and not used[j]]
        if tagged:
            status = "split-in-target" if len(tagged) > 1 else "aligned"
            if len(tagged) > 1:
                split.append(sid)
            for j in tagged:
                used[j] = True
                note_swap(sid, j)
            score = max(jaccard(src_anchors[i], tgt_anchors[j])
                        for j in tagged)
            pairs.append({"src_id": sid, "tgt_ids": tagged,
                          "status": status,
                          "anchor_score": round(score, 4)})
            i += 1
            continue

        # -- 2) greedy windowed anchor match --------------------------------
        lo, hi = i - WINDOW, i + WINDOW + 1
        j, score = best_unused(lo, hi, used,
                               lambda jj: jaccard(src_anchors[i],
                                                  tgt_anchors[jj]))
        if j < 0:
            # nothing unused inside the window: honest fallback over the
            # full target range (may produce an order-swap warning)
            j, score = best_unused(0, n_tgt, used,
                                   lambda jj: jaccard(src_anchors[i],
                                                      tgt_anchors[jj]))
        if j < 0:
            missing.append(sid)
            pairs.append({"src_id": sid, "tgt_ids": [],
                          "status": "missing-translation",
                          "anchor_score": 0.0})
            i += 1
            continue

        used[j] = True
        note_swap(sid, j)
        status = "aligned"
        if src_anchors[i] and tgt_anchors[j] and score == 0.0:
            status = "anchor-mismatch"

        # -- 3) merge: following sources folding into the same target -------
        # gated on a confident initial pairing: a weakly-anchored pair
        # (score < 0.5) must never swallow the paragraphs that follow it,
        # otherwise one mis-anchor could hide a whole run of deletions.
        group = [i]
        combined = set(src_anchors[i])
        k = i + 1
        while score >= 0.5 and k < n_src:
            # never swallow a source that carries an explicit tag
            if any(t["tag"] == src[k]["seg_id"] and not used[tt]
                   for tt, t in enumerate(tgts)):
                break
            alone = jaccard(src_anchors[k], tgt_anchors[j])
            combined_fit = jaccard(combined, tgt_anchors[j])
            union = jaccard(combined | src_anchors[k], tgt_anchors[j])
            alt_j, alt_s = best_unused(k - WINDOW, k + WINDOW + 1, used,
                                       lambda jj, kk=k: jaccard(
                                           src_anchors[kk], tgt_anchors[jj]),
                                       skip=(j,))
            alt_s = max(alt_s, 0.0)
            # fold src[k] into target j only when src[k] itself carries
            # anchors into j, fits j at least as well as any alternative,
            # and strictly improves the combined fit
            if alone > 0 and alone >= alt_s and union > combined_fit:
                combined |= src_anchors[k]
                group.append(k)
                k += 1
            else:
                break

        # -- 4) split: this source spread over consecutive targets ----------
        tgt_ids = [j]
        if len(group) == 1:
            while True:
                prev = jaccard(src_anchors[i], tgt_anchors[tgt_ids[-1]])
                nxt_j, nxt_s = best_unused(tgt_ids[-1] + 1,
                                           tgt_ids[-1] + WINDOW + 1,
                                           used,
                                           lambda jj: jaccard(
                                               src_anchors[i],
                                               tgt_anchors[jj]))
                if nxt_j >= 0 and nxt_s > 0 and nxt_s >= prev:
                    used[nxt_j] = True
                    note_swap(sid, nxt_j)
                    tgt_ids.append(nxt_j)
                else:
                    break

        # -- 5) record -------------------------------------------------------
        if len(group) > 1:
            status = "merged-in-target"
        elif len(tgt_ids) > 1:
            status = "split-in-target"
        if status == "anchor-mismatch":
            anchor_mismatch.append(sid)
        elif status == "merged-in-target":
            merged.extend(src[kk]["seg_id"] for kk in group)
        elif status == "split-in-target":
            split.append(sid)
        first = True
        for kk in group:
            sc = score if first else jaccard(src_anchors[kk],
                                             tgt_anchors[j])
            pairs.append({"src_id": src[kk]["seg_id"],
                          "tgt_ids": tgt_ids if first else [j],
                          "status": status,
                          "anchor_score": round(sc, 4)})
            first = False
        i = group[-1] + 1

    # -- leftover target blocks ----------------------------------------------
    for j in range(n_tgt):
        if not used[j]:
            extra.append(j)
            pairs.append({"src_id": None, "tgt_ids": [j],
                          "status": "extra-translation",
                          "anchor_score": 0.0})

    aligned = sum(1 for p in pairs
                  if p["src_id"] is not None
                  and p["status"] != "missing-translation")
    result = {
        "pairs": pairs,
        "coverage": {
            "source_paragraphs": n_src,
            "aligned": aligned,
            "missing": missing,
            "extra": extra,
            "anchor_mismatch": anchor_mismatch,
            "order_swaps": order_swaps,
        },
    }
    report = {
        "source_paragraphs": n_src,
        "target_blocks": n_tgt,
        "pairs": len(pairs),
        "missing_translation": missing,
        "extra_translation": extra,
        "anchor_mismatch": anchor_mismatch,
        "order_swaps": order_swaps,
        "merged_in_target": merged,
        "split_in_target": split,
    }
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
    with open(args.report, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    print("aligned %d/%d source paragraphs | missing=%d extra=%d "
          "anchor_mismatch=%d order_swaps=%d"
          % (aligned, n_src, len(missing), len(extra),
             len(anchor_mismatch), len(order_swaps)))
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())

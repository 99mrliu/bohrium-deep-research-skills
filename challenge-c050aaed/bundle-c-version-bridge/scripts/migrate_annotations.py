#!/usr/bin/env python3
"""migrate_annotations.py -- migrate annotations across document versions.

For every annotation whose file is NOT the canonical member of its cluster
in the version graph, align its anchored_text against the canonical file's
page texts (difflib.SequenceMatcher best fixed-length window over each
normalized page) and classify:

  migrated  ratio >= 0.9  -> record target file/page/char offsets + ratio
  shifted   0.7 <= ratio < 0.9 -> record best page + offsets + uncertainty
  orphaned  ratio < 0.7   -> keep on the old version, say why
  native    annotation already sits on the canonical member
  error     processing failed (e.g. canonical page texts missing)

Two annotations are NEVER merged. Each output record keeps annotation_id,
the source file hash and the target file hash.

Inputs:
  --annotations  JSONL, one object per line: {annotation_id, file,
                 file_sha256, page, type, anchored_text, contents}
  --texts-dir    extracted page texts: <filekey>/page-NNN.txt
  --graph        version_graph.json produced by version_graph.py
  --out          output migration_report.jsonl (one record per annotation)

Deterministic: annotations processed in sorted annotation_id order, first
best window wins on ties, ratios rounded to 4 decimals, no wall-clock.
Exit codes: 0 ok, 2 usage/input error, 3 degraded (some records have
status "error"; report still written).
"""
import argparse
import difflib
import json
import os
import re
import sys

SCHEMA = "version-bridge/migration_report@1"
GENERATOR = "migrate_annotations.py 1.0.0"
MIGRATED = 0.9
SHIFTED = 0.7
REQUIRED_KEYS = ("annotation_id", "file", "file_sha256", "page", "type",
                 "anchored_text", "contents")


def eprint(*a):
    print(*a, file=sys.stderr)


def normalize(s):
    return re.sub(r"\s+", " ", s.lower()).strip()


def load_pages(texts_dir, relpath):
    """{page_number: normalized page text} for a file (may be empty)."""
    d = os.path.join(texts_dir, relpath.replace("/", "__"))
    pages = {}
    if os.path.isdir(d):
        for name in sorted(os.listdir(d)):
            m = re.fullmatch(r"page-(\d+)\.txt", name)
            if m:
                with open(os.path.join(d, name), encoding="utf-8") as fh:
                    pages[int(m.group(1))] = normalize(fh.read())
    return pages


def best_window(anchor, text):
    """Best alignment of anchor inside text -> (start_offset, ratio).

    Exact substring match short-circuits at ratio 1.0. Otherwise a fixed
    window of len(anchor) is slid over the text (stride len/4, final
    position included) and the best SequenceMatcher ratio wins.
    Offsets refer to the normalized page text.
    """
    idx = text.find(anchor)
    if idx >= 0:
        return idx, 1.0
    L = len(anchor)
    if len(text) <= L:
        r = difflib.SequenceMatcher(None, anchor, text,
                                    autojunk=False).ratio()
        return 0, r
    stride = max(1, L // 4)
    positions = list(range(0, len(text) - L + 1, stride))
    last = len(text) - L
    if positions[-1] != last:
        positions.append(last)
    best_i, best_r = 0, -1.0
    for i in positions:
        r = difflib.SequenceMatcher(None, anchor, text[i:i + L],
                                    autojunk=False).ratio()
        if r > best_r:
            best_i, best_r = i, r
    return best_i, best_r


def locate(anchor_norm, pages):
    """Best (page, start, ratio) across pages, sorted page order, first best
    wins on exact ties."""
    best = (None, None, -1.0)
    for p in sorted(pages):
        i, r = best_window(anchor_norm, pages[p])
        if r > best[2]:
            best = (p, i, r)
    return best


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Migrate annotations from non-canonical document "
                    "versions onto the canonical member of each cluster.")
    ap.add_argument("--annotations", required=True, help="annotations.jsonl")
    ap.add_argument("--texts-dir", required=True,
                    help="dir with <filekey>/page-NNN.txt extracted texts")
    ap.add_argument("--graph", required=True, help="version_graph.json")
    ap.add_argument("--out", required=True, help="output migration_report.jsonl")
    args = ap.parse_args(argv)

    try:
        with open(args.graph, encoding="utf-8") as fh:
            graph = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        eprint(f"error: cannot read graph: {exc}")
        return 2
    node_sha = {n["relpath"]: n["sha256"] for n in graph.get("nodes", [])}
    cluster_of = {}
    clusters = {}
    for c in graph.get("clusters", []):
        clusters[c["cluster_id"]] = c
        for m in c["members"]:
            cluster_of[m] = c["cluster_id"]

    annots = []
    try:
        with open(args.annotations, encoding="utf-8") as fh:
            for ln, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    annots.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    eprint(f"error: annotations line {ln}: {exc}")
                    return 2
    except OSError as exc:
        eprint(f"error: cannot read annotations: {exc}")
        return 2
    annots.sort(key=lambda a: str(a.get("annotation_id", "")))

    had_error = False
    records = []
    for a in annots:
        missing = [k for k in REQUIRED_KEYS if k not in a]
        if missing:
            records.append({
                "schema": SCHEMA,
                "annotation_id": str(a.get("annotation_id", "<missing>")),
                "status": "error",
                "source": {"file": a.get("file"),
                           "file_sha256": a.get("file_sha256"),
                           "page": a.get("page")},
                "target": None,
                "ratio": None,
                "note": "annotation record missing keys: " + ", ".join(missing),
            })
            had_error = True
            continue

        aid = str(a["annotation_id"])
        f = str(a["file"])
        sha = str(a["file_sha256"])
        anchor_norm = normalize(str(a["anchored_text"]))
        rec = {
            "schema": SCHEMA,
            "annotation_id": aid,
            "type": a["type"],
            "contents": a["contents"],
            "source": {"file": f, "file_sha256": sha, "page": a["page"]},
        }
        if f in node_sha and node_sha[f] != sha:
            rec.setdefault("warnings", []).append(
                "annotation file_sha256 does not match the manifest hash for "
                f"{f}: annotation may have been taken on different bytes")

        cid = cluster_of.get(f)
        canonical = clusters[cid]["canonical"] if cid else f

        if cid is None:
            rec.update(status="native", ratio=1.0,
                       target={"file": f, "file_sha256": sha,
                               "page": a["page"],
                               "char_start": None, "char_end": None},
                       note="file not present in version graph; treated as a "
                            "standalone (native) document")
        elif f == canonical:
            target = {"file": f, "file_sha256": sha, "page": a["page"],
                      "char_start": None, "char_end": None}
            pages = load_pages(args.texts_dir, f)
            if pages:
                p, i, r = locate(anchor_norm, pages)
                if p is not None:
                    target.update(page=p, char_start=i,
                                  char_end=i + len(anchor_norm))
            rec.update(status="native", ratio=1.0, target=target)
        else:
            pages = load_pages(args.texts_dir, canonical)
            if not pages:
                rec.update(status="error", ratio=None, target=None,
                           note=f"no extracted page texts for canonical file "
                                f"'{canonical}'; cannot attempt migration")
                had_error = True
            else:
                p, i, r = locate(anchor_norm, pages)
                r4 = round(r, 4)
                target = {"file": canonical,
                          "file_sha256": node_sha.get(canonical),
                          "page": p,
                          "char_start": i,
                          "char_end": i + len(anchor_norm)}
                if r >= MIGRATED:
                    rec.update(status="migrated", ratio=r4, target=target)
                elif r >= SHIFTED:
                    rec.update(status="shifted", ratio=r4, target=target,
                               uncertainty=f"best match ratio {r4} in "
                                           f"[{SHIFTED}, {MIGRATED}); the text "
                                           "was probably reworded between "
                                           "versions; verify placement by hand")
                else:
                    rec.update(status="orphaned", ratio=r4, target=None,
                               note=f"anchored_text not found on canonical "
                                    f"version '{canonical}' (best ratio {r4} "
                                    f"< {SHIFTED}); kept on source version "
                                    f"'{f}' where it remains searchable")
        records.append(rec)

    counts = {}
    for r in records:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    try:
        with open(args.out, "w", encoding="utf-8") as fh:
            for r in records:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    except OSError as exc:
        eprint(f"error: cannot write output: {exc}")
        return 2

    eprint("migrate_annotations: " + ", ".join(
        f"{k}={counts[k]}" for k in sorted(counts)))
    return 3 if had_error else 0


if __name__ == "__main__":
    sys.exit(main())

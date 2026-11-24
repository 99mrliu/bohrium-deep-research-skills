#!/usr/bin/env python3
"""version_graph.py -- build an evidence-typed identity graph over a library.

Every node is a file from an inventory manifest. Edges carry an explicit type
plus the evidence that justifies them:

  byte_duplicate  same sha256 AND same basename
  renamed_copy    same sha256, different basename
  version_of      different sha256, same normalized name stem, AND character
                  5-gram Jaccard similarity of the concatenated normalized
                  page texts >= 0.6 (the ratio is reported as evidence).
                  Directed older -> newer by mtime; mtime is weak evidence
                  and is flagged under "uncertainty" in the output.

Pairs with the same normalized stem but similarity < 0.6 (or unavailable
texts) are reported in "metadata_conflicts" as suspect mislabeled files.

Inputs:
  --manifest   JSON manifest, schema version-bridge/manifest@1:
               {"schema": ..., "files": [{"relpath", "sha256", "size",
               "mtime"} , ...]} with mtime an ISO-8601 UTC string.
  --texts-dir  extracted page texts: <texts-dir>/<filekey>/page-NNN.txt where
               filekey = relpath with '/' replaced by '__'.
  --out        output path for the version graph JSON.

Deterministic: stable sorts everywhere, no wall-clock, ratios rounded to 4
decimals. Exit codes: 0 ok, 2 usage/input error, 3 degraded (output still
written; some evidence could not be obtained -- see "degraded" in output).
"""
import argparse
import json
import os
import re
import sys

SCHEMA = "version-bridge/version_graph@1"
GENERATOR = "version_graph.py 1.0.0"
SIM_THRESHOLD = 0.6
NGRAM = 5
CANONICAL_RULE = ("newest mtime wins; ties broken by shortest relpath, "
                  "then by lexicographic order (all comparisons stable)")
MTIME_NOTE = ("mtime is weak evidence of version order: copies, syncs and "
              "re-downloads rewrite it. Prefer explicit version notes in the "
              "case materials (task.md / attached notes) when present.")
STOP_TOKENS = {"copy", "final", "new", "old", "backup", "draft", "latest"}


def eprint(*a):
    print(*a, file=sys.stderr)


def norm_stem(relpath):
    """Normalized name stem: basename minus extension, lowercased, with
    separators, version markers (v1, 2, ...) and noise words removed."""
    base = relpath.rsplit("/", 1)[-1]
    stem = base.rsplit(".", 1)[0] if "." in base else base
    toks = [t for t in re.split(r"[^a-z0-9]+", stem.lower()) if t]
    toks = [t for t in toks
            if t not in STOP_TOKENS and not re.fullmatch(r"v?\d+", t)]
    return " ".join(toks)


def filekey(relpath):
    return relpath.replace("/", "__")


def normalize_text(s):
    return re.sub(r"\s+", " ", s.lower()).strip()


def load_text(texts_dir, relpath, cache):
    """Concatenated normalized page text for a file, or None if unavailable."""
    if relpath in cache:
        return cache[relpath]
    d = os.path.join(texts_dir, filekey(relpath))
    text = None
    if os.path.isdir(d):
        parts = []
        for name in sorted(os.listdir(d)):
            if re.fullmatch(r"page-\d+\.txt", name):
                with open(os.path.join(d, name), encoding="utf-8") as fh:
                    parts.append(fh.read())
        if parts:
            text = normalize_text(" ".join(parts))
    cache[relpath] = text
    return text


def ngrams(s, n):
    if not s:
        return set()
    if len(s) < n:
        return {s}
    return {s[i:i + n] for i in range(len(s) - n + 1)}


def jaccard(a, b):
    if not a and not b:
        return None
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a) + len(b) - inter
    return inter / union if union else None


class Dsu:
    def __init__(self, items):
        self.p = {x: x for x in items}

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if rb < ra:
            ra, rb = rb, ra
        self.p[rb] = ra


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Build an evidence-typed version-identity graph from a "
                    "file inventory manifest and extracted page texts.")
    ap.add_argument("--manifest", required=True,
                    help="inventory manifest JSON (version-bridge/manifest@1)")
    ap.add_argument("--texts-dir", required=True,
                    help="dir with <filekey>/page-NNN.txt extracted page texts")
    ap.add_argument("--out", required=True, help="output version_graph.json")
    args = ap.parse_args(argv)

    try:
        with open(args.manifest, encoding="utf-8") as fh:
            manifest = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        eprint(f"error: cannot read manifest: {exc}")
        return 2
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        eprint("error: manifest has no non-empty 'files' list")
        return 2

    nodes = []
    seen = set()
    for i, f in enumerate(files):
        try:
            rel = str(f["relpath"])
            sha = str(f["sha256"])
            size = int(f["size"])
            mtime = str(f["mtime"])
        except (KeyError, TypeError, ValueError) as exc:
            eprint(f"error: manifest files[{i}] invalid: {exc}")
            return 2
        if rel in seen:
            eprint(f"error: duplicate relpath in manifest: {rel}")
            return 2
        seen.add(rel)
        nodes.append({"relpath": rel, "sha256": sha, "size": size,
                      "mtime": mtime, "stem": norm_stem(rel)})
    nodes.sort(key=lambda n: n["relpath"])
    info = {n["relpath"]: n for n in nodes}

    dsu = Dsu([n["relpath"] for n in nodes])
    edges = []
    conflicts = []
    degraded = []
    uncertainty = [MTIME_NOTE]

    # --- hash-based edges: byte_duplicate / renamed_copy ---
    by_hash = {}
    for n in nodes:
        by_hash.setdefault(n["sha256"], []).append(n)
    for sha in sorted(by_hash):
        group = sorted(by_hash[sha], key=lambda n: n["relpath"])
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i], group[j]
                same_name = (a["relpath"].rsplit("/", 1)[-1]
                             == b["relpath"].rsplit("/", 1)[-1])
                edges.append({
                    "type": "byte_duplicate" if same_name else "renamed_copy",
                    "from": a["relpath"],
                    "to": b["relpath"],
                    "evidence": {
                        "sha256": sha,
                        "note": "identical file bytes" + (
                            "" if same_name else " under different names"),
                    },
                })
                dsu.union(a["relpath"], b["relpath"])

    # --- stem+text edges: version_of, plus metadata conflicts ---
    cache = {}
    by_stem = {}
    for n in nodes:
        if n["stem"]:
            by_stem.setdefault(n["stem"], []).append(n)
    for stem in sorted(by_stem):
        group = sorted(by_stem[stem], key=lambda n: n["relpath"])
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i], group[j]
                if a["sha256"] == b["sha256"]:
                    continue  # already typed as a duplicate pair
                ta = load_text(args.texts_dir, a["relpath"], cache)
                tb = load_text(args.texts_dir, b["relpath"], cache)
                if ta is None or tb is None:
                    missing = [n["relpath"] for n, t in ((a, ta), (b, tb))
                               if t is None]
                    conflicts.append({
                        "type": "similarity_unavailable",
                        "files": [a["relpath"], b["relpath"]],
                        "stem": stem,
                        "text_similarity": None,
                        "reason": ("same normalized name stem but page texts "
                                   "are missing for: " + ", ".join(missing)),
                    })
                    degraded.append("page texts missing for: "
                                    + ", ".join(missing))
                    continue
                sim = jaccard(ngrams(ta, NGRAM), ngrams(tb, NGRAM))
                sim_r = round(sim, 4) if sim is not None else None
                if sim is not None and sim >= SIM_THRESHOLD:
                    if (a["mtime"], a["relpath"]) <= (b["mtime"], b["relpath"]):
                        older, newer = a, b
                    else:
                        older, newer = b, a
                    edges.append({
                        "type": "version_of",
                        "from": older["relpath"],
                        "to": newer["relpath"],
                        "evidence": {
                            "normalized_stem": stem,
                            "text_similarity": sim_r,
                            "similarity_method": "character 5-gram Jaccard "
                                                 "over normalized concatenated "
                                                 "page texts",
                            "older_mtime": older["mtime"],
                            "newer_mtime": newer["mtime"],
                            "direction_basis": "mtime (weak evidence; see "
                                               "uncertainty)",
                        },
                    })
                    dsu.union(a["relpath"], b["relpath"])
                else:
                    conflicts.append({
                        "type": "suspected_mislabel",
                        "files": [a["relpath"], b["relpath"]],
                        "stem": stem,
                        "text_similarity": sim_r,
                        "reason": ("same normalized name stem but text "
                                   f"similarity {sim_r} < {SIM_THRESHOLD}; "
                                   "suspect mislabeled file"),
                    })

    # --- clusters (documents) with canonical member ---
    comp = {}
    for n in nodes:
        comp.setdefault(dsu.find(n["relpath"]), []).append(n["relpath"])
    clusters = []
    for root in sorted(comp):
        members = sorted(comp[root])
        maxmt = max(info[m]["mtime"] for m in members)
        cands = [m for m in members if info[m]["mtime"] == maxmt]
        canonical = min(cands, key=lambda r: (len(r), r))
        clusters.append({
            "cluster_id": "",
            "members": members,
            "canonical": canonical,
            "canonical_rule": CANONICAL_RULE,
        })
    clusters.sort(key=lambda c: c["canonical"])
    for k, c in enumerate(clusters):
        c["cluster_id"] = f"c{k + 1}"

    edges.sort(key=lambda e: (e["type"], e["from"], e["to"]))
    conflicts.sort(key=lambda c: (c["type"], c["files"]))
    if degraded:
        uncertainty.append(
            "some files had no extracted page texts, so text-similarity "
            "evidence is incomplete; see metadata_conflicts and degraded")

    out = {
        "schema": SCHEMA,
        "generator": GENERATOR,
        "params": {"similarity_threshold": SIM_THRESHOLD, "ngram": NGRAM,
                   "stem_stop_tokens": sorted(STOP_TOKENS)},
        "nodes": nodes,
        "edges": edges,
        "clusters": clusters,
        "metadata_conflicts": conflicts,
        "uncertainty": uncertainty,
        "degraded": sorted(set(degraded)),
    }
    try:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(out, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
    except OSError as exc:
        eprint(f"error: cannot write output: {exc}")
        return 2

    eprint(f"version_graph: {len(nodes)} nodes, {len(edges)} edges, "
           f"{len(clusters)} clusters, {len(conflicts)} metadata conflicts")
    return 3 if degraded else 0


if __name__ == "__main__":
    sys.exit(main())

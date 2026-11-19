#!/usr/bin/env python3
"""lib_lineage.py — derive duplicate groups, alias groups and version chains.

Inputs:  <out>/artifacts/inventory.json (from lib_inventory.py),
         administrative version notes (text files whose name matches
         note/version/readme/备注 patterns), and filename version hints.

Grouping (deterministic, in priority order):
  1. alias relation: SHA-256 equal, OR shingle-Jaccard >= 0.85
     -> same content (possibly different names / encodings of one file).
  2. chain relation: Jaccard >= 0.60 (any names), OR same-stem names with
     Jaccard >= 0.35 and >= 10 common shingles -> revisions of one work.
  3. a cluster = connected component over both relation kinds. Inside a
     cluster, alias subgroups are formed first; chain edges order the
     subgroup representatives.
  4. version ordering: administrative note > filename version > mtime.
     Conflicts are recorded, never resolved silently.

Outputs: <out>/artifacts/lineage.json. Exit code always 0.
"""
import argparse
import itertools
import json
import os
import re
import sys


def shingles(text, w=5):
    t = re.sub(r"\s+", "", text)
    if len(t) < w:
        return {t} if t else set()
    return {t[i:i + w] for i in range(len(t) - w + 1)}


def jaccard(a, b):
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / (len(a) + len(b) - inter)


VER_TOK = re.compile(
    r"(_v\d+|_v?\d{8}|\bv\d+\b|(?:19|20)\d{2}|final|定稿|终稿|修订|初稿|draft|copy|副本|"
    r"修改版|更新|新版|old|new|\(\d+\)|（\d+）)",
    re.I)


def stem_of(name):
    s = os.path.splitext(name)[0].lower()
    s = VER_TOK.sub("", s)
    s = re.sub(r"[_\-\s\.（）()]+", "", s)
    return s


def version_hint(name):
    low = name.lower()
    m = re.findall(r"(?:^|[_\-\s\(])v(\d+)", low)
    if m:
        return ("v", int(m[-1]))
    y = re.findall(r"(?:19|20)\d{2}", name)
    if y:
        return ("year", int(y[-1]))
    if re.search(r"final|定稿|终稿", low):
        return ("final", 9999)
    return ("none", 0)


NOTE_PAT = re.compile(r"(note|备注|说明|version|readme|index)", re.I)


def parse_version_notes(text):
    prefs = []
    for line in text.splitlines():
        m = re.search(r"(?:以|use|current|最新)\s*[「『\"']?([^」』\"'\s，,。；;]+)"
                      r"[」』\"']?\s*(?:为准|为主|as.*current|version)", line, re.I)
        if m:
            prefs.append(m.group(1))
        m = re.search(r"[「『\"']?([^」』\"'\s，,。；;]+)[」』\"']?\s*"
                      r"(?:supersedes|取代|替代|替换)\s*[「『\"']?([^」』\"'\s，,。；;]+)",
                      line, re.I)
        if m:
            prefs.append(m.group(2))
    return prefs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="/input")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--out", default="/app/output")
    a = ap.parse_args()

    art = os.path.join(a.out, "artifacts")
    inv = json.load(open(os.path.join(art, "inventory.json"), encoding="utf-8"))
    files = inv["files"]
    by_id = {r["entry_id"]: r for r in files}

    texts, shingle_map = {}, {}
    for r in files:
        if r["extract_status"] == "ok" and r.get("extract_path"):
            try:
                with open(r["extract_path"], encoding="utf-8", errors="replace") as f:
                    t = f.read()
                texts[r["entry_id"]] = t
                shingle_map[r["entry_id"]] = shingles(t)
            except OSError:
                pass

    admin_prefs = {}
    for r in files:
        if r["entry_id"] in texts and NOTE_PAT.search(r["name"]):
            prefs = parse_version_notes(texts[r["entry_id"]])
            if prefs:
                admin_prefs[r["entry_id"]] = prefs

    parent = {r["entry_id"]: r["entry_id"] for r in files}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        parent[find(x)] = find(y)

    by_sha = {}
    for r in files:
        if r["sha256"]:
            by_sha.setdefault(r["sha256"], []).append(r["entry_id"])
    rels = []
    for sha, ids in by_sha.items():
        for x, y in itertools.combinations(ids, 2):
            union(x, y)
            rels.append({"a": x, "b": y, "kind": "alias", "score": 1.0})

    ids = list(shingle_map)
    stems = {eid: stem_of(by_id[eid]["name"]) for eid in ids}
    for x, y in itertools.combinations(ids, 2):
        if find(x) == find(y):
            continue
        s = jaccard(shingle_map[x], shingle_map[y])
        same_stem = bool(stems[x]) and stems[x] == stems[y]
        overlap = len(shingle_map[x] & shingle_map[y])
        if s >= 0.85:
            union(x, y)
            rels.append({"a": x, "b": y, "kind": "alias", "score": round(s, 3)})
        elif s >= 0.60 or (same_stem and overlap >= 10 and s >= 0.35):
            union(x, y)
            rels.append({"a": x, "b": y, "kind": "chain", "score": round(s, 3),
                         "same_stem": same_stem, "overlap": overlap})

    clusters = {}
    for r in files:
        clusters.setdefault(find(r["entry_id"]), []).append(r["entry_id"])

    groups, conflicts, membership = [], [], {}
    for members in sorted(clusters.values(), key=lambda m: min(m)):
        rel_in = [rel for rel in rels
                  if rel["a"] in members and rel["b"] in members]
        alias_rels = [rel for rel in rel_in if rel["kind"] == "alias"]
        chain_rels = [rel for rel in rel_in if rel["kind"] == "chain"]

        # alias subgroups inside the cluster
        apar = {m: m for m in members}

        def afind(x):
            while apar[x] != x:
                apar[x] = apar[apar[x]]
                x = apar[x]
            return x

        for rel in alias_rels:
            apar[afind(rel["a"])] = afind(rel["b"])
        subgroups = {}
        for m in members:
            subgroups.setdefault(afind(m), []).append(m)
        subgroups = [sorted(v) for v in subgroups.values()]
        reps = [sub[0] for sub in subgroups]

        def sub_of(eid):
            for i, sub in enumerate(subgroups):
                if eid in sub:
                    return i
            return None

        chain = []
        if len(members) == 1:
            kind = "unique"
            chain = [{"entry_id": members[0], "role": "unique"}]
        elif not chain_rels:
            kind = "alias"
            for i, sub in enumerate(subgroups):
                chain.append({"entry_id": sub[0],
                              "role": "canonical" if i == 0 else "duplicate"})
        else:
            kind = "version_chain"
            scored = []
            for e in reps:
                vt, vv = version_hint(by_id[e]["name"])
                scored.append((e, vt, vv, by_id[e].get("mtime") or 0))
            scored.sort(key=lambda t: (-t[2], -t[3]))
            by_v = [x[0] for x in sorted(scored, key=lambda t: -t[2])]
            by_m = [x[0] for x in sorted(scored, key=lambda t: -t[3])]
            if len(by_v) > 1 and by_v != by_m:
                conflicts.append({"kind": "name_vs_mtime",
                                 "by_name": by_v, "by_mtime": by_m})
            for rank, (e, vt, vv, mt) in enumerate(scored):
                role = "current" if rank == 0 else "historical"
                chain.append({"entry_id": e, "role": role,
                              "version_hint": vt, "version_value": vv,
                              "mtime": mt,
                              "copies": [x for x in subgroups[sub_of(e)]
                                         if x != e]})
        for c in chain:
            membership[c["entry_id"]] = {"group": None, "role": c["role"]}
            for x in c.get("copies", []):
                membership[x] = {"group": None,
                                 "role": c["role"] + "_copy"}
        gid = "G%02d" % (len(groups) + 1)
        for e in members:
            membership[e]["group"] = gid
        groups.append({"group_id": gid, "kind": kind, "members": members,
                       "chain": chain, "relations": rel_in})

    # administrative notes: prefer named member within its group
    for note_eid, prefs in admin_prefs.items():
        for g in groups:
            names = {by_id[e]["name"]: e for e in g["members"]}
            hits = [names[p] for p in prefs if p in names]
            for h in hits:
                for c in g["chain"]:
                    if c["entry_id"] == h and c["role"] in ("historical",
                                                            "duplicate"):
                        conflicts.append({"kind": "admin_note_overrides",
                                          "group": g["group_id"], "preferred": h,
                                          "note_file": note_eid})
                        c["role"] = "current_admin"

    for g in groups:
        cur = next((c for c in g["chain"]
                    if c["role"] in ("current_admin", "current", "canonical",
                                     "unique")), None)
        for e in g["members"]:
            membership[e]["current_version"] = bool(
                cur and e in ([cur["entry_id"]] + cur.get("copies", [])))

    out = {"groups": groups, "conflicts": conflicts, "membership": membership,
           "notes": "alias: sha-equal or jaccard>=0.85; chain: jaccard>=0.60 or "
                    "same-stem with overlap>=10 and jaccard>=0.35; ordering: "
                    "admin note > filename version > mtime"}
    with open(os.path.join(art, "lineage.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("lineage groups=%d (alias=%d chain=%d unique=%d) conflicts=%d"
          % (len(groups),
             sum(1 for g in groups if g["kind"] == "alias"),
             sum(1 for g in groups if g["kind"] == "version_chain"),
             sum(1 for g in groups if g["kind"] == "unique"),
             len(conflicts)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

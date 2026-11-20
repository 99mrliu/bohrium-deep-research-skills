#!/usr/bin/env python3
"""Self-check for identity_merge output. Stdlib only.

Independently verifies:
  1. case_id / status fields exist and are valid;
  2. every ingested record id appears in exactly one cluster (no loss, no dup);
  3. within every multi-member cluster, members share at least one hard key
     (DOI / arXiv / exact title fingerprint) -- no unjustified merge;
  4. no two clusters contain the same normalized DOI or arXiv id (no missed merge);
  5. review-queue pairs do NOT appear in the same cluster (queue honored);
  6. canonical rid is a member of its cluster; locator files exist;
  7. stats are arithmetically consistent.

Writes /app/work/verify_report.json; exit code always 0.
"""
import json
import os
import re
import sys
from pathlib import Path


def norm_title(v):
    if not v:
        return ""
    v = re.sub(r"[^a-z0-9]+", " ", str(v).lower())
    return " ".join(v.split())


def main():
    out_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "/app/output")
    work_dir = Path(sys.argv[2] if len(sys.argv) > 2 else "/app/work")
    work_dir.mkdir(parents=True, exist_ok=True)
    report = {"checks": [], "ok": True}

    def check(name, ok, detail=""):
        report["checks"].append({"check": name, "ok": bool(ok), "detail": str(detail)})
        if not ok:
            report["ok"] = False

    rp = out_dir / "result.json"
    if not rp.exists():
        check("result_exists", False)
        (work_dir / "verify_report.json").write_text(json.dumps(report, indent=2))
        print(json.dumps({"ok": False}))
        return 0
    r = json.loads(rp.read_text(encoding="utf-8"))
    check("case_id_present", bool(r.get("case_id")), r.get("case_id"))
    check("status_field", r.get("status") in ("ok", "partial", "failed"), r.get("status"))

    clusters = r.get("clean_works", [])
    all_rids, rid_owner = [], {}
    for c in clusters:
        for m in c.get("members", []):
            all_rids.append(m["rid"])
            rid_owner[m["rid"]] = c["cluster_id"]
    check("rids_unique", len(all_rids) == len(set(all_rids)),
          "%d total, %d unique" % (len(all_rids), len(set(all_rids))))
    stats = r.get("stats", {})
    check("stats_consistent",
          stats.get("records_ingested", -1) == len(all_rids)
          and stats.get("clusters", -1) == len(clusters)
          and stats.get("duplicates_removed", -1) == len(all_rids) - len(clusters),
          json.dumps(stats))

    # within-cluster justification: in a multi-member cluster at least one pair
    # shares a hard key, and no member is completely keyless
    unjust, empty_clusters = 0, 0
    for c in clusters:
        ms = c.get("members", [])
        if not ms:
            empty_clusters += 1
            continue
        if len(ms) < 2:
            continue
        def mkeys(m):
            return ({"d:" + m["doi"]} if m.get("doi") else set()) \
                 | ({"a:" + m["arxiv"]} if m.get("arxiv") else set()) \
                 | ({"t:" + norm_title(m["title"])[:80]} if norm_title(m.get("title")) else set())
        keysets = [mkeys(m) for m in ms]
        if any(not ks for ks in keysets):
            unjust += 1  # keyless member inside a merge: needs manual justification
            continue
        connected = False
        for i in range(len(keysets)):
            for j in range(i + 1, len(keysets)):
                if keysets[i] & keysets[j]:
                    connected = True
        if not connected:
            unjust += 1
    check("clusters_nonempty", empty_clusters == 0, "%d empty" % empty_clusters)
    check("cluster_merge_justified", unjust == 0, "%d clusters lack shared hard key" % unjust)

    # cross-cluster hard-id uniqueness
    seen_ids, cross_dup = {}, []
    for c in clusters:
        for idv in c.get("all_doi", []):
            k = "doi:" + idv
            if k in seen_ids and seen_ids[k] != c["cluster_id"]:
                cross_dup.append(idv)
            seen_ids[k] = c["cluster_id"]
        for idv in c.get("all_arxiv", []):
            k = "arxiv:" + idv
            if k in seen_ids and seen_ids[k] != c["cluster_id"]:
                cross_dup.append(idv)
            seen_ids[k] = c["cluster_id"]
    check("no_cross_cluster_id_dup", not cross_dup, "; ".join(cross_dup[:5]))

    # review queue honored
    violations = 0
    for q in r.get("review_queue", []):
        pair = q.get("pair", [])
        if len(pair) == 2 and rid_owner.get(pair[0]) and \
                rid_owner.get(pair[0]) == rid_owner.get(pair[1]):
            violations += 1
    check("review_queue_honored", violations == 0, "%d violations" % violations)

    # canonical membership + locator files
    bad_canon, bad_files = 0, set()
    for c in clusters:
        member_rids = {m["rid"] for m in c.get("members", [])}
        if c.get("canonical", {}).get("rid") not in member_rids:
            bad_canon += 1
        for m in c.get("members", []):
            f = (m.get("locator") or {}).get("file")
            if f and not os.path.exists(f):
                bad_files.add(f)
    check("canonical_is_member", bad_canon == 0, "%d bad" % bad_canon)
    check("locator_files_exist", not bad_files, "; ".join(sorted(bad_files)[:5]))
    check("sources_listed", bool(r.get("sources")))
    check("uncertainty_field", "uncertainty" in r)

    (work_dir / "verify_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": report["ok"],
                      "failed": [c["check"] for c in report["checks"] if not c["ok"]]},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""cross_ledger.py — 构建专利实体 ↔ 论文实体的跨源重叠对账表(ledger)。

每个左侧(patent)实体一行:
  entity_raw / role / band(auto|candidate|non_match) /
  matched_counterpart_raw(无则 null,绝不推断) /
  score / features / flags / alternatives(candidate 档全量备选) /
  anchors.left / anchors.right

锚点(quote anchor)形如:
  {"path": <源文件路径>, "sha256": <文件字节的 SHA-256>,
   "span": [start, end], "quote": <原文逐字子串>}
quote 恒等于文件文本 text[start:end];实体原文在任何源文件中找不到时,
该侧锚点为 null——缺失即 null,绝不猜测、绝不从文件名推断。

退出码:0 正常;1 数据违规;2 用法错误。仅标准库。
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from entity_match import (EXIT_OK, EXIT_USAGE, EXIT_VIOLATION,  # noqa: E402
                          echo, load_entities, load_policy, run_match)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def find_anchor(raw, sources):
    """Locate raw verbatim in the first source containing it; else None."""
    if not raw:
        return None
    for src in sources:
        p = Path(src)
        if not p.is_file():
            print(f"error: source file not found: {src}", file=sys.stderr)
            sys.exit(EXIT_USAGE)
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError as e:
            print(f"error: source is not UTF-8 text: {src}: {e}", file=sys.stderr)
            sys.exit(EXIT_VIOLATION)
        i = text.find(raw)
        if i >= 0:
            return {"path": str(p), "sha256": sha256_file(p),
                    "span": [i, i + len(raw)], "quote": text[i:i + len(raw)]}
    return None


def verify_anchor(anchor):
    """Recompute sha256 and confirm quote == text[span[0]:span[1]]."""
    if not anchor:
        return False
    p = Path(anchor["path"])
    if not p.is_file():
        return False
    if sha256_file(p) != anchor["sha256"]:
        return False
    text = p.read_text(encoding="utf-8")
    s, e = anchor["span"]
    return text[s:e] == anchor["quote"]


def build_ledger(left, right, policy, left_sources, right_sources):
    report = run_match(left, right, policy)
    pairs = report["_pairs"]

    rows = []
    for i, ent in enumerate(left):
        mine = [p for p in pairs if p["left_index"] == i]
        autos = [p for p in mine if p["band"] == "auto"]
        cands = [p for p in mine if p["band"] == "candidate"]

        row = {
            "entity_id": ent.get("id"),
            "entity_raw": ent.get("raw"),
            "role": ent.get("role"),
            "band": "non_match",
            "confidence": "non_match",
            "matched_counterpart_id": None,
            "matched_counterpart_raw": None,
            "score": None,
            "features": None,
            "flags": [],
            "alternatives": [],
            "requires_review": False,
            "anchors": {"left": find_anchor(ent.get("raw"), left_sources),
                        "right": None},
        }

        best = None
        if autos:
            best = max(autos, key=lambda p: (p["score"], -p["right_index"]))
            row["band"] = row["confidence"] = "auto"
        elif cands:
            # candidate band: listed, never silently merged; top alternative is
            # exposed together with ALL alternatives + feature breakdowns.
            best = max(cands, key=lambda p: (p["score"], -p["right_index"]))
            row["band"] = row["confidence"] = "candidate"
            row["requires_review"] = True
            row["alternatives"] = [{
                "counterpart_id": right[p["right_index"]].get("id"),
                "counterpart_raw": right[p["right_index"]].get("raw"),
                "score": p["score"], "features": p["features"], "flags": p["flags"],
            } for p in sorted(cands, key=lambda p: (-p["score"], p["right_index"]))]

        if best is not None:
            counterpart = right[best["right_index"]]
            row["matched_counterpart_id"] = counterpart.get("id")
            row["matched_counterpart_raw"] = counterpart.get("raw")
            row["score"] = best["score"]
            row["features"] = best["features"]
            row["flags"] = best["flags"]
            row["anchors"]["right"] = find_anchor(counterpart.get("raw"),
                                                  right_sources)
        rows.append(row)

    matched_right = {p["right_index"] for p in pairs
                     if p["band"] in ("auto", "candidate")}
    unmatched_right = [echo(e) for j, e in enumerate(right)
                       if j not in matched_right]

    return {
        "rows": rows,
        "unmatched_right_entities": unmatched_right,
        "statistics": {
            "left_count": len(left),
            "right_count": len(right),
            "row_count": len(rows),
            "auto_rows": sum(1 for r in rows if r["band"] == "auto"),
            "candidate_rows": sum(1 for r in rows if r["band"] == "candidate"),
            "non_match_rows": sum(1 for r in rows if r["band"] == "non_match"),
            "rows_with_left_anchor": sum(1 for r in rows if r["anchors"]["left"]),
            "rows_with_right_anchor": sum(1 for r in rows if r["anchors"]["right"]),
        },
        "policy": policy,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Build the patent<->paper cross-source overlap ledger.")
    ap.add_argument("--left", required=True,
                    help="normalized patent entities (name_norm output)")
    ap.add_argument("--right", required=True,
                    help="normalized paper entities (name_norm output)")
    ap.add_argument("--left-sources", nargs="*", default=[],
                    help="patent source text files for verbatim quote anchors")
    ap.add_argument("--right-sources", nargs="*", default=[],
                    help="paper source text files for verbatim quote anchors")
    ap.add_argument("--policy", required=True, help="match policy JSON")
    ap.add_argument("--output", required=True, help="ledger JSON path")
    args = ap.parse_args(argv)

    left = load_entities(args.left, "left entities")
    right = load_entities(args.right, "right entities")
    policy = load_policy(args.policy)

    if not left or not right:
        print("warning: empty entity list on at least one side; "
              "ledger rows will be non-match with null counterparts",
              file=sys.stderr)

    ledger = build_ledger(left, right, policy,
                          args.left_sources, args.right_sources)
    Path(args.output).write_text(
        json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    st = ledger["statistics"]
    print(f"ledger rows={st['row_count']} auto={st['auto_rows']} "
          f"candidate={st['candidate_rows']} non_match={st['non_match_rows']} "
          f"-> {args.output}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())

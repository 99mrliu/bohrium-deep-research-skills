#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scaffold_result.py — 生成 /app/output/result.json 骨架

- case_id 取自 case.json；
- 组装 query（概念块 + 布尔式 + 版本）、hits（分轨）、screening（PRISMA + 逐条决定）、
  ranking（score 分解）、omissions、sources、uncertainty、change_log；
- 镜像 output_contract 的全部字段：契约里有而结果里没有的字段补 null 并在
  uncertainty 中如实登记；
- status 诚实取值：ok / partial / failed（自动判定可用 --status 覆写）。

用法：
  python3 scaffold_result.py --case /input/case.json --query query.json \
      --hits hits.json --screening screening.json --out /app/output/result.json [--status auto]
退出码：0 成功；1 读取错误；2 --status 取值非法。
"""
import argparse
import datetime
import json
import os
import sys

VALID_STATUS = {"ok", "partial", "failed"}


def _load(path):
    if not path:
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def compact_hit(h):
    return {"ref": "%s#%s" % (h.get("file", ""), h.get("loc", "")),
            "title": h.get("title", ""),
            "identifier": h.get("identifier", ""),
            "year": h.get("year"),
            "matched_via": h.get("matched_via"),
            "blocks_matched": list(h.get("blocks_matched", {}).keys()),
            "classification_matched": h.get("classification_matched", []),
            "duplicates": h.get("duplicates", [])}


def auto_status(hits_doc, screening):
    if not hits_doc or hits_doc.get("corpus", {}).get("records_total", 0) == 0:
        return "failed"
    if not screening:
        return "partial"
    p = screening.get("prisma", {})
    if p.get("included", 0) == 0:
        return "partial"
    if hits_doc.get("unclassified") or hits_doc.get("zero_hit_blocks"):
        return "partial"
    return "ok"


def run(case, query, hits_doc, screening, status_arg="auto"):
    case_id = case.get("case_id") or case.get("id") or "unknown"
    uncertainty = []
    now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")

    status = status_arg if status_arg != "auto" else auto_status(hits_doc, screening)
    if status not in VALID_STATUS:
        return None, ["status 取值非法: %r（须为 ok/partial/failed）" % status], 2

    hits_by_track = {"patent": [], "npl": []}
    if hits_doc:
        for h in hits_doc.get("hits", []):
            if h.get("track") in hits_by_track:
                hits_by_track[h["track"]].append(compact_hit(h))
        if hits_doc.get("unclassified"):
            uncertainty.append("存在 %d 条无法判定轨道的记录，未纳入任一轨道，详见 omissions.unclassified_records。"
                               % len(hits_doc["unclassified"]))
        if hits_doc.get("zero_hit_blocks"):
            uncertainty.append("概念块 %s 在语料中零命中，查全性受限。"
                               % hits_doc["zero_hit_blocks"])
    uncertainty.append("当前官方法律状态未知，未核验；result 中不含法律状态结论。")
    uncertainty.append("命中仅为本地语料内匹配，外部数据库未检索，存在遗漏。")

    sources = []
    if hits_doc:
        sources.extend(hits_doc.get("corpus", {}).get("files", []))

    result = {
        "case_id": case_id,
        "status": status,
        "query": {"topic": (query or {}).get("topic", ""),
                  "version": (query or {}).get("version", ""),
                  "mode": (query or {}).get("mode", "topic"),
                  "blocks": (query or {}).get("blocks", []),
                  "boolean": (query or {}).get("boolean", "")},
        "hits": hits_by_track,
        "screening": {"prisma": (screening or {}).get("prisma", {}),
                      "decisions": (screening or {}).get("decisions", []),
                      "threshold_blocks": (screening or {}).get("threshold_blocks")},
        "ranking": (screening or {}).get("ranking", []),
        "omissions": (screening or {}).get("omissions", {}),
        "sources": sources,
        "uncertainty": uncertainty,
        "change_log": [{"ts": now, "action": "scaffold_result 生成 result.json 骨架",
                        "detail": "status=%s；契约字段已镜像" % status}],
    }

    # 镜像 output_contract 全部字段
    contract = case.get("output_contract") or {}
    if isinstance(contract, list):
        contract = {str(k): "" for k in contract}
    if isinstance(contract, dict):
        for k in contract:
            if k not in result:
                result[k] = None
                result["uncertainty"].append("output_contract 字段 %r 暂无对应产物，置 null 待补。" % k)
    return result, [], 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="生成 result.json 骨架并镜像 output_contract")
    ap.add_argument("--case", required=True, help="/input/case.json")
    ap.add_argument("--query")
    ap.add_argument("--hits")
    ap.add_argument("--screening")
    ap.add_argument("--out", required=True)
    ap.add_argument("--status", default="auto",
                    help="auto 或 ok/partial/failed（覆写自动判定）")
    args = ap.parse_args(argv)

    try:
        case = _load(args.case) or {}
        query = _load(args.query)
        hits_doc = _load(args.hits)
        screening = _load(args.screening)
    except (OSError, json.JSONDecodeError) as e:
        sys.stderr.write("无法读取输入: %s\n" % e)
        return 1

    result, errors, code = run(case, query, hits_doc, screening, args.status)
    if errors:
        for e in errors:
            sys.stderr.write(e + "\n")
        return code
    out_dir = os.path.dirname(os.path.abspath(args.out))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write("\n")
    sys.stderr.write("result.json 已写入 %s（status=%s）\n" % (args.out, result["status"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())

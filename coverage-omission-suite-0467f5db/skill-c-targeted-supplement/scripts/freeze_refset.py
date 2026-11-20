#!/usr/bin/env python3
"""freeze_refset.py — 冻结参考集：从本地参考图与响应文件解析参考记录并去重冻结。

参考记录的优先级（全部来自本地材料，绝不来自检索结果）：
  1) 参考图文件（文件名含 graph / reference / refset）中声明的参考节点
  2) 其余 JSON 响应文件中含 title 的记录，仅作为兜底来源并在 provenance 中注明
去重键：归一化 DOI > 归一化 PMID > 规范化标题；同键合并时保留全部 provenance。
稳定编号：按 (year, 规范化标题) 排序后赋予 R0001…；内容哈希 refset_hash 作为冻结凭证。

输出：work/refset.json（含 provenance）、work/refset.csv。
退出码：0 正常；2 一条参考记录都解析不到；3 校验失败。仅标准库，支持 --help。
"""
import argparse
import csv
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from match_coverage import (
    EXIT_OK, EXIT_INSUFFICIENT,
    iter_records, load_json, norm_doi, norm_pmid, norm_title,
    doi_of, pmid_of, title_of, year_of, first_author_surname,
)

GRAPH_HINTS = ("graph", "reference", "refset")


def is_graph_file(path):
    name = os.path.basename(path).lower()
    return any(h in name for h in GRAPH_HINTS)


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_material_files(materials_dir):
    files = []
    for root, _dirs, names in os.walk(materials_dir):
        for name in sorted(names):
            if name.lower().endswith((".json", ".jsonl")):
                files.append(os.path.join(root, name))
    return sorted(files)


def parse_record_fields(rec):
    return {
        "doi": doi_of(rec),
        "pmid": pmid_of(rec),
        "title": title_of(rec),
        "title_norm": norm_title(title_of(rec)),
        "year": year_of(rec),
        "first_author": first_author_surname(rec),
        "retracted": bool(rec.get("retracted")) if isinstance(rec.get("retracted"), bool) else None,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="从本地材料解析并冻结参考集（分母的唯一合法来源）。"
    )
    ap.add_argument("--parsed", help="parse_case.py 产出的 parsed_case.json（可选）")
    ap.add_argument("--materials", default="/input", help="材料目录（默认 /input）")
    ap.add_argument("--work", default="/app/work", help="工作目录（默认 /app/work）")
    args = ap.parse_args(argv)

    os.makedirs(args.work, exist_ok=True)

    json_files = load_material_files(args.materials)
    if not json_files:
        print("[freeze_refset] 材料目录中无 JSON 文件：%s" % args.materials, file=sys.stderr)
        return EXIT_INSUFFICIENT

    # 第一遍：仅解析参考图文件；若有参考图，响应文件不得进入分母
    # （响应文件中的候选记录不是参考记录，并入会污染分母）。
    graph_files = [p for p in json_files if is_graph_file(p)]
    ordered = sorted(graph_files if graph_files else json_files)
    merged = {}
    order_counter = 0
    for path in ordered:
        try:
            obj = load_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        for rec in iter_records(obj):
            fields = parse_record_fields(rec)
            if not fields["title_norm"] and not fields["doi"] and not fields["pmid"]:
                continue
            order_counter += 1
            key = fields["doi"] or fields["pmid"] or ("title:" + (fields["title_norm"] or ""))
            provenance = {"file": os.path.abspath(path), "order": order_counter}
            if key not in merged:
                merged[key] = {"fields": fields, "provenance": [provenance]}
            else:
                cur = merged[key]["fields"]
                for fkey in ("doi", "pmid", "title", "title_norm", "year", "first_author"):
                    if not cur.get(fkey) and fields.get(fkey):
                        cur[fkey] = fields[fkey]
                merged[key]["provenance"].append(provenance)

    refs = list(merged.values())
    if not refs:
        print("[freeze_refset] 未能从本地材料解析出任何参考记录", file=sys.stderr)
        return EXIT_INSUFFICIENT

    refs.sort(key=lambda r: (r["fields"].get("year") or "9999",
                             r["fields"].get("title_norm") or ""))
    out_refs = []
    for i, item in enumerate(refs, start=1):
        f = item["fields"]
        out_refs.append({
            "ref_id": "R%04d" % i,
            "doi": f["doi"],
            "pmid": f["pmid"],
            "title": f["title"],
            "title_norm": f["title_norm"],
            "year": f["year"],
            "first_author": f["first_author"],
            "retracted": f["retracted"],
            "provenance": item["provenance"],
        })

    case_id = None
    if args.parsed and os.path.isfile(args.parsed):
        try:
            case_id = load_json(args.parsed).get("case_id")
        except (OSError, json.JSONDecodeError):
            pass

    canonical = json.dumps(out_refs, ensure_ascii=False, sort_keys=True)
    refset = {
        "case_id": case_id,
        "refset_hash": sha256_text(canonical),
        "count": len(out_refs),
        "dedup_keys": ["doi", "pmid", "title_norm"],
        "sources": sorted({p["file"] for r in out_refs for p in r["provenance"]}),
        "references": out_refs,
    }
    refset_path = os.path.join(args.work, "refset.json")
    with open(refset_path, "w", encoding="utf-8") as fh:
        json.dump(refset, fh, ensure_ascii=False, indent=2)

    csv_path = os.path.join(args.work, "refset.csv")
    with open(csv_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["ref_id", "doi", "pmid", "title", "year",
                         "first_author", "retracted", "n_provenance"])
        for r in out_refs:
            writer.writerow([r["ref_id"], r["doi"] or "", r["pmid"] or "",
                             r["title"] or "", r["year"] or "",
                             r["first_author"] or "", r["retracted"] or "",
                             len(r["provenance"])])

    print("[freeze_refset] 冻结参考集 %d 条（hash=%s…）-> %s / %s"
          % (len(out_refs), refset["refset_hash"][:12], refset_path, csv_path))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""governance_forge.py -- 运行治理与证据绑定交付（skill-e-run-governance-forge）。

重心：过程质量控制与下游渲染工程——结果不仅要对，还要可复跑、可抽检、可追溯。
  1. 运行清单 run_manifest.json：脚本哈希、输入文件哈希、各阶段产物哈希、时间戳；
  2. 确定性复跑 --replay：重算全部阶段并逐一比对产物哈希，任何漂移列名报告；
     （时间戳字段除外，比对前剔除）
  3. 独立复核抽检 audit_report.json：用一套与主管线不同的判定实现（包含度匹配）
     对确定性抽样的记录重判，报告一致率与分歧清单；
  4. 证据绑定渲染：coverage_report.md 中每个关键数字带绑定号，binding_map.json
     把绑定号映射到账本 JSON 路径；附纯文本 SVG 图（无需第三方库）。

仅 Python 标准库，不联网。退出码 0/2/3；--replay 漂移时退出码 4。
"""
import argparse
import csv
import datetime
import hashlib
import json
import os
import re
import sys

VERSION = "1.0.0"
AUDIT_STRIDE = 3  # 确定性抽样：每第 3 条记录复核一次


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(t):
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


def canonical(obj):
    """剔除时间戳后的规范 JSON 文本，用于跨运行哈希比对。"""
    def strip(o):
        if isinstance(o, dict):
            return {k: strip(v) for k, v in o.items() if k not in ("ts", "generated_at", "frozen_at", "timestamp")}
        if isinstance(o, list):
            return [strip(x) for x in o]
        return o
    return json.dumps(strip(obj), sort_keys=True, ensure_ascii=False)


def norm_doi(doi):
    if not doi:
        return ""
    d = str(doi).strip().lower()
    for pre in ("https://doi.org/", "http://doi.org/", "doi.org/", "doi:"):
        if d.startswith(pre):
            d = d[len(pre):]
    return d.strip().rstrip(".")


def norm_title(t):
    t = re.sub(r"[^a-z0-9 ]+", " ", str(t or "").lower())
    return re.sub(r"\s+", " ", t).strip()


def tokens(t):
    stop = {"the", "a", "an", "of", "and", "in", "on", "for", "to", "with", "by"}
    return [x for x in norm_title(t).split() if x not in stop]


def jaccard(a, b):
    sa, sb = set(a), set(b)
    return len(sa & sb) / len(sa | sb) if sa and sb else 0.0


def first_year(rec):
    for k in ("year", "published", "issued", "date"):
        v = rec.get(k)
        if v is None:
            continue
        m = re.search(r"(?:19|20)\d{2}", str(v))
        if m:
            return int(m.group(0))
    return None


def load_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return default


def dump_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------- 材料与主管线

def collect(input_dir):
    refs, queries = [], []
    for root, _d, names in os.walk(input_dir):
        for name in sorted(names):
            p = os.path.join(root, name)
            if not os.path.isfile(p) or os.path.islink(p):
                continue
            low = name.lower()
            if low in ("case.json", "task.md"):
                continue
            try:
                with open(p, encoding="utf-8", errors="replace") as fh:
                    head = fh.read(8192)
            except Exception:
                continue
            if re.search(r'"(queries|searches)"\s*:', head) and re.search(r'"(hits|results|records)"\s*:', head):
                data = load_json(p) or {}
                for q in data.get("queries") or data.get("searches") or []:
                    if isinstance(q, dict):
                        queries.append(q)
            elif low.endswith(".csv"):
                with open(p, encoding="utf-8", errors="replace") as fh:
                    for i, row in enumerate(csv.DictReader(fh)):
                        r = {str(k).strip().lower(): (v or "").strip() for k, v in row.items() if k}
                        if r:
                            refs.append({"record": r, "origin": "%s:row%d" % (p, i + 2)})
    return refs, queries


def primary_match(rec, hits):
    """主管线判定：L1 标识符 / L2 Jaccard≥0.80+年份。"""
    rd = norm_doi(rec.get("doi"))
    for h in hits:
        if rd and norm_doi(h.get("doi")) and rd == norm_doi(h.get("doi")):
            return "hit", "L1"
    for h in hits:
        if jaccard(tokens(rec.get("title")), tokens(h.get("title"))) >= 0.8:
            ry, hy = rec.get("year"), first_year(h)
            if not ry or not hy or ry == hy:
                return "hit", "L2"
    return "miss", None


def audit_match(rec, hits):
    """独立复核实现：包含度匹配（标题 token 包含率≥0.9）+ 年份。故意与主管线不同。"""
    rd = norm_doi(rec.get("doi"))
    for h in hits:
        if rd and norm_doi(h.get("doi")) and rd == norm_doi(h.get("doi")):
            return "hit"
    rt = set(tokens(rec.get("title")))
    if not rt:
        return "miss"
    for h in hits:
        ht = set(tokens(h.get("title")))
        if ht and len(rt & ht) / len(rt) >= 0.9:
            ry, hy = rec.get("year"), first_year(h)
            if not ry or not hy or ry == hy:
                return "hit"
    return "miss"


def run_pipeline(args, replay_mode=False):
    case = load_json(os.path.join(args.input, "case.json"), {}) or {}
    case_id = case.get("case_id") or case.get("id") or "unknown-case"
    oc = case.get("output_contract") or {}
    if isinstance(oc, dict):
        contract = list(oc.get("required_fields") or oc.get("fields") or oc.keys())
    elif isinstance(oc, list):
        contract = [str(x) for x in oc]
    else:
        contract = []
    if not contract:
        contract = ["coverage", "audit", "replay_manifest", "binding_map", "miss_list", "coverage_report"]

    status, uncertainty, change_log = "complete", [], []
    refs_raw, queries = collect(args.input)
    hits = []
    for q in queries:
        for h in q.get("hits") or q.get("results") or q.get("records") or []:
            if isinstance(h, dict):
                hh = dict(h)
                hh["_query_id"] = q.get("query_id") or q.get("id")
                hits.append(hh)

    refset, seen = [], set()
    for c in refs_raw:
        r = c["record"]
        key = norm_doi(r.get("doi")) or norm_title(r.get("title"))[:80]
        if key and key in seen:
            change_log.append({"event": "dedup_merge", "merged": c["origin"]})
            continue
        if key:
            seen.add(key)
        refset.append({"ref_id": "R%03d" % (len(refset) + 1), "doi": r.get("doi"),
                       "title": r.get("title", ""), "year": first_year(r),
                       "container": r.get("container", ""), "origin": c["origin"]})
    if not refset:
        status = "partial"
        change_log.append({"event": "no_reference_records"})
    if not queries:
        status = "partial"
        uncertainty.append("no query material found")

    # 主判定 + 独立复核抽检
    per_record, audit_rows, discrepancies = [], [], []
    for i, rec in enumerate(refset):
        st, lvl = primary_match(rec, hits)
        row = {"ref_id": rec["ref_id"], "doi": rec.get("doi"), "title": rec["title"][:140],
               "status": st, "match_level": lvl}
        per_record.append(row)
        if i % AUDIT_STRIDE == 0:
            ast = audit_match(rec, hits)
            agree = (ast == st)
            audit_rows.append({"ref_id": rec["ref_id"], "primary": st, "audit": ast, "agree": agree})
            if not agree:
                discrepancies.append({"ref_id": rec["ref_id"], "primary": st, "audit": ast,
                                      "note": "disagreement routed to manual adjudication; "
                                              "primary status retained, flagged in uncertainty"})
                uncertainty.append("audit disagreement on %s: primary=%s audit=%s" % (rec["ref_id"], st, ast))
    hit_n = sum(1 for r in per_record if r["status"] == "hit")
    denom = len(per_record)
    coverage = {"denominator": denom, "hit": hit_n, "miss": denom - hit_n,
                "coverage_ratio": round(hit_n / denom, 4) if denom else None,
                "per_record": per_record}
    audit = {"method": "deterministic stride sample (every %dth record) re-adjudicated by an "
                       "independent containment-based matcher" % AUDIT_STRIDE,
             "sampled": len(audit_rows),
             "agreement": round(sum(1 for a in audit_rows if a["agree"]) / len(audit_rows), 4) if audit_rows else None,
             "rows": audit_rows, "discrepancies": discrepancies}
    dump_json(os.path.join(args.work, "coverage_ledger.json"), coverage)
    dump_json(os.path.join(args.work, "audit_report.json"), audit)
    miss_list = [r for r in per_record if r["status"] == "miss"]

    # 证据绑定：每个关键数字 -> 账本 JSON 路径
    binding_map = {
        "B1_denominator": {"value": denom, "source": "coverage_ledger.json#/denominator"},
        "B2_hit": {"value": hit_n, "source": "coverage_ledger.json#/hit"},
        "B3_miss": {"value": denom - hit_n, "source": "coverage_ledger.json#/miss"},
        "B4_coverage_ratio": {"value": coverage["coverage_ratio"], "source": "coverage_ledger.json#/coverage_ratio"},
        "B5_audit_agreement": {"value": audit["agreement"], "source": "audit_report.json#/agreement"},
        "B6_audit_sampled": {"value": audit["sampled"], "source": "audit_report.json#/sampled"},
    }
    dump_json(os.path.join(args.work, "binding_map.json"), binding_map)

    # SVG 覆盖图（纯文本，无第三方依赖）
    svg_path = os.path.join(args.output, "coverage_chart.svg")
    bar_w = 300
    hit_w = int(bar_w * hit_n / denom) if denom else 0
    ticks = []
    for i, r in enumerate(per_record):
        color = "#2e7d32" if r["status"] == "hit" else "#c62828"
        ticks.append('<rect x="%d" y="60" width="18" height="18" fill="%s"><title>%s %s</title></rect>'
                     % (20 + i * 24, color, r["ref_id"], r["status"]))
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="640" height="120" font-family="monospace">'
           '<text x="20" y="24" font-size="14">coverage (synthetic-example rendering): '
           '%d/%d = %.4f</text>'
           '<rect x="20" y="34" width="%d" height="14" fill="#c62828"/>'
           '<rect x="20" y="34" width="%d" height="14" fill="#2e7d32"/>%s</svg>'
           % (hit_n, denom, coverage["coverage_ratio"] or 0.0, bar_w, hit_w, "".join(ticks)))
    with open(svg_path, "w", encoding="utf-8") as fh:
        fh.write(svg)

    # 报告（数字带绑定号）
    lines = ["# 覆盖率与遗漏分析报告（证据绑定版）", "",
             "- case_id: `%s`" % case_id,
             "- 分母 %d [B1] / 命中 %d [B2] / 漏检 %d [B3]，覆盖率 %.4f [B4]" % (
                 denom, hit_n, denom - hit_n, coverage["coverage_ratio"] or 0.0),
             "- 复核抽检：抽样 %d 条 [B6]，一致率 %s [B5]；分歧 %d 条（全部转人工并保留主管线状态）" % (
                 audit["sampled"], audit["agreement"], len(discrepancies)),
             "- 每个 [Bn] 绑定号可在 binding_map.json 中查到账本路径；coverage_chart.svg 为同数据渲染图",
             "", "## 逐条命中状态", "", "| ref_id | status | level |", "|---|---|---|"]
    for r in per_record:
        lines.append("| %s | %s | %s |" % (r["ref_id"], r["status"], r.get("match_level") or "-"))
    report_path = os.path.join(args.output, "coverage_report.md")
    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    # 运行清单
    input_files = []
    for root, _d, names in os.walk(args.input):
        for n in sorted(names):
            p = os.path.join(root, n)
            if os.path.isfile(p):
                input_files.append({"path": p, "sha256": sha256_file(p)})
    stage_hashes = {
        "coverage_ledger": sha256_text(canonical(coverage)),
        "audit_report": sha256_text(canonical(audit)),
        "binding_map": sha256_text(canonical(binding_map)),
        "report_md": sha256_text("\n".join(lines)),
    }
    script_path = os.path.abspath(__file__)
    manifest = {"skill": "run-governance-forge", "skill_version": VERSION,
                "generated_at": now_iso(), "case_id": case_id,
                "script_sha256": sha256_file(script_path) if os.path.isfile(script_path) else None,
                "inputs": input_files, "stage_hashes": stage_hashes,
                "determinism_note": "hashes computed on canonical JSON with timestamps stripped; "
                                    "--replay recomputes and compares"}
    dump_json(os.path.join(args.work, "run_manifest.json"), manifest)

    artifacts = {"coverage": {k: coverage[k] for k in ("denominator", "hit", "miss", "coverage_ratio")},
                 "audit": {"sampled": audit["sampled"], "agreement": audit["agreement"],
                           "discrepancies": len(discrepancies)},
                 "replay_manifest": manifest, "binding_map": binding_map,
                 "miss_list": miss_list, "coverage_report": report_path,
                 "coverage_chart": svg_path}
    result = {"case_id": case_id, "status": status,
              "sources": [{"path": f["path"], "sha256": f["sha256"]} for f in input_files],
              "uncertainty": uncertainty, "change_log": change_log,
              "skill": "run-governance-forge", "skill_version": VERSION}
    for f in contract:
        result[f] = artifacts.get(f)
    dump_json(os.path.join(args.output, "result.json"), result)
    missing = [f for f in contract if result.get(f) is None]
    return result, manifest, missing, status


def main():
    ap = argparse.ArgumentParser(description="运行治理与证据绑定交付：run / --replay")
    ap.add_argument("--input", default="/input")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--output", default="/app/output")
    ap.add_argument("--replay", action="store_true",
                    help="重算全部阶段并与 run_manifest.json 比对哈希")
    args = ap.parse_args()
    os.makedirs(args.work, exist_ok=True)
    os.makedirs(args.output, exist_ok=True)

    if args.replay:
        old = load_json(os.path.join(args.work, "run_manifest.json"))
        if not old:
            print("no run_manifest.json to replay against", file=sys.stderr)
            return 4
        result, manifest, missing, status = run_pipeline(args, replay_mode=True)
        drift = []
        for k, v in manifest["stage_hashes"].items():
            if old.get("stage_hashes", {}).get(k) != v:
                drift.append(k)
        verdict = {"replay_ok": not drift, "drifted_stages": drift,
                   "checked_at": now_iso(),
                   "note": "stage hashes recomputed from canonical JSON (timestamps stripped)"}
        dump_json(os.path.join(args.output, "replay_verdict.json"), verdict)
        print(json.dumps(verdict, ensure_ascii=False))
        return 0 if not drift else 4

    result, manifest, missing, status = run_pipeline(args)
    if missing:
        print("contract fields unresolved: %s" % missing, file=sys.stderr)
        return 3
    return 2 if status == "partial" else 0


if __name__ == "__main__":
    sys.exit(main())

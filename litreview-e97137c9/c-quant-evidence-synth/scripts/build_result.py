#!/usr/bin/env python3
"""build_result.py — 组装 result.json 并镜像 output_contract（bundle C）。

字段来源映射（contract 字段名 → 默认内容）：
  research_product / product / review / draft  → 草稿 + 研究问题 + 主题
  quant_summary / quantitative / quant         → 数值候选/归一化/冲突统计
  numeric_conflicts / conflicts                → 冲突候选清单（不调和）
  evidence_table / table                       → 定量证据表摘录
  uncertainties / uncertainty                  → 不确定性清单
  sources                                      → 文献清单 + sha256 + tier
  status                                       → completed | partial | blocked
  change_log / changes                         → 变更记录
  quant_gate_report / gate_report / gate       → 数字回链门控报告
未知名称的 contract 字段填 null 并在 uncertainties 说明，绝不漏字段。
"""
import json
import os
import sys


def load_jsonl(path):
    rows = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    rows.append(json.loads(line))
    return rows


def load_json(path, default):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


def read_text(path):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return f.read()
    return ""


def collect_uncertainties(work, out, docs, groups, norm_rows, conflicts, gate):
    u = load_json(os.path.join(work, "uncertainties.json"), [])
    dup_of = {m: g["members"][0] for g in groups for m in g["members"][1:]}
    for d in docs:
        did = d["doc_id"]
        if d.get("tier") == "abstract_only":
            u.append(f"{did}：仅摘要可用（abstract_only），数值证据强度不超过 suggestive")
        elif d.get("tier") == "metadata_only":
            u.append(f"{did}：仅有题录/URL 无全文，未纳入数值抽取")
        elif d.get("tier") == "failed":
            u.append(f"{did}：文本抽取失败（{d.get('extract_method')}），未纳入")
        if did in dup_of:
            u.append(f"{did}：与 {dup_of[did]} 判为近重复，冲突检测仅使用代表篇 {dup_of[did]}")
    unnorm = [r for r in norm_rows if r.get("norm_status") != "ok"]
    if unnorm:
        u.append(f"{len(unnorm)} 个数值候选无法归一化（unnormalized），已排除跨文献比较："
                 + "; ".join(f"{r['qid']}({r.get('metric')},{r.get('norm_note')})" for r in unnorm[:5]))
    if conflicts.get("conflict_count"):
        u.append(f"检测到 {conflicts['conflict_count']} 对数值冲突候选，并列保留供模型裁决，"
                 "未自动调和、未取平均；详见 numeric_conflicts 字段")
    if gate and not gate.get("gate_passed", True):
        u.append(f"数字回链门控：{gate.get('unlinked_count')} 个数字无法回链 quant candidate，"
                 "已在文中就地标 [数值未定位]；详见 quant_gate_report.json")
    return sorted(set(u))


def build(work, out, forced_status=None):
    profile = load_json(os.path.join(work, "case_profile.json"), {})
    docs = load_jsonl(os.path.join(work, "docs.jsonl"))
    groups = load_json(os.path.join(work, "dup_groups.json"), [])
    norm_rows = load_jsonl(os.path.join(work, "quant_normalized.jsonl"))
    conflicts = load_json(os.path.join(work, "numeric_conflicts.json"),
                          {"conflict_count": 0, "conflicts": []})
    gate = load_json(os.path.join(out, "quant_gate_report.json"), None)
    themes = load_json(os.path.join(work, "themes.json"), [])
    change_log = load_json(os.path.join(work, "change_log.json"), [])

    draft = read_text(os.path.join(out, "review_draft.md")) or \
        read_text(os.path.join(work, "review_draft.md"))
    table = read_text(os.path.join(out, "evidence_table.md")) or \
        read_text(os.path.join(work, "evidence_table.md"))

    usable = [d for d in docs if d.get("tier") in ("fulltext", "abstract_only")]
    if forced_status:
        status = forced_status
    elif not docs or not usable:
        status = "blocked"
    elif draft and gate and gate.get("gate_passed"):
        status = "completed"
    else:
        status = "partial"

    by_dim, unnorm = {}, 0
    for r in norm_rows:
        if r.get("norm_status") == "ok":
            by_dim[r["dimension"]] = by_dim.get(r["dimension"], 0) + 1
        else:
            unnorm += 1
    quant_summary = {
        "candidates": len(norm_rows),
        "normalized": len(norm_rows) - unnorm,
        "unnormalized": unnorm,
        "by_dimension": by_dim,
        "compared_pairs": conflicts.get("compared_pairs", 0),
        "conflict_pairs": conflicts.get("conflict_count", 0),
        "conflicts_file": "numeric_conflicts.json",
    }
    uncertainties = collect_uncertainties(work, out, docs, groups, norm_rows, conflicts, gate)
    sources = [{"doc_id": d["doc_id"], "ref": d.get("ref"), "sha256": d.get("sha256"),
                "tier": d.get("tier"), "metadata": d.get("provided_metadata") or {}}
               for d in docs]
    research_product = {
        "question": profile.get("research_question", ""),
        "themes": themes,
        "draft_file": "review_draft.md" if draft else None,
        "draft_excerpt": draft[:1500],
    }
    evidence_table = {"file": "evidence_table.md" if table else None,
                      "excerpt": table[:1500]}

    defaults = {
        "case_id": profile.get("case_id", "unknown_case"),
        "status": status,
        "research_product": research_product,
        "quant_summary": quant_summary,
        "numeric_conflicts": conflicts.get("conflicts", []),
        "evidence_table": evidence_table,
        "uncertainties": uncertainties,
        "sources": sources,
        "change_log": change_log,
        "quant_gate_report": gate,
    }
    alias = {
        "product": "research_product", "review": "research_product", "draft": "research_product",
        "quant": "quant_summary", "quantitative": "quant_summary", "quantitative_summary": "quant_summary",
        "conflicts": "numeric_conflicts", "conflict": "numeric_conflicts",
        "table": "evidence_table", "evidence": "evidence_table",
        "uncertainty": "uncertainties", "source": "sources",
        "changes": "change_log", "gate": "quant_gate_report", "gate_report": "quant_gate_report",
    }

    contract = profile.get("output_contract")
    fields = []
    if isinstance(contract, list):
        fields = [str(x) for x in contract]
    elif isinstance(contract, dict):
        fields = [str(k) for k in contract.keys()]
    if fields:
        result = {}
        for f in fields:
            key = f if f in defaults else alias.get(f.lower())
            if key:
                result[f] = defaults[key]
            else:
                result[f] = None
                uncertainties.append(f"output_contract 字段 '{f}' 无对应内容，填 null")
        result.setdefault("case_id", defaults["case_id"])
        result.setdefault("status", status)
        result.setdefault("uncertainties", uncertainties)
        result.setdefault("sources", sources)
        result.setdefault("change_log", change_log)
        result.setdefault("quant_gate_report", gate)
    else:
        result = defaults
        result["uncertainties"] = uncertainties

    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "result.json"), "w", encoding="utf-8") as fp:
        json.dump(result, fp, ensure_ascii=False, indent=2)
    return result


def main(argv):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    r = build(args.work, args.out)
    print(json.dumps({"status": r.get("status"), "fields": len(r)}, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])

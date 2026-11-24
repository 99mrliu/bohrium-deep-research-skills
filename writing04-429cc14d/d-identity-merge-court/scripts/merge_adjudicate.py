#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""merge_adjudicate.py — 身份裁决校验与施加（identity-merge-court / 方向 D）。

立场：去重不是字符串相似度问题，而是身份判定问题。本脚本是"法庭"：
  1) 逐案校验 decisions.json（三态裁决：merge / keep_separate / human_queue）；
  2) 任何违反 M1–M5 规则的裁决一律拒绝，退出码 1，且不写任何产物（原子）；
  3) 全部通过后才施加 merge：canonical 吸收成员字段、冲突字段入 exception list、
     生成 redirect_map 与逐案 rationale（merge_report.json / merge_report.md）。

M 规则（详见 references/adjudication_rules.md）：
  M1 同规范化 DOI 且书目坐标一致 → 允许 merge；
  M2 同规范化 DOI 但书目坐标（年/卷/期/页/文章号）规范化后冲突 → 必须 human_queue，禁止自动并；
  M3 仅题名相似、无坐标或标识符 corroboration（组证据 weak）→ 禁止 merge（keep_separate/human_queue）；
  M4 预印本-正式版关系成立（共享标识或材料内证据）→ 允许并入正式版，且 canonical 必须是正式版，留谱系；
  M5 同第一作者姓+同年但题名/容器显著不同 → 禁止 merge（同名作者不同文献保护）。

保守性原则：keep_separate 与 human_queue 永不拒绝（它们不造成不可逆后果）；
只有 merge 需要通过全部门检。

用法：
  python3 merge_adjudicate.py --candidates candidates.json --records records.jsonl \
      --decisions decisions.json --out OUTDIR
  竞赛环境：python3 /skills/weekly-skill/scripts/merge_adjudicate.py --candidates /app/work/candidates/candidates.json \
      --records /app/work/records.jsonl --decisions /app/work/decisions.json --out /app/work/merge
"""
import argparse
import copy
import json
import sys
from pathlib import Path

# 与同目录脚本共享规范化原语（脚本目录自动在 sys.path 中）
from dedup_candidates import (extract_doi, is_preprint, norm_text, norm_title,
                              norm_year, first_family)

SCHEMA_VERSION = "1.0"
VERDICTS = {"merge", "keep_separate", "human_queue"}
MIN_REASON_LEN = 8

# M2 "元数据冲突"的精确定义：书目坐标（年/卷/期/页/文章号）规范化后不一致。
# 题名/刊名/作者的语种与格式差异（中英译名、罗马化、大小写）不触发 M2，
# 而是记入 exception list 供人工抽查——见 references/adjudication_rules.md。
MATERIAL_FIELDS = {"year", "volume", "issue", "pages", "article_number"}

FILL_FIELDS = ["title", "title_original", "authors", "year", "date", "type",
               "container", "volume", "issue", "pages", "article_number",
               "doi", "pmid", "arxiv", "url", "version", "note", "translation_of"]

EXCEPTION_FIELDS = ["title", "year", "type", "container", "volume", "issue",
                    "pages", "article_number"]


def load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def load_records(path):
    recs = {}
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            recs[rec["record_id"]] = rec
    return recs


def group_facts(group, recs):
    """汇总候选组事实，用于 M 规则校验。"""
    members = group["members"]
    mrecs = [recs[m] for m in members]
    dois = [extract_doi(r) for r in mrecs]
    dois_non = [d for d in dois if d]
    # 必须至少两名成员持有同一规范化 DOI 才算"共享 DOI"（单边有 DOI 不构成 M1/M2 前提）
    same_doi = len(dois_non) >= 2 and len(set(dois_non)) == 1
    material_conflicts = [c for c in group.get("field_conflicts", [])
                          if c["field"] in MATERIAL_FIELDS and not c["normalized_equal"]]
    sig_types = {s["type"] for s in group.get("signals", [])}
    preprint_members = [r["record_id"] for r in mrecs if is_preprint(r)]
    nonpreprint_members = [r["record_id"] for r in mrecs if not is_preprint(r)]
    containers = {norm_text(r.get("container")) for r in mrecs if norm_text(r.get("container"))}
    titles = {norm_title(r.get("title")) for r in mrecs if norm_title(r.get("title"))}
    m5_pattern = ("author_year_title_jaccard" in sig_types
                  and len(containers) > 1 and len(titles) > 1)
    return {
        "same_doi": same_doi,
        "shared_doi": dois_non[0] if same_doi else "",
        "material_conflicts": material_conflicts,
        "sig_types": sig_types,
        "preprint_members": preprint_members,
        "nonpreprint_members": nonpreprint_members,
        "m5_pattern": m5_pattern,
        "grade": group.get("evidence_grade", "weak"),
    }


def validate(decisions, groups, recs):
    """校验全部裁决；返回 (errors, validated_decisions)。不写任何文件。"""
    errors = []
    by_group = {}
    if not isinstance(decisions, list):
        return ["decisions.json 必须是对象且含 decisions 数组"], {}
    for k, d in enumerate(decisions):
        tag = d.get("group_id") or f"第{k+1}条"
        gid = d.get("group_id")
        if not gid:
            errors.append(f"第{k+1}条裁决缺 group_id")
            continue
        if gid in by_group:
            errors.append(f"{tag}: group_id 重复裁决")
            continue
        if gid not in groups:
            errors.append(f"{tag}: 未知候选组（candidates.json 中不存在）")
            continue
        verdict = d.get("verdict")
        if verdict not in VERDICTS:
            errors.append(f"{gid}: verdict 必须是 {sorted(VERDICTS)} 之一，收到 {verdict!r}")
            continue
        reason = str(d.get("reason") or "").strip()
        if len(reason) < MIN_REASON_LEN:
            errors.append(f"{gid}: reason 缺失或过短（<{MIN_REASON_LEN} 字符），逐案理由是硬性要求")
            continue
        g = groups[gid]
        facts = group_facts(g, recs)
        if verdict == "merge":
            canon = d.get("canonical")
            if not canon:
                errors.append(f"{gid}: verdict=merge 必须给出 canonical")
            elif canon not in g["members"]:
                errors.append(f"{gid}: canonical={canon} 不是组成员 {g['members']}（拒绝）")
            # M2：同 DOI 但书目坐标冲突 → 禁止自动并
            if facts["same_doi"] and facts["material_conflicts"]:
                fields = sorted({c["field"] for c in facts["material_conflicts"]})
                errors.append(
                    f"{gid}: [M2] 共享规范化 DOI({facts['shared_doi']}) 但书目坐标冲突 {fields}，"
                    f"必须 human_queue，禁止 merge")
            # M5：同名作者不同文献保护
            if facts["m5_pattern"]:
                errors.append(
                    f"{gid}: [M5] 同第一作者姓+同年但题名/容器显著不同，判 merge 有误并风险，"
                    f"应 keep_separate 并写明理由（或 human_queue）")
            # M3：仅弱证据（题名相似无 corroboration）→ 禁止 merge
            elif facts["grade"] == "weak" and not facts["same_doi"]:
                errors.append(
                    f"{gid}: [M3] 组证据分级为 weak（仅题名相似、无坐标/标识符 corroboration），"
                    f"禁止 merge")
            # M4：预印本-正式版并案时 canonical 必须是正式版
            if canon and "preprint_published" in facts["sig_types"] and facts["nonpreprint_members"]:
                if canon in facts["preprint_members"]:
                    errors.append(
                        f"{gid}: [M4] 预印本-正式版并案的 canonical 必须是正式版 "
                        f"{facts['nonpreprint_members']}，不能是预印本 {canon}")
        by_group[gid] = d
    missing = sorted(set(groups) - set(by_group))
    for gid in missing:
        errors.append(f"{gid}: 候选组缺少裁决（每个候选组都必须逐案裁决）")
    return errors, by_group


def build_lineage(canon_id, member_rec, evidence_note):
    return {
        "relation": "published_version_of",
        "canonical_record_id": canon_id,
        "preprint_record_id": member_rec["record_id"],
        "preprint_arxiv": member_rec.get("arxiv", ""),
        "preprint_url": member_rec.get("url", ""),
        "preprint_year": member_rec.get("year", ""),
        "preprint_version": member_rec.get("version", ""),
        "redirect": f"{member_rec['record_id']} -> {canon_id}",
        "evidence": evidence_note,
    }


def apply_merges(groups, by_group, recs):
    """施加校验通过的 merge；返回 merged_records, redirect_map, report_cases。"""
    canon_of = {}      # absorbed_id -> canonical_id
    merged_recs = {}   # canonical_id -> merged record
    cases = []
    for gid in sorted(by_group):
        d = by_group[gid]
        g = groups[gid]
        verdict = d["verdict"]
        case = {"group_id": gid, "verdict": verdict, "reason": d["reason"],
                "members": g["members"], "signals": g.get("signals", []),
                "evidence_grade": g.get("evidence_grade"),
                "field_conflicts": g.get("field_conflicts", [])}
        if verdict != "merge":
            if verdict == "human_queue":
                case["follow_up"] = ("人工核查路径：核对出版方页面/DOI 解析结果后再判；"
                                     "在结果中显式登记为未决不确定性，不得静默跳过。")
            cases.append(case)
            continue
        canon_id = d["canonical"]
        canon = copy.deepcopy(recs[canon_id])
        absorbed, exceptions, lineage = [], [], []
        aliases, other_ids = [], {"doi": [], "pmid": [], "arxiv": [], "url": []}
        for mid in g["members"]:
            if mid == canon_id:
                continue
            m = recs[mid]
            absorbed.append(mid)
            canon_of[mid] = canon_id
            if m.get("cite_key"):
                aliases.append(m["cite_key"])
            # 字段填充：canonical 缺失的字段从成员补全
            for f in FILL_FIELDS:
                if canon.get(f) in (None, "", []) and m.get(f) not in (None, "", []):
                    canon[f] = m[f]
            # 冲突字段入 exception list
            for f in EXCEPTION_FIELDS:
                cv, mv = canon.get(f), m.get(f)
                if cv in (None, "", []) or mv in (None, "", []):
                    continue
                if json.dumps(cv, ensure_ascii=False, sort_keys=True) != \
                   json.dumps(mv, ensure_ascii=False, sort_keys=True):
                    norm_eq = (norm_year(cv) == norm_year(mv) if f == "year"
                               else norm_text(cv) == norm_text(mv))
                    exceptions.append({"field": f, "canonical_value": cv,
                                       "member_id": mid, "member_value": mv,
                                       "normalized_equal": norm_eq})
            # 保留双方标识符
            for f in ("doi", "pmid", "arxiv", "url"):
                v = m.get(f)
                if v and v != canon.get(f) and v not in other_ids[f]:
                    other_ids[f].append(v)
            # 谱系：预印本并入正式版
            if is_preprint(m) and not is_preprint(recs[canon_id]):
                noted = any(s["type"] == "preprint_published" and s["grade"] == "strong"
                            for s in g.get("signals", []))
                lineage.append(build_lineage(
                    canon_id, m,
                    "材料内 note 字段声明版本关系" if noted else "题名一致 + 预印本身份信号"))
        canon["merged_from"] = absorbed
        canon["aliases"] = sorted(aliases)
        other_ids = {k: sorted(v) for k, v in other_ids.items() if v}
        if other_ids:
            canon["other_identifiers"] = other_ids
        if exceptions:
            canon["merge_exceptions"] = exceptions
        if lineage:
            canon["lineage"] = lineage
        merged_recs[canon_id] = canon
        case.update({"canonical": canon_id, "absorbed": absorbed,
                     "exceptions": exceptions, "lineage": lineage,
                     "redirects": {m: canon_id for m in absorbed}})
        cases.append(case)

    merged_records = []
    for rid in sorted(recs):
        if rid in canon_of:
            continue
        merged_records.append(merged_recs.get(rid, recs[rid]))

    redirect_map = {
        "schema_version": SCHEMA_VERSION,
        "record_redirects": {k: canon_of[k] for k in sorted(canon_of)},
        "cite_key_redirects": {recs[k]["cite_key"]: recs[canon_of[k]]["cite_key"]
                               for k in sorted(canon_of)
                               if recs[k].get("cite_key") and recs[canon_of[k]].get("cite_key")},
        "groups": {gid: {"canonical": by_group[gid]["canonical"],
                         "absorbed": [m for m in groups[gid]["members"]
                                      if m != by_group[gid]["canonical"]]}
                   for gid in sorted(by_group) if by_group[gid]["verdict"] == "merge"},
    }
    return merged_records, redirect_map, cases


def render_report_md(cases, summary):
    lines = ["# 归并裁决报告（identity-merge-court）", "",
             f"- 候选组总数: {summary['groups']}",
             f"- merge: {summary['merged']}  keep_separate: {summary['keep_separate']}  "
             f"human_queue: {summary['human_queue']}",
             f"- 记录数: {summary['records_before']} → {summary['records_after']}",
             f"- 重定向条目: {summary['redirects']}", ""]
    for c in cases:
        lines.append(f"## {c['group_id']} — {c['verdict']}")
        lines.append(f"- 成员: {', '.join(c['members'])}")
        if c.get("canonical"):
            lines.append(f"- canonical: {c['canonical']}（被吸收: {', '.join(c['absorbed'])}）")
        lines.append(f"- 证据分级: {c.get('evidence_grade')}")
        for s in c.get("signals", []):
            lines.append(f"  - [{s['grade']}] {s['type']}: {s['detail']}")
        lines.append(f"- 裁决理由: {c['reason']}")
        if c.get("field_conflicts"):
            lines.append("- 逐字段冲突表:")
            for fc in c["field_conflicts"]:
                vals = "; ".join(f"{rid}={v!r}" for rid, v in fc["values"].items())
                flag = "规范化一致" if fc["normalized_equal"] else "规范化不一致"
                lines.append(f"  - {fc['field']}（{flag}）: {vals}")
        if c.get("exceptions"):
            lines.append("- exception list（已并入 canonical 但需人工抽查的字段）:")
            for e in c["exceptions"]:
                lines.append(f"  - {e['field']}: canonical={e['canonical_value']!r} "
                             f"vs {e['member_id']}={e['member_value']!r}")
        if c.get("lineage"):
            lines.append("- 谱系:")
            for ln in c["lineage"]:
                lines.append(f"  - {ln['preprint_record_id']}（arXiv:{ln['preprint_arxiv']}, "
                             f"{ln['preprint_year']}）--{ln['relation']}--> "
                             f"{ln['canonical_record_id']}；重定向 {ln['redirect']}；"
                             f"证据: {ln['evidence']}")
        if c.get("follow_up"):
            lines.append(f"- 后续: {c['follow_up']}")
        lines.append("")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="身份裁决校验与施加（违反 M1–M5 即拒绝，退出码 1，原子不写产物）")
    ap.add_argument("--candidates", required=True)
    ap.add_argument("--records", required=True)
    ap.add_argument("--decisions", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    try:
        cand = load_json(args.candidates)
        recs = load_records(args.records)
        decisions_payload = load_json(args.decisions)
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        print(f"输入读取失败: {exc}", file=sys.stderr)
        return 2

    decisions = decisions_payload.get("decisions") if isinstance(decisions_payload, dict) else None
    if not isinstance(decisions, list):
        print("decisions.json 必须是对象且含 decisions 数组", file=sys.stderr)
        return 2
    groups = {g["group_id"]: g for g in cand.get("groups", [])}
    for gid, g in groups.items():
        for m in g["members"]:
            if m not in recs:
                print(f"候选组 {gid} 引用了 records 中不存在的记录 {m}", file=sys.stderr)
                return 2

    errors, by_group = validate(decisions, groups, recs)
    if errors:
        print("裁决校验失败（未写任何产物）：", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    # 全部通过才施加（原子：先全部构建于内存，再一次写出）
    merged_records, redirect_map, cases = apply_merges(groups, by_group, recs)
    summary = {
        "groups": len(groups),
        "merged": sum(1 for c in cases if c["verdict"] == "merge"),
        "keep_separate": sum(1 for c in cases if c["verdict"] == "keep_separate"),
        "human_queue": sum(1 for c in cases if c["verdict"] == "human_queue"),
        "records_before": len(recs),
        "records_after": len(merged_records),
        "redirects": len(redirect_map["record_redirects"]),
    }
    report = {"schema_version": SCHEMA_VERSION, "tool": "merge_adjudicate.py",
              "summary": summary, "cases": cases}

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "merged_records.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in merged_records), encoding="utf-8")
    (out_dir / "redirect_map.json").write_text(
        json.dumps(redirect_map, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out_dir / "merge_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out_dir / "merge_report.md").write_text(render_report_md(cases, summary), encoding="utf-8")

    print(f"校验通过。merge={summary['merged']} keep_separate={summary['keep_separate']} "
          f"human_queue={summary['human_queue']}  记录 {summary['records_before']}→{summary['records_after']}")
    print(f"已写出: {out_dir}/merged_records.jsonl, redirect_map.json, merge_report.json, merge_report.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())

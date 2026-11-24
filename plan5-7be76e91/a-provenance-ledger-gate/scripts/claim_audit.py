#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""claim_audit.py — 论断逐字对账（provenance-ledger-gate 步骤 3）

输入：
  --claims    claims.json，模型按 references/claim_schema.json 抽取的论断清单。
              每条：{plan_id, field_group, field, value, unit,
                     status(given/inferred/missing/conflict),
                     source:{file, locator, quote}}
  --registry  source_registry.py 产出的 registry.json（内含已抽取的来源文本）。

对账规则（NFKC 规范化 + 空白折叠后逐字匹配，详见 references/audit_method.md）：
  status in {given, conflict}（视为事实断言，必须核验）：
    无 source 或 source.file/source.quote 为空            -> missing_source（缺陷）
    source.file 未登记于 registry                          -> missing_source（缺陷）
    来源文件标记 needs_extraction（无法逐字核验）           -> unsupported（缺陷）
    quote 在来源文本中找不到                               -> unsupported（缺陷）
    quote 找到，但 value 中的数值与 quote 中的数值无交集    -> conflict（缺陷）
    quote 找到且数值不矛盾                                 -> supported（报告 char_offset）
  status == inferred  -> recorded_inferred（只记录，不判负）
  status == missing   -> recorded_missing（只记录，不判负）

输出：
  --out-json  audit.json（逐条 verdict + char_offset + 摘要统计，键排序，无时间戳）
  --out-md    audit.md（人读报告）

退出码：0=全部断言核验通过；2=输入/用法错误；3=存在 unsupported/conflict/missing_source
缺陷（缺陷清单打印到 stdout，产物仍写出）。
"""

import argparse
import json
import os
import re
import sys
import unicodedata

TOOL_VERSION = "1.0"
DEFECT_VERDICTS = ("unsupported", "conflict", "missing_source")
NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")


def normalize(text: str) -> str:
    """NFKC 规范化 + 全部空白折叠为单个空格。"""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).strip()


def numbers_of(text: str):
    """提取文本中的全部数值（整数/小数），返回 float 列表。"""
    return [float(m.group(0)) for m in NUMBER_RE.finditer(text or "")]


def load_json(path, what):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print("ERROR: 无法读取 %s (%s): %s" % (what, path, exc), file=sys.stderr)
        sys.exit(2)


def audit_claim(index, claim, sources):
    """返回 (result_dict, is_defect)。sources: rel_path -> registry entry。"""
    plan_id = str(claim.get("plan_id", ""))
    field_group = str(claim.get("field_group", ""))
    field = str(claim.get("field", ""))
    value = claim.get("value")
    unit = claim.get("unit")
    status = str(claim.get("status", ""))
    result = {
        "claim_index": index,
        "plan_id": plan_id,
        "field_group": field_group,
        "field": field,
        "value": value,
        "unit": unit,
        "status": status,
        "char_offset": None,
        "detail": "",
    }
    if status == "inferred":
        result["verdict"] = "recorded_inferred"
        result["detail"] = "模型推断值，仅记录，不参与判负；进入比较前须标注为假设"
        return result, False
    if status == "missing":
        result["verdict"] = "recorded_missing"
        result["detail"] = "方案未给出该字段，仅记录为缺口"
        return result, False
    if status not in ("given", "conflict"):
        result["verdict"] = "unsupported"
        result["detail"] = "非法 status: %r（允许 given/inferred/missing/conflict）" % status
        return result, True

    src = claim.get("source")
    if not isinstance(src, dict) or not src.get("file") or not src.get("quote"):
        result["verdict"] = "missing_source"
        result["detail"] = "given/conflict 断言缺少 source.file 或 source.quote，无法对账"
        return result, True
    entry = sources.get(src["file"])
    if entry is None:
        result["verdict"] = "missing_source"
        result["detail"] = "来源文件未登记于 registry: %s" % src["file"]
        return result, True
    if entry.get("needs_extraction") or not entry.get("text"):
        result["verdict"] = "unsupported"
        result["detail"] = ("来源 %s 无可用抽取文本（needs_extraction=true），"
                            "无法逐字核验，按规约隔离" % src["file"])
        return result, True

    nq = normalize(src["quote"])
    nt = normalize(entry["text"])
    offset = nt.find(nq)
    if offset < 0:
        result["verdict"] = "unsupported"
        result["detail"] = "quote 在 %s 中逐字查找失败（NFKC+空白折叠后）" % src["file"]
        return result, True
    result["char_offset"] = offset

    val_nums = numbers_of(str(value)) if value is not None else []
    quote_nums = numbers_of(nq)
    if val_nums and quote_nums and not any(v in quote_nums for v in val_nums):
        result["verdict"] = "conflict"
        result["detail"] = ("quote 已定位（offset=%d），但 value 数值 %s 与 quote 中数值 %s 无交集"
                            % (offset, val_nums, quote_nums))
        return result, True
    result["verdict"] = "supported"
    result["detail"] = "quote 逐字命中 %s（locator=%s, offset=%d）" % (
        src["file"], src.get("locator", ""), offset)
    return result, False


def render_markdown(report):
    lines = []
    lines.append("# 论断对账报告（claim_audit）")
    if report.get("note"):
        lines.append("")
        lines.append("> %s" % report["note"])
    s = report["summary"]
    lines.append("")
    lines.append("## 摘要")
    lines.append("")
    lines.append("- 论断总数：%d" % s["total"])
    lines.append("- supported：%d" % s["supported"])
    lines.append("- unsupported：%d" % s["unsupported"])
    lines.append("- conflict：%d" % s["conflict"])
    lines.append("- missing_source：%d" % s["missing_source"])
    lines.append("- recorded_inferred：%d" % s["recorded_inferred"])
    lines.append("- recorded_missing：%d" % s["recorded_missing"])
    lines.append("- 缺陷合计（unsupported+conflict+missing_source）：%d" % s["defects"])
    lines.append("- 门禁结论：**%s**" % ("通过 PASS" if s["defects"] == 0 else "拦截 BLOCK"))
    lines.append("")
    lines.append("## 逐条结果")
    lines.append("")
    lines.append("| # | plan_id | 字段 | status | verdict | char_offset | 说明 |")
    lines.append("|---|---------|------|--------|---------|-------------|------|")
    for r in report["results"]:
        off = "" if r["char_offset"] is None else str(r["char_offset"])
        lines.append("| %d | %s | %s.%s | %s | %s | %s | %s |" % (
            r["claim_index"], r["plan_id"], r["field_group"], r["field"],
            r["status"], r["verdict"], off, r["detail"]))
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="对 claims.json 中的 given/conflict 断言逐字对账来源文本，输出 audit.json/audit.md。")
    parser.add_argument("--claims", required=True, help="claims.json 路径")
    parser.add_argument("--registry", required=True, help="registry.json 路径（source_registry.py 产物）")
    parser.add_argument("--out-json", required=True, help="audit.json 输出路径")
    parser.add_argument("--out-md", required=True, help="audit.md 输出路径")
    parser.add_argument("--note", default=None,
                        help="写入输出的备注（示例数据必须写：合成示例 / SYNTHETIC EXAMPLE）")
    args = parser.parse_args(argv)

    claims_doc = load_json(args.claims, "claims.json")
    registry = load_json(args.registry, "registry.json")
    claims = claims_doc.get("claims") if isinstance(claims_doc, dict) else claims_doc
    if not isinstance(claims, list):
        print("ERROR: claims.json 必须是列表或含 \"claims\" 列表的对象", file=sys.stderr)
        return 2
    sources = {e["rel_path"]: e for e in registry.get("files", [])}

    results = []
    defects = []
    for i, claim in enumerate(claims):
        if not isinstance(claim, dict):
            print("ERROR: 第 %d 条论断不是对象" % i, file=sys.stderr)
            return 2
        result, is_defect = audit_claim(i, claim, sources)
        results.append(result)
        if is_defect:
            defects.append(result)

    counts = {v: 0 for v in ("supported", "unsupported", "conflict",
                             "missing_source", "recorded_inferred", "recorded_missing")}
    for r in results:
        counts[r["verdict"]] += 1
    report = {
        "tool": "claim_audit.py",
        "tool_version": TOOL_VERSION,
        "claims_file": args.claims,
        "registry_file": args.registry,
        "summary": {
            "total": len(results),
            "supported": counts["supported"],
            "unsupported": counts["unsupported"],
            "conflict": counts["conflict"],
            "missing_source": counts["missing_source"],
            "recorded_inferred": counts["recorded_inferred"],
            "recorded_missing": counts["recorded_missing"],
            "defects": len(defects),
        },
        "results": results,
    }
    if args.note is not None:
        report["note"] = args.note

    for path in (args.out_json, args.out_md):
        out_dir = os.path.dirname(os.path.abspath(path))
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
    with open(args.out_json, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    with open(args.out_md, "w", encoding="utf-8") as fh:
        fh.write(render_markdown(report))

    if defects:
        print("对账拦截：%d 条缺陷（unsupported/conflict/missing_source）：" % len(defects))
        for r in defects:
            print("DEFECT\t%s\t%s\t%s.%s\t%s" % (
                r["verdict"], r["plan_id"], r["field_group"], r["field"], r["detail"]))
        return 3
    print("OK audit: %d 条断言全部核验通过 -> %s, %s"
          % (counts["supported"], args.out_json, args.out_md))
    return 0


if __name__ == "__main__":
    sys.exit(main())

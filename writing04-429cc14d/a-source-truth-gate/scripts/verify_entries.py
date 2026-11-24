#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_entries.py — 文献条目身份与元数据核验器。

仅依赖 Python 3.10+ 标准库；无网络访问；确定性输出。
所有判定均仅以 --snapshot 提供的"组织方可信元数据快照"为依据；
本工具绝不声称"已联网核实"，也不会凭模型记忆补全 DOI/页码/年份。

状态机（详见 references/verification_policy.md）：
  verified_identity       身份确认（DOI 命中且字段一致，或按标题命中且字段一致）
  metadata_conflict       DOI 命中但 title/year/first_author 存在冲突
  not_found_in_snapshot   DOI 语法合法但快照无记录（≠伪造，仅覆盖不全）
  not_checked             无 DOI 且按标题无法确认（不得写"已核实"）
  suspected_fabricated    DOI 语法非法，或条目元数据匹配到的快照记录 DOI 不同
  invalid_input           输入行不是合法 JSON 或缺少必填字段（输入级缺陷）

用法：
  python3 verify_entries.py --entries entries.jsonl --snapshot snapshot.json --out DIR

退出码：
  1  存在 suspected_fabricated / metadata_conflict / invalid_input；
  0  其余情形（含 not_found_in_snapshot 与 not_checked，仅作警告）。
"""
import argparse
import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timezone

TOOL_NAME = "verify_entries"
TOOL_VERSION = "1.0.0"
DEFAULT_TIMESTAMP = "1970-01-01T00:00:00Z"

# DOI 语法：10.<4-9 位数字>/<非空白序列>，且整体不含任何空白字符。
DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")

FAIL_STATUSES = {"suspected_fabricated", "metadata_conflict", "invalid_input"}
ALL_STATUSES = FAIL_STATUSES | {
    "verified_identity",
    "not_found_in_snapshot",
    "not_checked",
}

BASIS_NOTE = (
    "本报告仅以输入快照（snapshot）为核验依据，未进行任何联网核实；"
    "not_found_in_snapshot 表示快照覆盖不全，不等于条目系伪造；"
    "DOI 解析失败（传输层）与 Crossref 404 均不得作为删除条目的理由。"
)


def resolve_timestamp() -> str:
    raw = os.environ.get("SOURCE_DATE_EPOCH", "").strip()
    if not raw:
        return DEFAULT_TIMESTAMP
    if raw.isdigit():
        return datetime.fromtimestamp(int(raw), tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
    return raw


def normalize_title(s) -> str:
    """标题归一化：NFKC + 大小写折叠 + 去除全部标点 + 折叠空白。"""
    if not isinstance(s, str):
        return ""
    s = unicodedata.normalize("NFKC", s).casefold()
    chars = []
    for ch in s:
        cat = unicodedata.category(ch)
        if cat.startswith("P"):  # 去除标点
            continue
        chars.append(ch)
    return " ".join("".join(chars).split())


def first_author_surname(authors) -> str:
    """提取第一作者姓：'姓, 名' 取逗号前；否则取第一个空白分隔词。NFKC+折叠。"""
    if not isinstance(authors, list) or not authors:
        return ""
    name = authors[0]
    if not isinstance(name, str):
        return ""
    name = unicodedata.normalize("NFKC", name).strip()
    if "," in name:
        surname = name.split(",", 1)[0]
    else:
        surname = name.split()[0] if name.split() else ""
    return surname.casefold()


def norm_year(y) -> str:
    return str(y).strip() if y is not None else ""


def has_whitespace(s: str) -> bool:
    return any(ch.isspace() for ch in s)


def compare_fields(entry: dict, record: dict):
    """逐字段比对 title（归一化）/ year / first_author，返回冲突列表。"""
    conflicts = []
    e_title = normalize_title(entry.get("title"))
    s_title = normalize_title(record.get("title"))
    if s_title and e_title != s_title:
        conflicts.append(
            {"field": "title", "entry_value": entry.get("title"),
             "snapshot_value": record.get("title")}
        )
    e_year = norm_year(entry.get("year"))
    s_year = norm_year(record.get("year"))
    if s_year and e_year != s_year:
        conflicts.append(
            {"field": "year", "entry_value": entry.get("year"),
             "snapshot_value": record.get("year")}
        )
    e_au = first_author_surname(entry.get("authors"))
    s_au = first_author_surname(record.get("authors"))
    if s_au and e_au != s_au:
        conflicts.append(
            {"field": "first_author", "entry_value": (entry.get("authors") or [None])[0],
             "snapshot_value": (record.get("authors") or [None])[0]}
        )
    return conflicts


def load_snapshot(path: str):
    """读取快照。接受 {"records": [...]} 或裸列表。返回 (by_doi, by_title, count)。"""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        records = data.get("records", [])
    elif isinstance(data, list):
        records = data
    else:
        raise ValueError("snapshot.json 顶层必须是对象或数组")
    by_doi, by_title = {}, {}
    for rec in records:
        if not isinstance(rec, dict):
            continue
        doi = rec.get("doi")
        if isinstance(doi, str) and doi.strip():
            by_doi[doi.strip().casefold()] = rec
        t = normalize_title(rec.get("title"))
        if t:
            by_title[t] = rec
    return by_doi, by_title, len(records)


def verify_entry(entry: dict, by_doi: dict, by_title: dict) -> dict:
    """对单条条目执行状态机判定，返回结果记录。"""
    result = {
        "id": entry.get("id"),
        "title": entry.get("title"),
        "status": None,
        "reason": None,
        "evidence": {},
        "conflicts": [],
    }
    doi_raw = entry.get("doi")
    doi = doi_raw.strip() if isinstance(doi_raw, str) else None
    title_key = normalize_title(entry.get("title"))

    if doi:
        # 分支一：DOI 语法非法 -> suspected_fabricated
        if not DOI_RE.match(doi) or has_whitespace(doi):
            result["status"] = "suspected_fabricated"
            result["reason"] = "invalid_doi_syntax"
            result["evidence"]["doi"] = doi_raw
            rec = by_title.get(title_key)
            if rec is not None:
                result["evidence"]["title_match_in_snapshot"] = {
                    "doi": rec.get("doi"), "year": rec.get("year")}
                result["reason"] = "invalid_doi_syntax_but_title_matches_snapshot"
            return result
        doi_key = doi.casefold()
        rec = by_doi.get(doi_key)
        # 分支二：DOI 命中快照 -> 逐字段比对
        if rec is not None:
            conflicts = compare_fields(entry, rec)
            result["evidence"]["matched_by"] = "doi"
            result["evidence"]["snapshot_doi"] = rec.get("doi")
            result["conflicts"] = conflicts
            if conflicts:
                result["status"] = "metadata_conflict"
                result["reason"] = "doi_resolves_but_fields_differ"
            else:
                result["status"] = "verified_identity"
                result["reason"] = "doi_match_and_fields_consistent"
            return result
        # 分支三：DOI 未命中 -> 看标题是否匹配到 DOI 不同的记录
        rec2 = by_title.get(title_key)
        if rec2 is not None:
            snap_doi = rec2.get("doi")
            if isinstance(snap_doi, str) and snap_doi.strip() \
                    and snap_doi.strip().casefold() != doi_key:
                result["status"] = "suspected_fabricated"
                result["reason"] = "title_matches_record_with_different_doi"
                result["evidence"]["claimed_doi"] = doi
                result["evidence"]["snapshot_record"] = {
                    "doi": snap_doi, "title": rec2.get("title"),
                    "year": rec2.get("year")}
                return result
        # 分支四：快照确实无此条目 -> not_found_in_snapshot（≠伪造）
        result["status"] = "not_found_in_snapshot"
        result["reason"] = "valid_doi_absent_from_snapshot"
        result["evidence"]["claimed_doi"] = doi
        result["evidence"]["warning"] = (
            "快照覆盖不全时不应判为伪造；不得据此删除条目，"
            "亦不得凭记忆补写元数据。")
        return result

    # 分支五：无 DOI -> 按归一化标题查找
    rec = by_title.get(title_key)
    if rec is not None:
        conflicts = compare_fields(entry, rec)
        # 标题已命中，仅保留 year/first_author 维度的一致性判断
        conflicts = [c for c in conflicts if c["field"] != "title"]
        result["evidence"]["matched_by"] = "title"
        result["evidence"]["snapshot_doi"] = rec.get("doi")
        if not conflicts:
            result["status"] = "verified_identity"
            result["reason"] = "title_match_and_fields_consistent"
            result["note"] = "by_title"
        else:
            result["status"] = "not_checked"
            result["reason"] = "title_match_but_year_or_author_differ"
            result["conflicts"] = conflicts
        return result
    result["status"] = "not_checked"
    result["reason"] = "no_doi_and_title_not_in_snapshot"
    return result


def render_markdown(report: dict) -> str:
    lines = []
    lines.append("# 条目核验报告（verify_entries）")
    lines.append("")
    lines.append(f"- 生成时间（UTC）：{report['generated_utc']}")
    lines.append(f"- 条目文件：`{report['entries_file']}`")
    lines.append(f"- 快照文件：`{report['snapshot_file']}`（快照记录数：{report['snapshot_record_count']}）")
    lines.append(f"- 核验依据：{BASIS_NOTE}")
    lines.append("")
    s = report["summary"]
    lines.append("## 汇总")
    lines.append("")
    lines.append("| 状态 | 数量 |")
    lines.append("| --- | --- |")
    for st in sorted(ALL_STATUSES):
        lines.append(f"| {st} | {s.get(st, 0)} |")
    lines.append(f"| **总计** | {s['total']} |")
    lines.append("")
    lines.append("## 逐条目结果")
    lines.append("")
    for r in report["results"]:
        lines.append(f"### {r['id']} — {r['status']}")
        lines.append("")
        lines.append(f"- 标题：{r.get('title')}")
        lines.append(f"- 判定理由：{r.get('reason')}")
        if r.get("note"):
            lines.append(f"- 备注：{r['note']}")
        if r.get("conflicts"):
            lines.append("- 冲突字段：")
            for c in r["conflicts"]:
                lines.append(
                    f"  - `{c['field']}`：条目值 `{c['entry_value']}` "
                    f"≠ 快照值 `{c['snapshot_value']}`")
        if r.get("evidence"):
            lines.append(f"- 证据：`{json.dumps(r['evidence'], ensure_ascii=False)}`")
        lines.append("")
    lines.append("---")
    lines.append("免责声明：本报告未联网核验；任何 suspected_fabricated / "
                 "metadata_conflict 条目必须隔离登记，不得进入成品文献表。")
    lines.append("")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="以可信快照核验文献条目身份与元数据（仅标准库、无网络）。")
    parser.add_argument("--entries", required=True, help="entries.jsonl 路径")
    parser.add_argument("--snapshot", required=True, help="snapshot.json 路径")
    parser.add_argument("--out", required=True, help="输出目录")
    args = parser.parse_args(argv)

    for p, label in ((args.entries, "--entries"), (args.snapshot, "--snapshot")):
        if not os.path.isfile(p):
            print(f"[verify_entries] ERROR: {label} 文件不存在: {p}", file=sys.stderr)
            return 1
    try:
        by_doi, by_title, rec_count = load_snapshot(args.snapshot)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"[verify_entries] ERROR: 快照不可解析: {exc}", file=sys.stderr)
        return 1

    results = []
    summary = {st: 0 for st in ALL_STATUSES}
    with open(args.entries, "r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError as exc:
                results.append({
                    "id": f"__line_{lineno}", "title": None,
                    "status": "invalid_input",
                    "reason": f"json_decode_error: {exc}",
                    "evidence": {"raw_line": line[:200]},
                    "conflicts": []})
                summary["invalid_input"] += 1
                continue
            if not isinstance(entry, dict) or not entry.get("id") \
                    or not isinstance(entry.get("title"), str):
                results.append({
                    "id": entry.get("id") if isinstance(entry, dict) else f"__line_{lineno}",
                    "title": entry.get("title") if isinstance(entry, dict) else None,
                    "status": "invalid_input",
                    "reason": "missing_required_field_id_or_title",
                    "evidence": {}, "conflicts": []})
                summary["invalid_input"] += 1
                continue
            r = verify_entry(entry, by_doi, by_title)
            summary[r["status"]] += 1
            results.append(r)

    summary_out = {"total": len(results)}
    summary_out.update({st: summary.get(st, 0) for st in sorted(ALL_STATUSES)})
    report = {
        "tool": TOOL_NAME,
        "version": TOOL_VERSION,
        "generated_utc": resolve_timestamp(),
        "verification_basis": BASIS_NOTE,
        "entries_file": args.entries,
        "snapshot_file": args.snapshot,
        "snapshot_record_count": rec_count,
        "summary": summary_out,
        "results": results,
    }

    try:
        os.makedirs(args.out, exist_ok=True)
        jpath = os.path.join(args.out, "verification_report.json")
        mpath = os.path.join(args.out, "verification_report.md")
        with open(jpath, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
            f.write("\n")
        with open(mpath, "w", encoding="utf-8") as f:
            f.write(render_markdown(report))
    except OSError as exc:
        print(f"[verify_entries] ERROR: 无法写出报告: {exc}", file=sys.stderr)
        return 1

    bad = summary["suspected_fabricated"] + summary["metadata_conflict"] \
        + summary["invalid_input"]
    print(
        f"[verify_entries] 共 {len(results)} 条：verified={summary['verified_identity']} "
        f"conflict={summary['metadata_conflict']} fabricated={summary['suspected_fabricated']} "
        f"not_found={summary['not_found_in_snapshot']} not_checked={summary['not_checked']} "
        f"invalid={summary['invalid_input']} -> {args.out}"
    )
    if bad:
        print(f"[verify_entries] 检出 {bad} 条必须隔离/修复的条目，退出码 1。",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

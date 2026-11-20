#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prepare_sheets.py — 准备两套互不可见的标注表；fixture 模式下转换外部标注。

用法:
    python3 prepare_sheets.py [--work /app/work]

dual_model 模式输出:
    <work>/sheet_s1.jsonl  正序空白表，行内仅 {record_id, decision, reason_code,
                           evidence_quote, note} 空槽，不含任何 S2 信息；
    <work>/sheet_s2.jsonl  逆序空白表，同样不含任何 S1 结论。
    模型分两次独立请求各填一份，另存为 annotations_s1.jsonl / annotations_s2.jsonl。

dual_fixture 模式输出:
    直接由 <work>/external_annotations.json 转换生成
    <work>/annotations_s1.jsonl（fixture 第一标注组）与
    <work>/annotations_s2.jsonl（fixture 第二标注组），
    每行带 source=external_fixture 与 fixture_annotator 溯源；
    fixture 原始内容已在 external_annotations.json 中原样保留。
    注意：fixture 是输入材料，不是事实或金标准。

退出码: 0=成功, 2=用法或IO错误, 3=校验失败（如 fixture 标注组不足两组）
"""
import argparse
import json
import sys
import traceback
from pathlib import Path

INC = {"include", "included", "纳入", "包含", "入选", "yes", "y", "1"}
EXC = {"exclude", "excluded", "排除", "剔除", "no", "n", "0"}
UNC = {"uncertain", "unsure", "maybe", "待定", "不确定", "存疑", "unclear"}


def eprint(*a):
    print(*a, file=sys.stderr)


def load_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def norm_decision(v):
    s = str(v).strip().lower()
    if s in INC:
        return "include"
    if s in EXC:
        return "exclude"
    if s in UNC:
        return "uncertain"
    return str(v).strip() or "uncertain"


def pick(d, keys, default=""):
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    low = {str(k).lower(): v for k, v in d.items()}
    for k in keys:
        if k.lower() in low and low[k.lower()] not in (None, ""):
            return low[k.lower()]
    return default


def extract_groups(raw):
    """从 fixture JSON 中抽取 (标注者名, [标注条目]) 列表，兼容两种常见结构。"""
    groups = []
    if isinstance(raw, dict):
        anns = raw.get("annotators") or raw.get("reviewers") or raw.get("raters")
        if isinstance(anns, list):
            for i, a in enumerate(anns):
                if not isinstance(a, dict):
                    continue
                name = pick(a, ("annotator_id", "reviewer_id", "name", "id"),
                            f"annotator{i + 1}")
                items = (a.get("annotations") or a.get("labels")
                         or a.get("decisions") or a.get("screening") or [])
                groups.append((str(name), items))
        else:
            for k, v in raw.items():
                if (isinstance(v, list) and v and isinstance(v[0], dict)
                        and not str(k).startswith("_")):
                    groups.append((str(k), v))
    return groups


def convert_group(name, items, valid_ids):
    rows, dropped = [], []
    for it in items:
        if not isinstance(it, dict):
            continue
        rid = str(pick(it, ("record_id", "id", "record", "uid"), "")).strip()
        if not rid:
            continue
        if rid not in valid_ids:
            dropped.append(rid)
            continue
        rows.append({
            "record_id": rid,
            "decision": norm_decision(pick(it, ("decision", "label", "judgement",
                                                "judgment", "结论"), "uncertain")),
            "reason_code": str(pick(it, ("reason_code", "reason", "rationale",
                                         "code", "理由"), "FIXTURE-NOCODE")),
            "evidence_quote": str(pick(it, ("evidence_quote", "evidence", "quote",
                                            "snippet", "证据"), "")),
            "note": str(pick(it, ("note", "comment", "备注"), "")),
            "source": "external_fixture",
            "fixture_annotator": name,
        })
    return rows, dropped


def main():
    ap = argparse.ArgumentParser(description="生成双套标注表 / 转换 fixture 外部标注")
    ap.add_argument("--work", default="/app/work")
    args = ap.parse_args()
    work = Path(args.work)

    summary = json.loads((work / "case_summary.json").read_text(encoding="utf-8"))
    dedup_path = work / "records_dedup.jsonl"
    if not dedup_path.exists():
        eprint(f"[prepare_sheets] 缺少 {dedup_path}，请先运行 exact_dedup.py")
        return 2
    records = load_jsonl(dedup_path)
    valid_ids = {r["record_id"] for r in records}
    mode = summary.get("mode", "dual_model")

    if mode == "dual_fixture":
        ext_path = work / "external_annotations.json"
        if not ext_path.exists():
            eprint(f"[prepare_sheets] 缺少 {ext_path}，请先运行 load_records.py")
            return 2
        ext = json.loads(ext_path.read_text(encoding="utf-8"))
        groups = []
        for fname, raw in ext.get("raw", {}).items():
            groups.extend(extract_groups(raw))
        if len(groups) < 2:
            eprint("[prepare_sheets] fixture 标注组不足两组，"
                   "请降级为 dual_model 双视角模式并在 result.json 中声明")
            return 3
        all_dropped = []
        for idx, role in enumerate(("s1", "s2")):
            name, items = groups[idx]
            rows, dropped = convert_group(name, items, valid_ids)
            all_dropped.extend(dropped)
            out = work / f"annotations_{role}.jsonl"
            with out.open("w", encoding="utf-8") as f:
                for r in rows:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
            print(f"[prepare_sheets] fixture 组 '{name}' -> {out} ({len(rows)} 条, "
                  f"source=external_fixture)")
        if all_dropped:
            print(f"[prepare_sheets] fixture 中 {len(all_dropped)} 条标注指向已被去重/"
                  f"不存在的记录，已丢弃并记录: {sorted(set(all_dropped))}")
            (work / "fixture_dropped.json").write_text(
                json.dumps({"dropped_record_ids": sorted(set(all_dropped)),
                            "reason": "指向去重移除或不存在的记录"},
                           ensure_ascii=False, indent=2), encoding="utf-8")
        print("[prepare_sheets] 注意: fixture 为输入材料而非金标准，"
              "分歧仍需按 D1-D4 分类并仲裁。")
    else:
        slot = {"record_id": "", "decision": "", "reason_code": "",
                "evidence_quote": "", "note": ""}
        for role, seq in (("s1", records), ("s2", list(reversed(records)))):
            out = work / f"sheet_{role}.jsonl"
            with out.open("w", encoding="utf-8") as f:
                for r in seq:
                    row = dict(slot)
                    row["record_id"] = r["record_id"]
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
            print(f"[prepare_sheets] 空白标注表 -> {out} ({len(seq)} 行)")
        print("[prepare_sheets] 请用两次独立请求分别填写 sheet_s1 / sheet_s2，"
              "另存为 annotations_s1.jsonl / annotations_s2.jsonl；"
              "S2 不得参照 S1 的任何结论。")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        eprint("[prepare_sheets] 未捕获异常:")
        traceback.print_exc()
        sys.exit(2)

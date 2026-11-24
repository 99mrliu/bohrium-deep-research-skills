#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""evidence_spotcheck.py — 证据 locator 抽查比对（门禁 2/4）。

对待检 result.json 中 new_items 的每一条：
1. 解析其 locator（"相对路径#/json/pointer"，如
   materials/crossref_response.json#/message/items/3），定位到源文件中的题录记录；
   locator 不可解析（文件缺失 / 指针越界 / 格式非法）即报 fail；
2. 逐字段比对 result 条目与源记录：
   - DOI：归一化后必须完全一致（不一致 = fail）；
   - 标题：归一化后一致 = pass，近似（子串）= warn，不一致 = fail；
   - 日期：与源记录任一日期完全一致 = pass，同年月/同年 = warn，不一致 = fail；
   - 作者：result 首作者 family name 应出现在源记录作者列表中（缺失 = warn）。

locator 以 --base（缺省为 result.json 所在目录）为根解析，且禁止越出该目录。

用法：
    python3 evidence_spotcheck.py --result result.json [--base DIR] [--out report.json]

退出码：0=pass，2=warn，1=fail。仅标准库；永不访问网络。
"""
import argparse
import sys
from pathlib import Path

from qa_lib import (QaError, check, compare_date, compare_title, dump_json,
                    load_json, make_report, norm_doi, record_authors,
                    record_dates, record_doi, record_title, resolve_locator)


def _item_label(idx, item):
    doi = item.get("doi") if isinstance(item, dict) else None
    return f"new_items[{idx}]" + (f" ({doi})" if doi else "")


def spotcheck(result, base_dir):
    checks = []
    items = result.get("new_items")
    if not isinstance(items, list):
        checks.append(check(
            "new_items.present", "fail",
            "result.json 缺少 new_items 数组，无法执行证据抽查"))
        return checks
    if not items:
        checks.append(check(
            "new_items.present", "warn",
            "new_items 为空数组：本窗口无新增声明，抽查无从执行（请确认这是否属实）"))
        return checks

    for idx, item in enumerate(items):
        label = _item_label(idx, item)
        if not isinstance(item, dict):
            checks.append(check(
                f"item[{idx}].shape", "fail", f"{label} 不是对象，无法抽查"))
            continue
        locator = item.get("locator")

        # --- 1. locator 可解析性 ---
        try:
            record, path = resolve_locator(locator, base_dir)
        except QaError as exc:
            checks.append(check(
                f"item[{idx}].locator", "fail",
                f"{label} locator 不可解析: {exc}", locator=locator))
            continue
        checks.append(check(
            f"item[{idx}].locator", "pass",
            f"{label} locator 可解析 → {path}", locator=locator))

        # --- 2. DOI 比对 ---
        want = norm_doi(item.get("doi"))
        got = record_doi(record)
        if not want:
            checks.append(check(
                f"item[{idx}].doi", "fail", f"{label} 缺少 doi 字段", locator=locator))
        elif want != got:
            checks.append(check(
                f"item[{idx}].doi", "fail",
                f"{label} DOI 不一致: result={want!r}, source={got!r}", locator=locator))
        else:
            checks.append(check(
                f"item[{idx}].doi", "pass", f"{label} DOI 一致: {want}",
                locator=locator))

        # --- 3. 标题比对 ---
        level, detail = compare_title(item.get("title"), record_title(record))
        status = {"match": "pass", "near": "warn",
                  "mismatch": "fail", "missing": "fail"}[level]
        checks.append(check(
            f"item[{idx}].title", status, f"{label} 标题比对: {detail}",
            locator=locator))

        # --- 4. 日期比对 ---
        level, detail = compare_date(
            item.get("published_date") or item.get("date"), record_dates(record))
        status = {"match": "pass", "partial": "warn", "year-only": "warn",
                  "mismatch": "fail", "missing": "fail"}[level]
        checks.append(check(
            f"item[{idx}].date", status, f"{label} 日期比对: {detail}",
            locator=locator))

        # --- 5. 首作者比对（warn 级） ---
        item_authors = item.get("authors")
        if item_authors:
            first = str(item_authors[0]).strip()
            # result 作者格式可能是 "Wei Zhang" 或 "Zhang, Wei"：取末/首 token 作为 family 猜测
            guess = first.split(",")[0].split()[-1] if "," not in first \
                else first.split(",")[0].strip()
            fams = [f.lower() for f in record_authors(record)]
            if fams and guess.lower() not in fams:
                checks.append(check(
                    f"item[{idx}].authors", "warn",
                    f"{label} 首作者 {guess!r} 未在源记录作者列表 {fams} 中出现",
                    locator=locator))
            else:
                checks.append(check(
                    f"item[{idx}].authors", "pass",
                    f"{label} 首作者 {guess!r} 与源记录一致", locator=locator))
    return checks


def main(argv=None):
    ap = argparse.ArgumentParser(description="证据 locator 抽查比对（tracking-qa-harness 门禁 2/4）")
    ap.add_argument("--result", required=True, help="待检 result.json 路径")
    ap.add_argument("--base", default=None,
                    help="locator 解析根目录（缺省为 result.json 所在目录）")
    ap.add_argument("--out", default=None, help="报告 JSON 输出路径（缺省打印到 stdout）")
    args = ap.parse_args(argv)

    try:
        result = load_json(args.result)
        base = args.base or str(Path(args.result).resolve().parent)
        checks = spotcheck(result, base)
    except QaError as exc:
        checks = [check("tool.error", "fail", f"工具自身错误: {exc}")]

    report = make_report("evidence_spotcheck", checks)
    if args.out:
        dump_json(report, args.out)
    print(f"[evidence_spotcheck] status={report['status']} "
          f"errors={report['summary']['errors']} warnings={report['summary']['warnings']}")
    for c in checks:
        if c["status"] != "pass":
            print(f"  - [{c['status']}] {c['id']}: {c['message']}")
    return {"pass": 0, "warn": 2, "fail": 1}[report["status"]]


if __name__ == "__main__":
    sys.exit(main())

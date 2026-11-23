#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""audit_report.py — report-compiler：报告与台账的独立对账审计器。

不信任编译产物，重新读台账逐项核对：
  (1) report_map.json 登记的每个数字与台账当前值相等（防台账改了报告没重编译）；
  (2) report.md 指标比较表的行数 == comparison.json 条目数（覆盖率 100%），
      且逐格数值与台账一致（防报告文本被手改）；
  (3) 结论段不允许出现未登记数字（正则抽数，比对台账数字全集 + report_map
      登记值 + 显式白名单），且结论分级与按规则重算结果一致；
  (4) 对比图文件存在且非空（PNG 查魔数 / SVG 查 <svg 标签）；
  (5) result.json 含非空 case_id 且 output_contract 全部字段有非空值。

用法：
    python3 audit_report.py --ledgers <台账目录> --report <编译产物目录>

输出：<report>/audit.json；终端打印 PASS/FAIL。
退出码：0 = PASS；1 = FAIL（逐条列错）；2 = 审计自身无法执行（缺关键文件）。
"""
import argparse
import json
import os
import re
import sys

VERSION = "1.0"
LEDGERS = ["inventory", "targets", "runs", "comparison", "attributions", "result"]
ALLOWED_STATUS = {"success", "partial", "unable", "refused"}
NUM_RE = re.compile(r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?")


def fmt(v):
    """与 compile_report.py 完全一致的确定性格式化规则。"""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    f = float(v)
    if f == int(f) and abs(f) < 1e15:
        return str(int(f))
    return format(f, ".6g")


def is_num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def load_json(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def resolve_pointer(ledgers_dir, pointer):
    """解析 'file.json#/a/b/0/c' 形式的指针，返回 (值, 错误信息)。"""
    if "#" not in pointer:
        return None, "指针缺少 # 分隔：%s" % pointer
    fname, path = pointer.split("#", 1)
    p = os.path.join(ledgers_dir, fname)
    if not os.path.isfile(p):
        return None, "台账文件不存在：%s" % fname
    try:
        node = load_json(p)
    except (OSError, json.JSONDecodeError) as e:
        return None, "台账 %s 解析失败：%s" % (fname, e)
    for tok in [t for t in path.split("/") if t != ""]:
        tok = tok.replace("~1", "/").replace("~0", "~")
        if isinstance(node, list):
            if not tok.isdigit() or int(tok) >= len(node):
                return None, "指针越界：%s（在 %s）" % (pointer, tok)
            node = node[int(tok)]
        elif isinstance(node, dict):
            if tok not in node:
                return None, "指针键不存在：%s（缺 %s）" % (pointer, tok)
            node = node[tok]
        else:
            return None, "指针穿过标量：%s" % pointer
    return node, None


def values_equal(a, b):
    if is_num(a) and is_num(b):
        fa, fb = float(a), float(b)
        return abs(fa - fb) <= 1e-9 * max(1.0, abs(fa), abs(fb))
    return a == b


def within_calc(entry, tol):
    diff = abs(float(entry["reproduced_value"]) - float(entry["paper_value"]))
    eps = 1e-12 * max(1.0, abs(float(tol["value"])))
    if tol["type"] == "abs":
        return diff <= float(tol["value"]) + eps
    pv = abs(float(entry["paper_value"]))
    return (diff / pv if pv else float("inf")) <= float(tol["value"]) + eps


def compute_grade(entries, attributions, tol_by_metric):
    if not entries:
        return "unable"
    out = [e for e in entries
           if not within_calc(e, tol_by_metric[e["metric_id"]])]
    if not out:
        return "reproducible"
    attr_keys = {(a["metric_id"], a["method"]) for a in attributions}
    if all((e["metric_id"], e["method"]) in attr_keys for e in out):
        return "partially_reproducible"
    return "not_reproducible"


def eval_derivation(derivation, cmp_entries, tol_by_metric, att_list):
    """对派生登记（计数/分级）独立重算。"""
    if derivation == "grade":
        return compute_grade(cmp_entries, att_list, tol_by_metric)
    m = re.match(r"^(count|count_within|count_out|count_out_attributed):comparison\.json#/entries$",
                 derivation)
    if not m:
        return None
    kind = m.group(1)
    if kind == "count":
        return len(cmp_entries)
    flags = [within_calc(e, tol_by_metric[e["metric_id"]]) for e in cmp_entries]
    if kind == "count_within":
        return sum(1 for f in flags if f)
    if kind == "count_out":
        return sum(1 for f in flags if not f)
    attr_keys = {(a["metric_id"], a["method"]) for a in att_list}
    return sum(1 for e, f in zip(cmp_entries, flags)
               if not f and (e["metric_id"], e["method"]) in attr_keys)


def collect_numbers(node, out):
    if is_num(node):
        out.add(float(node))
    elif isinstance(node, dict):
        for v in node.values():
            collect_numbers(v, out)
    elif isinstance(node, list):
        for v in node:
            collect_numbers(v, out)


def section_text(md, title):
    """提取 '## title' 到下一个 '## ' 之间的文本。"""
    lines = md.split("\n")
    out, on = [], False
    for ln in lines:
        if ln.startswith("## "):
            if on:
                break
            on = ln[3:].strip() == title
            continue
        if on:
            out.append(ln)
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description="报告-台账对账审计器（report-compiler）")
    ap.add_argument("--ledgers", required=True)
    ap.add_argument("--report", required=True)
    args = ap.parse_args()

    checks = []

    def record(cid, ok, detail):
        checks.append({"id": cid, "status": "PASS" if ok else "FAIL", "detail": detail})
        return ok

    rmap_path = os.path.join(args.report, "report_map.json")
    md_path = os.path.join(args.report, "report.md")
    for p in (rmap_path, md_path):
        if not os.path.isfile(p):
            print("FATAL：缺少 %s，无法审计" % p, file=sys.stderr)
            return 2
    try:
        rmap = load_json(rmap_path)
        with open(md_path, encoding="utf-8") as f:
            md = f.read()
    except (OSError, json.JSONDecodeError) as e:
        print("FATAL：审计输入解析失败：%s" % e, file=sys.stderr)
        return 2

    ledgers = {}
    for name in LEDGERS:
        p = os.path.join(args.ledgers, name + ".json")
        if os.path.isfile(p):
            try:
                ledgers[name] = load_json(p)
            except (OSError, json.JSONDecodeError) as e:
                record("ledger_parse_%s" % name, False, "%s.json 解析失败：%s" % (name, e))

    cmp_entries = ledgers.get("comparison", {}).get("entries", [])
    att_list = ledgers.get("attributions", {}).get("attributions", [])
    tol_by_metric = {m["id"]: m["tolerance"]
                     for m in ledgers.get("targets", {}).get("metrics", [])}

    # (1) report_map 登记值 == 台账当前值 / 派生重算值
    errs = []
    for e in rmap.get("entries", []):
        loc = e.get("location", "?")
        if "pointer" in e:
            val, err = resolve_pointer(args.ledgers, e["pointer"])
            if err:
                errs.append("%s：%s" % (loc, err))
            elif not values_equal(val, e["value"]):
                errs.append("%s：报告登记 %s != 台账当前值 %s（%s）"
                            % (loc, fmt(e["value"]) if is_num(e["value"]) else e["value"],
                               fmt(val) if is_num(val) else val, e["pointer"]))
        elif "derivation" in e:
            val = eval_derivation(e["derivation"], cmp_entries, tol_by_metric, att_list)
            if val is None:
                errs.append("%s：无法识别的派生规则 %s" % (loc, e["derivation"]))
            elif not values_equal(val, e["value"]):
                errs.append("%s：报告登记 %s != 重算值 %s（%s）" % (loc, e["value"], val, e["derivation"]))
        else:
            errs.append("%s：登记项既无 pointer 也无 derivation" % loc)
    record("map_entries_consistent", not errs,
           "全部 %d 项登记与台账一致" % len(rmap.get("entries", [])) if not errs
           else "；".join(errs))

    # (2) 指标比较表：行数 == comparison 条目数，且逐格与台账一致
    sec = section_text(md, "指标比较")
    rows = [ln for ln in sec.split("\n") if ln.startswith("|")]
    data_rows = [r for r in rows if not set(r.replace("|", "").strip()) <= set("-: ")]
    if data_rows:
        data_rows = data_rows[1:]  # 去掉表头
    errs = []
    if len(data_rows) != len(cmp_entries):
        errs.append("比较表行数 %d != comparison.json 条目数 %d（覆盖率不完整）"
                    % (len(data_rows), len(cmp_entries)))
    else:
        for i, (row, e) in enumerate(zip(data_rows, cmp_entries)):
            cells = [c.strip() for c in row.strip().strip("|").split("|")]
            if len(cells) != 8:
                errs.append("第 %d 行列数 %d != 8" % (i, len(cells)))
                continue
            tol = tol_by_metric.get(e["metric_id"], {"type": "?", "value": 0})
            expect = [e["metric_id"], e["method"], fmt(e["paper_value"]),
                      fmt(e["reproduced_value"]), fmt(e["abs_diff"]), fmt(e["rel_diff"]),
                      "%s %s" % (tol["type"], fmt(tol["value"])),
                      "✓ 在容差内" if within_calc(e, tol) else "✗ 超差"]
            for k, (got, want) in enumerate(zip(cells, expect)):
                if got != want:
                    errs.append("比较表第 %d 行第 %d 列：报告中为「%s」，台账应为「%s」"
                                % (i, k + 1, got, want))
    record("comparison_coverage", not errs,
           "比较表 %d 行与 comparison.json 全覆盖且逐格一致" % len(cmp_entries) if not errs
           else "；".join(errs))

    # (3) 结论段孤儿数字 + 分级一致性
    conc = section_text(md, "复现结论")
    allowed = set()
    for name, data in ledgers.items():
        collect_numbers(data, allowed)
    for e in rmap.get("entries", []):
        if is_num(e.get("value")):
            allowed.add(float(e["value"]))
    for w in rmap.get("number_whitelist", []):
        if is_num(w):
            allowed.add(float(w))
    orphans = []
    for tok in NUM_RE.findall(conc):
        v = float(tok)
        if not any(abs(v - a) <= 1e-9 * max(1.0, abs(a)) for a in allowed):
            orphans.append(tok)
    errs = ["结论段出现未登记数字：%s（台账/登记/白名单中均不存在）" % t for t in sorted(set(orphans))]
    grade_expect = compute_grade(cmp_entries, att_list, tol_by_metric)
    grade_map = rmap.get("conclusion", {}).get("grade")
    if grade_map != grade_expect:
        errs.append("report_map 分级 %s != 按规则重算 %s" % (grade_map, grade_expect))
    if grade_expect not in conc:
        errs.append("结论段未出现重算分级「%s」（疑似手改结论）" % grade_expect)
    record("conclusion_no_orphans", not errs,
           "结论段无孤儿数字，分级一致：%s" % grade_expect if not errs else "；".join(errs))

    # (4) 图文件存在且非空
    errs = []
    figs = rmap.get("figures", [])
    if cmp_entries and not figs:
        errs.append("存在比较项但 report_map 未登记任何图")
    for fg in figs:
        p = os.path.join(args.report, fg["path"])
        if not os.path.isfile(p):
            errs.append("图缺失：%s" % fg["path"])
            continue
        sz = os.path.getsize(p)
        if sz < 100:
            errs.append("图过小（%d 字节，疑似空图）：%s" % (sz, fg["path"]))
            continue
        with open(p, "rb") as f:
            head = f.read(512)
        if fg["path"].endswith(".png") and not head.startswith(b"\x89PNG"):
            errs.append("PNG 魔数错误：%s" % fg["path"])
        if fg["path"].endswith(".svg") and b"<svg" not in head:
            errs.append("SVG 缺少 <svg 标签：%s" % fg["path"])
    record("figures_present", not errs,
           "%d 个图文件存在且非空" % len(figs) if not errs else "；".join(errs))

    # (5) result.json：case_id 与 output_contract 全字段
    errs = []
    res = ledgers.get("result")
    if res is None:
        errs.append("result.json 缺失")
    else:
        if not isinstance(res.get("case_id"), str) or not res["case_id"].strip():
            errs.append("case_id 缺失或为空")
        if res.get("status") not in ALLOWED_STATUS:
            errs.append("status 非法：%s" % res.get("status"))
        oc = res.get("output_contract")
        if not isinstance(oc, dict) or not oc:
            errs.append("output_contract 缺失或为空（须含 output_contract 全部字段）")
        else:
            for k, v in oc.items():
                if v is None or (isinstance(v, str) and not v.strip()):
                    errs.append("output_contract 字段 %s 为空" % k)
    record("result_contract", not errs,
           "case_id 与 output_contract 全部 %d 个字段齐备" % (len(res.get("output_contract", {})) if res else 0)
           if not errs else "；".join(errs))

    overall = "PASS" if all(c["status"] == "PASS" for c in checks) else "FAIL"
    audit = {"generator": "audit_report.py %s" % VERSION, "overall": overall, "checks": checks}
    with open(os.path.join(args.report, "audit.json"), "w", encoding="utf-8") as f:
        json.dump(audit, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print("审计结果：%s" % overall)
    for c in checks:
        print("  [%s] %s：%s" % (c["status"], c["id"], c["detail"]))
    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""delivery_gate.py — 交付前验收门禁。

纯标准库、无网络、确定性输出。

用法：
    python3 delivery_gate.py --input-dir /input --output-dir /app/output \
        --chapter /app/output/chapter.md --report /app/output/gate_report

检查项（逐项 PASS/FAIL/WARN 写入 gate_report.json 与 gate_report.md）：
  G1 result.json 存在且为合法 JSON。
  G2 case_id 与 case.json 一致（逐字符）。
  G3 output_contract 声明的全部字段在 result.json 中存在；
     每个字段非空，或带明确 status:"unavailable"/"partial"/"unknown"/"failed" + 原因；
     不得残留 status:"pending"。
  G4 result.json 引用的产物文件真实存在于 --output-dir。
  G5 若契约或 task.md 含预览要求，检查预览文件（*.svg/*.png/*.pdf）存在于 --output-dir。
  G6 正文数值抽样可回溯：抽取 chapter.md 中的数值，检查其能在 sources 指向的
     材料文件中被定位（找不到记 WARN，全部来源文件缺失记 FAIL）。
退出码：任一 FAIL → 1；全部通过（可有 WARN）→ 0；自身运行错误 → 2。
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from contract_probe import _find_contract  # 复用契约定位逻辑，保证与探针一致

NUMBER_RE = re.compile(r"(?<![\w.])\d+(?:\.\d+)?%?(?![\w%])")
MAX_NUM_CHECK = 40  # 抽样上限，确定性：按出现顺序取前 N 个去重值


class Report:
    def __init__(self):
        self.checks = []

    def add(self, item, status, detail):
        assert status in ("PASS", "FAIL", "WARN")
        self.checks.append({"check": item, "status": status, "detail": detail})

    @property
    def failed(self):
        return any(c["status"] == "FAIL" for c in self.checks)


def _load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f), None
    except (OSError, json.JSONDecodeError) as e:
        return None, str(e)


def _field_ok(value):
    """判定单个契约字段的填充是否可接受。返回 (status, detail)。"""
    if isinstance(value, dict) and "status" in value:
        st = value.get("status")
        if st == "pending":
            return "FAIL", "残留骨架状态 pending，未填充"
        if st in ("unavailable", "partial", "unknown", "failed"):
            reason = "; ".join(str(x) for x in
                               (value.get("uncertainty") or []) + ([value.get("notes")] if value.get("notes") else []))
            if reason:
                return "PASS", "状态 %s，已附原因：%s" % (st, reason[:200])
            return "FAIL", "状态 %s 但未说明原因（uncertainty/notes 均为空）" % st
        if st in ("done", "ok", "complete", "completed"):
            v = value.get("value")
            if v is None or (isinstance(v, str) and not v.strip()) or v == [] or v == {}:
                return "FAIL", "标记 done 但 value 为空"
            return "PASS", "done，value 非空"
        return "WARN", "未知 status 值 %r，建议用 done/partial/unavailable/unknown/failed" % (st,)
    # 扁平值：非空即可
    if value is None or (isinstance(value, str) and not value.strip()) or value == [] or value == {}:
        return "FAIL", "字段为空且无状态说明"
    return "PASS", "扁平值非空"


def _collect_file_refs(obj, refs):
    """从 result.json 收集指向产物文件的路径（value 为字符串且像文件名，或 sources 里的 file）。"""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "value" and isinstance(v, str) and re.search(r"\.(md|txt|svg|png|pdf|json|csv|tex|docx?)$", v):
                refs.append(v)
            elif k == "file" and isinstance(v, str):
                refs.append(v)
            else:
                _collect_file_refs(v, refs)
    elif isinstance(obj, list):
        for v in obj:
            _collect_file_refs(v, refs)


def check_g1(rep, output_dir):
    path = os.path.join(output_dir, "result.json")
    if not os.path.isfile(path):
        rep.add("G1 result.json 存在且合法", "FAIL", "不存在：%s" % path)
        return None
    data, err = _load_json(path)
    if err:
        rep.add("G1 result.json 存在且合法", "FAIL", "JSON 解析失败：%s" % err)
        return None
    rep.add("G1 result.json 存在且合法", "PASS", path)
    return data


def check_g2(rep, result, input_dir):
    case, err = _load_json(os.path.join(input_dir, "case.json"))
    if err:
        rep.add("G2 case_id 一致", "WARN", "case.json 不可读，无法比对：%s" % err)
        return
    expected = case.get("case_id") if isinstance(case, dict) else None
    actual = result.get("case_id")
    if expected is None:
        rep.add("G2 case_id 一致", "WARN", "case.json 无 case_id，跳过比对")
    elif actual == expected:
        rep.add("G2 case_id 一致", "PASS", "case_id=%r" % actual)
    else:
        rep.add("G2 case_id 一致", "FAIL", "result.json=%r，case.json=%r（疑似串案例）" % (actual, expected))


def check_g3(rep, result, case):
    _, contract = _find_contract(case) if isinstance(case, dict) else (None, None)
    names = []
    if isinstance(contract, dict):
        inner = None
        for key in ("fields", "properties", "schema"):
            if isinstance(contract.get(key), dict):
                inner = contract[key]
                break
        if inner is None and isinstance(contract.get("required"), list):
            names = [n for n in contract["required"] if isinstance(n, str)]
        else:
            src = inner if inner is not None else contract
            names = [n for n in src if isinstance(n, str) and n not in ("fields", "properties", "schema")]
    elif isinstance(contract, list):
        names = [x if isinstance(x, str) else x.get("name")
                 for x in contract if isinstance(x, (str, dict))]
        names = [n for n in names if isinstance(n, str)]
    if not names:
        rep.add("G3 契约字段完整", "WARN", "case.json 中未找到 output_contract 字段清单，"
                "仅检查 result.json 是否含 case_id；请人工核对交付要求")
        if "case_id" not in result:
            rep.add("G3 契约字段完整", "FAIL", "result.json 缺少 case_id")
        return
    for name in names:
        if name not in result:
            rep.add("G3 契约字段完整", "FAIL", "缺少字段 %r" % name)
        else:
            st, detail = _field_ok(result[name])
            rep.add("G3 契约字段完整", st, "字段 %r：%s" % (name, detail))


def check_g4(rep, result, output_dir, input_dir):
    refs = []
    _collect_file_refs(result, refs)
    artifact_refs = []
    material_refs = []
    for r in sorted(set(refs)):
        # sources.file 指向输入材料；value 指向交付产物
        candidate_out = os.path.normpath(os.path.join(output_dir, r))
        candidate_in = os.path.normpath(os.path.join(input_dir, r))
        if os.path.isfile(candidate_out) or os.path.isfile(candidate_in):
            (artifact_refs if os.path.isfile(candidate_out) else material_refs).append(r)
        else:
            rep.add("G4 引用文件存在", "FAIL", "引用文件不存在（output/input 均未找到）：%s" % r)
    rep.add("G4 引用文件存在", "PASS", "核对 %d 个引用：产物 %d、材料 %d"
            % (len(set(refs)), len(artifact_refs), len(material_refs)))


def check_g5(rep, case, input_dir, output_dir):
    need_preview = False
    text = json.dumps(case, ensure_ascii=False) if isinstance(case, (dict, list)) else ""
    task_path = os.path.join(input_dir, "task.md")
    if os.path.isfile(task_path):
        try:
            with open(task_path, "r", encoding="utf-8") as f:
                text += "\n" + f.read()
        except OSError:
            pass
    if re.search(r"预览|preview|渲染|render|svg|png|pdf", text, re.I):
        need_preview = True
    if not need_preview:
        rep.add("G5 预览存在", "PASS", "契约与 task.md 未提预览要求，跳过")
        return
    previews = [fn for fn in sorted(os.listdir(output_dir))
                if re.search(r"\.(svg|png|pdf)$", fn, re.I)] if os.path.isdir(output_dir) else []
    if previews:
        rep.add("G5 预览存在", "PASS", "发现预览文件：%s" % ", ".join(previews))
    else:
        rep.add("G5 预览存在", "FAIL", "要求预览但 %s 下无 .svg/.png/.pdf" % output_dir)


def check_g6(rep, result, chapter_path, input_dir, output_dir):
    if not chapter_path or not os.path.isfile(chapter_path):
        rep.add("G6 数值可回溯抽样", "WARN", "未提供 chapter 文件，跳过数值回溯抽样")
        return
    try:
        with open(chapter_path, "r", encoding="utf-8") as f:
            chapter = f.read()
    except OSError as e:
        rep.add("G6 数值可回溯抽样", "WARN", "chapter 读取失败：%s" % e)
        return
    # 收集 sources 指向的材料文本
    refs = []
    _collect_file_refs(result.get("sources") if isinstance(result, dict) else None, refs)
    for key in ("artifact", "essay", "chapter"):
        v = result.get(key) if isinstance(result, dict) else None
        if isinstance(v, dict):
            _collect_file_refs({"sources": v.get("sources")}, refs)
    # 汇总所有字段的 sources
    def all_sources(o):
        out = []
        if isinstance(o, dict):
            for k, v in o.items():
                if k == "sources":
                    _collect_file_refs(v, out)
                else:
                    out.extend(all_sources(v))
        elif isinstance(o, list):
            for v in o:
                out.extend(all_sources(v))
        return out
    refs = sorted(set(all_sources(result)))
    corpus = ""
    missing = []
    for r in refs:
        for base in (input_dir, output_dir):
            p = os.path.normpath(os.path.join(base, r))
            if os.path.isfile(p):
                try:
                    with open(p, "r", encoding="utf-8", errors="replace") as f:
                        corpus += "\n" + f.read()
                except OSError:
                    pass
                break
        else:
            missing.append(r)
    if not refs:
        rep.add("G6 数值可回溯抽样", "WARN", "result.json 无任何 sources 引用，无法回溯")
        return
    nums = []
    seen = set()
    for m in NUMBER_RE.finditer(chapter):
        tok = m.group(0)
        if tok not in seen:
            seen.add(tok)
            nums.append(tok)
        if len(nums) >= MAX_NUM_CHECK:
            break
    if not nums:
        rep.add("G6 数值可回溯抽样", "PASS", "正文无数值需回溯；来源 %d 个" % len(refs))
        return
    if not corpus:
        rep.add("G6 数值可回溯抽样", "FAIL",
                "sources 引用的材料全部不可读（%s），正文 %d 个数值无法回溯"
                % (", ".join(missing) or "无引用可读", len(nums)))
        return
    unmatched = [t for t in nums if t.rstrip("%") not in corpus]
    if missing:
        rep.add("G6 数值可回溯抽样", "WARN", "部分来源文件缺失：%s" % ", ".join(missing))
    if unmatched:
        rep.add("G6 数值可回溯抽样", "WARN",
                "抽样 %d 个数值中 %d 个未在 sources 材料中定位到：%s（可能为派生值，请人工确认）"
                % (len(nums), len(unmatched), ", ".join(unmatched[:10])))
    else:
        rep.add("G6 数值可回溯抽样", "PASS", "抽样 %d 个数值均可在 sources 材料中定位" % len(nums))


def write_reports(rep, report_prefix, result_path, chapter_path):
    summary = {
        "result": "FAIL" if rep.failed else "PASS",
        "result_json": result_path,
        "chapter": chapter_path,
        "checks": rep.checks,
    }
    json_path = report_prefix + ".json"
    md_path = report_prefix + ".md"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
        f.write("\n")
    lines = ["# 交付门禁报告", "", "总体结论：**%s**" % summary["result"], "",
             "| 检查项 | 结果 | 说明 |", "|---|---|---|"]
    for c in rep.checks:
        detail = c["detail"].replace("|", "\\|").replace("\n", " ")
        lines.append("| %s | %s | %s |" % (c["check"], c["status"], detail))
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return json_path, md_path


def main(argv=None):
    ap = argparse.ArgumentParser(description="交付前验收门禁")
    ap.add_argument("--input-dir", required=True)
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--chapter", default=None, help="章节正文路径（用于数值回溯抽样）")
    ap.add_argument("--report", default=None, help="报告前缀，默认 <output-dir>/gate_report")
    args = ap.parse_args(argv)

    rep = Report()
    result_path = os.path.join(args.output_dir, "result.json")
    result = check_g1(rep, args.output_dir)
    case = None
    if os.path.isfile(os.path.join(args.input_dir, "case.json")):
        case, _ = _load_json(os.path.join(args.input_dir, "case.json"))
    if result is not None:
        check_g2(rep, result, args.input_dir)
        if isinstance(case, dict):
            check_g3(rep, result, case)
        else:
            rep.add("G3 契约字段完整", "WARN", "case.json 不可用，跳过契约字段比对")
        check_g4(rep, result, args.output_dir, args.input_dir)
        chapter = args.chapter
        if chapter is None:
            for cand in ("chapter.md", "chapter.txt"):
                p = os.path.join(args.output_dir, cand)
                if os.path.isfile(p):
                    chapter = p
                    break
        check_g6(rep, result, chapter, args.input_dir, args.output_dir)
    check_g5(rep, case, args.input_dir, args.output_dir)

    prefix = args.report or os.path.join(args.output_dir, "gate_report")
    os.makedirs(os.path.dirname(os.path.abspath(prefix)), exist_ok=True)
    jp, mp = write_reports(rep, prefix, result_path, args.chapter)
    for c in rep.checks:
        print("[%s] %s — %s" % (c["status"], c["check"], c["detail"]))
    print("报告：%s / %s" % (jp, mp))
    if rep.failed:
        print("门禁结论：FAIL —— 修复后重跑，不得交付", file=sys.stderr)
        return 1
    print("门禁结论：PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())

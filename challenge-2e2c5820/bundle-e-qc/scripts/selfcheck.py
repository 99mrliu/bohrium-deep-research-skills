#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""selfcheck.py — 聚合六道质控门（定义见 references/qc_gates.md），输出 qc_report.md。

用法:
    python3 selfcheck.py <out_dir> <case.json>

质控门:
    G1 契约字段齐全     validate_result.py 通过                     FAIL 级
    G2 状态诚实         status 词表/部分完成必带 uncertainty/有过程记录 FAIL 级
    G3 结论-条件一致    lint_review.py 无硬违规（警告记 WARN）        FAIL 级
    G4 证据锚定密度     锚点数 ≥3                                    WARN 级
    G5 产物可复算校验   manifest.json 中全部哈希仍可复算匹配          FAIL 级
    G6 交付物齐全       review_report.md / result.json / 渲染预览     FAIL 级

退出码: 0 = 无 FAIL（允许 WARN）；1 = 存在 FAIL。
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MIN_ANCHORS = 3
ANCHOR_RE = re.compile(r"\[L\d+\]|（第[^）]{1,15}节）")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def run_tool(script, args):
    p = subprocess.run([sys.executable, os.path.join(SCRIPT_DIR, script)] + list(args),
                       capture_output=True, text=True)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def gate_g1(out_dir, case_json):
    result = os.path.join(out_dir, "result.json")
    if not os.path.isfile(result):
        return ("G1", "契约字段齐全", "FAIL", "缺少 result.json")
    rc, out = run_tool("validate_result.py", [case_json, result])
    if rc == 0:
        return ("G1", "契约字段齐全", "PASS", out.strip().splitlines()[-1])
    tail = "；".join(out.strip().splitlines()[:6])
    return ("G1", "契约字段齐全", "FAIL", "validate_result 未通过(exit=%d)：%s" % (rc, tail))


def gate_g2(out_dir):
    path = os.path.join(out_dir, "result.json")
    if not os.path.isfile(path):
        return ("G2", "状态诚实", "FAIL", "缺少 result.json")
    try:
        with open(path, encoding="utf-8") as f:
            r = json.load(f)
    except Exception as e:  # noqa: BLE001
        return ("G2", "状态诚实", "FAIL", "result.json 解析失败：%s" % e)
    problems = []
    st = r.get("status")
    if st not in ("complete", "partial", "failed"):
        problems.append("status 取值非法: %r" % (st,))
    unc = r.get("uncertainty")
    if st in ("partial", "failed") and (not isinstance(unc, list) or not unc):
        problems.append("status=%s 但 uncertainty 为空" % st)
    if not r.get("change_record"):
        problems.append("change_record 为空（无过程记录，无法复核状态演化）")
    if problems:
        return ("G2", "状态诚实", "FAIL", "；".join(problems))
    return ("G2", "状态诚实", "PASS", "status=%s，不确定性/过程记录齐备" % st)


def gate_g3(out_dir):
    review = os.path.join(out_dir, "review_report.md")
    if not os.path.isfile(review):
        return ("G3", "结论-条件一致", "FAIL", "缺少 review_report.md")
    rc, out = run_tool("lint_review.py", [review])
    m = re.search(r"(\d+) 个硬违规，(\d+) 个警告", out)
    hard = int(m.group(1)) if m else (1 if rc else 0)
    warn = int(m.group(2)) if m else 0
    if rc == 2 or hard:
        first = next((ln for ln in out.splitlines() if "硬违规" in ln), "")
        return ("G3", "结论-条件一致", "FAIL", "lint 硬违规 %d 个；首条：%s" % (hard, first))
    if warn:
        return ("G3", "结论-条件一致", "WARN", "lint 无硬违规，%d 个警告" % warn)
    return ("G3", "结论-条件一致", "PASS", "lint 通过（0 硬违规，0 警告）")


def gate_g4(out_dir):
    review = os.path.join(out_dir, "review_report.md")
    if not os.path.isfile(review):
        return ("G4", "证据锚定密度", "FAIL", "缺少 review_report.md")
    with open(review, encoding="utf-8") as f:
        n = len(ANCHOR_RE.findall(f.read()))
    if n >= MIN_ANCHORS:
        return ("G4", "证据锚定密度", "PASS", "锚点 %d 个（≥%d）" % (n, MIN_ANCHORS))
    return ("G4", "证据锚定密度", "WARN", "锚点仅 %d 个（<%d），请补充定位符" % (n, MIN_ANCHORS))


def gate_g5(out_dir):
    mpath = os.path.join(out_dir, "manifest.json")
    if not os.path.isfile(mpath):
        return ("G5", "产物可复算校验", "FAIL", "缺少 manifest.json（先运行 make_manifest.py）")
    with open(mpath, encoding="utf-8") as f:
        manifest = json.load(f)
    bad, missing, checked = [], [], 0
    names = set()
    for e in manifest.get("files", []):
        p = e.get("path", "")
        names.add(os.path.basename(p))
        if not os.path.isfile(p):
            missing.append(p)
            continue
        checked += 1
        if sha256_file(p) != e.get("sha256"):
            bad.append(p)
    if missing or bad:
        detail = []
        if missing:
            detail.append("文件缺失: %s" % ", ".join(missing[:3]))
        if bad:
            detail.append("哈希不匹配: %s" % ", ".join(os.path.basename(x) for x in bad[:3]))
        return ("G5", "产物可复算校验", "FAIL", "；".join(detail))
    note = "复算 %d 个文件哈希全部匹配" % checked
    for must in ("result.json", "review_report.md"):
        if must not in names:
            note += "；但 manifest 未覆盖 %s（建议重新生成）" % must
            return ("G5", "产物可复算校验", "WARN", note)
    return ("G5", "产物可复算校验", "PASS", note)


def gate_g6(out_dir):
    problems = []
    for must in ("review_report.md", "result.json"):
        if not os.path.isfile(os.path.join(out_dir, must)):
            problems.append("缺少 %s" % must)
    previews = [fn for fn in os.listdir(out_dir)
                if os.path.splitext(fn)[1].lower() in (".html", ".pdf", ".png")] \
        if os.path.isdir(out_dir) else []
    if not previews:
        problems.append("缺少渲染预览（review_report.html 或 PDF/PNG）")
    if problems:
        return ("G6", "交付物齐全", "FAIL", "；".join(problems))
    return ("G6", "交付物齐全", "PASS", "review_report.md / result.json / 预览(%s) 齐备"
            % ", ".join(sorted(previews)))


def main(argv=None):
    ap = argparse.ArgumentParser(description="聚合 G1-G6 质控门并输出 qc_report.md")
    ap.add_argument("out_dir")
    ap.add_argument("case_json")
    args = ap.parse_args(argv)

    if not os.path.isdir(args.out_dir):
        print("错误：交付目录不存在: %s" % args.out_dir, file=sys.stderr)
        return 2
    if not os.path.isfile(args.case_json):
        print("错误：case.json 不存在: %s" % args.case_json, file=sys.stderr)
        return 2

    gates = [gate_g1(args.out_dir, args.case_json),
             gate_g2(args.out_dir),
             gate_g3(args.out_dir),
             gate_g4(args.out_dir),
             gate_g5(args.out_dir),
             gate_g6(args.out_dir)]

    n_fail = sum(1 for g in gates if g[2] == "FAIL")
    n_warn = sum(1 for g in gates if g[2] == "WARN")
    overall = "FAIL" if n_fail else ("WARN" if n_warn else "PASS")
    now = datetime.datetime.now().isoformat(timespec="seconds")

    lines = ["# 质控报告（selfcheck）", "",
             "- 生成时间：%s" % now,
             "- 交付目录：`%s`" % os.path.abspath(args.out_dir),
             "- 依据：references/qc_gates.md（G1–G6）",
             "- 总体门：**%s**（FAIL %d / WARN %d / PASS %d）"
             % (overall, n_fail, n_warn, 6 - n_fail - n_warn), "",
             "| 门 | 名称 | 结果 | 说明 |", "| --- | --- | --- | --- |"]
    for gid, name, st, detail in gates:
        lines.append("| %s | %s | %s | %s |" % (gid, name, st, detail.replace("|", "/")))
    if overall != "PASS":
        lines += ["",
                  "> 处置要求：FAIL 必须修复后再交付；无法修复时将 result.json 降级为 "
                  "status=partial 并在 uncertainty 中写清缺口（见 references/partial_policy.md）。"]
    report = "\n".join(lines) + "\n"
    rpath = os.path.join(args.out_dir, "qc_report.md")
    with open(rpath, "w", encoding="utf-8") as f:
        f.write(report)

    for gid, name, st, detail in gates:
        print("%s %s: %s — %s" % (gid, name, st, detail))
    print("总体门: %s（详见 %s）" % (overall, rpath))
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""report_render.py — 复核报告渲染器（中文 Markdown，纯 stdlib）

把 result.json（+ 可选 replay_manifest.json）渲染成人类可读的复核报告，章节：
  案例标识与状态 / 主结果表 / 来源清单 / 不确定性与未完成项 / 变更记录 / 可复跑性。
可复跑性一节会对 manifest 引用的文件重新哈希，如实标注 fresh/stale/missing-input。

退出码：0 成功；2 用法/输入错误。
"""
import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def load_json(path, what):
    if not os.path.isfile(path):
        print(f"[错误] {what} 文件不存在: {path}", file=sys.stderr)
        sys.exit(2)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"[错误] {what} JSON 解析失败: {path}: {e}", file=sys.stderr)
        sys.exit(2)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def md_cell(v):
    if v is None:
        return "—"
    if isinstance(v, (list, tuple)):
        return "<br>".join(md_cell(x) for x in v) or "—"
    if isinstance(v, dict):
        v = json.dumps(v, ensure_ascii=False)
    s = str(v).replace("|", "\\|").replace("\n", " ")
    return s if len(s) <= 120 else s[:117] + "..."


def render_candidates(cands):
    lines = ["## 主结果表", ""]
    if not isinstance(cands, list) or not cands:
        lines += ["（无候选记录，或 candidates 尚未填写。）", ""]
        return lines
    if not all(isinstance(c, dict) for c in cands):
        lines += ["```json", json.dumps(cands, ensure_ascii=False, indent=2), "```", ""]
        return lines
    keys = []
    for c in cands:
        for k in c.keys():
            if k not in keys:
                keys.append(k)
    head = [k for k in ("name", "title", "pub_no", "id") if k in keys]
    cols = head + [k for k in keys if k not in head]
    lines.append("| " + " | ".join(cols) + " |")
    lines.append("| " + " | ".join("---" for _ in cols) + " |")
    for c in cands:
        lines.append("| " + " | ".join(md_cell(c.get(k)) for k in cols) + " |")
    lines.append("")
    return lines


def render_sources(sources):
    lines = ["## 来源清单", ""]
    if not isinstance(sources, list) or not sources:
        lines += ["（无来源记录。）", ""]
        return lines
    lines += ["| 名称 | 版本 | 查询/访问日期 |", "| --- | --- | --- |"]
    for s in sources:
        if isinstance(s, dict):
            lines.append("| {} | {} | {} |".format(
                md_cell(s.get("name")), md_cell(s.get("version")),
                md_cell(s.get("query_date") or s.get("access_date"))))
        else:
            lines.append(f"| {md_cell(s)} | — | — |")
    lines.append("")
    return lines


def render_replay(manifest, manifest_path):
    lines = ["## 可复跑性", ""]
    if manifest is None:
        lines += ["（未提供 replay manifest，无法评估可复跑性。）", ""]
        return lines
    env = manifest.get("environment", {})
    lines.append(f"- manifest 生成时间: `{manifest.get('generated_at')}`")
    lines.append(f"- 记录环境: Python {env.get('python', '?')} / {env.get('platform', '?')}")
    lines.append("")
    steps = manifest.get("steps", [])
    if not steps:
        lines += ["（manifest 中无步骤记录。）", ""]
        return lines
    lines += ["| 步骤 | 命令 | 输入 | 输出 | 复跑状态 |", "| --- | --- | --- | --- | --- |"]
    base = os.path.dirname(os.path.abspath(manifest_path)) if manifest_path else None
    for i, step in enumerate(steps, 1):
        stale, missing = False, False
        for group in ("inputs", "outputs"):
            for fe in step.get(group, []):
                p, want = fe.get("path"), fe.get("sha256")
                real = p
                if p and not os.path.isfile(p) and base:
                    cand = os.path.normpath(os.path.join(step.get("workdir", base), p)) \
                        if not os.path.isabs(p) else p
                    real = cand
                if not (real and os.path.isfile(real)):
                    if group == "inputs":
                        missing = True
                    else:
                        stale = True
                elif want and sha256_file(real) != want:
                    stale = True
        status = "missing-input（输入缺失）" if missing else \
                 ("stale（文件已变化）" if stale else "fresh（未变化，可复跑）")
        ins = len(step.get("inputs", []))
        outs = len(step.get("outputs", []))
        lines.append("| {} | {} | {} 个 | {} 个 | {} |".format(
            i, md_cell(step.get("cmd")), ins, outs, status))
    lines.append("")
    return lines


def main():
    ap = argparse.ArgumentParser(description="渲染中文复核报告 Markdown")
    ap.add_argument("--result", required=True, help="result.json 路径")
    ap.add_argument("--manifest", default=None, help="可选 replay_manifest.json 路径")
    ap.add_argument("--out", required=True, help="review.md 输出路径")
    args = ap.parse_args()

    result = load_json(args.result, "result.json")
    manifest = load_json(args.manifest, "replay manifest") if args.manifest else None

    L = ["# 复核报告", "",
         f"> 由 result-contract-replay-compiler 于 {utc_now()} 自动生成，供人工复核使用。", ""]

    L += ["## 案例标识与状态", "",
          f"- **case_id**: `{result.get('case_id')}`",
          f"- **交付状态**: **{result.get('status')}**",
          ""]
    note = result.get("omissions_note")
    if note:
        L += [f"- **遗漏与限制说明**: {note}", ""]

    L += render_candidates(result.get("candidates"))
    L += render_sources(result.get("sources"))

    L += ["## 不确定性与未完成项", ""]
    unc = result.get("uncertainty")
    if isinstance(unc, list) and unc:
        L += [f"- {u}" for u in unc]
    else:
        L.append("无（所有契约字段均已填写）。")
    L.append("")

    L += ["## 变更记录", ""]
    cr = result.get("change_records")
    if isinstance(cr, list) and cr:
        L += ["| 时间 (UTC) | 说明 |", "| --- | --- |"]
        for r in cr:
            if isinstance(r, dict):
                L.append(f"| {md_cell(r.get('ts'))} | {md_cell(r.get('note'))} |")
            else:
                L.append(f"| — | {md_cell(r)} |")
    else:
        L.append("（无变更记录。）")
    L.append("")

    L += render_replay(manifest, args.manifest)

    d = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(d, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print(f"[完成] 复核报告已写入: {args.out}（{len(L)} 行）")
    return 0


if __name__ == "__main__":
    sys.exit(main())

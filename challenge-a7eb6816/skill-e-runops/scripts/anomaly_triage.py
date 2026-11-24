#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""anomaly_triage.py — 输入异常分流器（仅 Python 3 标准库）。

扫描 case.json / task.md / 输入目录，输出 anomaly_register.json 与
anomaly_register.md。每条记录：
  {kind, locator, evidence, disposition ∈ proceed / mark-gap / halt, note}

四类异常：
  missing_input    引用到的文件路径不存在或为空
  conflict         跨文件数值冲突（同一锚点语境 ±10 字符窗口内出现不同数值；
                   保守误报可接受，一律列入人工确认）
  confidentiality  涉密/未发表标记（保密、机密、confidential、未发表、
                   embargo、内部资料、不得外传）→ 仅本地处理、禁止外发
  length_conflict  task 要求字数上限低于源文关键信息所需下限的启发式估计

处置规则：
  halt     全部被引用的文本输入均缺失/为空（无可加工材料）
  mark-gap 缺失个别输入、数值冲突、篇幅冲突 → 记入 limitations 继续
  proceed  涉密标记：允许本地继续处理，但限制写入 note 与 limitations

退出码：
  0  扫描完成，无 halt 项
  2  存在 halt 项（应停止管线，仅交付 partial）
  1  运行错误（参数 / IO / JSON 非法）
"""
import argparse
import json
import os
import re
import sys

TEXT_EXTS = (".md", ".txt", ".csv", ".json", ".cif", ".dat")
PATH_RE = re.compile(
    r"[\w\-./\\]+\.(?:md|markdown|csv|txt|json|pdf|docx?|xlsx?|cif|dat|png|jpe?g)",
    re.IGNORECASE)
NUM_RE = re.compile(r"[-+]?\d+(?:\.\d+)?")
ANCHOR_RE = re.compile(r"[一-鿿A-Za-z][一-鿿A-Za-z]*")
CONF_KEYWORDS = ["保密", "机密", "confidential", "未发表",
                 "embargo", "内部资料", "不得外传"]
UPPER_RES = [
    re.compile(r"(?:不超过|不得超过|控制在|上限为|限于|≤|<=)\s*(\d{2,6})\s*(?:字|字符)"),
    re.compile(r"(\d{2,6})\s*字(?:以内|之内|上限|为限)"),
]
CHARS_PER_KEYPOINT = 25  # 启发式：每个关键信息点约需 25 字转述
KIND_ORDER = {"missing_input": 0, "conflict": 1,
              "confidentiality": 2, "length_conflict": 3}


def read_text(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def walk_strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from walk_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk_strings(v)


def collect_scan_files(indir, extra):
    files = []
    if indir and os.path.isdir(indir):
        for dirpath, _dirs, names in os.walk(indir):
            for n in sorted(names):
                if n.lower().endswith(TEXT_EXTS):
                    files.append(os.path.join(dirpath, n))
    for p in extra:
        if p and os.path.isfile(p) and os.path.abspath(p) not in [
                os.path.abspath(x) for x in files]:
            files.append(p)
    return sorted(files)


def find_path_refs(case_path, task_path):
    """从 case.json 全部字符串与 task.md 文本中抽取疑似文件路径。"""
    refs = {}  # ref_string -> 来源描述
    base = os.path.dirname(os.path.abspath(case_path))
    try:
        case = json.loads(read_text(case_path))
        for s in walk_strings(case):
            for m in PATH_RE.finditer(s):
                refs.setdefault(m.group(0), "case.json")
    except json.JSONDecodeError:
        pass
    if task_path and os.path.isfile(task_path):
        for m in PATH_RE.finditer(read_text(task_path)):
            refs.setdefault(m.group(0), os.path.basename(task_path))
    resolved = []
    for ref, src in sorted(refs.items()):
        candidates = [os.path.join(base, ref), os.path.abspath(ref)]
        hit = next((c for c in candidates if os.path.exists(c)), None)
        resolved.append((ref, src, hit))
    return resolved


def check_missing(resolved):
    entries = []
    usable = 0
    for ref, src, hit in resolved:
        if hit is None:
            entries.append({
                "kind": "missing_input",
                "locator": f"{src} -> {ref}",
                "evidence": f"引用的路径 '{ref}' 在磁盘上不存在",
                "disposition": "mark-gap",
                "note": "相关内容留空并写入 limitations；待人工补充后重跑",
            })
        elif os.path.isfile(hit) and os.path.getsize(hit) == 0:
            entries.append({
                "kind": "missing_input",
                "locator": f"{src} -> {ref}",
                "evidence": f"文件 '{ref}' 存在但大小为 0 字节",
                "disposition": "mark-gap",
                "note": "视为缺失输入，记入 limitations",
            })
        elif hit.lower().endswith(TEXT_EXTS):
            usable += 1
    if resolved and usable == 0:
        for e in entries:
            if e["kind"] == "missing_input":
                e["disposition"] = "halt"
                e["note"] = "全部文本输入缺失/为空，无可加工材料，必须停止管线"
    return entries


def check_conflicts(scan_files):
    """同一锚点（数字前 ±10 字符窗口内的中文/英文词）跨文件出现不同数值。"""
    anchor_map = {}  # anchor -> {value: (file, line_no, context)}
    for path in scan_files:
        try:
            lines = read_text(path).splitlines()
        except OSError:
            continue
        for ln, line in enumerate(lines, 1):
            for m in NUM_RE.finditer(line):
                val = m.group(0)
                if val.isdigit() and 1900 <= int(val) <= 2100:
                    continue  # 年份降噪
                win = line[max(0, m.start() - 10):m.start()]
                words = [w for w in ANCHOR_RE.findall(win) if len(w) >= 2]
                if not words:
                    continue
                anchor = words[-1]  # 窗口内最后一个长度≥2 的中文/英文词
                slot = anchor_map.setdefault(anchor, {})
                slot.setdefault(val, (path, ln, line.strip()[:80]))
    # 锚点归并：最长公共子串 ≥4 字视为同一指标语境（容忍前缀/系词差异，
    # 保守归并，误报可接受，一律列入人工确认）
    anchors = sorted(anchor_map)
    parent = {x: x for x in anchors}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def longest_common_substr(x, y):
        best = 0
        for i in range(len(x)):
            for j in range(len(y)):
                n = 0
                while i + n < len(x) and j + n < len(y) and x[i + n] == y[j + n]:
                    n += 1
                if n > best:
                    best = n
        return best

    for i in range(len(anchors)):
        for j in range(i + 1, len(anchors)):
            if longest_common_substr(anchors[i], anchors[j]) >= 4:
                parent[find(anchors[j])] = find(anchors[i])
    groups = {}
    for x in anchors:
        groups.setdefault(find(x), []).append(x)

    def lcs_str(x, y):
        best = ""
        for i in range(len(x)):
            for j in range(len(y)):
                n = 0
                while i + n < len(x) and j + n < len(y) and x[i + n] == y[j + n]:
                    n += 1
                if n > len(best):
                    best = x[i:i + n]
        return best

    entries = []
    for members in sorted(groups.values(), key=lambda ms: ms[0]):
        vals = {}
        files = set()
        label = members[0]
        for x in members[1:]:
            label = lcs_str(label, x) or min(members, key=len)
        for x in members:
            for v, (f, ln, c) in anchor_map[x].items():
                vals.setdefault(v, (f, ln, c))
                files.add(os.path.basename(f))
        if len(vals) < 2 or len(files) < 2:
            continue  # 须跨文件且取值不同才上报
        ev = "; ".join(
            f"{os.path.basename(f)}:{ln} 取值 {v}" for v, (f, ln, _c) in sorted(vals.items()))
        entries.append({
            "kind": "conflict",
            "locator": f"锚点「{label}」跨文件: {', '.join(sorted(files))}",
            "evidence": ev,
            "disposition": "mark-gap",
            "note": "数值冲突，保守上报；须人工确认唯一口径后方可写入交付物",
        })
    return entries


def check_confidentiality(scan_files):
    entries = []
    for path in scan_files:
        try:
            lines = read_text(path).splitlines()
        except OSError:
            continue
        seen = set()
        for ln, line in enumerate(lines, 1):
            low = line.lower()
            for kw in CONF_KEYWORDS:
                if kw in seen:
                    continue
                if (kw.lower() in low) if kw.isascii() else (kw in line):
                    seen.add(kw)
                    entries.append({
                        "kind": "confidentiality",
                        "locator": f"{os.path.basename(path)}:{ln}",
                        "evidence": f"命中标记「{kw}」: {line.strip()[:80]}",
                        "disposition": "proceed",
                        "note": "仅本地处理、禁止外发；限制须写入 result.json 的 limitations",
                    })
    return entries


def estimate_keypoints(text):
    nums = [m for m in NUM_RE.findall(text)
            if not (m.isdigit() and 1900 <= int(m) <= 2100)]
    heads = re.findall(r"(?m)^#{1,6}\s", text)
    items = re.findall(r"(?m)^\s*(?:[-*]|\d+[.、])\s", text)
    return len(nums) + len(heads) + len(items)


def check_length(task_path, scan_files):
    if not task_path or not os.path.isfile(task_path):
        return []
    task = read_text(task_path)
    upper = None
    for rx in UPPER_RES:
        m = rx.search(task)
        if m:
            upper = int(m.group(1))
            break
    if upper is None:
        return []
    mds = [p for p in scan_files if p.lower().endswith(".md")
           and os.path.abspath(p) != os.path.abspath(task_path)]
    if not mds:
        return []
    src = max(mds, key=lambda p: os.path.getsize(p))
    kp = estimate_keypoints(read_text(src))
    required_min = kp * CHARS_PER_KEYPOINT
    if upper >= required_min:
        return []
    return [{
        "kind": "length_conflict",
        "locator": f"{os.path.basename(task_path)} vs {os.path.basename(src)}",
        "evidence": (f"task 字数上限 {upper} 字 < 源文 {kp} 个关键信息点"
                     f"×{CHARS_PER_KEYPOINT} 字 ≈ {required_min} 字下限"),
        "disposition": "mark-gap",
        "note": "篇幅约束冲突：须删减覆盖范围并在 limitations 声明，或与需求方确认",
    }]


def write_md(entries, counts, halt, path):
    lines = ["# 异常登记表 anomaly_register", "",
             f"- 条目总数: {len(entries)}",
             f"- 存在 halt 项: {'是' if halt else '否'}",
             "- 分类统计: " + (", ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "无"),
             "",
             "| kind | locator | evidence | disposition | note |",
             "| --- | --- | --- | --- | --- |"]
    for e in entries:
        row = [e["kind"], e["locator"], e["evidence"], e["disposition"], e["note"]]
        lines.append("| " + " | ".join(
            str(c).replace("|", "\\|").replace("\n", " ") for c in row) + " |")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main():
    p = argparse.ArgumentParser(description="输入异常分流器")
    p.add_argument("--case", required=True, help="case.json 路径")
    p.add_argument("--task", default=None, help="task.md 路径（可选）")
    p.add_argument("--indir", default=None, help="输入目录（递归扫描文本文件）")
    p.add_argument("--outdir", required=True, help="anomaly_register 输出目录")
    a = p.parse_args()
    if not os.path.isfile(a.case):
        print(f"[triage] case.json 不存在: {a.case}", file=sys.stderr)
        return 1
    os.makedirs(a.outdir, exist_ok=True)
    extra = [x for x in (a.task,) if x]
    scan_files = collect_scan_files(a.indir, extra)
    resolved = find_path_refs(a.case, a.task)

    entries = []
    entries += check_missing(resolved)
    entries += check_conflicts(scan_files)
    entries += check_confidentiality(scan_files)
    entries += check_length(a.task, scan_files)
    entries.sort(key=lambda e: (KIND_ORDER.get(e["kind"], 9), e["locator"]))

    counts = {}
    for e in entries:
        counts[e["kind"]] = counts.get(e["kind"], 0) + 1
    halt = any(e["disposition"] == "halt" for e in entries)
    register = {
        "generated_by": "anomaly_triage.py",
        "case": os.path.abspath(a.case),
        "scanned_files": [os.path.abspath(x) for x in scan_files],
        "counts": counts,
        "halt": halt,
        "entries": entries,
    }
    jpath = os.path.join(a.outdir, "anomaly_register.json")
    mpath = os.path.join(a.outdir, "anomaly_register.md")
    with open(jpath, "w", encoding="utf-8") as f:
        json.dump(register, f, ensure_ascii=False, indent=2)
        f.write("\n")
    write_md(entries, counts, halt, mpath)
    print(f"[triage] 共 {len(entries)} 条异常 "
          f"({', '.join(f'{k}={v}' for k, v in sorted(counts.items())) or '无'})，"
          f"halt={'是' if halt else '否'}")
    print(f"[triage] 已写出: {jpath} / {mpath}")
    return 2 if halt else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except OSError as e:
        print(f"[triage] IO 错误: {e}", file=sys.stderr)
        sys.exit(1)

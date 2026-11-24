#!/usr/bin/env python3
"""compile_workorder.py — 把 organizer-edit-workorder.json 编译为确定性操作 DSL（ops.json）。

分工：本脚本做"机械可判定"的部分——识别操作类型、解析目标章节、扫描图表引用、
生成可直接落改的 op。识别不出的 item 原样保留为 type="manual"（含 reason），交给模型。

仅使用 python3 标准库；所有路径均由命令行参数传入。
"""
import argparse
import json
import re
import sys
from pathlib import Path

# ---------- 规则常量 ----------

QUOTE_RE = re.compile(r'[“"\'「『]([^”"\'」』]+)[”"\'」』]')
CN_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
          "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}

# 题注行：行首（可带 ** 加粗或空白）出现 图x-y / 表x-y
CAPTION_RE = re.compile(r'^\s*(?:\*\*)?\s*(图|表)\s*(\d+)\s*[-–—]\s*(\d+)')
# 正文中的图表引用（任意位置）
REF_RE = re.compile(r'(图|表)\s*(\d+)\s*[-–—]\s*(\d+)')
HEADING_RE = re.compile(r'^#{1,6}\s+(.+?)\s*$')

ALL_TARGET_WORDS = ("全部章节", "全文", "所有章节", "全部", "所有", "all", "ALL")


def extract_quoted(text):
    """按出现顺序提取引号包裹的串（中文/英文引号）。"""
    return [m.strip() for m in QUOTE_RE.findall(text or "")]


def list_chapters(chapters_dir):
    d = Path(chapters_dir)
    if not d.is_dir():
        sys.exit(f"[compile] 章节目录不存在: {d}")
    files = sorted(p.name for p in d.glob("*.md") if p.is_file())
    if not files:
        sys.exit(f"[compile] 章节目录为空（无 .md）: {d}")
    return files


def first_heading(path):
    try:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            m = HEADING_RE.match(line)
            if m:
                return m.group(1)
    except OSError:
        pass
    return ""


def resolve_target(target, chapters_dir, files):
    """把 item.target 解析为章节文件名列表。返回 (files, warning|None)。"""
    t = (target or "").strip()
    if not t or t in ALL_TARGET_WORDS:
        return list(files), None
    hits = []
    # 1) 显式文件名 / 文件 stem
    for f in files:
        if f == t or Path(f).stem == t:
            hits.append(f)
    # 2) “第X章”
    m = re.search(r'第\s*([0-9一二三四五六七八九十]+)\s*章', t)
    if m:
        raw = m.group(1)
        n = int(raw) if raw.isdigit() else CN_NUM.get(raw)
        if n:
            for f in files:
                if re.search(rf'ch0*{n}(?!\d)', Path(f).stem, re.I):
                    hits.append(f)
                head = first_heading(Path(chapters_dir) / f)
                if (f"第{raw}章" in head) or (f"第{n}章" in head):
                    hits.append(f)
    # 3) 章节标题包含 target 文本
    if not hits:
        for f in files:
            if t and t in first_heading(Path(chapters_dir) / f):
                hits.append(f)
    # 去重保序
    seen, out = set(), []
    for f in hits:
        if f not in seen:
            seen.add(f)
            out.append(f)
    if out:
        return out, None
    return list(files), f"target “{t}” 未匹配到具体章节，已回退为全部章节"


# ---------- 图表引用扫描（float_ref_fix 的确定性核心） ----------

def scan_floats(chapters_dir, files):
    """返回 (captions, body_refs)。
    captions: {(kind, "a-b"): file}
    body_refs: [{file, kind, num, line}]（题注行之外的引用）
    """
    captions, body_refs = {}, []
    for f in files:
        text = (Path(chapters_dir) / f).read_text(encoding="utf-8")
        for ln, line in enumerate(text.splitlines(), 1):
            cap = CAPTION_RE.match(line)
            if cap:
                captions[(cap.group(1), f"{cap.group(2)}-{cap.group(3)}")] = f
                continue
            for m in REF_RE.finditer(line):
                body_refs.append({"file": f, "kind": m.group(1),
                                  "num": f"{m.group(2)}-{m.group(3)}", "line": ln})
    return captions, body_refs


def compile_float_ref_fix(item, chapters_dir, target_files):
    """对每个悬空引用生成确定性修复映射；无法唯一判定的记入 unresolved。"""
    captions, body_refs = scan_floats(chapters_dir, target_files)
    fixes, unresolved = [], []
    seen = set()
    for r in body_refs:
        key = (r["file"], r["kind"], r["num"])
        if (r["kind"], r["num"]) in captions or key in seen:
            continue
        seen.add(key)
        same_kind = sorted({num for (k, num) in captions if k == r["kind"]})
        same_prefix = sorted({num for num in same_kind
                              if num.split("-")[0] == r["num"].split("-")[0]})
        if len(same_prefix) == 1:
            new = same_prefix[0]
            rule = "同章同类型题注唯一"
        elif len(same_kind) == 1:
            new = same_kind[0]
            rule = "全文同类型题注唯一"
        else:
            unresolved.append({**r, "reason": "候选题注不唯一，需模型判断"})
            continue
        fixes.append({"file": r["file"], "kind": r["kind"],
                      "old_num": r["num"], "new_num": new, "rule": rule})
    params = {"fixes": fixes, "unresolved": unresolved,
              "captions": sorted([f"{k}{n}" for (k, n) in captions])}
    return params


# ---------- item 类型识别 ----------

def classify_item(item, chapters_dir, files):
    """返回 (op_type, params, reason|None)。"""
    action = item.get("action", "") or ""
    target_files, warn = resolve_target(item.get("target", ""), chapters_dir, files)
    quoted = extract_quoted(action)

    # 1) term_unify：“将X统一为Y”
    if "统一为" in action and len(quoted) >= 2:
        params = {"from": quoted[0], "to": quoted[1],
                  "protect_patterns": [], "protect_sections": [],
                  "sync_abbrev": False}
        # “参考文献/引用标题除外” → 保护参考文献节与文献条目行
        if ("参考文献" in action) or ("引用标题" in action) or ("文献" in action):
            params["protect_sections"].append("参考文献")
            params["protect_patterns"].append(r"^\s*\[\d+\]")
        if "缩写" in action:
            params["sync_abbrev"] = True
        return "term_unify", params, warn

    # 2) float_ref_fix：图/表 + 引用/编号/题注/纠错/修正
    if (("图" in action) or ("表" in action)) and any(
            w in action for w in ("引用", "编号", "题注", "纠错", "修正", "修复", "指向")):
        return "float_ref_fix", compile_float_ref_fix(item, chapters_dir, target_files), warn

    # 3) replace：明确给出旧文/新文（“改为”“替换为”）
    if (("改为" in action) or ("替换为" in action)) and len(quoted) >= 2:
        return "replace", {"old": quoted[0], "new": quoted[1], "count": "all"}, warn

    # 4) delete：删除 + 一个引号串
    if "删除" in action and len(quoted) >= 1:
        return "delete", {"text": quoted[0]}, warn

    # 5) format_normalize：已知规则表
    if any(w in action for w in ("格式", "规范", "空格", "归一")):
        if ("单位" in action) and ("空格" in action):
            return "format_normalize", {"rule": "number_unit_space"}, warn
        return "manual", {}, f"format_normalize 规则未命中已知规则表: {action}"

    return "manual", {}, f"未匹配任何确定性规则: {action}"


def main():
    ap = argparse.ArgumentParser(description="编译 organizer-edit-workorder 为 ops.json")
    ap.add_argument("--workorder", required=True)
    ap.add_argument("--case", required=True)
    ap.add_argument("--chapters", required=True, help="章节 .md 所在目录")
    ap.add_argument("--out", required=True, help="ops.json 输出路径")
    ap.add_argument("--note", default="", help="可选：写入 ops.json 的标注（如合成示例）")
    args = ap.parse_args()

    case = json.loads(Path(args.case).read_text(encoding="utf-8"))
    workorder = json.loads(Path(args.workorder).read_text(encoding="utf-8"))
    items = workorder.get("items", [])
    files = list_chapters(args.chapters)

    ops, manual_count = [], 0
    for item in items:
        op_type, params, reason = classify_item(item, args.chapters, files)
        target_files, _ = resolve_target(item.get("target", ""), args.chapters, files)
        op = {"op_id": f"op-{len(ops) + 1:03d}",
              "item_id": item.get("id"),
              "item_title": item.get("title", ""),
              "type": op_type,
              "target_files": target_files,
              "params": params}
        if op_type == "manual":
            op["action"] = item.get("action", "")
            op["reason"] = reason or "未识别"
            manual_count += 1
        elif reason:  # 编译警告（如 target 回退）
            op["warning"] = reason
        ops.append(op)

    doc = {"schema": "surgical-edit-ops/v1",
           "case_id": case.get("case_id", "UNKNOWN"),
           "source_workorder": Path(args.workorder).name,
           "chapter_files": files,
           "ops": ops,
           "summary": {"total": len(ops), "manual": manual_count,
                       "deterministic": len(ops) - manual_count}}
    if args.note:
        doc["note"] = args.note

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[compile] {len(ops)} ops -> {out} "
          f"(deterministic={len(ops) - manual_count}, manual={manual_count})")
    for op in ops:
        print(f"  {op['op_id']}  {op['type']:<16} item={op['item_id']}  "
              f"targets={','.join(op['target_files'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

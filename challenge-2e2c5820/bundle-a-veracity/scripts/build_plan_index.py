#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_plan_index.py <case.json> <out_dir>

递归遍历 case.json，定位候选方案文本（键名含 plan/version/方案/candidate 的
列表或字典；找不到时回退为整份 case 视为一份文档），输出：
  <out_dir>/plans.json           {"plans":[{"plan_id","title","text","source_path"}]}
  <out_dir>/plans.lineindex.json 每个 plan 的行偏移索引
  <out_dir>/materials.json       组织方合同/清单/参数域等素材（含 JSON 路径记录）

绝不臆造内容；找不到任何方案文本时以退出码 3 报错。
仅使用标准库，无网络。
"""
import json
import os
import re
import sys

PLAN_KEY_HINTS = ("plan", "version", "方案", "candidate", "草稿", "版本")
MATERIAL_KEY_HINTS = ("contract", "合同", "inventory", "清单", "parameter", "参数",
                      "budget", "预算", "resource", "booking", "预约", "price", "价格",
                      "domain", "域", "constraint", "约束")
TITLE_KEYS = ("title", "name", "标题", "名称", "label")
TEXT_KEYS = ("text", "content", "body", "正文", "内容", "full_text", "markdown", "md")


def usage(msg):
    sys.stderr.write("用法: build_plan_index.py <case.json> <out_dir>\n错误: %s\n" % msg)
    sys.exit(1)


def is_planish_key(key):
    k = str(key).lower()
    return any(h in k for h in PLAN_KEY_HINTS)


def is_material_key(key):
    k = str(key).lower()
    if "output_contract" in k or "deliverable" in k or "输出契约" in k:
        return False  # 输出契约不是素材
    return any(h.lower() in k for h in MATERIAL_KEY_HINTS)


def pick_title(node):
    if isinstance(node, dict):
        for k in TITLE_KEYS:
            for nk, nv in node.items():
                if k in str(nk).lower() and isinstance(nv, str):
                    return nv.strip()
    return None


def extract_text(node):
    """Return a single plan text string from a node, or None."""
    if isinstance(node, str) and len(node.strip()) >= 40:
        return node.strip()
    if isinstance(node, dict):
        for k in TEXT_KEYS:
            for nk, nv in node.items():
                if k in str(nk).lower() and isinstance(nv, str) and len(nv.strip()) >= 40:
                    return nv.strip()
        # concatenate all long string fields as fallback text
        parts = []
        for nk, nv in node.items():
            if isinstance(nv, str) and len(nv.strip()) >= 20:
                parts.append("## %s\n%s" % (nk, nv.strip()))
        if parts:
            joined = "\n\n".join(parts)
            if len(joined) >= 40:
                return joined
    return None


def walk(node, path, plans, materials, seen_ids):
    """DFS walk. plans/materials are output lists."""
    if isinstance(node, dict):
        # material container?
        if is_material_key(path.split(".")[-1] if path else "") and not is_planish_key(path):
            materials.append({"source_path": path or "$", "content": node})
            return
        for k, v in node.items():
            child = "%s.%s" % (path, k) if path else str(k)
            if is_planish_key(k):
                if isinstance(v, list):
                    for i, item in enumerate(v):
                        text = extract_text(item)
                        if text:
                            pid = None
                            if isinstance(item, dict):
                                pid = item.get("plan_id") or item.get("id") or item.get("version_id")
                            pid = str(pid) if pid else "plan-%d" % (len(plans) + 1)
                            title = pick_title(item) or ("候选方案 %s" % pid)
                            plans.append({"plan_id": pid, "title": title,
                                          "text": text, "source_path": "%s[%d]" % (child, i)})
                        else:
                            walk(item, "%s[%d]" % (child, i), plans, materials, seen_ids)
                elif isinstance(v, dict):
                    # a dict whose values may be versions v1/v2...
                    sub_plans = []
                    for sk, sv in v.items():
                        text = extract_text(sv)
                        if text:
                            pid = "%s" % sk
                            title = pick_title(sv) or ("候选方案 %s" % sk)
                            sub_plans.append({"plan_id": pid, "title": title,
                                              "text": text, "source_path": "%s.%s" % (child, sk)})
                    if sub_plans:
                        plans.extend(sub_plans)
                    else:
                        text = extract_text(v)
                        if text:
                            pid = "plan-%d" % (len(plans) + 1)
                            plans.append({"plan_id": pid, "title": pick_title(v) or pid,
                                          "text": text, "source_path": child})
                        else:
                            walk(v, child, plans, materials, seen_ids)
                elif isinstance(v, str) and len(v.strip()) >= 40:
                    pid = "plan-%d" % (len(plans) + 1)
                    plans.append({"plan_id": pid, "title": pid, "text": v.strip(),
                                  "source_path": child})
            elif is_material_key(k):
                materials.append({"source_path": child, "content": v})
            else:
                walk(v, child, plans, materials, seen_ids)
    elif isinstance(node, list):
        for i, item in enumerate(node):
            walk(item, "%s[%d]" % (path, i), plans, materials, seen_ids)


def build_line_index(plan):
    lines = plan["text"].split("\n")
    offsets = []
    pos = 0
    for i, line in enumerate(lines, start=1):
        offsets.append({"line": i, "start": pos, "end": pos + len(line)})
        pos += len(line) + 1
    return {"plan_id": plan["plan_id"], "n_lines": len(lines),
            "n_chars": len(plan["text"]), "lines": offsets}


def main():
    if len(sys.argv) != 3:
        usage("需要两个参数：case.json 路径与输出目录")
    case_path, out_dir = sys.argv[1], sys.argv[2]
    if not os.path.isfile(case_path):
        sys.stderr.write("错误: 找不到 case 文件: %s\n" % case_path)
        sys.exit(1)
    try:
        with open(case_path, "r", encoding="utf-8") as f:
            case = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        sys.stderr.write("错误: case.json 解析失败: %s\n" % e)
        sys.exit(1)

    os.makedirs(out_dir, exist_ok=True)
    plans, materials = [], []
    walk(case, "", plans, materials, set())

    if not plans:
        # fallback: whole case as one document (serialized)
        text = json.dumps(case, ensure_ascii=False, indent=2)
        if len(text) >= 40:
            plans.append({"plan_id": "plan-1", "title": "整份 case 文档（回退索引）",
                          "text": text, "source_path": "$"})

    if not plans:
        sys.stderr.write("错误(退出码3): 未能在 case.json 中定位任何候选方案文本；"
                         "请人工检查数据结构后手工构造 plans.json。\n")
        sys.exit(3)

    with open(os.path.join(out_dir, "plans.json"), "w", encoding="utf-8") as f:
        json.dump({"plans": plans}, f, ensure_ascii=False, indent=2)
    with open(os.path.join(out_dir, "plans.lineindex.json"), "w", encoding="utf-8") as f:
        json.dump({"lineindex": [build_line_index(p) for p in plans]},
                  f, ensure_ascii=False, indent=2)
    with open(os.path.join(out_dir, "materials.json"), "w", encoding="utf-8") as f:
        json.dump({"materials": materials}, f, ensure_ascii=False, indent=2)

    sys.stdout.write("OK: %d 份方案, %d 份素材 -> %s\n"
                     % (len(plans), len(materials), out_dir))
    for p in plans:
        sys.stdout.write("  - %s (%s, %d 字符) @ %s\n"
                         % (p["plan_id"], p["title"], len(p["text"]), p["source_path"]))
    sys.exit(0)


if __name__ == "__main__":
    main()

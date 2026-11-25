#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""apply_overrides.py — 人工复核 override 受理器（纯 Python3 标准库，离线）。

读取 overrides.jsonl，每行一个 JSON 对象：
  {
    "target_path": "items.2.conclusion",   # 点路径（列表段可用数字下标）
    "new_value": ...,                       # 任意 JSON 值
    "reviewer": "张 review",
    "rationale": "为何修改（必填，沉淀依据）",
    "date": "2026-11-25",
    "old_value_expected": ...               # 可选：乐观锁，防误改
  }

语义：
  * 按行序应用；目标路径必须已存在——只为 change_records 追加允许创建中间对象，
    拒绝创建任何其它新分支（防止把拼写错误静默变成新字段）；
  * 携带 old_value_expected 且与现值不符 → 拒绝并记录原因；
  * 每一行（应用/拒绝）都写入 <workdir>/changelog.jsonl；
  * 应用的 override 追加到 result["change_records"]（含 before/after）；
  * 全部处理完后写 <workdir>/sedimentation_report.md：按目标字段前缀聚类，
    统计次数，把“同一字段反复被人工改”翻译成流程/规模改进建议，而非沉默补丁。

退出码恒为 0（被拒绝的行绝不中断运行）；输入文件本身不可读时退出 1。
"""
import argparse
import datetime
import json
import os
import sys
from collections import Counter, defaultdict

REQUIRED_ROW_KEYS = ("target_path", "new_value", "reviewer", "rationale", "date")


def parse_path(target_path):
    """把点路径拆成段；非法路径返回 None。"""
    if not isinstance(target_path, str) or not target_path.strip():
        return None
    segs = target_path.split(".")
    if any(s == "" for s in segs):
        return None
    return segs


def resolve(root, segs, allow_create=False):
    """解析路径。返回 (parent, key, exists, reason)。

    allow_create=False 时，任何缺失的中间层/末层都拒绝（不创建新分支）。
    """
    node = root
    for i, seg in enumerate(segs[:-1]):
        if isinstance(node, dict):
            if seg not in node:
                if allow_create:
                    node[seg] = {}
                else:
                    return None, None, False, "路径中间层 %r 不存在，拒绝创建新分支" % seg
            node = node[seg]
        elif isinstance(node, list):
            if not seg.isdigit() or int(seg) >= len(node):
                return None, None, False, "列表下标 %r 越界或非法" % seg
            node = node[int(seg)]
        else:
            return None, None, False, "路径中间层 %r 不是容器，无法继续下钻" % seg
    last = segs[-1]
    if isinstance(node, dict):
        if last not in node and not allow_create:
            return node, last, False, "目标字段 %r 不存在，拒绝创建新字段" % last
        return node, last, last in node, None
    if isinstance(node, list):
        if not last.isdigit() or int(last) >= len(node):
            return node, last, False, "列表下标 %r 越界或非法" % last
        return node, int(last), True, None
    return None, None, False, "路径终点父节点不是容器"


def get_value(parent, key):
    return parent[key]


def set_value(parent, key, value):
    parent[key] = value


def values_equal(a, b):
    return json.dumps(a, sort_keys=True, ensure_ascii=False) == \
        json.dumps(b, sort_keys=True, ensure_ascii=False)


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def field_prefix(target_path):
    """聚类前缀：取点路径首段（去掉下标的字段族）。"""
    segs = parse_path(target_path) or [str(target_path)]
    return segs[0]


SUGGESTIONS = {
    "evidence": "evidence 字段被反复人工修正：建议在上游评估阶段固化证据抽取模板"
                "（source/locator 必填校验前置），并扩大证据覆盖采样规模。",
    "uncertainties": "uncertainties 被反复改写：建议把常见不确定性类型枚举化，"
                     "在生成阶段强制逐条归类，减少人工补写。",
    "items": "items 条目结论被反复人工纠正：建议对该类条目增加二次独立评估"
             "（双跑取一致）或提高该字段的模型请求预算。",
    "summary": "summary 被反复人工润色：建议把高频人工措辞固化为生成模板/写作规范，"
               "并在提示词中显式声明口径。",
    "status": "status 判定被反复推翻：建议把 success/partial/failed 的判定规则写成"
              "可执行的检查清单，由 contract_check 先行把关。",
}


def suggest_for(prefix, count):
    base = SUGGESTIONS.get(
        prefix,
        "字段族 %r 被人工修改 %d 次：建议回看这些 override 的 rationale 共性，"
        "把修正规则沉淀进上游生成/评估流程或扩大该字段的覆盖规模。"
        % (prefix, count))
    return base


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="人工复核 override 受理器（离线，纯标准库）")
    ap.add_argument("--result", required=True, help="result.json 路径")
    ap.add_argument("--overrides", required=True, help="overrides.jsonl 路径")
    ap.add_argument("--workdir", required=True,
                    help="工作目录（写 changelog.jsonl 与 sedimentation_report.md）")
    ap.add_argument("--out", default=None,
                    help="输出路径；缺省就地覆盖 --result")
    args = ap.parse_args(argv)

    out_path = args.out or args.result
    try:
        result = load_json(args.result)
    except (OSError, json.JSONDecodeError) as e:
        print("[ERROR] 无法读取 result.json: %s (%s)" % (args.result, e))
        return 1
    if not isinstance(result, dict):
        print("[ERROR] result.json 顶层必须是 JSON 对象")
        return 1

    os.makedirs(args.workdir, exist_ok=True)
    changelog_path = os.path.join(args.workdir, "changelog.jsonl")
    now = datetime.datetime.now().isoformat(timespec="seconds")

    applied, rejected = [], []
    try:
        ovf = open(args.overrides, "r", encoding="utf-8")
    except OSError as e:
        print("[ERROR] 无法读取 overrides 文件: %s (%s)" % (args.overrides, e))
        return 1

    with ovf, open(changelog_path, "a", encoding="utf-8") as log:
        for lineno, line in enumerate(ovf, 1):
            line = line.strip()
            if not line:
                continue
            entry = {"lineno": lineno, "processed_at": now}

            # 1) 行本身是合法 JSON？
            try:
                row = json.loads(line)
            except json.JSONDecodeError as e:
                entry.update(decision="rejected",
                             reason="第 %d 行不是合法 JSON: %s" % (lineno, e))
                log.write(json.dumps(entry, ensure_ascii=False) + "\n")
                rejected.append(entry)
                continue
            if not isinstance(row, dict):
                entry.update(decision="rejected", reason="行内容不是 JSON 对象")
                log.write(json.dumps(entry, ensure_ascii=False) + "\n")
                rejected.append(entry)
                continue
            entry["target_path"] = row.get("target_path")

            # 2) 必填键齐全？
            missing = [k for k in REQUIRED_ROW_KEYS if k not in row]
            if missing:
                entry.update(decision="rejected",
                             reason="override 缺少必填键: %s" % ", ".join(missing))
                log.write(json.dumps(entry, ensure_ascii=False) + "\n")
                rejected.append(entry)
                continue

            # 3) 解析路径（change_records 追加允许创建中间层）
            segs = parse_path(row["target_path"])
            if segs is None:
                entry.update(decision="rejected",
                             reason="target_path 非法: %r" % row["target_path"])
                log.write(json.dumps(entry, ensure_ascii=False) + "\n")
                rejected.append(entry)
                continue
            allow_create = (segs[0] == "change_records")
            parent, key, exists, reason = resolve(
                result, segs, allow_create=allow_create)
            if reason:
                entry.update(decision="rejected", reason=reason)
                log.write(json.dumps(entry, ensure_ascii=False) + "\n")
                rejected.append(entry)
                continue

            old_value = get_value(parent, key) if exists else None

            # 4) 乐观锁：old_value_expected 校验
            if "old_value_expected" in row:
                if not exists:
                    entry.update(decision="rejected",
                                 reason="声明了 old_value_expected 但目标当前不存在")
                    log.write(json.dumps(entry, ensure_ascii=False) + "\n")
                    rejected.append(entry)
                    continue
                if not values_equal(old_value, row["old_value_expected"]):
                    entry.update(
                        decision="rejected",
                        reason="old_value_expected 与现值不符: 期望 %r，实际 %r"
                               % (row["old_value_expected"], old_value))
                    log.write(json.dumps(entry, ensure_ascii=False) + "\n")
                    rejected.append(entry)
                    continue

            # 5) 应用
            set_value(parent, key, row["new_value"])
            record = {
                "target_path": row["target_path"],
                "old_value": old_value if exists else None,
                "new_value": row["new_value"],
                "reviewer": row["reviewer"],
                "rationale": row["rationale"],
                "date": row["date"],
                "applied_at": now,
                "kind": "human_override",
            }
            result.setdefault("change_records", [])
            if not isinstance(result["change_records"], list):
                result["change_records"] = [result["change_records"]]
            result["change_records"].append(record)
            entry.update(decision="applied",
                         old_value=record["old_value"],
                         new_value=record["new_value"])
            log.write(json.dumps(entry, ensure_ascii=False) + "\n")
            applied.append(entry)

    # ---- 写回 result.json ----
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
            f.write("\n")
    except OSError as e:
        print("[ERROR] 结果写回失败: %s (%s)" % (out_path, e))
        return 1

    # ---- 沉淀报告 ----
    clusters = defaultdict(list)
    for e in applied + rejected:
        tp = e.get("target_path") or "<unparseable>"
        clusters[field_prefix(tp)].append(e)
    counts = Counter({k: len(v) for k, v in clusters.items()})

    sed_path = os.path.join(args.workdir, "sedimentation_report.md")
    with open(sed_path, "w", encoding="utf-8") as f:
        f.write("# 人工复核沉淀报告（sedimentation report）\n\n")
        f.write("- 生成时间: %s\n" % now)
        f.write("- 受理 override 总数: %d（应用 %d / 拒绝 %d）\n\n"
                % (len(applied) + len(rejected), len(applied), len(rejected)))
        f.write("## 按目标字段族聚类\n\n")
        f.write("| 字段族前缀 | override 次数 | 应用 | 拒绝 | 流程/规模改进建议 |\n")
        f.write("|---|---|---|---|---|\n")
        for prefix, cnt in counts.most_common():
            rows = clusters[prefix]
            n_applied = sum(1 for r in rows if r["decision"] == "applied")
            n_rejected = cnt - n_applied
            f.write("| `%s` | %d | %d | %d | %s |\n"
                    % (prefix, cnt, n_applied, n_rejected,
                       suggest_for(prefix, cnt)))
        f.write("\n## 明细\n\n")
        for prefix, rows in sorted(clusters.items()):
            f.write("### `%s`\n\n" % prefix)
            for r in rows:
                f.write("- 第 %s 行 `%s` → **%s**：%s\n"
                        % (r.get("lineno", "?"), r.get("target_path", "?"),
                           r.get("decision", "?"),
                           r.get("reason") or "已写入 change_records"))
            f.write("\n")
        f.write("> 原则：同一字段族反复被人工修改时，优先把修正规则沉淀进流程"
                "（模板、校验、双跑、预算），而不是继续打一次性补丁。\n")

    print("[OK] overrides 处理完成: 应用 %d 行，拒绝 %d 行"
          % (len(applied), len(rejected)))
    for e in rejected:
        print("  [REJECTED] 第 %s 行 %s: %s"
              % (e.get("lineno"), e.get("target_path"), e.get("reason")))
    print("  changelog: %s" % changelog_path)
    print("  沉淀报告: %s" % sed_path)
    print("  结果写回: %s" % out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())

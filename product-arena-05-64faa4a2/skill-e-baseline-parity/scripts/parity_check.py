#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""parity_check.py — 同预算核验与统计协议缺口检查。

纯标准库、确定性、无网络。

功能：
  1) 从配置（.yaml/.yml/.json）与日志（.log/.txt）中提取各 run 的
     epochs / steps / 训练数据量 / 调参预算，按 run 分组后横向比较；
     任一预算维度在对照组间取值不一致即记为 parity 违规。
  2) 检查统计协议三要素——重复次数、均值±标准差、显著性检验——
     在材料（及可选草稿）中是否出现；缺失即列为缺口。

用法：
  python3 parity_check.py --input <目录或文件> [--input ...]
                          [--draft <章节草稿>] --out <输出目录>

输出：
  <out>/parity.json  结构化结果（runs / violations / protocol_gaps）
  <out>/parity.md    人读报告
退出码：恒为 0（核验结果写在产物里，由写作流程决定是否降级声明）。
"""
import argparse
import json
import os
import re
import sys

CONFIG_EXTS = {".yaml", ".yml", ".json"}
LOG_EXTS = {".log", ".txt", ".md"}

BUDGET_KEYS = {
    "epochs": re.compile(
        r"^\s*(?:max_)?epochs?\s*[:=]\s*(\d+)\s*$", re.IGNORECASE),
    "steps": re.compile(
        r"^\s*(?:max_|train_|training_)?steps?\s*[:=]\s*(\d+)\s*$", re.IGNORECASE),
    "data_size": re.compile(
        r"^\s*(?:train_)?(?:data(?:set)?_?(?:size|num|count)|num_?samples|"
        r"n_?samples)\s*[:=]\s*(\d+)\s*$", re.IGNORECASE),
    "tune_trials": re.compile(
        r"^\s*(?:n_?trials|num_?trials|tune_?(?:budget|trials)|"
        r"search_?trials|sweeps?)\s*[:=]\s*(\d+)\s*$", re.IGNORECASE),
}
RE_RUN_NAME = re.compile(
    r"^\s*(?:run_?name|name|model)\s*[:=]\s*[\"']?([A-Za-z0-9_\-]+)", re.IGNORECASE)
RE_LOG_RUN = re.compile(r"\brun\s*[=:]\s*([A-Za-z0-9_\-]+)")
RE_LOG_EPOCH = re.compile(r"\bepoch\s*[=: ]\s*(\d+)\s*/\s*(\d+)", re.IGNORECASE)
RE_LOG_KV = re.compile(
    r"\b(epochs?|steps?|train_data_size|data_size|n_trials)\s*[=:]\s*(\d+)",
    re.IGNORECASE)

PROTOCOL_CHECKS = {
    "repetition": {
        "label": "重复次数（多次独立运行/多种子）",
        "pattern": re.compile(
            r"重复\s*\d+\s*次|\d+\s*次重复|\d+\s*(?:个)?(?:随机)?种子|"
            r"\d+\s*(?:runs?|seeds?|repeats?|trials)\b|"
            r"runs?\s*=\s*\d+|seeds?\s*=\s*\d+", re.IGNORECASE),
    },
    "mean_std": {
        "label": "均值±标准差",
        "pattern": re.compile(
            r"±|\+/-|mean\s*(?:±|and|\+)|std|标准差|方差", re.IGNORECASE),
    },
    "significance": {
        "label": "显著性检验与置信水平",
        "pattern": re.compile(
            r"t-?test|wilcoxon|mann-?whitney|bootstrap|p\s*[<≤=]\s*0?\.\d+|"
            r"显著性检验|置信区间|置信水平|confidence interval|"
            r"significance test", re.IGNORECASE),
    },
}


def norm(name):
    return re.sub(r"[^a-z0-9]", "", name.lower())


def collect_files(inputs, exts):
    files = []
    for item in inputs:
        if os.path.isfile(item):
            if os.path.splitext(item)[1].lower() in exts:
                files.append(item)
        elif os.path.isdir(item):
            for root, dirs, names in os.walk(item):
                dirs.sort()
                for n in sorted(names):
                    if os.path.splitext(n)[1].lower() in exts:
                        files.append(os.path.join(root, n))
        else:
            print("警告：输入不存在，已跳过：%s" % item, file=sys.stderr)
    return sorted(dict.fromkeys(files))


def read_lines(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read().splitlines()
    except OSError as e:
        print("警告：无法读取 %s：%s" % (path, e), file=sys.stderr)
        return []


def parse_config(path, runs):
    """把 yaml/yml 简单键值与 json 顶层键值解析为一个 run 的预算字段。"""
    lines = read_lines(path)
    fields, evidence = {}, {}
    run_name = None
    ext = os.path.splitext(path)[1].lower()
    if ext == ".json":
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                obj = json.load(f)
        except (OSError, ValueError):
            obj = None
        if isinstance(obj, dict):
            for k, v in obj.items():
                kl = str(k).lower().replace("-", "_")
                if kl in ("run_name", "name", "model") and run_name is None:
                    run_name = str(v)
                fake = "%s: %s" % (kl, v)
                for field, pat in BUDGET_KEYS.items():
                    m = pat.match(fake)
                    if m and field not in fields:
                        fields[field] = int(m.group(1))
                        evidence[field] = "%s:json:%s" % (path, k)
    else:
        for i, text in enumerate(lines, 1):
            if run_name is None:
                m = RE_RUN_NAME.match(text)
                if m:
                    run_name = m.group(1)
            for field, pat in BUDGET_KEYS.items():
                m = pat.match(text)
                if m and field not in fields:
                    fields[field] = int(m.group(1))
                    evidence[field] = "%s:%d" % (path, i)
    if not fields and run_name is None:
        return
    name = run_name or os.path.splitext(os.path.basename(path))[0]
    key = norm(name)
    rec = runs.setdefault(key, {"run": name, "fields": {}, "evidence": {}})
    for field, val in fields.items():
        rec["fields"].setdefault(field, val)
        rec["evidence"].setdefault(field, evidence[field])


def parse_log(path, runs):
    for i, text in enumerate(read_lines(path), 1):
        m = RE_LOG_RUN.search(text)
        if not m:
            continue
        name = m.group(1)
        key = norm(name)
        rec = runs.setdefault(key, {"run": name, "fields": {}, "evidence": {}})
        em = RE_LOG_EPOCH.search(text)
        if em:
            total = int(em.group(2))
            if total >= rec["fields"].get("epochs", 0):
                rec["fields"]["epochs"] = total
                rec["evidence"]["epochs"] = "%s:%d" % (path, i)
        for km in RE_LOG_KV.finditer(text):
            k = km.group(1).lower()
            field = ("epochs" if k.startswith("epoch")
                     else "steps" if k.startswith("step")
                     else "tune_trials" if "trial" in k else "data_size")
            rec["fields"].setdefault(field, int(km.group(2)))
            rec["evidence"].setdefault(field, "%s:%d" % (path, i))


def compare_budgets(runs):
    violations = []
    fields_seen = sorted({f for r in runs.values() for f in r["fields"]})
    for field in fields_seen:
        values = {r["run"]: r["fields"].get(field) for r in
                  sorted(runs.values(), key=lambda x: x["run"])}
        present = {k: v for k, v in values.items() if v is not None}
        missing = [k for k, v in values.items() if v is None]
        if len(set(present.values())) > 1:
            violations.append({
                "field": field,
                "kind": "预算不一致",
                "values": present,
                "evidence": {k: runs[norm(k)]["evidence"].get(field)
                             for k in present},
                "action": "必须在对照实验小节中显式声明各组%s差异及理由，"
                          "否则不得下可比性结论" % field,
            })
        if missing and present:
            violations.append({
                "field": field,
                "kind": "预算未知",
                "values": present,
                "missing_runs": missing,
                "action": "以下 run 缺少%s记录：%s；需从材料补齐或在文中声明未知"
                          % (field, ", ".join(missing)),
            })
    return violations


def protocol_gaps(inputs, draft):
    texts = []
    for p in collect_files(inputs, LOG_EXTS | CONFIG_EXTS):
        texts.append((p, read_lines(p)))
    if draft:
        texts.append((draft, read_lines(draft)))
    gaps = []
    for key in sorted(PROTOCOL_CHECKS):
        chk = PROTOCOL_CHECKS[key]
        hit = None
        for path, lines in texts:
            for i, t in enumerate(lines, 1):
                if chk["pattern"].search(t):
                    hit = "%s:%d" % (path, i)
                    break
            if hit:
                break
        if hit is None:
            gaps.append({
                "element": key,
                "label": chk["label"],
                "status": "缺失",
                "action": "在统计协议中补充%s；无法补充时须声明缺口并降级相关论断"
                          % chk["label"],
            })
    return gaps


def main():
    ap = argparse.ArgumentParser(description="同预算与统计协议核验")
    ap.add_argument("--input", action="append", required=True)
    ap.add_argument("--draft", default=None, help="可选章节草稿路径")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    runs = {}
    for p in collect_files(args.input, CONFIG_EXTS):
        parse_config(p, runs)
    for p in collect_files(args.input, LOG_EXTS):
        parse_log(p, runs)

    violations = compare_budgets(runs)
    gaps = protocol_gaps(args.input, args.draft)

    result = {
        "tool": "parity_check",
        "inputs": args.input,
        "draft": args.draft,
        "runs": [runs[k] for k in sorted(runs)],
        "violation_count": len(violations),
        "violations": violations,
        "protocol_gap_count": len(gaps),
        "protocol_gaps": gaps,
    }
    os.makedirs(args.out, exist_ok=True)
    jpath = os.path.join(args.out, "parity.json")
    with open(jpath, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    mpath = os.path.join(args.out, "parity.md")
    with open(mpath, "w", encoding="utf-8") as f:
        f.write("# 同预算与统计协议核验（parity_check 自动产出）\n\n")
        f.write("## Run 预算汇总\n\n")
        f.write("| run | epochs | steps | data_size | tune_trials |\n")
        f.write("|---|---|---|---|---|\n")
        for r in result["runs"]:
            fd = r["fields"]
            f.write("| %s | %s | %s | %s | %s |\n" % (
                r["run"], fd.get("epochs", "未知"), fd.get("steps", "未知"),
                fd.get("data_size", "未知"), fd.get("tune_trials", "未知")))
        f.write("\n## Parity 违规清单（%d 项）\n\n" % len(violations))
        if violations:
            for v in violations:
                f.write("- **[%s] %s**：取值 %s。%s\n" % (
                    v["kind"], v["field"],
                    json.dumps(v["values"], ensure_ascii=False), v["action"]))
        else:
            f.write("- 未发现预算不一致。\n")
        f.write("\n## 统计协议缺口（%d 项）\n\n" % len(gaps))
        if gaps:
            for g in gaps:
                f.write("- **缺失：%s**。%s\n" % (g["label"], g["action"]))
        else:
            f.write("- 统计协议三要素均已找到。\n")

    print("parity_check：run=%d 个，预算违规=%d 项，协议缺口=%d 项 -> %s, %s"
          % (len(runs), len(violations), len(gaps), jpath, mpath))
    for v in violations:
        print("  ! [%s] %s: %s" % (v["kind"], v["field"],
                                   json.dumps(v["values"], ensure_ascii=False)))
    for g in gaps:
        print("  ! 缺口: %s" % g["label"])
    return 0


if __name__ == "__main__":
    sys.exit(main())

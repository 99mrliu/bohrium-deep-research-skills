#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
conflict_matrix.py — 多来源"键=值"型参数冲突抽取与裁决建议。

纯标准库、确定性、无网络。

用法：
    python3 conflict_matrix.py --materials <材料目录> --out-dir <输出目录>

输出：
    <输出目录>/conflicts.json / conflicts.md

抽取来源（仅数值型取值，见"边界"）：
    1. yaml/json 风格  key: value
    2. 日志风格        key=value
    3. 中文正文        “XX 为/是/取/等于/设置为 N”
    4. 英文正文        "xx is/equals/set to N"

冲突与观测的区分（避免把训练曲线误报为冲突）：
    - 同一文件内同一键出现多个不同取值 -> observation（视为时间序列/计数器，
      不参与冲突判定，仅记录）；
    - 同一键在 >=2 个文件各为单值且取值不一致 -> conflict。

裁决建议按 references/adjudication_rules.md 的来源优先级：
    运行日志(.log/.out) > 配置文件(.yaml/.yml/.json/.toml/.ini/.cfg)
    > 脚本默认(.py/.sh) > 草稿/转述(.md/.txt/.tex)。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict

TEXT_EXTS = {
    ".md", ".txt", ".log", ".out", ".yaml", ".yml", ".json",
    ".py", ".sh", ".toml", ".ini", ".cfg", ".csv", ".tex",
}

NUM = r"(-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?%?)"

PATTERNS = [
    ("kv_equals", re.compile(r"\b([A-Za-z_][A-Za-z0-9_.\-]*)\s*=\s*" + NUM)),
    ("yaml_like", re.compile(r"^\s*[\"']?([A-Za-z_][\w\-]*)[\"']?\s*[:：]\s*"
                             + NUM + r"\s*(?:[#;].*)?$")),
    ("cn_prose", re.compile(r"([\u4e00-\u9fffA-Za-z]{2,12})\s*"
                            r"(?:为|是|取|等于|设置为|设定为)\s*[:：]?\s*" + NUM)),
    ("en_prose", re.compile(r"\b([a-z][a-z_ ]{1,24}?)\s+"
                            r"(?:is|are|was|equals?|set to)\s+" + NUM + r"\b")),
]

# 键名归一化别名表（小写后查表）
ALIASES = {
    "epoch": "epochs", "epochs": "epochs", "num_epochs": "epochs",
    "n_epochs": "epochs", "total_epochs": "epochs", "max_epochs": "epochs",
    "轮数": "epochs", "训练轮数": "epochs", "训练轮次": "epochs",
    "lr": "lr", "learning_rate": "lr", "learning rate": "lr", "学习率": "lr",
    "batch_size": "batch_size", "batchsize": "batch_size", "batch size": "batch_size",
    "batch": "batch_size", "批大小": "batch_size", "批次大小": "batch_size",
    "seed": "seed", "random_seed": "seed", "random_state": "seed", "随机种子": "seed",
    "weight_decay": "weight_decay", "权重衰减": "weight_decay",
    "dropout": "dropout",
    "warmup": "warmup", "warmup_steps": "warmup",
    "train_ratio": "train_ratio", "val_ratio": "val_ratio", "test_ratio": "test_ratio",
}

CRITICAL_KEYS = {
    "epochs", "lr", "batch_size", "seed", "weight_decay",
    "train_ratio", "val_ratio", "test_ratio",
}

# 来源优先级：数字越小越优先
SOURCE_RANK = [
    (1, "运行日志", {".log", ".out"}),
    (2, "配置文件", {".yaml", ".yml", ".json", ".toml", ".ini", ".cfg"}),
    (3, "脚本默认", {".py", ".sh"}),
    (4, "草稿/转述", {".md", ".txt", ".tex"}),
]
RANK_LABEL = {r: lbl for r, lbl, _ in SOURCE_RANK}


def source_rank(path: str):
    ext = os.path.splitext(path)[1].lower()
    for rank, _lbl, exts in SOURCE_RANK:
        if ext in exts:
            return rank
    return 5


def canon_key(raw: str) -> str:
    k = raw.strip().lower()
    return ALIASES.get(k, k)


def norm_value(raw: str):
    """数值归一化：能转 float 则按 float 比较，同时保留原始串。"""
    s = raw.strip().rstrip("%")
    try:
        return float(s)
    except ValueError:
        return s


def iter_text_files(materials_dir: str):
    paths = []
    for root, dirs, files in os.walk(materials_dir):
        dirs.sort()
        for fn in sorted(files):
            if os.path.splitext(fn)[1].lower() in TEXT_EXTS:
                ap = os.path.join(root, fn)
                paths.append((os.path.relpath(ap, materials_dir), ap))
    return sorted(paths, key=lambda x: x[0])


def extract(materials_dir: str):
    """返回 entries: list of dict(key, key_raw, value, value_raw, file, line, via)。"""
    entries = []
    for disp, ap in iter_text_files(materials_dir):
        try:
            with open(ap, "r", encoding="utf-8", errors="replace") as f:
                lines = f.read().splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines, 1):
            for via, pat in PATTERNS:
                for m in pat.finditer(line):
                    key_raw, val_raw = m.group(1), m.group(2)
                    # 过滤明显的日期/时间片段误配
                    if via == "yaml_like" and re.fullmatch(r"\d{1,2}", key_raw):
                        continue
                    entries.append({
                        "key": canon_key(key_raw),
                        "key_raw": key_raw,
                        "value": norm_value(val_raw),
                        "value_raw": val_raw,
                        "file": disp,
                        "line": i,
                        "via": via,
                    })
    return entries


def build(entries):
    # (key, file) -> {value: [(line, value_raw)]}
    by_key_file = defaultdict(lambda: defaultdict(list))
    for e in entries:
        by_key_file[(e["key"], e["file"])][e["value"]].append((e["line"], e["value_raw"]))

    observations = []
    single_sources = defaultdict(list)  # key -> list of (file, value, line, value_raw)
    for (key, fname), valmap in sorted(by_key_file.items()):
        if len(valmap) > 1:
            observations.append({
                "key": key, "file": fname,
                "values": [
                    {
                        "value_raw": sorted({r for _, r in occ})[0],
                        "lines": [ln for ln, _ in sorted(occ)],
                    }
                    for _val, occ in sorted(valmap.items(), key=lambda kv: kv[1][0][0])
                ],
                "note": "同一文件内同一键存在多个取值，视为时间序列/计数器观测，不参与冲突判定。",
            })
        else:
            (val, occ), = valmap.items()
            ln, vr = sorted(occ)[0]
            single_sources[key].append({
                "file": fname, "value": val, "value_raw": vr, "line": ln,
                "rank": source_rank(fname),
            })

    conflicts = []
    for key, srcs in sorted(single_sources.items()):
        distinct = {s["value"] for s in srcs}
        if len(srcs) >= 2 and len(distinct) >= 2:
            srcs_sorted = sorted(srcs, key=lambda s: (s["rank"], s["file"]))
            winner = srcs_sorted[0]
            conflicts.append({
                "parameter": key,
                "blocking": key in CRITICAL_KEYS,
                "sources": [
                    {"file": s["file"], "line": s["line"], "value_raw": s["value_raw"],
                     "source_type": RANK_LABEL.get(s["rank"], "其他")}
                    for s in srcs_sorted
                ],
                "suggested_rule": (
                    f"按裁决优先级（运行日志 > 配置文件 > 脚本默认 > 草稿/转述），"
                    f"建议取 {winner['file']}:{winner['line']} 的值 {winner['value_raw']}；"
                    f"正文中应双值并陈并注明该裁决依据（见 references/adjudication_rules.md）。"
                ),
                "recommended_value": winner["value_raw"],
                "recommended_source": f"{winner['file']}:{winner['line']}",
            })
    return conflicts, observations


def main(argv=None):
    ap = argparse.ArgumentParser(description="多来源参数冲突矩阵")
    ap.add_argument("--materials", required=True, help="材料目录")
    ap.add_argument("--out-dir", required=True, help="输出目录（conflicts.json / conflicts.md）")
    args = ap.parse_args(argv)

    if not os.path.isdir(args.materials):
        print(f"[conflict_matrix] ERROR: 材料目录不存在: {args.materials}", file=sys.stderr)
        return 1

    entries = extract(args.materials)
    conflicts, observations = build(entries)

    result = {
        "tool": "conflict_matrix",
        "materials_dir": os.path.abspath(args.materials),
        "pairs_extracted": len(entries),
        "conflicts": conflicts,
        "observations": observations,
        "summary": {
            "conflict_count": len(conflicts),
            "blocking_count": sum(1 for c in conflicts if c["blocking"]),
            "observation_count": len(observations),
        },
    }

    os.makedirs(args.out_dir, exist_ok=True)
    jpath = os.path.join(args.out_dir, "conflicts.json")
    mpath = os.path.join(args.out_dir, "conflicts.md")
    with open(jpath, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    lines = ["# 参数冲突矩阵", ""]
    lines.append(f"- 材料目录: `{result['materials_dir']}`")
    lines.append(f"- 抽取键值对: {len(entries)}；冲突: {len(conflicts)}；观测(非冲突): {len(observations)}")
    lines.append("")
    lines.append("## 冲突记录")
    lines.append("")
    if not conflicts:
        lines.append("未发现跨来源取值冲突。")
    for c in conflicts:
        block = "阻断" if c["blocking"] else "非阻断"
        lines.append(f"### {c['parameter']}（{block}）")
        lines.append("")
        lines.append("| 来源 | 行 | 取值 | 来源类型 |")
        lines.append("| --- | --- | --- | --- |")
        for s in c["sources"]:
            lines.append(f"| `{s['file']}` | {s['line']} | {s['value_raw']} | {s['source_type']} |")
        lines.append("")
        lines.append(f"- 建议裁决：{c['suggested_rule']}")
        lines.append("")
    lines.append("## 观测记录（同文件多值，非冲突）")
    lines.append("")
    if not observations:
        lines.append("无。")
    for o in observations:
        vs = "、".join(f"{v['value_raw']}(行{v['lines'][:3]}{'…' if len(v['lines']) > 3 else ''})"
                       for v in o["values"])
        lines.append(f"- `{o['file']}` 键 `{o['key']}`: {vs} —— {o['note']}")
    lines.append("")
    with open(mpath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"[conflict_matrix] 键值对 {len(entries)}；冲突 {len(conflicts)}；"
          f"观测 {len(observations)} -> {jpath}, {mpath}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

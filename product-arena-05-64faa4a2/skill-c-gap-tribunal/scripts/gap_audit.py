#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gap_audit.py — 方法与实验章节"六要素"材料证据缺口审计。

纯标准库、确定性、无网络。

用法：
    python3 gap_audit.py --materials <材料目录> [--draft <草稿md>] --out-dir <输出目录>

输出：
    <输出目录>/gaps.json  机器可读：每要素 evidence_status + 命中证据 file:line + 编号缺口清单
    <输出目录>/gaps.md    人读摘要

判定规则（确定性阈值，见 references/gap_taxonomy.md）：
    - 命中 0 条                                -> missing
    - 命中 >=3 条且覆盖 >=2 类探针，
      且 must 组（若定义）有命中               -> sufficient
    - 其余                                      -> thin
    每个非 sufficient 要素生成一个编号缺口 G001、G002……，附追问措辞建议。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

TEXT_EXTS = {
    ".md", ".txt", ".log", ".out", ".yaml", ".yml", ".json",
    ".py", ".sh", ".toml", ".ini", ".cfg", ".csv", ".tex",
}

MAX_HITS_PER_ELEMENT = 12

# 六要素探针表：每项 (探针名, 正则)。must 组为"该要素被判 sufficient 前必须命中的探针组"。
ELEMENTS = [
    {
        "key": "steps",
        "label": "步骤",
        "probes": [
            ("命令行", r"(?:(?:^|\s)(?:python3?|bash|sh|make)\s+\S|docker run|conda run|\.\/\S+)"),
            ("步骤编号", r"(?:步骤\s*[一二三四五六\d]|step\s*\d|^\s*\d+[\.、]\s*\S)"),
            ("流程词", r"(?:首先|其次|然后|接着|最后|预处理|训练流程|推理流程)"),
        ],
        "must": [],
        "question": "请补充方法的完整执行步骤（命令行或编号步骤）：当前材料中步骤证据{hint}，"
                    "章节若直接给出步骤将被视为无来源陈述。",
    },
    {
        "key": "setup",
        "label": "实验设置",
        "probes": [
            ("硬件/驱动", r"(?:CUDA|cuda|GPU|A100|V100|RTX\s?\d|TPU|显卡)"),
            ("框架与版本", r"(?:torch|pytorch|tensorflow|jax|python\s*3(?:\.\d+)?|transformers)"),
            ("随机性控制", r"(?:seed|随机种子|random_state|deterministic)"),
        ],
        "must": [],
        "question": "请补充实验环境信息（硬件、框架版本、随机种子）：当前材料中设置证据{hint}。",
    },
    {
        "key": "params",
        "label": "参数与来源",
        "probes": [
            ("超参数名", r"(?:lr|learning_rate|学习率|epochs?|轮次|训练轮数|batch[_ ]?size|批大小|"
                          r"weight_decay|warmup|dropout|hidden)"),
            ("参数赋值", r"(?:[A-Za-z_][\w\-]*\s*=\s*-?\d|[\u4e00-\u9fff]{2,8}\s*(?:为|取|设置为)\s*-?\d)"),
            ("来源标注", r"(?:默认值|default|官方|official|复现自|取自|following\s+\[)"),
        ],
        "must": [],
        "question": "请列出全部关键超参数及其来源（配置/日志/官方默认）：当前材料中参数证据{hint}。",
    },
    {
        "key": "dataset",
        "label": "数据集与划分",
        "probes": [
            ("数据集名", r"(?:dataset|数据集|cifar|imagenet|mnist|squad|glue|coco|wmt|corpus|语料)"),
            ("划分信息", r"(?:split|ratio|train/val|train[/_-]?test|训练集|验证集|测试集|划分|样本数)"),
            ("规模数字", r"(?:\d[\d,\.]*\s*(?:张|条|个|篇|samples?|examples?|instances))"),
        ],
        "must": [
            ("版本与获取", r"(?:版本|version\s*[\d:vV]|v\d+(?:\.\d+)+|commit|sha1?|md5|"
                             r"下载|download|https?://|获取方式)"),
        ],
        "question": "请说明数据集的确切版本与获取方式（版本号/下载链接/校验值）："
                    "当前材料仅见数据集名称或划分信息，版本证据{hint}。",
    },
    {
        "key": "baselines",
        "label": "对照",
        "probes": [
            ("基线词", r"(?:baseline|基线|对照组|对比方法|比较方法)"),
            ("消融", r"(?:ablation|消融)"),
            ("对比结果", r"(?:优于|超过|outperform|compared with|对比实验)"),
        ],
        "must": [],
        "question": "请补充对照设置（基线名称、来源与配置；是否有消融）：当前材料中对照证据{hint}。",
    },
    {
        "key": "repro",
        "label": "复现与限制",
        "probes": [
            ("复现词", r"(?:复现|reproduc|replicate)"),
            ("环境清单", r"(?:requirements\.txt|environment\.yml|dockerfile|镜像|依赖)"),
            ("限制词", r"(?:限制|局限|limitation|不适用|失效)"),
        ],
        "must": [
            ("获取途径", r"(?:数据获取|获取方式|下载|download|https?://|申请|授权)"),
        ],
        "question": "请补充复现所需的完整信息（运行命令、依赖清单、数据获取途径）："
                    "当前材料中复现证据{hint}。",
    },
]

HINT = {"sufficient": "充足", "thin": "薄弱", "missing": "缺失"}


def iter_text_files(materials_dir: str, draft: str | None):
    """产出 (显示路径, 绝对路径) 列表，确定性排序。"""
    paths = []
    if os.path.isdir(materials_dir):
        for root, dirs, files in os.walk(materials_dir):
            dirs.sort()
            for fn in sorted(files):
                ext = os.path.splitext(fn)[1].lower()
                if ext in TEXT_EXTS:
                    ap = os.path.join(root, fn)
                    paths.append((os.path.relpath(ap, materials_dir), ap))
    if draft:
        ap = os.path.abspath(draft)
        paths.append((os.path.basename(draft) + "(draft)", ap))
    # 去重（draft 可能已在目录中），按显示路径排序保证确定性
    seen = set()
    out = []
    for disp, ap in sorted(paths, key=lambda x: x[0]):
        if ap in seen:
            continue
        seen.add(ap)
        out.append((disp, ap))
    return out


def read_lines(path: str):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read().splitlines()
    except OSError:
        return []


def audit_element(elem: dict, corpus: list):
    hits = []
    matched_probes = set()
    must_hits = []
    for disp, _ap, lineno, line in corpus:
        for probe_name, pattern in elem["probes"]:
            if re.search(pattern, line, re.IGNORECASE):
                matched_probes.add(probe_name)
                if len(hits) < MAX_HITS_PER_ELEMENT:
                    hits.append({
                        "file": disp, "line": lineno,
                        "probe": probe_name,
                        "snippet": line.strip()[:120],
                    })
        for probe_name, pattern in elem.get("must", []):
            if re.search(pattern, line, re.IGNORECASE):
                if len(must_hits) < MAX_HITS_PER_ELEMENT:
                    must_hits.append({
                        "file": disp, "line": lineno,
                        "probe": probe_name,
                        "snippet": line.strip()[:120],
                    })
    n = len(hits)
    if n == 0:
        status = "missing"
    elif elem.get("must") and not must_hits:
        status = "thin"  # 有旁证但关键面向（如版本）缺失，不可判 sufficient
    elif n >= 3 and len(matched_probes) >= 2:
        status = "sufficient"
    else:
        status = "thin"
    return status, hits, must_hits


def main(argv=None):
    ap = argparse.ArgumentParser(description="六要素材料证据缺口审计")
    ap.add_argument("--materials", required=True, help="材料目录")
    ap.add_argument("--draft", default=None, help="可选草稿文件（一并纳入证据池）")
    ap.add_argument("--out-dir", required=True, help="输出目录（gaps.json / gaps.md）")
    args = ap.parse_args(argv)

    if not os.path.isdir(args.materials):
        print(f"[gap_audit] ERROR: 材料目录不存在: {args.materials}", file=sys.stderr)
        return 1

    files = iter_text_files(args.materials, args.draft)
    corpus = []  # (disp, ap, lineno, line)
    for disp, apath in files:
        for i, line in enumerate(read_lines(apath), 1):
            corpus.append((disp, apath, i, line))

    elements_out = []
    gaps = []
    gid = 0
    for elem in ELEMENTS:
        status, hits, must_hits = audit_element(elem, corpus)
        entry = {
            "key": elem["key"],
            "label": elem["label"],
            "evidence_status": status,
            "hit_count_capped": len(hits),
            "hits": hits,
        }
        if elem.get("must"):
            entry["must_satisfied"] = bool(must_hits)
            entry["must_hits"] = must_hits
        elements_out.append(entry)
        if status != "sufficient":
            gid += 1
            hint = HINT[status]
            q = elem["question"].format(hint=hint)
            if elem.get("must") and hits and not must_hits:
                must_names = "、".join(n for n, _ in elem["must"])
                q += f"（缺失面向：{must_names}）"
            gaps.append({
                "id": f"G{gid:03d}",
                "element": elem["key"],
                "element_label": elem["label"],
                "status": status,
                "question": q,
            })

    result = {
        "tool": "gap_audit",
        "materials_dir": os.path.abspath(args.materials),
        "draft": os.path.abspath(args.draft) if args.draft else None,
        "files_scanned": [disp for disp, _ in files],
        "elements": elements_out,
        "gaps": gaps,
        "summary": {
            "total_gaps": len(gaps),
            "missing": [e["key"] for e in elements_out if e["evidence_status"] == "missing"],
            "thin": [e["key"] for e in elements_out if e["evidence_status"] == "thin"],
            "sufficient": [e["key"] for e in elements_out if e["evidence_status"] == "sufficient"],
        },
    }

    os.makedirs(args.out_dir, exist_ok=True)
    jpath = os.path.join(args.out_dir, "gaps.json")
    mpath = os.path.join(args.out_dir, "gaps.md")
    with open(jpath, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    lines = ["# 六要素缺口审计报告", ""]
    lines.append(f"- 材料目录: `{result['materials_dir']}`")
    lines.append(f"- 扫描文件数: {len(files)}")
    lines.append("")
    lines.append("| 要素 | 证据状态 | 命中数(截断) |")
    lines.append("| --- | --- | --- |")
    for e in elements_out:
        lines.append(f"| {e['label']} ({e['key']}) | {e['evidence_status']} | {e['hit_count_capped']} |")
    lines.append("")
    lines.append("## 编号缺口清单（待作者确认）")
    lines.append("")
    if not gaps:
        lines.append("无缺口：六要素证据均充足。")
    for g in gaps:
        lines.append(f"- **{g['id']}** [{g['element_label']} / {g['status']}] {g['question']}")
    lines.append("")
    lines.append("## 命中证据明细（file:line）")
    for e in elements_out:
        lines.append(f"\n### {e['label']} ({e['key']}) — {e['evidence_status']}")
        for h in e["hits"]:
            lines.append(f"- `{h['file']}:{h['line']}` [{h['probe']}] {h['snippet']}")
        for h in e.get("must_hits", []):
            lines.append(f"- `{h['file']}:{h['line']}` [must:{h['probe']}] {h['snippet']}")
    lines.append("")
    with open(mpath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"[gap_audit] 扫描文件 {len(files)} 个；缺口 {len(gaps)} 个 -> {jpath}, {mpath}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

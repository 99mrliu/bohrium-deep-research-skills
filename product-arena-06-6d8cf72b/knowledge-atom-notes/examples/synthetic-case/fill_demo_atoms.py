#!/usr/bin/env python3
"""fill_demo_atoms.py -- 合成示例的 atoms.json 生成器（SYNTHETIC EXAMPLE）。

代替真实运行中 Agent 的撰写步骤：按段落锚点从 sections.json 取证据并断言
逐字性，保证示例自洽。输出标注为合成示例。
"""
import argparse
import json


def find_para(sections, needle):
    for sec in sections["sections"]:
        for para in sec["paragraphs"]:
            if needle in para["text"]:
                return para["anchor"], para["text"]
    raise SystemExit("fixture paragraph missing: " + needle)


def ev(sections, needle, quote):
    anchor, text = find_para(sections, needle)
    assert quote in text, "quote not verbatim: " + quote
    return [{"anchor": anchor, "quote": quote}]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sections", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    with open(args.sections, encoding="utf-8") as fh:
        sections = json.load(fh)

    atoms = [
        {"id": "c-01", "type": "concept", "term": "Counting Bloom Sketch",
         "aliases": ["CBS", "counting bloom sketch"],
         "definition": "一种用 4 比特计数器替换比特位的概率集合表示，支持删除（合成示例）。",
         "evidence": ev(sections, "replaces each bit",
                        "replaces each bit with a small counter")},
        {"id": "m-01", "type": "method", "term": "4-bit counter insertion/deletion",
         "purpose": "插入时递增 k 个哈希位置，删除时递减，以支持删除操作。",
         "evidence": ev(sections, "Insertion increments",
                        "Insertion increments k hash positions")},
        {"id": "f-01", "type": "finding",
         "claim": "一百万合成键下，9.6 bits/key 时假阳性率 0.9%。",
         "metric": "false positive rate", "value": "0.9 percent",
         "conditions": "uniform synthetic keys, 9.6 bits per key",
         "evidence": ev(sections, "the observed false positive rate",
                        "the observed false positive rate was 0.9 percent")},
        {"id": "f-02", "type": "finding",
         "claim": "删除 10% 键后假阳性率仍低于 1.1%。",
         "evidence": ev(sections, "Deletion of 10 percent",
                        "kept the false positive rate below 1.1 percent")},
        {"id": "l-01", "type": "limitation",
         "claim": "评测仅使用均匀合成键，未测量偏斜真实负载。",
         "scope": "evaluation workload",
         "evidence": ev(sections, "skewed real workloads",
                        "skewed real workloads were not measured")},
        {"id": "v-01", "type": "variable", "symbol": "m",
         "meaning": "计数器个数", "value": "m counters of 4 bits",
         "evidence": ev(sections, "allocates m counters", "allocates m counters of 4 bits")},
    ]
    doc = {
        "atoms": atoms,
        "merges": [],
        "contract_fields": {
            "answer": {
                "paper_card": {
                    "question": "Bloom 过滤器不支持删除，如何以较低内存代价支持删除（合成示例）。",
                    "method": "Counting Bloom Sketch：4 比特计数器 + k 哈希位置递增/递减 [m-01]",
                    "data": "一百万均匀随机合成键",
                    "main_findings": ["9.6 bits/key 时 FPR 0.9% [f-01]",
                                      "删除 10% 键后 FPR < 1.1% [f-02]"],
                    "limitations": ["仅均匀合成负载 [l-01]"],
                },
                "knowledge_points": [a["id"] for a in atoms],
            }
        },
        "sources": [{"doc_id": sections["doc_id"], "sha256": sections["sha256"],
                     "backend": sections["backend"]}],
        "uncertainty": [],
        "limits": ["SYNTHETIC EXAMPLE：虚构论文，仅演示接口，非正式案例结果。"],
    }
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)
    print("wrote", args.out)


if __name__ == "__main__":
    main()

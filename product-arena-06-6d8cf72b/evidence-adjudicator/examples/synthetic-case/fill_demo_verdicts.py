#!/usr/bin/env python3
"""fill_demo_verdicts.py -- 合成示例的 verdicts.json 生成器（SYNTHETIC EXAMPLE）。

代替真实运行中 Agent 的双侧检索与裁定撰写：从 chunks.json 定位证据并断言
逐字性。q3 演示 not_reported 裁定（虚构论文未报告衰减率）。
"""
import argparse
import json


def find_chunk(chunks, needle, quote):
    for ch in chunks["chunks"]:
        if needle in ch["text"] and quote in ch["text"]:
            return {"anchor": ch["anchor"], "quote": quote}
    raise SystemExit("fixture evidence missing: " + needle)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunks", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    with open(args.chunks, encoding="utf-8") as fh:
        chunks = json.load(fh)

    doc = {
        "verdicts": [
            {"q_id": "q1", "verdict": "supported",
             "answer": "在部分阴影条件下，微逆配置每 kWp 年发电量平均多 8.2%（范围 3.1%–14.7%；合成示例）。",
             "evidence_for": [find_chunk(chunks, "8.2 percent",
                                         "a mean of\n8.2 percent more annual energy per kWp"
                                         if "a mean of\n8.2 percent" in "".join(
                                             c["text"] for c in chunks["chunks"])
                                         else "8.2 percent more annual energy per kWp")],
             "evidence_against": [],
             "searched": {"for": ["micro-inverter", "8.2", "annual energy"],
                          "against": ["no gain", "lower yield", "worse"]},
             "reason": "Results 节直接报告 24 屋顶平均增益 8.2%，条件为部分阴影仿真。"},
            {"q_id": "q2", "verdict": "supported",
             "answer": "无遮挡参考屋顶上差异为 0.4%，在仿真容差之内（即无实质差异）。",
             "evidence_for": [find_chunk(chunks, "0.4 percent",
                                         "the difference was 0.4 percent")],
             "evidence_against": [],
             "searched": {"for": ["unshaded", "reference roofs", "0.4"],
                          "against": ["shaded", "large difference"]},
             "reason": "Results 节明确给出 0.4% 且声明在容差内。"},
            {"q_id": "q3", "verdict": "not_reported",
             "answer": None,
             "evidence_for": [],
             "evidence_against": [],
             "searched": {"for": ["degradation", "衰减", "annual degradation rate",
                                  "per year", "aging"],
                          "against": []},
             "reason": "全文未出现 degradation/衰减率相关表述；仿真期为单一合成年，"
                       "且 Setup/Results/Discussion 均未涉及逐年性能衰减。"},
        ],
        "contract_fields": {
            "answer": {
                "q1": "部分阴影下微逆每 kWp 年发电量平均高 8.2%（范围 3.1%–14.7%）。",
                "q2": "无遮挡屋顶差异 0.4%，在仿真容差内。",
                "q3": None,
            }
        },
        "sources": [{"doc_id": chunks["doc_id"], "sha256": chunks["sha256"],
                     "backend": chunks["backend"]}],
        "uncertainty": ["q3 为 not_reported：已检索 degradation/aging 等词，"
                        "范围为全部窗口（合成示例）。"],
        "limits": ["SYNTHETIC EXAMPLE：虚构论文，仅演示接口，非正式案例结果。"],
    }
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)
    print("wrote", args.out)


if __name__ == "__main__":
    main()

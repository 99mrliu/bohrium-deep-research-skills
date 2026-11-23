#!/usr/bin/env python3
"""fill_demo_notes.py -- 合成示例的 notes.json + result.json 生成器。

代替真实运行中 Agent 的撰写步骤；断言所有锚点文本在虚构论文中逐字存在。
SYNTHETIC EXAMPLE，非正式案例结果。
"""
import argparse
import json
import re


def anchor_of(text, needle):
    for pno, page in enumerate(text.split("\f"), start=1):
        for lno, line in enumerate(page.splitlines(), start=1):
            if needle in line:
                return "p%d-l%d" % (pno, lno), line.strip()
    raise SystemExit("fixture line missing: " + needle)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--paper", required=True)
    ap.add_argument("--case", required=True)
    ap.add_argument("--out-notes", required=True)
    ap.add_argument("--out-result", required=True)
    args = ap.parse_args()
    with open(args.paper, encoding="utf-8") as fh:
        text = fh.read()

    a_cost, _ = anchor_of(text, "14 USD per unit")
    a_pkt, _ = anchor_of(text, "96 percent packet delivery")
    a_drift, _ = anchor_of(text, "2.1 percent of reading against")
    a_lim, _ = anchor_of(text, "Saline soils were not")

    notes = {
        "title": "Low-cost soil moisture sensor network for smallholder plots（合成示例笔记）",
        "card": {
            "研究问题": "小农地块灌溉决策受限于土壤湿度传感器成本",
            "方法": {"value": "12 节点电容式传感网络，LoRa 回传，15 分钟采样", "anchor": a_pkt},
            "成本": {"value": "14 USD/节点（不含网关）", "anchor": a_cost},
            "主要发现": {"value": "整季数据包送达率 96%；一季漂移 2.1%", "anchor": a_drift},
        },
        "sections": [
            {"heading": "1. Introduction", "body": "低成本传感是小农灌溉决策的瓶颈。",
             "anchors": [a_cost]},
            {"heading": "3. Findings", "body": "送达率 96%，漂移 2.1%，44 次灌溉事件中 41 次在一个采样间隔内被检出。",
             "anchors": [a_pkt, a_drift]},
            {"heading": "4. Limitations", "body": "单季三块地，盐碱土未测，成本不含网关。",
             "anchors": [a_lim]},
        ],
        "comparison": {"columns": ["指标", "数值", "条件"],
                       "rows": [["packet delivery", "96%", "16 周整季"],
                                ["drift", "2.1% of reading", "对照烘干法"],
                                ["node cost", "14 USD", "不含网关"]]},
        "open_questions": ["多季耐久性与盐碱土适用性未验证"],
        "limits": ["SYNTHETIC EXAMPLE：虚构论文，仅演示接口，非正式案例结果。"],
        "change_records": [],
    }
    with open(args.out_notes, "w", encoding="utf-8") as fh:
        json.dump(notes, fh, ensure_ascii=False, indent=2)

    result = {
        "case_id": json.load(open(args.case, encoding="utf-8"))["case_id"],
        "answer": {
            "notes_summary": "12 节点低成本土壤湿度网络在 3 块小农地块完成一季监测："
                             "送达率 96%、漂移 2.1%；多季耐久性未验证（合成示例）。",
            "key_metrics": [
                {"name": "packet delivery", "value": "96%", "anchor": a_pkt},
                {"name": "drift", "value": "2.1% of reading", "anchor": a_drift},
            ],
        },
        "status": "success",
        "sources": [{"path": "paper.txt (synthetic fixture)"}],
        "uncertainty": [],
        "limits": notes["limits"],
    }
    with open(args.out_result, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
    print("wrote notes + result")


if __name__ == "__main__":
    main()

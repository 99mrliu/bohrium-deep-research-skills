#!/usr/bin/env python3
"""fill_demo_draft.py -- 合成示例草稿生成器（SYNTHETIC EXAMPLE）。

stage=draft：刻意含两处违规（unit 不在 enum；open_question 为 null 且无理由），
stage=repaired：修复后版本。内容摘自虚构论文 paper.txt。
"""
import argparse
import json

BASE = {
    "case_id": "synthetic-contract-pilot-demo",
    "answer": {
        "summary": "竹纤维复合板（12 mm）三点弯曲强度均值 48 MPa，1 kHz 吸声系数 0.62"
                   "（合成示例摘要）。",
        "measurements": [
            {"name": "bending strength", "value": 48, "unit": "MPa"},
            {"name": "panel thickness", "value": 12, "unit": "mm"},
        ],
        "open_question": None,
    },
    "status": "in_progress",
    "evidence": {
        "summary": "Mean bending strength was 48 MPa (n = 5, sd = 4)",
        "open_question": "durability under humidity cycling remains an open question",
    },
    "limits": ["SYNTHETIC EXAMPLE：虚构论文，仅演示接口，非正式案例结果。"],
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--stage", choices=["draft", "repaired"], required=True)
    args = ap.parse_args()
    doc = json.loads(json.dumps(BASE))
    if args.stage == "draft":
        doc["answer"]["measurements"][1]["unit"] = "millimetre"  # enum 违规（故意）
        doc["null_reasons"] = {}  # open_question 为 null 且无理由（故意）
        doc["status"] = "success"  # 假 success（故意，validate 必须抓出）
    else:
        doc["null_reasons"] = {
            "$.answer.open_question": "正文中 open question 已由结论段命名"
            "（humidity cycling durability），无其他未答问题；字段按要求留 null。"
        }
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)
    print("wrote", args.out, "stage:", args.stage)


if __name__ == "__main__":
    main()

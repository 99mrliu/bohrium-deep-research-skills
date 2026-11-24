#!/usr/bin/env python3
"""make_fixture.py — 生成【合成示例】输入夹具（虚构资料库，非正式案例）。"""
import json
import os
import sys

DOC1 = """课题组数据说明（虚构）
样品 BAT-11 的首次库仑效率为 89.3%。
测试温度 25 摄氏度，倍率 0.1C。
"""

DOC2 = """补充记录（虚构）
BAT-11 循环 200 次后容量保持率 93.5%。
"""


def main():
    root = sys.argv[1]
    inp = os.path.join(root, "input")
    os.makedirs(os.path.join(inp, "docs"), exist_ok=True)
    with open(os.path.join(inp, "docs", "bat11_notes.txt"), "w") as f:
        f.write(DOC1)
    with open(os.path.join(inp, "docs", "bat11_cycle.txt"), "w") as f:
        f.write(DOC2)
    case = {
        "case_id": "synthetic-ledger-001",
        "questions": [
            {"question_id": "q1", "question": "BAT-11 的首次库仑效率是多少？"},
        ],
        "output_contract": {"fields": ["case_id", "answers", "sources", "uncertainty",
                                       "change_log", "status"]},
    }
    with open(os.path.join(inp, "case.json"), "w") as f:
        json.dump(case, f, ensure_ascii=False, indent=2)
    with open(os.path.join(inp, "task.md"), "w") as f:
        f.write("# 合成示例任务\n回答问题并交付可复核的过程记录。\n")
    print("fixture ready at", inp)


if __name__ == "__main__":
    main()

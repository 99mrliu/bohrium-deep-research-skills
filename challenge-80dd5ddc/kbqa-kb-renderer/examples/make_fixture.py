#!/usr/bin/env python3
"""make_fixture.py — 生成【合成示例】输入夹具（虚构资料库，非正式案例）。"""
import json
import os
import sys

PAPER = """研究简报：二维材料 MoS2 的光电响应（虚构）
器件 DEV-3 在 532 nm 激光下的响应度为 120 A/W。
响应时间 0.8 ms，探测率 1.2e11 Jones。
"""

NOTE = """测试备注（虚构）
DEV-3 的数据为暗态扣除后的净值。
532 nm 对应的功率密度为 5 mW/cm²。
"""


def main():
    root = sys.argv[1]
    inp = os.path.join(root, "input")
    os.makedirs(os.path.join(inp, "notes"), exist_ok=True)
    with open(os.path.join(inp, "dev3_brief.txt"), "w") as f:
        f.write(PAPER)
    with open(os.path.join(inp, "notes", "test_notes.txt"), "w") as f:
        f.write(NOTE)
    with open(os.path.join(inp, "notes", "test_notes_副本.txt"), "w") as f:
        f.write(NOTE)  # 字节级重复副本
    case = {
        "case_id": "synthetic-render-001",
        "questions": [
            {"question_id": "q1", "question": "DEV-3 在 532 nm 下的响应度是多少？"},
        ],
        "output_contract": {"fields": ["case_id", "answers", "sources", "uncertainty",
                                       "change_log", "status"]},
    }
    with open(os.path.join(inp, "case.json"), "w") as f:
        json.dump(case, f, ensure_ascii=False, indent=2)
    with open(os.path.join(inp, "task.md"), "w") as f:
        f.write("# 合成示例任务\n整理资料库并回答问题，交付可导航交接包。\n")
    print("fixture ready at", inp)


if __name__ == "__main__":
    main()

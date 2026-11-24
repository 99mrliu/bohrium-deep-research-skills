#!/usr/bin/env python3
"""make_fixture.py — 生成【合成示例】输入夹具（虚构资料库，非正式案例）。"""
import json
import os
import sys

R1 = """催化剂评价报告（第一版，虚构）
催化剂 CAT-9 在 400 摄氏度下 CO 转化率为 78%。
空速 30000 h-1，反应压力 0.1 MPa。
"""

R2 = """催化剂评价报告（修订版，虚构）
催化剂 CAT-9 在 400 摄氏度下 CO 转化率更正为 85%。
空速 30000 h-1，反应压力 0.1 MPa。
修订原因：第一版色谱积分参数有误。
"""

NOTES = """版本备注（虚构）
reports/cat9_v2.txt 为当前有效版本。
reports/cat9_v1.txt 已作废。
"""


def main():
    root = sys.argv[1]
    inp = os.path.join(root, "input")
    os.makedirs(os.path.join(inp, "reports"), exist_ok=True)
    with open(os.path.join(inp, "reports", "cat9_v1.txt"), "w") as f:
        f.write(R1)
    with open(os.path.join(inp, "reports", "cat9_v2.txt"), "w") as f:
        f.write(R2)
    with open(os.path.join(inp, "reports", "版本备注.txt"), "w") as f:
        f.write(NOTES)
    case = {
        "case_id": "synthetic-court-001",
        "questions": [
            {"question_id": "q1", "question": "CAT-9 在 400 摄氏度下的 CO 转化率是多少？"},
            {"question_id": "q2", "question": "CAT-9 的水热稳定性测试结果如何？"},
        ],
        "output_contract": {"fields": ["case_id", "answers", "sources", "uncertainty",
                                       "change_log", "status"]},
    }
    with open(os.path.join(inp, "case.json"), "w") as f:
        json.dump(case, f, ensure_ascii=False, indent=2)
    with open(os.path.join(inp, "task.md"), "w") as f:
        f.write("# 合成示例任务\n按充分性等级回答 case.json 中的问题。\n")
    print("fixture ready at", inp)


if __name__ == "__main__":
    main()

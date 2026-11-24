#!/usr/bin/env python3
"""make_fixture.py — 生成【合成示例】输入夹具（虚构资料库，非正式案例）。

用法：python3 make_fixture.py <目标目录>
"""
import json
import os
import sys

REPORT = """实验报告：固态电解质界面阻抗研究（虚构数据）
样品 SE-07，采用阻塞电极构型测量。
25 摄氏度下界面阻抗为 182 Ω·cm²。
60 摄氏度下界面阻抗降至 45 Ω·cm²。
活化能拟合结果为 0.62 eV。
结论：界面阻抗随温度升高显著下降。
"""

MEMO = """组内备忘录（虚构）
SE-07 的 25 摄氏度数据为三次重复测量的均值。
循环伏安数据尚未整理入库，预计下周补充。
"""

CSV = """temp_C,impedance_ohm_cm2
25,182
40,98
60,45
"""


def main():
    root = sys.argv[1]
    inp = os.path.join(root, "input")
    os.makedirs(os.path.join(inp, "reports"), exist_ok=True)
    os.makedirs(os.path.join(inp, "data"), exist_ok=True)
    with open(os.path.join(inp, "reports", "se07_report.txt"), "w") as f:
        f.write(REPORT)
    with open(os.path.join(inp, "reports", "memo.txt"), "w") as f:
        f.write(MEMO)
    with open(os.path.join(inp, "data", "impedance.csv"), "w") as f:
        f.write(CSV)
    case = {
        "case_id": "synthetic-forge-001",
        "questions": [
            {"question_id": "q1", "question": "SE-07 在 60 摄氏度下的界面阻抗是多少？"},
            {"question_id": "q2", "question": "循环伏安测试的扫描速率是多少？"},
        ],
        "output_contract": {"fields": ["case_id", "answers", "sources", "uncertainty",
                                       "change_log", "status"]},
    }
    with open(os.path.join(inp, "case.json"), "w") as f:
        json.dump(case, f, ensure_ascii=False, indent=2)
    with open(os.path.join(inp, "task.md"), "w") as f:
        f.write("# 合成示例任务\n回答 case.json 中的问题，全部论断须带逐字引文。\n")
    print("fixture ready at", inp)


if __name__ == "__main__":
    main()

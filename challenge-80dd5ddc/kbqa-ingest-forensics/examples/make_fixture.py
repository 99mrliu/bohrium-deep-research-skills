#!/usr/bin/env python3
"""make_fixture.py — 生成【合成示例】输入夹具（虚构科研资料库，非正式案例）。

用法：python3 make_fixture.py <目标目录>
在 <目标目录>/input 下生成：case.json、task.md、一个含重复副本、历史版本、
行政版本备注与不可读文件的小型虚构资料库。所有内容均为虚构。
"""
import json
import os
import sys

V1 = """实验报告：钙钛矿太阳能电池稳定性测试（第一版）
样品编号 PSC-042，批次 2024-03。
初始转换效率 23.1%，在 85 摄氏度氮气环境下老化。
500 小时后效率保持率 91.2%。
结论：器件稳定性满足室内应用要求。
"""

V2 = """实验报告：钙钛矿太阳能电池稳定性测试（修订版）
样品编号 PSC-042，批次 2024-03。
初始转换效率更正为 24.6%，在 85 摄氏度氮气环境下老化。
500 小时后效率保持率 91.2%。
1000 小时后效率保持率 87.4%。
结论：器件稳定性满足室内应用要求，数据以本版为准。
"""

NOTES = """资料库版本说明（行政备注）
1. papers/report_v2.txt 为当前有效版本，数据以该版为准。
2. papers/report_v1.txt 已作废，仅归档保留。
3. data/results.csv 与 v2 报告对应。
"""

CSV = """hour,efficiency_pct
0,24.6
100,24.1
500,22.4
1000,21.5
"""


def main():
    root = sys.argv[1]
    inp = os.path.join(root, "input")
    os.makedirs(os.path.join(inp, "papers"), exist_ok=True)
    os.makedirs(os.path.join(inp, "data"), exist_ok=True)
    os.makedirs(os.path.join(inp, "notes"), exist_ok=True)
    with open(os.path.join(inp, "papers", "report_v1.txt"), "w") as f:
        f.write(V1)
    with open(os.path.join(inp, "papers", "report_v2.txt"), "w") as f:
        f.write(V2)
    with open(os.path.join(inp, "papers", "copy_of_report_v2.txt"), "w") as f:
        f.write(V2)  # 字节级重复副本
    with open(os.path.join(inp, "notes", "版本说明.txt"), "w") as f:
        f.write(NOTES)
    with open(os.path.join(inp, "data", "results.csv"), "w") as f:
        f.write(CSV)
    locked = os.path.join(inp, "data", "locked_raw.bin")
    with open(locked, "wb") as f:
        f.write(b"\x00\x01\x02synthetic")
    os.chmod(locked, 0)  # 模拟权限受限（合成）
    case = {
        "case_id": "synthetic-demo-001",
        "questions": [
            {"question_id": "q1", "question": "PSC-042 样品 500 小时后的效率保持率是多少？"},
            {"question_id": "q2", "question": "当前有效版本报告的初始转换效率是多少？"},
        ],
        "output_contract": {"fields": ["case_id", "answers", "catalog", "repair_ledger",
                                       "sources", "uncertainty", "change_log", "status"]},
    }
    with open(os.path.join(inp, "case.json"), "w") as f:
        json.dump(case, f, ensure_ascii=False, indent=2)
    with open(os.path.join(inp, "task.md"), "w") as f:
        f.write("# 合成示例任务\n盘点资料库，回答 case.json 中的问题，交付编目与修复台账。\n")
    print("fixture ready at", inp)


if __name__ == "__main__":
    main()

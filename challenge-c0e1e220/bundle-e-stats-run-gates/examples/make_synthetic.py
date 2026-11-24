#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_synthetic — 生成【合成示例】数据（明确标注：全部数值为人工合成，非真实实验数据）。

产物（写入 --out 目录）：
  synthetic_vinegar.csv   两组（control/treatment）小样本产率数据，含 2 个缺失、1 行完全重复、2 个温和离群点
  synthetic_vinegar.db    同内容 SQLite（现场生成，演示 TEXT 存数值的兼容性核对）
  case.json               output_contract 与 SPEC 三案例一致
  task.md                 任务说明（含单位）
  plan.json               演示用分析计划（也可省略让 pipeline 自动判定）
"""
import argparse
import csv
import json
import os
import random
import sqlite3


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    rng = random.Random(20240501)

    rows = []
    # control: N(50, 5), treatment: N(55, 6)，合成
    for i in range(24):
        rows.append(["control", "%.2f" % rng.gauss(50.0, 5.0)])
    for i in range(22):
        rows.append(["treatment", "%.2f" % rng.gauss(55.0, 6.0)])
    # 埋入数据质量特征
    rows[3][1] = "NA"          # 缺失 token
    rows[10][1] = ""           # 空缺失
    rows.append(list(rows[5]))  # 完全重复行
    rows[7][1] = "82.50"       # 温和离群
    rows[40][1] = "21.30"      # 温和离群

    csv_path = os.path.join(args.out, "synthetic_vinegar.csv")
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["group", "yield_rate"])
        w.writerows(rows)

    db_path = os.path.join(args.out, "synthetic_vinegar.db")
    if os.path.exists(db_path):
        os.remove(db_path)
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    cur.execute("CREATE TABLE vinegar (c0 TEXT, c1 TEXT)")
    cur.executemany("INSERT INTO vinegar VALUES (?, ?)", rows)
    con.commit()
    con.close()

    case = {
        "case_id": "case-synthetic-vinegar-demo",
        "dataset": "Synthetic vinegar yield (SYNTHETIC, 47 rows x 2 cols)",
        "source": "make_synthetic.py 人工合成（seed=20240501），非真实实验数据",
        "data_files": ["synthetic_vinegar.csv", "synthetic_vinegar.db"],
        "output_contract": {
            "required_fields": ["case_id", "status", "cleaning", "descriptive", "hypothesis_test",
                                "effect_size", "confidence_interval", "interpretation", "limitations"]
        },
        "constraints": {"alpha": 0.05},
    }
    with open(os.path.join(args.out, "case.json"), "w", encoding="utf-8") as f:
        json.dump(case, f, ensure_ascii=False, indent=2)
        f.write("\n")

    task = """# 案例任务：合成食醋产率对比（合成示例）

数据为 synthetic_vinegar.csv（含表头：group, yield_rate，单位 %）及同源 SQLite（synthetic_vinegar.db，数值以 TEXT 存储）。
本数据集为 make_synthetic.py 人工合成，仅用于演示 stats-run-gates 工作流。

任务：
1. 数据质量审计（缺失、重复、异常值）与 CSV/SQLite 一致性核对。
2. 比较 control 与 treatment 两组的产率差异，说明检验方法选择依据。
3. 给出效应量（Hedges g）与 95% 置信区间。
4. 区分统计显著与实际意义，给出规范解释。
"""
    with open(os.path.join(args.out, "task.md"), "w", encoding="utf-8") as f:
        f.write(task)

    plan = {"group_column": "group", "outcomes": ["yield_rate"], "unit": "%"}
    with open(os.path.join(args.out, "plan.json"), "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print("SYNTHETIC OK: %s（合成示例数据，47 行 × 2 列 + db + case.json + task.md + plan.json）" % args.out)


if __name__ == "__main__":
    main()

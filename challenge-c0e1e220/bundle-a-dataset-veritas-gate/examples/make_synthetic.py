#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_synthetic — 现场生成**合成示例数据**（非真实实验数据，仅用于演示与测试）。

生成到目标目录：
  plants.csv  30 行（含表头）：id,group,height_cm,notes
              · 2 行完全重复（验证 dedupe_keep_first）
              · 3 个缺失 token（NA / 空 / -，验证 report_and_exclude）
              · 1 个 IQR 异常值（height_cm=45.8，验证 flag-only）
  plants.db   同一份数据的 SQLite 版，但 height_cm 以 TEXT affinity 存储
              （制造 numeric-in-text 类型陷阱，验证 source_audit 识别能力）
  case.json   output_contract 与 SPEC 相同的 9 个必备字段
  task.md     合成示例任务说明（含单位口径）

用法：python3 make_synthetic.py --out DIR
"""
import argparse
import json
import os
import sqlite3

HEADER = ["id", "group", "height_cm", "notes"]

# 29 行数据（+1 表头 = 30 行）。行内注释标明埋的雷。
ROWS = [
    ["p001", "control", "21.3", "ok"],
    ["p002", "control", "22.8", "ok"],
    ["p003", "control", "20.5", "ok"],
    ["p004", "control", "23.1", "ok"],
    ["p005", "control", "21.9", "ok"],
    ["p006", "control", "22.4", "ok"],
    ["p007", "control", "NA", "leaf bent"],        # 缺失 token 1（height_cm）
    ["p008", "control", "24.0", "ok"],
    ["p009", "control", "20.8", "ok"],
    ["p010", "control", "23.5", "ok"],
    ["p011", "control", "21.2", ""],               # 缺失 token 2（notes 空串）
    ["p012", "control", "22.6", "ok"],
    ["p013", "control", "21.7", "ok"],
    ["p014", "control", "23.9", "ok"],
    ["t001", "treatment", "27.4", "ok"],
    ["t002", "treatment", "28.9", "ok"],
    ["t003", "treatment", "26.8", "ok"],
    ["t004", "treatment", "29.5", "ok"],
    ["t005", "treatment", "27.1", "ok"],
    ["t006", "treatment", "-", "ok"],              # 缺失 token 3（height_cm）
    ["t007", "treatment", "28.3", "ok"],
    ["t008", "treatment", "30.2", "ok"],
    ["t009", "treatment", "26.5", "ok"],
    ["t010", "treatment", "29.0", "ok"],
    ["t011", "treatment", "45.8", "greenhouse error?"],  # IQR 异常值
    ["t012", "treatment", "27.8", "ok"],
    ["t013", "treatment", "28.6", "ok"],
    ["p003", "control", "20.5", "ok"],             # 完全重复 1（= 第 3 行）
    ["t002", "treatment", "28.9", "ok"],           # 完全重复 2（= 第 16 行）
]

CASE = {
    "case_id": "case-plants-synthetic",
    "dataset": "Synthetic plant heights (SYNTHETIC demo, 29 records)",
    "source": "make_synthetic.py 现场生成；合成示例，非真实实验数据",
    "data_files": ["plants.csv", "plants.db"],
    "output_contract": {
        "required_fields": ["case_id", "status", "cleaning", "descriptive",
                            "hypothesis_test", "effect_size", "confidence_interval",
                            "interpretation", "limitations"]
    },
    "constraints": {"alpha": 0.05, "missing_policy": "report_and_exclude",
                    "duplicate_policy": "dedupe_exact_keep_first"},
}

TASK = """# 案例任务：植物株高处理效应分析（合成示例数据）

> 本案例为 make_synthetic.py 生成的**合成示例数据**，仅用于演示与测试，非真实实验。

数据：plants.csv（有表头）与同数据 plants.db（注意：库中 height_cm 以 TEXT 存储）。
字段（单位）：id（编号）、group（处理组 control/treatment）、height_cm（cm）、notes（备注）。

任务：
1. 数据质量审计：缺失、重复、异常值；CSV 与 SQLite 跨源一致性；数据库字段类型口径。
2. 比较 control 与 treatment 两组在 height_cm 上的差异。
3. 说明检验方法选择依据；给出效应量与 95% 置信区间。
4. 区分统计显著与实际意义，给出规范解释。
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="输出目录（将包含 plants.csv/plants.db/case.json/task.md）")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    csv_path = os.path.join(args.out, "plants.csv")
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        f.write(",".join(HEADER) + "\n")
        for r in ROWS:
            f.write(",".join(r) + "\n")

    db_path = os.path.join(args.out, "plants.db")
    if os.path.exists(db_path):
        os.remove(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    # 故意全部声明为 TEXT：height_cm 以 TEXT affinity 存数值（类型陷阱）
    cur.execute('CREATE TABLE plants (id TEXT, "group" TEXT, height_cm TEXT, notes TEXT)')
    cur.executemany('INSERT INTO plants VALUES (?,?,?,?)',
                    [[None if c == "" else c for c in r] for r in ROWS])
    conn.commit()
    conn.close()

    with open(os.path.join(args.out, "case.json"), "w", encoding="utf-8") as f:
        json.dump(CASE, f, ensure_ascii=False, indent=2)
    with open(os.path.join(args.out, "task.md"), "w", encoding="utf-8") as f:
        f.write(TASK)

    print(f"[make_synthetic] 合成示例数据已生成 → {args.out}")
    print(f"  plants.csv: 30 行（含表头），埋雷：2 完全重复 / 3 缺失 token / 1 IQR 异常值")
    print(f"  plants.db : 同数据 29 行，height_cm 为 TEXT affinity（numeric-in-text 陷阱）")


if __name__ == "__main__":
    main()
